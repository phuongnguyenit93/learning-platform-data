# Reading static fields with Reflection: target argument is ignored

## 1. The problem: why can Field.get(null) still read the value?

In Java, **a static field belongs to the class** (more precisely, to the class that defines the field in each class-loading environment), rather than belonging individually to each object. Therefore, when using Reflection to read a static field, the `obj` argument of `Field.get(Object obj)` **is not used to select where the value is stored**. According to the Javadoc of `java.lang.reflect.Field`:

- If the field is **static**: `obj` **is ignored**; you can pass `null`, an instance of the declaring class, or even an unrelated object.
- If the field is an **instance** field: `obj` must be an instance of the class/interface declaring the field (or a compatible subtype); `null` causes `NullPointerException`, and an incompatible object causes `IllegalArgumentException`.

Basic example:

```java
class Settings {
    public static int port = 8080;
    public int id = 7;
}
```

Once you have `Field portField = Settings.class.getDeclaredField("port")`, calling `portField.get(null)`, `portField.get(new Settings())`, and `portField.get(new Object())` all read the same **current static value** `8080`, provided no other code has updated the field. Reading **does not require creating any `Settings` instance**.

Conversely, `id` is an instance field: `Settings.class.getDeclaredField("id").get(null)` is invalid, because there is no instance from which to find the value of `id`.

**Rule to remember:** The `Field` object determines *which field is read*, whereas `obj` specifies *which instance to read from* **if the field is not static**. For a static field, the value is tied to `Field.getDeclaringClass()`, not tied to the passed object.

## 2. Identifying a static field before reading

Reflection returns a `Field` representing a declaration, including its name, type, modifiers, and declaring class. Java 17+-compatible way to check static:

```java
Field f = Settings.class.getDeclaredField("port");
boolean isStatic = Modifier.isStatic(f.getModifiers());
Object value = f.get(isStatic ? null : someInstance);
```

The snippet above is just an **illustrative code fragment**; it must be placed in a method handling `NoSuchFieldException`/`IllegalAccessException` and providing the `someInstance` variable and necessary imports.

- `f.getModifiers()` returns the modifier bit mask; `Modifier.isStatic(...)` is the standard check.
- `f.getDeclaringClass()` returns the class/interface **declaring the field itself**, not necessarily `getClass()` of the target object you currently have.
- `f.getType()` returns the declared type of **the field's value** (e.g., `int.class` for `port`), and does not indicate whether the field is static or instance.
- `f.getName()` gives the field's name; `getDeclaredField("port")` searches for a direct declaration on `Settings`, whereas `getField("port")` searches for a `public` field according to public field lookup rules, including inherited members.

On JDK 20+, `f.accessFlags().contains(AccessFlag.STATIC)` also expresses this check using a flag set. However, `accessFlags()` **does not exist on JDK 17**; use `Modifier` if the code needs to run on JDK 17.

In code handling arbitrary fields, you should branch explicitly:

```java
Object read(Field field, Object instance) throws IllegalAccessException {
    if (Modifier.isStatic(field.getModifiers())) {
        return field.get(null);
    }
    return field.get(instance);
}
```

This is an illustrative method, not a complete program. Writing `get(null)` for static fields clarifies intent and avoids creating/evaluating unnecessary object expressions; in the instance branch, the caller must provide a suitable object and access permissions are still checked.

## 3. Standalone Java 17+ program, compilable and runnable

Save the entire code below to **`StaticFieldReadDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class StaticFieldReadDemo {
    public static class Settings {
        static { System.out.println("Settings initialized"); }
        public static int port = 8080;
        public int id = 7;
    }

    static Object makeTarget() {
        System.out.println("argument evaluated");
        return new Object();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Class.forName(Settings.class.getName(), false,
                StaticFieldReadDemo.class.getClassLoader());

        Field staticField = type.getDeclaredField("port");
        Field instanceField = type.getDeclaredField("id");

        System.out.println("static modifier = "
                + Modifier.isStatic(staticField.getModifiers()));
        System.out.println("before first get");
        System.out.println("get(null) = " + staticField.get(null));
        System.out.println("get(unrelated) = " + staticField.get(new Object()));
        System.out.println("get(expression) = " + staticField.get(makeTarget()));
        System.out.println("getInt(null) = " + staticField.getInt(null));
        System.out.println("instance get = " + instanceField.get(new Settings()));

        try {
            instanceField.get(null);
        } catch (NullPointerException ex) {
            System.out.println("instance with null = NullPointerException");
        }
        try {
            instanceField.get(new Object());
        } catch (IllegalArgumentException ex) {
            System.out.println("instance with unrelated = IllegalArgumentException");
        }

        staticField.setInt(null, 9090);
        System.out.println("after static set = " + staticField.getInt(new Object()));
    }
}
```

Compile/run in the directory containing the file using JDK 17 or newer:

```bash
javac StaticFieldReadDemo.java
java StaticFieldReadDemo
```

Stdout **verified when run on JDK 24**:

```text
static modifier = true
before first get
Settings initialized
get(null) = 8080
get(unrelated) = 8080
argument evaluated
get(expression) = 8080
getInt(null) = 8080
instance get = 7
instance with null = NullPointerException
instance with unrelated = IllegalArgumentException
after static set = 9090
```

### Step-by-step analysis

1. `Class.forName(name, false, loader)` loads/resolves the class **without actively initializing the class** when the `initialize` parameter is `false`. `Settings.class.getName()` and `getDeclaredField(...)` allow inspecting metadata without creating an instance; the example intentionally has not called `new Settings()` yet.
2. `Modifier.isStatic(staticField.getModifiers())` is `true`, which only checks metadata.
3. The first `staticField.get(null)` **initializes `Settings`** if not yet initialized; thus the line `Settings initialized` appears **after** `before first get` and **before** `get(null) = 8080`. Only after initialization can the field value be read.
4. `staticField.get(new Object())` does not throw `IllegalArgumentException` even though the target object does not belong to `Settings`, because static fields **ignore the target argument**.
5. With `staticField.get(makeTarget())`, **Java still evaluates the argument expression** `makeTarget()` before entering `Field.get`. That is why `argument evaluated` is still printed. Only the **returned reference value** of the expression is ignored by the method when locating the static field storage.
6. `getInt(null)` reads the `int` field directly as a primitive; `get(null)` returns an `Object` containing an `Integer` via boxing.
7. `instanceField.get(new Settings())` reads the instance field `id` properly. The next two calls illustrate errors with `null` and a wrong-typed object for an **instance field**.
8. `staticField.setInt(null, 9090)` illustrates the same rule for **writing** a non-`final` static field. The new value is read back via `getInt(new Object())`; the `new Object()` object is still ignored.

## 4. Comparison table across scenarios

Assuming the field has proper access permissions, the class initializes successfully, and no other thread modifies it:

| Operation | Static field | Instance field |
| --- | --- | --- |
| `field.get(null)` | Valid, reads value belonging to the declaring class | `NullPointerException` |
| `field.get(new DeclaringClass())` | Valid; instance is ignored | Valid, reads value of the passed instance |
| `field.get(new Unrelated())` | Valid; does not check whether target belongs to the declaring class | `IllegalArgumentException` |
| `field.getInt(null)` if field has type `int` | Valid, returns `int` | `NullPointerException` |
| `field.set(null, value)` | Target is ignored; write still depends on access permission, type, and `final` | `NullPointerException` |
| `field.getDeclaringClass()` | Class/interface owning the field | Class/interface owning the field |

**Limitation of the table:** `field.get(new Unrelated())` still performs **creating `new Unrelated()` before calling `get`**; if the constructor has side effects or throws an error, that still happens. "Ignored" only means Reflection does not use **the passed object** to select the static field's storage.

A strongly recommended choice is `field.get(null)` for static fields: clear intent, no object creation, and no unnecessary expression evaluation.

## 5. Which class does a static field's data belong to?

Consider **field hiding**, when a subclass and a superclass both declare a static field with the same name:

```java
class Parent {
    public static int count = 10;
}

class Child extends Parent {
    public static int count = 20;
}
```

With metadata taken from the **parent class declaration**:

```java
Field parentCount = Parent.class.getDeclaredField("count");
Object result = parentCount.get(new Child()); // 10
```

This is an illustrative snippet and requires corresponding Reflection imports/exceptions. Here `Field` points directly to **`Parent.count`**. Even though a `Child` instance is passed in, the static target is ignored; there is no "dynamic dispatch" selecting `Child.count`. To read `Child.count`, you must obtain `Field childCount = Child.class.getDeclaredField("count")`.

This differs greatly from **instance method overriding**: reading a field (even an instance field) does not apply dynamic dispatch rules based on the actual runtime class like calling an overridden method. `Field.getDeclaringClass()` is the true basis for knowing which class owns the field.

**The class loader is also part of a class's identity.** Two `Class<?>` objects with the same binary name but loaded by two different defining class loaders are two distinct runtime classes and have separate static state. If a Reflection tool uses the wrong `Class`/`ClassLoader`, seeing different static values does not mean `get` used the target; check `field.getDeclaringClass()` and the actual class loader.

## 6. Class initialization: reading static can trigger `<clinit>`

The Javadoc of `Field.get(Object)` specifies that **if the underlying field is static, the class that declared the field is initialized if it has not already been initialized**. Therefore, reading via Reflection is not purely a "metadata inspection" operation.

Operations commonly confused:

- `Class.forName(name, false, loader)`: requests not initializing the class at the step of finding/obtaining `Class`.
- `SomeClass.class`, `Field.getName()`, `Field.getModifiers()`, and `Class.getDeclaredField(...)`: used to reference/look up metadata; **not equivalent to reading the static value**.
- `field.get(null)` / `field.getInt(null)` on a static field: triggers initialization of the declaring class, if not yet initialized, before reading.
- If the static initializer fails, the call may throw `ExceptionInInitializerError` (or a related initialization error). Subsequent uses may encounter `NoClassDefFoundError` because the class is already in an erroneous initialization state.

In the main example, the `get(null)` line itself caused the `static { ... }` block to run. This is an important point when writing config scanners or plugins: "reading static just to inspect" can run unintended initialization code, open connections, or perform other tasks.

**Compile-time constant fields should not be equated with every static field.** With `static final int LIMIT = 123`, an ordinary Java expression referencing the constant can be inlined by the compiler, so initialization behavior differs from `Field.get(null)`. Under Reflection rules, reading an underlying static field still requires initializing the declaring class if not yet initialized. Do not rely on the inlining of direct calls to predict Reflection behavior.

## 7. Reading primitive static fields: get or getInt/getLong?

`Field.get(Object)` always returns `Object`. For a primitive `int` field, the value is boxed into `Integer`; for a reference field, it returns the object stored in the field (which may be `null`).

`Field` also has variants `getBoolean`, `getByte`, `getChar`, `getShort`, `getInt`, `getLong`, `getFloat`, `getDouble`. **The rule that static fields ignore the target also applies** to these typed reads.

Example with field `public static int port = 8080`:

```java
Object boxed = staticField.get(null); // Integer(8080)
int primitive = staticField.getInt(null); // 8080
long widened = staticField.getLong(null); // 8080L
```

This is an illustrative snippet within the scope of the main example, with `staticField` already retrieved from class `Settings`.

Typed getters use **primitive widening conversion** when valid. Since `int` can widen to `long`, `getLong(null)` works on an underlying `int`; however, `getInt(null)` cannot read an underlying `long` by narrowing to `int` and may throw `IllegalArgumentException`. Do not confuse a static field ignoring the *target* with it ignoring *data type checks*.

For a static field of reference type `String`, use `get(null)` and cast to the proper type after confirming `getType()` metadata or actual conditions. Do not call `getInt(null)` to read a `String` field.

## 8. Types of errors to keep separate

| Symptom | Actual cause to check |
| --- | --- |
| `NoSuchFieldException` from `getDeclaredField(...)` | No field with that name is **directly declared** on the queried `Class`; it may be an inherited field, misspelled name, or wrong class loader. |
| `IllegalAccessException` on `get(null)` | The field does not allow caller access under current Java/module rules. A `null` target does not bypass access checks. |
| `InaccessibleObjectException` from `setAccessible(true)` | Cannot allow deep reflection due to module rules and access conditions. |
| `NullPointerException` on `get(null)` | You may be reading an **instance field**; confirm `Modifier.isStatic(f.getModifiers())` first. |
| `IllegalArgumentException` on `get(wrongInstance)` | For instance fields, wrong target type; for typed getters, can also be an invalid primitive conversion. For **static `Field.get(Object)`**, an unrelated target alone is **not** a reason for this error. |
| `ExceptionInInitializerError` when reading static | Static initialization failed; check the cause in the static block/field initializer of the declaring class. |
| Different values across reads | Other code wrote to the field, threads mutated state, or you are looking at two runtime classes from different class loaders. |

For a `private static` field, passing `null` still works, yet **does not automatically bypass private access**. You can use `trySetAccessible()` when module/access conditions allow; success is not guaranteed. In JDK 17+, strong encapsulation of JDK modules and named modules can restrict reflection. Prefer public APIs or explicitly design package opening rules, instead of treating `setAccessible(true)` as always succeeding.

`Field.set(Object, Object)` and `setInt` also ignore the target argument if the field is static; however, write permission, `final` status, value type, class initialization, and module rules still apply. Many **`static final` fields are non-modifiable** via Reflection even after enabling `setAccessible(true)`; only demonstrate writing to a **non-final** static field as in the example.

## 9. Common misconceptions

**Misconception 1 — `null` always causes NullPointerException.** False for `Field.get(null)` on a **static field**. For an instance field, the error is expected due to the missing object holding the value.

**Misconception 2 — passing the wrong class causes the static field to be read from another class.** No. `Field` is already bound to its declaring class upon lookup; `obj` does not affect the static storage location.

**Misconception 3 — "ignored" means the argument expression does not run.** False. Java evaluates arguments before calling the method. `field.get(expensive())` can still execute `expensive()`, throw errors, or cause side effects. Only the final target value is not used by `get` if the field is static.

**Misconception 4 — Reflection automatically initializes the class as soon as you ask for a field name.** Not necessarily. Looking up `getDeclaredField` differs from reading the **static value**; `get` can trigger class initialization.

**Misconception 5 — passing a `new Object()` bypasses access permission checks.** False. Ignoring the target does not bypass `IllegalAccessException`, encapsulation, or module permissions.

**Misconception 6 — getInt() works for every numeric type.** False. Typed getters perform valid primitive conversions in the widening direction; they do not auto-narrow, do not parse `String`, and do not convert reference-type fields to primitives arbitrarily.

**Misconception 7 — static fields use dynamic dispatch like method overrides.** No. Field hiding differs from method overriding; `Field.getDeclaringClass()` tells you the exact field being read.

**Misconception 8 — reading a static field requires creating an instance.** No. `field.get(null)` is the intentional and usually clearest way to read it, once you have sufficient permissions.

## 10. Applying in reflection frameworks / utilities

When writing a reflection utility that handles both static and instance fields:

1. **Obtain the exact `Class`** to inspect; if plugins/class loaders are involved, identify the class's loader.
2. **Look up the exact `Field`** with `getDeclaredField` or `getField` according to the desired scope; handle `NoSuchFieldException`.
3. **Read `Modifier.isStatic(field.getModifiers())` metadata** and prepare the target: `null` for static, real instance for non-static.
4. **Check accessibility**; respect Java access control/module boundaries. If a field is non-public, evaluate whether deep reflection is genuinely needed or whether a legitimate accessor API exists.
5. **Read with the appropriate getter** for the field type: `get(null)` for references/when boxing is desired, `getInt(null)` for primitive `int`, etc. Consider the possibility of static initialization causing side effects.
6. **Interpret data** according to declaring class and field structure; do not infer from a target's runtime class that a static field has a "separate copy" on the object.

A concise helper usable for already-accessible fields:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public final class FieldReader {
    private FieldReader() {}

    public static Object read(Field field, Object instance)
            throws IllegalAccessException {
        Object target = Modifier.isStatic(field.getModifiers())
                ? null
                : instance;
        return field.get(target);
    }
}
```

This is a **complete utility class** without `main`; it is called from another application. It does not bypass private/module access on its own, does not validate that the target instance has the right type, and does not prevent side effects when class initialization occurs. For instance fields, `instance` must be compatible; for static fields, the caller can pass `null`. Java reflection still performs normal access checks.

## 11. Self-check

Suppose `Field score` points to `public static int score = 50` in `Game` with normal access permissions:

1. What does `score.get(null)` return? **An `Integer` containing `50`** via boxing.
2. Does `score.get(new Object())` cause `IllegalArgumentException` due to a wrong target? **No**; the target is ignored.
3. What does `score.getInt(null)` return? **Primitive `int` equal to `50`**.
4. If `static { System.out.println("init"); }` has not run yet, what can the first `score.get(null)` do? **Initialize `Game` and print `init` before returning the value**, if the class has not been initialized yet.
5. With `public int level = 2`, what does `levelField.get(null)` produce? **`NullPointerException`** due to missing instance.
6. If `score` is declared `private static` in a named module that disallows deep reflection, does passing `null` fix the access permission error? **No**.
7. In `score.get(makeTarget())`, is `makeTarget()` executed? **Yes**, because the argument expression is evaluated beforehand; the resulting target object is still ignored afterward.
8. Two different classes both have `static int score`: which field does Reflection read? **The field of the declaring class bound to the `Field` object**, not based on the class of the passed target.

## 12. Official documentation

- [Oracle Java SE 17 — Field.get(Object), set(Object,Object) and typed getters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Oracle Java SE 25 — Field.get(Object), Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html)
- [Oracle Java SE 17 — Modifier.isStatic(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html)
- [Java Language Specification 8.3.1.1 — static Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.1)
- [Java Language Specification 12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4)