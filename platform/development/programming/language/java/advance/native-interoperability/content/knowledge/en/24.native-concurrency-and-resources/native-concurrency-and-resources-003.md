# Synchronizing Data Read or Written by Both Java and Native Code

**Context:** Java Advance → native-interoperability → Concurrency and Resources.

When a Java application calls C/C++ via JNI, or shares a memory region with a native library via a direct buffer/Foreign Function & Memory API, both sides can observe and modify the same state. Being able to call a native function **does not automatically create a protection mechanism** for all other concurrent accesses taking place. For the data to be correct, you must determine who owns the memory region, who is allowed to read/write, which operations must be atomic, how changes are published, and when the memory region is freed.

After this lesson, you will be able to choose a synchronization mechanism suitable for each data type; use the same Java monitor from Java and JNI; distinguish thread safety from lifetime safety; and identify cases where Java and C/C++ appear to be “locked” but races actually still occur.

## 1. Accurately Identifying the Shared Data

| State | Java-side access | Native-side access | Important constraint |
| --- | --- | --- | --- |
| Java object field | Regular field/method, synchronized, Atomic* | JNI Get/Set field or calling a Java method | Both must follow the same synchronization convention on the Java object. |
| Java array | Array element access | JNI Get/Release array elements, Get/Set array region, critical access | A JNI pointer may point to a copy or a pinned region; it must not be treated as a live address indefinitely. |
| DirectByteBuffer | Java NIO byte reads/writes | JNI GetDirectBufferAddress or native holding memory wrapped by the buffer | Must agree on memory lifetime, byte order, alignment, field width, and synchronization method. |
| Native memory managed by FFM (JDK 22+) | MemorySegment, layout, VarHandle | C/C++ pointer pointing to a valid memory region | Scope/Arena controls access scope and lifetime, **and does not automatically make every read/write atomic**. |
| Native resource handle | Java holds an identifier/wrapper object | Native uses file/socket/struct/handle | Requires resource-closing rules and prevention of use-after-close. |

Before writing a lock, ask four questions:

1. **Same memory location or two copies?** JNI may create a copy when retrieving array elements; writing to a copy does not mean Java sees the change immediately.
2. **Who has write permission?** A single writer with multiple readers is usually easier to control than multiple concurrent writers.
3. **What is the valid operation?** Just reading a number, incrementing a counter, or updating multiple fields into a consistent state?
4. **When does the work end?** Access permissions must be revoked before freeing the memory or handle.

## 2. Four Conditions of a Correct Synchronization Protocol

**Mutual exclusion.** For a read–modify–write operation, such as incrementing a counter, two threads must not both read the old value and overwrite each other's result. You can use the same Java monitor, a Java service that performs atomic updates, or a native mechanism designed specifically for native memory.

**Visibility.** One thread finishing a write does not mean another thread immediately sees the new value if a synchronization relationship is missing. According to the Java Memory Model, an unlock operation on a monitor **happens-before** a subsequent lock operation on that same monitor. Thread.start and a thread completing before another thread successfully joins it also establish the necessary happens-before relationships.

**Ordering and atomicity.** A single write may be visible, yet the sequence “read state → check → update” is still not atomic. Java volatile is useful for publication/read rules of a Java variable, but the increment expression **value++** still consists of multiple steps. The C/C++ volatile keyword is not equivalent to Java volatile, nor does it replace C11/C++ atomics.

**Lifetime.** Proper locking cannot save a pointer to freed memory, an invalidated JNI reference, or a buffer released while native code is still operating on it. Lifetime and synchronization must be **a single shared contract**, including error paths, task cancellation, and shutdown.

In particular, the Java Memory Model describes Java's synchronization behavior. Do not assume that a **std::mutex** in C++ automatically corresponds to a Java **synchronized**, or that Java VarHandle and C11 atomic automatically have compatibility guarantees across all JVMs/ABIs. If direct concurrent off-heap access from both languages is required, you must explicitly establish the memory protocol, alignment, data types, operation ordering, platform support, and compatibility testing. A lower-risk approach is to route all updates through **one side responsible for synchronization**.

## 3. Choosing a Strategy by State Type

### 3.1. Java holds the state: the same Java monitor via JNI

If the data is a field of a Java object, Java can use **synchronized(lock)** and native code can use JNI's **MonitorEnter/MonitorExit** on **that exact lock object**. You must not synchronize Java on one object while C only locks a separate mutex and assume the two locks protect the same state.

Field accesses via JNI must be inside the corresponding critical section. Every path leaving a region where MonitorEnter succeeded must call MonitorExit, even when JNI raises an exception. MonitorExit must not be used to “exit on behalf of” a monitor that Java entered using the synchronized keyword; and returning from a Java synchronized method does not automatically exit a monitor entered via JNI MonitorEnter.

Another option is for native code to **call a properly synchronized Java method** (for example, a method using AtomicInteger.incrementAndGet) via JNI, instead of reading/writing the field directly. Call overhead may be higher, but the contract is more consistent and easier to maintain.

### 3.2. Native holds the state: encapsulating operations or exchanging snapshots

If multiple C/C++ threads own a native structure, let the native library manage the mutex/atomic and provide Java with operations that have complete semantics such as “get consistent snapshot”, “add an amount”, or “set configuration”. Java should not directly modify bytes of the structure while native code holds a mutex that Java does not participate in.

For large data, the **snapshot → process → publish result** pattern reduces lock-holding time: copy the state under the lock, process on the copy, then check the version or replace the state under the lock. Do not read multiple independent fields and treat them as a consistent snapshot if a writer can update them in between.

### 3.3. Truly shared off-heap memory

Choose one of the clear designs: a single writer with a verified publication mechanism; lock/callback through a bridge layer; or an atomic protocol confirmed compatible on both the specific JVM and native ABI. You must specify **address + size + alignment + byte order + who frees + termination condition**.

Shared memory, DirectByteBuffer, or Arena.ofShared allow memory access from multiple sides/threads, but do not provide by default that “every read/write is race-free”. Plain ByteBuffer.getInt/putInt should not be treated as a substitute for an atomic protocol for a structure shared between C and Java.

## 4. Runnable Example on Java 17+: Java and JNI Incrementing a Shared Counter

The example intentionally keeps the state on the **Java heap**. Two Java threads run concurrently: one increments in Java code, the other calls C code via JNI. Both use the **same monitor lock**. Each thread increments 100,000 times; the final value must be 200,000.

**File SharedCounterDemo.java**

~~~java
public final class SharedCounterDemo {
    static {
        System.loadLibrary("sharedcounter");
    }

    private final Object lock = new Object();
    private int value;

    private native void incrementNative(int times);

    private void incrementJava(int times) {
        for (int i = 0; i < times; i++) {
            synchronized (lock) {
                value++;
            }
        }
    }

    private int currentValue() {
        synchronized (lock) {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        final int times = 100_000;
        SharedCounterDemo counter = new SharedCounterDemo();

        Thread javaThread = new Thread(
                () -> counter.incrementJava(times), "java-writer");
        Thread nativeThread = new Thread(
                () -> counter.incrementNative(times), "jni-writer");

        javaThread.start();
        nativeThread.start();
        javaThread.join();
        nativeThread.join();

        System.out.println(counter.currentValue());
    }
}
~~~

**File sharedcounter.c**

~~~c
#include <jni.h>

JNIEXPORT void JNICALL
Java_SharedCounterDemo_incrementNative(
        JNIEnv *env, jobject self, jint times) {
    jclass cls = (*env)->GetObjectClass(env, self);
    if (cls == NULL) {
        return;  /* There may be a pending exception. */
    }

    jfieldID lockField = (*env)->GetFieldID(
            env, cls, "lock", "Ljava/lang/Object;");
    if (lockField == NULL) {
        (*env)->DeleteLocalRef(env, cls);
        return;
    }

    jfieldID valueField = (*env)->GetFieldID(
            env, cls, "value", "I");
    if (valueField == NULL) {
        (*env)->DeleteLocalRef(env, cls);
        return;
    }

    jobject lock = (*env)->GetObjectField(env, self, lockField);
    if (lock == NULL) {
        (*env)->DeleteLocalRef(env, cls);
        return;
    }

    for (jint i = 0; i < times; ++i) {
        if ((*env)->MonitorEnter(env, lock) != JNI_OK) {
            break;
        }

        jint previous = (*env)->GetIntField(
                env, self, valueField);
        if (!(*env)->ExceptionCheck(env)) {
            (*env)->SetIntField(env, self, valueField, previous + 1);
        }

        /* Entered the monitor via JNI, so must exit via JNI. */
        jint exitStatus = (*env)->MonitorExit(env, lock);
        if (exitStatus != JNI_OK || (*env)->ExceptionCheck(env)) {
            break;
        }
    }

    (*env)->DeleteLocalRef(env, lock);
    (*env)->DeleteLocalRef(env, cls);
}
~~~

The C-side JNI signature corresponds to the native method **incrementNative(int)** of a class with no package and no overloads. In real applications, use the header generated by **javac -h** to cross-check the signature rather than guessing the function name.

**Compile and run on Linux with JDK 17+ and GCC** (JAVA_HOME points to the JDK directory):

~~~bash
javac -h . SharedCounterDemo.java
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libsharedcounter.so sharedcounter.c
java -Djava.library.path=. SharedCounterDemo
~~~

**stdout when compiling/loading the library succeeds:**

~~~text
200000
~~~

On macOS, JNI headers use the **include/darwin** directory and the dynamic library uses the **.dylib** suffix; on Windows, headers use **include/win32** and the library uses **.dll**. The native library build command depends on the compiler/platform, while the Java/C code and monitor contract remain unchanged.

### Why is this example correct?

1. Both Java and C retrieve the **lock** object from the exact same **counter** instance. JNI MonitorEnter contends for ownership of **the exact same monitor** that synchronized(lock) uses.
2. The **read value → add 1 → write value** operation is entirely inside the critical section, so no updates are lost due to interleaving between the two writers.
3. MonitorExit executes after every successful MonitorEnter, even if a field operation leaves a pending exception. C does not forget to release the lock on the normal path.
4. Java calls **join()** on both threads before reading the result; the final read is also inside synchronized(lock). It does not rely on sleep or thread scheduling.
5. The **value** field does not need volatile because **all** accesses in the example follow the same monitor convention. If any lockless reader/writer is added, this reasoning no longer holds.

**Counterexample:** Removing synchronized in Java or removing MonitorEnter/MonitorExit in C breaks the shared contract. The result *may* be less than 200,000 or coincidentally still equal 200,000; one “correct” run does not prove the code is race-free. You also must not change the Java-side lock to **synchronized(this)** while the C side still locks the **lock** field: those are two different monitors.

The C code here illustrates a JNI thread already invoked by the JVM from Java. It does not create its own pthread and does not work directly with pointers into the Java heap. Error paths when looking up class/field may leave a JNI exception for the JVM to handle; in production code, you need a clearly designed error-propagation and monitoring policy instead of silently treating the operation as having succeeded.

## 5. Java Arrays, Copies, and Critical Regions

**GetIntArrayElements / ReleaseIntArrayElements** may return a pointer to the actual array region or a copy. If native code modifies elements, only after a Release operation with the appropriate mode can you rely on the copy having been written back. Do not retain the pointer for a native thread to use asynchronously after Release. If you only need to read/write a small region, the **GetIntArrayRegion / SetIntArrayRegion** APIs usually provide a clearer copy contract.

**GetPrimitiveArrayCritical / ReleasePrimitiveArrayCritical** have stricter constraints: keep the critical section very short; during this interval, do not make other JNI calls or syscalls that may block waiting for a Java thread, and do not lock and wait for I/O or callbacks. The VM may restrict heap movement/GC during that time and may still provide a copy. “Critical” in the API name **is not** a lock protecting concurrent Java threads modifying the same array.

For both API groups, you must distinguish **pointer lifetime**, **copy-back timing**, and **synchronization between threads**; these three conditions cannot substitute for one another. If there are multiple writers, prefer short operations with consistent locking/copying or hand off the work to a single owner.

## 6. DirectByteBuffer and FFM: Being Accessible Does Not Mean Concurrency-Safe

**DirectByteBuffer**: Java can allocate a buffer with ByteBuffer.allocateDirect; JNI can obtain the address via GetDirectBufferAddress (check for NULL result and capacity). If native code allocates memory and uses NewDirectByteBuffer to wrap that address, native code must ensure the memory remains valid until Java stops accessing it. Freeing native memory must not rely on the Java side “probably being done with it”. In particular, **NewDirectByteBuffer** initially has big-endian byte order per the JNI specification; choose the byte order explicitly before interpreting multi-byte structs.

With the **official FFM API since JDK 22** (package java.lang.foreign), MemorySegment carries bounds and scope; Arena determines the lifetime of the memory region. **Arena.ofConfined()** allows only the owner thread to access the corresponding segment; **Arena.ofShared()** allows multiple threads to access it, but **does not automatically lock update operations**. Close the Arena only after all native tasks/callbacks are no longer using the allocated address; a native pointer retained separately can escape Java-side lifetime checks.

The following example only illustrates **allocation and lifetime bounds**, without performing concurrent access; requires JDK 22+:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentLifetimeDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment segment = arena.allocate(
                    ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println(
                    segment.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

~~~text
42
~~~

In the FFM example, the **shared** label describes thread access permission, not a guarantee that **get then set** is an atomic increment. When building a shared protocol with C/C++, you must agree on numeric types, byte order, alignment, liveness, publication rules, and an atomic/lock mechanism actually guaranteed on the supported stack. Do not arbitrarily combine **C volatile**, Java plain get/set, and hope caches stay consistent on their own.

## 7. Native-Created Threads, Callbacks, and Lock Ordering

In the JNI example, C runs on the thread that called the native method, so it receives a **JNIEnv*** valid for that thread. If a library creates its own C/C++ thread and wants to call back into the JVM, that thread must attach using **JavaVM.AttachCurrentThread** (if not already attached), obtain its own JNIEnv*, and then detach at an appropriate point. **Do not share JNIEnv*** across native threads.

Local JNI references are only valid within a specific scope of a thread/native call. If native code stores a Java object for callbacks after the call returns, you must consider **NewGlobalRef** and release it with **DeleteGlobalRef** when you are sure it is no longer used. A global reference does not automatically make the data inside the object concurrency-safe.

Avoid holding a Java monitor when calling a native operation that may block for a long time, or holding a native mutex when calling an uncontrolled Java callback. If the workflow must use both locks, establish a **consistent lock acquisition order** across all paths. For example: thread A holds a Java monitor then waits for a native mutex, while thread B holds the native mutex then calls a Java callback that needs the same monitor → deadlock. Do not use busy-wait/sleep to “fix” lock-ordering issues.

At shutdown, a safe sequence is typically: stop accepting new work → signal stop → wait for all tasks using the resource to finish → revoke callbacks/global refs → free native memory/close handle. Do not free first and wait for threads to stop afterward.

## 8. Designing the Shared Contract Before Writing Code

A contract should explicitly state:

| Component | Example decision needed |
| --- | --- |
| Owner | Java owns the counter on the heap; native only accesses via JNI under the monitor. |
| Writer/readers | Java worker and JNI worker both write; all readers also use the same monitor. |
| Atomic region | The entire read–add–write operation, not just an individual read or write. |
| Publication mechanism | MonitorExit before the next MonitorEnter on the same object; join before summarizing. |
| Lifetime | Instance stays alive across both threads; do not store JNI local refs across calls. |
| Error/cancellation | Ensure unlock on all branches; define how native exceptions/status are surfaced to Java. |
| ABI if off-heap | Field sizes, alignment, byte order, struct version, free ownership, and free timing. |

If only one side needs to mutate state, consider using **message passing**: the Java side sends requests through a synchronized worker/queue, and native processes them and returns results/snapshots. Reducing shared writable memory is usually easier to prove correct than an off-heap structure that allows both languages to mutate arbitrarily.

## 9. Common Bugs and How to Detect Them

| Symptom or bug | Cause | How to fix |
| --- | --- | --- |
| Counter lower than expected, intermittently wrong | Two writers read–modify–write concurrently without a shared lock | Use the same JNI/Java monitor or an atomic update API at the owner. |
| Reader sees stale or half-updated state | No publication/visibility relationship, reading multiple fields outside a lock | Use the same acquire/release mechanism or take a snapshot under a lock. |
| Java synchronized, C std::mutex, yet still wrong | Two locks belong to two independent domains | Route updates through a single synchronization bridge or a proven off-heap protocol. |
| Crash in JNI/FFM, random data corruption | Expired pointer, freed buffer, wrong bounds/alignment/ABI | Design ownership, check size/offset, wait for tasks before freeing. |
| Array changes do not appear immediately on the Java side | JNI provided a copy or Release has not been called properly | Distinguish copy-back from synchronization; Release according to the API contract. |
| Program hangs/unusually long GC pauses | Holding critical array too long, waiting on I/O while pinned, lock inversion | Shorten critical section, remove blocking/callbacks, standardize lock ordering. |
| Native thread calling JNI fails unpredictably | Using another thread's JNIEnv*, wrong reference lifetime | Attach the thread itself, use global refs when needed, detach/cleanup at the right time. |
| Tests pass but production still races | Tests only run under one scheduling and one platform | Stress-test repeatedly, verify on real configurations and ABIs, test error/shutdown paths. |

### Deliberate Testing

- Run the example with **-Xcheck:jni** to catch more JNI violations, then repeat the test with a larger number of operations. Check both the final value and the absence of exceptions/native crashes.
- Stress multiple reader/writer threads, forcing interleaving with barriers/latches **in tests**, instead of concluding from a single run or using sleep as a synchronization mechanism.
- Test during task cancellation, JNI exceptions, shutdown, and active native callbacks. Watch for deadlocks and use-after-free bugs.
- For C/C++, use memory/race-checking tools appropriate for the native code and platform, keeping in mind that they do not automatically prove the entire Java Memory Model and JVM interaction are correct.
- For off-heap, test across all architectures/compilers/JVMs that the product actually supports; test mismatched alignment/endianness/version to ensure input validation does not miss anything.

## 10. Self-Check Questions

1. If Java uses synchronized(lock) while C only locks a pthread mutex before SetIntField, why can updates still be lost?
2. Why can't a shared **value++** operation be solved by independently adding Java volatile or C volatile?
3. If native code saves the GetDirectBufferAddress address to write to after the native method returns, how will you prove the buffer and backing memory remain alive?
4. When a native callback holds a native mutex and needs to enter a Java synchronized block, while a Java thread holds the monitor and waits for the native mutex, how does a deadlock form?
5. Why is Arena.ofShared different from a data synchronization mechanism, and when should you design a single owner/queue/snapshot instead of shared writable memory?

**Technical takeaway:** Only consider Java/native data “synchronized” when all conflicting reads/writes follow a single contract for atomicity, visibility, ordering, **and** lifetime. Start with ownership boundaries and a single synchronization point; only choose a more complex off-heap protocol when genuinely needed and verifiable on supported platforms.

## Authoritative References

- [Java Language Specification §17 — Threads and Locks (Java 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): monitors, happens-before, and data races.
- [JNI Functions (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): MonitorEnter/MonitorExit, array critical APIs, JNI references, and direct buffers.
- [Foreign Function and Memory API (Java 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): MemorySegment, Arena, memory bounds, and native interop.
