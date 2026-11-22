# Mapping boolean, byte, char, integers, and floating-point numbers to JNI types

## Objectives

When a Java method is declared `native`, the JVM needs to pass **primitive values** across the Java ↔ native code boundary according to the Java Native Interface (JNI). To declare C/C++ functions and call JNI APIs correctly, three things must be distinguished:

1. **The type in the Java declaration**, for example `boolean`, `byte`, `char`, `long`.
2. **The corresponding JNI type on the C/C++ side**, for example `jboolean`, `jbyte`, `jchar`, `jlong`. These are typedefs specified by JNI and shipped with the `jni.h` header.
3. **The symbol in the JNI type descriptor (type signature)**, for example `Z`, `B`, `C`, `J`. A descriptor encodes the type for the JVM; it is not a C type name and not a command string for casting.

After completing this, you will know how to read the mapping table, define native function signatures correctly, identify signedness and numeric width, handle UTF-16 characters, avoid precision loss when converting floating-point numbers, and verify the results with a runnable Java/JNI program.

## 1. Standard mapping table: eight primitives and `void`

| Java type | JNI type in C/C++ | Size/logical meaning | JNI descriptor | Important notes |
| --- | --- | --- | --- | --- |
| `boolean` | `jboolean` | False/true value; unsigned 8-bit JNI representation | `Z` | Use `JNI_FALSE` (0), `JNI_TRUE` (1); do not assume C `bool`/`int` has the same ABI |
| `byte` | `jbyte` | 8-bit signed integer: -128 to 127 | `B` | A byte with bit pattern `0xFF` has the value `-1` when interpreted as `jbyte` |
| `char` | `jchar` | An unsigned 16-bit **UTF-16 code unit**: 0 to 65535 | `C` | Not equivalent to C `char` or `wchar_t` |
| `short` | `jshort` | 16-bit signed integer | `S` | -32768 to 32767 |
| `int` | `jint` | 32-bit signed integer | `I` | -2³¹ to 2³¹ - 1 |
| `long` | `jlong` | 64-bit signed integer | `J` | Do not substitute with C `long` without proving the ABI |
| `float` | `jfloat` | 32-bit IEEE 754 binary32 floating-point number | `F` | Has NaN, ±Infinity, +0.0, and -0.0 |
| `double` | `jdouble` | 64-bit IEEE 754 binary64 floating-point number | `D` | More digits of precision than `float` but still an approximate binary number |
| `void` (return type) | C/C++ `void` | Returns no value | `V` | `V` is only valid as the return type of a method descriptor, not as a Java parameter |

**This is a type mapping, not an arbitrary cast.** When defining a JNI entry point, use the exact `j...` types from the header provided by the JDK. `jni.h` and `jni_md.h` will select the appropriate C declarations for the platform to preserve the required width and calling convention. For example, Java `long` is always 64 bits, whereas C `long` can be 32 bits wide on 64-bit Windows; `jlong` is the compatible name to use.

Conversely, `jint` differs from `jobject`: primitives are passed **by value**, whereas `String`, arrays, and Java instances are represented in JNI by **reference handles** such as `jstring`, `jbyteArray`, and `jobject`. You must not interpret `jbyteArray` as a C pointer pointing directly to a sequence of `jbyte`.

## 2. Why are JNI types needed instead of C `int`, `long`, `char`?

JNI is a contract between the JVM and native code that can run across many operating systems, CPU architectures, C compilers, and C data models:

- C `char` is usually 8 bits wide, and can be signed or unsigned depending on the compiler; `jchar` holds an exact **unsigned 16-bit** UTF-16 code unit.
- C `long` does not have a fixed width across all ABIs: LP64 typically has a 64-bit `long`, while LLP64 typically has a 32-bit `long`. Java `long` and `jlong` are **64-bit signed** types.
- C `bool`/`_Bool` is a logical type of the C language; `jboolean` is a JNI type with a representation and API convention defined by JNI.
- C `float`/`double` usually correspond to the JNI `jfloat`/`jdouble` storage layout on supported Java platforms, but the native declaration must still use `jfloat` and `jdouble` to match the interface exported by `jni.h`.

Do not use custom `typedef`s based on `sizeof(long)` or the current machine's width to replace `jint`/`jlong`. For example, a JNI prototype starts with `JNIEXPORT jlong JNICALL`, not an unverified choice like `long WINAPI` or `long long`. The `JNIEXPORT` macro ensures the symbol has the appropriate visibility; `JNICALL` uses the calling convention required by JNI on that platform.

**Important note on endianness:** when the JVM calls a JNI method with `jint`/`jlong` parameters, the C side receives the **numeric value** according to the ABI; normally you do not need to manually swap bytes because the CPU is little-endian or big-endian. Endianness becomes an issue when application code reads/writes **raw bytes**, casts pointers, or communicates over network/file protocols. Do not mix these two layers.

## 3. Boolean: `boolean` ↔ `jboolean`

A `boolean` in Java only represents `true` or `false`. JNI defines two constants:

~~~c
JNI_FALSE  /* 0 */
JNI_TRUE   /* 1 */
~~~

Example of safe handling in a JNI function:

~~~c
JNIEXPORT jboolean JNICALL Java_Example_isPositive(
        JNIEnv *env, jclass cls, jint value) {
    (void) env;
    (void) cls;
    return value > 0 ? JNI_TRUE : JNI_FALSE;
}
~~~

This is an **illustrative native function snippet**, not a standalone C program. It requires `jni.h`, a matching Java native declaration, and the header generated by `javac -h`. The first parameter is `JNIEnv *` (the interface for calling JVM services), and the second parameter is `jclass` because the example method is `static native`. Java primitive parameters start from the third parameter.

Notes:

- `jboolean` is not `jint`. Do not declare Java `boolean` as C `int` even if simple tests sometimes appear to work.
- When **returning** to Java, normalize to `JNI_TRUE` or `JNI_FALSE`. Do not pass an arbitrary number or a high byte value directly and assume every JVM will interpret it the same way.
- A `boolean[]` array corresponds to `jbooleanArray`, not `jboolean *`. You need to call the JNI array APIs to access elements when needed.

## 4. Byte: `byte` ↔ `jbyte`, signedness, and binary data

Java `byte` and JNI `jbyte` are both signed, ranging from -128 to 127. If the actual data is an octet with values 0..255, you can still keep the eight bits in `byte`; only the **arithmetic interpretation** changes.

~~~java
byte raw = (byte) 0xFE;
System.out.println(raw);           // -2
System.out.println(raw & 0xFF);    // 254
~~~

In C, when receiving `jbyte raw`, you can obtain the unsigned value by widening to `jint` and masking:

~~~c
jint unsigned_value = ((jint) raw) & 0xFF;
~~~

Both approaches above produce `254` from the bit pattern `0xFE`. Do not perform arithmetic on `jbyte` as if it were always an unsigned number; promotion to a larger integer type preserves the sign of the original value. For protocol codes, checksums, and binary structures, you must determine the exact signed/unsigned requirements.

If Java has `byte[]`, JNI receives the **`jbyteArray`** type; a Java array is an object managed by the JVM. To read or write its contents, use APIs such as `GetByteArrayRegion`, `SetByteArrayRegion`, or the `GetByteArrayElements`/`ReleaseByteArrayElements` pair, while respecting length and lifetime. **Do not cast `jbyteArray` directly to `jbyte *`.**

## 5. Char: `char` ↔ `jchar` is a UTF-16 code unit, not a C byte

Java `char` and JNI `jchar` are **16-bit unsigned** numbers. They hold **one UTF-16 code unit**, which is not necessarily equivalent to a complete Unicode character and should not be automatically treated as ASCII.

Examples:

- `'A'` has the UTF-16 value `0x0041` (65).
- `'中'` has the value `0x4E2D` (20013), exceeding the limit of one byte.
- A Unicode character outside the Basic Multilingual Plane (BMP), such as U+1F642, is encoded using **two UTF-16 code units (a surrogate pair)**, so it cannot fit inside a single `char`/`jchar`.

~~~java
char han = '中';
String smile = new String(Character.toChars(0x1F642));

System.out.println((int) han);       // 20013
System.out.println(smile.length());  // 2 UTF-16 code units
System.out.println(smile.codePointCount(0, smile.length())); // 1 code point
~~~

On the C side:

~~~c
jchar unit = /* jchar parameter received from Java */;
jint numeric_value = (jint) unit; /* 0..65535 */
~~~

The C snippet above only illustrates variable types inside a native method. In an actual program, `unit` is a parameter passed by the JVM or read from a `jcharArray`.

**Three common misconceptions:**

1. `jchar` **differs from C `char`**: casting to C `char` can lose the high bits.
2. `jchar` **differs from `wchar_t`**: `wchar_t` has a platform-dependent width and usage (for example, 16 or 32 bits). Do not directly use a `wchar_t *` pointer as `jchar *`.
3. `jchar` **differs from a Unicode code point**: a lone surrogate is a valid code unit at the UTF-16 representation level; to process text by code points, surrogate pairs must be considered.

When passing an entire string through JNI, `String` is represented by `jstring`. `GetStringChars` provides the UTF-16 `jchar`s after retrieving them via the JNI API; `GetStringUTFChars` uses JNI's **Modified UTF-8**, not standard UTF-8. Do not infer that `String` is an array of `jchar` solely from the type name.

## 6. Integers: `short`, `int`, `long` and fixed widths

The standard pairs are:

~~~text
Java short  -> jshort : 16-bit signed
Java int    -> jint   : 32-bit signed
Java long   -> jlong  : 64-bit signed
~~~

C++ does not automatically treat Java `long` as identical to C++ `long` on every platform. A Java method `native long getCounter()` must return **`jlong`**. If an underlying C library uses the `long` type, the conversion must be based on the actual value range, type limits, and ABI.

Example:

~~~java
long big = 5_000_000_000L;
int narrow = (int) big;
System.out.println(big);    // 5000000000
System.out.println(narrow); // 705032704
~~~

Java allows explicit casting from `long` to `int`; the result keeps the lower 32 bits, so the number loses value. This is solely **the behavior of the cast operator in Java**. When C converts from a larger integer type to a smaller signed integer type, an out-of-range result is subject to C/implementation-defined conversion rules and must not be assumed to match Java. Therefore, you should **check the value range before casting**.

For example, if a C function needs to narrow a positive `jlong` to `jint`:

~~~c
#include <stdint.h> /* INT32_MAX, INT32_MIN are usually in <stdint.h> */

int fits_in_jint(jlong value) {
    return value >= (-2147483647LL - 1LL)
        && value <= 2147483647LL;
}
~~~

The function above is an illustrative C helper; it is not a JNI entry point. Once confirmed to be within [-2³¹, 2³¹-1], it can be cast to `jint` without changing the value. When writing portable code for multiple native types, you can use `INT32_MIN`/`INT32_MAX` from `<stdint.h>` on environments supporting 32-bit types, but do not equate the limits of `size_t` or `long` with the limits of `jint`.

**Unsigned cases:** Java primitives do not have separate `unsigned int`/`unsigned long` types like C. When a native API uses `uint32_t` or `uint64_t`, agree on the type and how to interpret bit patterns, comparisons, stringification, and value ranges. Java provides unsigned operations such as `Integer.toUnsignedLong`, `Integer.compareUnsigned`, and `Long.compareUnsigned`. JNI `jint`/`jlong` remain signed types; the interface specification must clearly state how values exceeding the signed threshold are handled.

## 7. Floating-point numbers: `float` ↔ `jfloat`, `double` ↔ `jdouble`

`jfloat` and `jdouble` represent the two IEEE 754 floating-point formats in Java: **binary32 (32-bit)** and **binary64 (64-bit)**. These are not exact decimal representations for all values.

~~~java
float a = 0.1f;
double b = 0.1;

System.out.println(a == (float) b); // true
System.out.println((double) a == b); // false
System.out.println(Float.floatToRawIntBits(1.5f) == 0x3FC00000); // true
System.out.println(Double.doubleToRawLongBits(1.5) == 0x3FF8000000000000L); // true
~~~

`0.1f` is rounded to binary32, and `0.1` is rounded to binary64. Comparing `a == (float)b` evaluates to true because casting `b` to float produces the same binary32 value, whereas widening `a` to double cannot recover the lost precision.

JNI allows passing ±Infinity, NaN, and ±0.0 values through `jfloat`/`jdouble` parameters. When implementing in C:

- Do not assume that adding/subtracting/multiplying/dividing two floating-point numbers will equal an exact desired decimal result; decide the error tolerance policy based on the problem.
- `NaN` is not equal to itself: `NaN == NaN` is false. If handling sensitive parameters, check `isnan`/`isfinite` using C `<math.h>` on an appropriate platform.
- `+0.0` and `-0.0` compare numerically equal, but have different sign bits; operations such as division can distinguish them.
- `float` to `double` preserves the exact current binary32 value; it **does not recover** the decimal number prior to rounding.
- Casting NaN/infinite or overly large floating-point numbers to an integer in C may not behave like a Java cast; you must check the value range and error policy. The example in the JNI section only casts small, finite values within the `jlong` range.
- Do not arbitrarily replace a `jfloat` parameter with `jdouble` even though C has integer/floating promotion rules in some contexts. The JNI signature of the native method must match the Java declaration's types.

If native code handles exact currency, you usually need an **integer unit** model (for example, cents) or an agreed-upon decimal representation instead of expecting `float`/`double` to store every monetary amount accurately.

## 8. Method descriptors: Java type names mapped to `Z B C S I J F D`

A JNI method descriptor has the form:

~~~text
(parameter_type_1 parameter_type_2 ...)return_type
~~~

Do not put commas or spaces between descriptors in the actual string. For example:

~~~java
static native long total(boolean enabled,
                         byte octet,
                         char unit,
                         short small,
                         int number,
                         long big,
                         float decimal32,
                         double decimal64);
~~~

The descriptor for this exact method is:

~~~text
(ZBCSIJFD)J
~~~

Reading from left to right: `Z` = boolean, `B` = byte, `C` = char, `S` = short, `I` = int, `J` = long, `F` = float, `D` = double; outside the `)` is `J` = long return type.

Some standalone examples to practice reading:

| Java method declaration | JVM/JNI descriptor | Explanation |
| --- | --- | --- |
| `native boolean ready();` | `()Z` | No parameters, returns boolean |
| `native void set(byte x, short y);` | `(BS)V` | Byte and short, no return value |
| `native char upper(char x);` | `(C)C` | Char in/char out |
| `native double average(int n, double x);` | `(ID)D` | Int and double, returns double |
| `native long tick(long delta);` | `(J)J` | Long in/long out |

Array and reference types help distinguish context:

~~~text
byte[]                   [B
char[]                   [C
boolean[]                [Z
int[][]                  [[I
java.lang.String         Ljava/lang/String;
(byte[], String) -> void ([BLjava/lang/String;)V
~~~

A `[` adds one array dimension; an object type has the form `L<internal-class-name>;`, with `/` between package segments. The `V` symbol is only used for the return type. Java `String` does not have descriptor `C` and `byte[]` does not have descriptor `B`: those types are **references**, not scalar primitives.

To verify the actual descriptor from a compiled class, use:

~~~bash
javap -p -s PrimitiveBridge
~~~

This command prints the method information along with the line `descriptor: (ZBCSIJFD)J` for the `total` method in the complete example below. `javap` does not need the native library to be loaded to read the bytecode.

## 9. JNI entry point: hidden parameters, order, and return type

A `static native` declaration like the one above is implemented on the C side with the prototype (the exact class name in the example section is `PrimitiveBridge`):

~~~c
JNIEXPORT jlong JNICALL Java_PrimitiveBridge_total(
    JNIEnv *env,
    jclass cls,
    jboolean enabled,
    jbyte octet,
    jchar unit,
    jshort small,
    jint number,
    jlong big,
    jfloat decimal32,
    jdouble decimal64);
~~~

In an instance method (non-`static`), the position after `JNIEnv *` is `jobject receiver` instead of `jclass cls`. **These first two parameters are not in the Java method descriptor**; they are supplied by the JVM when calling the JNI entry point. The subsequent primitive values appear in **the exact order declared in Java**.

Rules:

1. Use `JNIEXPORT <return-jni-type> JNICALL` on the function definition.
2. Put `JNIEnv *` first; the second parameter is `jobject`/`jclass` depending on whether the method is instance/static.
3. Use the exact eight JNI primitive types; do not substitute C types guessed by name (`char`, `long`, `bool`).
4. The C signature of the native function and the Java declaration must be compatible; a mismatched calling convention, missing parameters, or wrong width can cause nonsensical results or process crashes.
5. Use `javac -h` to **generate the header** instead of guessing symbol names manually, especially when packages, method overloads, or characters requiring encoding in JNI name mangling are involved.

For a native method declared as `native void update(int x)`, the C entry point has return type `void`, argument `jint`, and method descriptor `(I)V`. There is **no** `jvoid` type for the return value.

## 10. Standalone Java 17+ example: observing values and bit patterns

Create the file `PrimitiveTypesOnly.java`, with no native library needed:

~~~java
public final class PrimitiveTypesOnly {
    public static void main(String[] args) {
        byte octet = (byte) 0xFE;
        char unit = '中';
        short small = -12345;
        int number = 2_000_000_000;
        long big = 5_000_000_000L;
        float decimal32 = 1.5f;
        double decimal64 = 1.5;

        System.out.println("byte=" + octet + ", unsigned=" + (octet & 0xFF));
        System.out.println("charCodeUnit=" + (int) unit);
        System.out.println("short=" + small + ", int=" + number);
        System.out.println("long=" + big);
        System.out.println("floatBits=" +
                Integer.toHexString(Float.floatToRawIntBits(decimal32)));
        System.out.println("doubleBits=" +
                Long.toHexString(Double.doubleToRawLongBits(decimal64)));
        System.out.println("supplementaryUnits=" +
                Character.charCount(0x1F642));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 PrimitiveTypesOnly.java
java PrimitiveTypesOnly
~~~

Exact stdout:

~~~text
byte=-2, unsigned=254
charCodeUnit=20013
short=-12345, int=2000000000
long=5000000000
floatBits=3fc00000
doubleBits=3ff8000000000000
supplementaryUnits=2
~~~

This is the **Java data-inspection part**, used to understand the exact values that JNI will receive. `0xFE` in a Java byte displays -2, while the Java char `中` is a code unit 20013; the bit patterns of the two `1.5` floating-point numbers show the binary32/binary64 widths.

## 11. Complete JNI example: eight primitives entering C

This example shows how to declare the signature, receive all C/JNI types, return a `jlong` result, and recover an unsigned value from `jbyte`. The calculations use small, finite values to avoid overflow or out-of-range conversions; this is a **type-mapping exercise**, not a production summation algorithm.

### 11.1. Java file `PrimitiveBridge.java`

~~~java
public final class PrimitiveBridge {
    static {
        System.loadLibrary("primitivebridge");
    }

    private static native long total(
            boolean enabled, byte octet, char unit, short small,
            int number, long big, float decimal32, double decimal64);

    private static native int unsignedByte(byte value);

    public static void main(String[] args) {
        long result = total(true, (byte) -2, 'A', (short) 1000,
                200_000, 3_000_000_000L, 1.5f, 2.5);
        System.out.println("total=" + result);
        System.out.println("unsignedByte=" + unsignedByte((byte) 0xFE));
    }
}
~~~

### 11.2. C file `PrimitiveBridge.c`

~~~c
#include <jni.h>
#include "PrimitiveBridge.h" /* generated by javac -h . */

JNIEXPORT jlong JNICALL Java_PrimitiveBridge_total(
        JNIEnv *env, jclass cls,
        jboolean enabled, jbyte octet, jchar unit, jshort small,
        jint number, jlong big, jfloat decimal32, jdouble decimal64) {
    (void) env;
    (void) cls;

    return (enabled == JNI_TRUE ? 1 : 0)
         + (jlong) octet
         + (jlong) unit
         + (jlong) small
         + (jlong) number
         + big
         + (jlong) decimal32
         + (jlong) decimal64;
}

JNIEXPORT jint JNICALL Java_PrimitiveBridge_unsignedByte(
        JNIEnv *env, jclass cls, jbyte value) {
    (void) env;
    (void) cls;
    return ((jint) value) & 0xFF;
}
~~~

The `total` function receives the parameters in the exact Java order. The `enabled` value is normalized by comparing with `JNI_TRUE`. The additions are promoted to `jlong` before computing with the integers in the example, helping preserve results larger than the `jint` range. Casting `jfloat 1.5f` and `jdouble 2.5` to `jlong` takes the integer part, 1 and 2 respectively. Do not apply this cast to NaN, infinity, or numbers outside the `jlong` range.

The `unsignedByte` function receives `jbyte -2` but returns `254` as `jint`, matching the unsigned representation of an `0xFE` octet.

### 11.3. Compiling and running on Linux

Requirements: JDK 17+, a C compiler supporting C11, and the `JAVA_HOME` environment variable pointing to the same JDK in use. Put the two files above in the same directory and run in a POSIX shell:

~~~bash
javac -encoding UTF-8 -h . PrimitiveBridge.java
javap -p -s PrimitiveBridge

cc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
   -I"$JAVA_HOME/include" \
   -I"$JAVA_HOME/include/linux" \
   PrimitiveBridge.c -o libprimitivebridge.so

java -Djava.library.path=. PrimitiveBridge
~~~

`javac -h .` creates `PrimitiveBridge.class` and the header `PrimitiveBridge.h`, which declares the exact JNI signatures for the C compiler to check. The files `libprimitivebridge.so`, `primitivebridge.dll`, or `libprimitivebridge.dylib` have platform-specific naming conventions; the `cc` command and include paths above are for **Linux**. For Windows or macOS, you need the corresponding compiler, shared-library flags, and JNI include paths; do not copy `-fPIC`/`include/linux` verbatim to every system.

Output of the **final Java command**:

~~~text
total=3000201067
unsignedByte=254
~~~

You can verify `total` by addition: `1 + (-2) + 65 + 1000 + 200000 + 3000000000 + 1 + 2 = 3000201067`. If the JVM cannot find the shared library, `System.loadLibrary` throws `UnsatisfiedLinkError` before calling the method; that is a library loading error, not evidence of an incorrect mapping table.

### 11.4. What to check in the auto-generated header

The C native declarations from the header will have the equivalent return type and parameter list:

~~~c
JNIEXPORT jlong JNICALL Java_PrimitiveBridge_total
  (JNIEnv *, jclass, jboolean, jbyte, jchar, jshort,
   jint, jlong, jfloat, jdouble);

JNIEXPORT jint JNICALL Java_PrimitiveBridge_unsignedByte
  (JNIEnv *, jclass, jbyte);
~~~

This is an illustrative prototype of the meaningful parts; the actual header also has include guards and macros/annotations generated by the JDK. Because the `PrimitiveBridge` class is in the default package and has no overloads, the symbols in the example are simple; names generated for classes with packages or overloads follow different JNI name mangling rules. Use the actual output of `javac -h` as the source of truth.

## 12. JNI APIs using the right primitive type family

JNI types appear not only in native method parameters, but also in the API groups for calling methods, accessing fields, and arrays. For example:

| Java kind | JNI scalar | Example method call API | Example field getter | Array reference |
| --- | --- | --- | --- | --- |
| boolean | `jboolean` | `CallBooleanMethod` | `GetBooleanField` | `jbooleanArray` |
| byte | `jbyte` | `CallByteMethod` | `GetByteField` | `jbyteArray` |
| char | `jchar` | `CallCharMethod` | `GetCharField` | `jcharArray` |
| short | `jshort` | `CallShortMethod` | `GetShortField` | `jshortArray` |
| int | `jint` | `CallIntMethod` | `GetIntField` | `jintArray` |
| long | `jlong` | `CallLongMethod` | `GetLongField` | `jlongArray` |
| float | `jfloat` | `CallFloatMethod` | `GetFloatField` | `jfloatArray` |
| double | `jdouble` | `CallDoubleMethod` | `GetDoubleField` | `jdoubleArray` |

Example of a C function that needs to call an instance Java method returning `int`:

~~~c
/* Illustrative snippet inside native code where env, object, and methodId are already available. */
jint result = (*env)->CallIntMethod(env, object, methodId);
if ((*env)->ExceptionCheck(env)) {
    /* Do not use result as a normal result while an exception is pending. */
}
~~~

`CallIntMethod` must be paired with a Java method returning `int`/descriptor `I`; if the method returns `long`, use `CallLongMethod` and `jlong`. For `static`, there are corresponding API families `CallStaticIntMethod` and `GetStaticIntField`. For an instance method returning `void`, use `CallVoidMethod`; there is no `jvoid`.

When working with arrays:

- `GetArrayLength` returns `jsize` (the array length type in JNI; equivalent to `jint` by specification), **not** the native allocator's `size_t`.
- `GetIntArrayRegion` and `SetIntArrayRegion` operate on `jintArray` with a `jint *` buffer by offset and element count.
- `GetFloatArrayElements` returns `jfloat *`, which may be a copy or a direct access region depending on the JVM. If you call a `Get...Elements` function, you must follow the corresponding `Release...Elements` pair and pointer lifetime rules.
- Each array type has its own API: `GetByteArrayRegion` must not be used with `jcharArray` or `jintArray`.

Lengths and pointer types have **their own conversion rules**. Passing an arbitrary `jlong` to a `jsize` parameter without bounds checking can cause it to be narrowed or become an incorrect value.

## 13. Edge cases that must be clearly understood

### 13.1. `boolean` differs from integer 0/1 in type descriptors

`boolean` has descriptor `Z`. `int` has descriptor `I`. Even if an application's internal API represents state using 0 and 1, the Java methods `native boolean isValid()` and `native int isValid()` have **different return signatures**. Do not change the C prototype from `jboolean` to `jint` just because "both return 0 or 1".

### 13.2. `char` cannot hold every Unicode character

Java `char` is a 16-bit code unit, so a code point outside the BMP requires a surrogate pair. JNI `jchar` passes **one code unit**, and does not automatically pair them. If you want to pass a decoded Unicode code point, explicitly define a contract taking `jint` containing a valid scalar value, or pass `String`/`jstring` and handle full UTF-16. Code points in the surrogate range U+D800..U+DFFF are not valid Unicode scalar values.

### 13.3. `jbyte` is signed; bit arithmetic may need masking

The raw byte `0xFF` in `jbyte` is -1. Need to treat it as unsigned? Mask with `0xFF` after widening to get 255. Conversely, do **not** mask every `jbyte` parameter if the problem genuinely uses signed numbers, such as signed-encoded temperature differences.

### 13.4. Native `long` differs from `jlong`

A C library with a `long nativeCounter` parameter does not automatically guarantee it can accept every Java `long` value. For a stable JNI API, accept `jlong` and convert to the underlying library type after min/max checking. On 64-bit Windows, C `long` is typically 32 bits even though pointers are 64 bits.

### 13.5. Overflow and narrowing are not automatically checked

JNI passes valid primitive values according to their types. If native code adds two large `jint`s and causes **signed integer overflow** in C, the behavior may be undefined in C; do not rely on Java's 32-bit `int` wrap-around mechanism in the corresponding expression. When larger calculations are needed, widen to `jlong` before adding and check for overflow. For sums of very large `jlong`s, bounds checking is required before performing the addition.

### 13.6. NaN, infinity, and signed zero

`jfloat`/`jdouble` carry floating-point numbers; NaN, infinity, and the sign of zero must be considered if the algorithm depends on boundary values. `==` is not the way to detect NaN; in Java use `Float.isNaN`/`Double.isNaN`, and in C use `isnan`. Raw bit patterns across NaNs may undergo canonicalization in some operations; do not use NaN payloads as a portable data channel when the contract does not specify it.

### 13.7. Descriptors and JNI name mangling are two different things

`(I)J` describes a method taking an int and returning a long. The C symbol `Java_package_Class_method` is tied to how the JVM locates the JNI native implementation; when methods are overloaded, the native name may append an encoding of the parameter types. Do not construct symbols by manually concatenating descriptors: `javac -h` will generate a header containing the exact names and C signatures.

### 13.8. Primitive scalars and references have different lifetime rules

Scalar `jint`/`jdouble` are values passed into the function; you do not "release a primitive value". `jstring`, `jobject`, and `jintArray` are JNI handles. When acquiring a pointer to array/string contents via JNI, you must follow acquire/release rules and limit usage duration. Do not store the pointer for an asynchronous operation after releasing it.

## 14. Checklist when code-reviewing a JNI primitive bridge

1. **Type table match:** Java `boolean/byte/char/short/int/long/float/double` ↔ JNI `jboolean/jbyte/jchar/jshort/jint/jlong/jfloat/jdouble`?
2. **Descriptor match:** `Z/B/C/S/I/J/F/D` and return type; `V` only for void-returning methods?
3. **Correct JNI entry point:** `JNIEXPORT`, `JNICALL`, `JNIEnv *`, `jobject` or `jclass`, parameter order, and `javac -h` header?
4. **Correct byte/char semantics:** `jbyte` signed, `jchar` unsigned UTF-16 code unit, `String` is `jstring`, arrays are `j<type>Array`?
5. **No guessing C widths:** `long`/`wchar_t`/`bool` and `size_t` are not automatically compatible with `jlong`/`jchar`/`jboolean`/`jsize`?
6. **Narrowing/overflow checks:** every value is representable in the target type, and integer addition/multiplication does not cause signed C overflow?
7. **Floating-point:** rounding, NaN, infinities, ±0, and unsafe casts are acknowledged and controlled?
8. **Testing the right boundary values:** -128/127 for byte; 0x00/0xFF as octets; U+0000/U+FFFF and surrogates for char; min/max int/long; 0.1, NaN, ±Infinity for float/double when allowed by the protocol?
9. **Independent verification:** run `javac -h`, inspect the header, test the Java ↔ C program on the target ABI, and measure actual results instead of just eyeballing the code?

## 15. Self-check questions

**Question 1.** What are the descriptor and C return type of Java `native long convert(int a, short b);`?

Answer: descriptor `(IS)J`; returns `jlong`, with Java parameters `jint` and `jshort` respectively, in addition to the two hidden JNI parameters.

**Question 2.** Why does `char c = '中';` not correspond to C `char c`?

Answer: Java `char`/JNI `jchar` is an unsigned 16-bit UTF-16 code unit; `'中'` has the value 0x4E2D (20013). C `char` is usually 8 bits and cannot hold that value.

**Question 3.** If Java passes `(byte)0xFF` to a native method taking byte, what value does `jbyte` have? What do you do to read it as an unsigned octet?

Answer: the value `-1`; use `((jint)value) & 0xFF` to get 255 when the data contract requires an unsigned 8-bit value.

**Question 4.** Is C `long` always large enough to hold `jlong`?

Answer: no. `jlong` is 64-bit signed according to JNI; C `long` can be 32-bit or 64-bit depending on the data model/ABI. Check before converting.

**Question 5.** What descriptor does a JNI method taking `float` and returning `double` have?

Answer: `(F)D`; in C, this corresponds to parameter `jfloat` and return type `jdouble`.

**Question 6.** Why can `double` not recover the precision lost when `float` has already been rounded?

Answer: widening to binary64 preserves the exact **already-rounded binary32 value**; it does not restore the earlier original numeric value.

**Question 7.** Does `char[]` have descriptor `C` or `[C`? Is the JNI C parameter `jchar *` or `jcharArray`?

Answer: `[C` and `jcharArray`. `C` is only a scalar `char`; to retrieve array elements, you must go through the JNI array APIs.

## Further reading

- [JNI Types and Data Structures (JNI specification)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): primitive table, references, `jvalue`, and JNI type signatures.
- [JNI Native Method Interface (specification)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): native functions, dynamic linking, and native method naming.
- [JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): functions for working with arrays, strings, calling methods, and accessing fields.
- [Java SE 17 `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): the `-h` option for generating JNI headers.
- [Java SE 17 `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): the `-s` option for displaying descriptors.

**Remember:** when Java calls JNI, scalar values are exchanged via `j...` types with defined widths and meanings. `char` is a UTF-16 code unit, `byte` is signed, `long` is 64 bits, and floating-point numbers follow IEEE 754 rules; the `Z B C S I J F D` descriptors describe types for the JVM. Preserving values depends on **the right signatures and conversion rules**, not on guessing C types by name.
