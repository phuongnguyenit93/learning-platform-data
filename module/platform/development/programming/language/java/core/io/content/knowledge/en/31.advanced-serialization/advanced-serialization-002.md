# `readObjectNoData()` and Hierarchy Changes in Java Serialization

## 1. The Problem: The Current Class May Have a Superclass Unknown to Old Data

`java.io.Serializable` allows a program to write an object using `ObjectOutputStream` and read it back using `ObjectInputStream`. However, between writing and reading, the class structure may have been modified. One specific scenario is when **a new version inserts a superclass implementing `Serializable`** into the hierarchy.

Old version example:

```text
Object
  └── Receipt implements Serializable
        └── id
```

New version:

```text
Object
  └── AuditInfo implements Serializable    // NEWLY added
        └── source
        └── Receipt implements Serializable // Same name and serialVersionUID
              └── id
```

The data written by the old version knows about `Receipt` but **has no descriptor/class data for `AuditInfo`**. When reconstructing the object with the new version, the JVM still has to create the state portion of `AuditInfo`, yet it cannot read bytes dedicated to this class from the old stream because they **do not exist**.

This is the exact circumstance that the special method **`private void readObjectNoData() throws ObjectStreamException`** was defined in Java Serialization to handle.

After this lesson, you will:

1. Know **when `readObjectNoData()` is invoked** and when it is not.
2. Distinguish it from `readObject(ObjectInputStream)`, `defaultReadObject()`, constructors, and field initializers.
3. Understand why hierarchy changes can leave new fields with default values `null`, `0`, `false`.
4. Write an example with **two Java source versions sharing the same class name**, serialize with version 1, and deserialize with version 2 to reproduce the callback accurately.
5. Identify the role of `serialVersionUID`, compatibility limits, and policies for rejecting invalid streams.
6. Design safe state migration without assuming every class change triggers this callback.

The scope of this lesson is **default Java Object Serialization for regular classes implementing `Serializable`**; it does not apply directly to enums, records, or `Externalizable`.

## 2. What Does a Serial Stream Contain?

When writing an object:

```java
try (ObjectOutputStream output = new ObjectOutputStream(
        Files.newOutputStream(path))) {
    output.writeObject(someSerializableObject);
}
```

This is a **snippet**: `path` and `someSerializableObject` are already declared, and imports plus checked exception handling are required. `ObjectOutputStream` encodes the object graph according to the Serialization protocol: type descriptors, version metadata, and the fields to be serialized, per class in the corresponding hierarchy.

When reading:

```java
try (ObjectInputStream input = new ObjectInputStream(
        Files.newInputStream(path))) {
    Object value = input.readObject();
}
```

This is also just a snippet. `ObjectInputStream` restores the object using the **class definitions present on the reader side**. It compares the stream's metadata with local classes and must handle the old stream / new local class scenario.

An easily forgotten detail: a serial stream **does not** contain the raw heap bytes of an object. It contains fields/descriptors according to the Serialization protocol. `static` and `transient` variables are not written by the default field mechanism; field initializers and constructors of **serializable classes** are not automatically called just to restore fields. Class-by-class restoration is critical when the hierarchy changes.

For a hierarchy like:

```text
A (non-Serializable)
  └── B implements Serializable
        └── C implements Serializable
```

When deserializing an instance of `C` under the normal protocol:

- The JVM allocates the object with default values for its fields.
- The no-arg constructor of the **nearest non-serializable superclass** (`A`) is invoked according to the Serialization mechanism.
- Constructors and field initializers of `B` and `C` **do not run via the normal instance creation path**.
- State of Serializable classes is restored in order from superclass down to subclass. For each class that has corresponding data, Java uses default field restoration or that class's `readObject` hook.
- For a **Serializable class present in the local hierarchy that has no corresponding data slot in the stream**, Java may invoke that class's `readObjectNoData` hook.

## 3. What Exactly Does `readObjectNoData()` Do?

Per Java SE 17, the special signature is:

```java
@Serial
private void readObjectNoData() throws ObjectStreamException {
    // Initialize fields declared by this class itself,
    // if the stream does not list this class as a corresponding superclass.
}
```

This is a **snippet**, must reside inside a `Serializable` class, and requires importing `java.io.Serial` and `java.io.ObjectStreamException`. The `@Serial` annotation is supported in Java 17 and helps the compiler/lint tools recognize declarations tied to Serialization; the annotation itself **does not** determine whether the callback is invoked.

### Trigger Contract

The hook is called when deserializing an instance of a subclass and **the serialization stream does not list a local Serializable class as a superclass of that instance**. The typical scenario is a writer using an older version with a shorter hierarchy, and a reader using a newer version that added a new Serializable superclass.

Java also notes the possibility of an incomplete stream or one tampered with to omit class data, so this hook is also useful for **restoring invariants** or rejecting unsafe states.

### Conditions NOT Sufficient to Trigger the Hook

- **Adding a new field to the same existing class** does not automatically trigger `readObjectNoData()`; that class's data slot is still present in the stream. A new field absent from the stream usually receives its type's default value.
- A field having value `null` in the stream does not mean **there is no class data**.
- When the local class still has corresponding data and declares `readObject(ObjectInputStream)`, Java processes it via `readObject` (if valid), **not** `readObjectNoData`, merely because some field is missing.
- Calling `new MyClass()` normally does not execute `readObjectNoData`.
- Do not assume "adding any superclass" triggers it: what matters is that **the specific local Serializable class has no corresponding slot in the stream**, while the overall hierarchy still satisfies all other compatibility requirements.
- `Externalizable` has its own protocol via `readExternal` and a public no-arg constructor; do not replace `readExternal` with this hook.

### Scope of Responsibility

`readObjectNoData()` must restore **the fields and invariants of the class defining the hook**, rather than trying to read subclass data. There is no `ObjectInputStream` parameter because **there is no data dedicated to this class to read**.

It may throw `ObjectStreamException`, commonly using the subclass `InvalidObjectException` when there is no safe way to restore state.

## 4. Distinguishing Serialization Hooks

| Hook / Mechanism | When Relevant | Role |
| --- | --- | --- |
| `private void writeObject(ObjectOutputStream out)` | When serializing a Serializable class with custom write | Writes default/custom data for **that class's slot** |
| `private void readObject(ObjectInputStream in)` | When the stream has corresponding class data and the class declares a valid hook | Reads/restores the class's state; may call `defaultReadObject()` |
| `private void readObjectNoData()` | When a local Serializable superclass has **no corresponding slot** in the stream | Initializes/rejects the class's state since there is no data to read |
| `in.defaultReadObject()` | Called **inside `readObject`** to restore default fields of the current slot | Not a standalone callback function |
| `private Object readResolve()` | Object resolution phase after deserialization per supported mechanism | Can substitute the object with another object |
| Constructor of a Serializable class | Creating a new object with `new` | **Does not** run during normal deserialization |
| No-arg constructor of the first **non-Serializable** superclass | When deserializing an instance of a Serializable class | Initializes the non-serializable state portion |
| `Externalizable.readExternal(ObjectInput)` | For Externalizable classes | Reads data according to a contract managed by the class |

`readObjectNoData` and `readObject` are two **different opportunities** for the same serializable class. If the local class appears in the stream hierarchy but a new field did not yet exist, the solution may be using `readObject`/`readFields` to handle that class's version; the `readObjectNoData` hook is **not** a general-purpose callback for every schema change.

## 5. Signature and Visibility Must Be Exact

Recommended declaration:

```java
import java.io.ObjectStreamException;
import java.io.Serial;
import java.io.Serializable;

public class ExampleBase implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String source;

    @Serial
    private void readObjectNoData() throws ObjectStreamException {
        source = "legacy";
    }
}
```

This is a **standalone compilable** class if saved as `ExampleBase.java`. It only illustrates how to define the hook; `new ExampleBase()` **does not** trigger the hook.

Signature mistakes to avoid:

```java
// The following lines are intentionally WRONG examples; DO NOT put them all
// into the same ExampleBase.java expecting the compiler to invoke the hook:
public void readObjectNoData() { }        // Not private
private int readObjectNoData() { return 0; } // Does not return void
private void readObjectNoData(ObjectInputStream in) { } // Wrong parameter
static void readObjectNoData() { }       // Not an instance hook
```

The method is a **private instance method, taking no parameters, returning `void`**, and may declare `throws ObjectStreamException`. `@Override` is inappropriate because this is not a method overridden from the `Serializable` interface; `Serializable` is just a **marker interface** and declares no `readObjectNoData` method to implement.

`@Serial` is an annotation supporting verification of the hook's shape; writing the wrong visibility/return type can turn the method into an ordinary method not called by deserialization as intended. Do not rely on a unit test merely compiling to confirm the callback is actually recognized — you need to run a **stream evolution** scenario.

## 6. Complete Example: Writing a v1 Object, Reading with the v2 Hierarchy

We use **two versions of a class with the exact same fully qualified name** `evolution.Receipt` compiled into **two separate output directories**, so the writer (v1) and reader (v2) do not accidentally mix class versions.

### Version v1: `Receipt` Directly Extends `Object`

Directory structure:

```text
v1/
└── evolution/
    ├── Receipt.java
    └── WriteV1.java
```

**File `v1/evolution/Receipt.java`**

```java
package evolution;

import java.io.Serial;
import java.io.Serializable;

public final class Receipt implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String id;

    public Receipt(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
```

**File `v1/evolution/WriteV1.java`**

```java
package evolution;

import java.io.ObjectOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class WriteV1 {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: WriteV1 <output-file>");
        }

        Path output = Path.of(args[0]);
        Receipt receipt = new Receipt("R-42");

        try (ObjectOutputStream out = new ObjectOutputStream(
                Files.newOutputStream(output))) {
            out.writeObject(receipt);
        }

        System.out.println("v1 wrote id=" + receipt.id());
    }
}
```

The object data in `receipt.ser` created by **v1** contains the descriptor and serialized field of `evolution.Receipt`; it cannot have an `AuditInfo` slot because that class **did not yet exist in the v1 hierarchy**.

### Version v2: Inserting Serializable Superclass `AuditInfo`

Structure:

```text
v2/
└── evolution/
    ├── AuditInfo.java
    ├── Receipt.java
    └── ReadV2.java
```

**File `v2/evolution/AuditInfo.java`**

```java
package evolution;

import java.io.ObjectStreamException;
import java.io.Serial;
import java.io.Serializable;

public class AuditInfo implements Serializable {
    @Serial
    private static final long serialVersionUID = 5L;

    private String source = "field-initializer";

    protected AuditInfo() {
        source = "constructor";
        System.out.println("AuditInfo constructor");
    }

    @Serial
    private void readObjectNoData() throws ObjectStreamException {
        // v1 stream has no AuditInfo slot.
        source = "legacy";
        System.out.println("AuditInfo.readObjectNoData");
    }

    public String source() {
        return source;
    }
}
```

**File `v2/evolution/Receipt.java`**

```java
package evolution;

import java.io.Serial;
import java.io.Serializable;

public final class Receipt extends AuditInfo implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String id;

    public Receipt(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
```

Note: the fully qualified name of `Receipt` and the value `serialVersionUID = 1L` **remain identical** to v1. In v2, `AuditInfo` is also Serializable, so `AuditInfo`'s constructor and field initializer do not execute via the normal instance creation path when deserializing `Receipt`.

**File `v2/evolution/ReadV2.java`**

```java
package evolution;

import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadV2 {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ReadV2 <input-file>");
        }

        try (ObjectInputStream in = new ObjectInputStream(
                Files.newInputStream(Path.of(args[0])))) {

            Receipt result = (Receipt) in.readObject();

            System.out.println("v2 read id=" + result.id());
            System.out.println("v2 read source=" + result.source());
        }
    }
}
```

### Compiling into Two Separate Classpaths

From the directory containing `v1` and `v2`, using a shell with `mkdir -p` (Linux/macOS/Git Bash):

```bash
mkdir -p build/v1 build/v2

javac -d build/v1 v1/evolution/Receipt.java v1/evolution/WriteV1.java
java -cp build/v1 evolution.WriteV1 receipt.ser

javac -d build/v2 v2/evolution/AuditInfo.java v2/evolution/Receipt.java v2/evolution/ReadV2.java
java -cp build/v2 evolution.ReadV2 receipt.ser
```

With **Windows PowerShell**, create directories via `New-Item -ItemType Directory -Force build/v1,build/v2` (or appropriate `mkdir`), then run `javac`/`java` similarly; `/` in classpath paths here is supported by Java on Windows. The source files must be saved inside an `evolution` directory because of the `package evolution;` declaration.

**Stdout when both `java` commands succeed, in exact execution order:**

```text
v1 wrote id=R-42
AuditInfo.readObjectNoData
v2 read id=R-42
v2 read source=legacy
```

**There is no `AuditInfo constructor` line.** Because `AuditInfo` is a serializable superclass of the local `Receipt`, when restoring the object Java does not invoke the constructor or field initializer of that Serializable class. Instead, because the v1 stream **does not list `AuditInfo`**, Java calls `readObjectNoData()` and we set `source = "legacy"`.

Step-by-step mechanics:

1. Run **v1**: JVM loads v1's `evolution.Receipt` and writes an object containing `id="R-42"`.
2. Run **v2**: JVM loads v2's `evolution.Receipt`, which now extends `AuditInfo`.
3. The old stream still has a `Receipt` descriptor compatible in name and `serialVersionUID`; the `id` field is restored via default serialization.
4. The JVM detects that the local v2 hierarchy includes `AuditInfo` while the stream lacks a slot for this class.
5. `AuditInfo.readObjectNoData()` is called to initialize the new superclass's own state. It sets `source` to `legacy`.
6. The complete `Receipt` object has `id=R-42` from old data and `source=legacy` from the new superclass's migration rule.

**Do not run `WriteV1` with the v2 classpath**: the resulting file would contain the `AuditInfo` slot, defeating the test. **Do not run `ReadV2` with the v1 classpath**: the reader would lack the new superclass. You must have **two separate Java processes with two versions sharing the name `Receipt`** to properly observe the schema evolution mechanism.

## 7. What Happens If `readObjectNoData()` Is Omitted?

In v2, temporarily **remove only the `readObjectNoData` method from `AuditInfo`**, recompile `build/v2`, and run `ReadV2` on **the same `receipt.ser` file created by v1**. Then:

- `AuditInfo` is still a new Serializable superclass absent from the stream.
- Because there is no hook to initialize it, `AuditInfo`'s fields take the JVM's default values.
- `source` is a `String` reference field, so its value becomes **`null`**, not `"field-initializer"` or `"constructor"`.
- `Receipt.id` can still be restored from the corresponding `Receipt` slot, provided other compatibility conditions remain satisfied.

Expected relevant lines:

```text
v2 read id=R-42
v2 read source=null
```

Key explanation: **field initializers of a new Serializable superclass do not run when reading an old object**. If the class assumes `source` is always non-null (for example calling `source.trim()`), the deserialized object can violate invariants and cause hard-to-trace failures elsewhere.

That is why `readObjectNoData()` is valuable at the **restoring valid state** level rather than merely "to log a callback".

## 8. Restoration Order Across the Hierarchy

Java Object Serialization processes Serializable classes in **superclass-to-subclass** order when restoring class data.

For the new hierarchy:

```text
Object
   |
 AuditInfo (Serializable, NO class data in v1 stream)
   |
 Receipt   (Serializable, HAS class data in v1 stream)
```

Conceptual flow:

```text
readObject() on ObjectInputStream
         |
         v
allocate Receipt instance per Serialization protocol
         |
         v
initialize appropriate non-Serializable superclass part (if any)
         |
         v
AuditInfo: no stream slot -> readObjectNoData()
         |
         v
Receipt: has stream slot -> read/restore Receipt.id field
         |
         v
return restored Receipt
```

When `AuditInfo.readObjectNoData()` runs, **Receipt-specific state may not have been restored yet**. Therefore:

- Do not call **overridable** methods from `readObjectNoData` if they could dispatch to a subclass and read unready state.
- Focus on setting state belonging to the superclass itself.
- If an invariant depends simultaneously on multiple levels (such as `Receipt.id` and `AuditInfo.source`), use a strategy to **validate after the entire object graph is restored** via supported APIs, such as `ObjectInputValidation` registered from an appropriate `readObject` hook.
- Do not expose an incompletely restored `this` reference to a global cache, background thread, or public callback.

This resembles the risk of calling overridable methods inside a constructor: the object is undergoing incomplete initialization.

## 9. `serialVersionUID` and Hierarchy Changes

In the example, both v1 and v2 declare:

```java
@Serial
private static final long serialVersionUID = 1L;
```

for **the same class `evolution.Receipt`**. This matters because `ObjectInputStream` compares version information to decide whether the local class descriptor can be used.

| Change | Consequence to Consider |
| --- | --- |
| Keep class name and compatible `serialVersionUID` | Allows remaining versioning rules to be evaluated |
| Add a new local Serializable superclass | May trigger that superclass's `readObjectNoData` if old stream lacks its slot |
| Change `serialVersionUID` of `Receipt` | May throw `InvalidClassException` when reading old streams |
| Rename package/class `Receipt` | Reader may fail to resolve the class; `ClassNotFoundException` or other errors |
| Add a field directly to `Receipt` | New field typically gets default value if missing from stream; does not automatically call `readObjectNoData` on Receipt |
| Change field type / Serializable contract / externalization | May be incompatible; hooks cannot "fix everything" |
| Add a **non-Serializable** superclass | Involves constructor and nonserializable state; not identical to the Serializable hook case |
| Corrupt stream source or mix multiple class versions on classpath | Can cause structural, versioning, or unexpected behavioral errors |

Setting an explicit `serialVersionUID` enables deliberate version control; **it does not guarantee every change is compatible**. Do not simply increment `serialVersionUID` as a "schema migration" and expect code to deserialize old data. Changing the UID is usually a way to declare **incompatibility** under the default protocol.

When `serialVersionUID` is omitted, the JVM computes a default UID based on class details; many class definition changes can alter that UID and block reading old data. For classes that must persist or exchange serialized data across versions, an explicit UID and versioning tests are critical steps.

## 10. Distinguishing from Adding a New Field Without Adding a Superclass

Suppose v1:

```java
class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
    private String name;
}
```

V2 keeps the same class and hierarchy but adds:

```java
class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
    private String name;
    private String region = "VN"; // NEW
}
```

These two snippets **illustrate two different versions** and must not be placed in the same source file. When deserializing a v1 object using v2, the `Customer` slot is still described by the stream. Because the `region` field is absent in the stream, it normally receives **`null`** rather than executing the `"VN"` initializer. However, **`Customer.readObjectNoData()` is not called merely because region is missing**, since `Customer`'s class data is not entirely missing.

Proper approaches for field migration:

- Use `private void readObject(ObjectInputStream in)` and `in.defaultReadObject()`, then apply defaults/validation for the new field of that class.
- Use `ObjectInputStream.GetField` / `readFields()` if you need to know specifically whether a field was present in the data and avoid confusing a valid default value with missing data.
- Build an explicit schema version in an application-controlled format with tested migrations.

Separate example of custom read (snippet inside an enclosing Serializable class):

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (region == null) {
        region = "VN";
    }
}
```

This snippet does not use `readObjectNoData()` and does not restore a new superclass slot. It is only a simple defaulting example; if `null` is a meaningful value in the new schema, distinguishing legacy data from a valid `null` requires a corresponding version/`GetField.defaulted` strategy.

## 11. Initialize Invariants or Reject Invalid Data?

`readObjectNoData()` has two primary handling directions.

### 11.1. Apply Safe Defaults

When the new class only adds metadata that does not compromise correctness, reasonable defaults can be set:

```java
@Serial
private void readObjectNoData() throws ObjectStreamException {
    source = "legacy";
    enabled = false;
}
```

The snippet assumes `source` and `enabled` belong to **the same Serializable class**. Never use default values that accidentally **grant privileges** to old objects: for instance, setting `admin=true` just because the stream lacks that information is a critical vulnerability. Defaults must follow fail-safe principles and remain transparent regarding existing data.

### 11.2. Reject Objects That Cannot Be Safely Restored

If the new superclass represents a mandatory invariant and no safe state can be inferred for legacy objects, throw `InvalidObjectException`:

```java
@Serial
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException(
            "Missing required superclass state");
}
```

The snippet requires importing `java.io.InvalidObjectException` and must reside inside a Serializable class. Because `InvalidObjectException` extends `ObjectStreamException`, it matches the signature. When the exception is thrown, `ObjectInputStream.readObject()` fails; the caller must handle it instead of treating the object as valid.

**Important:** a tampered stream can intentionally omit descriptors or data. `readObjectNoData()` **is not** a comprehensive security barrier against deserialization attacks; it merely provides a recovery/validation point in a specific situation. Treat untrusted serialized data as dangerous input.

## 12. Security: Untrusted Deserialization Is a Risk

`ObjectInputStream.readObject()` can instantiate many objects and execute state-restoration hooks/methods across the object graph. A malicious stream can exploit code present on the classpath, exhaust resources, or bypass invariant assumptions.

Measures to consider:

1. **Do not deserialize untrusted bytes whenever avoidable.** For cross-system data exchange, consider JSON, Protocol Buffers, CBOR, or formats with strictly validated schemas that do not reconstruct arbitrary object graphs.
2. If Java Serialization is unavoidable, configure an **`ObjectInputFilter`** with an appropriate allowlist and limits on depth, reference count, array size, and total bytes. Filters have their own limitations and do not replace validation.
3. Verify class identity, schema version, data origin, and invariant values after reading.
4. Do not let hooks call overridable code on incompletely restored objects or publish `this` externally.
5. Handle `InvalidClassException`, `ClassNotFoundException`, `InvalidObjectException`, and I/O errors at the input boundary; never continue using a failed stream as if nothing happened.
6. Use sample data generated by trusted code to test evolution; do not accept `.ser` files from unknown sources just to "check if they can be read".

Java SE 17 documentation warns that deserializing untrusted data is a dangerous operation; `readObjectNoData()` does not alter that warning.

## 13. Differences from `Externalizable`, Enum, and Record

### `Externalizable`

`Externalizable` extends `Serializable` but manages data through `writeExternal(ObjectOutput)` and `readExternal(ObjectInput)`, typically requiring a public no-arg constructor for restoration. Do not apply the rule "add a Serializable superclass and the `readObjectNoData` hook will handle it" as a standard migration mechanism for `Externalizable`. Depending on the problem, the class must version data within its own custom format.

### Enum

Enums have a specialized serialization form based on enum constant names; `readObject`, `readObjectNoData`, and `readResolve` hooks defined by an enum type are ignored during enum deserialization. Do not try adding this hook to an enum to fix data on hierarchy changes: enums do not have arbitrary hierarchies like regular classes.

### Record (Java 17)

Serializable records are deserialized under specialized rules, including invoking the canonical constructor to restore record components. Certain serialization hooks do not apply the same way as for ordinary Serializable classes. For records, use the corresponding record serialization rules and component/schema versioning rather than the superclass + `readObjectNoData` pattern from the `Receipt` example.

## 14. Common Mistakes and How to Fix Them

1. **Calling `readObjectNoData()` in a constructor to "trigger" it.** The hook is invoked only by Java Serialization when class data is missing; calling it manually defeats its purpose.
2. **Writing the method as `public`/`static` or with parameters.** It does not match the private instance method signature expected by Serialization.
3. **Confusing a missing field with a missing class slot.** Adding a field to a class does not automatically trigger the hook; use `readObject`/`readFields` to handle field versions.
4. **Keeping a default field initializer thinking it will run on deserialization.** For a Serializable superclass, a new field can remain `null`/`0`/`false` unless restored or fixed by a hook.
5. **Using a Serializable superclass constructor to fix old data.** Constructors of Serializable classes do not execute along the normal deserialization path.
6. **Changing `serialVersionUID` and expecting `readObjectNoData` to preserve compatibility.** A UID mismatch can trigger `InvalidClassException` before any valid object exists.
7. **Using the same `.class` directory for v1 and v2.** One version overwrites the other or the classloader loads the wrong one; use independent classpaths/processes as shown.
8. **Running a v2 writer and reading with v2 to test v1 data.** The stream already contains the new superclass slot, so the hook-triggering condition never occurs.
9. **Making the hook depend on subclass fields that are mid-restoration.** It may observe unready state; set only the current class's state or validate after graph restoration.
10. **Returning an object without safe invariants when superclass state is missing.** Use fail-safe defaults or throw `InvalidObjectException`.
11. **Treating successful deserialization as proof of trusted data.** Incorrect; verify origin, filters, versions, and invariants.
12. **Expecting the hook to "read extra bytes" from `ObjectInputStream`.** `readObjectNoData` takes no stream parameter and has no corresponding data slot to read; do not attempt to access another class's payload.
13. **Inserting a non-Serializable superclass and expecting `readObjectNoData` to run.** Distinguish this from constructor initialization of a non-serializable superclass.
14. **Treating `serialVersionUID` as an automatic schema upgrade version number.** It is a compatibility check mechanism, not a migration generator.
15. **Using `readResolve` to replace `readObjectNoData`.** `readResolve` substitutes the resulting object, not a "missing superclass data" event for a class slot.
16. **Lacking bidirectional testing across releases.** Each read/write direction can behave differently: forward compatibility and backward compatibility are not automatically symmetric.

## 15. Practice Exercises with Guided Answers

### Exercise A — Restoring a New Superclass Field

In the v2 example, add `private boolean verified;` to `AuditInfo` and set `verified=false` in `readObjectNoData()`. Why could the default `false` also appear if you omit the hook? How would you distinguish "explicitly confirmed unverified" from "missing data" at the business layer?

**Hint:** A default value alone carries no provenance information. You need migration/version rules or a distinct state such as an enum `UNKNOWN/PENDING/VERIFIED` with a safe default.

### Exercise B — Omitting the Hook and Reading Old Data

Remove `readObjectNoData` from v2 `AuditInfo`, keeping `source = "field-initializer"` and the constructor assignment `"constructor"`. Recompile v2 and read the v1 file. Predict the value of `source`.

**Answer:** `null`, because when restoring a Serializable superclass whose class data is missing, that class's field initializer/constructor does not run and there is no initialization hook.

### Exercise C — Changing Receipt's UID

In `v2/evolution/Receipt.java`, change the UID to `2L`; read `receipt.ser` generated by v1 with UID `1L`.

**Guided Answer:** Deserialization fails due to version mismatch, typically `InvalidClassException`. Do not expect `readObjectNoData` to preserve compatibility.

### Exercise D — Adding a Field Directly to Receipt

Keep the old hierarchy (without adding `AuditInfo`), and only add `String status = "NEW"` to v2 `Receipt`, keeping UID 1L. Read the v1 object. Does `Receipt.readObjectNoData()` run?

**Answer:** Not merely because `status` is a new field. The `Receipt` class slot still exists in the stream; the new field usually receives `null` and must be handled via a `readObject` hook or a separate version migration.

### Exercise E — Rejecting Streams Missing Required State

Modify `AuditInfo.readObjectNoData()` to throw `InvalidObjectException`. Run the reader on v1 data and confirm there is no `"v2 read id=..."` line.

**Guided Answer:** `ObjectInputStream.readObject()` fails and the exception propagates to the caller, so code after the call does not continue down the success path.

### Exercise F — Testing Class State Ordering

In v2 `Receipt`, add a custom `private void readObject(ObjectInputStream in)`, call `in.defaultReadObject()`, and print a line. Run the reader on v1 data and compare the log order with `AuditInfo.readObjectNoData`.

**Guided Answer:** Class data is processed superclass before subclass; `AuditInfo`'s hook runs before `Receipt`'s hook. Keep the proper checked exceptions and `@Serial` in the declaration.

## 16. Checklist When Evolving a Schema

Before releasing a new version of a Serializable class:

- [ ] List the old and new hierarchies, identifying which **class slots** were added, removed, or repositioned.
- [ ] Keep the class name and `serialVersionUID` unchanged when you want to maintain a controlled compatibility path.
- [ ] Check which parts are genuinely **Serializable**, which are non-Serializable, and which constructors will run.
- [ ] For a new Serializable superclass absent from old streams, are there invariants requiring `readObjectNoData()`?
- [ ] If only adding fields to an existing class, do not expect `readObjectNoData`; check `readObject`/`readFields` and defaulting.
- [ ] Design safe migration values; for mandatory state that cannot be inferred, reject with `InvalidObjectException`.
- [ ] Do not call overridable methods while the object is not yet fully restored; plan invariant checks after reading the whole graph.
- [ ] Test against **actual serialized bytes produced by the old version**, not just round-trips within the new version.
- [ ] Run tests in both directions v1→v2 and v2→v1 if the product requires both; clearly document which direction is supported.
- [ ] If streams come from external sources, use `ObjectInputFilter` and a policy to reject untrusted data.
- [ ] Do not change serialized formats arbitrarily without documentation and regression tests.

## 17. Official Java SE 17 Documentation

- [`ObjectInputStream` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): description of `readObjectNoData`, restoration order, and non-Serializable superclass constructors.
- [`Serializable` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): serialization hooks and versioning.
- [Java Object Serialization Specification, Section 3.5 — `readObjectNoData`](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html#the-readobjectnodata-method): trigger conditions and default fields when the hook is absent.
- [Java Object Serialization Specification — Versioning](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/version.html): field/hierarchy changes and compatibility rules.
- [`ObjectInputFilter` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): filtering classes/references/depth during deserialization.
- [`InvalidObjectException` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidObjectException.html): rejecting invalid objects during reading.

## 18. Takeaway

`readObjectNoData()` is a **special callback for each Serializable class** when the local hierarchy has a class to restore but **the stream contains no class data for that specific class**. Typical scenario: v2 inserts a Serializable superclass above a subclass written by a v1 stream.

The method has the form **`private void readObjectNoData() throws ObjectStreamException`**, with no `ObjectInputStream` parameter. It restores **that class's own** invariants or rejects the data with an exception. It **does not trigger merely by adding a field** to a class that still has a slot in the stream, and constructors/field initializers of a Serializable superclass do not run in `new`-style fashion during deserialization.

To use safely: preserve class name and `serialVersionUID` compatibility deliberately, separate two classpaths to test evolution, restore superclass state at the right time, validate the entire object graph, and never deserialize untrusted data without controls.
