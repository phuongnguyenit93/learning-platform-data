# Managing Reference Frames with PushLocalFrame and PopLocalFrame in JNI

## 1. The Problem: Local References Accumulating in a Long-Running Native Method

In the Java Native Interface (JNI), C/C++ code interacts with Java objects through **JNI references** such as `jobject`, `jstring`, `jclass`, or `jobjectArray`. When Java transfers control to a `native` method, the JVM creates a **local reference frame**. Local references in that frame are usually reclaimed automatically by the JVM after the native method finishes.

This automatic mechanism is convenient for short functions, but it can cause problems in a native function that processes **many elements in a single call**. For example, C code loops 50,000 times, each iteration calling `GetObjectArrayElement` or `NewStringUTF`, creating additional local references. If it only waits for the native method to finish, new handles can accumulate throughout the loop, consuming JVM resources and keeping Java objects reachable longer than necessary.

To organize a reference cleanup scope, JNI provides:

~~~c
jint PushLocalFrame(JNIEnv *env, jint capacity);
jobject PopLocalFrame(JNIEnv *env, jobject result);
~~~

- **`PushLocalFrame`:** opens a new local reference frame, guaranteeing the ability to create at least `capacity` local references in that frame.
- **`PopLocalFrame`:** closes the current frame, deleting all local references belonging to the frame; it can pass **one result reference** back to the previous frame.
- Both operations manage **JNI handles**, do not directly remove Java objects from the heap, do not force the garbage collector (GC) to run, and do not free C memory allocated by `malloc`.

**Lesson objectives:** understand the relationship with GC, distinguish local/global references, balance Push/Pop on every branch, retain a result with `PopLocalFrame(result)`, handle exceptions, and practice with standalone compilable and runnable Java 17 + C code.

## 2. Local References Differ from Java Objects and Global References

A **Java object** is an entity on the heap managed by the JVM; a **JNI reference** is a handle that allows native code to refer to that object through the JNI API. Multiple handles can point to the same Java object at the same time.

| JNI Reference Type | Typical Lifetime | Management Mechanism | Impact on GC |
|---|---|---|---|
| **Local reference** | While the native method is running or until deleted/frame is popped | JVM automatically cleans up when the native method returns; native code can clean up early | Acts as a strong reference while valid; can keep the object reachable |
| **Global reference** | Across multiple JNI calls, until explicitly deleted | `NewGlobalRef` / `DeleteGlobalRef` | Strong reference; can keep the object alive for a long time |
| **Weak global reference** | Handle exists until deleted; the target may be collected earlier by GC | `NewWeakGlobalRef` / `DeleteWeakGlobalRef` | Does not guarantee keeping the target object alive |

For example, `NewStringUTF(env, "hello")` returns a `jstring` local reference to the created Java string. When the local reference is deleted, it means the handle is no longer valid, **not** that the object is destroyed immediately. If Java code, a field, or a global reference still holds that object, GC cannot treat it as unreachable just because one local JNI handle has disappeared.

**Distinguishing data types:**

- `jstring`, `jclass`, `jarray` are all forms of JNI references and must be managed according to their lifetime.
- `jint`, `jlong`, and primitive types are values, not references.
- `jfieldID`, `jmethodID` are metadata identifiers, not `jobject`; do not call `DeleteLocalRef` on these IDs.
- Pointers from `GetStringUTFChars` or `malloc` are not JNI local references. They require their corresponding release/free operations, even after the frame has been popped.

## 3. Understanding Local Reference Frames as a LIFO Stack

When Java calls a native method, the JVM already has an initial frame for that call. C code can create additional **nested sub-frames**:

~~~text
Java calls nativeMethod()
    |
    v
[Root frame F0: exists for the native call]
  - receiver/object arguments
  - ref created before push
       |
       | PushLocalFrame(env, 8) == JNI_OK
       v
  [Sub-frame F1]
    - refA, refB... created in F1
    - refs belonging to F0 are still usable
         |
         | PushLocalFrame(env, 4) == JNI_OK
         v
    [Sub-frame F2]
      - refC, refD created in F2
         |
         | PopLocalFrame(env, NULL)
         v
    [F2 closed: refC and refD become invalid]
    [F1 is still active]
       |
       | PopLocalFrame(env, NULL)
       v
[F1 closed: refA and refB become invalid]
[F0 continues]
       |
       | nativeMethod() returns to Java
       v
[JVM reclaims remaining local refs belonging to the native call]
~~~

**LIFO (last in, first out)** rule: the frame pushed later must be popped first. Every **successful** `PushLocalFrame` needs a corresponding `PopLocalFrame` before exiting its scope.

Local references created in a **parent frame** remain valid in the active child frame. Conversely, local references created in a **child frame** must not be used after the child frame has been popped, even if a C variable still holds the bit pattern of the old handle.

This is a **reference management frame**, not a new C function call, does not create a thread, and does not open an independent Java method stack frame.

## 4. PushLocalFrame: Capacity Is a Guarantee, Not an Object Count or Byte Count

C API:

~~~c
jint PushLocalFrame(JNIEnv *env, jint capacity);
~~~

**Inputs:**

- `env` is a valid JNI interface pointer for the **current thread**.
- `capacity` must be **greater than 0** according to the specification; it is the minimum number of local references that can be created in the new frame.

**Outputs:**

- Success: returns `JNI_OK`, equal to `0`, and the new frame has been opened.
- Failure: returns a negative code; no new frame is opened. According to the specification, failure may be associated with a pending Java `OutOfMemoryError`; implementations may also limit the supported capacity.

Correct usage pattern in a JNI method returning an object:

~~~c
if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
    /* No new frame, do not call PopLocalFrame. */
    return NULL;
}

/* Create and use local references here. */

(*env)->PopLocalFrame(env, NULL);
return NULL;
~~~

This is a **structural snippet**, not a complete C file.

`PushLocalFrame(env, 8)` does not allocate eight Java objects and does not reserve an eight-byte heap region. It guarantees that **at least eight JNI local handles can be created in the new frame**. The JVM may allow creating more than that, but capacity cannot be treated as a hard limit or as an unlimited growth capability.

A typical native method is guaranteed by the JVM to be able to create at least **16 local references** upon entry. That is not enough to skip cleanup in a very long loop.

**Choose capacity based on the number of handles that need to stay alive concurrently in one iteration**, for example one element, one class, and one temporary string can use capacity 8. Do not use the total number of loop iterations as capacity if each iteration already pops all refs.

## 5. PopLocalFrame: Clean Up Everything, or Keep Exactly One Result

C API:

~~~c
jobject PopLocalFrame(JNIEnv *env, jobject result);
~~~

There are two important cases.

### 5.1. Not Keeping a Result: `PopLocalFrame(env, NULL)`

When only temporary objects are needed during processing:

~~~c
if ((*env)->PushLocalFrame(env, 4) != JNI_OK) {
    return; /* Example inside a native method returning void. */
}

jstring temp = (*env)->NewStringUTF(env, "temporary");
if (temp == NULL) {
    (*env)->PopLocalFrame(env, NULL);
    return;
}

/* Use temp while the frame is still active. */

(*env)->PopLocalFrame(env, NULL);
/* Do not use temp after this. */
~~~

This is an **illustrative snippet** inside a native method returning `void`. It emphasizes that `PopLocalFrame(NULL)` invalidates all local handles created in the new frame. If a Java exception is pending when `NewStringUTF` fails, `PopLocalFrame` is still allowed to be called for cleanup before returning to Java to handle the exception.

### 5.2. Wanting to Keep One Object: `PopLocalFrame(env, result)`

Suppose C code creates a `jstring` in a child frame but wants to return that string to Java. Use `PopLocalFrame` with a still-valid handle as the argument:

~~~c
if ((*env)->PushLocalFrame(env, 4) != JNI_OK) {
    return NULL;
}

jstring inside = (*env)->NewStringUTF(env, "kept");
if (inside == NULL) {
    (*env)->PopLocalFrame(env, NULL);
    return NULL;
}

return (jstring) (*env)->PopLocalFrame(env, inside);
~~~

This is a **snippet inside a JNI method returning `jstring`**, which will appear in the complete program below.

How to understand it:

~~~text
Before Pop:
  F0 (parent frame)       : [oldRef]
  F1 (child frame)        : [tempA, inside, tempB]

  kept = PopLocalFrame(env, inside)

After Pop:
  F0 (parent frame)       : [oldRef, kept]
  F1                      : reclaimed
  tempA, inside, tempB    : old handles become invalid
  kept                    : valid local reference in F0
~~~

`PopLocalFrame` does not copy the string `"kept"` into a new object. It **returns a local reference in the previous frame pointing to the same Java object**. The old handle value `inside` must not be reused after popping; you must use the **return value** of `PopLocalFrame`.

If there is no object to keep, pass `NULL`. Never call pop if push did not succeed; and never pop a frame twice.

## 6. Runnable Example: One Loop Cleaning Up Refs, One Result Surviving Across the Frame

We will write a **Java 17+ program and C JNI library** with two native methods:

1. `sumLengths(int iterations)`: each iteration opens a frame, creates the string `"JNI"`, reads its length, closes the frame, and keeps no local reference.
2. `keepOne()`: opens a frame, creates the string `"kept"`, closes the frame, but passes the result local reference back to the parent frame to return to Java.

All files are placed in the same directory:

~~~text
local-frame-demo/
├── LocalFrames.java
├── localframes.c
├── LocalFrames.h       (generated by javac -h)
├── LocalFrames.class   (generated by javac)
└── native library      (name depends on the operating system)
~~~

### 6.1. Write `LocalFrames.java`

~~~java
public final class LocalFrames {
    static {
        System.loadLibrary("localframes");
    }

    private LocalFrames() {
    }

    private static native long sumLengths(int iterations);

    private static native String keepOne();

    public static void main(String[] args) {
        System.out.println("total = " + sumLengths(4));
        System.out.println("result = " + keepOne());
    }
}
~~~

The `static` block loads the native library before the methods are called. Both methods are `static native`, so the C functions implicitly receive `JNIEnv *` and `jclass`; `sumLengths` also receives a `jint` corresponding to the Java `int` parameter.

### 6.2. Generate the JNI Header with the JDK

Run the command from the directory containing `LocalFrames.java`:

~~~bash
javac -h . LocalFrames.java
~~~

The result includes `LocalFrames.class` and `LocalFrames.h`. The generated header has two core declarations:

~~~c
JNIEXPORT jlong JNICALL Java_LocalFrames_sumLengths
  (JNIEnv *, jclass, jint);

JNIEXPORT jstring JNICALL Java_LocalFrames_keepOne
  (JNIEnv *, jclass);
~~~

This is an **excerpt**; the real header also contains include guards and `#include <jni.h>`. Use the generated header; do not invent C signatures by hand.

### 6.3. Write `localframes.c`

~~~c
#include "LocalFrames.h"

JNIEXPORT jlong JNICALL Java_LocalFrames_sumLengths(
    JNIEnv *env, jclass clazz, jint iterations
) {
    (void) clazz;

    if (iterations <= 0) {
        return 0;
    }

    jlong total = 0;

    for (jint i = 0; i < iterations; ++i) {
        /* A new frame on each iteration. */
        if ((*env)->PushLocalFrame(env, 4) != JNI_OK) {
            /* Push failed: no new frame to pop. */
            return 0;
        }

        jstring temporary = (*env)->NewStringUTF(env, "JNI");
        if (temporary == NULL) {
            /* Frame was pushed; clean up even when an exception is pending. */
            (*env)->PopLocalFrame(env, NULL);
            return 0;
        }

        total += (jlong) (*env)->GetStringLength(env, temporary);

        /* No need to keep temporary for the next iteration. */
        (*env)->PopLocalFrame(env, NULL);
    }

    return total;
}

JNIEXPORT jstring JNICALL Java_LocalFrames_keepOne(
    JNIEnv *env, jclass clazz
) {
    (void) clazz;

    if ((*env)->PushLocalFrame(env, 4) != JNI_OK) {
        return NULL;
    }

    jstring inside = (*env)->NewStringUTF(env, "kept");
    if (inside == NULL) {
        (*env)->PopLocalFrame(env, NULL);
        return NULL;
    }

    /* Return the ref in the parent frame, not the old inside handle. */
    return (jstring) (*env)->PopLocalFrame(env, inside);
}
~~~

This is the **complete C file** for the example. `JNIEXPORT` and `JNICALL` are provided by the JNI header through the exact declarations; the C functions use those exact signatures. `GetStringLength` returns the **UTF-16 length** of a Java string; since `"JNI"` consists of three ASCII letters, the length is 3. The `total` variable uses `jlong` to accumulate more safely than `int` for large iteration counts; the example only calls four iterations.

Check the two rules in C:

- After `PushLocalFrame` fails, the function returns immediately and **does not pop**.
- After `PushLocalFrame` succeeds, both the success path and the `NewStringUTF` failure path **pop exactly once**.
- `keepOne` does not return `inside` directly after popping, but instead returns the **local handle produced by `PopLocalFrame` in the parent frame**.
- `PopLocalFrame(env, NULL)` cleans up temporary refs after each iteration; one iteration cannot leave new refs accumulating into the next iteration.
- Returning `0` or `NULL` when an exception is pending is just a C-level return value; the Java side will see the pending exception. Do not call `ExceptionClear` on your own to hide an OOM error.

### 6.4. Compile on Linux, macOS, or Windows

Prerequisites: JDK 17+ with `jni.h`, `JAVA_HOME` pointing to the JDK, and a C compiler matching the **architecture of the running JVM**. Run **one** set of commands for your operating system after running `javac -h`.

**Linux — GCC:**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  localframes.c -o liblocalframes.so

java -Djava.library.path=. LocalFrames
~~~

**macOS — Clang:**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  localframes.c -o liblocalframes.dylib

java -Djava.library.path=. LocalFrames
~~~

**Windows — MSVC Developer Command Prompt (cmd.exe):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" localframes.c /Fe:localframes.dll

java -Djava.library.path=. LocalFrames
~~~

Depending on the operating system, `System.loadLibrary("localframes")` searches for the corresponding name `localframes.dll`, `liblocalframes.so`, or `liblocalframes.dylib` across the paths configured by the JVM. `-Djava.library.path=.` is placed **before** the class name `LocalFrames` so the JVM looks for the library in the current directory.

**Exact stdout when built and loaded successfully:**

~~~text
total = 12
result = kept
~~~

Why? `sumLengths(4)` calls `GetStringLength` on `"JNI"` of length 3 UTF-16 code units four times in total, so `4 × 3 = 12`. `keepOne` creates a string in the child frame, uses `PopLocalFrame(env, inside)` to transfer a reference to the parent frame, and returns `"kept"` to Java. The appearance of the output does not assert that GC ran; the example demonstrates **the reference contract and return value**.

## 7. Exception Handling: Push Failure and NewStringUTF Failure Differ

In JNI, a Java exception is recorded as a **pending exception** in the current thread. C code does not automatically jump to `catch` like Java; it must check return values or `ExceptionCheck` and exit the function / clean up properly.

| Failure Point | Does the New Frame Exist? | Standard Handling |
|---|---|---|
| `PushLocalFrame` returns other than `JNI_OK` | **No** | Do not call `PopLocalFrame`; handle/propagate the error |
| `NewStringUTF` returns `NULL` after a successful push | **Yes** | `PopLocalFrame(env, NULL)`, return so Java handles the pending exception |
| Another JNI API throws an exception while inside a child frame | **Yes** | Do not arbitrarily call further JNI APIs; clean up the frame and return |
| Processing succeeds, no object needed | **Yes** | `PopLocalFrame(env, NULL)` |
| Processing succeeds, result object needed | **Yes** | Use the return value of `PopLocalFrame(env, result)` |

`PopLocalFrame` belongs to the group of **JNI functions allowed to be called while an exception is pending**. JNI APIs in general **must not** be called arbitrarily while an exception is pending; if you actually handle exceptions in C, you must thoroughly understand `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, and managing acquired resources.

**Centralized cleanup pattern** (snippet inside a JNI method returning `jobject`; not a standalone program):

~~~c
jobject result = NULL;

if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
    return NULL;              /* Do not pop if push failed. */
}

/* ... process and create a valid result on success ...
   ... on error, leave result = NULL and jump to cleanup ... */

return (*env)->PopLocalFrame(env, result);
~~~

In a real C function, a cleanup label can be used after push succeeds. Regardless of how many `return` statements or error branches there are, **each successful push must be popped exactly once**. Do not pop twice, do not leave an active frame unpopped, and do not pop a frame that was never created.

## 8. Comparing Push/Pop with Other Reference Management APIs

| API | Purpose | Creates/Closes Frame? | Commonly Used When |
|---|---|---|---|
| `DeleteLocalRef(env, ref)` | Deletes a specific local reference | No | One iteration creates only a few references |
| `EnsureLocalCapacity(env, n)` | Guarantees at least n additional local references can be created in the **current** frame | No | Need to prepare capacity without needing a cleanup scope |
| `PushLocalFrame(env, n)` | Creates a child frame with capacity at least n | **Creates** | Each record/batch produces many temporary refs |
| `PopLocalFrame(env, result)` | Closes the frame, cleans up in bulk, and optionally keeps one ref to parent | **Closes** | Ending a local refs management scope |
| `NewLocalRef(env, ref)` | Creates a new local handle to the same object in the current scope | No | Need an additional local handle |
| `NewGlobalRef(env, ref)` | Creates a global handle that persists across multiple calls | No | Long-term object caching/ownership |

### Why Can't EnsureLocalCapacity Replace PushLocalFrame?

`EnsureLocalCapacity` makes room for more local refs **but does not create a sub-frame**. If every loop iteration calls `EnsureLocalCapacity` and creates a new string without `DeleteLocalRef`, refs still accumulate in the native method's frame. `PushLocalFrame` + `PopLocalFrame` creates a boundary to reclaim **the entire group of refs**.

### Why Can't NewLocalRef Replace PopLocalFrame(result)?

If `NewLocalRef(env, inside)` is called **inside the child frame**, the new handle also belongs to the active frame. Popping that frame still invalidates both handles. To pass an object to the parent frame, use **`PopLocalFrame(env, inside)`** and take its return value. If it needs to be kept long-term across multiple native calls, consider `NewGlobalRef` with an explicit release lifetime.

### When Is DeleteLocalRef Simpler?

If each iteration only fetches one element with `GetObjectArrayElement`, processes it immediately, and does not keep it, `DeleteLocalRef(env, element)` can be simpler. Push/Pop is useful when the processing logic creates **many temporary refs**, nests multiple functions, has multiple exit paths, or needs a clear scope design.

## 9. GC, Threads, and Native Resources: Important Boundaries

### 9.1. Pop Does Not Force GC to Free Objects Immediately

`PopLocalFrame` makes handles in the child frame invalid. If a Java variable, object field, class static field, or a global reference still points to the object, the object remains reachable. If no roots remain, GC **may** collect it later; `PopLocalFrame` does not schedule when GC runs.

Keeping a Java object alive is a consequence of strong local references, but the object and the reference are **two different things**. Do not use an immediately observed heap memory value to conclude whether Pop succeeded or failed.

### 9.2. Pop Does Not Replace Native Resource Cleanup

If native code has called:

- `malloc`: requires `free`;
- `GetStringUTFChars`: requires `ReleaseStringUTFChars`;
- `GetByteArrayElements`: requires `ReleaseByteArrayElements`;
- `GetPrimitiveArrayCritical`: requires `ReleasePrimitiveArrayCritical`;
- OS functions allocating a file/socket/handle: require closing via the corresponding API.

These pointers/resources do not disappear automatically just because the local frame was popped. Release them with the matching API pair, especially on error paths when a Java exception is pending.

### 9.3. Local References and JNIEnv Are Tied to a Thread

Local references are only valid in the **thread that created them**; you must not pass a raw local `jobject` to another native thread. `JNIEnv *` is also a per-thread interface and must not be reused from another thread. When you need to keep a Java object across multiple calls or switch thread contexts, use a global reference with clear ownership and follow JNI attach/detach rules.

In a native thread attached via `AttachCurrentThread`, local references may persist until the thread detaches unless explicitly cleaned up; therefore, long-running attached native threads should manage refs with `DeleteLocalRef` or Push/Pop.

### 9.4. Using a Handle After Pop Is a Bug

**The following C snippet is an INCORRECT example, shown only to identify the bug, not to run:**

~~~c
/* env is valid; error checks omitted to illustrate the mistake. */
(*env)->PushLocalFrame(env, 4);
jstring stale = (*env)->NewStringUTF(env, "hello");
(*env)->PopLocalFrame(env, NULL);

/* WRONG: stale is a JNI handle belonging to a popped frame! */
(*env)->GetStringLength(env, stale);
~~~

Even if the `"hello"` object is still alive due to another reference, the `stale` handle has been invalidated. The result may be a JNI check error or a JVM crash; do not expect Java `try/catch` to catch every error in C. The fix: if the string is needed, pass the valid `stale` into `PopLocalFrame(env, stale)` **before the frame closes**, then keep the **returned handle**.

## 10. Pattern for Looping Over Elements from a Java Object Array

Suppose a native method receives `jobjectArray array` and processes elements one by one. A per-iteration frame prevents local refs from accumulating:

~~~c
/* Snippet in a native method returning void; env/array/count are valid. */
for (jsize i = 0; i < count; ++i) {
    if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
        return; /* Push failed, do not pop an unopened frame. */
    }

    jobject element = (*env)->GetObjectArrayElement(env, array, i);
    if (element == NULL && (*env)->ExceptionCheck(env)) {
        (*env)->PopLocalFrame(env, NULL);
        return;
    }

    /* element may legitimately be null if the array contains null.
       Process element; create additional temporary refs if needed.
       Add exception checks on JNI calls that can fail. */

    (*env)->PopLocalFrame(env, NULL);
}
~~~

This is an **illustrative code skeleton**, not a standalone compilable file, and contains no business logic. It uses `ExceptionCheck` to distinguish a **valid null element** from `NULL` caused by an exception when fetching the element. Before putting it into a real application, you must add element processing, error branches, and corresponding cleanup. Each iteration creates its own frame of capacity 8; the frame is popped at the end of the iteration so the number of temporary local refs does not grow with the total number of iterations.

## 11. Common Mistakes and Diagnostic Tools

| Mistake | Consequence | Fix |
|---|---|---|
| Not checking the result of `PushLocalFrame` | May pop a frame that does not exist | Only pop if push returns `JNI_OK` |
| Forgetting to pop on an error `return` branch | Holds refs/frame longer than expected, unbalanced cleanup | Consolidate exits through cleanup or balance every branch |
| Double-pop | Pops the wrong frame, may corrupt JNI state | Each successful push must be popped only once |
| Returning `inside` after `PopLocalFrame(NULL)` | Use-after-pop on an old local handle | `return PopLocalFrame(env, inside)` |
| Thinking `capacity` is heap bytes or number of objects | Misestimates resources | Count concurrently live local references |
| Using `EnsureLocalCapacity` instead of cleanup | Refs still accumulate | `DeleteLocalRef` or Push/Pop |
| Using `NewLocalRef` in a child frame to “keep” a ref | The new ref is also popped | `PopLocalFrame(result)` |
| Storing a local `jobject` in a static C variable | Ref becomes invalid after the frame/native call | Use `NewGlobalRef` if long-term ownership is needed |
| Popping and forgetting `ReleaseStringUTFChars`/`free` | Native resource leak | Release/free separately according to the API |
| Using a local ref or `JNIEnv *` from another thread | Violates the JNI contract, may crash | Manage per thread and use global refs when needed |

On HotSpot, you can enable JNI checks:

~~~bash
java -Xcheck:jni -Djava.library.path=. LocalFrames
~~~

`-Xcheck:jni` can warn about certain invalid JNI usages (such as using an invalidated reference), but it does not prove native code is completely safe. For a valid program, the application stdout remains:

~~~text
total = 12
result = kept
~~~

If the JVM crashes in C/C++ code, inspect JVM diagnostic information such as `hs_err_pid...log` (if generated), the native stack, and the path of JNI references. Do not actively call `System.gc()` to “test whether the frame has been popped”: GC is not a tool for verifying the lifetime of a JNI handle.

## 12. Self-Check Questions

1. Why can a native method with 100,000 loop iterations still run out of local reference resources even though the JVM reclaims refs when the function returns?
2. Does `PushLocalFrame(env, 8)` create eight Java objects or hard-limit the number of refs to eight?
3. After a `PushLocalFrame` returns a negative error, should `PopLocalFrame` be called?
4. Why does `PopLocalFrame(env, NULL)` not mean every object from that frame has been collected by GC?
5. If you need to return a Java string created in a child frame, how do you use `PopLocalFrame(env, result)`?
6. What is the difference between `EnsureLocalCapacity` and `PushLocalFrame` in releasing refs after a processing batch?
7. When `NewStringUTF` fails after a successful push, can `PopLocalFrame` be called while a Java exception is pending?
8. If you call `NewLocalRef` inside a child frame and then pop, does the new reference survive in the parent frame?
9. When JNI code uses `malloc`, `GetStringUTFChars`, and `NewStringUTF`, which kind of resource does `PopLocalFrame` handle?
10. Why should you not pass a local `jobject` or `JNIEnv *` to another C thread?

**Key takeaway:** `PushLocalFrame` creates a new local JNI reference scope with a minimum capacity; `PopLocalFrame(env, NULL)` cleans up all temporary refs in that scope, while `PopLocalFrame(env, result)` returns a valid reference in the parent frame. Always check push, balance pop, keep the new handle after pop, respect thread boundaries, and clean up native resources separately.

### References

- [JNI Specification — Local References, PushLocalFrame, PopLocalFrame](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html): API signatures, capacity, return values, and scope.
- [JNI Specification — Referencing Java Objects](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): local/global references, validity lifetime, and relationship with GC.
- [Android NDK JNI Tips — Local references and exceptions](https://developer.android.com/ndk/guides/jni-tips): long loop scenarios, attached native threads, and cleanup with pending exceptions.
