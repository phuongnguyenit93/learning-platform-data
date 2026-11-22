# Comparing JNI and FFM with the Same Input Set, Results, and C Library

When migrating a native integration from **Java Native Interface (JNI)** to **Foreign Function & Memory API (FFM)**, simply being able to call a function is not enough to assert that the two binding approaches are equivalent. What needs to be proven is that **the same C library, the same business function, the same dataset, and the same error rules** produce the same results. Alongside a direct JNI–FFM comparison, there must be an **independent oracle** (for example, a pure Java algorithm) to avoid the situation where both binding paths return the same wrong result.

This article creates a single C shared library on **Linux x86-64**; JNI calls the C function through a JNI adapter, while FFM calls that C symbol directly. The Java program uses JDK **22 or later**, because FFM became a standard API in JDK 22 (JEP 454) in the java.lang.foreign package. JNI has been usable since many earlier JDKs; **the standard FFM code in this article does not compile on JDK 17**. Both calling approaches execute native code in the same JVM: pointer errors or memory corruption from C can still crash the entire process.

## 1. Defining the Criteria for “Two Equivalent Paths”

Fix the following variables before writing wrappers:

1. **One C source:** only one file containing the business function, compiled into a single file libbridge_compare.so. Do not re-implement the algorithm separately for JNI and FFM.
2. **One ABI:** the same C signature, calling convention, type sizes, parameter order, alignment, symbol name, and pointer ownership.
3. **One input set:** empty array; single-element array; negative numbers; large numbers at 32-bit boundaries; maximum valid length; invalid length.
4. **One output contract:** check the 64-bit integer result and error status code; map errors to the same Java exception type at the adapter layer.
5. **One independent oracle:** Java computes the expected value itself. If you only compare JNI == FFM, both paths could suffer from the same integer overflow or wrong offset read and still “PASS”.
6. **One reproducible environment:** record JDK, OS, architecture, compiler, build flags, native file path, version/hash, and JVM native access flags.

**Correctness** and **performance** must be evaluated separately. A parity test is not enough to claim that JNI or FFM is faster.

## 2. Common C Contract: Data, Result, Error

Choose the weighted sum calculation of a 32-bit integer array:

\[
\mathrm{weightedSum}(a)=\sum_{i=0}^{n-1}(i+1)\cdot a[i].
\]

C ABI signature:

~~~c
#include <stdint.h>

int32_t weighted_sum_i32(
    const int32_t *values,
    int32_t count,
    int64_t *result_out
);
~~~

Contract:

- **values** points to at least count int32_t elements that remain alive throughout the call; if count is 0, NULL may be passed.
- **count** is valid from 0 to 1024; negative numbers, exceeding 1024, or an invalid pointer under the input conditions are rejected.
- **result_out** must point to a valid 8-byte region to write the int64_t result; must not be NULL.
- **The C return value** is an int32_t status code: 0 on success, -1 on invalid parameters. The sum is written to *result_out; the return value is not used as the sum.
- The function **does not retain pointers**, does not modify input, does not allocate memory that outlives the return, does not invoke callbacks, and does not use global state.
- With count ≤ 1024, even if all elements have the maximum absolute value of a 32-bit signed integer, the weighted sum still stays within the int64_t range. This limit is chosen so the example does not depend on C signed overflow (undefined behavior).
- The demo uses the Linux x86-64 ABI, where int32_t is a 32-bit integer type, int64_t is a 64-bit integer, and pointers conform to the C ABI supported by the FFM linker. Switching OS/CPU/compiler requires re-checking calling convention, symbol export, and layout.

Returning **status separate from the result** is crucial: if -1 were returned as an error sentinel, a valid result equal to -1 would become ambiguous.

## 3. One C File Implementing the Business Function and JNI Adapter

Create the file **bridge_compare.c**:

~~~c
#include <stdint.h>
#include "CompareJniFfm.h"

enum { MAX_COUNT = 1024 };

// The single business function, called by both JNI and FFM.
int32_t weighted_sum_i32(
        const int32_t *values,
        int32_t count,
        int64_t *result_out) {

    if (result_out == NULL ||
            count < 0 ||
            count > MAX_COUNT ||
            (count > 0 && values == NULL)) {
        return -1;
    }

    int64_t sum = 0;
    for (int32_t i = 0; i < count; i++) {
        sum += (int64_t) values[i] * (int64_t) (i + 1);
    }
    *result_out = sum;
    return 0;
}

static void throw_invalid(JNIEnv *env) {
    jclass exception_class = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (exception_class != NULL) {
        (*env)->ThrowNew(
                env, exception_class, "native rejected input");
    }
}

// JNI adapter converts int[] to a pointer and then calls the business function above.
JNIEXPORT jlong JNICALL
Java_CompareJniFfm_jniSum(
        JNIEnv *env, jclass klass, jintArray input) {
    (void) klass;

    if (input == NULL) {
        throw_invalid(env);
        return 0;
    }

    jsize count = (*env)->GetArrayLength(env, input);
    jint *elements = NULL;

    if (count > 0) {
        elements = (*env)->GetIntArrayElements(env, input, NULL);
        if (elements == NULL) {
            // JNI failed to allocate the array; JVM reports the corresponding error.
            return 0;
        }
    }

    int64_t answer = 0;
    int32_t status = weighted_sum_i32(
            (const int32_t *) elements,
            (int32_t) count,
            &answer);

    if (elements != NULL) {
        (*env)->ReleaseIntArrayElements(
                env, input, elements, JNI_ABORT);
    }

    if (status != 0) {
        throw_invalid(env);
        return 0;
    }

    return (jlong) answer;
}
~~~

**Details to read accurately:**

- The header CompareJniFfm.h **is generated with javac -h** from the native method of the Java class in the next section. Do not guess JNI symbol names manually when the package or method name changes.
- JNI GetIntArrayElements may **pin or copy** the Java array depending on the JVM. You must not assume the returned address is always a direct address inside the Java heap.
- JNI_ABORT indicates that the wrapper only **reads** the data; it does not require copying changes from the native buffer back to the Java array. The Release operation must be performed after every successful GetIntArrayElements, even when C returns an error.
- The empty input case uses NULL/count=0 in accordance with the C contract; the C function does not dereference NULL.
- If GetIntArrayElements fails to allocate a buffer, JNI normally sets a pending exception; returning 0 here is only the value required by the JNI signature when an exception is pending, **not** a valid business value.
- The JNI adapter **does not compute the sum itself**, but directly calls weighted_sum_i32. FFM will call this exact function, avoiding having two versions of the C algorithm.
- The business function does not retain references after returning. If a real API retains pointers or processes asynchronously, you must not apply a short buffer lifetime as in this example.

GCC on Linux with default visibility exports the global C symbol weighted_sum_i32. When a project enables hidden visibility, the symbol must be exposed using an appropriate export annotation. If native code is compiled as C++, use extern "C" for the C ABI to avoid name mangling.

## 4. Java Program Calling Both Paths

Create the file **CompareJniFfm.java** in the **default package**. Both paths use the same library loaded by System.load. The program can be compiled on **JDK 22+**; the test example focuses on Linux x86-64.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Objects;

public final class CompareJniFfm {
    private static final int MAX_COUNT = 1024;

    static {
        System.load(Path.of("libbridge_compare.so")
                .toAbsolutePath().toString());
    }

    private static native long jniSum(int[] input);

    // Find the symbol in the exact library loaded by System.load
    // via this class's class loader.
    private static final MethodHandle C_SUM = bindCFunction();

    private static MethodHandle bindCFunction() {
        MemorySegment address = SymbolLookup.loaderLookup()
                .find("weighted_sum_i32")
                .orElseThrow(() -> new UnsatisfiedLinkError(
                        "C symbol weighted_sum_i32 is missing"));

        return Linker.nativeLinker().downcallHandle(
                address,
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT, // return int32_t status
                        ValueLayout.ADDRESS,  // const int32_t *values
                        ValueLayout.JAVA_INT, // int32_t count
                        ValueLayout.ADDRESS   // int64_t *result_out
                ));
    }

    private static long viaJni(int[] input) {
        Objects.requireNonNull(input, "input");
        return jniSum(input);
    }

    private static long viaFfm(int[] input) throws Throwable {
        Objects.requireNonNull(input, "input");

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cValues = input.length == 0
                    ? MemorySegment.NULL
                    : arena.allocateFrom(ValueLayout.JAVA_INT, input);
            MemorySegment cResult =
                    arena.allocate(ValueLayout.JAVA_LONG);

            int status = (int) C_SUM.invokeExact(
                    cValues, input.length, cResult);

            if (status != 0) {
                throw new IllegalArgumentException(
                        "native rejected input");
            }

            return cResult.get(ValueLayout.JAVA_LONG, 0);
        }
    }

    // Java reference calculation, independent of both JNI and FFM.
    private static long javaOracle(int[] input) {
        if (input.length > MAX_COUNT) {
            throw new IllegalArgumentException("too many elements");
        }

        long result = 0;
        for (int i = 0; i < input.length; i++) {
            result += (long) input[i] * (i + 1);
        }
        return result;
    }

    private static long verify(int[] input) throws Throwable {
        long expected = javaOracle(input);
        long jni = viaJni(input);
        long ffm = viaFfm(input);

        if (jni != expected || ffm != expected) {
            throw new AssertionError(
                    "Mismatch: input=" + Arrays.toString(input)
                    + ", expected=" + expected
                    + ", JNI=" + jni + ", FFM=" + ffm);
        }
        return expected;
    }

    private static boolean rejectedByJni(int[] input) {
        try {
            viaJni(input);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    private static boolean rejectedByFfm(int[] input)
            throws Throwable {
        try {
            viaFfm(input);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Throwable {
        int[][] samples = {
                {},
                {4},
                {1, 2, 3},
                {-3, 0, 4},
                {Integer.MAX_VALUE, Integer.MIN_VALUE}
        };

        for (int[] input : samples) {
            System.out.println(Arrays.toString(input)
                    + " -> " + verify(input));
        }

        int[] maximum = new int[MAX_COUNT];
        Arrays.fill(maximum, 2);
        System.out.println("1024 elements (all 2) -> "
                + verify(maximum));

        int[] oversized = new int[MAX_COUNT + 1];
        if (!rejectedByJni(oversized)
                || !rejectedByFfm(oversized)) {
            throw new AssertionError(
                    "1025 elements must be rejected by both paths");
        }
        System.out.println(
                "1025 elements -> JNI=REJECTED, FFM=REJECTED");
        System.out.println(
                "PASS: JNI and FFM match the Java oracle");
    }
}
~~~

### Why Is It Certain to Be the Same C Library?

System.load uses **the absolute path to a single file libbridge_compare.so**. At class initialization time, JNI links the method jniSum to the symbol Java_CompareJniFfm_jniSum in that file. Next, FFM's **SymbolLookup.loaderLookup()** looks up symbols in the libraries already loaded via System.load/System.loadLibrary by **the calling class loader**; therefore, FFM finds the business symbol weighted_sum_i32 from **the same loaded file**. There is no libraryLookup call to load another C library.

In JDK 22, loaderLookup only sees libraries within the scope of that class loader, and does not automatically scan all native libraries in the process. If using a multi-class-loader plugin system, you must verify the exact scope and lifetime of the loaded library.

### Decoding the Types in FunctionDescriptor

| C Parameter | FFM layout | MethodHandle Java Argument |
| --- | --- | --- |
| Return value int32_t status | JAVA_INT | int |
| const int32_t *values | ADDRESS | MemorySegment |
| int32_t count | JAVA_INT | int |
| int64_t *result_out | ADDRESS | MemorySegment |

On the target ABI, a pointer's MemorySegment holds a native address; the Java type long **must not be substituted** for ADDRESS just because pointers are also typically 8 bytes long on 64-bit platforms. In the same vein, cResult is allocated with **JAVA_LONG** because the memory cell holds an **int64_t value**, not a pointer.

MethodHandle.invokeExact must take exact **(MemorySegment, int, MemorySegment)** and return exact **int**, matching the descriptor; a type mismatch can cause WrongMethodTypeException, while a **wrong-ABI descriptor** can lead to memory corruption or a crash.

### Buffer Lifetime in Both Paths

- **JNI:** GetIntArrayElements creates a region that may be pinned/copied; C uses it synchronously and does not retain the pointer; ReleaseIntArrayElements with JNI_ABORT happens before Java receives the result.
- **FFM:** arena.allocateFrom(JAVA_INT, input) copies the integers into a native segment and allocates an additional int64_t slot for output; C uses them while the arena is alive; try-with-resources closes the arena after reading the result.
- **Empty input:** FFM passes MemorySegment.NULL, JNI passes NULL; C accepts NULL when count=0.
- **Error:** when status is non-zero, do not read cResult because C **does not guarantee writing output in the error case**. JNI also only returns a result when status==0.
- **Null Java array:** both wrappers viaJni/viaFfm normalize with Objects.requireNonNull before entering native; therefore both have the same NullPointerException at the Java boundary.

FFM has MemorySegment bounds/scope checks on the Java side, but C **does not automatically** become safe against wrong-sized pointers, use-after-free, or data races.

## 5. Compiling and Running on Linux x86-64

Prepare JDK **22 or newer**, GCC, and set JAVA_HOME to point to the right JDK directory. Both files bridge_compare.c and CompareJniFfm.java are in the same working directory.

~~~bash
# Verify the environment:
java -version
javac -version
gcc --version

# Compile Java, generate CompareJniFfm.h for JNI:
javac -h . CompareJniFfm.java

# Build a SINGLE library used for both paths:
gcc -std=c11 -O2 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  bridge_compare.c -o libbridge_compare.so

# Verify both the C API symbol and the JNI bridge:
nm -D libbridge_compare.so | grep -E \
  'weighted_sum_i32|Java_CompareJniFfm_jniSum'

# Run the comparison. Classpath code is granted native access:
java --enable-native-access=ALL-UNNAMED CompareJniFfm
~~~

The flag **--enable-native-access=ALL-UNNAMED** is required for restricted FFM calls such as Linker.downcallHandle in classpath code; for modular applications, enable it for the exact module name. The native access warning/restriction policy also changes across JDK releases, so you should not rely on an older JDK only printing a warning.

--enable-preview is not needed on JDK 22+ for the standard java.lang.foreign API. On JDK 17, JNI can run, but this FFM source cannot be compiled; if you want to test older JVMs, you need to separate a JNI-only version while keeping the same C library/test vectors.

**Expected output** of the program:

~~~text
[] -> 0
[4] -> 4
[1, 2, 3] -> 14
[-3, 0, 4] -> 9
[2147483647, -2147483648] -> -2147483649
1024 elements (all 2) -> 1049600
1025 elements -> JNI=REJECTED, FFM=REJECTED
PASS: JNI and FFM match the Java oracle
~~~

Three useful calculations to self-check:

- [1, 2, 3]: 1×1 + 2×2 + 3×3 = 14.
- [2147483647, -2147483648]: 2147483647 + 2×(-2147483648) = **-2147483649**, requiring long/int64_t.
- 1024 elements all equal to 2: 2×(1+2+...+1024) = 1024×1025 = **1049600**.

The program only prints **PASS** if both paths match the oracle for all valid inputs and both reject the 1025-element input with IllegalArgumentException. This is a parity test of a sample API; it does not prove that every other native API is equivalent.

### Troubleshooting Common Build Issues

- **JNI UnsatisfiedLinkError:** wrong export name Java_CompareJniFfm_jniSum, wrong package/class, .so file cannot be loaded, or invalid bitness. Regenerate the header with javac -h and inspect nm -D.
- **FFM reports missing weighted_sum_i32:** symbol is static/hidden or FFM is looking up in the wrong class loader. Check nm -D libbridge_compare.so and the order System.load → loaderLookup.
- **FFM WrongMethodTypeException:** Java types at invokeExact differ from the types required by MethodHandle; compare the entire descriptor, not just values.
- **IllegalCallerException/native-access warning:** missing native access configuration for the JDK/module.
- **C compile cannot find jni.h:** JAVA_HOME points to the wrong JDK, include/linux is missing, or the generated header is mistaken.
- **On macOS/Windows:** the .so extension, GCC flags/JNI headers, exports, and calling conventions differ. This is a **Linux build example**; do not run those commands verbatim on other operating systems.

## 6. Comparison Table of JNI and FFM on the Same Calculation

| Aspect | JNI | FFM (JDK 22+) | What to Verify |
| --- | --- | --- | --- |
| Business function | JNI adapter calls weighted_sum_i32 | MethodHandle calls weighted_sum_i32 directly | Same symbol in the same .so |
| Binding | Native method + header/symbol Java_... | Linker + SymbolLookup + FunctionDescriptor | Signature matches ABI |
| int[] data | GetIntArrayElements, may pin or copy | Arena.allocateFrom(JAVA_INT, input) copies into memory | Same order/signedness/length |
| Passing length | jsize → int32_t | Java int → JAVA_INT | No wrong offset or count |
| Result | C writes int64_t; JNI returns jlong | C writes int64_t; FFM reads JAVA_LONG | No 64-bit truncation |
| C error | JNI ThrowNew | Java checks status and throws | Same external exception type |
| Buffer management | ReleaseIntArrayElements(JNI_ABORT) | Arena closes after downcall | No pointer retained past lifetime |
| Native access | JNI rules and JVM version | Restricted linking API | Correct JVM flags for module/JDK |
| Callback | C calls Java via JNI | FFM upcall stub/MethodHandle | Demo has no callbacks yet |
| Concurrency | Depends on C/handle contract | Depends on C/handle contract | Binding does not make C automatically thread-safe |
| Packaging | C JNI glue + .so/.dll | Java descriptor + .so/.dll | Verify native build/distribution |
| Performance | Depends on call + copy/pin + release | Depends on linker + copy + arena | Separate benchmark after parity |

Do not conclude that FFM is always faster or always safer than JNI. FFM has an API that explicitly declares layout and scope; JNI uses a long-standing native API with deep customization capabilities. Suitability depends on JDK version, C ABI complexity, callback/ownership, native build, and actual workload.

## 7. Expanding the Test Suite to Catch Subtle Bridge Bugs

### Input Matrix

| Case | Example Input | Expected / Check |
| --- | --- | --- |
| Zero elements | [] | 0; NULL + count=0 is valid |
| One element | [4] | 4 |
| Order / weights | [1, 2, 3] | 14 |
| Negative numbers | [-3, 0, 4] | 9 |
| int32 boundaries | [MAX_INT, MIN_INT] | -2147483649 as long |
| Valid size boundary | 1024 elements all 2 | 1049600 |
| Exceeding max | 1025 elements | C status -1, Java IllegalArgumentException |
| Null Java array | null | Both Java wrappers throw NullPointerException |
| Repeated | Same sequence multiple times | Value does not depend on previous call state |
| Input mutated at caller | Change one element between two calls | New result matches new oracle |

For real systems, add property-based testing with a **fixed PRNG seed**, from which failing inputs can be reproduced. Keep the seed and minimal failing vector in logs. If you want to compare errors strictly, first define the public API contract including **exception type, error code, or message**; do not treat internal message differences as failures if the API only guarantees the error type.

### Data Invariance and Ownership

The business function declares const int32_t *values, so it **has no right to modify the input** by contract. However, with JNI, JNI_ABORT may discard changes made to a native copy; inspecting the Java array after the call **is not enough** to prove C never modified the native buffer. When strong verification is needed, instrument C/native tests with a separate buffer and inspect raw memory.

When C returns an error status, treat result_out as **having no guaranteed value**. If FFM reads the output before checking status, the test may occasionally fail or accidentally rely on uninitialized memory. The example checks status first.

For native APIs that return pointers or retain pointers asynchronously, expand the lifetime and data ownership contract before comparing JNI/FFM. In particular, closing an Arena does not mean C has stopped using the pointer. JNI Release also does not guarantee C has no separate thread still accessing the released region.

### Testing Crashes/Native Errors in an Isolated Process

Do not use a production-serving JVM to intentionally test invalid pointers, fake addresses, or use-after-free. Such violations can crash the entire JVM. Use a separate executable/test process with AddressSanitizer/LeakSanitizer or Valgrind depending on the platform when testing C code that actively violates memory safety.

## 8. Placing a Contract Test Suite Above Both Adapters

In a real system, instead of writing tests that only call JNI and then copying the logic to FFM tests, define a common interface:

~~~java
// Illustrates a test-oriented API, not a standalone program.
interface NativeWeightedSum {
    long calculate(int[] values);
}
~~~

Have both the JNI adapter and the FFM adapter implement the same interface. A standard parameterized test suite will:

1. Generate a valid input from a shared fixture set.
2. Compute expected using the Java oracle before calling native.
3. Pass **copies with identical content** to each adapter if the native API can modify input, or share an immutable input when the contract allows.
4. Compare both against expected, check error/edge cases, and verify cleanup on both success and exception paths.
5. Re-run the same fixtures across multiple threads **only when the real C API allows concurrent calls**.

Do not use the JNI output as the expected value for FFM: both paths call the same C algorithm and thus could share the same business bug. An independent oracle helps detect that case.

Some projects use Golden Data in JSON/CSV. For this integer problem, you must specify signedness and integer parsing, and not let serialization accidentally turn int64_t into a float or lose precision on large values.

## 9. Verifying ABI, Binaries, and Distribution Process

Identical Java code does not guarantee the same native artifact is loaded between dev and CI. Store build metadata alongside the .so:

~~~bash
# Run on a binary controlled and built by the team:
file libbridge_compare.so
nm -D libbridge_compare.so | grep weighted_sum_i32
ldd libbridge_compare.so
sha256sum libbridge_compare.so
~~~

Use ldd on trusted native binaries; do not run it carelessly on files of unknown origin. Compare hashes/versions and dependencies to know that staging/prod is not loading an outdated library by mistake. In CI/CD, there should be:

- A job that builds the shared C library with the target JDK's JNI headers.
- A job that compiles Java/JDK 22+ and runs the parity vector suite.
- Jobs testing officially supported ABIs/OSes/architectures, avoiding using a Linux artifact on Windows/macOS.
- Native unit tests to test the C algorithm independently of JNI/FFM.
- Smoke tests verifying the right symbol, load path, signed types, errors, and resource lifecycle.
- If there are older JDK JNI-only consumers, build/test that part separately, still calling **the same C API**.
- When compiler flags like -fvisibility=hidden, LTO, or C++ ABI are used, verify that exported symbols still have the exact expected names.

For structs or complex C ABIs, also add sizeof/alignof, offsets, and calling convention checks on both the C side and the FFM layout. Do not assume `long` in C is 64-bit on every OS; the example uses **int64_t** to set the exact size.

## 10. Performance: Measure After Confirming Parity

The current example **is not a benchmark**. JNI uses GetIntArrayElements (which may pin or copy), whereas the current FFM code **always copies** the Java int[] into a new Arena region. If you run many iterations and compare wall times directly, the results include copy, allocation, JNI release, and Arena close costs, not just native call overhead.

A meaningful benchmark should clearly define:

- **End-to-end latency:** preparing input, calling native, retrieving output, cleanup; close to the real cost of the public API.
- **Pure downcall overhead:** preparing buffers/method handles beforehand and measuring the call, while keeping buffers alive and respecting ownership constraints.
- **Throughput & contention:** whether concurrency is appropriate for the C API; thread count, buffer size, cache effects, native allocator.
- **JIT warm-up:** use JMH, multiple independent runs, consume results to avoid dead-code elimination, same JDK/CPU/OS/compiler.
- **Scope of conclusions:** report values, variance/percentiles where appropriate, and configuration; do not claim JNI/FFM is faster by default from a single experiment.

A program measuring “FFM vs JNI” that inadvertently measures two different marshalling strategies is still useful if the question is **end-to-end behavior**, but you cannot conclude from it about binding cost alone.

## 11. When the C API Has Strings, Structs, Handles, or Callbacks

The int32[] sample is intentionally simple. For real native interoperability, parity must also consider:

**Strings and Unicode.** JNI GetStringUTFChars uses **modified UTF-8**, which differs from standard UTF-8 in special cases. FFM arena.allocateFrom(String) on JDK 22 creates a NUL-terminated UTF-8 C string. To compare the exact same bytes, you must define the encoding: ASCII, Vietnamese, supplementary characters, embedded NUL, byte length, and release.

**Struct/union.** Check offset, alignment, padding, native endianness, C long/size_t types, and struct returns. FFM MemoryLayout is only correct when it accurately reflects the C ABI. A JNI adapter can also be wrong when doing manual memcpy or casts.

**Native handle/pointer.** Who creates, who closes/frees, does the handle have thread affinity, can a callback be used after close? Neither a JNI `jlong` holding an address nor an FFM MemorySegment helps C automatically free a leaked object. An Arena only manages memory within its own scope; it does not automatically free every pointer returned by C.

**Callback/upcall.** JNI needs the current thread's JNIEnv, attaching native threads when needed and managing references. An FFM upcall stub has a lifetime tied to an Arena; you must check reentrancy, exceptions, threads, and the lifetime scope of the callback pointer.

**C varargs and calling conventions.** Do not infer FunctionDescriptor from byte counts or parameter counts alone. Functions with unions, structs by value, errno, or varargs require dedicated API bindings and ABI tests.

Thus, the simple comparison example establishes **the methodology**; each real C API will have additional tests tailored to its specific data types and lifecycles.

## 12. Common Errors and Fixes

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| JNI runs but FFM cannot find weighted_sum_i32 | Symbol is hidden/static/mangled or wrong class loader | nm -D, linker export, loaderLookup |
| FFM throws WrongMethodTypeException | invokeExact uses wrong types for MethodHandle | Check (MemorySegment,int,MemorySegment)int |
| JVM crashes during downcall | FunctionDescriptor has wrong ABI or C accesses invalid pointer | Compare against C header, sanitizer in isolated process |
| JNI throws UnsatisfiedLinkError | Wrong Java_... name or library not loaded properly | javac -h, nm -D, check load path |
| FFM warns or throws IllegalCallerException | Native access not enabled for the right module | --enable-native-access flag per JDK |
| Fails only on MIN_VALUE/MAX_VALUE | Result truncated to int, wrong signedness | long oracle and boundary vectors |
| Same result but still wrong | JNI/FFM both hit a C bug or both misread input | Add independent Java oracle and expected values |
| Leak after tests | JNI missing Release or pointer retained after Arena.close | Check cleanup and native allocation profiler |
| Fails under concurrency | C has global state or unsafe shared handle | Thread policy docs and controlled stress tests |
| Passes on Linux but fails on Windows | Different ABI, .dll name, export, compiler | Platform-specific build/test matrix |
| Benchmark gives inconsistent results | Measuring copy/allocation/JIT instead of same workload | JMH, warm-up, separate marshalling from call |

## 13. Checklist for Finalizing Comparison Results

- [ ] Have a single C header/contract as the standard: function name, status, pointer, count, ownership, and type sizes.
- [ ] JNI and FFM both load/resolve **the same binary** and run the same C function.
- [ ] Have an independent Java oracle; both JNI and FFM are checked against expected.
- [ ] Include empty vector, negative numbers, ordering, 32-bit extremes, 64-bit result, size 1024, and size 1025.
- [ ] Error cases are compared per the Java contract; do not read result_out when C reports an error.
- [ ] JNI Get/Release and FFM Arena scope are fully managed; do not let C retain pointers past their lifetime.
- [ ] JNI header from javac -h and FFM descriptor match the exact same ABI.
- [ ] Java code and JNI/C build successfully on the specified JDK/OS; symbols/native access are verified.
- [ ] CI stores compiler/JDK/native library version/hash and reproducible test results.
- [ ] Benchmarks, if any, are a separate step, stating clearly whether measuring end-to-end API or downcall cost.
- [ ] If the real native API has callbacks/handles/thread affinity, have dedicated tests for lifecycle and concurrency.

**Conclusion:** Fix **the C function and the input set**, treat JNI/FFM as two binding mechanisms to be verified, and compare **each result and error behavior against an independent oracle**. Once the parity test passes edge cases, then evaluate maintainability, JDK support, and performance to choose between JNI and FFM.

### Technical References

- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): Standard FFM API since JDK 22.
- [JDK 22 SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): loaderLookup for libraries already loaded via JNI.
- [JDK 22 SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): allocation from int[] and String.
- [Oracle JDK 22 FFM Guide](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): FunctionDescriptor, Linker, Arena, and native access.
- [JNI Specification](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/index.html): symbol names, JNI arrays, exceptions, and reference lifetime.
