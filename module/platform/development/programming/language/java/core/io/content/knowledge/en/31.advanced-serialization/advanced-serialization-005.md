# Externalizable, writeExternal, and readExternal in Java Serialization

## 1. Overview and Goals

In Java Core I/O, `java.io.Externalizable` is an object serialization mechanism that lets **the object's own class actively write and read its data representation**. It extends `Serializable` but differs significantly from default serialization:

- Standard `Serializable`: `ObjectOutputStream` can automatically write eligible instance fields, excluding `static` and `transient`, according to Java serialization rules.
- `Externalizable`: the runtime calls **`writeExternal(ObjectOutput)`** when writing and **`readExternal(ObjectInput)`** when reading. The programmer decides what to write, in what order, and how to restore it.
- When deserializing a regular `Externalizable` class, Java requires a **`public` no-arg constructor** to instantiate the object before invoking `readExternal`.
- Managing data yourself **does not discard `ObjectOutputStream`'s object handle management** when calling `writeObject`/`readObject`. Reference graphs and aliases can be preserved, including cycles, if the protocol is designed properly.
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

This is a simplified API declaration for explanation; Java already provides this interface in `java.io`—**do not redefine it in your project**.

Two key methods:

| Method | When Does It Run? | Function |
|---|---|---|
| `writeExternal(ObjectOutput out)` | When `ObjectOutputStream` writes a new Externalizable instance | Explicitly writes fields/version/records in the order you choose |
| `readExternal(ObjectInput in)` | After the instance is created for deserialization | Reads the exact representation produced by `writeExternal` and rebuilds state |

`ObjectOutput` provides operations such as `writeInt`, `writeLong`, `writeBoolean`, `writeUTF`, `writeObject`, and `write(byte[])`. `ObjectInput` provides symmetric operations `readInt`, `readLong`, `readBoolean`, `readUTF`, `readObject`, `readFully`, etc.

**Do not treat `ObjectOutput` as a JSON writer.** You are producing a sequence of byte values per your application's own contract inside Java's object serialization stream.

### Externalizable Does Not Mean the Class Is Written Outside Java Serialization

`ObjectOutputStream.writeObject(externalizableObject)` still manages the object stream, class descriptors, identity handles, and related decoding machinery. `writeExternal` is responsible for the class's state payload, not replacing the entire stream format or class lookup by name when reading.

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

    // REQUIRED public and no-arg for deserialization mechanism.
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

Save as `Product.java` if you want to compile this class standalone. The snippet above is a **class definition** without a `main` method to run. It assumes `code` is non-null and within `writeUTF` limits; advanced examples must validate input data.

What you must guarantee yourself:

1. `writeExternal` writes `code` **before** `quantity`.
2. `readExternal` reads `code` with `readUTF` **before** `quantity` with `readInt`.
3. If you change the order or type of a component without updating the reading protocol, you can misread data, throw exceptions, or silently create invalid state.
4. There is no automatic mechanism to save new fields simply because you added a field to the class.
5. The `public Product()` constructor is invoked during deserialization; the two-argument constructor does not automatically run during that process.

## 4. Comparing Serializable and Externalizable

| Aspect | Default `Serializable` | `Externalizable` |
|---|---|---|
| Interface | Marker interface, no required methods | Extends Serializable; two required methods |
| Who decides which fields are saved? | Default serialization mechanism, customizable via hooks | `writeExternal` itself |
| Who reads the state? | Default mechanism, customizable via `readObject` | `readExternal` itself |
| Constructor on restoring normal class | Does not call the Serializable class's regular constructor like `new` | Invokes the Externalizable class's `public` no-arg constructor |
| `transient` and `static` | Not saved by default field rules | Not automatically excluded; values can be written explicitly |
| Reordering fields in source code | Does not force you to manually read/write in that order | Written protocol depends on order/types chosen by the author |
| Adding new fields | Default serialization compatibility rules may accommodate some changes | Must manually design how to detect and read old/new versions |
| Object identity/cycles via `writeObject` | Has handle mechanism | Still present when using the appropriate object stream mechanism |
| Flexibility | Less boilerplate for simple models | Full control over encoding, validation, and field selection |
| Risks | Versioning, object graphs, untrusted input | Same risks **plus protocol bugs from custom code** |

**Externalizable is not automatically faster, smaller, or safer than Serializable.** It can shrink payloads if you deliberately omit unnecessary fields, yet it still carries Java serialization metadata/handles and adds maintenance effort for manual encoding. Always benchmark if performance matters.

## 5. Why Is a Public No-Arg Constructor Required?

Unlike regular `Serializable` classes, Externalizable deserialization conceptually proceeds as:

```text
Read class metadata from object stream
        |
        v
Find/load compatible class
        |
        v
Invoke public no-arg constructor
        |
        v
Instance is created
        |
        v
Invoke readExternal(ObjectInput)
        |
        v
Instance state restored
```

Because the constructor actually runs:

- Field initializers and logic inside the no-arg constructor can execute.
- Afterward, `readExternal` can overwrite those newly initialized values.
- If a field **is not read** in `readExternal`, it can retain the value set by the constructor (or the default value if unassigned).
- A constructor with side effects (DB connections, spawning threads, writing files, mutating global state, etc.) introduces risk during deserialization. **Keeping this constructor simple and side-effect-free** is a critical recommendation.
- If the class lacks an accessible public no-arg constructor as required by the API, reading fails, typically with `InvalidClassException` or a related error.

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

The class above lacks a `public Bad()` constructor. The illustrative snippet assumes imports for `Externalizable`, `ObjectOutput`, `ObjectInput`, and `IOException`. Writing an instance may still produce bytes, but reading it back through Java serialization lacks the required constructor.

### Nested Classes Also Require Attention

When writing an Externalizable class inside another class, **`public static class ... implements Externalizable`** is usually cleaner than a non-static inner class. A non-static inner class carries a synthetic reference to the outer instance and an implicit outer parameter in its constructor, which easily violates the no-arg constructor requirement.

## 6. Everything Resides in the Protocol You Write

With default `Serializable`:

```java
private int age;
private String name;
private transient String token;
```

the default serialization mechanism knows to handle `age` and `name` and skip `token`.

With `Externalizable`, you decide:

```java
@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeInt(age);
    out.writeUTF(name);
    // token is not written because we DO NOT call write for it.
}
```

`transient` **does not automatically block** you from writing a field directly in `writeExternal`:

```java
private transient String token;

@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeUTF(token); // STILL puts token into the stream if called!
}
```

Therefore, do not rely on `transient` as an absolute safeguard against sensitive data when an Externalizable class uses a custom protocol. Audit what `writeExternal` actually writes.

Similarly, `static` is not default instance state, yet a programmer **can** still read a static field and write its value manually. That does not mean you should: shared state rarely belongs inside per-object persistence.

## 7. Primitives, Strings, and Objects: Choosing Method Pairs

| Write with ObjectOutput | Read with ObjectInput | Data Type |
|---|---|---|
| `writeInt(value)` | `readInt()` | 4-byte encoded int per DataOutput/DataInput protocol |
| `writeLong(value)` | `readLong()` | long |
| `writeBoolean(value)` | `readBoolean()` | boolean |
| `writeDouble(value)` | `readDouble()` | double |
| `writeUTF(value)` | `readUTF()` | Length-prefixed string using **modified UTF-8** |
| `writeObject(ref)` | `readObject()` | Java object/reference graph |
| `write(byte[])` | `readFully(byte[])` | Byte sequence with **known length** |

Some API pairs are **asymmetric** if misused. For example, `writeUTF(name)` is **not** equivalent to `writeObject(name)`, even though both transmit the same string content.

### writeUTF Is Not "Write Arbitrary-Length UTF-8"

`DataOutput.writeUTF` uses Java's **modified UTF-8** with a length capped at an unsigned 16-bit integer. A string whose modified UTF-8 representation exceeds 65,535 bytes can cause `writeUTF` to throw `UTFDataFormatException`. If you need very large strings, specify standard UTF-8 encoding, a bounded `int`/`long` length prefix, and raw byte writes; when reading, validate the length before allocating.

Example of a large-text schema (illustrative, not a standalone method):

```java
byte[] utf8 = name.getBytes(StandardCharsets.UTF_8);
if (utf8.length > MAX_NAME_BYTES) {
    throw new IOException("Name too long");
}
out.writeInt(utf8.length);
out.write(utf8);

// When reading:
int length = in.readInt();
if (length < 0 || length > MAX_NAME_BYTES) {
    throw new InvalidObjectException("Invalid name length");
}
byte[] raw = new byte[length];
in.readFully(raw);
name = new String(raw, StandardCharsets.UTF_8);
```

Here `name`, `out`, `in`, and `MAX_NAME_BYTES` must be declared in the class. Note that `new String(..., UTF_8)` may substitute invalid UTF-8 bytes with replacement characters per decoder defaults. If the protocol needs to **reject malformed Unicode**, use a `CharsetDecoder` with `CodingErrorAction.REPORT` and handle errors.

### Null Handling

`writeUTF(null)` is not a valid way to write a null string. Choose a schema such as:

```java
out.writeBoolean(name != null);
if (name != null) {
    out.writeUTF(name);
}

// Read in exact order:
boolean exists = in.readBoolean();
name = exists ? in.readUTF() : null;
```

Alternatively, use `writeObject`/`readObject` for a `String` reference, where null is handled naturally by the object stream. Choose based on size, representation, and type-control requirements.

## 8. Ordering Is Part of the Data Contract

Suppose the writer does:

```java
out.writeInt(version);
out.writeUTF(code);
out.writeLong(timestamp);
out.writeBoolean(active);
```

The reader **must read in the exact same order and representation**:

```java
int version = in.readInt();
String code = in.readUTF();
long timestamp = in.readLong();
boolean active = in.readBoolean();
```

If the reader instead calls `readLong()` where a String is stored, the stream will be misinterpreted; the result may be an exception or garbage values before failing later.

A Java object serialization file may be read by a different class version than the one that wrote it earlier. The `Externalizable` author must build compatibility into the protocol. Do not rely on field declaration order or appending fields at the end of the class as in some default serialization scenarios.

## 9. Complete Java 17+ Program: Externalizable Cycle + Object Graph

The next example simultaneously demonstrates:

1. `writeExternal`/`readExternal` manually writing/reading version, name, and reference.
2. Public no-arg constructor invoked during deserialization.
3. `transient cache` **not written**, while retaining the value initialized by the constructor during reading.
4. Two nodes forming cycle `A → B → A`; the cycle is preserved.
5. Writing the same root **twice** to the same `ObjectOutputStream` and reading twice still returns the same reference via stream handles.
6. Restored objects are distinct instances from the original JVM objects.
7. Data created in memory, **not** received from an untrusted source.

Save with exact name **`ExternalizableGraphDemo.java`**:

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

        // Required public and no-arg.
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
            out.writeObject(next);  // Preserve object identity/handles mechanism.
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

Compile and run in the directory containing the source:

```bash
javac ExternalizableGraphDemo.java
java ExternalizableGraphDemo
```

**Exact expected stdout in a single JVM run of the standalone program:**

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
- Serializing root A calls `writeExternal(A)` → writes version 1, name A, and reference to B; for B, `writeExternal(B)` writes version 1, name B, and back-reference to A.
- `ObjectOutputStream` tracks a handle for object A, so the B→A reference does not cause infinite recursion.
- When reading back, A and B are two new Externalizable instances; `public Node()` runs for each instance, making the counter 2.
- `readExternal` sets `name` and `next` from the stream; it **does not overwrite** `cache`, so the constructor-initialized value remains intact.
- `restoredFirst.next.next == restoredFirst` confirms the cycle was restored.
- The second `output.writeObject(a)` on the same stream reuses A's handle; both `readObject` calls return the same restored root, so `restoredFirst == restoredSecond`.
- `restoredFirst != a` shows the restored object does not share identity with the original object.

**Do not use a static counter as a shared metric across processes or concurrent runs in production.** In this standalone example it illustrates constructor calls; in real applications, constructors with side effects or global mutable state easily cause concurrency/reentrancy bugs.

## 10. Reference and Cycle Preservation Mechanism

When `Externalizable.writeExternal` calls `out.writeObject(reference)`, `ObjectOutputStream` continues using its object handle tracking. This is especially important for:

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
  └── finish root A
```

When reading, Java instantiates objects and tracks references sufficiently to reconstruct cyclic graphs per stream rules. However, **`readExternal` logic must avoid arbitrarily operating on objects whose state has not finished loading**. In a cycle, a reference can point to an object still under construction. For instance, if `B.readExternal` tries to read `A.name` before `A.readExternal` finishes, A's name may still be unassigned.

Therefore:

- Write references using `writeObject` and read with `readObject` to leverage handle tracking.
- Inside `readExternal`, stick to storing references and validating appropriate types; avoid running complex business logic on an incomplete graph.
- Do not assume every referenced object has completed validation at the moment a reference is assigned.
- If you need cross-node invariant checks, structure a validation pass after the entire graph root has finished reading.
- If you replace `writeObject` with manual recursion calling `next.writeExternal(out)` directly, you bypass handle tracking and **create infinite recursion** on cyclic graphs.

### Object Identity Differs from Object Equality

When testing reference preservation:

- `a == b`: are they the exact same instance in the JVM?
- `a.equals(b)`: are their values equivalent per the class's logic?

Two instances with the same `name` may still not be the same object. Use `==` to test aliases/cycles, not just `equals`.

## 11. Externalizable Does Not Automatically Write All Fields

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
- Adding `tags` to the Java class does not automatically include tags in the stream.

When `tags` must be persisted, you can explicitly write a bounded count and each element, or call `out.writeObject(tags)` (only when types and graphs are safe, trusted, and version-compatible). Writing a custom format typically gives better control over migration and size; `writeObject` is convenient but pulls in Java serialization classes and graphs.

## 12. Explicit Versioning: Managing the Protocol Yourself

When using `Externalizable`, **`serialVersionUID` and your custom payload version are two distinct layers**:

- `serialVersionUID` is used by Java serialization to partially check class compatibility when reading the object descriptor.
- `formatVersion` written by you via `writeInt` is a component of `writeExternal`'s custom protocol.

Example V1:

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

Reader V2 can read both:

```java
int version = in.readInt();
if (version != 1 && version != 2) {
    throw new InvalidObjectException("Unsupported version: " + version);
}

code = in.readUTF();
quantity = in.readInt();
priceInCents = version >= 2 ? in.readLong() : 0L;
```

These are **illustrative snippets of the same custom format**—do not place both writer versions into one class simultaneously. All variables must be declared; the reader should validate code/quantity/price immediately after reading. Be mindful that if data was written by V2 and a V1 reader reads it, the V1 reader **may not know how to handle v2** and should reject it instead of misinterpreting bytes.

### How Should serialVersionUID Be Declared?

Even with Externalizable, you should declare:

```java
@Serial
private static final long serialVersionUID = 1L;
```

`@Serial` is available in Java 17. The UID must be `static final long` with that exact name. When changing the payload schema while still wanting one class to accept older versions in `readExternal`, keep a compatible UID and branch on `formatVersion`. If you intentionally make an incompatible class change, a new UID causes old streams to be rejected with `InvalidClassException`.

**Keeping the old UID does not automatically ensure V1/V2 schema compatibility.** The reader must genuinely parse every version it promises to support, test real files, and handle defaults/validation.

### Validate Version Errors Early

Reading `version` first and checking supported bounds before parsing the remainder avoids misreading types in a completely different schema. Never ignore an unknown version and guess the remaining bytes under the current format.

## 13. Data Ordering and Hard-to-Spot Bugs

Wrong ordering can produce hard-to-diagnose bugs. Suppose the writer calls `writeInt(5)` then `writeLong(7L)`, while the reader calls `readLong()` then `readInt()`:

- An exception might not occur on the very first byte.
- Values can be stitched together from bytes belonging to two different fields.
- The next read offset is no longer aligned with the expected boundary.
- The actual failure may surface much later when a type token, length, or trailer is misinterpreted.

**Writing same-version round-trip unit tests is necessary but insufficient.** If writer and reader share the same symmetric bug, a single-version round-trip test will still pass. You must test cross-version compatibility using **golden files** saved from older versions as well as invalid inputs.

Testing checklist:

1. Minimal object and fully populated object.
2. Nulls, empty strings, Unicode, very long strings.
3. Negative numbers, large numbers, overflow, boundary values.
4. Reference graphs where the same object appears multiple times.
5. Graphs with cycles.
6. Streams truncated mid-primitive or mid-object.
7. Unsupported `formatVersion`.
8. Classes with/without a public no-arg constructor.
9. Errors when writing multiple consecutive objects in the same stream.
10. Older/newer versions and UID stability.

## 14. What Exceptions Can writeExternal/readExternal Throw?

| Scenario | Exception / Error Group |
|---|---|
| Corrupted stream, truncated file, or transport failure | `IOException`, `EOFException`, `StreamCorruptedException` depending on context |
| Invalid custom payload format | Can explicitly throw `InvalidObjectException` |
| `readObject()` encounters a class missing from classpath | `ClassNotFoundException` |
| Externalizable class fails constructor requirement | Typically `InvalidClassException` or related error |
| `writeObject(ref)` encounters a non-Serializable object | `NotSerializableException` |
| Incompatible class descriptor/UID | `InvalidClassException` |
| Invalid or overly long modified UTF-8 data | `UTFDataFormatException` |
| Wrong cast after `readObject` | `ClassCastException` (unchecked) |
| Java input filter rejects class/graph | Can result in `InvalidClassException` |

When `readExternal` throws an error:

- Do not use the partially constructed object as a valid domain object.
- Do not attempt to keep reading from a guessed offset without an explicit recovery protocol.
- Log or return an error with file/request/format version context, without printing sensitive data.
- If reading from an untrusted source, prefer **not using native deserialization**; exception handling does not eliminate risks from object instantiation before the error occurs.

## 15. Custom Formats and Resource Limits

The explicit control of Externalizable lets you validate data before allocating:

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

This is an illustrative snippet requiring imports for `ArrayList`, `List`, `InvalidObjectException`, `ObjectInput`, and declaration of `in`. Capping `itemCount` before allocating the `ArrayList` is good, yet:

- Each `String` can still be large; enforce a policy on total bytes/strings.
- If the protocol permits nested objects, enforce depth/reference-count limits.
- Concurrent reading requests can add up to high memory usage; cap concurrency.
- Network stream I/O can stall; enforce timeouts/backpressure and close resources when quotas are exceeded.
- Truncated input must fail clearly rather than silently restoring a partial list.
- `readUTF` has its own limits; protocols writing raw UTF-8 manually need stricter explicit limits.

## 16. How Does This Differ from Serializable's readObject/writeObject Hooks?

Two models are frequently confused:

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

These special `private` methods belong to a regular `Serializable` class and are discovered by the serialization runtime; you can retain default fields via `defaultWriteObject`/`defaultReadObject`.

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

`writeExternal`/`readExternal` must be **public** because they implement interface methods. You control the entire written payload; **`defaultWriteObject` is not a mandatory step of Externalizable**, and the `ObjectOutput` interface does not provide `defaultWriteObject()` like `ObjectOutputStream`.

**Do not write `private readExternal` expecting the runtime to invoke it like `readObject`.** That is not a valid interface implementation.

### When to Choose Which Model?

- Simple models with many fields needing minimal code: default `Serializable` may suffice in trusted internal environments.
- Needing a few validations/hooks while keeping most fields default: custom `readObject/writeObject` can make sense.
- Wanting tight control over ordering, versioning, and payload encoding inside a Java object stream: `Externalizable`.
- Needing a cross-language format, long-lived schemas, or accepting input from untrusted clients: **neither should be the default choice**; prefer DTOs/schemas and an appropriate serializer.

## 17. Security: Externalizable Is Not Safe Against Malicious Bytes

`Externalizable` can mislead authors into thinking "since I read fields manually, it must be safer." Yet it **is still triggered via `ObjectInputStream.readObject()`**, complete with class descriptors, object allocation, and related hooks. That still carries native Java deserialization risks.

Dangerous scenario:

```java
// DO NOT DO THIS with bytes sent by untrusted clients.
try (ObjectInputStream in = new ObjectInputStream(networkInput)) {
    Object value = in.readObject();
}
```

Reasons:

- Decoding can instantiate classes on the classpath with unwanted behavior.
- Externalizable's public no-arg constructor can execute and cause side effects before the payload is validated.
- `readExternal` may call `in.readObject()` and pull in an entire complex graph.
- Inputs can be crafted to trigger excessive CPU, memory consumption, or stack/resource exhaustion.
- Checking `instanceof` after `readObject` can be too late to prevent actions during deserialization.

Principles:

1. Avoid Java native deserialization at **trust boundaries**: public HTTP payloads, external submissions, files from untrusted sources.
2. Prefer simple data formats, DTOs/schemas, controlled parsers, and strict limits on bytes/depth/objects.
3. If handling legacy Java serialization data from trusted sources, restrict classes/arrays/depth/references via `ObjectInputFilter` where appropriate.
4. Validate data invariants and versions inside `readExternal`, not solely in constructors.
5. Never let constructors or `readExternal` perform irreversible side effects before the payload is verified.
6. Protect file origins and permissions, using checksums or cryptographic signatures if external integrity verification is required; plain CRCs/hashes alone do not establish source trust.

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

This is an illustrative snippet requiring `ObjectInputFilter`, `ObjectInputStream`, an `InputStream source`, and exception handling. The package `com.example.model` is just an example; for a graph containing `ArrayList`/`String`/other JDK classes, the actual allowlist must be derived from your model and tested against filter semantics.

A filter helps **reduce** risk in certain scenarios, but **does not prove arbitrary untrusted input is safe**. Nor does it replace I/O source limits, per-request quotas, timeouts, or application-level security controls.

## 18. Impact of Inheritance and Superclass State

An Externalizable class can inherit fields and behavior from a superclass. However, **`writeExternal` must decide how to persist all required fields**, including state owned by a superclass accessible through valid APIs.

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

This is an illustrative class example; place `Child` in `Child.java` alongside an appropriate `Base` and import interfaces/exceptions. `Base` is not Serializable, yet the `Base()` constructor executes via `Child()` when the Externalizable object is constructed. Then `readExternal` restores `id` from the stream. If `Child.writeExternal` **does not** write `id`, that state remains whatever the constructor initialized or other application logic sets.

This contrasts with assuming superclass state is automatically saved under default serialization. For superclasses with complex invariants, expose clear APIs to get/set persistable state.

## 19. Writing and Reading Multiple Externalizable Objects in One Stream

`ObjectOutputStream` manages a handle table **across the scope of the stream**, not just a single call:

```java
try (ObjectOutputStream out = new ObjectOutputStream(output)) {
    out.writeObject(a);
    out.writeObject(b);
    out.writeObject(a);
}
```

When read in the exact order:

```java
try (ObjectInputStream in = new ObjectInputStream(input)) {
    Object first = in.readObject();
    Object second = in.readObject();
    Object third = in.readObject();
    System.out.println(first == third);
}
```

These are two separate illustrative snippets, with `output` and `input` as a matching stream pair; `a`/`b` must be declared. If the same instance A is written again without resetting the handle table, the third object can be a reference to the first object, so the identity check returns `true`.

### Trap of Mutating an Object and Writing It Again

Suppose:

```java
out.writeObject(person);
person.setName("New name");
out.writeObject(person);
```

Within the same stream, the second write may **emit only a handle reference** and skip calling `writeExternal` to save the updated state. Do not build an append-log snapshot by calling `writeObject(sameInstance)` repeatedly expecting each call to record full state.

If you want an independent handle epoch within the same `ObjectOutputStream`, `out.reset()` can be used intentionally; interaction with readers and versioned formats must be explicitly designed. `writeUnshared`/`readUnshared` are separate APIs with specialized semantics and do not automatically deep-clone every nested reference in a graph.

## 20. File Durability and Atomicity Are Not Provided by Externalizable

Successful serialization does not mean a file was durably persisted or atomically "snapshot-updated."

If writing directly:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(target))) {
    out.writeObject(root);
}
```

a failure midway can leave the old target file truncated or holding a partial object stream. For important data:

1. Create an independent temporary file, preferably in the same directory as the target.
2. Write the entire graph and close `ObjectOutputStream` cleanly.
3. If high durability is required, sync data/metadata via the appropriate filesystem mechanism and understand its limits.
4. Validate the format/snapshot as needed before publishing.
5. Replace the target via move/rename using atomic support from the provider; if atomicity is mandatory, **do not silently fall back** to a non-atomic move while keeping the same guarantee.
6. Maintain backup/recovery and cleanup for leftover temp files after a crash.

`ObjectOutputStream.close()` is not a system-wide fsync; `Files.move(..., ATOMIC_MOVE)` only addresses part of name-replacement atomicity where supported and still carries durability and multi-writer caveats.

## 21. Testing and How to Choose Externalizable

Choose `Externalizable` when you **have a specific reason**:

- You need exact control over the state persisted inside a native Java object stream.
- You want to avoid writing large unnecessary subgraphs.
- You want a custom payload with versioning, lengths, and validation owned by the class itself.
- You need compatibility with data persisted by a trusted internal Java application.

Do not choose it merely because:

- You want to send payloads over a public network.
- You expect cross-language compatibility.
- You assume `writeExternal` automatically compresses better, is safer, or is faster.
- You want to "encrypt" data (serialization is not encryption).
- You want a database with transactions, queries, migrations, or indexing.

### Code Review Checklist

- [ ] Class genuinely implements `Externalizable` and has a **public no-arg constructor**.
- [ ] Both `writeExternal` and `readExternal` are `public` with exact signatures.
- [ ] Writes and reads happen in the **exact same order with matching data types**.
- [ ] Explicit `formatVersion` exists when long-term compatibility is needed.
- [ ] Deliberate fixed `serialVersionUID` is declared.
- [ ] Handles `null`, empty values, UTF, lengths, and out-of-range values.
- [ ] Does not accidentally write sensitive fields even if marked `transient`.
- [ ] Validates state/invariants after reading, with no dangerous side effects in the constructor.
- [ ] Tests alias/cycle graphs and references to non-Serializable classes.
- [ ] Handles `IOException`, `ClassNotFoundException`, `InvalidClassException`, and malformed streams.
- [ ] Does not deserialize untrusted data; restricts sources/graphs when reading trusted legacy data.
- [ ] If persisting to files, separates write, commit, and recovery strategies.

## 22. Common Mistakes

1. **Missing public no-arg constructor:** Externalizable deserialization fails.
2. **Declaring `readExternal`/`writeExternal` as `private`:** fails to implement the interface properly.
3. **Confusing `readExternal` with the `private readObject` hook:** two distinct protocols and extension points.
4. **Failing to write all fields needed for restoration:** post-read values fall back to defaults/constructor state.
5. **Assuming `transient` automatically stops custom writers from writing a token:** calling `writeUTF(token)` still persists the token.
6. **Reading primitives/objects out of order:** corrupted data or undecodable stream.
7. **Using `writeUTF` for overly long strings:** modified UTF-8 has a 65,535-byte limit.
8. **Forgetting explicit null encoding:** `writeUTF(null)` is not a valid null representation.
9. **Skipping custom payload version checks:** newer/older readers misinterpret the schema.
10. **Assuming a matching UID guarantees compatibility:** the reader must still understand the payload bytes.
11. **Manually recursing into `writeExternal` on a cyclic reference graph:** bypasses stream object handles and risks infinite recursion.
12. **Not accounting for graphs under construction:** `readExternal` may observe references to partially restored objects.
13. **Assuming a read object is already fully validated:** invariants/snapshots still need explicit checks after restoration.
14. **Writing the same instance multiple times expecting fresh snapshots:** the handle table may emit a reference instead.
15. **Letting constructors perform I/O/side effects during deserialization:** security and lifecycle hazard.
16. **Accepting native serialization bytes from untrusted clients:** security and resource-exhaustion risks.
17. **Overwriting the sole snapshot file in place:** a crash can destroy the old data.
18. **Skipping cross-version/golden-file tests:** changing reader and writer together can hide protocol bugs.
19. **Assuming better performance just because fewer fields are written:** benchmark on real object graphs instead of guessing.
20. **Treating Externalizable as a standard interchange format outside Java:** it remains tied to Java object serialization.

## 23. Practice Exercises

**Exercise 1 — Write a custom protocol for a record-like class.** Create `Report implements Externalizable` with `id`, `createdAtEpochMillis`, and `status`. Write version 1, String id, long timestamp, and a byte code representing status. Read it back and validate the status range; test a stream with an invalid version.

**Exercise 2 — Add a field in version 2.** Add an optional `source`. Define V1 without `source`, and V2 writing `source` with a boolean presence flag. Reader V2 must read both V1 and V2 bytes without over-reading V1.

**Exercise 3 — Verify constructor behavior.** Assign a transient field `"initialized"` in the public no-arg constructor; do not write it in `writeExternal`. After deserialization, verify the value stays intact. Remove the constructor and predict the exception.

**Exercise 4 — Shared object graph.** A `Group` has two fields pointing to the same `Node`. Write both via `out.writeObject`, read back, and verify `first == second`. Then form a two-Node cycle to verify cycle restoration.

**Exercise 5 — Ordering bug.** Write an `int` followed by a `long`, then attempt to read in reverse order. Observe the error or nonsensical values; fix the protocol and write golden-byte tests instead of only testing writer/reader from the same build.

**Exercise 6 — Invalid inputs.** Write `count=-1` or a huge `count` into a custom format. The reader must reject it before allocating the list. Continue testing long strings, unsupported versions, and truncated streams.

**Exercise 7 — Evaluate alternatives.** Design a 5-field DTO for storing configuration. Compare native Java Externalizable against JSON or Protocol Buffers in terms of versioning, diff reviewability, security risk, and cross-language compatibility.

## 24. Self-Check Questions

**Question 1.** How does `Externalizable` differ from the `Serializable` marker interface?  
**Answer:** `Externalizable` declares `writeExternal` and `readExternal` so the class explicitly writes and reads its payload; it still extends `Serializable`.

**Question 2.** Why does an Externalizable class need a public no-arg constructor?  
**Answer:** Deserialization uses that constructor to instantiate the object before calling `readExternal`.

**Question 3.** `writeExternal` skips writing `age`; after reading, is it automatically restored by default field serialization?  
**Answer:** No. Its value depends on the constructor/initializer and `readExternal` logic, since Externalizable does not automatically save default fields.

**Question 4.** Can a `transient password` field still be written to the stream?  
**Answer:** Yes, if `writeExternal` explicitly writes it. `transient` does not block custom writers.

**Question 5.** If `out.writeInt(12)` was called, should you read it with `readLong` to keep enough bytes?  
**Answer:** No. You must read it with the matching `readInt` in the exact schema order.

**Question 6.** Can A→B→A be preserved with Externalizable?  
**Answer:** Yes, by using `out.writeObject`/`in.readObject` for references under the serialization contract; the handle mechanism tracks cycles.

**Question 7.** If `readExternal` in B reads a reference to A while A is still being restored, are all of A's fields guaranteed to be populated?  
**Answer:** Not necessarily. Do not rely on complete object state while resolving cyclic graphs.

**Question 8.** Do `serialVersionUID=1L` and `formatVersion=2` conflict with each other?  
**Answer:** No. The UID governs Java object stream class compatibility; `formatVersion` is your self-defined payload version.

**Question 9.** Why should Externalizable not be used to deserialize requests from the internet?  
**Answer:** It still relies on Java native deserialization, which can instantiate classes and invoke dangerous constructors/hooks from untrusted bytes.

**Question 10.** Does calling `ObjectOutputStream.writeObject(a)` twice always write a fresh state snapshot the second time?  
**Answer:** No. The stream has a handle table; the second write may emit only a reference.

**Question 11.** Does `ObjectOutputStream.close()` guarantee a snapshot file is durably flushed across a power outage?  
**Answer:** No. You need filesystem-appropriate durability, atomic replacement, and recovery strategies.

**Question 12.** When does Externalizable make more sense than a public self-describing format?  
**Answer:** When a trusted internal Java application has a concrete reason to control payloads inside Java object serialization; it is not the default choice for public or cross-language APIs.

## 25. Takeaway

- **`Externalizable` extends `Serializable` and requires public `writeExternal(ObjectOutput)` + `readExternal(ObjectInput)`.**
- **A `public` no-arg constructor is mandatory** for normal instance reconstruction.
- **Every field to persist must be explicitly written and read by the class**; `transient`/`static` do not stop custom writers from writing data.
- **Payload ordering, types, and versions are the application's own contract.** `serialVersionUID` does not replace a custom format version.
- **Object graphs, aliases, and cycles can still be preserved** via `writeObject`/`readObject` and `ObjectOutputStream` handles.
- **Never use native Java deserialization on untrusted bytes.** Validation, `ObjectInputFilter`, and resource limits are complementary safeguards, not substitutes for trust-boundary design.
- Externalizable **is not a database, transaction engine, cross-language format, or security encryption**; choose APIs based on actual requirements.

### Java SE 17 API References

- [Externalizable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html)
- [ObjectOutput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutput.html)
- [ObjectInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInput.html)
- [ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html)
- [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html)
