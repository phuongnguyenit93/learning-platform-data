# Global State, Thread-Local Variables, and Reentrancy of C Functions Called from Java

## 1. Why Is This a Java Native Interoperability Problem?

When Java calls C code via JNI (Java Native Interface) or the Foreign Function & Memory API (FFM), the call may enter a native library used concurrently by multiple threads. The JVM manages Java threads and objects, but **does not automatically make global variables, static buffers, or C functions thread-safe**.

Three questions need to be separated:

1. **Where is the state stored?** One value shared across the library/process, one separate value per OS thread, or a fresh value for each invocation?
2. **What happens when multiple threads access it concurrently?** Is there a data race, lost update, inconsistent state read, or violation of memory lifetime rules?
3. **What happens when the same function is called nestedly before the previous call completes?** This is a question of *reentrancy*, which is different from thread safety.

Example of a nested call chain:

```text
Java thread T
  -> JNI C function f()
       -> f() calls Java callback
            -> callback calls JNI C function f() again
                 -> 2nd invocation of f() runs before 1st invocation of f() finishes
```

This case can happen **on the same thread**, even when the program does not create a second thread.

## 2. Three Places to Store State in C

### 2.1. Global variables and `static` variables: shared state

```c
/* Partial C illustration, not a standalone program. */
static int request_count = 0;

int next_count(void) {
    return ++request_count;
}
```

`request_count` has *static storage duration*: it is initialized once and exists for as long as the library/program instance containing it remains loaded. `static` at file scope restricts name linkage (*internal linkage*), **it does not create a copy per thread**. A global variable without `static` is still shared state, differing only in name linkage/visibility according to C rules and the linker.

Two C threads concurrently executing `++request_count` without synchronization will have conflicting accesses to a non-atomic object. Under the C memory model, that is a **data race leading to undefined behavior**; one cannot simply predict that it will only "occasionally lose an increment". `volatile` in C does not fix a data race.

Switch to atomics when only an independent counter is needed:

```c
#include <stdatomic.h>

static atomic_int request_count = ATOMIC_VAR_INIT(0);

int next_count(void) {
    return atomic_fetch_add_explicit(
        &request_count, 1, memory_order_relaxed
    ) + 1;
}
```

`memory_order_relaxed` is sufficient so that each counter increment is atomic and no updates are lost; it **does not** establish a publish/observe relationship for other data. If the state consists of multiple fields that must be consistent together, an appropriate synchronization mechanism must be designed, such as a mutex or an atomic protocol with proper memory ordering. A `static const` variable itself is only safe when the data is truly immutable and properly initialized/published.

**Sharing scope:** how the native library is loaded, library copies, and class loaders can affect whether the same native instance is shared. Do not assume each Java object will automatically get its own copy of a C `static` variable.

### 2.2. Automatic local variables: normally per-call

```c
int sum_1_to_n(int n) {
    int sum = 0;                 /* Each call has its own sum variable. */
    for (int i = 1; i <= n; ++i) {
        sum += i;
    }
    return sum;
}
```

Here `sum` is an automatic variable for each call, even when the function is called nestedly or recursively. However, this is only an example for small inputs to avoid `int` overflow: **local variables do not automatically make the entire function safe** if the function also accesses shared objects via pointers, calls unsafe APIs, or returns a pointer to memory whose lifetime has expired.

A pointer parameter can lead to shared memory even though the parameter itself resides on the stack of each call.

### 2.3. Thread-local storage (TLS): per OS thread

C11 has `_Thread_local`:

```c
static _Thread_local int calls_on_this_thread = 0;

int next_on_thread(void) {
    return ++calls_on_this_thread;
}
```

Each **OS thread** receives a separate `calls_on_this_thread` object, initially initialized to `0`. Calls on the same thread reuse that object; returning from a function does not clear TLS.

Equivalent or near-equivalent mechanisms may be encountered depending on the platform: `thread_local` in C++11, `pthread_key_create`/`pthread_getspecific` on POSIX, TLS/FLS on Windows. Initialization, destruction, destructor mechanisms, and compiler support differ; do not treat them as completely interchangeable at the source-code level.

TLS solves **OS threads stepping on the same variable**, but does not create new state per call, HTTP request, or task in a thread pool. For example, tasks A and B running sequentially on the same worker thread will both see that worker's TLS. With Java virtual threads, C TLS must also not be treated as per-virtual-thread state: native TLS is bound to the OS thread actually executing the C code.

## 3. How Are Thread-Safe and Reentrant Different?

- **Thread-safe:** multiple threads calling concurrently still satisfy the function's contract, provided inputs/memory lifetimes are valid.
- **Reentrant:** a new call can start before the previous call to the same function finishes, even on **the same thread**, without corrupting state or getting stuck.
- **Recursion:** a form of re-invocation in the call graph; a function might not be directly recursive yet still be reentered via a callback, signal handler, or another call path. Regular *reentrant* **is not synonymous** with *async-signal-safe*: signal handlers have even stricter rules.

| Implementation approach | Concurrent calls across multiple threads | Nested calls on the same thread |
| --- | --- | --- |
| Unsynchronized mutable `static int` | Has data race, unsafe | May overwrite state |
| Shared variable locked with a normal mutex | Can be safe if all accesses follow the same lock | May deadlock if lock is held and then reentered |
| `_Thread_local` variable | Separates object between OS threads | Still shares the same object when reentered on the same OS thread |
| Purely per-call local data | Usually safe if dependencies are also safe | Usually reentrant if not depending on shared state |
| Atomic operation on a single variable | Safe for the atomized operation | Reentrancy of the *entire function* still depends on other steps |

**Counterexample with TLS:** a function returning a pointer to a TLS buffer can still corrupt the result of an in-progress call:

```c
/* C illustration snippet; requires #include <stdio.h>. */
static _Thread_local char scratch[32];

const char *number_text(int n) {
    snprintf(scratch, sizeof scratch, "%d", n);
    return scratch;
}

/* Same OS thread: */
const char *first = number_text(10);
const char *second = number_text(20);
printf("%s | %s\n", first, second);  /* 20 | 20 */
```

`first` and `second` both point to the same buffer. If a callback reenters `number_text()` while the first caller still needs the old content, the content is overwritten. TLS prevents *other threads* from writing to the same buffer, but does not prevent *a subsequent call on the same thread* from overwriting it.

A better design is to let each call have its own caller-owned buffer:

```c
#include <stdio.h>
#include <stddef.h>

/* Return -1 if not fully written; do not retain pointer dst after returning. */
int number_text_into(char *dst, size_t capacity, int n) {
    if (dst == NULL || capacity == 0) {
        return -1;
    }
    int required = snprintf(dst, capacity, "%d", n);
    if (required < 0 || (size_t)required >= capacity) {
        return -1;
    }
    return 0;
}
```

This function does not hold state in a shared buffer. The caller must provide buffers that are large enough, still alive, and not subject to unauthorized concurrent write access. If two calls pass the same `dst`, safety again depends on the caller.

## 4. Practical Example: Java 17 + JNI + C11

The example below intentionally illustrates all three forms: **an atomic global counter**, **an OS-thread TLS counter**, and **a computation function using per-call variables**. All code in this section can run on Linux with JDK 17+ and a C compiler supporting C11.

### 4.1. File `NativeState.java`

```java
public final class NativeState {
    static {
        System.loadLibrary("native_state");
    }

    private static native int nextGlobal();
    private static native int nextOnThread();
    private static native int sum1ToN(int n);

    public static void main(String[] args) throws InterruptedException {
        System.out.println("global 1 = " + nextGlobal());
        System.out.println("global 2 = " + nextGlobal());

        System.out.println("main TLS 1 = " + nextOnThread());
        System.out.println("main TLS 2 = " + nextOnThread());

        Thread worker = new Thread(() -> {
            System.out.println("worker TLS 1 = " + nextOnThread());
            System.out.println("worker TLS 2 = " + nextOnThread());
        }, "demo-worker");

        worker.start();
        worker.join();

        System.out.println("main TLS 3 = " + nextOnThread());
        System.out.println("sum1ToN(5) = " + sum1ToN(5));
    }
}
```

`NativeState` is placed in the default package to simplify the example. In a packaged project, use the actual package name and **let `javac -h` generate the JNI header** instead of guessing mangled symbol names manually.

### 4.2. File `native_state.c`

```c
#include "NativeState.h"
#include <stdatomic.h>

/* A shared object within this library instance. */
static atomic_int global_hits = ATOMIC_VAR_INIT(0);

/* A separate object for each OS thread. */
static _Thread_local int tls_hits = 0;

JNIEXPORT jint JNICALL
Java_NativeState_nextGlobal(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;

    return (jint)(atomic_fetch_add_explicit(
        &global_hits, 1, memory_order_relaxed
    ) + 1);
}

JNIEXPORT jint JNICALL
Java_NativeState_nextOnThread(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;

    return (jint)(++tls_hits);
}

JNIEXPORT jint JNICALL
Java_NativeState_sum1ToN(JNIEnv *env, jclass cls, jint n) {
    (void)cls;

    /* Limit input so the sum does not overflow jint (at least 32 bits). */
    if (n < 0 || n > 1000) {
        jclass error_class = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException"
        );
        if (error_class != NULL) {
            (*env)->ThrowNew(
                env, error_class, "n must be between 0 and 1000"
            );
        }
        return 0;  /* Java sees the pending exception if ThrowNew succeeds. */
    }

    jint sum = 0;
    for (jint i = 1; i <= n; ++i) {
        sum += i;
    }
    return sum;
}
```

Meaning of each value:

- `global_hits` is visible to every OS thread passing through the same library instance; `atomic_fetch_add_explicit` makes each increment atomic.
- `tls_hits` increments starting from `1` on each new OS thread; it **does not reset after each JNI call**.
- `sum` belongs only to the current `sum1ToN` call. The limit `n <= 1000` caps the maximum sum at `500500`, staying within the range of `jint` commonly defined by JNI as a 32-bit signed integer.
- The JNI signature takes `JNIEnv *` and `jclass` because the Java methods are `static`; `JNIEnv *` belongs to the calling thread and must not be saved and used on another thread.

### 4.3. Compiling and Running (Linux)

Place both files in the same directory, configure `JAVA_HOME` to point to the **JDK** (containing the `include` directory), then run:

```bash
javac -h . NativeState.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnative_state.so native_state.c

java -Djava.library.path=. NativeState
```

If using a compiler named `gcc`, you can replace `cc` with `gcc`. On macOS, headers under `include/darwin` and appropriate dynamic library options are needed; on Windows, use the corresponding compiler format/library/command. The library name must comply with the platform's `System.loadLibrary` rules.

**Exact stdout** in a standalone run of the program:

```text
global 1 = 1
global 2 = 2
main TLS 1 = 1
main TLS 2 = 2
worker TLS 1 = 1
worker TLS 2 = 2
main TLS 3 = 3
sum1ToN(5) = 15
```

The order is deterministic: Java prints the two global values and the two TLS values of main before `worker.start()`; `worker.join()` waits for the worker to finish printing before printing main's third TLS value. This is a Java 17 example with regular platform threads. If another component calls into the same native variables at runtime, one cannot assume global starts at and increments strictly in the sequence above.

## 5. Why Locking Only on the Java Side Is Often Not Enough

Suppose Java wraps a native method with `synchronized`:

```java
private static native int updateNativeGlobal();

public static synchronized int guardedUpdate() {
    return updateNativeGlobal();
}
```

This only serializes **callers that share the same Java lock and actually go through `guardedUpdate()`**. It does not protect C data if:

- a native worker thread updates the same data without acquiring that monitor;
- another JNI method or another library directly accesses the same state;
- C invokes a callback and the callback reenters while a non-reentrant native lock is held.

For example, a normal C mutex protecting a shared struct can allow two threads to use it safely, but if C still holds the mutex when calling a Java callback, and the callback calls back into C to acquire **the same non-recursive mutex**, the thread can self-deadlock. Java's `synchronized` is reentrant for the same Java thread, but that property **does not automatically transfer to a C mutex**.

Cleaner design: own the lock at a single layer with a consistent convention; update shared structures in short sections; release locks before invoking callbacks that may reenter; do not expose pointers to shared data whose protection lifetime has ended.

## 6. When State Is Truly Needed: Pass a Context Instead of Using Globals

A solution that is easier to isolate is allocating a separate struct per instance or session:

```c
/* C example of a context-based API; not a complete program. */
typedef struct Counter {
    unsigned int value;
} Counter;

unsigned int counter_next(Counter *ctx) {
    return ++ctx->value;
}
```

Two separate `Counter` objects do not step on each other's data. However, **sharing the same `ctx` pointer across multiple threads** still requires synchronization; `Counter` is not automatically thread-safe. It is necessary to specify clearly:

- who creates and frees `Counter`, and when it may be freed;
- whether the pointer may be retained across JNI calls; if using `jlong` as a handle, lifetime, type, and validity must be checked—do not treat an arbitrary handle as a safe pointer;
- whether callbacks are allowed to re-access the same context while a previous call is in progress;
- whether the memory can be modified concurrently by another Java/native thread.

When state is not needed, designing to receive input and return results using per-call memory is simpler:

```c
#include <stddef.h>

/* data must point to at least length valid bytes when length > 0. */
size_t count_byte(const unsigned char *data,
                  size_t length,
                  unsigned char target) {
    size_t count = 0;
    for (size_t i = 0; i < length; ++i) {
        if (data[i] == target) {
            ++count;
        }
    }
    return count;
}
```

The function holds no mutable state between calls and is reentrant as long as the `data` region is valid and not concurrently modified. The `const` keyword only prevents the function from modifying through this parameter; it does not prevent another party from modifying the same memory.

## 7. Frequently Overlooked JNI/FFM Rules

### 7.1. `JNIEnv *` and native threads

`JNIEnv *` is a **thread-bound** JNI interface; only use it on the thread that received it. Do not store `JNIEnv *` in a global variable or TLS and then use it from another thread. A C-created native thread wishing to call into the JVM must have the appropriate `JavaVM *` and attach the thread via `AttachCurrentThread` before using JNI; that thread must detach properly before exiting. `JavaVM *` can be stored to obtain the interface/attach, whereas `JNIEnv *` cannot be arbitrarily shared.

JNI local references are typically only valid within the scope of the native call/local reference frame and per thread; to retain a Java object after the call ends, a global reference must be used and properly released with `DeleteGlobalRef`. A global reference **does not automatically synchronize data inside the object**. If native code is waiting on a lock and invokes a Java callback, the JVM/native lock ordering must also be considered.

### 7.2. Java `ThreadLocal` is not identical to C TLS

`ThreadLocal<T>` stores state per Java `Thread`; C11 `_Thread_local` stores state per **OS thread**. In programs using regular platform threads they may correspond while the thread is running, but that is not a shared data contract between the two systems. With thread pools, both Java `ThreadLocal` and native TLS can persist across tasks on a worker; with virtual threads, C TLS must not be used to identify the logical identity of a virtual thread or request.

State bound to a task should be **passed explicitly via parameters/context**, or use a mechanism managed by the execution layer, rather than relying on "which thread is running" at the Java/C boundary.

### 7.3. Data and memory crossing the Java/C boundary

A `jbyteArray`, `ByteBuffer`, or FFM memory region can be accessed by multiple call paths. C using local variables does not eliminate races on **the memory that a pointer references**. With JNI, strictly follow the contract of `Get/Release<PrimitiveType>ArrayElements`, `GetPrimitiveArrayCritical`, and reference lifetimes. In particular, do not perform arbitrary JNI operations or block for long periods while holding a "critical" region per JNI constraints.

With FFM (standard stable API since JDK 22), managing the lifetime and access permissions of `MemorySegment`/`Arena` is an additional concern; **the C global/TLS/reentrancy rules themselves remain unchanged**. Do not use JDK 22 FFM syntax as code that runs verbatim on Java 17: on Java 17, FFM had a different incubator API. Therefore, the practical example above uses JNI to be compatible with Java 17+.

### 7.4. C atomics do not automatically carry Java synchronization rules

C `_Atomic` protects atomic operations under the C memory model. Java `volatile`, `synchronized`, and `VarHandle` follow the Java memory model. When both sides operate on a native region or linked state, do not infer a *happens-before* relationship solely from "Java used synchronized" or "C used relaxed atomic". An access and synchronization contract consistent with the specific API, ABI, platform, and memory region lifetime is required.

## 8. Common Bugs and How to Fix Them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Native counter is occasionally wrong or has hard-to-reproduce bugs | C `static` accessed by multiple threads without synchronization; data race/UB | Use atomics for independent counters, mutexes for multi-field invariants, or separate state |
| Two string results change together | Function returns pointer to `static`/TLS scratch buffer | Caller provides buffer; return a copy with clear ownership |
| Result of request B contains data from request A | TLS is reused by the same worker thread | Reset intentionally or pass per-request context |
| Application hangs when native callback calls itself | Holding a non-recursive mutex across a reentrant call | Redesign lock ordering, release lock before callback, separate per-invocation state |
| Crash when native worker calls JNI | Wrong `JNIEnv *` or expired/wrong-thread reference | Attach thread, obtain own `JNIEnv *`, use global refs when needed |
| Java side is locked but native still races | Some C access paths do not obey the same lock | Place synchronization where the native state is actually owned |
| TLS is used but function is still not reentrant | Two nested calls on the same OS thread write to the same TLS | Remove per-thread scratch state from reentrant calls |
| Code runs on one JDK but fails on another | Confusing JNI with incubator/preview/standard FFM versions | Choose API per JDK version; isolate bindings and verify ABI |

## 9. Checklist When Designing or Reviewing a Native Function

1. **List all state** that the function reads/writes: globals, file-scope `static`, local `static`, TLS, heap via pointers, third-party library resources, `errno`, and callback data. Do not assume `errno` is a single global variable: modern C runtimes typically provide per-thread error state, but one must follow the specific platform contract.
2. **Determine the scope of state:** shared across which calls, which OS threads, which objects/contexts, and which sessions? Determine when it is initialized, reset, and freed.
3. **Ask concurrency questions:** can two threads touch the same object? Can a C data race, out-of-lifetime read/write, or cross-Java/native access occur?
4. **Ask reentrancy questions:** can the function invoke a Java callback, call an API that re-triggers the same function, or hold a mutex/buffer across a callback? Is there temporary data overwritten on reentry?
5. **Choose the smallest sufficient strategy:** per-invocation input/output if stateless; separate context when state belongs to an object; TLS only when state truly belongs to an OS thread; mutex/atomic when sharing is mandatory.
6. **Check the JNI/FFM boundary:** `JNIEnv *` on the right thread, references and native memory still alive, correct JNI method/symbol, exceptions handled, buffers not retained past their lifetime.
7. **Test under realistic load:** multiple platform threads calling concurrently; multiple sequential tasks on a thread pool; nested callback calls; invalid inputs; shutdown/unload and cleanup. Verify correctness via concrete results/invariants, not merely seeing that the program "runs".

**Rule of thumb:** global variables are shared state; TLS is per-OS-thread state; automatic variables are per-call state. Thread safety addresses concurrency, while reentrancy addresses nested calls. To make a native function easy to use from Java, make **ownership, lifetime, synchronization, and callback reentrancy** explicit right in the API contract.