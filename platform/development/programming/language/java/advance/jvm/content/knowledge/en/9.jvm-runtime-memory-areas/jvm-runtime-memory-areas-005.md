# Native method stack and the native code call boundary in the JVM

When a Java thread calls a method written in Java, the JVM provides the **Java Virtual Machine stack** model, **frames**, local variables, and the operand stack. When the call enters a method implemented in C/C++ or an operating system library, the thread crosses the **Java ↔ native boundary**. A JVM implementation may use a **native method stack** (commonly referred to as a “C stack”) to support execution outside Java bytecode.

The key point: **the native method stack is distinct from the Java heap, distinct from off-heap memory in general, and is not required to exist as a second physical stack independent of the Java stack on every JVM**. The JVM Specification (JVMS) describes behavior and implementation options, and does not mandate a single stack layout in the operating system. For a common JVM such as HotSpot, native calls typically use the stack and ABI of the running OS thread; JIT/compiler code may keep data in registers, inline functions, and organize frames in its own way.

This article goes from the memory area concept to the **JNI** boundary, how arguments and exceptions are passed, how it interacts with GC, native thread management, a complete **Java 17 + C** example, and a diagnostic workflow.

## 1. What is the native method stack according to JVMS?

JVMS §2.5.6 allows an implementation to use conventional stacks (often called **C stacks**) to support:

- **Native methods**: methods implemented in a language other than Java and called by the JVM.
- Internal JVM/interpreter code if implemented in a language that uses conventional call stacks.

If a JVM does not support loading native methods and does not need a conventional stack for its own implementation, the specification **does not require** providing native method stacks. When present, they are typically associated with a **thread** when the thread is created. The stack may have a fixed size or expand/contract according to implementation capabilities.

**Two correct conclusions:** Java has the abstract concept of a native method stack; actual native code needs an execution context and storage corresponding to the ABI/platform.

**Incorrect conclusion:** every Java method calling native definitely creates a separate native stack region from the Java stack, or every native call creates a new OS thread.

### 1.1. Memory limits

JVMS associates native method stacks with these error conditions:

- When computation requires a stack larger than the allowed size, a **`StackOverflowError`** occurs according to this memory area's rules.
- If the stack needs to expand or needs to be created for a new thread but appropriate memory cannot be allocated, an **`OutOfMemoryError`** occurs.

This is the error model of the JVM Specification. It **does not guarantee** that every error in C — stack smash, buffer overrun, use-after-free, invalid address dereference — will be turned into a Java exception that is easy to `catch`. Buggy C code can still cause a **SIGSEGV/access violation and crash the entire process**.

## 2. Native method stack, JVM stack, Java heap, and native memory

| Concept | Role | Scope | Must not be confused with |
| --- | --- | --- | --- |
| JVM stack | Frames, local variables, operand stacks, dynamic linking/return logic according to the JVM model | Per JVM thread | Java heap |
| Native method stack | Stack used for native methods/JVM implementation if using a conventional stack | Usually per thread | “all native memory” |
| Java heap | Java objects and arrays managed by GC | Shared across the JVM | C call frames |
| Method area / metaspace | Class metadata and corresponding runtime structures; allocation depends on the JVM | Managed by the VM | Native method call stack |
| Native/off-heap memory | Native stacks, `malloc`, direct buffers, JIT code cache, VM structures, and many other components | Depends on allocation | Only a native method stack |
| Registers | Values/call state managed by the compiler/CPU | At execution time | Fixed physical Java local-variable slots |

For example, `String input` in Java holds a **reference**, without copying the entire String content into the Java caller's frame. When passed through JNI, the native function receives a **`jstring` handle/reference**, not a mandatory copy of the Java object on the C stack.

JNI has functions to retrieve string data, but whether a copy is created or data is pinned depends on the API and JVM. It is necessary to distinguish between **the object residing on the Java heap**, **the handle held by native code**, and **temporarily allocated buffers**.

### 2.1. A JVM frame does not necessarily correspond to a C frame

A Java method may have a `Code` attribute with `max_stack` and `max_locals`. A C function follows a calling convention/ABI, and the native compiler may use registers, the machine stack, and tail/inlining optimizations.

- Java local slot 0 in an instance method is `this` according to the JVM, not an always-fixed C stack offset.
- A C variable `int result` may reside entirely in a register.
- A Java stack trace and a native debugger backtrace are not the same format and do not always print the same sequence of frames.
- Do not infer native stack usage simply by counting lines of Java source.

## 3. Crossing the Java → native call boundary

Java declares:

```java
static native int sum(int left, int right);
```

This is a **declaration**, without a Java method body. In the class file, the method carries the **`ACC_NATIVE`** flag, and has no `Code` attribute containing Java bytecode to perform the addition. The JVM binds this call to a **native entrypoint** through an appropriate interoperability mechanism, such as JNI.

```text
Java method (caller)
   │ invoke* to native declaration
   │ arguments per JVM descriptor
   ▼
JVM/JNI transition
   │ select native implementation and calling convention
   │ pass JNIEnv*, receiver/class, arguments
   ▼
Native C function
   │ C function calls / native stack or CPU registers
   │ may call JNI API or callback into Java
   ▼
Return JNI primitive/reference or pending exception
   │
   ▼
JVM restores Java caller semantics
   ├─ normal result → caller receives value
   └─ Java exception → find catch/unwind frames
```

There is no bytecode opcode named `jni_call`. Opcodes such as `invokestatic`, `invokevirtual`, or `invokespecial` can call methods declared `native`; executing the native code is the responsibility of the JVM and native linkage, with no Java bytecode body for `javap -c` to list.

### 3.1. `JNIEnv*` and implicit arguments

For a C JNI entrypoint:

- `JNIEnv *env` is an **interface pointer valid on the current thread**.
- Static native methods additionally receive `jclass clazz`.
- Instance native methods additionally receive `jobject receiver`.
- Java parameters are mapped to `jint`, `jlong`, `jdouble`, `jstring`, `jobject`, `jarray`, and appropriate JNI types.

| Java declaration | C signature (core part) |
| --- | --- |
| `static native int add(int a, int b)` | `(JNIEnv*, jclass, jint, jint) → jint` |
| `native long scale(long n)` | `(JNIEnv*, jobject, jlong) → jlong` |
| `static native void log(String value)` | `(JNIEnv*, jclass, jstring) → void` |

This is the mapping **at the API boundary**, not a promise that the C compiler pushes all parameters onto the native stack on every OS/CPU.

### 3.2. Primitive values and object references

Primitive arguments pass through JNI as **values** of their corresponding types. For references, JNI uses **opaque handles** instead of allowing native code to read internal Java heap object layouts via arbitrary dereferencing.

A `jstring` is not a `char*`. A `jobject` is not a stable pointer to an object that may be cast to a C `struct*`. GC may move objects, so to read fields, call methods, or retrieve data, supported JNI functions must be used.

## 4. Complete JNI example: Java calls C, C calls back into Java and throws an error

The example consists of two files: **`NativeBoundaryDemo.java`** and **`boundarydemo.c`**. The Java part is compiled with JDK 17; the C part requires a native compiler with the same architecture/ABI as the JDK. The program prints deterministic stdout when compiled and loaded successfully.

### 4.1. Java: `NativeBoundaryDemo.java`

```java
public class NativeBoundaryDemo {
    static {
        System.loadLibrary("boundarydemo");
    }

    private static native int add(int left, int right);

    private static native int twiceViaJava(int value);

    private static native void requireNonNegative(int value);

    private static int doubleValue(int value) {
        return value * 2;
    }

    public static void main(String[] args) {
        System.out.println("sum=" + add(5, 7));
        System.out.println("callback=" + twiceViaJava(9));

        try {
            requireNonNegative(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("done");
    }
}
```

`System.loadLibrary("boundarydemo")` uses a **logical name**, without the `lib` prefix or `.so`, `.dylib`, `.dll` extension. In this example, the class declares no package so that the C symbol is easy to read.

### 4.2. Generating the JNI header and Java bytecode

In the directory containing the Java source:

```bash
javac --release 17 -h . -d out NativeBoundaryDemo.java
```

`javac -h .` generates the **`NativeBoundaryDemo.h`** file with the corresponding JNI function prototypes; `-d out` places `NativeBoundaryDemo.class` into the `out` directory. Do not manually edit the JNI prototypes once you have the compiler-generated header.

### 4.3. C: `boundarydemo.c`

```c
#include <jni.h>

static jint add_in_c(jint a, jint b) {
    const jint result = a + b;
    return result;
}

JNIEXPORT jint JNICALL
Java_NativeBoundaryDemo_add(JNIEnv *env, jclass clazz,
                            jint left, jint right) {
    (void)env;
    (void)clazz;
    return add_in_c(left, right);
}

JNIEXPORT jint JNICALL
Java_NativeBoundaryDemo_twiceViaJava(JNIEnv *env, jclass clazz,
                                     jint value) {
    jmethodID method =
        (*env)->GetStaticMethodID(env, clazz, "doubleValue", "(I)I");

    if (method == NULL) {
        return 0; /* A pending JNI exception may exist. */
    }

    return (*env)->CallStaticIntMethod(env, clazz, method, value);
}

JNIEXPORT void JNICALL
Java_NativeBoundaryDemo_requireNonNegative(JNIEnv *env, jclass clazz,
                                           jint value) {
    (void)clazz;

    if (value >= 0) {
        return;
    }

    jclass type =
        (*env)->FindClass(env, "java/lang/IllegalArgumentException");
    if (type == NULL) {
        return; /* FindClass may have already raised a pending exception. */
    }

    (*env)->ThrowNew(env, type, "negative value");
    (*env)->DeleteLocalRef(env, type);
}
```

How to read:

- `JNIEXPORT` and `JNICALL` from `jni.h` support visibility/calling convention.
- `add_in_c` illustrates a C helper call. The native compiler may create a stack frame, inline it, or keep the value in registers; this is an optimization detail.
- `GetStaticMethodID` retrieves the handle for method `doubleValue` with descriptor **`(I)I`**.
- `CallStaticIntMethod` goes from native to Java and then returns to native on the same thread.
- If `GetStaticMethodID` fails, the code returns with a pending exception; `0` does not mean the JVM ignores the exception so the Java caller receives the number 0.
- `ThrowNew` sets a pending Java exception. `DeleteLocalRef` releases the local reference for `type` and is a permitted operation under a pending exception condition.
- A C library **does not** use C `throw` or propagate `errno` to Java automatically; for Java to catch a business error, native code actively communicates via JNI.

### 4.4. Compiling the native library

**Linux with GCC**, when `JAVA_HOME` points to a full JDK:

```bash
gcc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -o libboundarydemo.so boundarydemo.c
```

**macOS with Clang**:

```bash
cc -dynamiclib -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" -o libboundarydemo.dylib boundarydemo.c
```

**Windows with Visual Studio Developer Command Prompt** (use quotes for variables containing spaces):

```bat
cl /LD /I"%JAVA_HOME%/include" /I"%JAVA_HOME%/include/win32" boundarydemo.c /Fe:boundarydemo.dll
```

Each command is only for the **stated OS and native compiler**; corresponding JDK headers and the same CPU architecture (64-bit/arm64/x86_64) are required for the JVM and shared library.

### 4.5. Running and stdout

In the directory containing the shared library and the `out` directory:

```bash
java -Djava.library.path=. -cp out NativeBoundaryDemo
```

**Stdout when compiled/linked successfully:**

```text
sum=12
callback=18
caught=negative value
done
```

Progression:

1. `main` calls native `add(5,7)`. C calls `add_in_c` and returns `jint 12`; the Java caller prints `sum=12`.
2. `main` calls native `twiceViaJava(9)`. C calls `CallStaticIntMethod` into Java `doubleValue(9)`, receives `18`, returns to the Java caller, and prints `callback=18`.
3. `main` calls `requireNonNegative(-1)`. C uses `ThrowNew`; when the JNI method returns, the JVM transfers control along the exception path and `main` catches `IllegalArgumentException` and prints the message.
4. After the handler, Java continues and prints `done`.

**The real boundary:** a Java→native→Java callback call can create an interleaved chain of Java/native execution contexts. Do not conclude on your own that a new native OS thread or a second physical stack is created for each transition.

## 5. JNI local references, global references, and GC

JNI distinguishes the **lifetime of a reference** from the lifetime of the C variable holding it.

| JNI reference | Lifetime/ownership | How to manage |
| --- | --- | --- |
| **Local** | Valid within the corresponding JNI local frame/native invocation and only on the appropriate thread | Usually freed after native return; can call `DeleteLocalRef` early |
| **Global** | Retained across multiple native calls until deleted | `NewGlobalRef` and `DeleteGlobalRef` |
| **Weak global** | Does not keep the object strongly alive like a global ref; may be cleared by GC | `NewWeakGlobalRef`, check validity when used, and `DeleteWeakGlobalRef` |
| **Native pointer from `malloc`** | Follows native allocator/ownership | Must `free` or release per library contract |

**Incorrect** example, because C static storage outlives a JNI local reference:

```c
/* Anti-pattern illustration, not a standalone program */
static jobject saved;

JNIEXPORT void JNICALL
Java_Example_bad(JNIEnv *env, jclass clazz, jobject value) {
    (void)env;
    (void)clazz;
    saved = value; /* Local JNI reference becomes invalid after the native call */
}
```

If an object must genuinely be kept across multiple calls, native code needs **`NewGlobalRef(env, value)`**, error checking, and at the end of its lifecycle needs **`DeleteGlobalRef`**. A remaining JNI global reference can keep a Java object reachable on the heap, leading to heap pressure if leaked.

### 5.1. A `jobject` is not a raw pointer

JNI handles are tracked by the JVM. GC may move objects depending on the implementation; do not cast `jobject` directly to `void*` and read member layouts like a C struct.

Even when a `jobject` is stored in a C stack slot, **the handle's lifetime is managed by JNI**, not by whether the C local variable is still in scope.

### 5.2. Strings/arrays and release rules

A snippet illustrating how to retrieve `jstring` data using the correct API:

```c
/* Inside a native function with JNIEnv *env, jstring text;
   snippet only, not a standalone function. */
const char *buffer = (*env)->GetStringUTFChars(env, text, NULL);
if (buffer == NULL) {
    return; /* OutOfMemoryError may be pending. */
}

/* Read buffer within valid scope */
(*env)->ReleaseStringUTFChars(env, text, buffer);
```

Things to keep in mind:

- `GetStringUTFChars` uses JNI's **Modified UTF-8**, which is not identical to standard UTF-8 in all cases.
- Do not use C `free(buffer)` for memory that a JNI function requires **`ReleaseStringUTFChars`** for.
- `Get<PrimitiveType>ArrayElements` functions have corresponding release functions; they may return a copy or a pinned region depending on the implementation.
- When using `GetPrimitiveArrayCritical`, blocking operations between `Get` and `Release` should be strictly restricted per the JNI contract.
- In a native loop creating thousands of JNI local refs, manage refs in batches or use `PushLocalFrame`/`PopLocalFrame` instead of accumulating them unboundedly.

## 6. `JNIEnv*` is bound to a thread and must not be shared arbitrarily

JNI `JNIEnv*` is only valid on the **current thread**. Do not use an `env` pointer obtained on thread A to make JNI calls from thread B.

```text
Java thread A → native f() → JNIEnv* envA
Java thread B → native f() → JNIEnv* envB

envA MUST NOT be used in a C function executing on thread B.
JNI local references also have their own thread/lifetime constraints.
```

C code can have C static/global variables shared between threads within a process. However, that does not make `JNIEnv*` or JNI local refs thread-safe globals; shared C data requires proper synchronization.

### 6.1. When a native library creates its own OS thread

A thread created by `pthread_create` or a Windows native API **does not automatically have permission to call the JVM's JNI APIs**. A native thread wanting to call Java must:

1. Obtain the appropriate `JavaVM*`, for example via `GetJavaVM` in a valid JNI context.
2. From the new native thread, call **`AttachCurrentThread`** to receive that thread's own `JNIEnv*`.
3. Use JNI according to the thread's local refs and exception state rules.
4. Call **`DetachCurrentThread`** when finished and before the thread exits, per the API contract.

An attached thread must have appropriate stack capacity, configured according to the OS thread API/ABI. `DetachCurrentThread` must not be performed in a state where Java frames remain on the stack, violating API restrictions.

**A Java call into a native method does not automatically create a new thread.** Creating a thread is a separate decision of the native library if it has code that does so.

## 7. A pending Java exception is different from a C error that crashes the process

JNI has `Throw` / `ThrowNew`, `ExceptionCheck` / `ExceptionOccurred`, and `ExceptionClear`.

### 7.1. `ThrowNew` is not equivalent to C++ stack unwinding

When `ThrowNew` succeeds, JNI marks a **Java exception as pending**. The native function **does not automatically jump into a Java `catch` right in the middle of C execution**. It must return to the JVM or handle the pending exception according to JNI restrictions; many JNI functions must not be called while an exception is pending.

```text
C: ThrowNew(...)
     │
     ▼
pending Java Throwable on the JNI thread
     │
     ▼
C method returns execution control to the JVM
     │
     ▼
JVM finds Java exception handler or unwinds Java frames
```

In the example, Java `requireNonNegative(-1)` does not complete normally; the JVM runs `catch` in `main`.

### 7.2. C `SIGSEGV` is different from Java `NullPointerException`

If C dereferences an invalid address, has a use-after-free, buffer overflow, or mixes allocators incorrectly, the consequence may be:

- A Unix signal such as `SIGSEGV`.
- A Windows access violation.
- A fatal error log `hs_err_pid...log` written by HotSpot if possible.
- A full-process crash or hard-to-detect memory corruption.

**Java `try/catch(Exception)` is not guaranteed to rescue a process from a native crash.** The Java bytecode verifier is not capable of checking arbitrary C pointer accesses.

## 8. Native stack overflow, OOM, and Java heap limits

Platform threads can consume significant native address space and memory due to stacks and thread management structures. An application creating too many threads may report an error unable to allocate a native thread even while Java heap is still available.

Common JVM tool:

```bash
java -Xss1m MyApp
```

`-Xss` configures the Java thread stack size in supporting JVMs, but **does not guarantee that the native C stack of every thread — especially threads created by C libraries themselves — is exactly 1 MiB**. OS thread stack layout, guard pages, and stack reservation vary by implementation.

Do not assume increasing `-Xmx` solves native OOM. `-Xmx` is for the Java heap; native stack resources, direct memory, JNI allocations, and process limits are items that must be evaluated separately.

### 8.1. Java recursion and C recursion

- Java recursion can exhaust the JVM stack and throw `StackOverflowError`.
- Deep C recursion can exceed the native stack, leading to a crash or other errors depending on OS/JVM.
- A chain of JNI callbacks can interleave Java/native code and jointly put pressure on execution stack resources.
- Do not use an “infinite native recursion” test in a production application or a shared IDE session to measure stack size; there is a risk of killing the entire JVM.

## 9. Diagnosing the native boundary in practice

Useful Java/HotSpot commands:

```bash
java -version

# View Java thread dump, do not assume every native C frame will be visible:
jcmd <pid> Thread.print

# Check some additional JNI behaviors (HotSpot):
java -Xcheck:jni -Djava.library.path=. -cp out NativeBoundaryDemo

# Native Memory Tracking must be enabled at JVM startup:
java -XX:NativeMemoryTracking=summary -Djava.library.path=. -cp out NativeBoundaryDemo

# While the process with NMT is still running:
jcmd <pid> VM.native_memory summary
```

**Important limitations:**

- `jcmd Thread.print` helps view Java frames/thread states, and does not replace GDB/LLDB/WinDbg for viewing all native C stack frames.
- `-Xcheck:jni` can detect many errors in using JNI APIs, but **does not prove that all C code is free of buffer overflows/data races**.
- HotSpot Native Memory Tracking (**NMT**) only tracks native memory sources within HotSpot tracking scope; **it does not promise to see every `malloc` from inside every third-party native library**.
- `jcmd VM.native_memory` only works properly when the JVM has enabled NMT with the appropriate mode at startup.
- When the JVM crashes, read **`hs_err_pid...log`, core dump, native backtrace, and debugger symbols** instead of only looking for a Java exception stack trace.

### 9.1. `UnsatisfiedLinkError`

Usually occurs when:

- The shared library name/path does not match `System.loadLibrary` or `java.library.path`.
- `.dll` / `.so` / `.dylib` has the wrong architecture/ABI compared to the JVM.
- The JNI C symbol does not match the Java class name, package, method, or overloaded signature.
- Other shared library dependencies are missing.
- The library file is rejected by the OS loader due to corresponding policy/permission.

`UnsatisfiedLinkError` belongs to the `LinkageError` group; it does not indicate that the Java heap is out of memory. When changing a Java signature, you must recompile **both the generated header and the C library**, or update `RegisterNatives` if using dynamic registration.

## 10. JNI, DirectByteBuffer, and FFM API are not synonymous

JNI is a long-standing interoperability mechanism for Java to run native code and callback into the JVM. Java also has `ByteBuffer.allocateDirect` to use direct buffers, but a direct buffer is not a “native method stack”; it is primarily related to storage outside the heap and buffer management APIs.

In modern Java, the **Foreign Function & Memory (FFM) API** provides a different approach to native functions/memory. FFM became a standard feature in **Java 22**. One should not take a Java 22 FFM example and promote it as a standard API usable identically on Java 17 without differences in feature status, modules, flags, and lifecycle.

Regardless of the API, native code must still respect **ABI, memory ownership, stack/thread context, resource lifetime, and safety rules**. No mechanism automatically turns every raw C pointer access into Java GC-safe operations.

## 11. Common misconceptions

1. **“The native method stack resides in the Java heap.”** False: native stacks and the Java heap have different roles/runtime allocations.
2. **“Every JVM has a strictly independent physical native method stack.”** False: JVMS allows multiple implementation approaches.
3. **“Every native call creates a new thread.”** False: normally the current Java thread crosses the boundary.
4. **“A native method still has `Code` containing a Java bytecode body.”** False: an `ACC_NATIVE` method does not have a `Code` body like a normal Java method.
5. **“`jobject` is a C pointer that can be dereferenced into a Java object layout.”** False: it is a JNI reference per the VM contract.
6. **“`JNIEnv*` is shared between threads.”** False: the interface pointer belongs to the current thread.
7. **“A C global holding a `jobject` automatically gives the reference a global lifetime.”** False: `NewGlobalRef` must be used to extend a valid JNI reference.
8. **“The native method stack is all native/off-heap memory.”** False: off-heap includes many regions such as `malloc` and direct buffers.
9. **“GC will automatically `free` all C allocations.”** False: `malloc` requires `free`/library-specific release.
10. **“`jstring` always points to a null-terminated C UTF-8 string.”** False: use JNI string APIs and understand Modified UTF-8.
11. **“`ThrowNew` immediately exits the C function with a C++ exception.”** False: a pending Java exception is a separate mechanism.
12. **“Java catch can catch any `SIGSEGV` from JNI.”** False: a C native crash can terminate the JVM process.
13. **“A larger `-Xmx` fixes native stack OOM.”** False: heap and native resources have separate limits.
14. **“`-Xss` forces the stack of every C thread to have the same size on every OS.”** There is no cross-platform guarantee.
15. **“`Thread.print` contains all C frames.”** False: a Java thread dump does not replace a native debugger.
16. **“`-Xcheck:jni` detects all memory corruption.”** False: it only has a specific scope of JNI checks.
17. **“JNI local references stay alive forever if C does not call `DeleteLocalRef`.”** False: they usually become invalid after the native return.
18. **“Passing a `String` through JNI means copying the entire object onto the native stack.”** False: normally a JNI handle is passed; data access uses other APIs.
19. **“A native method can only return numbers and cannot call back into Java.”** False: JNI `Call...Method` supports callbacks per contract.
20. **“On Java 17, FFM is already a Java standard API equivalent to Java 22.”** False: feature status must be distinguished by release.

## 12. Self-check and answers

**Question 1.** Must the native method stack exist as a separate memory area on every JVM?

**Answer:** No. JVMS allows implementations to use conventional stacks to support native methods and does not mandate a separate physical structure.

**Question 2.** For `static native int add(int,int)`, what does the C JNI function receive before the two `jint`s?

**Answer:** `JNIEnv *env` and `jclass clazz`. An instance native method receives `jobject receiver` instead of `jclass`.

**Question 3.** In the example, does `twiceViaJava(9)` call back into Java code from C?

**Answer:** Yes. JNI `CallStaticIntMethod` calls `doubleValue(9)`, returns `18`, and then C returns `18` to the Java caller.

**Question 4.** Does `ThrowNew` in C behave like `areturn`?

**Answer:** No. It signals a pending Java exception, leading to the exceptional path when control returns to the JVM.

**Question 5.** Why is storing a local `jobject` in a C static variable unsafe to use after the native method returns?

**Answer:** A JNI local reference is only valid for the lifetime of the appropriate local-reference frame/thread, and does not automatically extend with the storage duration of a C variable.

**Question 6.** If a self-created native thread wants to call Java, what must be handled?

**Answer:** Use `JavaVM*` and `AttachCurrentThread` to obtain that thread's own `JNIEnv*`; use the proper APIs and `DetachCurrentThread` when finished per contract.

**Question 7.** A JNI library `malloc`s 2 GiB and forgets to `free`. Will a low Java heap `-Xmx` automatically decide to release that 2 GiB?

**Answer:** No. Native memory ownership is independent; JVM GC does not automatically `free` arbitrary C allocations.

**Question 8.** C accesses a freed pointer and causes `SIGSEGV`. Is Java `try/catch(RuntimeException)` guaranteed to save it?

**Answer:** No. A native crash can terminate the entire process; native diagnostics and fixing C memory safety are required.

**Question 9.** Why can `jcmd Thread.print` and a GDB native backtrace differ?

**Answer:** One focuses on Java thread/logical frames, while the other is based on the native machine call stack, ABI, and debug symbols.

**Question 10.** Does `-Xcheck:jni` guarantee a native application is completely safe?

**Answer:** No; it is an aid to detect some JNI API violations, not a general memory-safety verifier for C/C++.

**Question 11.** Can `jstring` be passed directly to C `strlen` via a cast?

**Answer:** No. Appropriate JNI string APIs must be used and released; `GetStringUTFChars` uses Modified UTF-8.

**Question 12.** Does increasing `-Xmx` completely solve an error where a native thread cannot be created?

**Answer:** No. One must check native address space, OS/process thread limits, native stacks, and actual memory allocations.

## 13. Remember by diagram

```text
Java platform thread
   │
   ├─ Java method frames (JVM stack model)
   │       └─ invoke native declaration
   │
   ▼
JVM / JNI transition
   ├─ thread-bound JNI interface: JNIEnv*
   ├─ primitive arguments and opaque JNI object handles
   └─ native function link / platform ABI
   │
   ▼
C/native function execution
   ├─ C stack/registers (implementation/compiler dependent)
   ├─ C malloc/free for native heap
   ├─ JNI refs to Java heap objects
   ├─ may callback Java via JNI
   └─ return value or pending Java exception
   │
   ▼
JVM returns control to Java caller
   ├─ normal typed result
   └─ exception handler/unwinding

GC manages Java heap; JNI manages reference contracts;
the native allocator and OS manage their own parts.
```

**Key takeaway:** The native method stack supports running native/VM code when the implementation uses conventional stacks. It is not where all Java objects live, nor is it a synonym for all off-heap regions. Across the Java ↔ native boundary, JVM/JNI manages argument passing, JNI handle lifetime, exception state, and thread identity. Native code can interact with the JVM but still carries memory-safety/ABI risks that do not exist in verified Java bytecode. When diagnosing, combine Java thread dumps, JNI checks, NMT within its limits, and a native debugger.

### References

- [JVMS Java SE 17, §2.5.6 — Native Method Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.6).
- [JVMS Java SE 17, `2.5.2 / `2.6 — JVM Stacks and Frames](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6).
- [JVMS Java SE 17, §4 — ACC_NATIVE and Code attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html).
- [Java SE 17 JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html).
- [Java SE 17 JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html).
- [Java SE 17 JNI Specification — Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html).
- [JDK 17 javac Documentation, `-h`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [JDK 17 Troubleshooting, `-Xcheck:jni`](https://docs.oracle.com/en/java/javase/17/troubleshoot/command-line-options1.html).
