# Re-writing Mutated Objects, reset, and Handle Caching

## 1. The Problem: Mutating an Object Yet Receiving Stale Data

When using Java Object Serialization, the first `ObjectOutputStream.writeObject(x)` call writes the object's state and assigns a **handle** (a stream-scoped reference identifier). If you later mutate a field on **the same instance** and call `writeObject(x)` again, the stream normally writes only a **back-reference** to the old handle. `ObjectInputStream.readObject()` on the receiving side then returns the exact same instance read the first time, carrying the old state.

This is a feature for preserving **object graph** topology, not a buffering bug. If two fields reference the same object, the reader must recreate `a.ref == b.ref`. If a graph has a cycle A → B → A, the handle table prevents infinite traversal.

Key distinctions:

- `writeObject(x)`: if the object has not been written yet, writes its definition; if it **already has a handle**, may emit a reference.
- `reset()`: creates a new boundary in the serialization stream, discarding state about previously written objects; subsequent writes serialize graphs anew.
- `writeUnshared(x)`: forces writing the **root object** of that call anew, though child objects that already have handles are not necessarily refreshed.
- `flush()`: pushes encoded bytes down to the underlying output; it **does not** clear handles.

Do not use `serialVersionUID` to track object mutations: the UID serves class compatibility, not per-object content versioning.

## 2. How the Handle Table Works

```text
Writer, same ObjectOutputStream:
    writeObject(x)  -> Object definition + handle H
    writeObject(x)  -> Reference to H

Reader, same ObjectInputStream:
    readObject()    -> Create object y, store H -> y
    readObject()    -> Return the exact same y
```

The handle table is **per stream instance**, not a JVM-wide global cache; object identity (`==`) differs from content equality (`equals()`). Two distinct objects with identical field values are still written independently.

For instance, an `Account` is written once with `balance=10`; afterward, in the sending JVM, it is mutated to `balance=20`. If the second write emits only a handle reference, the second read does not automatically become `20`. **`ObjectOutputStream` does not watch field mutations and does not compute deltas.**

The encoded data covers the **entire graph of eligible fields**, excluding `transient`, `static`, or customized serialization cases. A field holding a non-`Serializable` object can trigger `NotSerializableException`. The handle table also tracks encountered child objects and class descriptors; this matters for `reset`, `writeUnshared`, and long-lived streams.

## 3. Java 17 Example: Write Old, Reset, Then Write New

Create file `SerializationHandleDemo.java`:

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

Compile and run with Java 17 or newer:

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
3. The second `writeObject` emits a handle reference; `b` is the exact same object as `a`, with `text="before"`.
4. `out.reset()` writes a **reset marker** and clears the writer's known-objects table. The reader sees that marker and resets its own handle table too.
5. The third write encodes the object anew with `text="after"`. `c` has a different identity from `b`.

You do not need to create a new `ObjectInputStream` after `reset()`; the existing reader understands the protocol marker. Nor does `reset` erase objects the reader code already holds in variables `a` or `b`.

## 4. What `reset()` Does and Does Not Do

Signature: `public void reset() throws IOException`.

- Discards stream handle state for previously written objects; objects written after the marker are treated as unseen within the current **epoch**.
- Writes a reset token into the stream, coordinating with the matching `ObjectInputStream` state.
- Suitable for multiple **independent** snapshots of the same mutable graph when the reader must observe updated state.
- Can help bound memory retained by long-lived streams, at the cost of increased byte volume because objects and class descriptors must be re-encoded.

**What it does NOT do:** erase earlier bytes in a file, truncate, re-write objects without calling `writeObject` after reset, protect a snapshot from concurrent field mutations on another thread, confirm storage sync, or execute a transaction.

Never call `reset()` **while an object is actively being serialized**, such as inside a custom `private void writeObject(ObjectOutputStream out)` of the object being written. That invalid call can throw `IOException`. Call `reset` **between** complete graph writes.

Comparison:

| Call | Effect |
| --- | --- |
| `writeObject(x)` | Writes definition or back-reference. |
| `reset()` | Marks a new epoch; forgets all current object handles. |
| `flush()` | Pushes pending bytes; **does not refresh handles**. |
| `writeUnshared(x)` | Writes root `x` anew; nested graph may still reuse old handles. |
| `close()` | Closes stream/resource, not a mid-protocol reset. |
| `FileChannel.force(...)` | Requests syncing storage data; unrelated to handles. |

An operational bug is creating `new ObjectOutputStream(sameOutput)` repeatedly onto **the same continuous stream** while the receiver still uses a single `ObjectInputStream`. The stream constructor writes a new header; an unexpected header mid-stream causes `StreamCorruptedException`. For multiple snapshots on one stream, use one writer with `reset()`; for separate streams, use explicit framing and separate readers.

## 5. writeUnshared: New Root Yet Old Nested Objects

`writeUnshared(root)` suppresses emitting a back-reference for **the root** of that specific call, yet already-written child objects may still be referenced via handles. Therefore, it is **not a deep copy**, nor does it guarantee a snapshot of the whole graph with the latest field values.

Create file `WriteUnsharedDemo.java`:

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

The first write stores root `Wrapper` and child `Item`. After mutating root to `"two"` and child to `"blue"`, `writeUnshared(w)` writes a **new root**, yet the child still points back to the old `Item` with `"red"`. The subsequent `writeObject(w)` call still references the original root (`a==c`). To re-write the current state of the whole graph, `reset(); writeObject(w)` is much clearer.

`ObjectInputStream.readUnshared()` is not a "better" drop-in replacement for `readObject()`: if the entry read is a **back-reference**, `readUnshared` throws `ObjectStreamException`. Class mechanisms like `readResolve` and special object types can create further identity exceptions; do not assume all nested references are cloned.

## 6. Reset Intervals and Memory

A long-lived stream writing many distinct new objects causes the writer and reader handle tables to grow, adding overhead and retaining references. You can place boundaries between batches:

```java
// Illustrative snippet; out and makeMessage(i) are defined by the application.
for (int i = 0; i < 10_000; i++) {
    out.writeObject(makeMessage(i));
    if ((i + 1) % 1_000 == 0) out.reset();
}
```

The threshold `1_000` is illustrative; choose based on graph size, heap, throughput, identity requirements, and real benchmarks. Resetting **too frequently** forces many bytes to be re-serialized, hurting performance. Resetting **too rarely** lets handle state bloat. If the receiver needs to identify an entity across multiple snapshots, pass a **business ID/version**; do not rely on Java object handles staying constant.

## 7. Consistent Snapshots and Practical Applications

Handle caching is only half the problem. If another thread mutates the graph **during** serialization, the stream can capture an inconsistent combination of fields. `Serializable` does not imply automatic thread safety, and `reset` does not turn a write into a transaction.

Solutions to consider:

- Build an immutable DTO snapshot inside a lock or business transaction, then serialize the snapshot.
- Assign **a single owner** to `ObjectOutputStream`, coordinating producers through a queue; avoid interleaving `writeObject`, `reset`, and `flush` across threads.
- Define explicit versions/sequences when streaming objects continuously. `ObjectOutputStream` does not generate deltas or application acknowledgements.
- Handle `IOException`, EOF, and stream corruption; do not assume the peer processed a message just because local `writeObject` returned.
- If data must survive power loss, `flush`/`reset` do not replace file syncing and recovery protocols.
- Avoid arbitrarily deserializing untrusted data. If forced to do so, restrict permitted classes and cap depth/bytes/references with `ObjectInputFilter`, using a protocol with clear contracts.

When long-term storage, cross-language interoperability, or frequent schema evolution is needed, DTOs with formats like JSON/CBOR/Protobuf or a database are often more appropriate than native Java Serialization.

## 8. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Mutate `x` and call `writeObject(x)` again | Reader sees stale state | Call `reset` before a fresh snapshot or send separate objects/versions |
| Call `flush()` expecting fields to update | Handle table is unchanged | Distinguish byte buffering from object identity |
| Use `writeUnshared` as a deep copy | Nested fields remain stale | Use `reset` + `writeObject` for a fresh graph |
| Use `readUnshared` on a back-reference | `ObjectStreamException` | Align writer/reader contracts |
| Call `reset` inside custom `writeObject` | `IOException` | Reset between full graphs |
| Create multiple writers sequentially on one stream | Mid-stream header corruption | One writer + `reset`, or independent streams |
| Forget to reset long-lived streams | Memory pressure | Choose measured batch/epoch intervals |
| Reset excessively without reason | Increased size and encoding CPU | Tune policy to workload |
| Use `serialVersionUID` as an object version | Does not track instance mutations | Use business version/sequence fields |
| Serialize a graph while another thread mutates it | Torn/inconsistent snapshot | Immutable DTOs, ownership, synchronization |
| Treat `reset` as flushing to disk | Wrong durability assumption | Use proper storage sync/transactions |

## 9. Self-Check

**Why might a second `writeObject` omit mutated fields?** Because the root already has a handle, the writer may emit only a back-reference.

**Can two `readObject()` calls return the exact same object?** Yes, when the subsequent read reads a back-reference.

**Does `reset` erase prior bytes or strip references already held by the reader?** No; `reset` changes handle lookup state for the **subsequent portion of the stream**, without deleting objects already held by application variables.

**Does `reset` refresh the entire graph?** It clears the stream's handle state, so the graph in the next `writeObject` is processed anew, barring concurrent mutation races or custom hook intervention.

**Does `writeUnshared(root)` deep-copy the graph?** No. Only the root is fresh; child objects can still be referenced via prior handles.

**When should you avoid native Java Serialization?** When input is untrusted or when storage/communication requires durability, cross-language support, and easy versioning.

## Official Documentation

- [Java SE 21 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html)
- [Java SE 21 — ObjectInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html)
- [Java Object Serialization Specification — Output](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/output.html)
- [Java Object Serialization Specification — Input](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/input.html)
- [Java SE 21 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)

**Conclusion:** `ObjectOutputStream` remembers **the identity of written objects**, without tracking state changes automatically. `reset` starts a new epoch to re-write the object graph; `writeUnshared` guarantees only a fresh root; `flush` does not alter the handle cache.
