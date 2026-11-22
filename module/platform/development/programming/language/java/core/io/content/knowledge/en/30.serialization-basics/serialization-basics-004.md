# Java Serialization: Shared References, Circular References, and Object Handles

## 1. The Problem: How to Correctly Restore an **Object Graph**?

When using `ObjectOutputStream` and `ObjectInputStream`, what matters is not only saving each field's value. A Java object can **point to the same object from multiple different fields**, or objects can **reference each other in a cycle**.

Example:

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

home and office are **the same Address**, not two Addresses
that merely happen to have identical content.
~~~

And a circular reference:

~~~text
       +--------+   next    +--------+
       | Node A | --------> | Node B |
       +--------+           +--------+
            ^                   |
            +-------------------+
                      next
~~~

If field contents were merely copied as independent duplicates, after deserialization:

- The relationship `person.home == person.office` could be lost.
- The cycle `A -> B -> A` could turn into an infinite copy chain or an incorrect structure.
- Program semantics could change, because **identity** (reference identity) differs from equality (content equality).

**Default Java Object Serialization preserves sharing structure and circular references** by assigning an **object handle** to objects that have already appeared within *the same serialization stream*. Subsequent encounters are typically written as a **back-reference** instead of serializing the entire object again.

## 2. Basic Requirements to Serialize a Graph

A class serialized with the default mechanism typically implements `java.io.Serializable`:

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

- Regular instance fields that are **neither `transient` nor `static`** participate in the default serialization mechanism (subject to class/type rules).
- Primitive fields are stored by value.
- Fields referencing other objects can pull along the entire **graph of objects they point to**.
- `null` is written as a null value without creating a new object.
- Every object to be written in the graph must be eligible for the serialization mechanism; a field referencing a non-serializable object normally causes `NotSerializableException`, unless excluded or handled via custom serialization.

Do not confuse:

~~~java
Node first = new Node("X");
Node second = new Node("X");
boolean same = first == second;  // false
~~~

Even though `first.name.equals(second.name)` is true, they are **two distinct instances** and under the default mechanism will be saved with two different handles.

Conversely:

~~~java
Node shared = new Node("X");
Node first = shared;
Node second = shared;
boolean same = first == second;  // true
~~~

This is only **one object** with two references. Serialization preserves that `==` relationship when reconstructing the graph in the stream, provided custom object replacement does not alter it.

## 3. What Is an Object Handle?

`ObjectOutputStream` manages the stream's state, including a table tracking objects already serialized. When encountering an object for the first time:

1. The stream writes object type information (including a class descriptor when needed).
2. The object receives a **handle** — an internal identifier within the **stream**, not a Java reference, RAM address, or `hashCode()`.
3. The stream writes the fields to be persisted; if a field references another object, it continues processing that object.
4. If an already-written object is encountered again, the stream can write a **reference to the handle** instead of repeating the whole object.

On the reading side, `ObjectInputStream` maintains a corresponding handle table to return references to the **same restored instance**.

Conceptual diagram:

~~~text
ObjectOutputStream

Call 1: writeObject(address)
  -> NEW_OBJECT(Address, handle H1, fields ...)

Call 2: writeObject(address) with the SAME instance
  -> REFERENCE(H1)

ObjectInputStream

Call 1: readObject() -> Address#1
Call 2: readObject() -> the same Address#1

Therefore: firstRead == secondRead  ==> true
~~~

This is only a **logical diagram**. An actual stream also contains a header, class descriptors, element type codes, and handles for class descriptors, strings/arrays, and other objects. Do not treat `H1` as a fixed handle byte or an ID that can be stored independently.

### Handles Differ from `hashCode()`, `equals()`, and Business Object IDs

| Concept | What is it used for? | Scope/limitations |
|---|---|---|
| `==` on two references | Checks whether they are the same instance | Within one JVM |
| `equals()` | Checks equality defined by the class | Not necessarily the same instance |
| `hashCode()` | Supports hashing; not a unique ID | Can collide; can vary by implementation |
| **Serialization handle** | Identifies objects already seen in the stream | Internal per stream; affected by `reset()` |
| Business ID (UUID, database ID) | Identifies entities at the application level | Defined by the application, not auto-generated by serialization |

**Never use a handle read from a stream as a database primary key.** It is strictly a reference-representation mechanism inside the serialization format.

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

When the serializer traverses field `home`, it saves `address` and assigns a handle. Reaching field `office`, it sees the **same `address` object** and writes a back-reference. The reading side reconstructs:

~~~java
Person restored = (Person) in.readObject();
System.out.println(restored.home == restored.office); // true
~~~

If two fields point to **two different `Address` instances that happen to have equal values**, the default serializer does not "merge" them:

~~~text
Before write: home -> Address#1("HN")
              work -> Address#2("HN")
After read:   home -> Address#3("HN")
              work -> Address#4("HN")

home != work, even though their attributes may be identical.
~~~

This is why you must decide whether the problem requires preserving **identity** or only preserving **values**.

### Sharing Across Multiple Nested Levels

It is not only two fields of the same object that are preserved. If a list contains `sameNode` twice, or multiple different objects point to one child object, a back-reference can still be used within a graph written to the same stream.

~~~java
Node sameNode = new Node("shared");
List<Node> nodes = new ArrayList<>();
nodes.add(sameNode);
nodes.add(sameNode);
// After serializing/deserializing nodes, elements at index 0 and 1
// are still the same Node: nodes.get(0) == nodes.get(1).
~~~

This snippet is illustrative code, requiring `java.util.*` imports and a serializable `Node` class; it is not a standalone program.

## 5. Circular References: Why Doesn't the Serializer Recurse Infinitely?

If two objects point to each other:

~~~java
Node a = new Node("A");
Node b = new Node("B");
a.next = b;
b.next = a;
~~~

The saving process can be pictured as:

~~~text
writeObject(a)
  1) first encounter with A -> assign handle HA
  2) write A.next = B
     3) first encounter with B -> assign handle HB
     4) write B.next = A
        5) A already has HA -> write REFERENCE(HA), stop recursing
  6) return to finish B, then A
~~~

The key point: **an object's handle is assigned before all of its reference fields have finished being written**. Thus, when reaching a link back to an object currently being serialized, the serializer already has a handle to reference.

The reading side also allocates/registers the object before completing all of its fields under the default mechanism, enabling cycle reconstruction:

~~~java
Node restored = (Node) in.readObject();
boolean cycle = restored.next.next == restored; // true
~~~

Circular references **do not** need to be broken by setting fields to `null`. However, the serialization mechanism has resource limits (depth, size) and can fail on excessively large/complex graphs; do not assume arbitrary unbounded graphs or corrupted data can always be read.

### Self-Reference

An object can point to itself:

~~~java
Node self = new Node("SELF");
self.next = self;
~~~

After default serialization/deserialization:

~~~java
Node restored = (Node) in.readObject();
System.out.println(restored.next == restored); // true
~~~

This is a cycle of length 1. With many JSON libraries, handling cycles may require a special strategy; **do not assume JSON behavior applies to Java Object Serialization**.

## 6. Complete Java 17+ Program

This example demonstrates **four phenomena** by running actual code:

1. Two consecutive `writeObject(root)` calls in the same `ObjectOutputStream` reference the **same previously serialized object**.
2. Modifying the `name` field and calling `writeObject(root)` again **does not automatically save the new field value** if the object still has an existing handle in the stream.
3. `ObjectOutputStream.reset()` makes the next write a **new serialization**: the reading side receives a new graph, and the updated field content is written.
4. Shared references and the `A -> B -> A` cycle are still reconstructed **within each graph**.

Save the file **`ObjectHandleDemo.java`**:

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
            out.writeObject(a); // First graph, creates handles for A/B.
            out.writeObject(a); // Back-reference to the original A.

            a.name = "A-updated";
            out.writeObject(a); // Still a back-reference, does not write the new name.

            out.reset();        // Discard the stream's handle table.
            out.writeObject(a); // Write a new graph with the updated name.
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
- `old-name=A` because A's value was recorded when it **first appeared in the stream**; mutating A in memory **does not retroactively update already-serialized bytes**.
- `afterReset.name` is `"A-updated"` because the write after `reset()` serializes A's current state.
- `first != afterReset` because after reset, the reader creates a new graph for subsequent data.
- `first.next == first.also` shows that the shared B is preserved.
- `first.next.next == first` and `afterReset.next.next == afterReset` show that both the old graph and the new graph have intact cycles.
- `a == first` is false because `a` is the original object in memory before writing, whereas `first` is an object reconstructed by deserialization within the same JVM.

**Note:** `ByteArrayOutputStream` only holds bytes in memory, so the demo does not depend on the filesystem. It verifies identity and content, **not disk persistence/durability**.

## 7. What Is the Scope of an Object Handle?

The handle table belongs to **each `ObjectOutputStream`** and is tracked by the corresponding `ObjectInputStream`. It is **not a JVM-wide global cache**.

### Same Stream, Same Object

~~~java
out.writeObject(shared);
out.writeObject(shared);
~~~

The second operation can simply write a back-reference, since `shared` already has a handle in that stream. When reading the two corresponding entries, both variables receive references to the same object.

### Two Independent Streams

~~~java
// Illustration, two different ObjectOutputStreams:
outA.writeObject(shared);
outB.writeObject(shared);
~~~

The two streams have separate handle states. Reading independent streams normally creates a new object per stream, even if the writer passed in the exact same original object.

### Within One Write of an Entire Graph

~~~java
// Illustration: root holds the same subObject across multiple fields.
root.left = subObject;
root.right = subObject;
out.writeObject(root);
~~~

Fields `left/right` point to the same `subObject` in the restored graph (by default). This works regardless of whether `writeObject(root)` is called a second time.

### Two Objects with Equal Content

~~~java
out.writeObject(new Node("same"));
out.writeObject(new Node("same"));
~~~

These are **two distinct instances**, not a single shared reference. Reading normally creates two separate `Node` instances.

**Do not rely on `equals()` or `System.identityHashCode()` values to guess serialization handles.** Those are completely different mechanisms.

## 8. Why Can Mutating an Object and Calling `writeObject()` Again Receive the Old State?

A very common mistake:

~~~java
// Illustration: User is a Serializable class.
User user = new User("first");
out.writeObject(user);

user.name = "second";
out.writeObject(user); // Does not automatically resend the full new state.
~~~

The stream already knows `user`'s handle, so the second call can emit a back-reference. The reader returns the object with data restored from the **first write**.

### Solutions Depending on Your Goal

- **Want to preserve identity and do not want a new snapshot:** call `writeObject` as usual; back-referencing is the required behavior.
- **Want to write the new state of the entire graph:** call `ObjectOutputStream.reset()` at a valid boundary **before the next write**; the stream forgets old handles and re-serializes next time.
- **Want to explicitly resend the same object's state while keeping already-known child objects:** examine `writeUnshared(...)` or `writeObject` on a separate snapshot, understanding its sharing-scope limitations.
- **Want to update persisted state transactionally:** an object stream is not a database; use a versioned record format or an appropriate storage engine.

Do not manually tamper with handle tables or rely on `flush()` to refresh an object cached in the stream. **`flush()` pushes buffered bytes; it does not clear object handles.**

## 9. `ObjectOutputStream.reset()`: Clearing Handle State for Subsequent Writes

`reset()` on `ObjectOutputStream`:

1. Discards remembered state of objects already seen in the stream.
2. Writes a reset marker into the stream so the corresponding `ObjectInputStream` **also clears its handle table at that point**.
3. Previously written objects **are not modified or removed from existing bytes**.
4. If an object with the same Java reference is passed to `writeObject` after reset, it is serialized as a new occurrence.
5. Can increase stream size because objects and class descriptors may be written again.

Example:

~~~java
out.writeObject(root); // Root is assigned a handle for the first time.
out.writeObject(root); // Back-reference.
out.reset();            // Forget handle table.
out.writeObject(root); // Root's data is written again.
~~~

**Do not call `reset()` while the serializer is actively writing an object**, such as calling it arbitrarily inside `private writeObject(ObjectOutputStream out)` to force a fresh child. The specification forbids resetting mid-object serialization and it can throw `IOException`.

Reset is a **milestone for subsequent objects**, not a command to erase preceding bytes. Do not confuse it with `ByteArrayOutputStream.reset()`: `ByteArrayOutputStream`'s method clears the **byte buffer contents** in RAM, whereas `ObjectOutputStream.reset()` resets **serialization state** and writes the corresponding marker.

### Does Reset Perform a "Deep Copy"?

If after reset we serialize the whole root graph again, the reading side gets a new graph in which internal references remain properly shared/cyclic. However:

- Mutable data only reflects the state at the moment of re-serialization.
- If a field is `transient`/`static` or custom hooks alter logic, the resulting graph may differ.
- Defining a new graph does not automatically ensure thread-safety if another thread mutates the original object during serialization.

## 10. `writeUnshared()`: Rewriting the Root-Level Object Without Using an Old Back-Reference

Besides `writeObject`, Java provides:

~~~java
out.writeUnshared(obj);
~~~

According to `ObjectOutputStream` documentation:

- For the **root-level object passed directly**, `writeUnshared(obj)` always writes the object as a newly appearing object, rather than writing a back-reference to a previous write.
- Subsequent `writeObject(obj)` calls **do not back-reference a `writeUnshared` write** as if it were a regular shared write.
- This rule **applies only directly to the root object of the call**. Transitively referenced child objects can still share handles with other already-written objects.
- Therefore, **`writeUnshared()` is not a full-graph deep copy** and does not mean disabling object caching at every level.

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

`ObjectInputStream.readUnshared()` receives a new object **and prevents subsequent reads from back-referencing that handle**. If `readUnshared()` encounters an actual back-reference already in the stream, Java throws an **`ObjectStreamException`** (commonly `InvalidObjectException` by implementation; do not tie logic to a specific subtype if relying solely on the API contract).

Incorrect example:

~~~java
// Write:
out.writeObject(box);
out.writeObject(box); // Back-reference to box.

// Read:
Box first = (Box) in.readObject();
Box second = (Box) in.readUnshared(); // Invalid on a back-reference.
~~~

This is an **illustrative snippet across writer/reader sides**, not a standalone program. Do not arbitrarily substitute `readUnshared` for all `readObject` calls.

**Subtle exception:** `readResolve()` can replace an object with a singleton or an instance existing elsewhere, and `enum`/`Class` have special semantics. Thus combining `writeUnshared`/`readUnshared` is not an absolute guarantee of a brand-new instance for *every kind of object*. When `readResolve` returns an array, `readUnshared` uses a shallow clone per the specification. Child objects inside the graph can themselves still be shared.

## 11. Byte Stream: `TC_OBJECT`, `TC_REFERENCE`, and `TC_RESET`

In the Java Object Serialization protocol, stream elements are tagged with type codes:

| Token | General meaning |
|---|---|
| `TC_OBJECT` | Data for a new ordinary object |
| `TC_ARRAY` | A new array |
| `TC_STRING` / `TC_LONGSTRING` | A new String |
| `TC_CLASSDESC` | Corresponding class descriptor |
| `TC_REFERENCE` | Reference to an object/descriptor/string that already has a handle |
| `TC_NULL` | Null reference |
| `TC_RESET` | Resets the stream's handle state at this point |

This is a **conceptual view of the protocol**, not a list of every token. An actual stream also has a header like magic/version, descriptors, and other elements. Not every `writeObject` call emits `TC_OBJECT`; subsequent encounters may emit only `TC_REFERENCE`.

~~~text
writeObject(root)  -> NEW root (handle Hroot), children, fields ...
writeObject(root)  -> TC_REFERENCE(Hroot)
reset()            -> TC_RESET
writeObject(root)  -> NEW root/children, fresh handle table
~~~

A handle is not a memory pointer. It serves to represent object identity **inside the stream format**.

To learn the binary format, read the Java Object Serialization Stream Protocol instead of relying on a single example's hexdump; handles for class descriptors, strings, and auxiliary elements shift offsets depending on the graph.

## 12. When Can Sharing or Cyclic Relationships Be Altered?

The default mechanism preserves the graph, but special configurations/hooks can change the outcome:

### `transient` and `static`

~~~java
class Data implements Serializable {
    private static final long serialVersionUID = 1L;

    Node child;                // Serialized by default.
    transient Node cache;      // Not persisted by default serialization.
    static Node registry;      // Not part of persisted instance state.
}
~~~

If a cycle passes only through a `transient` field, that reference edge **is not saved** by the default mechanism. On deserialization, the object's transient field receives its default value unless custom logic restores it.

### `writeReplace()` and `readResolve()`

A class can define an **object substitution** mechanism on write/read. When `readResolve()` returns a singleton (e.g., a canonical instance), `==` results may no longer match what you would expect from regular new objects.

This is useful for singletons/canonicalization, yet must be carefully designed and tested because it easily causes identity confusion, especially when combined with `readUnshared`. Do not attach these hooks to default graph examples unnecessarily.

### Custom `writeObject/readObject`

A class can customize the field data stored in the stream. If a custom implementation skips an important field, manually writes unusual child objects, or restores according to bespoke rules, the resulting graph can differ.

**Rule of thumb:** if your goal is to preserve the graph as in default serialization, keep `defaultWriteObject()` / `defaultReadObject()` faithful to the contract inside hooks, and only add verified logic.

### `Externalizable`

`Externalizable` grants the class greater control to manually write/read its state. Do not blindly expect every custom format to restore the graph accurately if the author omits fields or fails to re-establish reference relationships. Distinguish the stream's handle capability from the data a class chooses to write.

## 13. Common Mistakes: Confusing Identity, Snapshots, and Reset

| Symptom | Cause | Solution |
|---|---|---|
| After reading, two fields are `==` when copies were expected | They originally pointed to the same object; stream preserves sharing | Clarify whether sharing or copying is needed; create new objects if required |
| After reading, two objects are `equals()` but `!=` | Before writing, they were two distinct instances | Do not confuse value equality with identity |
| Worrying circular references will cause infinite serialization | Mistakenly thinking serializer always recurses without memoization | Object handles break cycles under the default mechanism |
| Modifying a field then calling `writeObject` again, yet reader still sees old value | Stream uses a back-reference to the already-written object | Write a new snapshot or call `out.reset()` at a valid boundary |
| Still seeing old values after `flush()` | Flushing bytes does not clear the handle table | Use reset or another strategy; do not rely on flush |
| Calling `writeUnshared()` thinking all child objects are distinct too | Only the root object is guaranteed to be written as new | Understand transitively referenced children can still share handles |
| `readUnshared()` hits a back-reference and fails | API forbids reading a back-reference with `readUnshared` | Match write/read semantics properly |
| Calling `reset()` inside custom serialization throws an error | Reset cannot be called mid-object write | Only reset outside graph serialization turns |
| Serialization throws `NotSerializableException` on write | A reachable object is not serializable | Make it serializable, `transient`, or use a custom representation |
| `InvalidClassException` on read | Class metadata/`serialVersionUID` incompatible | Manage versions/schemas; do not just change UID arbitrarily |
| Data mutated concurrently during serialization | Object graph is not snapshotted atomically | Synchronize or create an immutable snapshot before writing |
| Stream grows continuously due to frequent resets | Each reset causes objects/class descriptors to be written again | Balance freshness, identity, and size |
| Reading original object from stream and comparing `==` against source object | Normal deserialization creates new objects | Compare identity within the restored graph, not across two worlds |

## 14. Relation to `serialVersionUID` and Exceptions

Serialization includes class information and field state. If a class changes incompatibly between write and read, `InvalidClassException` can occur. Declare `private static final long serialVersionUID` explicitly for serializable classes that need a stable format, though **declaring a UID does not guarantee every class change is compatible**.

Exceptions to know:

- `NotSerializableException`: an object in the graph does not support serialization and is not validly replaced/excluded.
- `InvalidClassException`: class descriptor/schema is incompatible with the current class version.
- `StreamCorruptedException`: stream data is malformed or corrupted.
- `EOFException`: reading past available stream data.
- `ClassNotFoundException`: the class to reconstruct cannot be found.
- `ObjectStreamException` when `readUnshared` encounters an illegal back-reference.
- `IOException`: underlying I/O failure or protocol error.

**Do not continue using an `ObjectOutputStream` or `ObjectInputStream` assuming its state is still safe after a serious error mid-graph write/read**. Read the Java serialization exception protocol documentation and create a new stream when recovering at a reliable boundary.

## 15. Security: Only Deserialize Trusted or Controlled Data

Java Object Serialization **is not a safe default communication format for untrusted data**. `ObjectInputStream.readObject()` can instantiate a rich class graph and trigger special mechanisms during restoration; a tampered stream can cause memory/resource abuse or other deserialization hazards.

For untrusted input:

1. Consider using a simpler, explicit-schema data format instead of Java native serialization.
2. If `ObjectInputStream` is unavoidable, configure **`ObjectInputFilter`** in Java 17 to restrict classes, graph depth, reference counts, array sizes, and total bytes within allowed bounds.
3. Bound input size before deserializing, authenticate the source, and check business invariants after reading.
4. Do not treat `serialVersionUID` or object handles as authentication or encryption measures.
5. Do not directly log the entire object graph in sensitive environments; it can introduce cycles or leak data.

Simple filter illustration:

~~~java
// Illustration; input is an already-created ObjectInputStream.
// Adjust the pattern to actual classes; do not copy
// a demo allowlist to production without reviewing it.
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=10000;maxbytes=1048576;maxarray=100000;!*");
input.setObjectInputFilter(filter);
~~~

The pattern above **blocks every class** not explicitly permitted, so it cannot read the `Node` example as-is; it only illustrates **resource limits + deny-by-default**. Real applications must add context-appropriate allowed classes. The snippet requires `import java.io.ObjectInputFilter;`.

## 16. Sound Design for Application Data

### When to Keep Sharing as Default

If multiple entities share **the same meaningful object** (for instance, a shared address/cache/config in the graph), default serialization restores the topology accurately. Use standard `writeObject` and ensure every object to be persisted in the graph has an appropriate representation.

### When You Need a Fresh Snapshot Version

If writing multiple consecutive snapshots of the same mutable object to **one `ObjectOutputStream`**, you need a refresh policy:

- Call `reset()` between snapshots if it is acceptable that the new object does not share identity with previous snapshots.
- Or build a new DTO/immutable snapshot for each write.
- Do not use `flush()` or `close()` as a way to ask the serializer to rewrite an object that already has a handle.

### When Avoiding Repeating the Entire Graph

If a graph is very large with many shared references, keeping handles can significantly reduce stream size. However, the handle table also retains state long-term in the stream; a very long-lived stream can consume more memory. You can reset at clear boundaries, accepting that data is re-serialized after reset.

### When Long-Term Persistence Is Required

Java native serialization depends on class format, serial UIDs, and compatibility rules. For multi-year persistence, cross-technology transfer, or strict schema control, consider a versioned, schema-independent format (such as JSON/CBOR/Protocol Buffers fitting the context), and explicitly model object IDs/references if sharing and cycles are needed.

## 17. Self-Check

1. Two fields point to the same object before writing. After default deserialization, is `field1 == field2`? **True.**
2. Two distinct objects have `equals() == true`. Does the serializer merge them automatically? **No.**
3. `A.next=B` and `B.next=A`. Why is there no infinite recursion? **The serializer assigns a handle before finishing writing fields and emits a back-reference when encountering A again.**
4. Is an object handle a Java memory address or a database ID? **No; it is a stream-scoped identifier.**
5. Call `writeObject(obj)` twice in the same stream without reset. What do two reads usually return? **The same deserialized instance via back-reference.**
6. Modify a field after the first write, then call `writeObject` again. Does it automatically send the new field? **No, if the second write is a back-reference.**
7. Does `ObjectOutputStream.reset()` erase already-written bytes? **No. It resets handle state and writes a reset marker.**
8. Is `ByteArrayOutputStream.reset()` the same as `ObjectOutputStream.reset()`? **No. One clears bytes in memory; the other resets serialization state.**
9. Does `writeUnshared(root)` guarantee all child objects are also unshared with the previous graph? **No; only the root at the call level.**
10. Is calling `readUnshared()` to read a back-reference valid? **No, it throws `ObjectStreamException`.**
11. Are `static` or `transient` fields saved by default serialization? **No.**
12. Should `ObjectInputStream` read arbitrary streams from the Internet? **No; source control, filters, and resource limits are required.**
13. Does `serialVersionUID` replace versioning/schema migration? **No.**
14. Using the same class across two different `ObjectOutputStream` instances—do they share a handle table? **No.**
15. Why is `original == restored` usually false even though the graph preserves identity? **Deserialization creates objects in a new graph; identity is only re-established among references within the read graph/stream.**

## 18. Official References

- [Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html): `writeObject`, `writeUnshared`, `reset`, and shared references.
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): `readObject`, `readUnshared`, graph restoration, serial filtering.
- [Java SE 17 — Java Object Serialization Specification: System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): handles, shared references, and cyclic references.
- [Java SE 17 — Object Output Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/output.html): handle assignment algorithm, reset, writeUnshared.
- [Java SE 17 — Object Input Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html): handle restoration, reset token, and readUnshared.
- [Java SE 17 — Stream Protocol](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/protocol.html): element format, `TC_REFERENCE`, `TC_RESET`, and class descriptors.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): limiting and filtering data during deserialization.