# writeReplace, readResolve, and Object Replacement in Java Serialization

## 1. Objectives and Scope

When serializing an object graph with `ObjectOutputStream` and restoring it with `ObjectInputStream`, Java allows an object to **designate another object to replace itself**. The two key hooks are:

- `writeReplace()`: evaluated **before writing the object**; the object can propose another representation to store in the stream.
- `readResolve()`: evaluated **after reading and restoring the object**; the read object can propose another object to return to the caller.

These two mechanisms help design a **serialization proxy**, protect data invariants, rebuild runtime-only resources, and preserve the identity of canonical objects, such as singletons. Be clear about the boundary: replacement occurs during the **serialization/deserialization process**, and does not mean an application's reference variable automatically changes the moment `writeObject` is called.

This lesson applies to Java Object Serialization in `java.io`, prioritizing **Java 17+**; JSON/XML libraries have their own rules and do not automatically invoke these two hooks.

## 2. Foundation: How Does Java Write an Object Graph?

`ObjectOutputStream.writeObject(obj)` processes the root object and the objects it references. Each object can be assigned a **handle** in the stream so repeated references point back to the same written entity. When reading, `ObjectInputStream` uses handles to preserve reference-sharing relationships according to the protocol rules.

In the standard mechanism:

1. The writer identifies the object to serialize and checks whether an appropriate `writeReplace` method exists.
2. If `writeReplace` returns a different representation, Java proceeds to process **that representation** for writing. The replacement object must be valid for serialization (or a special case supported by the format, such as `null`).
3. The reader restores the object according to the descriptor in the stream; this may be the **proxy class** rather than the original class.
4. If the restored class has an appropriate `readResolve`, the return value from that method replaces the object being read in the result and the corresponding reference table, with certain limitations regarding object cycles.
5. The application's `readObject()` receives the final result and typically needs to cast it to the expected contract.

Diagram for the proxy pattern:

~~~text
Writer Application                   Object stream                  Reader Application
Original o                          form of Proxy p                 New Original
    |                                      ^                             ^
    | writeReplace()                       |                             |
    +------------------> Proxy p ---------+                             |
                                                                         |
                         ObjectInputStream -> Proxy p' -> readResolve() --+
~~~

The `'` mark in the diagram denotes a newly restored representation, not the same identity as the proxy created on the writer side.

### 2.1. Standard Hook Signatures

A class implementing `Serializable` (or `Externalizable` when appropriate) can declare:

~~~java
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
~~~

This is an **illustrative snippet placed inside the body of a serializable class**, not a standalone Java program. `ObjectStreamException` belongs to `java.io`, and the `@Serial` annotation also belongs to `java.io` and is supported from Java 14; the `throws` clause may be omitted when the method throws no checked exceptions.

Important requirements:

- The name must be exactly `writeReplace` / `readResolve`, **with no parameters**, and a return type of `Object` in the specified serialization signature. An appropriate access modifier may be used: `private`, package-private, `protected`, or `public`. Inheritance and accessibility follow Java rules; a `private` hook on a superclass is not inherited by subclasses.
- These methods are not APIs you call manually to control the stream; `ObjectOutputStream` / `ObjectInputStream` automatically detect and invoke them when processing an object.
- Because they do not override a method on `Serializable`, **do not annotate them with `@Override`**. Use `@Serial` when appropriate so the compiler can help verify the declaration.
- A serializable class may have only `writeReplace`, only `readResolve`, or both. The hook belongs to **the class actually being written/read**, not necessarily the class initially passed in.

## 3. `writeReplace()`: Replacing the Stored Form Before Writing

### 3.1. When to Use It?

`writeReplace` is often suitable when the runtime model contains things that should not or cannot be persisted directly, such as a `Thread`, connection, executor, temporary resource, or internal structure that you do not want to freeze into a long-term compatibility contract.

Instead of writing every field of the real object, the hook returns a **serialization proxy** consisting of essential, curated data fields. This proxy itself implements `Serializable` and can use `readResolve` to reconstruct a valid object.

Distinguish `writeReplace` from `writeObject`:

| Mechanism | Effect | Result |
| --- | --- | --- |
| `writeObject(ObjectOutputStream)` (class hook) | Customizes how the class's own fields/data are saved | The class remains the class of the written object |
| `writeReplace()` | Proposes **another object** as the stream representation | The class actually written may be a different proxy class |
| `transient` | Skips the field in the default field-saving mechanism | Does not automatically create a proxy, does not change the recorded class |

Marking `transient` is useful when a field is simply a cache; a serialization proxy is useful when you need **full control over the stored representation** or must restore object invariants.

### 3.2. Runnable Example: Proxy Replacing an Object Containing a `Thread`

Create the file `ReplacementProxyDemo.java`:

~~~java
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
~~~

Compile/run from the directory containing the file:

~~~bash
javac ReplacementProxyDemo.java
java ReplacementProxyDemo
~~~

Standard output:

~~~text
T-17
true
true
~~~

Step-by-step explanation:

1. `TaskSession` implements `Serializable` but has `Thread runtimeThread`, and `Thread` is not designed to be serialized as execution state.
2. Before writing the fields of `TaskSession`, `writeReplace()` returns `SessionProxy`. The stored form contains only `taskId`, without the running thread.
3. On read, Java restores `SessionProxy`, then calls `SessionProxy.readResolve()`.
4. `readResolve` creates a new `TaskSession` via its constructor, so `runtimeThread` is freshly initialized and casting the result to `TaskSession` succeeds.

If you remove `writeReplace` while keeping the `runtimeThread` field non-`transient`, writing `TaskSession` will encounter a `NotSerializableException` when traversing that field. The example above intentionally keeps that field **non-transient** to highlight the role of the proxy.

**Notable detail:** `TaskSession.readResolve` is not required in this example; `TaskSession` is not the record type restored from the stream. The required hook lives on **`SessionProxy`** — the class actually being read.

### 3.3. Type Contract and Compatibility

When `writeReplace` returns a proxy of a different type, the final read call must receive a type compatible with its usage site. The proxy is restored and then `readResolve` returns `TaskSession`, so the `TaskSession after` variable receives the right type.

A flawed design can cause `ClassCastException` when the replacement object does not fit the reference site, for example a field expecting `TaskSession` while the final read result is a `String`. You should test when the original object resides **inside a collection or a specifically typed field**, not only when it is the root passed to `writeObject`.

Do not treat the proxy's hiding of the type as encryption or security: the object in the stream still has an inspectable binary structure, and restoration code must still validate data.

## 4. `readResolve()`: Canonicalizing Objects After Reading

### 4.1. Restoring Identity and Invariants

By default, reading a serializable object typically creates a new instance with a different identity from the original instance. For a **singleton**, this model violates the constraint "there is only one instance in the JVM." `readResolve` allows replacing the temporary instance constructed from the stream with the existing canonical instance.

Common scenarios:

- A singleton using a class with a private constructor; `readResolve` returns `INSTANCE`.
- Value objects interned/canonicalized by key; `readResolve` looks up a registry to return the canonical instance.
- A serialization proxy needing to call a validating factory/constructor to restore the real object.

For data that must be verified, validation should reside in the constructor/factory called during restoration. If the data is invalid, you can throw an `InvalidObjectException` (a subclass of `ObjectStreamException`), rather than accepting an object in an invalid state.

### 4.2. Runnable Example: Singleton After Deserialization

Create the file `ReadResolveSingletonDemo.java`:

~~~java
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
~~~

~~~bash
javac ReadResolveSingletonDemo.java
java ReadResolveSingletonDemo
~~~

Output:

~~~text
true
true
true
~~~

The first `readObject()` restores a temporary instance, but `readResolve` returns `AppConfig.INSTANCE`. The next read also references the same singleton instance; the object stream also has a handle mechanism for repeated references.

**Limitation of the example:** `first == second` when writing the same object repeatedly into **one stream** can hold thanks to the handle mechanism, even without `readResolve`. The decisive comparison here is `first == AppConfig.INSTANCE`. To verify thoroughly, try writing and reading across **two independent streams**; the canonical singleton remains the same `INSTANCE` within a JVM thanks to `readResolve`.

### 4.3. Should You Use a Singleton Class Like This?

If you do not need special instantiation behavior and only want a singleton safe against common Java Serialization cases, a Java `enum` with a single constant is usually simpler and stronger:

~~~java
enum AppConfig {
    INSTANCE
}
~~~

This is an **illustrative enum definition**, not a program with `main`. Enum serialization uses a special mechanism: on read, the JVM restores the declared constant by name; user-declared `writeReplace` and `readResolve` on an enum **are not invoked**. For singletons that need to hold separate runtime data, consider lifecycle and thread safety instead of relying solely on hooks.

## 5. Combining `writeReplace` + `readResolve` in the Serialization Proxy Pattern

Common pattern:

1. **Original:** a class with strong invariants, business APIs, and runtime state; implements `Serializable` so the hook operates.
2. **Proxy:** a `private static final` class or a separate class; implements `Serializable`; holds only stable data representations such as an id, simple values, or a key list.
3. **Original.writeReplace():** creates a proxy from the valid state of the original.
4. **Proxy.readResolve():** invokes the original's constructor/factory to check invariants and restore the object.
5. **Original.readObject():** if you want to force every read path through the proxy, you can block direct serialization of the original with a hook that throws `InvalidObjectException`.

The following snippet is **code added inside class Original implements Serializable**, illustrating rejection of reading the original directly without going through the proxy:

~~~java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    throw new InvalidObjectException("Proxy required");
}
~~~

This is not a standalone program. A complete version needs `writeReplace` on the original, a serializable proxy, and `readResolve` on the proxy as in the example in Section 3. In long-lived applications, the version of the **proxy** is the serialized contract that must be maintained; avoid changing the proxy's structure arbitrarily, set `serialVersionUID`, and maintain a clear migration plan.

### 5.1. Short Invariant Example

Suppose a domain object `Range` requires `min <= max`. Never assume serialized bytes entering the JVM always produce valid state. In the proxy, `readResolve` can call `new Range(min, max)`; the constructor checks the invariant and rejects nonsensical data. If you need to translate the error into a consistent I/O exception:

~~~java
@Serial
private Object readResolve() throws ObjectStreamException {
    try {
        return new Range(min, max);  // Constructor checks min <= max.
    } catch (IllegalArgumentException ex) {
        InvalidObjectException invalid =
                new InvalidObjectException("Invalid range");
        invalid.initCause(ex);
        throw invalid;
    }
}
~~~

This is **code inside the proxy class of the Range model**, assuming a `Range(int, int)` constructor exists; it is not a standalone file. Throwing `InvalidObjectException` clearly signals that the read data violates the contract, preventing an invalid object from entering business logic.

## 6. Identity, Handles, and Subtle Limitations

### 6.1. An Object Referenced Multiple Times

`ObjectOutputStream` manages identity using handles. If two fields point to **the same original object**, Java attempts to preserve the sharing relationship during replacement and re-reading: the same written object handle links to the same corresponding replacement result. `writeReplace` does not mean every reference in the graph invokes the hook to create an independent proxy infinitely many times.

However, do not conflate the following concepts:

- **Identity**: `a == b` means the exact same instance in the JVM.
- **Equality**: `a.equals(b)` can be true for two distinct instances.
- **Canonicalization**: multiple objects that are equivalent by key are mapped to one canonical instance when `readResolve` uses a registry/factory.

`readResolve` can intentionally collapse **multiple objects in the stream** into the same instance, altering identity per application policy; that is deliberate behavior, not the default for every read.

### 6.2. Reference Cycles When `readResolve` Returns a New Object

`readResolve` is invoked after the read object has already been constructed, so **references to the temporary object itself inside its own graph may not be updated to the replacement object**. The serialization specification warns that this is an issue with cycles (`cycle`) or self-references. The proxy pattern is generally safer when the proxy contains **simple immutable values**, avoiding circular references back to the original.

Similarly, if `writeReplace` returns a proxy whose graph points back to the original, replacement and reference restoration can produce unexpected structures. Do not use proxy graphs containing arbitrary back-references without round-trip testing.

### 6.3. `readUnshared` Is Not a Defense Against Canonicalization

`ObjectInputStream.readUnshared()` controls how read handles are reused. However, an object with `readResolve` can still return a singleton/instance from a registry that is shared outside the stream. Therefore, `readUnshared` **does not guarantee** the result is a unique new instance in the JVM.

### 6.4. `null` and Replacement Types

A hook can return `null`, but if the caller or a field expects a specific object, the result can be a `NullPointerException` or an invariant violation. Explicitly design and test a "nullable allowed" contract. If a hook returns an instance of a different type, it must be compatible with every usage site in the graph; otherwise, `ClassCastException` or another restoration failure may occur.

## 7. Comparison with Related Hooks and APIs

| Mechanism | Where Declared | Timing / Purpose |
| --- | --- | --- |
| `writeReplace()` | Serializable class | Before writing the object, proposes a replacement object |
| `readResolve()` | Serializable class | After restoring the object, proposes the final value |
| `private void writeObject(ObjectOutputStream)` | Serializable class | Customizes the class's own data section when writing |
| `private void readObject(ObjectInputStream)` | Serializable class | Customizes the class's own data section when reading |
| `ObjectOutputStream.replaceObject(Object)` | Stream subclass | **Stream-level** hook (requires `enableReplaceObject`) to replace objects per custom policy |
| `ObjectInputStream.resolveObject(Object)` | Stream subclass | **Stream-level** hook (requires `enableResolveObject`) to replace objects after the class's `readResolve` step |

Stream-level hooks are an advanced mechanism that affect all data passing through the stream; they differ in ownership and scope from the two class-level hooks. There is no need to subclass the stream just to implement an ordinary proxy or singleton.

**Notes on types:**

- `Serializable` and `Externalizable` support replacement hooks per the specification.
- Enums have dedicated serialization; replacement hooks declared on an enum are ignored.
- A record implementing `Serializable` can use `writeReplace` / `readResolve`, even though normal record field writing/reading differs from traditional serializable classes.
- `serialVersionUID` still pertains to the class actually stored/read. A proxy does not eliminate the need for version management or compatibility.

## 8. Common Mistakes and How to Handle Them

### 8.1. The Hook Does Not Run

Check whether the class actually implements `Serializable`/`Externalizable`, whether the name and signature are exact, and whether you accidentally added parameters or used `static`. For inherited methods, check accessibility under Java rules; a `private` hook on a superclass is not automatically inherited by subclasses. Check whether the actual object is an enum or record if behavior differs from expectations. You may temporarily log in the hook during experiments, then remove the logs before production.

### 8.2. `NotSerializableException` Still Occurs

If `writeReplace` returns a **non-serializable proxy** or the proxy still holds a non-serializable field, writing still fails. Simply noting that the original class has `writeReplace` is not enough; you must inspect the **object graph of the replacement result**.

### 8.3. `ClassCastException` on Read

A proxy with only `writeReplace` and no matching `readResolve` can cause `readObject()` to return the proxy instead of the original. Or `readResolve` returns the wrong type. Check both the root type and any field types referencing the original; do not just force casts and ignore the design issue.

### 8.4. Singleton Gets Duplicated

If a singleton class is deserialized without an appropriate `readResolve` hook, the reader can return a new instance. Keep `INSTANCE` as `static final`, make the constructor non-public, and implement the hook properly; for simple singletons, consider an enum. Remember to check inheritance/subclasses as well if the singleton class is not `final`.

### 8.5. State Is Lost or Differs from Before Saving

A proxy only saves what it holds. If it only holds an id while the domain model needs a timestamp, owner, or other state, the restored copy may be missing information. Identify the **invariants and data that must be preserved** before designing the proxy, rather than dropping fields just to avoid errors.

### 8.6. Old Versions Cannot Be Read

Renaming the proxy class, removing a required field, or changing `serialVersionUID` or restoration logic can break compatibility with old records. Use serialized fixtures from previous versions and test migration. Do not change the UID arbitrarily just to suppress `InvalidClassException`.

### 8.7. Deserializing Untrusted Data

Serialization proxies and `readResolve` **do not make Java deserialization inherently safe**. Do not construct an `ObjectInputStream` on untrusted data if it can be avoided; when necessary, set an `ObjectInputFilter` / allowlist rules, limit size, depth, reference count, and validate data. Hooks can invoke constructors/factories and application logic; never treat hooks as the sole security boundary.

## 9. Design and Testing Checklist

1. Does the original object need to preserve **value** or **identity**? If only simple fields are needed, replacement hooks may be unnecessary.
2. If using a proxy, have you selected enough fields for restoration while avoiding runtime resources and cycle-forming back-references?
3. Is the proxy `Serializable`, with a stable UID, and does `readResolve` return a type compatible with every field/caller?
4. Is input validated in the constructor/factory or hook, throwing an appropriate exception if invalid?
5. Have you tested round-trip for a single object, multiple references to the same object, null values, collections, historical data, and corrupted data cases?
6. If singleton/canonicalization is required, have you verified identity against the canonical instance, including across independent streams?
7. Is there a versioning/migration strategy and controls for untrusted data?

When testing, separate **ability to write the stream**, **ability to restore accurate values**, and **correctness of identity/invariants** into distinct checks; `readObject` not throwing an exception does not guarantee those three properties.

## 10. Self-Check Questions

**Question 1.** Is `writeReplace` called on the reader side or the writer side? Does it make an application's `original` variable point to the proxy after `writeObject(original)`?

**Answer:** On the writer side, before writing the object. It does not change the `original` reference variable in application memory; it only governs the data form and reference mapping written into the stream.

**Question 2.** Class `Employee` has `writeReplace` returning `EmployeeProxy`. When reading back, where should the `readResolve` hook be placed to return `Employee`?

**Answer:** Typically on `EmployeeProxy`, because the stream contains the proxy's representation. `EmployeeProxy.readResolve()` can construct/look up a valid `Employee` and return it.

**Question 3.** Reading the same singleton twice from one stream returns objects equal by `==`. Does that alone prove `readResolve` works?

**Answer:** No. The stream has a handle mechanism for repeated references. You need to compare against the canonical singleton, or test across multiple independent streams.

**Question 4.** `readResolve` returns a `String` for a field typed as `Employee`. What is the risk?

**Answer:** Type incompatibility; restoration or usage may throw `ClassCastException`. You must preserve the type contract at all reference sites.

**Question 5.** Why should you avoid having a proxy point circularly back to the original?

**Answer:** Replacement combined with handles and cycles can cause the restored graph to differ from the expected graph; specifically, `readResolve` runs after the temporary object is complete, so self-references may not be updated. A value-only proxy reduces this risk.

## 11. Technical Sources for Deeper Reference

- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): signatures, access scope, and replacement hooks.
- [Java Object Serialization Specification — Object Output Classes, Section 2.5](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/output.html): `writeReplace`, object mapping during writing.
- [Java Object Serialization Specification — Object Input Classes, Section 3.7](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html): `readResolve`, handle processing, and limitations with cyclic graphs.
- [Java Object Serialization Specification — System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): serialization graph, enum, record, and replacement.

Both hooks are **object replacement mechanisms at the stream boundary**. `writeReplace` chooses the stored form, and `readResolve` chooses the value used after reading; when combined into a serialization proxy, they help maintain an object's data contract and invariants deliberately.
