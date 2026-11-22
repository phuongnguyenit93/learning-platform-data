# Serializable with Enum and Record in Java 17+: Serialization, Restoration, and Compatibility Rules

## 1. Why Should Enum and Record Be Studied Separately?

Java Object Serialization lets you write objects into a byte stream using `ObjectOutputStream` and restore them using `ObjectInputStream`. The marker interface `java.io.Serializable` is the foundation enabling most Java objects to be processed by this mechanism.

However, **`enum` and `record` do not follow the same serialization rules as ordinary classes**:

- `enum` is **already serializable by default**. Its special format stores the **enum constant name**, not an instance state block like an ordinary class. When reading, Java looks up **the existing enum constant**.
- `record` **does not automatically implement Serializable**. When a record declares `implements Serializable`, its serial form is determined by its **record components**, and on read Java invokes its **canonical constructor** to create the object instead of restoring fields via the ordinary class mechanism.
- Both have specific limitations regarding `writeObject`/`readObject`, `serialVersionUID`, handling class definition changes, and deserialization security.

This lesson focuses on Java 17+ and **Java built-in Object Serialization**, not JSON, Jackson, protobuf, or database mapping. Objective: understand what gets stored, what happens on read, how to validate, and how to avoid mistakes when evolving to new versions.

## 2. Quick Recap: Serializable, Streams, and Object Graphs

An ordinary class can declare:

~~~java
import java.io.Serializable;

class Note implements Serializable {
    private static final long serialVersionUID = 1L;
    String text;
}
~~~

The snippet above **only illustrates a declaration**, not a complete program. The `Serializable` interface is a **marker interface**: it requires implementing no methods. `ObjectOutputStream.writeObject(value)` writes class information and necessary state; `ObjectInputStream.readObject()` reconstructs the objects in the object graph.

Common contract rules:

- An object being `Serializable` **does not guarantee the entire object graph is serializable**. If a field/component references an object that cannot be written, the process can throw `NotSerializableException`.
- `static` variables do not belong to per-instance state to be serialized; for ordinary classes, `transient` marks a field not to be saved by default serialization.
- Java Object Serialization uses a Java-specific binary format and requires compatible classes when reading back; it **does not automatically become a stable cross-language interchange protocol**.
- Streams should be closed with `try-with-resources`. Do not deserialize bytes from untrusted sources merely because they carry a `.ser` extension.
- The reference-tracking and object-cycle mechanism in Java Serialization has special cases for records; a later section explains this.

Comparison table:

| Feature | Ordinary `implements Serializable` Class | `enum` | `record implements Serializable` |
| --- | --- | --- | --- |
| Need to declare marker? | Yes (or inherit from a serializable type) | **No**, enums are inherently serializable | **Yes**, records are not automatically serializable |
| Primary stream content | Serializable fields per class mechanism | **Name of the enum constant** | **Record component values** |
| On deserialization | Restores instance and fields per class mechanism | Looks up constant via `Enum.valueOf` | **Invokes canonical constructor** |
| Object identity | Typically receives a newly constructed instance | Preserves exact enum singleton constant (`==`) | New instance, compare content with `equals` |
| Custom `writeObject/readObject` | Can be used when following the contract | **Ignored** | **Ignored** |
| `writeReplace/readResolve` | Applicable per rules | **Ignored** | **Applicable** |
| `serialVersionUID` | Very important for compatibility | Fixed at `0L`; declarations are ignored | Defaults to `0L` or explicitly declared; UID matching check is waived |
| Cycles pointing back to the object itself | Can be preserved via object handles | Enums are pre-existing constants | Cycles through components pointing back to the record **are not preserved** |

## 3. Enum: Stores Constant Name, Not Instance State

### 3.1. Why Is `implements Serializable` Unnecessary?

Every Java `enum` type extends `java.lang.Enum`, which implements `Serializable`. For example:

~~~java
enum Status {
    NEW, PROCESSING, DONE
}
~~~

This snippet is sufficient for values like `Status.DONE` to be passed to `ObjectOutputStream.writeObject(...)`; no extra marker or special constructor is required.

**On write:** the stream records the enum type identifier and the constant name returned by `name()`, such as `"DONE"`. Ordinals or instance fields you declare on constants are not state stored by the special enum mechanism.

**On read:** Java resolves the constant name via a mechanism equivalent to `Enum.valueOf(Status.class, "DONE")`. Consequently, the result is **the exact `Status.DONE` already present in the JVM**, without creating a second enum instance.

~~~java
Status original = Status.DONE;
// After successful writeObject then readObject:
Status restored = Status.DONE; // Example of the restored value.
System.out.println(original == restored); // true
~~~

The snippet above only illustrates the outcome. A complete runnable program is in Section 7.

### 3.2. `name()` Differs from `toString()` and `ordinal()`

An enum can define a display label:

~~~java
enum Level {
    LOW("Low"), HIGH("High");

    private final String label;

    Level(String label) {
        this.label = label;
    }

    @Override
    public String toString() {
        return label;
    }
}
~~~

If you serialize `Level.HIGH`, Java stores **the name `HIGH`**, rather than taking the string `"High"` from `toString()`. Nor does it store `ordinal()` as the constant's identifier.

Consequences:

- Changing `toString()` or display labels will not break deserialization of old enum values.
- Reordering constant declarations does not change the stored name `HIGH`.
- **Renaming/removing a constant** that appeared in older streams can cause restoration to fail because the name no longer exists. This is an important distinction when upgrading versions.

### 3.3. Fields Inside an Enum Are Not Restored from the Stream

Consider an enum with state:

~~~java
enum Mode {
    SAFE, FAST;

    private int visits;

    void markUsed() {
        visits++;
    }

    int visits() {
        return visits;
    }
}
~~~

If you call `Mode.SAFE.markUsed()` before serializing, the byte stream for `Mode.SAFE` still represents only **the SAFE constant**, containing no copy of `visits`.

When reading the enum in **the same JVM**, you get back `Mode.SAFE` with that singleton's current state in that JVM. If deserialized in another JVM, the state is initialized/managed by that runtime, **not the visit count that existed on the source JVM**. Do not use enum serialization to synchronize mutable data attached to an enum.

### 3.4. Custom Hooks on an Enum Have No Effect

For enums, Java Object Serialization ignores custom methods defined by the enum such as `writeObject`, `readObject`, `readObjectNoData`, `writeReplace`, and `readResolve`. It also ignores `serialPersistentFields` and any declared `serialVersionUID` field; an enum's UID is always `0L`.

Therefore, **do not write `readResolve()` inside an enum to protect uniqueness**: name-based restoration already guarantees no new enum constant is created. Do not expect writing `writeObject` to save extra dynamic fields to have any effect. If you need to store per-request varying data, put it in a **separate serializable class or record**, and use the enum only to represent a finite set of types/states.

## 4. Record: Structural Immutability Does Not Mean Serializable

### 4.1. Must Declare `implements Serializable`

Records became official in Java 16 (and are stable in Java 17), representing data through **record components**:

~~~java
record Point(int x, int y) {
}
~~~

The record above is **not yet serializable**, even though it has compiler-generated constructors, accessors, `equals`, `hashCode`, and `toString`. Passing an instance to `ObjectOutputStream.writeObject` can throw `NotSerializableException`.

A version supporting Java Object Serialization must declare:

~~~java
import java.io.Serializable;

record Point(int x, int y) implements Serializable {
}
~~~

Adding the marker alone is insufficient if a component has a reference type holding non-serializable data. For example:

~~~java
record Holder(Object value) implements Serializable {
}

Holder invalid = new Holder(new Object());
// writeObject(invalid) may throw NotSerializableException
// because java.lang.Object does not implement Serializable.
~~~

The two snippets above are **illustrative**. A component type of `Object` does not automatically support every value inside, just as `List` does not guarantee every implementation and element is serializable.

### 4.2. What Does Java Write for a Record?

Given:

~~~java
record Product(String sku, int quantity) implements Serializable {
}
~~~

The serial form of the record is based on **the values of the two components** `sku` and `quantity`. A record cannot declare arbitrary instance fields beyond those generated for its record components. `static` variables do not belong to per-instance state and are not part of the component serial form.

Unlike ordinary classes, record serialization does not use `serialPersistentFields` to pick custom fields and does not invoke a record-defined `writeObject`. Thus **the set of components is the direct data contract** to consider when versioning.

This does not mean "records serialize to JSON." The Java byte stream still contains type/class metadata and field information per the Java Object Serialization protocol.

### 4.3. The Canonical Constructor Runs on Deserialization

Records are restored through their **canonical constructor**: Java reconstructs the component values from the stream and then invokes this constructor.

~~~java
import java.io.Serializable;
import java.util.Objects;

record Account(String id, int balance) implements Serializable {
    public Account {
        Objects.requireNonNull(id, "id");
        if (id.isBlank() || balance < 0) {
            throw new IllegalArgumentException("Invalid account");
        }
    }
}
~~~

This is an illustrative declaration. `public` on the compact canonical constructor suits a public record; if the record is package-private, the constructor's access does not need to be `public`. Because the canonical constructor runs during deserialization, checks for non-blank `id` and `balance >= 0` get a chance to apply even when data comes from a serialized stream.

If the constructor rejects the restored values, Java can report `InvalidObjectException` (whose root cause is the exception from the constructor). **Do not rely on post-read setters to patch invariants**: records are constructed with the read values via the constructor.

Important: record validation **does not mean the data source is trusted**. The byte stream can trigger creation, parsing, or restoration of other component objects before the record's canonical constructor is called. You must apply deserialization security policies across the entire stream.

### 4.4. Which Serializer Hooks Take Effect?

For a serializable record, hooks that work on ordinary classes behave differently:

| Member | Record in Java Serialization |
| --- | --- |
| `private void writeObject(ObjectOutputStream)` | Ignored |
| `private void readObject(ObjectInputStream)` | Ignored |
| `readObjectNoData` | Ignored |
| `writeExternal/readExternal` | Ignored for the record's serial form |
| `serialPersistentFields` | Ignored |
| `writeReplace` | Can be used for object replacement |
| `readResolve` | Can be used to choose a replacement object after restoration |
| Canonical constructor | **Invoked** when constructing the record from the stream |
| `serialVersionUID` | Defaults to `0L`; can be declared, though UID matching is waived for records |

If you need to validate components, prefer placing invariants in the canonical constructor. If you need a **completely custom serialized form**, records do not allow ordinary `writeObject/readObject` customization; consider a **serialization proxy** using `writeReplace/readResolve` or an explicit format such as JSON/CBOR/protobuf with a clear schema.

Do not start with hooks to solve what is purely a validation issue; the less custom stream behavior you have, the easier it is to control and review.

## 5. SerialVersionUID: Enum, Record, and Ordinary Classes Differ

`serialVersionUID` is the class version identifier in Java Serialization. For ordinary classes, a UID mismatch can cause `InvalidClassException` on deserialization.

**Enum:**

- UID is always fixed at `0L`.
- If you write a field named `serialVersionUID` in an enum, serialization **ignores** it.
- Do not use UID to version enum constant names.

**Record:**

- UID defaults to `0L`, unless the record explicitly declares a value.
- Java **waives the requirement that the two UIDs must match** during record deserialization.
- This **does not guarantee all record structural changes are compatible**: adding/removing/renaming/changing component types can still alter restored data or cause the constructor to reject it.

Example:

~~~java
import java.io.Serial;
import java.io.Serializable;

record Invoice(String code, long cents) implements Serializable {
    @Serial
    private static final long serialVersionUID = 17L;
}
~~~

`@Serial` (available since Java 14) expresses the intent of declaring a field/method for serialization and helps the compiler detect certain semantically invalid declarations. The UID here is a serial version attribute of the record, but do not interpret it as a strict matching check like in ordinary classes.

## 6. Changing Class Definitions and Reading Old Data

### 6.1. When an Enum Changes

Suppose the old version is:

~~~java
enum Phase {
    NEW, DONE
}
~~~

and the new version is:

~~~java
enum Phase {
    NEW, ACTIVE, DONE
}
~~~

Adding `ACTIVE` usually does not prevent old streams containing `NEW` or `DONE` from decoding, provided the stored names still exist. Conversely, renaming `DONE` to `FINISHED` will cause old streams containing the name `DONE` to fail to find a matching constant.

**Approach if long-term support is needed:** avoid renaming enum constants already published in Java serialized data; consider storing a **separate stable business code** if the protocol must evolve across many versions. Do not assume a Java enum name is an eternally stable external identifier outside Java.

### 6.2. When a Record Changes

Initial version:

~~~java
record User(String name, int age) implements Serializable {
}
~~~

Later adding a component:

~~~java
record User(String name, int age, String region)
        implements Serializable {
}
~~~

When the local record has a component absent from an old stream, the value passed to the canonical constructor is the **type's default value**: `0` for `int`, `false` for `boolean`, `null` for references. If the new component `region` is absent in the stream, the constructor receives `null` for `region`.

If the new constructor rejects `null`:

~~~java
record User(String name, int age, String region)
        implements Serializable {
    public User {
        if (region == null) {
            throw new IllegalArgumentException("region required");
        }
    }
}
~~~

then old data may fail to deserialize. If business rules permit, missing info can be normalized in the constructor, such as setting `region = "UNKNOWN"`; that must be an intentional schema decision, never silently defaulting sensitive fields.

The mechanism also has these characteristics:

- Field data in the stream is matched to components by **name** and type-checked appropriately; do not naively assume declaration order alone drives mapping.
- Fields present in the stream that are no longer components of the local record may be ignored.
- Changing a component's type or making incompatible structural changes can result in an exception rather than automatic type conversion.
- **Validation runs again** in the canonical constructor, so version upgrades must account for new invariants.
- Waiving UID matching is not a "license" to change schemas arbitrarily and still read all legacy data.

For long-lived persisted data, store an explicit version in the **business format** or build separately tested migration logic. Using Java Object Serialization for internal temporary caches has very different requirements from using it as a 10-year storage format.

### 6.3. Class Lifecycle and Type Names

Both enums and records still depend on the reading JVM being able to locate the corresponding class. Changing packages, renaming classes, altering classpath/module visibility, or missing classes can lead to `ClassNotFoundException` or other compatibility errors, even if constant or component names are unchanged.

Do not confuse "record data compatibility" with "no need to maintain class names." Java byte streams carry Java-ecosystem type information.

## 7. Complete Java 17+ Example: Enum and Record Round-Trip

The following program uses no disk files: it writes Java serialized bytes to a `ByteArrayOutputStream` and reads them back with a `ByteArrayInputStream`. In this demo, all bytes are **generated by the program itself**; it is a learning example of how it works, **not a guide to accepting untrusted deserialization bytes from the network**.

The code demonstrates that enums preserve identity, records have value equality without preserving identity, and the canonical constructor is called during restoration.

Save the file **`EnumRecordSerializationDemo.java`**:

~~~java
import java.io.*;
import java.util.Objects;

public class EnumRecordSerializationDemo {
    enum Phase { NEW, DONE }

    record WorkItem(String id, Phase phase, int retries)
            implements Serializable {
        @Serial
        private static final long serialVersionUID = 17L;
        private static int constructed;

        WorkItem {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(phase, "phase");
            if (id.isBlank() || retries < 0) {
                throw new IllegalArgumentException("Invalid work item");
            }
            constructed++;
        }
    }

    private static byte[] encode(Object value) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
            out.writeObject(value);
        }
        return sink.toByteArray();
    }

    private static Object decode(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Phase state = Phase.DONE;
        Phase restoredState = (Phase) decode(encode(state));
        System.out.println("Enum identity preserved: "
                + (state == restoredState));

        WorkItem original = new WorkItem("task-42", Phase.DONE, 2);
        WorkItem restored = (WorkItem) decode(encode(original));
        System.out.println("Record equality preserved: "
                + original.equals(restored));
        System.out.println("Record same instance: "
                + (original == restored));
        System.out.println("Enum component identity: "
                + (restored.phase() == Phase.DONE));
        System.out.println("Canonical constructor calls: "
                + WorkItem.constructed);
        System.out.println("Restored: " + restored);
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 EnumRecordSerializationDemo.java
java EnumRecordSerializationDemo
~~~

**Stdout verified by `--release 17` compilation and JVM execution:**

~~~text
Enum identity preserved: true
Record equality preserved: true
Record same instance: false
Enum component identity: true
Canonical constructor calls: 2
Restored: WorkItem[id=task-42, phase=DONE, retries=2]
~~~

### Exact Breakdown of Each Output

1. `Phase` is an enum, so it does not need `implements Serializable`. The `DONE` value from the stream is resolved to the `Phase.DONE` singleton, so `state == restoredState` is `true`.
2. `WorkItem` declares `implements Serializable`; removing the marker would prevent `writeObject(original)` from serializing this record via standard Java Object Serialization.
3. `original.equals(restored)` is `true` because record equality compares by component (in this example `String`, enum, and `int` have appropriate semantics).
4. `original == restored` is `false`: the record is reconstructed as a distinct object. Do not assume every record retains identity across a round-trip.
5. The `phase` component remains the enum singleton, so `restored.phase() == Phase.DONE` is `true`.
6. The `constructed` variable is static and **not** saved in the byte stream. It increments once when `new WorkItem(...)` is called and once when the canonical constructor is invoked by deserialization; hence the result is 2 in this demo process.
7. `@Serial private static final long serialVersionUID = 17L` is the record's explicit UID. For records, UID matching is not enforced under the dedicated rule.
8. `ObjectOutputStream` is closed after writing to flush and release resources; `ObjectInputStream` is closed after reading. `ByteArrayOutputStream.toByteArray()` provides a copy of the bytes.
9. Because `ObjectInputStream.readObject()` returns `Object`, the demo casts to the expected type. With untrusted data, **casting after deserialization is not a safety mechanism**, because object creation may already have happened beforehand.

## 8. Why Is Validation in the Canonical Constructor Valuable?

An ordinary `Serializable` class can be reconstructed without the regular serializable class's constructor running like a fresh instantiation. That forces invariants to rely on specialized mechanisms like `readObject` or serialization proxies.

Records differ because **the canonical constructor is actually called** during deserialization. Thus invariants such as non-negative quantities, valid identifiers, or non-`null` enum components can be checked centrally where the object is constructed.

Example:

~~~java
record Reservation(String code, int seats)
        implements Serializable {
    public Reservation {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
        if (seats <= 0 || seats > 20) {
            throw new IllegalArgumentException("seats out of range");
        }
    }
}
~~~

This illustrative code is beneficial because rule-violating objects are not silently restored as valid records. However:

- The constructor is called **after reading component values**, so referenced objects in the graph may already have been deserialized.
- Any object component needs its own validation; records do not automatically turn mutable lists/maps into immutable ones.
- Avoid side effects in constructors, because reading a byte stream can cause the constructor to execute. Constructors should focus on checking values and pure data normalization, never transferring funds, making network calls, or mutating external resources.

### Records Are Shallowly Immutable

Given:

~~~java
record Batch(int[] numbers) implements Serializable {
}
~~~

The `numbers` reference field is final, but **the array elements are still mutable**. Someone holding a reference to the array can modify its values after creating the record, or use the accessor to obtain the array and mutate it.

If the contract requires deeper immutability, defensively copy inside the canonical constructor and on return (for arrays), or use an appropriate immutable structure. This is a **data design concern**, not automatically solved by serialization.

## 9. Object Cycles and Record-Specific Limitations

Object Serialization ordinarily uses handles/back-references to preserve reference relationships and many cycles in a graph. However, for records, **components are deserialized before the record object is constructed via its canonical constructor**.

Suppose an ordinary `Node` has a field pointing back to a record that contains that very Node. If the original graph had a cycle record → Node → record, on read the back-reference to the record can become `null`. This is a limitation explicitly documented in the Java Serialization specification; do not rely on records to represent complex graphs with back-references pointing back to the record itself.

**Better design pattern:** use an acyclic DTO/record serial form, storing IDs instead of cyclic references, then rebuild relationships after validation in an explicit graph-construction step.

Example using IDs:

~~~java
record Edge(String fromId, String toId)
        implements Serializable {
}
~~~

The `fromId/toId` fields are stable data used to relink inside the graph after deserialization, rather than a circular reference back to the record being reconstructed.

## 10. Security: Enum and Record Do Not Make Deserialization Safe

**Do not deserialize untrusted bytes simply because the expected result type is an enum or record.** A Java Serialization stream can contain an object graph with many other classes, and reading can trigger behavior in classes before the result is cast or finally validated.

Practical security rules:

1. **Prefer avoiding Java native deserialization for external data.** If a public protocol is needed, use explicitly schema-defined data like JSON/protobuf/CBOR with a controlled parser.
2. If Java Serialization is mandatory, **only accept trusted sources** and restrict allowed classes. Use `ObjectInputFilter` (JDK 9+, built into Java 17) following an allowlist/threat-model approach.
3. Limit graph depth, reference count, stream bytes, array lengths, and resource budgets; **filtering does not replace source authentication**.
4. Audit all libraries/classpath dependencies: serializable classes in the object graph may have special read hooks.
5. A record's canonical constructor validates after component values have been read, so **it does not replace deserialization input checks**.
6. Have a clear error policy for `InvalidClassException`, `ClassNotFoundException`, `StreamCorruptedException`, `InvalidObjectException`, and `NotSerializableException`.
7. Do not log entire serialized payloads or sensitive data; mind size/quotas even when writing to `ByteArrayOutputStream` in learning examples.

Illustrative snippet for graph bounds using `ObjectInputFilter`:

~~~java
ObjectInputFilter limit = info -> {
    if (info.depth() > 12
            || info.references() > 500
            || info.streamBytes() > 1024 * 1024) {
        return ObjectInputFilter.Status.REJECTED;
    }
    return ObjectInputFilter.Status.UNDECIDED;
};

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(limit);
    Object value = in.readObject();
}
~~~

This **is not a standalone program**; it requires importing `ObjectInputFilter` and `ObjectInputStream`, where `source` is an existing `InputStream`. The snippet **only sets resource limits** without a class allowlist, so it **is not sufficient** to safely deserialize untrusted input. In production, prefer a filter combining an allowlist of truly needed classes with byte/depth/array limits; test the filter against the entire valid object graph.

**Note:** data produced by your own program can also expire or become incompatible after a version upgrade; "trusted source" does not mean "readable across all versions."

## 11. Enum and Record in Real-World Systems

### 11.1. Internal Record DTOs or Temporary Caches

Example:

~~~java
enum TaskStatus { QUEUED, DONE }

record TaskSnapshot(String id, TaskStatus status, long updatedAt)
        implements Serializable {
}
~~~

A `TaskSnapshot` containing only primitives, `String`, and enums can be round-tripped relatively simply. When used as a temporary cache internal to a JVM/Java ecosystem with controlled version compatibility, Java Serialization can be viable.

However, if stored long-term in a database, sent across polyglot services, or shared between independently evolving application versions, an explicit-schema format is generally easier to migrate, audit, and secure.

### 11.2. Enum as Domain Code, Record as Payload

A clear design:

- Enums represent the set of states in Java code.
- Records represent the data of a snapshot/request.
- When exporting to a long-term format, map the enum to a stable business code, such as `"completed"`, and declare a payload schema. Avoid forcing external data to depend forever on Java constant names.

This lets you use enums/records within the Java domain while still managing migrations explicitly if package names, record types, or enum constants change.

### 11.3. When a Custom Serial Form Is Needed

If you need custom `writeObject/readObject` hooks, records do not provide the same customization path as ordinary `Serializable` classes. Options include:

- Use an ordinary serializable class with hooks per specification (and strict review).
- Use an explicit **serialization proxy** via `writeReplace` on the record and `readResolve` on the proxy; store the payload in an easily versionable form. This is an advanced technique requiring multi-version tests and ensuring compatible replacement types.
- Use a codec/schema independent of Object Serialization if the goal is stable storage or interchange.

Do not use `readResolve` on an enum as a proxy or to handle renames: enum hooks are ignored.

## 12. Common Mistakes and How to Fix Them

| Misconception | Consequence | Correct Understanding |
| --- | --- | --- |
| "Records are automatically Serializable because they are data carriers" | `NotSerializableException` | Must explicitly `implements Serializable` |
| "Enums need implements Serializable" | Redundant declaration, misunderstanding mechanism | Enums are already serializable via `java.lang.Enum` |
| "Enums serialize ordinals" | Broken versioning design | Enums store the **constant name** |
| "Enums serialize all instance fields" | Expecting mutable state to sync | Only the constant name is used to restore the constant |
| "Renaming an enum constant still reads old streams" | Cannot find the stored name | Keep old names or do explicit migration |
| "Enum readResolve prevents duplicate singletons" | Hook is not used | Enums inherently preserve singleton identity |
| "Record readObject will run" | Validation placed in the wrong spot | Put invariants in the canonical constructor |
| "Record deserialization skips constructors" | Missing that constructors can throw | The canonical constructor is invoked |
| "Record == stays true after round-trip" | Wrong identity comparison | Compare value via `equals` when appropriate |
| "Record UID must always match" | Misunderstanding compatibility | UID matching is specifically waived for records |
| "Record UID doesn't matter so any schema change is compatible" | Errors when changing components/invariants | Check names/types/defaults/constructor |
| "Record fields are final so all data is deeply immutable" | Mutable components still get mutated | Defensive copying/immutable schemas |
| "All record reference cycles are preserved" | Back-references can become `null` | Avoid cycles pointing back to records |
| "Records/enums eliminate untrusted stream deserialization risk" | Risk from other object graphs | Avoid untrusted Java Serialization; filter/allowlist |
| "Casting after readObject validates before object creation" | Too late to block deserialization side effects | Use safe structures/formats/filters from the start |

## 13. Self-Check Questions

**Question 1.** Does `enum Color { RED, BLUE }` need `implements Serializable` to be written with `ObjectOutputStream`?

**Answer:** No. Enums are already serializable.

**Question 2.** Does Java store `Color.RED` by ordinal or by name?

**Answer:** By the name `RED`, along with the necessary stream type info; ordinals are not used to identify constants.

**Question 3.** Can you change an enum's `toString()` without changing the serialized constant identifier?

**Answer:** Yes. Identification is based on `name()`; be careful when changing the constant's own name.

**Question 4.** Can `record User(String name) {}` be serialized with `writeObject(new User("Lan"))`?

**Answer:** Not under default Java Object Serialization because it does not declare `implements Serializable`.

**Question 5.** Does reading a record back from a stream invoke its canonical constructor?

**Answer:** Yes. The constructor can validate invariants and reject invalid data.

**Question 6.** Does a `private void readObject(...)` declared on a record customize restoration?

**Answer:** No. That hook is ignored when serializing/deserializing records; use the canonical constructor or an appropriate alternative serial form design.

**Question 7.** Adding a `String region` component to a record gives what value when reading an old stream without region?

**Answer:** The default value `null` is passed to the canonical constructor; if the constructor rejects null, the old data may fail to restore.

**Question 8.** Can you rely on record UID matching being waived to claim changing component types is always safe?

**Answer:** No. Names/types/defaults and validation still govern restoration capability.

**Question 9.** Does deserializing a record containing an object graph with a cycle pointing back to the record always preserve reference identity?

**Answer:** No. Cycles from components back to the record have specific limitations; back-references may become `null`.

**Question 10.** For bytes received from an HTTP request, is expecting only `MyRecord` as the result type enough to make `readObject()` safe?

**Answer:** No. Objects in the stream can be processed before the result is cast. Avoid untrusted native deserialization or apply filters/allowlists and multiple layers of defense.

## 14. Key Takeaways

- **Enum:** already `Serializable`; stores constant name, restores the exact enum constant, preserves `==`; does not store instance state and ignores custom serialization hooks.
- **Record:** must `implements Serializable`; stores record components; **invokes canonical constructor** on deserialization; typically has value equality while being a new object.
- **Compatibility:** enums depend on constant names; records depend on component names/types, defaults for missing components, and constructor invariants; record UID matching is waived but does not guarantee every migration.
- **Limitations:** records do not customize ordinary `writeObject/readObject`; `writeReplace/readResolve` are exceptions; cycles pointing back to a record are not preserved like in ordinary classes.
- **Security:** Java Object Serialization is not meant for arbitrary untrusted input; enums and records do not replace object graph controls, resource limits, or schemas.

### Official Documentation

- [Java SE 17 — Object Serialization Specification, System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html) — Sections 1.12 (enum), 1.13 (record), 1.14 (circular references).
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html) — deserialization API and security warnings.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) — filtering during deserialization.
- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html) — marker interface and serializable class mechanism.
