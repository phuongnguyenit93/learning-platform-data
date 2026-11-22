# Rewriting Mutated Objects, reset, and Handle Caching

## 1. The Problem: Mutating an Object Yet Receiving Old Data

When using Java Object Serialization, the first `ObjectOutputStream.writeObject(x)` call typically writes the object's state and assigns a **handle** (a stream-scoped reference identifier). If you later mutate a field of the **same instance** and call `writeObject(x)` again, the stream normally writes only a **back-reference** to the old handle. `ObjectInputStream.readObject()` on the receiving side can return the exact same instance read the first time, with its old state.

This is a feature that preserves **object graph** structure, not a buffering bug. If two fields reference one object, the reader must recreate `a.ref == b.ref`. If a graph contains a cycle A → B → A, the handles table prevents infinite traversal.

Key distinctions:

- `writeObject(x)`: if the object has not been written yet, writes its definition; if it **already has a handle**, may write a reference.
- `reset()`: creates a new boundary in the serialization stream, discarding state about previously written objects; subsequent writes serialize graphs anew.
- `writeUnshared(x)`: forces writing a fresh **root object** for that call, yet does not necessarily refresh child objects that already have handles.
- `flush()`: pushes encoded bytes to the underlying output; **does not** clear handles.

Do not use `serialVersionUID` to track object mutation: UID serves class compatibility, not per-object content versioning.

## 2. The Handles Table Mechanism

```text
Writer, same ObjectOutputStream:
    writeObject(x)  -> Object definition + handle H
    writeObject(x)  -> Reference to H

Reader, same ObjectInputStream:
    readObject()    -> Create object y, store H -> y
    readObject()    -> Return the same y
```

The handle table is **per stream instance**, not a JVM-wide global cache; object identity (`==`) differs from content equality (`equals()`). Two distinct objects with identical fields can still be written independently.

For example, an `Account` is written once with `balance=10`; afterward in the sending JVM it is modified to `balance=20`. If the second write emits only a handle reference, the second read does not automatically become 20. **`ObjectOutputStream` does not watch field changes and does not automatically generate deltas.**

What gets encoded is the **entire graph of eligible fields**, excluding `transient`, `static`, or custom-serialized cases. A field holding a non-`Serializable` object can trigger `NotSerializableException`. The handles table also remembers encountered child objects and class descriptors; that matters for `reset`, `writeUnshared`, and long-lived streams.

## 3. Java 17 Example: Write Old, Reset, Then Write New

Create `SerializationHandleDemo.java`:

```java
import java.io.*;

public class SerializationHandleDemo {
  static class Message implements Serializable {
    private static final long serialVersionUID = 1L;
    String text;
    Message(String text) { this.text = text; }
  }
  public static void main(String[] args) throws Exception {
    Message message = new Message("before");
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
      out.writeObject(message);
      message.text = "after";
      out.writeObject(message);
      out.reset();
      out.writeObject(message);
    }
    try (ObjectInputStream in = new ObjectInputStream(
        new ByteArrayInputStream(bytes.toByteArray()))) {
      Message a = (Message) in.readObject();
      Message b = (Message) in.readObject();
      Message c = (Message) in.readObject();
      System.out.println("values=" + a.text + "," + b.text + "," + c.text);
      System.out.println("a==b=" + (a == b));
      System.out.println("b==c=" + (b == c));
    }
  }
}
```

Compile/run with Java 17 or later:

```bash
javac --release 17 SerializationHandleDemo.java
java SerializationHandleDemo
```

Verified output:

```text
values=before,before,after
a==b=true
b==c=false
```

Explanation:

1. The first `writeObject` encodes `Message{text="before"}` and creates a handle.
2. Assigning `message.text="after"` mutates the object **in sender memory**, without modifying already-written bytes.
3. The second `writeObject` writes a reference to the handle; `b` is the same object as `a`, with `text="before"`.
4. `out.reset()` writes a **reset marker** and clears the writer's known objects table. The reader sees that marker and resets its own handles table too.
5. The third write encodes the object anew with `text="after"`. `c` has a different identity from `b`.

You do not need to create a new `ObjectInputStream` after `reset()`; the existing reader understands the marker in the serialization protocol. `reset` also does not erase objects that reader code already holds in variables `a` or `b`.

## 4. What Does `reset()` Do and Not Do?

Signature: `public void reset() throws IOException`.

- Discards the stream's handles state for previously written objects; objects after the marker are treated as never written in the current **epoch**.
- Writes a reset token to the stream, coordinating with the corresponding `ObjectInputStream` state.
- Suitable for multiple **independent** snapshots of the same mutable graph when the reader needs to see updated state.
- Can help bound the state remembered by a long-lived stream, at the expense of larger output because objects/class descriptors must be re-encoded.

**Does not:** erase prior bytes in a file, truncate, rewrite an object without calling `writeObject` after reset, protect snapshots against concurrent field mutations from other threads, confirm storage sync, or execute transactions.

Never call `reset()` **while serializing an object is in progress**, such as inside custom `private void writeObject(ObjectOutputStream out)` of the object being written. That invalid call can throw `IOException`. Reset **between** complete graph writes.

Comparison:

| Call | Effect |
| --- | --- |
| `writeObject(x)` | Writes definition or back-reference. |
| `reset()` | Marks a new epoch; forgets all current object handles. |
| `flush()` | Pushes pending bytes; **does not refresh handles**. |
| `writeUnshared(x)` | Writes root `x` anew; nested graph may keep using old handles. |
| `close()` | Closes the stream/resource, not a mid-protocol reset. |
| `FileChannel.force(...)` | Requests syncing storage data; unrelated to handles. |

An operational bug is creating `new ObjectOutputStream(sameOutput)` multiple times onto the **same continuous stream** while the receiver still uses a single `ObjectInputStream`. The stream constructor writes a new header; a sudden header mid-data can cause `StreamCorruptedException`. For multiple snapshots on one stream, use one writer plus `reset()`; for separate streams, use explicit framing/separate readers.

## 5. `writeUnshared`: Fresh Root Yet Old Nested Objects

`writeUnshared(root)` does not emit a back-reference for the **root** of that call itself, yet already-written child objects can still be referenced via handles. Therefore, it is **not a deep copy**, nor does it guarantee a snapshot of the entire graph reflects the latest fields.

Create `WriteUnsharedDemo.java`:

```java
import java.io.*;

public class WriteUnsharedDemo {
  static class Item implements Serializable {
    private static final long serialVersionUID = 1L;
    String value;
    Item(String value) { this.value = value; }
  }
  static class Wrapper implements Serializable {
    private static final long serialVersionUID = 1L;
    String label;
    Item item;
    Wrapper(String label, Item item) { this.label=label; this.item=item; }
  }
  public static void main(String[] args) throws Exception {
    Wrapper w = new Wrapper("one", new Item("red"));
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
      out.writeObject(w);
      w.label="two";
      w.item.value="blue";
      out.writeUnshared(w);
      out.writeObject(w);
    }
    try (ObjectInputStream in = new ObjectInputStream(
        new ByteArrayInputStream(bytes.toByteArray()))) {
      Wrapper a=(Wrapper)in.readObject();
      Wrapper b=(Wrapper)in.readUnshared();
      Wrapper c=(Wrapper)in.readObject();
      System.out.println("labels="+a.label+","+b.label+","+c.label);
      System.out.println("nested="+a.item.value+","+b.item.value);
      System.out.println("a==b="+(a==b));
      System.out.println("a==c="+(a==c));
      System.out.println("nested-shared="+(a.item==b.item));
    }
  }
}
```

```bash
javac --release 17 WriteUnsharedDemo.java
java WriteUnsharedDemo
```

Verified output:

```text
labels=one,two,one
nested=red,red
a==b=false
a==c=true
nested-shared=true
```

The first write stores root `Wrapper` and child `Item`. After mutating root to "two" and child to "blue", `writeUnshared(w)` writes a **new root**, yet the child can still point back to the old `Item` with "red." The next `writeObject(w)` can still reference the initial root (`a==c`). To write the entire current graph anew, `reset(); writeObject(w)` is much clearer.

`ObjectInputStream.readUnshared()` is not a "better" version of `readObject()`: if the entry being read is a **back-reference**, `readUnshared` throws `ObjectStreamException`. Class mechanisms like `readResolve` and special types can create further identity exceptions; do not assume all nested references are cloned.

## 6. Reset Cadence and Memory

A long-lived stream writing many new objects can grow the writer/reader handle tables, causing overhead and retaining references. You can place boundaries between batches:

```java
// Illustrative snippet; out and makeMessage(i) are defined by the application.
for (int i = 0; i < 10_000; i++) {
    out.writeObject(makeMessage(i));
    if ((i + 1) % 1_000 == 0) out.reset();
}
```

The threshold of 1,000 is illustrative only; choose based on graph size, heap, throughput, identity requirements, and real benchmarks. Resetting **too often** causes many bytes to be re-serialized, potentially hurting performance. Resetting **too rarely** lets handle state bloat. If the receiver needs to identify an entity across multiple snapshots, pass a **business ID/version**; do not rely on Java object handles staying constant.

## 7. Consistent Snapshots and Practical Applications

Handle caching is only part of the problem. If another thread mutates the graph **during** serialization, the stream can contain an invalid combination of fields. `Serializable` does not imply automatic thread-safety, and `reset` does not turn a write into a transaction.

Solutions to consider:

- Build an immutable DTO snapshot inside a lock or business transaction, then serialize the snapshot.
- Use a **single owner** for `ObjectOutputStream`, coordinating producers via a queue; avoid interleaving `writeObject`, `reset`, and `flush` across multiple threads.
- Define explicit versions/sequences when streaming objects continuously. `ObjectOutputStream` does not generate deltas or application acknowledgements.
- Handle `IOException`, EOF, and stream corruption; never assume a peer succeeded just because a local `writeObject` call returned.
- If data must survive power loss, `flush/reset` do not replace file syncing and recovery protocols.
- Avoid deserializing untrusted data arbitrarily. When required, restrict allowed classes and cap depth/bytes/references with `ObjectInputFilter`, using a protocol with an explicit contract.

For long-term storage, cross-language compatibility, or frequent schema upgrades, DTOs with formats like JSON/CBOR/Protobuf or databases are often better suited than native Java Serialization.

## 8. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Mutate `x` then call `writeObject(x)` again | Reader sees old state | Reset before a new snapshot or send a separate object/version |
| Call `flush()` to refresh fields | Handle table does not change | Distinguish byte buffering from object identity |
| Use `writeUnshared` as a deep copy | Nested fields stay stale | `reset + writeObject` for a fresh graph |
| Use `readUnshared` on a back-reference | `ObjectStreamException` | Match writer/reader contracts |
| Call `reset` inside custom `writeObject` | `IOException` | Reset between graphs |
| Create multiple writers continuously on one stream | Stream headers appear mid-stream | One writer + reset, or independent streams |
| Forget to reset on a long-lived stream | Memory pressure | Choose measured batch/epoch boundaries |
| Reset constantly without reason | Increases size and encoding work | Pick policy by workload |
| Use `serialVersionUID` as an object version | Does not track mutations | Use business version/sequence |
| Serialize a graph mutated concurrently by other threads | Inconsistent snapshot | Immutable DTO, single ownership, synchronization |
| Treat reset as flushing to disk | Wrong durability expectations | Appropriate storage sync/transactions |

## 9. Self-Check

**Why might a second `writeObject` not write modified fields?** Because the root already has a handle, so the writer may send only a back-reference.

**Can two `readObject()` calls return the same object?** Yes, if the later call reads a back-reference.

**Does reset erase old bytes or make the reader lose previous references?** No; reset changes the handle lookup state for the **subsequent stream segment**, without deleting objects the application already holds.

**Does reset refresh the entire graph?** It clears the stream's handles state, so the graph in the next `writeObject` is processed anew, provided no concurrent mutation/race or custom hook interferes.

**Does `writeUnshared(root)` deep-copy the graph?** No. Only the root is fresh; children can still be referenced from existing handles.

**When should native Java Serialization be avoided?** When input data is untrusted or when a durable, cross-language, easily versioned storage/communication format is required.

## Official Documentation

- [Java SE 21 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html)
- [Java SE 21 — ObjectInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html)
- [Java Object Serialization Specification — Output](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/output.html)
- [Java Object Serialization Specification — Input](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/input.html)
- [Java SE 21 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)

**Conclusion:** `ObjectOutputStream` remembers the **identity of already-written objects**, without tracking state mutations. `reset` starts a new epoch to rewrite object graphs; `writeUnshared` guarantees only a fresh root; `flush` does not affect the handle cache.