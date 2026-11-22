# Distinguishing the Separately Distributed jextract Tool from Built-in JDK Commands

## 1. Core Answer: jextract Is Not a Standard Command Bundled with the JDK

When first learning the **Foreign Function & Memory API (FFM)**, someone may have installed a new JDK, be able to run `java` and `javac`, yet when typing `jextract --version` receive a **command not found** or **is not recognized** error. This is not a paradox or a "broken" JDK installation: **`jextract` is a tool for generating Java bindings from C header files, developed and distributed separately in the OpenJDK jextract project**, not a mandatory command included in the `bin` directory of a standard JDK distribution.

A few points to distinguish right away:

- **`java`** runs the JVM and Java classes; **`javac`** compiles Java source into bytecode; **`javap`**, **`jar`**, **`jdeps`**, and **`jlink`** are tools commonly included in a **full JDK**.
- **`jextract`** parses **C headers** (`.h`) using a Clang foundation and **generates Java source code** that uses the FFM API to call a native library. It must be **downloaded/installed separately**, or built from the source of the jextract project.
- The fact that the FFM API was **finalized in JDK 22 (JEP 454)** **does not mean** `jextract` became a tool bundled with the JDK.
- You can **use FFM directly without jextract**: manually write `SymbolLookup`, `MemoryLayout`, `FunctionDescriptor`, and `Linker.downcallHandle(...)`. Conversely, to run generated bindings from jextract, you **still need a compatible JDK to compile/run** the generated Java code.
- **`javac -h` is different from `jextract` and processes in the opposite direction**: `javac -h` reads **Java `native` methods** and generates a **C JNI header**; `jextract` reads a **C header** and generates **Java FFM bindings**.
- The external `jextract` distribution has its own version, native platform support, and Clang/libclang dependencies; you cannot assume any arbitrary `jextract` file will work with every JDK and OS.

This lesson belongs to the **jextract bindings** group of **Java Advance – native-interoperability**. The focus is on **identifying, installing properly, verifying properly, not confusing tools, and executing the generation/build/runtime chain correctly**. The minimal Java examples are verified on JDK 24; the main `jextract` execution section is documented as a **procedure for an environment where the tool is already installed**, not presented as the output of an actual run if `jextract` has not been installed.

### Three Self-Check Questions Before Starting

1. "I have a JDK but no `jextract`. Is that normal?" **Yes.**
2. "If I have `jextract`, can I skip `javac`?" **No.** The tool generates Java source, while the Java compiler/runtime handles building and running.
3. "The JDK has `javac -h`, so can I use it instead of `jextract`?" **No.** Their inputs, outputs, APIs, and purposes are all different.

## 2. Two Tools Belonging to Two Different Layers

A native-interoperability system has a **Java toolchain**, a **jextract generator**, a **C toolchain**, and a **native library**. They should not be lumped together as a single "JDK suite":

| Component | Included in a standard development JDK? | Input | Main Output |
|---|---|---|---|
| `java` | Yes | Java bytecode / module | Runs the application in the JVM |
| `javac` | Yes | `.java` | `.class` bytecode |
| `javac -h` | Yes, as an option of `javac` | Java classes with `native` methods | C header for **JNI implementations** |
| `javap` | Yes | `.class` | Inspects signatures, descriptors, bytecode |
| `jar` | Yes | Java files/classes/resources | `.jar` and archive operations |
| `jdeps` | Yes | Java modules/JAR/classes | Dependency analysis |
| `jlink` | Yes | Java modules | Custom runtime image |
| `jextract` | **Not a standard bundled tool** | **C header (`.h`)**, Clang/preprocessor, options | **Java FFM binding sources** |
| `clang` / `gcc` / `cl.exe` | Not a standard JDK tool | `.c`/`.h` | Native `.so`/`.dylib`/`.dll` |
| `libclang` | Native dependency of jextract | C AST/parser APIs | Helps jextract understand C headers |

The table says "standard development JDK" to distinguish it from a **minimized Java runtime image** built with `jlink` or custom vendor distributions. Do not infer from a single `java.exe` file that the machine has all JDK commands. Conversely, a vendor may bundle additional tools in their own product; **check the actual distribution** rather than asserting all installers are identical.

### One-Line Distinction

~~~text
JDK tools:    .java ----javac----> .class ----java----> run JVM
                            |
                            +--- javac -h ---> .h for JNI/C adapter

Standalone:   C header .h ----jextract----> generated Java .java
                                              |
                                              +----javac----> .class
                                                         |
                                                         +----java + native .so/.dll/.dylib
~~~

**`jextract` is a build-time code generator**, not a Java runtime, a C compiler, or a JVM packaging component. Once suitable Java bindings have been generated and included in the build, you typically **do not need `jextract` installed on production machines**, unless production intentionally performs code generation at runtime (not the default model).

## 3. Why It Is Easy to Confuse: FFM Entered the JDK, but jextract Is Still Distributed Separately

The FFM API, standardized in **JEP 454**, provides classes such as:

~~~java
// Part of the public FFM API finalized since JDK 22.
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.Linker;
import java.lang.foreign.FunctionDescriptor;
~~~

These **Java APIs** reside in the `java.base` module of JDK 22+; the Java compiler sees them like normal classes. Meanwhile, **`jextract`** is an **executable tool** that the OpenJDK project distributes as separate artifacts; it parses C headers and emits Java source that uses the very FFM APIs mentioned above.

Key distinctions:

- **API finalized**: commits to a programming surface in **JDK 22+** for Java applications.
- **Standalone generator**: an **independent development tool**, whose version must match the Java/FFM API and the Clang environment on the generation machine.
- **Generated source**: code produced at build time; must be **compiled** by a suitable JDK and **linked to a native library** with the matching ABI/runtime.
- **Native binary**: the `.so`/`.dll`/`.dylib` itself is produced by a C compiler/linker or distributed by the library vendor; jextract **does not turn a header into a native binary**.

A C header can contain declarations without an implementation. For example:

~~~c
/* adder.h is only a C ABI contract: no native implementation yet. */
#ifndef ADDER_H
#define ADDER_H
int add_numbers(int a, int b);
#endif
~~~

Running `jextract` on that header can generate Java declarations/bindings, but **when the application runs**, a C library containing the actual `add_numbers` symbol is still required. If the binary is missing, exports are wrong, or the ABI mismatches, generated Java code cannot synthesize an implementation on its own.

## 4. Download Sources: Identifying jextract as a Separate Artifact

Official starting points:

- Tool release page: [OpenJDK jextract](https://jdk.java.net/jextract/).
- Source and build instructions: [openjdk/jextract](https://github.com/openjdk/jextract).
- User guide: [OpenJDK jextract GUIDE.md](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md).
- Official tutorial: [dev.java – Generate Java Bindings with Jextract](https://dev.java/learn/ffm/jextract/).
- Example in [Java SE 22 – Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html).

**Procedure for selecting the artifact before downloading:**

1. Determine the **current JDK runtime/build** using `java -version` and `javac -version`; do not rely solely on the IDE project SDK.
2. Go to the **jextract release page**; choose the binary matching the **OS and CPU architecture** of the generation machine, and do not blindly pick an x86_64 build for ARM64.
3. Read the release notes/README regarding the **JDK version that the tool and generated bindings target**. The jextract project may track mainline JDK and provide branches/releases for older JDK milestones. Do not assume "latest jextract" is always compatible with an application pinned to JDK 22.
4. Check requirements for **native libclang/LLVM**, library paths, system headers, and runtime libraries. Building jextract from source typically requires a matching JDK toolchain and `libclang`; prebuilt binaries may already bundle part of the dependencies depending on the release.
5. Extract/install into an **independent directory** (e.g., `tools/jextract-...`), and do not manually copy it into `$JAVA_HOME/bin` as if it were an original JDK file.
6. Run the **actual path of the executable** to verify before adding it to `PATH`; check `jextract --version`, `jextract --help`, and the target JDK.
7. Pin the jextract and JDK versions together in build scripts/toolchain config in CI, rather than letting PATH accidentally point to different releases across developer machines.

**Security:** only obtain binaries from trusted sources, verify checksums/signatures when provided by the publisher, and avoid running a spoofed `jextract` executable in a directory writable by others. Untrusted C headers can also contain complex macros/includes; generation in CI should run with least-privilege permissions.

### jextract and libclang

`jextract` is not a Java source parser; it leverages the **Clang C frontend / libclang** to read C syntax, macros, typedefs, structs, comments, and `#include` directives. Therefore:
- The C header must parse successfully on the machine running the generator, with appropriate include paths/defines.
- It may be necessary to install/deploy LLVM or provide the right `libclang` per the release instructions.
- `libclang` cannot be replaced by `javac` alone; the Java compiler does not parse C ASTs.
- Different compilers/versions/preprocessor macros can produce **different ABI models/generation results**. Test the generated source on the exact target platform (Windows/Linux/macOS) if the C header is not portable.

The official jextract page is the authoritative source for download locations and version details; **do not invent a "latest" version number** in a README that may remain around for years.

## 5. Checking Whether jextract Is Installed: PATH, JDK bin, Separate Tool

### 5.1. Linux/macOS, POSIX shell

~~~sh
java -version
javac -version

command -v java
command -v javac
command -v javap
command -v jar
command -v jdeps
command -v jlink

# jextract is a separate command: it may not be installed.
if command -v jextract >/dev/null 2>&1; then
    jextract --version
else
    echo "jextract is not on PATH; install a separate distribution if needed"
fi

# Inspect only the bin directory of the JDK set in JAVA_HOME (if set).
if [ -n "$JAVA_HOME" ]; then
    ls "$JAVA_HOME/bin"
fi
~~~

`command -v jextract` returning not found **only proves** the command is not on the current PATH; it may be installed in a directory that PATH does not point to yet. If you know where it was extracted, invoke `/opt/tools/jextract/bin/jextract --version` directly (illustrative path) before modifying PATH.

### 5.2. Windows PowerShell

~~~powershell
java -version
javac -version

Get-Command java, javac, javap, jar, jdeps, jlink |
    Select-Object Name, Source

# If absent, the result is empty; this is not evidence of a broken JDK.
$extract = Get-Command jextract -ErrorAction SilentlyContinue
if ($null -eq $extract) {
    Write-Output "jextract not on PATH"
} else {
    $extract.Source
    jextract --version
}

# Optional: inspect bin of the JDK pointed to by JAVA_HOME.
if ($env:JAVA_HOME) {
    Get-ChildItem -LiteralPath (Join-Path $env:JAVA_HOME "bin") |
        Select-Object Name
}
~~~

`Get-Command` shows **where a command is being resolved from**. If `jextract` is located in `C:\tools\jextract\bin`, that result proves there is an executable outside the JDK, not that the JDK "inherently has jextract". In case PATH has multiple overlapping tool versions, use `Get-Command jextract -All` to see all candidates, then pick the exact absolute path.

### 5.3. Windows CMD

~~~bat
where java
where javac
where jextract

java -version
javac -version
jextract --version
~~~

`where jextract` or `jextract --version` may return a non-zero exit code when not installed; **that is a diagnostic result**, not an error to fix by reinstalling the JDK.

### 5.4. Three Levels of Accurate Conclusions

| Check Result | Reliable Conclusion |
|---|---|
| `javac` runs, `jextract` not on PATH | JDK compiler may be working normally; jextract is not yet found on PATH |
| `jextract --version` runs, Source is outside JDK | Separate tool is installed/added to PATH; check version/compatibility |
| `jextract` is in a directory placed alongside the JDK by a vendor | Only proves **this current distribution** includes that tool; do not claim "every standard JDK includes it" |
| `java` exists but `javac` does not | Possibly using a minimized runtime image, a JRE/different alias, or a wrong PATH |
| `jextract` exists but `javac` does not | Separate generator is present; not guaranteed there is a suitable Java compiler to build generated source |

If multiple JDKs exist on the same machine, `java -version` and `javac -version` might come from **two different installations**. One command succeeding is not enough: check `JAVA_HOME` and resolved executable paths, and keep the toolchain consistent.

## 6. Runnable Java 17+: Auditing Which Tools Actually Exist in java.home/bin

This example intentionally **does not use FFM and does not require jextract**. It checks tool files alongside the current Java runtime and prints what is observed. Java 17+ is chosen so learners can do this identification exercise **even before upgrading the JDK to 22**.

Create **`JdkToolAudit.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class JdkToolAudit {
    private static void show(Path bin, String suffix, String tool) {
        boolean found = Files.isRegularFile(bin.resolve(tool + suffix));
        System.out.println(tool + "InRuntimeBin=" + found);
    }

    public static void main(String[] args) {
        Path bin = Path.of(System.getProperty("java.home"), "bin");
        String suffix = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win") ? ".exe" : "";

        System.out.println("jdkFeature=" + Runtime.version().feature());
        show(bin, suffix, "javac");
        show(bin, suffix, "javap");
        show(bin, suffix, "jar");
        show(bin, suffix, "jdeps");
        show(bin, suffix, "jlink");
        show(bin, suffix, "jextract");
    }
}
~~~

Compile and run in the directory containing the file:

~~~sh
mkdir -p out
javac --release 17 -d out JdkToolAudit.java
java -cp out JdkToolAudit
~~~

**Windows CMD**, if `out` does not exist yet: `mkdir out`, then use the same two `javac`/`java` commands. PowerShell can use `New-Item -ItemType Directory -Force out | Out-Null`.

On the **Windows x64 / Azul JDK 24.0.2 test environment**, the **exact** stdout is:

~~~text
jdkFeature=24
javacInRuntimeBin=true
javapInRuntimeBin=true
jarInRuntimeBin=true
jdepsInRuntimeBin=true
jlinkInRuntimeBin=true
jextractInRuntimeBin=false
~~~

Meaning:
- `java.home` is the root of **the runtime currently used by the JVM**; in the full JDK in the test environment, it contains the standard executables.
- `Files.isRegularFile(...)` **does not scan PATH**: if `jextract` is installed elsewhere, `jextractInRuntimeBin=false` can still be true. You need `command -v` / `Get-Command` to inspect PATH.
- `jdkFeature=24` is a **machine-dependent** value; on JDK 22/23/25/26 it changes. The `true/false` lines can also differ by build, runtime image, OS, and vendor.
- The example **does not verify whether the executable actually runs or has the right version**; it only answers the narrow question "is a file with this name in `java.home/bin`?". To verify functionality, you still must run `--version` and check the exit code.

This is an **empirical indicator**; do not use a single Windows machine to generalize that every distribution worldwide has the exact same file list.

## 7. Do Not Confuse `javac -h` with `jextract`: Opposite Code Generation Directions

Both involve Java and native code, but in **two different workflows**.

### 7.1. `javac -h`: Java `native` declaration → C JNI header

Create **`JniHeaderCheck.java`**:

~~~java
public final class JniHeaderCheck {
    private static native int twice(int value);

    public static void main(String[] args) {
        System.out.println("JVM_OK");
    }
}
~~~

Run the JDK compiler:

~~~sh
mkdir -p out headers
javac --release 17 -h headers -d out JniHeaderCheck.java
java -cp out JniHeaderCheck
~~~

**Windows CMD** can create `mkdir out` and `mkdir headers` sequentially; the `javac`/`java` commands are unchanged. `javac -h` is supported on JDK 17+ and generates **`headers/JniHeaderCheck.h`** from the **Java native method**.

The generated C header contains an equivalent prototype:

~~~c
/* Excerpt only of the header generated by javac -h. */
JNIEXPORT jint JNICALL Java_JniHeaderCheck_twice
  (JNIEnv *, jclass, jint);
~~~

Explanation:
- `JNIEnv *` is the environment pointer of the thread calling native code.
- `jclass` appears here because the Java method is **`static native`**; for an instance native method it would be `jobject`.
- `jint` represents Java `int` in JNI.
- The prefix `Java_JniHeaderCheck_twice` is the JNI exported symbol naming convention.
- The generated header helps you **write the corresponding C implementation**; `javac` **does not generate C implementation code**.

**Stdout when running the class above**:

~~~text
JVM_OK
~~~

`main` **does not call `twice`**, because there is no native library implementation yet; that allows demonstrating compilation and header generation independently. If you modify `main` to call `twice(2)` without a C JNI binary, an `UnsatisfiedLinkError` will occur. Do not take `JVM_OK` as proof that a JNI native method is already working.

In the JDK 24 test environment, `javac --release 17 -h` generated a header containing both `JNIEXPORT` and `Java_JniHeaderCheck_twice`; the Java program printed `JVM_OK` exactly as above.

### 7.2. `jextract`: C header → Java FFM bindings

Given a C header:

~~~c
#ifndef ADDER_H
#define ADDER_H

int add_numbers(int a, int b);

#endif
~~~

The C file **`native/adder.h`** above goes into **`jextract`**, and the typical output is a set of **Java source files** containing helper/FFM wrappers (depending on headers and version). Not a C JNI header:

~~~text
native/adder.h
       |
    jextract        (separately installed tool, uses Clang parser)
       |
       v
gensrc/demo/ffm/...  generated .java files
       |
     javac          (JDK tool)
       |
       v
Java bytecode .class
       |
     java            (JDK tool)
       |
       v
Actual C shared library (libadder.so / libadder.dylib / adder.dll)
~~~

`jextract` inspects **C declarations** and generates a matching Java mapping layer. It does not need a pre-existing Java class containing `native` methods and does not require the `Java_Class_method` naming convention. The generated bindings call ordinary **C ABI symbols** via `java.lang.foreign.Linker`.

### 7.3. Side-by-Side Comparison Table

| Question | `javac -h` | `jextract` |
|---|---|---|
| Is it a tool included in a standard JDK? | **Yes**, an option of `javac` | **No**, obtained as a separate distribution |
| Input | `.java` with `native` methods | **C header `.h`** |
| Output | **C JNI header `.h`** | **Java FFM binding sources `.java`** |
| Needs libclang to parse C headers? | No | Typically has **libclang/LLVM dependencies** per tool distribution |
| Goal | Match C implementation of a Java JNI native method to its signature | Java calls C ABI library functions / structs / constants |
| Uses `JNIEnv *`? | Yes, JNI C signatures | Generated FFM bindings normally have no JNI adapter |
| JDK version dependency? | Follows Java compiler/JNI platform | Follows **jextract release + FFM/JDK target** |
| When is it run? | Building JNI adapter | Generating Java bindings from C headers |

**An easy rule of thumb:** "`javac -h` is for *Java → C*, whereas `jextract` is for *C → Java*." The arrow refers to **the direction of declaration/binding generation**, not the execution direction of a native call.

## 8. Installing jextract Separately: General Reproducible Procedure

### Step 1 – Verify the JDK for the tool and project

~~~sh
java -version
javac -version
~~~

For example, a project using finalized FFM selects **JDK 22+**. If a jextract binary tool was built for a newer JDK release (as mainline advances), use **the JDK specified by that jextract release** to run the generator, then ensure the generated source uses APIs available in **the application's target runtime**. Do not assume a tool built for 25 can generate bindings that run on 22 without adjustment.

### Step 2 – Download the matching OS/architecture binary

Download from `https://jdk.java.net/jextract/` or refer to building from `https://github.com/openjdk/jextract`. Extract into a separate directory. Examples of **illustrative paths**, not mandatory exact locations:

~~~text
Linux:    /opt/tools/jextract/bin/jextract
macOS:    /opt/tools/jextract/bin/jextract
Windows:  C:\tools\jextract\bin\jextract.bat or the executable provided by the release
~~~

**Do not guess the Windows extension**: inspect the actual files in `bin` of the downloaded archive. Depending on the release, the launcher may be `jextract.bat`, `jextract.exe`, or a corresponding script; invoke the actual file present.

### Step 3 – Verify before modifying PATH

~~~sh
# Linux/macOS; illustrative path:
"/opt/tools/jextract/bin/jextract" --version
"/opt/tools/jextract/bin/jextract" --help
~~~

Windows PowerShell can use:

~~~powershell
# Replace launcher name with the actual extracted file.
& "C:\tools\jextract\bin\jextract.bat" --version
& "C:\tools\jextract\bin\jextract.bat" --help
~~~

If launching fails due to a missing DLL/`libclang`, read the release prerequisites and check native dependency paths; **do not randomly reinstall the JDK**.

### Step 4 – Only when needed, add the separate bin to PATH

Linux/macOS shell:

~~~sh
export PATH="/opt/tools/jextract/bin:$PATH"
jextract --version
~~~

Windows PowerShell for the **current session**:

~~~powershell
$env:PATH = "C:\tools\jextract\bin;" + $env:PATH
Get-Command jextract -All
jextract --version
~~~

This only adjusts the shell/CI session environment and does not modify the JDK. In reproducible builds/CI, prefer using a **pinned executable path** instead of resolving the command via an uncontrolled PATH.

### Step 5 – Pin metadata for reproducibility

Record in build documentation or CI cache metadata:
- jextract release/version (output from `jextract --version`).
- JDK toolchain version (`java/javac -version` output).
- Generator and target OS/architecture.
- Native header/library version; hash or dependency lock if appropriate.
- C compiler/preprocessor defines/include paths used for parsing.
- Whether generated files are committed per project policy or regenerated during build.
- Runtime native access flags required for the generated binding module.

Do not record a fake version or an output guessed from a zip filename; use the **actual** values from the installed tool.

## 9. jextract Workflow Example: From adder.h to Java Bindings

**This section requires a machine with jextract and a C compiler installed.** In the test environment for this lesson, `jextract` **was not installed**, so the following generation commands are **instructions per the official CLI**, not recorded as having been executed or having specific output verified.

### 9.1. C header and implementation are two separate files

Sample layout:

~~~text
adder-demo/
  native/
    adder.h
    adder.c
  gensrc/               # jextract writes Java sources here
  out/                  # javac writes .class files here
~~~

File **`native/adder.h`**:

~~~c
#ifndef ADDER_H
#define ADDER_H

int add_numbers(int a, int b);

#endif
~~~

File **`native/adder.c`**:

~~~c
#include "adder.h"

int add_numbers(int a, int b) {
    return a + b;
}
~~~

`adder.h` describes the **C ABI contract**; `adder.c` is the **native implementation**. On platforms where symbols must be exported from a DLL (especially Windows/MSVC), check **export visibility**; you may need `__declspec(dllexport)` or a `.def` file. Minimal C code on Linux/macOS usually exports global function symbols by default, whereas Windows does not automatically guarantee exports the same way.

### 9.2. Compile the native library separately

On Linux:

~~~sh
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -o libadder.so native/adder.c
~~~

On macOS:

~~~sh
cc -std=c11 -Wall -Wextra -dynamiclib \
  -o libadder.dylib native/adder.c
~~~

On Windows MSVC Developer Command Prompt, if `adder.c` does not have an export attribute, specify the export to the linker:

~~~bat
cl /nologo /W4 /LD native\adder.c /link /EXPORT:add_numbers /OUT:adder.dll
~~~

These commands are **toolchain templates**, not output tested across all three OSes. Adjust syntax according to compiler/version/architecture if needed. Before trusting the Java bindings, verify that the **exported symbol** is actually named `add_numbers`:
- Linux: `nm -D --defined-only libadder.so`;
- macOS: `nm -gU libadder.dylib`;
- Windows: `dumpbin /EXPORTS adder.dll`.

If the implementation is in C++, expose a **C ABI** via appropriate `extern "C"` declarations and then generate from the C-compatible header. jextract parses C declarations; it does not automatically extract full C++ templates/classes into equivalent Java FFM bindings.

### 9.3. Run standalone jextract with explicit arguments

In the `adder-demo` directory, after `jextract --version` succeeds:

~~~sh
jextract \
  --include-dir native \
  --output gensrc \
  --target-package demo.ffm \
  --library adder \
  native/adder.h
~~~

On Windows CMD as a single line:

~~~bat
jextract --include-dir native --output gensrc --target-package demo.ffm --library adder native\adder.h
~~~

Options:
- `--include-dir native`: adds a search path for `#include` / C headers.
- `--output gensrc`: root directory where **generated Java source files** are written.
- `--target-package demo.ffm`: package for the Java bindings.
- `--library adder`: instructs the generated bindings to load a native library with logical name `adder`; the tool/runtime maps the name per OS, e.g., `libadder.so`/`libadder.dylib`/`adder.dll`.
- `native/adder.h`: the primary C header to parse, **not a Java source file**.

According to the official guide, the generated root class is usually derived from the header name; `adder.h` may produce **`adder_h`** along with auxiliary files when structs, unions, or function pointers are present. **Class/method names and file types must be checked against the actual output**, because they can vary by jextract release/options and C declarations; do not pre-write a "runnable" Java client assuming exact generated signatures without having the tool/output.

### 9.4. Inspect artifacts, then continue with JDK tools

Linux/macOS:

~~~sh
find gensrc -type f -name '*.java'
# Inspect the generated files; if no .java files exist, stop.
# Compile generated source using a JDK compatible with the jextract release.
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem gensrc -Recurse -Filter *.java |
    Select-Object FullName
~~~

**The next step is `javac`**, not running `jextract` to execute a C function. In a real project, use Gradle/Maven/IDE to compile generated sources alongside application sources; CI can place them in a `gensrc` source set. Check the required target JDK before using `javac --release ...`, and do not force `--release 22` on bindings generated by a newer tool targeting a later FFM API.

After building, the JVM needs:
1. The Java classpath/module path to find the generated classes.
2. The actual `adder` native shared library matching the platform/arch.
3. The loader to find the library via **OS library search rules**, or bindings generated with an explicit path/appropriate loader option.
4. The module performing restricted FFM calls to be granted **native access** when required by the JDK, for example code on the classpath:

~~~sh
java --enable-native-access=ALL-UNNAMED -cp out YourClient
~~~

`YourClient` on this line is **an application-written client class name**, not a file automatically produced by the generator. When using a named module, replace `ALL-UNNAMED` with the appropriate module name.

### 9.5. When an explicit native library path is needed

The official `jextract` guide supports `--library` with either a **logical name** or a **path** prefixed with a colon:

~~~sh
# Linux illustration; the file and path must actually exist at runtime.
jextract \
  --output gensrc \
  --target-package demo.ffm \
  --library :/opt/native/libadder.so \
  native/adder.h
~~~

Here `:/opt/native/libadder.so` is **a single argument** starting with `:`, not two separate options. Without the prefix, `--library adder` is mapped to an OS filename and the loader searches via search paths. On Windows, native paths contain a drive colon `:`; use proper shell quoting and the options specified by **the release in use**.

Another option is `--use-system-load-library`: it switches how generated bindings load the library to `System.loadLibrary/System.load` following JVM JNI loader conventions. In that case `java.library.path` applies directly; with the default native `libraryLookup`, OS search paths such as Linux `LD_LIBRARY_PATH` / Windows `PATH` can matter. **Do not change `java.library.path` expecting all loader modes to be affected identically.**

## 10. Runnable JDK 22+ FFM Example WITHOUT jextract

To prove `jextract` is a **code-generation convenience, not a dependency for writing any FFM code**, we manually build a `strlen` binding using the standard `java.lang.foreign` classes.

Create **`FfmWithoutJextract.java`**:

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;

public final class FfmWithoutJextract {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        MemorySegment symbol = linker.defaultLookup().find("strlen")
                .orElseThrow(() -> new IllegalStateException(
                        "strlen absent from default lookup"));

        MethodHandle strlen = linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(
                        linker.canonicalLayouts().get("size_t"),
                        ValueLayout.ADDRESS));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment text = arena.allocateFrom("hello");
            long count = ((Number)
                    strlen.invokeWithArguments(text)).longValue();
            System.out.println("strlen=" + count);
            if (count != 5) {
                throw new AssertionError(count);
            }
        }

        System.out.println("FFM_PASS_WITHOUT_JEXTRACT");
    }
}
~~~

Compile and run (JDK 22+):

~~~sh
mkdir -p out
javac --release 22 -d out FfmWithoutJextract.java
java --enable-native-access=ALL-UNNAMED \
  -cp out FfmWithoutJextract
~~~

On Windows CMD/PowerShell you can write `java --enable-native-access=ALL-UNNAMED -cp out FfmWithoutJextract` on one line. Running on JDK 24 Windows x64 was verified with:

~~~text
strlen=5
FFM_PASS_WITHOUT_JEXTRACT
~~~

**Not a single line calls `jextract`!** The code manually writes `SymbolLookup`, `FunctionDescriptor`, and `Linker.downcallHandle`. `Arena.allocateFrom("hello")` allocates a `NUL`-terminated UTF-8 string; C `strlen` counts five bytes.

Environment caveat: `Linker.nativeLinker().defaultLookup()` has an OS/JVM-dependent symbol list; on an environment that does not expose `strlen`, the code proactively throws `IllegalStateException("strlen absent from default lookup")`. You can use an explicit library lookup if you know the corresponding C runtime. Do not infer whether jextract "works or not" from default symbol availability.

### Comparing the Three Runnable Examples in This Lesson

| Example | Minimum JDK | Needs jextract? | Needs C compiler? | What does it verify? |
|---|---:|---|---|---|
| `JdkToolAudit` | 17 | No | No | Files present in `java.home/bin` |
| `JniHeaderCheck` with `javac -h` | 17 | No | No if only generating header | Java native → C JNI declaration direction |
| `FfmWithoutJextract` | 22 | No | No if platform already provides `strlen` | Manual FFM downcall from JDK APIs |
| `adder.h` → jextract → generated code | Depends on jextract release; FFM finalized from 22 | **Yes** | Yes if building `adder` library yourself | C header → Java FFM bindings direction |

**Do not confuse "does not need jextract" with "does not need a native library":** `strlen` still executes in the native C runtime of the OS/JVM. Java FFM acts as a bridge rather than re-implementing the C function in Java.

## 11. JDK Releases and Compatibility Matrix to Self-Verify

Across Project Panama's history, the FFM API and jextract evolved across Java releases:

| Java release | FFM status | What to note when reading a jextract article |
|---|---|---|
| JDK 17–18 | Incubator-era APIs, e.g., `jdk.incubator.foreign` | Historical sources/flags and jextract branches differ; finalized code does not apply as-is |
| JDK 19–21 | Multiple preview versions with changing APIs | Must select matching **jextract build/branch and generated code** |
| **JDK 22** | **FFM finalized**, JEP 454, `java.lang.foreign` | Manual FFM example in this lesson compiles with `--release 22` |
| JDK 23+ | FFM continues evolving; native-access policy changes across releases | Check jextract release compatibility, required flags, and generated API instead of guessing |

There is no safe rule that "jextract version X works for all JDKs from 22 onward". The jextract master branch typically targets the latest mainline JDK and may maintain separate branches/tags for older JDK targets. Learners must rely on **`jextract --version`**, the README of the downloaded release, and the Javadoc of the target JDK.

### CI Version-Pinning Principle

~~~text
JDK used to run jextract   -> matches jextract binary requirement
jextract binary            -> matches version/branch for target API
C headers + libclang       -> same include/macro/ABI contract
javac target               -> compiles the newly generated Java source
java target/runtime        -> has matching FFM APIs/flags and native library
~~~

In a multi-OS pipeline, generated layouts and native ABIs must be tested per OS. C `long` can differ in size between Windows x64 and Linux x64; preprocessor `#ifdef` directives can also produce different declarations. Do not share one set of generated files across platforms just because the files all end in `.java`.

## 12. libclang, Native Compiler, and C Header: Three Different Things

A common mistake is "jextract can parse the header, so I don't need a C compiler anymore, right?". The answer depends on the library:

- If you **already have a trusted native binary** from a vendor, `jextract` can generate Java bindings from the corresponding headers; you do not need to recompile the C source yourself.
- If you **write C source yourself**, you need a C toolchain (GCC/Clang/MSVC) to produce `.so`/`.dll`/`.dylib`.
- `libclang` is a library supporting **header parsing inside the jextract tool**, not a substitute for your application's C shared library.
- `javac` compiles generated Java bindings, **not** C. `jar` packages Java classes/resources, and **does not turn C source into an executable**.
- Once generated code is compiled into `.class` files, **jextract is not needed during normal runtime**; runtime needs a suitable FFM JDK and an actual native binary.

### Matching Header Version with Binary Version

Suppose a vendor ships `libfoo-v1.so` and `foo-v2.h`. Even if jextract parses header v2 successfully, the generated method signatures may **not** match the C ABI of binary v1. This is more dangerous than a compilation error: a native call can return garbage, misread pointers, or crash the JVM. Projects must pair **headers ↔ binary ↔ architecture ↔ compiler ABI** at the same supported version.

Do not feed C++ headers containing templates/classes directly and expect jextract to understand the full C++ ABI. A common approach is to write a **C ABI wrapper layer** declared with `extern "C"` in a C-compatible header, then run jextract on the wrapper header.

## 13. Does jextract Need to Be Installed in Production?

In the standard workflow:

~~~text
Developer / CI:
  1. obtain headers + compatible jextract
  2. generate Java sources
  3. compile Java and package app
  4. ship app bytecode + native binary

Production:
  1. start suitable JVM
  2. load app/generated bindings
  3. load native library
  4. call C via FFM
~~~

**The `jextract` executable is not needed in production** if all Java bindings were generated/compiled during the build. Exceptions may exist if an application intentionally generates code at runtime, but that is a specialized architecture requiring different compiler/source/runtime privileges.

### Commit Generated Sources or Generate Every Build?

Both are viable:

- **Commit generated sources**: consumers only need a JDK and the native binary to build; code reviews easily show generated code diffs when headers update. In return, you must manage diffs, tool version metadata, and avoid hand-editing generated files.
- **Generate in CI**: controls C headers/defines and regenerates bindings automatically; requires the pipeline to have **a jextract distribution and libclang**. In return, the build is more complex and tool versions/repositories must be pinned to prevent drift.
- **Hybrid**: generate in a controlled step and commit into a `generated` directory, while CI runs a generation check to ensure no divergence. What matters is **having a single source of truth** for the C header/ABI and knowing when regeneration is mandatory.

The jextract guide recommends thinking in terms of regenerating when headers/tools update rather than necessarily on every JVM run; verify the actual generated file naming/output of your pinned version before designing Maven/Gradle tasks.

## 14. Common Errors: Identifying the Right Layer Instead of Reinstalling the JDK

| Error / Symptom | Layer Where It Occurs | Correct Fix |
|---|---|---|
| `jextract: command not found` / `not recognized` | PATH or **standalone tool** not installed | Download separate artifact, run by absolute path, then adjust PATH if needed |
| `java`/`javac` exist, `jextract` does not | **Not a bug** in standard JDK | Install jextract only when you actually need to generate bindings |
| `UnsupportedClassVersionError` when running jextract | Tool built for newer JDK than current runtime | Choose JDK matching tool release or a jextract release matching target |
| Missing `libclang`/native DLL on jextract startup | Native dependency of generator | Check LLVM/libclang per release/OS README |
| `fatal error: foo.h: No such file or directory` | Clang include paths | Proper `--include-dir/-I` and required C SDK headers |
| Parse failure due to macro/typedef | C preprocessor/ABI config | Appropriate `-D` defines, target OS/toolchain include paths |
| Generated Java code fails to compile | `javac`/generated API mismatch | Select compatible JDK and jextract target version; do not guess fixes with random flags |
| `javac -h` does not generate Java bindings from C | Wrong tool | `javac -h` only generates **C JNI header** from Java `native` |
| `jextract` creates Java code but there is no `adder.dll` | Missing native implementation binary | Build/install C library separately and check exports |
| `UnsatisfiedLinkError` / library load failure at runtime | Runtime library loading | File/path/OS deps/architecture/loader mode |
| `Optional.empty` when looking up symbol | Export name/library mismatch | `nm`/`dumpbin`/matching header version |
| `IllegalCallerException` when calling restricted FFM | Runtime native-access permissions | `--enable-native-access=ALL-UNNAMED` or named module |
| `WrongMethodTypeException` when invoking handle | Java method handle signature mismatch | Check carrier types/`MethodHandle.type()` |
| JVM crash during native call | Wrong ABI/pointer/lifetime | Compare C header with generated bindings, debug native; `try/catch` does not guarantee saving the JVM |
| Bindings work on Linux, fail on Windows | C `long`, macros, name decoration, struct packing | Generate/validate per actual OS/ABI, do not just copy generated files |
| `jextract --version` runs but generated code fails to build on JDK 22 | Generator binary targets a different JDK API | Pin release/branch matching target, regenerate |

**A tool error should not be solved by reflexively "downloading another JDK".** Identify which layer the error belongs to: JDK bin/PATH, jextract CLI/libclang, C header preprocessing, native library exports, Java compile target, native access policy, or C ABI.

## 15. Tool-Selection Exercises (with Solutions)

**Exercise 1.** A project already has `libmath.so` and C header `math.h`. You want to create Java wrappers using FFM for functions in the header; should you run `javac -h` or `jextract`?  
**Answer:** **`jextract`**. It reads C declarations and emits Java FFM binding sources. Use `javac` afterward to compile the generated Java source.

**Exercise 2.** A Java class declares `private native int compute(int x);` and you want the C function prototype to implement JNI. Which tool do you use?  
**Answer:** **`javac -h`** from the JDK, because it generates a C JNI header from a Java `native` declaration. `jextract` goes in the opposite direction and does not generate JNI implementations.

**Exercise 3.** `java -version` prints JDK 24, `javac -version` succeeds, and `jextract --version` fails. Do you need to reinstall the JDK?  
**Answer:** No. This is normal. Download/extract a suitable standalone jextract distribution and configure PATH if you need the generator.

**Exercise 4.** You have jextract on PATH, but generated bindings call a C function incorrectly because `sizeof(long)` differs between Windows and Linux. Is this fixed by adding `--enable-native-access`?  
**Answer:** No. Native access grants **permission** for restricted FFM operations; it does not fix layout/ABI. You must inspect headers, platform defines, and generated bindings on each ABI.

**Exercise 5.** A `JAR` already contains complete generated Java bindings and production has the right native library; do you need to ship the `jextract` executable?  
**Answer:** No in the standard model. The production JVM runs bytecode, and FFM calls the native library; codegen is a build-time step.

**Exercise 6.** Using `jextract --library foo`, the runtime cannot find `foo.dll`. Is the generated Java package wrong?  
**Answer:** Likely not. First check that the binary exists, export names, OS native loader path, dependencies, and `System.mapLibraryName` mapping. Java classpath and native library search path are two separate mechanisms.

**Exercise 7.** Is placing `jextract` into `$JAVA_HOME/bin` to "fix" a missing-tool warning a good idea?  
**Answer:** Not recommended. Keep the jextract artifact separate, pin its version clearly, run via absolute path, or add jextract's own `bin` to PATH. Copying manually into JDK bin obscures its origin and breaks easily when updating the JDK.

**Exercise 8.** You have `adder.h` but no `adder.c` or binary; can `jextract` create a runnable library?  
**Answer:** No. It generates Java bindings from C headers; a native implementation and compatible runtime binary are still required.

**Exercise 9.** You want to use FFM for a small C function without setting up jextract. Is that possible?  
**Answer:** Yes. Use `SymbolLookup`, `FunctionDescriptor`, and `Linker.downcallHandle` directly as in `FfmWithoutJextract`, with JDK 22+ and appropriate native access.

**Exercise 10.** `jextract --version` prints a target JDK newer than production's JDK. Can you ignore it because "FFM is already finalized"?  
**Answer:** No. Generated Java source may still use APIs or a bytecode target that do not exist in production. Choose the right generator branch/release and test against the target Java runtime before shipping.

## 16. Checklist Before Automating jextract in CI

- [ ] Determine whether the project **needs code generation from C headers** or only manual FFM bindings; do not install jextract unnecessarily.
- [ ] Pin **JDK**, **jextract version**, **OS/CPU architecture**, native headers, and binary versions; do not use an uncontrolled "latest".
- [ ] Verify `jextract --version` on the **separate binary**, without assuming the tool lives in `$JAVA_HOME/bin`.
- [ ] Verify `javac -version` and `java -version` match the target runtime; do not let PATH/JAVA_HOME point to different JDKs.
- [ ] Check Clang/libclang dependencies and include paths/defines before parsing C.
- [ ] Select the actual public C API header (correct include tree), without mixing C++ templates/class declarations into C ABI bindings.
- [ ] Use `--target-package`, `--output`, `--include-dir/-I`, and `--library` according to the semantics of the jextract release.
- [ ] Inspect **generated Java source files**, the root header class name, and generated method signatures; do not rely on guessed class/method names.
- [ ] Use **`javac`** to compile generated sources; do not confuse `javac -h` with a C→Java generator.
- [ ] Ensure the native shared library exists and exports the right names; build/test the C implementation on the target OS/ABI.
- [ ] Distinguish classpath/module path, OS loader path, and `java.library.path`; do not change the wrong setting.
- [ ] Grant native access to the module containing FFM bindings per JDK policy; do not use `--enable-preview` on finalized FFM JDK 22+ unless other preview features are used.
- [ ] Do not assume ABI portability: `long`/`size_t`/struct padding, macros, and callbacks must be tested per platform.
- [ ] Have a smoke test that calls the native function and checks the result; do not just look at generated files or compiler exit codes.
- [ ] When headers or the generator change, regenerate/review/diff in a controlled manner, without hand-editing generated code and forgetting the source of truth.
- [ ] CI deployment does not require jextract if codegen finished at build time; production has the right native binary/JVM.
- [ ] When the tool is missing, report clearly **"standalone jextract not installed"**, rather than assuming a broken JDK setup.
- [ ] Record accurately what was actually run; do not claim generation succeeded if only illustrative commands were shown.

## 17. Summary and Official References

Remember this chain:

~~~text
C HEADER .h ──[standalone jextract / libclang]──> Java FFM binding .java
                                                         |
                                                    [JDK javac]
                                                         |
                                                    Java .class
                                                         |
                                                    [JDK java]
                                                         |
                                           Actual native C library
~~~

Contrast:

~~~text
Java source with "native" ──[JDK javac -h]──> C JNI header .h
                  This is the OPPOSITE DIRECTION; cannot replace jextract.
~~~

**`jextract` is a separately distributed tool specialized in generating bindings from C headers; `javac`/`java` and other JDK tools are part of the Java toolchain; the FFM API is a standard library in JDK 22+; the native compiler and native library are a separate layer.** Separating these four layers helps diagnose missing commands, incompatible versions, and runtime errors accurately instead of misconfiguring the environment.

Official sources for learning and keeping up with releases:
- [OpenJDK jextract downloads](https://jdk.java.net/jextract/).
- [OpenJDK jextract source / build instructions](https://github.com/openjdk/jextract).
- [OpenJDK jextract detailed guide](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md).
- [dev.java — Generate Java Bindings with Jextract](https://dev.java/learn/ffm/jextract/).
- [Oracle Java SE 22 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html).
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454).
- [Oracle Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Oracle javac documentation (JDK 22)](https://docs.oracle.com/en/java/javase/22/docs/specs/man/javac.html).

**Verification scope:** the three examples `JdkToolAudit`, `JniHeaderCheck`, and `FfmWithoutJextract` were compiled/run with JDK 24 in the test session. **`jextract` was not present in PATH/JDK bin in this environment**, so the download and `adder.h` generation sections are instructions per official documentation, not output from an actual execution. Once the separate binary is available, the first command must be `jextract --version` to confirm the exact tool/release before generating.
