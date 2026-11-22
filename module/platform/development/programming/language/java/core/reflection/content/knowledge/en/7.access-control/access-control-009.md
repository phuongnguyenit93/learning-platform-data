# Do not treat `setAccessible` as a guarantee to modify every field in Java Reflection

## 1. Problem: opening access checks differs from having write permission

In Java Reflection, you can obtain a `Field` object representing a field, including a `private` field, via `getDeclaredField(...)`. Then, `setAccessible(true)` requests Reflection to **bypass certain Java language access checks** when reading/writing that field. This is **not** a guarantee that `Field.set(...)` will always succeed.

There are at least four distinct questions:

1. **Can the field be found?** `getField` only looks up matching public members, whereas `getDeclaredField` finds directly declared members regardless of visibility; neither means the access operation is valid.
2. **Can access checks be suppressed?** `setAccessible(true)` may succeed or be blocked by module/runtime boundaries. `trySetAccessible()` reports success as a boolean in the usual cases.
3. **Is the field allowed to be written?** `static final`, `final` fields in records, and `final` fields in hidden classes cannot be modified via `Field.set` even if opening access succeeded.
4. **Is the write call valid?** The target object, value type, primitive conversion rules, and class initialization state must all match. When any check fails, the API can throw an exception.

This distinction matters for mappers, dependency injection frameworks, serializers, migration tools, unit tests, and any code intending to "modify a private field via Reflection". Always treat opening access and writing as **two independent steps**.

## 2. What do `setAccessible`, `trySetAccessible`, and `canAccess` actually say?

| API | Meaningful result | What must **not** be inferred |
| --- | --- | --- |
| `field.setAccessible(true)` | Requests Reflection to bypass access checks within runtime-permitted scope; if not possible, can throw `InaccessibleObjectException`. | That the field is definitely writable or the entire module is open. |
| `field.trySetAccessible()` | Returns `true` when access-check suppression was enabled; usually returns `false` when it cannot be opened due to modules. Can throw `SecurityException` if denied by an active security mechanism. | That `Field.set` will definitely succeed. |
| `field.canAccess(target)` | Checks whether **the caller at call time** can reflectively access on a valid target under current state. | That the field can be modified; does not replace `final`, target, and value checks. |
| `field.get(target)` | Reads the value when access conditions and target are satisfied. | That being able to read a value means having write permission. |
| `field.set(target, value)` | Requests updating the value; succeeds only when all conditions for permission, writability, and type hold. | That merely calling `setAccessible(true)` beforehand is enough. |

`setAccessible(false)` re-enables access check enforcement for that Reflection object; calling `setAccessible(true)` does not edit the field's modifier in the class file, does not alter module definitions, and does not break every JVM constraint.

**Terminology note:** "accessible flag" on a `Field` object represents bypassing Reflection access checks. It is distinct from `public`/`private`/`protected` modifiers, and completely distinct from the `final` modifier. `canAccess` is a permission check in a specific context, not a writability prediction API.

## 3. Enabling reflection is bounded by the Java Platform Module System

Since Java 9, module boundaries matter for deep reflection. For a caller in class `C` wanting to enable access to a member of class `D`, the API lists cases where enabling is allowed, including:

- `C` and `D` belong to **the same module**.
- Both the member and `D` are `public`; `D`'s package is **exports** to the calling module.
- A `protected static` member in a public `D`; the package is exported and `C` is a subclass of `D`.
- `D`'s package is **opens** to the calling module; packages in unnamed modules or open modules are opened according to their respective semantics.

For private, package-private, or protected instance members in **another module**, `exports` alone does not grant deep reflection; the package must be appropriately `opens`. Otherwise, `setAccessible(true)` can throw `InaccessibleObjectException` and `trySetAccessible()` typically returns `false`. Exact rules depend on the caller, member kind, class location, and module opening configuration.

Illustrative example in `module-info.java` of the module owning the model (configuration snippet, not a standalone Java program):

~~~java
module app.domain {
    exports app.domain.model;          // Grants public API access.
    opens app.domain.model to app.mapper; // Grants app.mapper deep reflection.
}
~~~

`exports` and `opens` serve different purposes. A program on the classpath (unnamed module) that only wants to open a specific package for testing can run with a clearly scoped VM option, for example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp out ReflectiveWriteDemo
~~~

That option opens reflection into `java.lang` for unnamed modules and can make `trySetAccessible` on an internal private field of `java.lang.String` return `true`, yet it **does not** grant write permission to `final` fields that are forbidden from modification. Restrict `--add-opens` to legitimate needs and prefer configuring package opening in the module owning the code; avoid opening entire modules just to try your luck.

## 4. Which fields still cannot be modified even when opening succeeds?

The Java 17 Javadoc defines a group of **non-modifiable final fields** for which `setAccessible(true)` can only support reading, without granting write access:

| Field form | Open access (when allowed) | `Field.set(...)` |
| --- | --- | --- |
| Normal instance field, non-`final` | Can be enabled | Writable if target and value are valid. |
| Normal class `private final` instance field | Can be enabled if module allows | In Java 17, the API may allow writing if special conditions are met, but subsequent usability should not be relied upon. |
| `static final` field of any class/interface | Can be enabled for reading | **No write access** via `Field.set`. |
| `final` field declared by a record | Can be enabled for reading | **No write access** via `Field.set`. |
| `final` field in a hidden class | Can be enabled for reading | **No write access** via `Field.set`. |
| Private field in an unopened package of another module | May fail to enable | Cannot bypass module boundaries merely by calling `setAccessible`. |

Do not confuse `static` with `static final`: a **non-final** `static` field can still be changed if access rules and types permit; when calling `Field.set` on a static field, the target parameter is ignored and `null` can be passed.

**Risk with instance `final` fields in normal classes:** Per Java 17's `Field.set` contract, reflective modification is only meaningful in certain controlled reconstruction/deserialization workflows before the object is published. Other reads may continue observing the old value due to `final`-based assumptions/optimizations. Do not treat observing one successful write as proof that object invariants were safely updated. Behavior and limits on `final` can also change in newer JDK versions; check the actual version's documentation.

## 5. Runnable Java 17+ example: opening succeeds, writing fails

The following program separates opening access, writing, and error reporting. It tests a normal mutable field, `static final`, a record component, wrong value type, and JDK module boundaries.

Save to `ReflectiveWriteDemo.java`:

~~~java
import java.lang.reflect.Field;

public class ReflectiveWriteDemo {

    static class MutableModel {
        private String name = "old";
        private int count = 1;
        private static final String CATEGORY = "fixed";
    }

    record Snapshot(String code) {}

    static void attempt(String label, Field field,
                        Object target, Object newValue)
            throws ReflectiveOperationException {
        boolean opened = field.trySetAccessible();
        System.out.println(label + " | opened=" + opened);
        if (!opened) {
            System.out.println(label + " | write=SKIPPED");
            return;
        }

        try {
            field.set(target, newValue);
            System.out.println(label + " | write=OK");
        } catch (IllegalAccessException | IllegalArgumentException ex) {
            System.out.println(label + " | write="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        MutableModel model = new MutableModel();
        attempt("mutable private",
                MutableModel.class.getDeclaredField("name"),
                model, "updated");
        attempt("static final",
                MutableModel.class.getDeclaredField("CATEGORY"),
                null, "other");
        attempt("record final",
                Snapshot.class.getDeclaredField("code"),
                new Snapshot("original"), "other");
        attempt("wrong value type",
                MutableModel.class.getDeclaredField("count"),
                model, "not a number");

        Field jdkPrivate = String.class.getDeclaredField("value");
        System.out.println("JDK private | opened="
                + jdkPrivate.trySetAccessible());
    }
}
~~~

Compile and run on Java 17+ in a standard JDK configuration, without `--add-opens`:

~~~bash
javac -encoding UTF-8 ReflectiveWriteDemo.java
java ReflectiveWriteDemo
~~~

Output on JDK 17 or 21 when `java.base/java.lang` is not opened to the unnamed module:

~~~text
mutable private | opened=true
mutable private | write=OK
static final | opened=true
static final | write=IllegalAccessException
record final | opened=true
record final | write=IllegalAccessException
wrong value type | opened=true
wrong value type | write=IllegalArgumentException
JDK private | opened=false
~~~

Explanation of each case:

- `mutable private`: the model's private field in the same unnamed module allows enabling access-check suppression; the target type matches and the `String` value is valid, so writing succeeds.
- `static final`: opening returns `true`, yet `CATEGORY` is a non-modifiable field. `Field.set(null, ...)` throws `IllegalAccessException`.
- `record final`: `Snapshot.code` declared by a record is a non-modifiable final field; it also fails with `IllegalAccessException`.
- `wrong value type`: `count` is `int`. Passing a `String` cannot be unboxed/widened to `int`; `Field.set` throws `IllegalArgumentException` even though access was opened.
- `JDK private`: `String.value` is a private implementation field in module `java.base`. In the JDK configuration above, package `java.lang` is not opened to the program, so `trySetAccessible()` returns `false`. Running with an appropriate `--add-opens` can change this line; the example only illustrates the default state, do not write code depending on `String`'s internal structure.

Successfully obtaining `Field` here does not prove reading or writing will be allowed. Exact results for an internal JDK field depend on both JVM version and command-line flags, so applications should not rely on those details.

## 6. Why else can `Field.set` fail?

Even after opening access, `Field.set(target, value)` must still satisfy the Javadoc conditions:

1. **Wrong target object:** For instance fields, `target == null` causes `NullPointerException`. If target is not an instance of the field's declaring class (or a compatible subtype), it can throw `IllegalArgumentException`. For static fields, target is ignored.
2. **Wrong data type:** Java Reflection permits limited automatic conversions: valid unboxing and primitive widening, without arbitrary narrowing casts; for example, passing `Long` to an `int` field is not a widening conversion. Avoid assuming it behaves like a JSON mapper converter.
3. **Lack of access permission:** If checks are still enforced and the field is inaccessible, `Field.set` can throw `IllegalAccessException`. `trySetAccessible()==false` must be handled before calling.
4. **Field has no write access:** The non-modifiable final group listed above causes `Field.set` to throw `IllegalAccessException` even when the accessible flag can be `true`.
5. **Static class initialization:** Writing a static field can trigger class initialization; initialization errors can lead to `ExceptionInInitializerError`.
6. **Runtime/security policy:** `setAccessible(true)` can throw `InaccessibleObjectException`; if a `SecurityManager` mechanism is present and permission is denied, `SecurityException` can also be raised. Do not catch generic `Exception` and treat it as a missing-field error.

Distinguish **metadata lookup** errors (`NoSuchFieldException`), **access-enabling** errors (`InaccessibleObjectException` or `SecurityException`), **non-writable** errors (`IllegalAccessException`), and **argument** errors (`IllegalArgumentException` / `NullPointerException`). Each reports a different root cause.

## 7. Safe implementation workflow for tools using Reflection

When a tool must modify fields, turn hidden decisions into explicit conditions:

1. **Prefer normal APIs:** constructors, builders, setters, factories, business methods, or creating a new object. For records, create a new record rather than trying to mutate the old field.
2. **Select the exact field:** specify `declaringClass`, `name`, and `type`; use `getDeclaredField` when directly looking up a private field; when traversing superclasses, have a clear policy for shadowed field names. Do not pick arbitrarily by name alone.
3. **Check modifiers and structure:** `Modifier.isFinal(field.getModifiers())`, `Modifier.isStatic(...)`, `field.getDeclaringClass().isRecord()`, and model scope. If business logic does not support `final`, reject early; do not rely on attempting to write.
4. **Check module context:** if deep reflection is needed, require the package to be opened to the right module; do not assume the caller has permission. Use `trySetAccessible` and check the boolean, or catch errors from `setAccessible(true)`.
5. **Validate target/value:** instance fields need a matching target; static fields do not need a target; determine valid conversions instead of trying arbitrary casts.
6. **Write within controlled boundaries:** catch meaningful exceptions and return messages identifying `class.field` and the cause. Do not fall back to `Unsafe`, JNI, or modifier hacks to force writes into forbidden fields.
7. **Verify results per business contract:** mutable fields can be re-read when appropriate, but do not rely on a Reflection re-read to assert that modifying a `final` field took effect across all threads or all compiled code.

A utility method can express the policy forbidding writes to final fields upfront, avoiding treating `trySetAccessible` as a writability test:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

static void setMutableField(Field field, Object target, Object value)
        throws IllegalAccessException {
    if (Modifier.isFinal(field.getModifiers())) {
        throw new IllegalArgumentException("Refuse final field: "
                + field.getDeclaringClass().getName() + "."
                + field.getName());
    }
    if (!field.trySetAccessible()) {
        throw new IllegalAccessException("Cannot open field: "
                + field.getDeclaringClass().getName() + "."
                + field.getName());
    }
    field.set(target, value);
}
~~~

This is an **illustrative snippet** to place inside a suitable class, not a second standalone source file. Even when rejecting `final` and having enabled access, `Field.set` can still fail if target/value are wrong or runtime has other conditions. If a tool wants to avoid private reflection, supporting only public fields or requiring setter APIs in the model-owning module is easier to verify.

## 8. Common misconceptions and how to fix them

| Common misconception | Correct understanding |
| --- | --- |
| "Getting `getDeclaredField` means the field can be modified." | Metadata lookup does not determine read/write permission. |
| "`setAccessible(true)` can always open private members." | Module/package/security boundaries can prevent deep reflection. |
| "`trySetAccessible()==true` proves `Field.set` will succeed." | It only confirms access-check suppression state; writability and target/value still require validation. |
| "`final` is only a syntactic barrier." | There is a group of `final` fields with zero write access, plus immutability/memory rules that must be respected. |
| "Opening a module with `--add-opens` allows modifying `static final`." | Opening access does not change non-modifiable final rules. |
| "Re-reading the new value means the system updated safely." | Especially with `final`, other code paths may continue observing the old value; use an object-update model with clear contracts. |
| "An error in `Field.set` should be silently ignored." | You must distinguish module, writability, target, type, and initialization errors for accurate diagnostics. |

## 9. Verification exercises

- Remove `trySetAccessible` in the example and try `Field.set` on `MutableModel.name` from a top-level class without private access; compare `IllegalAccessException`.
- Keep `trySetAccessible` but replace `newValue` for `count` with `Integer.valueOf(5)`, and predict why unboxing from `Integer` to `int` is valid.
- Run the demo with and without `--add-opens java.base/java.lang=ALL-UNNAMED`; compare **only the ability to open access** to `String.value`, avoiding changing JDK internal structures.
- Write a constructor or `withCode(...)` method returning a new `Snapshot` record to update logic while preserving immutability.
- Create a separate multi-module application and experiment with the difference between `exports` and `opens` for `private` access. Keep opened module scopes as narrow as possible.

## 10. References and takeaways

- [Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): meaning of the accessible flag, JPMS rules, `trySetAccessible`, and non-modifiable final fields.
- [Java SE 17 — `Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `Field.set` conditions, target/type errors, writing `final`, and warnings about observed results.
- [dev.java — Reading and Writing Fields](https://dev.java/learn/api/reflection-method-handles/reflection/fields/): field read/write workflow and notes when operating on final fields.

**Core takeaway:** `setAccessible` addresses **access checks**, not **unlimited write permission**. Every reflective write path needs to verify module boundaries, modifiers, actual writability, target, value, and clear error handling. For immutable values, designing valid update APIs is always safer than trying to break immutability.