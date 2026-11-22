# Defensive Copying of Mutable Inputs and Outputs in Java

## 1. Goal: What Data Must an Immutable Class Protect?

An **immutable object** is an object whose observable state does not change after it has been completely initialized according to the class's contract. In Java 17+, `private final` fields and `final class` help build that model, but **they do not automatically guarantee deep immutability** if a field holds a reference to a mutable object such as a `Date`, array, `List`, `Map`, or a class with setters.

Example of a class that looks immutable but is not:

~~~java
import java.util.Date;

final class Event {
    private final Date when;

    Event(Date when) {
        this.when = when;       // Keeps the input reference unchanged.
    }

    Date when() {
        return when;            // Returns the mutable field.
    }
}
~~~

This is an **illustrative declaration snippet**, not a standalone Java program.

A caller can modify the object through **two paths**:

~~~java
Date date = new Date(1_000);
Event event = new Event(date);

date.setTime(9_000);           // Leaks state through the input alias.
event.when().setTime(8_000);  // Leaks through getter output.
~~~

The `when` field is final, so it cannot be reassigned from code inside the class after construction; however, the referenced `Date` object can still change its contents. When external code holds a reference (*alias*) to that exact object, any valid mutations on the alias change the contents that Event sees.

**Defensive copying** is creating an appropriate copy at the **data ownership boundary** so that external code cannot modify internal state through references that it already holds or has just received.

Topic of this lesson: **defensive copying of mutable inputs and outputs**, under Java Core → Class/Object → Immutable Classes. The lesson covers constructor/input aliases, getter/output aliases, arrays, `Date`, collections, nested mutable objects, shallow/deep copying, unmodifiable views, Java 17 records, builders, validation/TOCTOU, concurrency, performance, common mistakes, and exercises. The sample programs include filenames, `javac`/`java` commands, and verifiable stdout.

## 2. Aliasing: The Core Reason Copying Is Needed

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;
second.append("B");
System.out.println(first); // AB
~~~

`first` and `second` point to the same StringBuilder. Reference assignment **does not copy the object**. Even when two variables are in two different classes, they can still point to the same mutable object.

Diagram when the constructor keeps the input as-is:

~~~text
Caller ───── input ────────┐
                           ▼
                         Date A
                           ▲
Event ───── field ─────────┘
~~~

Diagram when the getter returns the field directly:

~~~text
Event ─── field ────────> Date A
                           ▲
                           │
Caller <── getter ─────────┘
~~~

If the class copies properly in both directions:

~~~text
Caller ── input ──────> Date A
                            │  copy when receiving
                            ▼
Event ─── field ──────> Date B
                            │  copy when returning
                            ▼
Caller <── getter ────> Date C
~~~

Changes to Date A and Date C do not change Date B. The objects are independent with respect to the snapshotted mutable state.

### 2.1. Input Mistake

~~~java
class Config {
    private final List<String> roles;

    Config(List<String> roles) {
        this.roles = roles; // Does not create a snapshot.
    }
}
~~~

The caller still holds `roles` and calls `roles.clear()` after Config is created. Config cannot control the list that it promised to keep fixed.

### 2.2. Output Mistake

~~~java
List<String> roles() {
    return roles; // Caller can clear/add if the List is mutable.
}
~~~

A public or package-private getter can also expose state to code that can call it. `private` on a field only hides the field name; **it does not protect the object after a getter hands out the reference**.

### 2.3. The Two-Way Rule

| Constructor/input | Getter/output | Outcome |
| --- | --- | --- |
| Keeps mutable reference | Returns mutable reference | Leaks on both sides |
| Copies mutable input | Returns mutable field | Getter still exposes internals |
| Keeps mutable reference | Copies output | Caller can still mutate via input |
| Copies mutable input | Copies output or returns safe immutable view/snapshot | Can protect state, depending on copy depth |

An instance may **not need copying** when the value is already truly immutable, such as `String`, `Instant`, `LocalDate`, or an immutable value object containing no mutable children. Sharing immutable references is usually the simplest solution.

## 3. Crucial Step: Identifying Mutable Types and Observable State

Some types worth checking:

- `java.util.Date` has `setTime(long)`.
- `Calendar` can modify time fields.
- `byte[]`, `char[]`, `int[][]` allow reassigning elements.
- `ArrayList`, `HashSet`, `HashMap`, and many mutable implementations have `add`, `remove`, `put`.
- `StringBuilder`/`StringBuffer` have content-modifying operations.
- `ByteBuffer` can share backing bytes even when returning a read-only view.
- Custom POJOs such as `Address`, `OrderLine`, `MutableProduct` have setters.
- Java records have private final component references, **but can hold a mutable List/Date**.

Immutability must be evaluated by **everything the caller can observe**, not only by fields assigned once.

Ask explicitly:

1. Does an external caller hold an alias to the input object?
2. Can an internal object be modified through a getter/callback/stream?
3. Does copying the outer container still share nested mutable elements?
4. Do equality/hashCode depend on nested mutable state?
5. Does the API intentionally provide a snapshot or a live view?
6. Is another thread allowed to modify the data while the snapshot is being created?

It is the **data ownership and mutation contract** that determines where defensive copying is needed.

## 4. Copying `Date` in the Constructor and Getter

`Date` is a clear example because merely modifying milliseconds with `setTime` changes the state. A class holding a time period can protect itself using two principles:

- The constructor creates **new Date objects** from input values.
- Getters return **new Date objects** instead of internal fields.

### 4.1. Complete Program 1 — Both Input and Output Are Protected

Create the file **`DefensiveDateRangeDemo.java`**:

~~~java
import java.util.Date;
import java.util.Objects;

public class DefensiveDateRangeDemo {
    static final class Period {
        private final Date start;
        private final Date end;

        Period(Date inputStart, Date inputEnd) {
            Objects.requireNonNull(inputStart, "start");
            Objects.requireNonNull(inputEnd, "end");

            Date startCopy = new Date(inputStart.getTime());
            Date endCopy = new Date(inputEnd.getTime());

            if (startCopy.after(endCopy)) {
                throw new IllegalArgumentException("Khoảng thời gian sai");
            }

            this.start = startCopy;
            this.end = endCopy;
        }

        Date start() {
            return new Date(start.getTime());
        }

        Date end() {
            return new Date(end.getTime());
        }

        long durationMillis() {
            return Math.subtractExact(end.getTime(), start.getTime());
        }
    }

    public static void main(String[] args) {
        Date from = new Date(1_000);
        Date to = new Date(5_000);
        Period period = new Period(from, to);

        from.setTime(100_000);
        to.setTime(200_000);

        System.out.println("Stored start = "
                + period.start().getTime());
        System.out.println("Stored end = "
                + period.end().getTime());

        Date output = period.start();
        output.setTime(-10_000);

        System.out.println("After getter mutation = "
                + period.start().getTime());
        System.out.println("Duration = " + period.durationMillis());

        try {
            new Period(new Date(9_000), new Date(1_000));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 DefensiveDateRangeDemo.java
java DefensiveDateRangeDemo
~~~

**Exact stdout:**

~~~text
Stored start = 1000
Stored end = 5000
After getter mutation = 1000
Duration = 4000
Rejected = Khoảng thời gian sai
~~~

### 4.2. Step-by-Step Explanation

- The constructor calls `new Date(inputStart.getTime())` and `new Date(inputEnd.getTime())`. Those are two new objects, retaining no external Date references.
- The code modifies `from` and `to` after construction; internal start/end remain unchanged.
- `period.start()` creates a new Date. Modifying the `output` variable with `setTime` only affects the newly returned copy.
- Duration remains `5000 - 1000 = 4000`.
- When startCopy is after endCopy, the constructor throws an exception and does not return a valid Period.

### 4.3. Why **Copy Before Validating**?

The operation:

~~~java
if (inputStart.after(inputEnd)) {
    throw new IllegalArgumentException();
}
this.start = new Date(inputStart.getTime());
this.end = new Date(inputEnd.getTime());
~~~

can check **one state**, yet store **another state** if an alias modifies the input between the check and the copy. Better:

~~~java
Date s = new Date(inputStart.getTime());
Date e = new Date(inputEnd.getTime());
if (s.after(e)) {
    throw new IllegalArgumentException();
}
this.start = s;
this.end = e;
~~~

These are **fragments**, with the corresponding `inputStart`/`inputEnd`/fields. Validation is performed on **the copy that will actually be stored**. This reduces a class of *time of check / time of use* bugs.

**Limitation:** copying two mutable Date objects separately does not create an atomic snapshot across both under concurrent mutations from other threads. If consistency at the **exact same point in time** is required, an ownership/synchronization protocol or an immutable aggregate input is needed. For new APIs, `Instant` or `LocalDate` is generally preferred to eliminate most of this problem.

## 5. Arrays: Why `clone()` Is Useful but Requires Understanding Depth

Java arrays are mutable reference objects:

~~~java
byte[] raw = {1, 2};
raw[0] = 9;
~~~

If a class wants to keep the bytes fixed:

~~~java
private final byte[] payload;

Packet(byte[] source) {
    this.payload = source.clone();
}

byte[] payload() {
    return payload.clone();
}
~~~

`clone()` on a **one-dimensional array of primitives** creates a new array containing the corresponding primitive values. The caller cannot alter the internal payload by modifying source or the array returned by the getter.

### 5.1. Complete Program 2 — Protecting `byte[]`

Create the file **`DefensiveArrayDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class DefensiveArrayDemo {
    static final class Packet {
        private final byte[] payload;

        Packet(byte[] source) {
            Objects.requireNonNull(source, "source");
            payload = source.clone();
        }

        byte[] payload() {
            return payload.clone();
        }

        int sumUnsigned() {
            int sum = 0;
            for (byte b : payload) {
                sum += Byte.toUnsignedInt(b);
            }
            return sum;
        }
    }

    public static void main(String[] args) {
        byte[] input = {10, 20, 30};
        Packet packet = new Packet(input);

        input[0] = 99;
        System.out.println("After input edit = "
                + Arrays.toString(packet.payload()));

        byte[] output = packet.payload();
        output[1] = 88;
        System.out.println("After output edit = "
                + Arrays.toString(packet.payload()));

        System.out.println("Sum = " + packet.sumUnsigned());
        System.out.println("Output independent = "
                + (output != packet.payload()));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 DefensiveArrayDemo.java
java DefensiveArrayDemo
~~~

**Exact stdout:**

~~~text
After input edit = [10, 20, 30]
After output edit = [10, 20, 30]
Sum = 60
Output independent = true
~~~

### 5.2. `Arrays.copyOf` Can Replace clone

~~~java
byte[] safe = Arrays.copyOf(source, source.length);
~~~

Creates a new array having the same elements as the source array within the copy range, with length semantics according to the API. This is a similar option when snapshotting an array of primitives.

### 5.3. Two-Dimensional Arrays: Cloning the Outer Array Is Not Enough

~~~java
int[][] original = {{1, 2}, {3, 4}};
int[][] outerOnly = original.clone();

outerOnly[0][0] = 99;
System.out.println(original[0][0]); // 99
~~~

`outerOnly[0]` still points to the same `int[]` as `original[0]`. To protect down to the rows:

~~~java
int[][] deep = new int[original.length][];
for (int i = 0; i < original.length; i++) {
    deep[i] = original[i].clone();
}
~~~

This is a fragment applicable when rows are non-null. With arrays of mutable objects, even cloning each row still retains **references to the same child objects**; you must decide to create a copy of each object if their state must be immutable.

## 6. Collections: Three Concepts to Separate

### 6.1. Mutable List

`ArrayList` allows adding, modifying, and removing elements. If a class keeps and directly returns an `ArrayList`, external code can break the invariant.

### 6.2. Unmodifiable View

~~~java
List<String> view = Collections.unmodifiableList(source);
~~~

`view.add("B")` throws `UnsupportedOperationException`. However, source may still be modified through the **original reference**. If `source.add("B")`, the view usually **also shows B**. It blocks mutation **through the view**, rather than being an independent snapshot.

### 6.3. Unmodifiable Snapshot

~~~java
List<String> snapshot = List.copyOf(source);
~~~

`List.copyOf` creates an unmodifiable List with elements matching the input state at the time of copying; structural changes to `source` afterward do not alter the snapshot list. The API may reuse certain unmodifiable inputs instead of mandating allocation of a new object. Rely on **semantics**, without depending on `snapshot != source`.

**`List.copyOf` only copies element references**, and does not deep-copy mutable element objects. In `List<String>`, String is immutable, so that is usually sufficient. In `List<MutableProduct>`, the caller can still modify a shared Product.

### 6.4. Complete Program 3 — View and Snapshot

Create the file **`ListSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListSnapshotDemo {
    static final class Catalog {
        private final List<String> names;

        Catalog(List<String> input) {
            names = List.copyOf(input);
        }

        List<String> names() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        Catalog catalog = new Catalog(source);

        source.add("B");

        System.out.println("Source = " + source);
        System.out.println("View = " + view);
        System.out.println("Snapshot = " + snapshot);
        System.out.println("Catalog = " + catalog.names());

        try {
            catalog.names().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Catalog list cannot be edited");
        }
        System.out.println("Catalog after attempt = "
                + catalog.names());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ListSnapshotDemo.java
java ListSnapshotDemo
~~~

**Exact stdout:**

~~~text
Source = [A, B]
View = [A, B]
Snapshot = [A]
Catalog = [A]
Catalog list cannot be edited
Catalog after attempt = [A]
~~~

### 6.5. Why Is It Still Safe for Catalog to Return `names` Directly?

Catalog already stores an **unmodifiable snapshot with immutable String elements**. No mutable backing ArrayList is retained by Catalog and returned to external code; doing `return names` grants no permission to mutate that state.

**Do not mechanically copy every time a getter runs:** if the internal representation is already truly immutable, sharing it is both correct and saves allocations.

### 6.6. Null in `List.copyOf`

`List.copyOf` rejects null elements with a `NullPointerException`. If the valid domain allows null, you must design a different copy, for example:

~~~java
List<String> output = Collections.unmodifiableList(
        new ArrayList<>(source));
~~~

This is a fragment. The wrapper blocks structural modification through output; inside is a new ArrayList that exposes no alias if you do not share it elsewhere. However, mutable elements remain shared. An **unmodifiable view of a copy** differs from an **unmodifiable view of source itself**.

## 7. Shallow Copy and Deep Copy

- **Shallow copy:** creates a new container/outer object, while keeping references to nested objects.
- **Deep copy (within a scope):** creates appropriate copies of the nested mutable objects on which the state of the whole depends.
- **Immutable value:** does not need copying to avoid mutation if all observable nested state is also immutable.
- **Unmodifiable view:** disallows modification through the view, yet can reflect changes to the backing object made through another alias.

### 7.1. List of Mutable Elements: Shallow Is Not Enough

~~~java
final class MutableAddress {
    String city;

    MutableAddress(String city) {
        this.city = city;
    }
}

List<MutableAddress> source =
        new ArrayList<>(List.of(new MutableAddress("Hanoi")));

List<MutableAddress> list = List.copyOf(source);
source.get(0).city = "Hue";
System.out.println(list.get(0).city); // Hue
~~~

The List structure was not modified, yet the same MutableAddress object is shared. If the class promises an address snapshot, each Address must be copied (or converted into an immutable value).

### 7.2. How Deep Should You Copy?

There is no single Java Core operation that automatically deep-copies every object graph correctly for every domain. You must decide:

- Primitive fields: copy values.
- `String`, `Instant`, immutable records: usually reuse references.
- Mutable arrays/Lists/Maps: copy the container.
- Mutable elements: copy each element when needed.
- Nested mutable references: continue according to the scope contract.
- Cyclic/shared graphs: may require identity tracking or creating an immutable DTO projection.

**Do not clone resources such as sockets, database connections, or threads** merely because the outer object holds a reference to them; resource ownership/lifecycle is a separate concern.

## 8. Complete Program 4 — Copying a Mutable Child Object

Create the file **`NestedObjectCopyDemo.java`**:

~~~java
import java.util.Objects;

public class NestedObjectCopyDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = Objects.requireNonNull(city);
        }

        Address(Address other) {
            this(other.city);
        }

        void moveTo(String next) {
            city = Objects.requireNonNull(next);
        }

        String city() {
            return city;
        }
    }

    static final class ContactSnapshot {
        private final String name;
        private final Address address;

        ContactSnapshot(String name, Address inputAddress) {
            this.name = Objects.requireNonNull(name);
            this.address = new Address(
                    Objects.requireNonNull(inputAddress));
        }

        String name() {
            return name;
        }

        Address address() {
            return new Address(address);
        }
    }

    public static void main(String[] args) {
        Address input = new Address("Hanoi");
        ContactSnapshot contact = new ContactSnapshot("Lan", input);

        input.moveTo("Hue");
        System.out.println("After input change = "
                + contact.address().city());

        Address output = contact.address();
        output.moveTo("Danang");
        System.out.println("After output change = "
                + contact.address().city());

        System.out.println("Name = " + contact.name());
        System.out.println("Copies are distinct = "
                + (output != contact.address()));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 NestedObjectCopyDemo.java
java NestedObjectCopyDemo
~~~

**Exact stdout:**

~~~text
After input change = Hanoi
After output change = Hanoi
Name = Lan
Copies are distinct = true
~~~

Here the Address copy constructor creates a separate object. Since Address only holds an immutable String, the copy is deep enough for the illustrative contract. If Address had a mutable `int[] coordinates`, the copy constructor would also need to copy coordinates.

### 8.1. When Should It Be Replaced with an Immutable Address?

If the domain does not need an Address with a setter, use:

~~~java
record AddressValue(String city) {
    AddressValue {
        Objects.requireNonNull(city);
    }
}
~~~

With an immutable String, sharing the AddressValue reference is safe; there is no need to copy in every getter. **Defensive copying is a safeguard for mutable boundaries, whereas eliminating unnecessary mutability is usually simpler.**

## 9. Maps, Sets, and Nested Collections

In Java 17:

| API | Properties | What It Does Not Automatically Guarantee |
| --- | --- | --- |
| `List.copyOf(source)` | Unmodifiable structural List snapshot | Deep-copying mutable elements |
| `Set.copyOf(source)` | Unmodifiable Set | Deep-copying mutable elements |
| `Map.copyOf(source)` | Unmodifiable structural Map snapshot | Deep-copying mutable keys/values |
| `Collections.unmodifiableList(source)` | View unmodifiable through the view | Snapshot independent of source |
| `Collections.unmodifiableMap(source)` | View unmodifiable through the view | Immutable backing map |
| `new ArrayList<>(source)` | Mutable List structural copy | Preventing caller from modifying the copied List if exposed |
| `new HashMap<>(source)` | Mutable Map structural copy | Deep-copying nested objects |

`List.copyOf`, `Set.copyOf`, and `Map.copyOf` do not accept null elements/keys/values in their respective positions. When the domain allows null, design a different representation.

An unmodifiable Map with a `StringBuilder` value can still have its contents modified:

~~~java
Map<String, StringBuilder> map =
        Map.of("title", new StringBuilder("A"));
map.get("title").append("B"); // Valid: modifies the value object.
~~~

The Map does not support `put`, yet it does not automatically make StringBuilder immutable.

### 9.1. A Map of Lists Needs Copying at Both Levels

For `Map<String,List<String>>`, if the class wants a snapshot:

~~~java
Map<String, List<String>> nested = new HashMap<>();
for (Map.Entry<String, List<String>> entry : input.entrySet()) {
    nested.put(entry.getKey(), List.copyOf(entry.getValue()));
}
this.groups = Map.copyOf(nested);
~~~

This is a constructor fragment requiring the corresponding `groups` field. With immutable String keys/elements, the representation is protected at both levels.

**Do not print an entire `Map.copyOf` and assert a specific output order**: the API does not guarantee that iteration order matches insertion order. If ordering is part of the contract, choose another representation with documented ordering.

### 9.2. Complete Program 5 — Nested List in a Map

Create the file **`NestedCollectionsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class NestedCollectionsDemo {
    static final class Directory {
        private final Map<String, List<String>> groups;

        Directory(Map<String, List<String>> input) {
            Objects.requireNonNull(input, "input");

            Map<String, List<String>> copy = new HashMap<>();
            for (Map.Entry<String, List<String>> entry
                    : input.entrySet()) {
                copy.put(entry.getKey(),
                        List.copyOf(entry.getValue()));
            }
            groups = Map.copyOf(copy);
        }

        List<String> members(String group) {
            return groups.getOrDefault(group, List.of());
        }

        int groupCount() {
            return groups.size();
        }
    }

    public static void main(String[] args) {
        List<String> team = new ArrayList<>(List.of("Lan"));
        Map<String, List<String>> input = new HashMap<>();
        input.put("dev", team);

        Directory directory = new Directory(input);

        team.add("Minh");
        input.put("ops", new ArrayList<>(List.of("Hoa")));

        System.out.println("Members = " + directory.members("dev"));
        System.out.println("Group count = "
                + directory.groupCount());
        System.out.println("Unknown = "
                + directory.members("missing"));

        try {
            directory.members("dev").add("Extra");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Members are unmodifiable");
        }

        System.out.println("Members after attempt = "
                + directory.members("dev"));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NestedCollectionsDemo.java
java NestedCollectionsDemo
~~~

**Exact stdout:**

~~~text
Members = [Lan]
Group count = 1
Unknown = []
Members are unmodifiable
Members after attempt = [Lan]
~~~

`team.add` modifies the caller's mutable List, and `input.put` modifies the caller's Map. Directory holds separate snapshots, so neither operation affects the received data. The getter returns unmodifiable Lists containing Strings, so no repeated copying is needed on output.

## 10. Java 17 Records: private final Components Can Still Be Mutable References

~~~java
record UnsafeRecord(Date created) {
}
~~~

A record has no compiler-generated setters, yet:

~~~java
Date d = new Date(1_000);
UnsafeRecord unsafe = new UnsafeRecord(d);
d.setTime(5_000);
unsafe.created().setTime(9_000);
~~~

still causes the record to observe changing Date state. The compiler-generated getter **returns the reference**; a `final` component reference does not make Date immutable.

### 10.1. Compact Constructor Protecting Input

~~~java
record SafeRecord(Date created) {
    SafeRecord {
        Objects.requireNonNull(created);
        created = new Date(created.getTime());
    }
}
~~~

In the compact constructor, we reassign the `created` parameter to a copy; the record uses the new value when the implicit field assignment occurs after the body. Do not write field assignments that are invalid under the compact constructor rules.

### 10.2. Accessor Protecting Output

~~~java
record SafeRecord(Date created) {
    SafeRecord {
        Objects.requireNonNull(created);
        created = new Date(created.getTime());
    }

    @Override
    public Date created() {
        return new Date(created.getTime());
    }
}
~~~

Copying in the constructor is **not enough** if the accessor still returns the internal Date. Overriding the accessor as above creates a new Date for the caller.

### 10.3. Complete Program 6 — Record with List and Date

Create the file **`DefensiveRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Objects;

public class DefensiveRecordDemo {
    record Document(List<String> tags, Date created) {
        Document {
            tags = List.copyOf(tags);
            Objects.requireNonNull(created, "created");
            created = new Date(created.getTime());
        }

        @Override
        public Date created() {
            return new Date(created.getTime());
        }
    }

    public static void main(String[] args) {
        List<String> tags = new ArrayList<>(List.of("draft"));
        Date date = new Date(1_000);

        Document doc = new Document(tags, date);

        tags.add("external");
        date.setTime(5_000);

        System.out.println("Tags = " + doc.tags());
        System.out.println("Created = " + doc.created().getTime());

        doc.created().setTime(10_000);
        System.out.println("Created again = "
                + doc.created().getTime());

        try {
            doc.tags().add("edited");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Tags are unmodifiable");
        }
        System.out.println("Tags again = " + doc.tags());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 DefensiveRecordDemo.java
java DefensiveRecordDemo
~~~

**Exact stdout:**

~~~text
Tags = [draft]
Created = 1000
Created again = 1000
Tags are unmodifiable
Tags again = [draft]
~~~

### 10.4. Records and `equals/hashCode`

Record-generated equality/hashCode depend on the components. If a component is an uncopied mutable object, mutating that object can cause equality/hashCode to change while the record is used as a key in a `HashMap`/`HashSet`. Defensive copying protects both the immutability contract and key stability where appropriate.

Additional note: a record with an array component does not automatically deep-compare bytes using `Arrays.equals` as you might expect for a value type. If equality by array contents is needed, you must design it explicitly.

## 11. Other Types of Mutable Inputs

### 11.1. `StringBuilder`: Often Converted to String

~~~java
StringBuilder input = new StringBuilder("A");
String fixed = input.toString();
input.append("B");
System.out.println(fixed); // A
~~~

`String` is immutable, so the class can store `fixed` and return it from a getter without copying.

### 11.2. `Calendar` and `java.sql.Timestamp`

These are types with mutable state; merely retaining the caller's reference can allow state inside the class to change. For new code, consider snapshotting to immutable `java.time` types according to the actual temporal semantics (Instant for a point in time, LocalDate for a date without a time zone, etc.).

Do not convert Date/Calendar/Timestamp to LocalDate/Instant **mechanically**: time zones, precision, and domain semantics may differ. Copying/converting must preserve the exact meaning of the data.

### 11.3. `ByteBuffer`: A Read-Only View Is Not Necessarily a Snapshot

`buffer.asReadOnlyBuffer()` returns a read-only view, yet the buffer view may **share backing bytes**. If the caller still holds a writable alias to the backing buffer, they can modify the contents observed through the read-only view. When an API must keep an immutable binary snapshot, copy the bytes to be stored into separate storage according to a clear policy regarding position/limit/slice.

### 11.4. Getters Returning an Iterator or Stream

~~~java
Stream<Item> items() {
    return internalItems.stream();
}
~~~

This is a fragment depending on a field and `java.util.stream.Stream`. It **does not automatically create a snapshot**. The stream may still observe mutable internal elements/collection. If an immutable snapshot is genuinely needed, create the snapshot first and then stream from the stable representation.

### 11.5. Callbacks Exposing Mutable Objects

~~~java
listener.onChanged(internalMutableState);
~~~

Even if getters are defensive, a callback can still hand an internal object directly to a listener. In systems with external code or plugins, send an immutable event DTO/snapshot instead of an internally owned mutable object.

## 12. Copy-Before-Validate and Avoiding Re-Reading Input

A constructor needs to validate that a List is non-empty:

**Do not do this:**

~~~java
if (input.isEmpty()) {
    throw new IllegalArgumentException("Empty");
}
this.values = List.copyOf(input);
~~~

If another thread modifies input between `isEmpty` and `List.copyOf`, validation might check something different from the stored snapshot.

**Do this instead:**

~~~java
List<String> snapshot = List.copyOf(input);
if (snapshot.isEmpty()) {
    throw new IllegalArgumentException("Empty");
}
this.values = snapshot;
~~~

Now the code validates **the exact snapshot** intended to be stored.

### 12.1. Do Not Take a Snapshot Twice

~~~java
List<String> first = List.copyOf(input);
validate(first);
this.values = List.copyOf(input); // Might be a different state!
~~~

Better:

~~~java
List<String> snapshot = List.copyOf(input);
validate(snapshot);
this.values = snapshot;
~~~

The fragments above assume a corresponding `validate` method and field. Reading the mutable source **once**, validating on the snapshot, and storing that same snapshot reduces TOCTOU risk as well as waste.

### 12.2. No Atomic Snapshot Across Multiple Data Sources by Default

If a constructor accepts two mutable Lists that are updated by another thread, copying them sequentially may capture data from two different points in time. If a relationship between the two Lists requires a shared invariant, you must build a **transaction/synchronized snapshot protocol** or pass an immutable aggregate. Defensive copying prevents external modification **after** the snapshot is stored; it does not automatically guarantee everything comes from the same point in time.

## 13. Copying Input in Setters of a Mutable Class

Defensive copying is not only for immutable classes. A mutable class may need to ensure callers cannot alter internal state **outside a valid update API**:

~~~java
class RegionService {
    private List<String> regions = List.of();

    void setRegions(List<String> input) {
        List<String> snapshot = List.copyOf(input);
        if (snapshot.isEmpty()) {
            throw new IllegalArgumentException("Empty regions");
        }
        regions = snapshot;
    }

    List<String> regions() {
        return regions;
    }
}
~~~

The service is allowed to replace `regions` through the setter, so **the service object is not immutable**, yet each stored snapshot is unmodifiable and cannot be modified through an external input alias. If multithreaded, a visibility/synchronization protocol is needed for publishing the snapshot reference; this is a separate concern.

### 13.1. Builders and Factory Methods

A mutable builder typically accumulates a List/Map and then creates a value object. `build()` should create a snapshot/immutable representation; if a raw builder reference is retained, the caller could keep adding elements to the builder after the object is created and inadvertently change the object's contents.

~~~java
final class Config {
    private final List<String> regions;

    Config(List<String> input) {
        regions = List.copyOf(input);
    }
}
~~~

A builder can call `new Config(builderRegions)`. Even if the builder continues to be used, Config has already captured an independent snapshot.

### 13.2. Does an Unmodifiable Getter Always Need to Create a New List?

No. If the class already stores `List.copyOf(input)` and the elements are immutable, the getter can return that exact immutable snapshot. If the class keeps an internal mutable ArrayList because it needs to change, the getter can return `List.copyOf(internal)` so the caller gets a structural snapshot at the time of the call.

**Good design clearly documents whether a getter returns a “snapshot” or a “live view”.**

## 14. When Is an Unmodifiable View Sufficient to Hold a Snapshot?

It can be sufficient when the class **creates its own completely private mutable backing collection with no other alias permitted to modify it**, and only returns an unmodifiable wrapper:

~~~java
List<String> copy = new ArrayList<>(input);
this.names = Collections.unmodifiableList(copy);
~~~

If the code does not retain the copy variable elsewhere, no mutator changes it later, and the elements are immutable Strings, the wrapper keeps the state stable.

The difference from:

~~~java
this.names = Collections.unmodifiableList(input);
~~~

is that the caller still holds `input` and can modify the backing list. Wrapping does not make the external source immutable.

When null does not need to be supported, `List.copyOf(input)` is usually more concise and conveys snapshot intent more clearly. When null elements are allowed, `List.copyOf` will throw an NPE; copying into an ArrayList and applying unmodifiable wrapping can be an intentional solution.

## 15. Deep Copying and Complex Object Graphs

If an immutable-looking class holds a `Map<String,List<MutableItem>>`, copying the outer Map + nested List still only copies references to MutableItem. When the caller keeps a MutableItem and modifies it, the state inside the snapshot can change.

You can capture an immutable DTO:

~~~java
record ItemView(String sku, long priceCents) {
}
~~~

and convert mutable items into `ItemView` objects:

~~~java
List<ItemView> safe = items.stream()
        .map(x -> new ItemView(x.sku(), x.priceCents()))
        .toList();
~~~

`Stream.toList()` (Java 16+) yields an unmodifiable List; the ItemView components are immutable String/long values. However, you need to check whether `sku()` and `priceCents()` could change concurrently between the two reads; if an atomic item snapshot is required, the owner must provide a snapshot method or synchronization.

### 15.1. Graphs with Cycles

A Parent ↔ Child graph with mutual references cannot be deep-copied by unconditional recursion; this easily leads to infinite recursion or loss of shared identity. You must design:

- Which objects actually belong to the value snapshot?
- Do back references need to be preserved?
- Is memoization via `IdentityHashMap<Original,Copy>` needed to handle cycles?
- Can a simpler immutable, acyclic DTO projection be created instead?

Do not use “deep copy everything” as a default rule, especially with resources or complex domain entities.

## 16. `clone()` Does Not Mean Deep Copy

`Object.clone()` with `Cloneable` normally performs a **shallow copy** at the level of the class object's fields when the clone mechanism is properly invoked. A `List<String>` field may still point to the same List after cloning. With mutable nested objects, the clone can unexpectedly share state.

A **copy constructor** or explicit factory expresses the scope more clearly:

~~~java
final class NoteSnapshot {
    private final String text;
    private final List<String> tags;

    NoteSnapshot(String text, List<String> tags) {
        this.text = text;
        this.tags = List.copyOf(tags);
    }
}
~~~

This is a fragment; in production code, null validation is needed according to the contract. With immutable String/List elements, structural copying is sufficient. With nested mutable elements, deeper handling is required.

There is no need for `new String(oldString)` merely as a defensive measure because String is immutable. Copying does not increase safety when the source is already immutable.

## 17. Immutable Objects, Hashing, and Collections

When a class is a value object used as a `HashMap` key or a `HashSet` member, `equals/hashCode` usually depend on internal fields.

~~~java
final class TagsKey {
    private final List<String> tags;

    TagsKey(List<String> input) {
        tags = List.copyOf(input);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof TagsKey key
                && tags.equals(key.tags);
    }

    @Override
    public int hashCode() {
        return tags.hashCode();
    }
}
~~~

Because the List structure is snapshotted and String elements are immutable, the caller modifying the original input List does not change TagsKey hash/equality. If the constructor only kept the mutable List reference, changing its contents could cause the hash to change while the object is already used as a key in a HashMap, leading to erratic lookups.

**Important:** defensive copying only protects the data. You still need to satisfy the contracts of `equals` (reflexive, symmetric, transitive, non-nullity, consistency) and `hashCode` (equal objects must have equal hash codes). Not every entity should override equality based on all mutable fields.

## 18. Concurrency: Defensive Copying Is Not Automatically a Transaction

Suppose thread A copies a mutable List while thread B adds/removes elements. The snapshot may be inconsistent, throw an exception, or exhibit API/synchronization-dependent behavior if the collection does not support concurrent modification.

Risks to distinguish:

1. **External mutation after snapshot:** proper defensive copying prevents internal state from changing.
2. **Concurrent mutation during copying:** requires a synchronized snapshot / immutable input / appropriate thread-safe contract.
3. **Shared mutable elements after shallow copy:** data races still exist if elements are shared.
4. **Publishing the object before the constructor completes:** can cause another thread to observe incomplete state (*this escape*).
5. **Atomic consistency across multiple inputs:** copying each input separately does not guarantee a same-instant snapshot.

### 18.1. A Final Field Does Not Make a Nested Object Thread-Safe

`private final List<Item> items` does not automatically turn a mutable Item into a thread-safe one. Java final-field semantics support safe initialization under appropriate conditions, but they do not prohibit mutating the referenced contents.

### 18.2. `Collections.synchronizedList` Does Not Mean Immutability

`Collections.synchronizedList` supports synchronization across operations according to its contract, yet the list remains mutable. `List.copyOf` creates an unmodifiable structural snapshot, yet mutable elements remain risky. Those are two different goals.

## 19. Performance: Copy in the Right Places, Avoid Pointless Copying

Defensive copying has memory/CPU costs depending on element count and depth. You should not skip copying based solely on performance guesswork, nor should you copy immutable objects on every read.

Balanced approach:

1. Use `Instant`, `LocalDate`, `String`, or immutable value records for new APIs.
2. Copy **once at the constructor/boundary** if sufficient.
3. Do not re-copy a `List.copyOf` snapshot containing immutable elements in every getter.
4. Deep-copy only nested mutable values that genuinely need protection.
5. If the output is a large byte array, consider streaming or an explicit ownership-transfer API instead of exposing a writable internal array.
6. If using persistent immutable data structures, structural sharing is possible, but you must understand the library's contract.
7. Benchmark with a real workload before choosing an alternative technique for performance.

**Copy-on-write** is a separate pattern: retain a published snapshot, and create a new state when modifications occur. It does not mean every getter must create a copy. `CopyOnWriteArrayList` has trade-offs suited to read-heavy/write-rare workloads, not a mandatory choice for every immutable class.

## 20. Less Obvious Sources of State Leaks

### 20.1. Returning a Stream/Iterator over a Mutable Backing Collection

`internal.stream()` and `internal.iterator()` do not automatically create an immutable snapshot. The caller can still see mutable elements or a collection being modified. Snapshot first if the API requires independence.

### 20.2. Callbacks Receiving Mutable Internal State

If a method calls `listener.accept(internalMutableObject)`, the listener can mutate the object if its API allows it. Pass an immutable DTO/snapshot or an appropriate non-mutating view.

### 20.3. Holding a Mutable Builder After build

A builder can be modified after `build()`. The built object must store a snapshot if it promises immutability; do not retain a raw builder reference to read state on every call.

### 20.4. Getters Returning a Read-Only ByteBuffer

A read-only view can share underlying storage with a writable alias. Preventing the caller from modifying through the view **does not prove the underlying bytes cannot change**. Snapshotting binary data requires copying bytes or owning exclusive storage according to the contract.

### 20.5. Deserialization and Frameworks

A framework may create/reconstitute objects via paths other than a public constructor, using proxies/hydration or keeping mutable references. If the immutability contract matters, inspect framework-specific initialization, validation, and defensive copying on every path that feeds data into the object. With legacy Java serialization, review deserialization hooks rather than assuming the public constructor always performs copying.

### 20.6. Subclassing Breaking Invariants

An immutable-looking class can be subclassed to add mutable observable state or override methods. `final class` generally helps keep the contract closed, yet **does not replace defensive copying** of nested objects.

## 21. Common Mistakes

1. Marking `private final Date` and concluding that Date cannot change.
2. Copying mutable input yet returning the field directly through a getter.
3. Copying output yet keeping the input alias in the constructor.
4. Using `Collections.unmodifiableList(source)` instead of a snapshot.
5. Believing `List.copyOf` deep-copies elements.
6. Using a record with `Date`/List components without copying.
7. Forgetting to override the record accessor when an internal component remains mutable.
8. Cloning only the outer array of `int[][]`.
9. Assuming `Object.clone()` creates a deep copy.
10. Validating mutable input first and copying afterward.
11. Copying the source multiple times and validating a different copy from the one stored.
12. Thinking copying multiple mutable inputs produces an atomic snapshot.
13. Returning a writable `ByteBuffer` or a read-only view sharing backing bytes and advertising it as a snapshot.
14. Returning a stream/iterator of a mutable internal collection.
15. Passing an internal mutable object to a callback/listener.
16. Treating an unmodifiable List as thread-safe for mutable elements.
17. Using `Map.copyOf` and then testing iteration order as if it were insertion order.
18. Using `List.copyOf` in a domain that allows null elements without a policy.
19. Thinking `final List<Item>` makes Item immutable.
20. Unnecessarily copying batches of immutable String/Instant objects.
21. Using generated equals/hashCode on a nested mutable reference, creating an unstable HashMap key.
22. Retaining a mutable builder reference inside the object after build.
23. Deep-copying a resource such as a socket/file/connection when an ownership/close policy is actually needed.
24. Using a read-only wrapper while letting the caller keep a writable backing alias.
25. Failing to specify clearly whether the API returns a snapshot or a live view.

## 22. Self-Check Exercises with Answers

**Question 1.** Is `private final Date when` enough to make an object immutable?

**Answer:** No. Final only prevents reassigning the reference; Date is still mutable.

**Question 2.** Why must both the constructor and the getter be defensive?

**Answer:** Copying in the constructor prevents an external input alias, while copying in the getter prevents the caller from modifying the internal mutable object through the output. Missing either one still leaves a mutation path.

**Question 3.** For a `String` input, is copying needed?

**Answer:** No. String is immutable, so sharing the reference is safe regarding mutation concerns.

**Question 4.** How should `Date` be copied in the example?

**Answer:** `new Date(input.getTime())` upon receipt; `new Date(field.getTime())` upon return, along with validation on the snapshot.

**Question 5.** Why copy before validation?

**Answer:** To validate the exact snapshot that will be stored; this prevents the caller from mutating the source between the check and the copy.

**Question 6.** Does `byte[] source.clone()` produce a separate array?

**Answer:** Yes, it creates a new byte array object containing copied primitive values.

**Question 7.** Does `int[][] outerCopy = source.clone()` isolate the inner arrays?

**Answer:** No. You must copy each row if a two-dimensional snapshot is needed.

**Question 8.** How does `List.copyOf` differ from `Collections.unmodifiableList(source)`?

**Answer:** List.copyOf provides an unmodifiable structural snapshot; unmodifiableList(source) is a view that can reflect mutations to the backing source.

**Question 9.** Does `List.copyOf(List<MutableItem>)` protect Item from external mutation?

**Answer:** No. The items are still referenced; immutable elements or a deep copy are needed when the contract requires it.

**Question 10.** If Catalog already stores `List.copyOf(input)` and the elements are Strings, does the getter need to create a new List?

**Answer:** No. Returning the immutable snapshot itself can be safe and economical.

**Question 11.** Can `Collections.unmodifiableList(new ArrayList<>(source))` serve as a structural snapshot?

**Answer:** Yes, if the backing copy is never exposed or mutated afterward. Mutable elements remain shared.

**Question 12.** Does `List.copyOf` allow null elements?

**Answer:** No, it will throw a NullPointerException.

**Question 13.** Does the record `record R(Date date)` automatically copy Date?

**Answer:** No. The constructor/accessor must be defensive or use an immutable type instead.

**Question 14.** How does a record compact constructor copy a List?

**Answer:** `tags = List.copyOf(tags)` in the body; the compiler assigns the reassigned parameter to the component field.

**Question 15.** Is `Map.copyOf(Map<String,List<String>>)` sufficiently deeply immutable?

**Answer:** Not if the nested Lists are mutable. The nested Lists must be copied when needed.

**Question 16.** Does a read-only `ByteBuffer` view always remain unchanged when the original buffer is modified?

**Answer:** No. A read-only view can share backing bytes.

**Question 17.** Should a mutable class defend input in a setter?

**Answer:** It may be necessary if you want to prevent callers from modifying an internal collection outside the API; this does not make the class immutable if the setter itself changes state.

**Question 18.** If another thread modifies input right while the constructor is copying, is the copy automatically atomic?

**Answer:** No. A synchronization/immutable snapshot protocol is needed when consistency across sources matters.

**Question 19.** Why does defensive copying matter for hashCode?

**Answer:** Mutable nested data can change the equality/hash of a value key after insertion into a HashMap/HashSet; immutable copying keeps the key stable.

**Question 20.** Is `Object.clone()` on a class with a mutable List field guaranteed to isolate the list?

**Answer:** No. A shallow clone can keep the same List reference.

**Question 21.** What advantage does `Instant` have over `Date` in an immutable DTO?

**Answer:** Instant is immutable, so it can be shared across inputs/outputs without Date-style copies.

**Question 22.** Can an immutable class be protected simply by omitting setters?

**Answer:** No. External aliases via constructors, getters, callbacks, or nested elements can still modify observable state.

**Question 23.** If you need to deep-copy a graph with reference cycles, can you always recursively copy unconditionally?

**Answer:** No. You may need memoization/identity-preserving graph copying or an immutable DTO projection.

**Question 24.** Is defensive copying always good regardless of memory/time costs?

**Answer:** No. Copy precisely the mutable boundaries that need protection; share immutable objects when safe, and measure performance if needed.

**Question 25.** What is the most important thing when reviewing a getter?

**Answer:** Determine whether the returned data is mutable or contains mutable nested objects, whether the caller can use it to change internal state, and whether the API promises a snapshot or a live view.

## 23. Checklist When Designing an Immutable Class

1. Does the class/instance have fixed observable state according to its contract?
2. Are there mutable inputs from constructors, builders, or factories?
3. Have mutable inputs that must remain independent been copied?
4. Is **validation performed on the exact snapshot** being stored?
5. Is the mutable input re-read after validation?
6. Does any getter/accessor return a mutable internal field?
7. If a getter returns an unmodifiable collection, does the backing data still have a mutable alias?
8. Are nested mutable elements copied or replaced with immutable values?
9. Does `List.copyOf` fit the domain's null contract?
10. Is iteration order being incorrectly assumed for `Map.copyOf`?
11. Are there multidimensional arrays or arrays containing mutable elements?
12. Does a record have mutable components without a defensive compact constructor/accessor?
13. Can `Date` be replaced with `Instant` or `StringBuilder` with String?
14. Does any stream/iterator/callback expose a mutable object?
15. Does the builder continue holding a reference to the object after build?
16. Are `final` fields being mistaken for deep immutability?
17. Are there keys whose `equals/hashCode` depend on nested mutable state?
18. Does copying occur concurrently with external writers?
19. Does cross-field validation require an atomic snapshot?
20. Is `this` published prematurely before the constructor completes?
21. Are there resources that should not be copied and instead require separate ownership/lifecycle?
22. Is copying once at the boundary sufficient instead of copying in every getter?
23. Is there a test modifying **the input after construction** and verifying state does not change?
24. Is there a test modifying **the output from a getter** and verifying state does not change?
25. Are there tests for nested mutable elements and null/invalid inputs?

## Conclusion

**Defensive copying** is not merely adding `clone()` or `List.copyOf()` everywhere. It is deciding **who owns mutable data and who is permitted to change which state**. For an immutable class, constructors should not retain mutable references that the caller can modify; getters should not hand out mutable internal references. Containers such as List/Map/array require examining both the outer structure and the mutable elements inside.

Doing it right consists of: **copying input before validating; storing an appropriate snapshot; returning a copy if internals remain mutable, or safely returning an immutable snapshot; understanding shallow/deep copying; avoiding leaks through callbacks/streams/builders; and adding synchronization if an atomic snapshot is required while other threads perform updates**.

Whenever possible, prefer **immutable value types** such as String, Instant, or a record with truly immutable components. When mutable inputs are necessary, defensive copying protects invariants at the boundary. Thus, immutability becomes a **testable behavioral guarantee**, rather than just the `private` and `final` keywords.
