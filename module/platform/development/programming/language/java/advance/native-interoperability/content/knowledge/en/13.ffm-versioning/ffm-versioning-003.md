# FFM and Versioning — The --enable-preview Option When Compiling and Running FFM Code for JDK 21

## 1. FFM in JDK 21: Why Is Preview Needed?

The **Foreign Function & Memory API (FFM)** allows Java programs to access off-heap memory and interact with native functions. JDK 21 provides the FFM APIs in the `java.lang.foreign` package, such as `Arena`, `MemorySegment`, `ValueLayout`, `Linker`, `SymbolLookup`, and `FunctionDescriptor`.

In **JDK 21**, FFM follows **JEP 442: Third Preview**. A preview API is an API available for developers to experiment with and provide feedback on, but it has not yet been finalized as a permanent Java SE API in that version. Therefore, the compiler and JVM **do not allow using** FFM preview by default unless the flag is enabled.

For source code using JDK 21 FFM:

```bash
# Use javac from JDK 21 to compile
javac --enable-preview --release 21 -d out PreviewMemoryDemo.java

# Use java from JDK 21 to execute
java --enable-preview -cp out PreviewMemoryDemo
```

**`--enable-preview` must be enabled in both steps**. `javac` and `java` are two separate processes: a flag used in the compiler does not automatically carry over to the launcher. If compilation succeeds but running lacks the flag, the JVM may throw `UnsupportedClassVersionError` and refuse to load the preview class file.

```text
Java source using java.lang.foreign of JDK 21
                    │
                    ▼
   javac --enable-preview --release 21
                    │
                    ▼
       .class containing preview bytecode
                    │
                    ▼
          java --enable-preview
                    │
                    ▼
           FFM program runs
```

The key point to remember is: **`--enable-preview` is for preview APIs, not synonymous with `--enable-native-access` for restricted native operations**. The two types of flags will be distinguished using tested programs.

## 2. Meaning of the Command-Line Options

| Flag | Tool | Purpose |
| --- | --- | --- |
| `--enable-preview` | `javac` 21 | Allows code to use preview features and preview APIs of JDK 21 itself |
| `--release 21` | `javac` 21 | Compiles targeting the language and APIs of release 21 |
| `-source 21` | `javac` 21 | Another way to specify the source level; can be used with preview, though `--release` is usually more appropriate |
| `-d out` | `javac` | Output directory for bytecode |
| `--enable-preview` | `java` 21 | Allows the JVM to load and run classes that use Java 21 preview features |
| `-cp out` | `java` | Where to look for `.class` files |
| `--enable-native-access=ALL-UNNAMED` | `java` 21 | Grants native access to code on the classpath when using restricted FFM operations |

`--enable-preview` on the compiler must be used with the **current release of javac**. For example, `javac 21 --enable-preview --release 20` is **invalid**: it does not enable Java 20 preview. To properly learn Java 21 FFM, use `javac 21` and `--release 21`. Check with:

```bash
javac -version
java -version
```

Both commands should return version **21.x**. Do not assume that the IDE, terminal, Maven, Gradle, and CI automatically use the same JDK.

In the `java` command, place `--enable-preview` **before** the main class name. If placed after the class, that string usually becomes a **program argument** to `main(String[] args)` instead of a VM option. `--release 21` is a **compile option**, not a JVM runtime option.

## 3. Runnable Example 1: FFM Memory, No C Library Required

This is the simplest way to test the flag: manipulating off-heap memory with JDK 21's `Arena` and `MemorySegment`, without using a linker or external native libraries.

### 3.1. Source: `PreviewMemoryDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class PreviewMemoryDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment number = arena.allocate(ValueLayout.JAVA_INT);
            number.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println("FFM value: " + number.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
```

- `Arena.ofConfined()` creates an arena with a bounded lifetime and thread-confined ownership.
- `arena.allocate(ValueLayout.JAVA_INT)` allocates memory compatible with the layout of `int`.
- `set/get` writes and reads the value at byte offset `0`.
- `try-with-resources` closes the arena when exiting the block, freeing the arena's memory region.

This example only uses **foreign memory access**, so **it does not require `--enable-native-access`**. However, the FFM classes are preview APIs in JDK 21, so **`--enable-preview` is still required**.

### 3.2. Compile and Run

Create the `PreviewMemoryDemo.java` file exactly as above, then in that directory run with JDK 21:

```bash
mkdir -p out

javac --enable-preview --release 21 \
  -encoding UTF-8 \
  -d out \
  PreviewMemoryDemo.java

java --enable-preview -cp out PreviewMemoryDemo
```

**Actual stdout verified with OpenJDK 21:**

```text
FFM value: 42
```

`javac` may print some notes `Note: ... uses preview features of Java SE 21` to stderr. This is a **normal notice**, not a compile error. To see detailed warnings by location, you can use `-Xlint:preview`.

**Source-file mode** also works in JDK 21:

```bash
java --enable-preview --source 21 PreviewMemoryDemo.java
```

The command above compiles the source in memory and executes it immediately; stdout is still `FFM value: 42`. For multi-class projects, you should choose the two-step workflow or a build tool.

## 4. Runnable Example 2: Calling a C Function with FFM

FFM not only allocates memory, but also allows Java to look up a native symbol and create a **downcall** to a C function. When calling `strlen` on **Linux x86-64**, we need to distinguish between preview permission and native-access permission.

### 4.1. Source: `PreviewStrlenDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public final class PreviewStrlenDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        MemorySegment symbol = linker.defaultLookup().find("strlen").orElseThrow();

        MethodHandle strlen = linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.ADDRESS));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cString = arena.allocateUtf8String("hello FFM");
            long length = (long) strlen.invokeExact(cString);
            System.out.println("strlen: " + length);
        }
    }
}
```

`Linker.nativeLinker()` gets the linker for the current ABI, `defaultLookup()` finds the `strlen` symbol, `FunctionDescriptor` describes the type of the native function, and `downcallHandle` creates a method handle for Java to call native code.

On **64-bit Linux in the example**, the C `size_t` type returned by `strlen` is 64 bits wide, matching `ValueLayout.JAVA_LONG`. On other ABIs, especially 32-bit, you must adjust the signature to match the C ABI rather than assuming `size_t` is always Java `long`. `strlen` returns **the byte length before the NUL byte**, not the number of Unicode code points. The ASCII string `hello FFM` is 9 bytes long.

### 4.2. Compile and Runtime Commands

```bash
javac --enable-preview --release 21 -d out PreviewStrlenDemo.java

java --enable-preview \
  --enable-native-access=ALL-UNNAMED \
  -cp out PreviewStrlenDemo
```

**Stdout verified on OpenJDK 21/Linux x86-64:**

```text
strlen: 9
```

**Roles of the two flags:**

- `--enable-preview` in **javac and java** enables the JDK 21 FFM preview API.
- `--enable-native-access=ALL-UNNAMED` in **java** allows **restricted FFM native operations** for code in the unnamed module (classpath), and avoids a warning when creating a downcall.

If you only use `--enable-preview` and omit the native-access flag, JDK 21 may **still perform the downcall but print a warning** to stderr, for example:

```text
WARNING: A restricted method in java.lang.foreign.Linker has been called
WARNING: java.lang.foreign.Linker::downcallHandle has been called by the unnamed module
WARNING: Use --enable-native-access=ALL-UNNAMED to avoid a warning for this module
```

This is a **native access permission** warning, not a preview error. The restricted native access policy in newer JDKs may be stricter, so do not write code relying on the assumption that it is "just a warning".

If the code belongs to a **named module**, you can grant permission to the specific module name, such as `--enable-native-access=com.example.app`, instead of opening permission to all classpath code. You should not enable it broadly if only one module actually needs to call native code.

## 5. Four Common Error Experiments

### 5.1. Compiling Without Preview Enabled

```bash
javac --release 21 -d out PreviewMemoryDemo.java
```

**Result:** JDK 21 reports something like `Arena is a preview API and is disabled by default`, along with a suggestion to enable `--enable-preview`; `MemorySegment` and `ValueLayout` are also preview APIs. Add the flag to **javac** to fix it.

### 5.2. Compiling Successfully but Running Without the Flag

```bash
javac --enable-preview --release 21 -d out PreviewMemoryDemo.java
java -cp out PreviewMemoryDemo
```

**Actual result on JDK 21:** `UnsupportedClassVersionError` with the message:

```text
Preview features are not enabled for PreviewMemoryDemo
(class file version 65.65535).
Try running with '--enable-preview'
```

`major version 65` corresponds to Java 21, and `minor version 65535` is the indicator of preview bytecode. You can inspect it with:

```bash
javap -verbose -classpath out PreviewMemoryDemo
```

Look for the two lines `major version: 65` and `minor version: 65535`. Run again with `java --enable-preview -cp out PreviewMemoryDemo` on JDK 21.

### 5.3. Compiling Preview of a Non-21 Release With the JDK 21 Compiler

```bash
javac --enable-preview --release 20 PreviewMemoryDemo.java
```

**Actual result:** `error: invalid source release 20 with --enable-preview`, explaining that preview only supports the compiler's current release 21. You cannot use `--enable-preview` to tell JDK 21 to enable JDK 20 preview.

### 5.4. Confusing `--enable-native-access` With `--enable-preview`

- `java --enable-native-access=ALL-UNNAMED -cp out PreviewMemoryDemo` **does not enable** preview.
- `java --enable-preview -cp out PreviewStrlenDemo` **enables** preview, but may warn about a restricted call.
- `java --enable-preview --enable-native-access=ALL-UNNAMED -cp out PreviewStrlenDemo` **properly enables both**.

Remember that `--enable-native-access` cannot fix a `javac` error missing preview, nor can it fix bytecode running on the wrong release.

## 6. Distinguishing FFM Across JDKs

| Java release | FFM Status | Notes |
| --- | --- | --- |
| **JDK 17** | Experimental API under **incubator module** `jdk.incubator.foreign` | Cannot copy JDK 21 source/flags as-is |
| **JDK 19** | First Preview — JEP 424 | Initial FFM preview |
| **JDK 20** | Second Preview — JEP 434 | Preview continues |
| **JDK 21** | **Third Preview — JEP 442** | **Requires `--enable-preview` at compile and run time** |
| **JDK 22** | **Final — JEP 454** | Does not require `--enable-preview` **just for using FFM** |

When migrating from JDK 21 → JDK 22 or newer, **recompile and re-verify the API**: preview APIs and preview bytecode do not guarantee cross-version compatibility. FFM in JDK 22 is a finalized API, but **restricted native operations** still have rules regarding `--enable-native-access`. If the project uses **another** preview feature in the new JDK, the `--enable-preview` flag may still be needed for that other reason.

Do not use `--add-modules jdk.incubator.foreign` from JDK 17 guides for JDK 21 `java.lang.foreign` source code. Also do not confuse `--enable-preview` with `-h` for generating JNI headers: the FFM example does not need a JNI header to call `strlen`.

## 7. Adding the Flags to Maven, Gradle, and IDEs

### 7.1. Maven

Illustrative `pom.xml` fragment, assuming **JDK 21** and compatible plugin versions (real projects should pin plugin versions for reproducible builds):

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <release>21</release>
        <compilerArgs>
          <arg>--enable-preview</arg>
        </compilerArgs>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <argLine>--enable-preview --enable-native-access=ALL-UNNAMED</argLine>
      </configuration>
    </plugin>
  </plugins>
</build>
```

The compiler plugin adds preview to **javac**. Surefire adds preview and native access to the **JVM running unit tests**. When the app runs outside Surefire, the launcher/deployment JVM still needs separate flags. If the project uses JaCoCo or another plugin that modifies `argLine`, you must merge the options so existing `-javaagent` arguments are not lost. For demos that only manipulate memory, the native-access flag can be omitted.

### 7.2. Gradle Groovy DSL

`build.gradle` fragment, assuming the Java plugin is already applied:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.compilerArgs += ['--enable-preview']
}
tasks.withType(Test).configureEach {
    jvmArgs '--enable-preview', '--enable-native-access=ALL-UNNAMED'
}
tasks.withType(JavaExec).configureEach {
    jvmArgs '--enable-preview', '--enable-native-access=ALL-UNNAMED'
}
```

`JavaCompile` controls compilation, `Test` controls the test JVM, and `JavaExec` controls the Java execution task. When running `java -jar` directly after building, you must pass the JVM options in that run command itself.

### 7.3. IDE, CI/CD

- Select **JDK 21** for the Project SDK, compile toolchain, and run JVM.
- Enable preview in both **compiler options** and **VM options** of Run/Debug; do not put `--enable-preview` into program arguments after the main class.
- The test runner has its own JVM options; if Maven/Gradle tests fail even though the terminal run works, check that task.
- Native-downcall code needs the native-access VM flag added for the corresponding module; do not use this flag in place of preview.
- Print `javac -version` and `java -version` in CI logs to confirm which JDK is actually running.

## 8. Safety and Limitations of Preview Mode

`--enable-preview` **does not make foreign memory completely safe**. FFM has contracts regarding lifetime, threads, and the C ABI:

- `Arena.ofConfined()` should only be accessed by the owning thread; segments are no longer valid after the arena is closed.
- `FunctionDescriptor` must match the layout and native ABI; wrong return/argument types or pointer lifetimes can crash the JVM.
- `--enable-native-access=ALL-UNNAMED` grants broad permission to all classpath code; modular applications should grant it only to the named modules that actually need it.
- `strlen` returns the **byte** length of a C string, which is not the same as `String.length()` and is not suitable for measuring an arbitrary number of Unicode characters.
- The restricted FFM method warning when native-access is not enabled in JDK 21 is **not** a promise of the same behavior in later Java releases.

## 9. Short Checklist and Self-Study Questions

**Checklist before running JDK 21 FFM:** verify JDK 21 for both `java`/`javac`; compile with `--enable-preview --release 21`; run with `--enable-preview` before the main class; grant `--enable-native-access` when using restricted methods; verify classpath and ABI; configure compiler/test/main JVMs separately in IDE/Maven/Gradle; do not treat JDK 21 preview bytecode as a portable binary for JDK 22+.

**Questions:**

1. Why does `--enable-preview` need to appear at both compile time and runtime in JDK 21?
2. Is `--release 21` used for `javac` or `java`, and why can't you use `--release 20` with `javac 21 --enable-preview`?
3. Why doesn't `PreviewMemoryDemo` need the native-access flag, while `PreviewStrlenDemo` should have this flag?
4. When runtime preview is missing, what does the `UnsupportedClassVersionError` for class file `65.65535` mean?
5. When moving to JDK 22, why is the preview flag not needed **just to use FFM**, yet you still have to review restricted native access?
6. If Maven compiles successfully but Surefire tests fail due to preview, in which step is the flag missing?

**Key Takeaway:** For **JDK 21 FFM**, the correct commands are **`javac --enable-preview --release 21`** and **`java --enable-preview`**. `--enable-native-access=...` is a **different runtime option**, for restricted native operations, not a replacement for preview. JDK 21 FFM is **Third Preview (JEP 442)**; JDK 22 FFM becomes a **final API (JEP 454)**.

### Official Documentation

- [Oracle — FFM API, JDK 21](https://docs.oracle.com/en/java/javase/21/core/foreign-function-and-memory-api.html).
- [Oracle — Preview Language and VM Features, JDK 21](https://docs.oracle.com/en/java/javase/21/language/preview-language-and-vm-features.html).
- [Oracle — javac, JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
- [Oracle — java launcher, JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [OpenJDK — JEP 442](https://openjdk.org/jeps/442).
- [OpenJDK — JEP 454](https://openjdk.org/jeps/454).
