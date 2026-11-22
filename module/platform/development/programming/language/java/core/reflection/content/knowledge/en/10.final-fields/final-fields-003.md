# Static final: Cannot Be Written by Normal Reflection Access Suppression

## 1. Core Question

In Java, a field declared `static final` is a **field belonging to the class** (or interface), and **its reference/value cannot be reassigned after being initialized** according to the rules of the language. When using Reflection, even when `Field.setAccessible(true)` or `Field.trySetAccessible()` has allowed accessing a member that was private, normal write APIs such as `Field.set(...)` and `Field.setInt(...)` are still **not granted permission to write to `static final`**.

Example:

~~~java
class Config {
    private static final int PORT = 8080;
}
~~~

Calling `Config.class.getDeclaredField("PORT")` can obtain metadata about the field; if module permissions allow, `setAccessible(true)` can allow reading `PORT`. However, calling `field.setInt(null, 9090)` will throw `IllegalAccessException`. Do not confuse obtaining a `Field` or enabling access with having permission to **modify** that field.

An important rule in JDK 17+ (and continuing in the JDK 26 API): **every `static final` field declared in a class or interface is a *non-modifiable final field* for `java.lang.reflect.Field`**. `AccessibleObject.setAccessible` and `Field.set` themselves define this limit; there is no distinction that permits writing merely because the field is `private`, `public`, a primitive type, `String`, or an object type.

## 2. Understanding the Three Layers of Checks Correctly

For a `private static final` field, there are three distinct questions:

1. **Can the field declaration be found?** `getDeclaredField("name")` looks up a field declared in the class, regardless of whether it is `public` or `private`. It can throw `NoSuchFieldException` if the name is wrong.
2. **Is accessing that member permitted?** `setAccessible(true)` requests relaxing Java language access checks; `trySetAccessible()` returns `true`/`false` depending on permissions. The Java Platform Module System (JPMS) can still deny deep reflection when the package is not open to the caller.
3. **Is writing to the field permitted?** Even if question 2 succeeds, a `static final` field remains a *non-modifiable final field*. Calling normal Reflection setters will throw `IllegalAccessException`.

These mechanisms operate at different layers. `setAccessible(true)` **does not remove the `final` modifier**, nor does it allow an application to bypass the write rules of `Field.set`.

| Operation | On a `static final` field |
| --- | --- |
| `Class.getDeclaredField("X")` | Obtains metadata successfully if the field exists; does not grant read/write permission by default. |
| `Field.getModifiers()` | Can inspect `Modifier.isStatic(...)` and `Modifier.isFinal(...)`. |
| `Field.setAccessible(true)` | May succeed if the caller has permission to open access; only supports reading if the field is *non-modifiable final*. |
| `Field.trySetAccessible()` | May return `true`; this result **does not** mean writing is allowed. |
| `Field.get(null)` / `getInt(null)` | Reads if permitted; the object argument is ignored for static fields. |
| `Field.set(null, value)` / `setInt(null, value)` | Throws `IllegalAccessException` because there is no write permission for `static final`, even after enabling access. |

With Reflection setters for static fields, `null` is normally passed as the object argument because the field is not tied to an instance. With instance fields, an object of the appropriate type must be passed. Passing `null` **is not the reason** why writing `static final` is rejected.

## 3. Complete Example, Runnable on Java 17 and Above

Save the following code into the file `StaticFinalDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;

class Settings {
    private static final int LIMIT = 10;
    private static final List<String> TAGS = new ArrayList<>(List.of("A"));
    private static int count = 1;

    static List<String> tags() {
        return TAGS;
    }
}

public class StaticFinalDemo {
    public static void main(String[] args) throws Exception {
        Field limit = Settings.class.getDeclaredField("LIMIT");
        System.out.println("static final: "
                + (Modifier.isStatic(limit.getModifiers())
                && Modifier.isFinal(limit.getModifiers())));
        System.out.println("accessible: " + limit.trySetAccessible());
        System.out.println("LIMIT: " + limit.getInt(null));

        try {
            limit.setInt(null, 20);
        } catch (IllegalAccessException e) {
            System.out.println("change LIMIT: " + e.getClass().getSimpleName());
        }

        Field tags = Settings.class.getDeclaredField("TAGS");
        tags.setAccessible(true);
        try {
            tags.set(null, new ArrayList<>(List.of("X")));
        } catch (IllegalAccessException e) {
            System.out.println("replace TAGS: " + e.getClass().getSimpleName());
        }

        Settings.tags().add("B");
        System.out.println("mutate TAGS object: " + Settings.tags());

        Field count = Settings.class.getDeclaredField("count");
        count.setAccessible(true);
        count.setInt(null, 2);
        System.out.println("change non-final static: " + count.getInt(null));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 StaticFinalDemo.java
java StaticFinalDemo
~~~

Stdout verified with the program compiled in Java 17 compatibility mode:

~~~text
static final: true
accessible: true
LIMIT: 10
change LIMIT: IllegalAccessException
replace TAGS: IllegalAccessException
mutate TAGS object: [A, B]
change non-final static: 2
~~~

**Explanation of each result:**

- `LIMIT` has both the `static` and `final` flags. `trySetAccessible()` returns `true` because the example code runs on the classpath: the `Settings` class belongs to the unnamed module whose package is open to reflection. That allows reading `10`.
- `limit.setInt(null, 20)` is not permitted to write because the field is `static final`. `IllegalAccessException` is the outcome that must be handled, even though the earlier access-suppression call succeeded.
- `TAGS` is a **final reference** to an `ArrayList`. `tags.set(null, new ArrayList<>(...))` attempts to replace the **field reference**, so it also fails.
- `Settings.tags().add("B")` changes the **state of the object** already referenced by the field, without reassigning the field itself. Because the object is a mutable `ArrayList`, the operation succeeds and prints `[A, B]`.
- `count` is declared `static` but **not `final`**, so Reflection can modify the field after opening access. The result `2` shows that the write restriction above is tied to `final`.

This lesson does not rely on JVM internal manipulation tricks. The ability to open access comes from the example code residing in the unnamed module; for a class in a **named module** that has not opened its package to the caller, `trySetAccessible()` can return `false` before the read step even happens.

## 4. `final` Preserves the Reference, Not Object Immutability

Consider:

~~~java
private static final List<String> ITEMS = new ArrayList<>();
~~~

Two fundamentally different actions:

- **Replacing the field:** `ITEMS = new ArrayList<>();` is blocked by the compiler after initialization; `Field.set(null, anotherList)` is also not permitted for `static final`.
- **Changing the object's state:** `ITEMS.add("x")` can still run because `ArrayList` is a mutable structure. Here the field still points to the same object.

Similarly, `static final StringBuilder BUILDER = new StringBuilder("A");` allows `BUILDER.append("B")` even though it does not allow `BUILDER = new StringBuilder("C")`. Conversely, `String` is immutable, so there is no operation that alters the contents of the `String` object itself.

To obtain a read-only collection at the API level, consider `List.of(...)` or an immutable copy via `List.copyOf(...)`. Even then, you must consider the mutability of **the elements** if they are complex objects; `final` and a collection that rejects structural modification do not guarantee deep immutability of the entire object graph.

## 5. Compile-Time Constants vs. Fields Initialized at Runtime

Some `static final` fields are **constant variables** according to the Java Language Specification: they have a primitive type or `String`, are declared `final`, and are initialized with a *constant expression*. Example:

~~~java
public static final int TIMEOUT = 30;
public static final String MODE = "safe";
~~~

When other code references these constants, the compiler may write the constant value directly into the bytecode of the calling code (*inlining*). Changing a value in a library without **recompiling** the consuming code can cause the program to keep seeing the old value. Therefore, never redesign runtime configuration by trying to mutate constant fields.

The following field is also `static final`, but its value is determined when the class is initialized:

~~~java
public static final int STARTED_AT_SECOND =
        java.time.LocalTime.now().getSecond();
~~~

This is **not** a constant variable whose value is determined at compile time. However, it **still cannot be written by normal Reflection setters**, because every `static final` field belongs to the non-writable group. The *inlining* rules and the Reflection write-permission rules are two separate matters.

A `static final` field can be assigned in a static initializer:

~~~java
static final int VALUE;

static {
    VALUE = 42;
}
~~~

This assignment is valid **during class initialization** under Java source rules. It does not open up permission to use Reflection to reassign the field after initialization.

## 6. Comparison with Other Kinds of `final`

| Field type | `Field.set` after `setAccessible(true)` succeeds | Notes |
| --- | --- | --- |
| `static final` in a class/interface | **Cannot be written.** | Independent of whether the field type is primitive or reference. |
| `final` instance in an ordinary class | In Java 17–25 may be written by Reflection under conditions documented as allowed. | Should not be used outside specialized object initialization/reconstruction scenarios; compiled code/JIT may continue observing the old value. |
| `final` instance belonging to a `record` | **Cannot be written via normal access-suppression mechanisms.** | Records are protected by the *non-modifiable final field* rule. |
| `final` belonging to a hidden class | **Cannot be written via normal access-suppression mechanisms.** | Not treated like a final instance field of an ordinary class. |
| `static` but not `final` | Can be written if access permissions and value type are valid. | For example `count` in the program above. |

Reflection restrictions for `final` instance fields continue to tighten: **JDK 26**, under JEP 500, begins warning on writes to *final instance fields* via deep reflection, with dedicated control options (such as `--illegal-final-field-mutation`). This write behavior is intended to be blocked by default in a future release. The key point for this lesson: **the rule forbidding writes to `static final` predates this; the final-field mutation flags in newer JDKs do not turn `static final` into a writable field.**

Do not rely on having been able to modify a `final instance field` on an older JDK to infer that `static final` can be modified in a similar way.

## 7. Related APIs and Exceptions

### `Field.setAccessible(true)` and `trySetAccessible()`

- `setAccessible(true)` requests relaxing Java access checks. It can throw `InaccessibleObjectException` if the caller is not permitted to open the member under JPMS.
- `trySetAccessible()` returns `false` if access permission cannot be enabled, instead of throwing `InaccessibleObjectException` for that normal permission case.
- **Neither creates write permission** for `static final`. Hence the program in section 3 still receives `IllegalAccessException` at the setter after `trySetAccessible()` returns `true`.

### `Field.get(...)` and `Field.set(...)`

`Field.get(null)` and primitive getters such as `Field.getInt(null)` read a static field if access permissions allow. `Field.set(null, value)` and primitive setters must pass the **write-permission check**, so `static final` is rejected. Other issues such as wrong argument types or invalid unboxing/narrowing can cause `IllegalArgumentException`; they are not evidence that `final` is being modified.

### Can `VarHandle` change this conclusion?

No. For a `VarHandle` pointing to a `final field`, *write access modes* such as `set` are not supported and will throw `UnsupportedOperationException` when invoked. Obtaining a handle or reading a value does not automatically grant write modes for `static final`. `MethodHandles.Lookup` has its own access-permission rules; it should not be viewed as a backdoor for bypassing the immutability of `final`.

### `Modifier.FINAL` is not a runtime toggle

`Modifier.isFinal(field.getModifiers())` reports the modifier. Searching for or modifying internal `Field` data to "clear the final bit", or manipulating memory with unsupported APIs, **does not belong to the normal Reflection write API** and offers no compatibility guarantee across JDKs. Such techniques can also conflict with compiler optimizations, class initialization, and the memory model. Avoid designing systems that depend on them.

## 8. Proper Design When a Value Truly Needs to Change

If a value must change while the program is running, do not place it in a `static final` field and rely on Reflection to modify it.

**Option 1 — a mutable field:** Use a non-`final` field, restrict access, and update it via an API provided by the class. In multi-threaded programs, consider `volatile` or an appropriate synchronization mechanism rather than assuming any arbitrary setter guarantees visibility.

~~~java
final class RuntimeSettings {
    private static volatile int timeoutSeconds = 30;

    static int timeoutSeconds() {
        return timeoutSeconds;
    }

    static void updateTimeoutSeconds(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        timeoutSeconds = value;
    }
}
~~~

This is an **illustrative class snippet for design**, without a `main`, so it produces no output on its own. `volatile` provides visibility and ordering for that field; it does not replace all atomicity requirements of multi-step logic.

**Option 2 — a final reference to a state holder with an update API:** You can keep the reference fixed while replacing the data inside the referenced object via a thread-safe API, such as `AtomicReference<Configuration>`. Here `static final` protects **the identity of the container**, while `container.set(newConfig)` changes **the state of the container** according to its contract. Use this pattern only when shared mutable state is genuinely needed and concurrency implications are understood.

~~~java
import java.util.concurrent.atomic.AtomicReference;

final class ConfigStore {
    static final AtomicReference<String> CURRENT =
            new AtomicReference<>("development");

    static void switchTo(String value) {
        CURRENT.set(value);
    }

    static String read() {
        return CURRENT.get();
    }
}
~~~

This is also an illustrative class without a `main`. Even though `CURRENT` is `static final`, nowhere does the code rewrite **the `CURRENT` field reference**; it only calls the object's update method.

**Option 3 — dependency injection or configuration at initialization:** If configuration is meant to remain fixed for the lifetime of an object, pass it through a constructor and instantiate a new instance when configuration changes. This approach clarifies ownership and data lifecycle, avoiding Reflection modifying runtime structures.

## 9. Common Mistakes and Self-Check Questions

1. **"`setAccessible(true)` succeeding means it can be written."** False: when a field is `static final`, it can only open read access; the setter still has no write access.
2. **"The error is caused by passing `null` to `Field.setInt(null, x)`."** False: for static fields, the instance argument is ignored.
3. **"Only `static final int` is locked because it is a compile-time constant."** False: `static final List<?>` cannot be reassigned via Reflection either; fields with runtime-computed values are also locked.
4. **"`static final List` means elements cannot be added to the list."** False: `final` fixes the reference; the mutability of the List determines whether its contents can change.
5. **"You can access `private static final` in another module if you enable accessible."** Not necessarily: JPMS can deny even deep reflection when the package has not been opened with `opens`; and even if opened, writing is still disallowed.
6. **"`Field.set` reports `IllegalAccessException`, so using `--add-opens` will fix it."** `--add-opens` only handles module barriers when appropriate; it does not grant write permission to a non-modifiable final field.
7. **"The new final-field mutation options will unlock `static final`."** False: they relate to writing `final` instance fields under supported conditions and do not remove the restriction on static final.

**Self-check:**

- Replace `TAGS` in the example with `List.of("A")`. What exception do you think `Settings.tags().add("B")` will throw? *Hint:* object immutability differs from the `final` modifier on a field.
- If you remove `final` from `LIMIT` while keeping the same name and the `setInt(null, 20)` statement, how will the output differ?
- Why does `static final int LIMIT = 10` carry extra risk related to inlining, whereas `static final List<String> TAGS` is not a constant variable?
- If `trySetAccessible()` returns `false`, which package or module open permissions should be checked before attempting to read? Why is writing `static final` still impossible even after opening the package?

## References

- [Java SE 17 API — `Field.set(Object, Object)` and `Field.setInt(Object, int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 17 API — `AccessibleObject.setAccessible(boolean)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java SE 17 API — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java Language Specification §4.12.4 — final Variables / constant variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4)
- [JEP 500 — Prepare to Make Final Mean Final (JDK 26)](https://openjdk.org/jeps/500)
- [Java SE 26 Migration Guide — Preparing for Final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
