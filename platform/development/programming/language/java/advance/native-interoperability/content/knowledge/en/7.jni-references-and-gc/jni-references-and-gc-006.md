# Weak Global References in JNI and How to Safely Promote Them to Strong References Before Use

## 1. Background: Why Does JNI Need Weak Global References?

When Java calls C/C++ code via the **Java Native Interface (JNI)**, the native side receives references such as `jobject`, `jstring`, or `jclass`. JNI manages **reference lifetimes** differently from Java object lifetimes: saving a `jobject` value received from a native method parameter into a C variable for use after the method returns is wrong if it is only a **local reference**.

Some native libraries want to **remember Java objects for later use**: caching callbacks, objects attached to a native handle, metadata, or classes. However, if a strong global reference is always used, the native library can keep the object and all related objects alive for too long, hindering garbage collection (GC).

JNI provides **weak global references**, of type `jweak`, through:

- `NewWeakGlobalRef(env, obj)`: creates a weak handle that can be stored across multiple JNI calls and used on appropriate threads.
- `DeleteWeakGlobalRef(env, weak)`: releases the weak handle when it is no longer needed.
- `NewLocalRef(env, weak)`: attempts to **promote** a weak global to a **strong local reference** before accessing the object.
- `NewGlobalRef(env, weak)`: attempts to promote to a **strong global reference**, when the object needs to be kept for a longer period.

A weak global **does not keep the Java object alive** simply because the C handle still exists. When GC collects the object, the `jweak` handle may still have a non-`NULL` value, but **the pointed-to object is gone**, and that handle behaves equivalently to a `null` reference in appropriate JNI operations.

**The most important rule: do not use an object just because you checked that "weak is not null". Create a strong reference first, check the result, and then use only that strong reference.**

## 2. Distinguishing the Three Types of JNI References

| JNI Type | How It Is Created | Keeps Object from Being GC'd? | Scope of Use and How to Release |
| --- | --- | --- | --- |
| **Local reference** (`jobject`/`jclass`/`jstring`…) | Object parameters to a native method; results from most JNI APIs; `NewLocalRef` | **Yes**, while still a valid local reference | Valid within the corresponding thread and local JNI frame; cleaned up when the native method returns to Java; `DeleteLocalRef` can be called early |
| **Strong global reference** | `NewGlobalRef` | **Yes**, until the global reference is deleted | Can be kept across multiple native calls and used on threads attached to the JVM; must call `DeleteGlobalRef` |
| **Weak global reference** (`jweak`) | `NewWeakGlobalRef` | **No** | Handle lives across calls/threads until `DeleteWeakGlobalRef`, but the referent can be collected by GC at any time |

**A weak reference is not a C pointer to a fixed object address.** Java objects can move during GC, and the JVM manages decoding JNI handles. Do not cast `jweak` to an address and dereference it in C/C++.

Illustrative example:

```text
C/C++ holds jweak W ---------+-------> Java object X
                             |
Java still holds strong S ---+
                             |
GC: does not collect X while S is alive.

Java no longer has strong S; X has no other strong roots:
GC may collect X.
W (handle) may still exist, but the referent has been cleared.
```

From this, two independent concepts emerge:

1. **Whether the handle still exists or has been deleted:** `W != NULL` only says the C variable may be storing a handle; `DeleteWeakGlobalRef` handles the handle's lifetime.
2. **Whether the Java referent is still alive or has been collected:** stable usage rights can only be obtained by **successfully promoting to a strong reference**. The referent may be gone even when variable `W` is not `NULL`.

## 3. Why Is Checking IsSameObject First and Then Using It Wrong?

JNI allows trying:

```c
jboolean gone = (*env)->IsSameObject(env, weak, NULL);
```

If `gone == JNI_TRUE`, the weak reference was already equivalent to `null` **at the time of the check**. However, a `JNI_FALSE` result only reflects **a single point in time**; afterward, GC may collect the object before the next JNI call.

**Unsafe** pattern (assuming `weak` is a still-valid `jweak` handle):

```c
/* WRONG: there is a race with GC between the two calls */
if (!(*env)->IsSameObject(env, weak, NULL)) {
    jclass cls = (*env)->GetObjectClass(env, weak);
    /* The reference may have already been cleared before GetObjectClass. */
}
```

Timeline:

```text
Native thread                   Garbage collector
-------------                   -----------------
IsSameObject(weak, NULL)
  → JNI_FALSE (still alive)
                                Java loses last strong root
                                GC clears weak global
GetObjectClass(weak)
  → no strong referent left
```

**This is a check-then-use (TOCTOU) bug:** "checking if alive" **does not keep the object alive** during the subsequent period.

In addition, `weak != NULL` is an even weaker condition: the handle may have already lost its referent while the handle value has not yet been cleared. Do not use C pointer comparisons to conclude that a Java object is alive.

**The right way** is to perform the reference promotion operation using JNI itself:

```c
jobject strong = (*env)->NewLocalRef(env, weak);
if (strong == NULL) {
    /* Referent is gone (or failed to obtain local ref, e.g. out of memory).
       Do not use weak to access the object. */
    return;
}

/* Now strong is a strong local reference. */
jclass cls = (*env)->GetObjectClass(env, strong);
/* Check cls/exception and operate on strong as needed. */

/* After finishing use: */
if (cls != NULL) {
    (*env)->DeleteLocalRef(env, cls);
}
(*env)->DeleteLocalRef(env, strong);
```

`NewLocalRef` returns `NULL` if the source reference is `null`, the weak's referent has been GC'd, or creating the local reference fails due to insufficient resources. Depending on the error and JVM, pay attention to pending exceptions; **do not always interpret every `NULL` as "GC has occurred"**.

If `strong != NULL`, that local reference itself keeps the object alive while it remains valid. GC cannot collect the referent while a valid strong reference holds it, even if the original `weak` variable is later cleared or deleted (provided no other thread **deletes the weak handle while the promotion operation itself is using that handle**; that is a separate synchronization problem, see section 8).

## 4. Two Promotion Types: NewLocalRef and NewGlobalRef

### 4.1. Promoting to a Local Reference for Use Within a Single Native Call

Most common when you want to use the object **right now**:

```c
jobject strongLocal = (*env)->NewLocalRef(env, weak);
if (strongLocal == NULL) {
    /* No usable object: return or handle error. */
    return;
}

/* Pass only strongLocal, NOT weak, to subsequent JNI calls. */
(*env)->DeleteLocalRef(env, strongLocal);
```

- `strongLocal` is valid in the current JNI thread and local reference frame.
- If a loop creates many local refs, release them immediately with `DeleteLocalRef` after use so as not to increase pressure on the local reference table.
- When a native method **returns `jobject`** as a local reference, you can return the strong local directly to Java; the JVM converts the result into an appropriate Java reference and cleans up the local frame upon return. **Do not delete the local reference before returning it.**
- For native threads that **self-attach** via `AttachCurrentThread`, local references are not automatically cleaned up per Java call like a normal native call; you must manage `DeleteLocalRef`/local frames properly and detach when finished.

### 4.2. Promoting to a Strong Global Reference for Use Across Multiple Calls/Threads

If you need to keep a Java object alive **beyond the lifetime of a local JNI frame**, for example to store in a native work queue, you can use:

```c
jobject strongGlobal = (*env)->NewGlobalRef(env, weak);
if (strongGlobal == NULL) {
    /* Referent was GC'd, or reference creation failed. */
    return;
}

/* Native code holds strongGlobal for as long as needed.
   When the work is done, use the attached thread's JNIEnv to delete: */
(*env)->DeleteGlobalRef(env, strongGlobal);
```

Note **not to call DeleteGlobalRef immediately** if asynchronous work still needs the object. Conversely, keeping a strong global indefinitely turns a weak cache into a long-lived object retention mechanism, preventing GC from freeing the referent.

### Comparing the Two Options

| Scenario | Appropriate Promotion | End of Lifetime |
| --- | --- | --- |
| Need to read a field/call a method immediately in the native function | `NewLocalRef(weak)` | `DeleteLocalRef` when done, or let the JNI frame clean up |
| Need to return the object to the Java caller | `NewLocalRef(weak)` then `return strongLocal` | Java manages the returned reference; do not delete before `return` |
| Native worker needs to keep the object until a job finishes | `NewGlobalRef(weak)` | `DeleteGlobalRef` when the job finishes |
| Want to cache while allowing GC to reclaim the object | `NewWeakGlobalRef` | `DeleteWeakGlobalRef` when removing the cache entry |
| Only check `IsSameObject(weak,NULL)` then call on weak | **Inappropriate** | Use a promotion operation directly |

## 5. Complete Java 17+ / JNI C Example: Storing jweak, Safe Promotion, and Releasing

This example creates a **single-slot** cache storing a single weak global reference. The API includes:

- `store(Object)`: creates a weak global reference and replaces the old handle.
- `get()`: uses `NewLocalRef` to **promote to a strong local** and returns the object to Java, or returns `null` when promotion is not possible.
- `dispose()`: deletes the weak handle and sets the C variable to `NULL`.

The three Java methods are declared `static synchronized native` so that calls to this native slot **do not overlap** when going through that Java class. This pattern assumes no other native worker accesses the C variable `saved` directly outside the three methods; when extending to native threads, synchronization on the native side must be used (section 8).

### 5.1. File src/demo/jni/WeakGlobalCache.java

```java
package demo.jni;

public final class WeakGlobalCache {
    static {
        System.loadLibrary("weakglobalcache");
    }

    public static synchronized native void store(Object value);
    public static synchronized native Object get();
    public static synchronized native void dispose();

    public static void main(String[] args) {
        Object keepAlive = new Object();

        store(keepAlive);
        Object strong = get();

        System.out.println("Same object: " + (strong == keepAlive));

        dispose();
        System.out.println("Empty slot: " + (get() == null));
    }
}
```

Checkpoint for a deterministic result: the Java variable `keepAlive` is still a strong reference at the time of comparing `strong == keepAlive`. Therefore, the example **does not rely on whether GC runs or not** to produce stdout. `dispose()` deletes the cache handle; it **does not** trigger GC and does not destroy the Java strong references `keepAlive`/`strong`.

### 5.2. Compiling Java and Generating the JNI Header

On Linux or macOS, from the project root directory:

```bash
mkdir -p build/classes build/include build/native

javac -h build/include \
  -d build/classes \
  src/demo/jni/WeakGlobalCache.java
```

This produces `build/classes/demo/jni/WeakGlobalCache.class` and `build/include/demo_jni_WeakGlobalCache.h`.

Important header (omitting the comments and include guards generated by `javac`):

```c
#include <jni.h>

JNIEXPORT void JNICALL Java_demo_jni_WeakGlobalCache_store
  (JNIEnv *, jclass, jobject);

JNIEXPORT jobject JNICALL Java_demo_jni_WeakGlobalCache_get
  (JNIEnv *, jclass);

JNIEXPORT void JNICALL Java_demo_jni_WeakGlobalCache_dispose
  (JNIEnv *, jclass);
```

The prototypes above have been verified with `javac -h` on JDK 24. The `synchronized` keyword belongs to Java's locking mechanism, does not change the JNI symbol name, and does not add JNI parameters. The second parameter is `jclass` because all three native methods are `static`.

### 5.3. File WeakGlobalCache.c

```c
#include <jni.h>
#include "demo_jni_WeakGlobalCache.h"

/* Weak handle persisting across multiple JNI calls.
   All accesses in this example go through synchronized static native methods. */
static jweak saved = NULL;

JNIEXPORT void JNICALL Java_demo_jni_WeakGlobalCache_store(
        JNIEnv *env, jclass cls, jobject value) {
    (void) cls;

    jweak fresh = NULL;

    if (value != NULL) {
        fresh = (*env)->NewWeakGlobalRef(env, value);
        if (fresh == NULL) {
            /* With a non-null Java argument still strong in the native call,
               failure is usually due to out of memory; do not delete the old handle.
               The JVM has already thrown an exception if NewWeakGlobalRef ran out of memory. */
            return;
        }
    }

    /* Only replace the slot after successfully creating the new weak handle. */
    if (saved != NULL) {
        (*env)->DeleteWeakGlobalRef(env, saved);
    }
    saved = fresh;
}

JNIEXPORT jobject JNICALL Java_demo_jni_WeakGlobalCache_get(
        JNIEnv *env, jclass cls) {
    (void) cls;

    if (saved == NULL) {
        return NULL;
    }

    /* Key operation: obtain a strong local, do not use jweak directly. */
    return (*env)->NewLocalRef(env, saved);
}

JNIEXPORT void JNICALL Java_demo_jni_WeakGlobalCache_dispose(
        JNIEnv *env, jclass cls) {
    (void) cls;

    if (saved != NULL) {
        (*env)->DeleteWeakGlobalRef(env, saved);
        saved = NULL;
    }
}
```

Lifetime explanation:

1. The `value` parameter passed from Java is a valid local reference during the native call, keeping the referent alive while `NewWeakGlobalRef` creates the handle.
2. `saved` is a `jweak` whose lifetime exceeds the `store` call. However, `saved` **does not keep the referent alive** after other strong roots are lost.
3. `get` returns `NewLocalRef(env, saved)`; when successful, the result is a strong local and can be held in Java by the `strong` variable.
4. If the referent has been GC'd, promotion may return `NULL` and Java receives `null`. If resources are insufficient or there is a pending exception, the error must be handled accordingly; the simple example does not attempt to classify every cause of `NULL`.
5. `dispose` calls **the right function `DeleteWeakGlobalRef`** and then assigns `saved = NULL` so the freed handle is not reused.
6. `store(null)` also deletes the old slot and stores `NULL`, because there is no need to create a weak handle for `null`.

Why does `store` create `fresh` **before deleting `saved`**? If `NewWeakGlobalRef` fails, the old cache still retains a valid weak handle; state is not lost due to an allocation error. Even if the old referent has already been GC'd, the old handle still needs to be deleted when replacing the cache.

### 5.4. Compiling the Shared Library on Linux

Requires JDK 17+ and GCC. The `JAVA_HOME` variable must point to the JDK directory containing `include/jni.h`:

```bash
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -o build/native/libweakglobalcache.so \
  WeakGlobalCache.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.WeakGlobalCache
```

**Exact stdout when compilation and library loading succeed:**

```text
Same object: true
Empty slot: true
```

If a newer JDK enables native access warnings, there may be **warnings on stderr**, but the two stdout lines above do not change. Depending on the JDK version, a program on the classpath may need the `--enable-native-access=ALL-UNNAMED` argument when running. Do not blindly add that argument to every JDK version.

### 5.5. macOS and Windows

**macOS** (after running the same `javac -h` command; with Clang and a valid `JAVA_HOME`):

```bash
clang -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  -o build/native/libweakglobalcache.dylib \
  WeakGlobalCache.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.WeakGlobalCache
```

**Windows**, in Visual Studio Developer Command Prompt (with `cl`, JDK, `JAVA_HOME`):

```bat
mkdir build\classes
mkdir build\include
mkdir build\native

javac -h build\include -d build\classes src\demo\jni\WeakGlobalCache.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" WeakGlobalCache.c /Febuild\native\weakglobalcache.dll

java -Djava.library.path=build\native -cp build\classes demo.jni.WeakGlobalCache
```

Platforms use the corresponding shared library `.so`, `.dylib`, or `.dll`. `System.loadLibrary("weakglobalcache")` only needs the logical name; the JVM maps it according to the operating system. **The JDK and native compiler must match in architecture** (x64, ARM64, etc.). File permissions and OS dynamic library configuration must be adjusted if the deployment environment differs.

## 6. When Can GC Occur? Why Not Test Using System.gc()?

The example behaves the same whether GC does not run, runs once, or runs multiple times. This is an intentional design point.

When no Java or JNI strong references hold the object (and there are no other sources keeping it alive), GC **may** collect the referent of `jweak`. However:

- `System.gc()` is only a **request/hint** to the runtime; the timing of processing and whether a GC run collects the target object are **not guaranteed**.
- The JVM may still have other strong roots: live Java variables, static fields, JNI local/global refs, or an object held by another structure.
- After a successful `NewLocalRef`, the strong local itself guarantees the referent stays alive during the usage period; collection timing must not be inferred solely from the number of GC calls.
- If all strong references are lost, `get()` **may** return the object or `null`, depending on whether GC has collected it yet; there is no guarantee that "immediately after `System.gc()` it must be `null`".

Additional experiment (just an **illustrative snippet**, placed in Java code with access to the native methods of `WeakGlobalCache`):

```java
store(new Object());  // Do not hold the object in a Java variable.
System.gc();          // Does not force GC to collect the object immediately.

Object snapshot = get(); // Attempt to promote atomically via NewLocalRef in JNI.
System.out.println(snapshot == null
        ? "No referent left to promote"
        : "Promoted to strong reference");

dispose();            // Release the weak handle.
```

The two string branches in `println` are **two different possibilities**, with no fixed output. If `snapshot != null`, Java holds a strong reference, preventing the object from being collected while this variable is actually still in use.

`jweak` is processed according to JNI's reachability/GC rules. **Do not completely equate** `jweak` with `java.lang.ref.WeakReference` or assume identical clearing order across all JVM versions. What matters for correct JNI code is: GC has the right to clear the referent of `jweak`, and promoting via `NewLocalRef`/`NewGlobalRef` is the protective boundary before access.

## 7. Handle Lifetime and Memory Management

### Creating, Replacing, and Deleting Weak References Properly

- Call `NewWeakGlobalRef` to create a **new** weak handle. Every successful creation must have a release path via `DeleteWeakGlobalRef`.
- A `jweak` may have had its **referent cleared** while still having a handle stored on the native side. **That handle must still be deleted** when no longer used.
- Do not pass a weak handle to `DeleteGlobalRef`; each handle type must be released with its **corresponding API**.
- After `DeleteWeakGlobalRef`, the old handle value must not continue to be used. Set the variable/slot to `NULL`, or remove it from the cache data structure.
- Do not call `DeleteWeakGlobalRef` while another thread might be using that same handle to call `NewLocalRef`; all operations on the slot must be synchronized.
- When replacing a handle, create the new handle first and only delete the old handle after succeeding, unless the design intentionally clears the cache even on allocation failure.

### Lifetime of the Strong Reference After Promotion

```text
jweak W still exists ------------------------------> DeleteWeakGlobalRef(W)
       |
       | NewLocalRef(W) succeeds
       v
jobject strong S =================> DeleteLocalRef(S)
     referent is guaranteed alive
     while S is valid
```

The `====` section indicates the period with a **strong reference**. Deleting `W` while `S` is still valid **does not** weaken `S`. Conversely, deleting `S` does not automatically delete `W`; the two handles manage independent lifetimes.

When a native method returns `S` as a `jobject` to Java, the local reference ends with the JNI frame, but **the returned object value remains a strong reference on the Java side** if received and used. Do not confuse local frame cleanup with "the Java object being destroyed".

### When Reference Allocation Fails

Reference-creation functions such as `NewWeakGlobalRef`/`NewGlobalRef`/`NewLocalRef` may return `NULL` when resources are insufficient. `NewWeakGlobalRef` may throw `OutOfMemoryError`. In native code, if there is a pending exception, avoid continuing to call arbitrary JNI APIs; return so Java can handle it or handle the exception using permitted APIs. Do not use `NULL` as sole proof that the referent was GC'd.

## 8. Multithreaded Safety: GC Race vs. Handle Deletion Race

There are **two independent types of races** to handle.

### Race A — GC Clears the Referent

The object may be collected between `IsSameObject` and the next JNI call. This is a **race with GC**, solved by **`NewLocalRef(weak)` or `NewGlobalRef(weak)`**, i.e., acquiring a strong reference before use.

### Race B — Another Thread Deletes or Replaces the Handle

Suppose thread A reads `jweak W` from the cache while thread B calls `DeleteWeakGlobalRef(W)`. If A subsequently passes the **already-deleted** handle into `NewLocalRef`, the JNI handle is no longer valid. Promoting to strong cannot fix a handle that was freed before the promotion.

Required model:

```text
Thread A (get)              Thread B (dispose/store)
-----------------           -----------------------
lock(slot)
  get valid W               wait for lock(slot)
  S = NewLocalRef(W)
unlock(slot)
                            lock(slot)
                              DeleteWeakGlobalRef(W)
                            unlock(slot)
use S (strong)
DeleteLocalRef(S)
```

Synchronization only needs to protect **the right to use handle W** while obtaining the strong reference; once `S` has been obtained, A can use `S` independently of B deleting `W`. Depending on the design, the lock can be a native mutex, a Java monitor respected on every access path, or an equivalent synchronization mechanism.

In the sample program, all accesses to `saved` are inside **three `static synchronized native` methods of the same class**. Java acquires the `Class` object's monitor upon entering each method, so calls going through that class are serialized. **If another native worker reads/deletes `saved` directly, the Java monitor does not automatically protect that worker**; switch to a mutex or explicit synchronization and do not hold the mutex across callback calls that risk deadlock.

A few other notes:

- `jweak` and strong globals can be stored across threads, **but `JNIEnv*` is only valid for the thread that owns it**. Do not store `JNIEnv*` to reuse from another thread.
- A native thread must call `AttachCurrentThread` to obtain its own `JNIEnv*`, then manage resources and call `DetachCurrentThread` when appropriate.
- A local reference created from `NewLocalRef` must be used/released in the exact same thread and frame; do not pass a local `jobject` to another thread for use after the frame ends.
- When needing to pass an object to another worker, create a strong global in the current thread while the local strong is still valid; the worker has its own `JNIEnv*` and releases the strong global after finishing its work.

## 9. Weak Global References in Callbacks, Class Caching, and Class Unloading

**Java callbacks:** a native library wants to store a listener object without preventing the listener from being collected. Store a `jweak` of the listener; whenever firing an event, use `NewLocalRef` to obtain a strong listener. If `NULL` is returned, skip the callback or clean up the cache slot; if successful, invoke the method via the strong reference, check for JNI exceptions, and release the local strong after the callback.

**Class caching:** `jclass` is also a JNI reference to a `java.lang.Class` object. If you want to cache weakly so as not to accidentally keep the class/class loader alive forever, store a `jweak` of the class and **promote it to a valid local `jclass`** before using `GetMethodID`, `GetStaticMethodID`, or related APIs. Do not keep a local `jclass` from a previous JNI call for use in a later callback.

**Class unloading:** when a class/class loader can be unloaded, other caches tied to the class such as `jmethodID` and `jfieldID` must be managed according to the class lifetime. A cleared weak global class does not guarantee that cached IDs remain usable in all circumstances. When designing reloadable plugins/modules, there must be a strategy to refresh both the class handle and corresponding metadata.

**A native cache is not automatically like Java's WeakHashMap:** `jweak` is a primitive for building caches; it does not automatically remove entries from a `std::unordered_map`/C map or callback table. Have a policy to check and remove entries whose referents have been cleared, avoiding letting the cache accumulate a large number of worthless weak handles.

## 10. Common Mistakes and How to Fix Them

| Mistake | Why It Is Dangerous | Correct Approach |
| --- | --- | --- |
| `if (weak != NULL) GetObjectClass(weak)` | Handle exists, referent may already be gone | `strong = NewLocalRef(weak)` then use only `strong` |
| `!IsSameObject(weak,NULL)` then `CallObjectMethod(weak,...)` | GC may run between check and use | Use a single strong promotion operation instead of checking first |
| Storing local `jobject` in a `static` variable across multiple native calls | Local reference expires when the old frame ends | Create `NewWeakGlobalRef` or `NewGlobalRef` as needed |
| Creating `NewGlobalRef` for "weak caching" | Strong global prevents the referent from being GC'd | Use `NewWeakGlobalRef` if you want to allow GC |
| Keeping a strong global forever after a job finishes | Keeps object alive too long, reference leak | `DeleteGlobalRef` according to the job's lifetime |
| Skipping `DeleteWeakGlobalRef` because GC cleared the weak | JNI handle still occupies resources | Delete the weak handle when the cache/owner ends |
| Calling `DeleteLocalRef(strong)` then continuing to use `strong` | Use-after-delete JNI reference | Do not use after deletion; return before frame cleanup |
| Native thread A deletes weak while B is promoting | Uses an already-freed handle | Synchronize read/promote/replace/delete handle operations |
| Sharing `JNIEnv*` across threads | `JNIEnv*` is thread-bound | Each thread must obtain its own `JNIEnv*` |
| Using `System.gc()` to assert weak was cleared | GC is not guaranteed to run at an exact time | Write deterministic tests for the API; do not assume GC timing |
| Concluding "was GC'd" for any `NULL` from `NewLocalRef` | Could also be caused by insufficient resources/exceptions | Check context and pending exceptions |

## 11. Code Review Checklist

When reading JNI code containing `jweak`, check in order:

1. **Source:** Was `jweak` created from a valid JNI reference with `NewWeakGlobalRef`? Are `NULL`/exceptions handled and the old cache preserved on allocation failure?
2. **Handle lifetime:** Who owns `jweak`? When is `DeleteWeakGlobalRef` called? Could it be double-deleted, leaked, or used after deletion?
3. **GC protection:** Does every attempt to use the referent call `NewLocalRef`/`NewGlobalRef` **before** use? Does any code rely solely on `IsSameObject` or `weak != NULL`?
4. **Strong lifetime:** If promotion succeeds, is the strong reference used and released at the right time? If returning a local ref to Java, does it avoid deleting before returning?
5. **Threading:** Who has permission to read/replace/delete the weak slot? Is creating the strong reference synchronized with deleting/replacing the weak handle? Do native threads have their own `JNIEnv*`?
6. **Errors:** What is the behavior when `NewLocalRef` returns `NULL`? Does it ignore important exceptions or use the referent without a strong reference?
7. **Tests:** Does it test correct results when the referent is definitely alive, handle deletion via the API, and that callbacks/workers do not cause use-after-delete?

A good review must check **both the GC race and the handle lifetime race**. Having `NewLocalRef` without synchronizing with `DeleteWeakGlobalRef` on another thread is still not safe enough.

## 12. Self-Check Exercises

**Question 1.** A native cache contains a non-`NULL` `jweak w`. Can we conclude the Java object exists?

**Answer:** No. `w != NULL` is only the state of the C-side handle. The referent may have already been cleared by GC. You need to promote using `NewLocalRef`/`NewGlobalRef` to obtain a strong reference if it is still alive.

**Question 2.** `IsSameObject(w,NULL)` returns `JNI_FALSE`. Is it safe enough to call `GetObjectClass(env,w)` immediately afterward?

**Answer:** No. GC may clear the referent between the two operations. Use `jobject local = NewLocalRef(env,w)` and only use `local` if it is non-`NULL`.

**Question 3.** `NewLocalRef(w)` succeeds, and then another operation deletes the weak handle `w`. Can the object be GC'd while `local` is still valid?

**Answer:** The object cannot be collected solely because `w` was deleted while `local` is still a valid strong reference. However, the **deletion of the weak handle itself must not run concurrently with using that handle to promote** if not synchronized.

**Question 4.** If a native worker needs to keep an object across multiple callbacks after the initial native method returns, should it store a local or global `jobject`?

**Answer:** Create a **strong global reference** while a valid strong reference still exists, hand the global handle to a synchronized work structure, and call `DeleteGlobalRef` when the job finishes. Do not store a local reference past its frame. If keeping the object alive is not required, the cache can hold a `jweak` and promote it on each use.

**Question 5.** GC has cleared the referent of `jweak`. Is `DeleteWeakGlobalRef` still needed?

**Answer:** Yes. GC clearing the referent does not automatically release the native-side handle; delete it with the proper API when the owner removes the slot/cache.

**Question 6.** Why does the sample program print `Same object: true` even when GC is active?

**Answer:** The Java variable `keepAlive` still keeps the object alive at the time of the check; `get()` promotes it to a strong local and returns it to Java. The `==` operation compares the same object, independent of GC scheduling.

## Official References

- [JNI Specification — Weak Global References, NewWeakGlobalRef, DeleteWeakGlobalRef](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#weak-global-references)
- [JNI Specification — NewLocalRef and NewGlobalRef](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#global-and-local-references)
- [JNI Specification — Local and Global References (Design Overview)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#global-and-local-references)
- [Oracle Java SE — java.lang.ref package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html)
- [Android NDK — JNI tips: local/global references, thread-specific JNIEnv](https://developer.android.com/ndk/guides/jni-tips)

**Key takeaway:** `jweak` only stores the ability to **try to retrieve** an object, not a guarantee that the object is alive. Only a successful `NewLocalRef`/`NewGlobalRef` creates a period of **strong reachability** for safe use; at the same time, the weak handle must be protected from being deleted/replaced by another thread while the promotion operation is taking place.
