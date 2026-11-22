# Passing Argument Lists via `jvalue` and the A or V Variants in JNI

When native C/C++ code needs to **call back into a Java method** via JNI (Java Native Interface), JNI provides several ways to pass arguments for the same method: passing arguments directly after `jmethodID`, packing each argument into a `jvalue[]` array and calling the function with the **A** suffix, or passing a C variable argument list `va_list` to the function with the **V** suffix.

The three approaches differ only in **the form used to pass arguments into the JNI call**. The target Java method, parameter order, return type, and JNI signature must be consistent across all three approaches. There is no mechanism to automatically detect the type of each element in `jvalue[]`: the programmer is responsible for matching the exact type to the method descriptor.

## 1. Context: Java Calling Native and Native Calling Java

Typical flow:

```text
Java: JniArgumentDemo.main()
   |
   | calls native method, e.g. callNumbers()
   v
C: Java_JniArgumentDemo_callNumbers(JNIEnv*, jclass)
   |
   | GetMethodID(...) / GetStaticMethodID(...)
   | prepare C arguments
   |
   +-- CallIntMethod(...)         // direct C arguments
   +-- CallIntMethodA(..., args)  // jvalue array
   +-- CallIntMethodV(..., ap)    // C va_list
   |
   v
Java: an instance/static method is called back
   |
   | returns a value or throws a Java exception
   v
C: continues processing / returns result to native caller
```

**Important boundary:** `jvalue[]`, `Call<Type>MethodA`, and `Call<Type>MethodV` serve the direction of **native calling a Java method**. They do not turn a Java `Object...` into a “JNI argument list”, nor do they replace the C signature of a `native` method called from Java. Java varargs is a language syntax compiled into **a single array parameter**; C varargs (`...`) is an entirely different ABI/C mechanism.

When JNI looks up a Java method, it typically requires:

1. A valid `JNIEnv *env` for the **current thread**.
2. A target `jclass` or `jobject` matching the method kind.
3. A `jmethodID` obtained via `GetMethodID` (instance/constructor) or `GetStaticMethodID` (static).
4. The exact JNI descriptor: `(parameter-types...)return-type`.
5. Argument values arranged in the **exact position and exact type**.

## 2. `jvalue` Is a C `union`, Not a Java Object

`jni.h` declares the value type for each argument **slot** as follows (this is the C definition according to the JNI specification):

```c
typedef union jvalue {
    jboolean z;
    jbyte    b;
    jchar    c;
    jshort   s;
    jint     i;
    jlong    j;
    jfloat   f;
    jdouble  d;
    jobject  l;
} jvalue;
```

A C `union` shares the same memory region across its members; at any given time, a slot must be assigned through **the member matching the Java parameter type at that exact position**. `jvalue` does not tag itself with “this is an int or a String” and does not perform safe type casting at runtime.

| Java parameter type | JNI descriptor character | Member in `jvalue` | JNI native type |
| --- | --- | --- | --- |
| `boolean` | `Z` | `.z` | `jboolean` |
| `byte` | `B` | `.b` | `jbyte` |
| `char` | `C` | `.c` | `jchar` (16-bit unsigned) |
| `short` | `S` | `.s` | `jshort` |
| `int` | `I` | `.i` | `jint` |
| `long` | `J` | `.j` | `jlong` |
| `float` | `F` | `.f` | `jfloat` |
| `double` | `D` | `.d` | `jdouble` |
| `String`, any object and array | `Ljava/lang/String;`, `L...;` or `[...]` | `.l` | `jobject` / `jstring` / `jarray` / ... |

Use `JNI_TRUE`/`JNI_FALSE` when creating a `jboolean`. Java `char` is a 16-bit UTF-16 code unit; do not equate it with a 1-byte C `char`. Similarly, `jlong` is JNI's signed 64-bit type; do not assume it is identical to C `long` across all ABIs.

### Example of Packing a Method with Different Types

Suppose Java has:

```java
public static String describe(String name, int count, double factor) {
    return name + ":" + count + ":" + factor;
}
```

The exact descriptor is `(Ljava/lang/String;ID)Ljava/lang/String;`: the first parameter is a `String` reference, the second is `int`, the third is `double`; returning `String`. On the C side:

```c
/* Illustrative snippet, not standalone: env, clazz must be valid. */
jmethodID mid = (*env)->GetStaticMethodID(
        env, clazz, "describe",
        "(Ljava/lang/String;ID)Ljava/lang/String;");
if (mid == NULL) {
    return; /* only suitable for a C function returning void */
}

jstring name = (*env)->NewStringUTF(env, "item");
if (name == NULL) {
    return; /* need to handle exception or out of memory */
}

jvalue args[3] = {{0}, {0}, {0}};
args[0].l = name;
args[1].i = 7;
args[2].d = 1.5;

jstring result = (jstring)(*env)->CallStaticObjectMethodA(
        env, clazz, mid, args);

(*env)->DeleteLocalRef(env, name);
/* Check ExceptionCheck and handle 'result' per the caller's contract. */
```

This is an **illustrative snippet** for a `void` native function where `env` and `clazz` are already provided; a complete runnable example with exception checking is in section 6. Note: do not pass a `char *` containing a C string directly into `args[0].l`. It must be a valid **Java reference** (here, a `jstring` created via JNI). `jvalue[]` itself is a C array residing in native memory, **not** a Java `jobjectArray`.

### Ordering Rule

If the target Java method declares `f(int a, long b, String c)`, use:

```c
jvalue args[3] = {{0}, {0}, {0}};
args[0].i = 10;        /* int a  */
args[1].j = (jlong)20; /* long b */
args[2].l = textRef;   /* String c: already valid jstring */
```

The order of elements in the array **is the exact parameter order of the descriptor**; there are no parameter name fields, no automatic reordering, and no automatic count checking. `args[1].i` cannot substitute for `args[1].j` simply because the value 20 is small. For reference types, `NULL` can represent Java `null` **if** the method's contract allows it; it does not substitute for a primitive.

## 3. Three Variants of the Same Call

Suppose the target Java method is:

```java
public int calculate(int x, int y) {
    return 100 + x * 10 + y;
}
```

On the C side, we already have a suitable `jobject target` and a `jmethodID mid` obtained from `GetMethodID(..., "calculate", "(II)I")`. Three ways to call it:

### No suffix: direct arguments in C `...`

```c
jint result = (*env)->CallIntMethod(env, target, mid, (jint)2, (jint)3);
```

Readable when the signature and arguments are already known at the call site. This is a **C variadic function call**, not Java's `Object...` mechanism.

### Suffix A: `jvalue[]`

```c
jvalue args[2] = {{0}, {0}};
args[0].i = 2;
args[1].i = 3;

jint result = (*env)->CallIntMethodA(env, target, mid, args);
```

Useful when values are already in a data structure and need to be arranged into an argument list before calling, such as a native bridge/dispatcher that has metadata about each parameter type. Do not assume “A” means **asynchronous**: A here stands for **array of `jvalue`**; the call is still synchronous just like the corresponding JNI function.

### Suffix V: `va_list`

```c
#include <stdarg.h>

static jint calculate_v(JNIEnv *env, jobject target,
                        jmethodID mid, ...) {
    va_list ap;
    va_start(ap, mid);
    jint result = (*env)->CallIntMethodV(env, target, mid, ap);
    va_end(ap);
    return result;
}

/* Inside a C function that has valid env, target, mid: */
jint result = calculate_v(env, target, mid, 2, 3);
```

`va_list` is created using `va_start` inside a C function that **actually has `...`**; it is not a pointer to `jvalue[]`. `va_end` must be called after use, even if the Java callback throws an exception (as in the wrapper above). If a `va_list` needs to be used multiple times, you must understand its lifetime and use `va_copy` according to the C ABI; do not assume JNI `...V` does not alter the internal position/representation of `va_list`.

All three examples above, if the Java method runs normally with `x = 2` and `y = 3`, return `123`. The difference lies in **how the arguments are supplied**, not in the Java formula or the result type.

## 4. Choosing the Right JNI Function Group

`<Type>` in the function name is the **return type of the Java method**, not the type of the first parameter. For example, if a Java method returns `long`, use `CallLongMethodA`; even if that method takes `int`, still do not use `CallIntMethodA`.

| Call target | Obtain `jmethodID` with | A / V / no suffix |
| --- | --- | --- |
| Instance method (normal virtual call) | `GetMethodID(env, clazz, name, signature)` | `Call<Type>MethodA` / `Call<Type>MethodV` / `Call<Type>Method` |
| Static method | `GetStaticMethodID(env, clazz, name, signature)` | `CallStatic<Type>MethodA` / `CallStatic<Type>MethodV` / `CallStatic<Type>Method` |
| **Nonvirtual** instance method | `GetMethodID` on the specified class/interface | `CallNonvirtual<Type>MethodA` / `...V` / `...`; takes an additional `jclass clazz` |
| Constructor | `GetMethodID(env, clazz, "<init>", "(...)V")` | `NewObjectA` / `NewObjectV` / `NewObject` |

The `<Type>` choices include `Object`, `Boolean`, `Byte`, `Char`, `Short`, `Int`, `Long`, `Float`, `Double`, `Void` (for Java methods returning `void`). `CallObjectMethodA` is for reference types, including `String` and arrays; the returned JNI value is a `jobject` local reference that can be cast to the appropriate subtype after verifying the method signature.

Signature examples:

| Java method | Descriptor | Appropriate call function |
| --- | --- | --- |
| `int sum(int a, int b)` | `(II)I` | `CallIntMethodA` if instance |
| `static long read(long seed)` | `(J)J` | `CallStaticLongMethodV` if you have a `va_list` |
| `String label(int id, String s)` | `(ILjava/lang/String;)Ljava/lang/String;` | `CallObjectMethodA` |
| `void fill(int[] numbers)` | `([I)V` | `CallVoidMethodA` with `args[0].l` as `jintArray` |
| `Widget(String name, int size)` | `(Ljava/lang/String;I)V` | `NewObjectA` or `NewObjectV` |

A constructor has no “Java return value”, so its descriptor always ends with `V`; **`NewObjectA` returns a `jobject`** for the newly created instance after the constructor is called. Do not use `CallObjectMethodA` to simulate a normal constructor call.

**Nonvirtual vs. virtual:** `Call<Type>MethodA` dispatches according to the Java instance; `CallNonvirtual<Type>MethodA` requires an explicit target class and can invoke a specified superclass implementation (similar to needing to call `super`) or a default interface method. You must pass `jclass` and `jmethodID` consistently with the corresponding class; do not choose nonvirtual arbitrarily just to avoid overrides.

## 5. Descriptors, Argument Promotion, and ABI Pitfalls

### Descriptors Are Runtime Contracts

JNI does not look at Java variable names or generic type parameters. `GetMethodID`/`GetStaticMethodID` looks up a method by **name and descriptor**. A missing `;` or `[` in the descriptor can cause method lookup to fail to find the method even if the display name looks the same.

| Java type | Descriptor |
| --- | --- |
| `boolean`/`byte`/`char`/`short` | `Z`/`B`/`C`/`S` |
| `int`/`long`/`float`/`double` | `I`/`J`/`F`/`D` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| `void` | `V` (return type or constructor) |

For example, `long evaluate(int count, String text, int[] samples)` has descriptor `(ILjava/lang/String;[I)J`. Classes in descriptors use `/` as in internal class names; `L...;` wraps reference types. For overloaded methods, each overload must be looked up by **its own descriptor**.

**How to verify:** `javap -s -p JniArgumentDemo` shows the descriptors of compiled Java methods (including private ones). Java's `int` and C's `jint` have an explicit width contract; native C `int`/`long` types are ABI-dependent and still need to be used via the corresponding JNI types.

### C Varargs Have Default Argument Promotions

In the no-suffix variant and inside the `...` helper for V, C applies argument conversion rules without individual parameter prototypes:

- `float` is promoted to `double`.
- Integer types smaller than `int` such as `char`/`short` are usually promoted to `int` (or `unsigned int` per C rules).
- `int` stays `int`; other types must be passed with the exact representation and ABI expected by the JNI function.

This **does not apply** automatically to the `jvalue[]` array. With `A`, assign `args[k].f` when the descriptor has `F`, `args[k].b` when it has `B`, `args[k].j` when it has `J`. With `V`, C handles the parameter list according to default promotions and the ABI. For instance, you cannot take `jvalue args[3]` and cast `(va_list)args` to call `Call...MethodV`: `va_list` may be a struct/register-backed type per the ABI and does not have a representation compatible with a union array.

On many platforms, `va_list` also has its own register and stack argument-passing mechanism; passing the wrong type to `...`/`...V` can cause incorrect values or a crash. When data comes from JSON, a metadata table, or a dynamic argument list, **A** is the more natural path: normalize the type and fill each `jvalue`. Do not hand-craft a `va_list` from a byte buffer.

### Java Varargs Do Not Increase the JNI Parameter Count

Example:

```java
public static String join(String delimiter, String... values) {
    return String.join(delimiter, values);
}
```

The descriptor is `(Ljava/lang/String;[Ljava/lang/String;)Ljava/lang/String;`. JNI sees **two** parameters: `String` and `String[]`, not N separate parameters from Java's `...`. With the A variant, you need `jvalue args[2]`: `args[0].l` is the `jstring` delimiter and `args[1].l` is the `jobjectArray` containing the `String`s. Do not push each element of the `values` array into multiple different `jvalue` slots.

## 6. Runnable Java 17+ and JNI C Example (Linux)

This example verifies simultaneously:

- `NewObjectA` to pass an `int` argument to a constructor.
- `CallIntMethodA`, `CallIntMethodV`, and `CallIntMethod` for the **same** instance method `compute(int,int)`.
- `CallStaticIntMethodA` for a static method returning `int`.
- `CallStaticObjectMethodA` with a mixed `jvalue` array of `String`, `int`, `double`.

The files are placed in the **same directory**, using GCC or Clang, and JDK 17+ on Linux with the same architecture as the native library. This example requires no framework; the native library uses the logical name `jniargsdemo`.

### Step 1 — `JniArgumentDemo.java`

```java
import java.util.Arrays;

public final class JniArgumentDemo {
    static {
        System.loadLibrary("jniargsdemo");
    }

    private final int base;

    public JniArgumentDemo(int base) {
        this.base = base;
    }

    public int compute(int a, int b) {
        return base + a * 10 + b;
    }

    public static int triple(int value) {
        return value * 3;
    }

    public static String describe(String name, int count, double factor) {
        return name + ":" + count + ":" + factor;
    }

    private static native int[] callNumbers();
    private static native String callMixed();

    public static void main(String[] args) {
        System.out.println("numbers=" + Arrays.toString(callNumbers()));
        System.out.println("mixed=" + callMixed());
    }
}
```

`System.loadLibrary("jniargsdemo")` searches for the library by logical name; Linux commonly maps this to the file `libjniargsdemo.so`. In this example, `-Djava.library.path=.` is used at startup. The Java native methods `callNumbers` and `callMixed` are only entry points from Java into C; `compute`/`triple`/`describe` are the targets of **C calling back into Java**.

### Step 2 — `jni_argument_demo.c`

```c
#include "JniArgumentDemo.h"  /* generated by javac -h; already includes jni.h */
#include <stdarg.h>

/* C wrapper with actual ...: builds va_list and forwards to JNI V. */
static jint compute_with_v(JNIEnv *env, jobject obj,
                           jmethodID method, ...) {
    va_list ap;
    va_start(ap, method);
    jint value = (*env)->CallIntMethodV(env, obj, method, ap);
    va_end(ap);
    return value;
}

/* Signature declared by javac -h in JniArgumentDemo.h. */
JNIEXPORT jintArray JNICALL
Java_JniArgumentDemo_callNumbers(JNIEnv *env, jclass clazz) {
    jmethodID ctor = (*env)->GetMethodID(
            env, clazz, "<init>", "(I)V");
    if (ctor == NULL) {
        return NULL; /* Java exception pending if lookup fails */
    }

    jvalue initArgs[1] = {{0}};
    initArgs[0].i = 100;
    jobject obj = (*env)->NewObjectA(env, clazz, ctor, initArgs);
    if (obj == NULL) {
        return NULL;
    }

    jmethodID method = (*env)->GetMethodID(
            env, clazz, "compute", "(II)I");
    if (method == NULL) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    jmethodID staticMethod = (*env)->GetStaticMethodID(
            env, clazz, "triple", "(I)I");
    if (staticMethod == NULL) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    /* 1. Variant A: two jvalue slots of type jint. */
    jvalue pair[2] = {{0}, {0}};
    pair[0].i = 2;
    pair[1].i = 3;
    jint viaA = (*env)->CallIntMethodA(env, obj, method, pair);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    /* 2. Variant V: C helper creates va_list. */
    jint viaV = compute_with_v(env, obj, method, 2, 3);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    /* 3. No suffix: direct C arguments after method. */
    jint direct = (*env)->CallIntMethod(
            env, obj, method, (jint)2, (jint)3);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    /* 4. Static method: must use GetStaticMethodID/CallStatic*. */
    jvalue one[1] = {{0}};
    one[0].i = 4;
    jint viaStatic = (*env)->CallStaticIntMethodA(
            env, clazz, staticMethod, one);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    jint values[4] = {viaA, viaV, direct, viaStatic};
    jintArray output = (*env)->NewIntArray(env, 4);
    if (output == NULL) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    (*env)->SetIntArrayRegion(env, output, 0, 4, values);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, output);
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    (*env)->DeleteLocalRef(env, obj);
    /* Local ref output is returned to Java; do not delete it here. */
    return output;
}

/* Example of reference + primitive side by side in jvalue[]. */
JNIEXPORT jstring JNICALL
Java_JniArgumentDemo_callMixed(JNIEnv *env, jclass clazz) {
    jmethodID method = (*env)->GetStaticMethodID(
            env, clazz, "describe",
            "(Ljava/lang/String;ID)Ljava/lang/String;");
    if (method == NULL) {
        return NULL;
    }

    jstring name = (*env)->NewStringUTF(env, "item");
    if (name == NULL) {
        return NULL;
    }

    jvalue mixed[3] = {{0}, {0}, {0}};
    mixed[0].l = name;
    mixed[1].i = 7;
    mixed[2].d = 1.5;

    jstring result = (jstring)(*env)->CallStaticObjectMethodA(
            env, clazz, method, mixed);

    /* Clean up input local ref; result is a different ref to return to Java. */
    (*env)->DeleteLocalRef(env, name);
    if ((*env)->ExceptionCheck(env)) {
        return NULL;
    }
    return result;
}
```

**Why are multiple `ExceptionCheck` calls needed?** When a Java callback method throws an exception, JNI marks an exception as pending; native code must return control to Java or handle the exception properly. Do not continue making arbitrary JNI calls while an exception is pending. `DeleteLocalRef` is one of the operations permitted while an exception is pending, so the example cleans up the object before returning `NULL`.

In `callNumbers`, `jint[] values` is a **C array** and `jintArray output` is a **Java array**; `SetIntArrayRegion` copies the four primitive values into the Java array. Meanwhile, `jvalue pair[2]` is a **C union array for passing JNI arguments**. These are three different structures.

### Step 3 — Compile and Run

Use a Linux shell. Set `JAVA_HOME` to point to the **installed JDK** (same architecture as the native compiler); for example, configure it from your environment's JDK before running the following commands:

```bash
# In the directory containing JniArgumentDemo.java and jni_argument_demo.c:
javac -h . JniArgumentDemo.java

# Requires JAVA_HOME pointing to the right JDK containing include/jni.h.
cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjniargsdemo.so jni_argument_demo.c

java -Djava.library.path=. JniArgumentDemo
```

`javac -h .` generates `JniArgumentDemo.class` and `JniArgumentDemo.h`; compile the C code after this step to use the header with the right signatures and JNI types. Linux uses `.so`; Windows needs `.dll` and appropriate compile/link options, and macOS uses the corresponding dylib/JDK rules. `-Djava.library.path=.` must precede the main class so the JVM can locate `libjniargsdemo.so`.

**Expected stdout**, when all steps succeed:

```text
numbers=[123, 123, 123, 12]
mixed=item:7:1.5
```

Part-by-part explanation:

- The constructor creates an object with `base=100`.
- `compute(2, 3)` returns `100 + 2*10 + 3 = 123`. The three calls `CallIntMethodA`, `CallIntMethodV`, and `CallIntMethod` pass the same two arguments to the same method, so all three receive `123`.
- `triple(4)` is a static Java method, returning `12`.
- `describe("item", 7, 1.5)` is a static method taking a reference, a primitive `int`, and a `double`, returning `"item:7:1.5"`. C assigns `.l`, `.i`, `.d` appropriately and uses `CallStaticObjectMethodA`.

All of the output above is **determined by the given Java code**; compiler/platform differences may change how the native library is built, but once the binary has the right ABI/JNI and is loaded, the values returned by Java must match the above.

### Step 4 — Verify Descriptors from the Compiled Class

```bash
javap -s -p JniArgumentDemo
```

In the longer output of `javap`, the notable descriptors are:

```text
public JniArgumentDemo(int);
  descriptor: (I)V

public int compute(int, int);
  descriptor: (II)I

public static int triple(int);
  descriptor: (I)I

public static java.lang.String describe(java.lang.String, int, double);
  descriptor: (Ljava/lang/String;ID)Ljava/lang/String;

private static native int[] callNumbers();
  descriptor: ()[I

private static native java.lang.String callMixed();
  descriptor: ()Ljava/lang/String;
```

These lines illustrate **the parts to cross-check**, not a copy of the entire output, as `javap` also prints the class header and other methods. The signatures used in `GetMethodID` and `GetStaticMethodID` must match exactly.

## 7. When Should You Use A, V, or the Direct Variant?

| Situation | Choose | Why |
| --- | --- | --- |
| Native C has a fixed number of arguments at the call site | No suffix, e.g. `CallIntMethod` | Short syntax, clearly shows the argument list |
| Native bridge builds an argument list from metadata | **A** with `jvalue[]` | Each slot holds the exact type per descriptor; easy to loop over metadata |
| You have an actual variadic C wrapper and want to forward to JNI | **V** with `va_list` | Avoids rewriting C `va_arg` reading logic |
| JNI callback to a static method | `CallStatic<Type>MethodA/V` | Target is `jclass`, `jmethodID` from `GetStaticMethodID` |
| JNI creates a Java object via constructor | `NewObjectA/V` | `<init>` has a `V` return descriptor, but the API returns a reference to the object |
| Want to call an implementation without virtual dispatch | `CallNonvirtual<Type>MethodA/V` | Passes an additional class specifying the implementation |
| Java method takes `String...` | A containing **one reference to String[]** for the varargs parameter | JNI uses an array descriptor; do not unpack Java varargs into C varargs |

**There is no general optimization rule that “A is faster than V”.** Choose the structure that matches the caller's actual data, ensure the ABI/descriptor is correct, and measure performance if the application is truly sensitive to JNI overhead. Differences at the Java/native boundary, boxing/allocations, object lifetimes, and the work done by the method usually matter more than guessing speed from the A/V suffix.

## 8. Reference Safety, Exception Handling, and Method ID Lifetime

### References in `jvalue.l` Must Remain Valid

`jvalue.l` stores a **JNI reference** such as `jstring`, `jobject`, or `jintArray`; it does not store a C pointer to an arbitrary buffer. When `CallObjectMethodA` returns a reference, the result is usually a new **local reference** (or `NULL`), which must be managed according to the JNI lifecycle. Within a native method call, local refs are automatically cleaned up when returning to Java; cleaning them up early with `DeleteLocalRef` helps avoid overflowing the local-reference table in long loops.

Example:

```c
jstring title = (*env)->NewStringUTF(env, "hello");
if (title == NULL) {
    return NULL; /* valid for a JNI function returning jobject/jstring */
}
jvalue arg[1] = {{0}};
arg[0].l = title;

/* ... CallObjectMethodA(..., arg) and check exception ... */

(*env)->DeleteLocalRef(env, title);
```

Do not use `title` after deleting the local ref. Do not store a `jobject` local ref in a global C cache for another thread to call after the native method has returned; you must create a **global reference** (`NewGlobalRef`) and release it (`DeleteGlobalRef`) at the appropriate lifecycle point, while also handling class-loader and thread attachment concerns. `JNIEnv *` **must not be shared across native threads**; a native thread must attach itself to the VM to obtain a valid `JNIEnv *` if it needs to make callbacks.

### Java Exceptions Do Not Turn into C Error Codes

`Call<Type>MethodA` or `...V` may execute a Java method that raises an exception. JNI does not “throw a C exception”; it creates a **pending Java exception** state on the thread. After the call, you must consider `ExceptionCheck(env)` or `ExceptionOccurred` before accessing the result or calling other JNI APIs. A common safe action is to delete any held local refs and return so the exception propagates to the Java caller.

Do not arbitrarily call `ExceptionClear` just to continue as if no error occurred; only clear it when there is a contract to catch/translate the exception and report the error clearly. In the runnable example, the error path returns `NULL` with the exception still pending; Java receives the appropriate exception.

### `jmethodID` Is Not an Object Reference

`jmethodID` is an opaque identifier for a method resolved by class, name, and descriptor. Do not assign it to `jvalue.l`; do not manage it with `DeleteLocalRef`. The ID remains valid for the lifetime of the loaded class; long-lived caching must account for class unloading and references to the class/class loader. In a multi-class-loader bridge, do not reuse the same `jmethodID` for a different class even if the method name is the same.

### Do Not Skip Argument Validation

- Read the `jvalue` array with the exact number of elements required by the descriptor; missing slots or uninitialized access can cause unpredictable native errors.
- Ensure the `jobject` receiver is not `NULL` when the API requires a valid object; static calls require a valid `jclass`.
- Do not use `CallIntMethodA` for a method returning `long` or `Object`.
- Ensure `jvalue.l` is a reference belonging to the current JVM, not an arbitrary address or an expired reference.
- For downcast references, check the type when appropriate; JNI does not automatically know “this is a Java String” solely from the C union.
- With JNI V, do not store `va_list` for asynchronous use after the C function has exited; `va_list` must follow its proper scope/ABI, `va_end`, and `va_copy`.

## 9. Common Mistakes and How to Read Symptoms

| Mistake | Common consequence | Fix |
| --- | --- | --- |
| Assigning `args[0].j` for Java `int` | Mismatched size/union member, wrong value or unpredictable error | Use `args[0].i` for descriptor `I` |
| Passing `jvalue[]` to `Call...MethodV` via cast | `va_list` has a different ABI layout, may crash | Use `...MethodA`; do not cast |
| Using `CallStaticIntMethodA` with an instance `GetMethodID` | Wrong method ID kind/calling contract | Static → `GetStaticMethodID`, instance → `GetMethodID` |
| Using `CallIntMethodA` with a method returning `long` | Wrong return carrier | Choose `CallLongMethodA` |
| Writing descriptor `(Ljava.lang.String;)V` | JNI class names use `/` and `L...;` | `(Ljava/lang/String;)V` |
| Using `GetStaticMethodID("<init>", ...)` for a constructor | A constructor is not a static method | `GetMethodID(clazz,"<init>","(...)V")` and `NewObjectA/V` |
| Passing Java `String...` as multiple `jvalue` slots | The JVM sees a single `String[]` parameter | Create a `jobjectArray` and put it in one `.l` slot |
| Calling `CallObjectMethodA` after deleting the input `jstring` | Invalidated Java reference | Keep the local ref alive until the call finishes |
| Not checking pending exception before the next JNI call | May mask the root cause or trigger other JNI errors | `ExceptionCheck`, clean up local refs, return or handle explicitly |
| Misusing `V` when data is an array prepared at runtime | Hard to construct a portable `va_list` | Use `A` with a type-checked union array |
| Storing `JNIEnv *`/local `jobject` for another thread to call | Wrong JNI thread/lifetime | Attach thread to get env; create global ref if holding object long-term |

**When the error is unclear:** run Java with `-Xcheck:jni` on JVMs that support this option to catch many JNI violations earlier, though do not treat it as proof that a native program is completely safe. Use headers generated by `javac -h`, inspect the full Java exception/stack trace, and verify exact signatures with `javap -s -p`.

## 10. Self-Check Questions

**1. For Java method `long sum(int a, long b)` using A, which array is correct?**

```c
jvalue args[2] = {{0}, {0}};
args[0].i = (jint)3;
args[1].j = (jlong)4;
/* GetMethodID with "(IJ)J"; call CallLongMethodA(...) */
```

Position 0 is `I`, position 1 is `J`, return type is `J`, so the function to call is `CallLongMethodA`.

**2. Can a `jvalue` array be converted to a `va_list` by casting?**

No. `jvalue[]` is a sequence of C unions; `va_list` describes ABI-specific varargs passing state and can only be created/managed via `<stdarg.h>` in an appropriate context.

**3. What is needed to call `static double price(String currency, int units)`?**

Use `GetStaticMethodID(clazz, "price", "(Ljava/lang/String;I)D")`, fill `args[0].l` with a valid `jstring` and `args[1].i` with `jint`, then `CallStaticDoubleMethodA(env, clazz, mid, args)`; or pass the exact C argument list if using the no-suffix/V variant.

**4. Are `NewObjectA` and `CallObjectMethodA` interchangeable?**

No. `NewObjectA` uses the `<init>` constructor method ID to create a new instance. `CallObjectMethodA` calls an instance method with a reference return type, after a receiver object already exists.

**5. Is `...` in Java `String... args` directly related to `Call...MethodV`?**

No. Java varargs is **a single array parameter** in JVM bytecode; JNI V takes a **C `va_list`**. They have similar-looking names, but different data and ABIs.

**6. Why might `CallIntMethodV` return a plausible-looking result even though the code is still wrong?**

The JNI/C ABI might coincidentally produce the same number in one environment; if the wrong type is passed (especially `float`, `long`, pointer) or an unsuitable `jmethodID` is used, behavior is not guaranteed. Verify the descriptor, prototype, and default promotions rather than inferring correctness from one lucky run.

## Official Documentation and References

- Oracle JNI Specification — *JNI Types and Data Structures*, `jvalue` declaration and descriptors: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html
- Oracle JNI Specification — *JNI Functions*, the `Call<Type>Method`, `Call<Type>MethodA/V`, static, nonvirtual, and `NewObjectA/V` groups: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html
- Oracle JNI Specification — *Design Overview*, exceptions and JNI rules: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html
- Oracle `javac`, `-h` option to generate native headers: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- GNU C Manual — `va_list`/`va_start`/`va_end` and default promotions: https://www.gnu.org/software/c-intro-and-ref/manual/html_node/Variable-Number-of-Arguments.html

**Remember:** correct `jmethodID` + correct descriptor + correct receiver/call kind + correct argument values are the core requirements. Use **A** when you already have `jvalue`-typed slots, use **V** when forwarding a valid C `va_list`, and use the **no-suffix** variant when arguments are written directly. Do not swap representations with one another, and do not ignore exceptions or the lifetime of Java references.