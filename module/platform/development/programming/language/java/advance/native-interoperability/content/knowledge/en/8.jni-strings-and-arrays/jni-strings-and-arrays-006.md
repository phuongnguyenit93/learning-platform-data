# Copy-Back Semantics, JNI_COMMIT, and JNI_ABORT When Releasing Arrays

When calling **GetIntArrayElements** or a corresponding **Get\<PrimitiveType\>ArrayElements** function, native code receives a pointer to access the elements of a Java primitive array. The JVM may provide a **copy** or **direct access** to the array data. This choice affects when Java sees the changes, the meaning of **JNI_ABORT**, and whether the buffer needs to be freed after **JNI_COMMIT**.

The three modes of **Release\<PrimitiveType\>ArrayElements** mean:

- **0:** if a copy is used, copy back the modified elements into the Java array and free the buffer; if not copied, end access to the direct data.
- **JNI_COMMIT:** if a copy is used, copy back the current values but **keep the copy buffer** so it can continue to be used; a final release with **0** or **JNI_ABORT** is needed afterward. When there is no copy, the mode does not change the release semantics.
- **JNI_ABORT:** if a copy is used, free the buffer **without copying back uncommitted changes**; if accessing directly, **changes already written to the Java array cannot be undone**.

**Key takeaway:** **JNI_ABORT is not a transaction rollback**, and **JNI_COMMIT is not how every array borrow ends**. This article goes from the memory model, the exact behavior table, and runnable JNI code to how to design array updates with the ability to reject results.

## 1. Borrowing Java Array Data from Native

A Java **int[]** array corresponds to the JNI **jintArray** type. When needing to manipulate multiple elements, native code typically does:

~~~c
/* Fragment inside a JNI function returning void.
 * Requires a valid array with at least one element. */
jboolean isCopy = JNI_FALSE;
jint *elements = (*env)->GetIntArrayElements(env, array, &isCopy);
if (elements == NULL) {
    return; /* Do not dereference; the JVM may have a pending exception. */
}

elements[0] = 42;
(*env)->ReleaseIntArrayElements(env, array, elements, 0);
~~~

**GetIntArrayElements** returns a valid pointer within the access window managed by the **Get/Release** pair. Do not call **free(elements)**, **delete[] elements**, keep the pointer for use after it has been released, or assume it is always the actual heap address of the Java array. The JVM has the right to choose the data-provisioning strategy per call, array type, and runtime state.

Two paths can occur:

~~~text
A. JVM allocates a copy buffer

Java int[] [1, 2, 3]  ── copy ──> native p [1, 2, 3]
                                         |
                                        p[0] = 42
                                         |
                            Release mode=0 / JNI_COMMIT
                                         |
Java int[] [42, 2, 3] <────── copy-back ┘

B. JVM gives direct access

Java int[] [1, 2, 3]  <───── p same data ─────────> native
            |
          p[0] = 42
            |
Java int[] [42, 2, 3]      (modified directly)
            |
     Release ends access
~~~

With branch A, modifying the pointer does not necessarily modify the Java array before copy-back. With branch B, modifying the pointer can modify the Java array immediately. Regardless of which branch is used, **Release** must be called in a matching pair.

## 2. isCopy: Detecting a Copy, Not Controlling the JVM

The JNI function has the form:

~~~c
jint *GetIntArrayElements(
    JNIEnv *env, jintArray array, jboolean *isCopy);
~~~

If **isCopy** is the address of a **jboolean** variable:

- **JNI_TRUE**: the JVM created a copy; to keep modifications, a copy-back is required.
- **JNI_FALSE**: the returned pointer is not a copy; modifications may occur directly on the Java array.
- **NULL** for the **isCopy** parameter: does not ask the JVM to return the information to you; **does not ask the JVM to provide a direct pointer**.

One **isCopy == JNI_TRUE** does not guarantee the next call will be the same. One **isCopy == JNI_FALSE** does not allow skipping **Release** or keeping the pointer indefinitely. JNI lifecycle rules still apply in both cases.

Example when only reading is needed:

~~~c
/* Fragment: valid array, env belongs to the current thread. */
jboolean copied = JNI_FALSE;
jint *p = (*env)->GetIntArrayElements(env, array, &copied);
if (p == NULL) {
    return;
}
/* Read from p; do not modify any element. */
(*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
~~~

**JNI_ABORT** is often appropriate when only reading because no copy-back is needed; this condition is completely different from trying to “cancel modifications that have already occurred”.

## 3. Exact Comparison of Mode 0, JNI_COMMIT, and JNI_ABORT

Signature:

~~~c
void ReleaseIntArrayElements(
    JNIEnv *env, jintArray array, jint *elems, jint mode);
~~~

| Mode | **isCopy == JNI_TRUE**: copy buffer | **isCopy == JNI_FALSE**: direct data |
| --- | --- | --- |
| **0** | Copy back the entire buffer and then free it | End access; changes written directly are kept |
| **JNI_COMMIT** | Copy back but do not free the copy; requires a final release | Mode has no separate effect when there is no copy; do not assume the pointer is still usable after Release |
| **JNI_ABORT** | Discard uncopied-back contents and free the copy | Does not restore direct modifications; ends access |

The JNI documentation specifies that the **mode parameter has no effect if elems is not a copy**. Therefore, you can only rely on keeping the buffer after **JNI_COMMIT** when a copy was actually provided (**isCopy == JNI_TRUE**). In the other branch, treat access as having ended after Release.

### 3.1. mode = 0: Results Are Applied

Suppose Java has the array **[1, 2, 3]**:

~~~c
p[0] = 10;
(*env)->ReleaseIntArrayElements(env, array, p, 0);
~~~

After the JNI function returns normally, Java has:

~~~text
[10, 2, 3]
~~~

The result does not depend on the copy or direct strategy: when copied, release copies the values back; when direct, the values have already changed. **p expires after release**.

### 3.2. JNI_ABORT: Two Valid Outcomes

~~~c
p[0] = 10;
(*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
~~~

If Java initially had **[1, 2, 3]**:

| isCopy | Java array after release | Reason |
| --- | --- | --- |
| **JNI_TRUE** | **[1, 2, 3]** | 10 only resides in the copy buffer, not copied back |
| **JNI_FALSE** | **[10, 2, 3]** | 10 was written directly; JNI_ABORT does not undo |

Consequence: do not use **JNI_ABORT** as a business rollback mechanism for an algorithm that modifies an array and might then be rejected.

### 3.3. JNI_COMMIT: Copy-Back Checkpoint for a Copy

When **isCopy == JNI_TRUE** is certain, you can do:

~~~c
p[0] = 10;
(*env)->ReleaseIntArrayElements(env, array, p, JNI_COMMIT);
/* Java has received 10; the copy buffer is still kept. */

p[0] = 20;
(*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
/* 20 is not copied back; Java still keeps 10. */
~~~

Java receives **[10, 2, 3]**. **JNI_ABORT at the end cannot undo the previous JNI_COMMIT**. If the final release uses mode **0**, the copy now containing **20** will be copied back, resulting in **[20, 2, 3]**.

Note: the snippet above is only valid when **p is a copy that is still kept**. If **isCopy == JNI_FALSE**, do not access **p** again after the Release call with **JNI_COMMIT**. In practice, if you do not need to keep using the buffer after copy-back, just calling **Release(..., 0)** is sufficient and less error-prone.

### 3.4. Practical Selection Table

| Purpose | Recommended approach |
| --- | --- |
| Native modifies array, Java must receive the result | **Release(..., 0)** |
| Native only reads, modifies nothing | **Release(..., JNI_ABORT)** to avoid useless copy-back |
| Want to publish the current state and continue using the **copy** | **JNI_COMMIT** with **isCopy == JNI_TRUE**, then final release |
| Want to discard all effects if the algorithm fails | **Independent buffer** and write to Java only when accepted |
| Only read/write a specific region | **Get...ArrayRegion/Set...ArrayRegion** per the desired contract |

## 4. Runnable JNI Example with Java 17+: Observing All Three Modes

The example demonstrates three separate array borrows and prints **isCopy** for each; it does not force the JVM to copy or pin. It also adds an “accept/reject” path using a native-owned buffer.

### 4.1. Java: src/ReleaseModesDemo.java

~~~java
import java.util.Arrays;

public final class ReleaseModesDemo {
    static {
        System.loadLibrary("release_modes");
    }

    private static final int NORMAL = 0;
    private static final int ABORT = 1;
    private static final int COMMIT_THEN_ABORT = 2;

    private static native boolean edit(int[] values, int scenario);
    private static native void applyWhenAccepted(int[] values, boolean accept);

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        boolean copyA = edit(a, NORMAL);
        System.out.printf("normal: %s (isCopy=%s)%n",
                Arrays.toString(a), copyA);
        require(a[0] == 10, "mode 0 must apply the change");

        int[] b = {1, 2, 3};
        boolean copyB = edit(b, ABORT);
        System.out.printf("abort: %s (isCopy=%s)%n",
                Arrays.toString(b), copyB);
        require(b[0] == (copyB ? 1 : 10),
                "JNI_ABORT must respect the copy/direct branch");

        int[] c = {1, 2, 3};
        boolean copyC = edit(c, COMMIT_THEN_ABORT);
        System.out.printf("commit: %s (isCopy=%s)%n",
                Arrays.toString(c), copyC);
        require(c[0] == 10, "committed value must remain");

        int[] staged = {1, 2, 3};
        applyWhenAccepted(staged, false);
        System.out.println("reject: " + Arrays.toString(staged));
        require(staged[0] == 1, "reject must keep original data");

        applyWhenAccepted(staged, true);
        System.out.println("accept: " + Arrays.toString(staged));
        require(staged[0] == 77, "accept must publish new data");

        System.out.println("Checks passed");
    }
}
~~~

The three numbers **NORMAL/ABORT/COMMIT_THEN_ABORT** are **scenario codes of the Java program**, not the constant values **JNI_ABORT/JNI_COMMIT**. The C side maps the choice to the actual JNI mode.

### 4.2. C: native/release_modes.c

~~~c
#include <jni.h>

static void invalid_input(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

JNIEXPORT jboolean JNICALL
Java_ReleaseModesDemo_edit(
        JNIEnv *env, jclass owner, jintArray array, jint scenario) {
    (void)owner;

    if (array == NULL) {
        invalid_input(env, "array must not be null");
        return JNI_FALSE;
    }
    if ((*env)->GetArrayLength(env, array) < 1) {
        invalid_input(env, "array must not be empty");
        return JNI_FALSE;
    }
    if (scenario < 0 || scenario > 2) {
        invalid_input(env, "unknown scenario");
        return JNI_FALSE;
    }

    jboolean copied = JNI_FALSE;
    jint *p = (*env)->GetIntArrayElements(env, array, &copied);
    if (p == NULL) {
        return JNI_FALSE; /* Do not dereference; an exception may be pending. */
    }

    p[0] = 10;

    if (scenario == 0) {
        (*env)->ReleaseIntArrayElements(env, array, p, 0);
    } else if (scenario == 1) {
        (*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
    } else {
        (*env)->ReleaseIntArrayElements(env, array, p, JNI_COMMIT);

        if (copied == JNI_TRUE) {
            /*
             * Only the copy branch keeps the buffer after COMMIT.
             * Modify again but discard the second change.
             */
            p[0] = 20;
            (*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
        }
        /* If not copied, do not use p after Release. */
    }

    return copied;
}

JNIEXPORT void JNICALL
Java_ReleaseModesDemo_applyWhenAccepted(
        JNIEnv *env, jclass owner, jintArray array, jboolean accept) {
    (void)owner;

    if (array == NULL) {
        invalid_input(env, "array must not be null");
        return;
    }
    if ((*env)->GetArrayLength(env, array) != 3) {
        invalid_input(env, "array must have exactly 3 items");
        return;
    }

    /* This buffer belongs to native, separate from the Java array. */
    jint staging[3];
    (*env)->GetIntArrayRegion(env, array, 0, 3, staging);
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    staging[0] = 77;
    if (accept == JNI_TRUE) {
        (*env)->SetIntArrayRegion(env, array, 0, 3, staging);
    }
}
~~~

The two exports **Java_ReleaseModesDemo_edit** and **Java_ReleaseModesDemo_applyWhenAccepted** correspond to a Java class in the **default package** and two **static** native methods; the second parameter is **jclass**. When an application places the class in another package, you must update the JNI symbol names according to the package or use native method registration.

**Path explanation:**

1. **scenario 0** modifies the first element and then releases with mode **0**, always returning **10** to Java.
2. **scenario 1** modifies the first element and then releases with **JNI_ABORT**, keeping **1** if copied or receiving **10** if direct.
3. **scenario 2** calls **JNI_COMMIT** after writing **10**; if there is a copy, it modifies further to **20**, then releases with **JNI_ABORT** to discard the second modification. If there is no copy, it does not reuse the released pointer. The Java result is **10** in both branches.
4. **applyWhenAccepted** copies into **staging** using **GetIntArrayRegion**; only when accepted does it call **SetIntArrayRegion**. Thus, rejection has a deterministic result, independent of whether the JVM chooses copy or direct in another API.

### 4.3. Compiling and Running (Linux, JDK 17+)

File structure:

~~~text
src/ReleaseModesDemo.java
native/release_modes.c
~~~

Ensure **JAVA_HOME** points to a JDK installation with JNI headers and a C compiler of the same architecture as the JVM:

~~~bash
mkdir -p src native out

javac -h native -d out src/ReleaseModesDemo.java

cc -std=c17 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/release_modes.c -o librelease_modes.so

java -Xcheck:jni -Djava.library.path=. -cp out ReleaseModesDemo
~~~

**javac -h** generates a header containing JNI prototypes for reference; the C source above uses **jni.h** and export names matching the demo class. On Windows/macOS, adjust the shared library build command and include paths according to the toolchain/JDK; do not use the Linux commands verbatim.

### 4.4. Stdout: Multiple Valid Outputs Due to isCopy

If all three calls use a copy buffer, stdout may be:

~~~text
normal: [10, 2, 3] (isCopy=true)
abort: [1, 2, 3] (isCopy=true)
commit: [10, 2, 3] (isCopy=true)
reject: [1, 2, 3]
accept: [77, 2, 3]
Checks passed
~~~

If all three calls access directly:

~~~text
normal: [10, 2, 3] (isCopy=false)
abort: [10, 2, 3] (isCopy=false)
commit: [10, 2, 3] (isCopy=false)
reject: [1, 2, 3]
accept: [77, 2, 3]
Checks passed
~~~

These are **two conditional examples**, not a guarantee of a fixed JVM choice. Each Get call can return **true** or **false** independently. The **require** checks in the program verify the semantics according to the **actual isCopy**, while **reject/accept** always have deterministic results.

If the library is missing or the JNI architecture mismatches, the JVM may throw **UnsatisfiedLinkError** before running the demo; that is a build/load error different from release mode semantics.

## 5. Why Shouldn't JNI_ABORT Be Used as a Transaction Cancel Command?

Suppose native code modifies data and then validates it. The following pattern has a **semantic bug**:

~~~c
/* Counter-example; assumes p was successfully obtained from GetIntArrayElements. */
p[0] = 99;
if (validationFailed) {
    (*env)->ReleaseIntArrayElements(env, array, p, JNI_ABORT);
    return;
}
(*env)->ReleaseIntArrayElements(env, array, p, 0);
~~~

If **p** is a direct pointer, the Java array already has **99**, even though the validation branch failed. Therefore, **JNI_ABORT** does not provide a “failure ⇒ Java array unchanged” guarantee.

A design with explicit rejection capability:

~~~text
Read Java array into a separate native region
            |
            v
    Compute / validate
         /        \
     failure    success
        |          |
  no Set...   Set...ArrayRegion
        |          |
Java unchanged  Java receives result
~~~

Depending on the problem, choose:

- **GetIntArrayRegion → staging → SetIntArrayRegion**: suitable for a slice of known size, with native managing the buffer.
- **Java array.clone() → process clone → apply only when accepted**: leverages Java memory management, useful when Java decides the result.
- **Create a new Java array with NewIntArray/SetIntArrayRegion**: returns separate result data, and the caller decides whether to use or discard it.
- **Independent native buffer with malloc**: if the data is large, you must compute **sizeof(jint) * len** safely, check allocation, and **free** at the right time. This is a native-owned buffer, not a Get...Elements pointer.

A Java-only example of this idea:

~~~java
import java.util.Arrays;

public final class ArrayDecision {
    static void maybeReplace(int[] target, boolean accept) {
        int[] candidate = target.clone();
        candidate[0] = 99;
        if (accept) {
            System.arraycopy(candidate, 0, target, 0, target.length);
        }
    }

    public static void main(String[] args) {
        int[] values = {1, 2, 3};
        maybeReplace(values, false);
        System.out.println(Arrays.toString(values));
        maybeReplace(values, true);
        System.out.println(Arrays.toString(values));
    }
}
~~~

Save as **ArrayDecision.java**, then run **javac ArrayDecision.java** and **java ArrayDecision**. Exact stdout:

~~~text
[1, 2, 3]
[99, 2, 3]
~~~

This is a **Java-only** program, not using JNI. The native **applyWhenAccepted** example in section 4 implements the same contract over a C buffer.

**Limitation warning:** **Set...ArrayRegion** is only a region-copy operation and does not automatically turn multiple write steps into a global transaction. If atomicity with other resources and threads is needed, you must design commit/handoff according to business requirements.

## 6. Related APIs and Scope of Modes

### 6.1. Primitive Arrays

The **Get/Release\<PrimitiveType\>ArrayElements** pairs share the same modes:

| Java | JNI Get | JNI Release |
| --- | --- | --- |
| **boolean[]** | **GetBooleanArrayElements** | **ReleaseBooleanArrayElements** |
| **byte[]** | **GetByteArrayElements** | **ReleaseByteArrayElements** |
| **char[]** | **GetCharArrayElements** | **ReleaseCharArrayElements** |
| **short[]** | **GetShortArrayElements** | **ReleaseShortArrayElements** |
| **int[]** | **GetIntArrayElements** | **ReleaseIntArrayElements** |
| **long[]** | **GetLongArrayElements** | **ReleaseLongArrayElements** |
| **float[]** | **GetFloatArrayElements** | **ReleaseFloatArrayElements** |
| **double[]** | **GetDoubleArrayElements** | **ReleaseDoubleArrayElements** |

Each pair must match the type and the same source array. For **boolean[]**, JNI provides **jboolean** elements, each taking one byte on the native side, regardless of how the JVM stores booleans internally. Other primitive arrays have contiguous data according to JNI, but the provided address must still be managed with the Get/Release pair.

### 6.2. Get/Set ArrayRegion Has No Release Mode

**GetIntArrayRegion** copies a region of a Java array into a caller-owned C buffer. **SetIntArrayRegion** copies back from a C buffer into Java. Neither function gives you a JNI pointer that you must Release, so **they do not accept JNI_COMMIT/JNI_ABORT**. Check indices and lengths, check for exceptions, and do not read/write past the buffer size.

### 6.3. GetPrimitiveArrayCritical Has Strict Restrictions

**GetPrimitiveArrayCritical** and **ReleasePrimitiveArrayCritical** have similar copy/direct and mode semantics, but a **critical region** exists:

- The time from Get to Release must be very short.
- Do not arbitrarily call other JNI functions inside the critical region.
- Avoid syscalls that may block waiting on Java threads, or prolonged locks/callbacks/I/O.
- Do not assume the API always provides zero-copy; the JVM may still create a copy.
- **JNI_ABORT** does not undo direct modifications if the pointer is not a copy.

Do not use **ReleaseIntArrayElements** to release a pointer obtained from **GetPrimitiveArrayCritical**; you must use **ReleasePrimitiveArrayCritical**.

### 6.4. String and Object Arrays Do Not Have These Modes

Java **String** is immutable, and **ReleaseStringChars**, **ReleaseStringUTFChars**, and **ReleaseStringCritical** do not take a **JNI_COMMIT/JNI_ABORT** parameter. For **jobjectArray**, use **GetObjectArrayElement/SetObjectArrayElement**; there is no **ReleaseObjectArrayElements**. **DirectByteBuffer** has its own memory ownership mechanism and also does not use the three modes of primitive arrays.

## 7. Lifecycle, Exceptions, and Thread Constraints

**Get failure:** if **GetIntArrayElements** returns **NULL**, do not dereference it, and do not call **ReleaseIntArrayElements** on a NULL pointer. The JVM may report **OutOfMemoryError** or an error state; the caller needs to handle pending exceptions per the contract. The JNI specification also allows some functions to return NULL without necessarily throwing an exception, so do not assume every NULL has a pending exception.

**Release in the right pair and the right number of times:**

- A pointer from **GetIntArrayElements** → **ReleaseIntArrayElements** on **the same jintArray**.
- After **Release(..., 0)** or **Release(..., JNI_ABORT)**, do not read/write through the pointer.
- With **isCopy==JNI_TRUE** and **JNI_COMMIT**, the copy buffer remains alive; end with a final release of **0** or **JNI_ABORT**.
- Do not misuse double-release; only the copy-buffer branch that remains alive after commit needs a final release. Do not call **free** on a pointer returned by JNI.

**Do not leak buffers on error paths:** when Get succeeds and there are multiple return conditions afterward, organize cleanup so every path calls Release. For code that may modify the array and then fail, cleaning up with JNI_ABORT **does not guarantee the data is discarded**; switch to an independent buffer if you need to preserve the array on error.

**Thread:** **JNIEnv*** belongs to a thread; do not pass it to another native thread. **isCopy==JNI_FALSE** does not allow native code to hold the pointer across unbounded time, even if the address does not change. If Java and native/other Java threads read and write the array concurrently, a valid synchronization protocol must be used; **Release...** does not by itself replace a lock, happens-before, or a result-publishing contract.

**JNI_COMMIT is not a transaction commit:** copied-back values can be observed by Java under valid conditions, but commit does not guarantee atomicity across multiple arrays or multiple operations, does not write data to disk, cannot roll back side effects that have already occurred, and does not by itself guarantee thread-safe visibility. The copy-back point must be distinguished from the business milestone.

## 8. Common Mistakes

| Misconception / Wrong Practice | Risk | Fix |
| --- | --- | --- |
| “JNI_ABORT guarantees the array is unchanged” | Direct pointer already modified the Java array | Use a staging buffer and only Set when accepted |
| “JNI_COMMIT frees the buffer like 0” | Copy buffer remains held, easy to leak resources | Final release when **isCopy==JNI_TRUE** |
| “isCopy=false so Release is unnecessary” | Violates JNI lifecycle, may hold GC-related resources | Always Release in matching pairs |
| Calling **free(p)** after Get | Wrong ownership, crash/corruption | Use **Release...ArrayElements** |
| Accessing **p** after final Release | Use-after-release | Do not use an expired pointer |
| Always continuing to modify **p** after **JNI_COMMIT** | If not copied, the pointer is not guaranteed to remain valid | Only reuse when the copy is still kept |
| Using **JNI_ABORT** to “undo” a commit that already happened | Committed values remain in the Java array | Design higher-level checkpoints or transactions |
| Mixing Get/Release of different types | JNI error, unsafe memory | Use the matching type pair and original array |
| Using **JNI_COMMIT** for **String/jobjectArray** | Wrong API | Use the appropriate string/object array API |
| Holding a critical pointer for long, calling other JNI or blocking I/O | Affects GC, risk of deadlock | Keep critical region very short |
| Not checking **NULL**/pending exception | Crash or meaningless results | Check and clean up |
| Expecting a single Release to synchronize all Java threads | Race, missing memory ordering | Design separate synchronization |

## 9. Self-Check Questions

**Question 1.** Java has **[3, 4]**, native receives **isCopy=JNI_TRUE**, assigns **p[0]=9**, then **JNI_ABORT**. What does Java receive?

**Answer:** **[3, 4]**. The copy buffer is discarded before copy-back.

**Question 2.** The same scenario above with **isCopy=JNI_FALSE**?

**Answer:** **[9, 4]**. Modified directly; JNI_ABORT does not undo.

**Question 3.** Native receives a **copy**, writes **p[0]=7**, calls **JNI_COMMIT**, writes **p[0]=8**, and finally **JNI_ABORT**. Which value does Java receive?

**Answer:** **7**, because the value **7** was already copied back during the commit; the value **8** was only in the copy buffer and was discarded afterward.

**Question 4.** When is using mode **0** appropriate?

**Answer:** When native has modified the data and wants Java to receive those values, while wanting to end holding the pointer immediately.

**Question 5.** Does using **JNI_ABORT** guarantee a native parser “never touched Java data” if the parser modified the pointer before reporting an error?

**Answer:** No. You must use a separate buffer or a new result array if you need to guarantee the original array is unchanged on failure.

**Question 6.** Why must **JNI_COMMIT** be distinguished from a transaction commit?

**Answer:** It only has JNI copy-back/buffer-management semantics. It does not guarantee atomicity of multiple operations, does not provide rollback, and does not by itself establish multithreaded synchronization.

## Official Documentation

- Oracle JNI Specification, Java SE 21 — **Get\<PrimitiveType\>ArrayElements / Release\<PrimitiveType\>ArrayElements**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#releaseprimitivetypearrayelements-routines
- Oracle JNI Specification — **Get\<PrimitiveType\>ArrayRegion / Set\<PrimitiveType\>ArrayRegion**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#getprimitivetypearrayregion-routines
- Oracle JNI Specification — **GetPrimitiveArrayCritical / ReleasePrimitiveArrayCritical**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#getprimitivearraycritical-releaseprimitivearraycritical
- Oracle JNI Specification — **Exception Handling**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#exception-handling

**Study takeaway:** **0** keeps modifications and ends access; **JNI_COMMIT** copies back but keeps the **copy buffer**; **JNI_ABORT** only discards uncopied-back changes **on a copy**. If you want to “discard results while ensuring Java is definitely unchanged”, use a **staging buffer** and explicitly control when data is copied back to Java.