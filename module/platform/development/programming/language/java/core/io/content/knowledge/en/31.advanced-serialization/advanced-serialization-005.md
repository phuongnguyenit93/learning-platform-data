# Externalizable, writeExternal, and readExternal in Java Serialization

## 1. Overview and Objectives

In Java Core I/O, `java.io.Externalizable` is an object serialization mechanism that allows **the object's own class to actively write and read its data representation**. It extends `Serializable` but differs significantly from default serialization:

- Standard `Serializable`: `ObjectOutputStream` can automatically write eligible instance fields, except `static` and `transient`, according to Java serialization rules.
- `Externalizable`: the runtime calls **`writeExternal(ObjectOutput)`** when writing and **`readExternal(ObjectInput)`** when reading. The programmer decides what to write, in what order to write it, and how to restore it.
- When deserializing a normal `Externalizable` class, Java requires a **`public` no-argument constructor** to create an instance before calling `readExternal`.
- Managing data yourself **does not eliminate the object handle mechanism** of `ObjectOutputStream` when you call `writeObject`/`readObject`. Reference graphs and aliases can be preserved, including cycles, if the protocol is designed properly.
- `Externalizable` is still **Java native object serialization**, not a safe mechanism for decoding untrusted data.

After this lesson, you will understand the API contract, write a standalone runnable Java 17+ example, test ordering/versioning of the data representation, handle reference graphs, and know when not to use this mechanism.

## 2. What Is Externalizable?

Interface declaration:

```java
public interface Externalizable extends Serializable {
    void writeExternal(ObjectOutput out) throws IOException;

    void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException;
}
```

This is an abbreviated API declaration for explanation; Java already provides this interface in `java.io`—**do not redefine it in your project**.

The two key methods:

| Method | When Does It Run? | Role |
|---|---|---|
| `writeExternal(ObjectOutput out)` | When `ObjectOutputStream` writes a new Externalizable instance | Manually writes fields/version/record in the order you choose |
| `readExternal(ObjectInput in)` | After the instance is created for deserialization | Reads the exact representation produced by `writeExternal` and rebuilds state |

`ObjectOutput` has operations such as `writeInt`, `writeLong`, `writeBoolean`, `writeUTF`, `writeObject`, and `write(byte[])`. `ObjectInput` has symmetric operations `readInt`, `readLong`, `readBoolean`, `readUTF`, `readObject`, `readFully`, etc.

**Do not treat `ObjectOutput` as a JSON writer.** You are creating a sequence of byte values according to your application's own contract, inside Java's object serialization stream.

### Externalizable Does Not Mean the Class Is Written Completely Outside Java Serialization

`ObjectOutputStream.writeObject(externalizableObject)` still manages the object stream, class descriptors, identity handles, and related decoding mechanisms. `writeExternal` is responsible for the class's state payload, not replacing the entire stream format or looking up classes by name when reading.

## 3. Minimal Example of an Externalizable Class

```java
import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectOutput;

public class Product implements Externalizable {
    private static final long serialVersionUID = 1L;

    private String code;
    private int quantity;

    // REQUIRED: public and no-argument for the deserialization mechanism.
    public Product() {
    }

    public Product(String code, int quantity) {
        this.code = code;
        this.quantity = quantity;
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeUTF(code);
        out.writeInt(quantity);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        code = in.readUTF();
        quantity = in.readInt();
    }

    @Override
    public String toString() {
        return code + ": " + quantity;
    }
}
```

Save as `Product.java` if you want to compile this class separately. The snippet above is a **class definition**, without a `main` method to run. It assumes `code` is non-null and within `writeUTF` limits; advanced examples need input data validation.

What you must guarantee yourself:

1. `writeExternal` writes `code` **before** `quantity`.
2. `readExternal` reads `code` with `readUTF` **before** `quantity` with `readInt`.
3. Changing the order or type of a component without updating the reading protocol can result in misreading data, throwing an exception, or silently producing invalid state.
4. There is no mechanism that automatically saves a new field just because you added a field to the class.
5. The `public Product()` constructor is used during deserialization; the two-argument constructor does not run automatically during that process.

## 4. Comparing Serializable and Externalizable

| Aspect | Default `Serializable` | `Externalizable` |
|---|---|---|
| Interface | Marker interface, no required methods | Extends Serializable; has two required methods |
| Who decides which fields are saved? | Default serialization mechanism, customizable via hooks | `writeExternal` itself |
| Who reads the state? | Default mechanism, customizable via `readObject` | `readExternal` itself |
| Constructor when restoring a normal class | Does not invoke the Serializable class's regular constructor like `new` | Invokes the `public` no-arg constructor of the Externalizable class |
| `transient` and `static` | Not saved by default field rules | Not decided automatically; values can be written explicitly |
| Reordering fields in source code | Does not force you to manually read/write in that order | Written protocol depends on the order/types chosen by the author |
| Adding a new field | Default serialization compatibility rules may support some changes | Must manually design how to recognize and read old/new versions |
| Object identity/cycles via `writeObject` | Has handle mechanism | Still present when using the appropriate object stream mechanism |
| Flexibility | Less code for simple models | Full control over encoding, validation, and data field selection |
| Risks | Versioning, object graph, untrusted input | Similar risks **plus protocol bugs from manual implementation** |

**Externalizable is not automatically faster, smaller, or safer than Serializable.** It can reduce payload size if you intentionally omit unnecessary fields, yet it still carries Java serialization metadata/handles and adds maintenance effort for manual encoding. Benchmark if performance matters.

## 5. Why Is a Public No-Argument Constructor Required?

Unlike regular `Serializable` classes, Java deserialization of Externalizable works conceptually as follows:

```text
Read class metadata from object stream
        |
        v
Find/load compatible class
        |
        v
Call public no-argument constructor
        |
        v
Instance is created
        |
        v
Call readExternal(ObjectInput)
        |
        v
Instance with restored state
```

Because the constructor actually runs:

- Field initializers and logic inside the no-argument constructor can execute.
- Afterward, `readExternal` can overwrite the initialized values.
- If a field is **not read** in `readExternal`, it can retain the value set by the constructor (or the default value if the constructor does not assign it).
- A constructor with side effects (DB connections, spawning threads, writing files, mutating global state...) poses risks during deserialization. **Keeping this constructor simple and side-effect-free** is an important recommendation.
- If the class lacks an accessible public no-argument constructor as required by the API, reading will fail, typically with `InvalidClassException` or a related error.

**Incorrect** example:

```java
class Bad implements Externalizable {
    private static final long serialVersionUID = 1L;

    private String value;

    public Bad(String value) {
        this.value = value;
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeUTF(value);
    }

    @Override
    public void readExternal(ObjectInput in) throws IOException {
        value = in.readUTF();
    }
}
```

The class above lacks `public Bad()`. This illustrative snippet assumes imports for `Externalizable`, `ObjectOutput`, `ObjectInput`, and `IOException`. Writing an instance may still produce bytes, but reading it back via Java serialization lacks the required constructor.

### Nested Classes Also Require Attention

When writing an Externalizable class inside another class, **`public static class ... implements Externalizable`** is usually clearer than a non-static inner class. A non-static inner class carries an implicit reference to the outer instance and an implicit outer-parameter constructor mechanism, making the no-argument constructor requirement easy to violate.

## 6. All Data Lives in the Protocol You Write

With default `Serializable`:

```java
private int age;
private String name;
private transient String token;
```

the default serialization mechanism knows to handle `age` and `name`, skipping `token`.

With `Externalizable`, you decide:

```java
@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeInt(age);
    out.writeUTF(name);
    // token is not written because we do NOT call write for it.
}
```

`transient` **does not automatically block** you from writing a field directly inside `writeExternal`:

```java
private transient String token;

@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeUTF(token); // STILL puts token into the stream if called!
}
```

Therefore, do not rely on `transient` as an absolute safeguard against sensitive data leaks when an Externalizable class has a custom protocol. Inspect the `writeExternal` code to see what is actually written.

Similarly, `static` is not default instance state, yet a programmer **can** manually read a static field and write its value. That does not mean you should do so: shared state is usually unsuitable to store per-object.

## 7. Primitives, Strings, and Objects: Choosing Method Pairs

| Write with ObjectOutput | Read with ObjectInput | Data Type |
|---|---|---|
| `writeInt(value)` | `readInt()` | 4 bytes encoding an int per DataOutput/DataInput protocol |
| `writeLong(value)` | `readLong()` | long |
| `writeBoolean(value)` | `readBoolean()` | boolean |
| `writeDouble(value)` | `readDouble()` | double |
| `writeUTF(value)` | `readUTF()` | String using **modified UTF-8** with length prefix |
| `writeObject(ref)` | `readObject()` | Java object/reference graph |
| `write(byte[])` | `readFully(byte[])` | Byte sequence with a **known prior** size |

Some API pairs can be **asymmetric** if misused. For example, `writeUTF(name)` is **not** equivalent to `writeObject(name)`, even though both transmit the same string content.

### writeUTF Is Not "Write Arbitrary-Length UTF-8"

`DataOutput.writeUTF` uses Java's **modified UTF-8** with a 16-bit unsigned length limit. A string whose modified UTF-8 representation exceeds 65,535 bytes can cause `writeUTF` to throw `UTFDataFormatException`. If you need very large strings, define your own UTF-8 encoding, a bounded `int`/`long` length prefix, and write raw bytes; on read, check the length before allocating.

Example of a large text schema (illustrative, not a standalone method):

```java
byte[] utf8 = name.getBytes(StandardCharsets.UTF_8);
if (utf8.length > MAX_NAME_BYTES) {
    throw new IOException("Name too long");
}
out.writeInt(utf8.length);
out.write(utf8);

// On read:
int length = in.readInt();
if (length < 0 || length > MAX_NAME_BYTES) {
    throw new InvalidObjectException("Invalid name length");
}
byte[] raw = new byte[length];
in.readFully(raw);
name = new String(raw, StandardCharsets.UTF_8);
```

Here `name`, `out`, `in`, and `MAX_NAME_BYTES` must be declared in the class. The example uses `new String(..., UTF_8)`, which may replace malformed UTF-8 bytes with replacement characters per decoder behavior. If the protocol must **reject malformed Unicode**, use `CharsetDecoder` with `CodingErrorAction.REPORT` and handle errors.

### Null Handling

`writeUTF(null)` is not a valid way to write a null string. Choose a schema such as:

```java
out.writeBoolean(name != null);
if (name != null) {
    out.writeUTF(name);
}

// Read in the exact same order:
boolean exists = in.readBoolean();
name = exists ? in.readUTF() : null;
```

Or use `writeObject`/`readObject` for a String reference, where null is handled naturally by the object stream. Choose based on size, representation, and type control requirements.

## 8. Ordering Is Part of the Data Contract

Suppose the writer does:

```java
out.writeInt(version);
out.writeUTF(code);
out.writeLong(timestamp);
out.writeBoolean(active);
```

The reader **must read in the same order and representation**:

```java
int version = in.readInt();
String code = in.readUTF();
long timestamp = in.readLong();
boolean active = in.readBoolean();
```

If the reader calls `readLong()` at the position storing the String, the stream will be misinterpreted; the result may be an exception or garbage values before failing later.

A Java object serialization file may be read by a different class version than the one that wrote it earlier. The `Externalizable` author must build compatibility into the protocol themselves. Do not rely on field declaration order or appending fields at the end of a class as with some default serialization cases.

## 9. Complete Java 17+ Program: Externalizable Cycle + Object Graph

The following example simultaneously demonstrates:

1. `writeExternal`/`readExternal` manually writing/reading version, name, and reference.
2. Public no-arg constructor being called during deserialization.
3. `transient cache` **not being written**, while keeping the value created by the constructor during reading.
4. Two nodes forming a cycle `A → B → A`; the cycle is preserved.
5. Writing the same root **twice** on the same ObjectOutputStream and reading twice can still return the same reference via stream handles.
6. Restored objects are different instances from the original objects in the JVM.
7. Data generated in memory, **not** received from an untrusted source.

Save with the exact filename **`ExternalizableGraphDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.Externalizable;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInput;
import java.io.ObjectInputStream;
import java.io.ObjectOutput;
import java.io.ObjectOutputStream;
import java.io.Serial;

public class ExternalizableGraphDemo {

    public static class Node implements Externalizable {
        @Serial
        private static final long serialVersionUID = 1L;

        private static int publicNoArgCalls = 0;

        private String name;
        private Node next;
        private transient String cache;

        // Required: public and no-arg.
        public Node() {
            publicNoArgCalls++;
            cache = "from-no-arg";
        }

        public Node(String name) {
            this.name = name;
            this.cache = "live-only";
        }

        @Override
        public void writeExternal(ObjectOutput out) throws IOException {
            out.writeInt(1);        // Version of custom protocol.
            out.writeUTF(name);
            out.writeObject(next);  // Preserves object identity/handles mechanism.
        }

        @Override
        public void readExternal(ObjectInput in)
                throws IOException, ClassNotFoundException {
            int formatVersion = in.readInt();
            if (formatVersion != 1) {
                throw new InvalidObjectException(
                        "Unsupported format version: " + formatVersion);
            }

            String restoredName = in.readUTF();
            Object restoredNext = in.readObject();

            if (restoredName.isBlank()) {
                throw new InvalidObjectException("Empty name");
            }
            if (restoredNext != null && !(restoredNext instanceof Node)) {
                throw new InvalidObjectException("Invalid next node");
            }

            name = restoredName;
            next = (Node) restoredNext;

            // cache remains "from-no-arg": not written/read here.
        }
    }

    public static void main(String[] args) throws Exception {
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;

        byte[] bytes;
        try (ByteArrayOutputStream memory = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(memory)) {
            output.writeObject(a);
            output.writeObject(a); // Same root instance.
            output.flush();
            bytes = memory.toByteArray();
        }

        Node restoredFirst;
        Node restoredSecond;
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            restoredFirst = (Node) input.readObject();
            restoredSecond = (Node) input.readObject();
        }

        System.out.println("Name: " + restoredFirst.name);
        System.out.println("Cycle restored: "
                + (restoredFirst.next.next == restoredFirst));
        System.out.println("Shared root: "
                + (restoredFirst == restoredSecond));
        System.out.println("No-arg constructor calls: "
                + Node.publicNoArgCalls);
        System.out.println("Transient cache: " + restoredFirst.cache);
        System.out.println("Restored differs: " + (restoredFirst != a));
    }
}
```

Compile and run in the directory containing the code:

```bash
javac ExternalizableGraphDemo.java
java ExternalizableGraphDemo
```

**Exact expected stdout in a single JVM running the standalone program:**

```text
Name: A
Cycle restored: true
Shared root: true
No-arg constructor calls: 2
Transient cache: from-no-arg
Restored differs: true
```

Detailed analysis:

- `new Node("A")` and `new Node("B")` call the parameterized constructor, **not** incrementing `publicNoArgCalls`.
- Serializing root A calls `writeExternal(A)` → writes version 1, name A, and a reference to B; for B, `writeExternal(B)` writes version 1, name B, and a reference back to A.
- `ObjectOutputStream` has a handle mechanism for object A, so the B→A reference does not cause infinite recursion.
- On read, A and B are two new Externalizable instances; the `public Node()` constructor is called for each instance, so the counter becomes 2.
- `readExternal` sets `name` and `next` from the stream; it **does not overwrite** `cache`, so the value initialized by the constructor is preserved.
- `restoredFirst.next.next == restoredFirst` confirms the cycle was restored.
- The second `output.writeObject(a)` on the same stream reuses A's handle; the two `readObject` calls return the same restored root, so `restoredFirst == restoredSecond`.
- `restoredFirst != a` shows the restored object does not share identity with the original object.

**Do not use a static counter as a shared metric across multiple processes or concurrent runs in production.** In this standalone example, it illustrates the constructor; in real applications, constructors with side effects or global state easily cause concurrency/reentrancy bugs.

## 10. Reference and Cycle Preservation Mechanism

When `Externalizable.writeExternal` calls `out.writeObject(reference)`, ObjectOutputStream continues using its object handles mechanism. This is especially important for:

```text
A.next = B
B.next = A

writeObject(A)
  ├── writeExternal(A)
  │      ├── writeInt(1)
  │      ├── writeUTF("A")
  │      └── writeObject(B)
  │             └── writeExternal(B)
  │                    └── writeObject(A) -> reference/handle
  └── complete root A
```

When reading, Java creates instances and manages references enough to reconstruct cyclic graphs according to stream rules. However, **`readExternal` logic must avoid arbitrary operations on objects whose state has not finished reading**. In a cycle, a reference may point to an object still partially constructed. For example, if `B.readExternal` tries to read `A.name` before `A.readExternal` finishes, A's name may still be unassigned.

Therefore:

- Write references with `writeObject` and read with `readObject` to leverage handle tracking.
- Inside `readExternal`, prefer storing references and validating appropriate types, avoiding complex business calls on an incomplete graph.
- Do not assume all referenced objects have finished validation at the moment a reference is assigned.
- If you need to validate invariants across multiple nodes, organize a validation step after the entire root graph has finished reading.
- If you replace `writeObject` with manual recursive calls like `next.writeExternal(out)`, you can bypass handle tracking and **create infinite recursion** for cyclic graphs.

### Object Identity Differs from Object Equality

When checking reference preservation:

- `a == b`: are they the exact same instance in the JVM?
- `a.equals(b)`: are their values equivalent per the class's logic?

Two instances with the same `name` may still not be the same object. Use `==` to test aliasing/cycles, not just `equals`.

## 11. Externalizable Does Not Automatically Write Every Field

A class has:

```java
private String id;
private int count;
private List<String> tags;
private transient String sessionToken;
```

If `writeExternal` only calls:

```java
out.writeUTF(id);
out.writeInt(count);
```

then:

- `id` and `count` are written according to the custom schema.
- `tags` is not written; after deserialization, its value depends on the `public` constructor and `readExternal` logic.
- `sessionToken` is not written **because the author did not call write for this field**. If the author writes it manually despite `transient`, the data still appears in the stream.
- Adding `tags` to the Java class does not make the stream automatically include tags.

When `tags` needs to be persisted, you can explicitly write a bounded count and each element, or `out.writeObject(tags)` (only when the types and graph are safe, trusted, and same-version). Explicit custom encoding usually controls migration and size better; `writeObject` is convenient but pulls in Java serialization classes/graphs.

## 12. Explicit Versioning: Managing the Protocol Yourself

When using `Externalizable`, **`serialVersionUID` and your custom payload version are two distinct layers**:

- `serialVersionUID` is used by Java serialization to partially check class compatibility when reading the object descriptor.
- `formatVersion` written by you via `writeInt` is a component inside `writeExternal`'s custom protocol.

V1 example:

```java
out.writeInt(1);
out.writeUTF(code);
out.writeInt(quantity);
```

V2 wants to add `price`:

```java
out.writeInt(2);
out.writeUTF(code);
out.writeInt(quantity);
out.writeLong(priceInCents);
```

A V2 reader can read both:

```java
int version = in.readInt();
if (version != 1 && version != 2) {
    throw new InvalidObjectException("Unsupported version: " + version);
}

code = in.readUTF();
quantity = in.readInt();
priceInCents = version >= 2 ? in.readLong() : 0L;
```

These are **illustrative snippets of the same custom format**, not two writer versions placed in one class at the same time. All variables must be declared; the reader should validate code/quantity/price immediately after reading. Note that if data was written by V2 and a V1 reader reads it, the V1 reader **may not know how to handle v2** and should reject it rather than misreading bytes.

### How to Attach serialVersionUID?

With Externalizable, you should still declare:

```java
@Serial
private static final long serialVersionUID = 1L;
```

`@Serial` is available in Java 17. The corresponding UID must be `static final long` with that exact name. When changing the payload schema while still wanting one class to accept older versions via `readExternal` logic, you can keep a compatible UID and branch on `formatVersion`. If you intentionally make an incompatible class change, a new UID can cause older streams to be rejected with `InvalidClassException`.

**Keeping the old UID does not automatically guarantee V1/V2 schema compatibility.** The reader must actually parse every promised supported version correctly, test real files, and handle defaults/validation.

### Check Version Errors Early

Reading `version` first and validating the supported range before processing the rest avoids misreading types under an entirely different schema. Do not ignore an unknown version and guess the remaining bytes under the current format.

## 13. Data Ordering and Subtle Bugs

Wrong ordering can produce hard-to-diagnose errors. Suppose the writer calls `writeInt(5)` then `writeLong(7L)`, while the reader calls `readLong()` then `readInt()`:

- An exception does not necessarily occur at the first byte.
- Values can be stitched together from bytes of two fields.
- Subsequent read positions are no longer aligned to expected boundaries.
- The actual error may appear much later when a type token, length, or trailer is misinterpreted.

**Writing a round-trip unit test is necessary but not sufficient.** If both writer and reader make the same corresponding mistake, a same-version round-trip test can still pass. You need cross-version verification using **golden files** saved from previous versions and tests for invalid inputs.

Testing checklist:

1. Minimal object and full object.
2. Null, empty strings, Unicode, very long strings.
3. Negative numbers, large numbers, overflow, boundary values.
4. Reference graph with the same object appearing multiple times.
5. Graph with cycles.
6. Stream truncated mid-primitive or mid-object.
7. Unsupported `formatVersion`.
8. Class with/without public no-arg constructor.
9. Errors when writing multiple consecutive objects in the same stream.
10. Old/new versions and UID stability.

## 14. What Exceptions Can writeExternal/readExternal Throw?

| Scenario | Exception/Error Category |
|---|---|
| Corrupted stream, truncated file, or transport error | `IOException`, `EOFException`, `StreamCorruptedException` depending on context |
| Invalid custom payload format | Can explicitly throw `InvalidObjectException` |
| `readObject()` encounters a class missing from classpath | `ClassNotFoundException` |
| Externalizable class fails constructor requirement | Typically `InvalidClassException` or related error |
| `writeObject(ref)` encounters a non-Serializable object | `NotSerializableException` |
| Incompatible class descriptor/UID | `InvalidClassException` |
| Invalid/overlong modified UTF-8 data | `UTFDataFormatException` |
| Wrong object cast after `readObject` | `ClassCastException` (unchecked) |
| Java input filter rejects class/graph | Can result in `InvalidClassException` |

When `readExternal` throws an error:

- Do not use the partially constructed new object as a valid domain object.
- Do not try to continue reading from a guessed position without a clear recovery protocol.
- Log or return an error with file/request/format version context, without printing sensitive data.
- If reading from an untrusted source, prefer **not using native deserialization**; exception handling does not eliminate risks from object creation before the error occurs.

## 15. Custom Formats and Resource Limits

The control of Externalizable lets you check data before allocating:

```java
int itemCount = in.readInt();
if (itemCount < 0 || itemCount > 10_000) {
    throw new InvalidObjectException("Invalid item count");
}
List<String> items = new ArrayList<>(itemCount);
for (int i = 0; i < itemCount; i++) {
    items.add(in.readUTF());
}
```

This is an illustrative snippet requiring imports for `ArrayList`, `List`, `InvalidObjectException`, `ObjectInput` and declaration of `in`. Bounding the count before creating `ArrayList` is good, but:

- Each `String` can still be large; you need a policy for total bytes/strings.
- If the protocol allows nested objects, you must control depth/reference count.
- Many concurrent read requests can add up to large memory usage; limit concurrency.
- I/O from network streams can be slow, requiring timeouts/backpressure and closing resources when quotas are exceeded.
- Truncated input must report an error clearly rather than silently restoring an incomplete list.
- `readUTF` has its own limit; protocols writing raw UTF-8 manually need explicit bounds.

## 16. How Does This Differ from Serializable's readObject/writeObject Hooks?

Two models are often confused:

### A. Serializable with Custom Hooks

```java
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    // Write custom part if any.
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Validate/restore custom part if any.
}
```

These special `private` methods belong to regular `Serializable` classes and are recognized by the serialization mechanism; you can preserve default fields via `defaultWriteObject`/`defaultReadObject`.

### B. Externalizable with a Public Contract

```java
@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeInt(1);
    out.writeUTF(name);
}

@Override
public void readExternal(ObjectInput in)
        throws IOException, ClassNotFoundException {
    int version = in.readInt();
    if (version != 1) {
        throw new InvalidObjectException("Bad version");
    }
    name = in.readUTF();
}
```

`writeExternal`/`readExternal` must be **public** because they implement interface methods. You decide the payload written; **`defaultWriteObject` is not a required step of Externalizable**, and the `ObjectOutput` interface does not provide `defaultWriteObject()` like `ObjectOutputStream`.

**Do not declare `private readExternal` expecting the runtime to call it like `readObject`.** That is not a valid implementation of the interface.

### When to Choose Which Model?

- Simple model with many fields needing minimal code: default `Serializable` may suffice in trusted internal environments.
- Need a few validations/hooks while keeping most default fields: custom `readObject/writeObject` can make sense.
- Want tight control over ordering, versioning, and encoding of the payload inside a Java object stream: `Externalizable`.
- Need a cross-language format, long-term versioning, or input from untrusted clients: **do not default to either**; prefer DTOs/schemas and an appropriate serializer.

## 17. Security: Externalizable Is Not Safe Against Malicious Bytes

`Externalizable` can mislead authors into thinking "manual field reading is safer." Yet it **is still triggered via `ObjectInputStream.readObject()`**, with class descriptors, instance instantiation, and related hooks. That still carries native Java deserialization risks.

Dangerous scenario:

```java
// DO NOT DO THIS with bytes sent by an untrusted client.
try (ObjectInputStream in = new ObjectInputStream(networkInput)) {
    Object value = in.readObject();
}
```

Reasons:

- Decoding can instantiate classes on the classpath with unintended behavior.
- An Externalizable's public no-arg constructor can run and cause side effects before the payload is validated.
- `readExternal` can call `in.readObject()` and pull in an entire complex graph.
- Data can be crafted to consume CPU, memory, or cause stack/resource exhaustion.
- Checking `instanceof` after `readObject` can be too late to block behavior during the deserialization phase.

Principles:

1. Avoid Java native deserialization at **trust boundaries**: public HTTP payloads, externally submitted data, files from untrusted parties.
2. Prefer simple data formats, DTOs/schemas, controlled parsers, and limits on bytes/depth/objects.
3. If legacy Java serialization data comes from a trusted source, restrict classes/arrays/depth/references via `ObjectInputFilter` where appropriate.
4. Validate data invariants and check versions in `readExternal`, not relying solely on the constructor.
5. Do not let constructors or `readExternal` perform irreversible side effects while the payload is unverified.
6. Protect file sources and access permissions, with checksums/cryptographic signatures if external integrity verification is needed; CRC/hashes alone usually do not prove a trusted source.

### ObjectInputFilter Example (for API Awareness Only)

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=100;maxarray=10000;maxbytes=1048576;"
      + "com.example.model.*;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object object = in.readObject();
}
```

This is an illustrative snippet requiring `ObjectInputFilter`, `ObjectInputStream`, an `InputStream source`, and exception handling. Package `com.example.model` is just an example; for a graph containing `ArrayList`/`String`/other JDK classes, the real allowlist must be determined from the model and tested against filter semantics.

A filter helps **reduce** risk in certain scenarios, but **does not prove any untrusted input is safe**. Nor does it replace I/O source limits, per-request quotas, timeouts, or application-layer security controls.

## 18. Impact of Inheritance and Superclass State

An Externalizable class can inherit fields and behavior from a superclass. However, **`writeExternal` must decide how to store all fields that need to persist**, including state owned by the superclass that the class can access through a valid API.

Example:

```java
class Base {
    protected int id;

    Base() {
        id = -1;
    }
}

public class Child extends Base implements Externalizable {
    private static final long serialVersionUID = 1L;

    private String name;

    public Child() {
        super();
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeInt(id);
        out.writeUTF(name);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        id = in.readInt();
        name = in.readUTF();
    }
}
```

This is an illustrative class example; put `Child` in `Child.java` alongside a suitable `Base` and import interfaces/exceptions. `Base` is not Serializable, yet `Base()` runs via `Child()` when the Externalizable object is constructed. Then `readExternal` restores `id` from the stream. If `Child.writeExternal` **does not** write `id`, that state only retains the value initialized by the constructor or other application logic.

This differs from assuming superclass state is automatically saved completely as in default serialization. For superclasses with complex invariants, provide clear APIs to get/set persistable state.

## 19. Writing and Reading Multiple Externalizable Objects in One Stream

`ObjectOutputStream` manages a **stream-scoped** handle table, not just per call:

```java
try (ObjectOutputStream out = new ObjectOutputStream(output)) {
    out.writeObject(a);
    out.writeObject(b);
    out.writeObject(a);
}
```

When reading in the exact same order:

```java
try (ObjectInputStream in = new ObjectInputStream(input)) {
    Object first = in.readObject();
    Object second = in.readObject();
    Object third = in.readObject();
    System.out.println(first == third);
}
```

These are two standalone illustrative snippets, with `output` and `input` as matching streams; `a`/`b` must be declared. If the same instance A is written again without resetting the handle mechanism, the third object may be a reference to the first object, so the identity check returns true.

### Trap of Mutating an Object and Writing It Again

Suppose:

```java
out.writeObject(person);
person.setName("New name");
out.writeObject(person);
```

In the same stream, the second write may **write only a reference** and not call `writeExternal` again to save the updated version. Do not build an append snapshot log by repeating `writeObject(sameInstance)` hoping each call writes full state.

If you want a fresh handle-independent phase within the same ObjectOutputStream, `out.reset()` can be used deliberately; interaction with the reader and versioned format must be explicitly designed. `writeUnshared`/`readUnshared` are different APIs with specific semantics and do not automatically deep-clone every reference inside the graph.

## 20. File Durability and Atomicity Are Not Inside Externalizable

Successful serialization does not mean a file is durably saved or an "atomic snapshot update" occurred.

If writing directly:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(target))) {
    out.writeObject(root);
}
```

a failure midway can leave the old target file truncated or containing an incomplete object stream. For important data:

1. Create a separate temporary file, ideally in the same directory as the target.
2. Write the entire graph and close ObjectOutputStream successfully.
3. If the task requires high durability, sync data/metadata using an appropriate filesystem mechanism and understand its limits.
4. Validate the required format/snapshot before publishing.
5. Replace the target using move/rename per provider atomic support; if atomicity is a strict requirement, **do not silently fall back** to a non-atomic approach while keeping the same guarantee.
6. Have backup/recovery and cleanup for leftover temp files if the process crashes.

`ObjectOutputStream.close()` is not a system-wide fsync command; `Files.move(..., ATOMIC_MOVE)` only addresses part of name-update atomicity if supported and still has durability/multi-writer limitations.

## 21. Testing and How to Choose Externalizable

Choose `Externalizable` when **you have a specific reason**:

- Need exact control over state data written into a native Java object stream.
- Want to avoid saving unnecessary large graph parts.
- Want a custom payload with versioning, lengths, and validation owned by the class itself.
- Need compatibility with data saved by a trusted internal Java application.

Do not choose it merely because:

- You want to transmit public network payloads.
- You expect cross-language compatibility.
- You assume writeExternal always compresses better, is safer, or is faster.
- You want to "encrypt" data (serialization is not encryption).
- You want a database with transactions, queries, migrations, or indexing.

### Code Review Checklist

- [ ] Does the class actually implement `Externalizable`, with a **public no-arg constructor**?
- [ ] Are both `writeExternal` and `readExternal` `public` with exact signatures?
- [ ] Are writes and reads in the **exact same order with matching data types**?
- [ ] Is there an explicit `formatVersion` when long-term compatibility is required?
- [ ] Is there an intentionally fixed `serialVersionUID`?
- [ ] Are `null`, empty values, UTF, lengths, and out-of-range values handled?
- [ ] Are sensitive fields prevented from being inadvertently written even if marked transient?
- [ ] Are there validation/invariants after reading, and no dangerous side effects from the constructor?
- [ ] Are alias/cycle graphs and references to non-Serializable classes tested?
- [ ] Are `IOException`, `ClassNotFoundException`, `InvalidClassException`, and corrupted streams handled?
- [ ] Is untrusted data not deserialized; are sources/graphs restricted when using trusted legacy data?
- [ ] If persisting to files, are write, commit, and recovery strategies separated?

## 22. Common Mistakes

1. **Missing public no-arg constructor:** Externalizable deserialization fails.
2. **Defining readExternal/writeExternal as private:** does not properly implement the interface.
3. **Confusing readExternal with the private readObject hook:** two different protocols/extension points.
4. **Failing to write all fields needed for restoration:** values after reading may stay at default/constructor state.
5. **Assuming transient prevents a custom writer from writing a token:** calling `writeUTF(token)` still stores the token.
6. **Reading primitives/objects out of order:** corrupted data or undecodable stream.
7. **Using writeUTF for overly long strings:** has a 65,535-byte modified UTF-8 length limit.
8. **Forgetting to encode null explicitly:** `writeUTF(null)` is not a valid null encoding.
9. **Not checking the custom payload version:** new/old readers misread the schema.
10. **Assuming a matching UID suffices for compatibility:** the reader must still understand the payload bytes.
11. **Manually recursing writeExternal on cyclic reference graphs:** bypasses stream object handles and can loop infinitely.
12. **Not managing partially constructed graphs:** readExternal can see references to incomplete objects.
13. **Thinking reading an object means full validation already occurred:** invariants/snapshots must be checked after restoration.
14. **Writing the same instance multiple times expecting each to be a fresh snapshot:** the handle table may write references.
15. **Letting constructors perform I/O/side effects during deserialization:** dangerous for security and lifecycle.
16. **Accepting native serialization bytes from untrusted clients:** security and resource exhaustion risk.
17. **Overwriting a single snapshot file directly:** a crash can destroy old data.
18. **Not testing cross-version/golden files:** editing reader/writer code together can mask bugs.
19. **Assuming good performance just from fewer fields:** measure on realistic object graphs instead of guessing.
20. **Treating Externalizable as a standard interchange format outside Java:** it remains tied to Java object serialization.

## 23. Practice Exercises

**Exercise 1 — Write a custom protocol for a Record.** Create a class `Report implements Externalizable` with `id`, `createdAtEpochMillis`, `status`. Write version 1, String id and long timestamp, and a byte code representing status. Read it back and validate the status domain; test a wrong-version stream.

**Exercise 2 — Add a field in version 2.** Add an optional `source`. Define V1 without source, and V2 writing source with a boolean presence flag. The V2 reader must read both V1 and V2 bytes without over-reading V1.

**Exercise 3 — Test the constructor.** Assign `"initialized"` to a transient field in the public no-arg constructor; do not write it in `writeExternal`. After deserialization, verify the value remains intact. Remove the constructor and predict the exception.

**Exercise 4 — Shared object graph.** A `Group` has two fields pointing to the same `Node`. Write both via `out.writeObject`, read them back, and verify `first == second`. Then form a two-Node cycle to test cycles.

**Exercise 5 — Ordering bug.** Write `int` then `long`, but attempt to read in reverse order. Observe the error or nonsensical values; fix the protocol and write a golden-bytes test rather than only testing writer/reader from the same source.

**Exercise 6 — Invalid input.** Write `count=-1` or a huge `count` into a custom format. The reader must detect it before allocating the list. Continue testing long strings, unsupported versions, and truncated streams.

**Exercise 7 — Evaluate alternatives.** Design a 5-field DTO to store configuration. Compare native Java Externalizable against JSON or Protocol Buffers in terms of versioning, diff reviewability, security risk, and language compatibility.

## 24. Self-Check Questions

**Question 1.** How does `Externalizable` differ from the `Serializable` marker?  
**Answer:** `Externalizable` declares `writeExternal` and `readExternal` so the class actively writes/reads its payload; it still extends `Serializable`.

**Question 2.** Why does an Externalizable class need a public no-arg constructor?  
**Answer:** Deserialization uses that constructor to instantiate the object before calling `readExternal`.

**Question 3.** `writeExternal` omits the `age` field; after reading, is it automatically restored by the default field mechanism?  
**Answer:** No. The value depends on the constructor/initializers and `readExternal` logic, because Externalizable does not automatically write default fields.

**Question 4.** Can a `transient password` field still be written to the stream?  
**Answer:** Yes, if `writeExternal` explicitly writes it. `transient` is not a mechanism that blocks a custom writer.

**Question 5.** If you wrote `out.writeInt(12)`, should you read it with `readLong` to preserve enough bytes?  
**Answer:** No. You must read with the matching `readInt` and the exact schema order.

**Question 6.** Can A→B→A cycles be preserved with Externalizable?  
**Answer:** Yes, if using `out.writeObject`/`in.readObject` for references and a suitable serialization contract; the handle mechanism manages cycles.

**Question 7.** If `readExternal` in B reads a reference to A currently being restored, are all fields of A necessarily complete?  
**Answer:** Not necessarily. Do not rely on complete object state while resolving cyclic graphs.

**Question 8.** Do `serialVersionUID=1L` and `formatVersion=2` conflict with each other?  
**Answer:** No. The UID belongs to Java object stream class compatibility; formatVersion is your custom payload version.

**Question 9.** Why not use Externalizable to deserialize requests from the internet?  
**Answer:** It still relies on Java native deserialization, which can construct classes and run dangerous constructors/hooks from untrusted bytes.

**Question 10.** Does calling `ObjectOutputStream.writeObject(a)` twice always write a fresh state snapshot the second time?  
**Answer:** No. The stream has a handle table; the second call may write only a reference.

**Question 11.** Does `ObjectOutputStream.close()` guarantee the snapshot file is durably flushed across power loss?  
**Answer:** No. You need filesystem-level durability, atomic replacement, and recovery strategies.

**Question 12.** When does Externalizable make more sense than a public self-describing format?  
**Answer:** When a trusted internal Java application has a specific reason to control payloads inside Java object serialization; it is not the default for public/cross-language APIs.

## 25. Key Takeaways

- **`Externalizable` extends `Serializable` and requires public `writeExternal(ObjectOutput)` + `readExternal(ObjectInput)`.**
- **A `public` no-argument constructor is required** to restore a normal instance.
- **Every field to persist must be explicitly written/read by the class**; `transient`/`static` do not stop a custom writer from writing data.
- **Payload ordering, types, and versioning are the application's own contract.** `serialVersionUID` does not replace a custom format version.
- **Object graphs, aliases, and cycles can still be preserved** via `writeObject`/`readObject` and ObjectOutputStream handles.
- **Do not use native Java deserialization for untrusted bytes.** Validation, ObjectInputFilter, and resource limits are complementary, not a substitute for trust-boundary design.
- Externalizable **is not a database, transaction engine, cross-language format, or security encryption**; API choices must be grounded in actual requirements.

### Java SE 17 API Documentation

- [Externalizable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html)
- [ObjectOutput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutput.html)
- [ObjectInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInput.html)
- [ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html)
- [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html)
