# Advanced Java Serialization: writeObject, readObject, defaultWriteObject, and defaultReadObject

Java Object Serialization converts an **object graph** into a byte stream and reconstructs the objects when read. For `Serializable` classes, the JVM normally saves eligible instance fields automatically. However, sometimes we want to **append extra data**, **restore `transient` state**, **validate business invariants**, or **actively manage format compatibility**. In such cases, Java provides a special customization mechanism via `private writeObject(ObjectOutputStream)` and `private readObject(ObjectInputStream)`, often paired with `defaultWriteObject()` and `defaultReadObject()`.

These four names are easy to confuse because **two of them are external APIs called to write/read an object**, while the two named `default...` are **APIs used only inside callbacks** during the serialization process. This lesson focuses on the order of operations, the meaning of default data versus extra data, object lifecycle, runnable Java 17+ examples, error handling, and security boundaries.

> **Security Warning:** Java native serialization is unsuitable for untrusted data from the Internet or arbitrary users. `ObjectInputStream.readObject()` can trigger code execution in deserialized classes before the call even returns. Prefer schema-controlled formats (JSON, Protocol Buffers, CBOR, etc.) and apply an allowlist/serialization filter if you must accept Java serialization data.

## 1. Distinguishing the Two API Levels with the Same Name

| Location | API | Who Calls It? | Role |
| --- | --- | --- | --- |
| Outside the object | `ObjectOutputStream.writeObject(Object obj)` | Application code | Starts writing an object and its related reference graph. |
| Inside a `Serializable` class | `private void writeObject(ObjectOutputStream out) throws IOException` | Serialization mechanism automatically if signature is valid | Customizes the data written for **that class**. |
| Inside `writeObject` callback | `out.defaultWriteObject()` | Callback code | Writes the fields belonging to the **default** serializable state of the current class. |
| Outside the object | `ObjectInputStream.readObject()` | Application code | Reads the next object from the stream; returns `Object`. |
| Inside a `Serializable` class | `private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException` | Deserialization mechanism automatically if valid | Customizes restoration and validation. |
| Inside `readObject` callback | `in.defaultReadObject()` | Callback code | Restores the default field state that was written correspondingly. |

**Do not assume `out.writeObject(this)` inside a callback is equivalent to `out.defaultWriteObject()`.** Writing `this` again via an object handle does not perform the default field serialization you expect; it can produce invalid data. Use `defaultWriteObject()` to write the class's field data according to the serialization contract.

Similarly, `in.readObject()` inside a callback does not mean restoring default fields: it reads **the next object** from the data in the stream. To restore the current class's field data, use `in.defaultReadObject()`.

## 2. What Does Default Serializable Save?

A class implementing `java.io.Serializable` can be serialized with `ObjectOutputStream`. By default, the following fields are considered:

- **Instance fields** that do not have the `transient` modifier and are not `static`.
- Primitive values are written according to the serialization protocol; references to other objects may trigger serialization of the referenced objects.
- The object graph preserves multiple identity/reference relationships via the stream's handle mechanism; it is not an independent text-like copy of individual fields.
- `transient` and `static` fields are not automatically saved by the default mechanism.
- If an instance field references a non-serializable class and is not handled appropriately, writing the object graph can throw `NotSerializableException`.

Example:

```java
class Profile implements Serializable {
    private static final long serialVersionUID = 1L;
    String name;                  // Saved by default.
    int age;                      // Saved by default.
    transient String cache;       // Ignored by default.
    static String applicationId;  // Belongs to the class, not object state.
}
```

This is a **snippet** and requires importing `java.io.Serializable`. After application-level `readObject()`, `name` and `age` are normally restored from field data; `cache` defaults to `null` unless custom code restores it; `applicationId` is determined by the class's current state rather than read from the instance stream.

Using `transient` is not an absolute guarantee that a value cannot leak out. If you manually write that value via `out.writeUTF` or through another serializable field, it **still appears in the stream**. Never serialize passwords, bearer tokens, session secrets, or sensitive information just to restore the "exact state".

## 3. Exact Callback Signatures — Not Ordinary Overrides

The Java serialization mechanism recognizes callbacks in the standard form:

```java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    // Write additional custom data for the class.
}

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Read custom data and validate state.
}
```

This is a **snippet inside a class implementing `Serializable`**, with imports for `java.io.Serial`, `java.io.IOException`, `java.io.ClassNotFoundException`, `ObjectOutputStream`, and `ObjectInputStream`.

Notes:

1. `writeObject` must be a **private instance method**, return `void`, and take exactly one `ObjectOutputStream` parameter; `readObject` is similar with `ObjectInputStream` and declares the appropriate checked exceptions. These are **special hooks** that the serialization runtime looks up, not methods that `Serializable` requires you to override.
2. A `public writeObject(...)` or `static writeObject(...)` method is **not an equivalent customization callback**. Do not annotate them with `@Override`.
3. `@Serial` (Java 14+) helps the compiler verify intent for serialization-related members; from Java 17 it can be used reliably. It is not required for the mechanism to work, but it helps catch declaration mistakes.
4. Callbacks apply to a specific class in the serializable hierarchy; **private methods are not inherited like regular overrides**.
5. Inside a callback, `defaultWriteObject/defaultReadObject` only work when in the **appropriate active serialization/deserialization context**. Calling them outside that context can throw `NotActiveException`.

Giving `readObject` the wrong signature prevents the JVM from automatically running your intended validation/restoration code. This is a dangerous bug because the program may still read successfully while creating an object that violates invariants.

## 4. Standard Order When Writing and Reading

When you need to preserve default fields **and** append optional custom data:

```text
Application                  Serializable Class
───────────                  ──────────────────────────
out.writeObject(order)
                              private writeObject(out)
                               ├─ defaultWriteObject()
                               │    writes default serializable fields
                               ├─ writeInt(version)
                               ├─ writeBoolean(hasNote)
                               └─ writeUTF(note) if present
                         → bytes in ObjectOutputStream

in.readObject()
                              private readObject(in)
                               ├─ defaultReadObject()
                               │    restores default field data
                               ├─ readInt() custom data version
                               ├─ readBoolean()
                               ├─ readUTF() if present
                               ├─ validate invariants
                               └─ rebuild transient/derived state
                         → restored object
```

Both ends must be **symmetric in order and data types**:

- If `int` is written first, `int` must be read first.
- If a `boolean` is written followed conditionally by `UTF`, the reading side must follow that exact logic.
- If `defaultWriteObject()` comes first, `defaultReadObject()` must also precede reading the optional custom data.
- Do not read until EOF of the entire `ObjectInputStream` to determine the end of an object's data: the stream has framing and may contain multiple subsequent objects.
- Do not arbitrarily mix raw bytes outside `ObjectOutputStream` with bytes in the serialization stream in a way that breaks headers/protocol.

`defaultWriteObject()` **does not save transient fields**. To restore a transient field that is safe to persist, the callback must **explicitly write it** and read it back correspondingly. For recomputable caches, you usually just rebuild them after `defaultReadObject()` rather than storing cache bytes.

## 5. Standalone Java 17+ Example: All Four Methods Working Together

The example uses an `Order` object with:

- `id` (String) and `cents` (int): saved via `defaultWriteObject`.
- `auditNote` as `transient`: **not** part of default data, but **explicitly written** as optional data to demonstrate the hook.
- `runtimeLabel` as `transient`: not written; `readObject` recreates it with the value `restored`.
- `formatVersion` in the custom section to detect unsupported formats.
- Validation that id is non-blank and amount is non-negative during deserialization.

Save as **`CustomSerializationDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class CustomSerializationDemo {
    private static final class Order implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private String id;
        private int cents;
        private transient String auditNote;
        private transient String runtimeLabel;

        Order(String id, int cents, String auditNote) {
            this.id = id;
            this.cents = cents;
            this.auditNote = auditNote;
            this.runtimeLabel = "constructed";
        }

        @Serial
        private void writeObject(ObjectOutputStream out) throws IOException {
            out.defaultWriteObject();
            out.writeInt(1);
            out.writeBoolean(auditNote != null);
            if (auditNote != null) {
                out.writeUTF(auditNote);
            }
        }

        @Serial
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            int formatVersion = in.readInt();
            if (formatVersion != 1) {
                throw new InvalidObjectException("Unsupported version");
            }
            auditNote = in.readBoolean() ? in.readUTF() : null;
            if (id == null || id.isBlank() || cents < 0) {
                throw new InvalidObjectException("Invalid order");
            }
            runtimeLabel = "restored";
        }

        String describe() {
            return "id=" + id + ",cents=" + cents
                    + ",note=" + auditNote + ",label=" + runtimeLabel;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        Order original = new Order("A-17", 1250, "verified");

        byte[] data;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(original);
            out.flush();
            data = bytes.toByteArray();
        }

        Order copy;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(data))) {
            copy = (Order) in.readObject();
        }

        System.out.println("original: " + original.describe());
        System.out.println("copy: " + copy.describe());
        System.out.println("different-instance=" + (original != copy));
        System.out.println("nonempty-stream=" + (data.length > 0));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CustomSerializationDemo.java
java CustomSerializationDemo
```

Stdout verified by compiling and running on JDK 17+:

```text
original: id=A-17,cents=1250,note=verified,label=constructed
copy: id=A-17,cents=1250,note=verified,label=restored
different-instance=true
nonempty-stream=true
```

**Accurate interpretation of the mechanism:**

1. When the application calls `out.writeObject(original)`, the runtime looks up the `Order.writeObject` callback with the matching signature.
2. `out.defaultWriteObject()` writes `id` and `cents` as the serializable field data of `Order`. It does not automatically write `auditNote` or `runtimeLabel` because both are `transient`.
3. The callback appends `int 1` to mark the format, a `boolean` indicating whether the audit note is present, and then `writeUTF("verified")`.
4. When the application calls `in.readObject()`, the runtime allocates the object via the serialization mechanism and invokes `Order.readObject`; `in.defaultReadObject()` restores `id/cents`.
5. The reading side consumes the custom version/boolean/UTF, validates id/amount, and sets `runtimeLabel = "restored"` instead of executing `Order`'s constructor.
6. `original != copy` because the read object is a new instance in the process; however, the reference graph within the stream still follows Java serialization's handle/identity rules.
7. The two lines showing the audit note prove that a `transient` field **can be serialized manually**. This is merely an example note and **must not** be taken as permission to put secret tokens into a byte stream.

In a small demo, `ByteArrayOutputStream` makes comparison easy. For large data, you need quotas, proper streaming, and an appropriate read/write strategy; do not buffer unbounded Java serialized byte streams in RAM just to simplify the API.

## 6. What Happens If defaultWriteObject or defaultReadObject Is Omitted?

When a class defines its own callback, default writing/reading **does not happen automatically** as it does for classes without custom callbacks. Therefore, if you omit `out.defaultWriteObject()` in the example:

- Non-transient fields like `id` and `cents` are no longer written automatically as part of that class's default field data.
- When reading while still calling `defaultReadObject()`, you may receive default/missing values or errors because the stream/class descriptor does not match expectations.
- Code checking `id == null` might catch the invalid state, but this should not be treated as a fallback mechanism for a proper format.

Conversely, if default field data is written without calling `in.defaultReadObject()`, the reader does not restore those fields via the class's default API. The data to be read and the optional sections risk being misinterpreted or skipped.

When you genuinely want to **write only custom-defined data**, you can design a custom format without calling the default methods, provided you understand the protocol precisely and maintain compatibility across all reader/writer versions. For most `Serializable` classes that need extra information, the easiest pattern to control is:

```java
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    out.writeInt(customVersion);
    // Extra fields in the defined order.
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    int customVersion = in.readInt();
    // Read in the exact order and validate lengths/values.
}
```

This is **pseudocode** inside a serializable class: `customVersion` must have a value before writing, not a standalone program. The default methods should only be called **once** and within the appropriate callback context.

## 7. transient, Derived Fields, and Restoring Invariants

A `transient` field typically falls into one of three categories:

| Category | Examples | What to Do After Reading? |
| --- | --- | --- |
| Recomputable cache | Preformatted values, derived statistics, lookup caches | Initialize empty or recompute; no need to serialize. |
| Runtime resource | File handle, socket, thread, logger with special lifecycle | Do not serialize directly; reopen/allocate as needed for the new lifecycle. |
| Data that must persist but not as a default field | Version compatibility fields, persistable snapshot metadata | If genuinely needed, explicitly write/read under a custom protocol and constrain the data. |

**Do not rely on the Serializable class's own constructor or field initializers** to restore transient state: during deserialization, constructors of serializable classes are not invoked as in normal object creation. The no-arg constructor of the first **non-Serializable** superclass may be invoked according to Java's rules.

Thus, if `runtimeLabel` must always be non-null, recreate it inside `readObject()`. If the object has critical invariants, such as `id != null`, `amount >= 0`, or mutually constrained attributes, enforce validation upon restoration.

Pattern:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (id == null || id.isBlank() || cents < 0) {
        throw new InvalidObjectException("Invalid order");
    }
    runtimeLabel = "restored";
}
```

This is a **snippet** for a class with fields `id`, `cents`, `runtimeLabel` that writes no extra data; if the writer writes custom fields, the reader must also read that section before completing the callback. Reject invalid objects immediately upon reading instead of letting bad state enter business logic.

Be careful when a class has cross-references within an object graph: `readObject` may execute while other objects in the graph are not yet fully restored. Do not publish `this` to another thread, a global registry, or code with side effects before the graph is verified.

## 8. serialVersionUID and Custom Data Versions Are Two Different Things

Two kinds of versions:

- **`serialVersionUID`:** identifies the serialization compatibility version of the class; if the class UID in the stream is incompatible with the local class, `InvalidClassException` may be thrown before custom deserialization can even handle it.
- **Self-written `formatVersion`:** an application-defined marker inside the callback's **optional data**; helps distinguish custom extra-data layouts when all other protocol/class conditions remain compatible.

```java
@Serial
private static final long serialVersionUID = 1L;

@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    out.writeInt(2); // Separate schema for the custom data section.
}
```

This is a snippet, not a complete example. When changing the optional-data version from 1 to 2, **the reader must include branches for both** if backward compatibility is required. Simply adding `writeInt(2)` while forgetting to update `readObject` will cause older readers to reject or misread the data.

Do not arbitrarily change `serialVersionUID` every time you add an optional field. The UID exists to govern compatibility of the **class serialization schema**. Keeping the UID fixed does not automatically guarantee that every change is safe: changing field types, class hierarchy, making a field `transient`, altering callback protocols, or switching to a serialization proxy all require real version/cross-version testing.

Certain default field changes follow Java serialization evolution rules, whereas optional data is **your own protocol that you are responsible for**. Keep fixtures containing bytes generated by older versions and test both old writer → new reader (and vice versa if the product requires it).

## 9. Optional Data, writeObject/readObject, and Symmetry

After `defaultWriteObject()`, a callback can write primitives or serializable objects:

```java
// Snippet: inside private writeObject(...)
out.defaultWriteObject();
out.writeInt(customSchema);
out.writeBoolean(optionalValue != null);
if (optionalValue != null) {
    out.writeUTF(optionalValue);
    out.writeObject(additionalObject);
}
```

Reading side:

```java
// Snippet: inside private readObject(...)
in.defaultReadObject();
int schema = in.readInt();
boolean present = in.readBoolean();
if (present) {
    String optionalValue = in.readUTF();
    Object additionalObject = in.readObject();
}
```

The variables `customSchema`, `optionalValue`, and `additionalObject` belong to application logic. `readObject()` inside a callback reads a **secondary** object, distinct from `defaultReadObject()` which restores default fields. You must determine allowed types for the secondary object, evaluate the trust level of the source, and avoid allowing unauthorized classes into the graph.

**Do not use `readUTF()` to read bytes written by `writeObject(String)` or vice versa.** The two methods use different encodings/protocols. `writeUTF/readUTF` uses modified UTF-8 and has the byte-length limit of that UTF format, rather than being an unbounded general-purpose string writer.

The custom data section needs a clear schema: ordering, markers, optional/null handling, size limits, handling of newer versions, and error handling when data is truncated. Do not let the reader "guess" from the remaining bytes of the entire stream; serialization framing spans the whole object graph.

## 10. When to Use putFields/readFields Instead of Default Methods?

Java also provides `ObjectOutputStream.PutField` and `ObjectInputStream.GetField` for cases where you want to control **the default field values serialized** without directly mutating runtime field state before writing.

```java
// Snippet inside private writeObject(...)
ObjectOutputStream.PutField fields = out.putFields();
fields.put("name", name);
fields.put("age", age);
out.writeFields();
```

And:

```java
// Snippet inside private readObject(...)
ObjectInputStream.GetField fields = in.readFields();
String restoredName = (String) fields.get("name", "");
int restoredAge = fields.get("age", 0);
```

These are snippets for a class with corresponding serializable fields and proper imports; `serialPersistentFields` can be used when defining a logical field set independent of the in-memory representation. **Do not mix `defaultWriteObject()` with `putFields/writeFields()` for the same default field data**; the two paths are mutually exclusive alternatives. The reading side likewise chooses either `defaultReadObject()` or `readFields()` correspondingly within the callback context.

Use `PutField/GetField` when maintaining meaningful legacy/virtual schemas, though it is a lower-level and more error-prone API. For learning the common mechanism, start with the `defaultWriteObject/defaultReadObject` pair.

## 11. Notes on Object Graphs and Stream Handles

`ObjectOutputStream` maintains a handle table to preserve identity when the same object is written multiple times on **the same stream**:

```java
out.writeObject(order);
out.writeObject(order);
```

Provided the object is not replaced by a special hook, the reading side can receive **the exact same instance in the graph** for the two corresponding calls, rather than always creating a second copy. This matters if the application modifies a field after the first write and assumes the second write will definitely record a fresh snapshot.

If you need the stream to write new state in a controlled way, study `ObjectOutputStream.reset()`, `writeUnshared()`, and define the application's synchronization semantics. **Do not call `reset()` arbitrarily** when the graph has reference relationships that must be preserved across different objects; altering handle semantics affects the reader.

Do not naively create a new `ObjectOutputStream` to "append" more objects to the end of an existing serialized file: the constructor writes a new stream header, which easily causes a sequential `ObjectInputStream` to throw `StreamCorruptedException`. If you need reliable append/update persistence, consider a self-describing record format or another storage solution.

## 12. Hierarchy, Inheritance, and Related Hooks

An object may consist of multiple serialization data segments belonging to different serializable classes in a hierarchy. Each class can have **its own** `writeObject/readObject` callbacks. They are not overridden methods in the usual polymorphic sense.

Important details:

- A `Serializable` subclass can have its own private callbacks; a `Serializable` superclass can have separate private callbacks.
- A non-serializable superclass is typically initialized via the no-arg constructor of the first non-serializable class in the hierarchy during deserialization. Fields in a non-serializable superclass are not automatically restored like serializable fields.
- `readObjectNoData()` is an optional special hook to handle cases where there is no serialization data for a class during certain hierarchy/version changes. It does **not** replace regular `readObject()`.
- `writeReplace()` and `readResolve()` can replace the object being written/read, leading to the **serialization proxy** pattern. This is a strong choice for immutable classes, though it has its own rules for object identity, compatibility, and validation.
- `Externalizable` is a **different** mechanism: code implements `writeExternal/readExternal` and constructor lifecycle per the Externalizable contract, not by adding `defaultWriteObject()` like a Serializable class.

If a class has invariants spanning multiple fields or should not allow object creation that bypasses constructors via serialization, consider the serialization proxy pattern or dropping support for Java native serialization.

## 13. Common Exceptions and Diagnostics

| Exception / Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `NotSerializableException` | An object in the graph does not implement Serializable, or there is no serialization strategy for the related field. | Choose serializable data; mark transient and recreate properly if appropriate. |
| `InvalidClassException` | Incompatible UID/class descriptor, or object construction preconditions violated. | Manage serialVersionUID, migrations, and compatibility tests. |
| `StreamCorruptedException` | Corrupted stream header/format, improperly concatenated data, or writing bytes outside the serialization protocol. | Use paired Object streams properly; do not arbitrarily concatenate headers. |
| `OptionalDataException` | Reader expects an object but encounters primitive optional data, or optional data does not match schema. | Balance read/write order and distinguish `readObject` from primitive reads. |
| `EOFException` | Byte stream truncated before enough data requested by the reader. | Check truncation, transport, framing, and retry/abort per policy. |
| `ClassNotFoundException` | Class to restore is missing from the corresponding classpath/module. | Check deployed versions and dependencies; disallow arbitrary external classes. |
| `InvalidObjectException` | `readObject` intentionally rejects an object violating schema/invariants. | Keep validation, fix writer/data source, never bypass checks. |
| `NotActiveException` | Calling `defaultReadObject/defaultWriteObject` outside a valid active callback. | Call only within the proper runtime callback context. |
| `transient` field is null after read | Not written by default, Serializable constructor does not run. | Recreate in `readObject` or lazy-init after reading. |
| Callback "does not run" | Wrong signature, non-private, static, or class not Serializable. | Declare private accurately and use `@Serial` for compiler-assisted checks. |
| Reader gets wrong custom field | `writeInt/writeUTF/...` order differs from `readInt/readUTF/...` or version is unsupported. | Write symmetric schema and maintain test fixtures. |
| Same object written twice "does not update" | Stream handle table preserves object identity; subsequent write may be a reference. | Design clear snapshot/stream lifecycle; study `reset()` appropriately. |

Never try to "fix" an exception by removing validation or catching everything and returning an incomplete object. Deserialization failure must be treated as a parse/validation error, with resources and application state cleaned up safely.

## 14. Security: Never Treat readObject as a Safe Parser for Arbitrary Input

Serialization is **a mechanism for instantiating an object graph where code can be invoked during reading**. When `ObjectInputStream.readObject()` processes bytes from an untrusted source, reading classes/graphs can trigger `readObject`, `readResolve`, and logic in other classes on the classpath before you even have a chance to cast or inspect values afterward.

Risks include:

- Gadget chains and unintended side effects on the classpath.
- Resource exhaustion from deep graphs, huge object counts, large arrays, or unbounded custom data.
- Objects with broken invariants (e.g., negative amounts, nulls in required fields) if the reader fails to validate.
- Sensitive data accidentally leaking into the stream, or custom callbacks explicitly writing secrets.
- Unexpected version data causing the reader to fail or apply outdated logic erroneously.

Minimum safeguards:

1. **Do not deserialize untrusted data** if you can design around it with a less powerful format.
2. If unavoidable: configure an `ObjectInputFilter`/serialization filter **before calling `readObject()`**, allowlist only strictly required classes, and limit depth, reference count, byte size, array length, and related resources.
3. Protect both transport and data source: authentication, authorization, integrity/authenticity checks; filters do not replace these mechanisms.
4. Validate all invariants inside the callback or proxy; reject invalid data with an exception such as `InvalidObjectException`.
5. Enforce quotas/timeouts on custom data sections; `ObjectInputFilter` does not automatically understand all business logic inside a custom callback.
6. Do not assume casting after `readObject()` makes it safe, because side effects may already have occurred.
7. Keep dependencies updated and conduct security testing; never assume safety just because your application's object class looks "simple".

**Note:** A filter is not an absolute silver bullet for every gadget/class and does not prevent intentional tampering with serialized bytes. For inter-service communication, schema-validated formats with explicit authentication are usually a better choice than native Java serialization.

## 15. Testing Correctness and Compatibility

A useful test suite should include:

| Test Type | What to Prove |
| --- | --- |
| Basic roundtrip | Write an object and read it back; default fields and optional data match. |
| Transient rebuild | Fields not saved automatically are properly reinitialized without stale unwanted values. |
| Null optional field | Boolean/marker accurately signals absence without over-reading `readUTF`. |
| Invalid invariants | Reader rejects null id, negative values, conflicting states, or malformed fields. |
| Unsupported custom version | Reader throws an intentional exception and produces no usable object. |
| UID/class mismatch | Incompatible class versions are detected without false success. |
| Truncated stream | Reader fails cleanly without exposing a partial object. |
| Cyclic/duplicate reference graph | Identity/reference semantics hold per the stream contract. |
| Old writer → New reader | Optional data schema has the expected backward compatibility. |
| Old reader → New writer | Verify forward compatibility if required by business rules; may intentionally reject. |
| High volume | Quotas, latency, size limits, and resource cleanup. |
| Untrusted source | Verify filters and ensure Java native deserialization is not used for public bytes unnecessarily. |

For the demo output, only verify `different-instance=true` and the relevant fields; do not compare exact serialized byte counts because implementation/class details can alter sizes and byte counts do not establish application schema correctness.

## 16. Practice Exercises

**Exercise 1 — Compare default vs. custom.** Create a class with only `implements Serializable` and no callbacks; roundtrip 2 regular fields and 1 transient field. Then add `writeObject/readObject`, properly use `defaultWriteObject/defaultReadObject`, and observe how the results change.

**Exercise 2 — Null optional field.** Using `CustomSerializationDemo`, pass `auditNote = null`. Trace the logical bytes: write `boolean false`, write no UTF; the reader must get back `null` without executing `readUTF()`.

**Exercise 3 — Validate invariants.** Extend Order with `quantity` and `unitPrice`, requiring cents to equal the product of the two values within overflow-safe bounds. Validate in `readObject` using overflow-safe math; explain why validation must happen before publishing the object.

**Exercise 4 — Versioning extra data.** Create custom version 1 storing only a boolean, and version 2 adding a string. Write a reader that switches on version, handles v1/v2 in exact order, and rejects unsupported future versions. Keep byte fixtures for each version.

**Exercise 5 — Never write secrets.** Add a transient `authToken` used only at runtime. Roundtrip the object and verify that after deserialization the token is null or reissued by the auth system, **not** written via optional data.

**Exercise 6 — Hook signatures.** Intentionally change the callback to `public void readObject(...)` or omit a parameter. Use `@Serial` and the compiler to spot the difference; explain why this is not a normal method override.

**Exercise 7 — Reading graphs.** Create two fields pointing to the same Address instance. After roundtrip, verify reference identity in the new object, not just `equals`. Try calling `writeObject` twice on the same object in a single stream and inspect the handle table behavior.

**Exercise 8 — Security boundary check.** Configure a filter limiting depth, references, bytes, and allowed classes for a test with self-generated data. Compare this with serializing a DTO to JSON with a controlled schema. Do not use exploit payloads, and do not accept serialized streams from users in a real service.

### Self-Check Questions

1. How does `ObjectOutputStream.writeObject(obj)` differ from `private writeObject(ObjectOutputStream)`?
2. Why does a callback need to call `defaultWriteObject()` if you still want to keep regular fields?
3. Does `defaultReadObject()` automatically restore `transient` fields?
4. If `defaultWriteObject()` is followed by writing `int, boolean, UTF`, what must the reader call and in what order?
5. Why are `@Serial` and the `private` modifier important for callbacks?
6. Why does `serialVersionUID` not replace a custom version for optional data?
7. Why cannot the constructor of a Serializable class handle full cache restoration?
8. Why should you not serialize a bearer token even if the field is marked `transient`?
9. Why must the filter be configured **before** calling `readObject()`?
10. What bug can occur if the same stream writes the same object twice while the application expects a fresh snapshot?

## 17. References

- [Java SE 21 — Serializable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html): private callback contracts, serialVersionUID, readObjectNoData, writeReplace/readResolve.
- [Java SE 21 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html): writeObject, defaultWriteObject, putFields, handles, reset, and writing protocol.
- [Java SE 21 — ObjectInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html): readObject, defaultReadObject, readFields, and exceptions.
- [Java SE 21 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html): filtering classes/object graphs and resource limits.
- [Java SE 21 — @Serial](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serial.html): annotation supporting serialization structure checks.
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html): format, class evolution, and protocol details.

**Takeaway:** `writeObject/readObject` are private callbacks of a Serializable class; `defaultWriteObject/defaultReadObject` handle default field data, while `writeInt/writeUTF/readInt/readUTF` handle supplementary data in symmetric order. Restore transient state and validate invariants explicitly, maintain proper versioning, and never use Java native deserialization with untrusted sources.
