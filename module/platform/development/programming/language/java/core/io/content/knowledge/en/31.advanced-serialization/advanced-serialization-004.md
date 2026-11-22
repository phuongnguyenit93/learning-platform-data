# writeReplace, readResolve, and Object Replacement in Java Serialization

## 1. Goals and Scope

When serializing an object graph with `ObjectOutputStream` and restoring it with `ObjectInputStream`, Java allows an object to **designate another object to take its place**. The two key hooks are:

- `writeReplace()`: evaluated **before writing the object**; the object may propose an alternative representation to store in the stream.
- `readResolve()`: evaluated **after reading and restoring the object**; the restored object may propose another object to return to the caller.

These two mechanisms support designing a **serialization proxy**, protecting data invariants, reconstructing runtime-only resources, and preserving the identity of canonical objects such as singletons. Be clear about the boundary: replacement occurs during the **serialization/deserialization process**; it does not mean the application's local reference variable changes immediately when calling `writeObject`.

This lesson applies to Java Object Serialization in `java.io`, targeting **Java 17+**; JSON/XML libraries follow their own rules and do not automatically invoke these two hooks.

## 2. Background: How Does Java Write an Object Graph?

`ObjectOutputStream.writeObject(obj)` processes the root object and the objects it references. Each object can be assigned a **handle** in the stream so that repeated references point back to the same written entity. When reading, `ObjectInputStream` uses handles to preserve reference-sharing relationships per protocol rules.

In the standard flow:

1. The writer identifies the object to serialize and checks whether an appropriate `writeReplace` method exists.
2. If `writeReplace` returns a different representation, Java continues by serializing **that representation**. The replacement object must be valid for serialization (or a special case supported by the format, such as `null`).
3. The reader restores the object according to the descriptor in the stream; this may be the **proxy class** rather than the original class.
4. If the restored class has an appropriate `readResolve`, the value returned by that method replaces the read object in the result and the corresponding reference table, subject to certain cycle limitations.
5. The application's `readObject()` receives the final result and usually casts it to the expected contract.

Diagram for the proxy pattern:

```text
Writing application                  Object stream                  Reading application
Original o                           form of Proxy p                New Original
    |                                      ^                             ^
    | writeReplace()                       |                             |
    +------------------> Proxy p ---------+                             |
                                                                         |
                         ObjectInputStream -> Proxy p' -> readResolve() --+
```

The `'` mark in the diagram denotes a newly restored representation, not the same identity as the proxy created on the writing side.

### 2.1. Standard Hook Signatures

A class implementing `Serializable` (or `Externalizable` where appropriate) can declare:

```java
@Serial
private Object writeReplace() throws ObjectStreamException {
    // Return an object that can be stored in the stream.
    return this;
}

@Serial
private Object readResolve() throws ObjectStreamException {
    // Return the object the application will use after reading.
    return this;
}
```

This is **illustrative code placed inside the body of a serializable class**, not a standalone Java program. `ObjectStreamException` belongs to `java.io`, and `@Serial` also belongs to `java.io` (supported since Java 14); the `throws` clause may be omitted if the method throws no checked exceptions.

Key requirements:

- Names must be exact: `writeReplace` / `readResolve`, **no parameters**, return type `Object` in the specified serialization signature. Any appropriate access modifier can be used: `private`, package-private, `protected`, or `public`. Inheritance and accessibility follow standard Java rules; a `private` hook on a superclass is not inherited by subclasses.
- These methods are not APIs you call manually to drive the stream; `ObjectOutputStream` / `ObjectInputStream` automatically detect and invoke them when processing objects.
- Because they do not override any method of `Serializable`, **do not write `@Override`**. Use `@Serial` where appropriate so the compiler can help verify declarations.
- A serializable class may have only `writeReplace`, only `readResolve`, or both. The hook lives on **the class actually being written or read**, not necessarily on the class initially passed.

## 3. `writeReplace()`: Changing the Storage Form Before Writing

### 3.1. When to Use?

`writeReplace` is often suited when a runtime model contains things that should not or cannot be persisted directly—such as a `Thread`, connection, executor, temporary resource, or internal structure you do not want to freeze into a long-term compatibility contract.

Instead of writing all fields of the real object, the hook returns a **serialization proxy** containing selected, essential data fields. This proxy itself implements `Serializable` and can use `readResolve` to reconstruct a valid object.

Distinguish `writeReplace` from `writeObject`:

| Mechanism | Effect | Result |
| --- | --- | --- |
| `writeObject(ObjectOutputStream)` (class hook) | Customizes how that class's own fields/data are saved | The class remains the class of the object written |
| `writeReplace()` | Proposes **another object** as the representation in the stream | The class actually written can be a different proxy class |
| `transient` | Excludes a field from the default field-saving mechanism | Does not create a proxy or change the recorded class |

Marking `transient` is handy when a field is simply a cache; a serialization proxy is useful when you need **full control over the persisted form** or must enforce object invariants on restoration.

### 3.2. Runnable Example: Proxy Replacing an Object Containing a `Thread`

Create `ReplacementProxyDemo.java`:

```java
import java.io.*;

public class ReplacementProxyDemo {
    static final class TaskSession implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String taskId;
        private final Thread runtimeThread = new Thread();

        TaskSession(String taskId) {
            this.taskId = taskId;
        }

        @Serial
        private Object writeReplace() throws ObjectStreamException {
            return new SessionProxy(taskId);
        }
    }

    private static final class SessionProxy implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String taskId;

        SessionProxy(String taskId) {
            this.taskId = taskId;
        }

        @Serial
        private Object readResolve() throws ObjectStreamException {
            return new TaskSession(taskId);
        }
    }

    public static void main(String[] args) throws Exception {
        TaskSession before = new TaskSession("T-17");
        var bytes = new ByteArrayOutputStream();

        try (var out = new ObjectOutputStream(bytes)) {
            out.writeObject(before);
        }

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            TaskSession after = (TaskSession) in.readObject();
            System.out.println(after.taskId);
            System.out.println(after.runtimeThread != null);
            System.out.println(after.getClass() == TaskSession.class);
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac ReplacementProxyDemo.java
java ReplacementProxyDemo
```

Expected output:

```text
T-17
true
true
```

Step-by-step explanation:

1. `TaskSession` implements `Serializable` but holds `Thread runtimeThread`, and `Thread` is not designed to be serialized as execution state.
2. Before writing `TaskSession`'s fields, `writeReplace()` returns `SessionProxy`. The serialized form holds only `taskId`, without the running thread.
3. When reading, Java restores `SessionProxy`, then calls `SessionProxy.readResolve()`.
4. `readResolve` constructs a new `TaskSession` via its constructor, so `runtimeThread` is freshly initialized and casting to `TaskSession` succeeds.

If you remove `writeReplace` while keeping `runtimeThread` non-`transient`, writing `TaskSession` throws `NotSerializableException` when traversing that field. The example intentionally leaves that field **non-transient** to highlight the proxy's role.

**Key detail:** `TaskSession.readResolve` is not needed in this example; `TaskSession` is not the record type restored from the stream. The required hook belongs on **`SessionProxy`** — the class actually read.

### 3.3. Type Contracts and Compatibility

When `writeReplace` returns a proxy of a different type, the final read call must receive a type compatible with the usage site. The proxy is restored and then `readResolve` returns `TaskSession`, so `TaskSession after` receives the expected type.

A flawed design can throw `ClassCastException` when the replacement object does not fit the reference site—for instance, a field expecting `TaskSession` when the final read result is a `String`. Test when the original object sits **inside a collection or a typed field**, not only when it is the root passed to `writeObject`.

Do not rely on a proxy hiding a type as encryption or security: the object in the stream still has an inspectable binary structure, and restoration code must still validate data.

## 4. `readResolve()`: Canonicalizing an Object After Reading

### 4.1. Restoring Identity and Invariants

By default, reading a serializable object creates a new instance with a different identity from the original instance. For a **singleton**, this violates the constraint "only one instance exists in the JVM." `readResolve` lets you substitute the temporary instance reconstructed from the stream with the existing canonical instance.

Common scenarios:

- A singleton using a class with a private constructor; `readResolve` returns `INSTANCE`.
- Value objects interned/canonicalized by key; `readResolve` looks up a registry to return the canonical instance.
- A serialization proxy needing to invoke a validating factory/constructor to reconstruct the real object.

For data that must be verified, validation should live in the constructor/factory called during restoration. If the data is invalid, throw an `InvalidObjectException` (a subclass of `ObjectStreamException`) rather than accepting a malformed object.

### 4.2. Runnable Example: Singleton After Deserialization

Create `ReadResolveSingletonDemo.java`:

```java
import java.io.*;

public class ReadResolveSingletonDemo {
    static final class AppConfig implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        static final AppConfig INSTANCE = new AppConfig();

        private AppConfig() {}

        @Serial
        private Object readResolve() throws ObjectStreamException {
            return INSTANCE;
        }
    }

    public static void main(String[] args) throws Exception {
        var bytes = new ByteArrayOutputStream();

        try (var out = new ObjectOutputStream(bytes)) {
            out.writeObject(AppConfig.INSTANCE);
            out.writeObject(AppConfig.INSTANCE);
        }

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            AppConfig first = (AppConfig) in.readObject();
            AppConfig second = (AppConfig) in.readObject();

            System.out.println(first == AppConfig.INSTANCE);
            System.out.println(second == AppConfig.INSTANCE);
            System.out.println(first == second);
        }
    }
}
```

```bash
javac ReadResolveSingletonDemo.java
java ReadResolveSingletonDemo
```

Output:

```text
true
true
true
```

The first `readObject()` restores a temporary instance, but `readResolve` returns `AppConfig.INSTANCE`. The next read also refers to the same singleton instance; the object stream additionally has its handle mechanism for repeated references.

**Limitation of this example:** `first == second` when writing the same object twice to **the same stream** can hold thanks to stream handles even without `readResolve`. The decisive comparison here is `first == AppConfig.INSTANCE`. To verify thoroughly, try writing and reading across **two independent streams**; the canonical singleton remains the exact `INSTANCE` in the JVM thanks to `readResolve`.

### 4.3. Should You Write Singleton Classes This Way?

If you do not need special instantiation behavior and only want a singleton resilient against common Java Serialization pitfalls, a Java `enum` with a single constant is usually simpler and stronger:

```java
enum AppConfig {
    INSTANCE
}
```

This is an **illustrative enum definition**, not a program with `main`. Enum serialization uses a specialized mechanism: when reading, the JVM resolves the declared constant by name; any user-declared `writeReplace` and `readResolve` methods on an enum **are ignored**. For singletons that need separate mutable runtime state, consider lifecycle and thread safety rather than relying solely on hooks.

## 5. Combining `writeReplace` + `readResolve` in the Serialization Proxy Pattern

Typical structure:

1. **Original:** class with strong invariants, business API, and runtime state; implements `Serializable` so hooks are active.
2. **Proxy:** `private static final` class or separate class; implements `Serializable`; stores only stable data such as IDs, simple values, or key lists.
3. **Original.writeReplace():** builds the proxy from the original's valid state.
4. **Proxy.readResolve():** calls the original's constructor/factory to check invariants and reconstruct the object.
5. **Original.readObject():** if you want to force all deserialization through the proxy, block direct serialization of the original via a hook throwing `InvalidObjectException`.

The following code is **added inside the Original class implementing Serializable**, illustrating how to reject direct reads of the original that bypass the proxy:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    throw new InvalidObjectException("Proxy required");
}
```

This is not a standalone program. A complete implementation needs `writeReplace` on the original, a serializable proxy, and `readResolve` on the proxy as shown in Section 3. In a long-lived application, the **proxy's** version becomes the serialized contract to maintain; avoid arbitrary structural changes to the proxy, declare an explicit `serialVersionUID`, and keep a clear migration plan.

### 5.1. Short Example of Invariants

Suppose business object `Range` requires `min <= max`. Never assume serialized bytes fed into the JVM always produce valid state. Inside the proxy, `readResolve` can invoke `new Range(min, max)`; the constructor validates the invariant and rejects nonsensical data. To translate failures into a consistent I/O exception:

```java
@Serial
private Object readResolve() throws ObjectStreamException {
    try {
        return new Range(min, max);  // Constructor validates min <= max.
    } catch (IllegalArgumentException ex) {
        InvalidObjectException invalid =
                new InvalidObjectException("Invalid range");
        invalid.initCause(ex);
        throw invalid;
    }
}
```

This is **code inside the Range model's proxy class**, assuming a `Range(int, int)` constructor exists; not a standalone file. Throwing `InvalidObjectException` clearly signals that the read data violated the contract, preventing corrupted objects from entering business logic.

## 6. Identity, Handles, and Subtle Limitations

### 6.1. An Object Referenced Multiple Times

`ObjectOutputStream` tracks identity using handles. If two fields point to **the same original object**, Java strives to preserve shared references across replacement and restoration: the same written object handle resolves to the same corresponding replacement result. `writeReplace` does not cause every reference in the graph to invoke the hook and emit arbitrarily many independent proxies.

However, do not conflate these concepts:

- **Identity:** `a == b` means the exact same instance in the JVM.
- **Equality:** `a.equals(b)` can be true for two distinct instances.
- **Canonicalization:** multiple key-equivalent objects are mapped to one canonical instance when `readResolve` consults a registry/factory.

`readResolve` can deliberately collapse **multiple objects in the stream** into a single instance, altering identity per application policy; that is intentional behavior, not the default for every read.

### 6.2. Reference Cycles When `readResolve` Returns a New Object

`readResolve` runs after the read object is already constructed, so **references pointing to that temporary object from within its own graph may not be updated to the replacement object**. The serialization specification warns about this issue with cycles or self-references. The proxy pattern is safer when the proxy holds **simple immutable values**, avoiding circular back-references to the original.

Similarly, if `writeReplace` returns a proxy whose graph points back to the original, replacement and reference restoration can yield an unexpected graph structure. Avoid arbitrary back-referencing proxy graphs without thorough round-trip tests.

### 6.3. `readUnshared` Does Not Prevent Canonicalization

`ObjectInputStream.readUnshared()` controls how read-back handles are shared. However, an object with `readResolve` can still return a singleton or registry instance shared outside the stream. Thus, `readUnshared` **does not guarantee** the result is a unique newly allocated instance in the JVM.

### 6.4. `null` and Replacement Types

A hook can return `null`, yet if the caller or field expects a concrete object, `NullPointerException` or an invariant violation can ensue. Explicitly design and test any "nullable" contract. If a hook returns an instance of a different type, it must be compatible with every reference site in the graph; otherwise, `ClassCastException` or restoration failures can occur.

## 7. Comparison with Related Hooks and APIs

| Mechanism | Where Declared | Timing / Purpose |
| --- | --- | --- |
| `writeReplace()` | Serializable class | Before writing object; proposes replacement object |
| `readResolve()` | Serializable class | After restoring object; proposes final returned value |
| `private void writeObject(ObjectOutputStream)` | Serializable class | Customizes the class's own written data section |
| `private void readObject(ObjectInputStream)` | Serializable class | Customizes the class's own read data section |
| `ObjectOutputStream.replaceObject(Object)` | Stream subclass | **Stream-level** hook (requires `enableReplaceObject`) to replace objects per stream policy |
| `ObjectInputStream.resolveObject(Object)` | Stream subclass | **Stream-level** hook (requires `enableResolveObject`) to replace objects after class `readResolve` |

Stream-level hooks are advanced mechanisms affecting all data passing through a stream; they differ in ownership and scope from the two class-level hooks. You do not need to subclass the stream just to implement a normal proxy or singleton.

**Notes on types:**

- `Serializable` and `Externalizable` both support replacement hooks per the specification.
- Enums have specialized serialization; replacement hooks declared on an enum are ignored.
- Records implementing `Serializable` can use `writeReplace` / `readResolve`, although normal record field reading/writing differs from traditional serializable classes.
- `serialVersionUID` still applies to the class actually stored and read. Using a proxy does not eliminate the need for version and compatibility management.

## 8. Common Mistakes and How to Fix Them

### 8.1. Hook Does Not Run

Check whether the class actually implements `Serializable`/`Externalizable`, whether the name and signature are exact, and whether a parameter or `static` was added by mistake. For inherited methods, check Java access rules; a `private` hook in a superclass is not inherited by subclasses. Check if the runtime object is an enum or record if behavior differs from expectations. You can temporarily log inside the hook during experiments, then remove logs before production.

### 8.2. `NotSerializableException` Still Occurs

If `writeReplace` returns a **non-serializable proxy** or a proxy still holding a non-serializable field, writing still fails. Simply adding `writeReplace` to the original class is not enough; inspect the **object graph of the replacement result**.

### 8.3. `ClassCastException` When Reading

A proxy with `writeReplace` but missing an appropriate `readResolve` can cause `readObject()` to return the proxy instead of the original. Or `readResolve` returns the wrong type. Check both the root type and any field types referencing the original; never mask a design flaw with an unsafe cast.

### 8.4. Singleton Gets Duplicated

If a singleton class is deserialized without an appropriate `readResolve` hook, the reader can return a new instance. Keep `INSTANCE` `static final`, keep the constructor non-public, and implement the hook properly; for simple singletons, consider an enum. Also check inheritance/subclasses if the singleton class is not `final`.

### 8.5. State Lost or Altered After Saving

A proxy saves only what it contains. If it holds only an id while the domain model needs a timestamp, owner, or other status, the restored object may miss information. Identify **all invariants and required data** before designing the proxy rather than dropping fields just to avoid errors.

### 8.6. Older Versions Fail to Read

Renaming a proxy class, removing a required field, changing `serialVersionUID`, or altering restoration logic can break compatibility with old records. Use serialized fixtures from older versions and test migrations. Never arbitrarily change a UID to hide `InvalidClassException`.

### 8.7. Deserializing Untrusted Data

Serialization proxies and `readResolve` **do not make Java deserialization inherently safe**. Avoid creating an `ObjectInputStream` on untrusted data whenever possible; when necessary, configure an `ObjectInputFilter` / allowlist rules, and limit size, depth, and reference counts while validating data. Hooks can trigger constructors/factories and application logic; never treat hooks as your sole security layer.

## 9. Design and Testing Checklist

1. Does the original object need to preserve **value** or **identity**? If simple fields suffice, replacement hooks may be unnecessary.
2. When using a proxy, have you selected all fields needed for restoration while avoiding runtime resources and cyclic back-references?
3. Is the proxy `Serializable` with a stable UID, and does `readResolve` return a type compatible with all fields/callers?
4. Is input validated inside constructors/factories or hooks, throwing appropriate exceptions if invalid?
5. Have you tested round-trips for a single object, shared references to the same object, null values, collections, historical data, and corrupted payloads?
6. If singleton/canonicalization is required, have you verified identity against the canonical instance, including across independent streams?
7. Do you have a version/migration strategy and controls against untrusted data?

When testing, separate **ability to write the stream**, **ability to restore accurate values**, and **correctness of identity/invariants** into distinct checks; `readObject` not throwing an exception does not guarantee all three.

## 10. Self-Check Questions

**Question 1.** Is `writeReplace` invoked on the writing side or the reading side? Does it cause the application's `original` variable to point to the proxy after `writeObject(original)`?

**Answer:** On the writing side, before writing the object. It does not alter the `original` reference variable in application memory; it only governs the serialized representation and reference mapping written to the stream.

**Question 2.** Class `Employee` has `writeReplace` returning `EmployeeProxy`. When reading back, where should `readResolve` be placed to return `Employee`?

**Answer:** Usually on `EmployeeProxy`, because the stream contains the proxy's representation. `EmployeeProxy.readResolve()` can construct or look up a valid `Employee` and return it.

**Question 3.** Reading the same singleton twice from a single stream returns objects equal by `==`. Does that alone prove `readResolve` is working?

**Answer:** No. The stream has a handle mechanism for repeated references. You must compare against the canonical singleton, or test across multiple independent streams.

**Question 4.** `readResolve` returns a `String` for a field typed as `Employee`. What is the risk?

**Answer:** Type incompatibility; restoration or subsequent usage can throw `ClassCastException`. Type contracts must hold at every reference site.

**Question 5.** Why should a proxy avoid circular references pointing back to the original?

**Answer:** Replacement combined with handles and cycles can yield a restored graph different from expectations; specifically, `readResolve` runs after the temporary object is built, so self-references may not be updated. A pure value proxy minimizes this risk.

## 11. Technical References for Deeper Study

- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): signatures, access modifiers, and replacement hooks.
- [Java Object Serialization Specification — Object Output Classes, Section 2.5](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/output.html): `writeReplace` and object mapping during writing.
- [Java Object Serialization Specification — Object Input Classes, Section 3.7](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html): `readResolve`, handle processing, and limits with cyclic graphs.
- [Java Object Serialization Specification — System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): serialization graphs, enums, records, and replacement.

Both hooks are mechanisms for **object replacement at the stream boundary**. `writeReplace` selects the storage representation, and `readResolve` selects the value used after reading; combined into a serialization proxy, they let you enforce data contracts and object invariants intentionally.
