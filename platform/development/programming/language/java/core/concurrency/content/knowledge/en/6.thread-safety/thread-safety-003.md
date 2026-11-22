# Immutability and Immutable Object Graphs in Java Concurrency

## 1. Why Does Immutability Make Concurrent Programs Easier to Get Right?

When multiple threads access a mutable object simultaneously, each thread must answer several questions: who is allowed to write, who is allowed to read, when to read, which lock is required, and whether the data is synchronized? If an object is **completely initialized and never changes afterward**, reader-only threads do not contend to modify that object's state. This significantly reduces situations that cause **data races**, intermediate states, and business invariant violations.

**Immutability** means that the observable state of an object does not change after it is created. **Immutable object graph** extends this idea to the objects reachable through reference fields, collection elements, arrays, nested objects, and other paths starting from a root object.

For example, consider a configuration with the following structure:

```text
AppConfig
  ├── name: String
  ├── limits: Map<String, Integer>
  └── endpoints: List<Endpoint>
                       ├── host: String
                       └── tags: List<String>
```

For this configuration to be truly immutable as observed by the caller, not only the `name` field, but also the contents of `limits`, `endpoints`, each `Endpoint`, and `tags` must be protected against subsequent modification. Merely adding `final` to the three fields of `AppConfig` is **not enough** if they point to a mutable `HashMap`, `ArrayList`, or `Endpoint`.

Objective of this lesson: distinguish between levels of immutability, identify the boundaries of an object graph, create and safely publish snapshots in Java, and recognize vulnerabilities caused by aliasing, nested collections, and concurrent updates. This topic covers **Java concurrency in general**.

## 2. Four Commonly Confused Concepts

| Concept | Actual Guarantee | Example | What Is Not Guaranteed |
| --- | --- | --- | --- |
| **Final field** | The field cannot be reassigned via normal Java code after initialization | `final List<String> items` | The referenced list does not automatically become immutable |
| **Unmodifiable view** | The view reference does not allow modification through its standard methods | `Collections.unmodifiableList(source)` | If `source` remains mutable, the view can reflect changes to the source |
| **Unmodifiable snapshot** | A collection that cannot be modified via its API and no longer reflects structural changes to the source collection | `List.copyOf(source)` | The element objects inside may still be mutable |
| **Immutable object graph** | The observable state of the entire reachable structure does not change after publication | Record with `String`, integers, and copied lists of immutable elements | Still requires proper initialization and safe reference publication |

For example, `final List<String>` can be very safe if the assigned value is genuinely an unmodifiable list of immutable `String` instances, but the `final` keyword **by itself does not prove that**.

We should also distinguish:

- **Shallow immutability:** direct fields cannot be reassigned, or a collection does not allow structural modification through the API being used; inner objects can still be mutated.
- **Deep immutability:** every part of the observable state reachable through relevant references does not change. Both nested objects and reference aliases must be checked.
- **Effective immutability:** an object that technically has mutating APIs, but after publication is guaranteed never to be modified again. This is a *protocol* that all code must adhere to, making it harder to verify than a truly immutable type.
- **Read-only reference:** the caller cannot modify the object through that reference, but another owner may still be able to mutate the underlying object. Read-only does not automatically mean immutable.

## 3. Object Graphs and the Aliasing Problem

Java stores objects on the heap; reference-type fields point to other objects. Multiple variables can point to the same object: this is **aliasing (multiple references sharing a single object)**.

```text
owner.source ───┐
                ├──────> ArrayList ───> MutableItem
snapshot.items ─┘                         ↑
                                         │
caller.savedItem ─────────────────────────┘
```

If the constructor only does `this.items = source`, the caller still has `source` to add or remove elements. If the constructor calls `List.copyOf(source)`, the caller cannot modify the snapshot's structure through `source`, but if the `MutableItem` element is still shared, the caller can mutate it through `savedItem`. Both modification paths must be considered.

Ask two separate questions:

1. **Does anyone still hold a reference to the mutable collection that the snapshot is using?** If yes, the collection must be copied.
2. **Does anyone still hold a reference to mutable elements inside the collection?** If yes, copying the collection is not enough: the elements must be converted into immutable values or deep-copied according to the contract.

The graph can be a DAG, share child objects, or even contain cycles (A references B, B references A). Not every domain needs to "deep copy" everything; the question to solve is **which paths allow observable state to change**. For graphs with cycles, a deep copy must track already-copied objects to preserve relationships and avoid infinite recursion.

## 4. The Simplest Mistake: `final` Holds the Reference, Not the Object

Create the file `FinalReferenceIsMutableDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalReferenceIsMutableDemo {
    private static final class Store {
        final List<String> items;

        Store(List<String> items) {
            this.items = items;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Store store = new Store(source);
        source.add("B");

        System.out.println("store size=" + store.items.size());
        store.items.add("C");
        System.out.println("source size=" + source.size());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FinalReferenceIsMutableDemo.java
java FinalReferenceIsMutableDemo
```

Output:

```text
store size=2
source size=3
```

The `items` field is `final`, yet both `store.items` and `source` point to the **same ArrayList**. When one side mutates it, the other side observes the change. If multiple threads use that list and one thread modifies it while another reads without synchronization, there is a risk of a data race or behavior not guaranteed by the collection's contract.

What is wrong with the design? The constructor **allowed data ownership to remain shared** unintentionally. The minimum fix is to create an independent copy of the collection when constructing the object and expose no subsequent mutation path.

## 5. `Collections.unmodifiableList` vs. `List.copyOf`

The two APIs have different purposes and scopes:

`Collections.unmodifiableList(source)` creates a **view** that disallows modification through the view. If `source` is still modified, the view can reflect those changes. It is not a snapshot detached from the source collection.

`List.copyOf(source)` (Java 10+) returns an **unmodifiable** list whose contents are a snapshot of the source collection's elements at creation time, according to the API contract. It does not continue to depend on additions or removals on the source. If the source is already an appropriate unmodifiable list, the implementation may reuse the instance; you should not rely on receiving a new instance. `List.copyOf` also **does not accept null elements**.

Create the file `ViewVsCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));

        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshot cannot be modified");
        }
    }
}
```

```bash
javac ViewVsCopyDemo.java
java ViewVsCopyDemo
```

Output:

```text
view=[A, B]
snapshot=[A]
snapshot cannot be modified
```

This is **structural immutability of the collection**. In this example, the `String` elements are also immutable, so the snapshot contains no mutable child objects.

Similar APIs: `Set.copyOf`, `Map.copyOf`, `List.of`, `Set.of`, `Map.of`. They create or return unmodifiable collections, but you must pay attention to rules regarding `null`, duplicate elements, duplicate keys, and iteration order. In particular, do not assume that the iteration order of `Map.copyOf` or `Set.copyOf` preserves insertion order if the contract does not guarantee it.

**Limitation:** `copyOf` copies *element references*; it does not automatically deep-copy the referenced objects. If a mutable element is still held by the caller, the snapshot will still observe changes to that element.

## 6. A Shallow Snapshot Can Still Be Mutated from Within

Create the file `ShallowCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowCopyDemo {
    record Snapshot(List<StringBuilder> names) {
        Snapshot {
            names = List.copyOf(names);
        }
    }

    public static void main(String[] args) {
        StringBuilder element = new StringBuilder("An");
        List<StringBuilder> source = new ArrayList<>();
        source.add(element);

        Snapshot snapshot = new Snapshot(source);
        source.clear();
        element.append("-updated");

        System.out.println("snapshot size=" + snapshot.names().size());
        System.out.println("snapshot value=" + snapshot.names().get(0));
    }
}
```

```bash
javac ShallowCopyDemo.java
java ShallowCopyDemo
```

Output:

```text
snapshot size=1
snapshot value=An-updated
```

Even though `Snapshot` is a `record` and used `List.copyOf`, the element inside is still a shared mutable `StringBuilder`. Clearing the `source` list does not affect the snapshot's size, but modifying `element` changes the string that the snapshot sees.

Lesson: a **record does not automatically guarantee deep immutability**, because record components can be arrays, collections, or mutable objects. The immutability of an object graph depends on the **types and mutation paths of every reachable object**, not just the root type name.

In a real application, `StringBuilder` is not thread-safe. If one thread modifies it while another thread calls `toString()` without synchronization, the result also risks a data race. This example runs sequentially to deterministically illustrate that aliasing exists, rather than trying to trigger a random race.

## 7. Designing an Immutable Object Graph with Records and Defensive Copies

A common pattern is **immutable values at the leaves + collection snapshots at every layer + no leaked mutable references**.

Create the file `DeepImmutableSnapshotDemo.java` (JDK 17+):

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class DeepImmutableSnapshotDemo {
    record Member(String name, int score) {
        Member {
            Objects.requireNonNull(name, "name");
            if (score < 0) {
                throw new IllegalArgumentException("score");
            }
        }
    }

    record TeamSnapshot(String teamName, List<Member> members) {
        TeamSnapshot {
            Objects.requireNonNull(teamName, "teamName");
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        List<Member> source = new ArrayList<>();
        source.add(new Member("An", 10));
        source.add(new Member("Binh", 20));

        TeamSnapshot snapshot = new TeamSnapshot("Core", source);
        source.add(new Member("Chi", 30));

        System.out.println("source size=" + source.size());
        System.out.println("snapshot size=" + snapshot.members().size());
        System.out.println("first=" + snapshot.members().get(0).name());

        try {
            snapshot.members().add(new Member("Dung", 40));
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshot is unmodifiable");
        }
    }
}
```

```bash
javac DeepImmutableSnapshotDemo.java
java DeepImmutableSnapshotDemo
```

Output:

```text
source size=3
snapshot size=2
first=An
snapshot is unmodifiable
```

**Why is the graph here immutable in its contents?**

1. `Member` is a record with `String` and `int` components; `String` is immutable, and `int` is a primitive value. No mutable fields are exposed.
2. `TeamSnapshot` holds `teamName` as a `String` and `members` as a `List<Member>`.
3. The compact constructor of `TeamSnapshot` converts `members` via `List.copyOf(members)`. After the constructor finishes, structural changes to `source` do not affect the snapshot list.
4. Every element in the list is an immutable `Member`. There is no path from the snapshot that allows changing a `Member`'s name or score.
5. Callers receive the list via the record accessor but cannot add or remove elements from the snapshot using the list API.

A formulaic summary:

```text
Immutable parent
    + immutable fields
    + defensive copies of incoming collections
    + immutable elements recursively
    + no mutable state leaked through accessors
    = immutable observable object graph
```

This is a design principle, not an automatic calculation. If you replace `Member(String, int)` with `Member(String, List<StringBuilder>)`, you must further check the list and every `StringBuilder`. If you return an internal array directly, you need to copy both on input and on output, or replace the array with an appropriate immutable structure.

### 7.1. Why Is a Record's Compact Constructor Useful?

In `record TeamSnapshot(String teamName, List<Member> members)`, the compact constructor can normalize the `members` parameter using `members = List.copyOf(members)`. After the compact constructor body completes normally, Java automatically assigns the normalized parameter value to the corresponding record field. This ensures every new instance follows the same snapshot contract.

However, a record can still define custom accessors or methods that expose mutable objects; a record is only a syntax for declaring a state carrier with final fields, not a tool that enforces deep immutability.

### 7.2. Constructors Must Validate Whole-State Invariants

If an invariant requires that total scores be non-negative or that each member ID be unique, those conditions should be validated **before publishing the snapshot**. Validation that runs on already-copied data or data that cannot be modified by others during validation is much easier to reason about.

In particular, if a caller passes an `ArrayList` that **another thread is concurrently modifying** while the constructor calls `List.copyOf`, the copy does not automatically guarantee a logically consistent snapshot: reading a collection that is being modified without synchronization can still be a data race. **Copying must be performed when the source is stable, or under the same synchronization mechanism protecting the source.**

## 8. Nested Collections: Copy at Every Mutable Layer

Suppose you have:

```java
Map<String, List<String>> permissions;
```

If you only call `Map.copyOf(permissions)`, the original map is no longer used directly by the snapshot structure; however, the `List<String>` values can still point to **mutable lists**. A caller could execute `permissions.get("admin").add("delete")`, causing the list contents inside the snapshot to change as well.

One way to build an immutable graph is to copy the value lists first, and then copy the map:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

static Map<String, List<String>> immutablePermissions(
        Map<String, List<String>> source) {
    Objects.requireNonNull(source);
    Map<String, List<String>> copy = new HashMap<>();
    for (var entry : source.entrySet()) {
        copy.put(
                Objects.requireNonNull(entry.getKey()),
                List.copyOf(entry.getValue()));
    }
    return Map.copyOf(copy);
}
```

This is an **illustrative method snippet**; place it inside an appropriate Java class. This function creates a deep-enough snapshot because keys and elements are immutable `String`s. If the map values were `List<MutableUser>`, you would need to convert each `MutableUser` into an immutable type or an independent snapshot.

### 8.1. A Chain of Copies Must Capture One Logical Point in Time When Invariants Exist

Copying a nested map while another writer is updating **related structures** can produce a result that mixes multiple versions. If the source object has invariants spanning multiple collections, take the copy inside a read-synchronized block, or organize the source as an immutable snapshot itself and publish replacements atomically.

### 8.2. Not Every Graph Needs Recursive Deep Copying

A service object might reference a shared logger, an atomic counter, or a mutable cache. In that case, the entire physical graph is not immutable. You can still design an **immutable configuration snapshot** separate from mutable resources. Define the exact **data boundary that requires immutability**, and protect every access path *within that boundary*. Calling an object deeply immutable while it still exposes a mutable cache is inaccurate.

## 9. Arrays, `Date`, and Mutable Types Requiring Two-Way Defensive Copying

For array types, `final byte[] data` only keeps the reference final; it does not prevent modifying `data[i]`. If the constructor keeps the input array directly, a caller modifying the array after creating the object will alter the internal data. If the getter returns the internal array directly, the caller can also mutate it on the way out.

Create the file `DefensiveArrayDemo.java`:

```java
import java.util.Objects;

public class DefensiveArrayDemo {
    static final class Packet {
        private final byte[] payload;

        Packet(byte[] input) {
            payload = Objects.requireNonNull(input).clone();
        }

        byte[] payloadCopy() {
            return payload.clone();
        }

        int firstUnsignedByte() {
            return Byte.toUnsignedInt(payload[0]);
        }
    }

    public static void main(String[] args) {
        byte[] source = {7, 8};
        Packet packet = new Packet(source);

        source[0] = 99;
        byte[] returned = packet.payloadCopy();
        returned[0] = 55;

        System.out.println("source first=" + source[0]);
        System.out.println("returned first=" + returned[0]);
        System.out.println("packet first=" + packet.firstUnsignedByte());
    }
}
```

```bash
javac DefensiveArrayDemo.java
java DefensiveArrayDemo
```

Output:

```text
source first=99
returned first=55
packet first=7
```

Two `clone()` calls establish independent ownership of the array. The `payload` field still points to a mutable array object at the Java language level, but the `Packet` class gives callers no path to mutate the internal array, and the class itself never modifies it; therefore, the state of `Packet` is **observationally immutable to callers** under this protocol.

Two-dimensional arrays `byte[][]` are trickier: calling `clone()` on the outer array only copies references to each sub-array. You must clone the sub-arrays if they are mutable, and consider element objects when using `Object[]`.

Similarly, `java.util.Date` is mutable; keeping an input reference or returning an internal reference from a getter can allow state to change. You can carefully copy `Date` or prefer immutable types in `java.time` such as `Instant`, `LocalDate`, and `LocalDateTime` when they fit the domain. Do not swap types just because of the name "Date": you must also consider timezone semantics and domain data requirements.

## 10. How Does an Immutable Object Differ from an Unmodifiable Object?

An **unmodifiable interface/view** prevents callers from performing mutations through a specific API. An **immutable object** guarantees that its own state never changes after creation according to the type's contract, regardless of how many valid reference paths are provided.

For example, `Collections.unmodifiableList` blocks `view.add(x)`, yet changes made through the backing list still appear on the view. That is a read-only view.

`List.copyOf` creates a structurally unmodifiable list, detached from subsequent structural changes to the source. However, if the elements are mutable, the underlying graph is not yet immutable.

An object `final class Person { private final Address address; }` is only deeply immutable if `Address` is also immutable or is copied/wrapped so that no one has a path to mutate it. `final class` prevents subclassing; it does not make child objects immutable.

Evaluating immutability means evaluating **the type, all reference assignment paths, and the public API**, not just checking whether `final` or `unmodifiable` keywords are present.

## 11. Immutability and Thread Safety: The Exact Relationship

A properly constructed immutable object is a powerful tool for **thread safety**, because multiple readers can read it without needing synchronization to protect against object mutation—provided they receive the valid object through a publication path with a clear contract.

However, you must distinguish:

1. **Is the object actually immutable?** After the constructor, which state is still allowed to change?
2. **Was the object properly constructed?** Did `this` leak during the constructor? Can a half-initialized object be returned?
3. **Was the reference safely published?** How do other threads receive the object? Via `volatile`, a lock, a concurrent queue, `Thread.start()`, class initialization, or another standard mechanism?
4. **Do readers read from the same snapshot?** If a computation needs multiple fields, does the reader fetch the same snapshot object once?
5. **Are there mutable resources outside the snapshot boundary?** If so, that work must still be synchronized under its own protocol.

### 11.1. `final` Has Special Initialization Guarantees, But Does Not Replace Comprehensive Safe Publication

The Java Memory Model provides special guarantees for the values of **instance final fields** of properly constructed objects: when a constructor completes without letting `this` escape early, the initialized final values have special visibility semantics. This is the foundation that enables immutable value objects to work reliably.

Even so, relying solely on the final-field guarantee does not form a complete sharing protocol: it does not ensure readers receive the reference when needed, does not protect non-final/mutable state, and does not replace synchronization relationships required for post-initialization updates. Safe publication through an explicit mechanism makes correctness much easier to prove.

Do not start a thread inside a constructor to pass `this` out and assume final fields are already complete; that is **this escape**, which can cause another thread to observe uninitialized state.

### 11.2. Each Snapshot Replacement Needs Atomic Publication

A common pattern:

```text
Reader A ---snapshot v1---> [immutable graph v1]
Reader B ---snapshot v1---> [immutable graph v1]

Writer: build complete graph v2
        validate
        atomic publication (swap one reference)

Reader C ---snapshot v2---> [immutable graph v2]
Reader A still holds valid v1, unmodified behind its back.
```

Because neither graph is modified after publication, a reader that obtains v1 continues using v1 stably; a reader that obtains v2 uses the new state. The coordination point is **which reference is published**, rather than locking every read of every sub-field of a mutable graph.

## 12. Example: Atomic Snapshot Updates from Multiple Writers

An immutable graph also helps handle **multi-field updates that must move together**, such as two balances whose sum is always 100. Each writer builds a new valid snapshot and then performs an atomic update at the reference level. Readers fetch the reference **once** so they do not mix two different generations.

Create the file `AtomicImmutableStateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicImmutableStateDemo {
    record Balances(int left, int right) {
        Balances {
            if (left < 0 || right < 0 || left + right != 100) {
                throw new IllegalArgumentException("invalid balances");
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Balances> current =
                new AtomicReference<>(new Balances(80, 20));

        Runnable moveOne = () -> {
            for (int i = 0; i < 10; i++) {
                current.updateAndGet(old ->
                        new Balances(old.left() - 1, old.right() + 1));
            }
        };

        Thread a = new Thread(moveOne, "writer-a");
        Thread b = new Thread(moveOne, "writer-b");
        a.start();
        b.start();
        a.join();
        b.join();

        Balances snapshot = current.get();
        System.out.println("left=" + snapshot.left());
        System.out.println("right=" + snapshot.right());
        System.out.println("total=" + (snapshot.left() + snapshot.right()));
    }
}
```

```bash
javac AtomicImmutableStateDemo.java
java AtomicImmutableStateDemo
```

Output:

```text
left=60
right=40
total=100
```

Two writers each perform 10 transfers of one unit, totaling 20 transferred. `AtomicReference.updateAndGet` may retry the lambda when writers update concurrently; every successful update transitions from one valid snapshot to another valid snapshot. No `Balances` object is ever mutated in place.

**Important caveat:** the function passed to `updateAndGet` may be executed **multiple times for a single successful update** due to CAS retries. Therefore, do not write logs with non-repeatable side effects, call external services, send messages, or debit real accounts *inside the lambda*. Only compute the next state from the old state; side effects must have their own coordination/transaction mechanism.

`left + right == 100` is an internal invariant of the record, though `int` arithmetic can overflow in larger applications. This example uses small numbers; if the domain involves large numbers, use overflow checks like `Math.addExact` or appropriate numeric types and overall validation.

**Reading pitfall:** doing this is wrong if you need a consistent snapshot:

```java
int left = current.get().left();
int right = current.get().right();
```

This is an **illustrative snippet**, assuming the `current` variable from the example above. Two `get()` calls may observe different v1 and v2 versions, even though both individual snapshots are valid. Replace it with:

```java
Balances snapshot = current.get();
int left = snapshot.left();
int right = snapshot.right();
```

Fetch the same snapshot once for the entire computation. `AtomicReference` resolves publication contention, while the **immutable snapshot object** guarantees that data within a single version does not change.

## 13. Immutable Graphs Do Not Solve Every Concurrency Problem

An immutable graph enables safe sharing of read data, but it **does not automatically solve** the following issues:

- **Lost updates between writers:** if writers A and B both read v1, compute v2A and v2B, and each assigns `volatileReference = newValue`, one change can overwrite the other. If an update depends on the old state, use CAS/`updateAndGet` or a lock.
- **Operations spanning multiple references:** if two variables `currentConfig` and `currentRules` must change simultaneously, updating each `volatile` separately can still give readers an invalid combination. Combine them into **a single root snapshot**.
- **I/O and resources outside the JVM:** an in-memory snapshot does not automatically turn file/database/network writes into atomic transactions. Storage or communication system mechanisms are still required.
- **Copying cost:** creating new snapshots can consume CPU and memory if the object graph is large. You can use persistent data structures that share immutable structure, copy-on-write at an appropriate granularity, or a smaller domain design, but you must measure.
- **Side effects from accessors/callbacks:** an "immutable object" with methods that return sockets, mutable maps, or emit time-dependent events does not necessarily behave purely; separate immutable data from services with side effects.
- **Child objects with mutable caches:** if a graph contains a `HashMap` cache updated behind the scenes, the graph is no longer physically deeply immutable. If the cache is purely a hidden implementation detail, the cache itself must still be thread-safe and must not alter observable values according to the object's contract.
- **Snapshot lifecycle:** holding references to millions of old snapshots indefinitely can consume memory. Immutable does not mean you can skip lifecycle policies, reference reclamation, and memory management.

When data changes continuously at high frequency and the graph is large, it may be more appropriate to use mutable state protected by locks. There is no single choice for every workload.

## 14. Common Design Mistakes

### 14.1. Putting `final` on Every Field and Declaring Thread-Safety

```java
final class Registry {
    private final java.util.Map<String, String> values =
            new java.util.HashMap<>();

    void put(String key, String value) {
        values.put(key, value);
    }
}
```

This is an illustrative class. The `values` field is never reassigned, but `HashMap` is still mutable and does not support unsynchronized concurrent reads and writes by contract. You need a lock, an appropriate concurrent map, or to swap the reference to an immutable map snapshot; the choice depends on whether invariants span multiple fields or only operate per key.

### 14.2. Using `List.copyOf` While Elements Remain Mutable

```java
List<StringBuilder> snapshot = List.copyOf(source);
```

The snapshot fixes the list structure, but the `StringBuilder` instances can still change. Convert elements to `String`/immutable records, or deep-copy as needed.

### 14.3. Constructor Copies Input, But Getter Returns Mutable Internal State

```java
class Payload {
    private final byte[] bytes;

    Payload(byte[] input) {
        bytes = input.clone();
    }

    byte[] getBytes() {
        return bytes; // Leaks internal array.
    }
}
```

This illustrative class defends **the input** but does not defend **the output**. A caller modifying `getBytes()[0]` will alter internal data. Fix this with `return bytes.clone()` or an unmodifiable value-access API.

### 14.4. Wrapping with `Collections.unmodifiableMap` While Keeping and Mutating the Backing Map

An unmodifiable view does not create a snapshot; if the original object continues to change, readers see the data change too. Use `Map.copyOf` on a stable source (and copy nested mutable values) when an immutable snapshot is needed.

### 14.5. Consolidating a Snapshot But Still Reading the Mutable Reference Multiple Times

```java
String host = config.get().host();
int port = config.get().port();
```

If `config` is swapped to a new snapshot between the two `get` calls, the caller may read v1's host and v2's port. Fetch `Config snapshot = config.get()` once, then read all required fields from that same snapshot.

### 14.6. Creating an Immutable Object from a Concurrently Modified Collection

Calling `List.copyOf(sharedArrayList)` while another thread calls `sharedArrayList.add(...)` does not guarantee a consistent snapshot and does not make reading the source safe. You need a stable source, a shared lock, or a source that is already an immutable snapshot.

### 14.7. Forgetting Validation and Exceptions Before Publication

If a constructor/factory allows creating a snapshot with broken invariants or lets a pointer to the partially constructed object escape before completion, you cannot rely on the `final` keyword to rescue the contract. Build the complete object, validate it, and only publish the reference after the constructor returns successfully.

## 15. Choosing a Strategy in Java Applications

| Scenario | Suitable Starting Design | What to Verify |
| --- | --- | --- |
| Small value object, read-only after creation | Record/class with final fields, immutable components | Contains no leaked mutable references |
| Configuration with nested lists/maps | Defensive copy at each mutable layer, immutable elements | Alias paths from callers and nested collections |
| Need to store a binary array without external mutation | Clone input and clone output | Nested arrays require deeper copying |
| Configuration replaced by version, many readers | One immutable root snapshot + `volatile` or `AtomicReference` | Readers fetch reference once; whether there are multiple writers |
| Multiple writers transforming state based on old version | CAS/`updateAndGet` on immutable snapshot or lock | Retry lambdas must have no side effects |
| Very large state, changing continuously | Mutable state with appropriate locks or persistent immutable structures | Performance, invariants, deadlock risk, and copy cost |
| Passing data via queue between workers | Immutable message + `BlockingQueue` | Safe publication; do not mutate message after sending |
| References to lifecycle-managed resources like sockets | Separate mutable resources from immutable config | Ownership, resource closing, and thread coordination |

Choose based on the **unit of state that must be consistent**, read/write frequency, data size, and contract verifiability. A small immutable class is usually easier to test and reason about than a mutable object shared by multiple threads; however, the cost of creating snapshots continuously can become significant when the graph is large.

## 16. Self-Check

**Question 1.** Does `final List<MutablePerson> people` make its enclosing object deeply immutable?

**Answer:** No. `final` only locks the reference. The collection can be mutable; even if the collection's structure cannot be modified, each `MutablePerson` can still be mutated via another alias. You need to copy and/or convert elements into immutable values according to the contract.

**Question 2.** How do `Collections.unmodifiableList(source)` and `List.copyOf(source)` differ when elements are added to `source`?

**Answer:** The unmodifiable view typically reflects changes to `source`; `List.copyOf` provides a structural snapshot detached from subsequent structural modifications to the source. Neither automatically freezes mutable element objects.

**Question 3.** Is `record Response(List<StringBuilder> values) {}` deeply immutable?

**Answer:** No. A record has final component fields, but the list and `StringBuilder` can be mutable. You must copy the structure and replace elements with immutable types or make appropriate copies.

**Question 4.** If a constructor already cloned the `byte[]` input, can a getter return the `byte[]` field directly?

**Answer:** No, if you want to preserve observational immutability. Returning the mutable array reference allows callers to modify elements inside; you must copy on output or provide an unmodifiable accessor.

**Question 5.** Two writers simultaneously build a new config from the same old config and assign a `volatile` field. What can happen?

**Answer:** Each reference assignment is a publication, but one writer's logical change can be overwritten by the other writer. You need CAS/`updateAndGet` or a lock when updates depend on old state.

**Question 6.** An immutable record has two correlated fields. A reader calls `current.get()` twice to fetch each field. Is it guaranteed to get both fields from the same generation?

**Answer:** No. A writer can swap the root snapshot in between. The reader must fetch a single snapshot reference and then read both fields from that snapshot.

**Question 7.** Why does one-level copying of `Map<String, List<String>>` with `Map.copyOf` not guarantee an immutable graph?

**Answer:** The map snapshot still holds references to the value lists; if those value lists are mutable, callers can modify them. You must copy the list for each value first, and then copy the map. Since the elements are `String`, the value graph then has no mutable elements left.

**Question 8.** Does object immutability automatically cause every thread to receive a reference to that object?

**Answer:** No. Immutability solves the problem of state changing after creation. The **publication** and reference-handoff path still requires its own synchronization contract when the application demands guaranteed visibility and timely data delivery.

## 17. Summary

**Immutability** keeps state shared across threads stable and reduces the need for locking on reads. However, immutability is only trustworthy when you examine the **entire observable state graph**: final fields, unmodifiable collections, inner elements, arrays, child objects, and any aliases that still have a mutation path.

To build an **immutable object graph** in Java, construct the complete state in the constructor/factory, validate invariants, defensively copy at every mutable boundary, retain or return only values that cannot be mutated through another alias, and publish a complete root snapshot using an appropriate memory mechanism. When state needs to change, build a new version and swap **one reference** (or use locks to preserve consistency). An immutable snapshot does not eliminate managing multiple writers, I/O, task cancellation, or off-JVM resources, but it makes the shared data layer much simpler and more reliable.
