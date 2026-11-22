# writeObject, readObject, and Stream Format in Java Object Serialization

## 1. From Objects in Memory to a Byte Stream

**Java Object Serialization** is the mechanism that turns the state of a Java object and all objects reachable through its reference fields into **a structured byte stream**; the reverse process reconstructs an object graph from that stream.

Two common entry points:

- `ObjectOutputStream.writeObject(obj)`: writes the serialized representation of an object to an `OutputStream`.
- `ObjectInputStream.readObject()`: reads the **next object** in the stream, restores its data and reference relationships, and returns an `Object`.

Neither method converts objects to JSON or plain text. The result is the **Java Object Serialization Stream Protocol binary format**, including header, type tags, class descriptors, field values, object references, and additional data when needed.

```text
Java object                      BINARY STREAM                    Java object
Message("HELLO", 7) ──writeObject──▶ AC ED 00 05 ... ──readObject──▶ Message("HELLO", 7)
                                ▲                   │
                        ObjectOutputStream     ObjectInputStream
                                │                   │
                           OutputStream          InputStream
```

Lesson goals: use `writeObject`/`readObject` accurately; understand what is stored in the stream and how to read it back in the right order; distinguish object data from stream headers/class descriptors; recognize handles/reference sharing, `serialVersionUID`, `transient`, exceptions, and security risks of calling `readObject` on untrusted data.

**Important security note:** never assume that bytes received over the network, externally downloaded files, or user-submitted blobs are safe to pass into `ObjectInputStream`. Java deserialization can trigger object reconstruction mechanisms and callbacks on the classpath; prefer safer data protocols or enforce strict limits and controls when its use is truly necessary.

## 2. Classes and Interfaces to Know

| Component | Role |
|---|---|
| `java.io.Serializable` | Marker interface indicating a class permits default Java serialization |
| `ObjectOutputStream` | Writes objects and primitive data into an Object Serialization Stream |
| `ObjectInputStream` | Reads objects and primitives according to the same stream rules |
| `ObjectStreamConstants` | Magic header, version, and protocol marker bytes (`TC_*`) |
| `ObjectStreamClass` | Describes a serializable class; exposes `serialVersionUID` and field descriptors |
| `serialVersionUID` | Version identifier used for class compatibility checks during deserialization |
| `transient` | Excludes an instance field from default serialization |
| `ObjectInputFilter` | Mechanism to filter/limit classes, depth, references, arrays, and bytes while reading |
| `Externalizable` | Mode where a class fully defines its own read/write behavior via `writeExternal`/`readExternal` |

At a basic level, implementing `Serializable` is enough for the default mechanism to write eligible fields:

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

This is a standalone compilable class in `Student.java`, **without `main`**. Since `String` is serializable and `int` is primitive, a `Student` instance's state can be serialized by default. Here, `serialVersionUID` is a `static final long` field meant for class version checking, **not** instance data written like a normal field.

### 2.1. Serializable Is Not a Method to Override

`Serializable` is a **marker interface**: it declares no `serialize()` or `deserialize()` methods. Therefore:

```java
class Entry implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    int number = 42;
}
```

already satisfies the basic requirement for object serialization. You are **not required** to override `writeObject`/`readObject` in every class; the `ObjectOutputStream` API performs the default mechanism.

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

This is an illustrative snippet inside a method that handles `IOException` and has the `Student` class available. It requires importing `java.io.ObjectOutputStream` and `java.io.FileOutputStream`.

Workflow:

1. Create `ObjectOutputStream`. Its constructor **writes the stream header** to the underlying output.
2. Call `writeObject(obj)` to store the object.
3. The encoder traverses the object graph reachable via serializable fields, writing class descriptors and required values.
4. The stream maintains a **handles** table to recognize references already written within the current stream.
5. When closing `ObjectOutputStream`, the underlying stream is also closed; use `try-with-resources` to prevent resource leaks.

You can write multiple objects **sequentially** on the same `ObjectOutputStream`, then read them back in the exact same order. Do not create a new `ObjectOutputStream` every time you append another object to the same file expecting a single `ObjectInputStream` to treat consecutive headers as a simple list of objects.

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

These two classes are illustrative top-level code in a Java file (non-`public`) or an equivalent valid scope. When calling `out.writeObject(new Person())`, the `Address` object referenced through `address` is also written, **without needing** a separate `writeObject(address)` call.

If `Address` does not support serialization and the `address` field is not `transient`, writing `Person` can fail with `NotSerializableException`. This mechanism does not automatically accept every object in the graph.

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

`readObject()` **must not** be used in place of `readInt()` to retrieve a primitive written by `writeInt()`. Mismatched data order or read types can cause `OptionalDataException`, `StreamCorruptedException`, or other errors depending on stream state. Note that `writeUTF` uses `DataOutput`'s *modified UTF-8* format, not standard unframed UTF-8 bytes.

## 4. ObjectInputStream and Reading Objects

Example reading back the previously written file:

```java
try (ObjectInputStream in =
        new ObjectInputStream(
                new FileInputStream("student.bin"))) {

    Object value = in.readObject();
    Student student = (Student) value;
}
```

This snippet belongs inside a method declaring or handling `IOException` and `ClassNotFoundException`, with a compatible `Student` class on the classpath. `readObject()` has static return type `Object` because incoming data can represent many different classes; Java cannot use generics to guarantee the returned runtime class.

**Steps when reading:**

1. The `ObjectInputStream` constructor reads and validates the stream header.
2. `readObject` reads type tags and descriptors, decoding the object graph against matching classes in the JVM.
3. For default `Serializable` classes, instance state is restored per field serialization rules.
4. The stream maintains a read-side handle table so repeated/cyclic references are rebuilt into proper relationships.
5. The caller must check the type and **verify business validity** of the restored object; a valid Java type does not mean the values are trustworthy.

`ObjectInputStream` must be used only on data genuinely conforming to the Java Object Serialization Stream Protocol. An arbitrary JSON, ZIP, or UTF-8 text file cannot be read natively by `ObjectInputStream`.

### 4.1. Constructor May Block Waiting for Header on Sockets

`new ObjectInputStream(input)` **can block waiting for header bytes**. If both sides of a socket create `ObjectInputStream` and wait for a header before either creates/flushes `ObjectOutputStream`, the program can **deadlock**.

The two-way exchange pattern must be designed accordingly:

```java
ObjectOutputStream out = new ObjectOutputStream(socket.getOutputStream());
out.flush(); // Push the header.
ObjectInputStream in = new ObjectInputStream(socket.getInputStream());
```

This is a snippet using a valid `socket`; it is not a complete TCP program. Calling `flush()` lets header bytes generated by the output stream reach the peer, though both sides must still agree on setup order, message protocol, timeouts, and socket lifecycle.

## 5. Complete Java 17+ Example: Header, Repeated References, Reset, and Transient

The following example uses `ByteArrayOutputStream`/`ByteArrayInputStream` to avoid filesystem dependencies. It demonstrates key aspects of `writeObject` and `readObject`: binary header; writing the same object twice; `reset()` creating a new handle-table boundary; and `transient` fields excluded from default state.

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
            out.writeObject(original); // Handle table: this instance is already written.
            out.reset();              // Clear remembered handles.
            out.writeObject(original); // Write a fresh object representation.
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

**Why does this output occur?**

1. A default Java serialization stream starts with magic `AC ED` and version `00 05`, i.e., `STREAM_MAGIC=0xACED` and `STREAM_VERSION=5`.
2. The first `writeObject(original)` stores class and object data; the second call on the **same instance** within the **same handle table** emits a reference to the already-written object. Thus the first two `readObject` calls return **the same instance** on the reading side (`== true`).
3. `out.reset()` clears the stream's handle state per contract and writes a reset token. The third write emits a fresh representation; the reader also resets its context, so the third object has a **different reference** (`== false`).
4. The `secret` field is declared `transient`, so the default mechanism **does not save `"TOKEN"`**. After deserialization, the reference field has default value `null`.
5. `text` and `sequence` are restored because they are ordinary serializable instance fields, the class is compatible, and valid data is present.

The code was verified on a JDK. The example source uses ASCII text so output stays consistent even on terminals without Unicode support; the lesson does not imply Java serialization only handles ASCII.

## 6. Object Serialization Stream Protocol Format

### 6.1. Stream Header: `AC ED 00 05`

A stream created by `ObjectOutputStream` generally has this high-level structure:

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

`ObjectInputStream` uses this header to recognize the format. If the first four bytes are invalid, the constructor may throw `StreamCorruptedException`, such as when accidentally reading a text or JSON file.

**Do not confuse:** "version 5" in the stream header is the **stream protocol version**, not Java 5, not JDK 17/21, and not the class's `serialVersionUID`. A stream still uses version 5 even when compiled on modern JDKs.

### 6.2. Main Type Tags

Tokens are defined in `ObjectStreamConstants`; when inspecting hex dumps, you may spot:

| Token | Hex value | High-level meaning |
|---|---|---|
| `TC_NULL` | `70` | Null reference |
| `TC_REFERENCE` | `71` | Reference to an existing object/descriptor handle |
| `TC_CLASSDESC` | `72` | New class descriptor |
| `TC_OBJECT` | `73` | New object instance |
| `TC_STRING` | `74` | New string |
| `TC_ARRAY` | `75` | New array |
| `TC_CLASS` | `76` | Class object |
| `TC_BLOCKDATA` | `77` | Short block of primitive/optional data |
| `TC_ENDBLOCKDATA` | `78` | End of an optional block-data section |
| `TC_RESET` | `79` | Reset context/handles |
| `TC_BLOCKDATALONG` | `7A` | Long block-data section |
| `TC_EXCEPTION` | `7B` | Exception information in protocol |
| `TC_LONGSTRING` | `7C` | Long string |
| `TC_PROXYCLASSDESC` | `7D` | Descriptor for a proxy class |
| `TC_ENUM` | `7E` | Enum constant |

These are **markers in a structured protocol**, not "every `73` byte in the file is a new object." A byte with value `73` can appear **inside a payload or class name**; a parser must follow grammar, lengths, and context rather than scanning arbitrarily for bytes.

### 6.3. What Does a Class Descriptor Contain?

The first time a serializable class is encountered in a stream, its descriptor can contain:

- The binary name of the class.
- `serialVersionUID`.
- Flags indicating how the class is serialized.
- The list of persisted fields with names and types.
- Superclass descriptor and optional custom data sections if any.

For instance, in `Message` above, the descriptor lists saved fields such as `sequence` and `text`; `secret` is omitted because it is `transient`. This is only a logical summary, **not** a complete hex layout across all JDKs and class paths. Actual byte streams also include nested class names, handles, string descriptors, annotations, and other protocol items.

**Never hand-craft raw byte streams** unless you are building a parser/encoder compliant with the Java Object Serialization Specification. `writeObject`/`readObject` are designed to handle descriptors, reference graphs, block data, and class matching for you.

### 6.4. Object Handles Preserve Reference Identity

Java serialization is not simply "dump every field on each call." It maintains a handle table to:

- Avoid repeating an entire already-written object when encountering **the same reference** again.
- Preserve relationships where multiple fields point to the same object after reading.
- Reconstruct graphs with **cycles** (cyclic references) without infinite recursion.
- Allow instance sharing after deserialization within the corresponding stream context.

In the protocol, handles are assigned starting from base value `0x7E0000` per spec, and `TC_REFERENCE` tokens point back to previously assigned handles. Do not use handle numbers as stable business IDs; they are internal to a single stream.

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

This snippet runs inside a method with `ObjectOutputStream out`; both `Node` instances are written using handles for the back-reference. Reading back `Node restored = (Node) in.readObject()` from the corresponding stream preserves `restored.next.next == restored`, provided classes are compatible and no custom replacement alters the structure.

### 6.5. Re-writing the Same Reference with `writeObject` Does Not Mean a Fresh Snapshot

```java
Entry entry = new Entry();
entry.number = 1;
out.writeObject(entry);

entry.number = 2;
out.writeObject(entry); // Usually writes only a reference to the already-seen instance.
```

This snippet uses the `Entry` `Serializable` class above with `out` open. The second read **is not guaranteed** to yield `number=2`; because the object is already in the handle table, the stream uses a handle to the object serialized the first time. Call `out.reset()` between writes if you genuinely need to record the object's updated state, understanding that resetting affects the entire handle table of the stream.

## 7. `reset()`, `writeUnshared()`, and `readUnshared()`

### 7.1. When to Use `ObjectOutputStream.reset()`?

`reset()` instructs `ObjectOutputStream` to discard stored handles; subsequently written objects get a fresh reference context. It also places a `TC_RESET` marker in the stream so `ObjectInputStream` stays synchronized.

```java
out.writeObject(state);
out.reset();
out.writeObject(state);
```

This is illustrative code with `out` open and `state` `Serializable`. It serves two purposes:

1. Allowing a **fresh snapshot** of the same instance to be sent after data mutated between writes.
2. Reducing accumulated object references in the handle table of a long-lived stream, at the cost of re-writing descriptors/objects after each reset.

Do not call `reset()` from inside an ongoing `writeObject` call while serializing an object graph; the API forbids resetting mid-graph and may throw `IOException`. Call it at **boundaries between complete writes**.

### 7.2. Are `writeUnshared` and `readUnshared` a Deep Copy?

No. `writeUnshared(obj)` has specific semantics regarding how the **top-level object** is treated as unshared; `readUnshared()` requires the input to satisfy matching unshared conditions. However, they **do not guarantee a deep copy of the entire object graph**, because objects referenced in child fields can still be shared per protocol.

Therefore, if the goal is creating a **completely independent copy**, Java serialization is not the implicit answer. You need a dedicated copy procedure with explicit ownership and policies. Do not use `writeUnshared` assuming it eliminates alias references in nested objects.

## 8. Which Fields Are Serialized?

Under default `Serializable`, **non-static, non-transient instance fields** are processed by serialization, subject to class hierarchy and declaration rules.

| Field kind | Included in default serialized state? | Example |
|---|---|---|
| `private int count` | Yes | Primitive value `7` |
| `private String name` | Yes | Reference to a `Serializable` `String` |
| `private Address address` | Yes if corresponding object graph is serializable | Another object graph |
| `private transient String password` | No | Usually `null` after deserialization |
| `private static int total` | No | Belongs to class/JVM, not instance |
| `private static final long serialVersionUID` | Not an instance field; used in descriptor | Compatibility check |
| Field referencing non-Serializable object | Writing may fail unless excluded/replaced | `NotSerializableException` |

### 8.1. `transient` Is Neither Encryption Nor Secure Erasure

A field marked `transient` is omitted **under the default mechanism**. It does not automatically:

- Wipe the value currently residing in RAM.
- Prevent custom `writeObject` from explicitly writing that value via other calls.
- Prevent sensitive data from leaking through other fields in the graph.
- Encrypt the written data.

Example:

```java
class Account implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String owner;
    transient String sessionToken;
}
```

If a caller sets `sessionToken="abc"` and serializes via the default mechanism, that value is absent from `Account`'s serialized fields. Yet another object holding the same token in a **non-transient** field could still cause the token to appear in the stream. Do not view Java serialization as a secrets vault or a safe format for credentials.

### 8.2. Distinguishing Normal Constructors from Deserialization

For an ordinary serializable class, deserialization **does not call that serializable class's constructor** the way `new` does. Fields are restored via serialization mechanics; the no-argument constructor of the **first non-Serializable superclass** is called according to specification rules.

This has consequences:

- Invariants established only inside the serializable class's constructor may not run upon restoration.
- Transient fields receive default values (unless code actively restores them), rather than being populated by that class's constructor.
- You cannot rely on constructors to guard every object created via deserialization.
- For important data, validation and source controls are needed; a `readObject` hook can verify invariants itself, which is also why deserializing untrusted data is dangerous.

## 9. `serialVersionUID` and Compatibility Across Class Versions

### 9.1. Why Does Java Check `serialVersionUID`?

During serialization, class info in the stream is tagged with `serialVersionUID`. During deserialization, Java checks whether the corresponding class in the JVM has an allowed version to reconstruct the stream.

```java
public final class UserProfile implements java.io.Serializable {
    private static final long serialVersionUID = 3L;
    private String displayName;
}
```

This is a standalone compilable class `UserProfile.java`. If a `Serializable` class **does not declare** `serialVersionUID`, Java computes a default value from class details per specification. That computed value can change when you edit the class definition; hence you should declare it explicitly to manage compatibility policies rather than relying on implicit computation.

If the stream and local class have mismatched `serialVersionUID` values, a common error is `InvalidClassException`:

```text
java.io.InvalidClassException: ... local class incompatible:
stream classdesc serialVersionUID = ..., local class serialVersionUID = ...
```

This is an **illustrative error message pattern**, not fixed stdout. It occurs when class metadata in the stream fails version compatibility checks.

### 9.2. The Same `serialVersionUID` Alone Does Not Guarantee All Class Changes Are Compatible

Keeping `serialVersionUID` unchanged can support **some** field changes. It does not mean you can:

- Arbitrarily change a field's type.
- Switch a class from `Serializable` to `Externalizable` without changing the contract.
- Change the inheritance hierarchy or class structure in incompatible ways.
- Delete or rename a class without a matching class at read time.
- Freely alter custom `writeObject`/`readObject` formats without versioning.

Class evolution rules are defined in *Java Object Serialization Specification – Versioning of Serializable Objects*. When storing files for years or across releases, version data at the application level, verify actual compatibility by testing sample files from older versions, and consider using explicit-schema formats.

### 9.3. Inspecting `serialVersionUID` via `ObjectStreamClass`

```java
long uid = java.io.ObjectStreamClass
        .lookup(UserProfile.class)
        .getSerialVersionUID();
System.out.println(uid);
```

This snippet assumes `UserProfile` above is available. The printed value is `3`, independent of any `UserProfile` instance. `ObjectStreamClass.lookup` is intended for serializable classes; do not assume every class type yields a useful descriptor.

## 10. Customizing Data with Private `writeObject` and `readObject` Inside a Class

Do not confuse:

- `out.writeObject(obj)`: the **public** method on `ObjectOutputStream`, invoked by callers to serialize an object.
- `private void writeObject(ObjectOutputStream out)`: a **special hook inside the `Serializable` class itself**, recognized by the serialization runtime by its signature.
- `private void readObject(ObjectInputStream in)`: a custom restoration hook inside the `Serializable` class itself.

If a class needs extra structured data or invariant validation on restoration, it can declare:

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

This is a **compilable class** (`PositiveCount.java`), though without `main`/stdout. `defaultWriteObject()` writes the class's default-selected fields; `defaultReadObject()` restores them. Afterward, `readObject` checks `count >= 0` because the serializable class's constructor is not guaranteed to execute during deserialization.

### 10.1. Customizing the Stream Format Requires Discipline

If a `writeObject` hook appends extra data:

```java
out.defaultWriteObject();
out.writeInt(42);
```

then the matching `readObject` hook must consume it in the exact same sequence:

```java
in.defaultReadObject();
int extra = in.readInt();
```

Both snippets belong inside their respective hooks, not as standalone programs. For custom serialization, Java provides optional-data/block-data framing in the protocol. To maintain cross-version compatibility, version explicitly rather than arbitrarily reordering or changing custom fields without backward-compatible reading.

These hooks do not permit bypassing type checks, security filters, or the `ObjectInputStream` contract. Beyond `writeObject`/`readObject`, `writeReplace`/`readResolve` can substitute objects during serialization/deserialization; they are advanced tools that also increase risk when reading untrusted data.

### 10.2. `Externalizable` Is Not the Same Default Path

`Externalizable` extends `Serializable` and requires the class to define `writeExternal(ObjectOutput)` / `readExternal(ObjectInput)`. With `Externalizable`, the class actively takes charge of writing/reading its contents and carries specific constructor requirements (including a `public` no-argument constructor) upon restoration.

Do not view `Externalizable` as merely "`Serializable` with an extra method." It changes formatting, versioning, and validation responsibilities, so use it only when fine-grained layout control is needed and backed by compatibility tests.

## 11. Streams Contain Primitive Block Data and Are Not JSON

In a hex view, you can see headers, tokens, and data blocks interleaved. For example:

```java
ByteArrayOutputStream buffer = new ByteArrayOutputStream();

try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
    out.writeInt(42);
    out.writeObject("hello");
}
```

This is an illustrative snippet inside a method handling `IOException`, with appropriate imports. In the stream, `writeInt(42)` is framed via `ObjectOutputStream`'s **block data** mechanism, followed by the serialized `String`. You **cannot** read the first 4 bytes of the file expecting the integer `42`, because the first four bytes are the header `AC ED 00 05`.

### 11.1. The Stream Format Is Structured, Not a JVM Memory Dump

Serialization writes a **logical object graph** per specification rather than copying raw memory addresses or pointers from the JVM.

- In-process memory addresses of objects are not preserved when reading from the stream.
- References between objects are represented by corresponding handles.
- Data depends on serializable class schemas and custom hooks, not fixed HotSpot memory layouts.
- Another process/JVM can deserialize when compatible classes are present, yet that **does not** make objects safe if bytes originate from untrusted sources.
- This stream cannot serve as a language-agnostic interchange standard the way JSON or Protocol Buffers are designed.

### 11.2. Not All Field Values Are Repeated on Every `writeObject`

Within a stream holding a handle table, Java may write `TC_REFERENCE` instead of re-serializing an object. Consequently, the byte count produced after each `writeObject` depends on stream history, the object graph, `reset` calls, and hooks—not simply `toString()` or current field count.

If you want to measure serialized byte size:

```java
ByteArrayOutputStream sink = new ByteArrayOutputStream();
try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
    out.writeObject(obj);
}
int byteCount = sink.toByteArray().length;
```

This snippet assumes a serializable `obj` and proper imports. The resulting `byteCount` is the number of bytes **written for the object plus stream overhead**, including header and descriptors—not the object's heap memory footprint.

## 12. Common Errors and Exceptions

| Exception | When encountered | How to handle |
|---|---|---|
| `NotSerializableException` | Graph contains an object of a non-serializable class | Serialize only purpose-built DTOs, using `transient` where appropriate |
| `InvalidClassException` | Stream/local classes are incompatible, often mismatched UID or violated serialization constraints | Manage `serialVersionUID` and test schema/versioning |
| `StreamCorruptedException` | Header/control bytes violate protocol, or stream is corrupted | Check source/format; avoid mixing multiple headers |
| `ClassNotFoundException` | JVM cannot locate a class needed for reconstruction | Verify classpath/modules; avoid storage coupled to unstable classes |
| `EOFException` | Not enough bytes left to continue reading as expected | Manage framing/counts; avoid relying on EOF for all structural logic |
| `OptionalDataException` | Reading an object at primitive data position or special optional-data states | Read in the same order and format as the writer |
| `InvalidObjectException` | Validation hook explicitly rejects invalid object state | Check schema and data; do not ignore the error |
| `IOException` | File/socket/stream I/O failure | Close stream, report error; do not treat partial bytes as complete |
| `ClassCastException` | Casting read object to expected class fails due to wrong type | Verify instance/type, filters, and schema |

**Never attempt to continue reading an `ObjectInputStream` after a serious serialization error assuming offsets remain valid.** The Java API may leave the stream in an indeterminate state. When encountering corrupted or untrusted data, normally close the stream, report the error, and perform application-level recovery rather than hunting for the next token in the byte array.

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

These are two illustrative classes. `out.writeObject(new Container())` fails because `helper` points to a class implementing neither `Serializable` nor `Externalizable`. Changing the field to `transient` is only appropriate if that state is not needed in restored data; never "fix" it by dropping critical data without designing a rebuild mechanism.

### 12.2. Do Not Use `toString()` to Compare Bytes or Identity

When reading an object, `System.out.println(obj)` may print a readable string if the class overrides `toString()`, or an identity hash string otherwise. It does not prove the object graph was restored accurately. To verify, inspect concrete fields, reference identity when needed, invariants, and application behavior; use `==` to test reference sharing as shown in `ObjectStreamDemo`.

## 13. Security Risks of `readObject`

JDK documentation warns that Java Object Deserialization is **dangerous when data comes from untrusted sources**. During reading, the runtime can load classes, instantiate objects via special mechanisms, and trigger hooks/deserialization logic in classes present on the classpath. An adversary-controlled byte sequence can try to construct deeply nested object graphs, huge arrays, or dangerous gadget chains.

**Priority principles:**

1. Never accept Java serialized object streams directly from the Internet or untrusted users when schema-validated JSON/CBOR/Protocol Buffers can be used.
2. If usage is unavoidable, **restrict allowed classes** and related resources via `ObjectInputFilter`, deployment-wide filter factories/policies, and classpath hygiene.
3. Enforce total byte-size limits before reading where the protocol permits; use transport-level timeouts and limits.
4. After deserialization, still verify object type, structure, required fields, and business invariants.
5. Keep JDK/libraries updated and avoid placing unnecessary classes on the deserializing process's classpath.
6. Never rely on `instanceof` **after** reading as your sole defense, because object creation/restoration has already occurred inside `readObject()`.

### 13.1. `ObjectInputFilter` and Limits

In modern Java versions, `ObjectInputStream` supports filters checking classes, array lengths, graph depth, reference counts, and consumed bytes. An **illustrative** policy example:

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

This is an **illustrative snippet**, not a standalone program: it requires importing `ObjectInputFilter` and `ObjectInputStream`; `source` is an `InputStream`; the caller handles `IOException`/`ClassNotFoundException`. Replace `com.example.dto.*` with actual classes allowed by your application architecture; valid container, array, or dependency classes must also be checked against policy. The trailing `!*` rejects classes not matched by the allowlist. Some string/primitive cases behave specially with filter callbacks, so the filter **is not a content validator**.

`setObjectInputFilter` is called **once** before reading objects; it is not meant to be swapped back and forth per item once stream reading begins. JVM-wide policies also exist via filter factories and JVM properties; how they combine is governed by the JDK and deployment configuration.

**Filters reduce risk but do not make a stream "guaranteed safe."** Treat deserialization from untrusted sources as a security boundary, apply defense in depth, and prefer formats built for data interchange.

### 13.2. Do Not Log or Deserialize Unchecked Bytes Just to Inspect Them

An antipattern:

```java
Object object = new ObjectInputStream(untrustedInput).readObject();
// Only afterward check which class the object belongs to.
```

This is **unsafe** illustrative code and must not be used with untrusted data. The risk lies **inside deserialization itself**, before your code inspects the returned object's class. Use schema-driven parsing and bound bytes/class graphs before ingesting payloads.

## 14. Saving Objects to Files and Data Durability

### 14.1. `flush()` Does Not Mean `fsync`

`out.flush()` pushes buffered bytes to the next `OutputStream`; `out.close()` closes the stream and flushes per contract. Neither **creates a guarantee** that data is durably persisted across power loss on every filesystem.

```java
try (FileOutputStream file = new FileOutputStream("state.bin");
     ObjectOutputStream out = new ObjectOutputStream(file)) {

    out.writeObject(state);
    out.flush();
    file.getFD().sync(); // Request syncing the file descriptor per contract.
}
```

This is an illustrative snippet inside a method with a `Serializable` `state`, importing `FileOutputStream`/`ObjectOutputStream`. `FileDescriptor.sync()` requests synchronizing file content through the descriptor; it carries cost and device/provider dependencies. If an application requires atomic state-file updates, write to a temporary file and publish via rename alongside appropriate filesystem durability guarantees—calling `writeObject` **does not** automatically confer durability.

### 14.2. Reading Long-Term Saved Files Does Not Always Succeed

An `ObjectOutputStream` may produce valid bytes in the current application version, yet years later:

- Packages or classes have been renamed.
- `serialVersionUID` differs.
- Some fields or classes in the object graph no longer exist.
- New deserialization filter policies reject legacy classes.
- Newer classes enforce different invariants and reject older data.

Therefore, Java serialization is generally suitable when **both writer and reader reside in a tightly managed Java ecosystem** with tested cross-version compatibility; it is not the default choice for business data needing stable schemas across years or deployment generations.

## 15. Read/Write Ordering and Protocol Framing

Suppose the writer does:

```java
out.writeObject(user);
out.writeObject(order);
out.writeInt(2026);
```

Correct reader:

```java
User user = (User) in.readObject();
Order order = (Order) in.readObject();
int year = in.readInt();
```

Both snippets assume `User`/`Order` are serializable, output/input streams share the same format, and checked exceptions are handled. `ObjectInputStream` does not inherently know "message 1 is `User`, message 2 is `Order`" beyond class descriptors in the stream itself. Callers must agree on **sequence and protocol**.

A solid design should specify:

- An outer application protocol version separate from Java's `STREAM_VERSION`.
- Allowed record types and scope of each message.
- Message counts, termination conditions, and byte limits.
- Handling for disconnects or truncated streams.
- Class version transitions and allowlist policies.
- When `reset()` is allowed to avoid reference aliasing across logical messages.
- Trust assumptions for byte sources and reconstructed objects.

### 15.1. Do Not Concatenate Stream Headers Arbitrarily

If a process opens a file in append mode, creates a **new `ObjectOutputStream`**, and writes an object:

```java
new ObjectOutputStream(new FileOutputStream("data.bin", true))
        .writeObject(obj);
```

This snippet illustrates a **design flaw** and also leaks resources by not closing the stream. The constructor writes a **new header** mid-file; when read sequentially with a single `ObjectInputStream` calling `readObject`, that embedded header can be rejected as invalid protocol data.

Solution: keep **a single `ObjectOutputStream` alive for the write session**, or design explicit framing around multiple independent serialized streams and read each frame with its own `ObjectInputStream`. Subclassing tricks to suppress headers during append easily break handles/protocol and require proof of correctness; do not copy header-skipping hacks into production without thorough testing.

## 16. Comparison with Other Storage Formats

| Goal | Java Object Serialization | Alternatives to consider |
|---|---|---|
| Passing Java object graphs between trusted components | Can fit when versions/classes are tightly controlled | Schema-backed binary protocol if greater stability is desired |
| Cross-language JSON API | Unsuitable: Java-specific binary format | JSON + validation |
| Saving human-editable config files | Hard to read/edit | Properties, JSON, YAML/TOML with a safe parser |
| Long-lived structured binary data | Coupled to classes and UIDs | Protocol Buffers, Avro, CBOR/schema |
| Storing raw byte arrays/images/files | Unnecessary object-graph overhead | `Files.readAllBytes`/`Files.write` or streams/channels |
| Storing secrets/credentials | No built-in encryption | Secret manager/keystore/appropriate encryption |
| Accepting untrusted bytes | High risk with `readObject` | Data formats with schema/allowlist/bounded parser |

If you use Java serialization, do so for **clear compatibility and lifecycle reasons**, not merely because two lines of code seem convenient.

## 17. Common Errors

1. **Forgetting `implements Serializable`** on a class or referenced child object. Can throw `NotSerializableException`.
2. **Assuming every field is written.** `static` and `transient` are excluded from default state.
3. **Thinking `transient` is encryption.** It is omitted by default but does not automatically protect other fields or aliases.
4. **Confusing the stream's `writeObject` with the class's private hook.** They differ in role and signature.
5. **Changing a class without checking `serialVersionUID`.** `InvalidClassException` may occur.
6. **Keeping UID equal and assuming every schema change is compatible.** Some field, hierarchy, or custom-data edits still break format compatibility.
7. **Reading a primitive with `readObject`.** Must use `readInt`/`readUTF`/etc. matching writer order.
8. **Reading a different number of objects than written.** Can cause `EOFException` or protocol errors.
9. **Confusing the `AC ED 00 05` header with object data.** It is stream startup metadata, not an object field.
10. **Thinking a second `writeObject(sameInstance)` sends fresh state.** The handle table may emit a reference to the first write.
11. **Mutating an object between writes without calling `reset()` when a fresh snapshot is needed.** The reader continues referencing old state.
12. **Thinking `writeUnshared` deep-copies the entire object graph.** It does not guarantee alias-free nested references.
13. **Trying to parse hex streams by scanning arbitrarily for `TC_OBJECT` bytes.** Tokens must be interpreted according to grammar and lengths.
14. **Creating a new `ObjectOutputStream` on every append to the same file.** Repeated mid-stream headers break continuous reading.
15. **Both socket endpoints creating `ObjectInputStream` before any output header is sent.** Can deadlock as constructors wait for header bytes.
16. **Closing `ObjectOutputStream` and then continuing to use the underlying `OutputStream`.** Close propagates to the underlying stream.
17. **Calling only `flush()` and claiming power-loss durability.** Java flushing differs from filesystem persistence.
18. **Using `readObject` on JSON, text, or ZIP files.** Incompatible format; fails header checks.
19. **Relying on a `Serializable` class's constructor to validate every deserialized object.** The class's own constructor may never be called.
20. **Checking only `instanceof` after `readObject` and treating external data as safe.** Deserialization has already occurred by then.
21. **Omitting `ObjectInputFilter`/resource limits when reading untrusted data.** Risks loading dangerous or oversized graphs.
22. **Catching every `IOException` and trying to keep reading a corrupted stream.** Object stream state may be indeterminate.
23. **Using `toString()` as proof of deep equality.** Test fields, references, and invariants instead.
24. **Thinking stream version `00 05` is the class's `serialVersionUID`.** They are independent concepts.
25. **Assuming `String` is always encoded as raw UTF-8 bytes throughout the stream.** The protocol uses its own encoding rules and markers; it is not identical to `"abc".getBytes(UTF_8)`.
26. **Treating serialization like a raw memory copy.** Java saves logical state per protocol and class descriptors.
27. **Failing to handle classes removed from the classpath.** `ClassNotFoundException` can make older data unreadable.
28. **Trusting that read-back objects always satisfy invariants.** Validation and class version management are required.
29. **Failing to cap maximum bytes/file size before deserializing.** Filters and resource limits should be enforced across multiple layers.
30. **Using object serialization as long-term storage without compatibility tests.** Files written today may fail to read in future deployments.

## 18. Self-Check Knowledge

**Question 1.** Does `writeObject` produce JSON or a proprietary binary format?  
**Answer:** The binary Java Object Serialization Stream Protocol, containing headers, descriptors, tokens, and handles.

**Question 2.** What are the first four bytes of a standard `ObjectOutputStream`?  
**Answer:** `AC ED 00 05` (magic and stream version).

**Question 3.** Must a `Serializable` class override `writeObject`?  
**No.** `Serializable` is a marker interface; the default mechanism can write eligible fields automatically.

**Question 4.** What happens if a `Serializable` class has a non-transient field pointing to a non-Serializable class?  
**Answer:** Writing the graph can throw `NotSerializableException`.

**Question 5.** What static return type does `readObject` have, and what should you do afterward?  
**Answer:** `Object`; check/cast to the valid type and verify the data, though post-read checks are not sufficient protection against untrusted input.

**Question 6.** Why can calling `writeObject(sameObj)` twice and reading twice yield the same reference?  
**Because** `ObjectOutputStream` maintains a handle table and may emit `TC_REFERENCE` for an already-written object.

**Question 7.** What does `out.reset()` between two writes do?  
**Answer:** Clears remembered handles and writes a reset marker; subsequently written objects are serialized in a fresh context.

**Question 8.** What does `transient String token` restore to under the default mechanism?  
**Answer:** Usually `null` unless custom logic alters it.

**Question 9.** How does `serialVersionUID` differ from `STREAM_VERSION`?  
**Answer:** The UID identifies class compatibility version; `STREAM_VERSION` identifies the serialization wire protocol version.

**Question 10.** Can an `ObjectInputStream` read an ordinary UTF-8 text file?  
**No.** The stream must follow the Java object serialization protocol; text files lack appropriate headers and class descriptors.

**Question 11.** Can you read untrusted data first and check its type afterward to eliminate all risks?  
**No.** Deserialization has already executed before the check. Prefer schema-backed formats, filters, and resource limits when object streams are unavoidable.

**Question 12.** If a class changes package or disappears while the byte file remains untouched, is deserialization guaranteed to succeed?  
**No.** The JVM still needs to resolve the class name and compatibility rules.

**Question 13.** Does `out.flush()` guarantee a file stays intact after a power outage?  
**No.** Java-level flushing does not guarantee storage-device or filesystem durability.

**Question 14.** Does `writeUnshared` guarantee every nested object is deep-cloned?  
**No.** It changes sharing semantics only at the level defined by the API; nested references can still be shared.

**Question 15.** How do you verify a stream file contains the full object graph rather than just matching printed text?  
**Answer:** Test field values, reference identity, cycles, invariants, serialization hooks, and cross-version readability.

## 19. Summary and Official Documentation

**Core takeaway:** `ObjectOutputStream.writeObject` writes an **object graph** into the Java Object Serialization Stream Protocol. `ObjectInputStream.readObject` reads the **next object** and restores references. The stream contains header `AC ED 00 05`, class descriptors, type tags, handles, and block data; it is neither JSON nor an array of independent objects. `Serializable`, `serialVersionUID`, `transient`, `reset`, and custom hooks govern how data is saved and restored.

**Safety rule:** deserialize only trusted sources, or enforce strict filtering and resource limits when reading Java object streams is unavoidable. Do not treat Java serialization bytes as the default storage format for systems needing long-term compatibility, cross-language support, or strong defense against adversary-controlled inputs.

Official Java resources:

- `ObjectOutputStream` — `writeObject`, `reset`, `writeUnshared`, stream header: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html
- `ObjectInputStream` — `readObject`, `readUnshared`, `setObjectInputFilter`, and security warnings: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html
- `Serializable` — marker interface and custom hooks: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- `ObjectInputFilter` — deserialization filtering: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html
- `ObjectStreamConstants` — STREAM_MAGIC/STREAM_VERSION/TC_*: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectStreamConstants.html
- `ObjectStreamClass` — serialVersionUID and class descriptors: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectStreamClass.html
- Java Object Serialization Specification, Stream Protocol: https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/protocol.html
- Java Object Serialization Specification, Versioning: https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/version.html
