# MonitorEnter, MonitorExit, and the Risk of Deadlock When Calling Back into Java While Holding a Lock

## 1. The Problem: Synchronization Across the Java ↔ JNI Boundary

In the **Java Advance – native-interoperability** module, under the **Threads with JNI** group, native code may need to protect the state of a Java object accessed by multiple threads. JNI provides `MonitorEnter` and `MonitorExit` to participate in the **same object monitor** that Java uses with `synchronized`. However, calling back from C/C++ into Java (*callback*) while holding a lock is a dangerous spot: the callback may wait on another lock, a worker, or an asynchronous task, forming a **wait cycle** and causing deadlock.

This lesson explains precisely **when a callback under the same lock is valid reentrancy**, **when a callback can deadlock**, and builds a runnable Java 17+ / C11 program with:
- A JNI method that acquires an object's monitor and then calls a Java `synchronized` method **on the same thread**; this is **reentrancy**, not a default deadlock.
- A JNI method that updates data under the monitor and **releases the monitor before calling the Java callback** to reduce the risk window.
- A callback that throws a Java exception; C still calls `MonitorExit` and does not leak the lock.
- Another Java thread that verifies the lock has actually been released after the exception.
- Build commands on Linux, macOS, Windows, expected stdout, and a deadlock diagnostic table.

Skills after this lesson: reading `JNIEnv *` / `jobject` / `jint` correctly, checking return codes, symmetric lock–unlock including on error paths, understanding reentrant monitors, recognizing AB–BA lock ordering, inspecting thread dumps, and designing callbacks that do not hold unnecessary locks.

**Scope:** this lesson focuses on **JNI object monitors**; C mutexes (`pthread_mutex_t`, `CRITICAL_SECTION`, `std::mutex`) are a **different kind of lock**—do not replace `MonitorExit` with a C mutex unlock or vice versa.

## 2. One Java Object, Same Monitor, Two Ways to Access

A Java object has a monitor that Java can enter using:

~~~java
// Illustrative fragment. lock is a valid Java object.
synchronized (lock) {
    // Only one thread owns this monitor at a time.
}
~~~

If C code receives a valid `jobject lock`, it can enter **that exact object's monitor**:

~~~c
/* C fragment inside a JNI method, with valid env/lock. */
jint result = (*env)->MonitorEnter(env, lock);
if (result != JNI_OK) {
    return;  /* Does not own the monitor; do not call MonitorExit. */
}

/* Section protected by lock's monitor. */

jint exit_result = (*env)->MonitorExit(env, lock);
if (exit_result != JNI_OK) {
    return;  /* This is an error; do not assume unlock succeeded. */
}
~~~

Mutual exclusion applies to the same **object identity** regardless of whether the enter comes from Java bytecode or from JNI. For example, Java `synchronized (lock)` and C `MonitorEnter(env, lock)` contend for the same lock.

### Monitor State and Reentrancy

~~~text
Object monitor M of State
  owner: none                  count=0
  Thread T calls JNI MonitorEnter count=1, owner=T
  C calls back State.add()     synchronized on the same State
  Thread T reenters M          count=2, owner=T
  Java method returns          count=1, owner=T
  C JNI MonitorExit            count=0, owner=none
~~~

**Monitors are reentrant:** a thread that already owns a monitor can reenter it without blocking itself. Therefore:

- JNI thread T holds `state`'s monitor.
- JNI calls `CallVoidMethod(state, add, ...)`.
- `State.add` is declared `synchronized` on **the same `state`**.
- The callback executes **synchronously on T itself**, increments the reentrance count, and returns to C.

This scenario **does not automatically deadlock**, because no other thread holds the monitor and there is no wait cycle. However, the callback may lock **another object**, wait on `Future.get()`, call another native API, or coordinate with another worker. As soon as an opposite lock acquisition order arises, there is still a risk of deadlock.

### Do Not Mix the Two Release Mechanisms

Even though they share the same monitor, **a JNI entry and a Java bytecode entry must be released by the exact mechanism that acquired them**:

- A JNI `MonitorEnter` **must** have a corresponding JNI `MonitorExit`. Do not rely on the closing `}` of Java `synchronized`, returning from a Java synchronized method, or returning from a native method to release the lock portion owned by JNI.
- A monitor entry created by Java `synchronized` / bytecode `monitorenter` **must not** be released by JNI `MonitorExit`.
- Java generates the corresponding `monitorexit` path for `synchronized` in `finally`; your C code **must write its own cleanup** for every branch after `MonitorEnter` succeeds.

The JNI specification mentions that `DetachCurrentThread` releases JNI monitors in certain situations, but **you must not design code relying on detaching as a substitute for proper cleanup**: detached threads have their own rules, and a Java-owned thread must not be detached arbitrarily.

## 3. `MonitorEnter`, `MonitorExit`: Prototypes, Status, Ownership

The two functions have the JNI prototypes:

~~~c
jint MonitorEnter(JNIEnv *env, jobject obj);
jint MonitorExit(JNIEnv *env, jobject obj);
~~~

How to call them in a **C** file:

~~~c
jint status = (*env)->MonitorEnter(env, obj);
/* ... */
jint exit_status = (*env)->MonitorExit(env, obj);
~~~

In **C++**, the JNI header provides a different wrapper syntax:

~~~cpp
jint status = env->MonitorEnter(obj);
// ...
jint exit_status = env->MonitorExit(obj);
~~~

The C/C++ code above are **fragments**, not standalone programs. Do not mix C++ syntax into a `.c` file.

| Item | `MonitorEnter` | `MonitorExit` |
|---|---|---|
| Second parameter | Valid `jobject`, **non-NULL** | Same object that was entered, **non-NULL** |
| Action | Acquires the monitor; if another thread holds it, waits | Decrements the reentrance count owned by the current thread; releases when it reaches 0 |
| Success | Returns `JNI_OK` = `0` | Returns `JNI_OK` = `0` |
| Failure | Negative value; do not treat as holding the lock | Negative value; for example, may throw `IllegalMonitorStateException` if the thread does not own it |
| Requirements | `env` attached to the current thread; object ref still valid | **Same thread that is the owner**; matches the count of JNI enters |
| Design bugs | Passing NULL, deadlock because the lock is owned by another thread | Forgetting to exit, under/over-exiting, exiting from a different thread |

`JNI_OK` does not merely mean "no exception"; it means **acquisition succeeded**. If `MonitorEnter` returns an error, do not set a `locked = 1` flag and do not blindly call `MonitorExit`. If entering succeeds, there must be a cleanup path executed **exactly once per JNI entry**. If the same thread enters twice via JNI, it must exit twice via JNI; calling a Java `synchronized` method in between does not compensate for the JNI entry count.

### Why Do `env` and `obj` Also Need Proper Lifetimes?

- `JNIEnv *env` is only valid for the thread to which the JVM issued it; do not pass `env` as-is to a native worker to lock on its behalf. A worker must attach to the JVM itself if needed and obtain its own `JNIEnv *`.
- A `jobject obj` from a JNI parameter is a local reference valid within the scope of that JNI call. If C stores the object across an asynchronous callback or after the call returns, it must create an appropriate global reference and have a `DeleteGlobalRef` path. **Holding a monitor does not turn a local ref into a global ref**.
- `obj == NULL` is a **precondition violation** of both monitor calls. Do not expect the JVM to handle NULL "safely" on all platforms.
- Do not cast an address from `malloc` or a C++ pointer to `jobject`; this monitor belongs to a Java object.

### Memory Synchronization

When the same Java object's monitor is entered/exited according to the rules, the synchronization logic corresponds to Java monitor lock/unlock: Java/C code must follow the same lock discipline for the protected data. For example, Java `synchronized int value()` and JNI `MonitorEnter(state)` followed by `SetIntField` help prevent data races **within the scope of paths that also use that monitor**. Another code path reading/writing the field bare without holding the lock still breaks the synchronization protocol.

## 4. Three Callback Patterns to Distinguish Reentrancy from Deadlock

### A. Reentrant Callback on the Same Monitor, Same Thread

~~~text
Thread T
  JNI MonitorEnter(State)      -- M(State) owner=T, count=1
    CallVoidMethod(State.add)  -- Java synchronized State.add
      Java monitorenter State -- M(State) owner=T, count=2
      add value
      Java monitorexit        -- count=1
  JNI MonitorExit(State)       -- count=0
~~~

This is the case used in a controlled manner in `callbackInside` of the program below. You should still limit calling unknown code inside a locked region: future callbacks might change behavior, acquire additional locks, or wait on other threads.

### B. AB–BA: JNI Holds B Then Callback Needs A; Another Thread Holds A Then Needs B

~~~text
          Thread T1 (JNI callback)             Thread T2 (Java + JNI)
         --------------------------------     ---------------------------
         JNI MonitorEnter(lockB)              synchronized(lockA)
         holds lockB                          holds lockA
         CallVoidMethod(listener.onEvent)     calls JNI MonitorEnter(lockB)
             synchronized(lockA)                 waits for lockB held by T1
                 waits for lockA held by T2
         --------------------------------     ---------------------------
                  T1 waits for A                T2 waits for B

                            A -> B -> A (wait cycle)
~~~

T1 cannot finish the callback to reach `MonitorExit(lockB)` because it needs A. T2 cannot exit `synchronized(lockA)` because it is waiting for B. This is a **real deadlock**, even though both monitors are reentrant: reentrancy only allows a thread to reenter **a monitor it already owns**, not a monitor held by another thread.

**Cycle-breaking rule:** an often effective approach is to **release B before the callback** and only then let the Java callback lock A. Of course, if code calling JNI from Java already holds other locks, you must analyze the entire lock graph, not just two lines of JNI.

### C. Holding a Monitor While Waiting on a Thread That Needs That Same Monitor

~~~text
Thread T1: JNI MonitorEnter(state)
           CallVoidMethod(Java.onEvent)
             Java onEvent: Future.get() / join() waits for T2
Thread T2: synchronized(state) to complete the task
           blocked by monitor held by T1
=> T1 waits for T2, T2 waits for T1
~~~

Even though the callback runs on T1 itself, it can **wait on another thread**. Thus "reentrant monitor" **does not mean a callback is always safe while holding the lock**. A callback can indirectly create a deadlock via a thread pool, UI event dispatch thread, completion callback, or native mutex.

## 5. Cleanup Principle: try/finally in Java, Common Exit Path in JNI

Java `synchronized` automatically releases the monitor via bytecode even when an exception escapes. JNI C has no such automatic mechanism:

~~~c
/* C fragment illustrating cleanup structure; obj/env must be valid. */
jint entered = (*env)->MonitorEnter(env, obj);
if (entered != JNI_OK) {
    return;
}

/* Ownership acquired. Every branch below must reach cleanup. */
do_work_under_lock();      /* Illustrative application function, may fail. */

/* Do not skip this step even if JNI/Java has thrown an exception. */
jint exited = (*env)->MonitorExit(env, obj);
if (exited != JNI_OK) {
    return;               /* Report error per application contract. */
}
~~~

The illustrative snippet does not have `goto cleanup` yet, so **do not** insert an early `return` inside `do_work_under_lock`. For complex native methods, use **a single cleanup label** and a `locked` flag or a tested C++ RAII scope guard. Do not call `MonitorExit` on the branch where `MonitorEnter` failed.

### CallVoidMethod Can Throw a Java Exception, Yet You Must Still Unlock

A JNI callback:

~~~c
(*env)->CallVoidMethod(env, obj, method_id, arg);
~~~

can leave a **pending Java exception**, for example when the Java callback throws `IllegalArgumentException`. At this point, native C must not arbitrarily call other JNI methods that may be unsafe while an exception is pending. However, the JNI spec permits calling **`MonitorExit`** with a pending exception. Valid structure:

~~~c
if ((*env)->MonitorEnter(env, obj) != JNI_OK) return;

(*env)->CallVoidMethod(env, obj, callback_id, arg);

/* Must release the JNI monitor even if the callback threw an exception. */
jint rc = (*env)->MonitorExit(env, obj);
if (rc != JNI_OK) return;

/* If the callback threw an exception, return to Java so it propagates.
   Do not invoke another JNI callback while an exception is pending. */
if ((*env)->ExceptionCheck(env)) return;
~~~

Here `ExceptionCheck` only **checks**; it does not clear the exception. When the native method returns with a pending exception, the JVM delivers that Java exception to the Java caller. Do not call `ExceptionClear` and print "success" unless the API is explicitly designed to **handle and translate** errors under a clear contract.

If `MonitorExit` reports an error (especially `IllegalMonitorStateException`), that is a **serious ownership violation** and must not be ignored as a harmless warning. An unbalanced held JNI monitor can cause other threads to hang forever.

## 6. Complete Java 17+ and C11 Example: Callback Inside Lock, Callback Outside Lock, and Exception

Project tree:

~~~text
jni-monitor/
├─ src/
│  └─ demo/
│     └─ jni/
│        └─ MonitorLesson.java
├─ native/
│  ├─ demo_jni_MonitorLesson.h   # Generated by javac -h
│  └─ monitor_lesson.c
├─ out/
│  └─ demo/jni/MonitorLesson.class
└─ libmonitorlesson.so          # Linux;
                               # macOS: libmonitorlesson.dylib
                               # Windows: monitorlesson.dll
~~~

The `.class` and `.h` files are generated by `javac`; you do **not** create them manually. The commands below run from the `jni-monitor` project directory.

### 6.1. Complete Java Source

Create **`src/demo/jni/MonitorLesson.java`**:

~~~java
package demo.jni;

import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public final class MonitorLesson {
    static { System.loadLibrary("monitorlesson"); }

    private MonitorLesson() {}

    public static final class State {
        private int value;
        private int notices;

        public synchronized void add(int delta) {
            if (delta < 0) {
                throw new IllegalArgumentException("negative delta");
            }
            value += delta;
        }

        public synchronized void onNotice() { notices++; }
        public synchronized int value() { return value; }
        public synchronized int notices() { return notices; }
    }

    private static native void callbackInside(State state, int delta);
    private static native void updateThenNotify(State state, int delta);

    public static void main(String[] args) throws Exception {
        State state = new State();

        callbackInside(state, 2);
        System.out.println("afterInside=" + state.value());

        updateThenNotify(state, 3);
        System.out.println("afterOutside=" + state.value()
                + ", notices=" + state.notices());

        try {
            callbackInside(state, -1);
            throw new AssertionError("Exception expected");
        } catch (IllegalArgumentException expected) {
            if (!"negative delta".equals(expected.getMessage())) {
                throw expected;
            }
            System.out.println("caught=" + expected.getMessage());
        }

        FutureTask<Integer> probe = new FutureTask<>(state::value);
        Thread verifier = new Thread(probe, "monitor-verifier");
        verifier.setDaemon(true);
        verifier.start();
        if (probe.get(5, TimeUnit.SECONDS) != 5) {
            throw new AssertionError("Unexpected state after exception");
        }

        updateThenNotify(state, 1);
        System.out.println("afterRecovery=" + state.value()
                + ", notices=" + state.notices());
        System.out.println("RESULT: PASS");
    }
}
~~~

**Step-by-step meaning:**

- `State.add` and `State.value` both lock the intrinsic monitor of **the `state` instance itself**. `State.onNotice` is also synchronized on that instance.
- `callbackInside(state, 2)`: JNI `MonitorEnter(state)` → `CallVoidMethod(state.add)` → Java `synchronized add` reenters on **the same thread** → JNI `MonitorExit`. Result: `value==2`.
- `updateThenNotify(state, 3)`: JNI updates `value` from 2 to 5 under the monitor, calls `MonitorExit`, and only then calls back `onNotice`, so `notices==1`. That is the **update–unlock–notify** pattern.
- `callbackInside(state, -1)` invokes the Java callback, which throws `IllegalArgumentException("negative delta")`. C **still calls `MonitorExit` before returning**. The Java catch only verifies the exact expected error so it does not accidentally mask JNI errors.
- `FutureTask` in another Java thread calls `state.value()` — an operation requiring `state`'s monitor. `get(5, TimeUnit.SECONDS)` creates a **time-bounded** check: if the monitor were still held by JNI after the exception, the verifier thread could not complete. The timeout is a scheduling-dependent test safety guard (it can false-fail on an overloaded machine), not real-time proof about GC/VM; on a normal run it completes.
- After the check, `updateThenNotify(state, 1)` increments from 5 to 6 and notifications to 2. No Java path prints `RESULT: PASS` before all checks complete.

**Contract bounds:** `value` and `notices` state are protected by `state`'s monitor, and the demo only operates on small values to avoid `jint` overflow. A real library must check for overflow and its own data invariants. Marking the Java fields `private` does not make them inaccessible from JNI; JNI can obtain field IDs when permitted by the JNI API.

### 6.2. Generate the JNI Header and Inspect Descriptors

Create the directory tree, then run:

~~~sh
mkdir -p src/demo/jni native out
javac --release 17 -h native -d out src/demo/jni/MonitorLesson.java
javap -s -p -classpath out demo.jni.MonitorLesson
~~~

On Windows CMD, you can create `src\demo\jni`, `native`, `out` with separate `mkdir` commands; then run `javac --release 17 -h native -d out src\demo\jni\MonitorLesson.java`.

`javac` generates **`native/demo_jni_MonitorLesson.h`**; JNI names are based on `package demo.jni` and `class MonitorLesson`. Both native methods take `State` and `int`, and return `void`. The method descriptors from `javap` will contain:

~~~text
private static native void callbackInside(demo.jni.MonitorLesson$State, int);
  descriptor: (Ldemo/jni/MonitorLesson$State;I)V

private static native void updateThenNotify(demo.jni.MonitorLesson$State, int);
  descriptor: (Ldemo/jni/MonitorLesson$State;I)V
~~~

The lines above are an **excerpt**, not the full `javap` stdout. The notation `Ldemo/jni/MonitorLesson$State;` is the Java nested static class type in a JVM descriptor; `I` is `int` and `V` is `void`.

The generated C header has the key prototypes:

~~~c
JNIEXPORT void JNICALL Java_demo_jni_MonitorLesson_callbackInside
  (JNIEnv *, jclass, jobject, jint);

JNIEXPORT void JNICALL Java_demo_jni_MonitorLesson_updateThenNotify
  (JNIEnv *, jclass, jobject, jint);
~~~

Because the methods are **`static native`**, the C side receives the hidden arguments `JNIEnv *` then `jclass`, followed by `jobject state` and `jint delta`. Do not manually edit the generated header, and do not omit `JNIEXPORT/JNICALL`.

### 6.3. Complete C Source: Always Exit the Monitor Before Returning

Create **`native/monitor_lesson.c`**:

~~~c
#include "demo_jni_MonitorLesson.h"

JNIEXPORT void JNICALL Java_demo_jni_MonitorLesson_callbackInside(
        JNIEnv *env, jclass ignored, jobject state, jint delta) {
    (void)ignored;

    jclass type = (*env)->GetObjectClass(env, state);
    if (type == NULL) return;
    jmethodID add = (*env)->GetMethodID(env, type, "add", "(I)V");
    (*env)->DeleteLocalRef(env, type);
    if (add == NULL) return;

    if ((*env)->MonitorEnter(env, state) != JNI_OK) return;

    (*env)->CallVoidMethod(env, state, add, delta);

    /* Always release even if CallVoidMethod left a pending exception. */
    if ((*env)->MonitorExit(env, state) != JNI_OK) return;
}

JNIEXPORT void JNICALL Java_demo_jni_MonitorLesson_updateThenNotify(
        JNIEnv *env, jclass ignored, jobject state, jint delta) {
    (void)ignored;

    jclass type = (*env)->GetObjectClass(env, state);
    if (type == NULL) return;
    jfieldID value = (*env)->GetFieldID(env, type, "value", "I");
    if (value == NULL) { (*env)->DeleteLocalRef(env, type); return; }
    jmethodID notify = (*env)->GetMethodID(env, type, "onNotice", "()V");
    (*env)->DeleteLocalRef(env, type);
    if (notify == NULL) return;

    if ((*env)->MonitorEnter(env, state) != JNI_OK) return;

    jint old = (*env)->GetIntField(env, state, value);
    if (!(*env)->ExceptionCheck(env)) {
        (*env)->SetIntField(env, state, value, old + delta);
    }

    /* Exit first, including on exceptional paths. */
    if ((*env)->MonitorExit(env, state) != JNI_OK) return;
    if ((*env)->ExceptionCheck(env)) return;

    /* Java callback occurs after releasing this JNI monitor. */
    (*env)->CallVoidMethod(env, state, notify);
}
~~~

**This C code was compiled and run with the exact Java source above** on Linux (JDK 21, GCC C11, `-Wall -Wextra -Werror -pedantic`, `-Xcheck:jni`). In the code:

1. `GetObjectClass` returns a **local `jclass` reference**, and `GetMethodID/GetFieldID` obtains IDs to call methods/access fields; delete `jclass` after the lookup. In the demo, the IDs are used within the same native call and the class remains loaded; do not cache a local class ref across calls.
2. Both methods **look up method/field IDs before `MonitorEnter`** to shorten the time the monitor is held and avoid unnecessary lookups/class initialization inside the locked region.
3. Each method checks `MonitorEnter == JNI_OK` before doing work. If not acquired, **do not call `MonitorExit`**.
4. `callbackInside` intentionally calls `CallVoidMethod` while holding the monitor. The Java callback `State.add` is `synchronized` on `state` itself and runs on **the same thread**, so it is a valid reentrant example. It can still throw a Java exception.
5. Even if the callback throws, the next statement is `MonitorExit`. JNI allows releasing a monitor while a Java exception is pending; the native method then returns so the exception propagates to Java.
6. `updateThenNotify` reads/writes the `value` field inside the monitor. `State.value()` in Java is also synchronized on the same `state`, so the code paths in this lesson follow the same locking protocol. After `MonitorExit`, if there is no pending exception, C then calls `State.onNotice`.
7. `State.onNotice` is still a Java synchronized method, but at this point **the native monitor just acquired by this method has already been released**; this reduces the risk of AB–BA lock ordering. It cannot guarantee there are no other deadlocks in the entire application if the caller is still holding another lock when entering JNI.
8. If `MonitorExit` fails, the method stops immediately (production code must report/log the cause per its error policy rather than attempting to run the callback). A successful balanced `MonitorExit` in this example is verified by the checks after the native call returns.

**Syntax and exception note:** `MonitorExit` is among the JNI functions permitted when an exception is pending. Do not arbitrarily insert `FindClass`, `GetMethodID`, or `CallVoidMethod` **between a throwing callback and `MonitorExit`**. After `MonitorExit`, `ExceptionCheck` is used to decide whether to continue with the callback.

### 6.4. Compiling the Native Library on Each Platform

**Linux** (GCC or Clang):

~~~sh
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

cc -std=c11 -Wall -Wextra -pedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o libmonitorlesson.so native/monitor_lesson.c

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.MonitorLesson
~~~

If `JAVA_HOME` is already set to the JDK root, you do not need to recompute it. `-fPIC` and `-shared` build a shared object, while `-I` lets the compiler find `jni.h`, `jni_md.h`, and the header generated by `javac -h`.

**macOS** (Clang + Xcode Command Line Tools):

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home)"

cc -std=c11 -Wall -Wextra -pedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o libmonitorlesson.dylib native/monitor_lesson.c

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.MonitorLesson
~~~

Choose the native binary architecture matching the JVM (arm64 for arm64; x86-64 for x86-64). Do not use the default Linux `.so` extension if macOS expects `.dylib`.

**Windows** (MSVC Developer Command Prompt, with `cl.exe`, `JAVA_HOME` pointing to the JDK):

~~~bat
javac --release 17 -h native -d out src\demo\jni\MonitorLesson.java

cl /nologo /W4 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /Inative ^
  native\monitor_lesson.c /Fe:monitorlesson.dll

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.MonitorLesson
~~~

The `^` character is **CMD** line continuation, not PowerShell. `System.loadLibrary("monitorlesson")` takes the logical name, and the JVM maps it to `libmonitorlesson.so` / `libmonitorlesson.dylib` / `monitorlesson.dll`; Java `-cp out` locates the bytecode, while `-Djava.library.path=.` locates the native library in the working directory.

### 6.5. Successful Stdout, Verified by an Actual Run

~~~text
afterInside=2
afterOutside=5, notices=1
caught=negative delta
afterRecovery=6, notices=2
RESULT: PASS
~~~

The output confirms the exact **sequence of behaviors in the exercise**:
- The callback inside the JNI lock can reenter the same monitor, increasing the result by 2.
- Update–unlock–notify increments by 3 more and notifies once.
- The failing callback propagated `IllegalArgumentException` back to Java, and another thread could still acquire the monitor afterward.
- The code continued with one more update without leaving the monitor held due to the callback error.

This result **does not prove that every callback in every project is safe**. The program deliberately chose a simple callback, a single state object, and small deltas. Evaluating production code requires also checking the lock graph, wait paths, C mutexes, thread pools, timeouts, exception paths, and shutdown.

## 7. AB–BA Deadlock When Calling Back into Java While Holding a Lock

### 7.1. Sample Scenario: Opposite Acquisition Order of Two Monitors

Suppose a library has two objects `lockA` and `lockB`. A Java callback may enter lock A. On thread T1, JNI code has called `MonitorEnter(lockB)` and then invokes a callback that requires A. Meanwhile, T2 has entered `synchronized(lockA)` and wants `MonitorEnter(lockB)`.

~~~text
Time        Thread T1                                  Thread T2
----------- ------------------------------------------ --------------------------------
t0          JNI MonitorEnter(lockB) succeeds
t1                                                     synchronized(lockA) succeeds
t2          CallVoidMethod(listener.callback())
t3          callback: synchronized(lockA) -- waits T2
t4                                                     JNI MonitorEnter(lockB) -- waits T1
t5          T1 cannot reach MonitorExit(lockB)         T2 cannot exit synchronized(lockA)
            because callback has not finished          because JNI call has not returned
~~~

Wait-for graph representation:

~~~text
T1 --needs--> lockA --owned-by--> T2
 ^                                   |
 |                                   v
 +----owned-by-- lockB <--needs------+
~~~

Deadlock conditions: there are at least two actors, each holds a resource the other needs, **neither can release its lock while waiting**, and they form a **cycle**. This is not an individual `MonitorEnter` bug: both APIs implement mutual exclusion properly, but **the application's callback/lock-order protocol** is wrong.

A Java fragment illustrating T2's side of the logic (not independently runnable):

~~~java
// Thread T2:
synchronized (lockA) {
    nativeAcquireLockB(lockB);  // JNI MonitorEnter(lockB) may wait on T1.
}
~~~

Fragment describing T1's side (illustrates the JNI sequence only):

~~~c
// Thread T1 has valid JNIEnv *env and local/global refs.
if ((*env)->MonitorEnter(env, lockB) != JNI_OK) return;
/* Calls a Java callback that may attempt synchronized(lockA). */
(*env)->CallVoidMethod(env, listener, callbackMethod);
(*env)->MonitorExit(env, lockB);
~~~

**Do not run these two fragments as a live demo without a timeout/kill:** with the right timing, the program can hang. When studying lock ordering, use **timelines and thread dumps** rather than constructing a permanent deadlock and expecting automatic recovery.

### 7.2. Why Doesn't a `synchronized` Callback on the Same Object Save the AB–BA Case?

Reentrancy only applies if **the same thread is already the owner** of **that exact monitor**. In the AB–BA situation:
- T1 owns B, while the callback needs A owned by T2.
- T2 owns A, while the native method needs B owned by T1.

Neither thread has the right to reenter a monitor held by the other thread. No `MonitorExit` operation can run, because both threads are blocked before their cleanup paths.

### 7.3. Why Does Moving the Callback Outside the Lock Reduce Risk?

Approach:

~~~text
Before:
    MonitorEnter(B)
      mutate native/Java state
      CallVoidMethod(Java callback)   <-- arbitrary callback runs under B
    MonitorExit(B)

After:
    MonitorEnter(B)
      mutate state / create snapshot
    MonitorExit(B)
    CallVoidMethod(Java callback)     <-- B has already been released
~~~

With this, T2 can acquire B while T1's callback waits for A; **there is no longer an edge where T1 holds B → waits for A** caused by this critical section itself. If the callback needs to read the updated data, create an **immutable snapshot** inside the locked region and notify using the snapshot after releasing the lock, or design the listener to receive a copied event object. Do not retain a reference to a native buffer that could be freed by another thread while the callback is reading it.

**However:** releasing B before the callback is not enough if the **Java caller** is still holding another lock C outside the native method, or if the callback imposes another lock-order requirement. You must inspect **the entire Java → native → Java path** and lock acquisition order across both languages.

## 8. Locking Policy: One Global Order, Short Critical Sections, No Waiting Under Locks

To design a multi-threaded JNI module, define an application-level **lock hierarchy**, for example:

~~~text
Lock A (session registry) -> Lock B (per-session state)
No path acquires A while already holding B.
~~~

When all code paths (Java synchronized, JNI MonitorEnter, C mutexes) follow a single acquisition order, the chance of forming a cycle via order inversion is greatly reduced. However, **the lock hierarchy must include callbacks**: a library may not control how a user-supplied callback acquires locks. Therefore, it is best **not to invoke arbitrary Java callbacks while holding a JNI monitor or a C mutex**.

Practical principles:
1. **Do not call unknown callbacks inside a lock.** This rule is more important than merely trusting reentrant monitors.
2. **Keep critical sections short.** Pre-resolve method/field IDs outside the lock, check conditions, update state, and release the monitor immediately.
3. **Do not perform I/O, network/blocking operations, `Future.get`, `Thread.join`, condition waits, or synchronous RPC inside a monitor** unless the wait protocol and lock graph have been thoroughly analyzed.
4. **Do not acquire additional locks in reverse order.** If Java holds A and calls native to acquire B, a callback while holding B must not turn around and require A on another thread.
5. **Do not hold a monitor across attach/detach, long-running computation, or native thread creation/join** unnecessarily.
6. **Lock the right object identity**—do not arbitrarily switch to synchronizing on a different object; if using a global ref in an async callback, ensure the ref remains valid and is cleaned up.
7. **Reduce unexpected reentrancy:** a callback can call back into the same JNI entry point, mutating state before the C method finishes. Design clear invariants or defer the callback until after commit+unlock.
8. **Do not swallow exceptions**, and always unlock even on exceptions. A pending exception does not mean the monitor is automatically released; a Java synchronized method releases Java's entry, **not the JNI entry**.
9. **Do not use monitors as a cancellation mechanism.** Java `Thread.interrupt` does not necessarily stop a thread waiting to enter an intrinsic monitor; shutdown/timeouts must be designed externally with diagnostic channels.
10. **Track owners and waiters.** In complex systems, log thread names, monitor/object identity in a controlled way, and enter/exit order—do not log raw native pointers as a measure of JNI ref validity.

If you must invoke a callback inside a locked region for business consistency, you must **lock down the callback contract**: it must only do fast work, never block, never wait on workers, and never reenter APIs that create a reverse lock order. Put those conditions in the public API contract and back them with real concurrency tests.

## 9. JNI Errors and Exceptions: Distinguishing Monitor Leaks from Method/Linker Errors

| Symptom | Layer Where It Occurs | How to Check |
|---|---|---|
| `jni.h: No such file or directory` | C compiler | JDK, `JAVA_HOME/include`, and platform include directory |
| `conflicting types for Java_demo_jni_MonitorLesson_...` | JNI header vs C signature | Regenerate with `javac -h`; use `JNIEnv *, jclass, jobject, jint` |
| `UnsatisfiedLinkError: no monitorlesson in java.library.path` | JVM has not loaded shared library | `libmonitorlesson.so`/`.dylib`/`monitorlesson.dll`, path, architecture |
| `UnsatisfiedLinkError` when calling native method | JVM cannot find exported JNI symbol | Package/method name, generated header, `nm`/`dumpbin`, up-to-date binary |
| Java callback throws exception, subsequent threads hang | JNI `MonitorExit` was skipped | Place cleanup after callback; ensure `MonitorExit` even with pending exception |
| `IllegalMonitorStateException` | `MonitorExit` when thread does not own monitor | Right object, right thread, balanced enter/exit count, do not exit a Java synchronized monitor |
| Works on single thread, hangs on concurrent callbacks | AB–BA, pool wait, or another native mutex | Build lock graph; thread dumps, lock-acquisition and callback timestamps |
| Java `synchronized` method reenters the same object | Normal reentrant monitor | Do not label as deadlock without a cycle/waiter; check other callbacks |
| `-Xcheck:jni` flags an issue | Invalid JNI refs/API usage | Read warnings by function and thread; do not treat as proof of absence of deadlock |
| Thread stuck in `Future.get`/`join` while holding a lock | Indirect deadlock | Which lock does the worker need to finish? Move the wait outside the lock |

You must distinguish **Java exceptions** from **native deadlocks**: an exception may be thrown and caught by Java code, yet the native monitor remains held if C failed to exit. Conversely, a deadlock may have no exception or crash; the JVM process stays alive while the involved threads make no progress.

## 10. Debugging Deadlocks with Thread Dumps and JNI Checks

### 10.1. Gather Evidence Instead of Guessing

When an application stalls during a JNI callback:

1. **Identify the JVM PID** and note the timestamp. If possible, collect **two or three thread dumps a few seconds apart** to see whether threads are transitioning or waiting indefinitely.
2. With a JDK that includes `jcmd`:

~~~sh
jcmd <PID> Thread.print -l
~~~

3. Or use `jstack` on the running JVM:

~~~sh
jstack -l <PID>
~~~

`<PID>` is a placeholder to be replaced with the actual PID; this is not a command to run directly without a PID. On HotSpot, a thread dump typically shows Java stack frames, blocked/waiting states, monitor ownership, and some native frames. Read the **"waiting to lock"** and **"locked"** relationships as well as JNI/callback stack frames. Not **every** custom C mutex, native join, or state inside a native library appears completely in a Java thread dump, so you may also need a native debugger, OS thread dump, logging, and lock ownership records.

4. Record the **chronological sequence of locks** across both Java and C:
   - Which monitor did T1 hold before `CallVoidMethod`?
   - Which monitor did the callback try to lock?
   - What is the thread holding that monitor waiting on, or which JNI method is it calling?
   - Is any thread holding a C mutex and waiting on a Java monitor, or vice versa?
5. Conclude "deadlock" only after constructing the cycle. A single `WAITING` or `BLOCKED` thread is not enough—it could just be normal contention or an intentional `wait()`.

### 10.2. Running Under `-Xcheck:jni` to Find JNI Misuse

~~~sh
java -Xcheck:jni -Djava.library.path=. \
  -cp out demo.jni.MonitorLesson
~~~

HotSpot `-Xcheck:jni` helps detect certain JNI API/handle misuse; **it is not a deadlock detector**. It does not guarantee reporting wrong lock ordering or infinite waiting between two threads. A logic deadlock can occur even when every individual JNI call is valid.

Java Management APIs such as `ThreadMXBean.findDeadlockedThreads()` can help detect cycles involving Java object monitors/ownable synchronizers that the JVM represents; however, they **do not guarantee detecting** all waiting states from C mutexes, thread joins outside the JVM, or native callbacks. Do not use a `null` return from that API as absolute proof that the application is deadlock-free.

### 10.3. Time-Bounded Test: Illustrated in the Program

The following Java snippet is taken from the example's `main`, using another thread to check the monitor after an exception:

~~~java
FutureTask<Integer> probe = new FutureTask<>(state::value);
Thread verifier = new Thread(probe, "monitor-verifier");
verifier.setDaemon(true);
verifier.start();
if (probe.get(5, TimeUnit.SECONDS) != 5) {
    throw new AssertionError("Unexpected state after exception");
}
~~~

If JNI forgot `MonitorExit` when the callback threw, `state.value()` from the other thread could block. `FutureTask.get` with a timeout lets the test fail in a controlled way instead of hanging forever; the verifier thread is marked daemon so it does not keep the JVM alive after `main` throws. The 5-second duration is only a **test threshold**, not a guarantee that the JVM will schedule the thread within that exact window under all loads. A timeout should prompt the learner to **investigate** rather than automatically concluding that JNI is the sole cause.

## 11. Extension: Java Threads, Native Threads, Callbacks, and JavaVM

A JNI native method called from Java receives the `JNIEnv *` of the **current thread**. `MonitorEnter`/`MonitorExit` must execute on the thread that owns the monitor; do not have another thread call `MonitorExit` to "release on its behalf." If a library creates its own POSIX/Windows threads and wants to call Java:
- It must have a valid `JavaVM *`, for example obtained via `GetJavaVM` from a JNI method.
- The native worker calls `GetEnv` to check if it is already attached; if `JNI_EDETACHED`, it must successfully `AttachCurrentThread` before any JNI call.
- Use **the worker's `JNIEnv *`**, not the Java caller's env.
- If a callback uses an object beyond the initial JNI call, hold a valid **global reference** (or weak global + proper promotion) instead of storing a local `jobject`.
- An attached worker must clean up local refs and any monitors it owns, finish callbacks, and then `DetachCurrentThread` according to ownership.
- Do not rely on `DetachCurrentThread` to "clean up" monitors you forgot to exit; release them explicitly and symmetrically before detaching.

Do not invoke a Java callback while holding a C mutex just to "avoid JNI monitors" and assume it is safe. An AB–BA deadlock can still occur between a **native mutex** and a **Java object monitor**. The key is not holding any significant lock across uncontrolled callbacks and using a **system-wide lock graph**.

## 12. Production Design: Safe Callbacks While Preserving Consistency

In a native pipeline that receives input and then calls back into Java, you can split it into three phases:

~~~text
Phase 1: Validate/lookup outside the monitor
    - check refs and method IDs
    - prepare valid input data/copies

Phase 2: SHORT critical section
    - MonitorEnter(state)
    - update state / sequence number
    - create immutable snapshot or event payload
    - MonitorExit(state) on every exit path

Phase 3: Notify AFTER UNLOCK
    - check pending exception
    - CallVoidMethod(listener, event)
    - handle exception/cancellation per contract
~~~

If a Java callback can call back into the native API (**reentrancy**) or swap the listener right inside the callback, clearly define:
- Has state been **committed** before the callback?
- Is the callback allowed to call `register/unregister/close` concurrently?
- Does the callback run on the same thread or get dispatched to an executor thread? Does waiting for the callback to finish hold any lock?
- Are the listener/native context still alive when the callback runs? Object refs need clear global/local ownership.
- When the Java callback throws an exception, does native code have any unreleased resources?
- Is there a risk of callback A invoking callback B and inverting the lock order?
- If the callback runs outside the lock, could other threads mutate state before the listener reads it? If an exact snapshot is needed, the callback must receive **the captured snapshot** rather than relying on unsynchronized live mutable state.

A common approach is to **queue events and dispatch outside the lock**. However, a queue also has its own lock/condition and capacity; do not block pushing onto the queue while still holding a JNI monitor if the consumer needs that monitor to drain the queue.

### When You Still Need a JNI Monitor

Use `MonitorEnter/MonitorExit` when you need to interact directly with a Java object's intrinsic monitor that Java code is also using. If you do not need to participate in the same Java monitor, a Java-level `synchronized` wrapper or `java.util.concurrent.locks.ReentrantLock` can express ownership more cleanly; private C state can use a separate C mutex. Choose one clear strategy and avoid "stacking" Java and C locks without an overall ordering.

## 13. Common Coding Mistakes and Fixes

**Mistake 1 — forgetting to exit when the callback throws:**

~~~c
/* Wrong: exceptional path returns without releasing. */
if ((*env)->MonitorEnter(env, state) != JNI_OK) return;
(*env)->CallVoidMethod(env, state, callback);
if ((*env)->ExceptionCheck(env)) return; /* JNI monitor remains held. */
(*env)->MonitorExit(env, state);
~~~

Fix by calling `MonitorExit` **before** the `ExceptionCheck` branch, as in the main example. If multiple resources must be cleaned up, use a single `cleanup` label and explicit state.

**Mistake 2 — thinking a Java synchronized return compensates for a JNI enter:**

~~~c
/* Ownership error: returning from a Java synchronized callback does not
   release the entry created by JNI MonitorEnter. */
(*env)->MonitorEnter(env, state);
(*env)->CallVoidMethod(env, state, callback);
/* missing MonitorExit */
~~~

A Java synchronized callback only releases **Java's own entry**; the JNI entry is still held by C.

**Mistake 3 — using the wrong object on exit:**

~~~c
/* Wrong: Java object A differs from object B. */
(*env)->MonitorEnter(env, lockA);
(*env)->MonitorExit(env, lockB);
~~~

This can throw `IllegalMonitorStateException` or break invariants. Practice: store the handle of the locked object clearly, call `MonitorExit` on the exact same handle/identity, and ensure ref lifetime.

**Mistake 4 — unlocking on the wrong thread:**

~~~text
T1: JNI MonitorEnter(lock)
T2: JNI MonitorExit(lock)  <-- T2 is not the owner
~~~

Object monitors do not transfer ownership across threads. Do not "offload" unlocking to a worker just to return a result asynchronously.

**Mistake 5 — callback inside lock calls Future.get:**

~~~text
JNI thread T1 holds monitor M
Java callback on T1 waits for Future F
worker completing F needs monitor M
=> cycle
~~~

Fix by updating/snapshotting and unlocking before the callback, or designing the worker so it does not need M to complete. Simply adding a timeout may help **detect** the issue but does not solve the lock-order problem itself.

**Mistake 6 — believing `JNI_OK` means the callback will not block:**

`JNI_OK` from `MonitorEnter` only proves **acquisition succeeded**; it says nothing about the behavior of subsequent callbacks. A callback may reenter, block, throw an exception, or call a new API the application did not anticipate.

## 14. Pre-Merge Checklist for a JNI Callback Implementation

- [ ] Identify the exact Java object used as the monitor; never pass NULL/invalid `jobject`.
- [ ] `JNIEnv *` belongs to the current thread; never share env cross-thread.
- [ ] `MonitorEnter` succeeds before accessing the protected region; every JNI enter is balanced by a **JNI MonitorExit** on the same thread.
- [ ] Do not confuse Java `synchronized` entries with JNI entries in lock counting and cleanup.
- [ ] A single cleanup path exists on **normal return, exception, early error, cancellation, and shutdown**.
- [ ] `MonitorExit` still executes if `CallVoidMethod` leaves a pending exception.
- [ ] Do not make disallowed JNI calls while a pending exception is active.
- [ ] Determine whether the callback reenters a Java synchronized method on the same object/thread or must acquire other locks.
- [ ] Map the lock graph across Java + JNI + C mutexes; ensure no A–B–A cycle or wait-on-worker while holding a lock.
- [ ] Prefer notifying/calling back after unlocking; if impossible, make the callback contract explicit, non-blocking, and concurrency-tested.
- [ ] All local/global JNI references used in the callback have valid lifetimes; never store a local ref beyond its JNI frame.
- [ ] Have tests for the exception path and another thread entering the monitor after the exception; tests have timeouts so they do not hang forever.
- [ ] Include `javac -h` commands, OS/arch-appropriate native build, `-Xcheck:jni`, and thread-dump tools for debugging.
- [ ] Do not treat a single PASS run or an empty deadlock report as proof that all interleavings are safe.

## 15. Review Questions (with Answers)

**Q1.** JNI calls `MonitorEnter(state)` and then `CallVoidMethod(state.add)`, where `add` is declared `synchronized` on `state` itself. Is a deadlock guaranteed?  
**Answer:** No. If the callback executes on the same thread, that is a **reentrant monitor**. A deadlock can happen if the callback must wait on another thread/lock, not merely from reentering the same monitor.

**Q2.** Thread T1 holds monitor B via JNI and calls a Java callback needing A; thread T2 holds A and calls JNI to acquire B. Why can neither thread make progress?  
**Answer:** T1 is waiting for A held by T2; T2 is waiting for B held by T1. The two wait conditions form an AB–BA cycle. Releasing B before the callback or standardizing lock order across all call paths is the appropriate design fix.

**Q3.** `CallVoidMethod` throws a Java exception while JNI is holding `MonitorEnter`. Is it allowed to call `MonitorExit` before returning?  
**Answer:** Yes, and you **must** clean up this entry. `MonitorExit` is among the JNI operations permitted when an exception is pending. Then return so Java receives the exception; do not swallow it.

**Q4.** Does returning from a Java synchronized method automatically release a lock just acquired by JNI `MonitorEnter` beforehand?  
**Answer:** No. Java and JNI share the same monitor, but each entry's ownership must be exited by its matching mechanism: JNI enter ↔ JNI exit.

**Q5.** Can Java thread T2 call `MonitorExit` on behalf of a monitor entered by T1?  
**Answer:** No. `MonitorExit` requires the **current thread** to be the owner; the wrong owner may throw `IllegalMonitorStateException`.

**Q6.** If callbacks are invoked after `MonitorExit`, is production code guaranteed to never deadlock?  
**Answer:** Not yet. The caller may still hold other Java/C locks; the callback may acquire locks in reverse order or wait on a worker. You must evaluate the entire lock graph and wait dependencies.

**Q7.** Why does `FutureTask.get(5, TimeUnit.SECONDS)` appear in the demo after the callback throws an exception?  
**Answer:** To verify from **another thread** that the monitor is not still held by JNI after the exception, with a deadline to avoid hanging indefinitely. A PASS result helps validate the example's cleanup path, not replace stress tests.

## 16. Summary and Authoritative Sources

**`MonitorEnter` and `MonitorExit` let C/C++ participate in a Java object's monitor.** It is a reentrant lock, so a synchronized callback on the same object/same thread can be safe with respect to acquisition; **however, a callback can pull in additional locks, wait on workers, or create AB–BA**, so avoid calling arbitrary Java code while holding a JNI monitor. If you must acquire one, always **exit via JNI on every branch**, even when a callback leaves a pending Java exception. Prefer *mutate under lock → MonitorExit → notify/callback* with an appropriate snapshot/contract, and inspect with thread dumps when needed.

Official specifications for reference:
- [Oracle Java SE 21 JNI Functions – Monitor Operations](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#monitor-operations).
- [Oracle Java SE 21 JNI Design Overview – Threads and Java Exceptions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [Oracle Java SE 21 JNI Invocation API](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html).
- [Java SE 21 ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

The build paths and stdout in this lesson apply to the two sample files shown; when moving to a real application, you must have tests tailored to that application's own lock order and lifecycle.