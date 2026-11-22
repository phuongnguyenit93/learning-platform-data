# Field.setInt(), Field.setLong(), and widening limits in Java Reflection

## 1. What will we learn and why understand type conversion rules?

With Java Reflection, a `java.lang.reflect.Field` object represents a field declared in a class or interface. Besides `Field.set(Object, Object)` which accepts the value as an object, Java provides methods specialized for primitive types such as `setByte`, `setShort`, `setChar`, `setInt`, `setLong`, `setFloat`, and `setDouble`.

Once you have obtained a `Field`, you may want to write a numeric value without explicitly boxing it into an `Integer` or `Long`:

~~~java
Field field = Counter.class.getField("total"); // total is public long
field.setInt(counter, 42);                      // valid: int -> long
~~~

The snippet above only illustrates when you already have a `counter` object of type `Counter`. A complete, compilable example is in section 5.

Key point: **the type of the value passed to a `setXxx` method does not have to match the field's declared type identically, but it can only be converted via an identity conversion or a widening primitive conversion.** Reflection rejects narrowing conversions, even when the specific value fits within the target type's range.

This lesson explains the two core methods `setInt` and `setLong`, how to determine conversion direction, the difference between `getXxx` and `setXxx`, the impact on precision, and practical errors.

## 2. Mechanism of the two methods

Two declarations in the `Field` API:

~~~java
void setInt(Object obj, int i)
        throws IllegalArgumentException, IllegalAccessException;

void setLong(Object obj, long l)
        throws IllegalArgumentException, IllegalAccessException;
~~~

- `obj` is the object containing the instance field. For a `static` field, `null` can be passed since there is no receiver object; for an instance field, passing `null` causes `NullPointerException`.
- `i` is an **`int` value**; `l` is a **`long` value**. The parameter type is fixed by the method signature, not inferred from the target field.
- `Field` knows the target type via `getType()`; at write time, Java checks whether the input value can be assigned to the field via identity or primitive widening.
- If the target type allows it, the value is converted and written to the field. If narrowing is required or the target type is incompatible, the method throws `IllegalArgumentException`. If write permission is lacking due to access checks or `final`, `IllegalAccessException` may occur.

Visualizing data flow:

~~~text
setInt(receiver, int)   -- identity / widening --> primitive field
setLong(receiver, long) -- identity / widening --> primitive field

No automatic narrowing branch to "force-fit" the target field.
~~~

**Distinction from casting in Java:** an explicit cast such as `(byte) 200` or `(int) someLong` is performed before calling the setter, as requested by the programmer. `setInt`/`setLong` themselves do not perform narrowing casts.

### Most important compatibility table

| Declared field type | `setInt(obj, int)` | `setLong(obj, long)` | Reason |
| --- | --- | --- | --- |
| `byte` | ❌ | ❌ | `int -> byte` and `long -> byte` are both narrowing |
| `short` | ❌ | ❌ | `int/long -> short` is not accepted |
| `char` | ❌ | ❌ | `int/long -> char` is not widening |
| `int` | ✅ | ❌ | `int -> int` is identity; `long -> int` is narrowing |
| `long` | ✅ | ✅ | `int -> long` is widening; `long -> long` is identity |
| `float` | ✅ | ✅ | `int -> float` and `long -> float` are widening |
| `double` | ✅ | ✅ | `int -> double` and `long -> double` are widening |
| `boolean` | ❌ | ❌ | No numeric conversion to `boolean` |
| `Integer`, `Long`, `Number`, or other reference types | ❌ | ❌ | `setInt`/`setLong` are for primitive fields, not wrapper/reference fields |

Here ✅ means **valid in terms of type conversion** if the receiver object and access permissions are also valid; it does not guarantee the call will always succeed when the field is `private`, `final`, or the object has the wrong type.

A short way to remember:

- `setInt` can write to: **`int` → `long` → `float` → `double`**.
- `setLong` can write to: **`long` → `float` → `double`**.
- **You cannot go backward toward smaller types**, regardless of whether the concrete number is `0`, `7`, or within the range of `byte`.

## 3. Widening is a type rule, not a value-size comparison

According to Java's primitive type conversion rules, common numeric widening directions include:

~~~text
byte  -> short -> int -> long -> float -> double
          ^       ^       ^       ^        ^
char  ------------+-------+-------+--------+
~~~

The diagram only expresses typical directions; `char` does **not** widen to `byte` or `short`. Full table of direct paths:

| Source type | Target types accepted via widening |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | No wider primitive type |
| `boolean` | Does not widen to any numeric type |

Each type also always allows an identity conversion to itself. `setInt` starts from source `int`, while `setLong` starts from source `long`; thus you only need to check these two rows plus identity.

**Why does `setInt(fieldByte, 7)` fail even though 7 fits in `byte`?** Java has a *compile-time constant narrowing* rule for certain assignments (e.g., `byte b = 7;`). That is a conditional rule in source-code assignment contexts, **not** a rule applied by `Field.setInt` to an `int` at runtime. Reflection does not inspect the value and shrink it back to `byte`.

Two separate examples:

~~~java
byte b = 7;                        // valid source code because of special int constant
Field f = Example.class.getField("b");  // Example has public byte b
f.setInt(example, 7);             // IllegalArgumentException
f.setByte(example, (byte) 7);     // right method for byte field
~~~

The code above is illustrative, assuming `example` is a valid instance of `Example`; the full program is in section 5.

Similarly, `setLong(fieldInt, 5L)` is rejected, even though `5L` lies within the `int` range. If business logic allows truncating values, you must introduce range checks and an explicit conversion first; pass to `setInt` an `int` only after verification.

## 4. Calling the setter properly and distinguishing from Field.set(Object, Object)

### 4.1. Choosing the overload by source and target types

~~~java
Field f = Data.class.getField("total"); // public long total
Data d = new Data();

f.setInt(d, 123);                       // valid: int -> long
f.setLong(d, 123L);                     // valid: long -> long
~~~

If the field is `public int count`:

~~~java
Field f = Data.class.getField("count"); // public int count
f.setInt(d, 123);                       // valid
f.setLong(d, 123L);                     // IllegalArgumentException
~~~

**A syntax trap:** `f.setLong(d, 123)` still compiles, because the compiler widens the literal `123` from `int` to the method's `long` parameter. When `setLong` actually runs, it is writing a **`long`** rather than "writing an `int`", so an `int` field is still rejected. The setter name determines the source type that runtime checks.

### 4.2. `set(Object, Object)` can unbox and then widen

For a primitive field, `Field.set(obj, value)` can **unbox** a wrapper value and then widen when needed:

~~~java
Field total = Data.class.getField("total"); // long
total.set(d, Integer.valueOf(25));          // Integer -> int -> long: valid
~~~

Equivalent in value type to `total.setInt(d, 25)`. Conversely, for a reference field:

~~~java
Field boxed = Data.class.getField("boxed"); // Integer boxed
boxed.set(d, Integer.valueOf(25));          // valid: sets Integer reference
boxed.setInt(d, 25);                        // IllegalArgumentException
~~~

**Distinguishing two concepts:** `int -> Integer` boxing commonly occurs when passing arguments to a method accepting `Object`, yet `Field.setInt` never converts a field declared as `Integer` into a primitive. Specialized setters operate according to primitive field rules.

When a program receives data of unknown type beforehand, check `field.getType()` and handle conversion intentionally rather than trying setters arbitrarily and catching errors.

### 4.3. Do not reverse the rules between get and set

- `field.setInt(obj, 7)`: source is `int`, asking whether the target field can accept `int`.
- `field.getLong(obj)`: source is **the field's declared type**, asking whether the read value can widen to `long`.

Therefore, `getLong` on an `int` field is valid, whereas `setLong` on an `int` field is invalid. `getInt` on a `long` field is also rejected because `long -> int` is narrowing. Section 5 gives an empirical example of this asymmetry.

## 5. Complete, runnable Java 17+ program

This program uses **public, non-final fields** to observe type conversion rules without getting tangled in access permissions; it also includes examples of a `static` field, boxing, and getter direction. Error output lines are normalized by exception type name so results do not depend on JDK error messages.

Create file **`WideningFieldDemo.java`**:

~~~java
import java.lang.reflect.Field;

public class WideningFieldDemo {
    static class Metrics {
        public int count;
        public long total;
        public float roundedFloat;
        public double roundedDouble;
        public byte tiny;
        public char symbol;
        public Integer boxed;
        public static long shared;
    }

    @FunctionalInterface
    interface FieldAction {
        void run() throws IllegalAccessException;
    }

    static void attempt(String label, FieldAction action) {
        try {
            action.run();
            System.out.println(label + ": OK");
        } catch (IllegalArgumentException ex) {
            System.out.println(label + ": IllegalArgumentException");
        } catch (IllegalAccessException ex) {
            System.out.println(label + ": IllegalAccessException");
        }
    }

    public static void main(String[] args) throws Exception {
        Metrics m = new Metrics();
        Class<Metrics> type = Metrics.class;

        Field count = type.getField("count");
        Field total = type.getField("total");
        Field roundedFloat = type.getField("roundedFloat");
        Field roundedDouble = type.getField("roundedDouble");
        Field tiny = type.getField("tiny");
        Field symbol = type.getField("symbol");
        Field boxed = type.getField("boxed");
        Field shared = type.getField("shared");

        count.setInt(m, 7);
        total.setInt(m, 42);
        roundedFloat.setInt(m, 16_777_217);
        roundedDouble.setLong(m, 9_007_199_254_740_993L);
        shared.setLong(null, 99);

        System.out.println("count=" + m.count
                + ", total=" + m.total
                + ", shared=" + Metrics.shared);
        System.out.println("int->float rounded=" + (int) m.roundedFloat);
        System.out.println("long->double rounded=" + (long) m.roundedDouble);

        attempt("int->byte", () -> tiny.setInt(m, 7));
        attempt("int->char", () -> symbol.setInt(m, 65));
        attempt("long->int", () -> count.setLong(m, 8L));
        attempt("int->Integer", () -> boxed.setInt(m, 3));

        attempt("Integer->long via set",
                () -> total.set(m, Integer.valueOf(88)));
        System.out.println("total after set=" + m.total);

        System.out.println("getLong(int field)=" + count.getLong(m));
        attempt("getInt(long field)",
                () -> System.out.println(total.getInt(m)));
    }
}
~~~

Compile and run from the directory containing the file (JDK 17 or newer):

~~~bash
javac --release 17 WideningFieldDemo.java
java WideningFieldDemo
~~~

**Stdout verified on JDK 21 when compiled with `--release 17`:**

~~~text
count=7, total=42, shared=99
int->float rounded=16777216
long->double rounded=9007199254740992
int->byte: IllegalArgumentException
int->char: IllegalArgumentException
long->int: IllegalArgumentException
int->Integer: IllegalArgumentException
Integer->long via set: OK
total after set=88
getLong(int field)=7
getInt(long field): IllegalArgumentException
~~~

### Why does the program produce this output?

1. `count.setInt(m, 7)` writes the exact value to the `int` field; `total.setInt(m, 42)` writes to `long` via widening. `shared.setLong(null, 99)` writes to the `static long` field without needing an instance.
2. `roundedFloat.setInt(m, 16_777_217)` is **type-valid**, yet `float` does not represent this number exactly; when cast back to `int` to observe, it yields `16_777_216`.
3. `roundedDouble.setLong(m, 9_007_199_254_740_993L)` is **type-valid**, yet `double` rounds down to the nearest representable value `9_007_199_254_740_992`.
4. The next four error lines prove `int -> byte`, `int -> char`, and `long -> int` are all invalid, and an `Integer` field cannot be written via `setInt`.
5. `total.set(m, Integer.valueOf(88))` succeeds because `Field.set` unboxes `Integer` to `int` and then widens to `long`.
6. `count.getLong(m)` reads from `int` and widens to `long`. Conversely, `total.getInt(m)` requires `long -> int`, so it fails.

Running the example on the classpath as in the commands above avoids access barriers across different named modules; the fields are public to focus solely on type conversion.

## 6. Widening is not a promise to preserve every digit

A common misconception is: "widening means a larger target type, so data is never lost." In fact, **widening integers to floating-point numbers can lose precision**.

| Conversion | Valid? | Is the value preserved exactly for all inputs? |
| --- | --- | --- |
| `int -> long` | Yes | Yes, every `int` value is representable in `long` |
| `int -> float` | Yes | No, `float` only has about 24 bits of significand precision |
| `int -> double` | Yes | Yes, every `int` is exactly representable in `double` |
| `long -> float` | Yes | No, may round |
| `long -> double` | Yes | No, `double` has about 53 bits of precision; large `long`s may round |

**Precision loss example:** `16_777_217` differs from `16_777_216` by one unit, yet `float` in that value range cannot hold this odd number exactly. Similarly, `9_007_199_254_740_993L` lies beyond the contiguous integer range that `double` can represent exactly.

Widening does not throw an error for precision loss: the conversion is permitted by **type kind**; the floating-point result is rounded according to Java rules. If the data is exact quantities, IDs, currency, or large integers, choose an appropriate storage type. Do not pick `float` or `double` just because the setter allows converting from `int`/`long`.

Another note: an explicit cast before calling the setter can still lose values. For example:

~~~java
long huge = 3_000_000_000L;
int narrowed = (int) huge; // narrowing cast may change value
countField.setInt(instance, narrowed);
~~~

The `setInt` call on the last line cannot recover information lost during the `(int) huge` cast. For business logic requiring safe conversion, you can check beforehand with `Math.toIntExact(huge)`; this method throws `ArithmeticException` if the `long` is outside the `int` range.

## 7. Runtime errors: value type, access permission, and receiver object

`IllegalArgumentException` from a setter usually indicates **incompatible types**, though not every reflection error is caused by widening.

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `IllegalArgumentException` with `setInt` or `setLong` | Field type does not allow identity/widening from `int`/`long` | Print `field.getType()`, consult the table in section 2 |
| `IllegalArgumentException` even though field has a compatible type | `obj` is not a valid instance of the field's declaring type | Compare `field.getDeclaringClass()` and the receiver's actual type |
| `NullPointerException` | Passing `null` for an instance field | Provide an instance; pass `null` only for static |
| `IllegalAccessException` | Field cannot be written due to access checks, or no write permission on `final` field | Inspect modifiers, package, module, and write policy |
| `NoSuchFieldException` | Wrong field name, or `getField` only finds eligible public fields | Verify the name; use `getDeclaredField` for directly declared non-public fields |
| `ExceptionInInitializerError` | Operating on a `static` field triggers class initialization and initialization fails | Inspect the cause of class initialization failure |

For **private fields**, obtaining a `Field` from `getDeclaredField` does not automatically open write permission. Calling `setAccessible(true)` or `trySetAccessible()` can only suppress certain permission checks when JPMS allows; they **do not** turn narrowing into widening.

For **final fields**, beyond access checks, the API imposes strict write restrictions; some forms of final fields are always non-writable through this mechanism, even after disabling access checks. Do not use reflection to modify constants or internal invariants. In the illustrative program, writable fields are declared non-final.

For `static` fields, the `obj` parameter is ignored for identifying an instance, though you should pass `null` for readability and to avoid creating dummy objects. Writing a static field can trigger class initialization if not yet initialized.

## 8. How to choose the API when the Field type is only known at runtime

If writing a configuration assigner, data mapper, or reflection tests, distinguish the target type from the start:

~~~java
Class<?> targetType = field.getType();

if (targetType == int.class) {
    field.setInt(receiver, intValue);
} else if (targetType == long.class) {
    field.setLong(receiver, longValue);
} else {
    // Handle other types according to the data contract;
    // do not assume all numeric types are compatible.
}
~~~

This is **illustrative code**: it assumes `field`, `receiver`, `intValue`, `longValue`, and proper exception handling already exist. The sample logic checks **the exact target type**, suitable when each source has already been validated. If you want an `int` source to write to `long`, `float`, or `double`, expand the branches explicitly and decide on a precision policy; if you want a `long` to write to `int`, range checks and an explicit conversion are mandatory.

A safe workflow:

1. **Identify the target:** retrieve `field.getType()`, `getModifiers()`, and `getDeclaringClass()`; distinguish primitive from wrapper and instance from static.
2. **Identify the source:** is it an `int`, a `long`, or an actual wrapper object? For text data, parse according to contract instead of guessing.
3. **Decide conversion:** use only allowed identity/widening, while evaluating whether rounding when moving to `float`/`double` is acceptable.
4. **Check write permission:** is the field public, private, or final? Does the caller have proper reflection rights? Minimize bypassing access checks.
5. **Execute and handle errors:** use the right setter, and log type errors separately from access permission errors so the root cause can be addressed.

When building JSON mapping, ORM, or mapper frameworks, the type compatibility strategy can be broader than `Field.setInt`'s mechanism. For instance, a business converter can parse the string `"42"` or convert `long` to `int` after range checking. That is an **application-authored conversion layer**, not a feature provided by `setInt` itself.

## 9. Practice exercises and answers

**Exercise 1.** Field `public long total`. Predict whether `setInt(obj, -5)` and `setLong(obj, -5L)` are allowed.

**Answer:** Both are valid. `int -> long` is widening, `long -> long` is identity; the value `-5` is preserved.

**Exercise 2.** Field `public short age`. Will `setInt(obj, 12)` succeed because `12` is within the `short` range? If not, what should be done?

**Answer:** No, it throws `IllegalArgumentException`. Use `setShort(obj, (short) 12)` after ensuring the input value's range, or convert with range checks at the business layer.

**Exercise 3.** Field `public int count`. Is `setLong(obj, 3)` valid? How does it differ from `setInt(obj, 3)`?

**Answer:** `setLong(obj, 3)` still compiles because the literal is widened to the `long` parameter, yet the setter throws `IllegalArgumentException` since the target field is `int`. `setInt(obj, 3)` succeeds.

**Exercise 4.** Field `public double amount`. Can you call `setLong(obj, 9_007_199_254_740_993L)`? Is the read-back value guaranteed exact?

**Answer:** The call is valid because `long -> double` is widening, but the value will be rounded in this example; preserving all integer bits is not guaranteed.

**Exercise 5.** Field `public Integer boxed`. Which method is appropriate between `setInt(obj, 42)` and `set(obj, Integer.valueOf(42))`?

**Answer:** Use `set(obj, Integer.valueOf(42))` to assign the reference. `setInt` is specialized for primitive fields, so it cannot directly assign a field declared as `Integer`.

**Exercise 6.** Field `public int n`. Why does `getLong(obj)` succeed while `setLong(obj, 5L)` fails?

**Answer:** The getter converts **field type `int` → return type `long`**, which is widening. The setter converts **parameter type `long` → field type `int`**, which is narrowing. The conversion directions differ.

**Exercise 7.** Use `getDeclaredField("count")` to get a private `int` field, then call `setLong(obj, 5L)` after `trySetAccessible()` succeeds. Will it write?

**Answer:** Still no, because opening access only handles language access checks; `long -> int` is still narrowing rejected by `Field.setLong`. You must choose the appropriate input type and method.

## 10. Takeaways and reference documentation

**Core rule:** `Field.setInt` only writes to primitive fields `int`, `long`, `float`, `double`; `Field.setLong` only writes to `long`, `float`, `double`. Runtime checks **the direction from the setter parameter type to the field type**, not whether the value "fits" in a smaller type. Widening to floating-point sometimes loses precision yet remains valid. Access permissions, `final`, and the receiver object are additional conditions independent of conversion kind.

Standard references:

- [`java.lang.reflect.Field` — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html): `setInt`, `setLong`, `set(Object,Object)`, `getInt`, and `getLong` methods.
- [Java Language Specification `5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-5.html#jls-5.1.2): widening directions and precision rules.