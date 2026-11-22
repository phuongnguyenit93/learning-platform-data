# Why a JNI Reference Is Not a Stable Address of a Java Object

## Lesson Objectives

In the Java Native Interface (JNI), parameters of type `jobject`, `jstring`, `jclass`, or `jarray` look like pointers on the C/C++ side. However, **a JNI reference is a handle managed by the JVM, not a guarantee that its bit value is the current physical address of the Java object on the heap**. The JVM needs such a reference mechanism to manage object lifetimes and allow the garbage collector (GC) to move objects while native code still accesses the logically correct object.

This lesson explains why `jobject` cannot be used as a stable address, how the GC and JNI coordinate, the limits of local/global/weak global references, how to determine identity with `IsSameObject`, and how to safely retain a Java object across multiple native calls. Examples use Java 17+ and C JNI, clearly distinguishing standalone code from illustrative snippets.

## 1. Java Reference, JNI Reference, and Memory Address Are Three Different Concepts

A familiar Java snippet:

~~~java
Object a = new Object();
Object b = a;
System.out.println(a == b); // true: same object by identity
~~~

`a` and `b` are **Java language-level references**; the Java specification does not define them as address numbers that an application is allowed to dereference. When Java calls:

~~~java
private static native void inspect(Object value);
~~~

the C code receives a parameter of type `jobject`:

~~~c
JNIEXPORT void JNICALL Java_Example_inspect(
        JNIEnv *env, jclass cls, jobject value);
~~~

For `static native`, the JVM prepends two arguments: `JNIEnv *` and `jclass`. An instance method receives `jobject receiver` as the second argument. `value` is a JNI reference to the passed-in Java object. **Only the JNI API is the guaranteed path to use this reference.**

It is necessary to distinguish:

| Concept | Meaning | Can it be used directly as a Java heap address? |
| --- | --- | --- |
| Java reference (`Object a`) | Language-level reference to an object | No; Java does not grant permission to read physical addresses |
| JNI reference (`jobject`, `jclass`, `jstring`, `jarray`) | Native handle tracked by the JVM, with a valid lifetime and scope | No; must call JNI functions |
| Native pointer (`void *`, `char *`, `uint8_t *`) | Address of a native memory region or a region lent by an API | Can be used within the bounds of the allocation/acquire/release contract; not synonymous with a Java object address |
| `jlong` used as a token | A 64-bit integer whose meaning is defined by the application | Does not automatically become a valid handle; cannot replace `jobject` or ownership mechanisms |

In headers, `jobject` may have a pointer-like representation, and even two handles may have values that look identical on a specific JVM. **A C type that looks like a pointer does not create an address contract.** Do not use `(void *)value` to dereference contents, do not cast `value` into `uintptr_t` and treat it as an address, and do not infer object layout from offsets.

## 2. Why Does the JVM Need Indirection?

Many modern garbage collectors have the ability to **move/compact** objects during heap management. For example, at one point object `X` might reside in heap region A; after a collection phase, the JVM places the same object by identity at heap region B. The important thing is that the object is still that object, and valid Java references and JNI references continue to point to it logically.

Conceptual diagram (not a mandatory layout of a JVM):

~~~text
Before GC:

Native JNI code                 JVM manages reference            Java heap
local jobject r  ──────────────>  handle / root  ───────────────> object X at A

After GC compaction:

Native JNI code                 JVM updates management           Java heap
local jobject r  ──────────────>  handle / root  ───────────────> object X at B

Identity: still object X.       Physical storage address: may change.
~~~

This example depicts one implementation using a handle table. A JVM can also use other strategies (such as updating or encoding references, read barriers, or custom handle mechanisms). **JNI only guarantees valid reference semantics and lifetimes; it does not standardize internal handle tables or object addresses.**

Two conclusions must not be confused:

- **A valid JNI reference can follow the same object across GC**, because the JVM recognizes and processes that reference.
- **There is no guarantee that the physical address of the object stays the same**; nor is there any guarantee that GC will move the object every time. The lesson is not to rely on addresses, not a claim that every JVM always moves every object.

If native code holds a raw memory address derived by some trick from an object and GC moves the object, the old address may no longer represent valid data, or may even be reused. A valid JNI reference protects **identity and accessibility through the JVM**, not direct read access to the heap layout.

## 3. A JNI Reference Is "Opaque": What Is Allowed?

In most JNI programs, the safe rules are:

1. Receive `jobject`/`jstring`/`jarray` from native parameters or from the JNI API.
2. Only use JNI functions to read fields, call methods, access arrays/strings, and create/delete reference types.
3. Do not dereference as a C struct and do not store self-interpreted address numbers.
4. Check reference validity by **lifetime and reference type**; do not treat a non-`NULL` pointer value as proof that the handle is still alive.
5. Use `IsSameObject` to compare **object identity** in JNI; do not rely on comparing the bit patterns of two `jobject`s.

Illustrative C JNI example (snippet inside a native function where `env`, `first`, and `second` are all still-valid references):

~~~c
jboolean same = (*env)->IsSameObject(env, first, second);
if (same == JNI_TRUE) {
    /* Both references point to the same object according to JNI identity. */
}
~~~

The `IsSameObject` function compares identity; it does not call Java `equals()`. Two objects can have `equals() == true` yet **not** the same identity. Conversely, Java `a == b` (for reference types) queries identity similarly to the meaning of `IsSameObject`.

### Why Is `first == second` in C Not Enough?

A JVM may create **two different local JNI references** for the same object; `NewLocalRef` is not required to reuse the same handle value as the original reference. If you only compare two pointer-like C variables with `==`, you might be comparing two internal handle slots instead of object identity. The fact that some runtimes happen to give the same bit pattern does not make that approach portable.

Also do not use `System.identityHashCode(object)` as an address; it returns a hash value based on identity, can collide between two objects, and does not represent a heap address.

## 4. Three Types of JNI Object References to Know

| Type | Common creation | Lifetime / where used | Effect on GC eligibility |
| --- | --- | --- | --- |
| **Local reference** | Method arguments, results of many JNI calls, `NewLocalRef` | Valid within the current JNI scope and **the thread that created it**; usually reclaimed automatically when the native method returns | Is a strong reference during its valid lifetime; the JVM may move the object but will not reclaim an object that still has only this strong reference |
| **Global reference** | `NewGlobalRef` | Valid until `DeleteGlobalRef`; can be carried across calls and other threads with proper synchronization | Is a strong reference; keeps the object reachable until deleted or the VM lifetime ends |
| **Weak global reference** (`jweak`) | `NewWeakGlobalRef` | Exists as a JNI handle until `DeleteWeakGlobalRef`, but the target object may no longer exist | Does not keep the object alive; after GC processing, the reference may behave like `NULL` |

**"Global" does not mean a stable object address.** It only extends the lifetime and allows JNI to use the reference across multiple native methods/threads according to the rules. The garbage collector can still move the object held by a global reference.

**"Weak global" is not equivalent to strong global.** A `jweak` can become unusable when GC reclaims the target, even though the `jweak` handle is still stored in a variable by native code. You must create a strong local/global reference from the weak reference before operating on it.

### 4.1. Local References: Scope and Cleanup

For example, if C receives `jobject arg` from a native method, `arg` is a valid local reference within the current call. Many JNI calls return additional local references, such as `FindClass`, `GetObjectField`, or `GetObjectArrayElement`.

If you create local references in a long loop, you should delete each handle when done so as not to accumulate too many local references:

~~~c
/* Illustrative snippet inside a JNI function, assuming array is valid. */
jsize length = (*env)->GetArrayLength(env, array);
for (jsize i = 0; i < length; ++i) {
    jobject item = (*env)->GetObjectArrayElement(env, array, i);
    if ((*env)->ExceptionCheck(env)) {
        return; /* Pending exception exists: caller receives the JVM exception. */
    }

    /* Process item via valid JNI APIs. */

    if (item != NULL) {
        (*env)->DeleteLocalRef(env, item);
    }
}
~~~

This is a **snippet**, not a standalone runnable C program: `env`, `array`, and the return type need to be inside the corresponding native function. In real code, if processing throws an exception, clean up before returning when safe. `DeleteLocalRef` does not immediately free the Java object; it removes one reference root, and then GC decides the object's lifetime based on the entire reference graph.

The APIs `EnsureLocalCapacity`, `PushLocalFrame`, and `PopLocalFrame` help manage many local refs in complex native code. For native threads that attach themselves to the JVM, be especially proactive about deleting leftover local refs; do not assume they are reclaimed after an arbitrary C helper call.

**Do not** store `jobject arg` in a static/global C variable or pass it to another thread and use it after the native method has returned. Specifically, the Java object still being alive in Java **does not revive an old local handle**. To use it after the call, create a `NewGlobalRef` or design native data with clear ownership.

### 4.2. Global References: Intentional Lifetime Extension

~~~c
/* Inside a native method; object is a still-valid local JNI reference. */
jobject retained = (*env)->NewGlobalRef(env, object);
if (object != NULL && retained == NULL) {
    /* There may be a pending OutOfMemoryError. */
    return;
}

/* ... Use retained in subsequent JNI calls, with appropriate synchronization ... */

if (retained != NULL) {
    (*env)->DeleteGlobalRef(env, retained);
}
~~~

These lines illustrate the principle, not a standalone program or a complete multi-call lifetime example. A full runnable example is in Section 8.

A global reference can be carried across threads, **but `JNIEnv *` cannot**: each thread must have its own interface pointer when accessing JNI (a native thread may need to attach via `JavaVM`). Global refs keep objects reachable, so forgetting `DeleteGlobalRef` can cause a **retention leak**, even when Java code no longer holds the object.

Do not use `free(retained)` or `delete retained`. This is a JNI resource managed by the JVM and must be deleted with **`DeleteGlobalRef`**, not as a native heap allocation.

### 4.3. Weak Global References: "Checking Alive" Is Not Enough

~~~c
/* Illustrative example; weak is a valid jweak created from NewWeakGlobalRef. */
jobject strong = (*env)->NewLocalRef(env, weak);
if (strong == NULL) {
    /* Target may have already been reclaimed by GC; also check for exceptions
       because allocating a local reference can fail. */
} else {
    /* While strong is valid, the object is kept reachable. */
    /* Use strong via JNI functions. */
    (*env)->DeleteLocalRef(env, strong);
}
~~~

**Why not just call `IsSameObject(env, weak, NULL)`?** GC can run **after the check** and before you use `weak`. A prior check result does not guarantee the object still exists at a later point (a race between check and use). Creating `NewLocalRef(env, weak)`, verifying the result, and holding the strong local reference throughout the operation is what avoids this race window. Afterward, call `DeleteLocalRef` and finally `DeleteWeakGlobalRef` when the weak reference is no longer needed.

Do not use a result that can change due to GC as a condition to write your own "stable address". Weak JNI references are subject to GC/reference processing policies; there is no portable way to force the target to always stay alive with `jweak` alone.

## 5. What Happens When a Native Method Finishes?

Look at the Java snippet:

~~~java
static native void saveForLater(Object object);

static void demo() {
    Object item = new Object();
    saveForLater(item);
    // Java may still hold item, but the JNI local ref created for
    // the saveForLater parameter is no longer valid after the method returns.
}
~~~

If C is written as follows, the **lifetime is wrong**:

~~~c
/* COUNTEREXAMPLE: never use in real code. */
static jobject invalid_cached;

JNIEXPORT void JNICALL Java_Example_saveForLater(
        JNIEnv *env, jclass cls, jobject object) {
    (void) env;
    (void) cls;
    invalid_cached = object;  /* Only copies the local handle value. */
}
~~~

After the function returns, `invalid_cached` holds an **expired local JNI reference**. Even if Java still has a strong reference to the same object, using the old handle in a JNI API later still violates the contract and can cause a crash or hard-to-reproduce bugs.

Fix it properly by creating a global reference:

~~~c
/* SKETCH: synchronization is needed when multiple threads access retained. */
static jobject retained = NULL;

JNIEXPORT void JNICALL Java_Example_saveForLater(
        JNIEnv *env, jclass cls, jobject object) {
    (void) cls;
    jobject fresh = (*env)->NewGlobalRef(env, object);
    if (object != NULL && fresh == NULL) {
        return; /* On OOM: keep old retained, do not delete. */
    }
    if (retained != NULL) {
        (*env)->DeleteGlobalRef(env, retained);
    }
    retained = fresh;
}
~~~

If `object == NULL`, `NewGlobalRef` returns `NULL` by contract; this snippet deletes the old reference. However, if allocation fails, you must **keep the old global** and let the pending exception propagate back to Java. Do not invent mechanisms to take addresses or retain local references out of fear of `NewGlobalRef` overhead.

The sketch example needs a synchronization mechanism for access to `retained`, ensuring no thread deletes the reference while another thread is using it. A simple way for a synchronized example is to serialize the native methods via `static synchronized` in Java. For libraries with multiple consumers, use a mutex / owner object / native handle table with appropriate thread-safety.

## 6. Object Identity, `equals`, and the Numeric Value of a Handle

Java has two clear concepts:

~~~java
String left = new String("data");
String right = new String("data");
String alias = left;

System.out.println(left == right);       // false
System.out.println(left.equals(right));  // true
System.out.println(left == alias);       // true
~~~

Create the file `IdentityOnly.java` to run standalone:

~~~java
public final class IdentityOnly {
    public static void main(String[] args) {
        String left = new String("data");
        String right = new String("data");
        String alias = left;
        System.out.println("same-object-a=" + (left == right));
        System.out.println("same-value=" + left.equals(right));
        System.out.println("same-object-b=" + (left == alias));
    }
}
~~~

Run on JDK 17 or higher:

~~~bash
javac -encoding UTF-8 IdentityOnly.java
java IdentityOnly
~~~

Stdout:

~~~text
same-object-a=false
same-value=true
same-object-b=true
~~~

If `left` and `right` are passed into JNI, `IsSameObject` returns `JNI_FALSE` because they are two objects with different identities, regardless of their `"data"` contents being equal. If `left` and `alias` are passed, `IsSameObject` returns `JNI_TRUE`.

**Avoid replacing identity with a memorable number.** Neither `hashCode()`, `System.identityHashCode`, nor an assumed address from `jobject` is an absolute unique ID or stable object address defined by the Java/JNI specification. To identify business entities across processes/sessions, the application must generate its own IDs with appropriate scope and uniqueness rules.

## 7. When Does JNI Return a Real Data Pointer?

Occasionally JNI code receives a **native pointer** from APIs such as:

- `GetByteArrayElements`/`GetIntArrayElements` and other primitive array APIs;
- `GetStringChars`/`GetStringUTFChars`;
- `GetPrimitiveArrayCritical`/`GetStringCritical`;
- `GetDirectBufferAddress` for a suitable direct `ByteBuffer`.

These pointers **do not turn `jobject` into a Java object address**. They are access rights to **specific data** with an API-defined lifetime:

| JNI API | What does the pointer point to? | Points to note |
| --- | --- | --- |
| `GetByteArrayElements` | Region of `byte[]` elements, which may be a copy or a pinned region | Do not assume it is a heap object header; call the matching `ReleaseByteArrayElements` |
| `GetStringChars` | Region of UTF-16 code units, which may be a copy | Call `ReleaseStringChars` when done |
| `GetStringUTFChars` | Region of Modified UTF-8 bytes | Call `ReleaseStringUTFChars`; do not confuse MUTF-8 with standard UTF-8 |
| `GetPrimitiveArrayCritical` | Region of primitive elements inside a critical region, which may be a copy | Keep the critical region short, avoid blocking/disallowed JNI calls, release immediately |
| `GetDirectBufferAddress` | Starting address of the direct buffer's memory region | That is the buffer region address, not the `ByteBuffer` object address |

With `GetPrimitiveArrayCritical`, the JVM may **pin** the data region or use another approach (including copying). Native code must not perform long blocking operations or restricted JNI calls inside the critical region. The pointer loses validity after release; whether the JVM actually pins or not is an implementation detail.

With `GetByteArrayElements`, assuming it "always returns a pointer to the heap" is wrong: the JVM may copy. If `isCopy == JNI_TRUE`, you still must follow the release mode to copy back / free the memory as intended. Even when accessing elements directly, the pointer only has the lifetime of the API, **not a permanently stable address of the Java object**.

With `GetDirectBufferAddress`, a direct buffer may use off-heap memory. If native code needs to keep the pointer longer than one call, clearly define ownership and ensure the buffer/native memory stays alive; an appropriate global reference to the buffer can help keep the Java object reachable, but **does not replace the lifetime rules of the underlying allocation**, especially when native memory is owned externally. The API may return `NULL` when the buffer does not support the requested direct access.

## 8. Complete JNI Example: Local Identity and Retaining an Object with a Global Reference

Program goals:

1. Create an additional local reference to the same object and use `IsSameObject` to compare identity.
2. Save the object across **multiple calls** using `NewGlobalRef`.
3. Compare a different object to see that the two objects do not share identity.
4. Delete the global reference with `DeleteGlobalRef`; afterward, the saved state no longer holds an object.

There is no step that reads an object address. The example output is deterministic, **does not need `System.gc()`, and does not depend on whether the JVM moves objects during the run**.

### 8.1. Java source: `ReferenceHandleDemo.java`

~~~java
public final class ReferenceHandleDemo {
    static {
        System.loadLibrary("jnihandles");
    }

    private static native boolean sameViaLocal(Object value);

    // Synchronize operations on the C global variable for this example.
    private static synchronized native void retain(Object value);
    private static synchronized native boolean matches(Object candidate);
    private static synchronized native void clear();

    public static void main(String[] args) {
        Object a = new Object();
        Object b = new Object();

        System.out.println("same-local=" + sameViaLocal(a));
        retain(a);
        try {
            System.out.println("saved-a=" + matches(a));
            System.out.println("saved-b=" + matches(b));
        } finally {
            clear();
        }
        System.out.println("saved-after-clear=" + matches(a));
    }
}
~~~

`static synchronized native` is a Java method that is both `native` and `synchronized`; the JVM acquires the monitor of `ReferenceHandleDemo.class` upon entering each of these methods. Within the scope of the example, the three functions `retain`/`matches`/`clear` all access the same global variable and are serialized through that monitor. When building a native library used concurrently by multiple class loaders, multiple API entry points, or threads that do not go through the monitor, appropriate native-level locking/ownership must be designed.

### 8.2. C source: `ReferenceHandleDemo.c`

~~~c
#include <jni.h>
#include "ReferenceHandleDemo.h"

static jobject saved_global = NULL;

JNIEXPORT jboolean JNICALL Java_ReferenceHandleDemo_sameViaLocal(
        JNIEnv *env, jclass clazz, jobject value) {
    (void) clazz;
    if (value == NULL) {
        return JNI_FALSE;
    }

    jobject alias = (*env)->NewLocalRef(env, value);
    if (alias == NULL) {
        /* If out of memory, there may be a pending exception. */
        return JNI_FALSE;
    }

    jboolean same = (*env)->IsSameObject(env, value, alias);
    (*env)->DeleteLocalRef(env, alias);
    return same;
}

JNIEXPORT void JNICALL Java_ReferenceHandleDemo_retain(
        JNIEnv *env, jclass clazz, jobject value) {
    (void) clazz;

    jobject fresh = NULL;
    if (value != NULL) {
        fresh = (*env)->NewGlobalRef(env, value);
        if (fresh == NULL) {
            /* Allocation failed: do not change saved_global. */
            return;
        }
    }

    if (saved_global != NULL) {
        (*env)->DeleteGlobalRef(env, saved_global);
    }
    saved_global = fresh;
}

JNIEXPORT jboolean JNICALL Java_ReferenceHandleDemo_matches(
        JNIEnv *env, jclass clazz, jobject candidate) {
    (void) clazz;
    if (saved_global == NULL) {
        return JNI_FALSE;
    }

    return (*env)->IsSameObject(env, saved_global, candidate);
}

JNIEXPORT void JNICALL Java_ReferenceHandleDemo_clear(
        JNIEnv *env, jclass clazz) {
    (void) clazz;
    if (saved_global != NULL) {
        (*env)->DeleteGlobalRef(env, saved_global);
        saved_global = NULL;
    }
}
~~~

Points to observe in C:

- `saved_global` has type `jobject` but **is never dereferenced** as a pointer to a Java struct.
- `NewLocalRef` creates a second handle with the same identity, `IsSameObject` confirms it; `DeleteLocalRef` removes the temporary handle.
- `NewGlobalRef` creates a strong JNI root valid across multiple calls. If it fails when `value != NULL`, the function keeps the old handle and lets Java receive the JVM's pending error.
- `matches` compares using `IsSameObject`. It does not compare `saved_global == candidate` because two reference values can differ even when pointing to the same object.
- `clear` deletes the exact global reference created earlier. After clear, the deleted handle is not reused.
- Function types and names must match the header generated by `javac -h`; the `JNIEnv *` and `jclass` parameters precede the Java arguments of `static native` methods.

### 8.3. Build on Linux and Stdout

Requirements: **JDK 17+**, a C compiler supporting C11, `JAVA_HOME` variable pointing to the JDK in use. Place both files in the same directory and run:

~~~bash
javac -encoding UTF-8 -h . ReferenceHandleDemo.java

cc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
   -I"$JAVA_HOME/include" \
   -I"$JAVA_HOME/include/linux" \
   ReferenceHandleDemo.c -o libjnihandles.so

java -Djava.library.path=. ReferenceHandleDemo
~~~

Stdout of the `java` command:

~~~text
same-local=true
saved-a=true
saved-b=false
saved-after-clear=false
~~~

Explanation:

- `same-local=true`: `value` and `alias` are two valid references both pointing to `a`.
- `saved-a=true`: the global reference is alive, `IsSameObject(saved_global, a)` returns true.
- `saved-b=false`: `b` is a different object.
- `saved-after-clear=false`: after `DeleteGlobalRef`, the C variable was set to `NULL`, and `matches` returns false. This **does not prove `a` has been reclaimed by GC** — in `main`, variable `a` may still hold the object, and GC has no fixed schedule.

The compiler command is **for Linux**; on macOS/Windows, the way to create a shared library, file extension, and `include/<platform>` directory differ. The example uses the default package for easy symbol verification. In programs with packages, overloads, or native names with special characters, **use `javac -h`** instead of guessing JNI name mangling.

The generated header file has equivalent prototypes:

~~~c
JNIEXPORT jboolean JNICALL Java_ReferenceHandleDemo_sameViaLocal
  (JNIEnv *, jclass, jobject);
JNIEXPORT void JNICALL Java_ReferenceHandleDemo_retain
  (JNIEnv *, jclass, jobject);
JNIEXPORT jboolean JNICALL Java_ReferenceHandleDemo_matches
  (JNIEnv *, jclass, jobject);
JNIEXPORT void JNICALL Java_ReferenceHandleDemo_clear
  (JNIEnv *, jclass);
~~~

These are **abbreviated prototypes for explanation**; the real header has include guards and other declarations. If the native library is not found, the JVM throws `UnsatisfiedLinkError`; that error relates to path/symbol/library names, not proof that GC changed the Java object's address.

## 9. Weak Global: Choosing Behavior When You Don't Want to Keep the Object Alive

Suppose native code needs a cache attached to a Java object, but caching must not by itself prevent the object from being collected. Use `jweak` and **promote it to a strong local reference before use**:

~~~c
/* Snippet: cached_weak is a valid jweak and has not had DeleteWeakGlobalRef called. */
jobject safe = (*env)->NewLocalRef(env, cached_weak);
if (safe == NULL) {
    if ((*env)->ExceptionCheck(env)) {
        /* Case where reference could not be created, e.g., OOM. */
    } else {
        /* Target can no longer be promoted to a strong reference. */
    }
    /* Do not call methods or access fields on cached_weak at this point. */
} else {
    /* safe keeps the object reachable while working via JNI. */
    /* ... some JNI operations using safe ... */
    (*env)->DeleteLocalRef(env, safe);
}
~~~

This snippet is **illustrative logic**, not a complete C function because it depends on `env` and `cached_weak`. `NewLocalRef` returns `NULL` when the weak target has already been reclaimed; you also need to check for exceptions due to failure to allocate a local reference. If `safe` is created, the strong local ref prevents the target from being reclaimed while that reference remains valid; it does not force an immutable heap address.

An example of check-then-use that is prone to a race:

~~~c
/* WRONG: not safe enough to use weak at a later point. */
if (!(*env)->IsSameObject(env, cached_weak, NULL)) {
    /* GC may process the target between the if and the next operation. */
    /* Do not treat cached_weak as a strong handle at this point. */
}
~~~

When the cache is no longer needed, call `DeleteWeakGlobalRef` exactly once for that valid handle and do not use it again. Do not inspect the pointer-like contents of `jweak` to assert that the object is still alive.

## 10. Passing References Across Threads and Callbacks

A common mistake is sending `jobject local` from Java thread A to native worker thread B. In JNI, **a local reference is only valid on the thread that created it**. This remains true even if you believe the JVM does not move objects or that the object is still alive in Java.

If a native job must use an object on another thread:

1. **Before the method returns**, create `NewGlobalRef(env, object)` on a thread with a valid `JNIEnv *`, while the local ref is still alive.
2. Hand off the global reference according to a thread-safe rule (queue/mutex/ownership), synchronizing deletion to avoid use-after-delete.
3. The native thread accesses JNI using **that thread's own `JNIEnv *`**; for self-created threads, attach to the JVM via `JavaVM` if needed and detach according to contract.
4. When processing finishes, delete the global reference with `DeleteGlobalRef` in a valid JNI context; do not hold it until process exit if unnecessary.

`JNIEnv *` is also not an object address. It is an interface pointer for JNI calls within a thread; **do not share this pointer itself between threads**. `JavaVM *` has VM scope and is used for attach/detach, but you still must obey the API and JVM lifetime.

If you only need independent data (for example, a numeric ID, a copied byte buffer, or immutable information), you can **copy the data** to native storage with clear ownership and not retain a Java reference. This decision depends on the goal: to keep a Java object for callbacks, use a global ref; to keep a separate data snapshot, a copy may be more appropriate.

## 11. Why Does "Printing the Address" Prove Nothing About Stability?

You may encounter test code like:

~~~c
/* Do not use this output as an object address or as identity. */
printf("%p\n", (void *) someJObject);
~~~

The output (if the code compiles and `someJObject` has a pointer-compatible representation) only describes the **numeric representation of the handle** in a specific runtime. It does not prove the object is located at that address, does not prove that number is stable over time, and does not prove two handles point to the same object.

There are three separate questions:

- **Same object?** Use `IsSameObject` when both JNI references are valid.
- **Is the reference still valid?** Base this on local/global/weak type, thread, frame, lifetime, and ownership; do not check by dereferencing or comparing pointer numbers.
- **Where is the actual memory located?** JNI does not promise to provide the address of a general Java object; only certain APIs lend pointers to specific data under their own contracts.

`GetObjectRefType` (when called with a valid reference) can return the local/global/weak type of a JNI reference, but it **is not a rescue tool for a dangling handle**: passing a deleted or invalid reference does not make the behavior safe. Do not use `GetObjectRefType` to prove to yourself that an object is still at the same address.

## 12. Common JNI Mistakes and How to Fix Them

| Mistake | What can happen? | Correct approach |
| --- | --- | --- |
| Casting `jobject` to a C struct pointer and reading fields at offsets | Misreading a handle table/invalid memory; crash or data corruption | Use `GetFieldID` + `GetObjectField`/`GetIntField` or appropriate JNI APIs |
| Saving a local `jobject` in a static C variable for a later call | Dangling local reference after the native method returns | Create `NewGlobalRef` before saving; `DeleteGlobalRef` at the right time |
| Passing a local reference from thread A to thread B | Violates thread restriction, may cause JNI errors | Use a global ref, clear ownership, thread B obtains its own `JNIEnv *` |
| Comparing two `jobject`s with the C `==` operator to check identity | May compare different handle values for the same object | `IsSameObject` |
| Thinking a global ref pins the object at its current heap location | Depends on layout/GC, not portable | Treat a global ref as a root with a lifetime; do not infer addresses |
| Checking a weak ref and using it after some time | GC may reclaim the target between check/use | `NewLocalRef(weak)` or `NewGlobalRef(weak)` and hold the strong ref |
| Forgetting `DeleteGlobalRef` | Global root keeps the object/object graph alive longer than intended | Explicitly pair every acquire with a release |
| Using a pointer from `GetArrayElements` after release | Use-after-release; a copied buffer may have been freed | Only use within the acquire/release window |
| Defining `jstring` as `char *` | Confusing an object reference with text data, wrong encoding | Use `GetStringChars` / `GetStringUTFChars` and release |
| Treating `System.identityHashCode` as an object address | Confusing identity hash with physical address | Treat it as a hash; do not encode pointers or unique IDs |

### Scenario 1: A native library caches `jclass`

`FindClass` normally returns a **local reference** of type `jclass`. If a library wants to keep a reference to the class across multiple calls, it needs `NewGlobalRef` for `jclass`, not caching the raw local handle. `jclass` is still a JNI reference to the class object, not an immutable address of Java metadata. When the cache is no longer needed, delete the global ref according to the designed ownership.

### Scenario 2: Native code works for a long time in a loop

If a native method iterates over hundreds of thousands of elements, repeatedly calling `GetObjectArrayElement` without `DeleteLocalRef` can fill the local-reference table, keep many objects alive, and cause errors. Delete each local ref right after use, or manage local frames appropriately.

### Scenario 3: A C library requires `void *userData` in a callback

Do not arbitrarily write `(void *)jobject` into `userData` and treat it as an object address. If the callback is on the same thread and synchronous within the local ref's lifetime, you may use the handle per the JNI contract at a valid time (with clear management). If the callback is asynchronous, create a global ref, define who owns/cancels the callback, synchronize before deleting, and ensure the callback thread is attached to the JVM. Another option is to allocate your own native context containing the **global reference** along with auxiliary data and free it after all callbacks finish.

### Scenario 4: "I called `System.gc()` and the printed reference stayed the same"

`System.gc()` is only a suggestion for the JVM to perform GC; it is not required to move objects or run in a specific way. The numeric value of a JNI handle is not an object address. Therefore, an experiment where "the printed pointer did not change" does not prove that code using that pointer is valid.

## 13. Checklist for a Safe JNI Reference Boundary

- [ ] Every `jobject`/`jstring`/`jclass`/`jarray` is used via JNI APIs, not dereferenced as an object address.
- [ ] Local refs are only used on the right thread and in the right JNI scope; local arguments are not retained after the method returns.
- [ ] If an object needs to live across multiple calls or threads, a global ref is created and the exact time for `DeleteGlobalRef` is determined.
- [ ] If caching weakly, `jweak` is used; always promote to a strong local/global ref successfully before operating and handle the possibility that the object was GC'd.
- [ ] Identity is compared with `IsSameObject`; identity is not inferred from pointer bits, `equals`, or `identityHashCode`.
- [ ] `Get...Elements`/`Release...Elements`, `GetString...`/`ReleaseString...`, and critical region pairs have their lifetimes handled properly.
- [ ] Callbacks/native worker threads use that thread's own `JNIEnv *` and have a synchronization/cleanup policy.
- [ ] Native code checks for JNI exceptions when an API can fail; does not treat a reference that just returned `NULL` as success.
- [ ] Does not rely on whether the JVM uses a moving collector or not, or on a specific heap layout.
- [ ] Tests cover lifetimes, local refs in loops, global leaks, cleared weak refs, callback order, and concurrency; do not require GC to happen on an exact schedule.

## 14. Self-Check Questions

**Question 1.** If two `jobject` variables have different bit patterns, is it certain they refer to two different Java objects?

No. The JVM can represent two different JNI handles for the same object. Use `IsSameObject` with two currently valid references.

**Question 2.** Does creating `NewGlobalRef` keep the physical address of the Java object unchanged?

No. A global ref preserves **strong reachability and the lifetime of the JNI handle** until `DeleteGlobalRef`; the JVM is still allowed to move the object.

**Question 3.** Java still holds the object after the native method returns. Can native code reuse a local `jobject` saved in a static variable?

No. A local reference expires with its scope regardless of whether the object is still reachable on the Java side. Create a `NewGlobalRef` before saving across multiple calls.

**Question 4.** Can `jweak` be used immediately after `IsSameObject(weak, NULL)` returns false?

It should not be. GC can process the weak target after the check and before use. Create `NewLocalRef(weak)` to get a strong local handle, check for NULL/exception, use the strong handle, and then delete it.

**Question 5.** `GetByteArrayElements` returns a pointer different from the printed address of `jbyteArray`. Is that a JVM bug?

No. `jbyteArray` is a JNI object reference; `GetByteArrayElements` returns a pointer to **the array's byte data**, which may be a copy, with a lifetime managed by release. These are two different kinds of values.

**Question 6.** When a callback runs on another native thread, what is needed to call a Java instance method on a saved object?

Hold the object with a global reference (and synchronize with deletion), use a `JNIEnv *` obtained for the callback thread via JVM attachment/VM API, call the appropriate JNI method, handle exceptions, and release the reference when ownership ends.

**Question 7.** To know if two objects are equal by content, is `IsSameObject` enough?

No. `IsSameObject` checks identity. If Java `equals` logic is needed, you must call the Java `equals` method via JNI or compare data according to an explicit content rule.

## Official Documentation

1. [JNI Specification — Design Overview: Referencing Java Objects](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): why the JVM manages references, local/global references, GC, and moving objects.
2. [JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewLocalRef`, `NewGlobalRef`, `DeleteGlobalRef`, `IsSameObject`, weak global, `GetObjectRefType`, array/string access, critical regions.
3. [JNI Specification — Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): object reference types and primitive types.
4. [Oracle javac — Generate Native Header](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): using `javac -h` to generate JNI headers.
5. [Android NDK — JNI Tips](https://developer.android.com/ndk/guides/jni-tips): reference ownership practices, global/local refs, and thread behavior (the referencing principles are also useful when working with standard Java JNI).

**Conclusion:** `jobject` is a **lifecycle-managed logical reference**. JNI keeps the link between the reference and the object accurate even when GC changes memory layout, but JNI does not promise a fixed physical address. Design based on **local/global/weak reference lifetimes**, access via JNI functions, comparison with `IsSameObject`, and explicit ownership management.