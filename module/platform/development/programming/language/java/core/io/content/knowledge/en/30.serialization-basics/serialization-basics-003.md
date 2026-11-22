# writeObject, readObject, and Stream Format in Java Object Serialization

## 1. From Objects in Memory to a Byte Stream

**Java Object Serialization** is the mechanism that converts the state of a Java object and the objects reachable through its reference fields into **a structured byte stream**; the reverse process restores an object graph from that stream.

Two common entry points:

- `ObjectOutputStream.writeObject(obj)`: writes the serialized representation of the object to an `OutputStream`.
- `ObjectInputStream.readObject()`: reads the **next object** in the stream, restores data/reference relationships, and returns an `Object`.

These two methods do not convert objects into JSON or plain text. The result is the **binary Java Object Serialization Stream Protocol format**, consisting of a header, type tags, class descriptors, field values, object references, and additional data when needed.

```text
Java Object                      BINARY STREAM                     Java Object
Message("HELLO", 7) ──writeObject──▶ AC ED 00 05 ... ──readObject──▶ Message("HELLO", 7)
                                ▲                   │
                        ObjectOutputStream     ObjectInputStream
                                │                   │
                           OutputStream          InputStream
```

Lesson goal: use `writeObject`/`readObject` properly; understand what is saved into the stream and how to read it back in the exact order; distinguish object data from the stream header/class descriptors; recognize handles/reference sharing, `serialVersionUID`, `transient`, exceptions, and the security risks of `readObject` on untrusted data.

**Important security note:** never assume that bytes received over a network, files downloaded externally, or user-submitted blobs are safe to pass into `ObjectInputStream`. Java deserialization can trigger object restoration mechanisms and callbacks on the classpath; prefer safer data protocols or apply strict limits/controls when it must be used.

## 2. Classes and Interfaces to Know

| Component | Role |
|---|---|
| `java.io.Serializable` | Marker interface indicating a class permits default Java serialization |
| `ObjectOutputStream` | Writes objects and primitive data into an Object Serialization Stream |
| `ObjectInputStream` | Reads objects and primitives according to the same stream rules |
| `ObjectStreamConstants` | Magic header, version, and protocol marker bytes (`TC_*`) |
| `ObjectStreamClass` | Describes a serializable class; can inspect `serialVersionUID` and field descriptors |
| `serialVersionUID` | Version identifier used for class compatibility checking during deserialization |
| `transient` | Excludes an instance field from default persistence |
| `ObjectInputFilter` | Mechanism to filter/limit classes, depth, references, arrays, and bytes when reading |
| `Externalizable` | Mode where a class defines its entire write/read behavior using `writeExternal`/`readExternal` |

At a basic level, a class implementing `Serializable` is enough for the default mechanism to write eligible fields:

```java
import java.io.Serializable;

public final class Student implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String name;
    private final int age;

    public Student(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

This is a standalone compilable class in `Student.java`, **without `main`**. Because `String` is serializable and `int` is a primitive, the state of this `Student` instance can be serialized by the default mechanism. `serialVersionUID` here is a `static final long` field meant for class version checking, **not** instance data written as a regular field.

### 2.1. Serializable Is Not a Method to Override

`Serializable` is a **marker interface**: it does not declare `serialize()` or `deserialize()`. Therefore:

```java
class Entry implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    int number = 42;
}
```

already meets the basic requirement for object serialization. You are **not required** to override `writeObject`/`readObject` in every class; the `ObjectOutputStream` API executes the default mechanism.

If a field references a non-serializable object, writing the entire graph can throw `NotSerializableException`, even though the root class implements `Serializable`.

## 3. Creating ObjectOutputStream and Writing Objects

An `ObjectOutputStream` wraps any `OutputStream` such as `FileOutputStream`, `ByteArrayOutputStream`, or a socket stream:

```java
try (ObjectOutputStream out =
        new ObjectOutputStream(
                new FileOutputStream("student.bin"))) {

    out.writeObject(new Student("Mai", 20));
}
```

This is an illustrative snippet inside a method handling `IOException` with the `Student` class already defined. Requires importing `java.io.ObjectOutputStream`, `java.io.FileOutputStream`.

Workflow:

1. Create `ObjectOutputStream`. The constructor **writes the stream header** to the underlying output.
2. Call `writeObject(obj)` to persist the object.
3. The encoder traverses the object graph reachable through serializable fields, writing class descriptors and necessary values.
4. The stream maintains a **handles** table to recognize references already written in the current stream.
5. When closing `ObjectOutputStream`, the underlying stream is also closed; use `try-with-resources` to prevent resource leaks.

You can write multiple objects **consecutively** to the same `ObjectOutputStream`, and then read them back in the exact same order. You should not create a new `ObjectOutputStream` each time you append an object to the same file and expect a single `ObjectInputStream` to treat every consecutive header as a simple list of objects.

### 3.1. `writeObject` Can Write an Entire Graph

Suppose:

```java
final class Address implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String city = "Ha Noi";
}
final class Person implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    Address address = new Address();
}
```

The two classes are illustrative code placed at top level in a Java file (non-`public`) or an equivalent valid location. When calling `out.writeObject(new Person())`, the `Address` object referenced through the `address` field is also written, **without needing** a separate `writeObject(address)` call.

If `Address` does not support serialization and the `address` field is not transient, writing `Person` can fail with `NotSerializableException`. This mechanism does not automatically accept every object in the graph.

### 3.2. Writing Primitives and Objects in the Same Stream

`ObjectOutputStream` also implements `DataOutput`:

```java
out.writeInt(7);
out.writeUTF("xin chao");
out.writeObject(student);
```

This is a snippet in a scope where `out` and `student` are already declared. The reading side must follow the **exact same order**:

```java
int version = in.readInt();
String title = in.readUTF();
Student student = (Student) in.readObject();
```

`readObject()` **cannot** be used in place of `readInt()` to receive a primitive written with `writeInt()`. Mismatched data sequences and read types can cause `OptionalDataException`, `StreamCorruptedException`, or other errors depending on the stream state. Note that `writeUTF` uses the *modified UTF-8* format from `DataOutput`, not standard UTF-8 encoding for arbitrary text bytes.

## 4. ObjectInputStream and How to Read Objects

Example reading back the file that was written:

```java
try (ObjectInputStream in =
        new ObjectInputStream(
                new FileInputStream("student.bin"))) {

    Object value = in.readObject();
    Student student = (Student) value;
}
```

This is a snippet inside a method declaring or handling `IOException` and `ClassNotFoundException`, with a compatible `Student` class on the classpath. `readObject()` has static return type `Object` because input data can represent many different classes; Java cannot rely on generics to guarantee the returned class.

**Steps when reading:**

1. The `ObjectInputStream` constructor reads and validates the stream header.
2. `readObject` reads type tags and descriptors, decoding the object graph with matching classes in the JVM.
3. For a default Serializable class, instance state is restored according to field serialization rules.
4. The stream maintains a handles table on the reading side so that repeated/cyclic references are built into the appropriate relationships.
5. The caller must check the type and **verify business validity** of the restored object; a valid Java type does not mean the values are always trustworthy.

`ObjectInputStream` must be used with data that actually follows the Java Object Serialization Stream Protocol. An arbitrary JSON, ZIP, or UTF-8 file cannot naturally be read with `ObjectInputStream`.

### 4.1. Constructor May Block Waiting for the Header When Reading from a Socket

`new ObjectInputStream(input)` **can block waiting for header bytes**. If both sides of a socket create `ObjectInputStream` and wait for the header before either side creates/flushes `ObjectOutputStream`, the program can **deadlock**.

The exchange pattern between both sides must be designed accordingly:

```java
ObjectOutputStream out = new ObjectOutputStream(socket.getOutputStream());
out.flush(); // Push the header.
ObjectInputStream in = new ObjectInputStream(socket.getInputStream());
```

This is a snippet with a valid `socket`; it is not a complete TCP program. `flush()` gives the header bytes generated by the output stream a chance to reach the other side, but both sides must still agree on setup order, message protocol, timeouts, and socket lifecycle.

## 5. Complete Java 17+ Example: Header, Repeated References, Reset, and Transient

The following example uses `ByteArrayOutputStream`/`ByteArrayInputStream` to avoid filesystem dependencies. It verifies the most important aspects of `writeObject` and `readObject`: the binary header; the same object written twice; `reset()` creating a new handle table boundary; and a `transient` field excluded from default state.

**File:** `ObjectStreamDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class ObjectStreamDemo {

    private static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;

        final String text;
        final int sequence;
        transient String secret;

        Message(String text, int sequence, String secret) {
            this.text = text;
            this.sequence = sequence;
            this.secret = secret;
        }
    }

    public static void main(String[] args) throws Exception {
        Message original = new Message("Xin chao", 7, "TOKEN");
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
            out.writeObject(original);
            out.writeObject(original); // Handle table: this instance has already been written.
            out.reset();              // Clear remembered handles.
            out.writeObject(original); // Write a new object representation.
        }

        byte[] wire = sink.toByteArray();
        System.out.printf(
                "header: %02X %02X %02X %02X%n",
                wire[0] & 0xFF,
                wire[1] & 0xFF,
                wire[2] & 0xFF,
                wire[3] & 0xFF);

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(wire))) {

            Message first = (Message) in.readObject();
            Message second = (Message) in.readObject();
            Message third = (Message) in.readObject();

            System.out.println("text: " + first.text
                    + ", sequence: " + first.sequence);
            System.out.println("first==second: " + (first == second));
            System.out.println("first==third: " + (first == third));
            System.out.println("transient restored: " + first.secret);
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac ObjectStreamDemo.java
java ObjectStreamDemo
```

**Exact stdout of the example:**

```text
header: AC ED 00 05
text: Xin chao, sequence: 7
first==second: true
first==third: false
transient restored: null
```

**Why does it produce this result?**

1. A default Java serialization stream starts with magic `AC ED` and version `00 05`, meaning `STREAM_MAGIC=0xACED` and `STREAM_VERSION=5`.
2. The first `writeObject(original)` stores class and object information; the second call on the **same instance** within the **same handle table** uses a reference to the already-written object. Therefore, the first two `readObject` calls return the **same instance** on the reading side (`== true`).
3. `out.reset()` clears the stream's handles state per contract and writes a reset token. The third write produces a new representation; the reading side also resets its context, so the third object has a **different reference** (`== false`).
4. The `secret` field is declared `transient`, so the default mechanism **does not store the value `"TOKEN"`**. After deserialization, the reference field has the default value `null`.
5. `text` and `sequence` are restored because they are ordinary serializable instance fields, the class is compatible, and the data is valid.

The code has been compiled and verified on the JDK. The source file in the example uses ASCII text so that output remains stable even on terminals without Unicode support; the lesson does not imply Java serialization only handles ASCII.

## 6. Object Serialization Stream Protocol Format

### 6.1. Stream Header: `AC ED 00 05`

A stream produced by `ObjectOutputStream` typically has this high-level structure:

```text
+------------------------------+
| STREAM_MAGIC                 | 2 bytes: AC ED
+------------------------------+
| STREAM_VERSION               | 2 bytes: 00 05
+------------------------------+
| Contents                     |
| - object/string/array tokens |
| - class descriptors          |
| - primitive / block data     |
| - reference handles          |
| - optional custom data       |
+------------------------------+
```

`ObjectInputStream` uses this header to recognize the format. If the first four bytes are incorrect, the constructor can throw `StreamCorruptedException`, for example when you accidentally use it to read a text or JSON file.

**Do not confuse:** "version 5" in the stream header is the **stream protocol version**, not Java 5, not JDK 17/21, and not the class's `serialVersionUID`. A stream still has version 5 even when the application is compiled with a modern JDK.

### 6.2. Main Type Tags

The tokens are defined in `ObjectStreamConstants`; when inspecting hex, you can recognize:

| Token | Hex value | General meaning |
|---|---|---|
| `TC_NULL` | `70` | Null reference |
| `TC_REFERENCE` | `71` | Reference to an object/descriptor that already has a handle |
| `TC_CLASSDESC` | `72` | New class descriptor |
| `TC_OBJECT` | `73` | New object instance |
| `TC_STRING` | `74` | New String |
| `TC_ARRAY` | `75` | New array |
| `TC_CLASS` | `76` | Class object |
| `TC_BLOCKDATA` | `77` | Short primitive/optional data block |
| `TC_ENDBLOCKDATA` | `78` | End of an optional block data section |
| `TC_RESET` | `79` | Reset context/handles |
| `TC_BLOCKDATALONG` | `7A` | Long data block |
| `TC_EXCEPTION` | `7B` | Exception information in the protocol |
| `TC_LONGSTRING` | `7C` | Long String |
| `TC_PROXYCLASSDESC` | `7D` | Descriptor for a proxy class |
| `TC_ENUM` | `7E` | Enum constant |

These are **markers in a structured protocol**, not "every byte equal to `73` in a file is a new object." A byte with value `73` can appear **inside a payload or class name**; a parser must read according to grammar, length, and context rather than scanning for arbitrary bytes.

### 6.3. What Does a Class Descriptor Contain?

When encountering a serializable class for the first time in a stream, a descriptor can contain:

- The binary name of the class.
- `serialVersionUID`.
- Flags representing how the class is serialized.
- The list of persisted fields with their names and types.
- Superclass description and optional custom data parts if present.

For example, for `Message` above, the descriptor describes the persisted fields such as `sequence` and `text`; the `secret` field is excluded because it is `transient`. This is only a logical description, **not** a complete hex byte layout for all JDKs/class paths. The actual byte stream also contains nested class names, handles, string descriptors, annotations, and other protocol parts.

**Do not write raw stream bytes by hand** unless you are building a parser/encoder strictly compliant with the Java Object Serialization Specification. `writeObject`/`readObject` are designed to handle descriptors, reference graphs, block data, and class matching for you.

### 6.4. Object Handles Preserve Reference Identity

Java serialization is not simply "dump every field on each call." It maintains a handle table to:

- Avoid repeating an entire already-written object when encountering the **same reference** again.
- Preserve relationships where fields point to the same object after reading.
- Reconstruct graphs with **cycles** (cyclic references) without infinite recursion.
- Allow sharing instances after deserialization within the corresponding stream context.

In the protocol, handles are assigned starting from base value `0x7E0000` per spec, and the `TC_REFERENCE` token points to an assigned handle. Do not use handle numbers as stable business IDs; they are internal data of a single stream.

**Cyclic graph example**:

```java
final class Node implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    Node next;
}

Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;

out.writeObject(a);
```

This is a snippet inside a method with `ObjectOutputStream out`; the two `Node` instances are written using handles for the back-reference. Reading back `Node restored = (Node) in.readObject()` from the corresponding stream preserves the relationship `restored.next.next == restored`, provided classes are compatible and no custom replacement breaks the structure.

### 6.5. Repeated `writeObject` on the Same Reference Does Not Mean a New Snapshot

```java
Entry entry = new Entry();
entry.number = 1;
out.writeObject(entry);

entry.number = 2;
out.writeObject(entry); // Usually only writes a reference to the already-seen instance.
```

This is a snippet with `Entry` as the Serializable class above and `out` open. The second read **does not necessarily** yield `number=2`; for an object already recorded in the handle table, the stream uses a handle to the same object serialized the first time. Use `out.reset()` between the two writes if you truly need to write the object's current state again, and understand that reset affects the stream's entire handle table.

## 7. `reset()`, `writeUnshared()`, and `readUnshared()`

### 7.1. When to Use `ObjectOutputStream.reset()`?

`reset()` instructs `ObjectOutputStream` to discard remembered handles; objects written subsequently will have a new reference context. It also places a `TC_RESET` marker in the stream so `ObjectInputStream` stays synchronized.

```java
out.writeObject(state);
out.reset();
out.writeObject(state);
```

This is illustrative code when `out` is open and `state` is Serializable. There are two implications:

1. You can send a **new snapshot** of the same instance when data has mutated between two writes.
2. You can reduce the number of object references accumulated in the handle table of a long-running stream, at the cost of re-writing descriptors/objects after reset.

Do not call `reset()` from inside an ongoing `writeObject` serializing an object graph; the API does not allow resetting mid-graph and may throw `IOException`. Perform it at **boundaries between complete writes**.

### 7.2. Are `writeUnshared` and `readUnshared` a Deep Copy?

No. `writeUnshared(obj)` has special semantics regarding how the **base-level object** is treated as unshared; `readUnshared()` requires the input to meet the corresponding unshared conditions. However, they **do not guarantee a deep copy of the entire object graph**, because objects referenced in child fields can still be shared according to the protocol.

Therefore, if the goal is to create a **completely independent copy**, Java serialization is not the implicit answer. You need a copy process with explicit ownership and policy. Do not use `writeUnshared` assuming all reference aliases in child objects have been eliminated.

## 8. Which Fields Are Serialized?

With default Serializable behavior, **non-static and non-transient instance fields** are the fields processed by the serialization mechanism, within the limits of class hierarchy and declarations.

| Field kind | Included in default serialized state? | Example |
|---|---|---|
| `private int count` | Yes | Primitive value 7 |
| `private String name` | Yes | Reference to a Serializable String |
| `private Address address` | Yes if the corresponding object graph is serializable | Another object graph |
| `private transient String password` | No | Usually null after deserialization |
| `private static int total` | No | Field belongs to class/JVM, not instance |
| `private static final long serialVersionUID` | Not an instance field; used in descriptor | Compatibility check |
| Field referencing a non-Serializable object | Writing can fail if not excluded/changed | `NotSerializableException` |

### 8.1. `transient` Is Not Encryption or Secure Erasure

A field marked `transient` is not persisted **by the default mechanism**. It does not automatically:

- Erase values currently existing in RAM.
- Prevent a custom `writeObject` from actively writing that value via another call.
- Prevent sensitive information from leaking through other fields in the graph.
- Encrypt the written data.

Example:

```java
class Account implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String owner;
    transient String sessionToken;
}
```

If the caller sets `sessionToken="abc"` and serializes using the default mechanism, that value is absent from `Account`'s serialized fields. However, another object holding the same token in a **non-transient** field can still cause the token to appear in the stream. Do not treat Java serialization as a secret store or a secure format for credentials.

### 8.2. Distinguishing Normal Constructors from Deserialization

For a regular serializable class, deserialization **does not invoke the constructor of the serializable class itself** the way normal `new` initialization does. Fields are restored by the serialization mechanism; the no-argument constructor of the **first non-Serializable superclass** is invoked according to the corresponding rules.

This has consequences:

- Invariants established only in the serializable class's constructor may not run during restoration.
- Transient fields receive default values (unless code actively restores them), and are not automatically assigned values by that class's constructor.
- You cannot rely on constructors to guard every object created by deserialization.
- For critical data, validation and source control are required; a `readObject` hook can check invariants itself, which is also why deserializing untrusted data is dangerous.

## 9. `serialVersionUID` and Compatibility Between Class Versions

### 9.1. Why Does Java Check serialVersionUID?

When serializing, class information in the stream is tagged with `serialVersionUID`. When deserializing, Java checks whether the corresponding class in the JVM has an allowed version to restore this stream.

```java
public final class UserProfile implements java.io.Serializable {
    private static final long serialVersionUID = 3L;
    private String displayName;
}
```

This is a standalone compilable class `UserProfile.java`. If a class implementing `Serializable` **does not declare** `serialVersionUID`, Java computes a default value based on class details per the specification. That default value can change when you edit the class definition; therefore, you should declare it explicitly to manage compatibility policy rather than relying on implicit calculation.

If the stream and local class have mismatched `serialVersionUID` values, a common error is `InvalidClassException`:

```text
java.io.InvalidClassException: ... local class incompatible:
stream classdesc serialVersionUID = ..., local class serialVersionUID = ...
```

This is an **illustrative** error message format, not fixed stdout. It occurs when class metadata in the stream is incompatible under version checking.

### 9.2. The Same serialVersionUID Is Not Enough to Guarantee Every Class Change Is Compatible

Keeping the same `serialVersionUID` can support **certain changes** to fields. However, it does not mean you can:

- Arbitrarily change a field's type.
- Switch a class from `Serializable` to `Externalizable` without changing the contract.
- Alter class hierarchy or structure in incompatible ways.
- Delete/rename a class without having the corresponding class available at read time.
- Freely change a custom `writeObject`/`readObject` format without versioning.

Class evolution rules are defined in the *Java Object Serialization Specification – Versioning of Serializable Objects*. When files must be stored for years or passed across releases, version data at the application layer, test real compatibility with sample files from older versions, and consider using an explicit-schema data format.

### 9.3. Inspecting serialVersionUID Yourself with ObjectStreamClass

```java
long uid = java.io.ObjectStreamClass
        .lookup(UserProfile.class)
        .getSerialVersionUID();
System.out.println(uid);
```

This is a snippet when the `UserProfile` class above is available. The printed value is `3`, independent of any specific `UserProfile` instance. `ObjectStreamClass.lookup` is for serializable classes; do not assume every kind of class has a useful descriptor.

## 10. Customizing Data with Private `writeObject` and `readObject` in a Class

Do not confuse:

- `out.writeObject(obj)`: the **public** method on `ObjectOutputStream`, called by the caller to serialize an object.
- `private void writeObject(ObjectOutputStream out)`: a **special hook inside the Serializable class itself**, recognized by the serialization runtime by signature.
- `private void readObject(ObjectInputStream in)`: custom restoration hook inside the Serializable class itself.

If a class needs additional structured data or invariant checks during restoration, it can declare:

```java
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class PositiveCount implements Serializable {
    private static final long serialVersionUID = 1L;

    private int count;

    public PositiveCount(int count) {
        if (count < 0) {
            throw new IllegalArgumentException("negative count");
        }
        this.count = count;
    }

    private void writeObject(ObjectOutputStream out)
            throws IOException {
        out.defaultWriteObject();
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();

        if (count < 0) {
            throw new InvalidObjectException("negative count");
        }
    }
}
```

This is a **compilable class** (`PositiveCount.java`) without `main`/stdout. `defaultWriteObject()` writes the fields selected by the class's default mechanism; `defaultReadObject()` restores them. Then `readObject` verifies `count >= 0` because the constructor of a serializable class is not guaranteed to be called during deserialization.

### 10.1. Customizing the Stream Format Requires Discipline

If the `writeObject` hook writes extra data:

```java
out.defaultWriteObject();
out.writeInt(42);
```

then the corresponding `readObject` hook must consume it in the exact same order:

```java
in.defaultReadObject();
int extra = in.readInt();
```

The two snippets above are inside their respective hooks, not standalone programs. With custom serialization, Java provides optional data/block data in the protocol. To maintain cross-version compatibility, explicit versioning is needed—do not arbitrarily change the order or number of custom fields without compatible reading logic.

These hooks do not bypass type checks, security filters, or the `ObjectInputStream` contract. Besides `writeObject`/`readObject`, `writeReplace`/`readResolve` can substitute objects during serialization/deserialization; those are advanced tools and also increase risk when reading untrusted data.

### 10.2. `Externalizable` Does Not Follow the Default Path

`Externalizable` extends `Serializable` and requires the class to define `writeExternal(ObjectOutput)` / `readExternal(ObjectInput)`. With `Externalizable`, the class actively takes responsibility for writing/reading the object's contents, with its own constructor requirements (including a public no-argument constructor) upon restoration.

Do not treat `Externalizable` as merely "`Serializable` with one extra method." It changes responsibilities for formatting, versioning, and data validity, so use it only when fine-grained structural control is needed and compatibility tests are in place.

## 11. Streams Contain Primitive Block Data and Are Not JSON

In a hex file, you can see headers, tokens, and data blocks interleaved. For example:

```java
ByteArrayOutputStream buffer = new ByteArrayOutputStream();

try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
    out.writeInt(42);
    out.writeObject("hello");
}
```

This is an illustrative snippet inside a method handling `IOException`, with appropriate imports. In the stream, `writeInt(42)` is represented via `ObjectOutputStream`'s **block data** mechanism, followed by the serialized `String`. You **cannot** read the first 4 bytes of the file and assume they are the number `42`, because the first four bytes are the `AC ED 00 05` header.

### 11.1. The Stream Format Is Structural, Not a JVM Memory Dump

Serialization records a **logical object graph** per the specification rather than copying raw memory addresses/pointers from the JVM.

- An object's memory address in a process is not preserved when reading from a stream.
- References between objects are represented using corresponding handles.
- Data depends on the serializable class schema and custom hooks, not HotSpot's fixed memory layout.
- Another process/JVM can deserialize when compatible classes are available, yet that **does not** make the object safe if bytes come from an untrusted source.
- This stream cannot be used as a language-independent exchange standard the way JSON or Protocol Buffers are designed.

### 11.2. Not All Field Values Are Repeated on Every writeObject

In a stream maintaining a handle table, Java may write `TC_REFERENCE` instead of re-serializing an object. Therefore, the byte size produced after each `writeObject` depends on stream history, object graph, `reset` calls, and hooks—not merely `toString()` or the current field count.

If you want to measure serialized byte size:

```java
ByteArrayOutputStream sink = new ByteArrayOutputStream();
try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
    out.writeObject(obj);
}
int byteCount = sink.toByteArray().length;
```

This is a snippet with a serializable `obj` and the corresponding classes imported. The resulting `byteCount` is the number of bytes **written for the object and stream overhead**, including header/descriptors; it is not the object's heap memory size.

## 12. Common Errors and Exceptions

| Exception | When encountered | How to handle |
|---|---|---|
| `NotSerializableException` | The graph contains an object of a non-serializable class | Only serialize DTOs designed for this purpose; use `transient` when appropriate |
| `InvalidClassException` | Stream/local class incompatible, often differing UID or violated serialization constraints | Manage `serialVersionUID` and test schema/versioning |
| `StreamCorruptedException` | Header/control bytes violate the protocol, or stream is corrupted | Check source/format; avoid mixing multiple headers |
| `ClassNotFoundException` | JVM cannot find the class needed for reconstruction | Ensure classpath/modules; avoid storage coupled to unstable classes |
| `EOFException` | Not enough bytes remain to continue reading as requested | Manage framing/counts; avoid relying on EOF for all structural logic |
| `OptionalDataException` | Reading an object at a primitive data position or special optional data cases | Read in the same order and format as the writing side |
| `InvalidObjectException` | Validation hook actively reports invalid object state | Check schema and data; do not ignore the error |
| `IOException` | File/socket/stream has an I/O failure | Close stream, report error; do not treat partial bytes written/read as complete |
| `ClassCastException` | Casting a read object to an expected class of the wrong type | Check instance/type, filters, schema |

**Do not try to keep reading an `ObjectInputStream` that has hit a serious serialization error and assume the offset is still valid.** The Java API may leave the stream in an indeterminate state. When corrupted or untrusted data is detected, generally close the stream, report the error, and perform application-level recovery rather than trying to find the next token in the byte array.

### 12.1. `NotSerializableException` Example

```java
final class NotSerializableHelper {
    int value = 10;
}
final class Container implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    NotSerializableHelper helper = new NotSerializableHelper();
}
```

These are two illustrative classes. `out.writeObject(new Container())` will fail because `helper` points to a class that does not implement `Serializable`/`Externalizable`. Changing the field to `transient` is only appropriate if that state is not needed in the restored data; do not "fix" it by dropping important data without designing a rebuild mechanism.

### 12.2. Do Not Use `toString()` to Verify Bytes or Identity

When reading an object, `System.out.println(obj)` may print a readable string if the class overrides `toString()`, or an identity hash string if not. It does not prove the object graph was restored accurately. For testing, compare specific fields, reference identity when needed, invariants, and application behavior; use `==` when testing reference sharing as in the `ObjectStreamDemo` example.

## 13. Security Risks of `readObject`

Java Object Deserialization is warned against in JDK documentation as **dangerous if data comes from an untrusted source**. When reading, the runtime can load classes, instantiate objects via special mechanisms, and trigger hooks/deserialization logic in classes present on the classpath. An adversary-controlled byte sequence can attempt to create a deeply nested object graph, huge arrays, or dangerous class/hook gadget chains.

**Priority principles:**

1. Do not accept Java serialized object streams directly from the Internet/untrusted users when JSON/CBOR/Protocol Buffers with clear schemas/validation can be used.
2. If you must use it, **restrict allowed classes** and related resources using `ObjectInputFilter`, a system/deployment-policy filter factory, and classpath control.
3. Enforce a total byte size limit before reading if the protocol allows; apply timeouts/limits at the transport layer.
4. After deserialization, still verify object type, structure, required fields, and business invariants.
5. Keep the JDK/libraries updated and avoid putting unnecessary classes on the classpath of the deserializing process.
6. Do not rely on `instanceof` **after** reading as the sole defense, because object creation/restoration steps have already run inside `readObject()`.

### 13.1. `ObjectInputFilter` and Limits

In modern Java versions, `ObjectInputStream` can use a filter to inspect classes, array lengths, graph depth, reference counts, and bytes consumed. **Illustrative** policy example:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=128;maxarray=1024;maxbytes=65536;"
      + "com.example.dto.*;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter); // Must be before readObject().
    Object value = in.readObject();
    // Continue validating type/schema/invariants.
}
```

This is an **illustrative snippet**, not a standalone program: it requires importing `ObjectInputFilter`, `ObjectInputStream`; `source` is an `InputStream`; the caller handles `IOException`/`ClassNotFoundException`. `com.example.dto.*` must be replaced with the actual classes permitted by the application architecture; valid container types, arrays, or dependent classes also need corresponding policy checks. The trailing `!*` blocks classes not on the allowlist. Certain string/primitive values have exceptions in how the filter is invoked, so the filter **is not a content validator**.

`setObjectInputFilter` is called **once** before reading objects; it is not a configuration to swap back and forth per item after the stream has started reading. There is also JVM-wide policy via filter factories/JVM properties; how they combine is defined by the JDK and actual configuration requirements.

**Filters reduce risk but do not guarantee the stream is "safe."** Treat deserialization from untrusted sources as a security boundary, apply defense in depth, and prefer formats designed for data exchange.

### 13.2. Do Not Log/Deserialize Unchecked Bytes Just to See What They Are

An antipattern:

```java
Object object = new ObjectInputStream(untrustedInput).readObject();
// Only check which class the object belongs to afterward.
```

This is **unsafe** illustrative code and should not be used with untrusted data. The risk lies **during deserialization**, before your code checks the returned object's class. Use schema-driven parsing and limit bytes/class graphs before accepting content.

## 14. Persisting Objects to Files and Data Durability

### 14.1. `flush()` Does Not Mean `fsync`

`out.flush()` pushes buffered data down to the underlying `OutputStream`; `out.close()` closes the stream and handles flushing per contract. Neither **automatically guarantees** that data is durably persisted across a power loss on every filesystem.

```java
try (FileOutputStream file = new FileOutputStream("state.bin");
     ObjectOutputStream out = new ObjectOutputStream(file)) {

    out.writeObject(state);
    out.flush();
    file.getFD().sync(); // Request file descriptor sync per contract.
}
```

This is an illustrative snippet in a method with a Serializable `state`, importing `FileOutputStream`/`ObjectOutputStream`. `FileDescriptor.sync()` requests syncing file contents via the descriptor; it has overhead and device/provider-dependent constraints. If an application needs atomic state file updates, write to a temporary file and publish via rename with appropriate filesystem durability requirements—**calling `writeObject` does not automatically provide durability**.

### 14.2. Reading Long-Term Stored Files Does Not Always Succeed

An `ObjectOutputStream` may produce valid bytes in the current application version, but after a few years:

- Packages/classes have been renamed.
- `serialVersionUID` differs.
- Some fields/classes in the object graph have disappeared.
- A new deserialization filter policy rejects old classes.
- The new class has different invariants and no longer accepts old data.

Therefore, Java serialization is generally suitable when **both writer and reader live within a tightly managed Java ecosystem** and version compatibility is tested; it is not the default choice for persisting business data that needs a stable schema across years or deployment generations.

## 15. Read/Write Order and Protocol Framing

Suppose the writer does:

```java
out.writeObject(user);
out.writeObject(order);
out.writeInt(2026);
```

Correct reading side:

```java
User user = (User) in.readObject();
Order order = (Order) in.readObject();
int year = in.readInt();
```

Both snippets assume `User`/`Order` are serializable, output/input streams share the same format, and checked exceptions are handled. `ObjectInputStream` does not inherently know "message number 1 is User, message number 2 is Order" beyond the stream's own class descriptors. Callers must agree on the **sequence/protocol**.

A solid design should specify:

- An outer application protocol version, separate from Java's `STREAM_VERSION`.
- Allowed record types and the scope of each message.
- Message count, termination conditions, and byte limits.
- How to handle disconnects/truncated streams.
- Class version evolution and allowlist policies.
- When `reset()` is allowed to avoid reference aliasing across logical messages.
- Trust conditions for the byte source and reconstructed objects.

### 15.1. Do Not Concatenate Stream Headers Arbitrarily

If a process opens a file in append mode and constructs a **new `ObjectOutputStream`** to write an object:

```java
new ObjectOutputStream(new FileOutputStream("data.bin", true))
        .writeObject(obj);
```

This snippet illustrates a **design bug** and also leaks resources because it never closes the stream. The constructor writes a **new header** in the middle of the file; when reading with a single `ObjectInputStream` and calling `readObject` repeatedly, that header may be treated as invalid protocol data.

Solution: keep **one `ObjectOutputStream` open for the corresponding write scope**, or design explicit framing for multiple independent serialized streams and read each frame with a separate `ObjectInputStream`. Techniques that subclass to suppress headers on append are very error-prone with handles/protocol and require proving correctness; do not copy header-suppression tricks into production without testing.

## 16. Comparison with Other Storage Formats

| Goal | Java Object Serialization | Alternatives Worth Considering |
|---|---|---|
| Passing Java object graphs between trusted components | Can fit when versions/classes are controlled | Schema-backed binary protocol if more stability is desired |
| JSON API across multiple languages | Unsuitable: Java-specific binary format | JSON + validation |
| Storing human-editable user configuration | Hard to read/edit | Properties, JSON, YAML/TOML with a safe parser |
| Structured binary data with long-term schema | Coupled to classes and UID | Protocol Buffers, Avro, CBOR/schema |
| Storing raw byte arrays/images/files | No need for object graph overhead | `Files.readAllBytes`/`Files.write` or streams/channels |
| Storing secrets/credentials | No default encryption | Secret store/keystore/appropriate encryption |
| Receiving untrusted bytes | Major risk on `readObject` | Data format with safe parser/allowlist/schema |

If you need Java serialization, use it for **clear compatibility/lifecycle requirements**, not just because two lines of code feel convenient.

## 17. Common Mistakes

1. **Forgetting to implement `Serializable`** on the class or a referenced child object. Can throw `NotSerializableException`.
2. **Assuming every field is written.** `static` and `transient` are not included in default state.
3. **Thinking `transient` means encryption.** It omits the field from the default mechanism but does not automatically protect other fields/aliases.
4. **Confusing the stream's `writeObject` with the class's private hook.** They have different roles and signatures.
5. **Changing a class without checking `serialVersionUID`.** `InvalidClassException` may occur.
6. **Keeping the same UID and assuming every schema change is compatible.** Some field/hierarchy/custom-data changes still break the format.
7. **Reading primitives with `readObject`.** Must use `readInt`/`readUTF`... in the writer's order.
8. **Reading a different number of objects than written.** Can hit `EOFException` or protocol errors.
9. **Confusing the `AC ED 00 05` header with object data.** That is stream-start metadata, not an object field.
10. **Thinking a second `writeObject(sameInstance)` sends new state.** The handle table may write a reference to the first occurrence.
11. **Mutating an object between two writes without calling `reset()` when a fresh snapshot is needed.** The reader still references the old state.
12. **Thinking `writeUnshared` deep-copies the whole object graph.** It does not guarantee alias-free nested references.
13. **Trying to parse a hex stream by scanning for arbitrary `TC_OBJECT` bytes.** Tokens must be interpreted according to grammar and lengths.
14. **Creating a new `ObjectOutputStream` each time while appending to the same file.** Repeated headers mid-stream break continuous reading.
15. **Both sides of a socket creating `ObjectInputStream` before any output header is sent.** Can deadlock because the constructor waits for header bytes.
16. **Closing `ObjectOutputStream` and then continuing to use the underlying `OutputStream`.** Close propagates to the underlying stream.
17. **Calling only `flush()` and claiming the file is durable across power loss.** Java flushing differs from filesystem persistence.
18. **Using `readObject` on JSON/text/ZIP.** Incompatible format; likely header error.
19. **Relying on the `Serializable` class constructor to validate every deserialized object.** That class's constructor may not be invoked.
20. **Only checking `instanceof` after `readObject` and treating external data as safe.** By then deserialization has already occurred.
21. **Omitting `ObjectInputFilter`/resource limits when reading untrusted data.** Risks loading dangerous/oversized graphs.
22. **Catching every `IOException` and trying to keep reading a corrupted stream.** Object stream state may be undefined.
23. **Using `toString()` as proof of deep equality.** Must test fields, references, and invariants.
24. **Thinking stream version `00 05` is the class's `serialVersionUID`.** The two concepts are independent.
25. **Assuming `String` is always encoded as raw UTF-8 bytes throughout the stream.** The protocol has its own encoding rules and markers; it is not identical to `"abc".getBytes(UTF_8)`.
26. **Treating serialization as raw memory copying.** Java persists logical state using the protocol and class descriptors.
27. **Not handling classes missing from the classpath.** `ClassNotFoundException` can make old data unreadable.
28. **Trusting restored objects to always have valid invariants.** Validation and class version management are needed.
29. **Not enforcing maximum byte/file size before deserializing.** Filters and resource limits should be layered.
30. **Using object serialization as long-term storage without compatibility tests.** Today's file might not be readable in a future deployment.

## 18. Self-Check Quiz

**Question 1.** Does `writeObject` produce JSON or a dedicated binary format?  
**Answer:** The binary Java Object Serialization Stream Protocol, containing headers/descriptors/tokens/handles.

**Question 2.** What are the first four bytes of a typical `ObjectOutputStream`?  
**Answer:** `AC ED 00 05` (magic and stream version).

**Question 3.** Does a `Serializable` class need to override `writeObject`?  
**No.** `Serializable` is a marker interface; the default mechanism can write eligible fields automatically.

**Question 4.** What happens if a `Serializable` class has a non-transient field pointing to a non-Serializable class?  
**Answer:** Writing the graph can throw `NotSerializableException`.

**Question 5.** What is the static return type of `readObject`, and what should you do afterward?  
**Answer:** `Object`; validate/cast appropriately and verify data, but do not treat post-read checks as full protection against untrusted input.

**Question 6.** Why can calling `writeObject(sameObj)` twice and reading twice produce the same reference?  
**Because** `ObjectOutputStream` maintains a handle table and can write `TC_REFERENCE` for an already-written object.

**Question 7.** What does `out.reset()` between two writes do?  
**Answer:** Clears remembered handles and writes a reset marker; objects written afterward are serialized anew in a fresh context.

**Question 8.** What is `transient String token` restored to under the default mechanism?  
**Answer:** Typically `null` unless custom logic modifies it.

**Question 9.** How does `serialVersionUID` differ from `STREAM_VERSION`?  
**Answer:** UID identifies a class's compatible version; `STREAM_VERSION` describes the serialization wire protocol version.

**Question 10.** Can an `ObjectInputStream` read an ordinary UTF-8 text file?  
**No.** The stream must follow the Java object serialization protocol; text files lack appropriate headers/class descriptors.

**Question 11.** Can you read untrusted data first and then check the type afterward to eliminate all risk?  
**No.** Deserialization has already started before the check. Prefer schema-based formats, or filters and resource limits when an object stream is unavoidable.

**Question 12.** If a class changes package or disappears while the file bytes remain intact, is deserialization guaranteed to succeed?  
**No.** The JVM still needs to resolve the class name and compatibility rules.

**Question 13.** Does `out.flush()` guarantee a file survives a power loss intact?  
**No.** Java-level flushing is not equivalent to device/filesystem durability.

**Question 14.** Does `writeUnshared` guarantee that all nested objects are deep-cloned?  
**No.** It only changes sharing semantics at the API-defined level; nested references can still be shared.

**Question 15.** How do you verify a stream file preserves the full object graph rather than just matching printed strings?  
**Answer:** Test field values, reference identity, cycles, invariants, serialization hooks, and compatibility across versions.

## 19. Summary and Official Documentation

**Essence:** `ObjectOutputStream.writeObject` writes an **object graph** into the Java Object Serialization Stream Protocol. `ObjectInputStream.readObject` reads back the **next object** and restores references. A stream has the `AC ED 00 05` header, class descriptors, type tags, handles, and block data; it is not JSON or an array of independent objects. `Serializable`, `serialVersionUID`, `transient`, `reset`, and custom hooks determine how data is saved and restored.

**Safety rule:** only deserialize trusted sources, or enforce strict filtering/limits when reading Java object streams is unavoidable. Do not treat Java serialization bytes as the default storage format for systems requiring long-term compatibility, cross-language support, or strong defense against adversary-controlled data.

Official Java resources:

- `ObjectOutputStream` — `writeObject`, `reset`, `writeUnshared`, stream header: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html
- `ObjectInputStream` — `readObject`, `readUnshared`, `setObjectInputFilter`, and security warnings: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html
- `Serializable` — marker interface and custom hooks: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- `ObjectInputFilter` — deserialization filtering: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html
- `ObjectStreamConstants` — STREAM_MAGIC/STREAM_VERSION/TC_*: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectStreamConstants.html
- `ObjectStreamClass` — serialVersionUID and class descriptors: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectStreamClass.html
- Java Object Serialization Specification, Stream Protocol: https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/protocol.html
- Java Object Serialization Specification, Versioning: https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/version.html