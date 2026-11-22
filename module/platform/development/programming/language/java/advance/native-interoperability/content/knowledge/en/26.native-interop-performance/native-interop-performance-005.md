# Strict Conditions of `Linker.Option.critical` and Restrictions on Blocking Functions or Upcalls

## 1. Objectives and Scope

`Linker.Option.critical(boolean allowHeapAccess)` belongs to the Foreign Function & Memory API (FFM) in `java.lang.foreign`. It is an option when creating a **downcall handle** so that the JVM can optimize the transition path from Java to a native function. In this lesson, "critical" means **an extremely strict contract on the behavior of the called native function**, not synonymous with a `synchronized` lock, a Java critical section, or an automatic speedup mechanism.

After this lesson, you should be able to:

- Identify the **two mandatory conditions** according to the specification: the native function runs extremely short **in all cases** (similar to an empty function) and **does not call back into Java**, including via an FFM upcall stub.
- Understand that `critical(false)` and `critical(true)` differ in the permission to pass a **heap memory segment** as a native pointer, not "less critical" and "more critical".
- Explain why a function that may be **blocking** (I/O, waiting on a lock, sleep, waiting for a callback, waiting for a result from another thread) or performs an **upcall into Java** must not be marked critical.
- Create a valid critical downcall; create an ordinary downcall with an upcall; identify cases where `critical` must be omitted even if the function appears "fast".
- Distinguish JVM implementation-specific optimizations from what the API guarantees; know the consequences of misdeclaration: degraded performance, unsafe behavior, or JVM crash.

**Version used:** The FFM API became official in JDK 22 (JEP 454); examples are written for **JDK 25**, without preview flags. The native compilation examples below target **Linux x86-64**, where C `int` is normally 32 bits. On other platforms/ABIs, you must re-verify layouts, symbol exports, and linker commands.

## 2. Downcall, Upcall, and the Critical Option

**Downcall:** Java calls a native function address using a `MethodHandle` created by `Linker.downcallHandle(...)`. The JVM must perform appropriate steps at the Java/native boundary, such as preparing ABI arguments and transitioning thread state; the exact implementation belongs to the JVM.

**Upcall:** C/C++ calls into Java through a function pointer created from `Linker.upcallStub(...)`. The Java callback runs while the native call is still active. An upcall needs to transition back into the Java runtime and may trigger activities that the critical path is not assumed to be safe for.

An ordinary call has the form:

```java
MethodHandle normal = linker.downcallHandle(
    targetAddress,
    FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)
);
```

A call declared as critical:

```java
MethodHandle critical = linker.downcallHandle(
    targetAddress,
    FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT),
    Linker.Option.critical(false)
);
```

The two snippets above are **illustrative excerpts**, assuming `linker` and `targetAddress` have already been created. `critical(...)` is an **option at link time**, not a native invocation method, and does not alter the C function signature. For a runnable version, see the full program in section 6.

According to the Javadoc, critical is an **optimization hint** for some implementations. The JVM can exploit the very strong assumption that the native function finishes almost instantaneously and does not re-enter Java. **There is no guaranteed promise of speed**, no automatic timeout detector, and no guarantee that the JVM will catch every case where you misdeclare it. Mislabeling a function that does not satisfy the contract can make the program slower or crash the JVM.

## 3. Strict Contract That Must Be Satisfied

### 3.1. Execution Time Must Be Extremely Short on **Every** Path

The Javadoc describes a critical function as having a runtime that is **“extremely short ... in all cases (similar to calling an empty function)”**. You cannot just look at the average, median, p99 of good inputs, or a single successful benchmark run.

A suitable candidate is a C function performing a few fixed operations, independent of input length, and calling no library that could block:

```c
int add_one(int x) {
    return x + 1;
}
```

Examples that are **ineligible** even if they sometimes run fast:

- `read`/`recv`/`accept`, file/network access, or any system I/O that may wait for data.
- `sleep`, `nanosleep`, waiting on an event, condition variable, semaphore, a held mutex/lock, `pthread_join`, or waiting on a thread.
- Functions using locks or allocations with a slow path that has no extremely short bound; wrappers calling external services.
- Loops dependent on the size of an array/buffer passed by the caller (e.g., scanning megabytes); `strlen` on unboundedly long strings.
- Functions calling native libraries that you do not control or have not verified on all paths, including error branches and signal handling.
- Functions that "usually take a few microseconds" but **occasionally** block, retry, wait on contention, or perform long work.

The extremely short bound is not expressed as a fixed number of milliseconds in the API; evaluate the **strictly bounded work** characteristic of every branch, rather than setting your own threshold like "under 5 ms is critical".

### 3.2. Strictly No Callback/Upcall into Java

A native function marked critical **must not call back into Java**. Examples of violations:

- Receiving a function pointer to `Linker.upcallStub(...)` and **actually invoking** that function pointer.
- Calling JNI to execute a Java method, such as `CallStaticVoidMethod` or `CallObjectMethod`.
- Calling another native library that internally has a callback to Java (including indirect callbacks via hooks/handlers).
- Triggering a callback unpredictably, for example only on an error branch or on a cache miss.

Reason: an upcall needs to go from native back into the JVM, whereas an implementation may optimize critical downcalls using assumptions about thread state, GC/safepoints, and runtime entry/exit paths. Marking critical and then upcalling breaks those assumptions. Failure can lead to a JVM crash rather than a clear Java exception.

If a native API takes a callback and **might** invoke it, the safe way to link it is an **ordinary downcall**, without passing `Linker.Option.critical(...)`. Even if the callback rarely runs or only runs in an error situation, that function is still ineligible for critical.

### 3.3. Do Not Retain State or Heap Pointers After the Call

A critical call may allow native code to use a temporary address of Java heap memory when `allowHeapAccess=true`. This native address is only valid **while the native function is being called**. Native code must not store the pointer in a static/global variable, return it for later use, pass it to a worker thread for asynchronous processing, or continue accessing it once the downcall has finished.

In particular, do not use that temporary heap pointer to:

- Wait for an asynchronous I/O operation to use the pointer after the C function returns.
- Send it to a worker thread and return to Java before the worker finishes reading.
- Store it in a native struct/cache for reuse in subsequent calls.

Native code accessing beyond the segment length, with wrong alignment, or retaining a pointer past its lifetime remains a memory safety bug: FFM cannot check every C/C++ operation inside a pointer passed across the ABI.

## 4. How Does `critical(false)` Differ from `critical(true)`?

Official API signature:

```java
static Linker.Option critical(boolean allowHeapAccess)
```

| Linking method | Heap `MemorySegment.ofArray(...)` as `ADDRESS` argument | Meaning |
| --- | --- | --- |
| Not passing `critical` | Not allowed under ordinary downcall address argument rules | Java → native transition via the ordinary path; use for functions that may block/upcall |
| `Linker.Option.critical(false)` | Not allowed | Promises extremely short function, no upcall; **does not** need a heap pointer |
| `Linker.Option.critical(true)` | Allowed | **Still** promises extremely short, no upcall, while also allowing receipt of a temporary pointer to heap memory |

`allowHeapAccess=true` does not "relax" the time limit or allow callbacks. It only adds the ability to pass a heap segment to a parameter with `AddressLayout`, in cases where copying to off-heap incurs overhead disproportionate to the function's extremely short work.

When passing a heap segment, the JVM provides a temporary native address valid for the **duration of the call**. The implementation strategy to achieve this may depend on the JVM/GC; you must not assume every JVM is always "zero-copy" or always directly pins the heap in one fixed way. This access path can affect GC and latency if held for long; therefore the **extremely short** condition is even more important when heap access is enabled.

Two common misconceptions:

1. Using `critical(true)` for a "stronger speedup" while only passing `int`/`long` arguments: the `true` parameter carries no speed meaning; it only enables heap segment access.
2. Using `critical(true)` for native I/O reading directly into a `byte[]` to avoid copying: even if some copy operations are avoided, the function can still block and is therefore **ineligible for critical**. Use an ordinary downcall with a native/off-heap buffer or a different I/O design.

If you pass a heap segment to a downcall with `ADDRESS` but without `critical(true)`, the API will reject it according to the corresponding contract (typically `IllegalArgumentException` when invoking the method handle); do **not** treat this as a reason to arbitrarily enable critical for a long function.

## 5. Decision Matrix: Choose Critical or Ordinary Downcall?

| Actual behavior of native function | Choice | Explanation |
| --- | --- | --- |
| A few fixed integer operations, no I/O, no callback, every branch extremely short | Can consider `critical(false)` | Satisfies the contract if even error branches are extremely short |
| Reads exactly 2 bytes from `byte[]` and adds them; does not store the pointer | Can consider `critical(true)` | Direct heap access within the scope of an extremely short call |
| Processes a buffer of unbounded size | Ordinary downcall | Time depends on data |
| `read` from socket, `sleep`, waiting on lock/semaphore | Ordinary downcall | Has blocking or unpredictable wait paths |
| Native calls a Java callback/upcall stub | Ordinary downcall | Callback violates the critical contract |
| Wrapper that might call JNI into Java | Ordinary downcall | Cannot guarantee no upcall |
| Calls a third-party native library with unknown paths | Ordinary downcall | Has not proven all branches are extremely short and callback-free |
| Function retains heap pointer and continues processing after returning | Must **redesign** ownership/lifetime | No `critical` option makes a temporary pointer live longer |
| Extremely short function but called very infrequently | Usually needs no optimization | Only a benchmark proves actual benefit |

Review rule: If you cannot describe and prove that **every branch** is nearly instantaneous and **has no upcall**, use an ordinary downcall. Do not use a happy-path benchmark as a substitute for proof of safety.

## 6. Runnable Lab: Two Valid Critical Calls and One Ordinary Upcall

The lab avoids intentionally violating critical because running a dangerous native example can **crash the JVM**. Instead, the program demonstrates **two safe critical calls** along with **one upcall properly using an ordinary downcall**.

### 6.1. Native Code: `criticallab.c`

On Linux x86-64, save the following full content as `criticallab.c`:

```c
#include <stdint.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

/* Single operation only: no allocation, no blocking, no callback. */
EXPORT int add_one(int value) {
    return value + 1;
}

/* Java must ensure the array has at least 2 bytes.
 * The pointer may only be read during this call. */
EXPORT int sum_two_bytes(const unsigned char *bytes) {
    return (int)bytes[0] + (int)bytes[1];
}

typedef int (*int_callback)(int);

/* Calls a Java-created callback: MUST NOT BE MARKED CRITICAL. */
EXPORT int call_callback(int value, int_callback callback) {
    return callback(value) + 1;
}
```

`add_one` only adds 1, and `sum_two_bytes` reads exactly 2 unsigned bytes; both have extremely short fixed work and do not call Java. Conversely, `call_callback` executes a function pointer leading back to Java: an ordinary downcall must be used even though the wrapper itself is only one line.

### 6.2. Java: `CriticalLinkerDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import static java.lang.foreign.ValueLayout.ADDRESS;
import static java.lang.foreign.ValueLayout.JAVA_INT;

public final class CriticalLinkerDemo {
    private static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) throws Throwable {
        System.loadLibrary("criticallab");

        Linker linker = Linker.nativeLinker();
        SymbolLookup symbols = SymbolLookup.loaderLookup();

        // Case A: critical without using a Java heap pointer.
        MethodHandle addOne = linker.downcallHandle(
            symbols.find("add_one").orElseThrow(),
            FunctionDescriptor.of(JAVA_INT, JAVA_INT),
            Linker.Option.critical(false)
        );
        int first = (int) addOne.invokeExact(41);
        System.out.println("critical(false): " + first);

        // Case B: native only reads 2 bytes from a Java array during the call.
        MethodHandle sumTwo = linker.downcallHandle(
            symbols.find("sum_two_bytes").orElseThrow(),
            FunctionDescriptor.of(JAVA_INT, ADDRESS),
            Linker.Option.critical(true)
        );
        byte[] pair = {7, 11};
        MemorySegment heapSegment = MemorySegment.ofArray(pair);
        int second = (int) sumTwo.invokeExact(heapSegment);
        System.out.println("critical(true): " + second);

        // Case C: native will upcall into Java. Do not use critical.
        MethodHandle callbackTarget = MethodHandles.lookup().findStatic(
            CriticalLinkerDemo.class,
            "twice",
            MethodType.methodType(int.class, int.class)
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment upcallStub = linker.upcallStub(
                callbackTarget,
                FunctionDescriptor.of(JAVA_INT, JAVA_INT),
                arena
            );

            MethodHandle callCallback = linker.downcallHandle(
                symbols.find("call_callback").orElseThrow(),
                FunctionDescriptor.of(JAVA_INT, JAVA_INT, ADDRESS)
            );

            int third = (int) callCallback.invokeExact(20, upcallStub);
            System.out.println("ordinary + upcall: " + third);
        }
    }
}
```

Points to verify in the code:

- `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` describes `int add_one(int)` and `int twice(int)` on the Linux x86-64 ABI; `MethodHandle.invokeExact` requires arguments and return types to **match exactly**.
- `FunctionDescriptor.of(JAVA_INT, ADDRESS)` describes `int sum_two_bytes(const unsigned char*)`, and only because `critical(true)` was promised is a Java heap segment allowed as `ADDRESS`.
- `FunctionDescriptor.of(JAVA_INT, JAVA_INT, ADDRESS)` describes `int call_callback(int, int (*)(int))`. The Java code **does not pass the critical option** when creating this handle because C will call back via `upcallStub`.
- `Arena.ofConfined()` controls the lifetime of the upcall stub. C invokes the callback **synchronously before returning**; the stub is used while the arena is still open and on the thread owning the arena.
- The `twice` callback does not throw exceptions. Upcall targets in real applications must catch/translate errors before an exception escapes across the native boundary; the `Linker.upcallStub` documentation warns that an exception escaping an upcall can cause the JVM to terminate abruptly.
- The program has `throws Throwable` to simplify the demo with `MethodHandle.invokeExact`; in real applications, a clearer error-handling strategy is needed.

### 6.3. Compiling and Running on Linux x86-64

Requires JDK 25, a C compiler (`cc` or `gcc`), and both files in the same directory:

```bash
cc -std=c11 -O2 -fPIC -shared criticallab.c -o libcriticallab.so
javac CriticalLinkerDemo.java
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. CriticalLinkerDemo
```

**Expected exact stdout:**

```text
critical(false): 42
critical(true): 18
ordinary + upcall: 41
```

Line-by-line explanation:

- 41 + 1 = 42 via `add_one` with `critical(false)`.
- Unsigned bytes 7 + 11 = 18 via `sum_two_bytes` with `critical(true)`, without retaining the pointer after the call.
- C calls the Java callback `twice(20)` → 40, then adds 1 → 41 via an **ordinary downcall**.

`System.loadLibrary("criticallab")` loads `libcriticallab.so`; `SymbolLookup.loaderLookup()` retrieves symbol addresses of the library loaded by the class loader. `--enable-native-access=ALL-UNNAMED` enables native access for the program running from the classpath, because the related FFM APIs have restricted access. `-Djava.library.path=.` allows the JVM to find the library in the current directory. Because the code uses official JDK 25 APIs, `--enable-preview` is not used.

On macOS you need to build `libcriticallab.dylib` (e.g., `cc -dynamiclib criticallab.c -o libcriticallab.dylib`); on Windows you need to build `criticallab.dll`, using the appropriate compiler/linker commands and ensuring the correct architecture. The example and stdout above are designed for the Linux x86-64/JDK 25 environment; changing the ABI or compiler requires re-verification.

### 6.4. Why Not Add `critical` to Case C?

Suppose someone changes how `call_callback` is linked as follows:

```java
// INCORRECT ILLUSTRATION — DO NOT RUN:
MethodHandle dangerous = linker.downcallHandle(
    symbols.find("call_callback").orElseThrow(),
    FunctionDescriptor.of(JAVA_INT, JAVA_INT, ADDRESS),
    Linker.Option.critical(false)
);
```

This is **not a safe runnable version**. Because `call_callback` will invoke `callback(value)` leading back to Java, the "no upcall" assumption of critical is violated. Do not run it to test whether the JVM reports an error: the Javadoc warns that misuse can crash the JVM. The correct fix is to **omit `Linker.Option.critical(...)`**, as in case C of the full program.

## 7. For Blocking Functions, Callbacks, or Long Work: Alternative Designs

### 7.1. Blocking Functions

For example, `read`, `recv`, `accept`, waiting on locks, waiting on signals, or out-of-process I/O usually have uncontrolled durations. Do **not** use `critical(false)` and also do **not** use `critical(true)`. Create an ordinary downcall matching the signature and ABI. Where low latency is required, consider timeouts, native nonblocking APIs, dedicated workers, completion/event-driven APIs, or separating the long work from an extremely short native segment.

Linking pattern (excerpt, without declaring `linker`, `address`, `descriptor`):

```java
// Native function that may block: ordinary downcall.
MethodHandle blockingCall = linker.downcallHandle(address, descriptor);
```

Omitting `critical` does **not** automatically make an I/O operation asynchronous: the thread calling the method handle must still wait for the native function to finish, unless you design asynchrony elsewhere.

### 7.2. APIs Using Callbacks

If a C library accepts a function pointer that can call back into Java, create an `upcallStub` and link the C function with an ordinary downcall. Ensure the arena holding the stub remains alive for the entire time C might invoke it. If the library retains the callback after the downcall finishes, do **not** use `Arena.ofConfined()` in a short try-block like in the lab: you must design registration/unregistration and a correspondingly long stub lifetime. Which thread C calls the callback from must also be evaluated for thread confinement constraints and runtime state; an asynchronous callback must not use a pointer or stub that has already been freed.

Every `upcallStub` must have a target `MethodHandle` matching the ABI and handle exceptions at the Java boundary; do not let unhandled exceptions escape across the native boundary. This is an upcall-specific risk **even with an ordinary downcall**.

### 7.3. Buffer/Heap Processing and Runtime Duration

If native code needs to read/write large amounts of Java heap data or processing time varies with size, use a mechanism that copies into a native `Arena`/off-heap memory and passes the address via an ordinary downcall, or design an appropriate streaming/alternative operation. Do not sacrifice safety to avoid one copy.

If only reading a few controlled bytes, you can measure `critical(true)` after proving the data is long enough, synchronous, has no escaping pointer, and has no callback. Explicitly document invariants regarding length, alignment, and lifetime in code review; `MemorySegment` bounds checks on the Java side **do not automatically protect** against native code dereferencing a bad pointer.

## 8. Performance: When Is Critical Actually Worth Using?

Critical is a **behavioral declaration** so that the JVM *may* reduce the cost of a native call. The difference is most meaningful when an extremely short function is called **very many times**, and the Java ↔ native transition overhead makes up a large proportion compared to the actual work.

To evaluate objectively:

1. First prove eligibility: inspect the C/C++ code, helper functions, error branches, buffer handling, locks, I/O, and callbacks **on every path**. Inspect the library version that will be deployed to production.
2. Create **two handles with the same signature** for the same eligible native function: an ordinary downcall and a `critical(false)` handle (or `critical(true)` if heap access is genuinely needed).
3. Use a benchmark with warm-up, consistent JVM/JDK/GC, sufficiently large loops, and dead-code elimination prevention. In Java, JMH is usually more convenient than a one-off measurement with `System.nanoTime()`.
4. Check both throughput and latency, including tail levels (p95/p99) and GC activity, under a realistic workload. If `allowHeapAccess=true`, also monitor GC impact under heavy call rates.
5. Only keep the optimization if the benefit is repeatable and outweighs the maintenance/risk cost, not just because of the name `critical`.

**Do not benchmark by intentionally attaching critical to `sleep`/I/O/upcall**. That is a contract-violating experiment and can cause JVM-level failures.

## 9. Troubleshooting and Common Misconceptions

| Symptom | Possibilities to check | How to handle |
| --- | --- | --- |
| JVM crashes after adding `critical` | Native function has upcall/blocking/wrong signature or memory safety violation | Remove `critical`, check callbacks/ABI/pointers; collect crash log if available |
| Benchmark improves but production tail latency increases | Native path has contention, GC interaction, or a slow path | Inspect all branches; measure realistic workload; revert to ordinary downcall if contract cannot be proven |
| `IllegalArgumentException` when passing `MemorySegment.ofArray(...)` as `ADDRESS` | Downcall does not allow heap segment address | Use a native buffer with an ordinary downcall, or **only when eligible for critical** consider `critical(true)` |
| `UnsatisfiedLinkError` | Native library or exported symbol has wrong name/path/architecture | Check `libcriticallab.so`, `java.library.path`, symbol exports, and ABI |
| `IllegalCallerException` or native access warning | Module does not have native access enabled | Use `--enable-native-access=ALL-UNNAMED` for classpath or specify the module name |
| `WrongMethodTypeException` on `invokeExact` | Java types at call site do not match `MethodHandle.type()` | Fix `FunctionDescriptor`/argument types/casts to match the actual signature |
| Upcall causes abort/JVM exit | Java callback throws an exception or signature/lifetime is wrong | Catch errors in the callback, map to native result, and keep the stub alive |

**Three points to distinguish carefully:**

- `Linker.Option.critical` is **not** JNI `GetPrimitiveArrayCritical` and is **not** JVM `-Xcheck:jni`. The mechanisms may relate to avoiding GC paths, but they do not replace each other.
- The absence of a Java exception or clear warning **does not mean** that marking critical is safe. Behavior after a contract violation may depend on the JVM, GC, architecture, and code branch.
- A Java method or native function that "does not directly call Java" must still be audited for **indirect calls** to other libraries, function pointers, or error handlers: any path with an upcall is unsuitable for critical.

## 10. Code Review Checklist Before Choosing `Linker.Option.critical`

- [ ] Every path of the C/C++ function has an extremely short runtime, near the level of an empty function; work is strictly bounded and does not depend on large input sizes.
- [ ] Performs no I/O, scheduler wait, sleep, lock, semaphore, allocation/slow path not guaranteed to be extremely short, or event wait.
- [ ] Has no Java callback/upcall, including via function pointers, JNI, intermediate libraries, or error branches.
- [ ] `FunctionDescriptor` signature, C types, calling convention/ABI, and `MethodHandle.invokeExact` match.
- [ ] `critical(false)` is preferred when passing a heap segment is not needed; `critical(true)` only when a pointer into the heap is genuinely needed and a benefit is proven.
- [ ] Buffer length/alignment is verified; all temporary heap pointers are only used **during** the native call.
- [ ] No storing, propagating, or accessing the heap pointer after the downcall finishes; no dispatching async work with the temporary address.
- [ ] Consulted the documentation/JDK in use and understood the option is only an optimization hint, with no guarantee of speedup.
- [ ] Have a benchmark comparing ordinary vs. critical, with warm-up, realistic workload, and GC/tail latency observation.
- [ ] When any condition is unproven, use an **ordinary downcall**.

## 11. Self-Check Questions

**1.** A C function normally runs in 20 ns, but on lock contention it waits for several seconds. Should `critical(false)` be used?  
**Answer:** No. The "extremely short in all cases" condition is broken by the lock-waiting branch.

**2.** A C function only calls `callback(7)` and returns. Even though it is very short, can `critical(true)` be used?  
**Answer:** No. Any callback into Java violates the contract; use an ordinary downcall.

**3.** Does `critical(true)` allow using a heap pointer from `MemorySegment.ofArray` after the native function returns?  
**Answer:** No. The temporary native address is only valid for the duration of the call.

**4.** Given two handles calling the same safe native function, one ordinary and one critical, is the critical one necessarily faster?  
**Answer:** No. It is an optimization hint, depending on the JVM implementation and workload; you must benchmark.

**5.** Why should you not fix a "heap segment rejected" error by always adding `critical(true)`?  
**Answer:** Because `true` only permits a heap argument when **simultaneously** meeting the conditions of an extremely short function and no upcall. An I/O function or one waiting on a callback is still ineligible.

## Official References

- Oracle JDK 25, `Linker.Option.critical(boolean)`, definition of extremely short duration, no upcalls, consequences of misuse, and `allowHeapAccess`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.Option.html
- Oracle JDK 25, `Linker`, downcall/upcall, ABI safety limits, and exceptions in upcalls: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html
- Oracle JDK 25, `MemorySegment`, heap/native segments, scope, and `ofArray`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html
- Oracle JDK 25, `SymbolLookup`, `loaderLookup`, and symbol resolution: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SymbolLookup.html
- Oracle JDK 25, Restricted Methods / native access: https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html
- OpenJDK JEP 454, *Foreign Function & Memory API* (finalized in JDK 22): https://openjdk.org/jeps/454
