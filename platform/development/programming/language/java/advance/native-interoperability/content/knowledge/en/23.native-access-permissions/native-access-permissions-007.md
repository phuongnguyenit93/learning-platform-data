# Native access permissions do not verify C signatures or library safety

When Java calls a function in a C/C++ library via the Foreign Function & Memory API (FFM) or Java Native Interface (JNI), being granted **native access permissions** only means that the application is allowed to perform certain risky operations such as loading libraries and linking native calls. This permission **does not prove** that the function description on the Java side matches the binary signature of the C function, that the passed data is valid, that pointers are still alive, or that the library is trustworthy. An allowed call can still corrupt data, corrupt memory, or cause the entire JVM to terminate abnormally.

**Objectives:** distinguish permission control from ABI contract checking; know how to read a C signature and cross-check `FunctionDescriptor`; understand risks when loading libraries; design ways to test and isolate native code.

## 1. Four independent questions at the Java ↔ native boundary

| Question | Related mechanism | What it does not guarantee |
| --- | --- | --- |
| Does Java code have permission to perform restricted native operations? | `--enable-native-access` for the appropriate module; JDK policy for restricted methods/JNI | Does not verify the C signature, library origin, or input data |
| Is the library/symbol found? | `System.loadLibrary`/`System.load` (JNI), `SymbolLookup` and the OS loader (FFM) | Finding a symbol does not prove it is the intended function or the right version |
| Under what ABI will Java pass arguments and receive results? | `Linker`, `FunctionDescriptor`, `MemoryLayout`, `MethodHandle` (FFM); JNI declarations and corresponding C code | The linker has no authoritative C declaration to match against automatically |
| Does the native code behave safely and according to contract? | Library design, testing, input validation, memory management, source/distribution auditing | The JVM cannot guarantee the safety of arbitrary machine code running in the same process |

These are different layers. For example, `findOrThrow("strlen")` confirms finding the symbol address according to the chosen lookup; `downcallHandle(...)` builds the calling mechanism according to the description **provided by the Java author**. These two steps do not read the C prototype to confirm the actual number or types of parameters.

On the Java side, `invokeExact` checks the Java argument types against the `MethodType` of the method handle. That only confirms the call matches the **signature declared for the handle**, not that the handle matches the underlying native function.

## 2. Native permission is an authorization boundary, not a safety certification

FFM became a standard API in **JDK 22**. Operations such as creating a downcall handle, creating an upcall stub, loading a native library via `SymbolLookup.libraryLookup`, and certain memory region reinterpretation operations are marked as **restricted** because misuse can break JVM integrity. Starting from **JDK 24**, native loading/linking operations related to JNI are also subject to the native access warning/permission policy.

For a program placed on the classpath, the way to run while proactively granting permission to unnamed modules is:

~~~bash
java --enable-native-access=ALL-UNNAMED SafeNativeCall
~~~

For code in a named module `com.example.bridge`, it can be granted more narrowly:

~~~bash
java --enable-native-access=com.example.bridge --module-path mods -m com.example.bridge/com.example.bridge.Main
~~~

Only use the second command when the module structure, module name, and main class match the actual project. `ALL-UNNAMED` grants permission to **all** unnamed modules on the classpath; it does not select an individual JAR. Prefer named modules when possible to limit the scope allowed to call restricted methods.

In **JDK 24/25**, if permission is not granted, the default policy is to warn for unauthorized native operations; `--illegal-native-access=deny` can be used to detect them via an `IllegalCallerException`. The default policy may become stricter in later JDKs, so check the documentation for the exact version being deployed. Do not rely on "still running despite warnings" as a long-term contract.

**Key takeaway:** `--enable-native-access` does not scan native bytecode, does not check library digital signatures, does not sandbox C/C++, does not verify `FunctionDescriptor`, and does not prevent a native function from intentionally reading/writing memory that the process is allowed to access.

## 3. Why can't Linker automatically verify C function signatures?

Consider the standard C function:

~~~c
size_t strlen(const char *s);
~~~

A dynamic symbol usually provides a **name and address**, without carrying standard metadata for Java to know for sure that it takes a `char*` and returns `size_t`. ABI (Application Binary Interface) information depends on the operating system, architecture, compiler, and how the library was compiled. `Linker.nativeLinker()` understands the calling convention of the current platform, but **does not know the true prototype** of the symbol the application chooses.

For calls via FFM, the author must accurately model:

- **Return type and each argument type:** `int`, `long`, `size_t`, `double`, pointer, structs returned by value.
- **Width/alignment per ABI:** for example, C `long` is usually 64-bit on Linux/x64 but 32-bit on Windows/x64; `size_t` is usually 64-bit on both of these 64-bit platforms. Do not infer C `long` from Java `long` by name.
- **Pointers:** `char *` is usually represented by `ValueLayout.ADDRESS` and the Java carrier is `MemorySegment`; there must still be agreement on encoding, NUL-termination, valid length, nullability, ownership, and lifetime.
- **Struct/union/array:** the layout must reflect padding, alignment, and the ABI's struct passing/returning rules, not just summing the sizes of individual fields.
- **Variadic functions and callbacks:** need to consider promotion rules/`Linker.Option.firstVariadicArg`, calling convention, callback function pointers, keeping callbacks alive, and allowed calling threads.
- **C++:** exported symbol names, name mangling, ABI, exceptions, and object layouts cannot be inferred from Java signatures. It is usually advisable to create an `extern "C"` interface layer with a stable contract if FFM must be used with a C++ library.

`linker.canonicalLayouts().get("size_t")` helps retrieve the C layout according to the current ABI. It **does not** verify that the chosen symbol actually returns `size_t`; that correspondence must still be based on the library's header/API contract.

## 4. Correct example: calling `strlen` via FFM on Linux/x86-64

Requirements: **JDK 22+**, this example targets **Linux x86-64** with `strlen` available in the default lookup, and `size_t` being 64 bits wide. On other operating systems/ABIs, confirm how to locate the library and C type mappings before using.

Save the file **`SafeNativeCall.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public class SafeNativeCall {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        MethodHandle strlen = linker.downcallHandle(
                linker.defaultLookup().findOrThrow("strlen"),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_LONG,
                        ValueLayout.ADDRESS
                )
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cString = arena.allocateFrom("Java");
            long length = (long) strlen.invokeExact(cString);
            System.out.println(length);
        }
    }
}
~~~

Compile and run in the same environment:

~~~bash
javac SafeNativeCall.java
java --enable-native-access=ALL-UNNAMED SafeNativeCall
~~~

Expected standard output on the stated environment:

~~~text
4
~~~

Step-by-step explanation:

1. `defaultLookup().findOrThrow("strlen")` finds the function **address** in the libraries exposed by the platform's native linker.
2. `FunctionDescriptor.of(JAVA_LONG, ADDRESS)` describes the call: returns a 64-bit value, takes an address. This is the matching mapping for `size_t strlen(const char *)` on Linux/x86-64, **chosen by the example author from the C contract**.
3. `arena.allocateFrom("Java")` creates a native memory region containing a NUL-terminated UTF-8 string, usable for this call. `Arena.ofConfined()` manages the memory lifecycle and restricts access to the owning thread.
4. `invokeExact(cString)` transitions to native. The value `4` is the number of **bytes** of the C string before NUL; for a UTF-8 string containing multi-byte characters, `strlen` does not return the number of Java/Unicode characters.
5. Upon exiting `try`, the arena is closed and the memory region is freed. This is safe here because `strlen` only reads during the call; do not apply this mechanically to native functions that **retain the pointer** after returning.

The example shows a properly modeled contract; it **does not prove that FFM can automatically detect every wrong description**.

## 5. Wrong example: Java description differs from C prototype

**The following snippet is for analysis only; DO NOT run it on a JVM or with real data.** Suppose we still call the `strlen` function above, but declare the return value as 32-bit:

~~~java
// WRONG on Linux/x86-64: strlen returns 64-bit size_t.
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS
);

// Do not create/invoke a downcall handle with this wrong descriptor.
~~~

`ValueLayout.JAVA_INT` makes an assumption about the return value that differs from the actual ABI. With short inputs, the result might look "right", keeping the bug hidden; in other situations it can be truncated or cause undefined behavior. More dangerous mismatches include: declaring too few/too many parameters, treating an integer as a pointer, wrong struct-by-value, wrong callback ABI, or pointing to a freed region. A mismatch can lead to reading/writing wrong addresses, corrupting heap/native memory, or crashing the JVM.

**The two types of checks do not replace each other:**

- `WrongMethodTypeException` can occur if **Java code** calls `invokeExact` with Java types that do not match the constructed method handle.
- A descriptor that is **valid in terms of syntax/linker** can still be **wrong relative to C**. The library is not forced to throw a clear Java exception; the result can be silently wrong or cause the process to crash.

Do not use crashes as a way to "verify signatures". Cross-check against the header and ABI, then test in an isolated environment.

## 6. A successfully loaded library can still be unsafe

At least three aspects need to be separated:

**Provenance and integrity.** A file named `libexample.so` or `example.dll` can be replaced via search paths, environment variables, distributions, or dependent libraries. Verify the vendor, version, build, download source, hash cross-checked from a trusted channel, and release signature when available. A hash matching one provided by the untrusted source itself does not create trust.

**Behavior on load and at runtime.** The native loader can trigger library initialization code before Java calls an intended function (for example, an initializer on Unix or a DLL entry point on Windows). The library can make OS calls, access resources with the process's permissions, spawn threads, modify memory, call other libraries, or contain vulnerabilities. `--enable-native-access` does not audit these behaviors.

**Matching contract but still logic bugs.** A `FunctionDescriptor` matching C does not prevent C from writing past `capacity`, keeping expired pointers, using unvalidated data, lacking thread synchronization, or using a library version that changes semantics. "Correct ABI" is a necessary condition for the call, not proof of security safety.

Hypothetical example:

~~~c
// The signature only specifies types, it does not guarantee the function respects capacity.
int fill_buffer(unsigned char *out, size_t capacity);
~~~

Java can pass the right pointer and length, but if `fill_buffer` writes `capacity + 1` bytes, neither native permissions, the linker, nor Java types can block the effect inside C.

## 7. Is JNI any different?

JNI usually declares a Java `native` method and implements the corresponding function in C/C++. The JVM knows the **Java** method signature; the C compiler can check the C declaration if the project uses the right header (for example, a header generated by `javac -h`). However:

- `System.load`/`System.loadLibrary` only loads the library according to search rules; it does not confirm the library is harmless.
- Checking the function name or Java method does not prove that the C code uses `JNIEnv*`, `jobject`/`jclass`, JNI data types, global/local reference lifecycles, or exception/thread handling rules correctly.
- Native code running in the JVM process can still cause memory corruption or crashes. The new JDK's native-access restrictions apply to loading/linking related to JNI, but do not turn C into Java-managed memory.

Therefore, the API differences between JNI and FFM do not change the principle: **permission to call ≠ correct signature ≠ trusted library ≠ safe execution**.

## 8. How to build a verifiable native boundary

When integrating a real library, follow this order:

1. **Lock down the C contract before writing Java.** Choose the header version and binary from the same build, documenting exported symbol names, types/constness, target ABI, ownership, nullability, lifetime, error returns, thread-safety, and semantics. For C++, wrap behind a stable C interface if feasible.
2. **Map each type per platform.** Compare C's `sizeof`/`alignof`/`offsetof` on the exact target build; use `canonicalLayouts()`, structs with appropriate padding, and verify return/argument layouts. Specifically check C `long`, `size_t`, `wchar_t`, struct-by-value, pointer-to-pointer, and variadic functions.
3. **Keep native permissions in a small adapter layer.** Centralize `Linker`/`SymbolLookup`, do not let every business module arbitrarily call native; grant specific modules when possible; do not distribute `ALL-UNNAMED` indiscriminately as a default.
4. **Control the loaded files.** Use approved releases, explicit paths, directories not writable by untrusted users; check accompanying native dependencies; pin compatible versions and control updates.
5. **Control memory and threads.** Determine who allocates/frees; do not retain `MemorySegment`/pointers past their expiration; check sizes and integer overflow; handle buffer length, UTF-8/NUL, null pointers, and callback lifetimes; do not call from the wrong thread with a confined arena.
6. **Test at the boundary.** Test zero/maximum lengths, multi-byte Unicode, errors and nulls per contract, abnormal inputs, concurrency, and version mismatches. Run native integration tests separately per OS/architecture and against the actual binary. When you control the C code, use ASan/UBSan or equivalent tools for test builds.
7. **Isolate high-risk libraries.** If the library cannot be trusted, consider calling it through a subprocess with a data protocol and restricted OS permissions. When the subprocess fails, the main JVM can observe and restart it instead of directly sharing the same address space.
8. **Observe at runtime.** Log the actual native library/version, error codes/`errno` when the API requires it; inspect JVM crash logs (`hs_err_pid...`), and JFR native-library load/unload events when supported. On appropriate JDKs, use `jnativescan` to detect signs of JNI usage; it is not a binary safety certification tool.

A Java wrapper should only expose a high-level API after it has validated parameters, established clear buffer ownership, and translated C errors into understandable results/exceptions. A wrapper working properly in one environment does not replace testing across all ABIs that the application supports.

## 9. Identifying errors and investigation directions

| Symptom | Questions to check first |
| --- | --- |
| `UnsatisfiedLinkError`, symbol/library not found | Name, directory, architecture, version, dependencies, exports; do not infer that the signature is right once this error is fixed |
| Native access warning or `IllegalCallerException` | Which module is calling the restricted method, which JDK/policy is running, has permission been granted to the right scope |
| `WrongMethodTypeException` | Do the carriers and Java types at `invokeExact` match the `MethodType` created from the descriptor |
| Wrong results on 32/64-bit or wrong only on one OS | `size_t`/`long`, signedness, packing/alignment, calling convention, and ABI version |
| JVM crash, corrupted data, or unstable errors | Wrong descriptor, pointer/lifetime, native buffer overflow, callback/thread, execution bug in the library; analyze crash logs and perform native debugging in an isolated environment |
| Library has the right name but exhibits strange behavior | Actual binary path, hash/release signature, transitively loaded dependencies, process permissions, and possibility of binary replacement |

`IllegalCallerException` is a **permission** symptom; `WrongMethodTypeException` is a **Java-side type** symptom; neither represents verification of the entire C contract or native safety.

## 10. Self-check of understanding

**Scenario A.** `--enable-native-access=ALL-UNNAMED` is enabled, `findOrThrow` finds the symbol, and `downcallHandle` is created successfully. Can we conclude `FunctionDescriptor` matches the C prototype? **No.** Corresponding header/ABI builds and testing are needed; the linker cannot automatically infer parameter types and counts from a symbol address.

**Scenario B.** `strlen("Tiếng Việt")` via FFM returns a different number than `String.length()`. Is it necessarily a signature bug? **No.** `strlen` counts UTF-8 bytes before NUL, whereas `String.length()` counts UTF-16 code units; the representations must be distinguished before diagnosing.

**Scenario C.** A library is signed by a valid vendor, and the C header matches the Java layout. Can it be considered completely safe? **No.** Trusted provenance and correct ABI reduce one group of risks; memory bugs, inputs, dependencies, execution permissions, lifecycle management, and isolation scope must still be examined.

**Scenario D.** A C method stores the input `char*` for use after returning. Should we pass a pointer from `Arena.ofConfined()` and close the arena immediately? **No.** The pointer retention contract must be followed, ensuring the memory region remains alive until native is finished and having a clear mechanism to end ownership.

## References

- [JDK 25 – Linker API and Safety considerations](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html)
- [JDK 25 – Restricted Methods and native access](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html)
- [dev.java – Foreign Function and Memory API](https://dev.java/learn/api/io/ffm/)
- [OpenJDK JEP 472 – Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)

**Practical conclusion:** Granting native permission is a decision to *allow crossing the JVM's managed boundary*. C/ABI signatures, binary trustworthiness, and memory safety must be verified by independent mechanisms; no permission flag does that job for you.