# Constructors of Serializable Classes and Non-Serializable Superclasses

## 1. The Core Question

When calling `new` to create a Java object, constructors across the inheritance chain run according to standard object-initialization rules. However, when using **Java Object Serialization** with `ObjectInputStream.readObject()` to restore an object whose class implements `java.io.Serializable`, constructor rules **differ significantly**.

**Rule to remember:** During default *deserialization* of an ordinary `Serializable` class, **constructors of the `Serializable` class itself and any `Serializable` superclasses are not called**. Instead, Java **invokes the accessible, no-argument constructor of the nearest superclass that does not implement `Serializable`**. From that constructor, constructors of non-`Serializable` ancestors continue executing via normal `super()` chaining.

Example:

```text
Object                 (not Serializable)
   |
   v
Base                   (not Serializable)  <-- no-arg constructor IS called
   |
   v
Account                (implements Serializable) <-- constructor does NOT run
   |
   v
PremiumAccount         (inherits Serializable) <-- constructor does NOT run

new PremiumAccount()                -> Object -> Base -> Account -> PremiumAccount
ObjectInputStream.readObject()      -> Object -> Base
                                   -> restore fields of Account/PremiumAccount
```

This diagram is simplified to illustrate constructors for the object being restored; the actual process also resolves descriptors, handles, references, string objects, and serialization hooks.

In particular, **never say "deserialization runs no constructors at all."** More accurately: it **does not run constructors of classes in the `Serializable` segment of the hierarchy**, yet it **still runs the no-argument constructor of the nearest non-`Serializable` superclass** and whatever ancestor constructors it invokes.

This topic governs which fields get restored, which fields get freshly initialized, and why lacking an appropriate superclass constructor can make `readObject()` fail.

## 2. `Serializable` Is Only a Marker Interface

`java.io.Serializable` is a **marker interface**: it declares no mandatory methods to implement. A class that directly writes `implements Serializable` or **inherits** from a class already implementing it belongs to the default serializable group, provided other serialization requirements are met.

```java
import java.io.Serializable;

class Parent {
    Parent() { }
}

class Child extends Parent implements Serializable {
    private static final long serialVersionUID = 1L;

    Child() {
        super();
    }
}
```

This is an illustrative snippet without `main`. `Parent` **does not** need to implement `Serializable` for `Child` to become `Serializable`. However, `Parent` being non-`Serializable` has consequences:

- **Fields declared in `Parent` are not automatically saved and restored by default Java serialization**.
- When deserializing a `Child`, Java invokes **`Parent`'s valid no-arg constructor**.
- `Child`'s constructor is not called; `Child`'s serializable fields are restored from the stream instead of initialized via a normal constructor.

Note: `Serializable` is inherited as a class capability. If `GrandParent implements Serializable`, `Parent extends GrandParent`, and `Child extends Parent`, both `Parent` and `Child` are `Serializable` even without repeating `implements Serializable`.

## 3. Why Do Constructors Behave Differently from `new`?

### 3.1. Creating an Object with `new`

In ordinary Java:

```java
Child child = new Child();
```

In principle, constructor order is:

1. JVM object allocation.
2. Constructor of the top-level class without an explicit parent, such as `Object()`, runs along the `super` chain.
3. Superclass constructors execute top-down.
4. The concrete `Child` constructor runs; field initializers and instance initializer blocks execute in Java initialization order.

If `Child`'s fields or constructor call `super(args)`, the corresponding ordering rules apply.

### 3.2. Restoring with `readObject()`

When calling:

```java
Child restored = (Child) objectInput.readObject();
```

the serialization mechanism must reconstruct the **persisted state** of the serializable portion, rather than "calling `new Child()` and overwriting a few fields" like ordinary application code.

Therefore:

- `Child`'s constructor does not run.
- **Instance field initializers** and **instance initializer blocks** of classes in the `Serializable` portion of the inheritance chain do not run.
- Constructors of intermediate `Serializable` superclasses do not run.
- The selected no-argument constructor of the nearest **non**-`Serializable` superclass does run; that constructor may in turn invoke its non-serializable superclass.
- Afterward, fields belonging to the serializable classes are restored from stream data via Object Serialization mechanics.

**Important:** static initialization is a separate JVM mechanism. When a class is first initialized, static initializers can execute per class-initialization rules; do not confuse that with instance constructors being called for each deserialized object.

## 4. Java 17 Example: Which Constructor Runs and Which Fields Are Preserved?

The following standalone program uses a **non-Serializable** superclass and a **Serializable** subclass.

Upon creation, the superclass sets `baseValue = 10`; the subclass constructor overrides it to `99` and sets `childValue = 77`. After writing and reading the object via a stream, the superclass constructor runs again and sets `baseValue = 10`, whereas the subclass constructor does not run. Because `baseValue` is a field of the non-Serializable superclass, the value `99` **is not automatically restored**; `childValue` belongs to the Serializable subclass and is restored as `77`.

**File `SerializableConstructorDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class SerializableConstructorDemo {
    static class Base {
        int baseValue;

        Base() {
            System.out.println("Base constructor");
            baseValue = 10;
        }
    }

    static class Child extends Base implements Serializable {
        private static final long serialVersionUID = 1L;

        int childValue;

        Child() {
            // super() is inserted by the compiler by default.
            System.out.println("Child constructor");
            baseValue = 99;
            childValue = 77;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        Child original = new Child();
        System.out.println("Before: base=" + original.baseValue
                + ", child=" + original.childValue);

        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                     new ObjectOutputStream(memory)) {
            output.writeObject(original);
        }

        Child restored;
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(memory.toByteArray()))) {
            restored = (Child) input.readObject();
        }

        System.out.println("After: base=" + restored.baseValue
                + ", child=" + restored.childValue);
    }
}
```

Compile and run with JDK 17+:

```bash
javac SerializableConstructorDemo.java
java SerializableConstructorDemo
```

**Exact stdout when the program succeeds:**

```text
Base constructor
Child constructor
Before: base=99, child=77
Base constructor
After: base=10, child=77
```

**Analysis:**

1. `new Child()`: runs `Base()` then `Child()`, yielding `baseValue=99` and `childValue=77`.
2. `ObjectOutputStream.writeObject(original)`: saves the `Serializable` state of `Child`. It does not automatically save `Base.baseValue` under default mechanics because `Base` is not `Serializable`.
3. `ObjectInputStream.readObject()`: the JVM allocates a `Child` instance via restoration mechanics, **without calling `Child()`**.
4. `Base()` is called because `Base` is the nearest non-Serializable superclass with a valid no-argument constructor, setting `baseValue=10`.
5. `childValue` belongs to the `Serializable` portion and is restored from the stream as `77`.

This is the clearest empirical verification: the second time, the output prints **`Base constructor`** but **not `Child constructor`**.

## 5. What If Multiple Serializable Classes Inherit from One Another?

Suppose:

```text
PlainRoot              not Serializable
   |
   +-- SerialParent    implements Serializable
          |
          +-- SerialChild  extends SerialParent
```

When restoring a `SerialChild`:

- Constructor `PlainRoot()` runs.
- Constructor `SerialParent()` **does not run**.
- Constructor `SerialChild()` **does not run**.
- Serializable fields of **both `SerialParent` and `SerialChild`** are restored from the stream, except fields excluded by default serialization (such as `transient`).

Classes below `SerialParent` are automatically `Serializable` by inheritance. Whether they define a no-arg constructor **does not determine** constructor invocation during default deserialization.

### Java 17 Example: Three-Level Inheritance

**File `SerializationHierarchyDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class SerializationHierarchyDemo {
    static class PlainRoot {
        int rootNumber;

        PlainRoot() {
            System.out.println("PlainRoot()");
            rootNumber = 1;
        }
    }

    static class SerialParent extends PlainRoot
            implements Serializable {
        private static final long serialVersionUID = 1L;

        int parentNumber;

        SerialParent() {
            System.out.println("SerialParent()");
            rootNumber = 99;
            parentNumber = 2;
        }
    }

    static class SerialChild extends SerialParent {
        private static final long serialVersionUID = 1L;

        int childNumber;

        SerialChild() {
            System.out.println("SerialChild()");
            childNumber = 3;
        }
    }

    public static void main(String[] args) throws Exception {
        SerialChild before = new SerialChild();

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                     new ObjectOutputStream(bytes)) {
            output.writeObject(before);
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            SerialChild after = (SerialChild) input.readObject();
            System.out.println("Values: " + after.rootNumber
                    + ", " + after.parentNumber
                    + ", " + after.childNumber);
        }
    }
}
```

Compile and run:

```bash
javac SerializationHierarchyDemo.java
java SerializationHierarchyDemo
```

**Exact stdout if I/O succeeds:**

```text
PlainRoot()
SerialParent()
SerialChild()
PlainRoot()
Values: 1, 2, 3
```

**Why `root=1` instead of `99`?** `rootNumber` is declared on the non-Serializable class `PlainRoot`. When instantiating with `new`, `SerialParent()` changed it to `99`; however, deserialization skips `SerialParent()` and invokes `PlainRoot()`, resetting it to `1`. The two serializable fields `parentNumber` and `childNumber` are restored as `2` and `3` from the stream.

## 6. The Constructor Must Exist on the **First Non-Serializable Superclass**

Suppose `Child implements Serializable` and `Base` is its direct non-Serializable superclass. `ObjectInputStream` requires a **valid no-argument constructor** on `Base` to restore the object.

### 6.1. Acceptable

```java
class Base {
    protected Base() {
        // Set up foundational state.
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    Child(int value) {
        super();
    }
}
```

Because `Base()` is `protected`, it is accessible to subclasses under Java access rules. Whether `Child(int)` takes parameters **does not matter for constructor invocation during deserialization**, because `Child`'s constructor is not used under default mechanics.

### 6.2. Missing No-Argument Constructor

```java
class Base {
    Base(int value) {
        // No no-arg Base() declared.
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    Child() {
        super(42);
    }
}
```

**This code compiles**, because `Child()` explicitly calls `super(42)` during normal construction. Yet `Base` **lacks a no-arg constructor**, so deserializing a regular `Child` cannot perform superclass initialization and fails with `InvalidClassException` reporting no valid constructor.

That is not a compile-time error. **The fact that `new Child()` and `writeObject(child)` succeed does not prove `readObject()` will succeed.**

### 6.3. Private or Inaccessible Constructor

The chosen constructor of the non-Serializable superclass must be **accessible to the subclass that is `Serializable`** according to the Java Object Serialization Specification.

- A `public` or `protected` no-arg constructor is generally a clear choice.
- A *package-private* no-arg constructor works only in a matching access context (e.g., same package).
- A `private` constructor cannot be accessed by a normal subclass; having a private no-arg constructor **does not** satisfy the requirement.
- Module/package access boundaries can create visibility issues in complex designs.

**Do not oversimplify this to "there must be a public no-arg constructor."** For regular `Serializable`, `protected` or contextually accessible no-arg constructors are also valid; the **`public`** requirement applies prominently to `Externalizable`, a separate mechanism compared below.

## 7. Java 17 Example: Missing No-Arg Constructor Leads to InvalidClassException

This example intentionally defines a class whose superclass has only a one-argument constructor. It demonstrates:

- The subclass constructor used for `new` works fine.
- Serialization via `writeObject` completes.
- **Deserialization fails** because the superclass provides no valid no-arg constructor.

**File `MissingSuperclassConstructorDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class MissingSuperclassConstructorDemo {
    static class Base {
        int value;

        Base(int value) {
            this.value = value;
        }
    }

    static class Child extends Base implements Serializable {
        private static final long serialVersionUID = 1L;

        Child() {
            super(42);
        }
    }

    public static void main(String[] args) throws Exception {
        Child original = new Child();
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (ObjectOutputStream output =
                     new ObjectOutputStream(sink)) {
            output.writeObject(original);
        }

        System.out.println("Write succeeded");

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(sink.toByteArray()))) {
            input.readObject();
            System.out.println("Read succeeded");
        } catch (InvalidClassException ex) {
            System.out.println("Read failed: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac MissingSuperclassConstructorDemo.java
java MissingSuperclassConstructorDemo
```

**Exact stdout when the expected error occurs:**

```text
Write succeeded
Read failed: InvalidClassException
```

The detailed message of `InvalidClassException` may vary across JDKs/implementations. Therefore the program prints only **the exception class name**, without assuming a fixed message string.

Appropriate fix if you have permission to edit the superclass:

```java
class Base {
    int value;

    protected Base() {
        value = 0;
    }

    Base(int value) {
        this.value = value;
    }
}
```

This snippet illustrates replacing the `Base` definition and does not run standalone. If `Child` is deserialized, `Base.value` is initialized by `Base()`, **not automatically restored to `42`** set at original creation. If non-serializable superclass state must be restored, you must add explicit saving/restoration logic per serialization contract.

## 8. Distinguishing **Which Superclass Constructor Runs** from **Which Fields Are Serialized**

These are two separate concerns:

| Where is the field declared? | Does that class's constructor run on deserialize? | Is the field restored automatically? |
| --- | --- | --- |
| First **non-Serializable** superclass | **Yes**, no-arg constructor runs | **No**, superclass fields are not saved by default |
| Non-Serializable ancestors higher up | Yes, along the invoked constructor's `super()` chain | **No** under default mechanics |
| First class that `implements Serializable` | **No** | Yes for eligible instance fields, barring exceptions like `transient` |
| Subclass of a `Serializable` class | **No** | Yes for eligible instance fields |
| `static` field | Not a per-instance field | **No**, not saved as instance state |
| `transient` field | `Serializable` field initializers do not run | **No**, not saved/restored automatically; gets default unless custom logic runs |

Fields **not saved** by default mechanics do not automatically remember prior state. `Base()` may reinitialize fields of the non-serializable superclass, or leave them at JVM defaults along the constructor chain.

One nuance: a non-serializable superclass field might hold a socket, file descriptor, or live runtime state. Even if you serialize some of its values, restoring an external connection **does not** mean deserializing an object automatically recreates that OS resource. When designing object graphs, clearly separate persistent state from live resources.

## 9. Do Instance Field Initializers and Initializer Blocks Re-Run?

**No, not for the serializable portion of an object deserialized via default mechanics.** This is why field values can look "unexpected."

Illustrative example:

```java
class Base {
    int parentCounter = 100;

    Base() {
        parentCounter++;
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    int number = 10;
    transient int cache = 20;

    {
        number += 5;
        cache += 5;
    }

    Child() {
        number += 1;
    }
}
```

When calling `new Child()`:

- `Base` field initializer sets `parentCounter=100`, constructor increments it to `101`.
- `Child.number` starts at `10`, initializer block increments to `15`, constructor increments to `16`.
- `cache` starts at `20`, initializer block increments to `25`.

If serialized and deserialized using default mechanics:

- `Base()` re-runs; `parentCounter` is **`101`** again.
- `Child` instance initializers and constructor **do not** run.
- `number` restores its persisted value, e.g., **`16`**.
- `cache` is `transient`, so it restores as **`0`** (the default value of `int`) unless custom deserialization handles it.

**Caution:** this example is an illustrative class snippet without `main`. Any assumption about `cache` values must account for a custom `readObject` hook if the class defines one.

## 10. Java 17 Example: `transient` and Initializers Do Not Re-Run

**File `TransientInitializationDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class TransientInitializationDemo {
    static class Base {
        int parentCounter = 100;

        Base() {
            parentCounter++;
        }
    }

    static class Child extends Base implements Serializable {
        private static final long serialVersionUID = 1L;

        int number = 10;
        transient int cache = 20;

        {
            number += 5;
            cache += 5;
        }

        Child() {
            number += 1;
        }
    }

    public static void main(String[] args) throws Exception {
        Child before = new Child();

        System.out.println("Before: parent="
                + before.parentCounter + ", number="
                + before.number + ", cache=" + before.cache);

        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
            out.writeObject(before);
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(sink.toByteArray()))) {
            Child after = (Child) in.readObject();

            System.out.println("After: parent="
                    + after.parentCounter + ", number="
                    + after.number + ", cache=" + after.cache);
        }
    }
}
```

Run:

```bash
javac TransientInitializationDemo.java
java TransientInitializationDemo
```

**Exact stdout when the operation succeeds:**

```text
Before: parent=101, number=16, cache=25
After: parent=101, number=16, cache=0
```

`parentCounter` is not restored from the stream, yet `Base()` sets it to `101` at both times. `number` is restored from the stream, while `cache` defaults to `0`. Because `Child`'s initializers do not re-run during deserialization, `cache` is not reset to `20` or `25`.

In real applications, `transient` fields sometimes need reinitialization per application logic after deserialization—for instance, using custom `readObject` to compute a cache from restored fields (along with invariant checks). Do not expect a `Serializable` constructor to do that automatically.

## 11. When a Non-Serializable Superclass Constructor Has Side Effects

A superclass constructor can perform behavior beyond setting fields:

```java
class ResourceBase {
    protected ResourceBase() {
        // May open resources, increment metrics, register listeners...
    }
}
```

Because this constructor **runs during deserialization**, its side effects can occur **once again for every object actually reconstructed**. Consequences to consider:

- The constructor may allocate new resources distinct from those present when the object was serialized.
- The constructor may register into singletons, listeners, or monitoring systems.
- If the constructor depends on the current environment (clock, config, OS, permissions), parent state may differ from write time.
- If the constructor throws an exception, deserialization fails or gets wrapped into an I/O/stream error per restoration rules.

Avoid designing superclass constructors with heavy side effects unless you understand they can execute during deserialization. Conversely, because **the `Serializable` class's constructor does not run**, never use it as the sole place enforcing invariants on stream-loaded data.

### Hazard: Superclass Constructor Calling an Overridable Method

Suppose:

```java
class Base {
    Base() {
        init();
    }

    void init() {
        // base logic
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String name;

    @Override
    void init() {
        // May observe name before it has been restored.
    }
}
```

This is an illustrative class snippet. Calling an overridable method from a superclass constructor can dispatch into the subclass implementation **before serializable state is restored**. At that moment, `name` may still be `null` even though the stream holds a non-null name.

This is also a classic Java object-initialization pitfall whenever a superclass constructor calls a virtual method, yet with deserialization the subtlety is even easier to miss because the subclass constructor never runs and serialized fields are populated only after superclass initialization completes.

**Recommendation:** avoid calling overridable methods from foundational constructors, especially when they touch subclass fields; if post-deserialization consistency checks are needed, use an appropriate hook and validate after state restoration.

## 12. How to Restore Fields of a Non-Serializable Superclass If Needed?

The default mechanism **does not automatically save** fields declared in a non-Serializable superclass. If an application needs to retain certain values, the `Serializable` subclass can customize **its own** `writeObject` and `readObject` hooks to write and restore extra state, provided data is safely versioned and validated.

Common structure:

```java
private void writeObject(ObjectOutputStream out)
        throws IOException {
    out.defaultWriteObject();
    out.writeInt(this.valueInheritedFromNonSerializableParent);
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    this.valueInheritedFromNonSerializableParent = in.readInt();
}
```

**This is only Java-like pseudocode:** the field `valueInheritedFromNonSerializableParent` must actually exist and be writable, hooks must reside in the proper class, with imports and stream-format management added. In particular, consider **visibility**: a superclass's `private` field cannot be assigned directly by a subclass just because the subclass is `Serializable`; you need an appropriate `protected` API or setter if the superclass permits it.

Points to remember:

1. `defaultWriteObject()` and `defaultReadObject()` handle the `Serializable` class's ordinary fields via default mechanics.
2. Extra values written via `writeInt`, `writeUTF`, etc., must be read back **in the exact matching order and types**.
3. The `readObject` hook **is not a constructor**. It is invoked by Object Serialization mechanics and can verify state once required fields are restored.
4. Stream data may be missing, invalid, or tampered with; validate business constraints and consider `InvalidObjectException` if invariants fail.
5. Changing a custom hook's data layout requires a version-compatibility plan.

### Mental Example

A non-Serializable superclass `BasePerson` has `protected int age`. Subclass `PersonRecord implements Serializable` can explicitly write `age` into the extra data section. During deserialization, `BasePerson()` runs first and initializes default `age`; afterward `PersonRecord.readObject(...)` reads the serialized `age` value and updates the field. Thus parent state can be restored **intentionally**, rather than relying on default mechanics that omit it.

Avoid saving non-reconstructible system-state fields such as native handles, open sockets, live threads, or active locks. Serialization does not guarantee faithful restoration of those OS resources.

## 13. `serialVersionUID` and Incompatible Class Errors

You should explicitly declare `serialVersionUID` in a `Serializable` class:

```java
private static final long serialVersionUID = 1L;
```

This ID is used when checking compatibility of the serialized class descriptor. If the local class is incompatible with the stream descriptor, `readObject()` can throw `InvalidClassException` before or during object reconstruction.

**Distinguish the causes:**

| Issue | Typical error/consequence |
| --- | --- |
| Non-Serializable superclass lacks a valid no-arg constructor | `InvalidClassException`, e.g., reason "no valid constructor" |
| Mismatched `serialVersionUID` or incompatible class descriptor | `InvalidClassException`, for a different reason |
| Field holds a non-serializable object during `writeObject` | `NotSerializableException` |
| Class needed for restoration is absent from classpath | `ClassNotFoundException` |
| Corrupted data or invalid stream | `StreamCorruptedException`/`IOException` or other contextual error |

Do not try to fix every `InvalidClassException` by "adding a constructor" if the root cause is an incompatible class version. Conversely, **declaring `serialVersionUID` cannot make up for a missing superclass constructor**.

## 14. `Serializable` Differs from `Externalizable`

`Externalizable` **extends `Serializable`**, yet uses a different serialization protocol: the class takes active responsibility for writing/reading all persisted contents via `writeExternal` and `readExternal`.

Crucial difference regarding constructors:

- **Standard `Serializable`:** during deserialization, **the `Serializable` class's constructor is not called**; the valid no-arg constructor of the nearest **non-Serializable** superclass is called.
- **`Externalizable`:** during deserialization, the runtime invokes **the `Externalizable` class's `public` no-arg constructor** and then calls `readExternal(...)`; because the `Externalizable` class's constructor runs, **its normal `super()` chain also executes**.

Comparison table:

| Criterion | Default `Serializable` | `Externalizable` |
| --- | --- | --- |
| Marker interface? | Yes | Yes, plus methods |
| Does the restored class's constructor run? | **No** | **Yes**, `public` no-arg constructor |
| Is a non-Serializable superclass initialized? | Yes, via selected no-arg constructor | Yes, via normal constructor chain |
| Who defines written data? | Default serialization, optional hooks | `writeExternal` / `readExternal` |
| Characteristic constructor requirement | Accessible no-arg on nearest non-serializable superclass | **`public`** no-arg on the `Externalizable` class |
| Common error | Superclass lacks valid no-arg constructor | `Externalizable` lacks `public` no-arg or asymmetric custom read/write |

**Do not apply the rule "Serializable constructors do not run" to `Externalizable` without distinguishing protocols.** This is a classic exception frequently asked in interviews.

## 15. Java 17 Example: `Externalizable` Constructor Is Called

**File `ExternalizableConstructorDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectInputStream;
import java.io.ObjectOutput;
import java.io.ObjectOutputStream;

public class ExternalizableConstructorDemo {
    public static class Data implements Externalizable {
        private static final long serialVersionUID = 1L;

        private int number;

        public Data() {
            System.out.println("Data constructor");
        }

        Data(int number) {
            this.number = number;
        }

        @Override
        public void writeExternal(ObjectOutput out) throws IOException {
            out.writeInt(number);
        }

        @Override
        public void readExternal(ObjectInput in)
                throws IOException {
            number = in.readInt();
        }
    }

    public static void main(String[] args) throws Exception {
        Data before = new Data(25);

        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                     new ObjectOutputStream(memory)) {
            output.writeObject(before);
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(memory.toByteArray()))) {
            Data after = (Data) input.readObject();
            System.out.println("Value: " + after.number);
        }
    }
}
```

Compile and run:

```bash
javac ExternalizableConstructorDemo.java
java ExternalizableConstructorDemo
```

**Exact stdout if the operation succeeds:**

```text
Data constructor
Value: 25
```

Why is there only **one** `"Data constructor"` line? `new Data(25)` runs the **one-argument** constructor, which prints nothing. When `readObject()` restores the `Externalizable` object, the runtime invokes **`public Data()`**, prints `"Data constructor"`, and then calls `readExternal()` to read `25`.

If the one-argument constructor also logged output, you would see its log upon original creation, while **deserialization still invokes only the `public` no-arg constructor**.

Note that the class in this example is a **`public static` nested class** with a `public` no-arg constructor. Using a **non-static inner class** for serialization carries pitfalls around implicit references to the enclosing instance and constructor requirements; prefer static nested classes or top-level classes in examples.

## 16. When the Superclass Changes Between Write and Read

Class definitions live in the receiving program, not merely inside serialized bytes. Thus altering the inheritance hierarchy between write and read can affect deserializability and how superclasses initialize.

Mental example:

1. Version 1 has `Child implements Serializable` and a non-serializable `Base` with a valid `Base()`.
2. A newer version replaces `Base()` with a constructor taking only parameters.
3. Old streams may still have a `serialVersionUID` matching `Child`, yet **deserialization fails** because superclass `Base` no longer has a valid no-arg constructor.

Compatibility behavior also depends on other class, field, and serial-descriptor edits. When modifying libraries containing long-lived serializable classes, test **deserializing data saved by the older version using the newer version**; do not run only same-binary `writeObject -> readObject` roundtrip tests.

If data must survive across many versions and languages, Java native serialization has significant limitations compared to versioned schema formats such as JSON/CBOR/Protocol Buffers or specialized stores. Do not choose Java serialization merely for automatic object-graph persistence without evaluating compatibility requirements.

## 17. Common Reasoning Errors

| Wrong reasoning | Why it is wrong | Correct understanding |
| --- | --- | --- |
| "Deserialization never calls any constructors." | Non-serializable superclasses still must be initialized | Invokes the valid no-arg constructor of the nearest non-Serializable superclass |
| "A `Serializable` class must have a no-arg constructor." | That class's own constructor is not called under default mechanics | The requirement applies to the first non-Serializable superclass |
| "Any no-arg constructor on the superclass works." | Private/inaccessible no-arg constructors violate the contract | Must be accessible to the `Serializable` subclass |
| "A subclass without `implements Serializable` runs its constructor." | `Serializable` is inherited | Every class in the serializable segment skips its constructor on deserialize |
| "Non-Serializable superclass fields are saved automatically." | Default serialization persists only the serializable portion | Superclass state is reinitialized by its constructor or custom logic |
| "`Serializable` initializers re-run." | Restoration skips instance initialization of `Serializable` classes | Serial fields come from stream; `transient` gets defaults |
| "Adding `serialVersionUID` fixes the missing no-arg constructor error." | Two independent requirements | Fix superclass structure/constructor or serialization model |
| "`Externalizable` also skips the class's constructor." | The `Externalizable` protocol invokes the `public` no-arg constructor | Distinguish the two mechanisms |
| "Subclass constructor always validates the stream." | Subclass constructor does not run | Validate via custom `readObject`/`readResolve` or appropriate mechanism |
| "Superclass constructor can safely call any overridden method." | The method can observe subclass state before restoration | Avoid virtual calls from superclass constructors |
| "An untrusted stream can be deserialized unconditionally." | Object graphs and hooks carry side effects and major risks | Use filters or avoid native serialization for untrusted input |

## 18. Security and Safety During Deserialization

Java native deserialization from **untrusted** sources poses severe risks: complex object graphs, unintended contents, gadget/hook chains, and classes with side effects. Even though the `Serializable` class's constructor **does not run**, **hooks such as `readObject`, `readResolve`**, non-serializable superclass initialization, and creation of other objects in the graph can still execute logic.

Therefore never conclude "deserialization is safe because constructors are skipped." For applications receiving bytes from clients or external sources:

- Prefer **schema-backed data formats** and strictly validating decoders whenever possible.
- If Object Serialization is unavoidable, configure `ObjectInputFilter` with contextual allowlists/denylists and limits on depth, object counts, and data sizes.
- Validate invariants after restoration and never pass unverified objects straight into privileged logic.
- Govern stream versions, permitted classes, resource quotas, and isolation.

`ObjectInputFilter` reduces risk, yet **does not make deserializing arbitrary untrusted data completely safe**. Permitted class sets and handling policies still require dedicated review.

## 19. Self-Check Questions

**Question 1.** Class `Child extends Base implements Serializable`, where `Base` is not `Serializable` and has `protected Base()`. When `readObject()` returns a `Child`, which constructors run?

**Answer:** `Base()` and the chain of non-serializable ancestor constructors that `Base()` invokes. `Child()` does not run under ordinary `Serializable` mechanics.

**Question 2.** `Base` has only `Base(int)`, while `Child()` calls `super(1)` so `new Child()` compiles. Will deserialization succeed?

**Answer:** Not under ordinary default `Serializable` mechanics: the non-serializable superclass lacks a valid no-arg constructor. `readObject()` will throw `InvalidClassException`.

**Question 3.** Non-Serializable `Base` has field `int x = 5` and a no-arg constructor setting `x = 8`. After `new Child()`, the app sets `x = 20` and serializes `Child`. After deserialization, what is `x`?

**Answer:** **`8`**, assuming no other custom serialization. `Base`'s field is not saved by default; the no-arg constructor `Base()` re-runs and sets `8`.

**Question 4.** `Serializable` `Child` has `transient int cache = 100`. After deserialization, is `cache` `100` or `0`?

**Answer:** **`0`** if there is no custom read hook. `Child`'s field initializer does not re-run, and `transient` is not restored by default serialization.

**Question 5.** A class `Data implements Externalizable` has `public Data()` and `Data(int)`. When reading from a stream, which constructor runs?

**Answer:** The runtime invokes **`public Data()`**, then `readExternal`. `Externalizable` does not follow the constructor-skipping rule of regular `Serializable`.

**Question 6.** Is it true that `static` fields are serialized if declared on a `Serializable` class?

**Answer:** No. Default Java Object Serialization handles instance state; `static` is class-level state. Static values can differ between reading and writing programs.

**Question 7.** Can the constructor of `Child implements Serializable` be used as the sole check for `balance >= 0` on objects read from a stream?

**Answer:** No. `Child`'s constructor does not run during default deserialization. Validate invariants in a restoration hook or an appropriate validation layer before using the object.

## 20. Summary

In Java Object Serialization, remember the three "zones" of an inheritance chain:

```text
               Object (not Serializable)
                   |
               Base   (not Serializable)
                   |
            --- boundary ---
                   |
             Parent (Serializable)
                   |
             Child  (Serializable)

new Child():
  Constructors Object -> Base -> Parent -> Child

deserialize Child:
  Constructors Object -> Base
  do NOT call Parent/Child constructors;
  restore Parent/Child Serializable state from the stream.
```

**Golden rule:** *Java only requires an accessible no-argument constructor on the nearest **non-Serializable** superclass; constructors of classes in the `Serializable` segment are skipped during ordinary object restoration. Consequently, non-Serializable superclass fields must be reinitialized or explicitly restored, while `Serializable` fields are read from the stream.*

Pay close attention to `transient`, instance initializers, constructor accessibility, differences from `Externalizable`, version compatibility, and security risks. This foundation explains most constructor questions in Java serialization and guides designing reliably deserializable classes.

**Java SE 17 References:**

1. [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html) — non-serializable superclass no-arg constructor requirement and restoration mechanics.
2. [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html) — `readObject()` and object graph restoration.
3. [Externalizable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html) — constructor and externalization protocol.
4. [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html) — restoration process, class state, and stream format.
5. [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) — limits when processing serialized data.
