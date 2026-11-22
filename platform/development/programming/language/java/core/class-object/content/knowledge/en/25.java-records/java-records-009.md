# Records Only Guarantee Shallow Immutability — Correctly Understanding `final`, Aliasing, and Defensive Copying in Java 17+

A Java `record` is a special kind of class used to represent a fixed group of **record components**. When you write `record User(String name, List<String> roles) {}`, Java generates the private final component fields and corresponding accessors such as `name()`, `roles()`. You cannot reassign a component field of an already-constructed record, yet **the object that a component reference points to can still change**.

That is the important meaning behind the statement **“records only guarantee shallow immutability”**: the structure of the **component references** is fixed after construction, whereas Java **does not automatically freeze the entire object graph** behind those references.

~~~java
record Group(java.util.List<String> members) {
}
~~~

This is a valid record declaration. A caller can create an `ArrayList`, pass it into Group, and then modify the ArrayList. The default `members()` accessor also returns a reference to the stored list, so someone else can call `add` on that list.

Conversely, `record Point(int x, int y) {}` contains only two primitives, so there is no mutable object beneath the component references. Point is a simpler **stable value** case than Group. Thus, the observed level of immutability depends on **the component types, constructor, accessors, and shared objects**, not just the `record` keyword.

This lesson belongs to **Java core – class-object**, **Record** group, topic **Records only guarantee shallow immutability**. All standalone programs are written for **Java 17+**, with file names, `javac`/`java` commands, and specifically analyzed stdout. Snippets without `main` and intentionally invalid code are distinguished separately.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the difference between a **final field reference** and an **immutable object**.
2. Identify where **aliasing** can occur before and after creating a record.
3. Know that the default accessor returns the component value; for a reference component, that is a **reference** to the object.
4. Distinguish between **modifiable collection**, **unmodifiable view**, **unmodifiable snapshot**, and **deep immutability**.
5. Use a **compact canonical constructor** or an explicit canonical constructor to defensively copy input data.
6. Know when to override an accessor, especially with arrays.
7. Understand that `List.copyOf`, `Set.copyOf`, and `Map.copyOf` do not automatically deep-copy elements and values.
8. Analyze mutable elements in a list that is already unmodifiable.
9. Predict the impact of mutable state on `equals`, `hashCode`, and `toString` of a record.
10. Design a value-record with nested collections or mutable Java legacy types.
11. Distinguish **immutability** from **thread safety** and data consistency.
12. Establish a clear ownership/copying policy at API boundaries.

## 2. What Does a Record Actually Generate?

Declaration:

~~~java
record OrderLine(String sku, int quantity) {
}
~~~

Java generates the following main components, according to record semantics:

- A class named `OrderLine`, implicitly `final`, extending `java.lang.Record`.
- Corresponding private final fields `sku` and `quantity`.
- Public component accessors `sku()` and `quantity()` if you do not define them.
- Canonical constructor with the parameters `String sku, int quantity`.
- `equals(Object)`, `hashCode()`, and `toString()` based on the components, if not overridden.

**Records do not generate setters by default.** There is no `line.setSku("X")` API unless you define a method with that name yourself, yet you still cannot use that method to reassign the final component field.

A record class is also restricted from declaring **additional instance fields**. You can add appropriate methods, static members, and nested types, but you cannot turn a record into a JavaBean with multiple arbitrary instance variables.

What Java guarantees is that **the field is not reassigned after construction**, not “everything accessed through the field is also immutable”.

## 3. Distinguishing Three Layers of State

Let us separate the following three layers:

| Layer | Example | What is locked? |
| --- | --- | --- |
| Component field in the record | `private final List<String> roles` | The reference stored in the field cannot be reassigned after being initialized |
| Object pointed to by the reference | `ArrayList<String>` | **Not** automatically locked; `add`, `remove`, and `set` can still modify it |
| Elements of the collection | `MutableUser`, `StringBuilder` | **Not** automatically locked; an element object can continue to be mutated |

Diagram:

~~~text
Record instance User
    |
    +-- final name ----------> String "An" (immutable)
    |
    +-- final roles ---------> ArrayList object (mutable)
                                  |
                                  +-- element 0 --> String "reader"
                                  +-- element 1 --> String "editor"

Record locks the roles reference, not operations on the ArrayList.
~~~

If accessors return references directly, external code can also **reach the target object** held by the record. If the caller already kept that reference before creating the record, changes also propagate back into the record.

This is **shallow immutability**, not deep immutability.

## 4. Program 1 — Two Paths to Mutate a Record Component

Create the file **`MutableRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

record Group(List<String> members) {
}

public class MutableRecordDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Group group = new Group(source);
        System.out.println("initial=" + group.members());

        source.add("Binh");
        System.out.println("after source=" + group.members());

        group.members().add("Chi");
        System.out.println("after accessor=" + source);
        System.out.println("record=" + group);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 MutableRecordDemo.java
java MutableRecordDemo
~~~

**Exact stdout:**

~~~text
initial=[An]
after source=[An, Binh]
after accessor=[An, Binh, Chi]
record=Group[members=[An, Binh, Chi]]
~~~

The line `source.add("Binh")` shows that **the input is shared**. The line `group.members().add("Chi")` shows that **the default accessor exposes the mutable reference**. These are two modification paths from both sides of the API boundary.

There is no assignment `group.members = otherList`, yet the contents of the list referenced by the final field still change.

## 5. `final` Protects Assignment, Not Mutation

In a record:

~~~java
record Basket(java.util.List<String> items) {
    void add(String item) {
        items.add(item);
    }
}
~~~

This is **valid** Java code. `Basket.add` can mutate the current List, even though `items` is a final field. However, this is a design that easily misleads readers into thinking the record is like an immutable value object when in fact it still has mutable behavior.

A direct assignment `this.items = anotherList` after construction is invalid; however, `this.items.add(...)` is a method call on the target object, not a field assignment.

For a primitive `int quantity`, there is no object content to mutate. You also cannot do `quantity++` inside a record instance method because the component field is final. With `String`, String itself is immutable; a reference to a String is therefore also stable in character content. But with `List`, `Date`, array, or a custom mutable DTO, a separate policy is needed.

## 6. Aliasing: The Root Cause of Shallow Immutability

**Aliasing** is when two or more references point to **the same object**.

~~~text
caller.source -----+
                   |
                   v
             ArrayList object
                   ^
                   |
record.items ------+

Calling source.add("X") or record.items().add("Y")
both modify the same ArrayList.
~~~

In a default record constructor, the component reference is received and stored without copying. Therefore, the caller and the record are often two parties holding aliases to the same object.

Both of the following points need to be considered:

- **Input aliasing:** the caller still holds `source` and modifies it after passing it into the record.
- **Output aliasing:** the caller calls the accessor, receives the component reference, and then modifies that object.

A record that achieves **shallow immutability** on its fields can still have its observable state changed through both of these paths. If the record is used as configuration, transaction data, or a key of a map, the risk becomes significant.

## 7. Defensive Approach with List: Copying in the Canonical Constructor

If the component is `List<String>`, a common approach is:

~~~java
import java.util.List;
import java.util.Objects;

record Team(String name, List<String> members) {
    Team {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }
}
~~~

This is a **complete record**, without `main` yet. `Team { ... }` is a **compact canonical constructor**.

- The parameter variable `members` is replaced with `List.copyOf(...)`, creating a snapshot that **does not support structural modification**.
- After the compact constructor block completes, the compiler assigns the `members` component field from **the replaced parameter**.
- The list object passed in by the caller can continue to change without causing the snapshotted list to receive those additions/removals.
- The default accessor `members()` can return the component reference directly, because the stored list is structurally unmodifiable.

`List.copyOf` does not allow a null list and null elements. If the domain allows null elements, a different copying strategy is needed.

**Note:** “copy” here is a **shallow copy of elements/references**, not copying every child object.

## 8. Program 2 — Copying on Input, Accessor Disallows Modification

File **`DefensiveListRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Team(String name, List<String> members) {
    Team {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }
}

public class DefensiveListRecordDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Team team = new Team("Core", source);

        source.add("Binh");
        System.out.println("source=" + source);
        System.out.println("team=" + team.members());

        try {
            team.members().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot add="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("still=" + team.members());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 DefensiveListRecordDemo.java
java DefensiveListRecordDemo
~~~

**Stdout:**

~~~text
source=[An, Binh]
team=[An]
cannot add=UnsupportedOperationException
still=[An]
~~~

It is the **compact constructor** that protects the input. If you only put the `final` modifier on the caller's local variable `source`, it still does not lock the list.

With `List<String>`, the elements are immutable strings, so a structural snapshot is usually sufficient for a record with stable observable state.

## 9. `Collections.unmodifiableList` Does Not Automatically Create a Snapshot

It is necessary to distinguish two approaches:

~~~java
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);
~~~

These are in-method snippets and require imports. Both `view` and `snapshot` **disallow direct structural modification** through the List interface. However:

- `Collections.unmodifiableList(source)` creates an **unmodifiable view** of source itself. If source is modified through another reference, the view reflects the changes.
- `List.copyOf(source)` provides an **unmodifiable list reflecting the contents at the time of the call**, not a live view of the mutable source.
- `List.copyOf` can **reuse a suitable unmodifiable list** instead of allocating a new object; the API does not promise to always create a separate object.
- Both only control modification of the **collection structure**, and do not automatically deep-copy elements.

If a record constructor uses `Collections.unmodifiableList(input)` directly, while the caller still holds a reference to `input`, the record still suffers from **input aliasing**.

To get an unmodifiable view **and** decouple from the mutable source when null elements are present, you can use `Collections.unmodifiableList(new ArrayList<>(input))`. This is a structural snapshot inside a wrapped private mutable copy, provided you do not expose that copy elsewhere.

## 10. Program 3 — Views and Snapshots Differ

File **`ViewVsSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

record ViewBox(List<String> values) {
    ViewBox {
        values = Collections.unmodifiableList(values);
    }
}

record SnapshotBox(List<String> values) {
    SnapshotBox {
        values = List.copyOf(values);
    }
}

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        ViewBox live = new ViewBox(source);
        SnapshotBox frozen = new SnapshotBox(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + live.values());
        System.out.println("snapshot=" + frozen.values());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
~~~

**Stdout:**

~~~text
source=[A, B]
view=[A, B]
snapshot=[A]
~~~

Unmodifiable **does not necessarily** mean an independent snapshot. This is a common mistake when implementing defensive copying for record components.

If real code intentionally needs a live view, clearly document in the API that the record does not have completely stable state; do not give it a misleading `Immutable...` name.

## 11. A Snapshotted List Can Still Contain Mutable Elements

Suppose:

~~~java
final class MutableMember {
    private String name;

    MutableMember(String name) {
        this.name = name;
    }

    void rename(String next) {
        name = next;
    }

    String name() {
        return name;
    }
}
~~~

Even if the record holds `List.copyOf(members)`, it still holds **references to the original MutableMember objects**. A caller can retain a member reference and call `rename`.

Diagram:

~~~text
source List --------> MutableMember("An")
                          ^
                          |
snapshot List ------------+

The snapshot breaks sharing of the List structure,
but does NOT automatically create a new MutableMember.
~~~

Therefore, `List.copyOf` can prevent `record.members().add(...)`, but cannot prevent `record.members().get(0).rename(...)` if the element exposes a mutating method.

To achieve deep immutability within that structural scope, you should use immutable elements (for example, a record containing only immutable values) or create **defensive element copies** and avoid exposing mutable children.

## 12. Program 4 — Elements of an Unmodifiable List Still Change

File **`MutableElementRecordDemo.java`**:

~~~java
import java.util.List;

final class MutableMember {
    private String name;

    MutableMember(String name) {
        this.name = name;
    }

    void rename(String newName) {
        name = newName;
    }

    @Override
    public String toString() {
        return name;
    }
}

record Squad(List<MutableMember> members) {
    Squad {
        members = List.copyOf(members);
    }
}

public class MutableElementRecordDemo {
    public static void main(String[] args) {
        MutableMember first = new MutableMember("An");
        Squad squad = new Squad(List.of(first));

        System.out.println("before=" + squad.members());

        first.rename("Binh");
        System.out.println("after external="
                + squad.members());

        squad.members().get(0).rename("Chi");
        System.out.println("after accessor="
                + squad.members());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MutableElementRecordDemo.java
java MutableElementRecordDemo
~~~

**Stdout:**

~~~text
before=[An]
after external=[Binh]
after accessor=[Chi]
~~~

In this demo, the list disallows structural modification, yet the MutableMember element still changes state. Because the accessor returns a List containing a reference to that MutableMember, the caller even has a direct access path to modify the element.

The condition “unmodifiable list” is **not sufficient** to conclude that a record containing that list is deep immutable.

## 13. Designing Immutable Elements and Converting at Boundaries

A safer approach is to **use an immutable value type** for the element, for example:

~~~java
record MemberName(String value) {
    MemberName {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("bad name");
        }
    }
}

record SquadSnapshot(List<MemberName> members) {
    SquadSnapshot {
        members = List.copyOf(members);
    }
}
~~~

The two records above have component types String and List<MemberName>. String is not mutable; MemberName also has no mutable children. The List is unmodifiable-snapshotted, so within this graph the state is stable.

When the original source is a DTO with setters, **convert each DTO into a new value record**:

~~~java
// Idea inside a method with source of type List<MutableMember>:
List<MemberName> stable = source.stream()
        .map(item -> new MemberName(item.name()))
        .toList();
SquadSnapshot snapshot = new SquadSnapshot(stable);
~~~

This is an in-method snippet with the types as declared. `Stream.toList()` returns an unmodifiable list, but most importantly, `new MemberName(item.name())` **creates a value element**, rather than retaining the old mutable DTO.

**Note:** if source is modified concurrently while copying, synchronization/snapshotting at the source boundary is needed to obtain consistent data. Defensive copying does not by itself resolve data races during the copying process.

## 14. Program 5 — Replacing Mutable Elements with Immutable Values

File **`DeepValueSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class MutablePerson {
    private String name;

    MutablePerson(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String name) {
        this.name = name;
    }
}

record PersonName(String value) {
    PersonName {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("bad name");
        }
    }
}

record GroupSnapshot(List<PersonName> members) {
    GroupSnapshot {
        members = List.copyOf(members);
    }

    static GroupSnapshot from(List<MutablePerson> source) {
        List<PersonName> values = new ArrayList<>();
        for (MutablePerson person : source) {
            values.add(new PersonName(person.name()));
        }
        return new GroupSnapshot(values);
    }
}

public class DeepValueSnapshotDemo {
    public static void main(String[] args) {
        MutablePerson person = new MutablePerson("An");
        List<MutablePerson> source = new ArrayList<>();
        source.add(person);

        GroupSnapshot group = GroupSnapshot.from(source);

        person.rename("Binh");
        source.add(new MutablePerson("Chi"));

        System.out.println("group=" + group.members());
        System.out.println("source size=" + source.size());
        System.out.println("first source name="
                + source.get(0).name());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 DeepValueSnapshotDemo.java
java DeepValueSnapshotDemo
~~~

**Stdout:**

~~~text
group=[PersonName[value=An]]
source size=2
first source name=Binh
~~~

GroupSnapshot does not share source's MutablePerson instances: it only holds immutable PersonName values. Modifying person or adding a new entry to source does not affect the snapshot.

This is a **deep snapshot within the scope of the chosen object graph**; it is not a general-purpose deep-copy algorithm for every class in Java. The copying policy must know the domain and which mutable layers actually exist.

## 15. Arrays Are the Most Easily Overlooked Case

Arrays in Java are mutable. With:

~~~java
record Packet(byte[] bytes) {
}
~~~

the implicit constructor stores the passed-in array reference; the `bytes()` accessor returns that very reference.

Two mutation paths:

~~~java
byte[] source = {1, 2};
Packet packet = new Packet(source);

source[0] = 9;
packet.bytes()[1] = 8;
~~~

This is a valid in-method snippet. The array inside the record now contains `[9,8]`, even though the component field `bytes` is final.

**Common mistake:** only cloning the input with `bytes = bytes.clone();` in the compact constructor while still using the default accessor. In that case, the caller can no longer modify it via **the original source**, yet can still modify it via **`packet.bytes()`**.

For an array that should not be mutated from outside, copying is needed at **both input and output boundaries**.

## 16. Program 6 — Arrays Are Not Protected by a Default Record

File **`ShallowArrayRecordDemo.java`**:

~~~java
import java.util.Arrays;

record Packet(int[] values) {
}

public class ShallowArrayRecordDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        Packet packet = new Packet(source);

        System.out.println("initial="
                + Arrays.toString(packet.values()));

        source[0] = 9;
        System.out.println("after source="
                + Arrays.toString(packet.values()));

        packet.values()[1] = 8;
        System.out.println("after accessor="
                + Arrays.toString(source));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ShallowArrayRecordDemo.java
java ShallowArrayRecordDemo
~~~

**Stdout:**

~~~text
initial=[1, 2]
after source=[9, 2]
after accessor=[9, 8]
~~~

An array is a standalone object with mutation operations via index. `final` ensures the record does not change its reference to another array, but does not forbid `packet.values()[0] = ...`.

## 17. Copying Input and Output for an Array Component

For a record `SafePacket(byte[] data)`, the defensive strategy is typically:

~~~java
import java.util.Objects;

record SafePacket(byte[] data) {
    SafePacket {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

This is a valid record. The compact canonical constructor changes **the parameter `data`** to the clone; the compiler assigns the component field from the clone after the body. The overridden accessor returns a new clone, preventing the caller from holding a reference to the internal array.

Without overriding the accessor, there is only **input protection**, not **output protection**.

Two design points should be noted:

1. `clone()` on a primitive array such as `byte[]` copies the primitive elements completely. On `MutableItem[]`, clone **only copies the array container**, while element references still point to the original MutableItem instances.
2. Record-generated `equals`/`hashCode` for array components **do not compare element contents using `Arrays.equals`**. If you want byte arrays to have value semantics, you need to override `equals`/`hashCode` consistently.

## 18. Program 7 — Two-Way Cloning and Array-Content Equality

File **`SafeBytePacketDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

record SafeBytePacket(byte[] data) {
    SafeBytePacket {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof SafeBytePacket that
                    && Arrays.equals(data, that.data));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(data);
    }
}

public class SafeBytePacketDemo {
    public static void main(String[] args) {
        byte[] source = {1, 2};
        SafeBytePacket first = new SafeBytePacket(source);
        SafeBytePacket second =
                new SafeBytePacket(new byte[] {1, 2});

        source[0] = 9;
        byte[] external = first.data();
        external[1] = 8;

        System.out.println("source="
                + Arrays.toString(source));
        System.out.println("external="
                + Arrays.toString(external));
        System.out.println("record="
                + Arrays.toString(first.data()));
        System.out.println("same content="
                + first.equals(second));
        System.out.println("same hash="
                + (first.hashCode() == second.hashCode()));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SafeBytePacketDemo.java
java SafeBytePacketDemo
~~~

**Stdout:**

~~~text
source=[9, 2]
external=[1, 8]
record=[1, 2]
same content=true
same hash=true
~~~

We proactively override `equals`/`hashCode` to compare byte contents, while also protecting the internal array. We do not print `first.toString()` in the demo because the default toString of an array component can reflect array identity rather than bytes in a stable format. If stable/clean output is required, `toString` can be intentionally overridden.

**You cannot infer** that a record generates equality by array contents just because the array is inside a record.

## 19. Record-Generated `equals`, `hashCode`, `toString` Depend on Components

Records are often chosen as **value carriers** because the compiler-generated methods are based on the record components:

~~~java
record Label(java.util.List<String> tags) {
}
~~~

If `tags` is a mutable ArrayList:

- `Label.equals` is based on the List component value; `List.equals` compares elements in order.
- `Label.hashCode` depends on the List's hashCode, and the hashCode of a mutable List can change when elements change.
- `Label.toString` displays component information; the displayed list portion can change after mutation.
- Two records sharing the same list reference can both observe a single mutation, even though the record fields remain final.

This is very dangerous when the record is used as a **key in a HashMap** or an element of a **HashSet**. Such collections rely on the key's hash/equality remaining relatively stable while the key is stored.

For a record containing only immutable value components, those behaviors are naturally more stable. With mutable references, the constructor needs to ensure state conforms to the desired value contract.

## 20. Program 8 — Equality and Hash Change Even Though the Field Is Final

File **`MutableRecordEqualityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

record TagKey(List<String> tags) {
}

public class MutableRecordEqualityDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        TagKey key = new TagKey(source);
        TagKey original = new TagKey(List.of("A"));

        int hashBefore = key.hashCode();

        System.out.println("before equal="
                + key.equals(original));

        source.set(0, "B");

        System.out.println("after equal="
                + key.equals(original));
        System.out.println("current=" + key.tags());
        System.out.println("hash changed="
                + (hashBefore != key.hashCode()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 MutableRecordEqualityDemo.java
java MutableRecordEqualityDemo
~~~

**Stdout:**

~~~text
before equal=true
after equal=false
current=[B]
hash changed=true
~~~

In the demo, `List.of("A")` and the `ArrayList` containing A initially compare equal according to List equality. After the ArrayList is modified from A to B, the record-generated equality changes.

The List's hash depends in part on element hashes; String `"A"` and `"B"` have different hashes, so the line `hash changed=true` has a deterministic result for this example. There is no need to print specific hash numbers or assume object allocation layout.

**Consequence:** if this mutable key is used as a HashMap key, modifying it after storing can cause lookups not to behave as expected. The preventive measure is to put **stable immutable value components** into keys.

## 21. `List.copyOf` Helps Stabilize Equality When Elements Are Also Immutable

With:

~~~java
record TagKey(java.util.List<String> tags) {
    TagKey {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

the List component is now an unmodifiable snapshot of the input, and the elements are immutable Strings, so hash/equality is stable under normal operations on that object graph.

If `String` is replaced with `MutablePart` whose `equals`/`hashCode` is based on a mutable field, `List.copyOf` **does not solve** the risk: hash and equality can still change because the component elements mutate.

**Principle:** for a record to work as a **stable hash key**, all data that `equals` and `hashCode` depend on must have stable observable state while the key is stored.

Do not try to patch this by caching hashCode from creation time in the record (records also do not allow adding arbitrary ordinary instance fields): a cached hash cannot fix equality that has been broken by mutation.

## 22. Multiple Collection Layers: Copy Each Mutable Layer That Needs Protection

A common component type is:

~~~java
record Permissions(
        java.util.Map<String, java.util.List<String>> roles) {
}
~~~

If you only write `roles = Map.copyOf(roles)`, you create a **map that disallows structural modification**, but the List values can still be mutable.

Example:

~~~text
Mutable Map source
    "admin" ----> Mutable List ["READ"]
                     ^
                     |
Map.copyOf(source) keeps the same List reference for key "admin"

source.get("admin").add("WRITE") causes the record to see WRITE.
~~~

To obtain a stable snapshot when map keys and list elements are immutable Strings, you need to copy **each list value** and then copy **the map container**. This is layer-by-layer defense.

The factory methods `Map.copyOf` and `List.copyOf` reject null keys/values/elements by contract. Validate inputs before building the snapshot if you need explicit exception messages.

## 23. Program 9 — Snapshotting a Map of Lists

File **`NestedCollectionSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

record Permissions(Map<String, List<String>> roles) {
    Permissions {
        Objects.requireNonNull(roles, "roles");
        Map<String, List<String>> copy = new HashMap<>();
        for (Map.Entry<String, List<String>> entry
                : roles.entrySet()) {
            copy.put(
                    Objects.requireNonNull(
                            entry.getKey(), "role"),
                    List.copyOf(
                            Objects.requireNonNull(
                                    entry.getValue(), "permissions")));
        }
        roles = Map.copyOf(copy);
    }
}

public class NestedCollectionSnapshotDemo {
    public static void main(String[] args) {
        List<String> admin = new ArrayList<>();
        admin.add("READ");

        Map<String, List<String>> source = new HashMap<>();
        source.put("admin", admin);

        Permissions permissions = new Permissions(source);

        admin.add("WRITE");
        source.put("guest", List.of("READ"));

        System.out.println("source admin="
                + source.get("admin"));
        System.out.println("record admin="
                + permissions.roles().get("admin"));
        System.out.println("record keys="
                + permissions.roles().size());

        try {
            permissions.roles().get("admin").add("DELETE");
        } catch (UnsupportedOperationException ex) {
            System.out.println("list protected=true");
        }

        try {
            permissions.roles().put("guest", List.of("READ"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("map protected=true");
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NestedCollectionSnapshotDemo.java
java NestedCollectionSnapshotDemo
~~~

**Exact stdout:**

~~~text
source admin=[READ, WRITE]
record admin=[READ]
record keys=1
list protected=true
map protected=true
~~~

The program uses `get` and `size` instead of printing the entire HashMap, so the result does not depend on the iteration order of HashMap or Map.copyOf. The snapshot decouples both the Map container and the List containers from the source, while the String elements are immutable.

If the values are `List<MutableUser>`, you still need to copy/convert each MutableUser into an immutable representation before claiming deep immutability.

## 24. `Map.copyOf`, `Set.copyOf`, and Data Rules

Corresponding approaches for collection types:

- `List.copyOf(source)`: unmodifiable snapshot of the list structure, preserving element order and rejecting null elements.
- `Set.copyOf(source)`: unmodifiable set, rejecting null; duplicate elements in the input collection are merged according to Set semantics, with no guarantee about which duplicate instance is kept if they are equal but differ in identity.
- `Map.copyOf(source)`: unmodifiable map, rejecting null keys/values; does not promise iteration order like a LinkedHashMap.
- `Collections.unmodifiableList(source)`: live view of source, not a snapshot; retains an alias if source is mutable.
- `new ArrayList<>(source)`: mutable container copy; sufficient to decouple structure from source, but the accessor can allow modifying the internal copy if returned directly.
- `Collections.unmodifiableList(new ArrayList<>(source))`: unmodifiable view of a new copy that can serve as a structural snapshot even when source contains null elements; still shallow with respect to mutable elements.

**Do not confuse**:
- Unmodifiable: structure cannot be modified through that collection API.
- Immutable snapshot: the observable structure/value graph does not change through aliases held externally.
- Deep immutable: all reachable mutable state within the chosen scope cannot be modified via external access paths.

An immutable collection can contain a mutable object; therefore, the term “immutable” must always clarify **which layer**.

## 25. Common Record Components and Copying Choices

| Component type | Main risk | Reasonable strategy |
| --- | --- | --- |
| `int`, `long`, `boolean` | No underlying mutable object | Domain validation |
| `String` | String is immutable | Null/format validation |
| `BigDecimal` | Immutable class | Check scale/rounding per domain |
| `LocalDate`, `Instant` | Immutable Java time values | Validation |
| `List<String>` | Mutable container | `List.copyOf` |
| `List<MutableThing>` | Mutable elements | Convert/copy each element and the collection |
| `Set<String>` | Mutable container | `Set.copyOf` |
| `Map<String,String>` | Mutable container | `Map.copyOf` |
| `Map<String,List<String>>` | Mutable map and nested lists | Copy each list, then copy the map |
| `byte[]`, `int[]` | Mutable array on both sides | Clone input and accessor; check equality |
| `Date` (legacy) | Mutable object | Copy on input and output |
| `AtomicInteger` | Mutable holder thread-safe for certain operations | Do not call this an immutable value just because the field is final |
| Custom DTO with setters | Aliases and state mutation | Immutable DTO/record snapshot with explicit mapping |

For Java time types, you can prefer `java.time` over legacy `java.util.Date` when the API allows it; however, do not convert time data automatically without a clear timezone policy.

## 26. Legacy `Date`: Copying in the Constructor Alone Is Not Enough

`java.util.Date` is a mutable class: `setTime(long)` can change the timestamp that the Date object represents.

If a record is defined as:

~~~java
record Appointment(java.util.Date when) {
}
~~~

then the caller can modify `when` through the passed-in reference or obtain the reference via the accessor. This is similar to an array/list, differing only in Date's mutating methods.

A defensive form:

~~~java
record Appointment(java.util.Date when) {
    Appointment {
        when = new java.util.Date(
                java.util.Objects.requireNonNull(
                        when, "when").getTime());
    }

    @Override
    public java.util.Date when() {
        return new java.util.Date(when.getTime());
    }
}
~~~

This record creates its own Date copy on input and returns a new Date on read. The component field is still `Date`, yet there is no mutable alias from the caller's side to the internal Date through those two normal paths.

For many problems, storing an immutable `Instant` will be simpler and less error-prone.

## 27. Program 10 — Defending `Date` on Both Sides

File **`LegacyDateRecordDemo.java`**:

~~~java
import java.util.Date;
import java.util.Objects;

record Appointment(Date when) {
    Appointment {
        when = new Date(
                Objects.requireNonNull(when, "when").getTime());
    }

    @Override
    public Date when() {
        return new Date(when.getTime());
    }
}

public class LegacyDateRecordDemo {
    public static void main(String[] args) {
        Date source = new Date(1_000L);
        Appointment appointment = new Appointment(source);

        source.setTime(2_000L);
        Date external = appointment.when();
        external.setTime(3_000L);

        System.out.println("source=" + source.getTime());
        System.out.println("external=" + external.getTime());
        System.out.println("record="
                + appointment.when().getTime());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LegacyDateRecordDemo.java
java LegacyDateRecordDemo
~~~

**Stdout:**

~~~text
source=2000
external=3000
record=1000
~~~

Use `Date.getTime()` (a fixed number of milliseconds) instead of printing `Date.toString()` so that the output **does not depend on the machine's timezone**.

The constructor and accessor create new Date instances from the timestamp, isolating the record from direct external aliases. However, a record with a Date component itself is still not an absolute deep-immutable pattern if the design adds another access path to the internal Date; using immutable `Instant` is more suitable when possible.

## 28. The Best Record Form Is Sometimes Changing the Component Type

Instead of:

~~~java
record Appointment(java.util.Date when) {
}
~~~

you can use:

~~~java
record Appointment(java.time.Instant when) {
    Appointment {
        java.util.Objects.requireNonNull(when, "when");
    }
}
~~~

When converting from Date to Instant:

~~~java
// In a method with a non-null Date source:
Appointment appointment =
        new Appointment(source.toInstant());
~~~

`Instant` is an immutable value type; mutating the caller's Date afterward does not alter the Instant stored by the record.

This approach is simpler than maintaining Date constructor/accessor clones. However, **it cannot always be substituted** if the API must return a legacy Date, or if the domain represents a local calendar date rather than an instant on the timeline. Choose `Instant`, `LocalDate`, `LocalDateTime`, or `ZonedDateTime` according to the exact time semantics.

**Prefer an immutable representation from the start** rather than adding complex defensive copying at every entry and exit point.

## 29. Records Are Not Automatically Thread-Safe

A major misconception: “a record has final fields, so every operation on it is thread-safe”.

For example:

~~~java
record SharedCounter(
        java.util.concurrent.atomic.AtomicInteger value) {
}
~~~

The component field `value` is not reassigned. However, `AtomicInteger` still holds **mutable state**. This state is managed by an atomic utility, so certain operations like `incrementAndGet` have their own thread safety.

Conversely, if a record holds an `ArrayList` and multiple threads call `add` concurrently, the List field being final **does not turn the ArrayList into a concurrent collection**. Readers still need to distinguish visibility, atomicity, safe publication, and synchronization under the Java Memory Model.

A record with an immutable object graph that is properly published is generally easier to share across threads; however, **immutability of component references** is not sufficient to guarantee safety for every reachable object.

## 30. Program 11 — A Final Reference to a Counter Still Mutates

File **`MutableCounterRecordDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

record Metrics(AtomicInteger count) {
}

public class MutableCounterRecordDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Metrics metrics = new Metrics(new AtomicInteger(0));

        Thread a = new Thread(
                () -> metrics.count().incrementAndGet());
        Thread b = new Thread(
                () -> metrics.count().incrementAndGet());

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("count="
                + metrics.count().get());

        metrics.count().incrementAndGet();
        System.out.println("after main="
                + metrics.count().get());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MutableCounterRecordDemo.java
java MutableCounterRecordDemo
~~~

**Stdout after the threads complete normally:**

~~~text
count=2
after main=3
~~~

`Metrics.count` is a private final field, yet `AtomicInteger` can change from 0 to 2 and then 3. The final values are predictable in this example because `incrementAndGet` is atomic and main calls `join` before reading.

**The thread safety of the increment** comes from `AtomicInteger`, not from the record. If only immutable configuration is needed, you should not put a mutable counter as a component and call that record an immutable config.

## 31. Records as Keys in `HashMap`/Elements in `HashSet`

When using a record as a key, ask:

- Which components participate in `equals` and `hashCode`?
- Can those components mutate after the key is stored?
- Is copying the container sufficient, or can mutable elements still change the hash?
- Does the accessor expose a mutable object?
- Is there a possibility that two threads are mutating data while the key is still being looked up?

A good pattern for tag names:

~~~java
record StableTagKey(java.util.List<String> tags) {
    StableTagKey {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

When components use stable String values and a list snapshot, the key has clear value semantics. For byte arrays, if the contents should form the key's identity, two-way cloning and custom `equals`/`hashCode` are required.

Do not modify a mutable object referenced by a record key after adding it to a hash-based collection. If updating the key's contents is mandatory, **create a new key**, remove the old key using the proper API, and insert the new key.

## 32. Shallow Immutability Does Not Equal a Serialization Snapshot

A record can be serialized if it satisfies the Serializable contract and its components/object graph support it. However, **serialization does not replace defensive copying** for ordinary APIs.

If a record holds a mutable List, sending data through serialization may observe state at a point in time depending on graph traversal and concurrency. Do not expect serialization to “freeze” a record that is being mutated elsewhere.

In addition, a component pointing to a non-serializable object can cause serialization to fail, even if the record type implements Serializable. You must inspect the actual **object graph**.

When a durable message/DTO is needed across service boundaries, create an **immutable value snapshot** whose fields/components have a clear schema before encoding or sending, rather than relying solely on the `record` modifier.

## 33. `toString()` Can Change When a Component Is Mutable

Generated `toString()` is used to describe component values. If a component is a mutable List, the list description in the output can change after mutation, as in Program 1.

This affects:

- Debug logs: the same record object logged at two different times displays different data.
- Caching: if a cache key is built from `toString()`, the result changes unexpectedly.
- Tests: a test might pass when there is no mutation, yet fail when the shared object is modified.
- Domain reasoning: readers assume the record is an immutable event, yet its payload changes.

**Do not use `toString()` as a storage protocol or a stable identifier**. For arrays, the default string representation of an array does not even display contents like `Arrays.toString`.

A boundary copy, combined with immutable component values, makes toString more reliable for debugging purposes; it still does not replace formal schema serialization.

## 34. Choosing When to Copy and How Many Layers?

Not every record needs a deep copy of the entire object graph. Copying carries memory/CPU overhead and sometimes **breaks intentional shared-state semantics**.

Classify three cases:

1. **Value object/snapshot:** the caller expects the record not to change after construction. Use immutable types or defensively copy all reachable mutable layers sufficiently.
2. **Read-only view of a mutable model:** the caller expects to see updated state, but must not modify it through the accessor. You can use an unmodifiable view and document that the data **will change along with the source**. In that case, the record is not deep immutable.
3. **Handle to a service/state holder:** the component may be an `AtomicInteger`, a client, or a listener, because the goal is to hold a dependency. Do not call this record a value snapshot; using a regular class may be better to express lifecycle/identity.

A proper defensive approach must start from the **API contract**, not just mechanically adding `copyOf`.

## 35. Watch Out for Nulls and Cyclic Data

Factory copy methods such as `List.copyOf`, `Set.copyOf`, and `Map.copyOf` have a policy of **rejecting null elements/keys/values**. If the domain requires null, you can:

- Represent “no data” with `Optional` at the API level where appropriate, while weighing the use of Optional as a field/component according to project style.
- Use an explicit domain value such as `Unknown`, `Missing`.
- Use a mutable copy where nulls are permitted, then place an unmodifiable wrapper over that **unexposed** copy.
- Validate and reject null early with a clear message.

For object graphs with **cycles**, “general-purpose deep copying” is not just recursive `clone` calls; it also must handle identity, cycles, shared aliases, and the fact that external resources may not be copyable. In a domain model, it is usually more effective to design an immutable representation **without unintended cycles**, or convert to a DTO snapshot with explicit mapping rules.

Do not try to deep-copy a `Thread`, `Socket`, database connection, or service object just because a record field points to it: those objects typically have **identity and lifecycle**, rather than being value data.

## 36. Normalization in a Compact Constructor Does Not Automatically Make an Object Graph Immutable

A compact constructor can process parameter references before the compiler assigns the component field:

~~~java
record Report(String title, java.util.List<String> tags) {
    Report {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title");
        }
        title = title.strip();
        tags = java.util.List.copyOf(tags);
    }
}
~~~

This is a valid record. After the constructor finishes:

- Component `title` holds a stripped String.
- Component `tags` holds an unmodifiable snapshot of the List container.
- The tag elements are Strings, so the object graph used here has stable value semantics.
- The caller cannot reassign `report.title` or `report.tags` because they are private final component fields.

If the `tags` component is changed to List<MutableTag>, `List.copyOf` is no longer sufficient for deep immutability. You must accurately identify which parts are mutable and avoid inferring immutability from the compact syntax alone.

## 37. Program 12 — Value Record with Snapshot and Normalization

File **`StableReportRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Report(String title, List<String> tags) {
    Report {
        title = Objects.requireNonNull(title, "title").strip();
        if (title.isEmpty()) {
            throw new IllegalArgumentException("blank title");
        }
        tags = List.copyOf(
                Objects.requireNonNull(tags, "tags"));
    }
}

public class StableReportRecordDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("java");

        Report first = new Report("  Tutorial  ", source);

        source.add("mutable");
        Report second =
                new Report("Tutorial", List.of("java"));

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("equal=" + first.equals(second));

        try {
            first.tags().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("protected="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 StableReportRecordDemo.java
java StableReportRecordDemo
~~~

**Stdout:**

~~~text
first=Report[title=Tutorial, tags=[java]]
second=Report[title=Tutorial, tags=[java]]
equal=true
protected=UnsupportedOperationException
~~~

The two records have the same values after normalization and snapshotting, so `equals` returns true. Data added to source after creating first does not appear in first. The List component's accessor returns an unmodifiable list, so direct mutation is rejected.

**Point to remember:** this policy works because String and the tag strings are immutable; the example does not represent a universal deep-copy solution for every type of object.

## 38. Is “Shallow Immutability” a Bug in Records?

No. **Records fulfill the exact contract Java designed:** they fix the set of record components and the object's field references, while providing a transparent API for observing data.

A record with an `AtomicInteger` or MutableThing component does not violate the language. It simply needs to be **named and documented with the right semantics**.

Bugs arise when the designer or caller draws wrong inferences:

- Believing that `record` acts like a deep-freeze mechanism for the entire object graph.
- Putting a mutable `List` as a component without defensive copying while advertising the API as an “immutable value”.
- Using a record containing mutable components as a stable HashMap key.
- Returning an internal array directly through the accessor.
- Using an unmodifiable view while assuming it is already a snapshot.
- Ignoring mutable elements after copying the collection structure.
- Letting multiple threads access the same mutable state while thinking a final field automatically synchronizes writes.

Therefore, the accurate statement is that **a record guarantees structural/shallow immutability of its component fields**, whereas deep immutable behavior is **the responsibility of the component types and constructor/accessor design**.

## 39. Common Mistakes and How to Fix Them

| Misconception / Coding style | Issue | Appropriate approach |
| --- | --- | --- |
| `record Box(List<String> items) {}` is considered completely immutable | The caller's / accessor's List can still mutate | `List.copyOf` when a value snapshot is needed |
| Using only `final List<String>` | Final only locks the reference | Copy/wrap the collection according to the contract |
| `Collections.unmodifiableList(source)` means a snapshot | The view still sees mutations on source | `List.copyOf` or a wrapper around a private copy |
| `List.copyOf(List<MutableItem>)` is a deep copy | Mutable elements remain aliased | Copy/convert each element |
| Cloning an array in the constructor without overriding the accessor | Caller modifies the internal array through the getter | Override the accessor to return a clone |
| Cloning `MutableItem[]` is treated as a deep copy | Clone only copies the array container | Clone/convert each element |
| Record-generated equals automatically compares array contents | Array component equality is usually by identity | Override equals/hashCode or change representation |
| A record key containing an ArrayList is modified after `put` | Hash/equality can change | Stable immutable key |
| `Map.copyOf` protects all nested lists | Map snapshot is only one level | Copy each list and the map |
| An unmodifiable collection means mutable value objects are locked | There is no deep-freeze mechanism | Immutable element types |
| A record with AtomicInteger is an immutable value | Counter state is still mutable | Describe it as a state holder, not a value snapshot |
| A record has final references so it is thread-safe | Mutable objects still suffer from races | Separate concurrency controls |
| Relying on `Date.toString` for stable output | Can depend on timezone | Use timestamps/Instant per domain |
| Deep-copying every dependency | Copying services/resources breaks semantics | Distinguish values from handles/lifecycles |
| Copying while source is concurrently modified without synchronization | Snapshot can be inconsistent | Synchronization/source snapshot policy |
| Thinking records are always suitable as mutable entities | Records emphasize value carriers | Consider a regular class for a mutable identity entity |

## 40. Procedure to Check Whether a Record Is Deeply Immutable

When reading any record, follow these steps:

1. List all **record components** and their types.
2. Mark components that are **primitive/immutable value** types versus **references to mutable types**.
3. Determine whether **the caller still holds input aliases**.
4. Read the canonical constructor: are there defensive copies/normalization?
5. If copying occurs, determine whether copying happens **at the container level or also for elements**.
6. Read component accessors: do they return the reference by default or are they overridden to return a copy?
7. Look for mutation paths through nested objects: `get(0).set...`, arrays, dates, maps of lists.
8. Check whether generated/custom `equals` and `hashCode` depend on data that can change.
9. If the object is used as a HashMap key/Set element, evaluate **hash stability**.
10. If shared across threads, analyze synchronization and publication.
11. If the API promises a snapshot, test “modifying the source after construction”.
12. If the API promises no modification via accessor, attempt mutation from the accessor.
13. If elements are mutable, test “modifying the original element after snapshotting”.
14. If there are arrays, test both input and output clones, and content-based equality.
15. Explicitly document the null/duplicate/order/lifecycle contract of collection components.

You can conclude “deep immutability” only **within the defined object graph scope** and after no viable mutation paths remain within that scope; you cannot rely solely on the `record` keyword.

## 41. Practice Exercises

**Question 1.** Does `record Point(int x,int y) {}` carry the same typical mutable reference risks as `record Box(List<String> items) {}`?

**Question 2.** If a record has a `final List<String>` component, why can `items.add("A")` still be valid?

**Question 3.** What is the difference between modifying `record.items` and modifying `record.items().add(...)`?

**Question 4.** Why does a caller modifying an ArrayList after passing it into a record cause the record's observable data to change?

**Question 5.** Does the default accessor of a List component return a defensive copy?

**Question 6.** How does `List.copyOf(source)` differ from `Collections.unmodifiableList(source)`?

**Question 7.** If the domain allows null list elements, can `List.copyOf` be used directly?

**Question 8.** Does `List.copyOf(List<MutableItem>)` clone MutableItem?

**Question 9.** To keep list members stable when source elements are mutable, what is an appropriate strategy?

**Question 10.** If a component is `byte[]`, is cloning the input in the constructor sufficient?

**Question 11.** With `byte[]`, what must the accessor do to prevent callers from modifying the internal array?

**Question 12.** Does the generated `equals` of a record with byte[] components call `Arrays.equals` by default?

**Question 13.** If you want BytePacket to compare bytes by value, which methods must you override consistently?

**Question 14.** If a record contains a mutable List, can the record-generated hashCode change over time?

**Question 15.** Why can using a record with mutable components as a HashMap key be unsafe?

**Question 16.** Does `Map.copyOf(Map<String,List<String>>)` already lock the List values?

**Question 17.** How do you snapshot both the Map and the List values when the elements are Strings?

**Question 18.** Is `Date` immutable like `Instant`?

**Question 19.** If a record contains a legacy Date, at which boundaries is protection needed?

**Question 20.** Can a record containing an AtomicInteger be mutated? Where does the atomic behavior come from?

**Question 21.** Does an unmodifiable view always remain unchanged over time?

**Question 22.** Why should you not use `record.toString()` as a stable persisted key?

**Question 23.** When is “deep copy everything” a wrong decision?

**Question 24.** If the source List is modified concurrently while the constructor is copying, does `List.copyOf` automatically create a transactional snapshot?

**Question 25.** Why is a record not automatically thread-safe when a component holds an ArrayList?

**Question 26.** If a list component is `List<String>` and List.copyOf is used, why is this simple case usually safe enough as a value snapshot?

### Answers and Explanations

1. No. Two primitive components do not refer to a mutable object.
2. `final` locks the component reference, not the List object.
3. Reassigning the component field is forbidden; calling a mutating method on the referenced object can still be valid.
4. The record and the caller both point to the same List object (*aliasing*).
5. No; the default accessor returns the component value, which is a reference if the component is a reference type.
6. List.copyOf creates a structural unmodifiable snapshot; unmodifiableList(source) is a live view.
7. No; List.copyOf rejects null elements. Another copy/wrapper is needed if the domain accepts null.
8. No; it only copies the list structure/references.
9. Convert MutableItem into a separate immutable value type and then snapshot the collection.
10. Not yet; the default accessor still returns the internal array reference.
11. Override the accessor to return a clone/defensive copy.
12. No; arrays use identity-based equality by default.
13. `equals` and `hashCode` using `Arrays.equals`/`Arrays.hashCode`; consider toString if a stable format is needed.
14. Yes; List.hashCode can change when contents change.
15. Hash-based lookup assumes the key's hash/equality remains consistent while the key is stored.
16. No; the List values can still be mutable.
17. Copy each List using List.copyOf, then call Map.copyOf on the new map.
18. No; Date is mutable, Instant is immutable.
19. Copy input and copy accessor output; or switch to an immutable representation.
20. Yes; AtomicInteger state changes, and atomicity comes from the AtomicInteger API rather than from the record.
21. No. A view can reflect changes in the mutable backing collection.
22. Output can change due to mutable components and is not a durable data schema.
23. When components are service/resource handles or the code intentionally needs to share identity/lifecycle.
24. No; a synchronization policy or a consistency-guaranteeing data source is needed.
25. A final reference does not synchronize operations on an ArrayList.
26. Strings are immutable and the list is snapshotted/unmodifiable, so the structure and contents within that graph do not change under ordinary external mutations.

## 42. Checklist Before Publishing a Record as an Immutable Value

- [ ] Have all components been listed and classified as mutable/immutable?
- [ ] Is it understood that `record` only automatically guarantees private final component fields?
- [ ] If there is a mutable List input, does the constructor create an appropriate snapshot?
- [ ] If an unmodifiable wrapper is used, has the backing mutable collection been decoupled where needed?
- [ ] If there are mutable elements, have the elements been converted or defensively copied?
- [ ] If there are nested maps/lists, have all container levels needing protection been copied?
- [ ] If there are arrays, have they been cloned on input and in the accessor?
- [ ] For array value semantics, have `equals`/`hashCode` been made consistent?
- [ ] For legacy Date, has two-way copying or an immutable Java time type been used?
- [ ] Do copy factories follow the domain's null/duplicate/order policy?
- [ ] Are immutable component types spared unnecessary copying?
- [ ] Are generated equality and hashCode stable when the record is used as a key?
- [ ] Has it been determined whether mutable state is intentionally shared or not?
- [ ] If there is multi-threaded access, has concurrency been analyzed separately?
- [ ] Is an unmodifiable view never implicitly treated as an independent snapshot?
- [ ] Is a shallow copy never called a deep copy?
- [ ] If the API promises a value object, is modifying the input after construction tested?
- [ ] Is a caller attempting to modify data through the accessor tested?
- [ ] Is modifying the original mutable element tested?
- [ ] Have lifecycle/ownership been defined for non-copyable dependencies?
- [ ] Are the immutability boundaries of the object graph documented?
- [ ] Is `toString()` avoided as a serialization format or business key?

## 43. Official Java 17 Documentation

- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record characteristics, components, and accessors.
- [JLS 17 §8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): record header and component declarations.
- [JLS 17 §8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): private final fields, accessors, `equals`/`hashCode`/`toString`.
- [JLS 17 §8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): compact canonical constructor and input normalization/copying.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): `final` and the meaning of prohibiting variable reassignment.
- [Java SE 17 — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): basic contract of a record.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable list and null policy.
- [Java SE 17 — Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): copying into a structurally unmodifiable set.
- [Java SE 17 — Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable map copy.
- [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view of a list.
- [Java SE 17 — Arrays.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#equals(byte[],byte[])): comparing array contents.
- [Java SE 17 — Arrays.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#hashCode(byte[])): hashing array contents.
- [Java SE 17 — Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Date.html): mutable legacy time type.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): immutable timestamp.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic mutable state.

## 44. Summary

**Records do not automatically guarantee deep immutability.** Java fixes the set of component fields and forbids reassigning initialized fields, yet a `List`, `Map`, array, `Date`, or mutable DTO component can still change through external aliases. Default accessors can expose those references.

When building records with **stable value semantics**:

1. **Choose immutable component types** whenever possible.
2. For `List<String>`, use `List.copyOf` in the canonical constructor to obtain an unmodifiable structural snapshot.
3. For mutable elements, **copy/convert each element**; copying the list container alone is not enough.
4. For arrays and legacy Date, protect **both input and output**, not just cloning the input.
5. For nested collections, copy **the layers that need protection** and consider the null/duplicate/order policy.
6. When using records as keys, ensure the data participating in `equals`/`hashCode` does not change.
7. When concurrency is involved, use proper synchronization/concurrent APIs; `final` does not automatically make mutable objects thread-safe.

**Deep immutability is a design decision for the entire object graph**, not an automatic effect of the `record` keyword. Knowing how to distinguish shallow from deep immutability helps you choose the right constructor, accessor, data types, defensive copy strategy, and API contract.
