# Intrinsics and Dependencies on CPU Architecture, JDK, and Implementation

## 1. What problem do intrinsics solve?

An **intrinsic** in HotSpot is a mechanism where the JVM/JIT recognizes a known Java library method or operation and **may** replace the normal compilation/execution path with **specialized compiler IR, custom-written machine code, or a runtime stub**. This optimization leverages the compiler's knowledge of the library, CPU, and runtime to perform equivalent work faster.

For example, operations that can potentially be implemented by HotSpot using intrinsics on suitable hardware include:

- Bit counting: `Integer.bitCount`, counting leading/trailing zero bits.
- `Math.sqrt`, `Math.fma`, and some exact arithmetic operations.
- `System.arraycopy`, array/string comparisons via specialized paths.
- Checksums `CRC32`, `CRC32C`; AES/SHA and suitable crypto processing algorithms.
- Some internal operations of BigInteger, Base64, runtime, and atomic operations.

**The most important word is "may".** Having a candidate method does not mean every call will be intrinsified. HotSpot must consider the JDK version, CPU platform, flag configuration, compiler tier, method/call-site, JIT compilation state, input shape, and guards.

**Three distinct layers:**

1. **Java API contract:** results, exceptions, and behaviors that must be preserved.
2. **HotSpot implementation:** which methods have an intrinsic ID, which compiler/stub supports them, and which flags are enabled.
3. **CPU/operating system:** ISA extensions and the VM's ability to use those features.

~~~text
Java code:
  x = Integer.bitCount(mask);
              |
              v
      Library method call
              |
              v
  HotSpot recognizes candidate?
       /               \
      No               Yes
      |                 |
      v                 v
 Normal path     Intrinsic path available?
                         /       \
                       Yes        No
                        |          |
                        v          v
                   Target IR/   Fallback
                   stub/code   library code
                        |          |
                        +-----+----+
                              |
                              v
                     Same Java result
~~~

**Intrinsics are not a mandatory part of the JVMS.** Java bytecode is portable according to JVM semantics; native compiled code is CPU/JVM-dependent.

## 2. Distinguishing intrinsics from method inlining

**Inlining** usually expands the callee's body into the caller's compiler IR. **Intrinsification** replaces/special-cases an operation with code or IR specifically known to HotSpot; it may not resemble the callee's Java body.

~~~java
static int addOne(int x) {
    return x + 1;
}

static int compute(int n) {
    return addOne(n) * 2;
}
~~~

The two methods above are illustrative, not a standalone runnable Java file.

- With **inlining**, the optimizer can bring the `addOne` body into `compute` and see a single expression `(n + 1) * 2`.
- With an **intrinsic**, for example `Integer.bitCount`, the optimizer can use a specialized bit-count node or instruction sequence without needing to execute step-by-step like the Java library bytecode.

| Criterion | Inlining | Intrinsic |
| --- | --- | --- |
| Principle | Expands callee IR at call site | Replaces/special-cases with VM-known representation |
| Relies on method body? | Usually yes | Not necessarily |
| Requires special CPU instruction? | No | Not required; may use multiple instructions/stub |
| Can be combined? | Yes | Yes |
| Guaranteed for every call? | No | No |
| Must preserve Java semantics? | Yes | Yes |

**You cannot infer** from `javap -c` still showing `invokestatic` that the JIT is not using an intrinsic: `javap` inspects **class-file bytecode**, not optimized native code.

## 3. `@IntrinsicCandidate` is an internal annotation, not a directive forcing the JIT

OpenJDK has `jdk.internal.vm.annotation.IntrinsicCandidate`. The documentation in the annotation source states:

- An annotated method/constructor **may be intrinsified by HotSpot**.
- The annotation **does not guarantee** that the intrinsic is actually used on all platforms/configurations.
- It is intended only for **JDK library maintainers**, not as a stable API for applications.
- When the library/HotSpot changes, maintainers must ensure compatible checks and semantics.
- With `CheckIntrinsics`, HotSpot can verify consistency between annotated methods and the VM intrinsics list during class loading.

Do not write:

~~~java
// DO NOT use in normal applications:
// @jdk.internal.vm.annotation.IntrinsicCandidate
// public static int fastWork(int x) { ... }
~~~

The internal annotation **does not automatically create a HotSpot intrinsic implementation** for a custom-written method. Even importing the internal package `jdk.internal.*` violates the goal of a portable Java application and may be restricted by the module system.

### Where is the intrinsic ID list?

In the HotSpot source, `src/hotspot/share/classfile/vmIntrinsics.hpp` describes the intrinsic IDs, method signatures, and related conditions. It distinguishes between intrinsics **that are replaced by the compiler with code/IR** and **bytecode intrinsics** that the compiler handles specially in another way.

This catalog changes across JDK releases. Code on the OpenJDK `master` branch may differ from JDK 17 or JDK 25 on your machine; check the exact **corresponding tag/branch** when researching in detail.

## 4. Preserving exact Java semantics is mandatory

Every optimization must preserve the **results and observable behavior protected by the Java API**.

| Target | Semantics that must be preserved |
| --- | --- |
| `Integer.bitCount` | Accurately counts the number of 1-bits in binary representation |
| `Math.fma` | **Fused** multiply-add rounding, must not be arbitrarily replaced by two separately rounded operations |
| `Math.addExact` | Throws `ArithmeticException` on integer overflow |
| `System.arraycopy` | Bounds/null/type checks, overlap handling, partial copy on type mismatch |
| Crypto digest | Algorithm/provider semantics and correct output bytes |
| Atomic/volatile | Java Memory Model, appropriate atomicity and ordering |
| Arrays/reference ops | Object identity, type safety, GC write barriers when needed |

OpenJDK `IntrinsicCandidate` notes that the intrinsic path may not itself perform the exact same checks as the Java method body **if checks are already on the caller path or in an equivalent guard**. However, the entire execution path must satisfy the contract; one cannot "optimize" by allowing out-of-bounds access or returning an incorrect checksum.

**A compiler intrinsic does not mean a single CPU instruction.** It can be an IR node that expands into multiple machine instructions, a call to a special native stub, or a specialized code branch with a fallback.

## 5. CPU and ISA extensions dependencies

A machine instruction only exists if the actual CPU supports the corresponding feature and the VM is permitted to use it. Examples of instruction families:

| Hardware capability | Example ISA group | Java operation that may be supported |
| --- | --- | --- |
| Population count | x86 POPCNT, ARM bit-count operations | `Integer.bitCount` |
| Leading/trailing zero count | x86 LZCNT/TZCNT/BSR or AArch64 CLZ and other idioms | `numberOfLeadingZeros`, `numberOfTrailingZeros` |
| SIMD/vector | SSE/AVX on x86, NEON/SVE on suitable ARM | Arrays/strings/vectorized routines |
| AES acceleration | AES-NI on some x86, ARM crypto extensions | AES implementations |
| CRC | CRC instructions on supporting CPUs | CRC32C or corresponding checksum paths |
| SHA acceleration | SHA extensions of suitable CPUs | SHA provider code paths |
| Fused multiply-add | x86 FMA or ARM64 FMA | `Math.fma` on suitable HotSpot |

**Especially easy to confuse:** the x86 CPU instruction named `CRC32` belongs to the appropriate CRC-32C (Castagnoli) family, **it does not by default mean the IEEE CRC32 of `java.util.zip.CRC32`**. The JVM must use the correct algorithm; the two have different polynomials.

Having the same x86-64 architecture does not mean every chip has AVX-512, AES-NI, FMA, or POPCNT; extensions depend on the CPU generation and feature bits. In virtual machines/hypervisors, some features may also be masked.

### Fallback when CPU instructions are unavailable

~~~text
Java API contract (unchanged)
              |
              v
HotSpot looks for hardware/VM-supported fast path
        /                \
       Yes                No
       |                   |
  specialized          ordinary optimized code /
  instruction/stub     library/software fallback
       |                   |
       +---------+---------+
                 |
                 v
         Correct observable result
~~~

The lack of acceleration **does not mean the Java API must fail**. Java code calling `Integer.bitCount` or `CRC32.update` still has a valid implementation on a suitable JVM/platform, although the speed may differ.

## 6. Intrinsics can vary by JDK and compiler

With the same Java binary, environments can differ across multiple dimensions:

- **JDK release:** the list of intrinsics, library methods, signatures, and compiler improvements change.
- **JVM vendor:** HotSpot, OpenJ9, and other runtimes have different implementations/flags.
- **Compiler:** HotSpot C1, C2, JVMCI/Graal have different intrinsification capabilities and policies.
- **CPU/OS:** hardware features, platform backends, instruction selection, and calling conventions differ.
- **JVM flags:** UseXXXIntrinsics groups can be enabled/disabled depending on configuration.
- **Runtime state:** whether the method is hot yet, whether the JIT has compiled it yet, and whether the call-site shape and input types are suitable.
- **Provider:** a `MessageDigest` or `Cipher` may use a different provider with a different code path.

A method **known to the JVM as an intrinsic candidate** can still be executed via the bytecode/library path if it is not yet compiled or the intrinsic path is unavailable at a specific call site.

**Differences in codegen do not mean different Java results.** On HotSpot JDK 17 and JDK 25, the native instruction sequence may differ, but the application must still observe the semantics of the Java API.

## 7. Bit intrinsics example: invariant results

The expressions:

~~~java
int bits = Integer.bitCount(0xF0F0F0F0);
int leading = Integer.numberOfLeadingZeros(1);
int trailing = Long.numberOfTrailingZeros(1L << 40);
~~~

Are illustrative statements, not a standalone program. According to Java semantics:

- `0xF0F0F0F0` has 4 bytes of F0, each byte having 4 1-bits, so `bitCount` returns **16**.
- 1 in 32 bits has **31 leading zeros**.
- `1L << 40` has its first bit at position 40 counting from the LSB, so trailing zeros is **40**.

On CPUs with suitable POPCNT/LZCNT/TZCNT/CLZ, the JIT may generate optimized instructions. Do not infer backwards from the results 16/31/40 which CPU opcode was executed: constant folding or fallback can also produce the same result.

## 8. `Math.fma` and `Math.addExact` illustrate correctness constraints

### Fused multiply-add

~~~java
double v = Math.fma(2.0, 3.0, 4.0); // 10.0
~~~

`Math.fma` has fused semantics: the result is equivalent to multiplication and addition with a single rounding step per the API contract, rather than arbitrarily substituting multiplication followed by addition with two rounding steps. For some floating-point inputs, `a * b + c` can produce a different result from `Math.fma(a,b,c)`.

The Oracle JDK 25 `java` manual describes `-XX:+UseFMA` for hardware-based FMA intrinsics on systems with suitable instructions (e.g., supporting Intel/ARM64 CPUs). On CPUs lacking the FMA extension, the VM must use a compatible implementation if the API is still supported.

### Exact arithmetic

~~~java
Math.addExact(Integer.MAX_VALUE, 1);
~~~

Per the API, that snippet **throws `ArithmeticException`**. Oracle JDK 25 describes the `-XX:+UseMathExactIntrinsics` group. An intrinsic can accelerate the operation with overflow checking, but **must not** turn it into `int` wraparound and silently return `Integer.MIN_VALUE`.

## 9. `System.arraycopy`: cannot be a blind memcpy

`System.arraycopy` is a classic example of an operation that can be deeply optimized by the JVM but must preserve these conditions:

- Check that source/destination are arrays and non-null.
- Check positions, length, bounds, and array component types.
- If source/destination overlap, preserve a result equivalent to copying through a temporary region.
- For reference arrays, check assignability; if the k-th element has the wrong type, the valid prefix before it may still be copied and then `ArrayStoreException` is thrown.
- For arrays containing references, appropriate GC barriers/card marking are needed so the object graph remains valid.

Example:

~~~java
int[] a = {1, 2, 3, 4, 5};
System.arraycopy(a, 0, a, 1, 4);
// a = [1, 1, 2, 3, 4]
~~~

If a forward-copy routine without overlap handling were used, the result could be wrong. An arraycopy intrinsic must choose the right direction/code path/guard, or fall back.

**Not every `System.arraycopy` will go through the exact same stub.** Array type, length, alignment, overlap, CPU, GC, and compiler decisions can all affect it.

## 10. CRC, SHA, AES, and HotSpot flags

The Oracle JDK 25 `java` manual lists the intrinsic groups:

| Operation group | Flag in JDK 25 manual | Dependency |
| --- | --- | --- |
| CRC32 | `-XX:+UseCRC32Intrinsics` | CPU/backend support |
| CRC32C | `-XX:+UseCRC32CIntrinsics` | CPU/backend support |
| AES | `-XX:+UseAES`, `-XX:+UseAESIntrinsics` | Hardware AES extension |
| AES/CTR | `-XX:+UseAESCTRIntrinsics` | Algorithm/mode/hardware |
| GHASH | `-XX:+UseGHASHIntrinsics` | Crypto platform |
| SHA | `-XX:+UseSHA`, `-XX:+UseSHA256Intrinsics` and variants | CPU/provider |
| Base64 | `-XX:+UseBASE64Intrinsics` | JVM/platform support |
| Adler32 | `-XX:+UseAdler32Intrinsics` | Build/platform |
| Math exact | `-XX:+UseMathExactIntrinsics` | Compiler path |
| BigInteger | `UseMultiplyToLenIntrinsic` and other groups | Architecture/compiler |

**JDK 25 requires `-XX:+UnlockDiagnosticVMOptions` for the intrinsic-controlling flags listed in the manual.** Example:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:-UseCRC32Intrinsics ChecksumIntrinsicDemo
~~~

Flags only take effect when supported by the VM; they do not conjure hardware instructions if the CPU lacks them. When using another JDK version, check the docs/`java -version`.

### SHA provider is not a minor detail

`MessageDigest.getInstance("SHA-256")` obtains the algorithm from a Java Security provider. Oracle JDK 25 has restrictions regarding SHA hardware intrinsic paths on the appropriate `sun.security.provider.Sun` provider. Therefore **do not claim that every third-party provider is accelerated** by the same HotSpot intrinsic.

**Intrinsics do not make a cryptographic algorithm safer by design.** Algorithm, mode, key, nonce, provider, and side-channel considerations still need to be handled properly.

## 11. Java 17+ runnable: bit, math, arraycopy, mismatch

Create the file **`IntrinsicBasicsDemo.java`**:

~~~java
import java.util.Arrays;

public class IntrinsicBasicsDemo {
    public static void main(String[] args) {
        System.out.println("bitcount=" + Integer.bitCount(0xF0F0F0F0));
        System.out.println("leading=" + Integer.numberOfLeadingZeros(1));
        System.out.println("trailing=" + Long.numberOfTrailingZeros(1L << 40));

        System.out.println("sqrt=" + Math.sqrt(81.0));
        System.out.println("fma=" + Math.fma(2.0, 3.0, 4.0));

        int[] source = {10, 20, 30, 40};
        int[] dest = new int[3];
        System.arraycopy(source, 1, dest, 0, 3);
        System.out.println("copied=" + Arrays.toString(dest));

        byte[] left = {1, 2, 3};
        byte[] right = {1, 2, 4};
        System.out.println("mismatch=" + Arrays.mismatch(left, right));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -g IntrinsicBasicsDemo.java
java IntrinsicBasicsDemo
~~~

**Exact stdout when the program completes normally:**

~~~text
bitcount=16
leading=31
trailing=40
sqrt=9.0
fma=10.0
copied=[20, 30, 40]
mismatch=2
~~~

This exercise demonstrates **Java API semantics**, **not** proof that the JVM emits POPCNT, FMA, or SIMD opcodes. The JIT may constant-fold because the inputs are fixed. Running `javap -c -p IntrinsicBasicsDemo` only inspects bytecode, not compiled native instructions.

## 12. Java 17+ runnable: CRC32, CRC32C, and SHA-256

Create the file **`ChecksumIntrinsicDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.zip.CRC32;
import java.util.zip.CRC32C;

public class ChecksumIntrinsicDemo {
    public static void main(String[] args)
            throws NoSuchAlgorithmException {
        byte[] data = "123456789".getBytes(StandardCharsets.US_ASCII);

        CRC32 crc32 = new CRC32();
        crc32.update(data, 0, data.length);
        System.out.printf("crc32=%08x%n", crc32.getValue());

        CRC32C crc32c = new CRC32C();
        crc32c.update(data, 0, data.length);
        System.out.printf("crc32c=%08x%n", crc32c.getValue());

        byte[] sha = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.US_ASCII));
        System.out.println("sha256=" + HexFormat.of().formatHex(sha));
    }
}
~~~

Run:

~~~bash
javac -g ChecksumIntrinsicDemo.java
java ChecksumIntrinsicDemo
~~~

**Standard stdout on a JDK with an available SHA-256 provider:**

~~~text
crc32=cbf43926
crc32c=e3069283
sha256=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

The two CRCs have **different polynomials** so their standard results differ; SHA-256 of the ASCII string `abc` is a common test vector. If the runtime is configured without a SHA-256 provider, the method may throw `NoSuchAlgorithmException`, not an intrinsic causing a wrong digest.

Try with flags when supported by HotSpot:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:-UseCRC32Intrinsics ChecksumIntrinsicDemo
java -XX:+UnlockDiagnosticVMOptions -XX:-UseCRC32CIntrinsics ChecksumIntrinsicDemo
~~~

**The API results remain correct** when the program runs successfully. Changing flags only changes the code paths the VM is permitted to use, not the algorithms or test vectors.

## 13. Java 17+ runnable: exceptions are still preserved

Create the file **`ArrayCopySemanticsDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayCopySemanticsDemo {
    public static void main(String[] args) {
        int[] overlap = {1, 2, 3, 4, 5};
        System.arraycopy(overlap, 0, overlap, 1, 4);
        System.out.println("overlap=" + Arrays.toString(overlap));

        Object[] mixed = {"ok", Integer.valueOf(17)};
        String[] target = new String[2];
        try {
            System.arraycopy(mixed, 0, target, 0, 2);
            System.out.println("unexpected-success");
        } catch (ArrayStoreException e) {
            System.out.println("caught=ArrayStoreException");
        }
        System.out.println("partial=" + Arrays.toString(target));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println("unexpected-success");
        } catch (ArithmeticException e) {
            System.out.println("caught=ArithmeticException");
        }
    }
}
~~~

~~~bash
javac -g ArrayCopySemanticsDemo.java
java ArrayCopySemanticsDemo
~~~

**Exact stdout:**

~~~text
overlap=[1, 1, 2, 3, 4]
caught=ArrayStoreException
partial=[ok, null]
caught=ArithmeticException
~~~

In arraycopy from `Object[]` to `String[]`, `"ok"` is copied first, then `Integer` is rejected, so target contains `[ok, null]`. `addExact` must throw an exception on overflow. **Whether HotSpot uses intrinsics or fallback, these results must remain valid**.

## 14. Enabled flags differ from proving an intrinsic actually runs

There are four independent questions:

1. **Does the JVM know the intrinsic ID?** — `vmIntrinsics.hpp` source for the exact JDK version.
2. **Do CPU/flags allow it?** — platform detection/VM initialization.
3. **Does the compiler/runtime choose the intrinsic at this call site?** — profiling, tier, hotness, inputs, fallback.
4. **What is the actual native code?** — compiler logs, disassembly, or appropriate profiling.

A flag `UseCRC32Intrinsics=true` only indicates **the configuration allows it**, not that the `CRC32.update` method at the site you are studying actually went through a hardware instruction.

The same method can:

- Run interpreted because it is not hot enough yet.
- Be compiled by C1 without using a special C2 optimization path.
- Be compiled and intrinsified by C2.
- Be constant-folded because of fixed inputs.
- Call a specialized runtime stub.
- Use a fallback when the CPU lacks instructions or flags are disabled.

**Do not assume "intrinsics only work in C2" for every VM operation.** HotSpot has both compiler intrinsics and runtime/library special-case paths, and each tier/build has different capabilities.

## 15. Guide to observing HotSpot

Start from the real version/flags:

~~~bash
java -version
java -Xlog:help
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintFlagsFinal -version
~~~

You can view compilation/inlining:

~~~bash
java -XX:+PrintCompilation IntrinsicBasicsDemo
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation IntrinsicBasicsDemo
~~~

**Diagnostics may add log lines**, so the entire process stdout when they are enabled will no longer consist solely of the program's output lines.

| Tool | Shows | Does not prove |
| --- | --- | --- |
| `java -version` | Vendor, JDK release, VM | Which call site uses an intrinsic |
| `PrintFlagsFinal` | VM flag values | That a compiled method used acceleration |
| `PrintCompilation` | Method compile events | Specific CPU instruction |
| `PrintInlining` | Inlining decisions | That every intrinsic path ran |
| `LogCompilation` | Compiler log when supported | Standard runtime when logging is enabled |
| `PrintAssembly` + hsdis | Machine code via supporting tool | Entire program/call sites if not captured completely |
| JFR and profiler | Runtime behavior/alloc/CPU | Intrinsic codegen without instruction evidence |
| JMH | Performance microbenchmark | Guarantee that an intrinsic was used |

The Oracle JDK 25 `java` manual describes that `PrintAssembly` may require an external `hsdis` library. It is not mandatory to download binaries from unknown sources. On non-HotSpot JVMs, `-XX` flags may not exist or may have different semantics.

### Fine-grained intrinsic controls

In OpenJDK HotSpot, `vmIntrinsics.hpp` has control mechanisms such as `ControlIntrinsic` / `DisableIntrinsic` alongside the `UseXXXIntrinsics` group. The ID list and syntax depend on the VM version, so **do not guess intrinsic ID names from Java method names** to test in production. Using documented official group flags is easier to verify.

## 16. Measuring intrinsic performance properly

A program that only prints `Integer.bitCount(0xFF)` **is not a POPCNT benchmark**, because the compiler can precompute the value at compile time. To study performance:

1. Use **JMH** with appropriate warmup/measurement iterations/forks.
2. Generate inputs that vary at runtime, reflecting real sizes and distributions.
3. Use Blackhole or consumption to avoid dead-code elimination.
4. Compare **the same JDK/CPU/workload** and change only one supported VM flag.
5. Avoid `println` or verbose logs inside the measured region.
6. Record the compiler tier, CPU ISA, provider, and JVM flags.
7. Inspect compiled machine code if the goal is to confirm opcode/ISA.
8. Report variance, throughput/latency, not just a single number from a single run.

**Intrinsics are not always faster:** with very small inputs, startup or guard/stub overhead dominates, and another code path may be equivalent or better. Changing CPU/JDK/provider at the same time makes the comparison unable to isolate the cause.

### Production troubleshooting

If CRC/SHA throughput differs between nodes:

- Record `java -version` and `UseCRC32Intrinsics`/`UseSHA*Intrinsics` flags.
- Check CPU feature masks, virtualization/hypervisor.
- Check the actual Java Security provider selected.
- Compare compiled code/profiles on a warmed-up workload.
- Look at CPU frequency, system load, GC, and I/O to avoid attributing every difference to intrinsics.

Do not toggle disable/enable intrinsics in production before verifying in a test environment.

## 17. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "An intrinsic is a new bytecode." | Usually a VM/compiler special case for a method/operation. |
| "`@IntrinsicCandidate` forces HotSpot to use it." | Only marks a candidate, does not guarantee. |
| "Annotating a custom method creates an intrinsic." | No; an implementation in the VM is required. |
| "One intrinsic is always one CPU instruction." | Can be IR, multiple instructions, or a stub. |
| "Intrinsic = inlining." | No, they can work together but are different mechanisms. |
| "Intrinsics are always faster." | Needs benchmarking on the specific workload/CPU/JDK. |
| "All x86-64 CPUs have AES-NI/AVX-512." | ISA extensions depend on hardware and feature masks. |
| "The CRC32 CPU instruction is Java CRC32." | x86 CRC32 corresponds to the CRC32C polynomial in the appropriate context. |
| "JDK 17 and 25 must generate the same machine code." | Compiler/library/backend change across releases. |
| "C1 and C2 support identical intrinsics." | They can differ. |
| "`javap -c` showing calls proves no intrinsic." | `javap` only inspects bytecode. |
| "Flag UseXXX=true proves the opcode ran." | Only indicates conditions may allow it. |
| "Disabling CRC32 intrinsic changes the checksum." | The Java API contract does not change. |
| "`Math.fma` is always equivalent to `a*b+c` in rounding." | Fused semantics can differ. |
| "Arraycopy intrinsic can skip type checks." | Exception/partial copy semantics must be preserved. |
| "A CPU lacking AES makes Java Cipher always fail." | A provider can use a correct software implementation. |
| "All SHA providers use the same HotSpot intrinsic." | Provider/code path matters. |
| "Using a JNI native method automatically becomes an intrinsic." | JNI and compiler intrinsics are different. |
| "JMH alone proves the CPU instruction." | JMH measures performance; codegen evidence is needed. |
| "-XX flags are part of the Java standard." | Vendor-specific, may differ by build/version. |
| "Fast crypto via intrinsic means mode/key design is secure." | Security requirements are independent of speed. |

## 18. Self-check with answers

**1.** What is an intrinsic?  
**Answer:** HotSpot may special-case a method/operation via compiler IR, machine code, or a runtime stub for optimization.

**2.** Does `@IntrinsicCandidate` guarantee intrinsification?  
**Answer:** No. Runtime CPU/JDK/compiler/flags determine availability.

**3.** How do intrinsics and inlining differ?  
**Answer:** Inlining expands the callee body into the caller; an intrinsic uses a VM-known specialized implementation.

**4.** Why do different CPU bitcount instructions on x86 and ARM still give the same Java result?  
**Answer:** Java API semantics are fixed, while the machine instruction sequence is chosen by the backend.

**5.** How does `Math.fma` differ from `a*b+c`?  
**Answer:** Fused rounding semantics can differ from two rounding steps.

**6.** Are CRC32 and CRC32C of `123456789` the same?  
**Answer:** No: `cbf43926` and `e3069283` respectively.

**7.** What happens if arraycopy copies a String and then encounters an Integer incompatible with String[]?  
**Answer:** The valid prefix may have already been copied; then `ArrayStoreException` is thrown.

**8.** Does `UseCRC32Intrinsics=true` prove the JIT used CPU CRC?  
**Answer:** No; the call site and compiled code must be verified.

**9.** Does a JVM lacking hardware AES extension force the Java AES API not to run?  
**Answer:** No; the implementation/provider can use a suitable software path.

**10.** Why are intrinsic benchmark numbers easily skewed when inputs are constants?  
**Answer:** The JIT can constant-fold or eliminate the work, not measuring the real operation.

**11.** On the same CPU, can two JDK releases differ in intrinsic availability?  
**Answer:** Yes, because VM source, policies, flags, libraries, and compilers change.

**12.** How to verify actual CPU instructions?  
**Answer:** Inspect appropriate compiled-code disassembly/profiling on the exact VM/JDK, not just Java stdout or `javap`.

## 19. References

- [OpenJDK — IntrinsicCandidate.java](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/jdk/internal/vm/annotation/IntrinsicCandidate.java): internal annotation, non-guarantee conditions for intrinsics, and preserving semantics.
- [OpenJDK HotSpot — vmIntrinsics.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/classfile/vmIntrinsics.hpp): intrinsic IDs, controls, and feature dependence.
- [Oracle JDK 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): UseAES/CRC32/CRC32C/SHA/FMA/MathExact flags, UnlockDiagnosticVMOptions, PrintCompilation, and PrintInlining.
- [OpenJDK HotSpot — globals.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/globals.hpp): implementation flags; master branch may differ from the running JDK version.
- [Java SE 25 — System.arraycopy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)): checks, overlap, and partial-copy behavior.
- [Java SE 25 — Math.fma](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#fma(double,double,double)): fused multiply-add semantics.
- [Java SE 25 — Integer.bitCount](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#bitCount(int)): bit count result contract.
- [Java SE 25 — CRC32](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/CRC32.html) and [CRC32C](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/CRC32C.html): two different checksum algorithms.
- [Java SE 25 — Arrays.mismatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#mismatch(byte[],byte[])): first differing index.
- [Java SE 25 — MessageDigest](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html): algorithm/provider behavior.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): measuring JVM performance after controlled warmup.

**Conclusion:** An intrinsic is a way HotSpot **may** execute a method through a special implementation, exploiting VM/compiler knowledge or CPU ISA. Actual availability depends on **CPU, JDK release, VM implementation, provider, flags, and JIT state**, but **results, exceptions, and Java API constraints must not change**. Do not confuse intrinsics with inlining, JNI, vectorization, or a single opcode; do not infer from source code, bytecode, or an enabled flag that the CPU actually executes the corresponding intrinsic.