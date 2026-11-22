# 3.9. Reading and Writing Fields with Reflection and Distinguishing static, instance, and final

In Java, a **field** is a variable declared in a class or interface. Normally, Java code accesses fields according to static types and compile-time access rules. Reflection (`java.lang.reflect.Field`) allows a program to **look up a field's metadata by name at runtime**, read its value, or write its value when conditions regarding type, target object, access permissions, and immutability are satisfied.

The key point is that **Reflection does not make every field writable**. A `static` field differs from an instance field of each object; a `final` field has its own restrictions; a `private` field is still subject to access checks by the Java Platform Module System (JPMS). This lesson focuses on how to read/write fields properly on Java 17+, and how to recognize when writing must be avoided.

## 1. Distinguishing a field, `Field`, and a field value

Example:

```java
class Counter {
    int value = 10;
}
```

`value` is a field declared in `Counter`. `Counter.class.getDeclaredField("value")` returns a **metadata object** of type `java.lang.reflect.Field`, describing that declaration: name, type, modifiers, and declaring class. The `Field` object is not a copy of the number `10`.

The same `Field` metadata can read the field from **multiple different instances**:

- `Field.get(counterA)` returns the value belonging to `counterA`.
- `Field.get(counterB)` returns the value belonging to `counterB`.
- `Field.set(counterA, newValue)` affects `counterA`, without automatically changing `counterB`.

For a `static` field, the value belongs to the declaring class (per the class definition loaded by the runtime), so two instances see one shared value. A `Field` object represents the field's declaration, whereas the **receiver argument** determines which instance is read/written if the field is not `static`.

Reflection works directly with the field; it **does not automatically invoke JavaBeans getters/setters**. Therefore, `Field.set` can bypass validation logic, computation, logging, or invariants located inside `setX(...)`. Only use direct access when there is a clear reason, such as serialization frameworks, mapping, or diagnostic tools.

## 2. Finding the right field declaration

Main APIs:

| API | Result | Common pitfalls |
| --- | --- | --- |
| `type.getDeclaredField("name")` | The exact-named field **directly declared** in `type`, with any access level | Does not automatically search fields inherited from a superclass |
| `type.getField("name")` | A `public` field found according to public member lookup rules, including inherited public fields | Does not find private/package-private fields just because Reflection is used |
| `type.getDeclaredFields()` | Array of directly declared fields, with any visibility | Return order is not guaranteed; may include synthetic fields |
| `type.getFields()` | Array of public fields exposed by the class/interface | Return order is not guaranteed and does not return private fields |
| `field.getDeclaringClass()` | The class or interface that **actually declares** the field | Very useful when inheritance or field hiding is involved |
| `field.getName()`, `field.getType()` | Name, declared type (`Class<?>`) | `getType()` returns the type after generic erasure where applicable |
| `field.getModifiers()` | Modifier bit mask | Use `java.lang.reflect.Modifier` to check `static`, `final`, `public`, etc. |

Thought experiment: `Parent` has `public int number`, while `Child extends Parent` does not declare `number`. `Child.class.getField("number")` finds the inherited public field and `getDeclaringClass()` returns `Parent.class`. Conversely, `Child.class.getDeclaredField("number")` throws `NoSuchFieldException`. When you need a private field of `Parent`, obtain it from `Parent.class.getDeclaredField(...)`, then check whether access is permitted.

If `Child` **declares** its own field with the same name `number`, that is **field hiding**, not overriding. The two declarations are two separate fields; each `Field` can be obtained from its respective declaring class. Fields do not use virtual dispatch like overridden instance methods.

## 3. Distinguishing instance, static, and final fields

| Field kind | Belongs to | Receiver for `Field.get`/`set` | Normal writability |
| --- | --- | --- | --- |
| Instance, non-`final` | Each object | An object of the declaring class or a subtype | Yes, if access checks and type compatibility pass |
| `static`, non-`final` | Declaring class | Pass `null` (clear convention; receiver is ignored) | Yes, if permitted and type-compatible |
| Instance `final` | Each object | Appropriate object when reading | **Readable; avoid modifying via Reflection**. Some cases may be writable under narrow JDK conditions, but stable semantics are not guaranteed |
| `static final` | Declaring class | Pass `null` when reading | **Modification via `Field.set` is not supported**, even if suppressing access checks succeeds |

Identify modifiers via the API, do not infer from the name:

```java
boolean isStatic = java.lang.reflect.Modifier.isStatic(field.getModifiers());
boolean isFinal = java.lang.reflect.Modifier.isFinal(field.getModifiers());
```

The `static`/`final` combinations are **two independent dimensions**: `static` states whether the value is tied to the class or an instance; `final` states whether the field can be reassigned under Java rules. `private`/`public` is another dimension, describing visibility.

For an instance field, passing a `null` receiver to `get`/`set` is invalid; a receiver not belonging to the declaring class or an appropriate subtype is also invalid. For a static field, using `null` clearly expresses that no specific object is being accessed. Reading/writing a static field via Reflection can trigger initialization of the declaring class if the class has not yet been initialized.

## 4. Complete Java 17+ example: reading/writing fields and checking modifiers

Save the following entire snippet as **`FieldAccessDemo.java`**. The file has one public class `FieldAccessDemo` and one package-private class `Device` to clearly demonstrate accessing a `private` field via Reflection.

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

class Device {
    static int total = 2;
    int level = 7;
    private String label = "alpha";
    final long id = 101L;
    static final String UNIT = "dB";
}

public class FieldAccessDemo {
    private static void describe(Field field) {
        int modifiers = field.getModifiers();
        String scope = Modifier.isStatic(modifiers) ? "static" : "instance";
        String mutability = Modifier.isFinal(modifiers) ? "final" : "mutable";
        System.out.println(field.getName() + ": " + scope + ", " + mutability);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Device first = new Device();
        Device second = new Device();

        // Instance field: each Device holds its own value.
        Field level = Device.class.getDeclaredField("level");
        System.out.println("instance before: "
                + level.getInt(first) + ", " + level.getInt(second));
        level.setInt(first, 12);
        System.out.println("instance after: "
                + first.level + ", " + second.level);

        // Static field: pass null, no specific receiver is used.
        Field total = Device.class.getDeclaredField("total");
        System.out.println("static before: " + total.getInt(null));
        total.setInt(null, 5);
        System.out.println("static after: " + Device.total);

        // Private field: requires permission to suppress visibility checks.
        Field label = Device.class.getDeclaredField("label");
        if (!label.trySetAccessible()) {
            throw new IllegalStateException("Cannot access label");
        }
        System.out.println("private before: " + label.get(first));
        label.set(first, "beta");
        System.out.println("private after: " + label.get(first));

        // Final fields: read-only, do not attempt to write.
        Field id = Device.class.getDeclaredField("id");
        Field unit = Device.class.getDeclaredField("UNIT");

        describe(level);
        describe(total);
        describe(id);
        describe(unit);
        System.out.println("final values: "
                + id.getLong(first) + ", " + unit.get(null));
    }
}
```

Run in an empty directory with JDK 17 or later:

```bash
javac -encoding UTF-8 FieldAccessDemo.java
java FieldAccessDemo
```

Expected output on a standard classpath (unnamed module):

```text
instance before: 7, 7
instance after: 12, 7
static before: 2
static after: 5
private before: alpha
private after: beta
level: instance, mutable
total: static, mutable
id: instance, final
UNIT: static, final
final values: 101, dB
```

Explanation:

1. `level` belongs to each instance: `setInt(first, 12)` only changes `first.level`; `second.level` remains `7`. This is a normal instance field, **unrelated to overriding**.
2. `total` belongs to class `Device`: `getInt(null)` reads the shared value and `setInt(null, 5)` updates the shared value. There is no need to create an object just to access a static field.
3. `label` is private. `getDeclaredField` **finding the metadata** does not mean reading/writing is already permitted. In this example on the classpath, both classes belong to the unnamed module, so `trySetAccessible()` can grant deep access; in another named module, the result may be denied.
4. `id` is an instance `final` field, read with `first`; `UNIT` is `static final`, read with `null`. There is no write call to any final field.
5. `describe` uses modifiers from metadata, not guesses from how the `Field` variable is declared.

The demo code directly uses package-private fields (`level`, `total`) because both classes are in the same package. If the declaring class is in a different package/module, do not assume reflective access is still permitted.

## 5. `get`/`set` and primitive variants

`Field.get(Object receiver)` returns `Object`:

- For reference-type fields (`String`, `List`, ...), the value is typically the corresponding reference or `null`.
- For primitives (`int`, `boolean`, `double`, ...), the value is boxed into a wrapper when returned as `Object`.
- For `static` fields, pass `null` as the receiver.
- For instance fields, pass an object whose class is compatible with the field's declaring class.

`Field.set(Object receiver, Object value)` writes to the field when it is writable, access is valid, and there is a type conversion allowed by the API. For primitives, an appropriate wrapper can be passed and Reflection performs unboxing/valid widening conversion. There is no arbitrary narrowing cast; you cannot assign a `String` to an `int` field with `set` and expect Java to parse the string automatically.

Specialized APIs avoid boxing when reading/writing primitives:

| Field type | Read | Write when non-`final` and permitted |
| --- | --- | --- |
| `int` | `getInt(receiver)` | `setInt(receiver, intValue)` |
| `long` | `getLong(receiver)` | `setLong(receiver, longValue)` |
| `boolean` | `getBoolean(receiver)` | `setBoolean(receiver, booleanValue)` |
| `double` | `getDouble(receiver)` | `setDouble(receiver, doubleValue)` |
| Reference type | `get(receiver)` | `set(receiver, value)` |

Choose the accessor matching the field type. Primitive getters/setters have certain **widening conversion** rules supported by the API; they do **not** automatically support narrowing conversion. Before mapping a configuration string to a number, parse and validate the value separately; Reflection does not replace data conversion.

If metadata comes from an untrusted source, check it beforehand:

```java
Class<?> declaredType = field.getType();
Class<?> owner = field.getDeclaringClass();
boolean staticField = Modifier.isStatic(field.getModifiers());
boolean finalField = Modifier.isFinal(field.getModifiers());
```

This is a **standalone snippet**, using an existing `field` variable, not an independent program. For reference fields, `declaredType.isInstance(value)` can be used when `value != null` to screen the assigned type; `null` is only valid for reference fields. For primitives, normalize the type/value yourself rather than treating `isInstance` as a complete rule.

## 6. Access permissions: finding a field ≠ being able to read/write it

Several concepts need to be separated clearly:

- **Discovery:** `getDeclaredField("label")` retrieves metadata, including private fields; if the name does not exist in the exact declaring class, it throws `NoSuchFieldException`.
- **Access check:** `field.get(...)` and `field.set(...)` still check whether the caller has access permission if language access checks have not been suppressed. Invalid access may throw `IllegalAccessException`.
- **Suppress access checks:** `field.trySetAccessible()` attempts to enable deep access and returns `true`/`false`; `field.setAccessible(true)` may throw `InaccessibleObjectException` if the module does not allow it. This is not a mechanism that breaks all boundaries.
- **Module boundary:** with **named modules** on Java 17+, `exports` usually relates to using public APIs from another module; for Reflection to deeply access non-public members in another module, the package needs to be **opens** according to the appropriate module relationship (or a mechanism allowed by the runtime). `exports` is not synonymous with `opens`.

`field.canAccess(receiver)` helps check current accessibility from the caller, but also requires an appropriate argument: `null` for static and an object of the right type for instance. It does not replace visibility/module checks. Deep access is also subject to the environment's security policy; `trySetAccessible()` may fail.

When building a framework, prefer `public` APIs or intentionally configured `opens`. Do not take a successful `setAccessible(true)` call in a classpath program as proof that a modular application or JDK internals will behave the same way.

### Common error example in a named module

If a library declares a package containing a private field that **only `exports`**, without `opens`, then Reflection code in another module can retrieve some metadata but cannot suppress access checks to read/write the private field. In that case:

- `trySetAccessible()` typically returns `false` if there is no permission to open the package.
- `setAccessible(true)` may throw `InaccessibleObjectException`.
- Instead of automatically adding global access flags, review the module descriptor (`opens package.name to module.name;`) or switch to an appropriate public accessor.

Module error messages usually specify which package is not open and which caller module needs permission. Only configure opening the exact package for the component that genuinely needs permission; do not treat every private field as a public contract for dependent applications.

## 7. Why must `final` be handled separately?

`final` prevents reassigning a field under the normal Java model once it has been properly initialized. Reflection has historical details that allow writing **some** instance final fields under restricted conditions, but that is not a choice for updating application state:

- **`static final`** is treated as a non-modifiable final field by `Field.set`; `setAccessible(true)` cannot be used to turn it into a writable field.
- **Instance final** can only be reflectively written in very narrow cases, where access checks can be suppressed and the runtime permits it. Final fields of a **record** or **hidden class** also belong to the group that cannot be modified by this mechanism.
- If a final field has already been published to another thread, mutating it after initialization can break assumptions about initialization safety and visibility. The JVM/JIT may optimize based on finality; do not assume every subsequent read will see the exact value just written.
- **Compile-time constant** is a special case: a `static final` primitive or `String` assigned a constant expression may be inlined into the bytecode of consuming code. Even attempting to force a value change via tricks outside `Field.set` can produce inconsistent results.

Therefore, the practical rule is **read final fields if permitted, do not write final fields via Reflection**. When a value needs to change, design a mutable object with a clear API or create a new object. For immutable data, prefer constructors, builders, or record constructors, rather than patching state via Reflection after the object is in use.

## 8. Common runtime errors when manipulating fields

| Symptom / exception | Common cause | How to handle |
| --- | --- | --- |
| `NoSuchFieldException` | Wrong name or calling `getDeclaredField` on a subclass while the field is declared in a superclass | Check `getDeclaringClass`, declaration location, and exact name |
| `IllegalAccessException` | Insufficient permission to read/write the field; or attempting to write a protected field | Check visibility, module openness, `final` modifier; prefer public APIs |
| `InaccessibleObjectException` | Attempting to suppress access checks when the package/module does not allow it | Open the package intentionally if the design requires it, or drop deep reflection |
| `IllegalArgumentException` | Receiver is the wrong class, or value/accessor type is incompatible with the field | Check `getType`, `isStatic`, and convert data beforehand |
| `NullPointerException` | Using a `null` receiver for an instance field operation, or a dereference error in caller code | Pass a valid object for instance fields; `null` is only for static |
| `SecurityException` | Security policy or permission checks block a reflective operation | Redesign the permission scope, do not ignore the exception |
| Read value does not match expectation | Reading a hidden field (field hiding), a shared static field, or relying on a forcibly modified final field | Print `getDeclaringClass`, `getModifiers`; check actual class and initialization |

**Unlike `Method.invoke`:** reading/writing a field with `Field.get`/`set` has no mechanism to wrap exceptions from a target method body in `InvocationTargetException`, because no method body is invoked. However, accessing a static field can involve class initialization and produce its own initialization errors. Do not use the same exception handler for all Reflection APIs without distinguishing the error source.

## 9. Field hiding and inheritance: do not confuse with dynamic dispatch

Suppose `Parent` declares `public int score = 1`, and `Child extends Parent` also declares `public int score = 2`. These two fields have the **same name but different declarations**. Given a `Child` object:

- `Parent.class.getDeclaredField("score").getInt(child)` reads `Parent`'s field, returning `1`.
- `Child.class.getDeclaredField("score").getInt(child)` reads `Child`'s field, returning `2`.
- `Field` does not automatically select a field based on the receiver's runtime class like method overriding.

This example assumes both classes and public fields are declared exactly as described. This also explains why field hiding should be avoided: two values with the same name easily cause confusion when serializing, mapping data, or debugging. If a framework scans the entire hierarchy using `getDeclaredFields`, it must identify name collisions by **declaring class + field name**, not simply by name alone.

## 10. Using Reflection fields safely in real applications

A reliable workflow:

1. **Define the data contract:** which class the field must belong to, what name, what type, and whether mutation is allowed. Do not let external data arbitrarily pick private fields by name.
2. **Find the exact declaration:** prefer `getDeclaredField` when the exact owner is known; if accessing an inherited public field, use `getField`.
3. **Inspect metadata:** `Modifier.isStatic` to choose `null` or an object receiver; `Modifier.isFinal` to block writes; `getType()` to validate the value.
4. **Check access permissions:** prefer public APIs. If deep reflection is genuinely needed, use `trySetAccessible()` and have a fallback branch when denied; understand module boundaries.
5. **Read/write with the right type:** use `get`/`set` for references or the appropriate primitive accessor; validate values before writing.
6. **Preserve invariants and thread-safety:** if a field is managed by setters, locks, `volatile`, atomics, or framework lifecycle, do not bypass those mechanisms arbitrarily. Reflection does not create synchronization on its own.
7. **Handle errors with context:** report the field name, declaring class, and read/write operation; do not leak sensitive data from field values into logs.

For systems that need frequent field access or memory/concurrency access modes, `VarHandle` in `java.lang.invoke` is worth studying. However, it still has explicit access and type requirements; it does not turn a final field into a mutable field. For most business logic, constructors/getters/setters/interfaces remain easier to verify and maintain than Reflection.

## 11. Quick self-check

1. Can one `Field` obtained from `Device.class.getDeclaredField("level")` read from both `first` and `second`? **Yes**, because the metadata is shared for the declaration; each instance holds its own value.
2. Is `getInt(null)` valid for `level`? **No**, it is an instance field. `null` is appropriate for `total`, which is a static field.
3. Does `getDeclaredField("x")` automatically find a private field `x` in a superclass? **No**, it must be looked up on the declaring class.
4. Does `getDeclaredField("label")` succeeding mean `Field.get` will definitely work? **No**, metadata discovery and access checks are two separate things.
5. Does `trySetAccessible()` always return `true` if the exact private field name is known? **No**, JPMS and access policies can block it.
6. Can `static final String UNIT` be reliably modified via `Field.set(null, "...")`? **No**; `static final` is not writable through this API, and constant inlining makes forced modification even more dangerous.
7. Does `Parent`'s `score` field automatically dispatch to `Child`'s `score` field when the receiver is `Child`? **No**; `Field` points to a specific declaration, and field hiding is not method overriding.
8. Does Reflection `Field.set` automatically invoke a setter containing validation? **No**, it writes directly to the field when permitted.

**Remember:** identify **declaring class → find `Field` → check `static`/`final`/type → determine receiver → check access/module → valid `get` or `set`**. For static fields, the receiver is `null`; for instance fields, a matching object is required; for final fields, prefer read-only. This is the most important boundary so that Reflection serves the program without breaking object correctness.