# Constructors of Serializable Classes and Non-Serializable Superclasses

## 1. The Core Question

When calling `new` to create a Java object, constructors of classes along the inheritance chain run according to normal object initialization rules. However, when using **Java Object Serialization** with `ObjectInputStream.readObject()` to restore an object whose class implements `java.io.Serializable`, constructor rules **differ significantly**.

**Rule to remember:** During default *deserialization* of an ordinary `Serializable` class, **the constructors of the `Serializable` class itself and of any `Serializable` superclasses are not invoked**. Instead, Java **invokes the accessible no-argument constructor of the nearest superclass that does not implement `Serializable`**. From that constructor, constructors of non-`Serializable` ancestors continue executing according to normal `super()` rules.

Example:

```text
Object                 (non-Serializable)
   |
   v
Base                   (non-Serializable)  <-- no-arg constructor is called
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

The diagram is simplified to illustrate constructors of the object being restored; the actual process also resolves descriptors, handles, references, object chains, and serialization hooks.

Specifically, **never say "deserialization runs no constructors at all."** More accurately: it **skips constructors of classes in the `Serializable` part of the hierarchy**, while **running the no-arg constructor of the nearest non-`Serializable` superclass** and whatever ancestor constructors that constructor calls.

This topic determines which fields are restored, which fields get freshly initialized values, and why lacking an appropriate superclass constructor causes `readObject()` to fail.

## 2. `Serializable` Is Only a Marker Interface

`java.io.Serializable` is a **marker interface**: it declares no mandatory methods to implement. A class that directly writes `implements Serializable` or **inherits** from a class implementing this interface belongs to the default serializable group, provided other serialization conditions are satisfied.

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

This is an illustrative snippet, without `main`. `Parent` does **not** need to implement `Serializable` for `Child` to be Serializable. However, `Parent` being non-Serializable has consequences:

- **Fields declared in `Parent` are not automatically saved and restored by default Java serialization**.
- When deserializing a `Child`, Java invokes the **valid no-arg constructor of `Parent`**.
- `Child`'s constructor is not called; `Child`'s Serializable fields are restored from the stream instead of being initialized via a normal constructor.

Note: `Serializable` is inherited as a class capability. If `GrandParent implements Serializable`, `Parent extends GrandParent`, and `Child extends Parent`, both `Parent` and `Child` are Serializable even without repeating `implements Serializable`.

## 3. Why Are Constructors Handled Differently from `new`?

### 3.1. Creating an Object with `new`

In ordinary Java:

```java
Child child = new Child();
```

The constructor sequence in principle is:

1. Object allocation per JVM rules.
2. The top-level class with no explicit parent, such as `Object()`, runs along the `super` chain.
3. Superclass constructors run top-down.
4. The concrete class `Child`'s constructor runs; field initializers and instance initializer blocks execute in Java initialization order.

If `Child`'s field or constructor invokes `super(args)`, the corresponding ordering rules apply.

### 3.2. Restoring with `readObject()`

When calling:

```java
Child restored = (Child) objectInput.readObject();
```

the serialization mechanism must recreate the **persisted state** of the serializable portion, rather than "calling `new Child()` and setting a few fields" like normal application code.

Therefore:

- `Child`'s constructor does not execute.
- **Instance field initializers** and **instance initializer blocks** of classes in the Serializable portion of the hierarchy do not execute.
- Constructors of intermediate Serializable superclasses do not execute.
- The selected no-argument constructor of the nearest **non**-Serializable superclass does execute; that constructor may in turn call its non-serializable superclass.
- Fields belonging to serializable classes are then restored from stream data per the Object Serialization mechanism.

**Important:** static initialization is a separate JVM mechanism. When a class is first initialized, static initializers can run under class initialization rules; do not confuse that with instance constructors running per deserialized object.

## 4. Java 17 Example: Which Constructor Runs and Which Fields Are Kept?

The following standalone program uses a **non-Serializable** superclass and a **Serializable** subclass.

At creation time, the superclass sets `baseValue = 10`; the subclass constructor overwrites it to 99 and sets `childValue = 77`. After writing and reading the object via a stream, the superclass constructor runs again and sets `baseValue = 10`, while the subclass constructor does not run. Since `baseValue` belongs to the non-Serializable superclass, the value 99 **is not automatically restored**; `childValue` belongs to the Serializable subclass and is restored to 77.

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
            // super() is added implicitly by the compiler.
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

1. `new Child()`: runs `Base()` then `Child()`, resulting in `baseValue=99` and `childValue=77`.
2. `ObjectOutputStream.writeObject(original)`: saves the Serializable state of `Child`. It does not automatically save `Base.baseValue` under the default mechanism because `Base` is not Serializable.
3. `ObjectInputStream.readObject()`: the JVM allocates an instance of `Child` via the restoration mechanism, **without calling `Child()`**.
4. `Base()` is called because `Base` is the nearest non-Serializable superclass with a valid no-argument constructor, setting `baseValue=10`.
5. `childValue` belongs to the Serializable portion and is restored from the stream as `77`.

This is the clearest empirical verification: the second pass prints **`Base constructor`** without **`Child constructor`**.

## 5. What If Multiple Serializable Classes Inherit from Each Other?

Suppose:

```text
PlainRoot              non-Serializable
   |
   +-- SerialParent    implements Serializable
          |
          +-- SerialChild  extends SerialParent
```

When restoring a `SerialChild`:

- Constructor `PlainRoot()` runs.
- Constructor `SerialParent()` **does not run**.
- Constructor `SerialChild()` **does not run**.
- Serializable fields of **both `SerialParent` and `SerialChild`** are restored from the stream, except fields excluded from default serialization (such as `transient`).

Subclasses below `SerialParent` are automatically Serializable by inheritance. Whether they have empty constructors **does not decide** constructor invocation during default deserialization.

### Java 17 Example: Three Levels of Inheritance

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

**Why is `root=1` instead of `99`?** `rootNumber` is a field declared on the non-Serializable class `PlainRoot`. On `new`, `SerialParent`'s constructor changed it to 99; however, deserialization does not call `SerialParent()` and instead calls `PlainRoot()`, resetting it to 1. The two Serializable fields `parentNumber` and `childNumber` are restored as 2 and 3 from the stream.

## 6. The Constructor Must Exist on the **First Non-Serializable Superclass**

Suppose `Child implements Serializable` and `Base` is its direct non-Serializable superclass. `ObjectInputStream` requires a **valid no-argument constructor** on `Base` to restore the object.

### 6.1. Acceptable

```java
class Base {
    protected Base() {
        // Initialize foundational state.
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    Child(int value) {
        super();
    }
}
```

Because `Base()` is `protected`, that constructor is accessible to the subclass under Java rules. Whether `Child(int)` takes parameters **does not matter for constructor invocation at deserialization time**, since `Child`'s constructor is not used in the default mechanism.

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

**This code compiles**, because `Child()` explicitly calls `super(42)` during normal instantiation. However, `Base` **has no no-arg constructor**, so ordinary deserialization of `Child` cannot perform superclass initialization and fails with `InvalidClassException` reporting no valid constructor.

This is not caught at compile time. **Having `new Child()` and `writeObject(child)` succeed does not prove `readObject()` will succeed.**

### 6.3. Private or Inaccessible Constructor

The chosen non-Serializable superclass constructor must be **accessible to the subclass that is Serializable** per the Java Object Serialization specification.

- `public` or `protected` no-arg constructors are generally clear choices.
- A *package-private* no-arg constructor works only in a matching access context (e.g., same package).
- A `private` constructor cannot be accessed by a normal subclass; having a private no-arg constructor **does not** satisfy the requirement.
- Module/access boundaries across packages and modules can create accessibility issues in complex designs.

**Do not oversimplify to "there must be a public no-arg constructor."** For ordinary `Serializable`, `protected` or contextually accessible no-arg constructors can also be valid; the **public** requirement specifically applies to `Externalizable`, a distinct mechanism compared below.

## 7. Java 17 Example: Missing No-Arg Constructor Leads to InvalidClassException

This example deliberately uses a superclass with only a single-parameter constructor. It proves:

- The subclass constructor used for `new` works.
- Serialization via `writeObject` completes.
- **Deserialization fails** because the superclass lacks a valid no-arg constructor.

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

The detailed message of `InvalidClassException` can vary across JDKs/implementations. Therefore, the program prints only the **exception class name** without assuming fixed message wording.

Appropriate fix if you own the superclass:

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

This snippet illustrates replacing the `Base` definition and does not run standalone. When deserializing `Child`, `Base.value` is initialized by `Base()`, **not automatically restored to 42** as set during creation. If non-serializable superclass state must be restored, add explicit save/restore logic per the serialization contract.

## 8. Distinguishing **Superclass Constructor Called** from **Fields Serialized**

These are two separate things:

| Where is the field declared? | Does that class's constructor run on deserialize? | Is the field restored automatically? |
| --- | --- | --- |
| First **non-Serializable** superclass | **Yes**, invokes no-arg constructor | **No**, fields of this superclass are not saved by default |
| Non-Serializable ancestors above it | Yes, via the `super()` chain of the invoked constructor | **No** under the default mechanism |
| First class `implements Serializable` | **No** | Yes for eligible serializable instance fields, except exclusions like `transient` |
| Subclass of a Serializable class | **No** | Yes for eligible instance fields |
| `static` field | Not a per-instance field | **Not** persisted as instance state |
| `transient` field | Initializers of Serializable class do not run | **Not** saved/restored automatically; takes default unless custom logic runs |

Fields **not persisted** by the default mechanism have no awareness of their previous state. `Base()` can re-initialize fields of the non-serializable superclass, or if left uninitialized they take default values per JVM/constructor-chain rules.

A nuance: a non-serializable class's field might hold a socket, file descriptor, or runtime state. Even if part of its values could be serialized, restoring an external connection **does not** mean deserializing an object can automatically rebuild that resource. When designing object graphs, clearly separate persistent state from live resources.

## 9. Do Instance Field Initializers and Initializer Blocks Re-run?

**No for the serializable portion of an object deserialized by the default mechanism.** This is what makes field values look "surprising."

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

On `new Child()`:

- `Base` field initializer sets `parentCounter=100`, constructor increments it to 101.
- `Child.number` starts at 10, initializer block increments to 15, constructor increments to 16.
- `cache` starts at 20, initializer block increments to 25.

If serialized and deserialized with the default mechanism:

- `Base()` re-runs; `parentCounter` is **101** again.
- `Child` instance initializers and constructor **do not** run.
- `number` restores its saved value, e.g., **16**.
- `cache` is `transient`, so it is restored to **0** (default value of `int`) unless custom deserialization handles it.

**Careful:** this example is an illustrative class snippet without `main`. Any assumptions about `cache` values must account for custom `readObject` if the class implements that hook.

## 10. Java 17 Example: transient and Initializers Are Not Re-invoked

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

`parentCounter` is not automatically restored from the stream, yet no-arg constructor `Base()` sets it to 101 at both points. `number` is restored from the stream, whereas `cache` defaults to 0. Because `Child`'s initializers do not re-run on deserialization, it is not reset to 20 or 25.

In real applications, `transient` fields sometimes need re-initialization per application logic after deserialization, such as using custom `readObject` to compute a cache from restored fields (alongside invariant checks). Do not expect the Serializable constructor to do that automatically.

## 11. When a Non-Serializable Superclass Constructor Has Side Effects

A superclass constructor can perform actions beyond setting fields:

```java
class ResourceBase {
    protected ResourceBase() {
        // May open resources, increment metrics, register listeners...
    }
}
```

Because this constructor **runs during deserialization**, side effects can occur **once more for every actually restored object**. Consequences to consider:

- The constructor may allocate new resources distinct from those that existed when the object was serialized.
- The constructor may register into singletons, listeners, or monitoring systems.
- If the constructor depends on the current environment (clock, config, OS, permissions), parent state may differ from when the stream was written.
- A constructor throwing an exception can fail deserialization or be wrapped into an I/O/stream error per the restoration mechanism.

Avoid designing superclass constructors with heavy side effects without understanding they can run during a deserialization workflow. On the other hand, **the Serializable class's constructor does not run**, so never rely on that constructor as the sole place enforcing invariants for data read from a stream.

### Danger Point: Superclass Constructor Calling an Overridable Method

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
        // Can observe name before it has been restored.
    }
}
```

This is an illustrative class snippet. Calling an overridable method from a superclass constructor can dispatch into the subclass implementation **before serializable state has been restored**. At that moment `name` can still be `null` even though the stream holds a non-null name.

This is also a classic object initialization issue in Java whenever a superclass constructor calls a virtual method, yet with deserialization the subtlety is even easier to miss because the subclass constructor never runs and data is restored only after superclass initialization.

**Recommendation:** avoid calling overridable methods from foundational constructors, especially when they depend on subclass fields; to check consistency after deserialization, use an appropriate hook and validate after state restoration.

## 12. How to Restore Fields of a Non-Serializable Superclass If Needed?

The default mechanism **does not automatically save** fields declared in a non-Serializable superclass. If an application needs to keep certain values, the Serializable class can customize **its own** `writeObject` and `readObject` to save and restore additional state, provided data is safely handled and properly versioned.

Typical structure:

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

**This is only Java-like pseudocode:** the field `valueInheritedFromNonSerializableParent` must actually exist and be writable, hooks must reside in the right class, imports must be added, and stream formatting must be managed. In particular, consider **access visibility**: a private field of a superclass cannot be directly assigned by a subclass just because the subclass is Serializable; an appropriate setter or protected API is needed if the superclass allows it.

Key points to remember:

1. `defaultWriteObject()` and `defaultReadObject()` handle the Serializable class's ordinary fields via the default mechanism.
2. Extra values written with `writeInt`, `writeUTF`… must be read back **in the exact order and matching types**.
3. The `readObject` hook **is not a constructor**. It is invoked by the Object Serialization mechanism and can re-verify state after required fields are restored.
4. Stream data can be missing, invalid, or tampered with; validate business constraints and consider `InvalidObjectException` when state violates invariants.
5. Changing a custom hook's data format requires a version compatibility plan.

### Conceptual Example

A non-Serializable superclass `BasePerson` has `protected int age`. Subclass `PersonRecord implements Serializable` can explicitly write `age` into the extra data section. During deserialization, `BasePerson()` runs first and sets a default age; then `PersonRecord.readObject(...)` reads the serialized age value and updates the field. As a result, parent state is restored **deliberately**, rather than relying on the default mechanism which does not save it.

Avoid saving non-reproducible system state fields, such as native handles, open sockets, live threads, or locks. Serialization does not guarantee restoring such OS resources intact.

## 13. `serialVersionUID` and Incompatible Class Errors

Declare `serialVersionUID` explicitly in Serializable classes:

```java
private static final long serialVersionUID = 1L;
```

This ID is used when checking compatibility of the serialized class descriptor. If the local class is incompatible with the descriptor in the stream, `readObject()` can throw `InvalidClassException` before or during object restoration.

**Distinguish the root causes:**

| Problem | Typical error/consequence |
| --- | --- |
| Non-Serializable superclass lacks a valid no-arg constructor | `InvalidClassException`, e.g., reason "no valid constructor" |
| `serialVersionUID` mismatch or incompatible class descriptor | `InvalidClassException`, but for a different reason |
| Field holds a non-serializable object during `writeObject` | `NotSerializableException` |
| Class to restore is missing from the classpath | `ClassNotFoundException` |
| Corrupted data or invalid stream | `StreamCorruptedException`/`IOException` or other errors depending on context |

Do not fix every `InvalidClassException` by "adding a constructor" if the real cause is an incompatible class version. Conversely, **declaring `serialVersionUID` cannot compensate for a missing superclass constructor**.

## 14. `Serializable` Differs from `Externalizable`

`Externalizable` **extends `Serializable`**, yet is a distinct serialization protocol: the class actively writes/reads all persisted contents via `writeExternal` and `readExternal`.

A critical point regarding constructors:

- **Ordinary `Serializable`:** on deserialize, **does not call the Serializable class's constructor**; calls the valid no-arg constructor of the nearest **non-Serializable** superclass.
- **`Externalizable`:** on deserialize, the runtime calls the **public no-arg constructor of the `Externalizable` class itself** and then calls `readExternal(...)`; because the `Externalizable` class's constructor runs, **the normal `super()` chain also runs**.

Comparison table:

| Criterion | Default `Serializable` | `Externalizable` |
| --- | --- | --- |
| Marker interface? | Yes | Yes, but adds methods |
| Does the restored class's constructor run? | **No** | **Yes**, public no-arg constructor |
| Is the non-Serializable superclass initialized? | Yes, via the selected no-arg constructor | Yes, via the normal constructor chain |
| Who defines what data is written? | Default serialization, optionally with hooks | `writeExternal` / `readExternal` |
| Specific constructor requirement | Accessible no-arg on nearest non-serializable superclass | **Public** no-arg on the `Externalizable` class |
| Common pitfalls | Superclass missing valid no-arg constructor | `Externalizable` missing public no-arg constructor or asymmetric custom read/write |

**Do not apply the rule "Serializable constructors do not run" to `Externalizable` without distinguishing the two protocols.** This is a key exception frequently asked in interviews.

## 15. Java 17 Example: `Externalizable` Constructor Is Invoked

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

Why is there only **one** "Data constructor" line? `new Data(25)` runs the **one-argument** constructor, which prints nothing. When `readObject()` restores the `Externalizable`, the runtime invokes **public `Data()`**, prints "Data constructor", and then calls `readExternal()` to read the number 25.

If the one-argument constructor also logged output, we would see its log when creating the new object, whereas **during deserialization only the public no-arg constructor is chosen**.

Note that the class in the example is a **public static nested class**, providing a public no-arg constructor. Serializing a **non-static inner class** carries traps involving the enclosing instance reference and constructor requirements; prefer static nested classes or top-level classes in examples.

## 16. When the Superclass Changes Between Write and Read

Class descriptors live in the program receiving the stream, not just in the serialized bytes. Thus changing the inheritance hierarchy between write and read can affect deserializability and superclass initialization.

Conceptual example:

1. Version 1 has `Child implements Serializable` and a non-serializable `Base` with a valid `Base()`.
2. A new version replaces `Base()` with a constructor that only accepts arguments.
3. An old stream may still have a `serialVersionUID` matching `Child`, yet **deserialization fails** because superclass `Base` no longer has a valid constructor.

Compatibility behavior also depends on other class/field/serial-descriptor changes. Therefore, when modifying a library containing long-lived serialized classes, test **deserializing data saved from older versions using the new version**; do not rely solely on a `writeObject -> readObject` roundtrip test within a single binary.

If data must be stored long-term across many versions and languages, Java native serialization has significant limitations compared to versioned schema formats like JSON/CBOR/Protocol Buffers or dedicated storage solutions. Do not pick Java serialization merely to auto-save object graphs without evaluating compatibility requirements.

## 17. Common Reasoning Errors

| Wrong reasoning | Why it is wrong | Correct understanding |
| --- | --- | --- |
| "Deserialization never calls any constructor." | Non-serializable superclasses still need initialization | Calls the valid no-arg constructor of the nearest non-Serializable superclass |
| "A Serializable class must have a no-arg constructor." | That class's constructor is not called under the default mechanism | The requirement applies to the first non-Serializable superclass |
| "Any no-arg constructor on the superclass works." | Private/inaccessible no-arg constructors do not satisfy the contract | It must be accessible to the Serializable subclass |
| "A subclass without `implements Serializable` runs its constructor." | Serializability is inherited | Every class in the serializable subtree has its constructor skipped on deserialize |
| "Fields of a non-Serializable superclass are saved automatically." | Default serialization only saves the serializable portion | Superclass state is re-initialized by its constructor or handled via custom logic |
| "Initializers of the Serializable class re-run." | Restoration skips Serializable instance initialization | Serial fields come from the stream; transient fields take defaults |
| "Adding `serialVersionUID` fixes missing no-arg constructor errors." | Two independent requirements | Fix the superclass structure/constructor or serialization model |
| "`Externalizable` also skips the class's constructor." | The Externalizable protocol calls its public no-arg constructor | Distinguish the two mechanisms |
| "The subclass constructor always validates the stream." | The subclass constructor does not run | Validate via custom `readObject`/`readResolve` or appropriate verification |
| "A superclass constructor can safely call any overridden method." | The method can observe subclass state not yet restored | Avoid virtual calls from superclass constructors |
| "An untrusted stream can be deserialized unconditionally." | Object graphs/hooks have side effects and high risks | Use filters or avoid native serialization for untrusted input |

## 18. Security and Safety During Deserialization

Java native deserialization from **untrusted** sources carries serious risks: complex object graphs, unexpected types, method/hook chains, and classes with side effects. Even though the `Serializable` class's constructor **does not run**, **hooks like `readObject`, `readResolve`**, non-serializable superclass initialization, and creation of other objects in the graph can still execute logic.

Therefore, never conclude "deserialization is safe because constructors are skipped." For applications accepting bytes from clients or external sources:

- Prefer **schema-based data formats** and strictly validating decoders whenever possible.
- If Object Serialization must be used, configure `ObjectInputFilter` with context-appropriate allowlists/denylists, depth limits, object counts, and data size limits.
- Validate invariants after restoration and never pass unverified objects directly into privileged logic.
- Manage stream versions, permitted class types, resource limits, and isolation mechanisms.

`ObjectInputFilter` reduces risk, yet **does not make deserializing arbitrary untrusted data completely safe**. Allowed restored classes and processing policies still require separate review.

## 19. Self-Check Questions

**Question 1.** Class `Child extends Base implements Serializable`, where `Base` is non-Serializable and has `protected Base()`. When `readObject()` returns a `Child`, which constructor runs?

**Answer:** `Base()` and the constructor chain of any non-serializable ancestors that `Base()` calls. `Child()` does not run under the ordinary Serializable mechanism.

**Question 2.** `Base` only has `Base(int)`, while `Child()` calls `super(1)`, so `new Child()` compiles. Will deserialization succeed?

**Answer:** Not under the ordinary default Serializable mechanism: the non-serializable superclass lacks a valid no-arg constructor. `readObject()` will throw `InvalidClassException`.

**Question 3.** Non-Serializable `Base` has field `int x = 5` and a no-arg constructor setting `x = 8`. After `new Child()`, the application changes `x = 20` and serializes `Child`. After deserialization, what is `x`?

**Answer:** **8**, assuming no other custom serialization. `Base`'s field is not saved by the default mechanism; the no-arg constructor `Base()` runs again and sets the value to 8.

**Question 4.** Serializable `Child` has `transient int cache = 100`. After deserialization, is `cache` 100 or 0?

**Answer:** **0** if there is no custom read hook. `Child`'s field initializer does not re-run, and `transient` is not restored by default serialization.

**Question 5.** A class `Data implements Externalizable` has `public Data()` and `Data(int)`. When reading from a stream, which constructor runs?

**Answer:** The runtime invokes **public `Data()`**, then calls `readExternal`. `Externalizable` does not follow the ordinary Serializable rule of skipping the class's own constructor.

**Question 6.** Is it true that `static` fields are serialized if declared in a Serializable class?

**Answer:** No. Default Java Object Serialization handles instance state; `static` is class-level state. Static values may differ in the reading program compared to the writing program.

**Question 7.** Can the constructor of `Child implements Serializable` be used as the sole place checking `balance >= 0` for objects read from a stream?

**Answer:** No. `Child`'s constructor does not run under default deserialization. Invariants must be checked in a restoration hook or an appropriate validation layer before using the object.

## 20. Summary

In Java Object Serialization, remember the three "zones" of the inheritance chain:

```text
               Object (non-Serializable)
                   |
               Base   (non-Serializable)
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
  Do NOT call Parent/Child constructors;
  restore Serializable state of Parent/Child from stream.
```

**Golden rule:** *Java only requires a suitable no-argument constructor on the nearest **non-Serializable** superclass; constructors of classes in the Serializable segment are skipped during ordinary object restoration. Therefore, fields of non-Serializable superclasses must be re-initialized or explicitly restored, while Serializable fields are read from the stream.*

Carefully check `transient`, instance initializers, constructor accessibility, differences with `Externalizable`, version compatibility, and security risks. This forms the foundation for explaining most constructor questions in Java serialization and designing classes that deserialize reliably.

**Java SE 17 References:**

1. [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html) — non-serializable superclass no-arg constructor requirement and restoration mechanism.
2. [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html) — `readObject()` and object graph restoration.
3. [Externalizable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html) — constructor and externalization protocol.
4. [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html) — restoration flow, class state, and stream format.
5. [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) — limits when processing serialized data.