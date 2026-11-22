# Records, Enums, and Format-Specific Serialization Rules

When upgrading or migrating a Java application, two data types that look “simple” have very specific serialization rules: **records** and **enums**. Both are commonly used to represent business data, yet their read/write format in **Java Object Serialization** differs from ordinary Java classes (`Serializable` classes). If an application still writes objects to files, stores byte streams in caches, or transmits objects over a Java-specific protocol, these differences can determine whether legacy data remains readable after upgrading the JDK or modifying classes.

These special rules are also easily confused with how JSON, XML, JPA, Avro, or Protocol Buffers handle the exact same Java types. For example, Java Object Serialization does not write enums by `ordinal()`; conversely, an ORM configured with `EnumType.ORDINAL` writes that exact ordinal number into the database. For records, Java serialization uses record components and invokes the **canonical constructor** when reconstructing the object, whereas a JSON mapper may use its own creator, converter, or module.

This lesson focuses on Java Object Serialization as a foundation, contrasts it with common data formats, and builds a migration workflow for records and enums that may evolve across application versions.

## 1. First: Identify Which Format “Serialization” Refers To

**Serialization** is the process of converting an object into a form that can be stored or transmitted. **Deserialization** performs the reverse. The Java API name alone is not enough to define the data contract; you must know the format on the wire or in storage.

A Java system may use multiple formats:

| Format/Mechanism | Data Typically Written | Factors Affecting Compatibility |
|---|---|---|
| Java Object Serialization (`ObjectOutputStream` / `ObjectInputStream`) | Object graph in Java's native stream protocol | Class name, descriptor, fields/components, enum constants, stream-specific rules |
| JSON | Objects, arrays, strings, numbers, booleans, null | Property names, converters, enum representation, null/default policy |
| XML | Elements, attributes, schema types | XML schema, bindings, and adapters |
| JPA/JDBC | Columns, rows, and relationships | Mappings, enum name/ordinal, converters, DB schema |
| Protocol Buffers | Field numbers and wire types | Field numbers, reserved fields, enum numeric values, unknown fields |
| Avro | Writer schema and reader schema | Schema resolution, defaults, enum symbols, unions |
| Custom binary format | Application-defined byte layout | Version headers, byte order, field mapping, and validation |

When asked to “convert a class to a record” or “add an enum constant,” the critical questions are not merely whether the code compiles, but also:

1. **Which serializer produced the stored bytes?**
2. **Can old and new application versions both read the same data?**
3. **Are field names, component names, or enum constant names part of a long-term data contract?**
4. **Is there schema versioning and a policy for missing/unknown values?**
5. **Must data remain readable for rollback, replay, or auditing?**

Do not infer JSON or database behavior solely from Java Object Serialization rules.

## 2. Overview of Java Object Serialization

### 2.1. `Serializable` Is a Marker Interface

An ordinary class wishing to participate in Java Object Serialization typically implements the marker interface `java.io.Serializable`:

```java
import java.io.Serializable;

public final class LegacyOrder implements Serializable {
    private static final long serialVersionUID = 1L;

    private String id;
    private long totalCents;

    public LegacyOrder(String id, long totalCents) {
        this.id = id;
        this.totalCents = totalCents;
    }
}
```

A marker interface does not automatically make every field serializable. During object writing, a field referencing a non-serializable object can cause writing to throw `NotSerializableException`. Rules involving `transient`, `static`, `serialVersionUID`, and serialization hooks apply to ordinary classes, yet **cannot be applied mechanically verbatim to records and enums**.

### 2.2. Writing Objects with `ObjectOutputStream`

Example writing an object into an internal buffer:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectOutputStream;

static byte[] serialize(Object value) throws IOException {
    try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
         ObjectOutputStream output = new ObjectOutputStream(bytes)) {

        output.writeObject(value);
        output.flush();
        return bytes.toByteArray();
    }
}
```

This example uses application-controlled data and does not represent a protocol suitable by default for untrusted inputs. Native Java deserialization carries the risk of executing unintended behavior through object graphs and serialization hooks of classes on the classpath. When accepting bytes from untrusted networks or users, prefer data formats with explicit schemas and boundaries, or apply serialization filters and proper trust isolation if Object Serialization is unavoidable.

### 2.3. Reading Objects: What Does the Current Class Control?

When `ObjectInputStream` reads a stream, it maps the class descriptor in the stream to a class available in the runtime. If the class changed, reading may succeed, fail, or produce an object with unintended default values.

Aspects to distinguish:

- **Class compatibility:** can the class by name and descriptor match the runtime class?
- **Version compatibility:** for ordinary Serializable classes, does `serialVersionUID` match validly?
- **Field compatibility:** how are missing, extra, or re-typed fields/components handled?
- **Object invariants:** does a constructor or callback validate the data?
- **Graph identity:** are reference relationships, aliasing, and cycles preserved as designed?
- **Security:** does the runtime permit deserializing the classes appearing in the stream?

For records and enums, Java specifies special rules across several of the steps above.

## 3. Record: A Data Type with Explicit Components

### 3.1. How Does a Record Differ from a POJO Class?

Records were standardized in Java 16 (JEP 395). A record declares **record components**, and the compiler generates corresponding `private final` fields, accessors, the canonical constructor, and `equals`, `hashCode`, and `toString` methods following the record contract.

Example:

```java
public record Money(String currency, long minorUnits) {
}
```

Records suit structured data and act value-like at the API model level. However, a record **is not automatically Serializable**. If Java Object Serialization is needed, declare it explicitly:

```java
import java.io.Serializable;

public record Money(String currency, long minorUnits)
        implements Serializable {
}
```

A record cannot extend an arbitrary superclass; it extends `java.lang.Record` directly. Records can implement interfaces such as `Serializable`. Being final prevents subclassing, yet does not imply that every object referenced by a component is immutable.

### 3.2. Records Are Shallowly Immutable at the Component Reference Level

Example:

```java
import java.io.Serializable;
import java.util.List;

public record Basket(List<String> items)
        implements Serializable {
}
```

A record does not allow reassigning the `items` reference after construction, yet the referenced list itself may remain mutable. If a caller passes an `ArrayList` and mutates it, the Basket's contents change accordingly.

To protect invariants and avoid retaining a mutable reference from the caller:

```java
import java.io.Serializable;
import java.util.List;
import java.util.Objects;

public record Basket(List<String> items)
        implements Serializable {

    public Basket {
        Objects.requireNonNull(items, "items");
        items = List.copyOf(items);
    }
}
```

`List.copyOf` ensures an unmodifiable list with appropriate elements, though it does not deep-copy mutable objects inside. During deserialization, the canonical constructor also participates in re-establishing invariants; thus, validation logic in the constructor directly impacts legacy data.

### 3.3. `Serializable` Does Not Verify Every Component's Serializability at Compile Time

Example:

```java
import java.io.Serializable;

final class NotSerializableHandle {
    final long address;

    NotSerializableHandle(long address) {
        this.address = address;
    }
}

public record NativeBinding(NotSerializableHandle handle)
        implements Serializable {
}
```

The record declaration compiles, yet `ObjectOutputStream.writeObject` will fail if attempting to write a component containing a non-serializable object. For native handles, sockets, connections, or live resources, the solution is usually not forcing every object to be Serializable, but moving to a **DTO holding only stable data**, while recreating or managing resources outside the stream.

## 4. Record-Specific Java Serialization Rules

### 4.1. Record Components Are the Source of Serialized Data

Java Object Serialization handles record classes using a mechanism dedicated to record components. Instead of assuming arbitrary hidden fields can be serialized and restored by allocating an instance without invoking a constructor as with ordinary Serializable classes, the runtime uses record component descriptors and their corresponding values.

A simple record:

```java
import java.io.Serializable;
import java.util.Objects;

public record CustomerSnapshot(
        String customerId,
        int loyaltyLevel,
        boolean active)
        implements Serializable {

    public CustomerSnapshot {
        Objects.requireNonNull(customerId, "customerId");
        if (loyaltyLevel < 0) {
            throw new IllegalArgumentException(
                "loyaltyLevel must be non-negative"
            );
        }
    }
}
```

During standard deserialization, stream data is mapped to the runtime record's components and passed to the **canonical constructor**. Therefore, validation and normalization logic inside the constructor runs not only when the application calls `new CustomerSnapshot(...)`, but also when restoring from a stream.

This is a major difference from ordinary Serializable classes, where deserialization does not invoke the Serializable class's own constructor as in normal object instantiation.

### 4.2. The Canonical Constructor Must Accept Valid Data from Earlier Versions

Suppose the first version is:

```java
public record CustomerSnapshot(String customerId)
        implements java.io.Serializable {
}
```

A newer version adds a component:

```java
public record CustomerSnapshot(
        String customerId,
        String region)
        implements java.io.Serializable {

    public CustomerSnapshot {
        if (region == null) {
            region = "UNSPECIFIED";
        }
    }
}
```

When an older stream omits the `region` component, deserialization supplies the type's default value (`null` for references, `0` for numeric types, `false` for `boolean`) for the missing component. The canonical constructor is where that default can be normalized into a valid representation.

However, a default is not always meaningful. If a newly added field must be non-null/present, reading legacy data may fail when the constructor checks invariants.

Example prone to breaking compatibility:

```java
public record CustomerSnapshot(
        String customerId,
        String region)
        implements java.io.Serializable {

    public CustomerSnapshot {
        java.util.Objects.requireNonNull(
            region, "region"
        );
    }
}
```

For a stream without `region`, the constructor receives `null` and rejects the data. If the system must read legacy data, design an appropriate default/migration or use a format with explicit schema evolution.

### 4.3. Adding, Removing, and Renaming Components

These are the cases to evaluate when a record serves as a persisted object:

| Change | Typical Impact on Java Serialization | Required Action |
|---|---|---|
| Adding a component | Old stream lacks the value; runtime supplies a default on restore | Set valid defaults and check the canonical constructor |
| Removing a component | Corresponding data from old stream has no receiving component | Verify whether important business data is lost |
| Renaming a component | Equivalent to removing the old name and adding a new name in data mapping | Write a migration/adapter if values must be preserved |
| Changing a component type | May fail to match stream field/type descriptor | Test deserialization; prefer explicit schema migration |
| Changing validation | Previously accepted streams may now be rejected | Normalize data or add a backward-compatible policy |
| Changing nested objects | Component holds another object with its own serialization rules | Test the entire object graph and related classes |

For long-lived data, do not treat record component names as arbitrary implementation details. In many other serializers, component names are also used as JSON property or schema field names.

### 4.4. Records Do Not Use Ordinary-Class Serialization Hooks the Same Way

For an ordinary Serializable class, developers can define special methods such as:

- `private void writeObject(ObjectOutputStream out)`
- `private void readObject(ObjectInputStream in)`
- `private void readObjectNoData()`

Records have their own serialization mechanism. Hooks that customize normal field reading/writing do not customize record serialization the way they do for regular classes. Similarly, do not expect `serialPersistentFields` to redefine which record components are written to the stream.

Example **not to use** as a strategy for omitting a record component:

```java
import java.io.IOException;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public record SessionRecord(
        String userId,
        String temporaryToken)
        implements Serializable {

    // Do not treat this standard Serializable-class hook
    // as a way to omit temporaryToken from record serialization.
    private void writeObject(ObjectOutputStream out)
            throws IOException {
        out.defaultWriteObject();
    }
}
```

To avoid persisting the token, design a DTO record containing only `userId` or use a separate serializer/schema mapping. Secret values should not appear in persisted DTOs merely because a domain object carries that field.

`writeReplace` and `readResolve` have specific rules and can support replacement/proxy patterns in Java Object Serialization; if you need them, verify the target runtime's contract and test explicitly instead of assuming every ordinary-class callback works identically.

### 4.5. A Record's `serialVersionUID` Has Special Rules

For an ordinary Serializable class, `serialVersionUID` is a key part of matching serialized class versions. For records, Java Object Serialization has a **special rule**: a record's default serialVersionUID is `0L` if not explicitly declared, and the serialVersionUID matching requirement during deserialization is relaxed for record classes.

A UID can still be declared on a record:

```java
import java.io.Serializable;

public record InvoiceLine(
        String sku,
        long quantity)
        implements Serializable {

    private static final long serialVersionUID = 1L;
}
```

However, **keeping the same UID does not solve all component changes**, and relaxing UID checks does not guarantee a modified record restores data properly. Constructor validation, component names/types, and nested graphs must still be tested.

For persisted data, establish an explicit schema evolution plan rather than treating serialVersionUID as a “compatibility switch.”

### 4.6. Records Have No Default Zero-Argument Constructor for Deserialization

Because the canonical constructor accepts the components and is invoked to reconstruct the record, Java Object Serialization of a record does not require a public no-arg constructor like many classic JavaBean serializers or ORMs.

However, **JSON mappers, JPA providers, and third-party frameworks may impose different constructor requirements**. Compatibility with `ObjectInputStream` does not mean every framework can read/write records across all versions.

### 4.7. Aliasing and Cyclic Object Graphs

For an ordinary object graph, Java serialization uses handles/references to preserve reference identity. Because records must be instantiated via their canonical constructor, reference cycles involving a record and an object under construction face notable limitations.

For example, a list might reference the record containing it:

```java
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

record ContainerRecord(List<Object> elements)
        implements Serializable {
}

List<Object> list = new ArrayList<>();
ContainerRecord container = new ContainerRecord(list);
list.add(container);
```

This object graph contains a cycle: record -> list -> record. Do not assume serialization/deserialization preserves all cycles involving records the way mutable regular classes do. When a system needs to persist cyclic graphs, design explicit IDs/references or use an appropriate format/model and test thoroughly.

An acyclic tree-structured DTO is usually easier to test, easier to version, and less coupled to JVM internals.

## 5. End-to-End Example: Serializing and Deserializing a Record

### 5.1. Declaring the Enum and Record

```java
import java.io.Serializable;
import java.util.Objects;

enum PaymentState {
    CREATED,
    APPROVED,
    REJECTED
}

record PaymentSnapshot(
        String paymentId,
        long amountMinor,
        PaymentState state)
        implements Serializable {

    private static final long serialVersionUID = 1L;

    public PaymentSnapshot {
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(state, "state");

        if (amountMinor < 0) {
            throw new IllegalArgumentException(
                "amountMinor must not be negative"
            );
        }
    }
}
```

`PaymentState` does not need to explicitly declare `implements Serializable` because enums have a serialization mechanism defined by Java. The `PaymentSnapshot` record still must implement `Serializable` to be written via `ObjectOutputStream`.

### 5.2. Writing and Reading an Internal Byte Stream

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public final class RecordSerializationDemo {
    public static void main(String[] args) throws Exception {
        PaymentSnapshot before = new PaymentSnapshot(
            "PAY-2026-001",
            150_000,
            PaymentState.APPROVED
        );

        byte[] bytes;

        try (ByteArrayOutputStream buffer =
                 new ByteArrayOutputStream();
             ObjectOutputStream output =
                 new ObjectOutputStream(buffer)) {

            output.writeObject(before);
            output.flush();
            bytes = buffer.toByteArray();
        }

        PaymentSnapshot after;

        // Only reading data just created in the same program,
        // not a byte stream from an untrusted source.
        try (ObjectInputStream input =
                 new ObjectInputStream(
                     new ByteArrayInputStream(bytes))) {

            Object value = input.readObject();

            if (!(value instanceof PaymentSnapshot snapshot)) {
                throw new IllegalStateException(
                    "Unexpected serialized type"
                );
            }

            after = snapshot;
        }

        System.out.println(before);
        System.out.println(after);
        System.out.println("Equal: " + before.equals(after));
    }
}
```

This example illustrates Object Serialization for records and enums. In production products, guard against untrusted data and do not adopt native Java streams as a default API wire format solely for brevity.

### 5.3. Explaining Reconstruction

When reading the object:

1. The runtime resolves the `PaymentSnapshot` class from the stream descriptor and available classes.
2. Record component values are decoded.
3. The record's canonical constructor is called with those values.
4. Validation inside the constructor may accept or reject the data.
5. The `state` component is restored according to enum-specific rules.

The third point is crucial for invariants: a record object is not treated as a “bag of fields” restored while bypassing the constructor. If the canonical constructor requires a non-null `paymentId`, a corrupted stream or an old stream lacking data can cause deserialization to fail.

## 6. Enums: Java Serialization Differs from Ordinary Objects

### 6.1. Enum Constants Are Runtime-Managed Singletons

Example:

```java
public enum FulfillmentStatus {
    CREATED,
    PICKED,
    DISPATCHED,
    DELIVERED
}
```

Each constant is an instance created and managed by the enum class mechanism. When Java Object Serialization writes an enum, it does not serialize all instance fields as it would for an ordinary object. It writes **the enum constant name** along with the type information required to identify the constant on read.

At deserialization time, the value is restored using the constant from the current enum class. This preserves enum identity: identical constants can be compared with `==`.

### 6.2. Enums Are Serialized by Name, Not Ordinal

Example:

```java
enum Status {
    NEW,
    RUNNING,
    DONE
}
```

If an object stream writes `Status.RUNNING`, the special enum representation relies on the constant name `RUNNING`, **not `ordinal() == 1`**.

If a later version inserts a new constant:

```java
enum Status {
    NEW,
    QUEUED,
    RUNNING,
    DONE
}
```

`RUNNING.ordinal()` changes from 1 to 2, yet Java Object Serialization can still look up `RUNNING` by name in the updated enum.

**Do not generalize this to databases or JSON.** An ordinal-based JPA mapping or a JSON serializer configured to emit numbers can break when constant ordering changes.

### 6.3. Renaming or Removing an Enum Constant

Suppose an old stream contains `Status.RUNNING` while the new runtime enum only has:

```java
enum Status {
    NEW,
    IN_PROGRESS,
    DONE
}
```

Renaming causes `RUNNING` to no longer be recognized by the runtime. Java Object Deserialization does not automatically know that `IN_PROGRESS` is a replacement name; reading old values can fail with an error for a nonexistent constant.

If historical data must remain readable, use one of these strategies:

- Retain the old constant during a compatibility period.
- Migrate stored data to a format with stable codes before renaming.
- Use a DTO class or serialization proxy with explicit version mapping.
- Run an offline data migration with verification and rollback.

Do not simply rename an enum constant and expect Object Serialization to translate aliases automatically.

### 6.4. Adding an Enum Constant

Adding a new constant generally does not stop a **newer runtime** from reading old streams containing still-existing constants. However, if a new producer starts sending the new constant to an old consumer, the old consumer lacks that name and may fail to deserialize it.

Example:

```text
Producer v1: NEW, RUNNING, DONE
Consumer v1: NEW, RUNNING, DONE

Producer v2: NEW, QUEUED, RUNNING, DONE
Consumer v1: NEW, RUNNING, DONE
                         ^
                does not recognize QUEUED
```

This is a forward compatibility issue: an old consumer cannot understand a new value merely because the new enum is binary-compatible with previously compiled code. For protocols where producers and consumers deploy asynchronously, use an open representation with `UNKNOWN` or retain raw values depending on the framework, rather than passing native enum serialization directly if future values must be handled.

### 6.5. Extra Fields on Enums Are Not Serialized Like Regular Fields

An enum may hold metadata:

```java
public enum ShippingMethod {
    STANDARD("STD", 3),
    EXPRESS("EXP", 1);

    private final String code;
    private final int estimatedDays;

    ShippingMethod(String code, int estimatedDays) {
        this.code = code;
        this.estimatedDays = estimatedDays;
    }

    public String code() {
        return code;
    }

    public int estimatedDays() {
        return estimatedDays;
    }
}
```

In Java Object Serialization, the stream represents the enum constant itself; it **does not store an independent copy of `code` and `estimatedDays`** as an ordinary object would. When read in a new runtime, metadata comes from the active enum definition.

If a new release changes `EXPRESS` from 1 day to 2 days, old streams containing `EXPRESS` read in the new runtime will observe the current constant's metadata. If you need a point-in-time snapshot of values at transaction time, serialize **snapshot values** in a separate record/DTO rather than expecting enum fields to preserve historical data.

### 6.6. Enums Have Very Strict Limits on Custom Serialization

Serialization methods such as `writeObject`, `readObject`, `readResolve`, `writeReplace`, and `serialVersionUID` declarations are not used to alter the serialized form of an enum the way they are for ordinary classes. Java specifies a dedicated serialization mechanism for enums, with a fixed serialVersionUID for enum types.

If you need control over wire representation, wrap the enum in a DTO with stable codes or use an external serializer with an explicit contract. Do not try a `readResolve` trick inside an enum to rename legacy constants in Java Object Serialization.

## 7. Comparing Records, Enums, and Ordinary Serializable Classes

| Aspect | Ordinary Serializable Class | Record Implementing Serializable | Enum |
|---|---|---|---|
| Must declare Serializable? | Yes | Yes | Enum mechanism already handles it |
| Primary data unit | Serializable instance fields | Record components | Enum constant name |
| Constructor on deserialize | Does not call the Serializable class's own constructor as usual | Calls the canonical constructor | Returns the existing enum constant |
| `serialVersionUID` | Checked under standard version rules | Special rules and relaxed matching requirement | Fixed enum rules |
| Custom `writeObject/readObject` | Can apply when signatures match | Not a mechanism for customizing record components | Not used to alter enum serialization |
| Adding data | Subject to field evolution rules | Missing component in stream receives default then passes through constructor | Adding a new constant affects older consumers receiving that value |
| Renaming | Field rename requires migration | Component rename requires migration | Constant rename has no automatic alias |
| Object graph | Standard handle/reference and cycle support | Watch out for cycle limitations involving constructor | Constant identity preserved by enum |
| Long-lived open wire format | Needs strict governance, generally discouraged | Needs strict governance, generally discouraged | Needs strict governance, generally discouraged |

This table reflects **Java Object Serialization rules** and does not directly describe Jackson, JAXB, Hibernate, or Protobuf behavior.

## 8. Compatibility When Converting a Regular Class to a Record

### 8.1. Changing Syntax Does Not Preserve the Serialized Form

Suppose the old class is:

```java
import java.io.Serializable;

public final class UserProfile implements Serializable {
    private static final long serialVersionUID = 7L;

    private String id;
    private String displayName;

    public UserProfile(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

A developer may want to replace it with:

```java
import java.io.Serializable;

public record UserProfile(
        String id,
        String displayName)
        implements Serializable {
}
```

At the API level, call sites must migrate from `getId()` to `id()`. At the bytecode level, a record class has a different structure; pre-compiled code referencing removed getters, constructors, or methods may fail to link. At the Object Serialization level, the runtime also applies record rules distinct from ordinary classes.

Even when the class name and field names appear identical, **you cannot conclude that old streams are guaranteed compatible with the new record**. Use a corpus of legacy data and test reading it with the new class in the target environment.

### 8.2. Constructor Contracts Can Render Legacy Data Invalid

An ordinary class can be restored without executing its own constructor. A record's canonical constructor is invoked during restoration.

If the new record enforces an invariant:

```java
public record UserProfile(
        String id,
        String displayName)
        implements java.io.Serializable {

    public UserProfile {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException(
                "displayName must not be blank"
            );
        }
    }
}
```

then legacy data with null or blank `displayName` will be rejected. That may be desirable business behavior, yet it must be handled in the migration plan—for example, by normalizing before switching formats or mapping through an intermediate DTO with an explicit policy.

### 8.3. Source, Binary, Data, and Behavioral Compatibility

| Level | Question When Converting a Class to a Record |
|---|---|
| Source compatibility | Does code calling getters/setters, subclasses, or no-arg constructors still compile? |
| Binary compatibility | Do old artifacts link against the new methods, constructors, and class? |
| Serialized-data compatibility | Can old byte streams be restored into the new type with accurate values? |
| Behavioral compatibility | Have invariants, equality, normalization, or mutability changed? |
| Framework compatibility | Do JSON mappers, ORMs, DI, and proxy/bytecode libraries support records on the target JDK? |

Refactoring a POJO into a record can improve model clarity while still representing a major contract change for un-upgraded consumers.

### 8.4. Safe Conversion Strategy

If the system has persisted millions of object streams using the old class, a low-risk approach is:

1. Retain the ability to read legacy streams via a compatible application version or converter.
2. Read the data in a trusted environment, applying validation and migration rules.
3. Re-export as a schema-based DTO such as JSON/Avro/Protobuf or a stable versioned format.
4. Verify readback, checksums/record counts, and business values.
5. Transition the new application to the record domain model without necessarily persisting the record directly via native serialization.
6. Keep rollback capability and a plan for handling unconverted artifacts.

If only a small number of byte streams are stored locally and all consumers deploy synchronously, you can test compatibility directly with integration tests. Still rely on concrete evidence rather than assuming identical class names suffice.

## 9. JSON: Enum Representation Can Differ Entirely from Java Serialization

### 9.1. Ways Enums Are Represented in JSON

Given the same enum:

```java
enum PaymentStatus {
    PENDING,
    SETTLED,
    REVERSED
}
```

One JSON serializer might write it as a string:

```json
{
  "status": "SETTLED"
}
```

Another serializer might be configured to write the ordinal:

```json
{
  "status": 1
}
```

Or the API uses a stable business code:

```json
{
  "status": "S"
}
```

These three forms carry different compatibility rules. There is no rule stating “every JSON library serializes enums like Java Object Serialization.” Inspect the exact configuration: annotations, converters, serializer modules, and library versions.

### 9.2. JSON Name Representation Carries Constant-Renaming Risk

If JSON uses enum names, adding a new constant can cause older consumers to reject the new value. Renaming a constant can render old data unparseable. If JSON uses ordinals, reordering constants is even more dangerous because it can **silently change meanings**.

Prefer stable wire codes when exposing a public API:

```java
public enum PaymentStatus {
    PENDING("P"),
    SETTLED("S"),
    REVERSED("R");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Then use an appropriate serializer/converter to map `code` to the JSON field. Do not assume that merely defining a `code()` method causes the JSON mapper to use it.

### 9.3. Handling Unknown Enum Values

With asynchronously deployed producers and consumers, define a policy when encountering:

```json
{
  "status": "UNDER_REVIEW"
}
```

An older consumer may:

- Reject and return a structured error.
- Map to `UNKNOWN` if the serializer supports it and policy permits.
- Keep the raw string in a DTO for newer logic to process.
- Ignore the field when it does not affect business semantics.

Do not default to `PENDING` as a fallback for every new value if doing so could cause transactions to be processed incorrectly. For payments, authorization, compliance, or order state, failing safely and logging are usually more important than “parsing successfully at all costs.”

### 9.4. Records in JSON Require Mapper Support for Constructors/Components

Record example:

```java
public record ApiUser(String id, String displayName) {
}
```

A modern mapper can recognize record components and call the canonical constructor to instantiate the object. However, older library versions might:

- Look only for JavaBean getters/setters.
- Require a no-arg constructor.
- Fail to recognize record component names.
- Handle unknown properties differently by default.
- Apply annotations or naming strategies differently across versions.

When upgrading the JDK and frameworks together, test JSON reading and writing with the exact mapper and configuration, rather than relying on `record` compiling.

### 9.5. Null, Missing, and Default Values in JSON

Distinguish:

```json
{}
```

and:

```json
{"displayName": null}
```

and:

```json
{"displayName": ""}
```

How a mapper passes missing or null values to the canonical constructor can depend on configuration and component types. For primitive `int` or `boolean`, a parser may supply defaults, reject missing values, or apply specific coercion rules.

Define an explicit JSON contract: required fields, nullability, valid defaults, and whether unknown fields are ignored or rejected. Then write tests for each.

## 10. JPA and Databases: Enum Ordinals Pose a Distinct Risk

### 10.1. `EnumType.ORDINAL`

A JPA mapping might use:

```java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
```

In that case, the provider typically stores the enum's declaration position as an integer. For example:

```java
enum OrderStatus {
    CREATED,   // 0
    PAID,      // 1
    SHIPPED    // 2
}
```

If a later version inserts `CANCELLED` in the middle:

```java
enum OrderStatus {
    CREATED,   // 0
    CANCELLED, // 1
    PAID,      // 2
    SHIPPED    // 3
}
```

Existing database rows storing `1` previously meant `PAID`, and now risk being read as `CANCELLED`. This is silent data corruption and more severe than an immediate exception.

Note: the annotation snippet depends on the project's JPA API; package names may differ between Jakarta Persistence and Java EE versions. The example only illustrates mapping differences, not a complete entity class.

### 10.2. `EnumType.STRING`

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

String storage avoids ordinal fragility yet still couples data to **the constant name**. Renaming `PAID` to `SETTLED` can break existing rows or legacy queries.

If values are persisted long-term and API names need freedom to evolve, use a converter mapping to stable business codes:

```text
CREATED  -> "C"
PAID     -> "P"
SHIPPED  -> "S"
```

A converter can use JPA/Jakarta Persistence's `AttributeConverter`, with an explicit policy for unknown codes. Test schema migrations and backfills before modifying application enums.

### 10.3. Records and ORMs

Many ORMs require entities to support lifecycle callbacks, identity, constructors, and proxy generation. Records are final and their component references cannot be reassigned, so do not assume a record can directly replace every mutable JPA entity.

Instead, records work well as **projections, query results, or DTOs** where the framework supports them, while entities keep an ORM-compatible structure. Base this decision on the framework version and lifecycle/dirty-checking requirements.

## 11. Avro, Protocol Buffers, and Schema Evolution

### 11.1. Do Not Equate Java Enums with Protocol Enums

A Java enum has constant names, whereas a Protocol Buffers enum has **numeric values** in its schema. Those numbers belong to the wire contract and must be managed independently of the generated Java enum's `ordinal()`.

Conceptual example:

```proto
enum PaymentStatus {
  PAYMENT_STATUS_UNSPECIFIED = 0;
  PAYMENT_STATUS_PENDING = 1;
  PAYMENT_STATUS_SETTLED = 2;
}
```

When adding a value, assign a **new stable number**. Never reuse field numbers or enum numeric values that carried a different meaning in historical data; use schema `reserved` mechanisms when retiring values.

Protobuf libraries apply their own rules for unknown enum values depending on language, schema syntax, and runtime version. Do not assume they will throw an error or map to `null` like Java Object Serialization.

### 11.2. Avro Uses Writer and Reader Schemas

In Avro, readability depends on resolving the record's writer schema against the consumer's reader schema. Record field defaults and enum symbols/defaults follow rules defined by Avro, not the canonical constructor rules of Java records.

When publishing a new Avro schema, run schema compatibility checks and test reading with both old and new reader schemas. Converting a Java class to a `record` neither automatically alters nor guarantees compatibility of the Avro wire schema.

### 11.3. Separating Domain Models from Wire Schemas

A sustainable strategy:

```text
Domain model (record/enum)
          |
          v
Explicit mapping / validation
          |
          v
Versioned wire DTO / schema
          |
          v
JSON / Avro / Protobuf / database
```

Separating these two layers allows you to:

- Refactor record component names without immediately breaking the public API.
- Use stable field names/codes in the wire format.
- Handle unknown enum values.
- Add defaults in the schema deliberately.
- Use records in the domain layer while keeping ORM-compatible entity models.
- Migrate historical data with versioning and rollback support.

## 12. Specific Changes to Check When Upgrading the JDK

### 12.1. Records Do Not Exist on JDK 8 as a Language Feature

Records became a standard language feature in Java 16. If a library starts shipping bytecode containing record classes, older runtimes such as JDK 8 or 11 cannot understand and execute that binary simply because its fields share familiar names.

When building a library used by multiple services, determine the minimum consumer JDK. You cannot compile source using `record` syntax with `javac --release 8`. If Java 8 must be supported, use a different source model or publish separate artifacts matching the runtime support matrix.

### 12.2. Java Serialization Stream Compatibility Is Not Java Source Compatibility

A new record running smoothly on JDK 21 may fail to deserialize old class data or be unreadable by a JDK 8 service. Multiple layers are involved:

- Source features and `javac --release`.
- Class-file version.
- Classpath/module visibility.
- Java serialization descriptors and object graphs.
- Invariants in the canonical constructor.
- Serialization filters and security policies.
- Data formats in caches, files, or message brokers.

A passing compile test verifies only the first layer; it does not prove stored data is compatible.

### 12.3. Java Object Serialization Still Exists, but Requires Security Consideration

A new JDK does not necessarily remove Object Serialization immediately. However, it carries significant risk when reading untrusted streams. Java added deserialization filtering mechanisms in modern JDKs, such as `ObjectInputFilter`, to restrict accepted object graphs and classes.

If reading streams from partially trusted sources is unavoidable, configure a class allowlist along with depth, reference, array size, and byte limits, and audit every library on the classpath. Filters are not a substitute for source authentication and safe protocol design.

For new public network APIs, prefer schema-controlled data formats with explicit validation rather than letting senders trigger instantiation of arbitrary object graphs by class name.

## 13. Data Risks When Enum, Record, and Deployment Versions Are Out of Sync

### 13.1. New Producer, Old Consumer

A new service defines:

```java
enum OrderState {
    CREATED,
    PAID,
    SHIPPED,
    RETURNED
}
```

The old consumer has only the first three constants. If it receives new data containing `RETURNED`:

- Java Object Serialization of the enum may fail to restore because the constant name does not exist.
- A JSON parser may reject it or apply the serializer's unknown-value policy.
- A database ORDINAL column risks mis-mapping depending on position.
- Protobuf/Avro apply their own unknown/default handling.
- A previously compiled exhaustive switch expression may hit a fallback error if runtime code receives the new enum constant in the same JVM.

Each format must be tested individually. There is no universal “safe enum constant addition rule” applicable everywhere.

### 13.2. New Consumer, Old Data

A record with a new component may receive a default value when reading an old stream; its constructor may reject that default. A JSON mapper may disallow missing properties; Avro may apply a schema default; Protobuf distinguishes field presence by schema and syntax.

Generate **golden test data** from actual deployed versions instead of fabricating synthetic data with new code and assuming it represents legacy data.

### 13.3. Data Persists After Rollback

During a canary rollout, a new producer may write a new enum constant or record field into the database, cache, or message queue. When rolling back consumers to an older version, the old version may fail to read the newly written data.

Therefore, the rollback plan must answer:

1. Can the old version read data written by the new version?
2. If not, can emitting the new values be deferred until all consumers are upgraded?
3. Is an expand-then-contract schema step needed?
4. Can data be safely back-migrated?
5. Does message replay or backup restoration require a migration tool?

Rolling back the binary does not guarantee rolling back data state.

## 14. Designing Stable Codes for Enums

### 14.1. Do Not Use `ordinal()` as a Long-Term Code

If a protocol or database needs stable codes, attach a code independent of declaration order:

```java
import java.util.Arrays;
import java.util.Optional;

public enum OrderState {
    CREATED("C"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    OrderState(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static Optional<OrderState> fromCode(String raw) {
        return Arrays.stream(values())
            .filter(value -> value.code.equals(raw))
            .findFirst();
    }
}
```

In a new version, enum constants can be inserted in any position without changing `C`/`P`/`S`. However, any new code must be published, and older consumers still need a policy for unknown codes.

### 14.2. Preserving the Raw Value When Forward Compatibility Is Needed

A DTO can retain the raw value:

```java
import java.util.Optional;

public record ParsedOrderState(
        String rawCode,
        Optional<OrderState> knownState) {

    public static ParsedOrderState parse(String raw) {
        return new ParsedOrderState(
            raw,
            OrderState.fromCode(raw)
        );
    }
}
```

If `"R"` arrives when older code only knows `C`/`P`/`S`, `knownState` is `Optional.empty()` while `rawCode` is still preserved for logging, pass-through, or replay.

Note: this is a **domain/parser DTO**, not an automatic wire schema. Depending on the serializer, `Optional` may need a dedicated converter; do not emit a record containing `Optional` directly to JSON or Java Object Serialization without checking support. For a persisted wire DTO, simply store `rawCode` and parse into the domain model at the application boundary.

### 14.3. Invariants and Unknown-Value Policies

If the logic involves money or authorization, receiving an unknown raw code should typically reject the sensitive action while still recording the raw value and metric for follow-up. If the value is purely for display labels, an “Unknown” fallback may be acceptable.

Never collapse unknown enum values into a concrete state such as `PAID` or `APPROVED` just to prevent errors. Any fallback must accurately reflect business meaning.

## 15. Managing Record Schema Versions

### 15.1. Adding a Field Is Not Automatically Safe

Suppose record API v1 is:

```java
record AccountEvent(
        String accountId,
        String action)
        implements java.io.Serializable {
}
```

V2 adds:

```java
record AccountEvent(
        String accountId,
        String action,
        long occurredAtEpochMillis)
        implements java.io.Serializable {
}
```

When receiving an old stream missing the new component, the primitive default may be `0L`. Yet in business logic, `1970-01-01T00:00:00Z` may not be a valid timestamp.

Solutions:

- Specify the meaning of missing values and conditions for accepting them.
- Apply constructor normalization if a valid default exists.
- If an accurate value cannot be inferred, use schema versioning and a migration tool.
- For long-lived events, represent optionality explicitly in the wire schema rather than relying on primitive defaults from Java Object Serialization.

### 15.2. Renaming a Component Is Not Merely Changing a Display Label

A record component name affects the source accessor (`accountId()`) and can affect field mapping in many serializers. If only a UI display label needs to change, do not rename the component used in a persistent schema.

For JSON, annotations or adapters can preserve the old wire property name while the domain component is renamed. For Object Serialization, test explicitly or migrate legacy data through an intermediate model; there is no generic mechanism guaranteeing a safe rename without altering the stream contract.

### 15.3. Validation Is Part of New-Version Data Semantics

A stricter invariant can render legacy data unreadable. For example:

```java
record ProductId(String value)
        implements java.io.Serializable {

    public ProductId {
        if (value == null || !value.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException(
                "Invalid ProductId"
            );
        }
    }
}
```

If old streams contain codes with lowercase characters or spaces, the new record's canonical constructor will reject them. Before rollout, determine how many existing records fail the new invariant and address them via migration or controlled backward-compatible normalization.

## 16. Testing Compatibility Using a Version Matrix

### 16.1. Producer and Consumer Matrix

| Producer | Consumer | Goal |
|---|---|---|
| V1 | V1 | Baseline for legacy data |
| V1 | V2 | Does V2 read legacy data and apply defaults properly? |
| V2 | V2 | Normal behavior of the new version |
| V2 | V1 | Does it support rolling deployments or rollback? |
| Malformed/untrusted data | Hardened consumer | Do filters/validation reject it safely? |

Not every combination must be supported in production, yet each decision must appear in the compatibility contract. For instance, if V2 writes a new enum constant that V1 does not support, the system may need to deploy consumers first and enable the producer afterward.

### 16.2. Golden Streams Must Be Generated by Real Versions

To test Java Object Serialization of records/enums:

1. Build an actual V1 artifact.
2. Run V1 code to generate representative byte streams.
3. Save fixtures with version, SHA-256, and business object description.
4. Build the V2 artifact separately.
5. Read V1 streams with V2 and verify values, invariants, and exception policies.
6. If rollback is needed, test V1 reading V2 streams.
7. Test new enum constants, missing components, renames, type changes, and nested objects.
8. Execute on the target JDK with the active serialization filter configuration.

Do not use V2 classes to generate a “simulated V1” stream merely by dropping JSON fields if you need to test **Java binary serialization**. Stream descriptors and object instantiation mechanisms can differ.

### 16.3. Testing Enum Renames

Test three conditions:

```text
V1 enum:
  NEW, RUNNING, DONE

V2 enum:
  NEW, IN_PROGRESS, DONE
```

- V1 writes `RUNNING`, V2 attempts to read: is there a policy for handling the old name?
- V2 writes `IN_PROGRESS`, V1 attempts to read: must rollback be supported?
- Do non-Java formats use `"RUNNING"` or a stable code `"R"`?

If wire format preservation is required, test the official mapping. Simply changing the constant name in Java is insufficient.

### 16.4. Testing Constructor Normalization

Example with a record adding the `region` component:

- Old stream missing `region`.
- New stream with `region = null`.
- New stream with `region = ""`.
- New stream with `region = "VN"`.
- New stream with an incompatible field type if malformed schema occurs.
- Large data streams or deeply nested graphs to check resource limits.

Expected outcomes must be stated clearly: normalize, reject, fall back, or migrate. Do not merely assert “no exception thrown” if the object is restored with semantically wrong data.

## 17. Checking Data Formats Outside Object Serialization

For JSON:

- [ ] V1/V2 JSON snapshots have the promised property names.
- [ ] Are enums serialized by string name, stable code, or number?
- [ ] Behavior for missing/null/unknown fields is explicitly defined.
- [ ] Mapper supports records on the current JDK/framework version.
- [ ] Unknown enum values are not mapped to hazardous states.

For databases:

- [ ] Enum mapping does not rely on ordinal if the table must evolve.
- [ ] Constant names or stable codes are pinned as the database contract.
- [ ] Schema migrations and backfills are tested.
- [ ] Rollback does not cause newly written data to be misinterpreted.
- [ ] ORM supports records in the chosen entity/projection/DTO role.

For Avro/Protobuf:

- [ ] Schema changes are checked under the appropriate compatibility mode.
- [ ] Field numbers, enum numbers, symbols, and defaults are governed.
- [ ] Unknown values are handled properly by each runtime.
- [ ] Producer/consumer rolling deployments and replay are tested.

## 18. Security When Reading Serialized Data

### 18.1. Do Not Deserialize Native Java Objects from Untrusted Sources by Default

Java Object Serialization can cause the runtime to instantiate and invoke classes on the classpath specified by the input stream. Certain classes contain callbacks, side effects, or complex execution gadgets. Accepting arbitrary bytes from the network and calling `ObjectInputStream.readObject()` creates a significant attack surface.

Mitigations:

- Prefer formats with schemas and field limits for public APIs.
- If Object Serialization is mandatory, restrict trusted sources.
- Apply `ObjectInputFilter` with a class allowlist and resource limits.
- Cap input bytes, graph depth, reference counts, and array lengths.
- Do not rely solely on type checks after `readObject()`, because most deserialization work has already executed.
- Update libraries and audit the object types appearing in streams.
- Isolate processes/containers when low-trust legacy data must still undergo format conversion.

### 18.2. Post-Read Type Checking Is Necessary but Insufficient

```java
Object value = input.readObject();

if (!(value instanceof PaymentSnapshot snapshot)) {
    throw new java.io.InvalidObjectException(
        "Unexpected root type"
    );
}
```

Root type checking helps enforce the application contract, yet does not replace serialization filtering: nested objects may already have been constructed before the root type check executes.

### 18.3. ObjectInputFilter Needs a System-Specific Policy

You can configure a filter on the stream to reject disallowed classes or oversized object graphs. Directional example:

```java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

ObjectInputFilter filter =
    ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=1000;maxbytes=1048576;" +
        "com.example.protocol.*;java.base/*;!*"
    );

input.setObjectInputFilter(filter);
```

This is an **illustrative filter syntax sample**, not a copy-paste production policy. Class allowlists, module/package patterns, and limits must be tailored to the actual classes allowed in streams and the target JDK version. Too broad a policy leaves gaps; too narrow a policy blocks valid data.

## 19. Recommended Migration Process

### Phase 1: Inventory Where Data Is Written and Read

Search source code and configurations for:

- `ObjectOutputStream`, `ObjectInputStream`.
- `Serializable`, `Externalizable`, `serialVersionUID`.
- `readObject`, `writeObject`, `readResolve`, `writeReplace`.
- File/cache/message formats designated as Java object streams.
- Enums in JSON, JPA, Avro, Protobuf, and custom converters.
- New domain/DTO records introduced during the JDK upgrade.
- Services that may run mixed versions during rolling deployments.

Initial search commands:

```shell
rg -n "Object(Input|Output)Stream|implements Serializable" src
rg -n "serialVersionUID|readObject|writeObject|readResolve|writeReplace" src
rg -n "EnumType\\.(ORDINAL|STRING)|@Enumerated" src
rg -n "\\brecord\\b|\\benum\\b" src
```

Not every matched file needs migration. Identify actual data paths, retention lifecycles, and active protocols.

### Phase 2: Document Data Contracts and Owners

For each persisted message or file type, build an inventory:

| Data Type | Current Writer | Current Reader | Format | Lifecycle | Risk |
|---|---|---|---|---|---|
| Session cache | Service A V1 | Service A V1/V2 | Java Object Serialization | Short | Record/enum class evolution |
| Order event | Producer | Multiple consumers | JSON/Avro | Long | Unknown enum, schema compatibility |
| Payment status | ORM | ORM and reporting | DB string/ordinal | Very long | Rename/ordinal mismatch |
| Legacy archive | Old batch job | New converter | Java object stream | Years | Missing classes, new validation |
| HTTP response | API | Mobile/web clients | JSON | Across many releases | Stable codes and unknown behavior |

Define compatibility requirements for reading legacy data, reading new data, and rollback capability.

### Phase 3: Decide the Migration Model

Options:

- **Retain Object Serialization temporarily:** suitable if all parties sit within internal control and have version-matrix tests.
- **Move to schema-based DTOs:** suitable for long-term storage or independently deployed consumers.
- **Separate domain records from persisted DTOs:** suitable if the domain needs strict invariants while the wire needs backward compatibility.
- **Switch enums to stable codes:** suitable when constant names or ordering may change.
- **Migrate historical data offline:** suitable when old data cannot be read directly by the new model.

Do not replace every format at once if rollout risk is too high. You can roll out in phases with readers supporting both old and new formats before switching writers.

### Phase 4: Build Golden Fixtures

Generate real data from V1 and V2, saving fixtures alongside JDK, library, schema version, checksums, and expected values. Test on the target runtime:

1. Read V1 fixtures with the V2 reader.
2. Read V2 fixtures with the V1 reader if rollback must be supported.
3. Read records with missing components and constructor defaults.
4. Read renamed or removed enum constants.
5. Read new enum values not yet supported by older consumers.
6. Test nested data, collections, and nulls.
7. Verify malformed/untrusted streams are rejected safely.

### Phase 5: Release via Expand-Then-Contract

Example with a new status enum:

1. Update active readers to recognize or intentionally reject the new value.
2. Update metadata/schemas and API documentation.
3. Deploy readers before producers.
4. Enable producers to emit the new value once enough consumers are ready.
5. Monitor metrics for unknown/rejected values.
6. Remove legacy mappings only when no old data or supported old consumers remain.

For record schemas, add default handling before writers start emitting new components. If rollback is needed, verify new data does not break the old version; if impossible, explicitly document rollback limits.

### Phase 6: Monitor and Clean Up

After rollout, monitor:

- Deserialization errors by class/schema/constant.
- Unknown enum values and reject/fallback rates.
- Record constructor validation failures.
- Message backlogs/retries/dead-letter queues.
- Cache misses or cache corruption after upgrade.
- Replay and rollback mechanisms.
- Data migration counts and checksums.

Do not delete legacy readers or converters immediately just because production switched to the new writer. Backups, event replay, and offline consumers may require a longer transition period.

## 20. Common Real-World Errors

### Error A: `NotSerializableException` When Writing a Record

**Symptom:** `ObjectOutputStream.writeObject` fails even though the record declares `implements Serializable`.

**Possible cause:** a component references a non-serializable object, such as a native handle or service object.

**Resolution:** use a snapshot DTO containing only writable data rather than serializing live resources; or move to a schema DTO with an explicit converter.

### Error B: Record Deserialization Fails After Adding a Component

**Symptom:** old streams read fine in V1, yet V2 throws an error when the canonical constructor runs.

**Cause:** the new component receives a default (`null`/`0`/`false`) that the constructor rejects.

**Resolution:** provide a valid default, migrate data, or use a versioned DTO; do not merely change serialVersionUID.

### Error C: Old Enum Data Fails to Read After Renaming

**Symptom:** the stream still holds the old constant name while the runtime enum was renamed.

**Cause:** Java enum serialization relies on the constant name.

**Resolution:** keep compatibility aliases in the appropriate model/format, or convert historical data before dropping the old name.

### Error D: Database Reads the Wrong State After Inserting a Constant

**Symptom:** no exception is thrown, yet order status is interpreted incorrectly.

**Cause:** `EnumType.ORDINAL` combined with changed enum declaration order.

**Resolution:** restore the mapping, perform tested data migration, and switch to a stable code/string contract where appropriate.

### Error E: JSON Mapper Cannot Instantiate a Record

**Symptom:** error citing missing no-arg constructor, creator, or property name.

**Cause:** mapper version or configuration lacks record support.

**Resolution:** upgrade the mapper/module, add required annotation/constructor mappings, and run round-trip tests on the exact runtime version.

### Error F: New Producer Breaks Old Consumer with a New Enum Value

**Symptom:** deserialization failure, unknown symbol, or incorrect fallback.

**Cause:** the producer emitted a value absent from the old schema/model.

**Resolution:** reader-first rollout, stable codes, unknown-value policies, and version negotiation where needed.

### Error G: Rolling Back Code Without Being Able to Roll Back Data

**Symptom:** V1 is redeployed but cannot read events/caches written by V2.

**Cause:** data changed to a new schema or new constant.

**Resolution:** design backward write compatibility, keep dual readers, or convert data; do not rely solely on rolling back the JAR/container.

### Error H: Same Class Name, but Data Violates New Invariants

**Symptom:** object loads yet carries wrong business semantics, or the new constructor rejects it.

**Cause:** class evolved without an aligned data contract, or the record constructor tightened validation.

**Resolution:** test golden fixtures and assert business values rather than merely checking “`readObject()` throws no exception.”

## 21. Completion Checklist

### Record

- [ ] Records needing Java Object Serialization declare `implements Serializable`.
- [ ] Every component holds serializable data or has an appropriate DTO converter.
- [ ] Canonical constructor properly handles nulls/defaults from legacy data.
- [ ] Tested adding, removing, renaming, and re-typing components.
- [ ] Did not rely on `writeObject/readObject` to customize record component serialization.
- [ ] Accounted for records with mutable nested objects and cyclic object graphs.
- [ ] Consumers' minimum runtime/JDK supports published record classes.

### Enum

- [ ] Identified whether enum format uses name, ordinal, stable code, or schema numeric value.
- [ ] Avoided `ordinal()` as a persisted business code when the schema must evolve.
- [ ] Defined a policy for renamed or removed constants.
- [ ] Older consumers have a policy when producers emit a new constant.
- [ ] Did not expect enum fields/`writeObject` to serialize like ordinary objects.
- [ ] Verified whether current enum metadata satisfies historical snapshot requirements.

### Data and Protocols

- [ ] Inventoried all places reading/writing Java object streams, JSON, DBs, and Avro/Protobuf.
- [ ] Assigned schema/versioning and an owner for each persisted contract.
- [ ] Created golden fixtures from the legacy writer version.
- [ ] Tested version-skewed producer/consumer pairs and rollback.
- [ ] Implemented validation, unknown-value policies, and monitoring.
- [ ] Do not accept native Java object streams from untrusted sources without controls.
- [ ] Defined a retention/conversion roadmap for historical data.

## 22. Practice Exercises

### Exercise 1: Adding a Component to a Record

V1:

```java
record Invoice(String id, long cents)
        implements java.io.Serializable {
}
```

V2:

```java
record Invoice(String id, long cents, String currency)
        implements java.io.Serializable {

    public Invoice {
        if (currency == null) {
            currency = "UNKNOWN";
        }
    }
}
```

Generate a stream using V1 code, read it with V2 code, and verify `currency` afterward. Next, modify the constructor to reject null and observe the difference. Explain why this failure cannot be solved merely by setting an identical `serialVersionUID`.

### Exercise 2: Enums and Database Ordinals

V1:

```java
enum TaskState {
    TODO, IN_PROGRESS, DONE
}
```

The database stores `IN_PROGRESS` as an ordinal. V2 inserts `BLOCKED` before `IN_PROGRESS`. Identify how existing database rows are affected and design a migration to stable codes with rollback.

### Exercise 3: New Producer, Old Consumer

Producer V2 adds `MANUAL_REVIEW` to a payment enum. Consumer V1 does not yet know this constant. Design:

- A policy when the consumer reads Java Object Serialization.
- A policy if the API uses JSON stable codes.
- Deployment order for readers and writers.
- Logs/metrics for unknown values.
- A rollback scenario when new messages are already in the queue.

### Exercise 4: Migrating a Legacy Object Stream

A batch job previously persisted `LegacyProfile` using Java Object Serialization. The development team wants to convert the domain model to a record and upgrade the JDK from 8 to 21. Describe the pipeline:

```text
Legacy reader -> validated DTO -> versioned schema -> new record domain model
```

Specify where golden fixtures are tested, where malformed data is handled, how record counts/checksums are verified, and how zero data loss is ensured on rollback.

## Conclusion

Records and enums follow distinct serialization rules in Java. **Records** must implement `Serializable` to use Java Object Serialization; record components are restored through the canonical constructor, so validation, defaults, and schema evolution directly affect stored data. **Enums** are serialized by **constant name**, not ordinal, and do not use ordinary-class custom serialization callbacks to alter their format. Adding, renaming, or removing constants can break un-upgraded consumers.

During migration, clearly identify the actual format: Java Object Serialization, JSON, JPA, Protobuf, and Avro each enforce different contracts. Do not verify only successful compilation; use golden data from older versions, test reading in both producer/consumer directions, test canonical constructors and unknown enum values, design stable codes/schema versions, and maintain a data rollback plan. Separating domain records/enums from wire or database DTOs when needed enables systems to evolve across JDK and service versions without silently corrupting business data.
