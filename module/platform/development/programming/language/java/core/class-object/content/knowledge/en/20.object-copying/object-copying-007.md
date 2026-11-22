# Choosing How to Copy Based on Ownership and Mutability in Java

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **object identity**, reference aliasing, assignment, shallow copy, selective deep copy, immutable snapshot, and live view.
- Analyze **who owns the data**, **who has permission to modify it**, **who needs to retain the data after the call**, and **whether the data changes over time** to choose a clear copying strategy.
- Know when **sharing a reference** is right: a truly immutable component, an intentionally borrowed resource, or live data under a contract that manages mutation.
- Know when to **defensively copy on input**, **output**, or **both**: mutable objects crossing API boundaries, snapshots that need to remain stable, and collections with mutable nested elements.
- Use copy constructors, factories, `array.clone()`, `Arrays.copyOf`, `new ArrayList<>(source)`, `List.copyOf`, and `Map.copyOf` with the right semantics, without confusing copying a container with copying a component.
- Distinguish **ownership transfer by convention** from language enforcement: Java does not have a move-only ownership system that guarantees all old aliases are invalidated.
- Design immutable value objects/records and snapshots that satisfy equality, hash-key stability, invariants, and ownership boundaries.
- Consider object graphs with cycles, shared nodes, and references to resources to decide the copy scope without breaking graph semantics.
- Understand the impact on multithreading: immutable snapshots help share stable data; a shallow copy does not isolate a mutable child from other threads.
- Compare copy cost, structural sharing, copy-on-write, lifetime, and resources; choose **the minimum copy level sufficient to satisfy the contract**, rather than choosing “deep copy everything” out of habit.
- Run standalone Java 17+ programs, predict stdout, and test copying decisions with identity/state tests.

## 1. Before Copying, You Must Ask: Who Owns It and Who Can Modify It?

In Java, a reference variable holds a **reference value** to an object. The statement:

~~~java
Document second = first;
~~~

**does not copy the Document object**; `second` and `first` refer to the same object. If Document is mutable, a change through one reference can be seen through the other reference.

Copying is only useful when it satisfies a specific requirement: separating modification rights, keeping a point-in-time snapshot, satisfying an API that the caller can use independently, preserving history, or protecting an invariant.

Without that requirement, copying can increase allocation, memory usage, and complexity without improving correctness.

### 1.1. Three Decision Axes

| Axis | Question to Answer | Impact on Copying Approach |
| --- | --- | --- |
| **Ownership** | Who is responsible for protecting/managing the state? Who can hold an alias? | Determines where to place the defensive boundary |
| **Mutability** | Can the state participating in the contract change? Are elements/nested objects mutable? | Chooses sharing, shallow copy, or selective deep copy |
| **Lifetime/observation** | Does the consumer need the current state or an immutable snapshot at time T? | Chooses a live reference/view or an immutable snapshot |

If a method only needs to **temporarily read** an immutable `String`, there is no need to clone the String. If a constructor stores an `int[]` input to read later and the caller can still mutate the array, it needs to copy the data or clearly document a shared-mutable contract.

### 1.2. Ownership Is a Design Contract, Not a Java Keyword

Java has `private`, `final`, GC, access controls, and concurrent primitives, but **does not have compile-time affine/move-only ownership types** like some other languages. A reference can be aliased:

~~~java
List<String> draft = new ArrayList<>();
List<String> alias = draft;
service.accept(draft);
~~~

Even if the API documentation says “service takes ownership”, the caller still has `alias` and can mutate the list, unless the program follows the convention or the service performs a defensive copy. Therefore, talking about *transferring ownership* in Java usually means a **coordination convention** or enforcement through an API wrapper/protocol, not the JVM automatically invalidating aliases.

## 2. Quick Selection Map

| Scenario | Usually Reasonable Strategy | Things to Note |
| --- | --- | --- |
| Truly immutable component, widely shared | **Share reference** | Do not use `==` for value equality |
| Mutable data existing only within one method, exclusive ownership | **Mutate in place**, no copy needed yet | Do not let the reference escape scope unintentionally |
| Caller passes mutable input, callee needs to keep a snapshot | **Copy at the input boundary** | Also copy mutable elements if needed |
| Callee holds mutable internal state, caller needs safe reads | **Immutable snapshot or defensive output copy** | Do not return the raw internal list/array |
| Two collections need independent structure, but elements may be shared | **Shallow container copy** | Mutating a shared element affects both |
| Consumer needs an immutable value snapshot | **Selective deep copy to an immutable representation** | Copy exactly the observable data that must be retained |
| Consumer needs to see live state changes | **Intentionally share reference/live view** | Clear synchronization, ownership, and lifetime |
| Large data, multiple versions sharing reads | **Immutable structural sharing/persistent structures** if appropriate | `List.copyOf` is not a persistent data structure by default |
| Object holds a socket/connection/stream | **Do not arbitrarily deep-clone resources** | Owner/borrower and close semantics |
| Graph has cycles and shared nodes | **Graph-aware copy** with an identity memo when needed | Preserve alias/cycle invariants |
| Mutable HashMap key | **Snapshot immutable key** | Equality/hash-relevant state must be stable |

This is a **decision tree**, not a rule that “a Java type must always be copied”. The API domain and the actual mutability of the *entire object graph* are what decide.

## 3. Aliasing: Why Is Looking Only at the Outer Object Not Enough?

Suppose:

~~~java
class Order {
    String id;
    Address shippingAddress;
}
~~~

A copy constructor can create a new Order while assigning `shippingAddress = source.shippingAddress`. In that case:

- The two Order objects have different identities.
- The same mutable Address object is referenced.
- Reassigning `copy.id` does not modify `source.id`.
- Reassigning `copy.shippingAddress` does not modify source's field (if the outer objects are different).
- However, calling `copy.shippingAddress.setCity(...)` can modify the Address that source also observes.

This is a **shallow copy**: primitive values and field reference values are copied, but nested objects are not automatically copied.

### 3.1. Program: Choosing a Copy Suitable for a Mutable Child

Save **`CopyDepthDecisionDemo.java`**:

~~~java
public class CopyDepthDecisionDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        Address(Address source) {
            this.city = source.city;
        }

        void moveTo(String next) {
            city = next;
        }

        String city() {
            return city;
        }
    }

    static final class Person {
        private String name;
        private Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person shallowCopy() {
            return new Person(name, address);
        }

        Person independentAddressCopy() {
            return new Person(name, new Address(address));
        }

        String description() {
            return name + "@" + address.city();
        }
    }

    public static void main(String[] args) {
        Person original = new Person(
                "Lan", new Address("Ha Noi"));
        Person shallow = original.shallowCopy();
        Person separate = original.independentAddressCopy();

        System.out.println("same outer=" +
                (original == shallow));
        System.out.println("shared address=" +
                (original.address == shallow.address));
        System.out.println("separate address=" +
                (original.address == separate.address));

        shallow.name = "Minh";
        shallow.address.moveTo("Hue");

        System.out.println("original=" + original.description());
        System.out.println("shallow=" + shallow.description());
        System.out.println("separate=" + separate.description());
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac CopyDepthDecisionDemo.java
java CopyDepthDecisionDemo
~~~

**Stdout:**

~~~text
same outer=false
shared address=true
separate address=false
original=Lan@Hue
shallow=Minh@Hue
separate=Lan@Ha Noi
~~~

**Analysis:**

- `Person.shallowCopy` creates a new outer object but shares the Address.
- `Person.independentAddressCopy` creates a new Address (deep enough because Address here only holds an immutable String).
- Modifying the name field in shallow does not change original's name; modifying the shared mutable Address causes original to see Hue.
- The separate copy keeps Ha Noi because it has no alias to the modified Address.
- You should not call `independentAddressCopy` a “permanent deep clone” if Address later adds nested mutable fields; the contract must be maintained when the class structure changes.

## 4. Ownership Terminology to Use Consistently

### 4.1. Owned mutable value

An object manages a mutable component and does not allow external code to hold references capable of modifying it. For example: an `OrderAggregate` holds an internal mutable `ArrayList`, providing only `addLine` domain methods with validation.

Here, **there is no need to copy during internal handling** within the same owner if there is no alias/temporal snapshot risk. However, when outputting data to a caller, a snapshot may be needed.

### 4.2. Borrowed reference

A method receives a reference for **temporary use** without long-term ownership. If it only reads synchronously and returns before the caller mutates it, copying may not be necessary.

However, if the method stores the reference in a field or submits a callback that runs later, it **has extended the lifetime** beyond the borrow scope; the contract must be updated or a copy made to prevent caller mutation after the call.

### 4.3. Shared ownership / live reference

Multiple components jointly manage or use an object and want to see live state changes. Not copying is intentional. Synchronization, lifecycle, permissions, and who has permission to change the state must be clearly specified.

### 4.4. Transfer-of-ownership convention

The caller hands a reference over to a receiver and **commits to no longer using/mutating it**. Java does not enforce this automatically. If the receiver does not control all aliases, invariants can be broken; either use an immutable representation or copy at the transfer boundary.

### 4.5. Immutable shared value

Multiple owners/readers hold references to the same immutable `LocalDate`, `String`, `BigDecimal`, immutable record... There is no need to duplicate them just to guard against mutation of that value itself.

**Note:** a `record` holding an `int[]` or a mutable `List<Item>` **is not automatically considered deeply immutable**.

## 5. Borrowed, Retained, and Snapshot Are Three Different Contracts

A method:

~~~java
void readNow(List<String> items) {
    System.out.println(items.size());
}
~~~

is an illustration of **short-term borrowing**: it only reads the size and then returns. If there is no unintended concurrent mutation and no alias is retained, copying is not necessarily beneficial.

A constructor:

~~~java
class SavedReport {
    private final List<String> lines;

    SavedReport(List<String> input) {
        lines = List.copyOf(input);
    }
}
~~~

demonstrates a **retained snapshot**: it stores the list structure at construction time. Because String is immutable, this is a stable text-value snapshot.

In contrast:

~~~java
class LivePanel {
    private final List<String> shared;

    LivePanel(List<String> shared) {
        this.shared = shared;
    }
}
~~~

can be a **live reference** if the API documents that the panel reflects external changes. This is not inherently wrong; the point is that **the caller and callee must agree on the same contract**, especially in concurrent code.

## 6. Program: Hold a Reference or Capture a Snapshot?

Save **`BorrowOrSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class BorrowOrSnapshotDemo {
    static final class LiveViewer {
        private final List<String> source;

        LiveViewer(List<String> source) {
            this.source = source;
        }

        int size() {
            return source.size();
        }
    }

    static final class FrozenReport {
        private final List<String> lines;

        FrozenReport(List<String> source) {
            lines = List.copyOf(source);
        }

        int size() {
            return lines.size();
        }
    }

    public static void main(String[] args) {
        List<String> draft = new ArrayList<>(List.of("A"));
        LiveViewer live = new LiveViewer(draft);
        FrozenReport frozen = new FrozenReport(draft);

        System.out.println("before live=" + live.size());
        System.out.println("before frozen=" + frozen.size());

        draft.add("B");

        System.out.println("after live=" + live.size());
        System.out.println("after frozen=" + frozen.size());
    }
}
~~~

Run:

~~~bash
javac BorrowOrSnapshotDemo.java
java BorrowOrSnapshotDemo
~~~

Output:

~~~text
before live=1
before frozen=1
after live=2
after frozen=1
~~~

**LiveViewer** intentionally observes the source list as the source changes. **FrozenReport** holds a structural snapshot with immutable String elements. Both can be right, but the class name/contract must clearly state what the user needs.

`LiveViewer` in the example is **not thread-safe** if the list is modified concurrently without synchronization. The program only modifies the list sequentially in main.

## 7. Defensive Copy at the Input Boundary

When a constructor or method needs to store mutable input for later use, ask: **does the caller still hold a reference?** If so, and the callee needs its own state, storing the raw reference is an ownership flaw.

Incorrect example:

~~~java
class UnsafeImage {
    private final byte[] pixels;

    UnsafeImage(byte[] pixels) {
        this.pixels = pixels;
    }
}
~~~

Even though the field is `private final`, a caller holding `pixels` can still write `pixels[0] = ...`, causing the data inside UnsafeImage to change.

The minimal fix for a primitive array is a defensive clone:

~~~java
class Image {
    private final byte[] pixels;

    Image(byte[] input) {
        pixels = input.clone();
    }

    byte[] pixels() {
        return pixels.clone();
    }
}
~~~

Copying in the constructor breaks the **input alias**; copying in the getter breaks the **output alias**. If you only do one side, the other side can still modify the internal array.

## 8. Program: Two-Way Defensive Copy

Save **`DefensiveBoundaryDemo.java`**:

~~~java
import java.util.Arrays;

public class DefensiveBoundaryDemo {
    static final class KeyBytes {
        private final byte[] bytes;

        KeyBytes(byte[] source) {
            bytes = source.clone();
        }

        byte[] copyBytes() {
            return bytes.clone();
        }

        int checksumForDemo() {
            int total = 0;
            for (byte item : bytes) {
                total += item;
            }
            return total;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof KeyBytes key
                    && Arrays.equals(bytes, key.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }
    }

    public static void main(String[] args) {
        byte[] original = {1, 2, 3};
        KeyBytes key = new KeyBytes(original);
        KeyBytes same = new KeyBytes(new byte[] {1, 2, 3});

        System.out.println("initial equality=" + key.equals(same));
        System.out.println("hash equality=" +
                (key.hashCode() == same.hashCode()));

        original[0] = 9;
        byte[] outgoing = key.copyBytes();
        outgoing[1] = 8;

        System.out.println("source changed=" + original[0]);
        System.out.println("outgoing changed=" + outgoing[1]);
        System.out.println("internal checksum=" +
                key.checksumForDemo());
        System.out.println("equality after=" + key.equals(same));
    }
}
~~~

Run:

~~~bash
javac DefensiveBoundaryDemo.java
java DefensiveBoundaryDemo
~~~

Output:

~~~text
initial equality=true
hash equality=true
source changed=9
outgoing changed=8
internal checksum=6
equality after=true
~~~

The results demonstrate that copies at both boundaries isolate external aliases from the internal mutable byte array. `checksumForDemo` only sums the bytes to illustrate state; it is **not** secure cryptographic checksum/hashing.

## 9. A Shallow Copy of a Collection Is Often Enough When Elements Are Immutable

With `List<String>` or `List<LocalDate>`, two different lists can hold references to the same immutable elements without worrying about the elements being mutated.

~~~java
List<String> mutableCopy = new ArrayList<>(source);
List<String> readOnlySnapshot = List.copyOf(source);
~~~

The choice depends on the requirements:

- `new ArrayList<>(source)`: a new, **mutable** list structure; element references are copied.
- `List.copyOf(source)`: an unmodifiable list retaining element values at the snapshot time; it **does not deep-copy** elements. It may reuse a suitable instance when source is already unmodifiable, so it does not guarantee that the outer identity is always different.
- `Collections.unmodifiableList(source)`: an unmodifiable **view**; source can still be mutated afterward and the view sees the changes.
- Direct `source` reference: the exact same list object.

### 9.1. Table: “new container” vs. “new element”

| API/operation | New outer structure? | New component objects? | Caller modifies structure via result? |
| --- | --- | --- | --- |
| `alias = source` | No | No | Follows source |
| `new ArrayList<>(source)` | Yes | No | Yes |
| `source.toArray()` | Creates a new array | No | Can replace element references in the array |
| `intArray.clone()` | Yes | Primitive values are copied | Yes |
| `ItemArray.clone()` | Yes | No, Item references shared | Yes |
| `List.copyOf(source)` | Not necessarily a new identity | No | No |
| `Collections.unmodifiableList(source)` | Wrapper/view; shared backing | No | Not through the view |
| `Map.copyOf(source)` | Snapshot unmodifiable structure | Does not clone keys/values | No |

A copy API may **not allocate a new object** when an immutable structure/value is already valid. Do not rely on `==` to require a new identity if the documentation only promises snapshot/value semantics.

## 10. Program: Same Elements, Different List Structure

Save **`CollectionChoiceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionChoiceDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> editable = new ArrayList<>(source);
        List<String> snapshot = List.copyOf(source);
        List<String> view = Collections.unmodifiableList(source);

        source.add("B");
        editable.add("C");

        System.out.println("source=" + source);
        System.out.println("editable=" + editable);
        System.out.println("snapshot=" + snapshot);
        System.out.println("view=" + view);

        try {
            snapshot.add("D");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }

        try {
            view.clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("view cannot clear");
        }
    }
}
~~~

Run:

~~~bash
javac CollectionChoiceDemo.java
java CollectionChoiceDemo
~~~

Output:

~~~text
source=[A, B]
editable=[A, C]
snapshot=[A]
view=[A, B]
snapshot cannot add
view cannot clear
~~~

This choice depends on the need: a mutable copy for active modification; a snapshot to store structural values; a live view to track source without letting the caller modify it through the wrapper.

## 11. Mutable Elements: Copying the List Is Not Enough to Protect Values

With `List<MutableItem>`, calling `new ArrayList<>(source)` or `List.copyOf(source)` still holds references to the existing Items. If Item has a setter and the caller still has an alias, the state observed through both containers can change.

### 11.1. Counterexample Program

Save **`MutableElementSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableElementSharingDemo {
    static final class Item {
        private String name;

        Item(String name) {
            this.name = name;
        }

        void rename(String next) {
            name = next;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Item item = new Item("old");
        List<Item> source = new ArrayList<>();
        source.add(item);

        List<Item> editable = new ArrayList<>(source);
        List<Item> snapshot = List.copyOf(source);

        System.out.println("same element=" +
                (source.get(0) == editable.get(0)));
        System.out.println("snapshot same element=" +
                (source.get(0) == snapshot.get(0)));

        item.rename("new");
        editable.add(new Item("extra"));

        System.out.println("source name=" + source.get(0).name());
        System.out.println("editable name=" + editable.get(0).name());
        System.out.println("snapshot name=" + snapshot.get(0).name());
        System.out.println("source size=" + source.size());
        System.out.println("editable size=" + editable.size());
        System.out.println("snapshot size=" + snapshot.size());
    }
}
~~~

Run:

~~~bash
javac MutableElementSharingDemo.java
java MutableElementSharingDemo
~~~

Output:

~~~text
same element=true
snapshot same element=true
source name=new
editable name=new
snapshot name=new
source size=1
editable size=2
snapshot size=1
~~~

Copying the structure is a separate decision; isolating mutable elements is another decision. If the requirement is “store the item name when finalizing the order”, copying the `Item` reference can be wrong because the name/price may be edited later.

## 12. Selective Copy: Storing Business Values Instead of Cloning the Entire Graph

A quoting API needs the **price at the time of ordering**, without sharing the catalog's live Product.price. Instead of cloning the entire Product entity (ID, cache, listeners, database hooks), convert the data that must be retained into an immutable value record.

### 12.1. Example of Choosing the Right Representation

Save **`SelectiveSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SelectiveSnapshotDemo {
    static final class MutableProduct {
        private final String sku;
        private long price;

        MutableProduct(String sku, long price) {
            this.sku = sku;
            this.price = price;
        }

        void setPrice(long price) {
            this.price = price;
        }

        String sku() {
            return sku;
        }

        long price() {
            return price;
        }
    }

    record QuotedLine(String sku, long unitPrice) {
    }

    static final class Quote {
        private final List<QuotedLine> lines;

        Quote(List<MutableProduct> products) {
            List<QuotedLine> snapshot = new ArrayList<>();
            for (MutableProduct p : products) {
                snapshot.add(new QuotedLine(p.sku(), p.price()));
            }
            lines = List.copyOf(snapshot);
        }

        long priceAt(int index) {
            return lines.get(index).unitPrice();
        }

        int size() {
            return lines.size();
        }
    }

    public static void main(String[] args) {
        MutableProduct product = new MutableProduct("PEN", 10);
        List<MutableProduct> catalog = new ArrayList<>();
        catalog.add(product);

        Quote saved = new Quote(catalog);

        product.setPrice(25);
        catalog.add(new MutableProduct("BOOK", 50));

        System.out.println("catalog price=" + product.price());
        System.out.println("saved price=" + saved.priceAt(0));
        System.out.println("catalog count=" + catalog.size());
        System.out.println("saved count=" + saved.size());
    }
}
~~~

Run:

~~~bash
javac SelectiveSnapshotDemo.java
java SelectiveSnapshotDemo
~~~

Output:

~~~text
catalog price=25
saved price=10
catalog count=2
saved count=1
~~~

**Why is this better than “deep cloning Product”?** Quote only needs `sku` and `unitPrice` at the time of capture. The immutable record QuotedLine owns concise data without bringing along the ability to mutate Product, connections, or cache.

**Concurrency caveat:** if catalog and prices can change concurrently while the constructor iterates over the list, snapshot consistency/locking/transactions are needed at the appropriate layer. Choosing a record does not automatically turn reading multiple mutable objects into an atomic snapshot.

## 13. Immutable Components Should Be Shared, Not Needlessly Duplicated

Java `String`, `LocalDate`, `BigInteger`, `BigDecimal`, and records containing only immutable components are value types whose references can be safely shared with respect to mutation of **the component itself**.

For example:

~~~java
record Coordinate(int x, int y) {
}

Coordinate shared = new Coordinate(1, 2);
Coordinate left = shared;
Coordinate right = shared;
~~~

There is no valid method to change `x` of shared. There is no need for `new Coordinate(shared.x(), shared.y())` just to prevent someone from mutating Coordinate.

**However**, a record with `int[] pixels`, `List<MutableItem>`, or a reference to a resource is not automatically deeply immutable. If the contract requires stability, check the state reachable through the components.

### 13.1. Program: Sharing Immutable Parts

Save **`ImmutablePartSharingDemo.java`**:

~~~java
public class ImmutablePartSharingDemo {
    record Point(int x, int y) {
        Point translated(int dx, int dy) {
            return new Point(x + dx, y + dy);
        }
    }

    record Segment(Point from, Point to) {
    }

    public static void main(String[] args) {
        Point shared = new Point(1, 2);
        Segment first = new Segment(shared, new Point(3, 4));
        Segment second = new Segment(shared, new Point(5, 6));

        System.out.println("shared endpoint=" +
                (first.from() == second.from()));

        Segment moved = new Segment(
                first.from().translated(10, 0),
                first.to());

        System.out.println("first from=" + first.from());
        System.out.println("moved from=" + moved.from());
        System.out.println("second from=" + second.from());
        System.out.println("same old endpoint=" +
                (first.from() == second.from()));
    }
}
~~~

Run:

~~~bash
javac ImmutablePartSharingDemo.java
java ImmutablePartSharingDemo
~~~

Output:

~~~text
shared endpoint=true
first from=Point[x=1, y=2]
moved from=Point[x=11, y=2]
second from=Point[x=1, y=2]
same old endpoint=true
~~~

Calling `translated` returns a new Point. There is no mutation of the shared Point; the two old Segments still use the shared reference. This is an example of **selective allocation**: creating only the values that actually change.

## 14. Copy Constructor or `clone()`, Factory, Record?

### 14.1. Copy Constructor

~~~java
class Config {
    private final String name;
    private final int[] weights;

    Config(Config source) {
        name = source.name;             // Share immutable String.
        weights = source.weights.clone(); // Copy mutable array.
    }
}
~~~

This is a snippet illustrating a class with corresponding fields and the required constructor/factory. A copy constructor helps define **each field**: share the immutable part, copy the mutable part.

### 14.2. Static Factory

~~~java
static Config snapshotOf(Config source) {
    return new Config(source);
}
~~~

The name `snapshotOf` expresses the **business intent** more clearly than `clone` and can add validation/normalization, yet the implementation must still preserve the promised semantics.

### 14.3. `Object.clone()`

`Object.clone` copies field values by default: primitive values are copied, and reference values **still point to the same child objects**, which is a shallow copy. `Cloneable` is a marker interface that does not declare a public `clone()`. The cloning mechanism has limitations with final fields, invariants, resource ownership, and subclasses.

Do not choose `clone` just because the name sounds like “deep copy”; to isolate mutable components, you must write custom logic. For a class with final state and complex invariants, a copy constructor/factory is usually easier to control.

### 14.4. Record

A record has final component fields and generated accessors/methods, but passing a raw array into a component does not automatically clone the array. If the model represents immutable values, the record components must also be immutable or protected with corresponding defensive copies.

### 14.5. Choose by Contract, Not by API Name

There is no universal requirement that “you must use clone” or “a copy constructor is deep”. The method name should reflect the **level of independence** that the user needs.

## 15. Program: Copy Constructor Sharing Safe Parts

Save **`SelectiveCopyConstructorDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class SelectiveCopyConstructorDemo {
    static final class Plan {
        private final String id;
        private final int[] hours;

        Plan(String id, int[] hours) {
            this.id = Objects.requireNonNull(id, "id");
            this.hours = hours.clone();
        }

        Plan(Plan source) {
            this.id = source.id;
            this.hours = source.hours.clone();
        }

        int totalHours() {
            return Arrays.stream(hours).sum();
        }

        int[] copyHours() {
            return hours.clone();
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) {
        int[] draft = {2, 3};
        Plan original = new Plan("A", draft);
        Plan copy = new Plan(original);

        System.out.println("same plan=" + (original == copy));
        System.out.println("same id reference=" +
                (original.id() == copy.id()));

        draft[0] = 99;
        int[] outgoing = copy.copyHours();
        outgoing[1] = 88;

        System.out.println("original total=" +
                original.totalHours());
        System.out.println("copy total=" + copy.totalHours());
    }
}
~~~

Run:

~~~bash
javac SelectiveCopyConstructorDemo.java
java SelectiveCopyConstructorDemo
~~~

Output:

~~~text
same plan=false
same id reference=true
original total=5
copy total=5
~~~

The two Plans have different identities, share the immutable String ID, yet separately copy the mutable `int[]`. The initial constructor also clones draft; the accessor only returns a clone. This is an example of **copying just enough**: not copying String to make it “deeper”.

### 15.1. Why Is the String Identity Above Guaranteed to Be True?

The copy constructor assigns `this.id = source.id` directly; both fields hold **the same reference value**. The result does not rely on JVM String interning/caching. Do not use identity comparison to compare String contents in business logic — here it only checks component sharing.

## 16. Ownership Cannot Be “Transferred” by Words Alone

An API might state:

~~~java
void takeOwnership(List<String> list) {
    this.items = list;
}
~~~

If the caller still holds `list` or another alias, it can still `add/remove` and alter the receiver's state. Java does not invalidate old references when passed by value.

### 16.1. Program Demonstrating the Risk of a Transfer Convention

Save **`OwnershipTransferConventionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OwnershipTransferConventionDemo {
    static final class Warehouse {
        private final List<String> items;

        Warehouse(List<String> transferred) {
            // Only safe if the caller actually stops using all aliases.
            items = transferred;
        }

        String contents() {
            return items.toString();
        }
    }

    static final class SafeWarehouse {
        private final List<String> items;

        SafeWarehouse(List<String> source) {
            items = List.copyOf(source);
        }

        String contents() {
            return items.toString();
        }
    }

    public static void main(String[] args) {
        List<String> draft = new ArrayList<>(List.of("A"));
        List<String> alias = draft;

        Warehouse live = new Warehouse(draft);
        SafeWarehouse saved = new SafeWarehouse(draft);

        alias.add("B");

        System.out.println("live=" + live.contents());
        System.out.println("saved=" + saved.contents());
    }
}
~~~

Run:

~~~bash
javac OwnershipTransferConventionDemo.java
java OwnershipTransferConventionDemo
~~~

Output:

~~~text
live=[A, B]
saved=[A]
~~~

**Explanation:** although the caller “hands” draft over to Warehouse, it still has an alias and modifies it. Warehouse reads live values. SafeWarehouse copies the structure right at the boundary, so it has a snapshot that is not affected by structural changes via the alias. Because the elements are immutable Strings, this snapshot is sufficient.

If you genuinely want to share a live structure, Warehouse can be right **when the API publicly declares those semantics**; it is only wrong if the receiver promises an independent snapshot.

## 17. Object Graphs with Cycles: Node-by-Node Copying Must Preserve Identity Logic

When an object graph contains a cycle A→B→A or two edges pointing to the same child, shallow-copying a single node keeps references to the old graph. If the business requirement calls for copying **the entire owned subgraph**, references must be reconstructed for the new graph.

A naive recursive deep copy that does not remember visited nodes risks a `StackOverflowError` on cycles or creating multiple copies for a single shared node.

The common approach is memoization by **reference identity**: `IdentityHashMap<OldNode, NewNode>`. Record the mapping as soon as the outer node copy is created, then recursively copy the edges; subsequent encounters with the old node reuse the existing copy.

### 17.1. Graph Copy Program Preserving Aliases and Cycles

Save **`GraphOwnershipCopyDemo.java`**:

~~~java
import java.util.IdentityHashMap;

public class GraphOwnershipCopyDemo {
    static final class Node {
        String label;
        Node next;
        Node shortcut;

        Node(String label) {
            this.label = label;
        }
    }

    static Node copyGraph(
            Node root, IdentityHashMap<Node, Node> seen) {
        if (root == null) {
            return null;
        }

        Node existing = seen.get(root);
        if (existing != null) {
            return existing;
        }

        Node result = new Node(root.label);
        seen.put(root, result);

        result.next = copyGraph(root.next, seen);
        result.shortcut = copyGraph(root.shortcut, seen);
        return result;
    }

    static Node copyGraph(Node root) {
        return copyGraph(root, new IdentityHashMap<>());
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        a.shortcut = b;
        b.next = a;

        Node copied = copyGraph(a);

        System.out.println("new root=" + (copied != a));
        System.out.println("new child=" + (copied.next != b));
        System.out.println("shared edges=" +
                (copied.next == copied.shortcut));
        System.out.println("cycle preserved=" +
                (copied.next.next == copied));

        copied.next.label = "NEW";
        System.out.println("original child=" + b.label);
        System.out.println("copied child=" + copied.next.label);
    }
}
~~~

Run:

~~~bash
javac GraphOwnershipCopyDemo.java
java GraphOwnershipCopyDemo
~~~

Output:

~~~text
new root=true
new child=true
shared edges=true
cycle preserved=true
original child=B
copied child=NEW
~~~

**Important regarding copy scope:** this code copies **the entire reachable Node graph** along the `next` and `shortcut` edges. It is only appropriate if the caller has the right to create a new graph version with those semantics. If an edge points to an external shared service/resource, you should not arbitrarily deep-copy the resource; vary the policy by edge type.

For large graphs, you also need to consider recursion depth, memory use, concurrent mutations, and snapshot consistency.

## 18. Shared Mutable Resources Are Not Value Objects to Clone

File handles, sockets, database connections, executors, native buffers, and transaction contexts have their own ownership and lifecycle. A wrapper's copy constructor may create a new wrapper while **still keeping the same resource reference**.

If wrapper A closes the resource, wrapper B can also lose the ability to use it. That is **shared resource ownership**, not a deep copy.

### 18.1. Program: Resource Borrowed and Closed

Save **`ResourceOwnershipDemo.java`**:

~~~java
public class ResourceOwnershipDemo {
    static final class Resource implements AutoCloseable {
        private boolean closed;

        String status() {
            return closed ? "closed" : "open";
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    static final class BorrowingClient {
        private final Resource resource;

        BorrowingClient(Resource resource) {
            this.resource = resource;
        }

        BorrowingClient(BorrowingClient source) {
            resource = source.resource;
        }

        String observe() {
            return resource.status();
        }

        // Do not close here because the client only borrows the resource.
    }

    public static void main(String[] args) {
        Resource owner = new Resource();
        BorrowingClient one = new BorrowingClient(owner);
        BorrowingClient two = new BorrowingClient(one);

        System.out.println("before one=" + one.observe());
        System.out.println("before two=" + two.observe());

        owner.close();

        System.out.println("after one=" + one.observe());
        System.out.println("after two=" + two.observe());
    }
}
~~~

Run:

~~~bash
javac ResourceOwnershipDemo.java
java ResourceOwnershipDemo
~~~

Output:

~~~text
before one=open
before two=open
after one=closed
after two=closed
~~~

This is a simulated resource to clarify **same reference + shared lifecycle**. In real applications, close semantics may differ, and a wrapper must not continue using a closed resource.

**Principle:** identify **one owner responsible for closing** or use reference counting/lifecycle orchestration as needed; do not duplicate or close arbitrarily just because the outer wrapper was “copied”.

## 19. Multithreading: A Shallow Copy Does Not Make a Mutable Child Safe

Suppose two different `SnapshotView` instances both hold a reference to one `MutableCounter`. Even though the outer objects are independent, two threads using them can still read/write **the same counter**.

When multiple readers need the same **unchanging** data, you can snapshot **the value** into an immutable record. If consumers intentionally use a live counter, appropriate concurrency primitives/locks are needed.

### 19.1. Shared Counter and Immutable Snapshot Demo

Save **`SharedMutableCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SharedMutableCounterDemo {
    static final class Viewer {
        private final AtomicInteger counter;

        Viewer(AtomicInteger counter) {
            this.counter = counter;
        }

        Viewer(Viewer source) {
            this.counter = source.counter;
        }

        int current() {
            return counter.get();
        }
    }

    record CounterSnapshot(int value) {
    }

    public static void main(String[] args) {
        AtomicInteger shared = new AtomicInteger(5);
        Viewer first = new Viewer(shared);
        Viewer second = new Viewer(first);
        CounterSnapshot frozen = new CounterSnapshot(shared.get());

        System.out.println("same counter=" +
                (first.counter == second.counter));
        System.out.println("snapshot before=" + frozen.value());

        shared.incrementAndGet();

        System.out.println("first=" + first.current());
        System.out.println("second=" + second.current());
        System.out.println("snapshot after=" + frozen.value());
    }
}
~~~

Run:

~~~bash
javac SharedMutableCounterDemo.java
java SharedMutableCounterDemo
~~~

Output:

~~~text
same counter=true
snapshot before=5
first=6
second=6
snapshot after=5
~~~

`AtomicInteger` provides atomic operations for **a single counter**; it does not turn a multi-field business transaction into an atomic operation. `CounterSnapshot` captures a primitive value, with no remaining live alias.

### 19.2. Publication and Temporal Snapshots

An immutable object graph should be completely constructed, then its reference published according to the Java Memory Model when other threads need to see that version. `volatile`, locks, thread-safe queues/executors, and appropriately constructed final fields each have their own rules.

Merely copying an object **does not by itself solve** a data race when the source is mutated concurrently while the snapshot is being created; a multi-field value snapshot can contain a mix of different points in time without appropriate synchronization/transactions.

## 20. Program: Sharing Immutable Versions, Replacing the Reference at the Owner

Save **`ImmutableVersionDemo.java`**:

~~~java
import java.util.List;

public class ImmutableVersionDemo {
    record Config(int version, List<String> features) {
        Config {
            features = List.copyOf(features);
        }
    }

    static final class ConfigHolder {
        private volatile Config current;

        ConfigHolder(Config initial) {
            current = initial;
        }

        Config snapshot() {
            return current;
        }

        void publish(Config next) {
            current = next;
        }
    }

    public static void main(String[] args) {
        ConfigHolder holder = new ConfigHolder(
                new Config(1, List.of("search")));

        Config old = holder.snapshot();

        holder.publish(new Config(
                2, List.of("search", "report")));

        Config recent = holder.snapshot();

        System.out.println("old version=" + old.version());
        System.out.println("old features=" + old.features());
        System.out.println("recent version=" + recent.version());
        System.out.println("recent features=" + recent.features());
    }
}
~~~

Run:

~~~bash
javac ImmutableVersionDemo.java
java ImmutableVersionDemo
~~~

Output:

~~~text
old version=1
old features=[search]
recent version=2
recent features=[search, report]
~~~

These are two **immutable snapshots** with String elements, with no mutation of old. Holder uses a `volatile` reference to publish versions using a common memory-visibility mechanism.

**Limitation:** `volatile` alone does not prevent two writers from experiencing a lost update in a read-modify-write workflow. If compare-and-set is needed, consider `AtomicReference` or appropriate synchronization. Immutability separates the stability of **each version** from the coordination of **changing versions**.

## 21. Mutable Hash Keys: Why You Must Choose a Snapshot by Stable Identity

`HashMap`/`HashSet` assume that the information used by a key/element's `equals`/`hashCode` is not modified in a way that breaks lookup while the key/element remains in the collection.

A mutable `Order` class has `id`, `status`, and `amount` fields. If the business identity is the ID, you can choose an immutable `OrderKey(id)` as the map key instead of using the entire mutable Order. This separates ownership of entity state from key equality.

### 21.1. Key Snapshot Program

Save **`StableKeySnapshotDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class StableKeySnapshotDemo {
    static final class MutableProduct {
        String sku;
        long price;

        MutableProduct(String sku, long price) {
            this.sku = sku;
            this.price = price;
        }

        void changePrice(long next) {
            price = next;
        }
    }

    record ProductKey(String sku) {
    }

    public static void main(String[] args) {
        MutableProduct product = new MutableProduct("PEN", 10);

        ProductKey stable = new ProductKey(product.sku);
        Map<ProductKey, String> map = new HashMap<>();
        map.put(stable, "item");

        product.changePrice(20);

        System.out.println("current price=" + product.price);
        System.out.println("key sku=" + stable.sku());
        System.out.println("lookup=" +
                map.get(new ProductKey("PEN")));
    }
}
~~~

Run:

~~~bash
javac StableKeySnapshotDemo.java
java StableKeySnapshotDemo
~~~

Output:

~~~text
current price=20
key sku=PEN
lookup=item
~~~

The key is an immutable record containing only the String SKU, with equality/hash based on SKU, so changing the mutable Product.price does not change the key. This is appropriate **if SKU is a stable business identity according to the domain**. If SKU can change or be reused, a different key identity must be defined.

### 21.2. Copying a List Does Not Solve Mutable Keys

`Map.copyOf` or `new HashMap<>(sourceMap)` does not automatically deep-copy key objects. If the original map uses unstable mutable keys, copying the map structure still uses the same keys by reference. **Fix the key contract/ownership** rather than just creating a new map.

## 22. Copy-on-Write and Structural Sharing

When data has many readers and few writers, one design approach is **copy-on-write**:

1. The writer takes the old version.
2. It builds a new version (copying the needed structure, sharing immutable elements).
3. It publishes the reference to the new version according to the concurrency protocol.
4. Readers that already obtained the old version continue reading the old snapshot.

### 22.1. Not `CopyOnWriteArrayList` for Every Case

Java has `CopyOnWriteArrayList`, which uses copy-on-write on its internal array structure for updates; it suits certain read-mostly workloads, but writes have a cost. Element objects can still be mutable.

### 22.2. Persistent Data Structures

A persistent tree/list can share **immutable nodes** across versions instead of copying everything. However, you must choose a data structure/library with an appropriate contract; `new ArrayList<>(source)` does not create a persistent list, and `List.copyOf` does not guarantee any structural sharing algorithm for arbitrary updates.

### 22.3. When Copying Less Is Safer

If an immutable tree node contains immutable children, an update may only create nodes along the path from the root to the changed leaf, sharing the remaining branches. This is safe because **nobody mutates the shared nodes**.

If shared nodes are mutable, structural sharing must be paired with extremely clear ownership/coordination; otherwise, readers of an old snapshot will see unexpected changes.

## 23. Shallow Copies Still Keep Graph Backlinks as Before

A root A has a child C, and child C has a backlink to A. If A is shallow-copied into A2 by copying the `child` field, A2 still points to **the old C**, and C still points back to the old A.

~~~text
A  ----child----> C ----parent----> A

A2 ----child----> C ----parent----> A
~~~

If business logic requires `child.parent == newRoot`, a shallow copy **does not satisfy it**, even though `newRoot != oldRoot`.

### 23.1. Resolution Approaches

- If sharing C is intentional, do not expect the backlink to point to A2.
- If a copied owned graph is needed, copy C and update C2.parent to point to A2.
- If the graph has cycles/multiple parents, use a memoization identity map as in the GraphOwnershipCopyDemo example.
- If edges point to external objects (shared service), identify which edges do **not** belong to the owned subgraph and keep the reference unchanged.
- Ensure that the graph's invariant is not broken midway through steps in a concurrent environment.

## 24. Multi-Level Copying: You Must Define What “Deep Enough” Means

**Primitive array:** cloning `int[]` creates independent values.

**Object array:** cloning `Item[]` creates a new array, while Item references are shared.

**Primitive matrix:** `int[][]` clone copies only the outer array; each row must be cloned if you want to isolate rows. Null rows need to be handled.

**List<List<String>>:** copying the outer list does not copy the inner lists; if inner lists are mutable, you may need to snapshot each inner list.

**List<ImmutableRecord>:** copying/snapshotting the outer list may be enough because elements are immutable, with no need to create new record instances.

**Graph with cycles:** requires a graph-aware copy if independence across all owned nodes is desired.

An API stating “deep copy” must specify **ownership/depth boundaries**; it cannot be interpreted as copying everything ad infinitum, especially resources and external shared nodes.

### 24.1. Nested List Snapshots Demo

Save **`NestedListSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedListSnapshotDemo {
    static List<List<String>> snapshot(
            List<List<String>> input) {
        List<List<String>> rows = new ArrayList<>();
        for (List<String> row : input) {
            rows.add(List.copyOf(row));
        }
        return List.copyOf(rows);
    }

    public static void main(String[] args) {
        List<String> row = new ArrayList<>(List.of("A"));
        List<List<String>> matrix = new ArrayList<>();
        matrix.add(row);

        List<List<String>> shallow = new ArrayList<>(matrix);
        List<List<String>> fixed = snapshot(matrix);

        row.add("B");
        matrix.add(new ArrayList<>(List.of("C")));

        System.out.println("source row=" + matrix.get(0));
        System.out.println("shallow row=" + shallow.get(0));
        System.out.println("fixed row=" + fixed.get(0));
        System.out.println("source rows=" + matrix.size());
        System.out.println("shallow rows=" + shallow.size());
        System.out.println("fixed rows=" + fixed.size());
    }
}
~~~

Run:

~~~bash
javac NestedListSnapshotDemo.java
java NestedListSnapshotDemo
~~~

Output:

~~~text
source row=[A, B]
shallow row=[A, B]
fixed row=[A]
source rows=2
shallow rows=1
fixed rows=1
~~~

This is a **selective deep structural snapshot** of two levels of lists, safe in the example because String elements are immutable. If the elements are mutable custom objects, they also need to be snapshotted.

`List.copyOf` from a source being mutated **concurrently** does not automatically produce an atomic multi-element snapshot; the caller must ensure the input is stable or use appropriate synchronization.

## 25. Performance: “Copy for Safety” Also Needs Proper Measurement

A program that deep-copies unconditionally can:

- Create many objects, increasing heap usage and GC work.
- Increase the time spent traversing the entire graph.
- Lose identity sharing that the domain needs.
- Incur I/O cost if trying to serialize/deserialize everything.
- Fail on cycles, non-serializable fields, or resource handles.
- Add complexity to constructors/cloners.

Conversely, failing to copy when an independent snapshot is needed can produce hard-to-detect bugs.

### 25.1. Reference Costs, Not a Benchmark

| Operation | Typical Cost by Size n | What to Check |
| --- | --- | --- |
| Reference assignment | O(1) | No ownership separation |
| Copy `int[]` of length n | O(n) | Values are isolated independently |
| Copy `ArrayList` of length n | O(n) | Element references are still shared |
| Snapshot nested list with m total elements | O(m) depending on levels | Mutable elements may not be copied |
| Copy graph with V nodes, E edges | O(V+E) for standard traversal | Identity map, memory, cycles |
| Structural sharing update in a balanced tree | Potentially O(log n) depending on implementation | Do not infer this from Java List.copyOf |
| Serialize→deserialize | Depends on format/graph/I/O | Not automatically suitable for resources/identity |

These complexities are typical algorithmic models; real implementations and workloads require profiling. Optimization is valuable once **correctness, ownership, and contracts are clear**.

## 26. When Should You Use an Immutable Snapshot from the Start?

If data needs to be widely shared (across multiple modules, caches, async handlers), it is often worthwhile to build an **immutable value representation** at the boundary.

Advantages:

- No need to copy a truly immutable value again every time it crosses a layer.
- Multiple consumers can hold references without worrying that the source will mutate the value.
- `equals`/`hashCode` remain stable if implemented properly and fields belong to an immutable graph.
- Easy to create new versions, events, and historical snapshots.
- Reduces the need for dedicated locks solely to protect unchanging state.

Remember that **a record is not automatically deeply immutable**. A record holding a `byte[]`, `List<MutablePayload>`, or resource reference can still observe mutation. Use immutable elements or defensive copies according to the exact ownership boundary.

## 27. Choosing How to Copy When an Object Still Changes by Business Logic

A domain entity such as `BankAccount` or `Order` has a mutable lifecycle. It is not necessary to turn the entire entity into an immutable object and copy it on every change; you can use:

- A mutable aggregate inside the boundary owned by the service/transaction.
- An immutable command DTO to receive requests.
- An immutable snapshot/result DTO to return data outward.
- Immutable value objects for IDs, Money, and Coordinates.
- Copying a field-specific representation when exporting reports or emitting events.

**Do not use a shallow copy of a mutable entity as a substitute for a transaction snapshot**: it can retain aliases to nested mutable state, causing an old report to see new values after business state changes.

### 27.1. The “Mutate Locally, Publish Immutably” Rule

A practical strategy:

1. Allow a temporary mutable builder/list within a narrow ownership scope.
2. Validate/normalize data during construction.
3. Convert to an immutable record/final value class, defensively copying mutable components.
4. Publish the immutable result.
5. On each update, create a new version or let the owner control the update and then emit a new snapshot.

This principle is useful when consumers do not need to modify the source, though it does not replace resource ownership or transaction rules.

## 28. Integrated Program: Mutable Builder, Immutable Result, Without Redundant String Copying

Save **`BuilderToSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BuilderToSnapshotDemo {
    record Task(String title, int points) {
        Task {
            Objects.requireNonNull(title, "title");
            if (points < 0) {
                throw new IllegalArgumentException("points");
            }
        }
    }

    record Plan(List<Task> tasks) {
        Plan {
            tasks = List.copyOf(tasks);
        }

        int points() {
            int result = 0;
            for (Task task : tasks) {
                result = Math.addExact(result, task.points());
            }
            return result;
        }
    }

    static final class Builder {
        private final List<Task> tasks = new ArrayList<>();

        Builder add(Task task) {
            tasks.add(Objects.requireNonNull(task));
            return this;
        }

        Plan build() {
            return new Plan(tasks);
        }
    }

    public static void main(String[] args) {
        Builder builder = new Builder().add(new Task("A", 2));

        Plan first = builder.build();
        builder.add(new Task("B", 3));
        Plan second = builder.build();

        System.out.println("first size=" + first.tasks().size());
        System.out.println("first points=" + first.points());
        System.out.println("second size=" + second.tasks().size());
        System.out.println("second points=" + second.points());
        System.out.println("first task shared=" +
                (first.tasks().get(0) == second.tasks().get(0)));
    }
}
~~~

Run:

~~~bash
javac BuilderToSnapshotDemo.java
java BuilderToSnapshotDemo
~~~

Output:

~~~text
first size=1
first points=2
second size=2
second points=5
first task shared=true
~~~

Builder has an internal mutable list, whereas Plan snapshots are unmodifiable. `Task` records contain only immutable String/primitive values, so sharing a Task reference across versions is safe; **there is no need to clone Task**, even when the outer list differs.

## 29. API Contract: Naming and Documentation That Avoid Misunderstanding

Instead of merely declaring:

~~~java
Data copy();
~~~

consider names/contracts:

- `shallowCopy()`: creates a new outer object, keeping component references unchanged.
- `toImmutableSnapshot()`: creates a stable value based on the listed set of fields.
- `copyWithOwnItems()`: isolates owned mutable elements.
- `view()`: returns a live view that may reflect source changes.
- `copyItems()`: returns a new mutable container with elements according to the contract.
- `borrowResource()`: borrows the handle; the caller does not own closing it.
- `withField(next)`: returns a new value object instead of mutating the original.

The names above are **design suggestions**, not built-in Java methods. The API documentation must still answer: **new outer identity? which components are shared? mutable? null? lifetime? ownership? thread safety?**.

### 29.1. Example of a Transparent Contract

A constructor stating:

> Holds an **immutable snapshot** of the line list and monetary values at construction time. The caller may continue modifying the original collection without affecting the invoice. String and immutable ID values may share references.

is clearer than the sentence:

> The constructor copies the list.

Because the second sentence does not tell whether it is a snapshot or live, whether it copies the list or each element, or whether it is mutable or unmodifiable.

## 30. Common Mistakes and Fixes

| Mistake | Correct Understanding/Fix |
| --- | --- |
| “`b = a` is a shallow copy.” | This is only reference assignment; it does not create a new outer object |
| “Once the owner receives a reference, external aliases automatically become invalid.” | Java does not have automatic move invalidation |
| “A final reference makes the child object immutable.” | Final prevents reassigning the field; it does not freeze the referenced object |
| “Since there is no setter, storing raw mutable input is safe.” | The caller still has an alias; a defensive copy is needed for a snapshot |
| “The getter returns the internal array because the field is private.” | The getter exposes an alias; return a clone/snapshot per the contract |
| “Copying a List means cloning every Item.” | Copying a List only copies the structure/references |
| “List.copyOf makes elements immutable.” | The structure is unmodifiable, while mutable elements remain shared |
| “An unmodifiable view is a snapshot.” | A view can reflect mutations to the backing collection |
| “A record is always deeply immutable.” | Record components can hold mutable refs |
| “`clone()` always creates a deep copy.” | Object.clone defaults to a field-by-field shallow copy |
| “Deep copy must clone String and LocalDate too.” | Immutable values can share references |
| “Copying a parent automatically updates child.parent.” | The backlink still points to the old graph if it is only a shallow copy |
| “Copying a graph can just recurse without a map.” | Cycles/shared nodes require identity memoization |
| “Copying a wrapper with a Connection yields a new Connection.” | The resource reference/lifecycle may be shared |
| “Copying an object is enough for an atomic snapshot across multiple threads.” | Concurrent source mutation still requires synchronization |
| “Immutable snapshots make holder updates atomic.” | Publishing/read-modify-write still requires coordination |
| “Copying a Map fixes mutable key hashing.” | Key references may still be mutable; snapshot key identity |
| “Never copying is optimal.” | Snapshot correctness may require copying |
| “Always deep-copying everything is safe.” | Costly, breaks identity, and cannot copy resources |
| “Copy must return a different instance every time.” | For immutable values/snapshot APIs, sharing/reusing is possible |
| “Equal hash codes prove the same object.” | Hash collisions are valid; use `==` to compare identity |
| “Copying causes GC to reclaim the source immediately.” | GC is based on reachability; copies/aliases can extend lifetime |

## 31. Checklist Before Choosing a Strategy

1. **Which objects are truly owned by this module?** Which references are still held externally?
2. **Is the data mutable?** Check nested arrays, collection elements, and custom objects.
3. **Will the callee only read temporarily or retain the reference past the call?**
4. **Does the receiver need live changes or the state captured at time T?**
5. **Is a distinct identity required?** Must the result be a different object, or is value semantics enough?
6. **Are there immutable components that can be shared to reduce copying?**
7. **Does a mutable component allowed to be shared have ownership/concurrency rules?**
8. **Does the API need to copy at the input, output, or both boundaries?**
9. **If it is a list/map snapshot, can elements/values also be modified through an alias?**
10. **If copying a graph, which invariants must nodes/cycles/shared edges/backlinks preserve?**
11. **Is there an external resource that must not be copied like a value object?**
12. **Is any HashMap key participating in equality/hash modified after storage?**
13. **Can the source be modified by other threads during the copy?** If so, what is the consistency protocol?
14. **Does a version update require atomic publication or compare-and-set?**
15. **How many objects might the copy create?** Is it worth profiling?
16. **Does the contract clearly state lifetime, mutability, and the ownership transfer convention?**
17. **Have tests tried mutating through input/output aliases and nested elements?**
18. **If a bug arises because the representation changes later, which test detects that the copy is no longer deep enough?**

## 32. Practice Exercises with Answers

**Question 1.** Does `Person b = a;` create a new Person?  
**Answer:** No, it only copies the reference value into variable b.

**Question 2.** Is `new Person(a)` guaranteed to create a deep copy?  
**Answer:** No. A copy constructor can be shallow/deep/selective depending on its body.

**Question 3.** When is sharing a `String`/`LocalDate` reference reasonable?  
**Answer:** When that value is truly immutable and the contract only needs reading, without needing an independent object identity.

**Question 4.** When a mutable `Address` is shallow-copied by Person, who experiences the mutation?  
**Answer:** All aliases to the same Address can observe changes; an ownership/mutation contract is needed.

**Question 5.** If the Person copy has a different outer identity, does reassigning `copy.address` automatically modify `original.address`?  
**Answer:** No, that is a field of the outer copy, assuming no other side effects.

**Question 6.** If `copy.address.setCity(...)` is called, can original's city change?  
**Answer:** Yes, if the Address reference is shared.

**Question 7.** What should an API do if it stores a `byte[]` input to compute a checksum over the long term?  
**Answer:** Defensively copy the input if an independent snapshot is needed and the caller still holds an alias.

**Question 8.** The constructor clones the input array, and the getter returns the internal array: is two-way protection achieved?  
**Answer:** No, the getter still exposes a mutable alias; it should return a copy if the contract requires it.

**Question 9.** Does `new ArrayList<>(source)` copy element objects?  
**Answer:** No, it copies element references.

**Question 10.** Does `List.copyOf(source)` create a deep immutable graph?  
**Answer:** No; the structure is unmodifiable, while mutable elements can still be shared.

**Question 11.** Does `Collections.unmodifiableList(source)` guarantee keeping a snapshot when source adds elements?  
**Answer:** No; it is typically an unmodifiable live view.

**Question 12.** Does `List.copyOf` always create a new list identity?  
**Answer:** No, it can reuse a suitable unmodifiable input list.

**Question 13.** Does `record Snapshot(int[] bytes)` automatically clone the array?  
**Answer:** No. Defensive copies are needed if independence is desired.

**Question 14.** In a shallow copy of `List<MutableItem>`, will an item rename through source show up in the copy?  
**Answer:** Yes, if they share the same Item references.

**Question 15.** If you want to keep a fixed quote from a mutable Product, do you copy the entire Product or snapshot the Price value?  
**Answer:** Usually snapshot the immutable SKU/price/quantity values according to the contract to be preserved.

**Question 16.** Why is a snapshot not automatically atomically consistent if the source is mutated concurrently?  
**Answer:** Multiple reads of mutable fields can observe different points in time; synchronization/transactions are needed.

**Question 17.** Does Java automatically invalidate old references after “transfer ownership”?  
**Answer:** No, transfer is usually a convention/protocol.

**Question 18.** When cloning Node A whose child has a backlink to A, does the backlink automatically change to the copy of A?  
**Answer:** No, unless the graph-copy logic updates the edge.

**Question 19.** Why should a graph with cycles use `IdentityHashMap` when deep cloning?  
**Answer:** Memoizing by identity avoids repeatedly cloning nodes, prevents recursion cycles, and preserves shared-edge structure.

**Question 20.** Does copying a wrapper containing a socket create another socket?  
**Answer:** No. The resource remains shared if the wrapper only copies the reference.

**Question 21.** If two viewers share the same `AtomicInteger`, is the value live?  
**Answer:** Yes, both observe the same shared mutable counter.

**Question 22.** If storing `CounterSnapshot(int)`, does changing the counter modify the snapshot?  
**Answer:** No; the primitive value was captured at creation time.

**Question 23.** What does `volatile Config current` with an immutable Config solve?  
**Answer:** Publication/visibility of the version reference; it does not automatically prevent lost updates from multiple writers.

**Question 24.** Does `new HashMap<>(source)` deep-copy mutable keys?  
**Answer:** No, key references remain shared; key state/equality/hash must be kept stable.

**Question 25.** Why is `record ProductKey(String sku)` usually better than a mutable Product as a key?  
**Answer:** The key value is stable if SKU is the appropriate identity, without changing with Product.price/status.

**Question 26.** Is copying every immutable `Task` record before putting them into a new list mandatory?  
**Answer:** No; immutable elements can be safely shared with respect to mutation.

**Question 27.** If the task list is large and updated frequently, what is the cost of copying the entire list each time?  
**Answer:** Potentially O(n) per update and increased GC pressure; consider persistent structures/workload.

**Question 28.** Can a mutable builder create different immutable Plan versions?  
**Answer:** Yes, if Plan snapshots the structure/values at the build boundary.

**Question 29.** To verify that an API copies properly, is checking `equals` alone enough?  
**Answer:** No. You need to check outer/child identities and mutation isolation/sharing according to the contract.

**Question 30.** On what principle should you choose how to copy?  
**Answer:** **Copy the exact mutable values that require independent ownership; share immutable values or live resources that have a clear contract.**

## 33. References

- Java Language Specification (Java SE 17), [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): references and objects.
- Java Language Specification, [`15.26 — Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26): assignment semantics.
- Java Language Specification, [`10.7 — Array Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.7): array clone and members.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): generated record components/accessors.
- Java Language Specification, [`17.4 — Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): concurrency/happens-before.
- Java Language Specification, [`17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): correctly constructed final fields.
- Java API Java SE 17, [`Object.clone()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()): cloning contract and shallow copying.
- Java API, [`Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): marker interface.
- Java API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot structure.
- Java API, [`Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable map snapshot.
- Java API, [`Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): backed unmodifiable view.
- Java API, [`ArrayList(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)): copy list structure.
- Java API, [`IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): object-reference identity for graph memoization.
- Java API, [`AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic shared mutable counter.
- Java API, [`HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): key equality/hash.
- Java API, [`AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource lifecycle.

## Conclusion

**There is no “best copy” independent of ownership and mutability.** Reference assignment does not create a new object. A shallow copy separates the outer structure while potentially sharing mutable components. A selective deep copy or immutable snapshot isolates **the values that must remain independent**, while continuing to share immutable String/record/LocalDate components.

Before every copy, ask **who owns it**, **who still holds an alias**, **who has permission to mutate**, **whether the receiver wants live state or a snapshot**, and **how long the data needs to live**. Choose defensive copying at input/output boundaries when a mutable representation must be protected; for graphs with cycles, preserve identity/sharing logic; for resources, define an owner responsible for closing. In concurrency, immutable values are useful, yet publication and mutable holders still require their own coordination.

Good design is often **mutable within a narrow ownership scope, immutable when exposing data for sharing**, and **minimal copying that is sufficient to uphold the contract**. Test with object identity `==`, state after mutation, and aliasing/nested-structure scenarios, rather than relying solely on names like `copy`, `clone`, or a promise of “deep”.
