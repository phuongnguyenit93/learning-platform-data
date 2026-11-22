# Distinguishing Reading a `final` Field from Modifying a `final` Field in Java Reflection

`final` expresses the intent that **the value of a variable is not reassigned after initialization completes according to the Java language rules**. When using Reflection, learners often mistakenly assume that if a `private final` field can be read using `Field#get(...)`, it can also be modified using `Field#set(...)`. These two operations have different conditions and limits.

**Core takeaway of this lesson:** Reflection may allow **reading** a `final` field once access rules are satisfied; that **does not prove** Reflection is allowed to **write** a `final` field. Several categories of `final` fields are always non-modifiable via `Field#set` even when accessibility has been enabled, while writing an ordinary instance `final` field is a special capability that becomes increasingly restricted starting in JDK 26.

## 1. What does `final` guarantee at the Java declaration level?

A field declared `final` can only be assigned according to the permitted initialization rules:

~~~java
class Configuration {
    private final int timeoutSeconds;              // blank final
    private static final String PRODUCT = "Demo";  // static final

    Configuration(int timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }

    int timeoutSeconds() {
        return timeoutSeconds;
    }
}
~~~

This is an **illustrative snippet**, without a standalone `main`. After the `Configuration` constructor finishes, ordinary Java source code cannot write `configuration.timeoutSeconds = 10;` because this field is `final`.

Distinctions:

- **`final` instance field:** each instance has its own state; the value is normally established in a field initializer, an instance initializer, or a constructor.
- **`static final` field:** attached to the class rather than an instance; initialized only according to the rules for static fields.
- **`private` and `final` are independent:** `private` governs access at the Java language level, whereas `final` governs assignability. A field can be `public final`, `private final`, `static final`, etc.
- **`final` does not make the referenced object deeply immutable:** `private final List<String> names` keeps the **reference** fixed after initialization in Java source, but if the list is mutable then `names.add(...)` can still modify its contents.

The Java Memory Model guarantees for `final` fields help programs have a reliable initialization model. Mutating `final` via Reflection after initialization can break assumptions made by the compiler/JVM and by threads reading the data. Therefore, mutation techniques should not be treated as a normal way to update configuration.

## 2. Two Reflection operations: reading and writing

A `java.lang.reflect.Field` object supports both metadata and value operations:

| Need | API | What to check |
| --- | --- | --- |
| Check whether a field has `final` | `Modifier.isFinal(field.getModifiers())` | Only reads the modifier; **does not** indicate whether it can be written |
| Look up a non-`public` field | `type.getDeclaredField("name")` | Only looks up metadata of a directly declared field; does not grant access by itself |
| Check current access permission | `field.canAccess(target)` | Instance uses an object; static uses `null` |
| Try enabling suppression of Java access checks | `field.trySetAccessible()` | Returns `true`/`false`; does not guarantee write capability for a `final` field |
| Read a field | `field.get(target)`, `getInt(target)`... | Requires access permission; returns the corresponding value |
| Try writing a field | `field.set(target, value)`, `setInt(target, n)`... | Requires actual write permission; `final` has additional restrictions and JDK-version-dependent rules |

*Remember:* there are at least **two questions** when using `Field`: whether you are allowed to **access** the member via Reflection, and whether you are allowed to **modify** this specific field. The two answers can respectively be "yes" and "no".

### `getDeclaredField` only looks up metadata, without manipulating values

~~~java
Field field = SomeType.class.getDeclaredField("value");
boolean isFinal = Modifier.isFinal(field.getModifiers());
~~~

This is an **illustrative snippet**, assuming `SomeType` has a `value` field and `Field` and `Modifier` are imported. Calling `getDeclaredField` can return the `Field` object representing a `private final` field. However, `Field` is metadata, so it **does not automatically imply** that a subsequent `get` or `set` has been granted permission.

## 3. Reading `final` instance and `static final` fields

Reading a `final` field via Reflection essentially follows the access rules of `Field`:

1. Obtain the `Field` from the right `Class<?>` object. Use `getDeclaredField` if you need a directly declared `private` field.
2. For an **instance field**, pass an instance of the right type to `canAccess`/`get`. For a **static field**, pass `null`.
3. If access is not yet allowed in the current state, check whether permission can be enabled using `trySetAccessible()` when genuinely needed.
4. Once permitted, call `get`, `getInt`, `getLong`, or a specialized read method. Reading a `final` field **does not change** its value.

Note on Java modules: since Java 9, `trySetAccessible()` can be rejected by JPMS boundaries. In this lesson's example, all classes reside in the **unnamed module of the same class loader**, so enabling deep access into application classes is allowed. Do not assume the same outcome when passing a `Field` to a helper in another module or accessing a library module that has not opened its package.

### Runnable example: reading three kinds of `final` fields

Create the file **`ReadFinalDemo.java`**, using Java 17+:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

class FinalData {
    private final int count;
    private static final String LABEL = "fixed";

    FinalData(int count) {
        this.count = count;
    }
}

record FinalRecord(int value) {}

public class ReadFinalDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        FinalData data = new FinalData(7);
        Field count = FinalData.class.getDeclaredField("count");
        System.out.println("Instance final: "
                + Modifier.isFinal(count.getModifiers()));
        System.out.println("Read before: " + count.canAccess(data));
        System.out.println("Open for read: " + count.trySetAccessible());
        System.out.println("Instance value: " + count.getInt(data));

        Field label = FinalData.class.getDeclaredField("LABEL");
        System.out.println("Static final: "
                + Modifier.isFinal(label.getModifiers()));
        System.out.println("Open static: " + label.trySetAccessible());
        System.out.println("Static value: " + label.get(null));

        FinalRecord record = new FinalRecord(42);
        Field recordValue = FinalRecord.class.getDeclaredField("value");
        System.out.println("Record final: "
                + Modifier.isFinal(recordValue.getModifiers()));
        System.out.println("Open record: "
                + recordValue.trySetAccessible());
        System.out.println("Record value: " + recordValue.getInt(record));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ReadFinalDemo.java
java ReadFinalDemo
~~~

**Stdout (verified on JDK 21):**

~~~text
Instance final: true
Read before: false
Open for read: true
Instance value: 7
Static final: true
Open static: true
Static value: fixed
Record final: true
Open record: true
Record value: 42
~~~

**Analysis:**

- `Modifier.isFinal(...)` reads the modifier flags of `count`, `LABEL`, and the backing field for the record component `value`; all three are `final`.
- `count` is a `private final` field of a class different from `ReadFinalDemo`, so `canAccess(data)` is initially `false`. After `trySetAccessible()` succeeds, `getInt(data)` reads the number `7`.
- `LABEL` is `static final`: pass `null` to `get(null)` because the field belongs to the class, not an instance.
- The record component `value` also has a compiler-generated `private final` field; the example reads that field after enabling access.
- The program **does not use `Field#set`**. The success of all three read operations **provides no evidence** that the three fields can be written using Reflection.

**Why doesn't the example use nested classes inside `ReadFinalDemo`?** Nested classes can be *nestmates*, having mutual access to each other's `private` members under Java rules, which causes `canAccess(...)` to return `true` initially and obscures the point of trying to enable access. The top-level classes `FinalData` and `ReadFinalDemo` in the example are in two separate nests.

## 4. Successful reading does not grant write permission

The example in section 3 demonstrated that three different `final` fields can be read. To decide whether `Field.set` should be called, you must also consider the **field category** and the **running runtime**. `trySetAccessible()` only handles requesting to bypass Java access checks; it does not remove the write restrictions of `final`.

| Field | `Field.get` with sufficient access | `Field.set` after enabling access |
| --- | --- | --- |
| Instance `final` of an ordinary class | Can be read | On JDK 17–25 there is a special write path when conditions are met; not a state-updating API |
| `static final` | Can be read | Cannot be written via Reflection setter |
| `final` in a record | Can be read | Cannot be written via Reflection setter |
| `final` in a hidden class | Can be read | Cannot be written via Reflection setter |
| Non-`final` field | Can be read | Can be written if access permission, receiver, and data type match |

**How to interpret this:** if `label.trySetAccessible()` succeeds and then `label.get(null)` returns `"fixed"`, we only know that the **read** operation on `static final LABEL` is valid in that context. Attempting `label.set(null, "changed")` is still rejected with `IllegalAccessException`. Similarly, a record may allow reading its component field but does not allow overwriting that field.

JDK 26 adds the JEP 500 policy for writing **ordinary final instance fields** via deep reflection: unauthorized operations may emit warnings or be blocked depending on configuration. Those options do not turn `static final`, record-final, or hidden-class-final into writable fields. Therefore, do not take a write result from one JDK and assume it holds across every other JDK.

## 5. Choosing the appropriate way to read

- If the class already provides a **public getter/accessor**, prefer it. For records, an accessor such as `recordValue.value()` clearly expresses the object's contract.
- If you need **metadata**, use `getDeclaredField`, `getModifiers`, or `getDeclaredFields` without unnecessarily opening value read access.
- If a tool genuinely needs to read a **private field**, identify the correct declaring class, receiver (an instance or `null` for static), and module access permissions. `trySetAccessible() == false` can be a valid outcome when a package is not open to the caller.
- If the real requirement is to **update a value**, do not turn a read workflow into a `set` call out of habit. Look for a constructor/factory, an update method, or create a new instance; subsequent lessons will analyze those limits and alternatives in depth.

## 6. Self-check

1. `getDeclaredField("count")` returns a `Field` for `private final int count`. Can you assert that `getInt(data)` will run immediately? **No**; you must check the caller's access permission.
2. `trySetAccessible()` returns `true` for `private static final String LABEL`. Can you call `Field.set(null, "new")`? **No**; `static final` does not gain write permission by enabling accessible.
3. Reading `record FinalRecord(int value)` via `getInt(record)` succeeds; can you infer that modifying the component field is possible? **No**; record final fields belong to the category that cannot be written via `Field.set`.
4. `final List<String>` points to an `ArrayList`. If calling `add` succeeds, did you just reassign the field? **No**; only the contents of the referenced object changed.

**Key takeaway:** looking up metadata, requesting access, reading, and writing are **four distinct operations**. This lesson teaches the **read** path and how to recognize the boundary toward **writing**; when writing is needed, you must inspect each `final` category together with the Java version separately before deciding on a design.

### References

- [Java SE 17 — Field API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 17 — AccessibleObject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [JEP 500 — Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
