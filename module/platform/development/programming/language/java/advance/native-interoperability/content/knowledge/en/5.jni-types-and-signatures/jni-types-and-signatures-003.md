# `jobject`, `jclass`, `jstring`, and array types are opaque references in JNI

## 1. Understanding “opaque reference” correctly

When Java calls a native method using the **Java Native Interface (JNI)**, a Java object can be passed to a C/C++ function as a `jobject`, `jclass`, `jstring`, `jarray`, or subtypes such as `jintArray` and `jobjectArray`. Those values are **references managed by the JVM**: native code is allowed to use them to call the appropriate JNI functions, but **must not assume it knows the address, memory layout, or internal structure of the Java object**.

“Opaque reference” means the internal representation is hidden from application code:

- You cannot safely treat `jobject` as a C pointer to a `struct` holding Java fields.
- You cannot use `jstring` like `char*`, because `jstring` is a reference to a **`java.lang.String` object**, not a NUL-terminated C byte array.
- You cannot treat `jintArray` as `jint*` and access it with `numbers[i]`; you must use `JNIEnv` array APIs to read or write.
- You cannot treat `jclass` as a pointer to a C++ type or a JVM class metadata structure; it is a reference to a **`java.lang.Class` object**.

The JVM may move objects in the Java heap when garbage collection (GC) occurs. **A JNI reference is a valid handle under the JNI contract**, allowing native code to reference an object within the specified lifetime scope without depending on the object's current physical location. Do not infer the handle's structure or perform pointer arithmetic on a JNI reference.

~~~text
Java heap                                Native JNI frame
+------------------------+               +----------------------+
| String ("Java")         |<-- JVM ------| jstring text         |
| StringBuilder ("node")  |<-- references| jobject value        |
| int[] {2, 3, 5}       |<--------------| jintArray numbers    |
| String[] {"a", "b"}    |<--------------| jobjectArray labels  |
| Class<StringBuilder>   |<--------------| jclass actualClass   |
+------------------------+               +----------------------+
      JVM manages layout                     C/C++ holds JNI handles
      and object liveness                    within valid scope
~~~

The arrows represent a logical relationship, **not claiming that each JNI reference directly contains the object's address**. When reading/writing values is needed, native code calls `(*env)->...` in C, or `env->...` in C++.

## 2. The JNI type system: primitives versus references

JNI divides data types into two broad groups.

**Primitive types** represent values corresponding to Java primitive types:

| Java | JNI | Meaning |
| --- | --- | --- |
| `boolean` | `jboolean` | JNI's boolean representation type, using constants `JNI_TRUE`/`JNI_FALSE` where appropriate |
| `byte` | `jbyte` | Signed 8-bit integer |
| `char` | `jchar` | Unsigned 16-bit UTF-16 code unit |
| `short` | `jshort` | Signed 16-bit integer |
| `int` | `jint` | Signed 32-bit integer |
| `long` | `jlong` | Signed 64-bit integer |
| `float` | `jfloat` | 32-bit float |
| `double` | `jdouble` | 64-bit float |

**Reference types** represent JVM objects or specialized forms of them:

| JNI type | Corresponding Java object | Common usage |
| --- | --- | --- |
| `jobject` | Any Java object | Object parameter/return value, instance receiver |
| `jclass` | `java.lang.Class` | Getting a class, looking up methods/fields, calling static methods |
| `jstring` | `java.lang.String` | Reading string length and contents via JNI APIs |
| `jarray` | Any Java array | Base type receiving an array reference |
| `jobjectArray` | Object arrays such as `String[]`, `Object[]` | Reading/writing each element as a JNI object reference |
| `jbooleanArray`, `jbyteArray`, `jcharArray`, `jshortArray`, `jintArray`, `jlongArray`, `jfloatArray`, `jdoubleArray` | Corresponding primitive arrays | Accessing data via `Get...ArrayRegion` or `Get...ArrayElements` |
| `jthrowable` | `java.lang.Throwable` | Working with an exception object |
| `jweak` | Weak global JNI reference | Weak reference; the target may be cleared by GC |

**`jsize`** is the type used for sizes/indices in many JNI APIs. **`jmethodID` and `jfieldID` are not `jobject`**: they are JVM method/field identifiers, do not follow local/global object reference rules, and must not be used as an object. **`jvalue`** is a union holding values for method calls with `...A`-style parameter lists; it is also not a JNI object reference.

In `jni.h`, C typedefs and C++ definitions may be presented differently, but **you must not rely on the current typedef to interpret the internal structure of an object**. For example, the C header may alias multiple reference types to an opaque pointer form; the specialized type names still serve to express the API contract and avoid confusion.

## 3. `jobject` and `jclass`: instance object versus `Class` object

Here are the two situations in JNI:

~~~java
// Illustrative Java, not a standalone program
class Example {
    native int instanceWork(String text);
    static native int staticWork(String text);
}
~~~

The corresponding C functions have the form:

~~~c
/* Illustrative signatures; actual names should be obtained from javac -h. */
JNIEXPORT jint JNICALL Java_Example_instanceWork(
        JNIEnv *env, jobject receiver, jstring text);

JNIEXPORT jint JNICALL Java_Example_staticWork(
        JNIEnv *env, jclass declaringClass, jstring text);
~~~

- `JNIEnv*` provides JVM functions for **the calling thread**. Do not save and reuse `JNIEnv*` from another thread.
- For an **instance native method**, the second JNI parameter is a `jobject` referencing the receiver (`this` in Java).
- For a **static native method**, the second JNI parameter is a `jclass` referencing the `Class` object that declares the method.
- A Java parameter of type `String` becomes `jstring`; Java type `Object` becomes `jobject`.

Useful functions for working with objects/classes:

| JNI function | Purpose |
| --- | --- |
| `GetObjectClass(env, obj)` | Returns the `jclass` representing the actual class of the object |
| `FindClass(env, "java/lang/String")` | Looks up a class by its slash-delimited JNI name |
| `IsInstanceOf(env, obj, clazz)` | Checks type compatibility of an object with a class |
| `IsSameObject(env, a, b)` | Checks whether two references point to **the same Java object** |
| `GetMethodID` / `GetStaticMethodID` | Gets the method ID for an instance/static call |
| `GetFieldID` / `GetStaticFieldID` | Gets the field ID of an instance/static field |

**`jclass` is still an object reference**, so it has a local/global lifetime and can be retained with `NewGlobalRef` if it needs to persist across multiple native calls. Do not use `jclass` as an address into metaspace.

**Do not compare two JNI references with `a == b` to conclude they point to the same Java object**. Two handles may differ while referencing the same object; use `IsSameObject`. Checking whether a reference equals `NULL` is valid, but do not use pointer equality to determine object identity.

### Passing an object down to C/C++ does not transfer object ownership

The `jobject receiver` or `jobject value` parameter is normally a **local reference** valid during the current native call. The Java heap remains managed by the JVM. Native code must not call `free(value)`, `delete value`, or retain a local reference for later use after the method has returned.

## 4. `jstring`: a String reference, not a character buffer

`jstring` represents a Java `String` object. Java uses **UTF-16 code units** in APIs such as `String.length()`; JNI provides APIs with contracts for encoding and lifetime.

| JNI API | Result/usage | Obligation |
| --- | --- | --- |
| `GetStringLength(env, str)` | Number of **UTF-16 code units** in the string | Does not create a content pointer |
| `GetStringChars(env, str, ...)` | Pointer to read `jchar`s (UTF-16); the JVM may copy/pin | Call `ReleaseStringChars` |
| `GetStringUTFChars(env, str, ...)` | NUL-terminated byte string in JNI's **Modified UTF-8** format | Call `ReleaseStringUTFChars` |
| `GetStringUTFLength(env, str)` | Number of bytes in **Modified UTF-8** format (excluding trailing NUL) | Not equal to the number of Unicode characters nor necessarily equal to `GetStringLength` |
| `GetStringRegion` / `GetStringUTFRegion` | Copies a region of content into a caller-provided buffer | Check bounds/capacity; `GetStringUTFRegion` does not guarantee adding a trailing NUL |
| `NewString` / `NewStringUTF` | Creates a Java String from UTF-16 or Modified UTF-8 | Correct encoding; result is a local `jstring` |

For example, the Java string `"A😀B"` has **4 UTF-16 code units**: the letter A (1), the emoji 😀 (2 surrogate units), and the letter B (1). It has **3 Unicode code points**. Therefore:

~~~java
// Illustrative Java code inside a method:
String text = "A\uD83D\uDE00B";
System.out.println(text.length());             // 4
System.out.println(text.codePointCount(0, text.length())); // 3
~~~

When sending `text` over JNI, `GetStringLength` returns `4`, not `3`. In addition, **Modified UTF-8 is not completely identical to standard UTF-8**: for example, the character U+0000 is encoded specially; surrogates have their own representation rules. Do not pass bytes from `GetStringUTFChars` directly to an API expecting standard UTF-8 without verifying/converting the encoding properly.

Example C code in a native method:

~~~c
/* Illustrative when text is a valid jstring and env belongs to the current thread. */
jsize units = (*env)->GetStringLength(env, text);
const jchar *chars = (*env)->GetStringChars(env, text, NULL);
if (chars == NULL) {
    return 0; /* Usually there is a pending exception such as OutOfMemoryError. */
}
/* Only read chars[0..units-1] while this region is still valid. */
(*env)->ReleaseStringChars(env, text, chars);
~~~

`chars` is a **pointer to a content region granted temporary access by JNI**, completely different from **`jstring`, which is an object reference**. Do not call `free(chars)` yourself. You must release with the matching API even when the JVM provided a copy; do not keep the pointer past the release point.

## 5. JNI arrays: `jarray` and specialized array types

A Java array is still a Java object; `jarray` and the specific types are **opaque references**, not pointers pointing directly to C elements.

| Java array | JNI parameter | Commonly used APIs |
| --- | --- | --- |
| `int[]` | `jintArray` | `GetArrayLength`, `GetIntArrayRegion`, `GetIntArrayElements`, `SetIntArrayRegion` |
| `byte[]` | `jbyteArray` | `GetByteArrayRegion`, `GetByteArrayElements`, `SetByteArrayRegion` |
| `double[]` | `jdoubleArray` | `GetDoubleArrayRegion`, `GetDoubleArrayElements` |
| `String[]` | `jobjectArray` | `GetObjectArrayElement`, `SetObjectArrayElement` |
| `Object[]` | `jobjectArray` | `GetObjectArrayElement`, `SetObjectArrayElement` |
| `int[][]` | `jobjectArray` at the **outer dimension** | Get each row with `GetObjectArrayElement` then process as `jintArray` |

### 5.1. Primitive arrays: reading a data region with Region

~~~c
/* Illustrative in a native method receiving jintArray numbers; length must be checked. */
jint firstThree[3];
jsize n = (*env)->GetArrayLength(env, numbers);
if (n >= 3) {
    (*env)->GetIntArrayRegion(env, numbers, 0, 3, firstThree);
    if ((*env)->ExceptionCheck(env)) {
        return 0;
    }
    /* firstThree now contains 3 integers copied from the Java array. */
}
~~~

`GetIntArrayRegion` **copies** the specified number of elements into a caller-owned C buffer; the caller does not need `ReleaseIntArrayRegion`. If the access is out of bounds, the JVM may throw an exception. Exceptions must be handled before using the buffer.

### 5.2. Primitive arrays: accessing with Elements

~~~c
/* Illustrative when numbers is a valid jintArray. */
jsize n = (*env)->GetArrayLength(env, numbers);
jint *elements = (*env)->GetIntArrayElements(env, numbers, NULL);
if (elements == NULL) {
    return 0;
}
jint sum = 0;
for (jsize i = 0; i < n; i++) {
    sum += elements[i];
}
(*env)->ReleaseIntArrayElements(env, numbers, elements, JNI_ABORT);
~~~

The JVM **may copy or pin** the array; never assume zero-copy by default. `JNI_ABORT` indicates that modifications do not need to be copied back on release, suitable for **read-only** cases like the example. If the code modified the buffer and wants to update the Java array, choose the appropriate release mode (`0` to update and release according to the contract). The `JNI_COMMIT` mode may copy changes back without **yet freeing the buffer**, so a subsequent release step is still required per the API contract.

### 5.3. Object arrays: each element is itself a JNI reference

~~~c
/* Illustrative when labels is a jobjectArray containing String. */
jsize n = (*env)->GetArrayLength(env, labels);
if (n > 0) {
    jobject element = (*env)->GetObjectArrayElement(env, labels, 0);
    if ((*env)->ExceptionCheck(env)) {
        return 0;
    }
    if (element != NULL) {
        jsize units = (*env)->GetStringLength(env, (jstring) element);
        /* Use units as needed. */
        (*env)->DeleteLocalRef(env, element);
    }
}
~~~

`GetObjectArrayElement` returns a **local reference**, even though the Java array element may remain alive after the native method returns. Consider deleting local refs inside large loops to avoid increasing pressure on the JNI reference table. Casting from `jobject` to `jstring` is only valid if **the actual Java type is known** to be `String`; do not turn an arbitrary object into a `jstring` by casting and then call String APIs.

With `GetPrimitiveArrayCritical` or `GetStringCritical`, the JVM may impose strict constraints during the critical period: avoid calling arbitrary JNI functions or performing long blocking operations; read the critical access contract and release as soon as possible.

## 6. Lifetimes of local, global, and weak global references

`jobject`/`jclass`/`jstring`/arrays express the **object type**. Meanwhile, local/global/weak global are **lifetime scope and object-retention strength**, which is a different classification dimension.

| Reference type | How is it created? | Scope and responsibility |
| --- | --- | --- |
| **Local** | JNI parameters, `GetObjectClass`, `FindClass`, `GetObjectArrayElement`, `NewStringUTF`, ... | Normally valid until the native call ends or until `DeleteLocalRef`/`PopLocalFrame`; use only in the appropriate thread context |
| **Global** | `NewGlobalRef(env, ref)` | Keeps the object reachable until `DeleteGlobalRef`; can be used across multiple native calls and properly attached threads |
| **Weak global** | `NewWeakGlobalRef(env, ref)` | Does not keep the object alive on its own; GC may clear the object, must handle null results and use `DeleteWeakGlobalRef` properly |

Key points:

1. **Do not store a local ref** in a C/C++ global variable, native handle, or queue for use after the native method returns. Doing so can become a use-after-invalid-reference bug.
2. If you genuinely need to keep an object across multiple calls, create a **global ref** and delete it at the right time. `NewGlobalRef` does not copy the Java object; it creates another reference with a longer lifetime.
3. A global reference keeps the object alive, so **forgetting `DeleteGlobalRef` retains the object unnecessarily** and can cause a memory leak at the JNI/heap level.
4. A weak global may be cleared by GC at any time between observations. If you need to use the object, **create a strong local ref with `NewLocalRef(env, weakRef)`**, check for `NULL`, and then operate on the new local within the valid scope.
5. **`JNIEnv*` is bound to a thread**. A global reference can be shared across properly attached threads, but the Java object itself **does not automatically become thread-safe**; synchronization is still required if there is concurrent access.

Example pattern when you want to keep an object from one JNI call to another:

~~~c
/* The following snippets illustrate logic in native code, not a standalone function. */
static jobject saved = NULL;

/* When saving, inside a properly synchronized JNI call: */
saved = (*env)->NewGlobalRef(env, incoming);
if (saved == NULL) {
    /* Check null/OOME and do not use saved. */
}

/* When no longer needed: */
if (saved != NULL) {
    (*env)->DeleteGlobalRef(env, saved);
    saved = NULL;
}
~~~

The illustrative code uses a global variable to show the lifetime; real-world applications must design **ownership**, synchronize all accesses to `saved`, avoid overwriting and leaking refs, and not free it while another thread is using it. For systems with multiple class loaders, one must also consider retaining classes/objects across deployment and unload cycles.

Local references created continuously in a loop can also fill up the local-ref table. Use `DeleteLocalRef` when finished, or `PushLocalFrame`/`PopLocalFrame` when needing to group many local refs. `GetObjectRefType` can report the type of a *valid* reference; do not use this API to “safely check” a pointer that has already been deleted or is not a JNI reference.

## 7. Complete runnable Java 17 + C/JNI example

The following program demonstrates **`jobject`, `jclass`, `jstring`, `jintArray`, and `jobjectArray`** together. The C function reads data only through JNI APIs, deletes local references it created itself, and releases the primitive array data region.

Example environment: **Linux + JDK 17+ + GCC matching the JVM's architecture**; the `JAVA_HOME` variable points to the JDK. No third-party libraries are needed.

### 7.1. File `OpaqueReferenceDemo.java`

~~~java
public final class OpaqueReferenceDemo {
    static {
        System.loadLibrary("opaque_refs");
    }

    private static native int score(
            Object value, String text, int[] numbers, String[] labels);

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";
        int result = score(
                new StringBuilder("node"),
                text,
                new int[]{2, 3, 5},
                new String[]{"alpha", "beta"});

        System.out.println("javaUtf16Units=" + text.length());
        System.out.println("score=" + result);
    }
}
~~~

Meaning: the first parameter is a Java object; the second is a `String` containing a character outside the BMP; the third parameter is a primitive `int[]` array; the last parameter is a reference `String[]` array. Java declares a `static native` method, so the JNI C function receives an additional `jclass declaringClass` in the second position.

### 7.2. File `opaque_refs.c`

~~~c
#include <jni.h>
#include "OpaqueReferenceDemo.h"

JNIEXPORT jint JNICALL Java_OpaqueReferenceDemo_score(
        JNIEnv *env,
        jclass declaringClass,
        jobject value,
        jstring text,
        jintArray numbers,
        jobjectArray labels) {

    (void) declaringClass;

    if (value == NULL || text == NULL
            || numbers == NULL || labels == NULL) {
        jclass ex = (*env)->FindClass(
                env, "java/lang/IllegalArgumentException");
        if (ex != NULL) {
            (*env)->ThrowNew(env, ex, "arguments must not be null");
            (*env)->DeleteLocalRef(env, ex);
        }
        return 0;
    }

    /* jclass is also a JNI reference, not a C++ class pointer. */
    jclass actual = (*env)->GetObjectClass(env, value);
    if (actual == NULL) {
        return 0;
    }

    jclass expected = (*env)->FindClass(
            env, "java/lang/StringBuilder");
    if (expected == NULL) {
        (*env)->DeleteLocalRef(env, actual);
        return 0;
    }
    jboolean sameType = (*env)->IsSameObject(
            env, actual, expected);

    /* jstring has a count of UTF-16 code units, not code points. */
    jsize textUnits = (*env)->GetStringLength(env, text);

    /* jintArray is accessed via APIs, not numbers[i]. */
    jsize count = (*env)->GetArrayLength(env, numbers);
    jint *elements = (*env)->GetIntArrayElements(
            env, numbers, NULL);
    if (elements == NULL) {
        (*env)->DeleteLocalRef(env, expected);
        (*env)->DeleteLocalRef(env, actual);
        return 0; /* The JVM has usually already set a pending exception. */
    }

    jint sum = 0;
    for (jsize i = 0; i < count; i++) {
        sum += elements[i];
    }
    (*env)->ReleaseIntArrayElements(
            env, numbers, elements, JNI_ABORT);

    /* Each object array element is a new local JNI reference. */
    jsize labelCount = (*env)->GetArrayLength(env, labels);
    jsize firstLabelUnits = 0;
    if (labelCount > 0) {
        jobject first = (*env)->GetObjectArrayElement(
                env, labels, 0);
        if ((*env)->ExceptionCheck(env)) {
            (*env)->DeleteLocalRef(env, expected);
            (*env)->DeleteLocalRef(env, actual);
            return 0;
        }
        if (first != NULL) {
            /* Java declared String[] so a non-null element is a String. */
            firstLabelUnits = (*env)->GetStringLength(
                    env, (jstring) first);
            (*env)->DeleteLocalRef(env, first);
        }
    }

    (*env)->DeleteLocalRef(env, expected);
    (*env)->DeleteLocalRef(env, actual);

    /* Only a small example calculation, not intended to handle general integer overflow. */
    return sum + textUnits + count + firstLabelUnits
            + (sameType ? 1 : 0);
}
~~~

**Points to observe in C:**

1. `jobject value` is still held by a local JNI reference; `GetObjectClass` returns an additional local `jclass`.
2. `FindClass` also returns a local `jclass`; `IsSameObject` compares two Java class objects. With `new StringBuilder("node")`, the condition is true.
3. `GetStringLength` of the string `A😀B` returns `4` UTF-16 code units.
4. `GetArrayLength(numbers)` returns `3`; `GetIntArrayElements` returns a temporary elements region, sum `2+3+5=10`; `ReleaseIntArrayElements(..., JNI_ABORT)` releases because it is read-only.
5. `GetObjectArrayElement(labels, 0)` returns a local reference for `"alpha"`; `GetStringLength` returns `5`; `DeleteLocalRef` frees the local handle, not `free`ing the Java object.
6. The two self-created local `jclass` references are also released with `DeleteLocalRef`. Parameters passed in from Java do not need to be deleted manually in the example.

This is complete illustrative code for **the lesson's fixed inputs**, not a general-purpose API for all array types or large sums. JNI errors with a pending Java exception must be handled at the application design level; the example returns immediately so the JVM propagates the existing exception back to Java. In production use, a clear error policy, exception checks, input constraints, and ownership tailored to the workload are required.

### 7.3. Compiling and running

Save both files in the same directory; from that directory:

~~~bash
javac -h . OpaqueReferenceDemo.java
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libopaque_refs.so opaque_refs.c
java -Djava.library.path=. OpaqueReferenceDemo
~~~

`javac -h .` generates the class file and `OpaqueReferenceDemo.h` with the exact JNI signature. `gcc -fPIC -shared` builds `libopaque_refs.so` for Linux; `System.loadLibrary("opaque_refs")` searches for the library by logical name in the configured `java.library.path`.

**Exact stdout** of the example on Linux/JDK 17+ when built successfully:

~~~text
javaUtf16Units=4
score=23
~~~

Calculation: `10` (sum of int array) + `4` (UTF-16 length) + `3` (number of `int[]` elements) + `5` (length of `"alpha"`) + `1` (matching class) = `23`.

On macOS, the library is typically named `libopaque_refs.dylib` and requires appropriate linking options such as `clang -dynamiclib` along with the JNI include `$JAVA_HOME/include/darwin`. On Windows, the name is typically `opaque_refs.dll` with JNI includes under `%JAVA_HOME%\include\win32` using MSVC/MinGW accordingly. **Java code, the JNI header, and the native binary ABI must match the platform exactly**.

## 8. JNI type signatures: how do `jobject`/`jstring`/arrays map?

JVM/JNI signatures use their own notation, not C typedef names. For the example's method:

~~~java
private static native int score(
        Object value, String text, int[] numbers, String[] labels);
~~~

The JVM descriptor is:

~~~text
(Ljava/lang/Object;Ljava/lang/String;[I[Ljava/lang/String;)I
~~~

Breakdown of each part:

| Descriptor component | Meaning |
| --- | --- |
| `Ljava/lang/Object;` | A reference to `Object` |
| `Ljava/lang/String;` | A reference to `String` |
| `[I` | Array `int[]`, corresponding to `jintArray` |
| `[Ljava/lang/String;` | Array `String[]`, corresponding to `jobjectArray` |
| `)I` | Method returns Java `int`/JNI `jint` |

Some common descriptors: `Ljava/lang/Class;` for `Class`, `[B` for `byte[]`, `[J` for `long[]`, `[[I` for `int[][]`, `V` for `void` (in the return type position). **An array is a reference type** even when its elements are primitives.

**Let `javac -h` generate the header**, especially when the class has a package, overloaded methods, or names containing characters that require encoding in the symbol name. The native entry point `Java_OpaqueReferenceDemo_score` here is simple because the class is in the default package and the method name is unique, but this is not a sufficient rule for guessing every JNI symbol manually. If `RegisterNatives` is used, native functions can be registered via a table instead of relying solely on exported names.

## 9. Reference safety: mistakes that easily cause crashes or leaks

### 9.1. Casting `jstring` to `char*`

**Wrong:**

~~~c
/* Wrong: jstring is not a C string! */
const char *bytes = (const char *) text;
printf("%s\n", bytes);
~~~

This snippet is invalid because `text` is an opaque reference. **Right approach**: use `GetStringUTFChars` and then `ReleaseStringUTFChars`; remember that the bytes obtained are **Modified UTF-8**, requiring conversion when the target API expects standard UTF-8.

### 9.2. Casting `jintArray` to `jint*`

**Wrong:**

~~~c
/* Wrong: jintArray is not a C int array pointer. */
jint *raw = (jint *) numbers;
jint first = raw[0];
~~~

**Right approach**: use `GetIntArrayRegion` or `GetIntArrayElements` and release according to the contract. If C needs to keep the data after the JNI call, create a C-owned copy or design a separate lifetime; do not keep an elements pointer that has already been released.

### 9.3. Saving a local `jobject` for later use by a native thread

**Lifetime error:**

~~~c
/* Wrong idea: keeping a JNI call's local ref after the method returns. */
static jobject cached;
cached = value;
~~~

**Right approach**: if needed for later use, call `NewGlobalRef` while the local ref is valid, synchronize access, and call `DeleteGlobalRef` when done. A native thread must attach to the JVM to obtain its own `JNIEnv*`; having a global ref **does not mean you can use the `JNIEnv*` of the thread that created the ref**.

### 9.4. Calling JNI APIs on a reference that is no longer valid

After `DeleteLocalRef`, `DeleteGlobalRef`, `PopLocalFrame`, or when a native call ends, terminated references **must not be accessed again**. Do not use `IsSameObject`, `GetObjectRefType`, or C casts to try to “revive” a destroyed reference.

### 9.5. Confusing object arrays with primitive arrays

`String[]` is `jobjectArray`, not `jstring*`; each element obtained from `GetObjectArrayElement` has a local-ref lifetime. `int[]` is `jintArray`, not `jobjectArray`; use only the corresponding primitive-array APIs.

### 9.6. Ignoring a pending Java exception

JNI APIs such as `FindClass`, `GetObjectArrayElement`, and `GetIntArrayElements` can fail and leave a pending exception. When a JNI API reports failure, do not continue assuming the result is valid. In many situations only a limited set of cleanup/exception handling APIs are permitted when an exception is pending. `ExceptionCheck` / `ExceptionOccurred` / `ExceptionClear` and appropriate release operations must be used deliberately; **do not arbitrarily clear an exception and return a success result**.

### 9.7. Deleting a local ref once does not solve every leak

Releasing a local reference does not make the Java object disappear if other references remain. Conversely, a remaining global reference can prevent GC from collecting the object. Check actual ownership: which local/global/weak references native code holds, who deletes them, and when.

## 10. Practical rules when designing Java–JNI APIs

- **Declare Java first, generate the header with `javac -h`.** Cross-check `jobject`, `jclass`, `jstring`, `jintArray`, and `jobjectArray` in the header instead of writing signatures from memory.
- **Use `JNIEnv` to manipulate objects.** Do not dereference, offset, perform pointer arithmetic, or call `free` on a JNI object reference.
- **Document ownership/lifetime clearly.** Local only within the native frame; global needs release; weak needs promotion and a null check before use.
- **Choose the data strategy based on need.** For primitive arrays needing few elements, `Get...ArrayRegion` is simple; for many elements, `Get...ArrayElements` may be appropriate but requires release; do not assume zero-copy.
- **Specify string encoding.** Distinguish UTF-16 code units, Unicode code points, Modified UTF-8, and standard UTF-8.
- **Pay attention to exceptions and threads.** `JNIEnv*` is not used across threads; every JNI call must handle error results and pending exceptions; shared objects still require appropriate synchronization/memory models.
- **Verify with JNI error-detection tools when needed.** On HotSpot, `-Xcheck:jni` can detect **some** incorrect JNI usage, but does not prove the entire native code is memory-safe.
- **Minimize the native surface area.** C/C++ should only receive the types/references truly needed and return objects/values via JNI APIs, letting Java continue managing objects while native ownership is explicitly described.

## 11. Self-check questions

1. Why cannot `jobject` be cast to a C pointer to access Java fields by offset?
2. In a static native method, what is the `jclass` received from the JVM? Is it a C++ class pointer?
3. A JNI function receives a `jstring`. Does `GetStringLength` return the number of UTF-8 bytes or UTF-16 code units?
4. Why must `GetIntArrayElements` be paired with `ReleaseIntArrayElements` even when the code only reads?
5. Why does `GetObjectArrayElement` return a local reference and why must it be handled differently from an ordinary C pointer?
6. If you need to keep a `jobject` after the native method returns, which reference type should you use and which API frees it?
7. Two different JNI references point to the same Java object. Which API should be used to compare object identity?
8. What JNI type does `int[][]` have at the outer array dimension? What type will each row element use?
9. Why should JNI's Modified UTF-8 bytes not be passed as standard UTF-8 data without a verification step?
10. What must a native thread keep in mind about `JNIEnv*` when it wants to use a global reference created on another thread?

**Suggested answers:** (1) opaque handle, object layout is managed by the JVM; (2) a `Class` object, not a C++ class pointer; (3) UTF-16 code units; (4) it may copy/pin, so it must be released or committed according to the mode; (5) local JNI lifetime and the JVM manages the object; (6) `NewGlobalRef`/`DeleteGlobalRef`; (7) `IsSameObject`; (8) `jobjectArray` on the outside, `jintArray` for each `int[]` row; (9) the two encodings have different rules; (10) the thread must attach and use its own `JNIEnv*`, while also guarding object access if needed.

## 12. Authoritative references

- [Oracle JNI Specification — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html)
- [Oracle JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)

**Core takeaway:** `jobject`, `jclass`, `jstring`, and JNI array types are **references to JVM objects**, not memory addresses that can be arbitrarily interpreted from C/C++. Reading/writing data, comparing objects, managing local/global references, and releasing temporary buffers must all go through the corresponding `JNIEnv` contract.
