# `clone()`, `Cloneable`, and the Limitations of Default Copying in Java

**Object copying** is creating another object from the state of an existing object. In Java, the `Object.clone()` method provides an object-level copying mechanism, but it **does not automatically create a deep copy** of the entire reference graph. The `Cloneable` interface also has a special meaning: it is a **marker interface** and does not declare a `clone()` method at all.

A newly shallow-copied object can carry the same primitive fields as the original while still **sharing references to the same child objects**, such as the same `ArrayList`, `Address`, or array elements. If learners understand `clone()` to mean "creating everything completely new", a small change on the copy can unintentionally mutate the original data.

This lesson belongs to **Java core - class-object**, in the **Object Class** group. The content targets **Java 17+**, distinguishing object identity from state, how `Object.clone()` works, `protected` access, the checked exception `CloneNotSupportedException`, cases involving arrays, inheritance, mutable fields, `final` fields, cyclic structures, and the **copy constructor**, **copy factory**, and **immutable value object** approaches. All standalone examples list the file name, run command, and stdout for comparison.

## 1. Copying Needs to Clarify "What Is Being Copied?"

Given two variables:

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;
~~~

This is a valid illustrative Java snippet. It **does not copy the object**: both variables reference the same `StringBuilder`. The statement `second.append("B")` causes the content accessed through `first` to become `"AB"`.

If a new object is created:

~~~java
StringBuilder second = new StringBuilder(first.toString());
~~~

in a context where the corresponding `first` variable exists, `second` is now an independent object, even though it has the same initial content.

When copying an object with multiple fields, you need to answer:

- **Identity:** Is the new object distinct from the original object? Usually, `copy != original` must hold.
- **Values:** Which primitive fields and business data are preserved?
- **References:** Does the new object still share reference fields with the original object?
- **Ownership:** Which child objects must be copied and which should be shared?
- **Invariant:** Are the constructor and business constraints preserved after copying?
- **Independence:** Is modifying the copy allowed to affect the original?

"Copy" only has a well-defined meaning when the **copying contract** answers the questions above. `clone()` cannot infer the ownership of every kind of field on its own.

## 2. `Object.clone()`: Signature and Basic Meaning

In `java.lang.Object`, the method has the API signature:

~~~java
protected native Object clone() throws CloneNotSupportedException;
~~~

This is the **JDK signature declaration**, not code to place into your own class and compile as-is. Key components to remember:

| Component | Meaning |
| --- | --- |
| `protected` | Not a public API for every caller on every object |
| `native` | Platform implementation provided by the JVM/JDK |
| Returns `Object` | Very broad return type at the superclass level |
| `throws CloneNotSupportedException` | Can fail if the object does not support cloning according to the rules |
| Not `final` | Subclasses can override it to expose an appropriate contract |

For an object whose class implements `Cloneable`, the `Object.clone()` implementation normally creates a **new object of the same runtime class**, copies the contents of its fields at the appropriate level, and returns it. Primitive fields are copied by value; for reference fields, the **reference value** is copied. Therefore, the default copy is a **shallow copy**.

For an object that does not implement `Cloneable`, calling `Object.clone()` on that object normally results in **`CloneNotSupportedException`**. Java has no automatic `new Object(...)` equivalent for all objects because many classes hold invariants or resources that cannot be copied simply.

**Important:** `Object.clone()` does not invoke the constructor of the new object's class through the normal instantiation path. Therefore, you cannot rely on validation or side effects in the constructor to "re-run" during cloning.

## 3. `Cloneable` Is a Marker Interface and Does Not Declare `clone()`

`java.lang.Cloneable` is an interface **with no methods**. It serves as a **marker** telling the `Object.clone()` mechanism that the class permits this object-level copy operation.

~~~java
final class Ticket implements Cloneable {
    private final int number;

    Ticket(int number) {
        this.number = number;
    }

    int number() {
        return number;
    }

    @Override
    public Ticket clone() {
        try {
            return (Ticket) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
~~~

This is a **complete Java class** that can be used by a class containing `main` in the same package. `Ticket` declares `implements Cloneable` so that `Object.clone()` has a basis to perform the copy operation, while overriding the method itself to **widen access to `public`** and return the concrete type `Ticket`.

Because `Cloneable` does not declare `clone`, writing `implements Cloneable` on a class **does not automatically make `object.clone()` a public call**. If a class does not expose a public clone method, external callers may not be able to call `clone()` even if the object is marked `Cloneable`.

The `final int number` field in the example is a primitive. Its numeric value is copied, but the clone operation does not re-run the `Ticket(int)` constructor.

## 4. Complete Program 1 — Basic Clone and Identity

Create the file **`SimpleCloneDemo.java`**:

~~~java
final class Point implements Cloneable {
    private int x;
    private int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    void move(int dx, int dy) {
        x += dx;
        y += dy;
    }

    @Override
    public Point clone() {
        try {
            return (Point) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return "(" + x + "," + y + ")";
    }
}

public class SimpleCloneDemo {
    public static void main(String[] args) {
        Point source = new Point(2, 3);
        Point copy = source.clone();

        System.out.println("same reference=" + (source == copy));
        System.out.println("source=" + source);
        System.out.println("copy=" + copy);

        copy.move(5, -1);
        System.out.println("after source=" + source);
        System.out.println("after copy=" + copy);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 SimpleCloneDemo.java
java SimpleCloneDemo
~~~

**Exact stdout:**

~~~text
same reference=false
source=(2,3)
copy=(2,3)
after source=(2,3)
after copy=(7,2)
~~~

With the two primitive fields `x` and `y`, a shallow clone is **sufficient** for the two objects to be independent in this state: both instances have the same initial values, yet modifying fields on the copy does not affect the source.

You should not infer that `clone()` is always this independent when a class holds a `List`, `Date`, `StringBuilder`, an array, or mutable child objects.

## 5. Without `Cloneable`: What Actually Happens?

If a class is not marked `Cloneable` but calls `super.clone()`, `Object.clone()` checks the actual object and can throw **`CloneNotSupportedException`**.

Create the file **`NotCloneableDemo.java`**:

~~~java
class PlainRecord {
    private final int id;

    PlainRecord(int id) {
        this.id = id;
    }

    PlainRecord attemptClone()
            throws CloneNotSupportedException {
        return (PlainRecord) super.clone();
    }

    int id() {
        return id;
    }
}

public class NotCloneableDemo {
    public static void main(String[] args) {
        PlainRecord item = new PlainRecord(7);

        try {
            PlainRecord copy = item.attemptClone();
            System.out.println("copy id=" + copy.id());
        } catch (CloneNotSupportedException ex) {
            System.out.println("exception="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NotCloneableDemo.java
java NotCloneableDemo
~~~

**Stdout:**

~~~text
exception=CloneNotSupportedException
~~~

The `attemptClone()` method is a wrapper inside the subclass itself, so it is permitted to call `Object`'s `super.clone()` even though it is protected. External callers do **not** call `item.clone()` directly: that method is still not a public API exposed by `PlainRecord`.

The deciding factor is not "having a method named attemptClone". The runtime object does not implement `Cloneable`, so the `Object.clone()` mechanism rejects the operation.

When a class does **not** promise to support cloning, that may be a deliberate design choice: file/socket resources, handles, locks, lifecycle-dependent objects, and complex invariants should not be copied arbitrarily.

## 6. Shallow Copy: Copying References, Not Child Objects

Suppose a `Notebook` object holds:

~~~text
Notebook N1
    title -> "Java"
    tags  -> ArrayList A ["core"]

clone N1 using Object.clone():
    Notebook N2 (new object)
    title -> same String reference value "Java"
    tags  -> still points to ArrayList A
~~~

Structurally, a shallow clone produces `N2 != N1`, while `N2.tags == N1.tags` is true. That means:

- Adding an element to `N2.tags` is also visible through `N1.tags`.
- Reassigning the field `N2.tags = new ArrayList<>(...)` after cloning can separate the collection, provided the field is not final and the code permits it.
- Replacing the reference field `N2.title` with another string does not modify `N1.title`. `String` objects are inherently **immutable**, so sharing a String does not pose the same internal mutation risk as an ArrayList.

**Shallow copying is not inherently wrong.** It is appropriate when every referenced object is immutable, or when the design intentionally lets two objects share a dependency. It is **not** appropriate if API users are promised an independent copy of a mutable list while the implementation shares that very list.

## 7. Complete Program 2 — Seeing Aliasing After a Shallow Clone

Create the file **`ShallowCloneDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

class Notebook implements Cloneable {
    private String title;
    private List<String> tags = new ArrayList<>();

    Notebook(String title) {
        this.title = title;
    }

    void addTag(String tag) {
        tags.add(tag);
    }

    void rename(String next) {
        title = next;
    }

    List<String> tags() {
        return List.copyOf(tags);
    }

    String title() {
        return title;
    }

    boolean sharesTagsWith(Notebook other) {
        return tags == other.tags;
    }

    @Override
    public Notebook clone() {
        try {
            return (Notebook) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class ShallowCloneDemo {
    public static void main(String[] args) {
        Notebook source = new Notebook("Java");
        source.addTag("core");

        Notebook copy = source.clone();
        System.out.println("same object=" + (source == copy));
        System.out.println("same tags="
                + source.sharesTagsWith(copy));

        copy.rename("Java Copy");
        copy.addTag("oop");

        System.out.println("source title=" + source.title());
        System.out.println("copy title=" + copy.title());
        System.out.println("source tags=" + source.tags());
        System.out.println("copy tags=" + copy.tags());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ShallowCloneDemo.java
java ShallowCloneDemo
~~~

**Stdout:**

~~~text
same object=false
same tags=true
source title=Java
copy title=Java Copy
source tags=[core, oop]
copy tags=[core, oop]
~~~

`rename()` **reassigns the `title` reference field** of the copy, so it does not change the title of the source. However, `addTag()` mutates the **exact same ArrayList** referenced by both notebooks, so `oop` also appears in the source.

Even having `tags()` return `List.copyOf(tags)` so as not to expose the mutable collection directly **cannot fix the existing alias between the two Notebooks created by cloning**. The snapshot only protects callers from modifying the list through the getter.

## 8. Deep Copy: Defined by Ownership Scope

A deep copy is commonly understood as **creating new copies of mutable child objects owned by the original object**, so that meaningful changes on the copy do not affect the original. However, there is no single "standard deep clone" that applies to every Java object graph.

For example, an `Invoice` with a list of `Line` items:

~~~text
Invoice source -> List A -> Line A1 (sku="P1", qty=2)
Invoice copy   -> List B -> Line B1 (sku="P1", qty=2)
~~~

If `List A != List B` but `A1 == B1`, we have only **copied the collection**, without deep-copying its mutable elements. Only when `List A != List B` and `A1 != B1`, while the important fields of Line are copied independently, is there isolation at this level.

Some objects can be **safely shared**: `String`, immutable value objects, enum constants, class tokens, or resources intentionally shared by contract. A deep copy **does not need** to recreate every immutable object. Even copying a resource such as a connection/socket may be an invalid concept.

Therefore, when designing a deep copy, explicitly state the **ownership boundary** and **which objects need to remain independent after copying**.

## 9. Complete Program 3 — Copying a List and Each Element

Create the file **`DeepCloneDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

class Line implements Cloneable {
    private final String sku;
    private int quantity;

    Line(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    void setQuantity(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity âm");
        }
        this.quantity = quantity;
    }

    int quantity() {
        return quantity;
    }

    @Override
    public Line clone() {
        try {
            return (Line) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

class Invoice implements Cloneable {
    private List<Line> lines = new ArrayList<>();

    void add(Line line) {
        lines.add(line);
    }

    Line line(int index) {
        return lines.get(index);
    }

    boolean sharesListWith(Invoice other) {
        return lines == other.lines;
    }

    @Override
    public Invoice clone() {
        try {
            Invoice copy = (Invoice) super.clone();
            copy.lines = new ArrayList<>();
            for (Line line : lines) {
                copy.lines.add(line.clone());
            }
            return copy;
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class DeepCloneDemo {
    public static void main(String[] args) {
        Invoice source = new Invoice();
        source.add(new Line("P1", 2));

        Invoice copy = source.clone();
        copy.line(0).setQuantity(9);

        System.out.println("same invoice=" + (source == copy));
        System.out.println("same list="
                + source.sharesListWith(copy));
        System.out.println("same line="
                + (source.line(0) == copy.line(0)));
        System.out.println("source qty="
                + source.line(0).quantity());
        System.out.println("copy qty="
                + copy.line(0).quantity());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 DeepCloneDemo.java
java DeepCloneDemo
~~~

**Exact stdout:**

~~~text
same invoice=false
same list=false
same line=false
source qty=2
copy qty=9
~~~

Explanation:

1. `super.clone()` first creates a new `Invoice` whose `lines` field points to the **same list**.
2. `copy.lines = new ArrayList<>()` detaches the collection from the source.
3. The loop creates a separate `Line.clone()` for each item so no alias to a mutable element is retained.
4. `String sku` and the primitive quantity are safe under `Line`'s copying approach: String is immutable, and primitives are copied by value.
5. Modifying the quantity on the clone does not affect the source.

**Limitations:** This example is intentionally simple and single-threaded. If `Line` later gains a mutable field such as `Address` or a discount list, `Line.clone()` must also have its contract revisited. Deep copying is a **commitment across all relevant state**, not an automatic result of the `Cloneable` keyword.

## 10. Why Copying Only an `ArrayList` Is Not Necessarily a Deep Copy

All of the following **create a new list container**:

~~~java
List<Line> other = new ArrayList<>(lines);
List<Line> snapshot = List.copyOf(lines);
~~~

These are illustrative statements placed where `lines` of type `List<Line>` is present and contains no nulls. However:

- `new ArrayList<>(lines)` creates a **new mutable list** containing the **same Line references**.
- `List.copyOf(lines)` returns a **list that does not support mutating its contents through the list API**, yet it **also retains the original Line objects**. It is a **shallow** snapshot and does not guarantee that the returned list object has a distinct identity in every immutable-input case.
- If `Line` is mutable, calling `other.get(0).setQuantity(...)` or `snapshot.get(0).setQuantity(...)` can still modify the very Line held in the source list.

**A read-only collection does not mean an immutable object graph**. If you want to copy internal data into an independent value object, copy the elements or convert them into appropriate immutable DTOs/value objects.

## 11. `clone()` Does Not Run the Copied Object's Constructor

An important property of `Object.clone()`: it creates an object whose fields have been copied **without executing the normal constructor of the new object's class**.

Create the file **`CloneConstructorDemo.java`**:

~~~java
class TrackedObject implements Cloneable {
    private static int nextId;
    private final int id;

    TrackedObject() {
        id = ++nextId;
        System.out.println("constructor id=" + id);
    }

    int id() {
        return id;
    }

    @Override
    public TrackedObject clone() {
        try {
            return (TrackedObject) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class CloneConstructorDemo {
    public static void main(String[] args) {
        TrackedObject source = new TrackedObject();
        TrackedObject copy = source.clone();

        System.out.println("different objects="
                + (source != copy));
        System.out.println("source id=" + source.id());
        System.out.println("copy id=" + copy.id());

        TrackedObject next = new TrackedObject();
        System.out.println("next id=" + next.id());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CloneConstructorDemo.java
java CloneConstructorDemo
~~~

**Stdout:**

~~~text
constructor id=1
different objects=true
source id=1
copy id=1
constructor id=2
next id=2
~~~

Cloning does not print `constructor id=...` a second time, because the `TrackedObject()` constructor **is not executed for the clone**. Since the `id` field is copied as-is, **two distinct objects share the same ID**.

This is an example of a business invariant/identity violation if `id` is required to be **unique per object**. `Object.clone()` does not understand that requirement and does not automatically generate a new ID.

If a new ID is mandatory, do not assume calling `super.clone()` will automatically run the ID-assignment logic in the constructor. Design a **copy factory or a creation mechanism** with explicit ID-generation rules.

## 12. `final` Fields and Limitations on Modifying the Clone

Copying via `Object.clone()` also copies the values of `final` fields. However, `final` enforces assignment rules in Java source code: normal methods **cannot reassign** a `final` instance field after the object has been constructed.

Example:

~~~java
final class Basket implements Cloneable {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    void add(String item) {
        items.add(item);
    }

    @Override
    public Basket clone() {
        try {
            return (Basket) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
~~~

This is a valid illustrative class. After a shallow clone, `items` in both Baskets points to the same `ArrayList`. We **cannot** change this to `copy.items = new ArrayList<>(items)` in the clone method because the field is `final`.

Subtle point: **`final` locks reassignment of the field reference; it does not make the referenced object immutable.** `items.add(...)` can still mutate the list.

If a class contains `final` references to mutable objects and you want the **copy to own new data**, a copy constructor or factory that constructs the object through a constructor is a much clearer solution. Using reflection or tricks to bypass `final` just to force cloning can violate the language contract and memory model; you should not do this.

## 13. Complete Program 4 — Copy Constructor with Defensive Copy

Create the file **`CopyConstructorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class SafeBasket {
    private final String owner;
    private final List<String> items;

    SafeBasket(String owner, List<String> items) {
        this.owner = Objects.requireNonNull(owner, "owner");
        this.items = new ArrayList<>(
                Objects.requireNonNull(items, "items"));
    }

    SafeBasket(SafeBasket other) {
        this(other.owner, other.items);
    }

    void add(String item) {
        items.add(Objects.requireNonNull(item, "item"));
    }

    List<String> items() {
        return List.copyOf(items);
    }

    String owner() {
        return owner;
    }
}

public class CopyConstructorDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("book");

        SafeBasket source = new SafeBasket("An", input);
        SafeBasket copy = new SafeBasket(source);

        input.add("external");
        copy.add("pen");

        System.out.println("same=" + (source == copy));
        System.out.println("owner=" + copy.owner());
        System.out.println("source=" + source.items());
        System.out.println("copy=" + copy.items());
        System.out.println("input=" + input);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CopyConstructorDemo.java
java CopyConstructorDemo
~~~

**Stdout:**

~~~text
same=false
owner=An
source=[book]
copy=[book, pen]
input=[book, external]
~~~

Here:

- The constructor receiving `items` creates its own `ArrayList`, protecting against aliasing to the caller's collection.
- The copy constructor `SafeBasket(SafeBasket other)` **creates a new object through the normal constructor**, so final fields are initialized validly.
- `String` is immutable, so `owner` can be shared safely.
- `List<String>` uses immutable Strings; a new list container is enough for the two Baskets to be independent with respect to list changes.

**Trade-off:** A copy constructor **knows the specific target type**. If there is a hierarchy and you need to preserve the dynamic subclass, a base-type constructor does not automatically create the subclass. This is a contract that must be designed explicitly rather than assuming a copy constructor provides polymorphic cloning.

## 14. Copy Factory: Expressing Intent Instead of Forcing Everything into `clone()`

A named factory can express the exact kind of copy:

~~~java
final class AccountSnapshot {
    private final String id;
    private final long balance;

    private AccountSnapshot(String id, long balance) {
        this.id = id;
        this.balance = balance;
    }

    static AccountSnapshot of(String id, long balance) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id rỗng");
        }
        return new AccountSnapshot(id, balance);
    }

    AccountSnapshot copy() {
        return AccountSnapshot.of(id, balance);
    }

    AccountSnapshot withBalance(long next) {
        return AccountSnapshot.of(id, next);
    }

    long balance() {
        return balance;
    }
}
~~~

This is a **complete Java class**, designed to be immutable without needing to implement `Cloneable`. `copy()` creates a new object with the same data; `withBalance()` creates a **new value** with a different balance.

Some immutable value objects can even return `this` from a "copy" operation if the contract **does not require a new identity**. However, do not return `this` from an API described as a "fresh independent instance" without explicitly documenting that behavior.

**Benefits of a factory/copy constructor:** They can run validation, choose the copying policy for mutable references, use clear names, and avoid dealing with the special checked exception of `Object.clone()`.

## 15. Arrays Are a Special Case: Supporting `clone()`

Java arrays have a public `clone()` method matching the array type; array objects implement `Cloneable` and `java.io.Serializable`. Therefore:

~~~java
int[] values = {1, 2, 3};
int[] copy = values.clone();
~~~

is normal syntax, requiring neither manually implementing `Cloneable` nor catching `CloneNotSupportedException` at the call site.

One-dimensional primitive arrays: each element is a primitive value, so cloning creates a new array with independent values.

Reference arrays: cloning creates a **new array**, but the elements still point to the **same child objects**.

Multidimensional arrays: `int[][]` is actually an **array holding references to `int[]` arrays**. `matrix.clone()` only copies the **outermost** array, while the inner row arrays are shared.

Do not conclude from the convenient `array.clone()` syntax that Java recursively clones every level.

## 16. Complete Program 5 — Primitive, Reference, and Two-Dimensional Arrays

Create the file **`ArrayCloneDemo.java`**:

~~~java
public class ArrayCloneDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2};
        int[] numberCopy = numbers.clone();
        numberCopy[0] = 9;

        System.out.println("numbers[0]=" + numbers[0]);
        System.out.println("copy[0]=" + numberCopy[0]);
        System.out.println("same primitive array="
                + (numbers == numberCopy));

        StringBuilder[] labels = {
                new StringBuilder("A")
        };
        StringBuilder[] labelCopy = labels.clone();
        labelCopy[0].append("!");

        System.out.println("same reference array="
                + (labels == labelCopy));
        System.out.println("same element="
                + (labels[0] == labelCopy[0]));
        System.out.println("original label=" + labels[0]);

        int[][] grid = {{1, 2}, {3, 4}};
        int[][] gridCopy = grid.clone();
        gridCopy[0][0] = 8;

        System.out.println("same outer="
                + (grid == gridCopy));
        System.out.println("same first row="
                + (grid[0] == gridCopy[0]));
        System.out.println("original grid[0][0]="
                + grid[0][0]);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ArrayCloneDemo.java
java ArrayCloneDemo
~~~

**Exact stdout:**

~~~text
numbers[0]=1
copy[0]=9
same primitive array=false
same reference array=false
same element=true
original label=A!
same outer=false
same first row=true
original grid[0][0]=8
~~~

Cloning `int[]` yields an independent array object because its elements are inherently primitive values. Meanwhile, `StringBuilder[]` copies the **StringBuilder references**, not the StringBuilders themselves. `grid.clone()` shares the row objects, so modifying an element in a row is observable through both outer arrays.

If you need independent copies of the rows in an `int[][]`, you must copy each row, for example using `grid[i].clone()` for each non-null `int[]`. If rows can be null or if elements are mutable objects, you also need appropriate null-handling rules and deep copying.

## 17. `Arrays.copyOf` and `System.arraycopy` Are Also Typically Shallow for References

Common array-copying APIs:

- `array.clone()` creates a new array of the same runtime array type.
- `Arrays.copyOf(array, newLength)` creates a new array with the desired length, copies existing elements, and pads with default values if longer.
- `System.arraycopy(src, pos, dest, pos, length)` copies a range between existing arrays.
- `Arrays.copyOfRange` copies a specified range.

For reference arrays, these operations **copy reference values** and do not automatically clone child objects. If you change an element in the new array to a different object, the original array keeps the old reference; however, if you **mutate the object itself** pointed to by both arrays, both see the mutation.

Note that `System.arraycopy` can cause `ArrayStoreException` if runtime element types are incompatible, and in some cases copying may have already transferred elements before the error; do not rely on it as an automatic rollback transaction for incompatible copies.

## 18. Inheritance: A Subclass with Mutable Fields Makes the Superclass Clone Insufficiently Deep

With a hierarchy, overriding `clone()` in a superclass can return the right **runtime class** via `super.clone()`, yet it still shallow-copies fields added by the subclass. It cannot automatically know which mutable data each subclass needs to separate.

Create the file **`InheritedCloneDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

class BaseProfile implements Cloneable {
    private final String id;

    BaseProfile(String id) {
        this.id = id;
    }

    String id() {
        return id;
    }

    @Override
    public BaseProfile clone() {
        try {
            return (BaseProfile) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

class DetailedProfile extends BaseProfile {
    private List<String> skills = new ArrayList<>();

    DetailedProfile(String id) {
        super(id);
    }

    void addSkill(String skill) {
        skills.add(skill);
    }

    List<String> skills() {
        return List.copyOf(skills);
    }

    boolean sharesSkills(DetailedProfile other) {
        return skills == other.skills;
    }

    @Override
    public DetailedProfile clone() {
        DetailedProfile copy = (DetailedProfile) super.clone();
        copy.skills = new ArrayList<>(skills);
        return copy;
    }
}

public class InheritedCloneDemo {
    public static void main(String[] args) {
        DetailedProfile source = new DetailedProfile("P1");
        source.addSkill("Java");

        DetailedProfile copy = source.clone();
        copy.addSkill("SQL");

        System.out.println("same object=" + (source == copy));
        System.out.println("copy class="
                + copy.getClass().getSimpleName());
        System.out.println("shares skills="
                + source.sharesSkills(copy));
        System.out.println("source=" + source.skills());
        System.out.println("copy=" + copy.skills());
        System.out.println("source id=" + source.id());
        System.out.println("copy id=" + copy.id());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 InheritedCloneDemo.java
java InheritedCloneDemo
~~~

**Stdout:**

~~~text
same object=false
copy class=DetailedProfile
shares skills=false
source=[Java]
copy=[Java, SQL]
source id=P1
copy id=P1
~~~

Here, `BaseProfile.clone()` creates a copy with the same runtime class `DetailedProfile`. However, to make the mutable `skills` field independent, `DetailedProfile.clone()` must **add the step of copying the subclass's own list**.

If `DetailedProfile` did not override it, the clone inherited from BaseProfile would return an actual `DetailedProfile` object, but the `skills` list would be aliased. This is why designing an open hierarchy with a clone contract is complex: a new subclass adding a mutable field can unintentionally break the assumption that "a clone is independent".

## 19. Why Overriding `clone()` in a Hierarchy Is Hard to Maintain

In a hierarchy, there can be multiple levels:

~~~text
BaseDocument
    |
    +-- PdfDocument
    |      |
    |      +-- SignedPdfDocument
    |
    +-- HtmlDocument
~~~

Each level may add primitive, immutable, or mutable fields, resource handles, or object graphs with cyclic references. Each clone implementation must know **its own data** and satisfy the shared contract with the superclass.

Risks:

1. The superclass calls `super.clone()`, but a subclass forgets to copy a mutable field.
2. A subclass is not intended to be cloned, yet inherits a public `clone()` from the superclass.
3. A `final` field holding a mutable object is hard to detach after `super.clone()`.
4. The parent class changes constructor validation, while cloning **bypasses the constructor**.
5. Relationships between child objects can break if they are copied independently without preserving necessary identity/sharing.
6. Adding a new subclass makes the target-type assumption of a copy constructor insufficient.

When the API does not need polymorphic cloning, some designs choose **a `final` class + copy constructor/factory** to centralize invariant control. When polymorphic copying is needed, you can define a `copy()` method on an interface/domain contract with explicit rules, rather than relying on implicit `Object.clone()`.

## 20. Cyclic Graph: Deep Copy Cannot Simply Recurse Infinitely

An object can reference itself or share a common child object:

~~~text
A -> B -> A         (cycle)
C -> Shared
D -> Shared         (two paths to the same object)
~~~

If you write a naive deep-copy algorithm along the lines of "copy A, then copy each field, then copy each field of B", it can loop infinitely on the A↔B cycle. And if you copy each time a reference is encountered without remembering it, the two paths to the Shared object will produce **two distinct copies**, altering the **sharing** semantics of the graph.

Conceptual solution: use an **identity map** mapping original objects to their copies:

~~~text
copy(node):
    if node is already in identity map -> return existing copy
    create node copy
    record map[original node] = node copy before recursing
    copy child links, reusing map
    return node copy
~~~

With an identity map, objects must be compared by **reference**, not by `equals()`, because two nodes with different identities may hold the same value while still being two separate graph vertices.

## 21. Complete Program 6 — Copying a Cyclic Graph

Create the file **`GraphCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

public class GraphCopyDemo {
    private static final class Node {
        private final String name;
        private final List<Node> neighbors = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        void connect(Node neighbor) {
            neighbors.add(neighbor);
        }

        Node neighbor(int index) {
            return neighbors.get(index);
        }

        Node deepCopy(Map<Node, Node> visited) {
            Node previous = visited.get(this);
            if (previous != null) {
                return previous;
            }

            Node copy = new Node(name);
            visited.put(this, copy);
            for (Node neighbor : neighbors) {
                copy.neighbors.add(neighbor.deepCopy(visited));
            }
            return copy;
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.connect(b);
        b.connect(a);

        Node copiedA = a.deepCopy(new IdentityHashMap<>());
        Node copiedB = copiedA.neighbor(0);

        System.out.println("new root=" + (copiedA != a));
        System.out.println("new child=" + (copiedB != b));
        System.out.println("cycle preserved="
                + (copiedB.neighbor(0) == copiedA));
        System.out.println("original untouched="
                + (a.neighbor(0) == b));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GraphCopyDemo.java
java GraphCopyDemo
~~~

**Stdout:**

~~~text
new root=true
new child=true
cycle preserved=true
original untouched=true
~~~

Key mechanism: `visited.put(this, copy)` happens **before** recursing into neighbors. When copy B follows the back-reference to A, the map already holds copy A and returns it, avoiding infinite recursion.

The example uses `IdentityHashMap` because the problem requires **graph-vertex identity**, not equality by name. This is a deep-copy method using a normal constructor, **without using `Object.clone()`**; it shows that deep vs. shallow is a property of the copying algorithm, not of the method name `clone`.

## 22. Deep Copy Must Preserve Both Relationships and Invariants

Simply creating a new object for every field is not always right. For example, two fields `billingAddress` and `shippingAddress` may intentionally point to the **same Address object** if the customer selects "ship to billing address".

If a deep copy creates two independent Address copies, the copy loses the meaningful aliasing relationship present in the original model. If the original has a parent/child cycle or both sides of an association, manually cloning each object without an identity map can break relationships or create redundant objects.

Determine:

- Must you preserve only the **same values**, or also the **reference-sharing structure**?
- Which relationships fall within the ownership scope of the copied object?
- Which objects should continue referencing **external sources** (services, repositories, immutable metadata)?
- Which child objects have IDs that need to be regenerated, and which keep their IDs as the same entity?
- Are there callbacks, listeners, threads, or transaction state that should not be copied?
- After copying, do invariants still hold when executing every business method?

A clear deep-copy contract is much easier to test than the slogan "clone all fields".

## 23. `equals()`, `hashCode()`, and `==` After Cloning

Three distinct concepts:

- `original == copy` compares **reference identity**; for a proper clone that normally returns a new object, this must be false.
- `original.equals(copy)` depends on the class's **`equals` contract**. If the class does not override `Object.equals`, the default result is usually false because it compares identity. If it is a value object and equals compares fields, it can be true.
- `hashCode()` has a contract with equals: **if equals is true, hashCode must be equal**, though two distinct objects are not required to have different hashes. Do not use hashCode results to conclude whether an object "has been cloned or not".

If a class has a domain-unique ID, you must decide whether the copy keeps it or receives a new ID. If it keeps the same ID, two objects with different identities may be considered the **same entity** according to how equality is defined, even if other data differs. If a new ID is assigned, there must be a controlled creation method rather than expecting `Object.clone()` to run the ID allocator automatically.

`System.identityHashCode(obj)` is an identity-related value, yet it is **not a globally unique key**; collisions can occur, so it should not be used as a business identifier.

## 24. Immutable Value Objects May Not Need `clone()`

An immutable object can be **safely shared** across multiple places because there is no mutable state to isolate.

~~~java
record Coordinates(int x, int y) {
    Coordinates move(int dx, int dy) {
        return new Coordinates(x + dx, y + dy);
    }
}
~~~

This is a complete Java 17 record. `move` **does not mutate the old record**, but creates a new `Coordinates` with different values. The record has primitive components, so state immutability is straightforward.

For `String`, `Integer`, and other immutable value objects, it is unnecessary to create a new-identity copy just to avoid mutation. However, a record that has a **mutable `List` component** does not automatically become deeply immutable: record components are final references, and the referenced object can still be mutated without defensive copying.

Immutable design often makes **copying easier** by replacing in-place mutation with validated creation of new values.

## 25. When Should You Use a Copy Constructor, Factory, or `clone()`?

| Option | Strengths | Limitations |
| --- | --- | --- |
| `super.clone()` + `Cloneable` | Can copy runtime class, fast shallow field copying | Constructor does not run, mutable references alias |
| Override `clone()` with needed deep copy | Can expose a clone API suited to the class | Hard to maintain in hierarchies, handling final refs/cycles |
| Copy constructor `new T(original)` | Explicit, runs constructor, initializes `final` fields validly | Not automatically polymorphic for runtime subclasses |
| Static factory `T.copyOf(original)` | Easy to express name/contract, easy to validate | Requires application-defined copy code |
| Immutable `withX` / value replacement | Low risk of mutable aliasing, safe to share | May allocate many new objects, performance must be considered |
| Registry/graph-aware copy | Preserves identity and cycles within scope | More complex than copying a simple object |

**Java Core tip:** Do not treat `Cloneable` as a "mandatory shortcut" to support copying. For domain objects with complex invariants/ownership, a copy constructor or factory usually makes the contract more transparent.

If you are working with a specific JDK API that requires `Cloneable` or explicitly provides a public `clone()`, read that API's own contract rather than applying one assumption across all classes.

## 26. Testing Clone/Copy Behavior Properly

To prove a copy method is safe, design multi-layered tests:

| Check | What to Verify |
| --- | --- |
| Root-level identity | `copy != source` if the contract requires a new object |
| Primitive fields | Values are preserved accurately |
| Immutable fields | Can be shared without creating mutable aliases |
| Mutable collections | `copy.list != source.list` if independence is promised |
| Mutable elements | `copy.list.get(0) != source.list.get(0)` when owned elements require deep copying |
| Mutation isolation | Modifying the copy does not change the source and vice versa |
| Final fields | The copy maintains valid invariants without bypassing final |
| Constructor invariants | Are they validated/restored according to the contract? |
| Repeated references | Two links to the same child object in source still share properly in copy |
| Cycles | Graph clone terminates and reconstructs cyclic relationships accurately |
| Subclass fields | Clone preserves the runtime class and protects mutable fields added by the subclass |
| Exceptions | Invalid input/copy failure does not leave source unexpectedly mutated |
| Resource handles | Does not clone socket/lock/file handles in violation of their lifecycle |
| Concurrency | Does copying require a consistent snapshot or synchronization with writers? |

You can use JUnit, yet **no framework is required** for basic checks; `if (...) throw new AssertionError(...)` statements let you write self-tests with the plain JDK.

You should test **post-mutation behavior**, not just check `copy.equals(source)` immediately after copying. A shallow clone can have identical initial data and still harbor an aliasing bug that only surfaces once mutations begin.

## 27. Copying and Concurrency: Snapshots Are Not Automatically Thread-Safe

If one thread is modifying an `ArrayList` while another thread concurrently clones the object holding that list, `Object.clone()` does not automatically provide an **atomically consistent snapshot** of the entire object graph.

Some risks:

- Field values are read/copied at different points in time, creating an inconsistent snapshot.
- Iterating over a mutable collection while another thread modifies it can lead to wrong results or exceptions depending on the API.
- A shallow copy only copies references; it does not establish synchronization or ownership.
- A multi-step deep copy may need to hold a lock or capture an immutable snapshot under a consistent protocol.

If the application requires concurrent snapshots, design appropriate synchronization, immutable persistent structures, read/write locks, or versioning/transaction mechanisms. **`Cloneable` is not a thread-safe contract**.

Do not try to "fix" concurrency by calling `clone()` repeatedly until no error occurs; correctness requires an explicit consistency rule.

## 28. Copying Objects Containing Resources and External State

Not all Java state is valid to copy from a business perspective:

- A `Socket` or database connection is an external resource; a valid duplicate connection cannot be created merely by copying fields.
- An `InputStream` has a read position, open/closed state, and underlying data; sharing it or attempting to copy fields can corrupt its lifecycle.
- `Thread`, lock, and condition objects carry state tied to synchronization and execution scheduling; they are not data values to shallow-copy.
- Objects with external identity such as transactions, bookings, or database entities may require a new ID or may not be permitted to be duplicated.

When a domain object holds these dependencies, it is usually better to copy the **domain data** into a new object and **inject dependencies** according to the appropriate lifecycle, rather than cloning the entire reference graph and expecting every resource to function independently.

In many cases, creating a **DTO/record snapshot** of the important data is a more accurate choice than copying a live domain entity.

## 29. Should You Use Serialization for Deep Copying?

Some legacy code attempts deep copying by serializing an object to bytes and deserializing it back into a new object. That approach can copy a graph within serialization's scope, yet it is **not a safe general-purpose copy solution**:

- Not every object is serializable.
- Serialization has its own contracts for `transient`, custom read/write methods, identity, versioning, and object resolution.
- Constructors/invariants follow special rules during deserialization.
- It incurs CPU and memory overhead as well as security risks when deserializing untrusted data.
- Live resources such as sockets/connections are not suitable for "copying over a byte stream".
- Serialization does not resolve business intent such as "which objects keep their ID and which must be new".

Therefore, do not use serialization merely to avoid writing an explicit copy constructor or factory. If a system already uses a controlled data format and needs to produce an independent DTO, evaluate serialization as **a separate component** with proper testing and security.

## 30. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Calling `clone()` always performs a deep copy." | `Object.clone()` shallow-copies reference fields by default |
| "`Cloneable` defines a public `clone()`." | The marker interface declares no methods |
| "Implementing `Cloneable` lets every caller call `obj.clone()`." | `Object.clone()` is protected; the class usually must expose its own API |
| "Without implementing Cloneable, `super.clone()` still works." | `Object.clone()` can throw `CloneNotSupportedException` |
| "`clone()` always calls the constructor and then copies fields." | `Object.clone()` does not run the copied object's constructor |
| "A final List field is automatically immutable." | Final blocks reassigning the reference, not `List.add` |
| "`new ArrayList<>(old)` is a deep copy of the list." | New container, reference elements are still shared |
| "`List.copyOf` deep-copies every element." | Shallow snapshot; mutable elements can still be aliased |
| "`array.clone()` deep-copies the elements." | New array, reference elements are still shared |
| "Cloning an `int[][]` makes every row independent." | Outer array is new; inner rows are shared by default |
| "Superclass clone automatically knows how to copy subclass mutable fields." | Subclasses need to uphold the contract and copy appropriate fields |
| "If there is a cycle, just copy recursively." | An identity map is needed to avoid infinite loops and preserve sharing |
| "After copying, both objects must have the same business identifier." | Separate contracts are needed for ID, equality, and identity |
| "Different objects must have different `hashCode` values." | Collisions can happen; identity does not equal hash |
| "Cloning in another thread automatically creates a consistent snapshot." | Requires dedicated synchronization/consistency |
| "Connections/locks can be cloned like data." | Resource ownership and lifecycle cannot be copied via fields |
| "A copy constructor always preserves the runtime subclass." | A constructor instantiates the exact type called, not virtually |
| "Immutable objects must be cloned to be safe." | They can be shared safely depending on the contract |

## 31. Guide to Solving Shallow/Deep Copy Exercises

When a problem gives a class and asks what the program prints after `clone()`:

1. Check whether the runtime object **implements `Cloneable`** and which clone method is actually invoked.
2. Check whether the clone method has public/covariant return or if the caller is simply trying to access a protected method.
3. For `super.clone()`, visualize the **new root object** and **each field** being copied.
4. Mark primitive fields with independent values; reference fields initially **point to the same** child objects.
5. If the clone method reassigns a field to a new copy, redraw that reference edge.
6. If mutable elements are cloned individually, check whether the child objects are new or still share inner references.
7. When a subclass is involved, check which clone override is called and which subclass fields have been deep-copied.
8. When there is a final field, check whether the code tries to reassign it inside a normal method; compilation errors must be identified before computing stdout.
9. When encountering multidimensional arrays, separate **the outer array and each row** into distinct objects.
10. If there is a mutation after cloning, identify **which object is actually mutated**, then check all references pointing to that object.
11. For a copy constructor, trace the constructor statements: validation, defensive copying, and the initialized fields.
12. For graphs, check whether there are sharing/cycles and an identity map.
13. Only at the end compute `==`, `equals`, field values, and stdout.

Do not answer "clone creates a copy so they do not affect each other" without indicating **at what level references** were copied.

## 32. Practice Exercises

**Question 1.** Does `Cloneable` declare a `clone()` method? Why might a class that implements Cloneable still not allow external callers to call `clone()`?

**Question 2.** How does `Object.clone()` copy primitive data types and reference fields by default?

**Question 3.** A class does not implement Cloneable, yet has a method that calls `super.clone()`. When the method runs, what happens?

**Question 4.** `Point` has only two primitive fields `int x, y`. Is a shallow copy sufficient for the state of these two fields to be independent?

**Question 5.** `Notebook` holds `List<String> tags`. After `super.clone()`, the copy calls `tags.add("new")`. What does the original see? Why?

**Question 6.** Why does returning `List.copyOf(tags)` in a getter not automatically fix the alias created by a shallow clone?

**Question 7.** A class holds `final List<String> items`. After `super.clone()`, can you write `copy.items = new ArrayList<>(items)` inside the clone method?

**Question 8.** If the constructor assigns an incrementing ID, why can cloning produce two objects with the same ID?

**Question 9.** `int[] a = {1,2}; int[] b=a.clone(); b[0]=9;`. What is the value of `a[0]`?

**Question 10.** `StringBuilder[] a` has one element containing `StringBuilder("X")`; `b=a.clone(); b[0].append("Y");`. What will element `a[0]` display?

**Question 11.** `int[][] m={{1},{2}}; int[][] c=m.clone(); c[0][0]=7;`. Does `m[0][0]` remain 1 or change to 7?

**Question 12.** A superclass implements Cloneable with a public shallow clone; a subclass adds an `ArrayList` field. If it does not override clone, what is the risk?

**Question 13.** When deep-copying graph A↔B recursively, why must A be placed in the identity map **before** traversing edge A→B?

**Question 14.** Two fields in the source point to the same child object. When deep-copying, is creating two separate copies of that child object always the right thing to do?

**Question 15.** When is a copy constructor more appropriate than `Object.clone()`? When does a copy constructor not automatically handle polymorphism?

**Question 16.** If a class's `equals` is defined by ID and `clone` preserves the ID, what can `source == copy` and `source.equals(copy)` evaluate to, respectively?

**Question 17.** Why might cloning an object while another thread is modifying it fail to produce a consistent snapshot?

**Question 18.** Can serialization/deserialization be regarded as a perfect deep-copy method for all objects?

### Solutions

1. No; Cloneable is a marker interface. `Object.clone()` is protected, so the class needs to expose a method with appropriate visibility if callers should be able to use it.
2. Primitive fields copy their values; reference fields copy **reference values**, so child objects may still be shared.
3. It normally results in `CloneNotSupportedException` from `Object.clone()`.
4. Yes, for those specific fields, provided there are no other mutable child objects.
5. The source also sees the `"new"` element, because both notebooks point to the same list.
6. `List.copyOf` only creates a read-only list/snapshot for the caller; it does not change the `tags` field that is already aliased between the two notebooks.
7. No; a `final` field cannot be reassigned inside a regular method. Use a constructor/factory or another design.
8. Cloning does not re-run the constructor that assigns the ID; the ID value is copied as-is.
9. `1`: the new primitive array holds its own values.
10. `"XY"`: both arrays point to the same StringBuilder element.
11. `7`: the row array is shared because only the outer array was cloned.
12. The copy keeps the same subclass list; mutating the copy can modify the source.
13. So that when B traverses back to A, the map returns the already created copy of A, avoiding infinite recursion.
14. Not necessarily. If sharing is meaningful, use an identity map so that both edges in the copy point to the same copy of the shared object.
15. A copy constructor is suitable when validation, final fields, or defensive copying is needed; it instantiates the called type and does not automatically preserve the runtime subclass.
16. `false` and possibly `true`, if equals is based on the preserved ID. You must inspect the specific equality contract.
17. Different fields/collections may be read at different times; clone does not automatically lock all writers.
18. No. Serialization has its own contracts, type constraints, lifecycle, performance overhead, and security risks.

## 33. Checklist for Designing a Copy API

- Does the caller need a **new object identity** or just a value view?
- Must the source remain unchanged after copying, even if copying fails?
- Which primitive/immutable fields can be copied by value or shared?
- Which mutable references belong to the object's ownership and must be detached?
- Does the collection hold mutable elements or only immutable values?
- Do repeated references and cycles need their aliasing structure preserved?
- Are there `final` fields that make post-clone processing difficult or invalid?
- Does the constructor enforce invariants or assign a unique ID?
- Does the system have subclasses that add mutable fields?
- What semantics do `equals/hashCode` have on the copy?
- Are there resources that cannot or should not be copied?
- Should callers be allowed to directly modify mutable collections after copying?
- Is consistent concurrency/snapshotting supported?
- Is mutation isolation tested in **both directions**?
- Should the method be named `clone()`, `copy()`, `snapshot()`, `withX()`, or `duplicateAsNew()` to convey the exact intent?
- Does the API documentation clearly state shallow/deep semantics, identity, ownership, null handling, and the failure policy?

## 34. Official Java 17 Documentation

- [Object.clone — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()): access visibility, shallow field copying, and exceptions.
- [Cloneable — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): the marker interface and its meaning for Object.clone.
- [CloneNotSupportedException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CloneNotSupportedException.html): the checked exception type when a clone operation is not supported.
- [Array — Java Language Specification 17, §10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): arrays, array cloning, and element types.
- [Object Creation — JLS 17 §12.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): normal object creation, distinct from the native clone mechanism.
- [Final Fields — JLS 17 §17.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): semantics of final fields in the Java Memory Model.
- [ArrayList — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): mutable list and copy constructor.
- [List.copyOf — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): collection-level immutable list snapshot.
- [Arrays.copyOf — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): array copying.
- [IdentityHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): compares keys by reference identity, suitable for certain object graph copying problems.
- [Effective Java, Third Edition — Item 13](https://www.pearson.com/en-us/subject-catalog/p/effective-java/P200000000182): covers overriding `clone()` judiciously; treat as further reading, not a substitute for the Java specification.

**Conclusion:** `Cloneable` only signals that a class permits the `Object.clone()` mechanism and does not provide a public copy method; `Object.clone()` fundamentally **creates a new object and shallow-copies its fields** **without calling a constructor**. For objects containing only primitive/immutable values, a shallow copy may suffice. For mutable references, collections, multidimensional arrays, subclasses, and cyclic graphs, you must design **intentional copy semantics** and test mutation isolation. Copy constructors or factories are usually clearer choices when validation, `final` fields, lifecycles, and domain invariants are required.
