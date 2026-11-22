# Comparing Objects Using `IsSameObject` Instead of Comparing JNI Reference Values

## 1. The problem: the same Java object can have multiple JNI references

When Java code calls a `native` method, the JVM passes the Java object to the C/C++ side as a **JNI reference** such as `jobject`, `jstring`, `jclass`, or `jarray`. These values are *JVM-managed handles/references*, not stable memory addresses of the Java object that programmers can compare directly using C pointer operators.

Suppose Java passes the same object into two parameter positions. JNI may provide different handles that both point to the same object. In addition, `NewLocalRef` or `NewGlobalRef` can also create a new reference to an existing object. Therefore, the operation:

```c
/* WRONG to assert that two JNI references point to the same Java object. */
if (first == second) {
    /* Not guaranteed to be an object identity check. */
}
```

only compares **the representation of two reference values on the C side**, which the JNI specification does not guarantee to be object identity. Some JVMs or runs may happen to give the right result, but the program will depend on implementation details. You must not turn an observed coincidence of addresses/handles into a JNI contract.

JNI provides the official function:

```c
jboolean IsSameObject(JNIEnv *env, jobject ref1, jobject ref2);
```

When using JNI in **C**, the call syntax is:

```c
jboolean same = (*env)->IsSameObject(env, first, second);
```

And in **C++**:

```cpp
jboolean same = env->IsSameObject(first, second);
```

`IsSameObject` checks whether two valid references point to **the same Java object**. The result is `JNI_TRUE` or `JNI_FALSE`. You do not need to, and should not, decode the representation of `jobject` yourself.

**Selection rule:** if you want to check for *the same object in the Java heap*, use `IsSameObject`; if you want to check for *equality in application semantics*, use `equals` or an appropriate value-comparison rule. These are two different questions.

## 2. Three comparisons that are easily confused

| Comparison | Question answered | Example |
| --- | --- | --- |
| Java `a == b` on references | Do two Java variables point to the same object? | Two separately created `String`s may contain the same content, yet `a == b` is `false` |
| Java `a.equals(b)` | How does object `a` define **value/semantic** equality? | Two `new String("jni")` instances have `equals` returning `true` |
| JNI `IsSameObject(env, a, b)` | Do two **JNI references** point to the same Java object? | A local ref and a global ref pointing to the same instance yield `JNI_TRUE` |
| C/C++ `a == b` on two JNI references | Do two handle representations compare equal in native code? | **Not an object identity check guaranteed by JNI** |

Java example:

```java
String a = new String("jni");
String b = new String("jni");

System.out.println(a == b);       // false: two different objects
System.out.println(a.equals(b));  // true: same content
```

`IsSameObject(env, refA, refB)` corresponds in **identity semantics** to Java `a == b`, *not* `a.equals(b)`. JNI does not automatically call `equals()`, nor does it compare the contents of Strings, arrays, records, or field values.

Several other approaches also **do not replace** `IsSameObject`:

- `System.identityHashCode(object)` returns an **`int` hash**, not a unique identifier: two different objects can have the same hash (collision).
- `GetObjectClass` gives the class of an object; two instances can have the same class without being the same object.
- `memcmp(&refA, &refB, sizeof(jobject))` only compares the bytes representing the handles in native memory; JNI does not define those bytes as object identity.
- Casting `jobject` to `void *` or an integer and putting it into a map/set as a stable object ID violates the contract and also risks reference expiration.

## 3. What exactly does `IsSameObject` return?

According to the JNI specification, `IsSameObject` returns `JNI_TRUE` if the two arguments refer to the same Java object **or both are `NULL`**; otherwise it returns `JNI_FALSE`.

| `ref1` | `ref2` | Result |
| --- | --- | --- |
| Local ref A to object X | Another local ref B also to X | `JNI_TRUE` |
| Local ref to X | Global ref to X | `JNI_TRUE` |
| Ref to X | Ref to Y distinct from X, even if `X.equals(Y)` is `true` | `JNI_FALSE` |
| `NULL` | `NULL` | `JNI_TRUE` |
| `NULL` | Valid ref to a live object | `JNI_FALSE` |

Minimal example to distinguish:

```c
jboolean sameObject =
        (*env)->IsSameObject(env, left, right);

if (sameObject == JNI_TRUE) {
    /* left and right both point to the same object,
       or both are NULL. */
}
```

**Two notes on input preconditions:**

1. `IsSameObject` should only receive JNI references that are **still valid** within their scope/lifetime, or `NULL`. It does not validate a reference that has already had `DeleteLocalRef`/`DeleteGlobalRef` called on it, a reference used out of scope from another thread, or a value cast from an arbitrary address.
2. `IsSameObject(ref, NULL)` can be used to check for NULL under JNI semantics; with a **weak global reference**, this rule also has a special effect when the object is reclaimed by GC (Section 6). For strong, valid local/global references, `ref == NULL` is the usual *null value* check; what must be avoided is `ref1 == ref2` between **two non-null references** to infer object identity.

## 4. Why can references differ even when pointing to the same object?

JNI deliberately separates the **Java object** from the **handle** held by native code:

```text
                  Java heap
             ┌──────────────────┐
             │ Object X         │
             │  ("JNI example") │
             └──────────────────┘
                  ↑      ↑
                  │      │
     JNI local ref A      JNI global ref B
     (current call)       (retained across calls)
                  │      │
               jobject jobject
```

The lines point to the same Object X, yet the JVM is free to represent the two references with different handle values. The garbage collector can move the actual object in the heap while JNI references remain usable because the JVM manages the necessary indirection layer.

Three important reference types:

- **Local reference**: typically received from `native` parameters or JNI functions such as `NewLocalRef`/`FindClass`. Its valid scope is tied to the thread and native frame; normal local refs are automatically freed when the native method returns. Use `DeleteLocalRef` early when creating many references in a loop.
- **Global reference**: created with `NewGlobalRef` and must be cleaned up with `DeleteGlobalRef`. It keeps the object strongly referenced until deleted, making it suitable when needed across multiple native calls. Do not retain a local ref and use it as a global ref.
- **Weak global reference**: created with `NewWeakGlobalRef`, deleted with `DeleteWeakGlobalRef`. It does not keep the object alive; after GC reclaims the referent, the weak ref becomes effectively `NULL`. Do not use an earlier comparison as a guarantee that the object will still be alive in a subsequent call.

`IsSameObject` performs the comparison based on **the object that the reference represents**, regardless of whether the handle was created as local or global, as long as the reference is still valid. It **does not extend** the lifetime of a local/global ref after the ref is deleted, and does not provide a persistent identifier key across multiple GC cycles or multiple processes.

## 5. Runnable Java 17+ and C JNI example

This example verifies four things: (1) two local refs to the same object are recognized correctly; (2) two `String`s with equal content are two different objects; (3) local and global references pointing to the same object; (4) `NULL` is handled properly.

Demonstration environment: JDK 17+, a C compiler such as GCC or Clang on **Linux**. On Windows/macOS, platform-appropriate build commands and shared library conventions must be used.

### 5.1. File `NativeIdentity.java`

```java
public final class NativeIdentity {
    static {
        System.loadLibrary("identityjni");
    }

    private NativeIdentity() {
    }

    private static native boolean same(Object left, Object right);

    private static native boolean globalRoundTrip(Object value);

    public static void main(String[] args) {
        String first = new String("jni");
        String second = new String("jni");

        System.out.println("same reference: "
                + same(first, first));
        System.out.println("equal text, distinct objects: "
                + same(first, second));
        System.out.println("Java equals: "
                + first.equals(second));
        System.out.println("local and global: "
                + globalRoundTrip(first));
        System.out.println("both null: "
                + same(null, null));
        System.out.println("one null: "
                + same(first, null));
    }
}
```

`new String("jni")` creates two distinct String objects; both objects have the same `"jni"` content. Both native methods are declared `static`, so the corresponding hidden parameter on the C side is `jclass`, not `jobject this`.

### 5.2. File `native_identity.c`

```c
#include <stddef.h>
#include "NativeIdentity.h"

JNIEXPORT jboolean JNICALL Java_NativeIdentity_same(
        JNIEnv *env, jclass cls, jobject left, jobject right) {
    (void)cls;
    return (*env)->IsSameObject(env, left, right);
}

JNIEXPORT jboolean JNICALL Java_NativeIdentity_globalRoundTrip(
        JNIEnv *env, jclass cls, jobject value) {
    (void)cls;

    /* Create a new global reference to the same Java object. */
    jobject global = (*env)->NewGlobalRef(env, value);

    /* If value is not NULL and ref allocation fails,
       the JVM may have a pending OutOfMemoryError.
       Return so the pending error is propagated to Java. */
    if (value != NULL && global == NULL) {
        return JNI_FALSE;
    }

    /* Compare object identity, not the two jobject values. */
    jboolean result = (*env)->IsSameObject(env, value, global);

    if (global != NULL) {
        (*env)->DeleteGlobalRef(env, global);
    }
    return result;
}
```

The `globalRoundTrip` snippet is important because `global` is **a new reference**. We only know it points to the same object thanks to `IsSameObject`; we must not assume `global == value`. After the check, `DeleteGlobalRef` must be called so references are not leaked.

The corresponding JNI function signatures are generated automatically from the Java class using `javac -h`. The entry point names in this code match because the class is in the **default package** and the two native method names are not overloaded. With other package/method names, do not guess symbols manually: use the header generated by `javac -h`.

### 5.3. Compiling and running on Linux

Run from the directory containing `NativeIdentity.java` and `native_identity.c`. The `JAVA_HOME` variable must point to a JDK containing the `jni.h` headers.

```bash
mkdir -p build

javac -h build -d build NativeIdentity.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild \
  native_identity.c -o libidentityjni.so

java -Djava.library.path=. -cp build NativeIdentity
```

These commands respectively generate `NativeIdentity.class`, the header `build/NativeIdentity.h`, the shared library `libidentityjni.so`, and invoke the Java program. The logical name `identityjni` maps to `libidentityjni.so` on Linux.

**Expected stdout:**

```text
same reference: true
equal text, distinct objects: false
Java equals: true
local and global: true
both null: true
one null: false
```

The result does not depend on whether two `jobject` values happen to be equal. If a newer JVM/JDK requires granting native access to code on the classpath, you can add `--enable-native-access=ALL-UNNAMED` to the `java` command according to that JDK version's instructions; this option does not change the meaning of `IsSameObject`.

### 5.4. What the example verified

- `same(first, first)` is `true` because it is the same Java instance.
- `same(first, second)` is `false` even though `first.equals(second)` is `true`; **identity is different from value equality**.
- `globalRoundTrip(first)` is `true` because `NewGlobalRef` creates a global ref to the exact object from the parameter.
- `same(null, null)` is `true` per JNI rules (similar to Java `null == null`).
- `same(first, null)` is `false` because one reference points to an object while the other reference is null.

## 6. Especially important: `jweak` and the gap between check and use

A **weak global reference** (`jweak`) allows the Java object to be reclaimed by GC. JNI specifies that a weak ref can be compared with `NULL`:

```c
jboolean cleared = (*env)->IsSameObject(env, weak, NULL);
```

When the referent has been reclaimed by GC, the weak reference becomes equivalent to `NULL`, so the result is `JNI_TRUE`. However, there is a common race bug:

```c
/* Unsafe if after this check the object only has the weak ref remaining. */
if ((*env)->IsSameObject(env, weak, NULL) == JNI_FALSE) {
    /* A GC may run after the check!
       You cannot conclude that weak is guaranteed alive
       for all subsequent JNI function calls. */
}
```

**Correct pattern for subsequent use:** create a **strong local reference** from the weak ref, then work through that strong ref within its valid scope.

```c
/* Fragment: weak is a valid jweak;
   candidate is a valid local/global reference or NULL. */
static jboolean matches_live_referent(
        JNIEnv *env, jweak weak, jobject candidate) {

    jobject strong = (*env)->NewLocalRef(env, weak);

    if (strong == NULL) {
        /* The referent may have been reclaimed.
           If reference allocation failed, you must also
           check for a pending JNI exception. */
        return JNI_FALSE;
    }

    jboolean same =
            (*env)->IsSameObject(env, strong, candidate);

    (*env)->DeleteLocalRef(env, strong);
    return same;
}
```

This is an **illustrative helper function**, not a standalone Java/C program. It returns `JNI_FALSE` when a **live referent** cannot be obtained. The case of a pending `OutOfMemoryError` must be handled/propagated by the caller; do not silently treat every `NULL` from `NewLocalRef` as "already GC'd". When creating the local ref succeeds, the strong ref prevents the object from being reclaimed while it is needed. Afterward, call `DeleteLocalRef` to free the reference.

**Subtlety:** `IsSameObject(weak, NULL)` is an **observation of state at the time of the call**, not a way to "pin" the referent. If you want to *compare and then continue using the object*, you must convert the weak reference to a strong reference first; do not separate the two operations with an unprotected time gap.

## 7. Comparing in caches, callbacks, and multiple threads

### 7.1. To keep an object across two JNI calls: use a global reference

A common mistake is storing a local `jobject` in a `static` variable or native container for use in a later call:

```c
/* WRONG: obj may be a local ref that expires after return. */
static jobject cached;

static void unsafe_save(jobject obj) {
    cached = obj;
}
```

The **lifetime**-correct way is to create a global reference and free it when no longer needed:

```c
/* Fragment: called while in a valid native frame.
   Separate synchronization is needed if multiple threads use a shared cache. */
jobject persistent = (*env)->NewGlobalRef(env, obj);

/* ... use persistent in subsequent JNI calls ... */

(*env)->DeleteGlobalRef(env, persistent);
```

You must handle `NULL` caused by a null input object or out-of-memory; do not use `persistent` if creating the global reference failed. Keeping a global ref for a long time keeps the object alive and can cause leaks, so every `NewGlobalRef` needs an appropriate cleanup path. With a global ref cache, use `IsSameObject` when you need to know whether a new parameter is the exact object stored.

**Do not use `jobject` as a stable hash key** based on handle bits. For a small number of references, you can search linearly using `IsSameObject`; if a high-performance map is needed, consider managing stable keys in the Java layer or assigning explicit IDs with a clear lifecycle (do not use identity hash as a unique ID).

### 7.2. A `JNIEnv *` is only for its owning thread

`JNIEnv *` is the JNI interface tied to the calling thread. Do not cache a `JNIEnv *` and pass it to another thread. Native code running on another thread must properly attach the thread to the JVM to obtain that thread's `JNIEnv *`, and detach when appropriate. Global references can be used across properly attached threads, but shared cache state requires synchronized access, and a global ref must not be deleted while another thread is using it without a safe lifecycle protocol.

### 7.3. Content equality requires calling Java logic

If the business requirement is "do two objects have the same value?", `IsSameObject` does not solve that problem. On the Java side, one typically uses:

```java
import java.util.Objects;

// Has equals semantics and handles two null arguments.
boolean equalValues = Objects.equals(left, right);

// Has identity semantics.
boolean sameInstance = left == right;
```

This is an **illustrative Java snippet**, assuming `left` and `right` are two existing variables. If content comparison really needs to happen from native code, you can call `equals(Object)` via `GetMethodID` + `CallBooleanMethod` and handle exceptions, or better yet, have Java compute `Objects.equals` and pass the result down to JNI. `IsSameObject` itself does not execute any Java method.

## 8. Common mistakes and how to diagnose them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `a == b` on two `jobject`s | Compares JNI handle representations, not Java object identity | `(*env)->IsSameObject(env, a, b)` |
| Assuming `IsSameObject` calls `equals()` | Compares identity, not object semantics | Use `equals` or `Objects.equals` if value comparison is needed |
| Comparing `System.identityHashCode(a) == System.identityHashCode(b)` | Hashes can collide | Check identity directly |
| Storing a local `jobject` across multiple native calls | Local ref expires when the native frame ends | Use `NewGlobalRef`/`DeleteGlobalRef` |
| Treating `IsSameObject(weak, NULL)` as proof that the weak ref stays alive | GC can reclaim it right after the check | `NewLocalRef` and then use the strong ref |
| Continuing to use a reference after `DeleteLocalRef` | Invalid reference, undefined behavior for subsequent JNI operations | Ensure proper lifetime, remove any use after delete |
| Not deleting a global ref when the cache expires | Keeps the object alive, causing a leak | Invalidate cache per lifecycle and call `DeleteGlobalRef` |
| Caching `JNIEnv *` for use from another thread | `JNIEnv *` is thread-bound | Attach the thread and obtain a valid `JNIEnv *` |
| Implicitly assuming two classes with identical content are one object | Class/instance identity still depends on the object and class loader | Identify the right instance; use `IsSameObject` for object identity |

### When results are not as expected

1. **Check whether it is truly the same Java instance?** Two `new` calls create two instances; `String` or boxed types can make "same content" feel like "same object". Do not rely on coincidences of String interning or wrapper caching.
2. **Check whether the JNI reference is still valid?** Was a local ref kept beyond its native frame, deleted early, or used on the wrong thread? Has `DeleteGlobalRef` already been called on the global ref?
3. **Check null/weak references.** Both null is `JNI_TRUE`; a GC'd weak ref may be treated as null. If about to use a weak ref, promote it to a strong local/global ref first.
4. **Check whether the question is actually about `equals`?** Two distinct objects can certainly be equal in value.
5. **When debugging native code**, you can use JNI Check mode (e.g., `-Xcheck:jni` on supported HotSpot) to help catch many reference/JNI API usage errors. This tool assists with diagnostics; it does not turn comparing `jobject` with `==` into a valid identity check.

## 9. Self-check

**Question 1.** `localA` and `globalB` both point to Java object X, but their handle values differ. What is the right operation to tell whether they point to the same X?  
**Answer:** `(*env)->IsSameObject(env, localA, globalB)`. If both references are valid and point to the same X, the result is `JNI_TRUE`.

**Question 2.** `new String("abc")` and `new String("abc")` have `equals` returning `true`. What does `IsSameObject` of two references to them return?  
**Answer:** `JNI_FALSE`, because they are two separate objects.

**Question 3.** What does calling `IsSameObject(env, NULL, NULL)` return?  
**Answer:** `JNI_TRUE`. JNI explicitly specifies the case where both are null.

**Question 4.** A `jweak` just returned `IsSameObject(env, weak, NULL) == JNI_FALSE`. Can we safely use it later?  
**Answer:** No. GC can run between the two operations. Create a strong local reference with `NewLocalRef`, check the result, and use that strong reference for as long as needed.

**Question 5.** Native code needs to keep a Java object longer than one call. Can we assign the `jobject` parameter to a C static variable and compare it on the next call?  
**Answer:** No, because the parameter is usually a local ref. You must create a global ref (or design a storage approach in Java), manage synchronization if multi-threaded, and clean up the reference when no longer used.

**Question 6.** Is `IsSameObject` sufficient to determine whether two `Person` objects have the same `id`?  
**Answer:** No. If application rules consider two `Person`s with the same `id` equal, write/apply `equals` or compare `id` appropriately. `IsSameObject` only answers whether they are one single instance.

## 10. Takeaways

- `jobject` is a JVM-managed **JNI reference**; the handle representation is not a stable Java object ID.
- Compare **object identity** with `IsSameObject`. In C: `(*env)->IsSameObject(env, a, b)`; in C++: `env->IsSameObject(a, b)`.
- The result is `JNI_TRUE` when two references point to the same object **or both are `NULL`**.
- **Identity ≠ value equality:** `IsSameObject` corresponds to Java reference `==`, not `equals`.
- Respect **the lifetime of local/global/weak references**: keep objects across calls with `NewGlobalRef`, clean up with `DeleteGlobalRef`; for `jweak`, use `NewLocalRef` before continuing operations.
- Do not rely on `jobject == jobject`, casting to an address/integer, `memcmp`, or `identityHashCode` to assert that two JNI references point to the same Java object.

### Official documentation

- [Oracle — JNI Functions: IsSameObject, NewGlobalRef, NewLocalRef, Weak Global References (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): function signatures, null rules, and reference lifecycles.
- [Oracle — JNI Design Overview: Referencing Java Objects (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): differences between local/global references and the JVM's object-handling model.
- [Oracle — JNI Functions (Java SE 22)](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/functions.html): rules for `IsSameObject` and weak global references in modern documentation versions.
