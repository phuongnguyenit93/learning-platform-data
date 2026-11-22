# ObjectOutputStream and ObjectInputStream in Java: Object Serialization and Restoration

## 1. What Is Serialization?

**Object serialization** is the process of converting a Java object graph into bytes according to the Java Object Serialization protocol. **Deserialization** is the process of reading those bytes back and restoring the objects along with their reference relationships following the protocol's rules.

Java Core I/O provides:

- `java.io.ObjectOutputStream`: writes an object graph, primitive values, and other values to an underlying `OutputStream`.
- `java.io.ObjectInputStream`: reads from an `InputStream` containing data in the Java Object Serialization format and reconstructs the object graph.
- `java.io.Serializable`: a marker interface (with no methods) indicating that a class can participate in the standard serialization mechanism.
- `java.io.Externalizable`: an interface for cases where a class takes responsibility for its own data format via `writeExternal`/`readExternal`, differing from default `Serializable`.

This lesson focuses on **`ObjectOutputStream` and `ObjectInputStream`**, how they combine with `Serializable`, class metadata, stream lifecycle, which fields are kept or omitted, error handling, version compatibility, and safety when reading external data.

> **Key point:** Java Object Serialization is a binary format for the Java ecosystem; it is **not** JSON, not simply writing `toString()` strings, not a snapshot of all JVM memory, and does not encrypt or authenticate data by default. Do not use `ObjectInputStream` to deserialize **untrusted** data without appropriate architecture, controls, and security policies; in many cases you should choose a safer data format.

## 2. Which Layers Does the Data Flow Through?

```text
WRITE                                            READ
-----                                            ----
Java object                                      Java object
    |                                                 ^
    v                                                 |
ObjectOutputStream.writeObject(obj)         ObjectInputStream.readObject()
    |                                                 ^
    v                                                 |
Bytes per Java serialization protocol       Parse stream + build object graph
    |                                                 ^
    v                                                 |
OutputStream                                    InputStream
    |                                                 ^
    +--> File / socket / memory ----------------------+
```

An application can combine these with `Files.newOutputStream(path)`, `FileOutputStream`, `BufferedOutputStream`, `ByteArrayOutputStream`, `Socket.getOutputStream()`, or other streams. Read using the corresponding input classes. **The underlying stream must carry the exact format expected by the reading side**.

Template example:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(file))) {
    out.writeObject(myObject);
}

try (ObjectInputStream in =
         new ObjectInputStream(Files.newInputStream(file))) {
    Object restored = in.readObject();
}
```

This is an **illustrative snippet inside a method**, not a standalone class: it requires `file`, `myObject`, appropriate imports, and handling of `IOException` / `ClassNotFoundException`. Using `try-with-resources` ensures streams are closed even when an error occurs.

## 3. Requirement: Classes Must Support `Serializable`

A class to be saved using the default mechanism typically implements `java.io.Serializable`:

```java
import java.io.Serializable;

public class Student implements Serializable {
    private static final long serialVersionUID = 1L;

    private String name;
    private int age;

    public Student(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

This is a class that can be compiled separately in `Student.java`. `Serializable` is a **marker interface**: no required methods need to be implemented. Java serialization uses an internal mechanism to write data for eligible, non-excluded fields.

### 3.1. Is Every Field Written?

Default rules for a `Serializable` class:

| Field kind | Written by default serialization? | Explanation |
| --- | --- | --- |
| Regular instance field (`int`, `String`, serializable object, etc.) | Yes | Writes values and referenced objects in the graph |
| `private` instance field | Yes | `private` **does not** prevent serialization |
| `final` instance field | Possibly yes | Value is saved/restored per protocol without relying on a setter |
| `static` | No | Belongs to the class/JVM, not per-instance state |
| `transient` | No in default form | On read back, receives default value unless custom logic handles it |
| Field referencing a non-serializable object | May cause `NotSerializableException` | Cannot save the whole graph via default mechanism when encountering a non-serializable object |

`transient` affects only the **default field-writing** mechanism; it does not guarantee secrets are wiped from RAM, nor does it guarantee the object won't be written via another field or custom `writeObject()` logic.

### 3.2. Serializable Applies to the Entire Object Graph

If `Order` implements `Serializable` but holds a `PaymentGateway gateway` field (non-serializable) that is not `transient`, `out.writeObject(order)` usually throws `NotSerializableException` upon reaching the `gateway` object.

Intentional ways to address this:

- Persist only necessary data; mark runtime dependencies such as connections, executors, logger state, or service clients as `transient`.
- Design serializable DTOs independent of service/runtime objects.
- Do not force a third-party library or class to be `Serializable` through arbitrary changes.
- If state must be kept in a stable format, consider JSON/CBOR/Protobuf or an appropriate schema instead of serializing domain objects directly.

An object graph can contain reference cycles and shared objects; Java serialization tracks the **identity of already-written objects** to emit corresponding references. That leads to an important behavior covered next.

## 4. Complete Java 17+ Example: Writing, Reading, and Preserving References

This example has two people sharing one `Address` object, writes the first person twice and the second person once. After writing, the program modifies a static field to prove **static is not included in serialized data**; the `transient` field is restored as `null`.

Create the file **`SerializationDemo.java`**:

```java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.nio.file.Files;
import java.nio.file.Path;

public class SerializationDemo {
    private static final class Address implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String city;

        private Address(String city) {
            this.city = city;
        }
    }

    private static final class Person implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private static String appVersion = "v1";

        private final String name;
        private final Address address;
        private transient String sessionToken;

        private Person(String name, Address address, String token) {
            this.name = name;
            this.address = address;
            this.sessionToken = token;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        Path file = Files.createTempFile("object-stream-", ".bin");

        try {
            Address shared = new Address("Ha Noi");
            Person an = new Person("An", shared, "secret-A");
            Person binh = new Person("Binh", shared, "secret-B");

            try (ObjectOutputStream out =
                    new ObjectOutputStream(Files.newOutputStream(file))) {
                out.writeObject(an);
                out.writeObject(an);   // Same identity written a second time.
                out.writeObject(binh); // Shares the same Address as an.
            }

            Person.appVersion = "v2";

            try (ObjectInputStream in =
                    new ObjectInputStream(Files.newInputStream(file))) {

                Person first = (Person) in.readObject();
                Person second = (Person) in.readObject();
                Person third = (Person) in.readObject();

                System.out.println("first: " + first.name
                        + " / " + first.address.city);
                System.out.println("same object twice: " + (first == second));
                System.out.println("shared address: "
                        + (first.address == third.address));
                System.out.println("transient token: " + first.sessionToken);
                System.out.println("static app version: " + Person.appVersion);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac SerializationDemo.java
java SerializationDemo
```

Output:

```text
first: An / Ha Noi
same object twice: true
shared address: true
transient token: null
static app version: v2
```

**Why does this output happen?**

1. Both `Person` and `Address` implement `Serializable`, so `ObjectOutputStream` can traverse the graph.
2. The first write of `an` includes `shared`. The second write of `an`, on the same stream, is normally represented as a **back-reference** to the previously written object rather than copying its fields again as an independent object.
3. `binh` is a different `Person` object whose `address` field points to the **same** `Address`; upon deserialization, `first.address == third.address` is `true`.
4. `sessionToken` is declared `transient`. The reader does not invoke the `Person(name,address,token)` constructor to assign a token; the reference field defaults to `null`.
5. `appVersion` belongs to the class, not an instance; changing its value in the JVM to `"v2"` before reading leaves the value `"v2"` after reading.

The `==` comparison in this example demonstrates **identity** within a single graph/stream; it does not mean two reads from **two different fresh streams** will yield the same object instance.

## 5. `ObjectOutputStream`: Key Operations

### `writeObject(Object)`

Writes an object according to the Java serialization protocol; if the object is `null`, a `null` marker can be written. If the graph contains a non-serializable object that is not properly excluded, it can throw `NotSerializableException`.

```java
out.writeObject(student);
out.writeObject(null);
```

This is an illustrative snippet assuming an already-opened `ObjectOutputStream out`.

### `writeInt`, `writeBoolean`, `writeUTF`, and `DataOutput`

`ObjectOutputStream` implements `ObjectOutput`, providing methods to write primitives and UTF strings:

```java
out.writeInt(2026);
out.writeBoolean(true);
out.writeUTF("Hello");
out.writeObject(student);
```

The reader **must read in the exact same order and matching types**:

```java
int year = in.readInt();
boolean flag = in.readBoolean();
String message = in.readUTF();
Student s = (Student) in.readObject();
```

Both snippets are illustrative code assuming both ends agree on format, stream, and compatible `Student` class. Writing with `writeInt` and reading with `readObject` violates the protocol; you may encounter `OptionalDataException`, `StreamCorruptedException`, or other errors depending on context.

`writeUTF`/`readUTF` use **modified UTF-8** and `DataOutput`/`DataInput`'s own length encoding, not raw headerless UTF-8. `writeUTF` limits the encoded representation of the string to 65,535 bytes and can throw `UTFDataFormatException`; do not use it for arbitrarily large text.

### `flush()`, `close()`

`flush()` pushes bytes currently buffered by the output stream down to the underlying stream per the `Flushable` contract; it **does not mean** data has been fsynced to durable storage or received on the network side.

`close()` closes `ObjectOutputStream` along with the underlying stream. For simple files, use `try-with-resources` to avoid truncated files caused by forgetting to close. If crash-safe durability is needed, separately apply flush/force at the file/channel layer and design an appropriate atomic write flow.

### `writeUnshared(Object)` and `reset()`

By default, `ObjectOutputStream` maintains an object handle table to preserve references. The `writeUnshared` and `reset` APIs alter how the stream handles object sharing, though they **should not be interpreted as a guaranteed "deep clone" for all child objects**.

- `writeUnshared(obj)` requests writing the root object as an unshared value per protocol rules; child objects referenced by the root can still be shared via the default mechanism.
- `reset()` clears the stream's reference table state so subsequently written objects do not emit back-references to earlier ones. A protocol-compliant reader also receives the corresponding reset marker.
- Do not call `reset()` arbitrarily while an object graph is actively being serialized; the API has rules and may throw `IOException`.

## 6. `ObjectInputStream`: Reading Data and Exceptions

Create an `ObjectInputStream` from a stream that already has a serialization header, then call `readObject()`:

```java
try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(file))) {
    Object value = in.readObject();
    if (value instanceof Student student) {
        System.out.println(student);
    } else {
        throw new IOException("Unexpected object type");
    }
}
```

This is an in-method example with variable `file` and class `Student` available; pattern matching for `instanceof` works in Java 17.

`readObject()` declares `IOException` and `ClassNotFoundException`. Before using the result, verify the **expected type**. However, checking `instanceof` **after** `readObject()` does not prevent malicious objects from participating in deserialization; safety controls must occur **before** calling `readObject()` and at the data-source design level.

### 6.1. Reading the Exact Number of Objects

If the writer wrote three objects, the reader should read exactly three objects, or use a custom protocol stating the count. Do not assume you can simply call `readObject()` indefinitely and get an automatic `null` sentinel at end-of-file.

Calling `readObject()` when no more valid data remains typically throws `EOFException`. Do not swallow every `IOException` and treat it as EOF: a corrupted stream or one truncated mid-object must be handled as a data error. You may choose `writeInt(count)` before a list of objects if the application controls the format, then read that exact count with a reasonable quota.

### 6.2. Headers and Two-Way Socket Synchronization

The `ObjectOutputStream` constructor writes a **serialization stream header**. The `ObjectInputStream` constructor needs to read and validate that header; if the stream is a socket and the peer has not yet written/flushed its header, creating the input stream can **block**.

If both peers create `ObjectInputStream` first, both can wait for each other indefinitely because neither has sent a header. In applications with a protocol trusted enough to use serialization, create the output stream first and **`flush()` the header**, then create the input stream:

```java
ObjectOutputStream out =
        new ObjectOutputStream(socket.getOutputStream());
out.flush(); // Allows peer to read the serialization header.
ObjectInputStream in =
        new ObjectInputStream(socket.getInputStream());
```

This is an illustrative snippet; `socket` is already connected and stream/channel ownership must be clearly managed. If you repeatedly create `new ObjectOutputStream` on the same socket midway without framing/a unified protocol, you may inject multiple headers into the stream and break the format the reader expects.

**Security note:** sending Java objects over sockets is appropriate only between **trusted, controlled** endpoints, and still requires authentication, resource limits, and class policies when reading objects; do not turn Object Serialization into a network protocol for untrusted clients.

## 7. Object Identity, Handle Tables, and the "Stale Data" Effect

A behavior that easily surprises developers: after the first `writeObject(obj)`, mutating fields on the **same instance** and calling `writeObject(obj)` a second time on the **same `ObjectOutputStream`** does not necessarily write the new values. The writer may simply emit a back-reference to the already-written object.

```java
MutableValue value = new MutableValue("old");
out.writeObject(value);

value.setText("new");
out.writeObject(value); // A back-reference may be written.
```

This is an in-method snippet (with a serializable `MutableValue` class and an open `out`). A reader reading twice may receive the **same object** still carrying the initial `"old"` value. This is not a random bug: the stream uses a reference/identity mechanism.

If your goal is to record independent snapshots over time, design **independent DTO/snapshot instances**, or consider `out.reset()` before rewriting when appropriate for the protocol. `reset()` can enlarge the stream because prior references are not reused; do not use it indiscriminately as a fix-all.

### 7.1. `readUnshared()` Is Not a General Clone Command

`ObjectInputStream.readUnshared()` has specific rules matching data written via unshared semantics; if a root turns out to be a back-reference in an invalid case, it can throw `ObjectStreamException`. Do not blindly use `readUnshared` to solve graph design problems. Business data may need DTO mapping with clear independent semantics.

## 8. `serialVersionUID` and Version Compatibility

`serialVersionUID` is the serialization version identifier of a `Serializable` class, of type `static final long`. It helps verify compatibility of the class descriptor when the reader restores data.

```java
@Serial
private static final long serialVersionUID = 1L;
```

This declaration goes inside a `Serializable` class, using `import java.io.Serial;` (this annotation has been available since Java 14). You can omit the UID, in which case Java computes a default value based on class structure; that approach **changes unexpectedly** when editing code and is unsuitable for data read across multiple versions.

| Change between writer and reader | Risk/impact |
| --- | --- |
| Changing `serialVersionUID` | Usually `InvalidClassException` due to identifier mismatch |
| Adding a regular instance field | May be compatible in default serialization; new field receives default value when reading old stream |
| Removing an instance field | May be compatible; old field in stream is ignored if absent in reader class |
| Changing field type, class hierarchy, or semantics | May be incompatible, causing errors or restoring invalid business data |
| Renaming class/package | Class name in stream no longer resolves directly, potentially `ClassNotFoundException` |
| Removing `Serializable` or changing serialization mechanism | May make old streams unreadable |

**Keeping the same UID does not make every change compatible.** It only participates in version checking; you must still test reading older data versions, validate invariants, and handle defaulted fields.

For example, if `age` is a newly added field, a reader of the new class reading an old stream may receive `age=0` without running a constructor to set `age=18`. If `0` is invalid in business logic, include a post-read validation/migration step.

Serialization does not replace schema migration mechanisms in a long-lived store. For data maintained over many years, explicit formats and versioned DTOs are usually better than serialized domain objects.

## 9. Constructors, `transient`, and Default Values

A common point of confusion: when deserializing a `Serializable` object, Java **does not invoke that serializable class's normal constructor** to populate serialized fields. Fields are restored per protocol. The no-argument constructor of the **first superclass not implementing `Serializable`** must satisfy serialization's accessibility rules and will be called while initializing the non-serializable superclass portion.

Consequences:

- Invariant checks in a serializable class's constructor **must not be relied upon** as a guard for incoming read data.
- A `transient String token` field usually restores as `null` without additional logic.
- A `transient int counter` field usually restores as `0`.
- `static` is not loaded from the stream; it belongs to the running class state in the JVM.
- Normal `final` fields can be populated from default serialized state rather than by running a constructor on read.

You must design safe post-read reinitialization for runtime resources like executors, sockets, non-serializable locks, or caches. Hook mechanisms like `private void readObject(ObjectInputStream in)` and `private void writeObject(ObjectOutputStream out)` are advanced, carry specific contracts, and can introduce risks if validated carelessly; hooks are unnecessary for simple DTO storage.

## 10. Class-Level Serialization Customization

If a `Serializable` class needs control over how its fields are written/read, it can declare private methods with prescribed signatures:

```java
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    // Additional data can be written in a format decided by the class.
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Validate and restore invariants from the read data.
}
```

These are **two illustrative methods that must be placed inside a `Serializable` class** along with `java.io.*` imports. When used, writer and reader must agree on the extra schema; anything extra written must be read in the exact same order and format. Never invoke custom `readObject` manually from outside.

`defaultWriteObject()` and `defaultReadObject()` are valid only inside their respective serialization callback contexts. Do not call them as general-purpose object read/write APIs.

### 10.1. Validating Invariants After Reading

If business rules require `balance >= 0`, the class can verify that condition after `defaultReadObject` and throw `InvalidObjectException` when invalid. Remember that deserialization **may bypass the constructor** that checks data. For untrusted data, validating after object construction is **not sufficient** to prevent deserialization gadgets or runtime-level attacks.

### 10.2. `readObjectNoData`, `readResolve`, `writeReplace`

Java has advanced hooks for handling missing class data in a stream, replacing objects, or maintaining certain object identity patterns. These hooks affect graphs/references and lifecycles, so use them only when you thoroughly understand the API contract and have tests. Do not add them to DTOs merely to "optimize" without a real requirement.

## 11. Safety: Never Deserialize Untrusted Bytes

**Object deserialization carries special risks** because restoration can load classes and trigger code in custom serialization hooks (such as `readObject`, `readResolve`, `Externalizable.readExternal`) or gadget chains from libraries on the classpath. Simply casting the object after `readObject()` **cannot prevent** actions that already happened beforehand.

Therefore:

1. **Ideally, do not use Java native object serialization for data sent by untrusted users or over the Internet.** Choose formats with clear schemas, bounded parsers, and data validation (JSON, CBOR, Protobuf, etc.) where appropriate.
2. If a legacy system must accept serialized objects, combine source verification (authentication/integrity), updated libraries, process isolation, an **object deserialization filter**, limits on depth/references/arrays/bytes, and class allowlisting.
3. Never rely on a rule that merely blocklists a few dangerous class names: allowlisting permitted domain classes is generally easier to audit.
4. Never expose an `ObjectInputStream` endpoint directly to the Internet just because the protocol is easy to code; this is a high-risk pattern.
5. Filters help **reduce attack surface**; they do not guarantee elimination of all gadgets, side effects, application behaviors, or library vulnerabilities.

### 11.1. `ObjectInputFilter` in Java 17+

Java 17 supports `java.io.ObjectInputFilter` to enforce controls during deserialization. An **illustrative** pattern-based filter example:

```java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

// Run before the first readObject() call.
// "com.example.dto.*" is the package of the DTO classes in the illustrative app.
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=100;maxbytes=1048576;maxarray=10000;"
      + "com.example.dto.*;!*");
in.setObjectInputFilter(filter);
```

This is a **configuration snippet**, assuming `ObjectInputStream in` is already created. Replace `com.example.dto.*` with **the real classes that must be permitted** and test thoroughly against valid object graphs; classes outside the allowlist may cause legitimate data to be rejected. The filter should not be interpreted as thoroughly inspecting every byte/string/primitive, nor does it replace schema/business validation. The `!*` directive (written without extra trailing spaces inside the pattern string) sets a policy rejecting classes not matched by earlier allow patterns.

You can configure a JVM-wide filter or use a filter factory depending on the environment. What matters is applying the policy **before deserialization**, consistently across entry points, and testing against your actual JDK/library versions. Do not write a filter just to "pass tests" and end up allowing every class with wildcard `*`.

### 11.2. Limiting File Size and Object Counts

Object serialization contains graph/metadata information allowing deeply nested objects, huge arrays, and deep reference graphs. Limiting only file length is insufficient: you must limit depth, reference counts, array sizes, byte counts, and processing time, plus aggregate quotas across concurrent requests.

When storing to files, use restrictive file permissions, integrity checks as needed, restrict user-supplied paths, and do not assume a local file is "trusted" if multiple actors can modify it.

### 11.3. Do Not Confuse `transient` with Security

`transient` is useful for omitting a field from default serialization, but it **does not encrypt**, does not wipe copies elsewhere in the graph, does not stop custom logic from writing that field, and does not control where the byte stream is stored. Secrets should be kept out of serializable objects; if sensitive state must be persisted, use proper encryption/authentication and key management at the appropriate layer.

## 12. Stream Lifecycle Management and Performance

### 12.1. Should You Wrap with Buffered Streams?

You can wrap with `BufferedInputStream`/`BufferedOutputStream` when it makes sense for the data source, though it does not always yield dramatic gains. For example:

```java
try (ObjectOutputStream out = new ObjectOutputStream(
        new BufferedOutputStream(Files.newOutputStream(file)))) {
    out.writeObject(data);
}
```

This is an illustrative snippet inside a method; import `java.io.*` and `java.nio.file.*`, with `file` and `data` supplied by the application. Closing the outer stream closes the underlying stream down the wrapper chain. Do not close the underlying stream prematurely while `ObjectOutputStream` still needs to write.

### 12.2. Do Not Repeatedly Open New Streams on the Same File to Append

`ObjectOutputStream` writes a **stream header** upon creation. Reopening an `ObjectOutputStream` in append mode and writing more objects to a file already containing serialized data inserts extra headers in the middle and causes a standard `ObjectInputStream` to throw `StreamCorruptedException`.

Append scenarios require a purpose-built format/protocol or continuous stream management; do not simply add `StandardOpenOption.APPEND` and expect the reader to parse multiple stream headers automatically.

### 12.3. Memory Leaks When Writing Very Many Objects

The handle table in `ObjectOutputStream` retains references to objects that have appeared in the stream. For a long-lived stream continuously writing many new objects, this table can grow and increase memory pressure. Consider snapshot batching, sensible stream rotation, or `reset()` at object boundaries **if the protocol permits**, noting that resetting drops sharing across before/after regions and can increase stream size.

### 12.4. Default Serialization Is Not Optimal for RPC

Java serialization embeds class names and metadata in the stream, depends on the classpath and serial UID, is difficult to interoperate with other languages, and carries higher security risk than bounded schema formats. For service communication and long-lived storage, versioned schemas and explicit protocols are usually preferable.

## 13. Common Exceptions and How to Distinguish Them

| Exception | Common cause | How to handle |
| --- | --- | --- |
| `NotSerializableException` | Object in graph is not `Serializable` | Persist only valid DTOs or exclude runtime fields |
| `InvalidClassException` | Local class incompatible with serialized descriptor, mismatched `serialVersionUID` | Define schema/migration; do not just force the UID |
| `ClassNotFoundException` | Class named in stream is missing/not found on reader | Check classpath, version, package; avoid trusting class names from untrusted sources |
| `StreamCorruptedException` | Wrong stream header/type codes or data violates serialization protocol | Check format, append behavior, socket stream alignment |
| `EOFException` | Reading past available data or stream was truncated | Distinguish expected EOF from truncated objects |
| `OptionalDataException` | Reading an object when primitive/block-data or different format state is present | Match order of `writeInt`/`readInt`, `writeObject`/`readObject` |
| `InvalidObjectException` | Object was read but violated invariants checked during read validation | Handle as invalid data |
| `WriteAbortedException` | Object write aborted due to a prior error and reader hit exception record | Inspect root-cause exception and stream integrity |
| `IOException` | General file/socket/stream error | Close streams properly and do not masquerade as EOF |
| `ClassCastException` | Casting returned object to the wrong type | Verify type and data contract |

If the reader reports `StreamCorruptedException: invalid stream header`, do not blindly try to "fix" it by skipping initial bytes: verify that the byte stream genuinely uses the Java serialization format and contains exactly one header for the active stream.

## 14. Comparison with Other Data-Writing Approaches

| API/approach | Best suited for | Difference from Java Object Serialization |
| --- | --- | --- |
| `DataOutputStream`/`DataInputStream` | Primitives and custom binary protocols | Does not automatically write class metadata/object graphs; application manages order/schema |
| `ObjectOutputStream`/`ObjectInputStream` | Java object graphs between trusted endpoints in the same ecosystem | Writes class descriptors, reference handles, requires `Serializable`, carries deserialization risk |
| `BufferedWriter`/`BufferedReader` | Plain text | Explicit charset/line format, does not serialize objects automatically |
| JSON + suitable library | Data exchanged across services and different languages | More explicit schema and validation; libraries still require safe configuration |
| Protobuf/Avro or schema-based binary | Versioned RPC/events/storage | Explicit schema IDs/versions and field mapping; does not preserve Java object identity by default |
| JDBC/ORM | Persisting business state in a database | Provides transactions, queries, constraints; not a full Java graph snapshot |

Even when a class implements `Serializable`, it does not automatically become a durable storage format or stable API contract. Serialization is **a technical mechanism**, not a substitute for data modeling.

## 15. Common Mistakes

1. **Forgetting `implements Serializable` on an object in the graph:** throws `NotSerializableException`.
2. **Thinking `private` fields are skipped:** `private` instance fields are still written; use `transient` intentionally.
3. **Omitting `serialVersionUID`:** class edits can generate a different default UID, breaking compatibility.
4. **Only changing the UID to "fix" `InvalidClassException`:** does not resolve semantic or structural mismatches.
5. **Assuming deserialization runs the normal constructor:** invariants may not be initialized as expected.
6. **Mutating an object's field and calling `writeObject` again on the same stream:** the writer may only emit an old handle reference.
7. **Reading `writeInt`/`writeObject` in the wrong order:** the stream parser loses format alignment.
8. **Creating `ObjectInputStream` on both socket ends before output:** both wait for the serialization header, deadlocking the socket.
9. **Opening a new `ObjectOutputStream` to append:** inserts extra stream headers mid-file, which standard readers cannot parse properly.
10. **Treating EOF as a safe object-stream terminator:** streams can be truncated; use an explicit count protocol and error recovery.
11. **Using `transient` as encryption:** data is not secured by this keyword alone.
12. **Deserializing bytes from the Internet without filters/schemas:** exposes security gadget and resource exhaustion risks.
13. **Calling `readObject()` and then casting to "filter classes":** dangerous classes may already be deserialized before the cast runs.
14. **Closing the underlying stream before the outer stream:** can leave data unflushed or partially written.
15. **Serializing objects holding sockets, connections, or executors:** runtime state is usually non-serializable or cannot restore properly.
16. **Assuming the stream always captures object mutations across writes:** the handle table and `reset` have specific semantics.

## 16. Self-Check Questions

**Question 1.** A class implements `Serializable` and has a non-`transient` field referencing a non-serializable object. Why can `writeObject()` fail?

**Answer:** Writing the object graph must traverse that field. When the target object is not serializable and has no valid replacement mechanism, `NotSerializableException` can be thrown.

**Question 2.** What does `transient String token` default to after deserialization?

**Answer:** `null`, unless the class has custom logic to restore it. `transient` does not wipe the token from RAM or remove copies stored in other fields.

**Question 3.** Two fields point to the same `Address` before serialization; after reading the graph, must they become two separate copies?

**Answer:** No. Standard Java Object Serialization tracks object identity; both fields can point to the same restored instance.

**Question 4.** On the same `ObjectOutputStream`, you call `writeObject(obj)`, mutate a field, and call `writeObject(obj)` again. Is the reader guaranteed to see the new field value?

**Answer:** No. The second write may emit a back-reference instead of new state. Design proper snapshots and use `reset()` or independent instances as appropriate.

**Question 5.** If `serialVersionUID=1L` is kept unchanged, are all class changes guaranteed to read older data?

**Answer:** No. The UID is only one component of compatibility checking; it does not guarantee that field type, inheritance, or invariant changes remain compatible.

**Question 6.** Can a reader call `readObject()` instead of `readInt()` to retrieve an integer previously written with `writeInt()`?

**Answer:** No; it must read using the exact matching format and order.

**Question 7.** Why can two socket endpoints deadlock if both create `ObjectInputStream` before creating output streams?

**Answer:** The `ObjectInputStream` constructor waits for the stream header, yet neither side has written/flushed a header.

**Question 8.** Is checking `instanceof TrustedDto` after `readObject()` enough to stop malicious deserialization?

**Answer:** No. The graph may already have been constructed and hooks may already have executed. Avoid deserializing untrusted input or apply filters, quotas, isolation, and proper schema design.

**Question 9.** Is a class's `static int counter` restored to the value the writer had?

**Answer:** Not by default. Static state is managed by the class in the reading JVM.

**Question 10.** Can Java Object Serialization be used as a shared data format between Java and Python without additional specifications?

**Answer:** It is not a suitable choice. It is a Java-specific format; choosing a language-independent protocol/schema is simpler and more sustainable.

## 17. Implementation Checklist

- **Data scope:** serialize only truly needed DTOs/object graphs; avoid service/runtime state.
- **Class compatibility:** define `serialVersionUID` intentionally and test data across versions.
- **Field semantics:** distinguish instance, static, transient, shared references, and object identity.
- **I/O:** close streams with `try-with-resources`; match `writeObject` and `readObject` order.
- **Protocol:** if sending multiple objects, define counts, types, ordering, and stream lifecycle; handle EOF/truncated data separately.
- **Snapshots:** do not assume rewriting the same object emits fresh field values; pay attention to the handle table and `reset()`.
- **Security:** never read object streams from untrusted sources; for legacy systems that must use them, apply `ObjectInputFilter`, allowlists, quotas, integrity/authentication, updated dependencies, and isolation.
- **Memory:** bound object counts, graph depth, arrays, and stream sizes; avoid persisting huge unnecessary object graphs.
- **Error handling:** explicitly handle `ClassNotFoundException`, `InvalidClassException`, `NotSerializableException`, `EOFException`, and `IOException`.
- **Technology choice:** consider JSON/Protobuf/versioned schema formats for cross-JVM communication, long-term storage, or untrusted clients.

## Official Documentation

- Java SE 17 — `ObjectOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html
- Java SE 17 — `ObjectInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html
- Java SE 17 — `Serializable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Java SE 17 — `ObjectInputFilter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html
- Java Object Serialization Specification: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html
- JEP 290 — Filter Incoming Serialization Data: https://openjdk.org/jeps/290
- JEP 415 — Context-Specific Deserialization Filters: https://openjdk.org/jeps/415
