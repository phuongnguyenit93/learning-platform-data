# Java Serialization: Shared References, Cyclic References, and Object Handles

## 1. The Problem: How to Restore an **Object Graph** Accurately?

When using `ObjectOutputStream` and `ObjectInputStream`, it is not enough to merely save each field's value. A Java object can **point to the same object from multiple fields**, or objects can **reference each other in cycles**.

For example:

~~~text
               +-------------------+
               |    Person (An)    |
               |  home ----+       |
               |  office --|--+    |
               +-----------|--|----+
                           |  |
                           v  v
                      +----------+
                      | Address  |
                      |  Hà Nội  |
                      +----------+

home and office are the **same Address**, not two Address
objects that merely happen to have identical contents.
~~~

And a cyclic reference:

~~~text
       +--------+   next    +--------+
       | Node A | --------> | Node B |
       +--------+           +--------+
            ^                   |
            +-------------------+
                      next
~~~

If you merely copied field contents into independent duplicates, after deserialization:

- You could lose the `person.home == person.office` relationship.
- You could turn the `A -> B -> A` cycle into an infinite copy chain or an incorrect structure.
- You could alter program semantics, because **identity** (reference sameness) differs from equality (content equivalence).

**Default Java Object Serialization preserves sharing structure and cyclic references** by assigning an **object handle** to objects that have already appeared within *the same serialization stream*. Subsequent encounters are typically written as a **back-reference** rather than serializing the entire object again.

## 2. Basic Requirements to Serialize a Graph

A class serialized by default normally implements `java.io.Serializable`:

~~~java
import java.io.Serializable;

final class Node implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}
~~~

`Serializable` is a **marker interface**: no methods are required. `ObjectOutputStream.writeObject(root)` traverses objects reachable through serializable reference fields:

- Normal instance fields, **neither `transient` nor `static`**, participate in default serialization (subject to class/type rules).
- Primitive fields are stored by value.
- A field referencing another object can pull in the entire **graph of objects it points to**.
- `null` is written as a null value without creating a new object.
- Every object written in the graph must be compatible with serialization; a field referencing a non-serializable object typically throws `NotSerializableException`, unless excluded or handled via custom logic.

Do not confuse:

~~~java
Node first = new Node("X");
Node second = new Node("X");
boolean same = first == second;  // false
~~~

Even though `first.name.equals(second.name)` is true, these are **two distinct instances** and under default serialization will be saved under two separate handles.

Conversely:

~~~java
Node shared = new Node("X");
Node first = shared;
Node second = shared;
boolean same = first == second;  // true
~~~

This is just **one object** with two references. Serialization preserves that `==` relationship when restoring the graph within the stream, provided custom object-replacement hooks do not alter it.

## 3. What Is an Object Handle?

`ObjectOutputStream` manages stream state, including a table remembering which objects have already been serialized. When encountering an object for the first time:

1. The stream writes type metadata (including a class descriptor when needed).
2. The object receives a **handle** — an internal identifier within the **stream**, not a Java reference, RAM address, or `hashCode()`.
3. The stream writes persisted fields; if a field references another object, it recursively processes that object.
4. If an already-written object is encountered again, the stream can emit a **reference to its handle** instead of repeating the whole object.

On the reading side, `ObjectInputStream` maintains a corresponding handle table to return references pointing to **the same restored instance**.

Conceptual diagram:

~~~text
ObjectOutputStream

Call 1: writeObject(address)
  -> NEW_OBJECT(Address, handle H1, fields ...)

Call 2: writeObject(address) with the SAME instance
  -> REFERENCE(H1)

ObjectInputStream

Call 1: readObject() -> Address#1
Call 2: readObject() -> the exact same Address#1

Therefore: firstRead == secondRead  ==> true
~~~

This is only a **logical diagram**. Real streams also include headers, class descriptors, element type codes, and handles for class descriptors, strings/arrays, and other objects. Do not treat `H1` as a fixed byte handle or an identifier you can store standalone.

### Handles Differ from `hashCode()`, `equals()`, and Business Object IDs

| Concept | What is it used for? | Scope/limitations |
|---|---|---|
| `==` on two references | Checks whether they point to the same instance | Within one JVM |
| `equals()` | Checks equality defined by the class | Not necessarily the same instance |
| `hashCode()` | Supports hashing; not a unique ID | Can collide and vary by implementation |
| **Serialization handle** | Identifies objects already seen in the stream | Internal to each stream; affected by `reset()` |
| Business ID (UUID, database ID) | Identifies entities at the application level | Defined by the application, not auto-generated by serialization |

**Never use a handle read from a stream as a database primary key.** It is strictly an internal reference-encoding mechanism within the serialization format.

## 4. Why Are Shared References Preserved?

Suppose:

~~~java
// Illustrative snippet in a context with Serializable Address and Person classes.
Address address = new Address("Hà Nội");
Person person = new Person();
person.home = address;
person.office = address;
out.writeObject(person);
~~~

When the serializer traverses the `home` field, it writes `address` and assigns it a handle. Upon reaching `office`, it sees **the same `address` object** and emits a back-reference. The reading side reconstructs:

~~~java
Person restored = (Person) in.readObject();
System.out.println(restored.home == restored.office); // true
~~~

If two fields point to **two different `Address` objects that happen to have identical values**, the default serializer does not automatically "merge" them:

~~~text
Before write:  home -> Address#1("HN")
               work -> Address#2("HN")
After read:    home -> Address#3("HN")
               work -> Address#4("HN")

home != work, even though their attributes may match.
~~~

This is why you must determine whether a problem requires preserving **identity** or only preserving **values**.

### Sharing Across Multiple Nested Levels

It is not just two fields of the same object that are preserved. If a list contains `sameNode` twice, or multiple distinct objects point to a shared child object, back-references are still used throughout a graph written to the same stream.

~~~java
Node sameNode = new Node("shared");
List<Node> nodes = new ArrayList<>();
nodes.add(sameNode);
nodes.add(sameNode);
// After serializing/deserializing nodes, elements at index 0 and 1
// remain the same Node: nodes.get(0) == nodes.get(1).
~~~

This snippet is illustrative code requiring `java.util.*` imports and a serializable `Node` class; it is not a standalone program.

## 5. Cyclic References: Why Doesn't the Serializer Recurse Infinitely?

If two objects point to each other:

~~~java
Node a = new Node("A");
Node b = new Node("B");
a.next = b;
b.next = a;
~~~

The saving process can be visualized as:

~~~text
writeObject(a)
  1) first encounter with A -> assign handle HA
  2) write A.next = B
     3) first encounter with B -> assign handle HB
     4) write B.next = A
        5) A already has HA -> write REFERENCE(HA), stop recursing
  6) unwind and finish B, then A
~~~

Crucial point: **an object's handle is assigned before all of its reference fields finish being written**. Therefore, when traversal follows a link back to an object currently in the middle of being serialized, the serializer already has a handle to reference.

The reading side also creates and registers the object before populating all of its fields under the default mechanism, enabling cycle reconstruction:

~~~java
Node restored = (Node) in.readObject();
boolean cycle = restored.next.next == restored; // true
~~~

Cyclic references **do not** need to be broken by setting fields to `null`. However, serialization has resource limits (depth, size) and can fail on overly huge or complex graphs; do not assume arbitrary unbounded graphs or corrupted data can always be read.

### Self-Reference

An object can point to itself:

~~~java
Node self = new Node("SELF");
self.next = self;
~~~

After default serialize/deserialize:

~~~java
Node restored = (Node) in.readObject();
System.out.println(restored.next == restored); // true
~~~

This is a cycle of length 1. With many JSON libraries, handling cycles requires a separate strategy; **do not project JSON behavior onto Java Object Serialization**.

## 6. Complete Java 17+ Program

This example proves **four behaviors** by running actual code:

1. Two consecutive `writeObject(root)` calls on the same `ObjectOutputStream` refer to **the same previously serialized object**.
2. Mutating the `name` field and calling `writeObject(root)` again **does not automatically save the new field value** while the object still has an old handle in the stream.
3. `ObjectOutputStream.reset()` makes the next write **a fresh serialization**; the reader receives a new graph, and the updated field content is written.
4. Shared references and the `A -> B -> A` cycle are still re-established **within each graph**.

Save the file as **`ObjectHandleDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class ObjectHandleDemo {

    private static final class Node implements Serializable {
        private static final long serialVersionUID = 1L;

        String name;
        Node next;
        Node also;

        Node(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) throws Exception {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        a.also = b; // Both fields of A point to the same B.
        b.next = a; // A -> B -> A forms a cycle.

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out =
                     new ObjectOutputStream(bytes)) {
            out.writeObject(a); // First graph, containing handles for A/B.
            out.writeObject(a); // Back-reference to the previous A.

            a.name = "A-updated";
            out.writeObject(a); // Still a back-reference, does not write new name.

            out.reset();        // Discard the stream's handle table.
            out.writeObject(a); // Write a fresh graph with the updated name.
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {

            Node first = (Node) in.readObject();
            Node second = (Node) in.readObject();
            Node third = (Node) in.readObject();
            Node afterReset = (Node) in.readObject();

            System.out.println("same-root="
                    + (first == second && second == third));
            System.out.println("old-name=" + first.name);
            System.out.println("updated-name=" + afterReset.name);
            System.out.println("new-root="
                    + (first != afterReset));

            System.out.println("shared-child="
                    + (first.next == first.also));
            System.out.println("cycle="
                    + (first.next.next == first));
            System.out.println("new-cycle="
                    + (afterReset.next.next == afterReset));

            System.out.println("original-vs-restored="
                    + (a == first));
        }
    }
}
~~~

Compile and run in the directory containing the source file:

~~~bash
javac ObjectHandleDemo.java
java ObjectHandleDemo
~~~

**Exact stdout when the program succeeds:**

~~~text
same-root=true
old-name=A
updated-name=A-updated
new-root=true
shared-child=true
cycle=true
new-cycle=true
original-vs-restored=false
~~~

**Line-by-line explanation:**

- `first == second == third` are all true because the first three reads restore **one object handle** from one new object followed by two back-references.
- `old-name=A` because A's value was written when it **first appeared in the stream**; mutating A in memory **does not retroactively update already-serialized bytes**.
- `afterReset.name` is `"A-updated"` because the write after `reset()` serializes A's current state.
- `first != afterReset` because after reset, the reader builds a fresh graph for the subsequent data.
- `first.next == first.also` shows that the shared `B` is preserved.
- `first.next.next == first` and `afterReset.next.next == afterReset` show that both the old and new graphs have proper cycles.
- `a == first` is false because `a` is the original object in memory prior to writing, whereas `first` is an object reconstructed by deserialization in the same JVM.

**Note:** `ByteArrayOutputStream` only holds bytes in memory, so the demo has no filesystem dependency. It verifies identity and contents, **not on-disk persistence or durability**.

## 7. What Scope Does an Object Handle Exist In?

The handle table belongs to **each individual `ObjectOutputStream`** and is tracked by its matching `ObjectInputStream`. It is **not a JVM-wide global cache**.

### Same Stream, Same Object

~~~java
out.writeObject(shared);
out.writeObject(shared);
~~~

The second operation may emit only a back-reference because `shared` already has a handle in that stream. Reading the two items returns references to the same object.

### Two Independent Streams

~~~java
// Illustration, two different ObjectOutputStream instances:
outA.writeObject(shared);
outB.writeObject(shared);
~~~

Two streams have separate handle states. Reading independent streams normally creates distinct objects per stream, even if the writer passed the exact same original object into both.

### Within One Full-Graph Write

~~~java
// Illustration: root holds the same subObject across multiple fields.
root.left = subObject;
root.right = subObject;
out.writeObject(root);
~~~

The `left` and `right` fields both point to `subObject` in the restored graph (by default). This works regardless of whether `writeObject(root)` is called a second time.

### Two Objects with Equal Contents

~~~java
out.writeObject(new Node("same"));
out.writeObject(new Node("same"));
~~~

These are **two distinct instances**, not a shared reference. Reading normally creates two separate `Node` instances.

**Do not rely on `equals()` or `System.identityHashCode()` to guess serialization handles.** Those are completely separate mechanisms.

## 8. Why Can Mutating an Object and Calling `writeObject()` Again Still Yield Old State?

A very common mistake:

~~~java
// Illustration: User is a Serializable class.
User user = new User("first");
out.writeObject(user);

user.name = "second";
out.writeObject(user); // Does not automatically re-emit the entire new state.
~~~

The stream already knows `user`'s handle, so the second call may emit a back-reference. The reader returns an object with data restored from **the first write**.

### Approaches Based on Your Goal

- **Want to preserve identity and don't need a new snapshot:** call `writeObject` as usual; back-referencing is the intended behavior.
- **Want to write fresh state for the entire graph:** call `ObjectOutputStream.reset()` at a valid boundary **before the next write**; the stream forgets old handles and serializes anew.
- **Want to explicitly resend the same object's state while retaining known auxiliary objects:** examine `writeUnshared(...)` or call `writeObject` on a separate snapshot copy, understanding sharing-scope limits.
- **Want transactional updates to persisted state:** an object stream is not a database; use a record/version format or an appropriate storage engine.

Never manually tamper with handle tables or rely on `flush()` to refresh an object cached in the stream. **`flush()` pushes buffered bytes; it does not clear object handles.**

## 9. `ObjectOutputStream.reset()`: Clearing Handle State for Subsequent Writes

Calling `reset()` on `ObjectOutputStream`:

1. Discards remembered state of objects that previously appeared in the stream.
2. Writes a reset marker in the stream so the corresponding `ObjectInputStream` **also clears its handle table at that point**.
3. Previously written objects **are neither modified nor erased from existing bytes**.
4. An object with the same Java reference passed to `writeObject` after reset will be serialized as a brand-new appearance.
5. May increase stream size because objects and class descriptors may be written again.

Example:

~~~java
out.writeObject(root); // Root is assigned a handle for the first time.
out.writeObject(root); // Back-reference.
out.reset();            // Forget the handle table.
out.writeObject(root); // Root's data is written anew.
~~~

**Never call `reset()` while the serializer is actively writing an object**, such as arbitrarily calling it inside `private writeObject(ObjectOutputStream out)` to force a fresh child. The specification forbids resetting mid-object serialization and can throw `IOException`.

Reset is a **milestone for subsequent objects**, not a command that erases bytes before it. Do not confuse it with `ByteArrayOutputStream.reset()`: `ByteArrayOutputStream`'s method clears **buffered byte contents** in RAM, whereas `ObjectOutputStream.reset()` resets **serialization state** and emits the corresponding marker.

### Does Reset Perform a "Deep Copy"?

If after reset you re-serialize the entire root graph, the reader receives a new graph in which internal references remain properly shared/cyclic. However:

- Mutable data reflects only the state at the moment of re-serialization.
- If a field is `transient`/`static` or custom hooks alter logic, the resulting graph can differ.
- Defining a new graph does not automatically guarantee thread safety if the original object is modified concurrently by another thread during serialization.

## 10. `writeUnshared()`: Writing a Top-Level Object Without Using Prior Back-References

Besides `writeObject`, Java provides:

~~~java
out.writeUnshared(obj);
~~~

According to the `ObjectOutputStream` documentation:

- For **the top-level object passed directly**, `writeUnshared(obj)` always writes the object as a newly appearing object rather than emitting a back-reference to a previous write.
- Subsequent `writeObject(obj)` calls **do not back-reference the object written via `writeUnshared`** as though it were a normal shared write.
- This rule **applies directly only to the root object of the call**. Transitively referenced child objects can still share handles with other already-written objects.
- Therefore, **`writeUnshared()` is not a full-graph deep copy** and does not disable object handle sharing at every level.

### Direct Example with Two Unshared Writes

Save as **`UnsharedDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class UnsharedDemo {

    private static final class Box implements Serializable {
        private static final long serialVersionUID = 1L;
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) throws Exception {
        Box box = new Box(7);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out =
                     new ObjectOutputStream(bytes)) {
            out.writeUnshared(box);
            out.writeUnshared(box);
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            Box first = (Box) in.readUnshared();
            Box second = (Box) in.readUnshared();

            System.out.println("first=" + first.value);
            System.out.println("second=" + second.value);
            System.out.println("distinct=" + (first != second));
        }
    }
}
~~~

Run:

~~~bash
javac UnsharedDemo.java
java UnsharedDemo
~~~

**Stdout:**

~~~text
first=7
second=7
distinct=true
~~~

In this example `Box` is simple, with no `readResolve()` or child objects, so the two reads receive **two distinct instances**.

### `readUnshared()` Differs from `readObject()`

`ObjectInputStream.readUnshared()` reads a new object **and prevents subsequent reads from back-referencing that handle**. If `readUnshared()` encounters an existing back-reference in the stream, Java throws an **`ObjectStreamException`** (commonly `InvalidObjectException` in implementations; do not tie logic to a specific subtype when relying only on the API contract).

Incorrect example:

~~~java
// Write:
out.writeObject(box);
out.writeObject(box); // Back-reference to box.

// Read:
Box first = (Box) in.readObject();
Box second = (Box) in.readUnshared(); // Invalid on a back-reference.
~~~

This is an **illustrative snippet spanning write and read sides**, not a standalone program. Never use `readUnshared` indiscriminately in place of every `readObject`.

**Subtle exception:** `readResolve()` can replace an object with a singleton or an instance existing elsewhere, and `enum`/`Class` have special semantics. Thus combining `writeUnshared`/`readUnshared` is not an absolute guarantee of a fresh instance for *every object kind*. If `readResolve` returns an array, `readUnshared` uses a shallow clone per specification. Child objects within the graph can also remain shared.

## 11. Byte Stream: `TC_OBJECT`, `TC_REFERENCE`, and `TC_RESET`

In the Java Object Serialization protocol, stream elements are tagged with type codes:

| Token | High-level meaning |
|---|---|
| `TC_OBJECT` | Data for a new ordinary object |
| `TC_ARRAY` | A new array |
| `TC_STRING` / `TC_LONGSTRING` | A new `String` |
| `TC_CLASSDESC` | Corresponding class descriptor |
| `TC_REFERENCE` | Reference to an existing object/descriptor/string handle |
| `TC_NULL` | Null reference |
| `TC_RESET` | Resets the stream's handle state at this point |

This is a **conceptual view of the protocol**, not a complete list of every token. An actual stream also contains headers such as magic/version, descriptors, and other elements. Not every `writeObject` call emits `TC_OBJECT`; subsequent encounters can emit just `TC_REFERENCE`.

~~~text
writeObject(root)  -> NEW root (handle Hroot), children, fields ...
writeObject(root)  -> TC_REFERENCE(Hroot)
reset()            -> TC_RESET
writeObject(root)  -> NEW root/children, new handle table
~~~

A handle is not a memory pointer. It represents object identity **within the stream format**.

To learn the binary format, read the Java Object Serialization Stream Protocol rather than relying on a single example's hexdump; handles for class descriptors, strings, and auxiliary items shift offsets depending on the graph.

## 12. When Can Sharing Relationships or Cycles Be Altered?

The default mechanism preserves graphs, but special configurations/hooks can alter the outcome:

### `transient` and `static`

~~~java
class Data implements Serializable {
    private static final long serialVersionUID = 1L;

    Node child;                // Serialized by default.
    transient Node cache;      // Not saved by default serialization.
    static Node registry;      // Not part of persisted instance state.
}
~~~

If a cycle passes only through a `transient` field, that reference edge **is not saved** under default mechanics. Upon deserialization, the transient field receives its default value unless custom logic restores it.

### `writeReplace()` and `readResolve()`

A class can define **object-replacement** hooks during writing/reading. When `readResolve()` returns a singleton (for instance, a canonical instance), `==` comparisons may no longer behave like ordinary newly instantiated objects.

This is useful for singletons/canonicalization, though it must be designed and tested carefully because it easily causes identity surprises, especially alongside `readUnshared`. Do not add these hooks to basic graph examples unnecessarily.

### Custom `writeObject`/`readObject`

A class can customize which field data is stored in the stream. If a custom implementation skips a critical field, writes unusual child objects, or reconstructs state via custom rules, the resulting graph can differ.

**Rule:** if the goal is preserving the graph like default serialization, keep `defaultWriteObject()` / `defaultReadObject()` compliant with the contract inside hooks, and add only thoroughly verified logic.

### `Externalizable`

`Externalizable` gives the class full responsibility for writing/reading its state. Do not assume every custom format restores graphs accurately if the author omits fields or fails to re-establish reference links. Distinguish the stream's handle capability from the data a class chooses to write.

## 13. Common Mistakes: Confusing Identity, Snapshots, and Reset

| Symptom | Cause | How to fix |
|---|---|---|
| After reading, two fields are `==` when copies were expected | They pointed to the same object; the stream preserved sharing | Clarify whether sharing or copying is needed; create new objects if required |
| After reading, two objects are `equals()` yet `!=` | Two distinct instances existed before writing | Do not confuse value equality with identity |
| Worrying a cycle will cause infinite serialization | Mistakenly thinking the serializer recurses without memoization | Object handles break cycles under default mechanics |
| Mutating a field then calling `writeObject` again, yet reader sees old value | Stream emitted a back-reference to the already-written object | Write a new snapshot or call `out.reset()` at a valid boundary |
| Still seeing old value after `flush()` | Flushing bytes does not clear the handle table | Use `reset()` or another strategy; do not rely on `flush()` |
| Calling `writeUnshared()` and thinking all child objects are independent | Only the root object is guaranteed to be written as new | Understand that transitively referenced children can still be shared |
| `readUnshared()` encounters a back-reference and fails | The API forbids reading a back-reference with `readUnshared` | Match write and read semantics properly |
| Calling `reset()` inside custom serialization throws an error | Reset cannot be called mid-object write | Call `reset()` only outside graph serialization turns |
| Serialization throws `NotSerializableException` while writing | A reachable object is not serializable | Make it serializable, `transient`, or use a custom representation |
| `InvalidClassException` when reading | Incompatible class metadata/`serialVersionUID` | Manage versions/schemas rather than changing UIDs arbitrarily |
| Data mutated concurrently during serialization | Object graph was not snapshotted atomically | Synchronize or build an immutable snapshot before writing |
| Stream grows continuously due to frequent resets | Every reset causes objects/class descriptors to be rewritten | Balance freshness, identity, and size |
| Reading back an object and comparing `==` against the original source object | Normal deserialization creates new objects | Compare identity within the restored graph, not across two worlds |

## 14. Connection to `serialVersionUID` and Exceptions

Serialization stores class metadata and field state. If a class changes incompatibly between writing and reading, `InvalidClassException` can occur. You should declare `private static final long serialVersionUID` on serializable classes needing format stability, though **declaring a UID does not guarantee every class change is compatible**.

Errors to know:

- `NotSerializableException`: a non-serializable object exists in the graph and was not validly replaced or excluded.
- `InvalidClassException`: class descriptor/schema is incompatible with the current class version.
- `StreamCorruptedException`: stream data violates format or is corrupted.
- `EOFException`: reading past available stream data.
- `ClassNotFoundException`: required class for reconstruction cannot be found.
- `ObjectStreamException` when `readUnshared` encounters an illegal back-reference.
- `IOException`: underlying I/O or protocol error.

**Never continue using an `ObjectOutputStream` or `ObjectInputStream` assuming its state remains valid after a serious mid-graph read/write error.** Consult the Java serialization exception protocol documentation and open fresh streams when recovering at a trusted boundary.

## 15. Security: Deserialize Only Trusted or Controlled Data

Java Object Serialization **is not a safe communication format by default for untrusted data**. `ObjectInputStream.readObject()` can instantiate a rich class graph and trigger special mechanisms during reconstruction; tampered streams can cause memory/resource abuse or other deserialization hazards.

For untrusted inputs:

1. Consider using a simpler data format with an explicit schema instead of Java native serialization.
2. If `ObjectInputStream` is unavoidable, configure **`ObjectInputFilter`** in Java 17 to restrict allowed classes, graph depth, reference counts, array sizes, and total bytes.
3. Bound input size before deserializing, authenticate the source, and check business invariants after reading.
4. Never treat `serialVersionUID` or object handles as authentication or encryption measures.
5. Never log entire object graphs directly in sensitive environments; they may contain cycles or leak data.

Illustrative simple filter example:

~~~java
// Illustrative snippet, input is an already-created ObjectInputStream.
// Adjust the pattern to actual classes; do not copy
// a demo allowlist to production without auditing.
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=10000;maxbytes=1048576;maxarray=100000;!*");
input.setObjectInputFilter(filter);
~~~

The pattern above **blocks every class** not explicitly permitted, so it cannot read the `Node` example as written; it illustrates **resource limits + deny-by-default**. In a real application, add the context-specific list of permitted classes. This illustrative snippet requires `import java.io.ObjectInputFilter;`.

## 16. Sound Design for Application Data

### When to Keep Default Sharing

If multiple entities share **the same meaningful object** (such as a shared address, cache, or config in the graph), default serialization restores the exact topology. Use regular `writeObject` and ensure every object needing persistence in the graph has an appropriate representation.

### When Fresh Versioned Snapshots Are Needed

If writing multiple consecutive snapshots of the same mutable object to **one `ObjectOutputStream`**, establish a refresh policy:

- Call `reset()` between snapshots if it is acceptable that new objects do not share identity with earlier snapshots.
- Or construct a fresh DTO/immutable snapshot for each write.
- Never rely on `flush()` or `close()` to force the serializer to re-write an object that already has a handle.

### When Avoiding Graph Repetition

If a graph is very large with many shared references, keeping handles reduces stream size significantly. However, the handle table also retains state in the stream; a very long-lived stream can consume more memory. You can reset at clear boundaries, accepting that data will be re-serialized after reset.

### When Long-Term Persistence Is Required

Java native serialization is coupled to class layout, serial UIDs, and compatibility rules. If persisting for years, transferring across different tech stacks, or needing strict schema governance, consider versioned, schema-independent formats (such as JSON/CBOR/Protocol Buffers suited to the context), and explicitly represent object IDs/references if sharing and cycles are needed.

## 17. Self-Check

1. Two fields before writing point to the same object. After default deserialization, is `field1 == field2`? **True.**
2. Two distinct objects have `equals() == true`. Does the serializer merge them automatically? **No.**
3. `A.next=B` and `B.next=A`. Why doesn't serialization recurse infinitely? **The serializer assigns a handle before finishing fields and emits a back-reference when encountering A again.**
4. Is an object handle a Java memory address or database ID? **No; it is a stream-scoped identifier.**
5. Calling `writeObject(obj)` twice on the same stream without reset: what do the two reads normally return? **The same deserialized instance via back-reference.**
6. Mutating a field after the first write and calling `writeObject` again: does it automatically send the new field? **No, if the second write emits a back-reference.**
7. Does `ObjectOutputStream.reset()` erase already-written bytes? **No. It resets handle state and writes a reset marker.**
8. Is `ByteArrayOutputStream.reset()` the same as `ObjectOutputStream.reset()`? **No. One clears in-memory bytes; the other resets serialization state.**
9. Does `writeUnshared(root)` guarantee all child objects are unshared with earlier graphs? **No; only the top-level root of the call.**
10. Is it valid for `readUnshared()` to read a back-reference? **No; it throws `ObjectStreamException`.**
11. Are `static` or `transient` fields saved by default serialization? **No.**
12. Should `ObjectInputStream` read arbitrary streams from the Internet? **No; source verification, filters, and resource limits are required.**
13. Does `serialVersionUID` replace versioning/schema migration? **No.**
14. Using the same class across two separate `ObjectOutputStream` instances: do they share a handle table? **No.**
15. Why is `original == restored` usually false even when the graph preserves identity? **Deserialization constructs objects in a new graph; identity is restored only among references within the read graph/stream.**

## 18. Official References

- [Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html): `writeObject`, `writeUnshared`, `reset`, and shared references.
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): `readObject`, `readUnshared`, graph restoration, serial filtering.
- [Java SE 17 — Java Object Serialization Specification: System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): handles, shared references, and cyclic references.
- [Java SE 17 — Object Output Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/output.html): handle assignment algorithm, reset, `writeUnshared`.
- [Java SE 17 — Object Input Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html): handle restoration, reset tokens, and `readUnshared`.
- [Java SE 17 — Stream Protocol](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/protocol.html): element format, `TC_REFERENCE`, `TC_RESET`, and class descriptors.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): limiting and filtering data during deserialization.
