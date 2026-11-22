# Serialization, Serializable, and Saving Object Graphs in Java

## 1. What Is Serialization?

**Serialization** is the process of converting an object along with its persisted state into a representation that can be written to a byte stream. **Deserialization** is the process of reading that representation and reconstructing the corresponding objects.

In Java Core I/O, the built-in object serialization mechanism uses:

- `java.io.Serializable`: a **marker interface** marking a class as eligible for Java serialization.
- `java.io.ObjectOutputStream`: writes an object and its reference graph to an `OutputStream`.
- `java.io.ObjectInputStream`: reads bytes produced in the Java serialization format and reconstructs the objects.

It is important to distinguish:

- **Serialization**: Java object data is encoded into a structured byte format.
- **Persistence**: state is stored to survive beyond the process lifetime; Java serialization is only one way to do this, and not always the best choice.
- **Deep copying**: serialize–deserialize can be used to copy a suitable graph, though it is typically expensive and does not apply to every object.
- **Object graph**: the set of objects and reference relationships connecting them, which may share the same object or contain cycles.

Example graph:

```text
team (ArrayList)
  ├── [0] ──> alice ───── friend ──> bob
  │             ^                      │
  │             └────── friend ────────┘
  ├── [1] ───────────────────────────> bob
  └── [2] ──> alice   (same reference as [0])
```

When writing the **entire graph** with `ObjectOutputStream.writeObject(team)`, Java serialization also records **object identity information within the stream**. When reading it back, shared and cyclic references can be restored accurately according to the graph, rather than simply creating a separate copy each time the same object is encountered.

> **Important security note:** do not use `ObjectInputStream` to deserialize bytes coming from untrusted sources. Java native deserialization has a large attack surface; `ObjectInputFilter` is only an additional defense layer and does not make untrusted input completely safe. For public data exchange, consider a controlled schema/DTO format and an appropriate parser.

## 2. Serializable Is a Marker Interface

A class that wants to participate in the standard serialization mechanism can implement `Serializable`:

```java
import java.io.Serializable;

public class Student implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String id;
    private final String name;

    public Student(String id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public String toString() {
        return id + " - " + name;
    }
}
```

This is **a standalone illustrative class**, which can be saved as `Student.java`; to run it, you need another class containing `main` or an application that uses it.

`Serializable` is a **marker interface**: it defines no methods that must be overridden. Calls to `ObjectOutputStream.writeObject` and the runtime logic handle this class through a special mechanism.

This **does not mean** every class is automatically serializable:

- An object of a **non-serializable** class appearing in the graph can cause `writeObject` to fail with `NotSerializableException`.
- Fields declared as `transient` do not participate in the default field serialization mechanism.
- `static` belongs to class state, **not** instance state saved by default.
- Certain object kinds have special serialization rules, such as `enum` and `record`; you should not mechanically apply all regular class rules to them.
- A `Serializable` class can customize serialization behavior using valid hooks, but that must not be used to bypass security and invariant checks.

### Serializable Is Not Just "Writing Fields as Text"

`ObjectOutputStream` produces **a proprietary Java binary stream format**, consisting of a header, class descriptors, field data, and reference information. Do not open the file in Notepad expecting to read its contents like JSON. Do not use this native format as a long-term public protocol if interoperability with applications written in other languages is required.

## 3. ObjectOutputStream and ObjectInputStream

Basic pipeline:

```text
Student object
     |
     v
ObjectOutputStream.writeObject(...)
     |
     v
Java serialization stream bytes
     |
     v
FileOutputStream / ByteArrayOutputStream / other OutputStream
     |
     v
ObjectInputStream.readObject()
     |
     v
Reconstructed Student object
```

To write:

```java
try (ObjectOutputStream out = new ObjectOutputStream(
        Files.newOutputStream(Path.of("student.ser")))) {
    out.writeObject(student);
}
```

To read:

```java
try (ObjectInputStream in = new ObjectInputStream(
        Files.newInputStream(Path.of("student.ser")))) {
    Student restored = (Student) in.readObject();
}
```

Both snippets are **illustrative code**, requiring imports for `ObjectOutputStream`, `ObjectInputStream`, `Files`, `Path` and a declared `student` object. The reading method must handle `IOException` and `ClassNotFoundException`. Only use `ObjectInputStream` on streams created by trusted, managed sources.

A few details:

1. The `ObjectOutputStream` constructor writes the **stream header** before `writeObject` is called.
2. The `ObjectInputStream` constructor reads/verifies the input header and may **block** waiting for a header from an open stream, especially on bidirectional connections.
3. `writeObject` writes the representation of the object and related parts of the graph.
4. `readObject` returns `Object`; the caller checks/casts to the expected type and verifies whether the data is valid at the business level.
5. Try-with-resources closes the wrapper and the underlying stream, ensuring resources are flushed/closed according to the API contract.
6. Reading objects may instantiate new objects with **different references** from the original objects, but sharing relationships **within** the restored graph are preserved according to serialization semantics.

`ObjectInputStream.readObject()` is not a "pure data-only" parser; it can trigger behavior in classes during deserialization, including hooks and object construction. This is a primary reason why untrusted input is dangerous.

## 4. How Is an Object Graph Stored?

A graph typically has multiple interconnected objects. For example:

```java
final class Node implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}
```

This is an illustrative class placed in an appropriate package/file and requires importing `Serializable`. If:

```java
Node a = new Node("A");
Node b = new Node("B");
a.next = b;
b.next = a;
```

then the graph has a cycle `A → B → A`.

Java serialization does not naively recurse infinitely. `ObjectOutputStream` manages **reference handles in the stream**. When encountering an object that has already appeared, the stream can write a reference to that object's handle instead of repeatedly writing the entire object forever.

Upon deserialization:

- The corresponding objects are recreated.
- Reference fields are assigned to re-establish relationships.
- Reference cycles can be restored.
- Two fields that previously pointed to the same object within the jointly written graph will again point to the same **new** object in the restored graph.

Key takeaway: **object identity within the graph is preserved**, while restored objects do not share the same identity as the original objects still alive in the original JVM.

### Identity vs. Equality

- `a == b`: do two references point to the same object instance?
- `a.equals(b)`: comparison logic as defined by the class, which can be true even if two objects are different instances.

When studying graph serialization, you must use `==` to prove that reference sharing was restored. Calling `equals` may only prove field values match, **not** aliasing.

## 5. Complete Java 17+ Program: Shared References, Cycles, and Transient

This example uses only `ByteArrayOutputStream` and `ByteArrayInputStream` so it runs easily without filesystem dependencies. Object graph relationships are constructed explicitly:

- A list contains `alice` at indices 0 and 2, demonstrating **the same reference**.
- `alice.friend = bob` and `bob.friend = alice` create a **two-way cycle**.
- The `sessionToken` field is marked `transient`, so after deserialization it receives the default value `null`.
- `serialVersionUID` is explicitly declared on the class participating in serialization.
- Stdout lines do not rely on file size or byte-format details.

Save the file as **`SerializationGraphDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class SerializationGraphDemo {

    private static final class Person implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String name;
        private Person friend;
        private transient String sessionToken;

        private Person(String name, String sessionToken) {
            this.name = name;
            this.sessionToken = sessionToken;
        }
    }

    public static void main(String[] args) throws Exception {
        Person alice = new Person("Alice", "secret-a");
        Person bob = new Person("Bob", "secret-b");

        alice.friend = bob;
        bob.friend = alice;

        List<Person> team = new ArrayList<>();
        team.add(alice);
        team.add(bob);
        team.add(alice); // Same instance as team.get(0).

        byte[] serialized;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(team);
            output.flush();
            serialized = bytes.toByteArray();
        }

        List<?> restored;
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(serialized))) {
            restored = (List<?>) input.readObject();
        }

        Person restoredAlice = (Person) restored.get(0);
        Person restoredBob = (Person) restored.get(1);

        System.out.println("List size: " + restored.size());
        System.out.println("Names: "
                + restoredAlice.name + ", " + restoredBob.name);
        System.out.println("Shared reference: "
                + (restoredAlice == restored.get(2)));
        System.out.println("Cycle restored: "
                + (restoredAlice.friend == restoredBob
                    && restoredBob.friend == restoredAlice));
        System.out.println("Transient is null: "
                + (restoredAlice.sessionToken == null));
        System.out.println("Original differs: "
                + (restoredAlice != alice));
    }
}
```

Run with Java 17+:

```bash
javac SerializationGraphDemo.java
java SerializationGraphDemo
```

**Exact stdout:**

```text
List size: 3
Names: Alice, Bob
Shared reference: true
Cycle restored: true
Transient is null: true
Original differs: true
```

Why does this output occur?

1. `ArrayList` is serializable, so the list object along with the `Person` elements can be written.
2. `Person` implements `Serializable` and contains `name` of type `String` (serializable), `friend` pointing to `Person` (serializable), and `sessionToken` which is transient.
3. When `alice` is encountered again at index 2, `ObjectOutputStream` records the appropriate handle/alias relationship; when read back, `restored.get(2) == restored.get(0)`.
4. The cycle `alice → bob → alice` is deserialized with properly connected references, without causing infinite recursion just because a cycle exists.
5. `sessionToken` is not saved, so the field on the restored object is `null`. This **does not erase** the secret string still living in the original object; also, `transient` should not be treated as a complete secret-management system.
6. `restoredAlice != alice` because they are two distinct instances. Identity is preserved only **within the restored graph**, not across the two graphs at two different stages.

**Note:** in the example code, `Person` is a **static** nested class. A non-static inner class can carry an implicit reference to the enclosing class instance; this hidden reference can affect serialization and cause `NotSerializableException`. When designing serializable DTOs, prefer top-level classes or static nested classes with explicit state.

## 6. Which Fields Are Saved?

For the default serialization mechanism of a regular class:

| Component kind | Saved by default? | Notes |
|---|---|---|
| Non-static, non-transient instance field | Yes | Primitive values and references to objects can be processed |
| `transient` instance field | No | When read back, usually receives default value or is restored via hook |
| `static` field | No | Belongs to the running class, not tied to a serialized instance |
| `serialVersionUID` | Not instance data | UID describing the serialization version of the class |
| Methods and class bytecode | Not as instance state | Compatible class must be available to the deserializing runtime |
| Fields of referenced objects | Possibly | If reachable in the graph and types satisfy the `Serializable` contract |

### Transient and Default Values

`transient` excludes a field from being saved by the default field mechanism:

```java
class Session implements Serializable {
    private static final long serialVersionUID = 1L;

    String username;
    transient String accessToken;
    transient int retryCounter;
}
```

When a `Session` object is restored via default serialization, `accessToken` may be `null` and `retryCounter` `0`. If the class defines a `readObject` hook that reinitializes these fields, the result can differ.

Things to keep in mind:

- `transient` prevents **that field** from being written to the stream by default; it does not guarantee sensitive values are not saved through other fields or custom hooks.
- By default, fields of a serializable object are reconstructed without running that class's normal constructor. If the constructor assigns a default token, do not rely on that constructor to restore the token.
- If an object holds resources such as a socket, thread, file handle, or database connection, exclude the resource from the persisted form and recreate it when needed in a controlled manner.

### Static Is Not Snapshotted Per Object

`static int counter` is a property of the class in the JVM. Writing an instance does not save an "individual copy" of `counter`; after reading back, the static field value reflects the current state of the class at runtime. Therefore, serializing an instance cannot be used to back up the application's entire global state.

## 7. Graphs Containing Non-Serializable Objects

Marking the root class `Serializable` **does not** automatically make every object deeper in the graph serializable.

For example:

```java
final class ResourceHolder implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String label;
    private final Thread worker; // Thread is not Serializable.

    ResourceHolder(String label, Thread worker) {
        this.label = label;
        this.worker = worker;
    }
}
```

If `worker` is non-null and the object is written with the default mechanism:

```java
output.writeObject(holder);
```

it can throw **`java.io.NotSerializableException`** because `Thread` does not satisfy the serialization contract. These two snippets are illustrative and must be placed inside a class/method with `output` and `holder` declared accordingly.

The solution is not to blindly "force everything to implement `Serializable`". Ask:

1. Does the field actually need to be persisted?
2. Does it represent an **active resource**? If so, serialization is usually not the place to store that resource.
3. If only an identifier is needed, store an ID/string/DTO that can recreate the resource after reading.
4. If the field is just a temporary cache/handle, mark it `transient` and design a reinitialization step.
5. If the entire graph is too complex, create a **separate persistence data model** instead of serializing domain objects directly.

### Does Marking Transient Always Make the Graph Safe?

No. Remaining fields must still be serializable, and custom serialization callbacks can still write other values into the stream. Moreover, business invariants of an object can be broken after deserialization if validation checks are not re-executed.

## 8. Object Identity and Handles Within One Stream

When using **a single `ObjectOutputStream`** and calling `writeObject` multiple times on the same object, the stream maintains a handle table. For example:

```java
ObjectOutputStream out = ...;
out.writeObject(person);
out.writeObject(person);
```

Without changing sharing behavior or resetting the stream, the second write may emit a reference to the already-written object. When reading sequentially:

```java
Object first = in.readObject();
Object second = in.readObject();
System.out.println(first == second); // Usually true in this pattern.
```

Both snippets are illustrative only; `out`/`in` must be declared, lifecycle-managed, and operate on the corresponding serialization stream.

**The "modified object and called `writeObject` again" trap**: if `person.name` is mutated between two `writeObject(person)` calls on the same stream, the second call may write only a handle reference, **not a snapshot of the new state**. When you need to start a fresh write cycle with an independent handle table, `ObjectOutputStream.reset()` can be used intentionally.

`reset()` makes `ObjectOutputStream` forget previously written reference state for subsequent objects after the reset, but it does not turn the stream into a fully versioned JSON append log. Nor does it replace closing/reopening when format, consistency, or transactional requirements differ.

### writeUnshared/readUnshared

Java provides `writeUnshared`/`readUnshared` for certain situations where you need to avoid sharing the top-level object's handle. These are specialized APIs, **not a simple deep clone**: references deeper inside the graph still follow their own semantics. For foundational work, understand `writeObject` and the handle mechanism before reaching for `writeUnshared`.

## 9. serialVersionUID and Version Compatibility

A typical serializable class should explicitly declare:

```java
@Serial
private static final long serialVersionUID = 1L;
```

In Java 17, `@Serial` (`java.io.Serial`) helps the compiler and tools recognize serialization-related declarations. `serialVersionUID` must be a `static final long` field with that exact name, per API rules.

The UID is used during class compatibility checking at deserialization time. If the current class version's UID does not match the UID recorded in the stream, the runtime typically throws **`InvalidClassException`**.

Why declare it explicitly?

- If omitted, the JVM computes a default UID based on class details. Source or compiler changes can alter that UID unintentionally.
- An explicit UID allows model upgrades to be controlled more predictably.
- It **does not** guarantee that every change keeping the same UID is semantically compatible. You must still verify schemas, invariants, and object-reading rules.

### Changing a Class Between Versions

Suppose V1 is:

```java
class Account implements Serializable {
    private static final long serialVersionUID = 1L;
    String id;
}
```

Later V2 adds a field:

```java
class Account implements Serializable {
    private static final long serialVersionUID = 1L;
    String id;
    String displayName;
}
```

These are **two illustrative versions** of the same class, not meant to be declared simultaneously in the same file/package. If an old stream is read by V2 using compatible default field semantics, `displayName` may receive the default value `null`.

However, adding/removing/changing field types, changing the hierarchy, or altering class semantics can cause errors or invalid states. For example, if V2 expects `displayName` to be non-null, it must check/assign a fallback after reading; you cannot assume the constructor will run to fix it.

### When to Increment serialVersionUID?

The UID is part of the compatibility contract. If a change is no longer compatible and you intentionally want to block reading old streams, you can choose a new UID. If retaining backward readability, test cross-version serialization/deserialization in practice. Do not increment the UID automatically after **every** code edit, and do not keep the old UID without testing.

### Java Serialization Is Not a Stable Format for Every System

Object models evolve with application versions, package/class names, inheritance structures, class loaders, and custom hooks. Therefore, you should not use a serialized object stream as a long-term or public storage format when cross-language compatibility, complex migrations, or data transmission across trust boundaries are required.

## 10. Constructors and Object Creation During Deserialization

A common misconception is: "`readObject` calls the class constructor just like `new`." For a regular `Serializable` class, deserialization **does not call that class's normal constructor** to restore saved fields. The no-argument constructor of the first **non-Serializable** superclass in the hierarchy is invoked according to serialization rules.

For example, a class with a constructor:

```java
public Profile(String username) {
    if (username == null || username.isBlank()) {
        throw new IllegalArgumentException("Invalid username");
    }
    this.username = username;
}
```

This constructor runs on `new Profile(...)`, but it must not be assumed to re-run automatically as a validation gate when Java restores `Profile` from a serialized stream.

Consequences:

- Invariants checked only in the constructor may **not** be automatically enforced after deserialization.
- Transient fields and newly added fields typically receive default values unless handled by custom logic.
- Objects may need validation upon reading, especially if used as input for sensitive operations.
- Do not deserialize untrusted data expecting the constructor to block dangerous states.

For a non-serializable superclass, its no-argument constructor must be accessible under Java access rules for subclass deserialization to succeed. If not satisfied, `InvalidClassException` may occur.

## 11. readObject/writeObject for Customization (Extended Topic)

A class can define special hooks:

```java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    // Additional data can be written following a managed custom protocol.
}

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Check invariants and restore transient state when needed.
}
```

These are two **illustrative methods** inside a `Serializable` class; they require importing `Serial`, `ObjectOutputStream`, `ObjectInputStream`, `IOException`, and `ClassNotFoundException`.

Details:

- The methods must match the exact signature, visibility, and contract of Java serialization; they do not override interface methods.
- `defaultWriteObject()` and `defaultReadObject()` handle the class's default serializable field set.
- If additional custom data is written, the reading logic must consume it in the exact matching order and version.
- `readObject` should validate invariants after receiving data, potentially throwing `InvalidObjectException` for invalid state.
- Hooks can execute during deserialization, making untrusted byte streams dangerous; **do not** treat custom hooks as a sandbox.

Do not add hooks just to "make an example work": for simple classes, default serialization is usually sufficient for learning the mechanism.

### Post-Read Invariant Example

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (id == null || id.isBlank()) {
        throw new InvalidObjectException("Missing id");
    }
}
```

This snippet is only an illustrative method; the `id` field and imports must exist in the actual class. This check adds validation during deserialization, but **does not** make opening an untrusted stream safe: other object types may be instantiated or processed before this class's validation finishes.

## 12. Serializable, Externalizable, and Special Types

### Externalizable

`Externalizable` extends `Serializable` and allows a class to explicitly define:

- `writeExternal(ObjectOutput out)`
- `readExternal(ObjectInput in)`

It requires taking responsibility for managing the data layout and typically requires a `public` no-argument constructor. It is an advanced tool, not a cure-all for compatibility or security issues. For learning serialization basics, `Serializable + ObjectOutputStream/ObjectInputStream` is the foundation to master first.

### Enum

Enums have special Java serialization mechanics: semantically, an enum constant is deserialized to the corresponding constant of the enum class, rather than an independent copy like a regular class. Default hooks and `serialVersionUID` for enums follow dedicated rules. Do not use enums as typical examples for saving arbitrary instance fields like ordinary classes.

### Record

Java records also have dedicated serialization semantics when implementing `Serializable`. Record reconstruction during deserialization involves the canonical constructor per specification, so you should not claim every serializable class skips constructors in all cases. If designing a record DTO, consult the documentation for your target Java version.

### Arrays and Collections

Many arrays and standard Java collections support serialization, but **a serializable collection does not guarantee every element can be written**. For example, an `ArrayList<Thread>` typically cannot be serialized when it contains non-null threads. Verify the actual runtime graph, not just the root collection type.

## 13. Common Exceptions and How to Diagnose Them

| Exception | Common cause | What to check |
|---|---|---|
| `NotSerializableException` | Graph contains a non-serializable object | Which field/reference was not excluded or converted to a DTO? |
| `InvalidClassException` | Incompatible UID/class descriptor or class violates contract | Class version, `serialVersionUID`, hierarchy, and field format |
| `StreamCorruptedException` | Invalid serialization stream header/token | Was it written with `ObjectOutputStream`, or was the stream truncated/mixed with other bytes? |
| `ClassNotFoundException` | Reading runtime lacks a class needed to reconstruct an object | Are package, classpath, and class loader using the right version? |
| `OptionalDataException` | Reading object/primitive mismatches stream structure or hits unexpected EOF | Write/read order and custom hooks |
| `EOFException` | Stream ended before expected amount of data | Was the file truncated or are you reading more objects than written? |
| `InvalidObjectException` | Custom validation / hook rejected the object | Which invariant was not satisfied? |
| `IOException` | I/O error during stream read/write/close | Permissions, file path, resources, already-closed stream, etc. |

Do not swallow `NotSerializableException` and continue writing to the same file as if the transaction succeeded. A failed output stream can leave an incomplete file or invalid state that must be discarded; rewrite from scratch via a temporary file after fixing the root cause.

`ClassCastException` can also appear when the caller casts the read object to the wrong class; it is not an `IOException`, yet you still need to control types after deserialization.

## 14. Security: Avoid Deserializing Untrusted Data

Java native serialization is designed to reconstruct **Java object graphs**, not to parse passive data in an automatic sandbox. `readObject` can trigger behavior in loaded classes, including hooks. Certain combinations of objects/classes can cause excessive CPU/memory consumption or unintended behavior in applications carrying exploitable libraries.

**Safety principles:**

1. Never accept raw Java serialized bytes directly from clients, HTTP requests, public queues, cookies, or externally controlled files and pass them to `readObject`.
2. When communicating across a trust boundary, prefer **JSON/CBOR/Protocol Buffers/Avro or schema-backed DTOs** with parsers and explicit validation. These formats still require resource limits, schemas, and security controls, but they avoid exposing the full Java object-graph reconstruction engine to untrusted input.
3. For legacy data that must use Java serialization, read only from trusted locations and enforce **limits on bytes, depth, reference counts, array sizes, and allowed classes**.
4. Use `ObjectInputFilter` (JEP 290, available since Java 9) as **defense in depth** where appropriate.
5. Do not treat a simple filter as an absolute guarantee: filters are not invoked identically for every object case, and allowed classes can still have harmful behavior; audit the entire classpath, custom `readObject` implementations, and library versions.
6. Handle deserialization exceptions cleanly and avoid continuing with partially read objects.

### ObjectInputFilter in Java 17

Illustrative example of the API mechanism, **not a copy-paste production configuration**:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=8;maxrefs=100;maxarray=10000;maxbytes=1048576;"
      + "com.example.dto.*;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
    // Check type and additional invariants.
}
```

This snippet requires `ObjectInputFilter`, `ObjectInputStream`, an `InputStream source`, and checked exception handling. The illustrative filter only allows a hypothetical DTO package plus limits; a real graph containing `ArrayList` or other JDK classes would be rejected unless included in a proper allowlist. Do not remove `!*` just to "make it work" without precisely defining the model and trust boundary.

`ObjectInputFilter.Config.createFilter(...)` uses a pattern string; criteria and the class allowlist must be verified by testing against valid data rather than trusting sample strings. You should also bound **bytes read into the stream** at an outer layer if needed; the filter does not replace file-size policies, timeouts, and application quotas.

**Security conclusion:** even with `ObjectInputFilter`, native Java deserialization is not the recommended choice for parsing payloads from untrusted sources. The better solution is usually to **avoid Java serialized data at trust boundaries**.

## 15. Persistence: When to Use It or Not?

### Suitable for Learning and Limited Internal Use

- Demonstrating how object graphs are written and restored.
- Saving temporary internal snapshots where the application controls the entire producer, consumer, and model version.
- Passing objects between trusted Java components in an environment with a clear serialization contract.

Even when trusted, you must still consider **schema/versioning, file durability, mid-write failures, and resource limits**.

### Should Not Be Used by Default as a Long-Term Format

- Configuration files that humans need to read/edit and review in Git.
- Multi-language public APIs.
- Data continuously upgraded across many application versions.
- Systems requiring easy querying, indexing, and migration.
- Untrusted payloads coming from the internet.
- Sensitive data where exact control over what gets persisted is required.

For those needs, consider JSON/YAML/Properties/CSV, a database, or schema-based binary formats depending on the problem. Java serialization stores **Java class structure**, so coupling between data and code can be high.

### Differences from Database Storage

Java serialization does not provide:

- Multi-object/multi-file transactions in the database sense.
- Indexes, field-level queries, and isolation.
- Automatic version migration.
- Access control, backups, and crash recovery like a DBMS.
- Security guarantees merely because a class implements `Serializable`.

Do not use `ObjectOutputStream` as a multi-user database when the system requires strong consistency.

## 16. Safer File Writing with Temporary Files

A direct operation:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(target))) {
    out.writeObject(root);
}
```

can leave the destination file partially written if serialization or I/O fails. For internal data where the old copy must be preserved on error, you should:

1. Create a separate temporary file in the **same directory** as the target.
2. Use `ObjectOutputStream` to write the entire graph and close the stream cleanly.
3. If required, sync the temporary file data and verify it can be read/validated.
4. Move/replace the target file according to filesystem capabilities and your defined atomicity policy.
5. Clean up the temporary file on failure and maintain a post-crash recovery strategy.

Pattern example:

```java
Path target = Path.of("snapshot.ser").toAbsolutePath();
Path temporary = Files.createTempFile(
        target.getParent(), ".snapshot-", ".tmp");

try {
    try (ObjectOutputStream output = new ObjectOutputStream(
            Files.newOutputStream(temporary))) {
        output.writeObject(root);
    }

    Files.move(temporary, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} finally {
    Files.deleteIfExists(temporary);
}
```

This is an **illustrative snippet inside a method**, requiring imports, `IOException` handling, and `root` being a serializable object. Note:

- `ATOMIC_MOVE` may not be supported; a `Files.move` call can throw `AtomicMoveNotSupportedException`.
- Per the `Files.move` API, when `ATOMIC_MOVE` is specified, other options are ignored; if the target already exists, replacement behavior depends on the provider. Do not treat this snippet as a guarantee of portable atomic replacement.
- `finally` only cleans up the temporary file during normal execution; unexpected power loss or crashes require separate cleanup mechanisms.
- Surviving power loss also depends on syncing file data and directory metadata; `ObjectOutputStream.close()` does not guarantee flushing to the underlying storage device.
- Do not test-read with `ObjectInputStream` if the temp location could be tampered with by others; keep the directory in a trusted location and apply appropriate limits.

### Writing/Reading Multiple Objects in One Stream

You can write sequentially:

```java
out.writeObject(header);
out.writeObject(team);
out.writeObject(metadata);
```

And read in the exact same order:

```java
Header h = (Header) in.readObject();
Team t = (Team) in.readObject();
Metadata m = (Metadata) in.readObject();
```

These lines are **illustrative code**, requiring `Header`/`Team`/`Metadata` declarations and variables. Because this is a single shared stream, the handle table can preserve aliases across multiple writes. The application must define its own versioning and know how many objects to read; do not loop until EOF guessing the structure, because the stream is not a self-describing message format for all use cases.

## 17. Optimizing Size and Performance

Java native serialization incurs overhead from class descriptors, graph traversal, handle tables, metadata, and intermediate objects. A few points to note:

- Do not assume the serialized byte size equals the sum of field sizes. It includes format overhead and graph metadata.
- `ObjectOutputStream` stores handles for written objects. For very long-lived streams, the handle table can retain references to many objects; `reset()` can release state and start a new "snapshot round," though it changes sharing semantics across rounds.
- Avoid serializing an entire cache or large object graph when only a few DTO values are needed.
- If you need to store many independent records with random access, a sequential stream does not provide an index. You may need a custom record format or a database.
- You can wrap the stream with `BufferedOutputStream`/`BufferedInputStream` to reduce I/O calls on some sources; benchmark for your use case.
- If wrapping with `GZIPOutputStream`, choose the right filter order; e.g., `new ObjectOutputStream(new GZIPOutputStream(raw))` compresses serialization bytes before reaching `raw`. Closing the outer wrapper closes lower layers and finishes gzip.
- Never use compression as security: compressed serialized data can still contain sensitive information, and decompressing an untrusted stream introduces decompression-bomb risks.

### Compressing a Serialization Stream — Illustrative Example

```java
try (OutputStream file = Files.newOutputStream(path);
     GZIPOutputStream gzip = new GZIPOutputStream(file);
     ObjectOutputStream objectOut = new ObjectOutputStream(gzip)) {
    objectOut.writeObject(root);
}
```

Variables `path` and `root` must be declared. Reading back uses `new ObjectInputStream(new GZIPInputStream(Files.newInputStream(path)))`. Both the Java object stream and gzip have headers, and **the wrapper order must be symmetric**; do not attempt to read GZIP bytes directly with `ObjectInputStream`.

## 18. Common Design Mistakes

1. **Implementing `Serializable` only on the root and assuming all fields are safe.** A non-transient reference to a non-serializable object can cause `NotSerializableException`.
2. **Confusing Serialization with JSON.** It is a proprietary Java binary format, not a text file readable in a text editor.
3. **Confusing `equals` with identity.** Use `==` to verify alias/reference sharing after restoring a graph.
4. **Ignoring reference cycles.** Java serialization manages handles, whereas other serializers do not necessarily preserve cycles automatically.
5. **Storing file handles, threads, or connections directly in the object graph.** Live runtime resources should not be expected to survive serialization into a byte stream.
6. **Forgetting `transient` on state that should not be persisted.** Tokens, caches, or short-lived resources can accidentally become part of persisted data if they are serializable.
7. **Treating `transient` as encryption.** It only omits the field from default saving; it does not replace security mechanisms.
8. **Treating `static` as per-instance saved state.** Default Java serialization does not snapshot static fields.
9. **Omitting `serialVersionUID` and skipping version testing.** Class changes can make old data unreadable.
10. **Keeping the same `serialVersionUID` while assuming all edits are compatible.** Actual validation and schema testing are still required.
11. **Relying on constructors to validate after deserialization.** A `Serializable` class's regular constructor is not called like `new` during restoration.
12. **Not reading objects in the exact order they were written.** Object streams are positional; reading out of order can cause cast failures or unexpected data.
13. **Writing the same object again to one `ObjectOutputStream` expecting a fresh snapshot each time.** The handle table may cause subsequent writes to emit references.
14. **Ignoring `NotSerializableException`/`InvalidClassException`.** Files may be left incomplete or incompatible across versions.
15. **Deserializing untrusted input.** This is a severe attack surface; filters alone are no substitute for choosing a safe format.
16. **Failing to limit bytes/depth/refs/arrays.** Large or complex payloads can exhaust resources.
17. **Using serialized objects as a long-term database.** Migrations, queries, transactions, and interoperability become difficult.
18. **Overwriting the sole saved file directly.** A mid-write crash can destroy the previous snapshot.
19. **Believing `close` equals `fsync`.** Closing the stream does not guarantee durability across power loss.
20. **Missing type and invariant checks after `readObject`.** Restored objects must satisfy current business constraints.
21. **Accidently using non-static inner classes.** The implicit reference to the outer instance can make the graph hard to serialize.
22. **Writing a shared graph expecting separate copies for each reference.** The handle mechanism preserves sharing within the stream.
23. **Expecting a serialized object to bundle the entire class bytecode.** The reading runtime must have a compatible class to reconstruct it.
24. **Forgetting to close `ObjectInputStream`/`ObjectOutputStream`.** This leads to resource leaks, unflushed trailing bytes, or truncated files.
25. **Using `ObjectInputFilter` as a guarantee against all malicious payloads.** You need a threat model, allowlist, resource limits, and ideally to avoid native deserialization at trust boundaries.

## 19. Practice Exercises

### Exercise 1: Three-Node Cycle

Create three `Node` instances A, B, C with `A.next=B`, `B.next=C`, `C.next=A`. Serialize A and deserialize it into `a2`. Check:

```java
boolean cycle = a2.next.next.next == a2;
```

If the graph was restored properly, `cycle == true`. Do not use an infinitely recursive `toString` to print the node chain.

### Exercise 2: Same Object in Two Fields

Create an `Order` object with two fields `billingAddress` and `shippingAddress` pointing to the same `Address` instance. After deserialization, check:

```java
restored.billingAddress == restored.shippingAddress
```

If the same instance was saved in the graph, the result is normally `true` under default semantics. Then change the setup to two distinct `Address` instances with equal contents and observe the difference.

### Exercise 3: Skipping Transient Fields

Add `transient String token` to a serializable class and assign a token before saving. After reading it back, verify that `token` is `null` under default mechanics; explain why the old object cannot be used to deduce the new token state.

### Exercise 4: Non-Serializable Field Error

Add a non-transient `Thread worker` field to a `Serializable` class and assign `new Thread()`. Predict the exception upon writing. Then change the field to `transient Thread worker` and determine how the application should reinitialize `worker` when needed.

### Exercise 5: Version Upgrade Testing

Save data using version V1 with `serialVersionUID=1L`. Add a field in version V2 keeping the same UID, read V1 data, observe the default value of the new field, and add validation/migration. Then try a different UID to observe `InvalidClassException`. Perform this on test data, never on production files.

### Exercise 6: Input Limits

Write a DTO class holding a few `String` and integer fields. Create a controlled storage format; compare native serialization with JSON or a schema-backed binary format. Evaluate readability, versioning, size, and safety when parsing untrusted data.

## 20. Self-Check Questions

**Question 1.** Which methods does `Serializable` require implementing?  
**None.** It is a marker interface so Java serialization recognizes the class.

**Question 2.** If `root` is serializable but holds a non-null, non-transient `Thread` reference, what can happen when writing `root`?  
**`NotSerializableException`**, unless the storage structure is customized to omit that field.

**Question 3.** Serialize a `List` containing the same object A at two positions. Deserialize and compare the two positions with `==` — what does `true` mean?  
**It proves sharing within the restored graph** if true; not merely that field values are equal.

**Question 4.** Will a graph containing a cycle A→B→A cause `ObjectOutputStream` to recurse infinitely?  
**Not under the standard mechanism**, because the stream manages reference handles while writing the graph.

**Question 5.** Is a `transient String password` field saved by default?  
**No.** However, you must inspect custom hooks/other fields and never treat `transient` as a complete security method.

**Question 6.** Is a `static` field snapshotted individually per instance?  
**No.** It belongs to class state, not an instance field saved by default.

**Question 7.** Does keeping the same `serialVersionUID` guarantee every version can read the others?  
**No.** It also depends on field/hierarchy changes, custom hooks, application logic, and compatibility.

**Question 8.** Does `readObject` run the `Serializable` class's constructor like calling `new`?  
**Not for regular `Serializable` classes.** The constructor of the first non-Serializable superclass plays a role per specification; records and enums have their own rules.

**Question 9.** Why shouldn't you accept Java serialized bytes from a public HTTP API and call `ObjectInputStream.readObject()`?  
**Because native deserialization can trigger dangerous object construction and hooks**; use controlled formats/parsers and do not cross trust boundaries with it.

**Question 10.** If you write the same object twice to a single `ObjectOutputStream` and the object was modified in between, is the second write guaranteed to be a fresh snapshot?  
**No.** The stream has a handle table; the second write may just be a reference to the previously written object.

**Question 11.** Does `ObjectOutputStream.close()` guarantee file durability across a power loss?  
**No.** Appropriate durability policies and filesystem guarantees are required.

**Question 12.** When should you prefer a DTO + schema over `Serializable`?  
**When you need public APIs, untrusted data handling, long-term versioning, multiple languages, or exact control over the storage format.**

## 21. Summary

- **Java serialization** converts an object and its **object graph** into a byte stream, read back via `ObjectInputStream`; regular classes must implement the `Serializable` marker.
- **Object graphs include aliases and cycles**. Java preserves reference-sharing relationships within the stream scope; restored instances are distinct from original instances.
- **Non-static, non-transient fields** participate in default serialization; `transient` is not saved, and `static` is not instance state. A non-serializable reference can cause writing to fail.
- **`serialVersionUID`** partially manages version compatibility; it does not replace migration or testing.
- **Deserialization can bypass normal constructors and trigger hooks**, so invariants must be validated, especially when classes change.
- **Never deserialize untrusted data**. `ObjectInputFilter` is an additional defense layer, not a substitute for a threat model and safe formats.
- For important persistence, you need **safe file-writing workflows, versioning, resource limits, and recovery**; native serialization is neither a database nor a transaction manager.

### Java SE 17 References

- [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html)
- [ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html)
- [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html)
