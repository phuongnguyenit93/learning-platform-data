# Shallow Immutability Limits and Defensive Copying in Java 17 `record`

`record` lets Java describe a data object concisely: declare data components once and let the compiler generate the constructor, accessors, `equals()`, `hashCode()`, and `toString()`. Yet a common misconception is assuming **every record is completely immutable**.

In Java 17, a record's component fields are `private final`, meaning references cannot be reassigned after the object is created. If a component is a `List`, `Map`, array, or an object with mutator methods, the **inner** data can still change. The distinction between *shallow immutability* and *deep immutability* governs how you design records used as DTOs, domain values, cache entries, or collection keys.

This lesson focuses on that limitation and **defensive copying** techniques when accepting and returning data. Examples use stable Java 17 APIs, including `record`, `List.copyOf`, `Map.copyOf`, `java.time`, and `Arrays`; no preview features are needed.

## 1. To What Extent Is a Record Truly Immutable?

Consider the declaration:

~~~java
public record Team(String name, java.util.List<String> members) {
}
~~~

The compiler generates component fields conceptually equivalent to:

~~~java
private final String name;
private final java.util.List<String> members;
~~~

This guarantees:

- You cannot reassign `name` or `members` on the same record after construction.
- No default setters exist.
- Accessors `name()` and `members()` expose component data.
- The record class itself is `final`, so subclasses cannot be created with `extends`.

However, `final` on a **reference field** only locks the reference, not making the referenced object immutable.

~~~java
import java.util.ArrayList;
import java.util.List;

record Team(String name, List<String> members) {
}

class Demo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("An", "Binh"));
        Team team = new Team("Backend", source);

        source.add("Chi");             // Mutate through the original variable
        team.members().remove("An");   // Mutate through the record's accessor

        System.out.println(team.members()); // [Binh, Chi]
    }
}
~~~

Even though you cannot write `team.members = ...`, the list can still be mutated via two paths: **the original reference held by the caller** and **the reference returned by the accessor**.

| Component in a record | What does the `final` field prevent? | Can data change after creation? |
| --- | --- | --- |
| `int count` | Reassigning the numeric value | No, primitive values are stored directly |
| `String name` | Reassigning the string reference | `String` itself is immutable |
| `LocalDate date` | Reassigning the date reference | `LocalDate` is an immutable type |
| `List<String> names` | Reassigning the list reference | Yes, if the held list implementation is mutable |
| `Map<String, String> settings` | Reassigning the map reference | Yes, if the held map is mutable |
| `byte[] bytes` | Reassigning the array reference | Yes, array elements can be reassigned |
| `List<MutableItem> items` | Reassigning the list reference | Yes, both list structure and individual element state can be mutated |

**Shallow immutability** means direct components are fixed at the reference or primitive-value level. **Deep immutability** requires that no external path can mutate any observable state of the object, including nested child objects across multiple levels.

A record containing only `String`, `int`, `BigDecimal`, `LocalDate`, or truly immutable values is usually sufficient on its own. With collections and arrays, you must examine data ownership boundaries.

## 2. Two State-Leakage Paths to Prevent

Defensive copying addresses two independent scenarios.

### 2.1. Leakage on Constructor **Input**

~~~java
List<String> input = new ArrayList<>(List.of("An"));
Team team = new Team("Core", input);

input.add("Binh"); // If Team keeps the raw reference, the record changes too.
~~~

If the constructor simply assigns `members = input`, the caller still owns a reference to a mutable object. Even if the accessor later blocks direct edits, the caller can still mutate via `input`.

### 2.2. Leakage on Accessor **Output**

~~~java
List<String> values = team.members();
values.clear(); // If the accessor returns the internal mutable list, the record is mutated.
~~~

Even if the constructor creates `new ArrayList<>(input)`, if the default accessor returns the internal list, recipients can still mutate the record.

Therefore, keeping a reliable snapshot in a record requires handling **both ingress and egress**:

- **On input:** take a copy independent of external collection structure.
- **On output:** do not hand callers a reference that can mutate internal state.

For a collection holding only immutable elements, a concise approach is storing `List.copyOf(input)`: the resulting list rejects structural modification operations, so the default accessor returning that list is structurally safe.

For **arrays**, Java has no immutable arrays: you must copy on input **and** on output.

## 3. Using Compact Constructors and `List.copyOf`

Let's build a record storing a team name and member list. After creation, we want:

1. The list not to change if the caller keeps mutating the original list.
2. Callers unable to `add`/`remove` through `team.members()`.
3. Team name non-blank; list contains no `null`.

**File `Team.java`:**

~~~java
import java.util.List;
import java.util.Objects;

public record Team(String name, List<String> members) {

    public Team {
        Objects.requireNonNull(name, "name");
        if (name.isBlank()) {
            throw new IllegalArgumentException("Team name must not be blank");
        }

        members = List.copyOf(Objects.requireNonNull(members, "members"));
    }
}
~~~

This is a **compact canonical constructor**: constructor name `Team` without an explicit parameter list. Java implicitly provides parameters `name`, `members` from the record header. The statement:

~~~java
members = List.copyOf(members);
~~~

reassigns the **constructor parameter** to the protected copy. When the compact constructor finishes normally, the compiler automatically assigns the parameter's final value to the corresponding component field. You do not need—and are not allowed—to write `this.members = ...` in a compact constructor body.

**File `TeamDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.List;

public class TeamDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("An", "Binh"));
        Team team = new Team("Core", source);

        source.add("Chi"); // Only modifies the source list.
        System.out.println(team.members()); // [An, Binh]

        try {
            team.members().add("Dung");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot modify list inside record");
        }

        System.out.println(team.members()); // [An, Binh]
    }
}
~~~

Command to run directly with JDK 17 when both files are in the same directory:

~~~bash
javac --release 17 -encoding UTF-8 Team.java TeamDemo.java
java TeamDemo
~~~

Expected output:

~~~text
[An, Binh]
Cannot modify list inside record
[An, Binh]
~~~

Here **you do not need to rewrite the `members()` accessor** because the reference stored by the record already points to an unmodifiable list. An important prerequisite is that the `String` elements are also immutable.

### What Does `List.copyOf` Do?

`List.copyOf(collection)` (available since Java 10 and standard in Java 17) creates an unmodifiable list with elements in the input collection's order.

- Mutating operations such as `add`, `set`, `remove`, and `clear` are unsupported.
- `null` is rejected: a `null` collection or `null` element throws `NullPointerException`.
- If the input is already a suitable unmodifiable list, the implementation may reuse that instance instead of allocating a new copy; do not rely on object **identity** between the two lists.
- It only **copies the collection structure**, not deep-copying individual elements.

If an empty member list is allowed, no extra validation is needed. If business rules require at least one member, check `members.isEmpty()` after calling `List.copyOf`.

## 4. Distinguishing Copies from Read-Only Views

The three collection approaches below behave differently:

~~~java
List<String> source = new ArrayList<>(List.of("A"));

List<String> view = java.util.Collections.unmodifiableList(source);

List<String> mutableCopy = new ArrayList<>(source);

List<String> snapshot = List.copyOf(source);

source.add("B");

System.out.println(view);        // [A, B]
System.out.println(mutableCopy); // [A]
System.out.println(snapshot);    // [A]
~~~

| Creation Method | Sees subsequent structural edits to `source`? | Can recipient mutate the result directly? |
| --- | --- | --- |
| `Collections.unmodifiableList(source)` | **Yes**, because it is only a view over the source list | Cannot mutate **through the view**, but the source can still be mutated |
| `new ArrayList<>(source)` | No, for structural changes to source after copying | **Yes** |
| `Collections.unmodifiableList(new ArrayList<>(source))` | No, for structural changes to source after copying | Not through the wrapper |
| `List.copyOf(source)` | No, for structural changes to source after copying | No |

`Collections.unmodifiableList` **is not equivalent to copying**. It creates a read-only view that reflects changes to the backing collection. In Java 17, `List.copyOf` is usually the cleanest option for storing a snapshot of a collection with immutable elements.

Similarly, `Set.copyOf` and `Map.copyOf` create unmodifiable collections:

~~~java
Set<String> tags = Set.copyOf(inputTags);
Map<String, String> options = Map.copyOf(inputOptions);
~~~

Behaviors to keep in mind:

- `Set.copyOf` and `Map.copyOf` do not guarantee list-like iteration order; do not depend on print order when displaying data or comparing snapshots.
- `Map.copyOf` rejects `null` keys or values; `Set.copyOf` rejects `null` elements.
- `Set.copyOf` deduplicates elements by equality; if input objects have distinct references yet are equal via `equals`, do not depend on which representative instance is retained.
- Structural collection unmodifiability **does not** mean the elements inside are immutable.

## 5. Crucial Limitation: `List.copyOf` Is Still a Shallow Copy

Suppose list elements are objects with a setter:

~~~java
import java.util.ArrayList;
import java.util.List;

final class MutableAddress {
    private String city;

    MutableAddress(String city) {
        this.city = city;
    }

    String city() {
        return city;
    }

    void changeCity(String city) {
        this.city = city;
    }
}

record Route(List<MutableAddress> stops) {
    Route {
        stops = List.copyOf(stops);
    }
}

class RouteDemo {
    public static void main(String[] args) {
        MutableAddress first = new MutableAddress("Hanoi");
        List<MutableAddress> addresses =
                new ArrayList<>(List.of(first));

        Route route = new Route(addresses);
        first.changeCity("Da Nang");

        System.out.println(route.stops().get(0).city()); // Da Nang
    }
}
~~~

Even though `Route` uses `List.copyOf`, the new list still holds **a reference to the exact same `MutableAddress`**. Thus mutating `first` outside changes the state observed from the record.

Diagrammatically:

~~~text
Original list ─────────┐
                       ├──> MutableAddress { city = "Da Nang" }
copyOf list ───────────┘
       ^
       |
     Route.stops
~~~

What gets copied is **the list of references**, not the entire object graph.

### Approach 1: Prefer Immutable Elements

If the domain allows, design `Address` as a record with immutable components:

~~~java
import java.util.List;
import java.util.Objects;

record Address(String city) {
    Address {
        Objects.requireNonNull(city, "city");
        if (city.isBlank()) {
            throw new IllegalArgumentException("City name must not be blank");
        }
    }
}

record Route(List<Address> stops) {
    Route {
        stops = List.copyOf(Objects.requireNonNull(stops, "stops"));
    }
}
~~~

`Address` holds only immutable `String`. `Route` holds a structural list snapshot containing `Address` objects that are also immutable. This achieves **deep immutability** for the `stops` data in the example.

The advantage of this approach is avoiding manual cloning per component, reducing risk of breaking `equals`/`hashCode`, and simplifying concurrent usage across threads.

### Approach 2: Create an Independent Snapshot for Each Mutable Element

If you must accept a mutable object from another API, **convert it to an immutable value** before storing:

~~~java
record AddressSnapshot(String city) {
}

record RouteSnapshot(List<AddressSnapshot> stops) {
    RouteSnapshot {
        stops = stops.stream()
                .map(address -> new AddressSnapshot(address.city()))
                .toList();
    }
}
~~~

`Stream.toList()` (available since Java 16) returns an unmodifiable list. In this example, each `MutableAddress` is converted into a fresh `AddressSnapshot` before building the list, and the `String` stored inside the snapshot is immutable.

This snippet assumes the input list and its elements are non-`null`, and that `MutableAddress` is not concurrently mutated by another thread while taking the snapshot. If a public API needs clear error reporting, add null checks and synchronize at the boundary where data is captured.

### Deep Copying Does Not Necessarily Mean Calling `clone()`

Deep copying means copying **enough of the mutable parts that need to be independent** in an object structure. There is no universal mechanism that automatically ensures every reference is cloned properly. `Object.clone()` typically performs only a shallow copy by default, and many classes do not support cloning. In Java 17, constructors converting to **immutable values**, copy constructors, or snapshot factories usually express intent much better.

## 6. Nested Collections: Copy Each Mutable Layer

A record can hold a map of lists:

~~~java
record Permissions(Map<String, List<String>> rolesByUser) {
}
~~~

If you only do:

~~~java
rolesByUser = Map.copyOf(rolesByUser);
~~~

then keys cannot be added/removed from the **outer map** via the record, yet the lists serving as **map values** remain mutable.

How to keep an independent snapshot of both the map and each list:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public record Permissions(Map<String, List<String>> rolesByUser) {

    public Permissions {
        Objects.requireNonNull(rolesByUser, "rolesByUser");

        Map<String, List<String>> snapshot = new HashMap<>();

        for (Map.Entry<String, List<String>> entry : rolesByUser.entrySet()) {
            String user = Objects.requireNonNull(entry.getKey(), "user");
            List<String> roles = List.copyOf(
                    Objects.requireNonNull(entry.getValue(), "roles"));
            snapshot.put(user, roles);
        }

        rolesByUser = Map.copyOf(snapshot);
    }
}
~~~

Usage example:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

class PermissionDemo {
    public static void main(String[] args) {
        List<String> roles = new ArrayList<>(List.of("READ"));
        Map<String, List<String>> source = new HashMap<>();
        source.put("an", roles);

        Permissions permissions = new Permissions(source);

        roles.add("WRITE");
        source.put("binh", new ArrayList<>(List.of("ADMIN")));

        System.out.println(permissions.rolesByUser());
        // {an=[READ]}
    }
}
~~~

Immutability here is achieved because:

- `Map.copyOf` prevents structural changes to the outer map and detaches it from the source.
- `List.copyOf` creates a new list for **each value**, preventing structural changes to nested lists.
- Keys and elements are all immutable `String`s.

If elements inside nested lists are mutable classes, keep copying/converting each element as shown in the previous section. If **insertion iteration order** must be preserved, consider `LinkedHashMap` with an appropriate read-only wrapper copy; `Map.copyOf` does not guarantee preserving iteration order.

### Note on Generics

The type `Map<String, List<String>>` only specifies element types; it does not guarantee that each list's implementation is unmodifiable. Generic types do not replace ownership checks or defensive copying.

## 7. Arrays in Records: Must Copy Both Input and Output

Java arrays always allow writing to elements, even when the reference is declared `final`. The following record is easily mutated:

~~~java
record RawPacket(byte[] data) {
}

byte[] input = {1, 2, 3};
RawPacket packet = new RawPacket(input);

input[0] = 9;          // Mutated outside constructor.
packet.data()[1] = 8; // Mutated via accessor.
~~~

If you only fix the constructor:

~~~java
record HalfSafePacket(byte[] data) {
    HalfSafePacket {
        data = data.clone();
    }
}
~~~

then callers cannot mutate via the original `input`, **but can still mutate via `packet.data()`** because the default accessor returns the internal array directly.

### 7.1. Bidirectional Copying

~~~java
import java.util.Arrays;
import java.util.Objects;

public record BytePacket(byte[] bytes) {

    public BytePacket {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BytePacket that
                && Arrays.equals(this.bytes, that.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }

    @Override
    public String toString() {
        return "BytePacket[length=" + bytes.length + "]";
    }
}
~~~

Here:

1. The compact constructor clones the array to isolate it from the caller's `byte[]`.
2. The `bytes()` accessor clones again so the stored array is not exposed.
3. `equals()` and `hashCode()` are overridden to compare **array contents** via `Arrays.equals`/`Arrays.hashCode`.
4. `toString()` is overridden to show useful length info instead of relying on default array reference formatting.

Usage example:

~~~java
import java.util.Arrays;

class BytePacketDemo {
    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        BytePacket packet = new BytePacket(input);

        input[0] = 9;

        byte[] readBack = packet.bytes();
        readBack[1] = 8;

        System.out.println(Arrays.toString(packet.bytes()));
        // [1, 2, 3]

        System.out.println(
                packet.equals(new BytePacket(new byte[] {1, 2, 3})));
        // true
    }
}
~~~

### 7.2. Why Pay Attention to `equals` and `hashCode` for Arrays?

For a record containing `byte[]` without overrides, the auto-generated `equals`/`hashCode` treat the array component by **array object identity**, rather than comparing contents with `Arrays.equals`.

~~~java
record Bytes(byte[] data) {
}

Bytes a = new Bytes(new byte[] {1, 2});
Bytes b = new Bytes(new byte[] {1, 2});

System.out.println(a.equals(b)); // false: two arrays with different references
~~~

Therefore, if a record represents **a byte value by content**, consider one of two options:

- Manually implement `equals`, `hashCode`, and a copying accessor like `BytePacket`.
- Convert the data into an immutable type with content-based value equality and an appropriate API. Do not blindly switch to `List<Byte>` when binary performance/memory matters, as boxing carries its own overhead.

For **two-dimensional arrays** or arrays holding mutable objects, `array.clone()` only copies the outer array. You must clone each subarray or convert each element to an immutable value, and consider `Arrays.deepEquals`/`Arrays.deepHashCode` if the structure has content-based equality semantics.

## 8. Immutability Makes `equals()`, `hashCode()`, and Caching More Reliable

Records auto-generate `equals` and `hashCode` based on components. If a mutable component changes after the record is placed into a `HashMap`/`HashSet`, the hash value can change and break lookups.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

record MutableKey(List<String> tags) {
}

class KeyDemo {
    public static void main(String[] args) {
        List<String> tags = new ArrayList<>(List.of("A"));
        MutableKey key = new MutableKey(tags);

        Set<MutableKey> keys = new HashSet<>();
        keys.add(key);

        tags.add("B"); // The record key's hashCode changed because the List changed.
        System.out.println(keys.contains(key)); // May be false.
    }
}
~~~

`HashSet` picks a bucket when adding an element based on the element's hash at that time. If the hash changes after insertion, lookups may no longer match the stored bucket. This is not unique to records, but a record's concise syntax easily tricks readers into assuming an object is already a safe value object.

Replace with:

~~~java
import java.util.List;

record StableKey(List<String> tags) {
    StableKey {
        tags = List.copyOf(tags);
    }
}
~~~

When elements are immutable `String`s, `StableKey` has a stable hash. This property is essential when using records as keys in caches, maps, sets, or value objects in domain models.

Do not override `hashCode()` to **hide** mutable state while `equals()` still depends on that state; both methods must keep honoring their consistency contract. A better design is preventing state used in equality from being mutated.

## 9. Domain Example: Order with a Stable List of Line Items

An order object needs an order ID and multiple line items. If each line item is also immutable, only the list structure needs copying.

**File `LineItem.java`:**

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record LineItem(String sku, int quantity, BigDecimal unitPrice) {

    public LineItem {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Unit price must not be negative");
        }
    }

    public BigDecimal amount() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Both `String` and `BigDecimal` are immutable. `quantity` is a primitive. Thus every successfully created `LineItem` has fixed state.

**File `Order.java`:**

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public record Order(String orderId, List<LineItem> items) {

    public Order {
        Objects.requireNonNull(orderId, "orderId");
        if (orderId.isBlank()) {
            throw new IllegalArgumentException("Order ID must not be blank");
        }

        items = List.copyOf(Objects.requireNonNull(items, "items"));
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Order must have line items");
        }
    }

    public BigDecimal total() {
        return items.stream()
                .map(LineItem::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
~~~

**File `OrderDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class OrderDemo {
    public static void main(String[] args) {
        List<LineItem> input = new ArrayList<>();
        input.add(new LineItem("BOOK-01", 2, new BigDecimal("125.50")));
        input.add(new LineItem("PEN-02", 3, new BigDecimal("10.00")));

        Order order = new Order("ORD-17", input);
        input.clear(); // Does not clear the order's line items.

        System.out.println(order.items().size()); // 2
        System.out.println(order.total());        // 281.00
    }
}
~~~

Run in the directory containing all three files:

~~~bash
javac --release 17 -encoding UTF-8 LineItem.java Order.java OrderDemo.java
java OrderDemo
~~~

Expected output:

~~~text
2
281.00
~~~

In this design, `Order` holds a snapshot of the list, while each `LineItem` holds immutable components. This is a suitable way to use records for data models needing value semantics, provided initial data is valid.

## 10. Immutable APIs to Prefer in Java 17

Choosing **component types** is just as important as copying. When choosing between a mutable type and an immutable type representing the same concept, prefer the immutable type to cut down on defensive copying code.

| Need | Typically Suitable Type | Reason |
| --- | --- | --- |
| Text | `String` | Immutable |
| Primitive integers, floats | `int`, `long`, `double` | Stores value directly |
| Exact decimals | `BigDecimal` | Immutable; suitable for money when rounding rules are defined |
| Calendar date | `LocalDate` | Immutable |
| Absolute point in time | `Instant` | Immutable |
| Time span | `Duration` | Immutable |
| Identifier | `UUID` | Immutable |
| Simple set/list of values | `List.copyOf`, `Set.copyOf` | Unmodifiable container; requires immutable elements |
| Configuration mapping | `Map.copyOf` | Unmodifiable container; requires immutable keys/values |
| Binary data | `byte[]` with bidirectional clone or immutable binary value | Arrays are not inherently immutable |

Example using `Instant` instead of storing a mutable date-time object:

~~~java
import java.time.Instant;
import java.util.Objects;

record AuditEvent(String action, Instant occurredAt) {
    AuditEvent {
        Objects.requireNonNull(action, "action");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

With `Instant`, there is no need to clone timestamps in either direction. If timezone conversion is needed for display, use `java.time` APIs to transform the presentation without mutating the original `Instant`.

Records can hold objects from external libraries. Before deciding whether to copy, inspect **that type's immutability contract**, not merely whether the record's field is `final`.

## 11. Testing Defensive Copying

Defensive copying should be verified from both directions: mutating the input after creation and attempting to mutate accessor output.

JUnit Jupiter 5 example testing `Team`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class TeamTest {

    @Test
    void changesToInputDoNotChangeRecord() {
        List<String> source = new ArrayList<>(List.of("An"));
        Team team = new Team("Core", source);

        source.add("Binh");

        assertEquals(List.of("An"), team.members());
    }

    @Test
    void accessorDoesNotAllowStructuralModification() {
        Team team = new Team("Core", List.of("An"));

        assertThrows(
                UnsupportedOperationException.class,
                () -> team.members().add("Binh"));
    }

    @Test
    void equivalentValuesAreEqual() {
        Team first = new Team("Core", new ArrayList<>(List.of("An")));
        Team second = new Team("Core", List.of("An"));

        assertEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode());
    }
}
~~~

For `BytePacket`, test both array directions:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class BytePacketTest {

    @Test
    void copiesInputAndOutputArrays() {
        byte[] source = {1, 2, 3};
        BytePacket packet = new BytePacket(source);

        source[0] = 9;

        byte[] returned = packet.bytes();
        returned[1] = 8;

        assertArrayEquals(new byte[] {1, 2, 3}, packet.bytes());
        assertEquals(
                new BytePacket(new byte[] {1, 2, 3}),
                packet);
    }
}
~~~

For nested collections or mutable elements, also test mutating **child elements** after creation; merely testing `add`/`remove` on the outer list is insufficient to catch deep leaks.

These tests describe the API's contract. If the project uses Maven or Gradle, configure JUnit accordingly and place tests in the configured test source directory; do not rely solely on running isolated tests from an IDE.

## 12. Limitations and Trade-Offs to Know

### 12.1. Copying Has a Cost

`List.copyOf` traverses elements when creating a snapshot of a mutable collection; cloning arrays copies bytes; copying nested objects can consume extra CPU and memory. For large datasets, establish **who owns the data and when a snapshot is needed** rather than copying redundantly.

If data is genuinely owned exclusively by one layer and mutable references are never exposed externally, copying at every internal boundary may be unnecessary. However, public APIs accepting mutable collections from outside should have clear ownership contracts to avoid hidden coupling.

### 12.2. A Snapshot Does Not Guarantee Absolute Thread Safety

`List.copyOf` creates a snapshot of collection structure at copy time; it **does not** make reading the input atomic if another thread is modifying the collection during copying. Similarly, if mutable elements are updated concurrently, captured data may be inconsistent.

When sharing records across threads:

- Publish the record only after construction succeeds.
- Ensure referenced internal elements are also immutable or properly synchronized.
- If snapshotting a concurrently updated structure, arrange a consistent read mechanism before capturing.

A record's `final` fields support Java's safe initialization semantics, but do not eliminate data races arising from mutable state referenced by the record.

### 12.3. Unmodifiable Collections Differ from Deeply Immutable Data

`List.copyOf`, `Map.copyOf`, and `Stream.toList` produce unmodifiable containers. However, they do not guarantee that objects inside are immutable. The term **unmodifiable** refers to mutation via the collection API; **deep immutable** refers to all state observable across references.

### 12.4. A "Deep" Copy Should Be Defined by Domain Needs

Blindly cloning every object is not always right. If an object graph contains cycles, intentional shared references, external connections, or non-cloneable resources, copying everything can break semantics. Design snapshots containing the exact values the recipient needs kept stable, such as `AddressSnapshot(city)` rather than keeping a full mutable address object with rich behavior.

### 12.5. Considerations for Serialization, Caching, or Logging

Records are frequently used for requests/responses and caching. While frameworks map components conveniently, deserialization can produce mutable collections or invalid values if object creation paths bypass expected contracts. Putting validation and copying in constructors/factories maintains a single enforcement point for invariants.

A record containing arrays or sensitive values may need a custom `toString()` to avoid logging data that should stay private. Clearly specify which fields may be exposed when designing APIs and telemetry.

## 13. Practice Exercises

**Exercise 1 — List of Names:** Create `record Course(String title, List<String> students)`. Use a compact constructor to validate the title and call `List.copyOf`. Write a test modifying the source list after creation and modifying via the accessor; record both outcomes.

**Exercise 2 — List of Mutable Objects:** Create a class `MutableScore` with a `setValue(...)` setter, then create `record Scores(List<MutableScore> values)`. Observe why `List.copyOf` does not prevent scores from changing. Switch the data to `record ScoreSnapshot(int value)` and verify state stability.

**Exercise 3 — Byte Arrays:** Create `record DocumentBytes(byte[] content)`. Write a compact constructor cloning input, an accessor cloning output, and `equals`/`hashCode` using `Arrays`. Create two arrays with different references but identical contents and verify equality behavior.

**Exercise 4 — Nested Map:** Create `record FeatureFlags(Map<String, List<String>> enabledByTeam)`. Require keys and value lists to be non-`null`. Copy each list and then create an unmodifiable map; try mutating both the input map and input lists.

**Exercise 5 — Keys in `HashSet`:** Use a record with a mutable `List<String>` as a key and observe the result after mutating the list; then replace it with a record using `List.copyOf` and compare behavior.

**Conclusion:** `record` in Java 17 guarantees that **component fields** cannot be reassigned after creation, but does not automatically protect the state of referenced objects. To design a stable value object, choose immutable components when possible, snapshot mutable data on ingress, avoid exposing mutable references on egress, and consider deep copying at layers where it is truly required.
