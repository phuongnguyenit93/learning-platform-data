# Creating, Traversing Object Arrays, and Cleaning Up Generated Local References in JNI

## 1. Problem Statement and Background

In the Java Native Interface (JNI), Java types such as `String[]`, `Object[]`, `Person[]`, or `String[][]` are manipulated from C/C++ code through **JNI object arrays** (`jobjectArray`). A Java array is still an object managed by the JVM; on the C/C++ side, `jobjectArray` is an **opaque reference**, not a C pointer pointing directly to the element storage area.

This lesson focuses on three tightly coupled operations:

1. **Creating an array:** Using `NewObjectArray` with the number of elements, the class of the **element**, and an initial value.
2. **Traversing and updating:** Using `GetArrayLength`, `GetObjectArrayElement`, and `SetObjectArrayElement`; distinguishing between null, valid object elements, and Java exceptions.
3. **Cleaning up generated local references:** Each `GetObjectArrayElement` call that retrieves a non-null element normally creates a **new local JNI reference**. In a long loop, you must call `DeleteLocalRef` immediately after finishing with it or manage a local frame.

Guiding example:

~~~text
Java: String[] labels = {"red", "blue", "green"};
           |
           v
JNI: jobjectArray labels
           |
           +-- GetArrayLength(labels)               -> 3
           +-- GetObjectArrayElement(labels, 0)     -> local jstring #1
           |       +-- process element "red"
           |       +-- DeleteLocalRef(local #1)
           +-- GetObjectArrayElement(labels, 1)     -> local jstring #2
           |       +-- process element "blue"
           |       +-- DeleteLocalRef(local #2)
           +-- GetObjectArrayElement(labels, 2)     -> local jstring #3
                   +-- process element "green"
                   +-- DeleteLocalRef(local #3)
~~~

**Most important point:** `DeleteLocalRef` deletes the **temporary JNI handle created by the element read**; it **does not clear the slot in the Java array**, does not automatically set the element to `null`, and does not call `free` on the Java object. The array still holds a reference to the element if the element has not been replaced.

## 2. Which JNI Type Corresponds to a Java Array?

| Java Type | JNI Parameter/Return Type | How to Access Elements |
| --- | --- | --- |
| `Object[]`, `String[]`, `MyClass[]` | `jobjectArray` | `GetObjectArrayElement`, `SetObjectArrayElement` |
| `int[]` | `jintArray` | `GetIntArrayRegion`, `GetIntArrayElements`, and primitive array APIs |
| `byte[]` | `jbyteArray` | `GetByteArrayRegion`, `GetByteArrayElements` |
| `double[]` | `jdoubleArray` | `GetDoubleArrayRegion`, `GetDoubleArrayElements` |
| `String[][]` | `jobjectArray` for the outer array, each row is a `jobjectArray` | Get the row with `GetObjectArrayElement`, then get the Strings in the row |
| `int[][]` | `jobjectArray` for the outer array, each row is a `jintArray` | Get the row with the object array API, process each row with the int array API |

A `jobjectArray` variable is not a `jobject*`. Although a Java `Object[]` holds references to objects, **how the JVM represents and moves objects is an implementation detail**. Reading elements with `array[i]` like a C array violates the JNI contract.

JVM descriptors to distinguish:

~~~text
Ljava/lang/String;        a String object
[Ljava/lang/String;       a String[] array
[[Ljava/lang/String;      a String[][] array
[I                        an int[] array
[[I                       an int[][] array
~~~

The `[` character represents one array dimension; `L...;` represents a reference type, while `I` is the primitive `int` type. In C JNI, a method receiving `String[]` has a `jobjectArray` parameter; a method receiving `int[]` has a `jintArray` parameter. Choose the API based on the **element type of the dimension being operated on**, not just because all of them are arrays in Java.

## 3. Creating an Object Array: `NewObjectArray`

The C JNI signature called through `JNIEnv*`:

~~~c
jobjectArray result = (*env)->NewObjectArray(
        env, length, elementClass, initialElement);
~~~

Parameter meanings:

| Parameter | Type | Role |
| --- | --- | --- |
| `env` | `JNIEnv*` | The JNI interface of the current thread |
| `length` | `jsize` | Number of elements, must be non-negative; allocation may fail if out of memory |
| `elementClass` | `jclass` | Java class of **each element** allowed to be stored in the array |
| `initialElement` | `jobject` or `NULL` | Initial reference assigned to **every slot** |
| Result | `jobjectArray` | **Local reference** to the new array, or `NULL` on failure |

To create a `String[]` of three null elements:

~~~c
/* Example placed inside a native method; not a standalone program. */
jclass stringClass = (*env)->FindClass(env, "java/lang/String");
if (stringClass == NULL) {
    return NULL; /* A Java exception may be pending. */
}

jobjectArray values = (*env)->NewObjectArray(
        env, 3, stringClass, NULL);
(*env)->DeleteLocalRef(env, stringClass);

if (values == NULL) {
    return NULL; /* For example: may be due to OutOfMemoryError. */
}

/* values is a local reference to String[3] initially all null. */
return values;
~~~

Steps:

1. `FindClass("java/lang/String")` returns a local `jclass` describing the class of the **String element**. This is not the descriptor string `"Ljava/lang/String;"`.
2. `NewObjectArray(env, 3, stringClass, NULL)` allocates the `String[3]` array. The Java heap holds the array object; allocation and GC are managed by the JVM.
3. After creating the array, the `stringClass` local ref is no longer needed, so `DeleteLocalRef` is called.
4. You can **return the local `values`** directly from a native method returning `String[]`; the JVM handles the result before cleaning up the local frame.
5. Do not call `DeleteLocalRef(env, values)` and then return `values`: a deleted reference will no longer be valid.

### The Initial Value Is Not a Per-Element Copy

If `initialElement` is not null, all slots initially point to the **same Java object**, not N distinct objects.

~~~c
/* Illustration: shared is a valid jobject of the right elementClass. */
jobjectArray repeated = (*env)->NewObjectArray(
        env, 3, elementClass, shared);
~~~

In that case, changing the state of the `shared` object is visible through all three positions, provided the object is actually mutable. This is just like Java:

~~~java
// Illustration only; not a standalone program.
StringBuilder one = new StringBuilder("x");
StringBuilder[] repeated = {one, one, one};
repeated[0].append("y");
// repeated[1] and repeated[2] also point to the "xy" object.
~~~

When you want three independent objects, you must create each object separately and call `SetObjectArrayElement` for each slot.

### Errors to Consider When Creating

`NewObjectArray` can fail due to `NegativeArraySizeException` (negative size) or `OutOfMemoryError`. `FindClass` can fail because the class is not found or cannot be initialized/resolved in the appropriate context. If the API returns `NULL` and there is a pending Java exception, **do not continue as if the array had been created**.

Specifically: `elementClass` is the element class. If you use `FindClass("java/lang/Object")`, you create an `Object[]`, not a `String[]`, even if you only put `String`s into it afterward. When a Java method is declared to return `String[]`, you need to create an array with a compatible runtime type, such as `String[]`.

## 4. Reading and Traversing Arrays with `GetArrayLength`, `GetObjectArrayElement`

For a valid object array:

~~~c
jsize n = (*env)->GetArrayLength(env, array);
for (jsize i = 0; i < n; i++) {
    jobject element = (*env)->GetObjectArrayElement(env, array, i);
    if ((*env)->ExceptionCheck(env)) {
        return; /* Example: native method returns void. */
    }

    if (element != NULL) {
        /* Use element via the appropriate JNI APIs. */
        (*env)->DeleteLocalRef(env, element);
    }
}
~~~

**Detailed mechanics:**

- `GetArrayLength` returns the number of elements (type `jsize`), not the memory size in bytes. A `String[]` of length 3 has length 3 even if the strings have different lengths.
- `GetObjectArrayElement(array, i)` returns a **local `jobject`** for the `i`-th element. With `String[]`, a non-null element can be used as a `jstring` according to the runtime type already checked by Java.
- If the Java element itself at position `i` is `null`, the API returns `NULL`. If the index is invalid, the API may raise a Java exception. Therefore **`NULL` alone is not enough to identify all errors**; check `ExceptionCheck` when you need to distinguish.
- The local ref from each read is kept until deleted, when the local frame is popped, or when the native invocation ends. **It does not automatically expire when the C loop moves to the next iteration**.
- After processing the element, delete the new local ref with `DeleteLocalRef(env, element)`, especially in long loops.

Retrieving a non-null element from `String[]` does not transfer ownership of the array to C. Similarly, do not use `free(element)`, `delete element`, or cast an opaque reference to a direct pointer to JVM data.

### Reading a String Inside an Element

Assuming Java is guaranteed to pass a `String[]`:

~~~c
/* Illustrative snippet: not a standalone function. */
jobject obj = (*env)->GetObjectArrayElement(env, labels, 0);
if ((*env)->ExceptionCheck(env)) {
    return 0;
}
if (obj != NULL) {
    jsize units = (*env)->GetStringLength(env, (jstring) obj);
    /* units is the number of UTF-16 code units, not the number of UTF-8 bytes. */
    (*env)->DeleteLocalRef(env, obj);
    return units;
}
return 0;
~~~

Casting `(jstring) obj` **is only valid because the element actually is a String**, not because any `jobject` can be treated as a String. If the array is an `Object[]` containing multiple types, check the type with `IsInstanceOf` when needed, or design the API to accept the exact data type.

With `GetStringUTFChars`, the resulting pointer requires `ReleaseStringUTFChars`. This is a **different release rule** from `DeleteLocalRef`; the two actions address two different resources.

## 5. Writing Elements with `SetObjectArrayElement`

Conceptual signature:

~~~c
(*env)->SetObjectArrayElement(env, array, index, value);
~~~

- `array`: a valid `jobjectArray`.
- `index`: position of type `jsize`; must be in the range `0 <= index < GetArrayLength(array)`.
- `value`: a `jobject` compatible with the runtime component type or `NULL`.
- The API returns `void`; to know if an error occurred along the execution path, you can use `ExceptionCheck` after the call.

Creating three Java strings and storing them in an array:

~~~c
/* Illustrative snippet inside a native method with valid env and values. */
for (jsize i = 0; i < 3; i++) {
    jstring part = (*env)->NewStringUTF(env, "item");
    if (part == NULL) {
        return NULL;
    }

    (*env)->SetObjectArrayElement(env, values, i, part);
    jboolean failed = (*env)->ExceptionCheck(env);

    /* Delete local handle part after finishing with it. */
    (*env)->DeleteLocalRef(env, part);

    if (failed) {
        return NULL;
    }
}
return values;
~~~

**Why is the element still preserved after `DeleteLocalRef`?** After `SetObjectArrayElement` succeeds, the **array** itself already holds a reference to that Java String. Deleting the local handle `part` only removes a temporary JNI root; the element in `values[i]` still points to the object. When Java receives `values`, `values[0]` can still read the String normally.

If you want to replace with null:

~~~c
/* Illustration only, slot must be within valid bounds. */
(*env)->SetObjectArrayElement(env, values, slot, NULL);
~~~

That changes the array element. Differences:

| Operation | Effect on Java Array | Effect on JNI Reference |
| --- | --- | --- |
| `SetObjectArrayElement(array, i, obj)` | Assigns `obj` to position `i` | Does not automatically clean up local `obj` |
| `SetObjectArrayElement(array, i, NULL)` | Assigns null to position `i` | Does not automatically clean up any local refs pointing to the old object |
| `DeleteLocalRef(env, obj)` | **Does not** change `array[i]` | Deletes the local JNI handle `obj` |
| `GetObjectArrayElement(array, i)` | Only reads the element | May create a **new local JNI reference** that needs cleanup |

**Type checking on write:** If `array` is actually a `String[]` and we try to store an `Integer`, the JVM may throw `ArrayStoreException`. Compatibility depends on the **runtime component type of the array**. Java arrays are covariant (`String[]` is an `Object[]` in terms of type), so merely seeing a parameter type of `Object[]` does not mean any object can be stored.

**Index checking:** `SetObjectArrayElement` can throw `ArrayIndexOutOfBoundsException` if the index is wrong. A pending native exception must be propagated or handled intentionally, rather than assuming the write succeeded.

## 6. Local Reference Mechanics When Creating and Traversing Arrays

This is the part most prone to bugs when processing thousands of objects:

~~~text
Running native frame
|
+-- local jobjectArray result    (array created by NewObjectArray)
+-- local jclass stringClass     (created by FindClass)
|
+-- loop i = 0
|      +-- local jstring element0 (created by NewStringUTF)
|      +-- SetObjectArrayElement(result, 0, element0)
|      +-- DeleteLocalRef(element0)
|
+-- loop i = 1
|      +-- local jstring element1
|      +-- SetObjectArrayElement(result, 1, element1)
|      +-- DeleteLocalRef(element1)
|
+-- DeleteLocalRef(stringClass)
+-- return result to Java
       +-- JVM keeps the result object valid
       +-- JVM cleans up remaining local refs of the native invocation
~~~

`stringClass` and each `element` are cleaned up early. `result` is the final array so it **must remain valid to return**. Other local refs can be cleaned up when done without causing the Java array to lose its elements.

### Why Do Loops Need Early Cleanup?

The **bad** case:

~~~c
/* Illustration: method processes a very long array but skips cleanup. */
for (jsize i = 0; i < n; i++) {
    jobject obj = (*env)->GetObjectArrayElement(env, array, i);
    /* Process obj, then move to the next iteration without DeleteLocalRef. */
}
~~~

Local JNI references generated in each iteration **are not automatically deleted when the C variable `obj` is overwritten**. They can accumulate in the same native frame. JNI guarantees minimum capacity for a certain number of local refs (per the specification, at least 16 upon entering a native method), but **does not guarantee arbitrary accumulation**. Across different JVMs, creating too many local refs can cause warnings, allocation failures, or increased resource consumption.

The good case:

~~~c
/* Illustration: valid array; method assumed to return void. */
for (jsize i = 0; i < n; i++) {
    jobject obj = (*env)->GetObjectArrayElement(env, array, i);

    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    if (obj != NULL) {
        /* Process obj before deleting the local handle. */
        (*env)->DeleteLocalRef(env, obj);
    }
}
~~~

**Note:** You can delete local `obj` even if that object is still in the array or still has references in Java. `DeleteLocalRef` does not invoke a Java destructor or directly free the Java heap; it only removes the JNI handle. On a GC-managed JVM, the object can only be reclaimed when no strong roots remain and when the GC decides to run.

### Local, Global, and Weak Global Are Different Handle Types

| Reference Type | Created By | Lifetime |
| --- | --- | --- |
| Local | `GetObjectArrayElement`, `FindClass`, `NewStringUTF`, `NewObjectArray`, ... | Belongs to the JNI thread/frame; cleaned up when deleted, frame popped, or native invocation ends |
| Global | `NewGlobalRef` | Persists across multiple calls and can be used on attached threads; cleaned up with `DeleteGlobalRef` |
| Weak global | `NewWeakGlobalRef` | Does not keep an object alive on its own; target may be cleared by GC, cleaned up with `DeleteWeakGlobalRef` |

For the task of **traversing an array inside one native method**, there is no need to turn each element into a global reference. That only increases management overhead and can keep objects alive unnecessarily. If you truly need to use an object after the native method or from another thread, you must design explicit ownership and lifetime, typically using a global reference.

## 7. Complete Java 17 + C/JNI Example

Program goals:

- Call a native method from Java that creates a `String[]` using `NewObjectArray`.
- C code creates each Java String with `NewStringUTF`, assigns it via `SetObjectArrayElement`, and **cleans up the local `jstring` immediately after assigning**.
- Java prints the created elements.
- Java calls another native method to traverse that same array: `GetArrayLength`, `GetObjectArrayElement`, `GetStringLength`, then `DeleteLocalRef`.
- Deterministic output, helping verify that deleting local handles **does not delete the contents inside the Java array**.

Runtime environment: **Linux + JDK 17 or later + GCC** (the JDK and C compiler must match CPU/ABI). The `JAVA_HOME` variable must point to the JDK directory. The project has two initial files:

~~~text
jni-object-array-demo/
  ObjectArrayWalkDemo.java
  object_array_walk.c
~~~

### 7.1. File `ObjectArrayWalkDemo.java`

~~~java
import java.util.Arrays;

public final class ObjectArrayWalkDemo {
    static {
        System.loadLibrary("objectarraywalk");
    }

    private static native String[] makeLabels(int count);

    private static native int sumUtf16Units(String[] labels);

    public static void main(String[] args) {
        String[] labels = makeLabels(3);

        System.out.println("length=" + labels.length);
        System.out.println("labels=" + Arrays.toString(labels));
        System.out.println("utf16Units=" + sumUtf16Units(labels));
    }
}
~~~

Java declares two `static` native methods. In C/JNI, the second JNI parameter position is `jclass` (for an instance native method it is `jobject receiver`). The name `makeLabels` denotes the function that creates `String[]` and `sumUtf16Units` denotes the traversal that sums the total number of **UTF-16 code units**, not UTF-8 bytes.

### 7.2. File `object_array_walk.c`

~~~c
#include <jni.h>
#include <stdio.h>
#include "ObjectArrayWalkDemo.h"

JNIEXPORT jobjectArray JNICALL Java_ObjectArrayWalkDemo_makeLabels(
        JNIEnv *env, jclass owner, jint count) {
    (void) owner;

    if (count < 0 || count > 100) {
        jclass badArgument = (*env)->FindClass(
                env, "java/lang/IllegalArgumentException");
        if (badArgument != NULL) {
            (*env)->ThrowNew(
                    env, badArgument, "count must be between 0 and 100");
            (*env)->DeleteLocalRef(env, badArgument);
        }
        return NULL;
    }

    jclass stringClass = (*env)->FindClass(
            env, "java/lang/String");
    if (stringClass == NULL) {
        return NULL;
    }

    jobjectArray labels = (*env)->NewObjectArray(
            env, (jsize) count, stringClass, NULL);

    /* The array already has runtime component type String. */
    (*env)->DeleteLocalRef(env, stringClass);

    if (labels == NULL) {
        return NULL;
    }

    for (jsize i = 0; i < (jsize) count; i++) {
        char buffer[32];
        int written = snprintf(
                buffer, sizeof buffer, "item-%d", (int) i);

        /* Explicit check even though count <= 100 makes the buffer long enough. */
        if (written < 0 || (size_t) written >= sizeof buffer) {
            jclass errorClass = (*env)->FindClass(
                    env, "java/lang/IllegalStateException");
            if (errorClass != NULL) {
                (*env)->ThrowNew(
                        env, errorClass, "label formatting failed");
                (*env)->DeleteLocalRef(env, errorClass);
            }
            return NULL;
        }

        jstring item = (*env)->NewStringUTF(env, buffer);
        if (item == NULL) {
            return NULL; /* Example: pending OutOfMemoryError. */
        }

        (*env)->SetObjectArrayElement(
                env, labels, i, item);
        jboolean failed = (*env)->ExceptionCheck(env);

        /* Correct even if SetObjectArrayElement raises an exception:
           item was already created, so the local handle must be deleted. */
        (*env)->DeleteLocalRef(env, item);

        if (failed) {
            return NULL;
        }
    }

    /* Keep the local ref to the array to return the result to Java. */
    return labels;
}

JNIEXPORT jint JNICALL Java_ObjectArrayWalkDemo_sumUtf16Units(
        JNIEnv *env, jclass owner, jobjectArray labels) {
    (void) owner;

    if (labels == NULL) {
        jclass npe = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (npe != NULL) {
            (*env)->ThrowNew(env, npe, "labels must not be null");
            (*env)->DeleteLocalRef(env, npe);
        }
        return 0;
    }

    jsize n = (*env)->GetArrayLength(env, labels);
    jint total = 0;

    for (jsize i = 0; i < n; i++) {
        jobject obj = (*env)->GetObjectArrayElement(
                env, labels, i);

        if ((*env)->ExceptionCheck(env)) {
            return 0;
        }

        if (obj != NULL) {
            /* Because the Java parameter is String[], the element is a String. */
            total += (*env)->GetStringLength(
                    env, (jstring) obj);

            /* Each GetObjectArrayElement creates a local ref that needs cleanup. */
            (*env)->DeleteLocalRef(env, obj);
        }
    }

    return total;
}
~~~

Explanation of key points:

1. `FindClass("java/lang/String")` returns the local `jclass` for the component type; `NewObjectArray` creates the exact `String[]` of length `count`.
2. `DeleteLocalRef(env, stringClass)` cleans up the local handle for the class after creating the array; **it does not change the runtime type of `labels`**.
3. `snprintf` creates the ASCII C strings `item-0`, `item-1`, `item-2`. ASCII is valid in Modified UTF-8 so `NewStringUTF` creates the corresponding Java Strings; no arbitrary assumptions about complex Unicode are needed.
4. `SetObjectArrayElement(labels, i, item)` stores the Java String into the array. **Immediately afterward**, the local handle `item` is deleted; the object remains reachable from `labels[i]`.
5. For an error in `SetObjectArrayElement`, the code remembers to clean up the local `item` and then return so Java receives the pending exception. For error paths before returning, any remaining local `labels` will be cleaned up when the native method ends; do not return a fake value pretending success.
6. The `sumUtf16Units` function retrieves `jobject` on each `GetObjectArrayElement` call, uses `GetStringLength`, and calls **`DeleteLocalRef` inside the loop itself**.
7. A null element does not create a non-null local handle and is skipped when summing lengths. For the example's input, there are no nulls.

**Intentional limitations:** The example applies to at most 100 elements, with each string built from short ASCII. In a real application, you must define input limits, guard against sum overflow, and specify encoding conventions; do not keep demo limits as-is for production APIs. The `ExceptionCheck`, `DeleteLocalRef`, and `return` pattern on the error path is chosen so objects are not used further while a Java exception is pending.

### 7.3. Compiling and Running on Linux

In the directory with the two files:

~~~bash
javac -h . ObjectArrayWalkDemo.java

gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libobjectarraywalk.so object_array_walk.c

java -Djava.library.path=. ObjectArrayWalkDemo
~~~

- `javac -h .` compiles the class and generates the `ObjectArrayWalkDemo.h` header matching the native method signatures; do not guess JNI symbol names for classes with packages/overloads.
- `gcc -fPIC -shared` builds a shared library for Linux. The library must use an architecture compatible with the running JVM.
- `System.loadLibrary("objectarraywalk")` asks the JVM to look for `libobjectarraywalk.so` on typical Linux systems, in the `java.library.path=.` path passed at startup.

**Exact stdout** of the example:

~~~text
length=3
labels=[item-0, item-1, item-2]
utf16Units=18
~~~

Because `item-0`, `item-1`, and `item-2` each have six UTF-16 code units, the sum is `6 + 6 + 6 = 18`. The `Arrays.toString(labels)` output proves that the elements remain valid **after C code deletes each local `jstring`**.

On macOS, the binary is typically `libobjectarraywalk.dylib`, with JNI include `$JAVA_HOME/include/darwin` and linker options such as `clang -dynamiclib`. On Windows, the library is typically `objectarraywalk.dll`, requiring the JNI include `%JAVA_HOME%\include\win32` and a build toolchain matching the JVM. Those are changes at the build/library-loading stage; the contracts for `NewObjectArray`, `GetObjectArrayElement`, `SetObjectArrayElement`, and local references remain the same.

## 8. Cleaning Up References in Large Loops: Strategies

### 8.1. Deleting Each Element with `DeleteLocalRef`

For operations that only need one element at a time, the common approach is:

~~~c
/* Illustration inside a native method returning void. */
jsize count = (*env)->GetArrayLength(env, array);
for (jsize i = 0; i < count; i++) {
    jobject value = (*env)->GetObjectArrayElement(
            env, array, i);

    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    if (value != NULL) {
        /* Process value ... */
        (*env)->DeleteLocalRef(env, value);
    }
}
~~~

This reduces the number of simultaneously live handles **without** needing complex local frame calculations. Note that every early exit path (`return`, error branches, break) after creating a handle must follow cleanup for resources still owned; if the native method returns, the JVM still cleans up remaining local refs, but **that does not replace the responsibility to release native buffers obtained via separate APIs**.

### 8.2. Using `PushLocalFrame` / `PopLocalFrame` When One Iteration Creates Many Refs

If each element requires a series of temporary classes/objects/strings, use a nested local frame to group cleanup:

~~~c
/* Illustration inside a native method returning void.
   array is a valid jobjectArray; do not use nested results outside the frame. */
jsize n = (*env)->GetArrayLength(env, array);

for (jsize i = 0; i < n; i++) {
    if ((*env)->PushLocalFrame(env, 16) < 0) {
        return; /* OutOfMemoryError may be pending. */
    }

    jobject item = (*env)->GetObjectArrayElement(env, array, i);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->PopLocalFrame(env, NULL);
        return;
    }

    if (item != NULL) {
        /* Create/look up additional JNI local references if needed,
           using them only before popping the frame. */
    }

    /* Clean up all refs of the child frame at once (including item). */
    (*env)->PopLocalFrame(env, NULL);
}
~~~

`PushLocalFrame(env, 16)` asks the JVM to ensure space for at least 16 local references in the new frame. `PopLocalFrame(env, NULL)` discards that frame's refs. If you need to pass an object out to the parent frame, you must use the **`jobject` value returned by `PopLocalFrame(env, result)`**, not the old handle belonging to the popped frame.

The two approaches are **not required to be used together**: if you only create one local reference per iteration, `DeleteLocalRef` is simpler. For native threads created by C/C++ and then attached with `AttachCurrentThread`, explicit cleanup is even more important because local refs may persist until the thread detaches if unmanaged.

### 8.3. When to Use `EnsureLocalCapacity`?

`EnsureLocalCapacity(env, required)` asks the JVM to guarantee the ability to create additional local refs in the current frame, returning an error code when it cannot be satisfied (possibly with a pending exception). This API **does not automatically delete** old local refs and **does not replace** `DeleteLocalRef`. If processing millions of elements, the solution is still to keep the number of simultaneously live local handles small via cleanup or batching.

## 9. Multi-Dimensional Arrays: Creating and Traversing Row by Row

A Java `String[][]` is an **array containing `String[]` elements**, not a flat `jstring**` region. In C/JNI, the outer array is a `jobjectArray`, and each row is also a `jobjectArray`.

Creating an outer array with two `String[]` rows:

~~~c
/* Illustration inside a native method, with JNIEnv* env. */
jclass rowClass = (*env)->FindClass(
        env, "[Ljava/lang/String;");
if (rowClass == NULL) {
    return NULL;
}

jobjectArray matrix = (*env)->NewObjectArray(
        env, 2, rowClass, NULL);
(*env)->DeleteLocalRef(env, rowClass);

if (matrix == NULL) {
    return NULL;
}

/* Each element matrix[0], matrix[1] is initially null.
   You can create separate String[] arrays and call SetObjectArrayElement for each row. */
return matrix;
~~~

**Why use `"[Ljava/lang/String;"`?** `FindClass` needs the class representing the **element of the outer array**, which is `String[]`, so the JNI array-class descriptor with `[` is used. When directly creating a one-dimensional `String[]` array, the component type is `java.lang.String`, so `FindClass("java/lang/String")` is used.

Traversing a two-dimensional array:

~~~c
/* Illustration inside a native method returning void; matrix is valid. */
jsize rowCount = (*env)->GetArrayLength(env, matrix);
for (jsize r = 0; r < rowCount; r++) {
    jobject rowObj = (*env)->GetObjectArrayElement(
            env, matrix, r);
    if ((*env)->ExceptionCheck(env)) {
        return;
    }
    if (rowObj == NULL) {
        continue; /* Java allows null rows. */
    }

    jobjectArray row = (jobjectArray) rowObj;
    jsize colCount = (*env)->GetArrayLength(env, row);

    for (jsize c = 0; c < colCount; c++) {
        jobject element = (*env)->GetObjectArrayElement(
                env, row, c);
        if ((*env)->ExceptionCheck(env)) {
            (*env)->DeleteLocalRef(env, rowObj);
            return;
        }
        if (element != NULL) {
            /* Process String at row r, column c ... */
            (*env)->DeleteLocalRef(env, element);
        }
    }

    (*env)->DeleteLocalRef(env, rowObj);
}
~~~

**There are two levels of local references:** the `rowObj` handle for each row and the `element` handle for each cell. Both need cleanup at their respective levels. Java allows jagged multi-dimensional arrays (different numbers of elements per row) and `null` rows; therefore always check `GetArrayLength(row)` for the current row instead of assuming a rectangular matrix.

Distinguish this from `int[][]`: the outer array is still `jobjectArray`, but each row is a `jintArray`, so numeric elements are processed using `GetIntArrayRegion` or `GetIntArrayElements` along with the corresponding release API.

## 10. Exception Safety When Creating, Assigning, and Traversing

JNI calls can fail and leave a **pending Java exception**; C JNI does not use C++ exception mechanisms to represent all those cases. For example:

| API | Possible Failure | Practical Handling |
| --- | --- | --- |
| `FindClass` | Class not found or resolution/loading error | Check `NULL`; let the Java exception propagate or handle it intentionally |
| `NewObjectArray` | Negative size, out of memory | Check `NULL`, do not use the array when creation fails |
| `NewStringUTF` | Out of memory, Modified UTF-8 data violates contract | Check the result; provide valid encoding |
| `GetObjectArrayElement` | Index out of bounds | Check `ExceptionCheck`; do not blindly treat `NULL` as a null element |
| `SetObjectArrayElement` | Invalid index or element incompatible with runtime component type | After the `void` call, check `ExceptionCheck` if the next branch requires success |
| `PushLocalFrame` | Cannot allocate enough capacity | Check the return value; stop the normal processing path |

In the complete example, the code has the order:

~~~c
(*env)->SetObjectArrayElement(env, labels, i, item);
jboolean failed = (*env)->ExceptionCheck(env);
(*env)->DeleteLocalRef(env, item);
if (failed) {
    return NULL;
}
~~~

This is an important pattern: **even if the assignment fails, still clean up the `item` local reference created earlier**. `DeleteLocalRef` is a cleanup operation permitted in JNI situations with an appropriate pending exception. Do not continue calling `NewStringUTF` or using other objects along the normal execution path when a Java exception is already pending.

### Differences Easily Confused

- **Null element:** `GetObjectArrayElement` can return `NULL` without a pending exception; this is a valid Java `null` data case.
- **Allocation failure:** `NewObjectArray` or `NewStringUTF` can return `NULL` with an exception; must not be dereferenced.
- **Type mismatch:** `SetObjectArrayElement` putting an `Integer` into a `String[]` is not like assigning null; the JVM rejects it with `ArrayStoreException`.
- **Invalid index:** Out-of-bounds access can raise `ArrayIndexOutOfBoundsException`; use `jsize n = GetArrayLength(...)` and loop `i < n` instead of guessing the size.
- **Native crash:** Casting `jobjectArray` to a C pointer and reading/writing memory can crash the process. This is no longer just a normal Java exception.

Do not unconditionally clear exceptions with `ExceptionClear` to keep running: that can lose the real error and cause Java to receive unreliable results.

## 11. Reading an Element and Saving It Across Calls or Threads: Do Not Use Old Local Refs

`GetObjectArrayElement` creates a local reference in the **current thread**, typically valid until the native method returns or it is deleted earlier. **Do not store a raw local `jobject` in a static/global C variable and use it after the native return**:

~~~c
/* WRONG: cached only copies the JNI local handle. */
static jobject cached = NULL;

static void rememberWrong(jobject element) {
    cached = element;
}
~~~

That approach does not keep the object alive validly. If you need to use the same Java object across multiple native calls or threads, use the **global reference** contract:

~~~c
/* Illustration of creating a global ref while the local is still valid. */
jobject stable = (*env)->NewGlobalRef(env, element);
if (stable == NULL) {
    /* OutOfMemoryError may be pending. */
}

/* When there are no more users and no concurrent access: */
if (stable != NULL) {
    (*env)->DeleteGlobalRef(env, stable);
}
~~~

This snippet only illustrates the API; production code needs to design handle ownership, access synchronization, error handling, release timing, and thread attachment. Although a global reference can be used from a properly attached thread, **`JNIEnv*` must be obtained from the currently running thread itself** and the Java object may still need synchronization if mutable.

If Java can hold the array/object and **pass it back in the next native call**, the JVM will issue a new local reference for that invocation. This design is often simpler than managing global refs in native code.

## 12. Common Mistakes and How to Fix Them

### Mistake 1: Using an object array as a C pointer array

~~~c
/* WRONG: jobjectArray is an opaque JNI reference. */
jobject *items = (jobject *) array;
jobject first = items[0];
~~~

**Fix:** `GetObjectArrayElement(env, array, 0)`, check for errors, and call `DeleteLocalRef` on the local result when done.

### Mistake 2: Forgetting to clean up local references in a loop

~~~c
/* RESOURCE MANAGEMENT BUG IF n IS VERY LARGE. */
for (jsize i = 0; i < n; i++) {
    jobject element = (*env)->GetObjectArrayElement(env, array, i);
    /* Loop finishes without DeleteLocalRef(element). */
}
~~~

**Fix:** `DeleteLocalRef(env, element)` each iteration or `PushLocalFrame`/`PopLocalFrame` per batch. The `element` variable going out of C scope **does not** automatically delete the JNI handle.

### Mistake 3: Deleting the result array's local reference before returning

~~~c
/* WRONG: result is no longer valid when returned. */
(*env)->DeleteLocalRef(env, result);
return result;
~~~

**Fix:** Keep `result` valid and return it directly. The JVM will process the returned object and clean up the local frame. If the result is inside a nested local frame, `PopLocalFrame(env, result)` must create the corresponding local reference in the parent frame, and **return the value provided by PopLocalFrame**.

### Mistake 4: Thinking `DeleteLocalRef(item)` empties `array[i]`

~~~c
/* This is not a statement that clears an array element. */
(*env)->DeleteLocalRef(env, item);
~~~

**Fix:** If you want to assign null, call `SetObjectArrayElement(env, array, i, NULL)`. Cleaning up a local handle and changing array contents are **two different operations**.

### Mistake 5: Using the array's class instead of the element's class

~~~c
/* Creating Object[] when String[] is expected has the wrong runtime type. */
jclass objectClass = (*env)->FindClass(env, "java/lang/Object");
jobjectArray wrongType = (*env)->NewObjectArray(
        env, 3, objectClass, NULL);
~~~

**Fix:** For `String[]`, use `FindClass("java/lang/String")` to get the component class; for the outer array of `String[][]`, use class `"[Ljava/lang/String;"` as the component type.

### Mistake 6: Keeping a local reference from `GetObjectArrayElement` for an asynchronous callback

Once the native call ends, its local refs become invalid. **Fix:** create a global reference while the local is still valid and ensure it is released, or have Java pass the element back when the future callback begins.

### Mistake 7: Using the wrong encoding for `NewStringUTF`

`NewStringUTF` accepts **Modified UTF-8**, not arbitrary UTF-8 byte sequences. For the `"item-0"` example there is only ASCII, so there is no difference. For general Unicode content, determine the encoding and consider using `NewString` with a UTF-16 buffer, or convert encodings properly.

### Mistake 8: Confusing object arrays with primitive arrays

`String[]` uses `GetObjectArrayElement`; `int[]` uses `GetIntArrayRegion`/`GetIntArrayElements`. Pointers obtained from primitive array APIs must be released with the proper function (`ReleaseIntArrayElements`); `DeleteLocalRef` does not replace releasing the elements region.

### Mistake 9: Thinking `GetObjectArrayElement` returning the same object means no cleanup is needed

Even if the array contains multiple slots pointing to **the same Java object**, each `GetObjectArrayElement` call can create a **separate local handle**. Therefore you must still clean up the handles generated per read. Same object identity does not mean the same JNI reference lifetime.

## 13. Error Checking and Performance in Real Applications

With large object arrays, overhead can come from:

- Many `GetObjectArrayElement`/`SetObjectArrayElement` JNI calls and the volume of temporary local references.
- Creating many new Java objects via `NewStringUTF`/`NewObject`.
- Converting character data between Modified UTF-8, UTF-16, and external encodings.
- GC pressure from the number of Java arrays and objects, plus the cost of handling Java exceptions if they occur.
- Holding local/global references too long, keeping Java objects reachable unnecessarily.

**Do not assume every JNI call is zero-copy.** With object arrays, we operate through handles and JVM APIs; there is no guarantee that the entire array is a contiguous C memory region that can be dereferenced directly.

On HotSpot, try running the demo with JNI checks:

~~~bash
java -Xcheck:jni -Djava.library.path=. ObjectArrayWalkDemo
~~~

`-Xcheck:jni` can detect some incorrect JNI usages and produce diagnostic information; it cannot prove native code is completely safe. For real applications, test empty arrays, null elements, null rows if two-dimensional, long arrays, index/type errors, OOME, and early exit paths to verify cleanup.

A minimal checklist when reviewing a JNI object array loop:

1. Correct `jobjectArray` for the runtime array type and correct `jclass` for the element type?
2. `GetArrayLength`, bounds `0 <= i < n`, and null array handling present?
3. Is each element retrieved from `GetObjectArrayElement` used within a still-valid thread/frame?
4. Are null elements distinguished from pending exceptions?
5. Is `DeleteLocalRef` called for each newly generated local reference, including on error paths?
6. Does `SetObjectArrayElement` check compatibility and pending exceptions when needed?
7. If returning an array, is the local result still valid until return?
8. If there are buffers/string chars, are they released with the **right API**, not confused with `DeleteLocalRef`?
9. With nested arrays, are both row and element local refs cleaned up?
10. Are local refs avoided across native calls/threads, and is there an ownership strategy when global refs are truly needed?

## 14. Knowledge Self-Check

1. What does `NewObjectArray(env, 4, stringClass, NULL)` create? What values do the elements initially have?
2. If `initialElement` is a `StringBuilder`, do the four slots in the new array point to four separate instances?
3. Why can't `GetObjectArrayElement` be replaced by `array[index]` in C?
4. `GetObjectArrayElement` returns `NULL`: how do you distinguish a Java null element from an error with a pending exception?
5. After `SetObjectArrayElement(array, i, part)` succeeds, does calling `DeleteLocalRef(part)` make `array[i]` null?
6. Why should a loop reading one million elements proactively call `DeleteLocalRef` on each element instead of just waiting for the native method to return?
7. What JNI type does `String[][]` use at the outer dimension, and what class is needed as the component type when creating the outer array?
8. When you want to return a `jobjectArray` created by a native method, can you call `DeleteLocalRef` on that array itself and then return the old handle?
9. What type of Java exception does `SetObjectArrayElement` writing an `Integer` into a `String[]` typically encounter?
10. When you need to keep an array element for another native thread to use after the method has returned, is a local `jobject` sufficient?
11. Why does `GetStringUTFChars` require a different release from `DeleteLocalRef`?
12. How do you run the demo so HotSpot checks for additional JNI errors?

**Suggested answers:** (1) `String[4]` with four null elements; (2) no, they all reference `initialElement`; (3) the array is an opaque JNI ref; (4) check for a pending exception; (5) no, the array still holds the object; (6) to limit the number of simultaneously live JNI local handles; (7) `jobjectArray`, component class `"[Ljava/lang/String;"`; (8) no, only return a valid ref or use the result of `PopLocalFrame`; (9) `ArrayStoreException`; (10) no, a global ref or a design where Java passes the data back is needed; (11) the string chars buffer has its own release API, separate from the JNI object handle; (12) add `-Xcheck:jni` when running.

## 15. Official Documentation

- [Oracle JNI Specification — Array Operations: `NewObjectArray`, `GetObjectArrayElement`, `SetObjectArrayElement`](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle JNI Specification — Local and Global References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle JNI Specification — JNI Types and Array Descriptors](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html)
- [Java SE 17 — `String` and UTF-16](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)

**Key takeaways:** `NewObjectArray` creates a **Java object array**, `GetObjectArrayElement` creates a local handle when retrieving an element, and `SetObjectArrayElement` changes the value of a **slot in the array**. A successful assignment does not force JNI to keep the local `jobject` forever; **deleting a local reference after use does not delete the Java object held by the array**. Always keep the **lifetime of the Java array/object** clearly separated from the **lifetime of JNI local handles**, especially in long loops and when exceptions occur.
