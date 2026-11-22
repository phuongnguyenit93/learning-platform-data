# Field.set with reference or primitive types in Java Reflection

## 1. Problem statement and the contract of Field.set

`java.lang.reflect.Field` describes a **specific** field declared in a class/interface. `Field.set(Object obj, Object value)` assigns a new value to that field if access permission, write permission, target object, and data type are all compatible. The same API applies to **reference-type** fields (e.g., `String`, `Number`, `Integer`, `List<?>`, arrays) and **primitive** fields (`boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`), though the validation rules for `value` are not the same.

When writing a mapping, serialization, or binding tool, four independent questions must be answered:

1. What type is the field? `field.getType()` returns the declared type; `field.getType().isPrimitive()` separates the primitive branch from reference types.
2. Does `obj` point to a valid object? Instance fields require an object of the declaring class (or subtype); for static fields `obj` is ignored and can be `null`.
3. Is the field writable? `getDeclaredField` finds a private field but does not guarantee accessibility. `trySetAccessible()` may fail due to module boundaries; `final` fields also have write-access restrictions.
4. Is the passed value compatible with **the field's type**? For reference types, this is object assignability. For primitives, this is **unboxing** the wrapper followed by identity/widening primitive conversion.

`Field.set` does not parse numbers from strings, does not arbitrarily cast types, does not instantiate objects, does not guarantee generic safety, and does not bypass Java Platform Module System restrictions.

Related API signatures:

~~~java
// Illustrative API signatures; not a standalone compilable program.
public void set(Object obj, Object value)
        throws IllegalArgumentException, IllegalAccessException;
public void setInt(Object obj, int i)
        throws IllegalArgumentException, IllegalAccessException;
~~~

When writing `field.set(obj, 42)`, the compiler boxes the literal `42` into an `Integer` to pass through the `Object` parameter. If the actual field is `int`, Reflection unboxes `Integer` back to `int` before writing. Do not confuse call-site boxing with unboxing inside `Field.set`'s implementation.

## 2. Rules for reference-type fields

A reference field of type `T` accepts `null` or an object assignable to `T` at runtime. Incompatible values cause `Field.set` to throw `IllegalArgumentException`, even if they could be converted by custom application logic.

| Declared field | Value passed to `set` | Result |
| --- | --- | --- |
| `String name` | `"Lan"` | Succeeds because the type matches. |
| `CharSequence text` | `new StringBuilder("hi")` | Succeeds because it implements `CharSequence`. |
| `Number amount` | `Integer.valueOf(10)` | Succeeds because `Integer` is a subtype of `Number`. |
| `Object payload` | `new int[] {1, 2}` | Succeeds; an array is also an object. |
| `Integer boxed` | `Integer.valueOf(10)` | Succeeds; `Integer` is **not** primitive. |
| `Integer boxed` | `Long.valueOf(10)` | Fails; wrapper `Long` is not automatically coerced to `Integer`. |
| `String name` | `null` | Succeeds if the field is writable. |
| `String name` | `Integer.valueOf(10)` | Fails; the API does not call `toString()`. |

Typical check before writing a reference:

~~~java
// Snippet inserted into a method that already has Field field, Object obj, Object value.
Class<?> type = field.getType();
if (!type.isPrimitive()) {
    if (value != null && !type.isInstance(value)) {
        throw new IllegalArgumentException("Reference type mismatch");
    }
    field.set(obj, value);
}
~~~

`Class.isAssignableFrom` can also check type relationships when `value != null`, e.g., `type.isAssignableFrom(value.getClass())`. Do not call `value.getClass()` on `null`; also do not use `isInstance` to infer conversion from a wrapper to a primitive.

**Arrays are categorized as reference types.** A field `int[] values` has a runtime type that is an array class, meaning `valuesField.getType().isPrimitive() == false`. You can assign another `int[]` or `null`; you cannot assign an `Integer[]` in place of `int[]` via per-element auto-boxing. Modifying an element of an existing array is a different operation (`Array.setInt` or standard array code), not `Field.set` on the field.

**Generics are erased:** A field `List<String> names` still has `getType() == List.class`. `Field.set` does not check the `String` type parameter of elements, so assigning a `List<Integer>` can pass the runtime type check even though code later reading elements as `String` will encounter `ClassCastException`. `getGenericType()` reflects the parameterized declaration so frameworks can build additional checks themselves.

## 3. Rules for primitive fields: unboxing and widening

`Field.set` accepts `Object value`, so to write a primitive field the value object is normally one of the eight wrappers: `Boolean`, `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`. Reflection attempts unboxing, then applies identity or a valid **widening primitive conversion** in Java. The API does not perform narrowing even if the actual number fits within the target range.

| Primitive type after unboxing | Allowed target fields |
| --- | --- |
| `boolean` (from `Boolean`) | `boolean` |
| `byte` (from `Byte`) | `byte`, `short`, `int`, `long`, `float`, `double` |
| `short` (from `Short`) | `short`, `int`, `long`, `float`, `double` |
| `char` (from `Character`) | `char`, `int`, `long`, `float`, `double` |
| `int` (from `Integer`) | `int`, `long`, `float`, `double` |
| `long` (from `Long`) | `long`, `float`, `double` |
| `float` (from `Float`) | `float`, `double` |
| `double` (from `Double`) | `double` |

Examples explained in order:

- `int count` accepts `Integer.valueOf(7)`, `Byte.valueOf((byte) 7)`, `Character.valueOf('A')`: identity or widening to `int`.
- `long elapsed` accepts `Integer.valueOf(7)`: `Integer → int → long`.
- `double ratio` accepts `Float.valueOf(1.5f)`: `Float → float → double`.
- `int count` does **not** accept `Long.valueOf(7L)`: `long → int` is forbidden narrowing.
- `short small` does **not** accept `Integer.valueOf(1)`: the small number `1` still does not grant `int → short` narrowing.
- `boolean active` only accepts an appropriate `Boolean`; values like `"true"` and `Integer.valueOf(1)` are not automatically parsed/coerced.
- All primitive fields do **not** accept `null`: cannot be unboxed, so `Field.set` throws `IllegalArgumentException`. Reference fields accept `null` if write permission is valid.

Widening is a **type** rule, not a guarantee of zero precision loss. For instance, `long → float` is allowed, yet large integers can lose accuracy; business tools can apply stricter rules when exact value preservation is required.

A tool receiving user input from `String`/JSON needs an **explicit converter** before calling `set`. For example, parse `"42"` into `Integer.valueOf(42)`, check for overflow, and only then write to `int`; do not pass `"42"` directly to `Field.set` expecting the API to handle it.

## 4. The setXxx methods for primitives

In addition to `set(Object, Object)`, `Field` provides `setBoolean`, `setByte`, `setShort`, `setChar`, `setInt`, `setLong`, `setFloat`, and `setDouble`. The type of the second parameter in these methods is the corresponding primitive.

~~~java
// Illustrative API snippet, not standalone source.
field.setBoolean(target, true);
field.setByte(target, (byte) 3);
field.setShort(target, (short) 3);
field.setChar(target, 'A');
field.setInt(target, 3);
field.setLong(target, 3L);
field.setFloat(target, 1.5f);
field.setDouble(target, 1.5);
~~~

You must distinguish **the source value type** from **the target field type**. For example, `setInt(target, 9)` on a `long` field succeeds due to `int → long`, whereas `setLong(target, 9L)` on an `int` field fails due to narrowing. Similarly, `setDouble` does not automatically narrow down to a `float` field.

**Do not use `setInt` to write an `Integer` field:** an `Integer` field is a reference, not a primitive `int`. On Java 17/21, calling `setInt` on an `Integer` field throws `IllegalArgumentException`; use `set(target, Integer.valueOf(9))`. On a `Number` field, likewise use `set` with an `Integer` object instead of a primitive setter. Choose the API based on `field.getType()`:

~~~java
// Illustrative snippet: field and target are already resolved, permissions checked separately.
Class<?> type = field.getType();
if (type == int.class) {
    field.setInt(target, 9);
} else if (type == Integer.class) {
    field.set(target, Integer.valueOf(9));
} else {
    // Check / convert according to the actual declared type.
}
~~~

`int.class` and `Integer.class` are two different `Class` objects; Reflection does not treat them as the same field declaration.

## 5. Complete Java 17+ example: valid and invalid writes

Create file `FieldSetTypesDemo.java`:

~~~java
import java.lang.reflect.Field;

public class FieldSetTypesDemo {
    static class Sample {
        private Number amount;
        private String label = "initial";
        private int pieces;
        private long ticks;
        private double price;
        private boolean available;
        private Integer boxed;
        private static int visits = 1;
    }

    @FunctionalInterface
    interface WriteAction {
        void run() throws IllegalAccessException;
    }

    static Field field(String name) throws NoSuchFieldException {
        Field result = Sample.class.getDeclaredField(name);
        if (!result.trySetAccessible()) {
            throw new IllegalStateException("Cannot access: " + name);
        }
        return result;
    }

    static void expectFailure(String label, WriteAction action) {
        try {
            action.run();
            System.out.println(label + " -> unexpected success");
        } catch (IllegalAccessException
                 | IllegalArgumentException
                 | NullPointerException error) {
            System.out.println(label + " -> "
                    + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Sample sample = new Sample();
        Field amount = field("amount");
        Field label = field("label");
        Field pieces = field("pieces");
        Field ticks = field("ticks");
        Field price = field("price");
        Field available = field("available");
        Field boxed = field("boxed");
        Field visits = field("visits");

        // Reference: compatible object, or null.
        amount.set(sample, Integer.valueOf(25));
        label.set(sample, null);
        boxed.set(sample, Integer.valueOf(12));

        // Primitive: unbox then widen if needed.
        pieces.set(sample, Byte.valueOf((byte) 7));  // byte -> int
        ticks.setInt(sample, 9);                     // int -> long
        price.set(sample, Float.valueOf(1.5f));     // float -> double
        available.setBoolean(sample, true);

        // Static field: target is null.
        visits.setInt(null, 4);

        System.out.println("amount=" + sample.amount
                + " (" + sample.amount.getClass().getSimpleName() + ")");
        System.out.println("label=" + sample.label
                + ", pieces=" + sample.pieces
                + ", ticks=" + sample.ticks
                + ", price=" + sample.price
                + ", available=" + sample.available
                + ", boxed=" + sample.boxed
                + ", visits=" + Sample.visits);

        expectFailure("reference wrong type",
                () -> amount.set(sample, "not a Number"));
        expectFailure("primitive narrowing",
                () -> pieces.set(sample, Long.valueOf(10L)));
        expectFailure("primitive null",
                () -> pieces.set(sample, null));
        expectFailure("instance null target",
                () -> label.set(null, "new"));
        expectFailure("primitive setter on wrapper",
                () -> boxed.setInt(sample, 8));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FieldSetTypesDemo.java
java FieldSetTypesDemo
~~~

Output:

~~~text
amount=25 (Integer)
label=null, pieces=7, ticks=9, price=1.5, available=true, boxed=12, visits=4
reference wrong type -> IllegalArgumentException
primitive narrowing -> IllegalArgumentException
primitive null -> IllegalArgumentException
instance null target -> NullPointerException
primitive setter on wrapper -> IllegalArgumentException
~~~

Output explanation:

- `amount` is declared `Number` yet holds an `Integer` object; this is a compatible reference assignment.
- `pieces` is declared `int`, receives `Byte`, unboxes to `byte`, and widens to `int`.
- `ticks` is declared `long` and receives a primitive `int` source value via `setInt`.
- `price` is declared `double` and receives `Float` via unboxing and widening.
- `boxed` is a `Integer` reference so `set` accepts `Integer` successfully; `setInt`, however, does not apply to reference fields.
- `set(sample, null)` requests writing a **null value**, whereas `set(null, "new")` supplies a **null target**. The second case causes `NullPointerException` for an instance field. For a static field, a null target is valid.

`trySetAccessible()` in the example can be enabled because the code and model classes reside in the same unnamed module; the program needs no external libraries and accesses no internal JDK fields. In modularized applications, you must check `exports`/`opens` and the actual caller.

## 6. Parent class fields, hidden fields, and target types

`Field` binds to **the original field declaration**, and does not re-select by name on the runtime type of `obj`. If two hierarchy levels share the name `id`, `Parent.class.getDeclaredField("id")` and `Child.class.getDeclaredField("id")` are two distinct `Field` objects that can carry **two different types**. Type conversion rules apply according to the `field.getType()` of each `Field` object.

Standalone example, save as `HiddenFieldDemo.java`:

~~~java
public class HiddenFieldDemo {
    static class Parent {
        int id = 1;
    }
    static class Child extends Parent {
        long id = 2;
    }

    public static void main(String[] args) throws Exception {
        Child child = new Child();
        Parent.class.getDeclaredField("id").setInt(child, 5);
        Child.class.getDeclaredField("id").setLong(child, 8L);

        System.out.println("Parent.id=" + ((Parent) child).id);
        System.out.println("Child.id=" + child.id);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 HiddenFieldDemo.java
java HiddenFieldDemo
~~~

Output:

~~~text
Parent.id=5
Child.id=8
~~~

A tool that automatically traverses superclasses needs to specify its policy when field names collide: pick the field closest to the subclass, pick the parent's field, or report a conflict. Do not use the `id` name alone to determine the value type without checking `getDeclaringClass()`.

## 7. Access permissions, final, and runtime errors

Choosing a value of the right type is **not enough** for `Field.set` to succeed.

| Error or condition | Practical meaning |
| --- | --- |
| `NoSuchFieldException` during lookup | Wrong name or querying a class that does not declare that field; `getDeclaredField` does not automatically search parents. |
| `trySetAccessible() == false` | Cannot bypass access check, usually because the module/package is not open. |
| `InaccessibleObjectException` on `setAccessible(true)` | Deep reflection blocked by the Java Platform Module System. |
| `IllegalAccessException` on `set` | Field does not allow writing or access check failed. |
| `IllegalArgumentException` on `set` | Wrong value type, cannot unbox/widen, or target has the wrong type. |
| `NullPointerException` on `set` | Target is null for an instance field. |
| `ExceptionInInitializerError` | Initialization of the static field's class failed. |

**`static final`** fields, `final` fields in records, and `final` fields in hidden classes cannot be written via `Field.set`, even when `setAccessible(true)` succeeded for reading. `private final` instance fields in ordinary classes have special rules in Java 17: Reflection sometimes permits writing if access is properly opened, but mutating after object publication can cause unpredictable behavior; do not use this technique to update business state.

When the target is non-`null`, it must be an instance of the declaring class (or a compatible subtype). When a static field is written, the target object is ignored; the operation may trigger initialization of the declaring class. Therefore, do not treat every error at `Field.set` as a "type cast failure".

`setAccessible` permission is not permission to update every field. Under JPMS, opening private members in another module usually requires the package to be `opens` to the caller's module; `exports` for public APIs does not automatically grant deep reflection.

## 8. Designing an intentional data converter

For a mapper/binder, the processing flow should be driven by the **target type**, not solely the source type:

~~~text
Field + target + rawValue
   |
   +-- Determine declaringClass, static/instance, final, and access permissions
   |
   +-- Class<?> type = field.getType()
   |
   +-- type.isPrimitive() ?
          |
          +-- false: rawValue == null or type.isInstance(rawValue)?
          |             true  -> field.set(target, rawValue)
          |             false -> custom converter or error
          |
          +-- true: is rawValue the corresponding wrapper?
                        unboxing -> valid identity/widening?
                           true  -> field.set or setXxx
                           false -> converter with range check or error
~~~

Decisions that must be explicitly documented at the business layer:

- For primitives receiving `null` input: report missing value or use an agreed default; do not silently turn `null` into `0` or `false`.
- For numeric strings: use an appropriate parser, handle overflow and precision; `Field.set` does not parse.
- For generics: you may need to inspect `getGenericType()` and individual elements, because runtime field checks are insufficient.
- For final fields or immutable objects: prefer constructors, factories, builders, or creating a new object.
- For narrowing conversions: only allow when business policy requires and with overflow checks; do not assume `Field.set` supports it.
- For errors: report `declaringClass.fieldName`, target type, and source type, while avoiding logging sensitive values.
- For performance: cache metadata when performing many assignments, but mind `ClassLoader` lifetimes and access permissions.

## 9. Common traps

1. **Confusing `Integer` with `int`:** `Integer.class.isPrimitive() == false`. `setInt` is not a safe shortcut for an `Integer` field; use `set` with `Integer`.
2. **Confusing boxing with arbitrary conversion:** `field.set(obj, 3)` involves boxing at the Java caller, yet a `short` field still does not accept `Integer(3)` via `int → short` narrowing.
3. **Confusing `null` in the two parameters:** `set(obj, null)` can write a reference field; `set(null, value)` throws an error for an instance field.
4. **Confusing String parsing with primitive widening:** `"5"` is not converted by Reflection into `int 5`. Input data conversion belongs to the application's converter.
5. **Confusing generic declarations with runtime checks:** `List<String>` does not guarantee that a value assigned via `Field.set` contains only Strings.
6. **Confusing primitive arrays with primitive fields:** `int[]` is a reference; an `Integer[]` array cannot automatically replace an `int[]`.
7. **Confusing access permission with write permission:** `trySetAccessible` succeeding does not guarantee that final/modifier/module/target constraints are satisfied.
8. **Ignoring precision loss in numeric widening:** a type-valid `long → float` conversion can still lose numeric information.

## 10. Exercises and verification

- For an `int` field, try the wrappers `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`; explain each outcome using the widening table.
- For a `long` field, compare `setInt(target, 9)` and `setDouble(target, 9.0)`.
- For an `Integer` field, compare `set(target, Integer.valueOf(9))` and `setInt(target, 9)`.
- For a `CharSequence` field, try `String`, `StringBuilder`, `null`, and `Integer`.
- For a `List<String>` field, assign a `List<Integer>` and then read as String to observe the consequence of generic erasure.
- For `static int counter`, call `setInt(null, 4)`; compare with an instance `int counter` and a `null` target.
- Extend `HiddenFieldDemo` with `getDeclaringClass()` and demonstrate that each `Field` carries its type from its own declaration.

## 11. References

- [Java SE 17 — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `set`/`setXxx`, primitive unboxing/widening, target, exceptions, write access of final fields.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible` and deep reflection permissions under JPMS.
- [Java Language Specification `5.1.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2): valid widening primitive conversions.

**Remember:** Reference fields follow **object/null assignability**; primitive fields follow **wrapper → unboxing → identity/widening**. Determine the field type and target clearly first, then choose `set` or `setXxx` and handle write permissions.