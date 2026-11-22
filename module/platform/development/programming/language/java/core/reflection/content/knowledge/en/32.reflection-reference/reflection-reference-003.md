# Table of Allowed Type Conversions in Reflection `get`, `set`, `invoke`, and `newInstance`

When using Java Reflection, type names may only be known at runtime, yet calls still must obey **type conversion rules**. Some conversions are supported automatically by Java Reflection, especially **primitive widening** and **unboxing** in appropriate cases. Conversely, **narrowing** conversions such as `long → int` or `double → float` are not performed automatically by Reflection.

Four API groups are easily confused:

- `Field.get(...)`, `Field.getInt(...)`, `Field.getLong(...)`...: **read a field's value**, potentially boxing or widening depending on which getter is called.
- `Field.set(...)`, `Field.setInt(...)`, `Field.setLong(...)`...: **write a value to a field**, only when the value matches the field type.
- `Method.invoke(...)`: invokes **a found method**, checking/converting **actual arguments to the declared parameter types**.
- `Constructor.newInstance(...)`: creates an object using **a found constructor**, applying argument conversion rules similar to `Method.invoke`.

This article provides a complete table for all eight primitives, compares the API groups, gives compilable Java 17+ examples, and highlights failure cases to recognize. The topic is **data types**, not automatically bypassing `private`, `final`, or module boundaries.

## 1. Foundations: Identity, Widening, Boxing, and Unboxing

### 1.1. Identity and Primitive Widening

**Identity conversion** keeps the same type, e.g., `int → int`.

**Widening primitive conversion** converts a primitive type to a target type permitted by Java according to the diagram:

```text
byte  ──> short ──> int ──> long ──> float ──> double
                 ^
char ────────────┘

boolean  (converts only to boolean)
```

The diagram only illustrates the main branches. The full table below is the authoritative reference, especially since `char` does not convert directly to `short` and numeric types have multiple widening branches.

| Source Type | Allowed Target Primitive Types (including itself) |
| --- | --- |
| `boolean` | `boolean` |
| `byte` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `short` | `short`, `int`, `long`, `float`, `double` |
| `char` | `char`, `int`, `long`, `float`, `double` |
| `int` | `int`, `long`, `float`, `double` |
| `long` | `long`, `float`, `double` |
| `float` | `float`, `double` |
| `double` | `double` |

**Not allowed automatically:** `int → byte`, `long → int`, `double → float`, `short → char`, `char → short`, and any conversion between `boolean` and numeric types.

`byte → char` is also not allowed even though positive byte values can be represented by `char`. Reflection follows **type conversion relationships**, without checking whether the current value fits within the target type's value range.

**Widening does not guarantee absolute precision preservation:** for example, `long → float` and `int → float` are valid conversions but can lose precision bits due to floating-point representation. The widening rules here refer to **type convertibility**, not a guarantee of zero numeric information loss.

### 1.2. Boxing and Unboxing

The eight corresponding primitive/wrapper pairs:

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

- **Boxing**: `int` into an `Integer` object.
- **Unboxing**: `Integer` back to primitive `int`.
- **Unboxing then widening**: `Integer(4) → int → long` is valid when the target method/constructor/field requires `long`.
- **No automatic conversion chain of unbox → widen → box to a different wrapper**: `Integer` does not automatically turn into `Long` to populate a field or parameter **declared as `Long`**.

When writing `method.invoke(target, 5)`, the compiler automatically boxes the literal `5` into `Integer` to place it in the `Object...` argument list. Then, if the **target method parameter is `long`**, Reflection can unbox `Integer → int` and widen `int → long`.

## 2. Quick Table: Which API Accepts Which Conversion?

| Reflection Call | Actual Source Type | Target Type / Value Expected | Main Rule |
| --- | --- | --- | --- |
| `field.get(obj)` | Declared type of the field | Returned `Object` | Primitive fields are **boxed as their exact original type**; reference fields return the reference value itself |
| `field.getInt(obj)` or `getX` | Primitive of the field | Primitive named by the getter | Readable only when **field type → getter type** is identity/widening |
| `field.set(obj, value)` | `value` object | Declared type of the field | Primitive field: **unbox wrapper** then (if needed) widen; reference field: check value is assignable or `null` |
| `field.setInt(obj, n)` or `setX` | Primitive named by the setter | Declared type of the field | Writable only if **setter type → field type** is identity/widening |
| `method.invoke(obj, args...)` | Each `Object`/wrapper argument | Declared parameter of **the selected method** | Unbox + widen for primitives; references must be compatible; no automatic narrowing |
| `constructor.newInstance(args...)` | Each `Object`/wrapper argument | Declared parameter of **the selected constructor** | Similar to `Method.invoke`; no automatic narrowing |

**The two directions most easily confused:**

- Getters have a target type: `Field.getLong` can read an `int` field because `int → long`.
- Setters have a source type: `Field.setLong` **cannot** write to an `int` field because `long → int` is narrowing.

In short: reading uses the direction **field → getter result**; writing/invoking/instantiating uses the direction **argument → target slot**.

## 3. `Field.get(obj)`: Reading a Field as `Object`

`Field.get(Object obj)` returns an `Object`.

- If the field is a reference, returns the stored reference, which may be `null`.
- If the field is primitive, the value is **boxed** into the corresponding wrapper. A `short` field returns `Short`, an `int` field returns `Integer`; it does not turn `short` into `Integer` just because `get`'s declared return type is `Object`.
- `(int) field.get(obj)` can unbox when the actual object is `Integer`, but it is **not** a general way to convert a boxed `Short` to `int`: such a cast can throw `ClassCastException`.

Example:

```java
class Sample {
    public short small = 7;
}

// Assume another piece of code created the Sample object:
Sample x = new Sample();
java.lang.reflect.Field field = Sample.class.getField("small");

Object raw = field.get(x);          // a Short holding value 7
short small = (Short) raw;          // valid
int widened = field.getInt(x);     // valid: short → int
```

This illustrative snippet depends on where class `Sample` is placed to have appropriate access permissions; the complete, standalone program is in Section 7.

## 4. `Field.getBoolean/getByte/.../getDouble`: Widening Read Lookup

Primitive getters include `getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble`.

**Table direction: the "Field Type" column is the source, "Allowed Getters" are target types.**

| Field Type | Valid Primitive Getters |
| --- | --- |
| `boolean` | `getBoolean` |
| `byte` | `getByte`, `getShort`, `getInt`, `getLong`, `getFloat`, `getDouble` |
| `short` | `getShort`, `getInt`, `getLong`, `getFloat`, `getDouble` |
| `char` | `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble` |
| `int` | `getInt`, `getLong`, `getFloat`, `getDouble` |
| `long` | `getLong`, `getFloat`, `getDouble` |
| `float` | `getFloat`, `getDouble` |
| `double` | `getDouble` |

Example:

```java
// field is an instance Field of type short.
int a = field.getInt(instance);      // valid: short → int
double b = field.getDouble(instance);// valid: short → double
byte c = field.getByte(instance);    // IllegalArgumentException: short → byte
```

The snippet above is illustrative, not a standalone runnable file. Note that **typed getters do not automatically unbox reference fields**: if a field is declared as `Integer`, `getInt` is not a general way to read the wrapper. Use `get`, check for `Integer`, and then unbox manually.

The semantics of the table do not depend on the runtime value: a `short` field currently holding the number 7 still **cannot** be retrieved via `getByte` because the field type is `short`.

## 5. `Field.set(obj, value)`: Writing a Field, Checking Target Type

`Field.set(Object obj, Object value)` accepts the second argument as a reference.

### 5.1. Writing to a Primitive Field

Suppose the field is declared:

```java
public long count;
```

Allowed values:

```java
field.set(obj, Long.valueOf(9));     // Long → long
field.set(obj, Integer.valueOf(9));  // Integer → int → long
field.set(obj, Short.valueOf((short) 9)); // Short → short → long
field.set(obj, Character.valueOf('A'));  // Character → char → long
```

For a `long` field, `Byte`, `Short`, `Character`, `Integer`, and `Long` are unboxed and widened if needed; `Float`, `Double`, and `Boolean` are not compatible.

The following operations fail:

```java
field.set(obj, Double.valueOf(9)); // IllegalArgumentException: double → long
field.set(obj, "9");               // IllegalArgumentException: String is not a numeric wrapper
field.set(obj, null);              // IllegalArgumentException: cannot unbox null
```

Reflection **does not parse numeric strings**, does not check and automatically narrow a `Long` down to `int`, and does not automatically convert `Double` to `Integer` like an explicit cast. When input comes from JSON/CSV/String, the application must parse it, validate bounds, and supply a wrapper that can unbox/widen validly.

### 5.2. Writing to a Reference Field

If a field is declared `CharSequence`, you can assign `String`, `StringBuilder`, or `null` because they are compatible with the target type:

```java
// Field text is declared: public CharSequence text;
textField.set(instance, "abc");                    // valid
textField.set(instance, new StringBuilder("abc")); // valid
textField.set(instance, null);                     // valid
textField.set(instance, Integer.valueOf(3));       // IllegalArgumentException
```

For a field declared `Long`, `Integer.valueOf(3)` is **not** converted into `Long.valueOf(3)`: these are two different reference wrapper types.

### 5.3. Final, Static, Receiver, and Accessibility Are Separate Concerns

- An instance field requires a receiver of the exact class or a subtype; `null` cannot be passed.
- For a static field, the receiver is ignored (`null` can be used).
- Writing to `final` fields is subject to specific restrictions, and attempting to grant access via `setAccessible(true)` does not guarantee write permission. `final static` fields are strictly constrained.
- `getDeclaredField` finds metadata for a private field, but does not mean reading/writing is permitted; `IllegalAccessException` can occur.
- When the name/receiver/access permission is invalid, an error can occur **before** value conversion rules are applied.

## 6. `Field.setBoolean/setByte/.../setDouble`: Primitive Setter Table

Typed setters take a primitive value (for example `setInt(Object obj, int i)`). **Table direction: setter parameter type → target field type.**

| Setter Called | Field Types Accepted |
| --- | --- |
| `setBoolean` | `boolean` |
| `setByte` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `setShort` | `short`, `int`, `long`, `float`, `double` |
| `setChar` | `char`, `int`, `long`, `float`, `double` |
| `setInt` | `int`, `long`, `float`, `double` |
| `setLong` | `long`, `float`, `double` |
| `setFloat` | `float`, `double` |
| `setDouble` | `double` |

Example with a field of type `long`:

```java
wideField.setInt(instance, 42);       // valid: int → long
wideField.setLong(instance, 42L);     // valid: long → long
wideField.setDouble(instance, 42.0);  // IllegalArgumentException
```

Do not invert the direction of the getter and setter tables. `getLong` from an `int` field is valid, whereas `setLong` into an `int` field is invalid.

## 7. Java 17+ Program: Running Actual Success and Failure Cases

The following example demonstrates **all four APIs**, including primitive widening, unboxing, reference assignability, exact signature lookup, `void`, varargs, and narrowing errors.

Create the file **`ReflectionConversionsDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionConversionsDemo {
    public static class Target {
        public short small = 7;
        public int number = 10;
        public long wide;
        public CharSequence text = "before";
        public static int shared = 3;

        public Target(long seed) {
            this.wide = seed;
        }

        public double twice(double value) {
            return 2 * value;
        }

        public String describe(CharSequence value) {
            return "[" + value + "]";
        }

        public void touch() {}

        public static String join(String... words) {
            return String.join("|", words);
        }
    }

    @FunctionalInterface
    interface Checked {
        void run() throws Exception;
    }

    private static void expectIllegal(String label, Checked action)
            throws Exception {
        try {
            action.run();
            System.out.println(label + ": unexpected success");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + ": IllegalArgumentException");
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Target> ctor = Target.class.getConstructor(long.class);
        Target target = ctor.newInstance(Integer.valueOf(4));
        System.out.println("constructor long=" + target.wide);

        Field small = Target.class.getField("small");
        System.out.println("Field.get wrapper="
                + small.get(target).getClass().getSimpleName());
        System.out.println("Field.getInt short=" + small.getInt(target));
        expectIllegal("Field.getByte short", () -> small.getByte(target));

        Field wide = Target.class.getField("wide");
        wide.set(target, Integer.valueOf(21));
        System.out.println("Field.set Integer -> long="
                + wide.getLong(target));
        wide.setInt(target, 33);
        System.out.println("Field.setInt -> long="
                + wide.getLong(target));

        Field number = Target.class.getField("number");
        number.set(target, Character.valueOf('A'));
        System.out.println("Field.set Character -> int="
                + number.getInt(target));
        expectIllegal("Field.set Long -> int",
                () -> number.set(target, Long.valueOf(5)));

        Field text = Target.class.getField("text");
        text.set(target, new StringBuilder("ready"));
        System.out.println("Field.set subtype=" + text.get(target));
        expectIllegal("Field.set incompatible reference",
                () -> text.set(target, Integer.valueOf(3)));

        Method twice = Target.class.getMethod("twice", double.class);
        System.out.println("Method.invoke Integer -> double="
                + twice.invoke(target, Integer.valueOf(6)));
        expectIllegal("Method.invoke String -> double",
                () -> twice.invoke(target, "6"));

        Method describe =
                Target.class.getMethod("describe", CharSequence.class);
        System.out.println("Method.invoke String -> CharSequence="
                + describe.invoke(target, "abc"));

        try {
            Target.class.getMethod("twice", int.class);
            System.out.println("getMethod int: unexpected success");
        } catch (NoSuchMethodException expected) {
            System.out.println("getMethod int: NoSuchMethodException");
        }

        Method touch = Target.class.getMethod("touch");
        System.out.println("void invoke -> null="
                + (touch.invoke(target) == null));

        Method join = Target.class.getMethod("join", String[].class);
        System.out.println("varargs array="
                + join.invoke(null, (Object) new String[]{"a", "b"}));
        expectIllegal("varargs no auto packing",
                () -> join.invoke(null, "a", "b"));

        expectIllegal("newInstance String -> long",
                () -> ctor.newInstance("4"));
        System.out.println("primitive get boxed="
                + (number.get(target) instanceof Integer));
    }
}
```

**Compile/run:**

```bash
javac -encoding UTF-8 ReflectionConversionsDemo.java
java ReflectionConversionsDemo
```

**Actual program output:**

```text
constructor long=4
Field.get wrapper=Short
Field.getInt short=7
Field.getByte short: IllegalArgumentException
Field.set Integer -> long=21
Field.setInt -> long=33
Field.set Character -> int=65
Field.set Long -> int: IllegalArgumentException
Field.set subtype=ready
Field.set incompatible reference: IllegalArgumentException
Method.invoke Integer -> double=12.0
Method.invoke String -> double: IllegalArgumentException
Method.invoke String -> CharSequence=[abc]
getMethod int: NoSuchMethodException
void invoke -> null=true
varargs array=a|b
varargs no auto packing: IllegalArgumentException
newInstance String -> long: IllegalArgumentException
primitive get boxed=true
```

The output above was verified with `javac` and `java`. Several statements use `expectIllegal` for illustration and **deliberately catch the error**, so the program still terminates normally.

**Reading the results by group:**

1. `Constructor<Target>` takes a parameter declared as `long`. Passing `Integer(4)` unboxes to `int` and widens to `long`, so `wide = 4`.
2. `small` is a `short` field. `Field.get` boxes to `Short`; `getInt` is valid; `getByte` fails because it would have to narrow `short → byte`.
3. `wide` is a `long` field. Writing `Integer(21)` or calling `setInt(33)` are both valid. `number` is an `int` field; writing `Character('A')` becomes 65, while `Long(5)` cannot be automatically narrowed to `int`.
4. `text` is declared `CharSequence`, so it accepts `StringBuilder` because it implements this interface, but does not accept `Integer`.
5. `twice(double)` accepts `Integer(6)` after unbox+widen and returns `Double(12.0)`. Passing the string `"6"` does not auto-parse.
6. `describe(CharSequence)` accepts `String` because `String` implements `CharSequence`.
7. `getMethod("twice", int.class)` **does not find it** just because `twice(double)` exists: lookup requires **the declared parameter signature**, without applying widening rules when searching for a method.
8. `void` returns `null` via `Method.invoke`. A method taking `String...` actually has a final reflection parameter of type `String[]`, so an array must be passed as **a single argument**.
9. The `Target(long)` constructor does not automatically convert `String` to `long`.

## 8. `Method.invoke`: Argument Conversion After Selecting the Method

`Method.invoke(Object receiver, Object... args)` permits type conversions when **passing values** for each method parameter:

| Target Method | Argument Passed | Result |
| --- | --- | --- |
| `f(long)` | `Integer.valueOf(3)` | Valid: unbox `int`, widen `long` |
| `f(double)` | `Long.valueOf(3)` | Valid: unbox `long`, widen `double` |
| `f(CharSequence)` | `"abc"` | Valid: compatible reference |
| `f(Number)` | `Integer.valueOf(3)` | Valid: `Integer` is a subtype of `Number` |
| `f(Long)` | `Integer.valueOf(3)` | Invalid: does not auto-unbox+widen+box to `Long` |
| `f(int)` | `Long.valueOf(3)` | Invalid: requires narrowing `long → int` |
| `f(boolean)` | `Integer.valueOf(1)` | Invalid: numbers do not convert to boolean |
| `f(int)` | `null` | Invalid: cannot unbox `null` |
| `f(String)` | `null` | Valid if the method call/internal logic accepts `null` |
| `f(int)` | `"123"` | Invalid: Reflection does not parse String |

**Critically important:** the following two steps are completely different:

```java
Method m = Target.class.getMethod("twice", double.class); // FIND exact signature
Object result = m.invoke(target, Integer.valueOf(6));    // CONVERT value
```

`getMethod` and `getDeclaredMethod` search based on **name + exact declared parameter types**, without choosing an overload based on argument widening. Reflection does not perform overload resolution on behalf of the compiler.

### Return Value of `invoke`

- Method returning primitive: `Method.invoke` boxes into the corresponding wrapper, e.g. `double → Double`.
- Method returning reference: returns the actual object, which may be `null`.
- Method returning `void`: `invoke` returns `null`.
- Primitive arrays such as `int[]` are returned as the `int[]` array object, **without** automatically boxing each element into `Integer`.

**Errors other than conversion:** if the method is valid but target code throws an exception, `Method.invoke` wraps the exception in `InvocationTargetException`; inspect `getCause()`. Argument-checking errors from Reflection are typically `IllegalArgumentException`, access errors can be `IllegalAccessException`, and an unsuitable receiver also leads to its own error.

## 9. `Constructor.newInstance`: Same Argument Rules, but the Right Constructor Must Be Chosen

`Constructor<T>.newInstance(Object... args)` applies **unboxing and method invocation conversions** to match each argument with the parameter type of the selected constructor.

```java
Constructor<Target> constructor =
        Target.class.getConstructor(long.class); // exact lookup for long
Target value = constructor.newInstance(Integer.valueOf(4)); // valid
```

In the snippet above, `Target` is the class defined in the Section 7 example. If you change it to `getConstructor(int.class)`, lookup throws `NoSuchMethodException` because only the `Target(long)` constructor exists.

A few scenarios:

- `newInstance(Short.valueOf((short) 5))` for constructor `(long)`: valid.
- `newInstance(Long.valueOf(5))` for constructor `(int)`: invalid.
- `newInstance("5")` for constructor `(long)`: invalid because Reflection does not parse.
- `newInstance(null)` can cause ambiguity in a **Java varargs call**. If you want to pass **a single `null` argument** to a constructor with one reference parameter, use `newInstance((Object) null)`. For a no-arg constructor, you can use `newInstance()`.

Similar to `Method.invoke`, a constructor with a varargs parameter **does not automatically take separate arguments of the target method and pack them into an array**. Pass a properly typed array as one formal argument.

An `abstract` class, enum, inaccessible class, or constructor throwing an exception can still cause `newInstance` to fail for reasons other than conversion. `Class.newInstance()` has been deprecated since Java 9; use `getDeclaredConstructor().newInstance()` when appropriate instead.

## 10. Varargs Has Two Layers: The Reflection API's and the Target Method's

The signature `Method.invoke(Object receiver, Object... args)` means **the Reflection API itself accepts varargs**. That does not make `invoke` automatically perform varargs packing for the invoked method.

Target method example:

```java
public static String join(String... words) {
    return String.join("|", words);
}
```

Its runtime signature is `join(String[])`. When using Reflection:

```java
Method join = Target.class.getMethod("join", String[].class);
Object result = join.invoke(null, (Object) new String[]{"a", "b"}); // valid
```

Casting to `(Object)` ensures the array is **a single element** of `args` instead of potentially being interpreted as the array containing the arguments to `Method.invoke` itself.

```java
join.invoke(null, "a", "b"); // Wrong: 2 arguments instead of 1 String[] argument
```

In complex situations, the clearest approach is to construct an `Object[]` array containing the exact count/order of formal parameters:

```java
Object[] supplied = {new String[]{"a", "b"}};
Object output = join.invoke(null, supplied);
```

If the target method has two parameters where the last parameter is varargs, pass **two elements** in the Reflection argument array; the second element is the properly typed packed array.

## 11. Important Limitations When Combining Boxing/Unboxing

### Do Not Treat Every `Number` as Unboxable to Any Primitive

Even though `Integer` and `Long` both extend `Number`, Reflection only uses the matching primitive wrappers for unboxing. A `BigDecimal` object **does not** automatically convert to `double` via `doubleValue()` just because it extends `Number`.

```java
// Illustration; not a standalone program:
methodExpectingDouble.invoke(target, new java.math.BigDecimal("1.2"));
// IllegalArgumentException: not a valid primitive wrapper to unbox
```

If you want to accept `Number` flexibly, you must define your own conversion/precision rules and pass a `Double` or permitted wrapper to the method with formal parameter `double`.

### No Implicit Narrowing Even When the Value "Fits"

```java
// Target method has a byte parameter:
methodExpectingByte.invoke(target, Integer.valueOf(5));
// IllegalArgumentException: automatic int → byte is forbidden even though 5 fits in byte.
```

If a policy allows narrowing conversion, the application must **explicitly check the value range**, e.g. `value >= Byte.MIN_VALUE && value <= Byte.MAX_VALUE`, and then construct `Byte.valueOf((byte) value)` before invoking.

### Reference Types Are Not Converted into a Different Wrapper

```java
// Target method declares Long, argument is Integer:
methodExpectingLongObject.invoke(target, Integer.valueOf(8));
// IllegalArgumentException: Integer is not assignable to Long.
```

Unlike a target method declaring `long`, this case **does not** automatically perform `Integer → int → long → Long`.

### Null and Primitives

If a formal parameter is primitive, `null` cannot be unboxed; the call can throw `IllegalArgumentException`. For a reference parameter, `null` can be passed through, though target code can still throw an exception if it dereferences `null`.

## 12. Distinguishing Lookup Errors, Conversion Errors, and Access Errors

| Operation | Issue | Typical Outcome |
| --- | --- | --- |
| `getMethod("f", int.class)` when only `f(long)` exists | Looked up wrong signature; method not called yet | `NoSuchMethodException` |
| `getDeclaredField("missing")` | No such declared field | `NoSuchFieldException` |
| `getInt` on a `short` field | Valid widening | Returns `int` |
| `getByte` on a `short` field | Narrowing forbidden | `IllegalArgumentException` |
| `setInt` on a `long` field | Valid widening | Writes the value |
| `setLong` on an `int` field | Narrowing forbidden | `IllegalArgumentException` |
| `invoke` with `Long` for an `int` parameter | Narrowing forbidden | `IllegalArgumentException` |
| `invoke` with valid arguments but target throws an error | Business method execution error | `InvocationTargetException` wrapping cause |
| `newInstance` with wrong argument type | Cannot convert according to rules | `IllegalArgumentException` |
| Accessing a disallowed member | Access/JPMS | `IllegalAccessException` or `InaccessibleObjectException` when opening access |
| Wrong receiver class or `null` for instance member | Accessing wrong object | `IllegalArgumentException` or `NullPointerException` depending on API |

**Separate error handling into two steps:**

1. **Lookup and metadata validation**: confirm the field/method/constructor is correctly selected, receiver is valid, access is allowed, and formal types and arguments are convertible.
2. **Read/write/invoke/instantiate**: catch Reflection errors per API, while distinguishing exceptions raised by **the invoked code**.

Do not rely on catching generic `Exception` and guessing a conversion error when the error actually comes from access rights or business logic.

## 13. Pre-Checking Types When Processing a List of Fields/Methods

A mapping library or batch runner should not try `invoke` on each value and wait to break on the last item. You can perform a preflight check:

1. For each selected member, obtain the **actual target types** via `Field.getType()`, `Method.getParameterTypes()`, or `Constructor.getParameterTypes()`.
2. For a **reference target type**, confirm the value is `null` or `targetType.isInstance(value)`.
3. For a **primitive target type**, identify the source wrapper (if the value is non-`null`), unbox to the corresponding primitive, and check the widening table in Section 1.
4. For typed `Field.getX/setX`, compare **the declared primitive type** using the correct direction in the tables of Sections 4/6.
5. Check argument count, packed varargs array, receiver, static/instance, and access permissions.
6. Only when all entries pass should you schedule execution, while still handling exceptions thrown during execution.

You can implement a helper `canWidenPrimitive(source, target)` based on the table in Section 1; **do not** use `target.isAssignableFrom(source)` for primitive widening because `isAssignableFrom` checks runtime type assignability, not the primitive widening table.

Example:

```java
int.class.isAssignableFrom(short.class); // false: does not check widening
Number.class.isAssignableFrom(Integer.class); // true: reference subtype
```

Mappers that need to support conversions from text, enum, date/time, or custom numeric types must define conversion policies **outside** Reflection rules and report when a value cannot be safely converted.

## 14. Checklist and Self-Check Questions

**Checklist:**

- Do you know the **exact field/formal parameter type** and the conversion direction to check?
- If primitive, is the source type in the target type's widening table?
- If reference, is the value assignable or `null`? Are you confusing `Integer` with `Long`?
- Have you distinguished `Field.get` (boxing) from `Field.getX` (widening) and the reverse direction `Field.setX`?
- Were `getMethod`/`getConstructor` looked up using the exact declared signature?
- Have varargs been packed into **a single array argument**?
- Are access control, receiver, final/static, and exceptions from target code handled?

**Self-check:**

1. Can a field declared as `char` be read via `getShort`, `getInt`, and `getDouble`? Why?
2. Does a field declared as `int` accept `Long.valueOf(3)` via `Field.set`, even though 3 is very small?
3. With constructor `Widget(double)`, is passing `Integer.valueOf(5)` to `Constructor.newInstance` valid? Will looking up with `getConstructor(int.class)` find that constructor?
4. When `Method.invoke` calls a method returning `long`, what wrapper does it return? What about a method returning `void`?
5. Why does `Field.get` on a `short` field return `Short`, while `Field.getInt` on that field returns `int`?
6. Does a method with signature `f(Long)` accept `Integer` automatically? How does it differ from `f(long)`?
7. With `String... args`, why can `Method.invoke(receiver, "a", "b")` be wrong?
8. In which case does Reflection throw `InvocationTargetException` instead of `IllegalArgumentException` when calling a method?

### Official References

- [Java SE 17: `Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): getters/setters, widening, and boxing.
- [Java SE 17: `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke`, argument conversion, and return value.
- [Java SE 17: `Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): `newInstance`, parameters, and exceptions.
- [Java Language Specification 17 §5.1–5.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html): widening, boxing, unboxing, and method invocation conversions.
