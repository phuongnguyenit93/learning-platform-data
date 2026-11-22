# serialPersistentFields and Controlling Serialized Form in Java Serialization

When implementing `java.io.Serializable`, many classes initially rely on the default mechanism: Java writes all non-`static`, non-`transient` instance fields. However, if an application persists `.ser` files long-term or exchanges objects between two program versions, **the field names and types written into the stream** become a compatibility contract. Renaming a field in source code can prevent old data from automatically mapping into the new field.

`serialPersistentFields` lets a class **explicitly declare its serialized form**, decoupling it from the current Java field structure. Combined with `writeObject`/`readObject` and the `PutField`/`GetField` API, you can continue writing and reading the exact same data layout even when changing how state is stored in memory.

**Scope:** This mechanism is for Java Object Serialization of regular Serializable classes. It does not apply directly to JSON, JPA, protobuf, Java Records, or `Externalizable`. A `.ser` format is a binary stream containing class descriptors, object references, and data for each serializable class in the inheritance hierarchy; it is not merely a table of fields.

## 1. Decoupling In-Memory State from the Serialized Form

Suppose an old version has the class:

```java
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 7L;

    String fullName;
    int points;
}
```

With default serialization, the two fields are written as `fullName:java.lang.String` and `points:int`. If a new version renames them to `displayName` and `rewardBalance`, keeping UID `7L` **does not automatically rename the data on the stream**. When reading an old file, the new names do not match, so they default to `null`/`0` while the old field data is ignored. When the new version writes a file, the old version cannot automatically locate the new field names either.

We want the new class to use cleaner field names in code while continuing to expose the historical fields `fullName` and `points` on the stream:

```text
Version 1                           Stable Serialized Form                 Version 2
fullName: String  ────────────────> fullName: String <──────────────────> displayName: String
points: int       ────────────────> points: int      <──────────────────> rewardBalance: int
```

The arrow direction from v2 into the wire format is handled by **explicit mapping code**. This is the primary reason to use `serialPersistentFields`.

## 2. Declaring serialPersistentFields According to the Contract

Inside a class implementing `Serializable`, define the special field as follows:

```java
import java.io.ObjectStreamField;
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 7L;

    private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("fullName", String.class),
        new ObjectStreamField("points", int.class)
    };

    private String displayName;
    private int rewardBalance;
}
```

This is a **compilable declaration snippet**, though not yet a complete data-mapping example. Because the field names in the array do not match the physical fields, Section 4 adds `writeObject/readObject`.

The rules:

1. The name must be exactly `serialPersistentFields`, type `ObjectStreamField[]`, modifiers `private static final`. If declared with the wrong name, missing modifiers, `null` value, or wrong type, the mechanism treats it as absent and falls back to computing default fields; thus, a mistake can silently alter the schema.
2. Each `new ObjectStreamField("name", Type.class)` describes **one field on the stream**, including name and type. For primitives use `int.class`, `long.class`, etc.—do not use `Integer.class` as a substitute for `int.class`. Java does not automatically coerce types during deserialization.
3. You can describe a field that **does not physically exist** in the new Java class (a virtual persistent field). The goal is to preserve the old wire schema name while the in-memory fields have changed.
4. Physical fields not listed in the array **do not belong to the serialized form of that class** under this mechanism. Conversely, listed fields can still be written even if no matching physical field exists. A `transient` modifier does not automatically guarantee exclusion if the persistent fields policy explicitly includes that name in the schema.
5. An empty array `new ObjectStreamField[0]` means there are no persistent fields for **this class**, though it does not remove class descriptor metadata or data of other serializable classes in the inheritance hierarchy.
6. The `ObjectStreamField` array holds no object data values; it only declares names/types (and optionally `unshared`). Concrete values are fetched from the object when writing and assigned back when reading.

`serialVersionUID` and `serialPersistentFields` solve two separate problems. The UID verifies class version compatibility when reading; persistent fields define the set of serializable fields. **Sharing the same UID does not guarantee compatibility** if names, types, custom data order, or data contracts changed in an unhandled way.

## 3. APIs for Controlling Writing and Reading

### Writing: putFields → put → writeFields

Inside the private `writeObject(ObjectOutputStream out)` method, call:

```java
ObjectOutputStream.PutField fields = out.putFields();
fields.put("fullName", displayName);
fields.put("points", rewardBalance);
out.writeFields();
```

This is a **snippet placed inside `writeObject`**, not a standalone program.

- `out.putFields()` creates a container holding values for the fields declared in the current serialized form. It may only be called from a valid `writeObject`.
- `fields.put("fullName", displayName)` places the internal value `displayName` under the legacy wire field name `fullName`. Overloads of `put` handle primitive and reference types.
- `out.writeFields()` writes the placed values in the canonical protocol-defined order, not the order in which `put` was called. Fields omitted from `put` are written with their type's default value.
- Do not mix `defaultWriteObject()` and `putFields()/writeFields()` for the same required field data in a single `writeObject` call.

**Do not call `out.writeObject(displayName)` instead of `putFields`** expecting the stream to contain a field named `fullName`. Writing objects directly creates separate *optional data*, which is not equivalent to the required fields described in the class descriptor; altering custom read/write contracts carelessly can break cross-version compatibility.

### Reading: readFields → get → Check Invariants

Inside the private `readObject(ObjectInputStream in)` method, call:

```java
ObjectInputStream.GetField fields = in.readFields();
displayName = (String) fields.get("fullName", null);
rewardBalance = fields.get("points", 0);
```

This is likewise a **snippet inside `readObject`**.

`in.readFields()` retrieves persistent field data from the stream, allowing lookup by name via `get(String, <default value>)` overloads. `fields.defaulted("fullName")` checks whether that field name was absent from the current stream. It is useful when distinguishing "an old file without the field yet" from "a file that has the field with value `null`".

You must validate data after reading: constructors and initializers of a `Serializable` class itself do not run during normal deserialization. Consequently, an object could end up in a state a normal constructor would reject. You can throw `InvalidObjectException` if invariants fail.

### When to Use defaultWriteObject/defaultReadObject?

If the names and types in `serialPersistentFields` match actual instance fields and require no value transformation, the default mechanism can still map them. Inside a custom `writeObject` method, `defaultWriteObject()` writes the required fields per the serialized form; `defaultReadObject()` reads and assigns the corresponding fields. However, **you cannot expect defaultWriteObject/defaultReadObject to know on their own that `displayName` is the new name for `fullName`**. For virtual field mapping or value conversion, use `PutField/GetField`.

## 4. Complete Runnable Example: Renaming Internal Fields While Keeping the Wire Schema

We will write with v1, read with v2, then write with v2 and read back with v1. To avoid collisions between two `Customer` classes sharing the same name, place the sources in two separate directories and run each version with its own classpath. The example runs on JDK 17+ (including Java 21).

### Version 1 — Traditional Class Using Default Serialization

Create `v1/Customer.java`:

```java
import java.io.Serializable;

public final class Customer implements Serializable {
    private static final long serialVersionUID = 7L;

    String fullName;
    int points;

    public Customer(String fullName, int points) {
        this.fullName = fullName;
        this.points = points;
    }
}
```

Create `v1/LegacyApp.java`:

```java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public class LegacyApp {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("write|read <file>");
        }

        if ("write".equals(args[0])) {
            Customer c = new Customer("Lan", 120);
            try (ObjectOutputStream out =
                    new ObjectOutputStream(new FileOutputStream(args[1]))) {
                out.writeObject(c);
            }
            System.out.println("v1 wrote: " + c.fullName + "/" + c.points);
        } else if ("read".equals(args[0])) {
            try (ObjectInputStream in =
                    new ObjectInputStream(new FileInputStream(args[1]))) {
                Customer c = (Customer) in.readObject();
                System.out.println("v1 read: " + c.fullName + "/" + c.points);
            }
        } else {
            throw new IllegalArgumentException("Unknown command");
        }
    }
}
```

### Version 2 — Internal Field Names Changed, Persistent Field Names Same as v1

Create `v2/Customer.java`:

```java
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.ObjectStreamField;
import java.io.Serializable;

public final class Customer implements Serializable {
    private static final long serialVersionUID = 7L;

    // Commit to keeping the schema used since v1:
    private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("fullName", String.class),
        new ObjectStreamField("points", int.class)
    };

    // Internal data renamed, no longer matching wire field names:
    private String displayName;
    private int rewardBalance;

    public Customer(String displayName, int rewardBalance) {
        if (displayName == null || displayName.isBlank() || rewardBalance < 0) {
            throw new IllegalArgumentException("Invalid customer");
        }
        this.displayName = displayName;
        this.rewardBalance = rewardBalance;
    }

    public String displayName() {
        return displayName;
    }

    public int rewardBalance() {
        return rewardBalance;
    }

    private void writeObject(ObjectOutputStream out) throws IOException {
        ObjectOutputStream.PutField fields = out.putFields();
        fields.put("fullName", displayName);
        fields.put("points", rewardBalance);
        out.writeFields();
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        ObjectInputStream.GetField fields = in.readFields();
        displayName = (String) fields.get("fullName", null);
        rewardBalance = fields.get("points", 0);

        if (displayName == null || displayName.isBlank()
                || rewardBalance < 0) {
            throw new InvalidObjectException("Invalid customer state");
        }
    }
}
```

Create `v2/NewApp.java`:

```java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public class NewApp {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("write|read <file>");
        }

        if ("write".equals(args[0])) {
            Customer c = new Customer("Mai", 75);
            try (ObjectOutputStream out =
                    new ObjectOutputStream(new FileOutputStream(args[1]))) {
                out.writeObject(c);
            }
            System.out.println("v2 wrote: "
                    + c.displayName() + "/" + c.rewardBalance());
        } else if ("read".equals(args[0])) {
            try (ObjectInputStream in =
                    new ObjectInputStream(new FileInputStream(args[1]))) {
                Customer c = (Customer) in.readObject();
                System.out.println("v2 read: "
                        + c.displayName() + "/" + c.rewardBalance());
            }
        } else {
            throw new IllegalArgumentException("Unknown command");
        }
    }
}
```

From the parent directory containing `v1/` and `v2/`, run sequentially:

```bash
javac -encoding UTF-8 -d v1-classes v1/Customer.java v1/LegacyApp.java
javac -encoding UTF-8 -d v2-classes v2/Customer.java v2/NewApp.java
java -cp v1-classes LegacyApp write legacy.ser
java -cp v2-classes NewApp read legacy.ser
java -cp v2-classes NewApp write current.ser
java -cp v1-classes LegacyApp read current.ser
```

Stdout from the four `java` commands:

```text
v1 wrote: Lan/120
v2 read: Lan/120
v2 wrote: Mai/75
v1 read: Mai/75
```

The results explain both directions:

1. `legacy.ser` created by v1 has class name `Customer`, UID `7L`, and persistent fields `fullName: String` and `points: int`. V2 uses `readFields()` to route them into `displayName` and `rewardBalance`.
2. V2 writes `current.ser` via `putFields/writeFields`; even though the v2 class has no instance fields named `fullName` or `points`, the stream **still contains fields compatible with v1**. V1 reads it back with default serialization.
3. The classes in both directories must share the **same binary class name** (`Customer` in the default package in this example) and a compatible UID. In practice, use a stable package and compile each version into separate artifacts.
4. The two files may differ in raw bytes because v2's stream descriptor carries a flag indicating a custom write method. The goal is **reading the data and restoring the exact state**, not requiring `legacy.ser` and `current.ser` to be byte-for-byte identical.

If v2 simply renamed the fields to `displayName/rewardBalance` without `serialPersistentFields` and the mapping code, Java would default to writing/reading the new names: the test above would no longer preserve both legacy fields seamlessly.

## 5. Inspecting the Schema Actually Published by the JVM

You can inspect the persistent field list using `ObjectStreamClass`. In the v2 example, add the following snippet to any `main` method on the v2 classpath (this is an **illustrative snippet**, requiring `import java.io.ObjectStreamClass;` and `import java.io.ObjectStreamField;`):

```java
ObjectStreamField[] declared =
        ObjectStreamClass.lookup(Customer.class).getFields();

for (ObjectStreamField field : declared) {
    System.out.println(field.getName() + ":"
            + field.getType().getSimpleName());
}
```

Corresponding output (primitive fields are sorted before object fields by name):

```text
points:int
fullName:String
```

Even though the v2 class's instance fields are `displayName` and `rewardBalance`, the descriptor still publishes `points` and `fullName`. This is a helpful check after refactoring or updating a library. `ObjectStreamClass.lookup` returns `null` for non-Serializable classes.

Another variation is explicitly listing the fields currently being serialized without retaining legacy names. However, if already-released data uses the old schema, **changing the persistent schema is also a contract change**. You must plan how to read old data and verify compatibility using fixtures.

## 6. Scope of Impact and Advanced Scenarios

| Approach | Serialized Fields | When Appropriate | Notes |
| --- | --- | --- | --- |
| `implements Serializable` only | Non-`static/transient` instance fields | Simple classes without a long-lived schema | Refactoring field names impacts the stream |
| `transient` | Excludes a field from the default set | Temporary data, recomputable caches | Data is lost on restoration; insufficient to govern the full schema |
| `serialPersistentFields` | Explicitly declared set of names/types | Stabilizing field protocol and hiding internal structure | Virtual fields require explicit value mapping |
| `writeObject/readObject` + `PutField/GetField` | Explicit field set plus mapping logic | Renaming fields, normalizing data, migrating storage formats | Maintain order and presence of required data |
| `Externalizable` | Fully custom-defined via `writeExternal/readExternal` | Lower-level protocol control | Separate mechanism and versioning rules; does not use `serialPersistentFields` like Serializable |
| Serialization proxy (`writeReplace/readResolve`) | An independent proxy object representing state | Immutable types or types with strict invariants | Must be designed compatibly with existing streams |

### Missing Field in an Older Version

If v3 adds a persistent field `String membershipLevel` and v3 reads a v1/v2 stream lacking this field, `GetField` can check:

```java
String level = fields.defaulted("membershipLevel")
        ? "STANDARD"
        : (String) fields.get("membershipLevel", null);
```

This is a **snippet inside v3's `readObject`**, valid only when `membershipLevel` is already declared in v3's `serialPersistentFields`. `defaulted` checks whether the field is absent from the stream, **not** whether it is `null`. Distinguish these so you do not overwrite an intentional `null` value.

If v3 needs to write files readable by v1/v2, it must still preserve the persistent fields required by legacy code. Additional fields are typically ignored by older code, though business correctness still requires testing. Changing a field's type—for example `points:int` to `points:long`—while keeping the same name or UID **does not make Java convert it automatically**. You can keep the wire field `points:int` and manage `long` internally while checking range/overflow, or design a new format migration.

### The unshared Option of ObjectStreamField

`new ObjectStreamField("name", SomeClass.class, true)` instructs serialization to treat the referenced field as unshared. It affects reference sharing/aliasing for that object field, not field naming or UID bumps. Only use it when you thoroughly understand the object graph and sharing requirements; do not enable it arbitrarily during a simple refactor.

### Multiple Inheritance Levels, Inner Classes, and Special Types

Serialized form is processed **per Serializable class** in the inheritance chain, not just the leaf class. A subclass's `serialPersistentFields` does not alter its superclass's schema. Hierarchy changes and custom write/read data can strongly impact compatibility.

Non-static inner classes are poor choices for building stable serialized schemas: they usually hold a synthetic reference to the enclosing instance and cannot declare `private static final ObjectStreamField[]` as needed in common cases. Use top-level classes or static nested classes for models needing a custom serialized form. For enums and records, serialization rules differ from regular classes; do not apply this example mechanically.

## 7. Common Errors and Diagnostic Symptoms

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| After refactoring, new field reads as `null` or `0` | Only renamed field in code without preserving wire field or mapping | Declare legacy persistent schema and transfer values via `GetField` |
| File written by v2 reads as default values in v1 | V2 wrote new field names/types, dropping fields v1 expects | Preserve legacy persistent field names/types; test v2 → v1 direction |
| `InvalidClassException` | UID mismatch or incompatible serializable class/field format | Compare UID, classpath, field names/types, and custom protocol |
| `IllegalArgumentException` calling `put/get` | Field name missing from declared persistent fields or wrong overload | Check against `ObjectStreamClass.getFields()` and exact Java types |
| `NotActiveException` | Calling `putFields/readFields/defaultWriteObject` outside a valid serialization context | Call only inside private hooks with exact signatures |
| Runs but stream lacks expected fields | `serialPersistentFields` declared with wrong modifiers/type, or virtual field values never written | Check declaration and class descriptor; test with real fixtures |
| Same data produces invalid state after reading | Skipped invariant checks or Serializable initializers didn't run | Validate inside `readObject`; throw `InvalidObjectException` |
| `NotSerializableException` when writing | Reference value in persistent fields leads to a non-Serializable object | Adjust model, store a safe representation, or mark excluded |
| Data reads successfully but old code misinterprets it | Binary compatibility differs from semantic compatibility | Enforce business compatibility rules and migrate if necessary |

A particularly subtle trap is **mixing required fields with optional custom data**. When using `writeObject`, ensure the mechanism writing required fields (`defaultWriteObject` or `writeFields`) always aligns with the reading mechanism (`defaultReadObject` or `readFields`) across versions that must remain compatible. Only after the required section can you write additional optional data; both writer and reader must agree on ordering, version markers, and missing-data handling. Do not arbitrarily move everything into ad-hoc `writeInt/writeObject` calls while still expecting older versions to read fields as before.

## 8. Limitations, Safety, and Design Alternatives

`serialPersistentFields` **is not a security tool**. It helps constrain a class's serialized state, but it does not authenticate streams, encrypt data, or prevent object-instantiation exploits during deserialization. Never deserialize Java data from untrusted sources. When unavoidable, restrict allowed classes/depth/reference count/size using `ObjectInputFilter` and strict input policies; enforce invariants after reading.

Removing a secret from `serialPersistentFields` only affects newly written files; existing files may still contain that data. If stored secrets must be purged, plan a cleanup for legacy files and backups.

Avoid using Java native serialization for cross-language storage contracts or new public APIs. For long-lived schemas with complex migrations, prefer formats with explicit versioning/schemas (such as versioned JSON with validation, protobuf, or Avro depending on requirements). If a system already depends on Java serialization, `serialPersistentFields` is useful for decoupling the wire schema from physical fields, paired with compatibility fixtures on every upgrade.

## 9. Checklist for Modifying a Class with Existing Serialized Data

1. Record the class/package name, `serialVersionUID`, and descriptors of all supported versions; retain real fixture files.
2. List the exact names and types of legacy persistent fields. Decide which fields must be preserved and which require migration.
3. Declare `serialPersistentFields` with the right modifiers and type; if new fields do not match physical fields, implement `writeObject`/`readObject` using `PutField/GetField`.
4. Validate state after `readFields()`, including absent fields, `null` values, negative numbers, referenced objects, and invalid data.
5. Run **v1 → v2** fixtures and, if rollback/multi-version support is required, also run **v2 → v1**. Verify values, invariants, and business behavior—not just "no exception thrown".
6. Maintain tests whenever adding, retyping, deleting, marking `transient`, altering hierarchy, or changing optional custom data. If compatibility cannot be preserved, deliberately change the protocol and provide a migration.

## 10. Self-Check Questions

1. V2 renames `fullName` to `displayName` while using default serialization and keeping the same UID. Will Java automatically transfer the value when reading a v1 file? **No.** Explicit mapping or a migration step is required.
2. If `serialPersistentFields` has `new ObjectStreamField("oldName", String.class)` while the class only has `newName`, does `defaultWriteObject()` automatically read `newName`? **No.** Use `PutField.put("oldName", newName)` followed by `writeFields()`.
3. Does the `serialPersistentFields` array specify names/types or store each object's values? **It specifies the schema.** Values are written during serialization.
4. How does `GetField.defaulted("status")` differ from checking `get("status", null) == null`? **One checks whether the field is absent from the stream, while the other can encounter a field that is present with value `null`.**
5. Why must you test v2 → v1 even when v2 successfully reads v1 data? **Because being able to read old data does not prove v2 still writes the exact schema v1 expects.**

**Official Documentation:** Java Object Serialization Specification — *1.5 Defining Serializable Fields for a Class*, *1.7 Accessing Serializable Fields of a Class*, and *Chapter 5: Versioning of Serializable Objects*. See also JDK APIs `ObjectStreamField`, `ObjectStreamClass`, `ObjectOutputStream.PutField`, and `ObjectInputStream.GetField`:

- https://docs.oracle.com/en/java/javase/11/docs/specs/serialization/serial-arch.html
- https://docs.oracle.com/en/java/javase/26/docs/specs/serialization/version.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectStreamField.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.GetField.html
