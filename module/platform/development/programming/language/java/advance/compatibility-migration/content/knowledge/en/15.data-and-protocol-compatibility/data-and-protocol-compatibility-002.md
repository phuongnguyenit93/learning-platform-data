# Changing Serializable classes and readability of stored objects

When a Java application saves objects with `ObjectOutputStream` and reads them back with `ObjectInputStream`, the written data can outlive the class version that created it. After a JDK upgrade, library upgrade, or model refactoring, the same `.ser` file may no longer be readable. Failures can be `InvalidClassException` due to a different `serialVersionUID`, `ClassNotFoundException` because the class changed packages, `ClassCastException` because old data does not satisfy the new type, or more subtly: the object reads successfully, yet new fields receive `null`, `0`, or `false`, causing business logic to behave incorrectly.

The core question is not simply "Is Java serialization compatible across JDKs?". Java Object Serialization defines a stream format and class evolution rules; however, the ability to read **a specific object graph** depends on the binary name of the class, version identifier, field structure, superclass, serialization customizations, referenced classes, and the classpath/runtime when reading. When changing code, what must be verified is **whether the new class version can read data written by the old version**, with correct business behavior afterward.

This lesson focuses on migrating classes that implement `Serializable`, scenarios for reading stored data, intentional use of `serialVersionUID`, organizing golden-file tests, and more durable data options for systems requiring upgrades over many years.

## 1. Identifying the exact kind of stored data

Not every object transmitted over the network or stored in a file uses Java Object Serialization. First identify the actual mechanism.

| Mechanism | Example | Primary migration risks |
|---|---|---|
| Java built-in serialization | `ObjectOutputStream.writeObject(...)` / `ObjectInputStream.readObject()` | Class names, UIDs, field layout, hooks, and object graph |
| Java `Externalizable` | `writeExternal` / `readExternal` | Developer-managed format, constructor, version marker |
| JSON/XML | Jackson, Gson, JAXB | Field names, annotations, schema, polymorphism, date/time |
| Protobuf/Avro/Thrift | Specific message schemas | Schema evolution, field identifiers, compatibility rules |
| Database ORM | JPA/Hibernate entities | Database schema, converters, lazy proxies, mapping |
| Binary cache/session | Redis/session store with Java serializer | Object lifecycle, rolling deployment, mixed-version reads |
| RMI/Java-specific protocol | Object serialization over Java transport | Classpath on both ends, graph, security, protocol |
| Application-specific byte format | `DataOutputStream` or custom codec | Framing, byte order, version, and codec contract |

`Serializable` is a marker interface; a class might implement it even though the application never writes objects via `ObjectOutputStream`. Conversely, a cache/session framework might use Java serialization implicitly without business source code calling `writeObject` directly. Therefore, inventory actual storage and reading paths, not just imports.

Places commonly holding serialized data to include in the audit scope:

- Snapshot files, checkpoints, backups, batch outputs, and archives.
- Distributed caches or disk-backed caches.
- HTTP session replication/session persistence.
- Queue/message payloads in systems using Java serialization.
- RPC/remote invocation or plugin exchange.
- Persisted job state, workflow engines, and schedulers.
- Data persisted by third-party frameworks/libraries.
- Object graphs used in legacy test fixtures.

A system that does not require backward compatibility for cache data may opt for a controlled cache flush during upgrade; a system storing business records or long-lived state usually cannot do that. Clearly document data retention lifetimes and whether data must remain readable after a rollback.

## 2. What is Serializable and what does the JVM write?

### 2.1. Basic example

```java
package com.example.account;

import java.io.Serial;
import java.io.Serializable;

public class AccountSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String accountId;
    private long balanceInCents;

    public AccountSnapshot(String accountId, long balanceInCents) {
        this.accountId = accountId;
        this.balanceInCents = balanceInCents;
    }

    public String getAccountId() {
        return accountId;
    }

    public long getBalanceInCents() {
        return balanceInCents;
    }
}
```

Writing the object:

```java
import java.io.ObjectOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("snapshots", "account.ser");
Files.createDirectories(path.getParent());

AccountSnapshot snapshot = new AccountSnapshot("ACC-42", 125_000L);

try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject(snapshot);
}
```

Reading the object:

```java
import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (ObjectInputStream in =
         new ObjectInputStream(Files.newInputStream(path))) {
    Object loaded = in.readObject();
    AccountSnapshot snapshot = (AccountSnapshot) loaded;
    System.out.println(snapshot.getAccountId());
}
```

The example assumes the file comes from a trusted source and the matching class is on the classpath. **Do not use `ObjectInputStream` directly to read data sent by external parties or untrusted inputs.** Deserialization security is discussed separately in a later section.

### 2.2. The stream contains more than just field values

The Java Object Serialization Stream Protocol encodes the information needed to reconstruct an object graph, including:

- The stream magic header and protocol version.
- Class descriptor: binary name, `serialVersionUID`, flags, and list of serialized fields.
- Object field values.
- Reference handles to preserve shared objects/cycles in the graph.
- Descriptors and data of referenced objects.
- Custom information written by hooks or `Externalizable` when used.

This explains why renaming a class or package is not like renaming a key in JSON. The class name lives in the stream descriptor; the deserializer must locate a local class with matching identity.

### 2.3. Object graphs contain multiple classes requiring compatibility

Suppose:

```java
class OrderSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private CustomerSnapshot customer;
    private List<OrderLine> lines;
}
```

Even if `OrderSnapshot` keeps the same UID, the object graph still cannot be read properly if an inner class such as `CustomerSnapshot` or `OrderLine` undergoes an incompatible change to its binary name, serial UID, or representation.

When building a compatibility matrix, list **every class that can appear in the object graph**, including collection wrappers, enums, custom value objects, subclasses, proxies, and framework/library-provided classes. Do not inspect only the root object.

## 3. What is serialVersionUID?

### 3.1. Role of serialVersionUID

`serialVersionUID` is a `long` used by the class compatibility verification mechanism during deserialization. Serializable classes should declare it explicitly:

```java
@Serial
private static final long serialVersionUID = 1L;
```

Since JDK 14, the `@Serial` annotation helps the compiler recognize serialization-related declarations, though this annotation does not alter the stream format. If source code must support JDKs prior to `@Serial`, consider the source level. `serialVersionUID` remains effective without the annotation.

When reading a standard class, Java compares the serial version identifier in the stream with the local class. If they do not match, it can throw `InvalidClassException`.

Example message:

```text
java.io.InvalidClassException: com.example.account.AccountSnapshot;
local class incompatible:
stream classdesc serialVersionUID = 1,
local class serialVersionUID = 2
```

Distinguish **serialization compatibility** from semantic/business compatibility. A matching UID is an important condition for the verification mechanism, but it does not guarantee old fields remain semantically valid or that all hooks are compatible.

### 3.2. Undeclared UID: the default UID can change

If a `Serializable` class does not declare `serialVersionUID`, Java computes a default value from class characteristics per the specification, including certain names, modifiers, interfaces, fields, constructors, and methods.

Consequently, a source change seemingly unrelated to data — such as modifying a public method or class structure — can change the default UID. After recompiling, old data becomes unreadable due to a UID mismatch even though the fields the application cares about are unchanged.

You can inspect the current class's UID with:

```java
import java.io.ObjectStreamClass;

long uid = ObjectStreamClass
    .lookup(AccountSnapshot.class)
    .getSerialVersionUID();

System.out.println(uid);
```

Or using the JDK tool:

```bash
serialver -classpath old-library.jar com.example.account.AccountSnapshot
```

When preserving old data from a class that never declared a UID, extract **the UID value of the old binary version** before changing source code. After evaluating class evolution, you can declare an explicit UID equal to the old value to maintain readability. Do not invent a new UID or change a UID just to make an error message disappear.

### 3.3. Do not mechanically increment UID with the application version

`serialVersionUID` does not have to match the Maven version, semantic version, or release count. If class changes fall within compatible evolution, keeping the old UID may be the right choice.

Conversely, if changing the representation incompatibly, forcing the UID to stay the same merely lets the deserializer pass the identity check and risk failing during field reading or creating an object in an invalid state.

Decide the UID based on data design:

- Keep the UID if the object format can still be read and converted safely.
- Change the UID if intentionally rejecting incompatible legacy data, accompanied by a data migration plan.
- Use records/DTOs/versioned schemas or another format if complex long-term evolution is needed.

### 3.4. UID is not a full schema version

A single UID does not describe added fields, removed fields, business invariants, data types, inheritance relationships, or null handling. If storing data for many years, a separate **data/schema version** may be needed to apply transformations and validation.

For instance, a class may keep `serialVersionUID = 1L` while adding a `formatVersion` field or out-of-stream metadata mechanism to distinguish business generations. Each version needs explicit conversion rules; do not merely increment the version field and ignore stored data.

## 4. Class evolution rules with default serialization

Default serialization primarily handles non-`static` and non-`transient` instance fields. When the local class changes relative to the stream, Java defines rules for matching serialized fields by name and type, with compatible and incompatible cases.

### 4.1. Adding an instance field

Version v1:

```java
public class CustomerSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private String id;
    private String name;
}
```

Version v2:

```java
public class CustomerSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private String id;
    private String name;
    private String locale;
}
```

When v2 reads a stream written by v1, the `locale` field is absent from the stream. With default serialization, it receives the **type's default value**: `null` for references, `0` for integral types, `false` for booleans.

Note: the constructor of an ordinary serializable class is **not invoked** the way `new CustomerSnapshot()` is when restored via default deserialization. Therefore, default initialization logic in constructors or field initializers must not be relied upon to populate new fields during migration.

If business rules require `locale` to default to `"vi-VN"`, add a mechanism to assign and validate the value on read; `readObject` can be used if it fits the contract.

### 4.2. Removing an instance field

If v1 had `middleName` and v2 removes it, the serialized v1 stream may contain `middleName` data. When read by v2 via default serialization with a matching UID, data for the removed field is typically ignored.

However, if an existing method, `readObject`, `readResolve`, or business invariant still depends on `middleName`, that is a separate logic issue. Do not conclude "removing a field is always safe" solely from the absence of `InvalidClassException`.

### 4.3. Renaming a field

Renaming a field is a combination of **removing the old field and adding a new field** from the perspective of serialized field mapping.

Example:

```text
v1: customerName
v2: displayName
```

When reading v1 data with v2, `displayName` may receive `null` while `customerName` data is discarded. The deserializer does not automatically recognize them as the same business field.

To preserve old values, design a mapping in a compatibility layer or use an advanced serialization mechanism such as `serialPersistentFields`/`readObject` to read the legacy field name. Do not merely refactor the variable name and hope old data is retained.

### 4.4. Changing a field's type

Changing the type of a serialized field can cause incompatibility. Example:

```text
v1: int age
v2: long age
```

If a field keeps the same name while changing its primitive type, do not assume Java will widen `int` to `long` the way the source compiler does. Deserialization uses field type metadata, and type incompatibility can lead to `InvalidClassException`.

Similarly, changing from `String` to `LocalDate` or from one model class to another can result in mismatched layouts or values.

To change representation, separate it into a new field, keep the legacy field during migration, or transition via a DTO/versioned schema with explicit rules. An offline data conversion step may be necessary.

### 4.5. `static`, `transient`, and `final`

- `static` fields belong to the class, not instance state saved by default serialization.
- `transient` fields are not written by default serialization.
- `final` instance fields can be part of serialized state, but do not rely on the serializable class's constructor/initializers to re-establish invariants on read.
- Changing a field to `transient` can prevent old data from being restored as before.

Example:

```java
public class SessionState implements Serializable {
    private static final long serialVersionUID = 1L;

    private String sessionId;
    private transient String accessToken;
    private static String deploymentRegion;
}
```

`sessionId` is stored by default serialization; `accessToken` and `deploymentRegion` are not. Marking the token `transient` is not sufficient to protect data if tokens were already persisted in earlier versions; assess and handle legacy files/caches.

### 4.6. Field change comparison table

| Change from v1 to v2 | Ability to read v1 stream with v2 | Risks to check |
|---|---|---|
| Add a new field | Usually readable if UID/structure match | Default value differs from expectation |
| Remove a field | Usually readable if UID/structure match | Loss of old data still needed |
| Rename a field | Equivalent to remove + add | New field gets default value |
| Change field type keeping name | Potentially incompatible | `InvalidClassException` or invalid data |
| Change `transient` | Readable, though stored data changes | Field is or is not restored |
| Change `static` | Outside default instance state | Changes configuration/runtime behavior |
| Change generic type argument | Keeps erased field type | Runtime cast errors and semantic mismatch |
| Change class hierarchy | Must be evaluated separately | Constructors, class data, superclass state |
| Rename class/package | Usually incompatible by default | Binary name cannot be resolved |
| Change serialVersionUID | Usually rejected | `InvalidClassException` |

"Usually readable" is not an absolute guarantee: binary name, type relationships, UID, stream format, hooks, and the entire object graph must also remain compatible.

## 5. Reproducible example: adding a field and reading v1 data

### 5.1. Binary v1 for writing data

In version v1, store the class under the exact package and name below:

```java
package com.example.data;

import java.io.Serializable;

public class CustomerSnapshot implements Serializable {
    private static final long serialVersionUID = 7L;

    private String id;
    private String name;

    public CustomerSnapshot(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
}
```

The application writes:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject(new CustomerSnapshot("C-100", "An"));
}
```

The file produced by **binary v1** must be saved as an immutable test fixture. Do not generate fixtures directly from class v2, as that does not verify reading historical data.

### 5.2. Binary v2 reading legacy data

Keep the binary name `com.example.data.CustomerSnapshot` and UID unchanged:

```java
package com.example.data;

import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.Serial;
import java.io.Serializable;

public class CustomerSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 7L;

    private String id;
    private String name;
    private String locale;

    public CustomerSnapshot(String id, String name, String locale) {
        this.id = id;
        this.name = name;
        this.locale = locale;
    }

    @Serial
    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();

        if (id == null || id.isBlank()) {
            throw new java.io.InvalidObjectException("Missing id");
        }

        // v1 data has no locale: receives null when read.
        if (locale == null) {
            locale = "vi-VN";
        }
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getLocale() { return locale; }
}
```

In v2, `in.defaultReadObject()` reads the fields present in the stream and matches them to local fields per the rules. Fields absent from the stream receive default values; afterward, `readObject` can restore invariants for legacy data.

Test example:

```java
try (ObjectInputStream in =
         new ObjectInputStream(Files.newInputStream(legacyPath))) {
    Object value = in.readObject();

    if (!(value instanceof CustomerSnapshot snapshot)) {
        throw new java.io.InvalidObjectException(
            "Unexpected root type"
        );
    }

    if (!"vi-VN".equals(snapshot.getLocale())) {
        throw new AssertionError("Legacy locale mapping failed");
    }
}
```

The example assumes trusted fixture data, appropriate imports for `Files`/`Path`/`ObjectInputStream`, and a file genuinely from v1. For untrusted data, eliminate native Java deserialization at that boundary or enforce strict, independently reviewed protection policies.

### 5.3. What is not guaranteed?

If the v1 file already had a `locale` field where an actual `null` carried distinct meaning, checking `locale == null` cannot distinguish "field absent" from "field present but null". In that case, `ObjectInputStream.GetField` can inspect the field's defaulted status, or explicit version metadata can be designed.

When migrating across many versions, avoid piling too many guesses onto a null value. An explicit schema version is usually easier to manage.

## 6. readObject, writeObject, and defaultReadObject

### 6.1. Customizing the reading process

A `Serializable` class can declare a private method with a special signature:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Restore invariants or verify data.
}
```

`readObject` is not a method the application calls directly. The serialization mechanism discovers this method according to specification rules.

When using `readObject`, decide:

- Whether to call `defaultReadObject()` or read persistent fields with `readFields()`.
- Which validation must run before the object is used.
- How new field values are initialized.
- What to do when old values are no longer valid.
- How to avoid dangerous side effects while the object graph is not yet fully restored.

Do not invoke business methods that may depend on a complete object graph prematurely during deserialization. Avoid registering the object into singletons/registries inside `readObject` before the object is fully validated.

### 6.2. Customizing the writing process

Example:

```java
@Serial
private void writeObject(ObjectOutputStream out)
        throws IOException {
    out.defaultWriteObject();
    // Optional extra data can be written per the class protocol.
}
```

If writing additional optional data after `defaultWriteObject()`, the reader must understand the structure/version of that extra section. Changing the order or count of custom data can make old/new streams incompatible, even with matching UIDs.

Do not add or remove `writeObject` casually in an API with existing persisted data. Review Java Object Serialization versioning rules and test against legacy data.

### 6.3. Using GetField when you need to distinguish absent fields

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    ObjectInputStream.GetField fields = in.readFields();

    id = (String) fields.get("id", null);
    name = (String) fields.get("name", null);

    boolean absent = fields.defaulted("locale");
    locale = absent
        ? "vi-VN"
        : (String) fields.get("locale", null);
}
```

`defaulted("locale")` determines whether the field was missing in the stream compared to the current class's fields. To use this approach, the field must belong to the declared serializable fields of the current class.

This is an appropriate technique for migrations distinguishing "field did not exist in the old version" from "field existed and was null". After reading, validate invariants and type assumptions.

### 6.4. readObjectNoData

In certain cases where a serializable class appears in the local hierarchy without corresponding class data in the stream, the mechanism can invoke `readObjectNoData()` if properly declared.

```java
@Serial
private void readObjectNoData()
        throws java.io.ObjectStreamException {
    // Restore valid state when class data is absent.
}
```

This is not a callback that runs whenever a new field is added. It serves cases where class data for **a class in the hierarchy** is missing, such as certain hierarchy changes. Add this method only for a specific evolution scenario with tests confirming it is invoked as expected.

## 7. serialPersistentFields and controlled field renaming

`serialPersistentFields` lets a class explicitly declare the set of fields appearing in the serialized form, partially decoupled from current physical fields.

Declaration example:

```java
@Serial
private static final ObjectStreamField[] serialPersistentFields = {
    new ObjectStreamField("id", String.class),
    new ObjectStreamField("customerName", String.class)
};
```

This mechanism typically pairs with `writeObject`/`readObject` and `PutField`/`GetField` to map between persistent field names and current representation.

A migration approach:

- v1 had field `customerName`.
- v2 wants to use an in-memory field named `displayName`.
- v2 still declares serialized field `customerName` to read old files.
- `readObject` maps persistent field `customerName` to `displayName`.
- `writeObject` decides which layout to write for supported consumers.

This approach is more complex than using a compatible DTO, especially when supporting multiple versions in one object graph. Do not use `serialPersistentFields` as a trick to "patch every old stream"; provide clear contracts, tests, and documentation.

## 8. writeReplace, readResolve, and the Serialization Proxy Pattern

### 8.1. Why use a proxy?

A business class with many invariants, transient fields, caches, locks, or internal state should not necessarily be serialized via its direct layout. The **Serialization Proxy Pattern** helps decouple a stable serialized form from the implementation class.

In this pattern:

1. The object implements `writeReplace()` to substitute a serializable proxy.
2. The proxy holds minimal state, version, and normalized invariants.
3. On deserialization, the proxy implements `readResolve()` to construct a valid domain object.

Conceptual example:

```java
public final class Money implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String currency;
    private final long minorUnits;

    public Money(String currency, long minorUnits) {
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("currency");
        }
        this.currency = currency;
        this.minorUnits = minorUnits;
    }

    @Serial
    private Object writeReplace() {
        return new SerializationProxy(currency, minorUnits);
    }

    private static final class SerializationProxy
            implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String currency;
        private final long minorUnits;

        SerializationProxy(String currency, long minorUnits) {
            this.currency = currency;
            this.minorUnits = minorUnits;
        }

        @Serial
        private Object readResolve() {
            return new Money(currency, minorUnits);
        }
    }
}
```

The example illustrates decoupling serialized representation from the domain object. For a production implementation, also address preventing direct deserialization of the outer class and inheritance rules. If the proxy's binary name or serialized fields change, old files can still be affected.

### 8.2. readResolve is not an automatic package-renaming tool

`readResolve` can return a replacement object after a class has been deserialized. It does not solve the JVM failing to find a class with the old binary name from the stream.

If a package was renamed, the deserializer must be able to load the legacy representation or use a purpose-built stream conversion mechanism. Keeping a legacy DTO/proxy is usually simpler and more reliable than attempting arbitrary class descriptor remapping.

## 9. Renaming classes or packages and stored data

Suppose v1:

```java
package com.example.legacy;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
}
```

v2 becomes:

```java
package com.example.domain;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
}
```

The two classes have **different binary names**. Sharing `1L` as UID does not mean a file containing `com.example.legacy.Customer` is automatically read as `com.example.domain.Customer`.

Options:

1. **Keep the old class:** continue providing `com.example.legacy.Customer` to read old streams, then convert to the new domain class via an adapter.
2. **Offline conversion:** use the old binary/classpath to deserialize historical data in a safe environment, then serialize to a new versioned/schema format.
3. **Custom resolution:** in some cases a custom `ObjectInputStream.resolveClass` can be used, but it is constrained by class descriptors, hierarchy, naming, structure, and type checking; do not treat it as a safe arbitrary rename.
4. **Maintain a legacy artifact:** if data is read only rarely, package a separate conversion module/process to avoid complicating the main runtime.

Do not create a new class with the same UID and assume old streams will open. A package migration plan must include data migration, not just refactoring imports.

## 10. Changing class hierarchy and constructors

### 10.1. Adding or removing Serializable on a superclass

Serialization rules differ between a class implementing `Serializable` and a non-serializable superclass. When deserializing a normal serializable object, constructors of serializable classes in the inheritance chain do not run as with `new`; the accessible no-arg constructor of the first non-serializable superclass runs per Java Object Serialization rules.

If `Serializable` is added to or removed from a superclass, or a new class is inserted into the hierarchy, the per-class data written/read can change. A class might deserialize yet miss invariants or previously initialized state.

### 10.2. Non-serializable superclasses must be suitable

If a non-serializable superclass lacks an appropriate no-arg constructor for the object-restoration mechanism to invoke, deserialization can fail, for instance with `InvalidClassException`.

Risky example:

```java
class BaseEntity {
    BaseEntity(String tenant) {
    }
}

class ChildSnapshot extends BaseEntity implements Serializable {
    private static final long serialVersionUID = 1L;

    ChildSnapshot(String tenant) {
        super(tenant);
    }
}
```

If this class must be deserialized with Java serialization, inspect the non-serializable superclass's constructor against the mechanism's requirements. You cannot examine only `ChildSnapshot`'s constructor.

### 10.3. Changing fields in a superclass

If a field moves between subclass and superclass, the serialized form can change because each serializable class's data in the hierarchy is written under its own class descriptor. Do not assume identical field names/types are enough to move values across layers automatically.

Check:

- Class ordering in the hierarchy.
- Class data in old streams.
- UID of each serializable class.
- Which class owns each field's state.
- `readObject`/`readObjectNoData` and hooks.
- Invariants that must be restored when constructors do not run.

## 11. Serializable records and enums

### 11.1. Records have their own serialization mechanism

Java records follow distinct Java Object Serialization rules compared to ordinary serializable classes. A record must implement `Serializable` if it is to be serialized with this mechanism.

```java
import java.io.Serializable;

public record CustomerRecord(String id, String name)
        implements Serializable {
    public CustomerRecord {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id");
        }
    }
}
```

When deserializing a record, the mechanism invokes its **canonical constructor** from the component values. Therefore, invariants in the canonical constructor can be enforced during restoration. Unlike ordinary serializable classes, serialization hooks such as `readObject`/`writeObject` are not used in the ordinary way for records.

Requirements for matching `serialVersionUID` are handled specially for record classes; do not mechanically apply reasoning meant for ordinary serializable classes to records. Evaluate against the target JDK's record serialization specification.

If a record component is added, old data will lack the new component and a default value will be passed to the canonical constructor, potentially causing validation to fail. Changing component names/types also affects the serialized form.

### 11.2. Enums are serialized by constant name

Enums have their own serialization mechanism: constant identity is recorded primarily via the enum type name and constant name. UID is not processed like an ordinary class and serialization hooks generally do not apply in the same way.

Example:

```java
public enum Status {
    NEW,
    ACTIVE,
    DISABLED
}
```

If an old stream contains `ACTIVE` and v2 renames it to `ENABLED`, the deserializer does not infer they are equivalent constants. Old data may fail to read, e.g., throwing `InvalidObjectException` when the enum constant is not found.

For persisted data, consider keeping the old constant during a transition phase or mapping to stable business codes in an external data format. Do not rename enum constants without checking persisted payloads.

## 12. Externalizable: greater control, greater responsibility

A class implementing `Externalizable` takes direct control over how data is written/read via `writeExternal` and `readExternal`.

```java
import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectOutput;

public class EventEnvelope implements Externalizable {
    private static final long serialVersionUID = 1L;

    private int formatVersion;
    private String eventId;

    public EventEnvelope() {
        // Public no-arg constructor required for Externalizable.
    }

    public EventEnvelope(String eventId) {
        this.formatVersion = 1;
        this.eventId = eventId;
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeInt(formatVersion);
        out.writeUTF(eventId);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        int version = in.readInt();

        if (version == 1) {
            eventId = in.readUTF();
            formatVersion = version;
        } else {
            throw new java.io.InvalidObjectException(
                "Unsupported event format: " + version
            );
        }
    }
}
```

This structure is only a minimal example. `Externalizable` still participates in the Java Object Serialization Protocol and class identity; it does not turn the data into a JDK/language-neutral protocol.

Points to watch:

- Requires a suitable public no-arg constructor.
- The developer manually manages field order and data types during writing and reading.
- Reordering or dropping a field without version handling easily breaks reading of old files.
- `writeUTF` uses its own Modified UTF-8 format; do not treat it as identical to standard UTF-8 in non-Java protocols.
- A version marker must be read before the payload, with handling defined for unknown versions.
- Test truncated streams, missing values, malformed lengths, and malicious payloads.

If the system already uses `Externalizable`, inspecting `writeExternal`/`readExternal` code matters more than guessing compatibility via default field evolution.

## 13. Generics, proxies, collections, and object graphs

### 13.1. Changing generic arguments differs from changing serialized field types

Suppose v1 has:

```java
private List<String> tags;
```

v2 changes it to:

```java
private List<Integer> tags;
```

At the erased field type level, both remain `List`. The stream may still read if other conditions match. Yet if v2 iterates `List<Integer>` and casts each element, `String` elements in the old stream can cause `ClassCastException` or misprocessing.

This shows Java serialization compatibility requires **checking actual data**, not just descriptors.

### 13.2. Collection implementations are also part of the graph

An object field typed as `List` may hold an instance of `ArrayList`, `LinkedList`, an unmodifiable wrapper, or a custom collection. The stream records the concrete object type, not merely the `List` field declaration.

When upgrading dependencies or the JDK, check the concrete classes present in legacy data. A removed collection wrapper or library-specific class can make data unreadable even if the root model is unchanged.

If a schema must live long, avoid relying heavily on serialized forms of library-internal classes or implementation details.

### 13.3. Dynamic proxies and framework classes

Frameworks can place dynamic proxies, lazy-loading proxies, generated subclasses, or session objects into the graph. Some proxies are not serializable, and some require a specific container/provider when read back.

Issues often appear only in session replication or distributed caches when the application upgrades its framework. Prefer persisting explicit DTOs/state rather than raw objects attached to a runtime container, connection, thread, lock, or persistence context.

## 14. Security: Java deserialization is not for untrusted data

### 14.1. The risk is more than class mismatch

Java native deserialization can trigger code execution through class loading, serialization hooks, and unexpected object graphs. If untrusted data can reach `ObjectInputStream`, the system can face severe risks depending on the classpath and usage.

Security principles:

- **Do not deserialize native Java objects from untrusted requests, messages, or files** whenever another format can be chosen.
- Do not rely on `serialVersionUID` as a data authentication mechanism.
- Do not assume Base64-encoded or compressed data is safe.
- Do not simply catch exceptions and assume an object was handled safely.
- Prefer schema-based formats, data allowlists, and business validation at boundaries.

### 14.2. ObjectInputFilter

JDK 9 added serialization filtering (JEP 290). JDK 17 added context-specific deserialization filters (JEP 415), allowing filtering policies to be configured per context. Filters can constrain class types, graph depth, reference counts, and byte counts.

Illustrative policy example for an **authenticated and trusted** internal source, not a default allowance for data from the Internet:

```java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
    "maxdepth=20;maxrefs=5000;maxbytes=1048576;" +
    "com.example.model.**;java.lang.*;java.util.*;!*"
);

try (ObjectInputStream in =
         new ObjectInputStream(Files.newInputStream(path))) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
```

This is only a sample illustrating filter syntax. A production policy must allow **only the classes truly required**, avoid opening overly broad packages, enforce appropriate size/depth bounds, and be tested with both valid and abnormal payloads. Filters do not replace authentication, data provenance, validation, dependency updates, or the rule against accepting untrusted native serialization.

### 14.3. Migrating legacy files in an isolated environment

If the provenance of historical data is uncertain, reading legacy files with the full application classpath can increase risk. When data conversion is required, consider:

- A dedicated process with least privileges.
- A minimal classpath containing only the necessary legacy classes.
- Limits on CPU, memory, file system, network, and processing time.
- Filters, maximum sizes, and payload validation.
- Logs/checksums of converted files and outcomes.
- Not running the converter with production secrets unless necessary.

Converted data should be exported to a format with an explicit schema/version to reduce long-term dependence on Java object graphs.

## 15. Why can upgrading from JDK 17 to 21 still affect Serializable data?

Java Object Serialization follows a shared specification; JDK 21 does not automatically render every file written by JDK 17 unreadable. Yet during a JDK upgrade, simultaneous changes often occur:

- Frameworks/drivers/collection libraries are upgraded or replaced.
- Classes are refactored, moved to different packages, or change hierarchies.
- The new JDK enables different security rules or filter configurations.
- Artifacts are packaged differently, omitting a class needed for reading.
- A class in the object graph belonged to a library previously on the classpath that is now removed.
- Custom serialization hooks depended on implementation details.
- Recompiled source changes the default UID because no explicit UID was declared.
- Old and new data coexist during a rolling deployment.

Do not assume "JDK 21 broke the stream" when the real cause is a domain model version change or a missing dependency. Test **the same binary and the same data** across runtimes, then vary one factor at a time to isolate the cause.

JEP 400 changed the default charset starting in JDK 18 for many text APIs, but **ObjectOutputStream writes a binary format per the serialization protocol**, not relying on `Charset.defaultCharset()` to encode the stream like an ordinary text file. If an encoding error arises, inspect surrounding text I/O code or custom serialization manually converting bytes/strings rather than concluding Java serialized streams changed charsets.

## 16. Reading both old and new data during rolling deployments

### 16.1. One-way and two-way compatibility are different requirements

Data migration typically has two directions:

- **Backward read:** the new version reads data created by the old version.
- **Forward read:** the old version reads data created by the new version.

If rolling out by replacing all v1 servers with v2 and no rollback needs to read new state, backward read alone may suffice. However, during rolling deployments or blue-green cutovers, v1 and v2 may concurrently read/write the same cache, queue, or session store during the transition window.

In that case, **both directions** must be evaluated.

### 16.2. Field addition example

v2 adds `locale` while keeping a compatible UID. When v2 reads a v1 stream, the new field defaults to null, which `readObject` can handle. Conversely, when v1 reads a v2 stream, it can ignore the `locale` field since it does not know it exists.

However, if v2 starts relying on `locale` to determine currency/date formatting or writes state under new business semantics, v1 does not understand that information. Technically the stream may deserialize, yet business behavior remains incompatible.

Therefore a matrix is needed:

| Writer | Reader | What to verify |
|---|---|---|
| v1 | v1 | Baseline |
| v1 | v2 | Reading historical data, defaults/migration |
| v2 | v2 | New functionality |
| v2 | v1 | Rolling deployment, rollback, whether ignoring the new field is safe |

Not every product is required to support v2 → v1. If unsupported, design the deployment so no old version ever reads new state.

### 16.3. Ways to reduce shared persistent state risk

Several strategies:

- Keep the serialized form schema stable across the entire rolling window.
- Separate cache namespaces or key prefixes by version.
- Deploy migration code first, change the writer format afterward.
- Move state to a stable, versioned DTO/schema.
- Use a versioned serializer or upcaster when supported by the framework.
- Define when caches can be cleared or rehydrated from the source of truth.

If it is merely a regenerable cache, intentional versioned invalidation may work. If it is critical business data, a migration/recovery plan is required—do not use "clear cache" as a catch-all fix.

## 17. Golden-file compatibility tests

### 17.1. Golden files are data genuinely created by the old binary

A serialization test that only creates an object and reads it back within the same version misses evolution issues. Save **stream fixtures genuinely written by the old version**.

Process:

1. Check out/preserve binary v1 and its dependencies.
2. Run the v1 program to generate streams with representative object graphs.
3. Store `.ser` files in test fixtures or a controlled artifact repository.
4. Record checksums, producer version, UID, classpath, and data context.
5. Read those files using binary v2 and verify contents.
6. For rolling/rollback support, also generate v2 files for binary v1 to test reading if committed.
7. Keep tests running on both minimum and target JDKs/runtimes when supporting multiple JDKs.

Do not hand-edit fixture bytes or patch only the serialVersionUID bytes to make tests pass. That does not accurately test released streams.

### 17.2. Using two separate classpaths for v1 and v2

You cannot load two versions with the same binary name `com.example.data.CustomerSnapshot` into the same class loader and expect the JVM to pick "v1 for writing, v2 for reading" as intended. Create **two separate processes or classpath environments**:

```text
Producer JVM:
  classpath = app-v1.jar + dependencies-v1
  action    = write test-data/customer-v1.ser

Consumer JVM:
  classpath = app-v2.jar + dependencies-v2
  action    = read test-data/customer-v1.ser
```

Using a single JVM with multiple custom class loaders complicates tests and risks confusing class identity. Two independent processes are usually simpler for simulating real deployment.

### 17.3. Representative datasets

Do not create only objects where every field is non-null. Include:

- Objects with null fields, empty collections/strings, and default values.
- Objects with nested references and collections.
- Object graphs with cycles and shared references.
- Legacy enum values, including values soon to be deprecated.
- Data containing dates/times, monetary amounts, and Unicode characters.
- Subclasses/polymorphic objects in interface/base-typed fields.
- Objects with transient fields or custom-serialized state.
- Representative data from multiple still-supported older versions.
- Truncated or corrupted streams to test fail-safe behavior, within a safe test environment.

### 17.4. What to assert

- Root object has the expected type and deserializes.
- Business fields retain accurate values.
- New fields receive correct defaults/mappings.
- Invariants/validation are enforced.
- Collection contents, reference identity, and relationships are intact.
- No required state is lost across read/write cycles.
- Invalid data errors are rejected rather than silently accepted.
- No unexpected class/provider loading occurs.
- If two-way compatibility is required, binary v1 reads v2 output per contract.

### 17.5. Controlling test fixtures

Record metadata alongside the file:

```yaml
fixture: customer-v1.ser
producer:
  application_version: "1.4.2"
  jdk: "17"
  class_name: "com.example.data.CustomerSnapshot"
  serial_version_uid: 7
scenario: "Customer with nullable legacy fields"
expected_reader_versions:
  - "2.x"
```

This is an example metadata format; add JDK vendor/update, checksum, and reference commit. Never commit production data containing personal information or secrets into the repository just to create fixtures.

## 18. Common errors and how to trace them

| Symptom | Possible causes | Investigation steps |
|---|---|---|
| `InvalidClassException`, UID mismatch | Default UID changed or explicit UID differs | Extract old and new binary UIDs with `serialver`/`ObjectStreamClass` |
| `InvalidClassException`, incompatible field types | Serialized field keeps name but changed type incompatibly | Compare field descriptors and stream schema |
| `ClassNotFoundException` | Binary name in stream absent from reader's classpath | Check package renames, dependencies, and class loaders |
| `NoClassDefFoundError` | JVM requires a related class that cannot be found/loaded | Compare object graph and runtime classpath |
| `ClassCastException` | Generic field erasure stayed the same while actual data type changed | Inspect collection elements and casts |
| `InvalidObjectException` | Validation/hook rejected object or enum name does not exist | Check business invariants, enum evolution, and stack trace |
| `StreamCorruptedException` | Header/stream content violates serialization protocol | Check for overwritten, truncated, compressed, or mis-wrapped files |
| `EOFException` | Stream missing bytes or ended prematurely | Check file size, writer, crashes, atomic file publishing |
| `OptionalDataException` | Custom serialization protocol mismatch | Compare `writeObject`/`readObject` or Externalizable |
| `WriteAbortedException` | Writer encountered an exception while serializing | Inspect the cause recorded in the stream/stack trace |
| Reads cleanly but new field is null | Field absent in old stream | Assign migration default, use GetField/validation |
| Reads cleanly but business behavior is wrong | Schema/semantic change, hooks did not run as assumed | Behavioral golden tests and invariant checks |

Not every message above has a single cause. Record the full stack trace, class names, source version, runtime classpath, and fixture data before modifying code.

## 19. Diagnostic and verification tools

### 19.1. serialver

Inspect the Java-computed UID for a class:

```bash
serialver -classpath legacy.jar com.example.data.CustomerSnapshot
serialver -classpath current.jar com.example.data.CustomerSnapshot
```

If the tool/version is absent from a minimal runtime image, run it from an appropriate JDK toolchain. Do not rely on freshly recompiled source to discover historical UIDs; use the actual old artifact.

### 19.2. javap

Inspect class binaries, fields, and method hooks:

```bash
javap -classpath legacy.jar -private com.example.data.CustomerSnapshot
javap -classpath current.jar -private com.example.data.CustomerSnapshot
javap -classpath current.jar -verbose com.example.data.CustomerSnapshot
```

`javap` inspects declarations/bytecode but does not read stored stream contents itself. Cross-check it against fixture files and classpath tests.

### 19.3. API diff and dependency graph

japicmp, Revapi, or similar tools can assist in comparing class/method/field APIs. However, many serialized fields are private and outside the public API contract; configure diffs appropriately or compare serialized fields, UIDs, and hooks directly.

Use the Gradle/Maven dependency graph to determine which implementation classes are selected at runtime. Upgrading a library version can change concrete classes inside persisted graphs even when the domain root class has not changed.

### 19.4. Logging and observability

Log class names, fixture/version identifiers, UID mismatches, succeeded/failed record conversion counts, processing duration, and validation errors. Never log raw serialized objects or sensitive contents. For batch conversion, track succeeded, skipped, failed, and retryable record counts clearly.

## 20. Strategy for migrating away from Java native serialization

Java Object Serialization fits certain controlled internal mechanisms, yet it is not ideal for business data retained for years or cross-language protocols. It tightly couples to class names and runtime object graphs, increasing class evolution costs.

To reduce long-term risk, consider:

| Option | Advantages | What must be managed |
|---|---|---|
| JSON + schema/version | Human-readable, cross-language integration | Validation, field naming, polymorphism |
| Protobuf | Explicit field numbers and schema evolution | Field-number reuse rules, compatibility |
| Avro | Schema-based serialization, reader/writer schemas | Schema registry, defaults, resolution |
| XML + XSD | Clear contract, common in long-standing integrations | Namespaces, schemas, parser security |
| Database schema | Queryable, mature migration tooling | Transactions, schema/backfills |
| Custom versioned binary codec | Full control over format and overhead | Specification, testing, maintenance cost |

You do not have to migrate all data at once. You can build a **legacy reader → canonical DTO → new writer**:

```text
Legacy .ser files
      |
      v
Isolated legacy reader (trusted inputs, limited permissions)
      |
      v
Validation and explicit version mapping
      |
      v
Canonical DTO/schema
      |
      v
New versioned data format
```

The plan must answer:

1. Who owns the data and what is the retention period?
2. Is offline conversion/halting writes permitted during migration?
3. Do multiple applications read the same state?
4. How long is rollback or dual-read/dual-write required?
5. How is zero data loss verified?
6. Does the system have audit, encryption, and retention requirements?

Do not treat format migration as "done" simply because one test file reads cleanly; inventory, migration batches, reconciliation, and recovery are required.

## 21. Step-by-step migration workflow

### Step 1: Inventory data persistence mechanisms

Search for `ObjectOutputStream`, `ObjectInputStream`, `Serializable`, `Externalizable`, framework cache/session serializers, and file/state storage locations. Determine what data can be discarded, regenerated, or must be retained.

### Step 2: Capture baseline from the production release

Save old binaries, UIDs, class names, object graphs, dependency versions, and fixtures from representative data. Do not generate baselines from refactored source code.

### Step 3: Determine compatibility direction

Decide whether v2 only needs to read v1 or whether v1 must also read v2. Define rolling deployment/rollback requirements and how long multiple versions coexist.

### Step 4: Analyze class evolution

List added/removed/renamed/retyped fields, transient/static changes, hierarchy changes, enums/records/proxies, custom hooks, and Externalizable formats. Compare class descriptors and UIDs.

### Step 5: Design representations or adapters

Keep the same serialized class name/UID where appropriate, add `readObject`/GetField for defaults and validation, or build converters/serialization proxies. For major breaking changes, adopt a new schema-versioned format.

### Step 6: Write compatibility tests

Read v1 golden files on v2 and assert invariants. If bidirectional support is required, read v2 files with v1. Keep producer/consumer classpaths separate.

### Step 7: Test security and malformed data

Restrict data sources, validate streams, configure filters with narrow scope, and test corrupted/truncated payloads. Never read untrusted data directly via native deserialization.

### Step 8: Test on the target artifact and runtime

Test with the exact JDK vendor/build, library/framework versions, container classpath, and production state format. Do not run only from an IDE.

### Step 9: Convert data and monitor

If offline conversion is needed, run in batches with checkpoints, checksums, metrics, and rollback. For live state, define the dual-write/dual-read window and how old versions are retired.

### Step 10: Close the migration with evidence

Archive the UID/class map, compatibility matrix, fixture checksums, test reports, data conversion logs, deployment plan, and recovery procedure. Do not remove the legacy reader until data retention and rollback windows have ended per policy.

## 22. Pre-release checklist

- [ ] Accurately identified where Java Object Serialization is used.
- [ ] Distinguished regenerable cache data from business data that must be preserved.
- [ ] Saved binaries/UIDs/classpaths of versions that wrote old streams.
- [ ] Every serializable class has a controlled `serialVersionUID` policy.
- [ ] Reviewed added, removed, renamed, retyped, `transient`, and `static` fields.
- [ ] Checked all classes in the object graph, not just the root object.
- [ ] Reviewed class/package renames and binary names in streams.
- [ ] Checked superclasses, constructors, `readObjectNoData`, and hierarchies.
- [ ] Reviewed `readObject`/`writeObject`/`readResolve`/`writeReplace`.
- [ ] Checked `Externalizable` classes and custom-format version markers.
- [ ] Checked enum constant renames and record component evolution.
- [ ] Verified generic collection types and runtime cast behavior.
- [ ] Ran golden-file tests: binary v2 reading streams written by binary v1.
- [ ] Where rolling deployment/rollback requires it, verified v1 reads v2 streams.
- [ ] Tested null, empty, nested/cyclic data, and malformed streams.
- [ ] Defined deserialization security policy and input filters.
- [ ] Ran the final artifact on the exact target JDK/library/container runtime.
- [ ] Provided mappings or converters for incompatible changes.
- [ ] Implemented checksums, auditing, and data recovery capabilities.
- [ ] Updated schema/version documentation and legacy reader retention timelines.

**Changing a `Serializable` class is not just a code change:** it can alter the format of data written in the past. Intentionally maintaining `serialVersionUID`, understanding field and hierarchy evolution rules, managing serialization hooks, and testing with golden files generated by old binaries are how you prove a new application version can read legacy data. For long-lived data, a format with an explicit schema/version and a controlled conversion pipeline is usually far more sustainable than tightly coupling stored state to internal Java classes.