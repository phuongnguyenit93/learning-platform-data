# Serializable with Enum and Record in Java 17+: Serialization, Restoration, and Compatibility Rules

## 1. Why Must Enum and Record Be Studied Separately?

Java Object Serialization lets you write objects into byte sequences via `ObjectOutputStream` and restore them via `ObjectInputStream`. The marker interface `java.io.Serializable` is the foundation enabling most Java objects to participate in this mechanism.

However, **`enum` and `record` do not follow the same serialization rules as ordinary classes**:

- `enum` **is serializable by default**. Its special format stores the **enum constant name**, not an instance state bundle like a normal class. When reading, Java looks up **the existing enum constant**.
- `record` **does not automatically implement Serializable**. When a record declares `implements Serializable`, its serialized form is determined by **record components**, and when reading, Java invokes the **canonical constructor** to construct the object instead of restoring fields like an ordinary class.
- Both have specific limitations regarding `writeObject`/`readObject`, `serialVersionUID`, handling class definition changes, and deserialization security.

This lesson focuses on Java 17+ and **built-in Java Object Serialization**, not JSON, Jackson, protobuf, or database mapping. Goal: understand what gets stored, what happens on read-back, how to validate, and how to avoid pitfalls when evolving versions.

## 2. Quick Recap: Serializable, Streams, and Object Graphs

An ordinary class can declare:

```java
import java.io.Serializable;

class Note implements Serializable {
    private static final long serialVersionUID = 1L;
    String text;
}
```

The snippet above **merely illustrates the declaration**, not a complete program. The `Serializable` interface is a **marker interface**: it requires implementing no methods. `ObjectOutputStream.writeObject(value)` writes class metadata and necessary state; `ObjectInputStream.readObject()` reconstructs objects in the object graph.

Typical contract points:

- An object being `Serializable` **does not guarantee the entire object graph is serializable**. If a field or component references a non-serializable object, the process can throw `NotSerializableException`.
- `static` fields do not belong to per-instance serialized state; in ordinary classes, `transient` marks fields excluded from default serialization.
- Java Object Serialization uses a Java-specific binary format requiring compatible classes on read-back; it **does not automatically serve as a stable cross-language interchange protocol**.
- Streams should be closed with `try-with-resources`. Never deserialize bytes from untrusted sources simply because they carry a `.ser` extension.
- Reference and cycle preservation in Java Serialization has special caveats for records, explained later.

Comparison table:

| Feature | Regular `implements Serializable` Class | `enum` | `record implements Serializable` |
| --- | --- | --- | --- |
| Need to declare marker? | Yes (or inherit a serializable type) | **No**, enums are already serializable | **Yes**, records are not automatically serializable |
| Primary stream content | Serializable fields per class mechanism | **Name of the enum constant** | **Values of record components** |
| On deserialization | Restores instance and fields per class mechanism | Looks up constant via `Enum.valueOf` | **Invokes canonical constructor** |
| Object identity | Usually receives a newly reconstructed instance | Preserves exact enum singleton constant (`==`) | New instance; compare contents via `equals` |
| Custom `writeObject/readObject` | Usable when following the contract | **Ignored** | **Ignored** |
| `writeReplace/readResolve` | Applicable per specification | **Ignored** | **Applicable** |
| `serialVersionUID` | Crucial for compatibility | Fixed at `0L`; explicit declarations ignored | Defaults to `0L` or explicitly declared; UID matching is waived |
| Self-referential cycles back to object | Can be preserved via object handles | Enums are pre-existing constants | Cycles through components back to the record **are not preserved** |

## 3. Enum: Stores Constant Name, Not Instance State

### 3.1. Why Is `implements Serializable` Unnecessary?

Every Java `enum` type extends `java.lang.Enum`, which already implements `Serializable`. Example:

```java
enum Status {
    NEW, PROCESSING, DONE
}
```

This declaration is sufficient for values like `Status.DONE` to be passed to `ObjectOutputStream.writeObject(...)`; no extra marker or special constructor is needed.

**When writing:** the stream writes the enum type identifier and the constant name returned by `name()`, such as `"DONE"`. Ordinals or instance fields declared on constants are not persisted as state under the special enum mechanism.

**When reading:** Java resolves the constant name via a mechanism equivalent to `Enum.valueOf(Status.class, "DONE")`. Consequently, the result is **the exact `Status.DONE` already present in the JVM**, without instantiating a duplicate enum object.

```java
Status original = Status.DONE;
// After writeObject then readObject succeeds:
Status restored = Status.DONE; // Example restored value.
System.out.println(original == restored); // true
```

The snippet above only depicts the result. The complete runnable program is in Section 7.

### 3.2. `name()` Differs from `toString()` and `ordinal()`

An enum can define a display label:

```java
enum Level {
    LOW("Thấp"), HIGH("Cao");

    private final String label;

    Level(String label) {
        this.label = label;
    }

    @Override
    public String toString() {
        return label;
    }
}
```

If `Level.HIGH` is serialized, Java stores the **name `HIGH`**, not the string `"Cao"` from `toString()`. Nor does it store `ordinal()` as the constant identifier.

Consequences:

- Changing `toString()` or display labels does not break deserialization of old enum values.
- Reordering constant declarations does not alter the stored name `HIGH`.
- **Renaming or deleting a constant** that already appeared in old streams can break restoration because that name no longer exists. This is a critical distinction when upgrading versions.

### 3.3. Fields Inside an Enum Are Not Restored from the Stream

Consider an enum with state:

```java
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
```

Even if `Mode.SAFE.markUsed()` is called before serializing, the byte stream for `Mode.SAFE` still represents only **the constant SAFE**, without a snapshot of `visits`.

When reading the enum in **the same JVM**, you receive `Mode.SAFE` with whatever current state that singleton holds in that JVM. If deserialized in another JVM, the state is whatever that runtime initialized or manages, **not the visit count from the source JVM**. Never use enum serialization to synchronize mutable data attached to an enum.

### 3.4. Custom Hooks on Enums Have No Effect

For enums, Java Object Serialization ignores custom methods defined on the enum such as `writeObject`, `readObject`, `readObjectNoData`, `writeReplace`, and `readResolve`. It also ignores `serialPersistentFields` and any explicit `serialVersionUID` field; an enum's UID is always `0L`.

Therefore, **do not write `readResolve()` inside an enum to protect uniqueness**: name-based lookup already guarantees no new enum constant is created. Never assume writing `writeObject` to store extra dynamic fields will work. If you need per-request mutable data, place it in a **separate serializable class or record**, keeping the enum strictly for a finite set of types or states.

## 4. Record: Structural Immutability Does Not Mean Serializable

### 4.1. Must Declare `implements Serializable`

Records became standard in Java 16 (and are stable in Java 17), representing data via **record components**:

```java
record Point(int x, int y) {
}
```

The record above is **not yet serializable**, even though it has a compiler-generated constructor, accessors, `equals`, `hashCode`, and `toString`. Passing an instance to `ObjectOutputStream.writeObject` throws `NotSerializableException`.

A version supporting Java Object Serialization must declare:

```java
import java.io.Serializable;

record Point(int x, int y) implements Serializable {
}
```

Simply adding the marker is insufficient if a component has a reference type holding non-serializable data. Example:

```java
record Holder(Object value) implements Serializable {
}

Holder invalid = new Holder(new Object());
// writeObject(invalid) can throw NotSerializableException
// because java.lang.Object does not implement Serializable.
```

The two snippets above are **illustrative**. A component typed `Object` does not automatically make all contained values supported, just as `List` does not guarantee every implementation or element is serializable.

### 4.2. What Does Java Write for a Record?

Given:

```java
record Product(String sku, int quantity) implements Serializable {
}
```

The serialized form of a record is based on the **values of its two components** `sku` and `quantity`. A record cannot declare arbitrary instance fields beyond those generated for record components. `static` fields are not part of per-instance state and do not belong to the component serialized form.

Unlike regular classes, record serialization does not use `serialPersistentFields` to arbitrarily select fields and does not invoke a `writeObject` defined by the record. Thus, **the component set is directly the data contract** to consider during versioning.

This does not mean "records serialize to JSON." The Java byte stream still carries type/class metadata and field descriptors per the Java Object Serialization protocol.

### 4.3. The Canonical Constructor Runs on Deserialization

A record is restored via its **canonical constructor**: Java reconstructs the component values from the stream and passes them to this constructor.

```java
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
```

This is an illustrative declaration. `public` on a compact canonical constructor suits a public record; for a package-private record, constructor visibility need not be `public`. Because the canonical constructor executes during deserialization, checks like non-blank `id` and `balance >= 0` are enforced even when data originates from a serialized stream.

If the constructor rejects the restored values, Java reports `InvalidObjectException` (with the constructor's exception as its cause). **Do not rely on post-read setters to patch invariants**: records are constructed directly with the read values through the constructor.

Important: record validation **does not imply the data source is trusted**. A byte stream can trigger creation, parsing, or restoration of other component objects before the record's canonical constructor is ever reached. Apply deserialization security policies across the entire stream.

### 4.4. Which Serializer Hooks Take Effect?

For a serializable record, hooks that apply to regular classes behave differently:

| Member | Record in Java Serialization |
| --- | --- |
| `private void writeObject(ObjectOutputStream)` | Ignored |
| `private void readObject(ObjectInputStream)` | Ignored |
| `readObjectNoData` | Ignored |
| `writeExternal/readExternal` | Ignored for the record's serialized form |
| `serialPersistentFields` | Ignored |
| `writeReplace` | Can be used for object replacement |
| `readResolve` | Can be used to choose a replacement object after restoration |
| Canonical constructor | **Invoked** when constructing the record from the stream |
| `serialVersionUID` | Defaults to `0L`; declarable, though UID matching is waived for records |

When component validation is needed, prefer placing invariants in the canonical constructor. If you need a **completely custom serialized form**, records do not support `writeObject/readObject` customization like regular classes; consider a **serialization proxy** using `writeReplace/readResolve` or an explicit format like JSON/CBOR/protobuf with a clear schema.

Do not start with hooks for problems that are purely validation; the less custom stream behavior you have, the easier it is to audit and control.

## 5. SerialVersionUID: Differences Across Enum, Record, and Class

`serialVersionUID` is the class version identifier in Java Serialization. For ordinary classes, a UID mismatch can cause `InvalidClassException` during deserialization.

**Enum:**

- UID is always fixed at `0L`.
- If you declare a field named `serialVersionUID` inside an enum, serialization **ignores** it.
- Do not use UIDs to version enum constant names.

**Record:**

- UID defaults to `0L` unless the record declares an explicit value.
- Java **waives the requirement that the two UIDs match** when deserializing records.
- This **does not guarantee all record structural changes are compatible**: adding/removing/renaming/retyping components can still alter restored data or cause the constructor to reject it.

Example:

```java
import java.io.Serial;
import java.io.Serializable;

record Invoice(String code, long cents) implements Serializable {
    @Serial
    private static final long serialVersionUID = 17L;
}
```

`@Serial` (available since Java 14) expresses intent for serialization-related fields/methods and helps the compiler flag semantically invalid declarations. The UID here is a serial version attribute of the record, but do not interpret it as a strict matching check like an ordinary class.

## 6. Class Definition Changes and Reading Legacy Data

### 6.1. When an Enum Changes

Suppose the old version:

```java
enum Phase {
    NEW, DONE
}
```

and the new version:

```java
enum Phase {
    NEW, ACTIVE, DONE
}
```

Adding `ACTIVE` normally does not prevent old streams containing `NEW` or `DONE` from decoding, provided the stored names still exist. Conversely, renaming `DONE` to `FINISHED` causes old streams holding `DONE` to fail because no matching constant exists.

**Approach for long-term support:** avoid renaming enum constants already published in Java serialized data; consider storing a **separate stable business code** if the protocol must evolve across versions. Never assume a Java enum constant name is a permanent external identifier.

### 6.2. When a Record Changes

Initial version:

```java
record User(String name, int age) implements Serializable {
}
```

Later adding a component:

```java
record User(String name, int age, String region)
        implements Serializable {
}
```

When the local record has a component absent from the old stream, the value passed to the canonical constructor is **the type's default value**: `0` for `int`, `false` for `boolean`, `null` for references. Since the new component `region` is absent from the stream, the constructor receives `null` for `region`.

If the new constructor rejects `null`:

```java
record User(String name, int age, String region)
        implements Serializable {
    public User {
        if (region == null) {
            throw new IllegalArgumentException("region required");
        }
    }
}
```

then old data may fail to deserialize. If domain rules allow, you can normalize missing data in the constructor—such as assigning `region = "UNKNOWN"`; that must be a deliberate schema decision, never defaulting sensitive fields blindly.

Additional behavioral characteristics:

- Stream field data is matched to components by **name** and checked for type compatibility; do not naively assume declaration order alone dictates mapping.
- Fields present in the stream that are no longer components of the local record are ignored.
- Changing a component's type or making an incompatible structural change may throw an exception rather than auto-converting values.
- **Validation re-runs** in the canonical constructor, so version upgrades must account for new invariants.
- Waived UID matching is not a "free pass" to reshape schemas arbitrarily while expecting all old data to still load.

For long-lived persisted data, store an explicit version in the **business format** or build a separately tested migration mechanism. Using Java Object Serialization for transient internal caches has very different requirements from using it as a 10-year storage format.

### 6.3. Class Lifecycle and Type Names

Both enums and records still depend on the reading JVM being able to locate the corresponding class. Changing packages, renaming classes, altering classpath/module visibility, or missing classes can cause `ClassNotFoundException` or other compatibility failures, even when constant names or components remain unchanged.

Do not confuse "record data compatibility" with "no need to maintain class names." A Java byte stream embeds Java ecosystem type metadata.

## 7. Complete Java 17+ Example: Enum and Record Round-Trip

The following program touches no disk files: it writes Java serialized bytes into a `ByteArrayOutputStream` and reads them back with a `ByteArrayInputStream`. In this demo, all bytes are **self-generated by the program**; it is a learning example for mechanics, **not a guide for accepting untrusted deserialization bytes over a network**.

The code demonstrates that enums preserve identity, records have value equality without identity preservation, and the canonical constructor runs during restoration.

Save as **`EnumRecordSerializationDemo.java`**:

```java
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
```

Compile and run with JDK 17+:

```bash
javac --release 17 -encoding UTF-8 EnumRecordSerializationDemo.java
java EnumRecordSerializationDemo
```

**Stdout verified by compiling with `--release 17` and running on the JVM:**

```text
Enum identity preserved: true
Record equality preserved: true
Record same instance: false
Enum component identity: true
Canonical constructor calls: 2
Restored: WorkItem[id=task-42, phase=DONE, retries=2]
```

### Exact Analysis of Each Result

1. `Phase` is an enum, so it needs no `implements Serializable`. The `DONE` value from the stream resolves to the `Phase.DONE` singleton, so `state == restoredState` is `true`.
2. `WorkItem` declares `implements Serializable`; removing the marker prevents `writeObject(original)` from serializing this record via standard Java Object Serialization.
3. `original.equals(restored)` is `true` because record equality compares components (here `String`, enum, and `int` all have matching semantics).
4. `original == restored` is `false`: the record is reconstructed as a distinct object. Never assume records preserve reference identity across a round-trip.
5. The `phase` component remains the enum singleton, so `restored.phase() == Phase.DONE` is `true`.
6. The `constructed` field is static and **not** written into the byte stream. It increments once on `new WorkItem(...)` and once when the canonical constructor is called by deserialization, yielding 2 in this demo process.
7. `@Serial private static final long serialVersionUID = 17L` is the record's explicit UID. For records, UID matching is waived under the record-specific rule.
8. `ObjectOutputStream` is closed after writing to flush and release resources; `ObjectInputStream` is closed after reading. `ByteArrayOutputStream.toByteArray()` supplies a copy of the bytes.
9. Because `ObjectInputStream.readObject()` returns `Object`, the demo casts to the expected type. For untrusted data, **casting after deserialization is not a security measure**, because object construction has already taken place.

## 8. Why Is Validation Inside the Canonical Constructor Valuable?

A normal `Serializable` class can be reconstructed without running its regular constructors in the usual way. This forces invariants into specialized hooks like `readObject` or a serialization proxy.

Records differ because the **canonical constructor is actually invoked** during deserialization. Thus, invariants such as non-negative quantities, valid identifiers, or non-`null` enum components can be enforced centrally at the object creation point.

Example:

```java
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
```

This illustration is valuable because rule-violating objects cannot silently materialize as valid records. Still:

- The constructor runs **after component values have been read**, so referenced objects in the graph have already been deserialized.
- Every object component must be validated individually; records do not automatically make mutable lists or maps immutable.
- Avoid side effects in constructors, since reading a byte stream will run the constructor. Constructors should focus on validating values and pure data normalization rather than sending payments, making network calls, or mutating external resources.

### Records Are Shallowly Immutable

Given:

```java
record Batch(int[] numbers) implements Serializable {
}
```

The `numbers` reference field is final, yet **the array elements remain mutable**. Anyone holding a reference to the array can mutate its contents after creating the record, or retrieve the array via its accessor and modify it.

If the contract requires deep immutability, defensively copy inside the canonical constructor and accessor (for arrays), or use an appropriate immutable structure. This is a **data-design responsibility**, not something solved automatically by serialization.

## 9. Object Cycles and Record-Specific Limitations

Object Serialization generally uses handles/back-references to preserve reference sharing and many cycles in an object graph. With records, however, **components are deserialized before the record object itself is constructed via its canonical constructor**.

Suppose a regular `Node` holds a field pointing back to a record containing that `Node`. If the original graph had a cycle record → Node → record, when reading back, the back-reference pointing to the record can become `null`. This limitation is explicitly documented in the Java Serialization Specification; do not rely on records to represent complex graphs with back-references pointing back to the record itself.

**Better design pattern:** an acyclic DTO/record serialized form storing IDs instead of cyclic references, then rebuilding links after validation in an explicit graph-assembly step.

ID-based example:

```java
record Edge(String fromId, String toId)
        implements Serializable {
}
```

The `fromId/toId` fields provide stable data for relinking the graph after deserialization rather than a circular reference back to a record under construction.

## 10. Security: Enum and Record Do Not Make Deserialization Safe

**Never deserialize untrusted bytes simply because the expected result type is an enum or a record.** A Java Serialization stream can contain an object graph of many other classes, and reading can trigger behavior inside those classes long before the result is cast or finally validated.

Practical security rules:

1. **Prefer avoiding Java native deserialization for external data.** For public protocols, use explicit-schema formats like JSON/protobuf/CBOR with controlled parsers.
2. If Java Serialization is mandatory, **accept only trusted sources** and restrict deserializable classes. Use `ObjectInputFilter` (JDK 9+, built into Java 17) following an allowlist and threat model.
3. Cap graph depth, reference count, stream bytes, array length, and resource budgets; **filtering does not replace source authentication**.
4. Audit all libraries/classpath: any serializable class reachable in the object graph may contain custom read hooks.
5. A record's canonical constructor validates only after component values are read, so it **does not replace deserialization input controls**.
6. Define clear error handling for `InvalidClassException`, `ClassNotFoundException`, `StreamCorruptedException`, `InvalidObjectException`, and `NotSerializableException`.
7. Do not log full serialized payloads or sensitive data; watch sizes and quotas even when writing to `ByteArrayOutputStream` in learning examples.

An illustrative snippet restricting graph shape via `ObjectInputFilter`:

```java
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
```

This is **not a standalone program**; it requires importing `ObjectInputFilter` and `ObjectInputStream`, with `source` as an existing `InputStream`. The snippet **only sets resource limits** without allowlisting classes, so it is **insufficient** to deserialize untrusted input safely. In production, prefer combining an allowlist of strictly needed classes with byte/depth/array caps, and test the filter against every valid object graph.

**Note:** data produced by your own program can still become stale or incompatible after an upgrade; "trusted source" does not imply "readable across all versions."

## 11. Enum and Record in Real-World Systems

### 11.1. Internal Record DTOs or Short-Lived Caches

Example:

```java
enum TaskStatus { QUEUED, DONE }

record TaskSnapshot(String id, TaskStatus status, long updatedAt)
        implements Serializable {
}
```

A `TaskSnapshot` containing only primitives, `String`, and enums can round-trip fairly simply. If used as a short-lived cache internal to a JVM/Java ecosystem with tightly controlled version compatibility, Java Serialization can be viable.

However, for long-term database storage, cross-service polyglot communication, or sharing across independently evolving app versions, an explicit-schema format is usually far easier to migrate, audit, and secure.

### 11.2. Enum as Domain Code, Record as Payload

A clean design:

- Enums model fixed state sets in Java code.
- Records represent snapshot/request data.
- When exporting to a long-lived format, map enums to stable business codes—such as `"completed"`—and declare a payload schema. Avoid tying external data forever to Java constant identifiers.

This lets you enjoy enums/records in Java domain logic while retaining explicit migration control if packages, record types, or enum constants are renamed.

### 11.3. When a Custom Serial Form Is Required

If you need custom `writeObject/readObject` hooks, records lack the customization path of ordinary `Serializable` classes. Options include:

- Using a regular serializable class with spec-compliant hooks (and thorough code review).
- Using an explicit **serialization proxy** via `writeReplace` on the record and `readResolve` on the proxy, persisting an easily versioned payload. This is an advanced technique requiring multi-version tests and compatible replacement types.
- Using a codec/schema independent of Object Serialization if the goal is stable data persistence or exchange.

Do not try to use `readResolve` on an enum as a proxy or rename check: enum hooks are ignored.

## 12. Common Mistakes and Fixes

| Misconception | Consequence | Correct Understanding |
| --- | --- | --- |
| "Records are automatically Serializable as data carriers" | `NotSerializableException` | Must explicitly `implements Serializable` |
| "Enums need implements Serializable" | Redundant declaration, misunderstanding of mechanism | Enums are already serializable via `java.lang.Enum` |
| "Enums serialize their ordinal" | Broken versioning design | Enums store the **constant name** |
| "Enums serialize all instance fields" | Expecting mutable state to sync | Only the constant name is used to resolve the constant |
| "Renaming an enum constant still reads old streams" | Stored name not found | Keep old names or perform explicit migration |
| "Enum readResolve prevents duplicate singletons" | Hook is ignored | Enums inherently preserve singleton identity |
| "Record readObject will execute" | Validation placed in dead code | Put invariants in the canonical constructor |
| "Record deserialization skips constructors" | Missing that constructors can throw errors | The canonical constructor is invoked |
| "Record == holds after round-trip" | Wrong identity comparison | Compare values with `equals` when appropriate |
| "Record UID must always match" | Misinterpreting compatibility | UID matching is specifically waived for records |
| "Waived record UID means any schema change is safe" | Failures on component/invariant changes | Check names/types/defaults/constructors |
| "Final record fields mean deep immutability" | Mutable components still get mutated | Use defensive copies / immutable schemas |
| "All record reference cycles are preserved" | Back-references can become `null` | Avoid cycles pointing back to records |
| "Records/enums eliminate untrusted stream risk" | Exposure via other object graphs | Avoid untrusted Java Serialization; use filters/allowlists |
| "Casting after readObject validates before creation" | Too late to block deserialization side effects | Use safe formats/structures/filters upfront |

## 13. Self-Check Questions

**Question 1.** Does `enum Color { RED, BLUE }` need `implements Serializable` to be written with `ObjectOutputStream`?

**Answer:** No. Enums are already serializable.

**Question 2.** Does Java store `Color.RED` by ordinal or by name?

**Answer:** By name `RED`, along with required stream type metadata; ordinals are not used to identify constants.

**Question 3.** Can you change an enum's `toString()` without changing the serialized constant identifier?

**Answer:** Yes. Identification relies on `name()`; exercise caution only when renaming the constant identifier itself.

**Question 4.** Can `record User(String name) {}` be serialized by `writeObject(new User("Lan"))`?

**Answer:** Not under default Java Object Serialization because it has not declared `implements Serializable`.

**Question 5.** Does reading a record back from a stream invoke its canonical constructor?

**Answer:** Yes. The constructor can validate invariants and reject invalid data.

**Question 6.** Does a `private void readObject(...)` declared on a record customize restoration?

**Answer:** No. That hook is ignored during record serialization/deserialization; use the canonical constructor or another suitable serial-form design.

**Question 7.** Adding a `String region` component to a record yields what value when reading an old stream lacking `region`?

**Answer:** The default value `null` is passed to the canonical constructor; if the constructor rejects null, old data may fail to restore.

**Question 8.** Can you rely on waived record UID matching to conclude that changing a component's type is always safe?

**Answer:** No. Names, types, defaults, and constructor validation still determine whether restoration succeeds.

**Question 9.** Does deserializing a record whose object graph contains a cycle pointing back to the record always preserve reference identity?

**Answer:** No. Cycles from components back to the record have specific limitations; the back-reference can turn into `null`.

**Question 10.** For bytes received from an HTTP request, is expecting result type `MyRecord` enough to make calling `readObject()` safe?

**Answer:** No. Objects inside the stream can be processed before the result is cast. Avoid untrusted native deserialization or apply filters/allowlists and proper defense-in-depth layers.

## 14. Takeaway

- **Enum:** already `Serializable`; stores constant name, resolves back to the exact enum constant preserving `==`; does not persist instance state and ignores custom serialization hooks.
- **Record:** must declare `implements Serializable`; stores record components; **invokes the canonical constructor** during deserialization; normally provides value equality as a new instance.
- **Compatibility:** enums depend on constant names; records depend on component names/types, defaults for missing components, and constructor invariants; record UID matching is waived, yet migrations are not guaranteed.
- **Limitations:** records do not customize `writeObject/readObject` like ordinary classes; `writeReplace/readResolve` are supported exceptions; cycles pointing back to a record are not preserved like ordinary classes.
- **Security:** Java Object Serialization is not meant for untrusted arbitrary input; enums and records do not replace object-graph controls, resource limits, or explicit schemas.

### Official Documentation

- [Java SE 17 — Object Serialization Specification, System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html) — Sections 1.12 (enum), 1.13 (record), 1.14 (circular references).
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html) — deserialization APIs and security warnings.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) — filtering during deserialization.
- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html) — marker interface and serializable class mechanics.
