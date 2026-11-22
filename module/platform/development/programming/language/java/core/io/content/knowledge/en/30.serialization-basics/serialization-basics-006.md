# serialVersionUID and Class Compatibility in Java Serialization

When a Java object is written using `ObjectOutputStream`, the data may live on disk or be transmitted to another program longer than the lifetime of the class version that created it. If the class structure changes before the data is read back with `ObjectInputStream`, Java must decide whether the old data can still be read with the current class. `serialVersionUID` is part of that verification mechanism.

This lesson applies to **Java Object Serialization** (`java.io.Serializable`), not data versioning mechanisms in JSON, JDBC, protobuf, or Java Records under a different protocol.

## 1. The Role of serialVersionUID

A class wishing to participate in Java Object Serialization typically implements the marker interface `Serializable`. When writing an object, `ObjectOutputStream` writes class descriptive metadata (a class descriptor), including the class name, descriptions of serializable fields, and the **serial version UID**. When reading, Java locates the corresponding existing class and compares the UID in the stream with the local class's UID.

- **UID matches:** Java proceeds to check structure and decode data according to compatibility rules. A matching UID **does not guarantee** every class change is compatible.
- **UID differs:** For an ordinary `Serializable` class, reading fails with `java.io.InvalidClassException` (the message typically mentions "local class incompatible" along with both UIDs).
- **Class not found:** You may receive `ClassNotFoundException` before getting any object; setting the same UID does not fix an incorrect class/package name or a missing classpath entry.

Recommended declaration:

```java
import java.io.Serializable;

public class Invoice implements Serializable {
    private static final long serialVersionUID = 1L;

    private String code;
    private long total;
}
```

`serialVersionUID` must be a field with that exact name, of type `long`, `static`, and `final`; `private` is normally used. It is **class version metadata**, not an instance data field of each object. A UID does not encrypt, authenticate, or verify data integrity. You do not need to increment the UID after *every* source edit; change it intentionally only when deciding that serialized data from a prior version **should no longer be allowed / cannot** be read with the new structure.

If a UID is **not** declared, the JVM computes a default UID based on several characteristics of the class (class name, modifiers, interfaces, and fields/methods/constructors participating in the algorithm). As a result, source edits seemingly unrelated to data can alter the computed UID and cause reads of old streams to fail. Declaring a UID explicitly keeps the compatibility contract stable, though it does not turn dangerous structural changes into safe ones.

> Two classes both declaring `serialVersionUID = 1L` does not mean they can swap objects with each other. Deserialization also depends on binary class name, class structure, and field descriptors.

## 2. What Does Java Actually Save?

With default serialization of a `Serializable` class, Java stores **non-`static`, non-`transient`** instance fields across the serializable classes in the object graph, along with class identity information and necessary object references. Objects referenced from persisted fields must also be serializable; otherwise, `NotSerializableException` can occur while writing.

- `static` belongs to the class, so it is not part of persisted instance state. On read, its value comes from the class/JVM currently running.
- `transient` explicitly excludes a field from default data. On read, the field receives its Java default value (such as `null`, `0`, `false`) unless custom code restores it.
- Constructors and field initializers of the `Serializable` class itself **are not invoked/executed to recreate state** during default deserialization. The no-argument constructor of the first **non**-Serializable superclass is invoked per Java's rules.
- `serialVersionUID` is a `static final` field, so it is not a persisted instance field; the UID value belongs to the **class descriptor**.

`Serializable` has no mandatory methods. `writeObject`, `readObject`, `serialPersistentFields`, or `Externalizable` are separate customization mechanisms that alter the data contract and must be managed carefully.

## 3. Hands-On: Writing with Version 1, Reading with Version 2

We use two source sets with the same class name `Customer` and the same UID, but **compiled into two separate directories and run in two separate processes**. Do not put both `Customer.java` files on the same classpath when running.

### Step A — Version 1 Writes the File

Create `v1/Customer.java`:

```java
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;
    int points;

    Customer(String name, int points) {
        this.name = name;
        this.points = points;
    }
}
```

Create `v1/Writer.java`:

```java
import java.io.FileOutputStream;
import java.io.ObjectOutputStream;

public class Writer {
    public static void main(String[] args) throws Exception {
        try (ObjectOutputStream out =
                new ObjectOutputStream(new FileOutputStream("customer.ser"))) {
            out.writeObject(new Customer("Lan", 120));
        }
        System.out.println("Da ghi customer.ser");
    }
}
```

Compile and run from the directory containing `v1` (requires JDK 17+; Java 17 and 21 both work):

```bash
javac -encoding UTF-8 -d v1-classes v1/Customer.java v1/Writer.java
java -cp v1-classes Writer
```

Stdout:

```text
Da ghi customer.ser
```

This creates `customer.ser` in the current working directory. This is **Java's binary serialization format**, not a text file; do not edit it with a text editor. Keep the file to test reading with v2.

### Step B — Version 2 Adds a Field While Keeping the UID

Create `v2/Customer.java`:

```java
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;
    int points;
    String level = "BASIC";
}
```

Create `v2/Reader.java`:

```java
import java.io.FileInputStream;
import java.io.ObjectInputStream;

public class Reader {
    public static void main(String[] args) throws Exception {
        try (ObjectInputStream in =
                new ObjectInputStream(new FileInputStream("customer.ser"))) {
            Customer c = (Customer) in.readObject();
            System.out.printf("name=%s, points=%d, level=%s%n",
                    c.name, c.points, c.level);
        }
    }
}
```

Compile v2 **separately**, then read the exact `customer.ser` file written in Step A:

```bash
javac -encoding UTF-8 -d v2-classes v2/Customer.java v2/Reader.java
java -cp v2-classes Reader
```

Exact stdout:

```text
name=Lan, points=120, level=null
```

Explanation:

1. `Customer` on both sides has the same class name and `serialVersionUID = 1L`.
2. Both `name` and `points` match in name/type, so the old data is restored.
3. `level` **does not exist in the version 1 stream**, so when read by v2, Java assigns the default `null`. The initializer `String level = "BASIC";` on the Serializable class does not run during deserialization, so it does not get `"BASIC"`.

This is an example of a change that is **compatible at the serialization mechanism level**, yet can still cause business bugs if new code assumes `level` is always non-null.

### Step C — Intentionally Changing the UID and Observing the Error

In `v2/Customer.java`, change only:

```java
private static final long serialVersionUID = 2L;
```

Recompile and read the old file again:

```bash
javac -encoding UTF-8 -d v2-classes v2/Customer.java v2/Reader.java
java -cp v2-classes Reader
```

The second command fails with `java.io.InvalidClassException`; the message will state stream UID `1` and local UID `2`. This is an **intentional error** illustrating "rejecting old-version data." To re-run B, restore v2's UID back to `1L` and recompile. Simply changing the UID back to match **also cannot fix** arbitrary incompatible field changes.

## 4. Which Class Changes Are Compatible?

The following rules apply to **default serialization of `Serializable`**, assuming the class name is found and the matching UID is preserved. "Compatible" means the stream can be read according to serialization rules; it does not automatically guarantee the data remains semantically valid for business logic.

| Change in the new version | Typical result when reading old data | Consequence to handle |
| --- | --- | --- |
| Add a serializable instance field | Compatible; new field takes default `null`/`0`/`false` | Normalize value on read if business logic requires |
| Remove an instance field | Compatible; old field's data in the stream is ignored | Part of old state is lost when read by the new class |
| Rename an instance field | Equivalent to removing the old name and adding a new name | Old name's value is not automatically transferred to the new name |
| Change `private`/`public` of a field while keeping name/type | Usually compatible when UID is fixed | Still review encapsulation impact |
| Change an instance field to `static` or `transient` | Equivalent to removing the field from the serialized form | Old value is not restored into that field |
| Change a `static`/`transient` field to a serializable instance field | Equivalent to adding a field | Old data lacks this field; receives default |
| Change field type (e.g., `int` to `long`, or `String` to `Integer`) | **Considered incompatible**; can throw `InvalidClassException` | Design versioned data conversion |
| Add/edit normal methods | Usually does not change default serialized form if UID is fixed | May change logic consuming old data |
| Rename class, package, or move classpath missing the class | Class name resolution fails; can throw `ClassNotFoundException` | Needs migration strategy or reading with old code |
| Switch from `Serializable` to `Externalizable` (or vice versa) | Format/mechanism incompatibility | Default field rules do not apply |
| Change superclass, inheritance depth, custom data format | Case-dependent and potentially incompatible | Test against real files from each version |

**Distinguish two layers:** a differing UID usually blocks reading immediately at the version-identification step; an identical UID only lets Java attempt matching data under serialization rules. Therefore, *preserving a UID* must go hand-in-hand with preserving readable structure and data meaning.

Java defines the details in the **Java Object Serialization Specification**, section *Versioning of Serializable Objects*. For complex changes to inheritance hierarchies, `writeObject/readObject`, `readResolve`, proxies, or enums/records, consult the specification itself and verify with bidirectional fixtures.

## 5. When an Added Field Needs a Business Default Value

A new field has no data in an old stream and thus receives only the Java type's default value, **not the initializer** of the Serializable class itself. If `null` is invalid for `level`, you can update the logic consuming old data, or customize `readObject` to fill in the missing value.

The following example **replaces the default read logic in `Customer` v2** (placed inside the class body; requires `import java.io.IOException;` and `import java.io.ObjectInputStream;`). Not a standalone program:

```java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    ObjectInputStream.GetField fields = in.readFields();

    name = (String) fields.get("name", null);
    points = fields.get("points", 0);
    level = fields.defaulted("level")
            ? "BASIC"
            : (String) fields.get("level", null);
}
```

`GetField.defaulted("level")` checks whether the field is absent from the stream being read; this distinguishes "old version without the field" from "new version that intentionally stored `null`." For simpler needs, you can use `in.defaultReadObject()` and then validate/normalize fields, though that cannot distinguish those two cases. If custom `writeObject/readObject` or `serialPersistentFields` already exist, maintain the published format carefully.

Do not silently alter the UID to "fix" data or use casts to bypass errors. For long-lived data, the sustainable solution is usually an **explicit schema/versioned data format** with migration steps and tests on stored data from released versions.

## 6. Generating, Checking, and Managing UIDs

- **Declare UIDs explicitly** for Serializable classes that the application actually persists, caches durably, or sends across version boundaries. For example, `private static final long serialVersionUID = 1L;`.
- **Keep the UID** when changes remain compatible and the new program still understands old data. Verify at both the data level and the business level.
- **Change the UID intentionally** when old files must be rejected and `InvalidClassException` is expected. Then plan cache invalidation, migration, or legacy-version support if needed.
- **Do not treat the UID as an application version number** or timestamp. There is no rule requiring `1L`, `2L` per release.
- **The JDK's `serialver` tool** can print the `serialVersionUID` of a compiled class, e.g. `serialver -classpath v1-classes Customer`. The API `ObjectStreamClass.lookup(Customer.class).getSerialVersionUID()` also reports a class's UID at runtime.
- **Do not rely on auto-computed UIDs** when long-term data compatibility is required. A change in signatures, modifiers, or toolchain can alter the default UID.
- **Test with real fixture files:** write with v1 and read with v2 (consider the reverse direction as well if rollback is supported); check values, invariants, and expected errors. Keep fixtures in your compatibility test suite when schemas evolve.

Note: some Java types have special serialization rules, such as `enum` being represented primarily by constant name and `record` having its own versioning rules. Do not extrapolate all ordinary Serializable class examples to those types.

## 7. Common Issues and How to Tell Them Apart

| Symptom | Cause to check | How to handle |
| --- | --- | --- |
| `InvalidClassException: local class incompatible` | UID in stream differs from running class's UID | Check actual classpath/build, UIDs on both sides, and migration policy |
| `InvalidClassException` even though UIDs match | Structural change or violated serialization requirements | Compare field types, hierarchy, Serializable/Externalizable, custom format |
| `ClassNotFoundException` on `readObject()` | Class name in stream cannot be found | Supply the proper classpath, keep legacy class, or convert format |
| `NotSerializableException` on `writeObject()` | An object in the graph is not Serializable | Fix the model or mark `transient` if intentional |
| New field returns `null` despite having an initializer | Serializable initializer does not run when reading old objects | Migrate/restore in `readObject` or business layer |
| Old data reads cleanly yet behavior is wrong | Binary compatibility does not mean semantic compatibility | Validate invariants, supply defaults, migrate data |

Because `ObjectInputStream.readObject()` can instantiate objects, trigger custom restoration mechanisms, and traverse entire object graphs, **never treat Java serialized data from untrusted sources as safe**. For new systems, prefer explicit-schema data formats with type control. If reading Java serialization is mandatory, control the data source, set size/depth/reference limits and class allowlists using `ObjectInputFilter` (Java 9+), and apply appropriate security practices. A UID provides no security protection.

## 8. Self-Check Questions

1. V1 has `int points`; v2 adds `boolean active` and keeps the UID. When reading data from v1, what is `active`? **Answer:** `false` (unless custom restoration is added).
2. V1 saves `String fullName`; v2 renames it to `name` and keeps the UID. Is the old value automatically assigned to `name`? **No**; explicit migration/mapping is required.
3. V1 and v2 have identical fields, but the UID is changed from `1L` to `2L`. What will `readObject()` do? **Throw `InvalidClassException`** for an ordinary Serializable class.
4. Can you keep the UID, change a field from `int` to `long`, and expect Java to convert it automatically? **No**. You need a planned serialized-form change or migration.
5. Why did `level = "BASIC"` still print `null` in v2? **Because the Serializable class's initializer does not execute when a v1 object is deserialized**.

**Source material:** Java Object Serialization Specification — sections *Class Descriptors*, *Versioning of Serializable Objects*, and *Input*; Java API docs for `Serializable`, `ObjectInputStream`, `ObjectStreamClass`, and `ObjectInputFilter`.