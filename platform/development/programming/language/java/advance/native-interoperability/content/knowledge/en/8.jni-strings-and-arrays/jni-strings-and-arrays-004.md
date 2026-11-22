# Reading or Writing an Array Region with GetArrayRegion and SetArrayRegion in JNI

## Objectives

When a Java program calls C/C++ code through the Java Native Interface (JNI), native code sometimes only needs to **read a slice** of a Java array or **write results into a slice** of that array. JNI provides the `Get<PrimitiveType>ArrayRegion` and `Set<PrimitiveType>ArrayRegion` function families to copy elements within a specified region.

After this lesson, you will be able to:

- Understand the exact meaning of `array`, `start`, `len`, and `buf` in both API families; distinguish **element index** from **byte offset**.
- Choose the right function for Java's eight primitive array types: `boolean[]`, `byte[]`, `char[]`, `short[]`, `int[]`, `long[]`, `float[]`, `double[]`.
- Read data from a Java array into a C buffer, or write data from a C buffer into a Java array, without holding a pointer to the entire array.
- Check bounds and buffer capacity safely; detect JNI exceptions instead of continuing with invalid data.
- Compile and run a Java 17 + JNI C example that performs both `GetIntArrayRegion` and `SetIntArrayRegion`, including chunked reading so no large buffer is needed.
- Know when to choose `Get/Set<Type>ArrayRegion`, when to consider `Get/Release<Type>ArrayElements`, and why region APIs do not apply directly to `Object[]`.

> **API naming note:** There are no two standalone executable JNI functions named literally `GetArrayRegion` and `SetArrayRegion`. Those are shorthand names for **primitive-type function families**, such as `GetByteArrayRegion`, `SetByteArrayRegion`, `GetIntArrayRegion`, or `SetIntArrayRegion`.

## 1. Data Model: Java Array and Native Buffer

Suppose Java has:

~~~java
int[] values = {10, 20, 30, 40, 50, 60};
~~~

We only want to read three elements starting at index 1:

~~~text
Java int[]:
index       0    1    2    3    4    5
value      10   20   30   40   50   60
                 |-------------|
                    start=1
                    len=3

GetIntArrayRegion(values, 1, 3, buf)
                              ↓
C buffer:   buf[0]=20, buf[1]=30, buf[2]=40
~~~

This model has four points:

1. `start` is the **index of the first element in the Java array**, 0-based.
2. `len` is the **number of elements**, not bytes and not the ending index.
3. `buf` is a caller-prepared native memory region that must hold at least `len` elements of the corresponding JNI type. Copied data always starts at `buf[0]`.
4. `GetIntArrayRegion` only **copies from Java to the native buffer**; it does not delete or modify the original array elements.

In the opposite direction:

~~~text
C buffer: [7, 8, 9]

SetIntArrayRegion(values, 2, 3, buf)
                               ↓
Java int[] after writing:
index       0    1    2    3    4    5
value      10   20    7    8    9   60
                       |------------|
                         start=2
                         len=3
~~~

Here `SetIntArrayRegion` reads **three `jint` values from the C buffer** and overwrites exactly `values[2]`, `values[3]`, and `values[4]`. Java elements outside the region are not modified by this operation. After writing completes, `buf` remains the native code's buffer; the JVM does not take ownership or automatically free it.

## 2. Function Signatures and Parameter Meanings

General C form per the JNI specification:

~~~c
void Get<PrimitiveType>ArrayRegion(
    JNIEnv *env, ArrayType array,
    jsize start, jsize len, NativeType *buf);

void Set<PrimitiveType>ArrayRegion(
    JNIEnv *env, ArrayType array,
    jsize start, jsize len, const NativeType *buf);
~~~

This is the **API name template in the documentation**; actual C code must replace `<PrimitiveType>` with `Int`, `Byte`, `Double`, etc., and `ArrayType`/`NativeType` with the concrete JNI types.

| Component | Role | Notes |
|---|---|---|
| `JNIEnv *env` | JNI interface bound to the current thread | Do not take a `JNIEnv*` from one thread and use it on another thread |
| `array` | Reference to a primitive Java array | Must have the array type matching the function; do not pass `NULL` |
| `start` | Starting index in the Java array | Must be non-negative and valid |
| `len` | Number of elements to copy | Non-negative; not measured in bytes |
| `buf` (Get) | **Destination** in C memory | Has enough space for `len` elements; not `NULL` |
| `buf` (Set) | **Source** in C memory | Initialized with the data to write; not `NULL` |
| Return type | `void` | Success/failure is detected via **JNI exception**, with no return code |

The corresponding functions are typically written in C source as follows:

~~~c
(*env)->GetIntArrayRegion(env, javaArray, start, len, buf);
(*env)->SetIntArrayRegion(env, javaArray, start, len, buf);
~~~

With C++ using the JNI C++ wrapper, the usual syntax is:

~~~cpp
env->GetIntArrayRegion(javaArray, start, len, buf);
env->SetIntArrayRegion(javaArray, start, len, buf);
~~~

The two snippets above **illustrate call syntax** inside a native function that already has all valid variables and types. Do not mix C and C++ syntax: `(*env)->...` is the style used in C, while `env->...` is the syntax of the JNI C++ interface.

### 2.1. The Eight Supported Function Pairs

| Java array | JNI array reference | C buffer type | Region read and write functions |
|---|---|---|---|
| `boolean[]` | `jbooleanArray` | `jboolean` | `GetBooleanArrayRegion` / `SetBooleanArrayRegion` |
| `byte[]` | `jbyteArray` | `jbyte` | `GetByteArrayRegion` / `SetByteArrayRegion` |
| `char[]` | `jcharArray` | `jchar` | `GetCharArrayRegion` / `SetCharArrayRegion` |
| `short[]` | `jshortArray` | `jshort` | `GetShortArrayRegion` / `SetShortArrayRegion` |
| `int[]` | `jintArray` | `jint` | `GetIntArrayRegion` / `SetIntArrayRegion` |
| `long[]` | `jlongArray` | `jlong` | `GetLongArrayRegion` / `SetLongArrayRegion` |
| `float[]` | `jfloatArray` | `jfloat` | `GetFloatArrayRegion` / `SetFloatArrayRegion` |
| `double[]` | `jdoubleArray` | `jdouble` | `GetDoubleArrayRegion` / `SetDoubleArrayRegion` |

**Why use JNI types?** `jint` corresponds to Java `int` (32-bit), `jlong` corresponds to Java `long` (64-bit), and `jchar` is a 16-bit UTF-16 code unit; do not assume C's `long` is always equal to Java `long`. `jboolean` represents booleans via the JNI values `JNI_FALSE` / `JNI_TRUE`; when manipulating them, use the specified JNI type. `jbyte` is an 8-bit signed type corresponding to Java's `byte`.

The copied region is measured in **elements**: `GetLongArrayRegion(..., start, 3, buf)` requires space for three `jlong` values, not three bytes. If a C buffer is dynamically allocated, calculate the size based on `sizeof(jlong)` and check for multiplication overflow in the allocation.

### 2.2. Why Doesn't `Object[]` Use These Functions?

`Get<PrimitiveType>ArrayRegion`/`Set<PrimitiveType>ArrayRegion` are for **primitive arrays**. For `String[]` or `MyObject[]`, JNI provides `GetObjectArrayElement` and `SetObjectArrayElement` by individual index; each `jobject` retrieved is a JNI reference whose lifecycle must be properly managed. Do not assume there is a `GetObjectArrayRegion` equivalent to the functions for primitive types.

For `String`, there are also `GetStringRegion` and `GetStringUTFRegion`, but those are **string manipulation APIs** with their own character-unit/modified UTF-8 semantics; they do not replace primitive array regions.

## 3. Region Validity Conditions and How to Avoid Overflow

Let:

- `n = GetArrayLength(env, array)`.
- `start` be the starting position.
- `len` be the number of elements.

A valid region has the half-open form `[start, start + len)`. When also handling empty regions, `len == 0` can be represented without copying any elements.

**Safe check when using signed integers:**

~~~c
if (start < 0 || len < 0 || start > n || len > n - start) {
    /* Invalid region */
}
~~~

**Why not just use `start + len > n`?** If the inputs are very large integers, signed addition in C can overflow before the comparison. After checking `start >= 0` and `start <= n`, the expression `n - start` is always non-negative, allowing `len` to be checked without overflowing addition. This is also the idea used in Java with `int`/`jsize`.

Examples for a six-element array:

| `start` | `len` | Meaning | Conclusion |
|---:|---:|---|---|
| 1 | 3 | Indices 1, 2, 3 | Valid |
| 0 | 6 | Entire array | Valid |
| 3 | 0 | Empty region | Valid per application check; no copy needed |
| 6 | 0 | Empty region at the end | Can be handled at the application layer **without calling the region function** |
| -1 | 1 | Negative start | Invalid |
| 4 | 3 | Exceeds index 5 | Invalid |
| 2 | -1 | Negative length | Invalid |
| 7 | 0 | Start outside the array | Invalid |

In the runnable example below, when `len == 0`, the native code proactively skips `Get/Set...ArrayRegion` so it does not depend on how a JNI implementation handles pointers/boundaries for a 0-length copy. The JNI specification requires `buf` to be non-`NULL` when **actually calling** a region function; do not pass `NULL` just because `len == 0`.

### What Does `GetArrayLength` Return?

~~~c
jsize n = (*env)->GetArrayLength(env, array);
~~~

`GetArrayLength` returns the length of the Java array; the type `jsize` is the integer type used for JNI sizes/indices. The API also works for object arrays, but that does not mean object arrays support `Get<Type>ArrayRegion`. `array` must be a valid, non-`NULL` JNI array reference.

**Do not confuse three units**:

- `start`/`len`: **number of Java elements**.
- `sizeof(jint) * len`: minimum number of **native bytes** to store `len` contiguous `jint` values in C.
- `sizeof(array)` on a `jintArray` variable in C: size of the **JNI reference variable**, completely unrelated to the byte size of the Java array.

## 4. Get: Copying Data from Java to Native Memory

C example for an `int[]` array, inside a native function that has received `jintArray numbers` and validated `start`/`len`:

~~~c
jint local[3];

(*env)->GetIntArrayRegion(env, numbers, 1, 3, local);
if ((*env)->ExceptionCheck(env)) {
    return;  // Pattern used in a native function returning void.
}

/* local[0], local[1], local[2] hold copies of the Java values. */
~~~

`GetIntArrayRegion` writes the values into the C memory pointed to by `local`. You can use a stack buffer as above for small slices, or a heap buffer that is allocated and capacity-checked for large slices. **The Java array is not modified** just because you modify `local[0]` after copying; to write back, you must call `SetIntArrayRegion`.

Specifically:

~~~text
Java:    [4, 8, 15, 16, 23, 42]
Get: start=2, len=3
C:       [15, 16, 23]

C modifies local[1] to 99:
C:       [15, 99, 23]
Java:    [4, 8, 15, 16, 23, 42]   (unchanged)
~~~

**There is no release function corresponding to `GetIntArrayRegion`.** There is only a single copy; the buffer is the responsibility of the native code. If you need to keep the buffer, manage it yourself; otherwise, a stack buffer becomes invalid when the C function returns. Never store the address of a stack buffer for use after the native function ends.

## 5. Set: Copying from a Native Buffer into a Java Array

Example writing three numbers at indices 2–4:

~~~c
jint patch[3] = {7, 8, 9};

(*env)->SetIntArrayRegion(env, numbers, 2, 3, patch);
if ((*env)->ExceptionCheck(env)) {
    return;
}
~~~

If `numbers` was previously `[10, 20, 30, 40, 50, 60]`, after a valid write it will be:

~~~text
[10, 20, 7, 8, 9, 60]
~~~

`SetIntArrayRegion` does **not** “take ownership” of the `patch` memory. The Java array holds a copy of the values; after the API completes, the C buffer can continue to be used or freed according to C rules. For primitive types, there is no `jobject` or separate local reference per element.

Do not call `Set<Type>ArrayRegion` when `buf` points to uninitialized memory or has fewer elements than required. The JVM cannot infer the capacity of a raw C pointer, so a capacity error can become an invalid memory access rather than a catchable Java exception.

## 6. Complete Java 17 + JNI C Example: Copying a Slice and Writing a Region

We build two native methods:

1. `copyRegion(int[] source, int start, int len)` creates a new Java array and copies the source region in small chunks: **Get from source array → C buffer → Set into result array**.
2. `fillRegion(int[] destination, int start, int len, int value)` prepares a `jint` buffer containing the value to write and uses **Set into an existing Java array**.

Both verify bounds. The fixed buffer of eight `jint` elements avoids `malloc` and avoids holding Java elements across multiple JNI calls. This example uses a class in the **default package** so JNI names and build commands are easy to test.

### 6.1. File `JniRegionDemo.java`

~~~java
import java.util.Arrays;

public final class JniRegionDemo {
    static {
        System.loadLibrary("jniregiondemo");
    }

    private static native int[] copyRegion(
            int[] source, int start, int length);

    private static native void fillRegion(
            int[] destination, int start, int length, int value);

    public static void main(String[] args) {
        int[] numbers = {10, 20, 30, 40, 50, 60};

        int[] part = copyRegion(numbers, 1, 3);
        System.out.println("part=" + Arrays.toString(part));

        fillRegion(numbers, 2, 2, 99);
        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("partAfterWrite=" + Arrays.toString(part));

        int[] empty = copyRegion(numbers, numbers.length, 0);
        System.out.println("empty=" + Arrays.toString(empty));

        try {
            copyRegion(numbers, 5, 2);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println(
                    "bounds=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Meaning of the test cases:

- `copyRegion(numbers, 1, 3)` selects three elements `20, 30, 40` and creates a **new array**, sharing no storage with `numbers`.
- `fillRegion(numbers, 2, 2, 99)` writes into indices `2` and `3` of the original array.
- `part` remains unchanged even after `numbers` is modified, because `Get/Set...ArrayRegion` created **value copies**, not a Java array view.
- `copyRegion(numbers, numbers.length, 0)` returns `int[0]`; it does not call the region function with `len == 0`.
- `copyRegion(numbers, 5, 2)` is out of bounds and is rejected before copying.

### 6.2. Generating the JNI Header

Using JDK 17+ in the directory containing the Java file:

~~~bash
javac -h . JniRegionDemo.java
~~~

This command generates `JniRegionDemo.class` and `JniRegionDemo.h`. The header is generated according to the exact signatures of the two native methods. Whenever you change the class/package or overload a native method, you must regenerate the header and rebuild the corresponding C code.

### 6.3. File `jniregiondemo.c`

~~~c
#include "JniRegionDemo.h"

#define BLOCK_SIZE 8

/* Helper function that throws a Java exception when no exception is pending. */
static void throw_java(JNIEnv *env, const char *class_name,
                       const char *message) {
    jclass exception_class = (*env)->FindClass(env, class_name);
    if (exception_class == NULL) {
        return; /* Preserve the exception thrown by FindClass. */
    }

    (*env)->ThrowNew(env, exception_class, message);
    (*env)->DeleteLocalRef(env, exception_class);
}

/* Safe bounds check: avoids start + count overflow. */
static jboolean valid_range(JNIEnv *env, jintArray array,
                            jint start, jint count) {
    if (array == NULL) {
        throw_java(env, "java/lang/NullPointerException",
                   "array must not be null");
        return JNI_FALSE;
    }

    jsize length = (*env)->GetArrayLength(env, array);
    if (start < 0 || count < 0 ||
        start > length || count > length - start) {
        throw_java(env, "java/lang/ArrayIndexOutOfBoundsException",
                   "invalid start or length");
        return JNI_FALSE;
    }

    return JNI_TRUE;
}

JNIEXPORT jintArray JNICALL
Java_JniRegionDemo_copyRegion(
        JNIEnv *env, jclass clazz, jintArray source,
        jint start, jint count) {
    (void)clazz;

    if (!valid_range(env, source, start, count)) {
        return NULL;
    }

    jintArray result = (*env)->NewIntArray(env, count);
    if (result == NULL) {
        return NULL; /* Preserve the JVM allocation error. */
    }

    jint buffer[BLOCK_SIZE];

    for (jsize copied = 0; copied < count; ) {
        jsize remaining = count - copied;
        jsize batch = remaining < BLOCK_SIZE
                ? remaining : BLOCK_SIZE;

        /* Copy from source[start + copied] into buffer[0]. */
        (*env)->GetIntArrayRegion(
                env, source, start + copied, batch, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return NULL;
        }

        /* Copy from buffer[0] into result[copied]. */
        (*env)->SetIntArrayRegion(
                env, result, copied, batch, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return NULL;
        }

        copied += batch;
    }

    return result;
}

JNIEXPORT void JNICALL
Java_JniRegionDemo_fillRegion(
        JNIEnv *env, jclass clazz, jintArray destination,
        jint start, jint count, jint value) {
    (void)clazz;

    if (!valid_range(env, destination, start, count)) {
        return;
    }

    jint buffer[BLOCK_SIZE];
    for (jsize i = 0; i < BLOCK_SIZE; ++i) {
        buffer[i] = value;
    }

    for (jsize written = 0; written < count; ) {
        jsize remaining = count - written;
        jsize batch = remaining < BLOCK_SIZE
                ? remaining : BLOCK_SIZE;

        (*env)->SetIntArrayRegion(
                env, destination, start + written, batch, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return;
        }

        written += batch;
    }
}
~~~

**Code walkthrough:**

1. `valid_range` uses `GetArrayLength` to check `start` and `count`. When the array is `null`, it throws `NullPointerException`; when the region is out of bounds, it throws `ArrayIndexOutOfBoundsException`. Both branches return before calling the region API with invalid arguments.
2. `NewIntArray` creates the destination Java array with `count` elements. If allocation fails, `result` must not be used as a valid array.
3. `GetIntArrayRegion` copies at most eight elements from source to `buffer`, and `SetIntArrayRegion` copies those same eight elements to result. The loop handles arbitrarily long arrays in multiple chunks while using a fixed amount of stack memory.
4. `fillRegion` prepares eight `jint` elements with `value`, then uses `SetIntArrayRegion` to write consecutive blocks. No `Get` is needed because this write does not depend on previous values.
5. `ExceptionCheck` is called immediately after each region API; if an exception occurred, the native method stops. With `GetIntArrayRegion`/`SetIntArrayRegion`, **there is no `ReleaseIntArrayRegion`**.
6. `result` is a local JNI reference returned to Java, which the JVM handles when the native method returns. The `jint[8]` buffer is on the C stack; do not return this buffer's address to Java.

There is no `DeleteLocalRef` call for `result` on the success path because we are returning it to Java. On error paths, unreturned local references are reclaimed by the JVM when the native frame exits.

### 6.4. Building the Native Library by Operating System

Use a **JDK with JNI headers** and a native compiler matching the OS and the JVM's architecture/ABI. Each command group below is for one environment; do not run them simultaneously.

**Linux — GCC:**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  jniregiondemo.c -o libjniregiondemo.so

java -Djava.library.path=. JniRegionDemo
~~~

**macOS — Clang:**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  jniregiondemo.c -o libjniregiondemo.dylib

java -Djava.library.path=. JniRegionDemo
~~~

**Windows — MSVC Developer Command Prompt:**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jniregiondemo.c /Fe:jniregiondemo.dll
java -Djava.library.path=. JniRegionDemo
~~~

`System.loadLibrary("jniregiondemo")` uses a **logical name**; the JVM resolves the filename according to OS conventions (such as `libjniregiondemo.so`, `libjniregiondemo.dylib`, `jniregiondemo.dll`). If the library is not found or the binary does not match the ABI, you may encounter `UnsatisfiedLinkError` before the program prints any output. On Windows, the `cl` command must be run in an environment configured with the MSVC compiler. If the project has a Java package other than the default package, use the new JNI header and corresponding lookup name.

### 6.5. Exact Output When Compiled and Loaded Successfully

~~~text
part=[20, 30, 40]
numbers=[10, 20, 99, 99, 50, 60]
partAfterWrite=[20, 30, 40]
empty=[]
bounds=ArrayIndexOutOfBoundsException
~~~

Explanation in order:

- `part` takes `numbers[1..3]`, so it is `[20, 30, 40]`.
- `fillRegion(numbers, 2, 2, 99)` replaces `numbers[2]` and `numbers[3]` with 99. `numbers[4]` and `numbers[5]` are unchanged.
- `part` was created by `NewIntArray` and copied using the region API: modifying `numbers` does not change `part`.
- The empty region `start = numbers.length`, `length = 0` returns a new array of length 0.
- `start=5`, `len=2` on an array of length 6 is rejected by `valid_range`, so Java catches `ArrayIndexOutOfBoundsException`.

Point to distinguish: this program **proactively throws an exception from a JNI helper** if the bounds are invalid. The `Get/Set<Type>ArrayRegion` functions themselves also specify `ArrayIndexOutOfBoundsException` for an invalid region; checking beforehand avoids calling the API when input data is already invalid and makes the conditions clear in the code.

## 7. When to Allocate a Buffer and Manage Capacity?

In the example, `jint buffer[8]` is fixed, so there is no risk of using a buffer smaller than `batch`, because `batch <= BLOCK_SIZE`. If you want to copy all `len` elements at once with `malloc`, you must check the size first:

~~~c
/* Illustrative snippet: assumes len > 0 and the Java region is valid. */
if ((size_t)len > SIZE_MAX / sizeof(jint)) {
    /* Cannot represent the number of bytes to allocate. */
    return;
}

jint *buffer = malloc((size_t)len * sizeof(jint));
if (buffer == NULL) {
    /* Report error and return; do not pass NULL to the region API. */
    return;
}

/* Copy, check for errors, then free(buffer) on all paths. */
free(buffer);
~~~

The snippet above **is not a standalone native function**: it requires `#include <stdint.h>` (for `SIZE_MAX`), `#include <stdlib.h>` (for `malloc`/`free`), and an appropriate Java error-reporting mechanism. The code illustrates the checks needed before allocating.

For small `len`, a stack buffer is simple. For large `len`, a dynamically allocated buffer can consume a lot of RAM; a fixed buffer copying in chunks is often easier to control. Whichever approach you use, do not pass a `buf` without sufficient space: because a native pointer carries no capacity information, the JVM cannot protect the application from all C buffer overflows.

### Copying Is Not Inherently Atomic

`GetIntArrayRegion` does not define a transaction or a snapshot synchronized across threads. If another Java thread modifies the same array while native code copies multiple chunks, different parts may reflect different points in time. With `SetIntArrayRegion`, other threads may also observe the array being updated piecemeal. When cross-thread consistency is required, synchronization must be implemented at the application layer: locks, a pre-created snapshot, or an ownership design with no competing writers.

## 8. Comparison with GetArrayElements/ReleaseArrayElements

These are two different management models:

| Criterion | `Get/Set<Type>ArrayRegion` | `Get/Release<Type>ArrayElements` |
|---|---|---|
| Data to operate on | A slice `start,len`; can also copy the whole array | Accesses array elements via a returned pointer |
| Where does the buffer come from? | **Caller-provided**; JVM copies data in/out | JVM returns a pointer, which may be a **copy or a pinned region** |
| Release required? | **No Release...ArrayRegion** | **Must Release** a non-null returned pointer |
| Two-way copying | `Get` to read, `Set` to write | Modify through the pointer; `Release` mode controls copy-back/freeing |
| Holding the pointer long-term? | Just a native buffer you manage | Must follow the Release contract; do not hold after Release |
| Using for a small slice | Clear, no need to hold the entire array | May be overkill if only a few elements are needed |
| Limitations | Copies data; call overhead if too many small chunks | Must handle copy/pin, release mode, lifetime, and GC impact |

When using `GetIntArrayElements`:

~~~c
jboolean is_copy;
jint *elements = (*env)->GetIntArrayElements(env, array, &is_copy);
if (elements == NULL) {
    return; /* May be an allocation error or an exception. */
}

/* Read/write elements[index] within the array length bounds. */

(*env)->ReleaseIntArrayElements(env, array, elements, 0);
~~~

This is an **illustrative JNI C snippet** inside a native method returning `void`, assuming `array` is valid. `is_copy == JNI_FALSE` indicates that the JVM may allow direct array access rather than creating a copy, though this cannot be inferred before calling. Once `elements` is successfully obtained, it must be released properly; mode `0` is commonly used to copy back (if it was a copy) and free the corresponding buffer. `JNI_ABORT` discards copying back a copy, while `JNI_COMMIT` copies back without necessarily freeing the copy buffer.

**`GetPrimitiveArrayCritical` is different again:** it has special restrictions, such as not blocking threads or making arbitrary JNI calls while inside a critical region. Do not use it just to copy a few elements; the region API is clearer and safer for that task.

Do not claim that `Get/Set<Type>ArrayRegion` is always faster or slower than `Get/Release<Type>ArrayElements`. Performance depends on the JVM, sizes, call counts, and memory management. For tasks that only need a small slice, start with the region API; benchmark in a real environment if performance is a critical requirement.

## 9. Differences by Data Type

### `byte[]` and File/Network Data

`GetByteArrayRegion` copies `jbyte` values, but Java's `byte` is signed from -128 to 127. If C needs to display bytes as 0–255, explicitly interpret them as unsigned when needed; do not treat `jbyte` as a character code.

~~~c
jbyte header[4];

(*env)->GetByteArrayRegion(env, data, 0, 4, header);
if ((*env)->ExceptionCheck(env)) {
    return;
}

/* header contains four jbyte values; it does not contain a '\0' string terminator. */
~~~

This is a JNI code snippet for a function returning `void`, where `data` is already guaranteed to be a `jbyteArray` containing at least four elements. Do not use `strlen` on raw byte buffers; binary data can contain `0` at any position.

### `char[]` Is Not a C/UTF-8 String

`jchar` is a UTF-16 code unit, not necessarily a full Unicode code point (it may be half of a surrogate pair). Use `GetCharArrayRegion` with `jchar[]` when working with a Java `char[]`. Do not cast `jchar*` to `char*` and treat it as UTF-8 or a NUL-terminated C string.

### `boolean[]`

JNI `jboolean` is typically represented as an 8-bit element and uses the logical values `JNI_FALSE` (0) / `JNI_TRUE` (1). If creating a buffer to write to `boolean[]`, use those JNI constants rather than assuming any non-zero byte value is normalized the way you expect.

### `long[]`, `float[]`, `double[]`

Use `jlong`, `jfloat`, `jdouble`; do not arbitrarily use C `long` or `double` just because they "look like the same name". JNI defines concrete mappings between Java primitives and native types. `len` is still measured in **elements**; for example, `SetDoubleArrayRegion(array, 3, 2, buffer)` writes two `double` numbers at indices 3 and 4.

## 10. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `GetArrayRegion` by that literal name | No corresponding concrete JNI function exists | Use `GetIntArrayRegion`, `GetByteArrayRegion`, etc., according to type |
| Confusing `len` with the ending index | Copies too many elements or goes out of bounds | Describe the region as `[start, start+len)` |
| Confusing elements with bytes | Under-allocates buffer, reads/writes incorrectly | Buffer must have at least `len * sizeof(NativeType)` bytes |
| `start + len` causing signed overflow | Incorrect bounds check | Use `start > n || len > n-start` after ruling out negative numbers |
| Calling region with `array == NULL` | Violates JNI precondition, may crash | Check for `NULL` first and throw `NullPointerException` |
| Using `buf == NULL` or an undersized buffer | Invalid native memory access | Ensure a valid pointer and sufficient capacity |
| Ignoring exceptions because the function returns `void` | Native code continues in a broken JNI state | `ExceptionCheck` and return/cleanup |
| Modifying the buffer after `Get` expecting Java to change | Java array has not been copied back | Call `Set<Type>ArrayRegion` when intending to write |
| Looking for `ReleaseIntArrayRegion` | JNI has no such Release API | Manage the native buffer yourself; only ArrayElements needs Release |
| Using `GetObjectArrayRegion` | No region family exists for `Object[]` | Use `GetObjectArrayElement`/`SetObjectArrayElement` |
| Using a short buffer for a large `len` | Stack/native heap overflow, may crash the JVM | Check length or split into chunks |
| Writing multiple chunks and assuming atomicity | Other threads may see partially updated data | Synchronize at the application layer |
| Copying in-place between overlapping regions with a forward loop | Later chunks may read data that was just overwritten | Use an intermediate snapshot or an explicit overlap-safe algorithm |

### Be Careful When Copying Between Overlapping Regions

If you read all of `source[start..start+len)` into a sufficiently large native buffer **before calling Set**, a subsequent `Set` into another region of the same Java array can rely on the original copy and avoid overwriting the source of that copy itself.

Conversely, an algorithm that `Get`s one chunk and immediately `Set`s that chunk, looping forward from left to right, **is not equivalent to `memmove`** when source and destination are the same array and the two regions overlap in a direction that risks overwriting unread elements. For example, copying `[1,2,3,4]` to a region starting one index later with a forward loop easily loses elements that still need to be read. To support overlap, choose the appropriate copy direction or read an independent snapshot before writing. The runnable example in this lesson creates a **new destination array**, so it does not encounter this aliasing issue.

## 11. JNI Exceptions, Cleanup, and Lifecycle

`Get<Type>ArrayRegion`/`Set<Type>ArrayRegion` return `void`, so bounds errors are represented by a **pending Java exception**, such as `ArrayIndexOutOfBoundsException`. When an exception is detected:

1. Stop processing the result of the failed region call; do not assume the native buffer contains all desired data.
2. Leave the Java exception pending so the Java caller receives it, unless you actually have an error-handling/replacement flow.
3. If a buffer was allocated with `malloc`, free it with `free` before returning. If global references were created, manage their lifecycle according to ownership. JNI local-reference cleanup operations permitted while an exception is pending may be called.
4. Do not continue calling arbitrary JNI functions while an exception is pending; use `ExceptionCheck` to inspect, and `ExceptionClear` only when you are actively handling the exception.

If an error occurs after `Set` has written some chunks, the Java array **may have been partially modified**. This differs from throwing an exception before any operation via prevalidation. If an operation must be all-or-nothing, design the computation step into a new buffer/array and commit in a controlled manner; do not assume a sequence of JNI calls is a transaction.

A reference to a Java array, such as `jintArray`, is a JNI object reference. A `jint*` buffer on the C stack/heap is a different memory region. Do not cache `JNIEnv*` across threads, and do not keep a stack pointer after a native call ends; when other JNI callbacks operate on the same Java array, establish synchronization rules.

## 12. Exercises with Answers

**Exercise 1 — Predict the copy.** Java has `int[] a = {1, 2, 3, 4, 5};`. JNI calls `GetIntArrayRegion(a, 1, 3, buf)`. What does the buffer contain? **`{2, 3, 4}`**, because it starts at index 1 and copies three elements.

**Exercise 2 — Effect of writing.** With the same array above and `jint patch[2] = {8, 9};`, call `SetIntArrayRegion(a, 2, 2, patch)`. The array becomes **`{1, 2, 8, 9, 5}`**. Indices outside 2–3 keep their old values.

**Exercise 3 — Overflow check.** An array has length 6; `start = 5`, `len = 2`. The condition `len > n - start` becomes `2 > 1`, so the region is invalid. In the runnable example, the helper throws `ArrayIndexOutOfBoundsException` before copying.

**Exercise 4 — Only part of a byte array.** A `byte[]` is 1000 bytes long, but native code only needs a 12-byte header starting at index 4. Use `GetByteArrayRegion(array, 4, 12, header)` with a pre-sized `jbyte header[12]`, rather than taking a pointer to the entire array and risking forgetting `ReleaseByteArrayElements`.

**Exercise 5 — Lifecycle.** If a C function creates `jint buffer[8]`, calls `GetIntArrayRegion` successfully, and returns, is the Java array lost? **No**. The native buffer becomes invalid when C returns, while the Java array is managed by the JVM; copying data does not transfer ownership of the Java object to C code.

**Exercise 6 — Object array.** A `String[]` needs its 3rd element updated. Can `SetStringArrayRegion` be used? **No.** JNI uses `SetObjectArrayElement` with a valid `jstring` and a checked index; `String[]` does not belong to the primitive arrays family.

## References

- [Oracle Java SE 17 JNI Function Specification — Get/Set<PrimitiveType>ArrayRegion](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getprimitivetypearrayregion-routines).
- [Oracle Java SE 17 JNI Functions — GetArrayLength, Get/Release<PrimitiveType>ArrayElements, critical access](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html).
- [Oracle Java SE 17 JNI Types — primitive types, jarray and jsize](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html).

## Key Takeaways

- **`Get<Type>ArrayRegion` = Java array → native buffer; `Set<Type>ArrayRegion` = native buffer → Java array.** These two APIs copy a slice of a primitive array and **have no Release counterpart**.
- `start` is an index and `len` is an element count; check region bounds safely using `start >= 0`, `len >= 0`, `start <= n`, and `len <= n-start`.
- The C buffer must have enough space, the JNI type must match the Java array type exactly, and any pending exception must be handled properly.
- For small regions or chunked copying, the region API is very clear; for pointers from `Get<Type>ArrayElements`, you must use `Release<Type>ArrayElements` according to its own contract.
- Region copying does not create a lock, transaction, or atomic copy across threads. If consistency is needed, design explicit synchronization and ownership.
