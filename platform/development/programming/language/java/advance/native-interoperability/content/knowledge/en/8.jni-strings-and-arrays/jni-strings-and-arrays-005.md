# GetArrayElements May Copy or Pin the Array Depending on the JVM

## 1. The Core Issue: Where Does the Native Pointer Point?

When Java calls C/C++ via **JNI (Java Native Interface)**, native code sometimes needs to directly read or modify the elements of a Java array, such as `int[]`, `byte[]`, or `double[]`. The **`Get<PrimitiveType>ArrayElements`** family of functions allows obtaining a C-style pointer to the element region of a **primitive array**. For example, `GetIntArrayElements` returns `jint *` to read/modify a `jintArray`.

However, **JNI does not guarantee that the pointer always points directly to the original storage of the Java array**. Depending on the JVM implementation, garbage collector (GC), array type, and runtime conditions, the JVM may choose to:

1. **Copy:** create a native buffer containing the elements and return a pointer to that buffer; when changes need to be written back to the Java array, JNI may have to copy back upon `Release<Type>ArrayElements`.
2. **Do not copy (direct access, often described as pinning):** return a pointer accessing the original elements according to the mechanism supported by the JVM; the JVM must maintain safe access while the pointer remains valid, and may have to restrict moving the array or use another mechanism.

**Your code must work correctly in both cases.** You must not assume "this JVM always pins", "small arrays are always copied", "large arrays are always pinned", or "`GetIntArrayElements` is always zero-copy". This is an implementation detail that the JNI specification leaves to the JVM to decide.

### 1.1. Data Flow Illustration

```text
                 Java int[]  [10, 20, 30]
                          |
             GetIntArrayElements(...)
                          |
               +----------+----------+
               |                     |
         JVM chooses copy      JVM chooses direct
               |                     |
      temp buffer [10,20,30]   array element region
               |                     |
          jint *elements        jint *elements
               |                     |
       Native modifies elements[i] on returned pointer
               |                     |
             ReleaseIntArrayElements(..., mode)
               |                     |
       May copy back           No copy-back needed
       before freeing buffer   from temp buffer
                          |
                    Java continues
```

In the copy branch, Java may **not yet see** the newly written native values until release/copy-back. In the direct branch, native code may have already touched the original memory before release, but that is not a reason to skip `Release...`. You should not rely on intermediate observation timing when multiple threads are involved.

## 2. Exact API Names and Supported Scope

`GetArrayElements` is usually just a **conceptual shorthand**. There is no standard JNI function literally named `GetArrayElements` for all array types. The actual names include the type name:

| Java Array | JNI Type | Element Retrieval Function | Returned C Pointer | Corresponding Release Function |
| --- | --- | --- | --- | --- |
| `boolean[]` | `jbooleanArray` | `GetBooleanArrayElements` | `jboolean *` | `ReleaseBooleanArrayElements` |
| `byte[]` | `jbyteArray` | `GetByteArrayElements` | `jbyte *` | `ReleaseByteArrayElements` |
| `char[]` | `jcharArray` | `GetCharArrayElements` | `jchar *` | `ReleaseCharArrayElements` |
| `short[]` | `jshortArray` | `GetShortArrayElements` | `jshort *` | `ReleaseShortArrayElements` |
| `int[]` | `jintArray` | `GetIntArrayElements` | `jint *` | `ReleaseIntArrayElements` |
| `long[]` | `jlongArray` | `GetLongArrayElements` | `jlong *` | `ReleaseLongArrayElements` |
| `float[]` | `jfloatArray` | `GetFloatArrayElements` | `jfloat *` | `ReleaseFloatArrayElements` |
| `double[]` | `jdoubleArray` | `GetDoubleArrayElements` | `jdouble *` | `ReleaseDoubleArrayElements` |

This family **applies only to primitive arrays**. For `String[]` or `Object[]`, use object array APIs such as `GetObjectArrayElement`/`SetObjectArrayElement`; there is no standard `GetObjectArrayElements` to get a direct pointer to all object elements. A single `String` has its own string API family with its own access-region release rules.

According to the specification, `GetBooleanArrayElements` returns a sequence of `jboolean` as **one byte per element** regardless of how the JVM represents `boolean[]` internally; therefore, for `boolean[]`, one cannot infer from the Java layout that a pointer to the original region can always be returned without conversion. Other primitive arrays are guaranteed to have a contiguous element representation according to this interface.

### 2.1. Typical Signature

In C JNI, the conceptual shape of the API pair is:

```c
jint *GetIntArrayElements(
        JNIEnv *env, jintArray array, jboolean *isCopy);

void ReleaseIntArrayElements(
        JNIEnv *env, jintArray array, jint *elems, jint mode);
```

When called from C code using `JNIEnv`:

```c
jboolean isCopy = JNI_FALSE;
jint *elems = (*env)->GetIntArrayElements(env, array, &isCopy);
/* Use elems, check for NULL before dereferencing. */
(*env)->ReleaseIntArrayElements(env, array, elems, 0);
```

The snippet above only illustrates the **API pattern**, not a complete function: in a real program you must check that `array` is valid, `elems != NULL`, and manage error exit paths; a full runnable example is in section 7.

## 3. Why Might the JVM Have to Choose Copy Instead of Pinning?

Java typically allows the garbage collector to manage the heap and may **move objects** when executing certain GC phases. A raw memory address (`jint *`) stored in C is not updated by the GC like an ordinary Java reference if the JVM moves the array.

Therefore, to keep the pointer valid, the JVM can:

- **Copy** the elements to a stable temporary region. The GC continues to manage the Java array according to its mechanism; upon release, writing back may be necessary.
- **Pin** the array or use an equivalent direct-access mechanism for a period of time. This can complicate moving objects, put pressure on the GC, or affect pause times/memory reclamation capability, depending on the collector and implementation.

There is no rule in the JNI Specification forcing the JVM to choose a branch based on array size or GC name. A `GetIntArrayElements` call may copy on one system and not copy on another. Use the `isCopy` flag to **observe the decision of a specific call** if needed, not to change the release contract.

### 3.1. Performance Trade-offs

| JVM Decision | Potential Advantages | Costs/Risks to Note |
| --- | --- | --- |
| Copy | Native code works with an independent buffer; GC can manage the original array more flexibly | May require allocating and copying the entire element region, then copying back on release |
| Direct/pin | Can avoid copying large contents, reading/writing directly on the original data region | May restrict certain GC operations; holding the pointer for long is a risk for the runtime and thread coordination |

**Avoid concluding "direct is definitely faster".** In real workloads there are also JNI call overhead, cache effects, data volume, JIT optimizations, pinning cost, GC, and synchronization. You should measure the entire Java→native→Java path, especially with large arrays or high call frequency.

## 4. Understanding the `isCopy` Parameter Accurately

Example:

```c
jboolean copied = JNI_FALSE;
jint *p = (*env)->GetIntArrayElements(env, numbers, &copied);

if (p == NULL) {
    /* Access error; must not dereference p. */
    return;
}

if (copied == JNI_TRUE) {
    /* The JVM created a copy of the elements. */
} else {
    /* The JVM did not create a copy for this call. */
}

(*env)->ReleaseIntArrayElements(env, numbers, p, 0);
```

This is an **illustrative snippet placed inside a JNI function returning `void`**, with a valid `numbers`; it is not a standalone C program.

Meaning:

- Passing `&copied`: JNI writes `JNI_TRUE` if it **copied**, `JNI_FALSE` if it **did not copy**.
- Passing `NULL` for the `isCopy` argument: valid if you do not need to know which strategy the JVM used.
- `copied == JNI_FALSE` is **not** a certificate that you can keep the pointer forever or use it after release. Nor does it guarantee that the JVM used a specific pinning mechanism.
- The `isCopy` value is **not** a success/failure code. Check the **returned pointer** separately: `NULL` indicates the call failed to provide an access region (possibly accompanied by `OutOfMemoryError`).

`isCopy` can be used for **statistics/diagnostics**, but functional code should not branch into "release on copy branch, skip release on direct branch" — **both must release**.

## 5. Memory Contract: Acquire → Use → Release

The `Get<Type>ArrayElements` and `Release<Type>ArrayElements` pair must be treated as a resource lifecycle:

1. Have a non-null `j<type>Array`, read its length with `GetArrayLength` if needed.
2. Call `Get<Type>ArrayElements`, check the pointer for `NULL` before accessing.
3. Use `elems[i]` within the range `0 <= i < length`.
4. Call the **exact corresponding release function** for the same array and pointer, with the appropriate mode.
5. Do not read/write `elems` after release has actually completed; do not store the pointer in a global variable, object, or worker thread for later use.

If the JVM copied, changes to the buffer may **not yet** be in the Java array until release copies them back. If the JVM used direct/pin, changes may affect the original region immediately as native code writes. Java code should not observe half-finished state from another thread: that is not a synchronization protocol; it must be protected with appropriate thread-safety mechanisms.

**Do not use `free(elems)`, `delete[] elems`, or `realloc(elems,...)`:** the memory is managed by the JVM under the JNI contract; only the corresponding `Release...` function has the authority to return the access region. Calling release with the wrong type or with a pointer not obtained from the corresponding Get function can cause undefined behavior.

### 5.1. The Three `mode` Values of `Release<Type>ArrayElements`

| `mode` | When the JVM **copied** | When the JVM returned a **direct region** |
| --- | --- | --- |
| `0` | Copy changes from the buffer back to the Java array (if needed), then free the JNI buffer | End access, perform necessary cleanup/unpin operations |
| `JNI_COMMIT` | Copy changes back to the Java array but **do not free the temporary buffer yet** | Mode has no separate copy-back effect; must not assume the pointer can still be kept |
| `JNI_ABORT` | Free the temporary buffer, **do not copy** modifications from the buffer to the Java array | Not an undo/rollback operation for modifications that already touched the original memory |

According to the JNI Specification, the `mode` value has no effect on **non-copy buffers**. That explains why **`JNI_ABORT` does not guarantee discarding modifications**: if the pointer points directly to the original region, the values may have already changed before release is called. `JNI_ABORT` only guarantees **skipping the copy-back step when the JVM uses a copy**.

**Use `mode=0` as the default when writing data.** For read-only operations, `JNI_ABORT` is usually sensible: if there is a temporary buffer, it avoids unnecessary copy-back; in both cases it still releases. `JNI_COMMIT` is an advanced case when you want to push copied contents back to Java while still needing the buffer: **if the buffer is a copy**, you must still call a final `Release...` with `0` or `JNI_ABORT` afterward to free it. Do not treat `JNI_COMMIT` as a complete release in the copy branch.

### 5.2. Incorrect Example with `JNI_ABORT`

```c
jint *p = (*env)->GetIntArrayElements(env, arr, NULL);
if (p != NULL) {
    p[0] = 999;
    (*env)->ReleaseIntArrayElements(env, arr, p, JNI_ABORT);
}
```

**It is impossible to say for sure that `arr[0]` still retains its old value.** If `p` is a copy, the modification is not copied back; if `p` points to the original region, the value `999` may have already been written directly. If you need to "try modifying and possibly roll back", **copy into your own buffer**, or process in separate data and actively write only when you truly decide to commit.

## 6. Pointer Hold Duration and GC Impact

The returned pointer is only valid within the **usage window permitted by the API**. Keep the time from Get to Release short:

- Do not hold the pointer while performing slow I/O operations, network calls, or waiting on locks if processing can be separated.
- Do not return `jint *` to Java as a long-lived address of the Java array.
- Do not hand the pointer to another thread to continue using after the current function releases.
- Do not perform processing that can exit early while skipping release; in C, organize a clear exit path (for example, a cleanup label when appropriate).
- If an error occurs while holding an access region, you must still release before exiting, unless the specification allows otherwise; do not arbitrarily call a series of JNI APIs while an exception is pending.

**Why should you not hold it for long?** In the copy branch, the temporary buffer consumes native memory; in the pin/direct branch, the JVM having to keep the original region stable can hinder collector operations. The specific impact depends on the JVM and GC. There is no "fixed maximum pin duration" promised by the specification for the regular GetArrayElements family; the right practice is to **design the ownership duration to be as short as possible**.

## 7. Runnable JNI Example on Java 17+: Same Result Whether the JVM Copies or Uses Direct Access

This example does two things:

1. `increase`: native code increments each element of `int[]` by `5`; uses `ReleaseIntArrayElements(..., 0)` so changes are reflected back to Java under both strategies.
2. `sum`: native code only reads data and computes the sum; uses `ReleaseIntArrayElements(..., JNI_ABORT)` to avoid copy-back when there are no modifications.

Additionally, `increase` returns a boolean observing `isCopy`. **This boolean value depends on the JVM/runtime and must not be used as a mandatory test assertion.**

### 7.1. File `ArrayElementsDemo.java`

```java
import java.util.Arrays;
import java.util.Objects;

public final class ArrayElementsDemo {
    static {
        System.loadLibrary("arrayelementsdemo");
    }

    private ArrayElementsDemo() {
    }

    private static native boolean increaseNative(int[] values);
    private static native int sumNative(int[] values);

    public static boolean increase(int[] values) {
        return increaseNative(Objects.requireNonNull(values, "values"));
    }

    public static int sum(int[] values) {
        return sumNative(Objects.requireNonNull(values, "values"));
    }

    public static void main(String[] args) {
        int[] values = {3, 7, 11};
        System.out.println("before = " + Arrays.toString(values));

        boolean copied = increase(values);
        System.out.println("after = " + Arrays.toString(values));
        System.out.println("sum = " + sum(values));

        System.out.println("isCopy = "
                + (copied ? "JNI_TRUE" : "JNI_FALSE"));
    }
}
```

`Objects.requireNonNull` in the Java wrappers ensures `int[]` is non-null before calling JNI along the demonstration path. The native methods are declared `private static native`, so C receives `jclass` as the second hidden JNI argument. For real-world code with multiple call paths, input validation is needed at the native boundary according to the API contract.

### 7.2. Generating the JNI Header

In the directory containing `ArrayElementsDemo.java`, using JDK 17+:

```bash
javac -h . ArrayElementsDemo.java
```

The command generates `ArrayElementsDemo.class` and `ArrayElementsDemo.h`. The header file contains the declarations `Java_ArrayElementsDemo_increaseNative`, `Java_ArrayElementsDemo_sumNative`, and `jni.h` matching the Java signatures.

### 7.3. File `ArrayElementsDemo.c`

```c
#include "ArrayElementsDemo.h"

/* If GetIntArrayElements fails and the JVM has not left an
   exception, convert the error state to OutOfMemoryError. */
static void report_access_failure(JNIEnv *env) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    jclass error = (*env)->FindClass(env, "java/lang/OutOfMemoryError");
    if (error != NULL) {
        (*env)->ThrowNew(env, error, "Cannot access int[] elements");
        (*env)->DeleteLocalRef(env, error);
    }
}

JNIEXPORT jboolean JNICALL Java_ArrayElementsDemo_increaseNative(
        JNIEnv *env, jclass clazz, jintArray array) {
    (void) clazz;

    jsize length = (*env)->GetArrayLength(env, array);
    if (length == 0) {
        return JNI_FALSE; /* No need to call Get; no actual isCopy. */
    }

    jboolean isCopy = JNI_FALSE;
    jint *elements = (*env)->GetIntArrayElements(env, array, &isCopy);
    if (elements == NULL) {
        report_access_failure(env);
        return JNI_FALSE; /* Exception will be propagated to Java. */
    }

    for (jsize i = 0; i < length; i++) {
        elements[i] += 5;
    }

    /* When copied: sync back to Java then free buffer.
       When direct: end access/allow JVM cleanup. */
    (*env)->ReleaseIntArrayElements(env, array, elements, 0);
    return isCopy;
}

JNIEXPORT jint JNICALL Java_ArrayElementsDemo_sumNative(
        JNIEnv *env, jclass clazz, jintArray array) {
    (void) clazz;

    jsize length = (*env)->GetArrayLength(env, array);
    if (length == 0) {
        return 0;
    }

    /* No need to know whether this access is a copy. */
    jint *elements = (*env)->GetIntArrayElements(env, array, NULL);
    if (elements == NULL) {
        report_access_failure(env);
        return 0; /* Exception will be propagated to Java. */
    }

    jint total = 0;
    for (jsize i = 0; i < length; i++) {
        total += elements[i];
    }

    /* Read-only: skip copy-back, still release per contract. */
    (*env)->ReleaseIntArrayElements(env, array, elements, JNI_ABORT);
    return total;
}
```

**Why is the example correct whether the JVM copies or uses direct access?** `increaseNative` always uses `mode=0`, so if there is a copy, the contents are written back; if not copied, the data is already in the original region. `sumNative` does not modify `elements`, so `JNI_ABORT` does not encounter the "cannot roll back" issue explained above. Every successful Get call has a corresponding Release.

`GetIntArrayElements` can return `NULL` on failure; the example does not dereference a null pointer. When the JVM already has an exception, the helper function preserves it; if not, it attempts to create an `OutOfMemoryError` to avoid silently returning a value that looks like success.

### 7.4. Compiling/Running on Linux (GCC)

Set `JAVA_HOME` to point to a suitable JDK and run in the directory containing the Java/C sources:

```bash
javac -h . ArrayElementsDemo.java

gcc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  ArrayElementsDemo.c -o libarrayelementsdemo.so

java -Djava.library.path=. ArrayElementsDemo
```

### 7.5. Compiling/Running on macOS (Clang)

```bash
javac -h . ArrayElementsDemo.java

clang -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  ArrayElementsDemo.c -o libarrayelementsdemo.dylib

java -Djava.library.path=. ArrayElementsDemo
```

### 7.6. Compiling/Running on Windows (MSVC)

Open a Developer Command Prompt with a compiler matching the JVM architecture; `JAVA_HOME` must be a JDK. In `cmd.exe`:

```bat
javac -h . ArrayElementsDemo.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" ArrayElementsDemo.c /link /OUT:arrayelementsdemo.dll

java -Djava.library.path=. ArrayElementsDemo
```

### 7.7. Execution Output and How to Read It

**The first three stdout lines are always** (when compiling/loading and calling JNI succeeds):

```text
before = [3, 7, 11]
after = [8, 12, 16]
sum = 36
```

The last line is **one of two possibilities**, for example:

```text
isCopy = JNI_TRUE
```

or

```text
isCopy = JNI_FALSE
```

Both cases are **valid**. You should not hard-code an assertion requiring `JNI_TRUE` or `JNI_FALSE`, even when running repeatedly on the same JVM/GC. If you only care about the correctness of the increment and sum operations, the values `[8, 12, 16]` and `36` are the stable test criteria.

**Note for newer JDKs:** On JDK 24+ there are native access restrictions for JNI; you may need to grant native access when running on the classpath with `--enable-native-access=ALL-UNNAMED` (depending on the policy and JDK version in use). This Java/C example uses APIs compatible with **Java 17** and does not require the FFM API.

## 8. Does `GetPrimitiveArrayCritical` Always Avoid Copying?

**No.** JNI also has the pair:

```c
void *GetPrimitiveArrayCritical(
        JNIEnv *env, jarray array, jboolean *isCopy);

void ReleasePrimitiveArrayCritical(
        JNIEnv *env, jarray array, void *carray, jint mode);
```

This is a family intended for **critical access regions**, with the goal of increasing the chance of avoiding copies in some JVMs. However, the specification still allows the JVM to copy if necessary due to memory representation or implementation constraints. Changing `GetIntArrayElements` to `GetPrimitiveArrayCritical` **does not mean guaranteed zero-copy**.

The critical contract has additional **strict restrictions**:

- Keep the duration between Get/Release **very short**.
- Inside a critical region **do not call other JNI functions**, and **do not make system calls that may block waiting for another Java thread** (e.g., waiting on I/O or a corresponding lock).
- The JVM may delay/restrict GC while a critical pointer is held, so holding it too long can affect the entire application.

Only consider `GetPrimitiveArrayCritical` if you just need to process an array in a short loop and have measured a bottleneck. For processing that requires Java callbacks, I/O, waiting on locks, or performing long-running work, avoid keeping a critical region open. You must also not apply the same set of rules to both families while forgetting the extra restrictions of the Critical family.

## 9. When Should You Use `Get/Set<Type>ArrayRegion` Instead?

You do not always need to obtain a pointer to the entire array. JNI has a family of operations that **copy a defined region**:

```c
void GetIntArrayRegion(
        JNIEnv *env, jintArray array,
        jsize start, jsize len, jint *buf);

void SetIntArrayRegion(
        JNIEnv *env, jintArray array,
        jsize start, jsize len, const jint *buf);
```

In C JNI, the actual APIs are called via `(*env)->GetIntArrayRegion(...)` and `(*env)->SetIntArrayRegion(...)`.

- `GetIntArrayRegion` copies the range `[start, start + len)` from the Java array into a C buffer **provided by you**.
- `SetIntArrayRegion` copies data from the C buffer into the corresponding region of the Java array.
- The `Region` family **does not return a pointer needing `Release...`**; you manage your own C buffer memory and must check indices, lengths, and exceptions.
- If you only process a **small slice** of a very large array, Region can avoid having the JVM provide/copy the entire contents when calling GetElements; however, it is still an intentional copy, not a promise to be faster in every case.

Illustrative example (assuming `env`/`arr` are valid and the array has at least three elements):

```c
jint values[3];
(*env)->GetIntArrayRegion(env, arr, 0, 3, values);
/* If there is no exception: values can be read/modified in C. */
values[0] += 100;
(*env)->SetIntArrayRegion(env, arr, 0, 3, values);
```

This code snippet **is not a standalone C program**; after `GetIntArrayRegion` in a real program, you should check for exceptions before using the buffer when invalid arguments are possible.

### 9.1. API Choice Comparison

| Need | Suggested API | Nature |
| --- | --- | --- |
| Read/modify most elements of a primitive array | `Get<Type>ArrayElements` and `Release...` | Copy or direct depending on JVM |
| Read-only primitive array and no copy-back needed | `Get...Elements`, release `JNI_ABORT` | Always release; if copied, skips copy-back step |
| Operate on only a small segment | `Get/Set<Type>ArrayRegion` | Copies specific range, no release pair |
| Very short processing loop, controllable critical region | `GetPrimitiveArrayCritical` / `Release...Critical` | Attempts to reduce copying, but has very strict restrictions |
| Access elements of `Object[]` / `String[]` | `GetObjectArrayElement` / `SetObjectArrayElement` | Works with object references, not primitive pointers |
| Share a native region with explicit lifecycle instead of a Java heap array | `DirectByteBuffer` and appropriate direct buffer APIs | Different memory/ownership design, requires lifecycle management |

## 10. Common Mistakes with Copy/Pin

### Mistake 1 — Not releasing because `isCopy == JNI_FALSE`

```c
jboolean copied;
jint *p = (*env)->GetIntArrayElements(env, arr, &copied);
if (p != NULL && copied == JNI_TRUE) {
    (*env)->ReleaseIntArrayElements(env, arr, p, 0);
}
/* WRONG: the direct branch is not released! */
```

Whether copied or direct, a successfully obtained pointer must be returned to the JVM. Correct code must release after finishing all processing, without relying on `isCopy`.

### Mistake 2 — Treating `JNI_ABORT` as "undo"

`JNI_ABORT` skips copy-back **when the JVM has a copy**, but does not undo modifications if the pointer is direct. If you want an abortable operation, **do not modify the original pointer directly**; process on an independent buffer and then commit intentionally.

### Mistake 3 — Using the pointer after release

```c
jint *p = (*env)->GetIntArrayElements(env, arr, NULL);
if (p != NULL) {
    (*env)->ReleaseIntArrayElements(env, arr, p, 0);
    /* p[0] = 42;  WRONG: p is no longer valid to access. */
}
```

Both a freed copy region and a direct region after release no longer have access rights under the JNI contract.

### Mistake 4 — Using the wrong `Release<Type>ArrayElements`

`GetIntArrayElements` must be paired with `ReleaseIntArrayElements`, using **the same `jintArray` and the same pointer** provided. Do not substitute `ReleaseByteArrayElements` or free with a C allocator.

### Mistake 5 — Forgetting to check `NULL` and exceptions

`Get...Elements` can return `NULL` (e.g., out of memory). Dereferencing immediately causes a native crash. If you need to return a success value to Java, handle the failure as an exception/clear error path and still clean up previously acquired resources.

### Mistake 6 — Assuming changes are visible before release

If the JVM copied, the Java array contents may not be synchronized yet. If direct, changes may already exist in the heap, but **that does not mean other threads are allowed to race-read them**. `Get/Release...Elements` does not provide a standalone Java Memory Model synchronization protocol; use locking, ownership, or explicit data handoff if multiple threads are involved.

### Mistake 7 — Using `JNI_COMMIT` and thinking you are done

If the JVM copied, `JNI_COMMIT` copies the contents back but **keeps the temporary buffer**. A final appropriate release is needed to free it. The simplest approach for normal tasks is to release with `mode=0` once.

### Mistake 8 — Using `GetPrimitiveArrayCritical` for slow operations

Holding a critical pointer during network calls, lock waits, or JNI callbacks can violate the API's restrictions and impact GC. Long processing should be separated from the critical region.

## 11. Practical Design Scenarios

**Scenario A: A C library processes an entire `short[]` audio sample array.** If each call processes a complete data block and needs to write results back, use `GetShortArrayElements`, modify in native code, and release with `0`. Measure overall time; pin/copy is a JVM decision, and you should not target a specific `isCopy` value.

**Scenario B: Reading only a few header bytes from a very large `byte[]` array.** Using `GetByteArrayRegion` with the exact header size is usually easy to control: only a portion is copied, the buffer is owned by C code, and no Java array pointer is held.

**Scenario C: Needing to read an array multiple times without modifying it.** You can `Get<Type>ArrayElements` and release with `JNI_ABORT` in each short scope. If the same algorithm is called frequently, measure per-call overhead and consider batching work or choosing a different memory structure; do not hold the pointer for long just to save calls.

**Scenario D: Wanting to "try modifying" with the option to cancel.** Do not use `JNI_ABORT` as a transaction. Create an independent application-managed copy, process on the copy, and only write to the Java array when you decide to apply it.

**Scenario E: The array is modified concurrently by multiple Java threads.** Do not use `isCopy` to infer that data will be consistent. Design handoff/synchronization before and after the native call or use thread confinement; avoid uncoordinated concurrent access.

## 12. Self-Check Questions

**1. Is `GetIntArrayElements` guaranteed to return the original address of `int[]`?** No. The JVM may return a copied buffer or a direct-access region. The right rule is to use the pointer within its valid window and always release.

**2. Does `isCopy == JNI_TRUE` mean the Java array changes immediately when C modifies `p[0]`?** No. The copy may only be synchronized when `ReleaseIntArrayElements` performs copy-back (with an appropriate mode).

**3. If `isCopy == JNI_FALSE`, can `ReleaseIntArrayElements` be skipped?** No. The JVM still needs to end access/perform cleanup, even when there is no copy.

**4. Can `JNI_ABORT` be used to discard all native changes?** No. It only skips copy-back of a copied buffer. With a direct pointer, changes may have already been written to the real array.

**5. Why is `JNI_COMMIT` not enough in the copy branch?** Because the temporary buffer has not been freed yet; there must be a final release with `0` or `JNI_ABORT`.

**6. Does `GetPrimitiveArrayCritical` force the JVM to do zero-copy?** No. The critical API increases the chance of direct access but can still copy, while requiring a very short critical duration and restricting inner calls.

**7. If you only need to read five elements in the middle of a million-element array, what should you consider?** `Get<Type>ArrayRegion` for the specific slice, followed by error checking; avoid managing a pointer for the whole array unnecessarily.

## 13. Checklist When Writing and Reviewing JNI Array Code

1. Choose the right primitive `Get<Type>ArrayElements` family for the array type; do not use it with object arrays.
2. Ensure `jarray` is non-null; handle length and index bounds.
3. Check the returned pointer for **`NULL`** before dereferencing.
4. Treat `isCopy` only as one-time observational information, not a condition to skip release or a performance guarantee.
5. If modifying the array and wanting to keep the result, prefer `Release(..., 0)`.
6. If **read-only**, you can use `JNI_ABORT` to skip copy-back; remember it is not a rollback for operations that already modified data.
7. If using `JNI_COMMIT` on a copied buffer, there must be a final release to free it.
8. Do not hold the pointer too long, use it after release, free it manually, or pass it to another thread without a safety contract.
9. If only processing a slice, consider `Get/Set<Type>ArrayRegion`; if considering Critical, strictly follow all blocking/JNI call restrictions.
10. Test logic results across **multiple JVMs/GCs/OSes** if the product requires it; do not assert a fixed `isCopy` value. Benchmarks should measure latency, GC, and native memory.

## Official References

- [Oracle — JNI Functions (Java 17): Get<PrimitiveType>ArrayElements and Release<PrimitiveType>ArrayElements](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): pointer rules, `isCopy`, `mode=0`, `JNI_COMMIT`, `JNI_ABORT`.
- [Oracle — JNI Functions (Java 17): Get/Set<PrimitiveType>ArrayRegion](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): operations for copying an array segment.
- [Oracle — JNI Functions (Java 17): GetPrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): meaning of critical regions and restrictions.
- [Oracle — JNI Specification (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): overview of types, reference lifecycles, and how JNI binds Java/C.
- [OpenJDK — JEP 472: Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): warning/permission configuration behavior for JNI starting in JDK 24.