# Distinguishing Native Interoperability from Compiling Java to Machine Code or Native Image

## 1. Three Questions to Separate

In Java, the word **native** can refer to three different things:

1. **Native interoperability:** a Java program **calls or is called by code outside the Java runtime**, typically a C/C++ library or an operating system API. Main question: *How does Java communicate with foreign code?*
2. **Compiling Java code to machine code via JIT:** the JVM takes bytecode and can compile frequently executed sections into machine instructions **while the program is running**. Main question: *How does the JVM execute and optimize Java code?*
3. **Ahead-of-time (AOT) compilation to Native Image:** tools like **GraalVM Native Image** produce a machine code executable **before deployment**, typically running without starting a separate HotSpot JVM. Main question: *What type of file is the application packaged into and run with?*

**Core conclusion:** “Calling a native library” is about **connecting two worlds of code**; “Java compiled to native code” is about **how Java is executed or packaged**. They are conceptually independent and can coexist in the same application.

## 2. How Does Standard Java Execute?

For a standard Java program:

```text
.java file
   │ javac (compiled at build time)
   ▼
.class file / bytecode
   │ java (starts JVM)
   ▼
JVM: class loading, bytecode verification, interpretation and/or JIT
   │
   ▼
Machine instructions executed by CPU
```

- `javac` normally produces **bytecode** (`.class`), and **does not directly produce** a standalone executable like `.exe`.
- **JIT (Just-In-Time)** is an optimization capability of the JVM: “hot” methods can be compiled into machine code to run faster. A small program may finish before a method is JIT-compiled; not every line of Java is necessarily JIT-compiled.
- The fact that the CPU ultimately runs machine instructions **does not mean** the application called a C/C++ library provided by the programmer. The JVM itself must execute on the CPU, even when the application only uses pure Java.
- JIT is also not synonymous with Native Image: JIT machine code is generated **inside the JVM process at runtime**, whereas AOT machine code is generated **before the application runs**.

For example, `Math.addExact(7, 5)` is a Java API call; even if the JVM optimizes it with JIT, it is **not** an example of JNI or an FFI call explicitly declared by the application.

## 3. Native Interoperability: Crossing the Java ↔ Native Code Boundary

For example, a Java application may need to call an existing C library to handle a device, use an SDK that only provides a native API, or integrate an existing maintained C/C++ algorithm. In that case, an **interoperability mechanism** is needed to align function symbols, data types, pointers, memory, resource lifecycles, and the ABI (Application Binary Interface).

Common approaches:

- **JNI (Java Native Interface):** the long-standing standard interface of the JDK; Java declares a `native` method, and a C/C++ library exports the matching JNI function; calls can go in both directions, Java → native and native → Java. JNI requires careful handling of pointers, JNI references, threads, and exceptions.
- **Foreign Function & Memory API (FFM):** an API in `java.lang.foreign`, finalized as a standard feature in **JDK 22 (JEP 454)**. It allows accessing off-heap memory and calling foreign functions via function/type descriptors, without needing to write a C JNI layer for every call. Granting native access permissions and support depend on the JDK version and runtime environment.
- **JNA/JNR-FFI and wrappers:** third-party libraries that support native calls at different levels of abstraction; version and actual deployment capabilities should be checked.
- **IPC or network service calls:** Java can also communicate with a native program in *another process* using sockets, HTTP, or pipes. This is system integration, not an in-process native function call like JNI/FFM.

Merely marking a method `native` **does not compile all of Java to machine code**. It declares that **the method body is provided by the native environment**. The rest of the Java code can continue running under the standard JVM and be JIT-compiled as before.

### Minimal JNI Example, Buildable on JDK 17+

Create the file `NativeMath.java`:

```java
public final class NativeMath {
    static {
        System.loadLibrary("nativemath");
    }

    private static native int sum(int a, int b);

    public static void main(String[] args) {
        System.out.println("JNI: " + sum(7, 5));
    }
}
```

Generate the JNI header using the JDK:

```bash
javac -h . NativeMath.java
```

The command above compiles the Java class and generates `NativeMath.h`. Create `NativeMath.c` in the same directory:

```c
#include <jni.h>
#include "NativeMath.h"

JNIEXPORT jint JNICALL Java_NativeMath_sum(
        JNIEnv *env, jclass clazz, jint a, jint b) {
    (void) env;
    (void) clazz;
    return a + b;
}
```

On **Linux**, when `JAVA_HOME` points to the JDK directory and GCC is available:

```bash
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libnativemath.so NativeMath.c
java -Djava.library.path=. NativeMath
```

On **macOS** with Clang, replace the library compilation command with:

```bash
clang -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -o libnativemath.dylib NativeMath.c
java -Djava.library.path=. NativeMath
```

On **Windows**, from a *Developer Command Prompt* with MSVC and `JAVA_HOME` configured:

```bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" NativeMath.c /Fe:nativemath.dll
java -Djava.library.path=. NativeMath
```

When compiled properly and the library is loaded, **stdout** is:

```text
JNI: 12
```

Exact explanation of what just happened:

1. `javac` compiles `NativeMath.java` into `NativeMath.class` and generates the header declaring the corresponding JNI signature.
2. The C compiler creates the **platform shared library**: `libnativemath.so`, `libnativemath.dylib`, or `nativemath.dll`. This is the machine code part of the C function.
3. The JVM runs the Java bytecode, `System.loadLibrary("nativemath")` loads the library according to the OS naming convention, and `-Djava.library.path=.` adds the search directory.
4. The call `sum(7, 5)` crosses the Java/native boundary and returns a `jint` result to Java. The application is still running **inside the JVM**, even though one function is implemented in C.

If the library is missing, the CPU architecture is wrong, or the symbol name or path is incorrect, an `UnsatisfiedLinkError` may occur. This example does not require GraalVM Native Image, and is only compatible with the ABI/operating system for which the library was compiled.

## 4. Native Image: Compiling a Java Application Before Running

GraalVM Native Image reads Java bytecode along with required metadata, analyzes which components can be called, and **AOT compiles and links** them into an executable for a specific operating system/architecture. The binary typically bundles the necessary runtime components (such as memory management/GC and threads), although **no separate HotSpot JVM process is needed** to run the compiled application.

Pure Java example, file `SimpleApp.java`:

```java
public final class SimpleApp {
    public static void main(String[] args) {
        int total = 7 + 5;
        System.out.println("Total: " + total);
    }
}
```

Running in JVM mode:

```bash
javac SimpleApp.java
java SimpleApp
```

When the machine has a distribution with the `native-image` command and the required compiler toolchain installed, create an AOT build from **that same bytecode**:

```bash
native-image SimpleApp simple-app
./simple-app
```

The last run command illustrates Linux/macOS; on Windows, run `simple-app.exe`. Both approaches print:

```text
Total: 12
```

`SimpleApp` **does not call JNI, FFM, or any custom C library at all**. The native executable only changes **how the Java application is deployed/run**. Conversely, a JVM program that calls JNI like `NativeMath` still uses native interoperability even when not AOT-compiled.

Note: Native Image uses static analysis under a principle commonly called the **closed-world assumption**. Reflection, dynamic proxies, resource loading, serialization, or JNI accessing elements dynamically may require appropriate metadata/configuration. Packaging into a binary does not guarantee that every application using dynamic loading mechanisms will run the same as on the JVM without configuration adjustments. Do not equate “standalone executable” with “requires no operating system libraries at all”: native runtime dependencies still depend on the build and linking approach.

## 5. Comparison Table by Exact Criteria

| Criterion | Native interoperability (JNI/FFM) | JVM with JIT | AOT / GraalVM Native Image |
| --- | --- | --- | --- |
| Goal | Call/receive calls from code outside Java, exchange data via ABI | Optimize Java bytecode execution while the program runs | Turn a Java application into a binary before running |
| Technical boundary | Java ↔ library/function/native memory | Bytecode ↔ machine code managed by the JVM | Bytecode/build-time ↔ machine code executable |
| Primary timing | When the application executes a foreign call | At runtime, depending on “hotness” | When building the release |
| Typical input/output | Java + `.so`/`.dylib`/`.dll` library or native API | `.class`/JAR run with `java`, JIT emits internal machine code | `.class`/JAR → executable for OS/CPU |
| Is writing C/C++ required? | JNI wrappers usually are; FFM can call existing libraries without writing a JNI wrapper | No | No |
| Is a HotSpot JVM required to run? | Usually yes in a standard Java application; can be combined with Native Image | Yes | No separate HotSpot startup needed for a Native Image binary |
| Portability | Java code can be portable; native libraries must match OS/CPU/ABI | Bytecode can be moved across environments if a suitable JVM is available | Must build/distribute binaries matching the platform |
| Characteristic issues | Linkage, ABI, pointers, native crashes, memory management | Warm-up, JIT optimization/deoptimization, JVM runtime | Build time, size, metadata for dynamic features, environment differences |
| Proper understanding | **Code integration mechanism** | **Execution/optimization mechanism** | **Compilation/packaging mechanism** |

## 6. They Can Certainly Be Combined

There are four valid scenarios:

| How the application runs | Does not call custom native libraries | Calls native libraries |
| --- | --- | --- |
| **Runs on JVM** | Pure Java application; the JVM can JIT-compile | Java application using JNI/FFM; the Java part can still be JIT-compiled |
| **Runs as Native Image** | AOT binary of a pure Java application | AOT binary still integrates native libraries via mechanisms supported by Native Image with appropriate configuration |

Real-world example: a Java service that calls a C image-processing library via JNI is **native interoperability**; if that service is also compiled with GraalVM Native Image, it simultaneously uses **interop and AOT**. There is no contradiction: the two choices solve two different problems.

GraalVM Native Image supports JNI, but classes/methods/fields accessed dynamically via JNI may need to be declared at **build time**. For FFM and other native features, support must be checked for the **GraalVM/JDK version in use**.

## 7. Consequences When Choosing a Solution

**Integration goal:** If you need to call an OS SDK or an existing C/C++ library, evaluate JNI, FFM, or a suitable wrapper. Choosing Native Image alone **does not automatically generate bindings** to every C function and does not resolve ABI differences.

**Deployment goal:** If you need short startup time, reduced overhead for certain workloads, or to distribute an executable without requiring users to install a separate HotSpot JVM, evaluate Native Image. It may trade off longer build times, metadata requirements, and some limitations on dynamic behavior; performance results depend on the application, and one cannot conclude that AOT is always faster than JVM JIT.

**Performance goal:** JNI/FFM has call-boundary crossing overhead and data conversion costs; very small, tightly repeated calls may not be beneficial. JVM JIT has warm-up, but can optimize a long-running workload well. Native Image often has a startup advantage in many scenarios, while throughput/memory must be measured under real load and actual configuration.

**Safety goal:** A native bug such as an invalid pointer access or out-of-bounds memory write can corrupt the process or cause a crash; Java's GC does not automatically manage resources allocated in C. Native Image still has memory management for Java objects, so “machine code” does not mean “all memory is manually managed.”

**Portability goal:** A pure Java JAR is relatively independent of OS/CPU when an appropriate JDK/JRE is present. Native libraries and AOT executables usually must be built for the right platform, CPU architecture, and related dependencies/ABI.

## 8. Common Misconceptions and How to Correct Them

1. **“Having the `native` keyword means Java has been AOT-compiled into an executable.”** False. `native` only declares that the method body resides outside Java; `javac` still produces bytecode for the Java class.
2. **“JIT generates machine code, so it is native interoperability.”** False. JIT generates machine code for **Java code**; it does not imply any call to a custom C library.
3. **“Native Image always requires JNI.”** False. A pure Java application can be AOT-compiled without declaring any JNI functions.
4. **“Native Image cannot call C/C++.”** False. Supported interoperability mechanisms, such as JNI, can be used with the corresponding build configuration.
5. **“Creating an executable eliminates OS dependencies.”** False. The binary targets an OS/CPU and may still depend on shared libraries and OS-level runtimes.
6. **“Native Image eliminates GC and is guaranteed to be faster.”** False. Native Image still has a runtime that supports GC; performance depends on startup, runtime duration, memory, build options, and workload.
7. **“Calling C from Java is as safe as calling pure Java.”** False. An incorrect ABI, memory lifecycle, or pointer operation can cause severe errors outside Java's usual type guarantees.

## 9. Self-Check with Three Questions

When encountering a technology with the word “native”, ask:

- **Is there a call crossing the Java ↔ external code/data boundary?** If yes, we are talking about **interop** (JNI, FFM, FFI, or IPC, depending on how it connects).
- **Who compiles the Java code to machine instructions and when?** The JVM optimizing at runtime is **JIT**; a tool compiling before running is **AOT**.
- **Which file is deployed and which runtime starts it?** `.class`/JAR with `java` is the JVM model; an executable generated by `native-image` is the AOT Native Image model.

Being able to explain these three questions lets you distinguish them accurately even when a product uses JNI, JIT, and Native Image at different stages.

## Official References

- [Java Native Interface Specification (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html)
- [Foreign Function & Memory API (JDK 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html) and [JEP 454](https://openjdk.org/jeps/454)
- [GraalVM Native Image](https://www.graalvm.org/latest/reference-manual/native-image/)
- [GraalVM: JNI in Native Image](https://www.graalvm.org/reference-manual/native-image/JNI/)
