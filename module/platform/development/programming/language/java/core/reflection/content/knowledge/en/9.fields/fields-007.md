# Field.getInt(), getLong(), getDouble() and allowed type conversions

When reading a field value using Java Reflection, `java.lang.reflect.Field` provides two groups of APIs: `get(Object)` returns `Object`, whereas methods such as `getInt(Object)`, `getLong(Object)`, and `getDouble(Object)` return a **specific primitive type**. Those `getXxx` methods do not simply "coerce" arbitrary data into type `Xxx`: they only accept fields whose **primitive type is compatible under widening primitive conversion rules**.

For example, with a field declared as `byte`, `getInt`, `getLong`, and `getDouble` can all read the value. However, with a `double` field, calling `getInt` throws `IllegalArgumentException`, even when the `double` value happens to be `10.0`. The conversion is evaluated based on **the field's declared type**, not whether the current value can "fit" inside the target type.

This lesson focuses on the three methods `getInt`, `getLong`, and `getDouble`, while presenting the general rules to apply correctly to the other primitive getters as well.

## 1. What do Field.getInt(), getLong(), and getDouble() do?

A `Field` represents **a specific field in the declaring class**, not a copy of a field value. When calling a getter, the `obj` argument specifies the object holding the value to read (or `null` if it is a `static` field).

| Method | Java return type | Accepts fields with declared type |
| --- | --- | --- |
| `getInt(obj)` | `int` | `byte`, `short`, `char`, `int` |
| `getLong(obj)` | `long` | `byte`, `short`, `char`, `int`, `long` |
| `getDouble(obj)` | `double` | `byte`, `short`, `char`, `int`, `long`, `float`, `double` |

In each row, a field with the **same type** as the return type is also valid (identity conversion). The remaining types are valid because a **widening primitive conversion** exists from the field's type to the getter's return type.

Examples of valid conversions:

- `byte` field holding `12`: `field.getInt(obj)` returns `12` of type `int`; `getLong(obj)` returns `12L`; `getDouble(obj)` returns `12.0`.
- `char` field holding `'A'`: `getInt(obj)` returns **65** (`char` is an unsigned 16-bit UTF-16 code unit, widened to `int` by numeric value).
- `float` field holding `1.25f`: `getDouble(obj)` returns `1.25`.
- `long` field: `getDouble(obj)` is allowed, though it **may round and lose precision**.

Invalid examples:

- `getInt` on `long`, `float`, or `double`: this would be **narrowing**, which getters do not perform.
- `getLong` on `float` or `double`: no corresponding widening primitive conversion exists.
- `getInt` on `boolean`: `boolean` does not widen to numeric types.
- `getInt` on `Integer`: `Integer` is a **reference type**, not a primitive `int` field. `getInt` does not automatically unbox an `Integer` object stored in the field.

## 2. Complete conversion table for all primitive getters

To avoid memorizing individual functions in isolation, remember that **the source type is the field's declared type** and **the target type is the getter's return type**. A getter only supports identity or a valid widening primitive conversion step according to the Java Language Specification.

| Getter | Allowed field types |
| --- | --- |
| `getBoolean` | `boolean` |
| `getByte` | `byte` |
| `getShort` | `byte`, `short` |
| `getChar` | `char` |
| `getInt` | `byte`, `short`, `char`, `int` |
| `getLong` | `byte`, `short`, `char`, `int`, `long` |
| `getFloat` | `byte`, `short`, `char`, `int`, `long`, `float` |
| `getDouble` | `byte`, `short`, `char`, `int`, `long`, `float`, `double` |

Diagram of common numeric widening paths:

```text
byte  -> short -> int -> long -> float -> double
char  ---------> int -> long -> float -> double
                 (char does not widen to short or byte)
```

This diagram illustrates steps in the widening direction, including steps that can jump over intermediate types (such as `byte -> double`). `short` does **not** automatically convert to `char`; `char` does not convert to `short` because their value ranges differ. `boolean` stands alone and can only be read via `getBoolean`.

**Widening differs from casting/narrowing in Java code:** a Java expression can write `(int) someDouble` with an explicit cast, whereas `Field.getInt` does not accept a `double` field. To read and then cast intentionally, you must first use the getter matching the source type and then perform the conversion at the application layer.

## 3. Compilable and runnable Java 17+ example

The example below illustrates successful widening conversions, two rejected cases, reading a `static` field, and a case where **widening still loses numeric precision**. All fields to be read are declared `public` in a nested class so the example focuses on getter type rules without access permission complications.

Create file `FieldWideningDemo.java`:

```java
import java.lang.reflect.Field;

public class FieldWideningDemo {
    public static class Values {
        public byte small = 12;
        public char letter = 'A';
        public short portion = 32_000;
        public int count = 16_777_217; // 2^24 + 1
        public long huge = 9_007_199_254_740_993L; // 2^53 + 1
        public float fraction = 1.25f;
        public double price = 2.5;
        public Integer wrapper = 99;
        public boolean active = true;
        public static int staticCount = 7;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Values obj = new Values();

        Field small = Values.class.getDeclaredField("small");
        Field letter = Values.class.getDeclaredField("letter");
        Field portion = Values.class.getDeclaredField("portion");
        Field count = Values.class.getDeclaredField("count");
        Field huge = Values.class.getDeclaredField("huge");
        Field fraction = Values.class.getDeclaredField("fraction");
        Field price = Values.class.getDeclaredField("price");
        Field wrapper = Values.class.getDeclaredField("wrapper");
        Field active = Values.class.getDeclaredField("active");
        Field staticCount = Values.class.getDeclaredField("staticCount");

        System.out.println("byte -> int: " + small.getInt(obj));
        System.out.println("char -> long: " + letter.getLong(obj));
        System.out.println("short -> double: " + portion.getDouble(obj));
        System.out.println("float -> double: " + fraction.getDouble(obj));
        System.out.println("int -> float (rounded): " + (int) count.getFloat(obj));
        System.out.println("long -> double (rounded): " + (long) huge.getDouble(obj));
        System.out.println("static int -> long: " + staticCount.getLong(null));
        System.out.println("boolean -> boolean: " + active.getBoolean(obj));

        try {
            price.getInt(obj); // double -> int: not widening
        } catch (IllegalArgumentException ex) {
            System.out.println("double -> int: rejected");
        }

        try {
            wrapper.getInt(obj); // Integer is a reference field
        } catch (IllegalArgumentException ex) {
            System.out.println("Integer -> int: rejected");
        }
    }
}
```

Compile and run commands:

```bash
javac FieldWideningDemo.java
java FieldWideningDemo
```

Output:

```text
byte -> int: 12
char -> long: 65
short -> double: 32000.0
float -> double: 1.25
int -> float (rounded): 16777216
long -> double (rounded): 9007199254740992
static int -> long: 7
boolean -> boolean: true
double -> int: rejected
Integer -> int: rejected
```

The two casts `(int) count.getFloat(obj)` and `(long) huge.getDouble(obj)` are **only used to print an integer after the value has been rounded during the widening step**, making the difference easy to see. They are not conversions automatically performed by `Field.getFloat` or `Field.getDouble`. Widening `16_777_217` to `float` produces `16_777_216.0f`; widening `9_007_199_254_740_993L` to `double` produces `9_007_199_254_740_992.0`.

In the two `try/catch` blocks, the program demonstrates **failure due to an incompatible source type**, not a private field access error. `IllegalArgumentException` is caught at the exact points so the program continues printing the remaining lines.

### Reading values from a static field

For a `static` field, the receiver parameter `obj` **is ignored**; the clearest way to express intent is `staticCount.getLong(null)`. For an instance field, a valid instance must be passed, e.g., `small.getInt(obj)`. Passing `null` for an instance field causes `NullPointerException`, not "reading a default value".

## 4. Widening is allowed, yet precision loss can still occur

The term "widening" in the JLS does not mean every value preserves all significant digits. Distinguish two groups:

**Group preserving exact values when widening:**

- `byte -> int/long/double`, `short -> int/long/double`, `char -> int/long/double`;
- `int -> long` and `int -> double`;
- `float -> double` preserves the exact numeric value *already represented by float* (it does not recover data that may have been lost when the float was created).

**Group that may be rounded:**

- `int -> float`;
- `long -> float`;
- `long -> double`.

For example, `int` has 32 bits, whereas `float` normally has 24 bits of binary significand precision. Therefore, the integer `16_777_217 = 2^24 + 1` cannot be represented exactly as a `float`. Similarly, `double` has 53 bits of binary precision, so `2^53 + 1` cannot be represented exactly as a `double`.

These conversions are still **valid per the API** and do not throw errors: the program receives the rounded result. This is especially important when handling large numeric identifiers, high-resolution timestamps, monetary values, or comparisons requiring absolute precision. For financial data, choose appropriate data types and calculation models from the start, rather than relying on `float`/`double` to preserve every decimal digit.

Another misconception is "reading `float` with `getDouble` makes the original calculation more accurate". In reality, it only represents **the existing float value** as a `double`; if the float was already rounded upon assignment, reading it will not restore earlier data.

## 5. How do primitive getters differ from Field.get(Object)?

`Field.get(Object)` always has a declared return type of `Object`:

- If the field is declared with a primitive type, the value is **boxed** into the corresponding wrapper object (`int -> Integer`, `long -> Long`, `double -> Double`, etc.).
- If the field is declared with a reference type, `get(obj)` returns the existing reference itself (which may be `null`).
- `get(obj)` does not automatically convert a `long` into a `double` according to the target getter type a program desires.

Example (illustrative snippet assuming `count`, `obj`, and `wrapper` are the `Field`/`Values` variables declared in the example above):

```java
Object boxedPrimitive = count.get(obj);  // Integer(16777217)
Object referenced = wrapper.get(obj);    // Integer(99)
int fromReference = ((Integer) referenced).intValue();
```

Here `count` describes a primitive `int` field, whereas `wrapper` describes a reference `Integer` field. Both return an `Integer` when calling `get`, but for different reasons: the primitive is boxed, while the reference already stores an `Integer` object.

Consequently, you cannot see `get` return an `Integer` and infer that `wrapper.getInt(obj)` will also succeed. **Primitive getters check the field's declared type**, and do not automatically unbox a wrapper field. To handle various fields of reference type `Number`, first read with `get(obj)`, check the type/null, and then choose a conversion in the application — keeping in mind that `Number.intValue()` may narrow, drop fractional parts, or overflow depending on the source type.

The conversion example below is **explicit narrowing outside Reflection**, not the behavior of `getInt`:

```java
double value = price.getDouble(obj); // primitive double field
int narrowed = (int) value;           // Explicit Java cast
```

Do not use this explicit cast to argue that `price.getInt(obj)` ought to have succeeded.

## 6. Choosing a getter based on metadata and data requirements

For code analyzing/serializing many fields, inspect the declared type using `field.getType()` and decide how to read based on an explicit contract. Example:

```java
Class<?> type = field.getType();
if (type == int.class) {
    int value = field.getInt(receiver);
    // Handle int value.
} else if (type == long.class) {
    long value = field.getLong(receiver);
    // Handle long value.
} else if (type == double.class) {
    double value = field.getDouble(receiver);
    // Handle double value.
} else {
    Object value = field.get(receiver);
    // Handle other types, possibly including wrappers or null.
}
```

The snippet above **is not a standalone Java program**: it requires `field` and `receiver` variables, properly scoped local declarations, and handling/declaring `IllegalAccessException`. It illustrates explicit type-based dispatch. If business logic genuinely wants every numeric primitive field as `double`, you may choose `getDouble` since all numeric primitives have a widening path to `double`, while still accepting the risk of precision loss for `long`.

An API that only accepts an exact input type (for instance, a schema distinguishing `int` and `long`) should check `field.getType()` first, rather than calling `getLong` on every field and assuming every read value was originally a `long`.

**Do not confuse with `Field.setXxx`:** when *writing*, the source/target roles of conversion are reversed. `getDouble` reading an `int` is valid, but that does not prove `setInt` will accept a field declared as `double` in other contexts without checking the API contract separately; read the corresponding documentation for write operations. Setters have their own rules and restrictions, especially for `final` fields.

## 7. Exceptions and access conditions

Besides type compatibility, a field read must also be valid with respect to the receiver object, access permissions, and class initialization:

| Scenario | Expected behavior |
| --- | --- |
| Target getter does not accept the field's primitive type (`getInt` for `double`) | `IllegalArgumentException` |
| Primitive getter called on a reference-type field (`Integer`, `String`, `Number`) | `IllegalArgumentException` |
| Instance field with `null` receiver | `NullPointerException` |
| Instance field with wrong receiver object type | `IllegalArgumentException` |
| No permission to read the field via Reflection | `IllegalAccessException` |
| Reading a static field triggers class initialization and initialization fails | `ExceptionInInitializerError` |

For example, `getDeclaredField("hidden")` can **find** a private field, yet that does not mean `getInt(obj)` is permitted to read it. Java language access rules and module boundaries must be respected. If normal access already exists, enabling the suppress flag is unnecessary; if deep reflection is required, `canAccess(receiver)` and `trySetAccessible()` can help check/request access per the contract, though they should not be treated as a default way to bypass encapsulation.

`IllegalAccessException` is a checked exception declared by the getters. `IllegalArgumentException` and `NullPointerException` are unchecked; having `main` declare `throws ReflectiveOperationException` in the example does not turn wrong-getter-type errors into checked exceptions. This is why the example intentionally catches the two `IllegalArgumentException`s separately.

When a getter reads a `static` field, Java may initialize the declaring class if not yet initialized. If initialization fails, the error relates to the initialization process, **not the conversion from `int` to `long`**.

## 8. Common mistakes when working with Field

**1. "The method name dictates the exact declared type the field must have."** `getInt` is not exclusive to `int` fields, but is also valid for `byte`, `short`, and `char`. Conversely, it cannot directly read `long`, `float`, or `double` fields.

**2. "If the value fits in the int range, getInt(doubleField) is allowed."** False; the API inspects **the field's type**, not its value. A `double` field holding `1.0` is still invalid for `getInt`.

**3. "getDouble never loses data."** False; `long -> double` can lose precision even though the conversion is valid. Widening is not necessarily exact.

**4. "The Integer wrapper is equivalent to primitive int in Reflection."** False; `Field.getInt` does not unbox reference fields. `Field.get` is the option to retrieve the wrapper, after which the application handles it.

**5. "getLong can read float because long is 64-bit."** False; primitive widening relationships are based on numeric kinds and JLS rules, not merely bit width. `float -> long` is narrowing and is not performed by `getLong`.

**6. "char to int returns the character like a String."** False; `getInt` returns the numeric value of the UTF-16 code unit. For `'A'`, the result is `65`, not the string `"A"`.

**7. "The receiver must always be an instance."** False for `static` fields; passing `null` is the clearest expression. However, instance fields strictly require a valid receiver.

**8. "IllegalAccessException and IllegalArgumentException are the same."** False; one concerns **access permissions**, while the other usually concerns **an incompatible getter type or receiver**. Fix the actual root cause rather than trying `setAccessible(true)` to cure every error.

## 9. Self-check

1. Can a field declared as `byte` use `getInt`, `getLong`, and `getDouble`? **Yes**, because the corresponding widening paths exist.
2. Can a field declared as `char` use `getShort`? **No**, `char -> short` is not a widening primitive conversion.
3. Can a field declared as `float` be read with `getLong`? **No**; `float -> long` is narrowing.
4. Can a field declared as `long` be read with `getDouble`? **Yes**, though precision loss may occur.
5. Can an `Integer` field holding `42` be read via `getInt`? **No**; it is a reference field. Use `get` and then convert with checks.
6. Can a `double` field holding exactly `100.0` be read with `getInt`? **No**; the declared type is incompatible.
7. Why can `getInt` return `65` when a field is declared as `char letter = 'A'`? **Because `char -> int` is widening**, representing the UTF-16 value of `'A'` as a number.
8. Can a `static int` field be read by calling `getLong(null)`? **Yes**: the receiver is ignored for static fields and `int -> long` is valid.

## 10. Official documentation

- [Oracle Java SE 21 — `java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html): contract of `get`, `getInt`, `getLong`, `getDouble`, other primitive getters, receiver types, and exceptions.
- [Java Language Specification SE 21 — §5.1.2 Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.2): list of valid conversions and cases where precision may be lost.

**Remember:** When reading with `Field.getInt/getLong/getDouble`, go from **the field's declared primitive type** to **the getter's return type** via identity or widening. There is no automatic narrowing, no unboxing of wrapper fields, and widening to floating-point does not always preserve the exact original number.