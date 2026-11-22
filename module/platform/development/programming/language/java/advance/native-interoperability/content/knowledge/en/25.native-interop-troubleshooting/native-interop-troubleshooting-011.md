# Isolating a Minimal Reproducible Example from a Large Application Before Concluding a JVM Bug

## Objectives

When a Java service using JNI or the Foreign Function & Memory API (FFM) encounters `UnsatisfiedLinkError`, `IllegalCallerException`, incorrect native results, or the JVM process terminates with `SIGSEGV` / `EXCEPTION_ACCESS_VIOLATION`, it is very easy to blame the JVM because the message appears in the `java` process. However, the bug may lie in the JVM configuration, the native library, the ABI, memory lifecycle, input data, the application, the operating system, or the JVM itself.

A **minimal reproducible example (MRE)** is the smallest set of code, data, and run commands that can reproduce **the exact phenomenon under investigation** in the described environment. It is necessary to minimize each part while preserving the exact trigger conditions, rather than creating an error that merely “looks like” the original error.

After this lesson, learners can:

- Identify the **error fingerprint** that must be preserved when reducing.
- Gradually strip away frameworks, databases, HTTP, dependencies, and business logic, while retaining the JNI/FFM conditions that are actually relevant.
- Run controlled experiments to distinguish configuration errors, native library bugs, application bugs, and JVM bug hypotheses.
- Prepare a reproduction package with sufficient information for others to re-run, verify, or report the incident.

## 1. “An Error in the Java Process” Does Not Yet Mean “a JVM Bug”

| Symptom | Initial meaning | What needs to be verified |
| --- | --- | --- |
| `UnsatisfiedLinkError` | Unable to load, find, or link the native library/function | Library name/path, binary matching OS/CPU, native dependencies, symbol name, JNI signature |
| Restricted native access warning / `IllegalCallerException` | Code executed a restricted native operation, but the module lacks permission under the JDK policy | JDK version and `--enable-native-access`, `--illegal-native-access` flags; the module making the call |
| `WrongMethodTypeException` / `IllegalArgumentException` in FFM | Java-side method handle, layout, argument, or API precondition may be mismatched | `FunctionDescriptor`, `MethodType`, size/alignment, lifetime, and passed values |
| Normal Java exception | A Java thread threw an exception; usually the JVM process stays alive | First stack trace, input, logic, and the library throwing the exception |
| `SIGSEGV` or `EXCEPTION_ACCESS_VIOLATION`, `hs_err_pid*.log` file | Fatal error causing the VM process to terminate | Problematic frame, native stack, crash dump, C/C++/JNI/FFM library, compiler/JIT, OS |
| Hang, wrong result, memory leak | May involve race, deadlock, memory safety, logic, or runtime | Thread dump, load pattern, run duration, resources, and repeatability |

**Insufficient evidence:** “Whenever native is called, the JVM crashes”; “the stack has `jvm.dll` so the bug is definitely in the JVM”; “adding `-Xint` makes the error go away so the JIT definitely has a bug”. For example, JNI code can corrupt memory and then crash in a JVM frame much later. A JVM flag change can also alter timing or layout, which only helps isolate the issue rather than proving the root cause.

## 2. Capture the Initial Baseline Before Modifying or Trimming

Every reduction needs a **reliable comparison point**. First, re-run the original version, and record the environment and symptoms. Do not change the JDK, flags, native binary, and input simultaneously and then use the result to draw conclusions.

### 2.1. Save the error fingerprint

Record at least four groups:

1. **Trigger:** operation, request/input, Java → JNI/FFM call path, step sequence, thread count, iteration count, random seed, and time of occurrence.
2. **Symptoms:** exception type and original stack trace; if the VM died, save the fatal error log (usually `hs_err_pid<process-id>.log`), problematic frame, signal, running thread, exit code, and time until crash.
3. **Environment:** JDK vendor + **full build/update**, VM name, OS, CPU architecture, container/base image, CPU/memory limits; native library version, architecture/ABI, and dependent native libraries.
4. **Run command:** exact path to the `java` binary, class path/module path, `-D` properties, `-X` / `-XX` flags, `--enable-native-access`, `--add-opens`, environment variables that may affect library search, and all inputs.

Reference commands, run with **the exact JDK of the failing application**:

```bash
java -version
javac -version
```

If the Java process is still running, HotSpot/JDK can provide:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.system_properties
```

The two `jcmd` commands are **syntax templates**; replace `<pid>` with the actual PID, which requires attach permissions and may not be available in some containers. Collect selectively because system properties and crash dumps may contain paths, tokens, and sensitive data. For runtimes running inside an IDE, Docker, or Gradle, do not assume `java` on `PATH` is the same JVM as the process; check the actual binary invoked.

### 2.2. Distinguish a fatal crash from a caught exception

- **Java Exception:** has a stack trace and can be caught (for example, `UnsatisfiedLinkError` is an `Error`). Merely seeing an exception is not sufficient evidence that the VM died.
- **Fatal VM crash:** usually produces a HotSpot fatal error log and the process terminates abnormally; `SIGSEGV` on Unix systems or `EXCEPTION_ACCESS_VIOLATION` on Windows are signs requiring native/runtime investigation.
- **Process killed by the OS:** may not generate `hs_err`, such as container out-of-memory or an external signal. Cross-check exit status, container events, and OS logs.
- **Wrong result or hang:** must not be turned into a crash just because it is hard to reproduce. Keep the exact same phenomenon type when creating an MRE.

## 3. Reduction Process: Keep the Trigger Intact, Remove Layer by Layer

Suppose a large application has the following flow:

```text
HTTP request
  -> Spring Controller
  -> Service / business rules
  -> Database / queue / cache
  -> JNI or FFM bridge
  -> libimage.so / image.dll / libimage.dylib
  -> native function reads buffer
  -> JVM dies or returns wrong result
```

The goal is not necessarily to delete every component. The goal is to find **the minimal set of conditions that still produces the same error**. Proceed sequentially:

1. **Freeze the baseline:** keep an original runnable version and configuration. Create an independent test copy to trim down; record the run command and result before/after each change.
2. **Replace the orchestration layer:** call the bridge directly from `public static void main(String[] args)`; remove HTTP, scheduler, DI, or framework if the error still persists.
3. **Replace the data source:** if possible, replace the database/remote API with a byte array, fixture file, or fixed input. Preserve the exact encoding, length, special values, endianness, and data order that the native side receives.
4. **Isolate the integration layer:** reduce down to a Java wrapper with `System.load(...)` / `System.loadLibrary(...)` or an FFM downcall, and the corresponding native library. Do not rush to remove the native library because it may be the component causing the bug.
5. **Trim the native side in a controlled way:** if you own the C/C++ source, reduce the native function to a smaller operation while **preserving the error**. For third-party libraries without source, keep the actual binary, version, checksum, and instructions to obtain it.
6. **Shrink concurrency/resources:** only remove threads or load if the error still appears; for race/UAF issues, thread count, interleaving, warm-up, or iteration frequency may be the trigger itself.
7. **Re-run the original at checkpoints:** when the minimal version loses the error, revert the most recent change, retry, and identify the dependency/condition that was removed too aggressively.

You can use **delta debugging**: split the set of dependencies/operations into two groups, temporarily remove one group, and run the test; if the same error still occurs, keep the trimmed version; if the error disappears, restore it and try the other group. Halving is only a search strategy; interdependent factors (for example, a native library + the matching layout) may need to be kept as a group. For intermittent errors, repeat enough times and compare occurrence rates before/after; **a single successful run does not prove the error has disappeared**.

### What does a real native MRE need to keep?

| Component | Keep only when relevant; examples |
| --- | --- |
| Java source | A class with `main()`, the JNI/FFM call snippet, data types, and the observed error |
| Native source/binary | Minimal C/C++ function or exact `.so`/`.dll`/`.dylib` file version, build method, and dependencies |
| Interface definition | `JNIEXPORT` signature; FFM `FunctionDescriptor`, `MemoryLayout`, calling convention, pointer ownership |
| Data | Byte sequence, charset, buffer size, offset, alignment, boundary values, iteration count |
| Runtime | JDK build and affecting flags, OS/CPU, binary architecture, library load path |
| Timing/resources | If it is a race: thread count, scheduling, warm-up, workload, container limits |

Do not replace a `downcallHandle` call with code that manually does `throw new RuntimeException(...)` to “reproduce the error”: even though an exception appears on the console, the origin point and mechanism are different. Similarly, replacing the native binary with a broken file so that `UnsatisfiedLinkError` appears does not prove you have reproduced the original crash.

## 4. Standalone Java Example: Isolating a Library Loading Error from the Application

Suppose a Spring Boot service reports `UnsatisfiedLinkError` when initializing a JNI wrapper. The first step is to **test the library loading operation in isolation**, without a controller, database, or server. The following example illustrates the error mechanism caused by a missing file; **this is an intentional environmental error, not evidence of a JVM bug**.

Create the file **`MinimalNativeLoad.java`**:

```java
import java.nio.file.Path;

public final class MinimalNativeLoad {
    public static void main(String[] args) {
        Path missingFile =
                Path.of("__missing_native_repro_93cf6f91__.bin")
                    .toAbsolutePath();

        try {
            System.load(missingFile.toString());
            System.out.println("UNEXPECTED: library loaded");
        } catch (UnsatisfiedLinkError error) {
            System.out.println("REPRODUCED: UnsatisfiedLinkError");
        }
    }
}
```

The code uses Java 17+ compatible syntax, while **the run command below is for JDK 24–25** because JNI native access control was expanded starting in JDK 24. Run in a directory **that does not contain a file** named `__missing_native_repro_93cf6f91__.bin`:

```bash
javac MinimalNativeLoad.java
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny MinimalNativeLoad
```

Expected stdout, if the file does not exist:

```text
REPRODUCED: UnsatisfiedLinkError
```

**Why are two flags needed in the run command?** On JDK 24–25, `System.load` is a restricted native operation. `--enable-native-access=ALL-UNNAMED` grants permission to classes running on the class path; `--illegal-native-access=deny` turns missing permission into an explicit error. Granting full permission allows the library loading step to proceed and fail specifically due to **the file not existing**. If tested without the native access flag in `deny` mode, the error may turn into `IllegalCallerException` before the JVM even checks the file; that is **a different trigger**.

This example only demonstrates that an MRE can be created for the **library loading error category**. When handling a real application, replace the dummy path with the exact path/binary having the problem and only consider it a successful reproduction when **the same stage and same meaningful symptom** occur. An `UnsatisfiedLinkError` due to “file not found” is different from an `UnsatisfiedLinkError` due to “undefined symbol” or a missing secondary native dependency, even though the exception class name is the same.

### Controlled checks are more valuable than merely seeing an exception

If the original version fails when loading a real library, check sequentially:

- Does the file actually exist at the path the application uses? `System.load` requires an absolute path; `System.loadLibrary` uses a logical name for the JVM to locate the library according to configuration.
- Does the binary match the OS/architecture (x64, aarch64), ABI, C runtime version, and dependencies?
- Does the JNI symbol have the exact name, linkage, and signature? For FFM, does the descriptor match the native function and memory region ownership/lifetime?
- Does the direct test command use the exact JDK and an equivalent set of flags as the original?

Platform-specific tools to inspect native dependencies include `ldd` (Linux), `otool -L` (macOS), and `dumpbin /DEPENDENTS` (Windows, when appropriate tools are available). They assist in diagnosing the binary; they are not automatic proof that the JVM is buggy.

## 5. Controlled Experiments: Change One Variable at a Time

Set a pass/fail criterion based on **the original error signature**, not merely on “the process exits non-zero”. For example, if the issue is a SIGSEGV in a native function after 100 calls, check whether it has the same crash type/stack and call conditions; an `IllegalCallerException` occurring earlier does not count as a reproduction.

The following table is an **experiment plan**; the result column is for the practitioner to record from the real environment, without assuming in advance:

| Run | Keep constant | Change exactly one factor | Question |
| --- | --- | --- | --- |
| A | Original app, JDK, input, native binary | No change (baseline) | At what rate does the error appear, and what is its signature? |
| B | JDK, flags, native binary, input | Replace HTTP/service with `main()` calling the bridge | Is the framework required for the error to occur? |
| C | JDK, flags, bridge, native binary | Replace database with fixed input | Is the exact byte buffer causing the error preserved? |
| D | MRE and input | Use a different native build, still same ABI | Does the error follow the native binary or not? |
| E | MRE and same native binary | Change one JDK build/update on an equivalent environment | Is there a difference related to the JVM version? |
| F | MRE and JDK | Add `-Xcheck:jni`, if using JNI | Does the JNI checker detect any operation violation? |

In comparisons, avoid changing two factors at the same time. If you need to try `-Xint` to see the difference when disabling the JIT, record it as an **isolation experiment**: the error disappearing could be due to the JIT, timing, or altered memory layout. Do not claim a JIT bug solely from that observation.

### When the error is nondeterministic

A small MRE may alter thread scheduling, speed, or memory layout and make a rare race appear less often. You should:

1. Keep comparable inputs/seeds and binary data; if timing relationships are a condition, record sufficient threads and sequences.
2. Fix warm-up, iteration count, and resources across each comparison run.
3. Record **failure count / total runs**, for example in a test report you can write it in the form “7/50”; this is only a formatting example, not an observed result of this lesson.
4. Increase or decrease concurrency step by step to find the threshold; when changing environments, keep the test identical to avoid noise.
5. If you cannot reduce further while keeping the same error, **stop at the smallest current MRE**. Do not force it into a single Java file by sacrificing the trigger.

## 6. Reading Crash Evidence in the JNI/FFM Context

For a HotSpot fatal error, first inspect `hs_err_pid*.log` or the file configured via `-XX:ErrorFile=...`. Pay attention to the header (signal, JDK build, problematic frame), current thread, native frames, loaded libraries, JVM flags, and OS. A crash dump/core file may be necessary when the stack is corrupted.

- **`C [libcustom.so+offset]`:** the crash point is currently in the native library. Investigate C/C++, dependencies, pointers, ABI, and the JNI contract first; still do not rule out data corrupted elsewhere.
- **`V [libjvm.so+offset]` / `V [jvm.dll+offset]`:** the crash is recorded in VM code. This is not enough to claim a JVM bug; an earlier native error can cause memory corruption and kill the JVM on a subsequent access.
- **`J ...`:** a JIT-compiled Java code frame, worth examining compiler/optimization, but you must still rule out data and native corruption.
- **No `hs_err`:** check whether the process actually hit a HotSpot fatal error or was killed by the OS, blocked by launcher/container, lacked log write permissions, or the JVM died before it could write the information.

For **JNI**, try enabling `-Xcheck:jni` on the same MRE:

```bash
java -Xcheck:jni --enable-native-access=ALL-UNNAMED MyJniRepro
```

`MyJniRepro` is an illustrative name; the command only runs when the corresponding class and native library are present. `-Xcheck:jni` can detect improper JNI usage and sometimes stops the VM upon detecting serious violations, but **it does not prove all native code is safe if it reports no errors**. For FFM, review the scope/lifetime of `Arena` / `MemorySegment`, valid pointers, alignment, and downcall/upcall signatures; errors on the native side are not guaranteed to be fully caught by the JVM.

If third-party native code causes a crash, you need the binary version and instructions on how to obtain it for reproduction. If you own the C/C++ code, you can add a build with symbols/debug information and use an appropriate native debugger, but note clearly that a debug build may change timing/layout compared to the original failing build.

## 7. When Is a “JVM Bug” Hypothesis Strong Enough to Report?

Consider it only a **strengthened hypothesis**, not yet a conclusion, when multiple pieces of evidence are present simultaneously:

1. There is a **consistent reproduction** of the same original error on a small MRE, with exact run commands and necessary data.
2. External factors have been ruled out or documented: missing native library, wrong ABI, JNI/FFM contract violation, API calls outside lifetime, data race, resource exhaustion, and OS/container differences.
3. Tested on an appropriate JDK update and a few controlled comparison configurations; if the error only appears on one build, state that exact build rather than claiming all JVMs are buggy.
4. Cross-checked known issues in [OpenJDK JBS](https://bugs.openjdk.org/) or the corresponding bug reporting channel, while avoiding conclusions based solely on similar exception names.
5. Provided enough evidence for others to run independently: source files, required native code/binary, compiler/SDK, build/run commands, expected/actual, reproduction rate, logs, and results of each trial.

A Java process crash **does not by itself confirm the JVM has a bug**; and an MRE running fine on another JDK **does not by itself prove the bug is in the original JDK** if the native binary, OS, workload, or timing was also changed at the same time.

### Standard reproduction package for sharing or reporting

A good bug report should have the following sections, with real data instead of guesses:

- **Summary:** exact phenomenon (exception, fatal crash, hang, wrong output) and the step where it occurs.
- **Reproduction environment:** Java vendor/build, OS/CPU, container, native library, and ABI.
- **Run conditions:** minimal file structure, how Java/native are built, full `javac`/`java` commands, all relevant flags.
- **Input and trigger:** minimal data, call order, thread/iteration count, seed, how the result is verified.
- **Expected vs actual:** expected behavior and observed behavior; include both exit code and log type.
- **Evidence:** stack trace or `hs_err`, core dump if available, JNI/FFM trace, output of controlled experiments.
- **Known limitations:** parts that could not be reduced further or uncontrolled environmental conditions.

Before sharing, strip personal data, secrets, internal paths, and sensitive information; however, do not modify input bytes, alignment, checksums, or trigger parameters to the point where the error disappears. When real data cannot be shared, state the limitation clearly and try to create a synthetic fixture with equivalent behavior.

## 8. Common Mistakes When Minimizing

1. **Keeping the same exception name without keeping the same cause.** Two `UnsatisfiedLinkError` instances can arise at completely different stages: file not found, missing dependency, or missing native symbol.
2. **Removing the native library too early.** If the error occurs due to a UAF pointer or ABI, a pure Java MRE no longer reproduces what needs to be diagnosed.
3. **Changing both the JDK and the native binary at once.** Losing the error afterward does not indicate which factor was decisive.
4. **Enabling/disabling multiple JVM flags at the same time.** In particular, `-Xint`, `-Xcheck:jni`, GC flags, and access flags can alter timing and execution paths.
5. **Trimming concurrency and claiming it is fixed.** A race may only appear with two threads, warm-up, or specific memory pressure.
6. **Discarding evidence in `catch`.** Merely printing “native error” without saving the exception message/stack in the investigation record loses an important signature.
7. **Concluding from a single run.** Rare errors require expressing probability/rate and number of trials.
8. **Providing source without build commands and environment.** With native interoperability, compiler, architecture, library lookup, and ABI are often part of the repro.

## Practical Conclusion

A reliable path is: **freeze the original error → capture environment and signature → remove unnecessary layers one by one → retain the smallest Java/native boundary that still triggers the error → run controlled comparisons → evaluate JVM bug evidence**. Successful reduction speeds up the investigation; more important than the number of lines of code is preserving the root cause and enabling others to reproduce the exact phenomenon.

## References

- [Oracle JDK 25 — Troubleshoot System Crashes](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-system-crashes.html): how to read fatal error logs, problematic frames, native errors, and JVM errors.
- [Oracle JDK 25 — Troubleshooting `-Xcheck:jni`](https://docs.oracle.com/en/java/javase/25/troubleshoot/command-line-options1.html): scope of JNI checks and diagnostic limitations.
- [Oracle — Submit a Bug Report](https://docs.oracle.com/en/java/javase/17/troubleshoot/submit-bug-report.html): capturing environment baselines, reducing tests, and recording reproduction commands.
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): impact of `--enable-native-access` and `--illegal-native-access` on JDK 24.
- [Oracle JDK 25 — Migrating from JDK 8 and Later](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): JNI/FFM native access and diagnostic tools.