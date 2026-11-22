# Why Doesn't Reflection Automatically Narrow or Convert String to a Number?

## 1. The problem: Reflection invokes methods, it is not an arbitrary data converter

In Java Reflection, calling `Method.invoke(receiver, args...)` must pass arguments compatible with the **declared parameter types** of the target method. Reflection supports a specific set of conversions, consisting of **unboxing** from the corresponding wrapper and permitted **widening primitive conversion**. It **does not automatically perform narrowing primitive conversion** (e.g., `long → int` or `int → short`) and **does not parse `String` into numbers** (e.g., `"42" → 42`).

For example, if the target method has the signature:

~~~java
public static int doubleIt(int number) {
    return number * 2;
}
~~~

then `Method.invoke(null, Integer.valueOf(7))` can invoke the method with an `int` parameter by unboxing `Integer`; `Method.invoke(null, Byte.valueOf((byte) 7))` can also invoke it by unboxing `byte` and widening `byte → int`. However, passing `Long.valueOf(7L)` or `"7"` to an `int` parameter will not automatically convert to an integer; the call fails with `IllegalArgumentException`.

This is a **type-checking design**, avoiding guessing values or arbitrarily performing conversions that could cause data loss, alter meaning, or depend on string formatting.

## 2. Which conversions does Java allow during `Method.invoke()`?

Reflection signature:

~~~java
Object Method.invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
~~~

At runtime, arguments passed to `Object... args` are references: when writing `method.invoke(null, 7)`, the Java compiler boxes the literal `7` into `Integer` to pass via varargs. Reflection then matches the **runtime value** against the target method's parameter type.

For **primitive** parameters, Reflection can unbox from an appropriate wrapper and then widen the primitive if needed. It does not narrow primitive values. For **reference** parameters, the value must be compatible in the reference type relationship; Reflection does not automatically "turn" an `Integer` into a `Long` wrapper and does not convert digit strings into any numeric type.

| Target parameter | Value passed to `invoke()` | Result | Reason |
| --- | --- | --- | --- |
| `int` | `Integer.valueOf(7)` | Allowed | Unboxing `Integer → int`. |
| `int` | `Byte.valueOf((byte) 7)` | Allowed | Unbox `Byte → byte`, widening `byte → int`. |
| `int` | `Character.valueOf('A')` | Allowed | Unbox `char`, widening `char → int` (UTF-16 Unicode code of `'A'` is 65). |
| `long` | `Integer.valueOf(7)` | Allowed | Unbox `int`, widening `int → long`. |
| `int` | `Long.valueOf(7L)` | **Not allowed** | Requires narrowing `long → int`. |
| `short` | `Integer.valueOf(7)` | **Not allowed** | Requires narrowing `int → short`, even though 7 is representable as a short. |
| `int` | `"7"` | **Not allowed** | `String` is not a numeric wrapper; no automatic parsing. |
| `int` | `null` | **Not allowed** | Cannot unbox `null` to a primitive. |
| `Long` (reference) | `Integer.valueOf(7)` | **Not allowed** | `Integer` is not a subtype of `Long`; no automatic unbox–widen–rebox. |
| `Number` (reference) | `Integer.valueOf(7)` | Allowed | `Integer extends Number`: widening reference. |
| `String` | `"7"` | Allowed | Already a `String`, no type conversion needed. |

With widening, **numeric precision** can be lost in some conversions (for example, `long → float`); "widening" describes a type/representation-range relationship, **not a promise that every value is preserved bit-for-bit**. The key point is that Java has predefined widening rules, whereas narrowing requires an explicit decision from the author.

## 3. Standalone Java 17+ example: success and failure cases

Create the file `ReflectionConversionDemo.java`:

~~~java
import java.lang.reflect.Method;

public class ReflectionConversionDemo {
    public static int acceptInt(int n) {
        return n * 2;
    }

    public static short acceptShort(short n) {
        return n;
    }

    public static long acceptLong(long n) {
        return n + 1;
    }

    private static void test(String label, Method method, Object arg)
            throws Exception {
        try {
            System.out.println(label + " => " + method.invoke(null, arg));
        } catch (IllegalArgumentException e) {
            System.out.println(label + " => " + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Method intMethod =
                ReflectionConversionDemo.class.getMethod("acceptInt", int.class);
        Method shortMethod =
                ReflectionConversionDemo.class.getMethod("acceptShort", short.class);
        Method longMethod =
                ReflectionConversionDemo.class.getMethod("acceptLong", long.class);

        test("Integer -> int", intMethod, Integer.valueOf(7));
        test("Byte -> int", intMethod, Byte.valueOf((byte) 3));
        test("Character -> int", intMethod, Character.valueOf('A'));
        test("Integer -> long", longMethod, Integer.valueOf(7));
        test("Long -> int", intMethod, Long.valueOf(7));
        test("Integer -> short", shortMethod, Integer.valueOf(7));
        test("String -> int", intMethod, "7");
        test("null -> int", intMethod, null);
        test("explicit parse", intMethod, Integer.parseInt("7"));
        test("explicit narrow", shortMethod, (short) 7);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ReflectionConversionDemo.java
java ReflectionConversionDemo
~~~

Stdout, executed and verified with a Java 17-compatible JDK compiler:

~~~text
Integer -> int => 14
Byte -> int => 6
Character -> int => 130
Integer -> long => 8
Long -> int => IllegalArgumentException
Integer -> short => IllegalArgumentException
String -> int => IllegalArgumentException
null -> int => IllegalArgumentException
explicit parse => 14
explicit narrow => 7
~~~

**How to read the program:**

- `getMethod("acceptInt", int.class)` looks up the **declared signature**, without calling the method; the expected type is `int.class`.
- `test(...)` accepts `Object arg`; at `method.invoke(null, arg)`, Reflection checks the **runtime type of arg**. For instance, `Byte.valueOf((byte) 3)` carries source primitive `byte` when unboxed, which can widen to `int`; `acceptInt(3)` returns `6`.
- `Character.valueOf('A')` unboxes to `char`; widening to `int` produces `65`; the method doubles it and returns `130`. This processes the character code, **not string parsing**.
- `Long.valueOf(7)` is rejected for `int` even though `7L` is small enough to fit in `int`. Reflection does not automatically narrow by value.
- `"7"` is a `String`. Reflection does not know whether the author wants base 10, base 16, how to handle whitespace, negative numbers, or input errors, so it must be parsed before invoking.
- `null` cannot become primitive `int`; the example catches `IllegalArgumentException` from passing an invalid argument.
- `Integer.parseInt("7")` performs conversion with **explicit parsing rules** before the call; the resulting `int 7` passed into `Object...` is boxed into `Integer` and then unboxed by Reflection on invocation.
- `(short) 7` is an explicit narrowing in Java source; after boxing to `Short`, Reflection can invoke `acceptShort(short)`. Note that casting out-of-range numbers can cause data loss.

## 4. Why doesn't `String` automatically become a number?

Strings only store **characters**. User input, CSV lines, HTTP parameters, and JSON content can contain values like `"15"`, `" 15 "`, `"1,500"`, `"0xFF"`, `""`, or `"abc"`. Whether they have numeric meaning depends on data conventions:

- `"15"` can be parsed in base 10 to `15`.
- `" 15 "` requires deciding whether to `trim()` or `strip()` first; plain `Integer.parseInt` does not accept leading/trailing spaces.
- `"1,500"` could mean one thousand five hundred or one point five depending on locale; Reflection cannot guess.
- `"0xFF"` might be intended as base 16, while `Integer.parseInt(text)` defaults to base 10; base 16 requires specifying the appropriate handling.
- `"abc"` or out-of-range `int` values must be handled as invalid data.

Reflection is not a parser or data-binding framework. To call a method accepting `int`, your code must have an explicitly chosen **rule for converting String to int**:

~~~java
String input = " 42 ";
int parsed = Integer.parseInt(input.strip());
Object result = intMethod.invoke(null, parsed);
~~~

This snippet depends on the `intMethod` variable from section 3 and is not a standalone program. `parsed` is an `int`; when passed into `invoke`'s `Object...`, the compiler boxes it and Reflection automatically unboxes it per the API. The result of `acceptInt` will be `Integer(84)`.

Common parsing APIs:

| Type to produce | Explicit conversion example | Invalid data |
| --- | --- | --- |
| `int` | `Integer.parseInt(text)` | `NumberFormatException` |
| `long` | `Long.parseLong(text)` | `NumberFormatException` |
| `double` | `Double.parseDouble(text)` | `NumberFormatException` for invalid syntax; special values like `NaN` exist if syntax supports them. |
| `BigDecimal` | `new BigDecimal(text)` | `NumberFormatException`; better suited than binary floating-point when exact decimal representation is needed. |
| `short` | `Short.parseShort(text)` | `NumberFormatException` if unparseable or outside `short` range. |

For locale-sensitive data, use an appropriate parser like `NumberFormat` and manage `ParsePosition`/check that the entire string was consumed if strictness is required. Do not call `Double.parseDouble` and cast to `int` to parse identifiers or integers: there is a risk of losing fractional parts and overflowing the range.

## 5. When narrowing is mandatory, decide explicitly about data loss

Narrowing primitive conversion is converting to a type with a smaller representation range, for example:

~~~java
long source = 3_000_000_000L;
int narrowed = (int) source; // May lose data
~~~

The cast syntax above is valid in Java source, but the result does not necessarily equal the original value. If you want to **reject overflow** instead of losing data, use:

~~~java
long source = 3_000_000_000L;
int safe = Math.toIntExact(source); // Throws ArithmeticException if outside int range
~~~

For a value genuinely in range, such as `long source = 7L;`, `Math.toIntExact(source)` returns `int 7`; passing this `int` to a method with an `int` parameter is valid.

Consider two approaches:

- **Intentional data-loss acceptance:** use a cast `(int) someLong`, `(short) someInt` per data design and document the limits.
- **No data loss accepted:** check the range with `Math.toIntExact` or the condition `Short.MIN_VALUE <= n && n <= Short.MAX_VALUE` before casting.

Reflection cannot choose between these two policies for you; the caller must decide before passing arguments to `invoke()`.

## 6. Safe data conversion workflow before calling Reflection

When building a system that reads config, CLI, HTTP requests, or CSV and invokes methods dynamically:

1. **Identify signature:** Use `Method.getParameterTypes()` or `getGenericParameterTypes()` when generics are present; clearly understand whether the method expects `int`, `Long`, `String`, or another type.
2. **Define input schema:** Know the format, locale, nullability, range limits, units, and error reporting. Do not infer numeric types solely from display strings.
3. **Parse if data is text:** Use the right parser for the type. Handle `NumberFormatException`, empty strings, whitespace, overflow, and invalid values.
4. **Convert numbers explicitly when narrowing is needed:** Consider intentional casting or range checking with an appropriate function/condition. Do not pass `Long` into `int` hoping Reflection will handle it automatically.
5. **Check null and reference types:** Primitives do not accept null; references can accept null if the method's logic allows it. There is no "valid conversion to null" for primitives.
6. **Only then call `invoke(...)`:** Pass the right receiver and arguments in order. Handle `IllegalArgumentException` for argument errors; `InvocationTargetException.getCause()` for errors thrown by the target method.

Example of handling a numeric string before calling a method accepting `int`:

~~~java
static Object invokeIntFromText(Method method, Object target, String text)
        throws ReflectiveOperationException {
    int value = Integer.parseInt(text.strip());
    return method.invoke(target, value);
}
~~~

This is an **illustrative method** that must be placed in a class importing `java.lang.reflect.Method`. It is intended for situations where it is known for certain that the target method takes exactly one `int`. `Integer.parseInt` can throw `NumberFormatException` (unchecked) on bad input; the signature above does not replace validation at system boundaries. For other target types, an appropriate parser/converter must be chosen.

## 7. Self-practice and verification

1. Does `acceptInt(int)` accept `Short.valueOf((short) 4)` via Reflection? Predict the output if the method logic doubles it.
2. Does `acceptInt(int)` accept `Float.valueOf(4.0f)`? Even though the value equals an integer, what is the reason for rejection?
3. With `acceptLong(long)`, is there a difference between passing `Long.valueOf(9)` and `Integer.valueOf(9)`? Which case requires widening?
4. If the text data is `" 2147483648 "` and the target is `int`, what must be handled besides `strip()`? Should you cast directly from `long`?
5. If the target is a `Long` reference (not primitive `long`), why does passing `Integer.valueOf(9)` not work?
6. Modify the code in section 3 so that after `Long -> int` is rejected, it uses `Math.toIntExact(7L)` and calls it again. Explain why the argument is now compatible.

**Takeaway:** Reflection enforces **well-defined conversion rules**: it accepts appropriate unboxing and widening, but **does not guess String parsing, does not automatically narrow, and does not arbitrarily convert one wrapper to another**. The caller is responsible for choosing how to convert and validating input before invoking.

## Official references

- [Java SE 17 — `Method.invoke()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Java SE 17 — `Constructor.newInstance()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...))
- [Java SE 17 — `Field.set()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object))
- [Java Language Specification §5.1 — Kinds of Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1)
- [Java Language Specification §5.3 — Method Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3)