# 5.7. Write Restrictions on `static final`, Record Fields, and Hidden Class Fields

In Java, reflection allows retrieving metadata and reading the value of a field using `java.lang.reflect.Field`. However, **finding a field and having read permission does not mean having write permission**. With Java 17, even after calling `field.setAccessible(true)` successfully, certain `final` fields still fall into the category of **non-modifiable final fields via Core Reflection** (*non-modifiable final fields*):

1. Any `static final` field declared in a class or interface.
2. Any `final` field declared in a **record class**.
3. Any `final` field declared in a **hidden class**.

This is a specific restriction of the write operations `Field.set(...)`/`setInt(...)` and their corresponding setters, not merely a `public`/`private` access check. This lesson explains the mechanism, the boundaries of each category, how to recognize errors, a runnable Java 17+ program, and how to design applications so they do not depend on modifying restricted fields.

## 1. Distinguishing `final`, Access Rights, and Writability

**`final`** on a field means that normal Java code may only assign a value in the initialization locations permitted by the language; after initialization, it cannot be directly reassigned via `instance.field = ...` or `Class.FIELD = ...`. For a reference field, `final` protects the **reference**, not automatically making the referenced object immutable.

**Access rights** are a separate concern: a `private` field may be blocked even without `final`. `Field.setAccessible(true)` requests bypassing normal Java access checks, within the scope permitted by the Java Platform Module System (JPMS). It **does not remove the `final` modifier**, does not make every field mutable, and does not disable the non-modifiable final rule.

In Java 17, `Field.set(Object receiver, Object newValue)` for a `final` field can only write when all of the following are **simultaneously** satisfied:

- Calling `setAccessible(true)` on that exact `Field` object has succeeded.
- The field is an **instance field**, meaning it does not have `static`.
- The **declaring class** of the field is not a **record class**.
- The **declaring class** of the field is not a **hidden class**.

Even when the above conditions are met, writing to an ordinary final instance field via reflection is only meaningful in very special workflows, such as reconstruction/deserialization **before the object is published to other code**. Using it to modify a live object can lead to unpredictable results due to `final` semantics, JIT/optimization behavior, and the Java Memory Model. This is **not** a recommended mechanism for updating application state.

| Field under consideration | Can `setAccessible(true)` succeed? | Can `Field.set*` write to `final`? | Proper initialization/update approach |
| --- | --- | --- | --- |
| `static final` in a regular class/interface | Yes, if access rights/module permit | **No** | Set value at declaration or in a static initializer; use a non-`final` field if modification is needed |
| Record component such as `record Point(int x)` | Yes, if access rights/module permit | **No** | Initialize via the canonical constructor; create a new record when data changes |
| `final` instance/static field of a hidden class | Yes, if access rights/module permit | **No** | Initialize before use; separate mutable state if needed |
| `final` instance field of an ordinary class (not record/hidden) | Yes, if access rights/module permit | Possible under narrow conditions on Java 17; **unsafe to rely on** | Constructor/factory/deserialization following proper lifecycle |
| **Non-final** field | Depends on access rights | Possible, if receiver and data type are valid | Intentional setter/API or reflection when truly necessary |

The above conditions describe the contract of **Java 17 Core Reflection**. Tools outside Core Reflection, internal APIs, or JVM variants do not provide a general guarantee that this restriction can or is permitted to be bypassed.

## 2. `static final`: Cannot Be Rewritten with `Field.set`

`static` means the field belongs to the class, not an instance. `final` means the reference or value may only be validly assigned during the defined initialization process. The `static final` pair is commonly used for constants:

```java
class Configuration {
    static final int MAX_RETRIES = 3;
    static final String SERVICE_NAME = "orders";
}
```

These are primitive/String **constant variables** with constant expressions, so other Java code can **inline the values at compile time**. Modifying bytecode or attempting to interfere with storage at runtime does not guarantee that call sites using the constant will observe the new value.

Not every `static final` field is a compile-time constant:

```java
class Defaults {
    static final Integer TIMEOUT = Integer.valueOf(30);
    static final java.util.List<String> TAGS = new java.util.ArrayList<>();
}
```

`TIMEOUT` is not a constant variable according to the JLS because it uses a wrapper and factory method; `TAGS` holds a `final` reference, though the list can be modified via `TAGS.add(...)` if unprotected. **Neither field can be reassigned via `Field.set(...)`** on Java 17.

Illustrative reflection example:

```java
Field field = Configuration.class.getDeclaredField("MAX_RETRIES");
field.setAccessible(true);
int oldValue = field.getInt(null); // OK, null receiver for static field
field.setInt(null, 7);             // IllegalAccessException
```

Here `getDeclaredField` succeeds, `setAccessible(true)` can succeed, and `getInt(null)` can read the value, but `setInt` is rejected because the field is `static final`. In static operations, the receiver argument is ignored, so passing `null` is the clearest approach.

**Do not confuse:** `Field.setInt(...)` throws a **checked `IllegalAccessException`** in this case, even though `setAccessible(true)` succeeded. `InaccessibleObjectException`, on the other hand, is typically related to **the access-opening request itself** being blocked by a module, which is a different stage.

For interfaces, every declared field is implicitly `public static final`, so it is subject to the same restriction. If the goal is to change configuration at runtime, replace a `static final` constant with an intentional mutable configuration mechanism, an immutable snapshot replaced atomically, or a reallocated configuration object; consider thread-safety when data is shared across multiple threads.

## 3. Record Fields: Preserving Initialized Component State

Records have been officially supported since Java 16. Example:

```java
record Point(int x, int y) {}

Point original = new Point(2, 5);
Point changed  = new Point(8, original.y()); // create a new record
```

The compiler generates fields corresponding to the record components `x` and `y`; each component field is a **`private final` instance field**. A record is a final class; no additional instance fields can be declared in the record body. Setting components occurs during the execution of the canonical constructor (or compact constructor via Java's automatic assignment mechanism), not via `Field.set` after the record is created.

With `record Point(int x, int y)`:

```java
Field x = Point.class.getDeclaredField("x");
x.setAccessible(true);
System.out.println(x.getInt(original)); // 2
x.setInt(original, 99);                 // IllegalAccessException
```

**Why is modification disallowed?** The record contract relies on a stable set of components: the accessors `x()`, `y()`, along with the default `equals`, `hashCode`, and `toString` use the component state. Secretly modifying a component after initialization breaks the semantics that the record API must uphold.

Distinguish the following:

- `record Point(int x)` can declare a **static field** `static int counter`; if it is **not final** and access rights are valid, that field can still be updated. The rule does not mean "every field in a record is write-prohibited".
- If a record has a `static final` field, that field is already restricted under the `static final` rule.
- If a component has a reference type pointing to a mutable object, **the referenced object may still be mutable**. For example, `record Basket(List<String> items) {}` does not automatically protect `items` from changes inside the `List`. Defensive copying is needed if deep immutability is desired:

```java
record Basket(java.util.List<String> items) {
    Basket {
        items = java.util.List.copyOf(items);
    }
}
```

In the compact constructor above, the parameter value `items` is normalized before the compiler assigns it to the component field. `List.copyOf` also rejects `null` elements and creates a copy that cannot be modified via the List API, though it does not deep-copy element objects if they are mutable.

## 4. `final` Fields of a Hidden Class: Boundaries Preserved in Dynamic Class Creation

A **hidden class** is a class dynamically created from bytecode using an API such as `MethodHandles.Lookup.defineHiddenClass(...)` (since Java 15), typically used by runtimes/frameworks to generate implementations, lambdas, or helper logic. A hidden class:

- Is defined from class-file bytes in the context of a `Lookup`.
- Can be checked using `Class.isHidden()`.
- Has no binary name usable for lookup via `Class.forName(...)` or `ClassLoader.loadClass(...)` like a normal class.
- Still has reflection metadata and fields, for example `hiddenType.getDeclaredField("value")`.
- Can have regular fields or `final` fields. **Only `final` fields declared in a hidden class are non-modifiable final under this category**; non-final fields remain subject to normal access/type rules.

Conceptual example:

```java
Class<?> hiddenType = lookup.defineHiddenClass(bytes, true).lookupClass();
System.out.println(hiddenType.isHidden()); // true

Field value = hiddenType.getDeclaredField("value");
value.setAccessible(true);
Object current = value.get(hiddenInstance); // can read
value.set(hiddenInstance, replacement);     // IllegalAccessException if final
```

This is a snippet **illustrating a context** that already has valid `lookup`, `bytes`, `hiddenInstance`, and `replacement` variables; the full example below constructs all of these variables.

Passing class-file bytes is not a decorative detail: `defineHiddenClass` does not accept an existing `Class<?>`, but rather **bytecode**, and returns a `Lookup` on the newly created class. The package of the class bytes must match the lookup class, and module/access permissions must satisfy the API requirements. If the bytecode is invalid or the package is wrong, defining the class will fail **before reaching the field-write step**.

**Do not infer:** "hidden class" is not the same as "private field". A hidden class can contain a public field and still be prohibited from being written if that field is `final`. `setAccessible(true)` does not change this.

## 5. What Exactly Do `setAccessible`, `canAccess`, and `Field.set` Check?

The three operations answer different questions.

| API | Question | Key outcome |
| --- | --- | --- |
| `SomeType.class.getDeclaredField(...)` | Is there a field directly declared with this name? | `Field` or `NoSuchFieldException` |
| `field.trySetAccessible()` | Can access-check suppression be requested? | `true`/`false`; does not mean writable |
| `field.setAccessible(true)` | Is bypassing Java language access checks allowed if module rules permit? | May succeed or throw `InaccessibleObjectException` |
| `field.canAccess(receiver)` | With this receiver, is the field **currently accessible**? | `boolean`, does not guarantee `set` will succeed |
| `field.get(receiver)`, `getInt(receiver)` | Can the value be read? | Value or access/receiver/type exception |
| `field.set(receiver, value)`, `setInt(receiver, value)` | Can a valid value be written? | Success or `IllegalAccessException`/`IllegalArgumentException`/receiver error |

`getDeclaredField` is a method of **`Class`**, not of `Field`. When reading code, it is necessary to distinguish the class owning each API.

There are two independent layers of restriction:

1. **Java access control/JPMS:** `public`, `private`, package scope, `exports`, and `opens` determine accessibility. For a package of another module not opened for deep reflection, `setAccessible(true)` may throw `InaccessibleObjectException`; `trySetAccessible()` may return `false`.
2. **Non-modifiable final:** even when the class and module permit access, `Field.set` does not grant write permission for the three groups mentioned. When write conditions are not met, `IllegalAccessException` can still occur.

To check the restriction based on metadata, a **preliminary detector** can be built (this only checks the `final` category condition on Java 17, not a full write-permission validator):

```java
static boolean isNonModifiableFinal(java.lang.reflect.Field field) {
    int modifiers = field.getModifiers();
    Class<?> owner = field.getDeclaringClass();

    return java.lang.reflect.Modifier.isFinal(modifiers)
            && (java.lang.reflect.Modifier.isStatic(modifiers)
                || owner.isRecord()
                || owner.isHidden());
}
```

Returning `false` **does not promise** that `Field.set` will definitely succeed: access rights may be missing; the receiver may be of the wrong class, the value type may be incompatible, or the JVM may apply another restriction. Returning `true` accurately describes the three non-modifiable final groups in JDK 17.

**Exceptions should be read accurately:**

- `NoSuchFieldException`: wrong lookup name or field not found within the scope of the called API.
- `InaccessibleObjectException`: opening access via `setAccessible(true)` is not permitted, usually due to module/package rules.
- `IllegalAccessException`: access or write is denied in `Field.get/set`; for the three final groups, the write operation is denied even when opening access succeeded.
- `IllegalArgumentException`: wrong receiver type, or value passed to setter cannot be validly converted; do not automatically conclude it is a `final` error.
- `NullPointerException`: `null` receiver for an instance field; for a static field, the receiver is ignored.
- `ExceptionInInitializerError`: static initialization was triggered and failed, not a `final` property error.

## 6. Runnable Java 17+ Example: Three Write-Prohibited Groups and One Requiring Caution

The program below compiles as **a single file**, demonstrating successful reads followed by write rejections for `static final`, a record component, and a `final` field of a hidden class. It also compares these with an ordinary final instance field: Java 17 Core Reflection can write this category when access is opened, but you should not rely on that result for application design.

Name the file **`FinalFieldRulesDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Field;

public class FinalFieldRulesDemo {
    private static final int STATIC_CONSTANT = 7;

    record Point(int x) {}

    static final class Ordinary {
        final int x;
        Ordinary(int x) { this.x = x; }
    }

    // Template compiled by javac into a separate .class file.
    static class HiddenTemplate {
        public final int x;
        public HiddenTemplate(int x) { this.x = x; }
    }

    public static void main(String[] args) throws Exception {
        // A. static final: accessible/readable, not writable.
        Field staticField =
                FinalFieldRulesDemo.class.getDeclaredField("STATIC_CONSTANT");
        staticField.setAccessible(true);
        System.out.println("static read: " + staticField.getInt(null));
        try {
            staticField.setInt(null, 8);
        } catch (IllegalAccessException e) {
            System.out.println("static write: " + e.getClass().getSimpleName());
        }

        // B. Record component: private final instance field.
        Point point = new Point(3);
        Field recordField = Point.class.getDeclaredField("x");
        recordField.setAccessible(true);
        System.out.println("record read: " + recordField.getInt(point));
        try {
            recordField.setInt(point, 9);
        } catch (IllegalAccessException e) {
            System.out.println("record write: " + e.getClass().getSimpleName());
        }

        // C. Ordinary final: Java 17 can write via reflection
        // under certain conditions; do not use this technique as a design.
        Ordinary ordinary = new Ordinary(4);
        Field ordinaryField = Ordinary.class.getDeclaredField("x");
        ordinaryField.setAccessible(true);
        ordinaryField.setInt(ordinary, 10);
        System.out.println(
                "ordinary reflection read: " + ordinaryField.getInt(ordinary));

        // D. Get bytecode from the nested class that javac just generated.
        byte[] templateBytes;
        try (InputStream in = FinalFieldRulesDemo.class.getResourceAsStream(
                "FinalFieldRulesDemo$HiddenTemplate.class")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing compiled HiddenTemplate class");
            }
            templateBytes = in.readAllBytes();
        }

        // Create hidden class from bytecode, rather than using Class.forName.
        Class<?> hiddenType = MethodHandles.lookup()
                .defineHiddenClass(templateBytes, true,
                        MethodHandles.Lookup.ClassOption.NESTMATE)
                .lookupClass();

        Object hidden = hiddenType.getDeclaredConstructor(int.class)
                .newInstance(5);
        Field hiddenField = hiddenType.getDeclaredField("x");
        hiddenField.setAccessible(true);

        System.out.println("hidden: " + hiddenType.isHidden());
        System.out.println("hidden read: " + hiddenField.getInt(hidden));
        try {
            hiddenField.setInt(hidden, 6);
        } catch (IllegalAccessException e) {
            System.out.println("hidden write: " + e.getClass().getSimpleName());
        }
    }
}
```

So that the bytecode of `HiddenTemplate` can be found via `getResourceAsStream`, keep the `.class` files generated by `javac` **together on the classpath**, for example by running directly in the directory where compilation occurred:

```bash
javac --release 17 FinalFieldRulesDemo.java
java FinalFieldRulesDemo
```

Standard `stdout` of the program:

```text
static read: 7
static write: IllegalAccessException
record read: 3
record write: IllegalAccessException
ordinary reflection read: 10
hidden: true
hidden read: 5
hidden write: IllegalAccessException
```

**Result explanation:**

1. `STATIC_CONSTANT` is found and read as `7`; `setInt(null, 8)` throws `IllegalAccessException` because it is `static final`.
2. `Point.x` can be read as `3` after opening access; the setter throws `IllegalAccessException` because it is a `final` component of a record.
3. `Ordinary.x` belongs to a regular class, so in Java 17 it can be set via reflection after `setAccessible(true)`. The line `ordinary reflection read: 10` only verifies the value through **`Field.getInt` itself**; do not use this result to infer that all code/JIT/threads will see the new value.
4. `HiddenTemplate` is compiled into class-file bytes. `defineHiddenClass(..., NESTMATE)` defines a new class, `isHidden()` returns `true`; field `x` can be read as `5` but cannot be written as `6` via reflection.
5. The example does not require `--add-opens` because all code is owned by us in the same unnamed module, with appropriate access conditions. For classes from another module, the `setAccessible(true)` step may fail **before** reaching the write operation.

`Lookup.ClassOption.NESTMATE` allows the hidden class to join the nest of the lookup class, giving the operations in the example appropriate access rights. It **does not** grant write permission to the `final` fields of the hidden class.

## 7. Why Can't Common Tricks "Fix" This?

### 7.1. `setAccessible(true)` Does Not Unlock `final`

This API handles **accessibility** checks, not changing the field category. For the three non-modifiable final groups, it can only allow reading (and metadata access), not write permission. `trySetAccessible()==true` or `canAccess(receiver)==true` also **does not** prove a field is writable.

### 7.2. Cannot Rely on Modifying the `final` Modifier via Reflection

Word-of-mouth snippets like finding `Field.class.getDeclaredField("modifiers")` and clearing the `Modifier.FINAL` bit are not valid APIs, are not guaranteed to run on modern Java, and do not alter the non-modifiable final contract. Moreover, `Class.getDeclaredFields()` may hide sensitive internal fields of core reflection. Do not use this approach in tutorials, libraries, or production code.

### 7.3. `VarHandle` Is Not a Bypass for Writing `final`

`java.lang.invoke.VarHandle` can read a `final` field when the lookup has sufficient access, but for a VarHandle pointing to a **read-only variable** such as a final field, write access modes (e.g., `set`, `setVolatile`) and atomic updates are not supported; calling them leads to `UnsupportedOperationException`. You can query `handle.isAccessModeSupported(VarHandle.AccessMode.SET)` before use.

```java
// Illustration in a context that already has VarHandle handle for the final field:
if (!handle.isAccessModeSupported(
        java.lang.invoke.VarHandle.AccessMode.SET)) {
    System.out.println("write unsupported");
}
```

Internal/unsupported APIs such as `sun.misc.Unsafe`, memory manipulation, privileged agents, or bytecode rewriting to force field mutation are not guaranteed workarounds. Even if they have an effect on a specific runtime, they can still be wrong with respect to class loading, constant folding, the memory model, module boundaries, or JVM versions. **Do not rely on those workarounds to preserve application correctness.**

### 7.4. Use `--add-opens` Only When the Real Error Is Module Access

`--add-opens module/package=targetModule` (or `ALL-UNNAMED` depending on the runtime model) can resolve certain cases where a module disallows deep reflection and help `setAccessible(true)` succeed, but it **does not elevate write permissions** for `static final`/record final/hidden-class final on Java 17.

You must distinguish:

- `setAccessible(true)` reports `InaccessibleObjectException` → review `opens` and modules.
- `setAccessible(true)` succeeds but `setInt` reports `IllegalAccessException` for a non-modifiable final → must change the data/lifecycle design.
- `setInt` reports `IllegalArgumentException` → check the value, receiver, primitive/wrapper types, and conversions.

## 8. Proper Design When Data Needs to Change

| Need | Design approach |
| --- | --- |
| Update parameters while the program is running | Place state in managed mutable fields, a configuration object with a replacement API, or external configuration that is reloaded; synchronize appropriately |
| Shared constant value that never changes | Keep `static final`; load from initial configuration via initializer/factory if not a constant expression |
| Change a component of a record | Create a **new record** with the new component; update the reference in the state-management layer |
| Record containing a collection with immutability requirements | Defensively copy in the constructor and accessor when needed; check mutable elements |
| Add operational state to a hidden class | Use a **non-final** field if the model requires it and access rules permit, or keep mutable state in an external object |
| Serialization/deserialization of legacy objects | Prefer appropriate constructors/factories/serializers; only perform special handling on ordinary blank finals before publishing if there is a clear contract |
| Framework cannot instantiate object due to access error | Review `exports`/`opens`, public APIs, caller lookup, and module structure; do not treat that as permission to modify `final` |

For records, a useful pattern is creating a new instance:

```java
record Settings(String host, int port) {
    Settings withPort(int newPort) {
        return new Settings(host, newPort);
    }
}

Settings oldSettings = new Settings("localhost", 8080);
Settings updated = oldSettings.withPort(9090);
```

The snippet above illustrates the *copy with change* design pattern for immutable data. `oldSettings` remains unchanged; `updated` is a different instance. In a multi-threaded system, the state-storage layer can use `AtomicReference<Settings>` or an appropriate synchronization mechanism to replace the entire snapshot explicitly.

## 9. Diagnostic Procedure When `Field.set` Fails

Suppose a framework reports `IllegalAccessException` when attempting to write a field. Before handling it, record:

1. `field.getDeclaringClass().getName()` and the field name from `field.getName()`.
2. `static` and `final` modifiers via `Modifier.isStatic(...)` and `Modifier.isFinal(...)`.
3. `field.getDeclaringClass().isRecord()` and `.isHidden()`.
4. `canAccess`/`trySetAccessible` status, and module information of the declaring class and caller.
5. The receiver object (`null` for static) and the assigned data type (for instance fields, check receiver compatibility).
6. Whether the original exception type came from the **open-access** operation or the **write** operation; keep the stack trace so the two stages are not mixed up.

Preliminary classification code, **for observation only**:

```java
static String fieldCategory(java.lang.reflect.Field field) {
    Class<?> owner = field.getDeclaringClass();
    int flags = field.getModifiers();
    boolean finalField = java.lang.reflect.Modifier.isFinal(flags);

    if (!finalField) return "not final";
    if (java.lang.reflect.Modifier.isStatic(flags)) return "static final";
    if (owner.isRecord()) return "record final";
    if (owner.isHidden()) return "hidden-class final";
    return "ordinary instance final";
}
```

In the case where a hidden class also has a `static final` field, the order in the helper above classifies it as `static final` because that alone is sufficient to block writing. Both conditions can be true simultaneously; the helper is not intended to mark them as mutually exclusive.

Example of an error:

```text
java.lang.IllegalAccessException: Cannot set static final int field ...
```

Interpretation: lookup has already found the field, but **the write operation** is blocked. Trying to switch to `getDeclaredField`, `setAccessible`, or `--add-opens` will not resolve the `static final` rule if read permission is already sufficient.

## 10. Self-Check Exercises

**A.** A `private static final int LIMIT` field in a class in the same module: `setAccessible(true)` succeeds, `getInt(null)` returns `10`. Will calling `setInt(null, 20)` succeed? Why?

**B.** `record User(long id, String name) {}`: a framework finds `Field name` and `trySetAccessible()` returns `true`. Can `nameField.set(user, "new")` be called? If you want to change the name, how must it be done?

**C.** A class created via `Lookup.defineHiddenClass` has `final int code` and `int counter`. According to Java 17's non-modifiable final rule, which field is definitely blocked from being written with `Field.set`, and which field *can* be written when access rights permit?

**D.** `static final List<String> NAMES = new ArrayList<>()`: the reference cannot be reassigned via reflection; so what can `NAMES.add("x")` do? How must it be designed if true immutability is desired?

**E.** On the same record field, `setAccessible(true)` can succeed while `Field.set(...)` throws `IllegalAccessException`. Do these two results contradict each other?

**Answers:**

- **A:** No; `LIMIT` is `static final`, which belongs to the non-modifiable final group. The setter throws `IllegalAccessException` even when read permission is available.
- **B:** No; the `name` component is stored in a `private final` field of the record. Create `new User(user.id(), "new")` and replace the reference managing the object.
- **C:** `code` is blocked because it is `final` in a hidden class; `counter` is not `final`, so it can be written if access/receiver/data type are valid.
- **D:** Calling `add` can mutate **the contents of the list** because `final` only locks the reference. To make the list immutable, use an immutable snapshot and do not expose a mutable backing collection.
- **E:** No. `setAccessible` evaluates permission to bypass access checks; `Field.set` also enforces the non-modifiable final write rule.

## 11. Java 17 Reference Sources

- [Javadoc `java.lang.reflect.Field` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `setAccessible` and `set`, the three categories of non-modifiable final fields, and conditions for writing ordinary final fields.
- [Javadoc `MethodHandles.Lookup` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass` and `NESTMATE`.
- [Javadoc `VarHandle` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): unsupported access modes on read-only/final fields.
- [Java 17 Records](https://docs.oracle.com/en/java/javase/17/language/records.html): record components, constructors, and data model.

**Takeaway:** `setAccessible(true)` can open read access or bypass certain access checks, **it does not unlock every `final` field**. On Java 17, `static final`, record `final`, and hidden-class `final` are the three categories that **cannot be written using `Field.set*`**. When data needs to change, place the change in constructors, new objects, or explicitly designed mutable state.