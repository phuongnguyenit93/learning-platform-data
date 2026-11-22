# Choosing Between Source Code and Precompiled Class When Both Are Found

## 1. Scenario: Same Java Type with Both .java and .class

When compiling `Client.java`, `javac` needs to know how the type `demo.Greeting` is declared. A project might contain both:

- `source-src/demo/Greeting.java` — the source version of that type;
- `lib/demo/Greeting.class` — the precompiled version;
- `client-src/demo/Client.java` — the code referencing `demo.Greeting`.

If the compiler finds both a source file and a class file for **the same implicitly looked-up type**, it must decide which one to use. With `javac` on JDK 17+:

- `-Xprefer:newer` (default): prefers the file with the newer modification timestamp.
- `-Xprefer:source`: prefers the source file when both source and class are found.
- When a source file is chosen implicitly, `javac` may compile that file and emit an additional class file. `-implicit:class` or `-implicit:none` controls **emitting class files for implicit sources**, and does not replace the `-Xprefer` rule.

This rule explains many puzzling incidents: editing a source file while the compiler still uses an old binary; compiling one file unexpectedly emitting a class file for another; a build succeeding on machine A while picking a different dependency on machine B; or compilation succeeding while runtime still loads an old class.

**Learning objectives:** identify where `javac` searches for types, understand the exact conditions where `-Xprefer` applies, observe source/class selection with a runnable example, distinguish `-implicit` from `-Xprefer`, and resolve inconsistent output/runtime classpath issues.

This lesson uses a classpath-based Java project (unnamed module), JDK 17+, and verification examples with JDK 21 `javac`. For Java Platform Module System (JPMS) projects, type lookup in modules follows additional module rules, noted at the end.

## 2. Before Choosing: Where Does javac Look for a Type?

Given the command:

```bash
javac -cp lib --source-path source-src -d out client-src/demo/Client.java
```

the compiler needs declarations from `Client.java` and from types it references, such as `demo.Greeting`. To find types not supplied directly, it inspects the appropriate locations:

| Information source | Option | What is searched? |
| --- | --- | --- |
| **Explicitly named source files** | `client-src/demo/Client.java` (or a list of `.java` files) | Source files the command asks the compiler to process |
| **Source path** | `--source-path source-src` / `-sourcepath source-src` | Dependent source files not directly listed, following package hierarchy |
| **Classpath** | `-cp lib` / `--class-path lib` | Precompiled class files/JARs |
| **Platform modules** | Default system configuration or `--system`/`--release` | Types of the corresponding Java SE platform, per module rules |
| **Module path** | `--module-path` and related options | Compiled modules; lookup rules follow the module graph |

In the **non-modular** example:

1. When both `-cp` and `--source-path` are specified, `javac` searches for **class files on the classpath** and **source files on the source path**.
2. When `-cp` is specified without `--source-path`, `javac` can search for **both `.class` and `.java` on the user classpath**.
3. When no classpath is set, the default user classpath is the current working directory unless affected by environment variables like `CLASSPATH`; specify the classpath explicitly when reproducibility matters.
4. Implicitly located source files must follow the appropriate package structure, e.g., type `demo.Greeting` corresponds to `demo/Greeting.java` under a source-path root.

**`-d out` only chooses where to write output.** In standard classpath usage, it **does not automatically add `out` to the compile classpath**. If you want the compiler to use existing class files under `out` as dependencies, you must specify `-cp out` or an appropriate classpath.

There are two very different kinds of "found": finding two **versions of the same type**, one source and one binary; or finding two **same-named binaries** on two classpath entries. `-Xprefer` handles the case where **both source and class are found**, not choosing between two different JARs containing the same class.

## 3. When Exactly Does -Xprefer Apply?

`javac` supports:

```text
-Xprefer:source
-Xprefer:newer
```

| Mode | When both source and class are found for an implicitly searched type | If only one form exists |
| --- | --- | --- |
| `-Xprefer:newer` | Picks the file with the newer modification time; this is the default | Uses whichever form was found |
| `-Xprefer:source` | Picks the source file | Uses whichever form was found |

Oracle documentation clearly defines this scope as **implicitly compiled classes**: the compiler encounters a needed type whose source file **was not in the list of explicitly passed source files**.

Example of two fundamentally different commands:

```bash
# Greeting.java is explicitly requested for compilation
javac -d out client-src/demo/Client.java source-src/demo/Greeting.java
```

```bash
# Only Client.java is an explicit source; Greeting is found via sourcepath/classpath
javac -cp lib --source-path source-src -Xprefer:source -d out client-src/demo/Client.java
```

In the first command, `Greeting.java` is a **directly requested source input**. No timestamp comparison with a `Greeting.class` is needed to decide whether to process that source file.

In the second command, the compiler starts only from `Client.java` and searches for `Greeting` along the search paths. Only if both forms exist does `-Xprefer` govern which version is read.

**Do not interpret `-Xprefer:source` as "always recompile every source file in the project."** It does not scan the entire repository and has no effect on a type the compiler does not need to look up or cannot find source for. Conversely, when a source is picked implicitly, the compiler may emit additional class files that you did not list on the command line.

## 4. Runnable Example: Same Type Name, Two Versions with Different Content

Create a new directory `prefer-demo` with the following source tree:

```text
prefer-demo/
├── binary-src/
│   └── demo/
│       └── Greeting.java
├── source-src/
│   └── demo/
│       └── Greeting.java
└── client-src/
    └── demo/
        └── Client.java
```

The two `Greeting.java` files have **the same fully qualified name `demo.Greeting`**, yet different contents. This layout is for testing source/binary selection; do not pass both files into the same compile command.

### 4.1. Version Used to Build the Precompiled Binary

File `binary-src/demo/Greeting.java`:

```java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String text() {
        return "BINARY";
    }
}
```

### 4.2. Source Version Available to the Compiler

File `source-src/demo/Greeting.java`:

```java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String text() {
        return "SOURCE";
    }
}
```

Both files declare the same package `demo` and public class `Greeting`, differing in the body of `text()`. Since they share the same method signature, `Client` compiles validly against either; the difference appears at runtime for easy observation.

### 4.3. Client Uses Greeting Without Redefining It

File `client-src/demo/Client.java`:

```java
package demo;

public final class Client {
    private Client() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.text());
    }
}
```

`Client` and `Greeting` are in the same package, so `import demo.Greeting` is not needed. `Client` simply calls the public method present in both versions of `Greeting`.

### 4.4. Compile the BINARY Version into Directory lib

From `prefer-demo`:

```bash
javac --release 17 -d lib binary-src/demo/Greeting.java
```

Result:

```text
lib/
└── demo/
    └── Greeting.class
```

This class file has a `text()` method returning `"BINARY"`. From this point on, we have a valid binary dependency. `lib` is the **compile/runtime classpath root**, not a package name.

Do not put `binary-src` on the source path for subsequent test commands; the intended source candidate is in `source-src`.

## 5. Experiment 1: Forcing javac to Prefer Source

The following command lists only **Client.java** as an explicit source input. The compiler will have to look up `demo.Greeting`:

```bash
javac --release 17 -cp lib --source-path source-src -Xprefer:source -implicit:class -d out client-src/demo/Client.java
```

Breakdown of options:

- `-cp lib` makes `lib/demo/Greeting.class` visible to the compiler.
- `--source-path source-src` makes `source-src/demo/Greeting.java` visible to the compiler.
- `-Xprefer:source` instructs it to take the declaration from **source** if both are found.
- `-implicit:class` asks it to generate class files for **implicitly** read sources.
- `-d out` keeps this compilation's output separate from `lib`.
- `--release 17` keeps the example on Java 17; it does not alter `-Xprefer`'s file-selection logic.

After successful compilation, `out` contains:

```text
out/
└── demo/
    ├── Client.class
    └── Greeting.class
```

`Greeting.class` in `out` was emitted by the compiler from **source-src/demo/Greeting.java**, not automatically copied from `lib/demo/Greeting.class`.

Run on Linux/macOS:

```bash
java -cp "out:lib" demo.Client
```

Or Windows PowerShell:

```powershell
java -cp 'out;lib' demo.Client
```

**Exact stdout:**

```text
SOURCE
```

Reason: the compiler chose the source and generated `out/demo/Greeting.class`; the runtime classpath lists `out` **before** `lib`, so the JVM loads the newly compiled version. If reversed to `lib:out` on Linux/macOS (or `lib;out` on Windows), the program prints `BINARY` because the runtime classpath picks the version in `lib` first. **javac's compile-time selection rules are not the same as runtime class-loading order.**

This experiment does not depend on timestamps: `-Xprefer:source` prefers source even if the class file is newer.

## 6. Experiment 2: Default Selection of the Newer File

Omitting `-Xprefer:source` makes `javac` use the mode equivalent to `-Xprefer:newer`. When both source and class are found, the compiler compares the modification times of the two files. To predict the outcome, we must **pin the timestamps before testing**, instead of relying on which file happened to be created first.

On Linux/macOS with `touch`, in directory `prefer-demo`:

```bash
touch -t 202001010000 source-src/demo/Greeting.java
touch -t 202101010000 lib/demo/Greeting.class
```

These two commands only adjust mtime so that the class file is newer than the source file. They do not alter source or binary contents. With Windows PowerShell:

```powershell
(Get-Item 'source-src/demo/Greeting.java').LastWriteTimeUtc = [datetime]'2020-01-01T00:00:00Z'
(Get-Item 'lib/demo/Greeting.class').LastWriteTimeUtc = [datetime]'2021-01-01T00:00:00Z'
```

Then use a **different output directory**, avoiding leftover class files from the previous experiment:

```bash
javac --release 17 -cp lib --source-path source-src -Xprefer:newer -d out-newer client-src/demo/Client.java
```

With the mtime just set, `lib/demo/Greeting.class` is newer than `source-src/demo/Greeting.java`. The compiler reads the class file; it only needs to emit `out-newer/demo/Client.class` and does not need to compile `Greeting.java` into `out-newer`.

Run on Linux/macOS:

```bash
java -cp "out-newer:lib" demo.Client
```

Or Windows PowerShell:

```powershell
java -cp 'out-newer;lib' demo.Client
```

**Exact stdout with the fixed files and mtime:**

```text
BINARY
```

`Greeting.class` exists only in `lib` in this test, so the JVM loads the version returning `BINARY`. Even if `-Xprefer:newer` is omitted from the compile command, it remains `javac`'s **default mode**.

Changing mtime so the source is newer than the class flips the `newer` mode's decision when everything else stays constant. This is why copying sources, restoring artifacts from a cache, changing filesystems, or extracting archives with different timestamps can cause `javac` to pick a different input even with identical filenames.

**Timestamps are not version control.** A class file with a newer mtime is not guaranteed to contain newer functional code. If strict reproducibility is required, record hashes, source/build versions, and the `-Xprefer` setting; relying solely on mtime is risky.

## 7. Experiment 3: Source Is Read, Without Emitting a New Class

Run:

```bash
javac --release 17 -cp lib --source-path source-src -Xprefer:source -implicit:none -d out-none client-src/demo/Client.java
```

`-Xprefer:source` still lets the compiler use `Greeting.java` to check references from `Client.java`. However, `-implicit:none` **does not emit `Greeting.class` from implicitly found sources**. In this example, the output only needs:

```text
out-none/
└── demo/
    └── Client.class
```

Run on Linux/macOS:

```bash
java -cp "out-none:lib" demo.Client
```

Or Windows PowerShell:

```powershell
java -cp 'out-none;lib' demo.Client
```

**Stdout:**

```text
BINARY
```

Because `out-none` does not contain `Greeting.class`, the JVM uses `lib/demo/Greeting.class`, returning `BINARY`. This is an important situation: **javac checked the source while runtime loaded a different binary**.

In this test, both `Greeting` versions share the same `text():String` signature, so the call still links. If the source adds a new method that the binary lacks, the client can compile successfully against the source and then fail with `NoSuchMethodError` when run against the old binary. Therefore, do not treat compiling successfully with `-implicit:none` as proof that the runtime dependency is compatible.

**`-implicit:none` does not mean "read class instead of source."** It only disables emitting class files for implicitly found dependent sources. If a source file is **explicitly listed** on the command line, it remains an explicit source compilation unit and is not treated as implicit just because of this flag.

## 8. -Xprefer and -implicit Answer Two Different Questions

| Question | Option | Effect |
| --- | --- | --- |
| When both `Greeting.java` and `Greeting.class` exist, **which should the compiler read**? | `-Xprefer:source` or `-Xprefer:newer` | Chooses source or binary to obtain type declarations |
| If the compiler **picked an implicitly found source file**, should it emit `.class` for it? | `-implicit:class` or `-implicit:none` | Emits an extra class file or uses the source solely for type info |

Some key cases to remember:

| Candidate availability | Prefer flag | Implicit flag | Outcome |
| --- | --- | --- | --- |
| Only class found | Any | Any | Uses class; does not compile nonexistent source |
| Only source found | Any | `-implicit:class` | Reads source and emits class for implicit source |
| Only source found | Any | `-implicit:none` | Reads source; does not emit class for implicit source |
| Both found, source newer | `-Xprefer:newer` | `-implicit:class` | Picks source; emits class |
| Both found, class newer | `-Xprefer:newer` | `-implicit:class` | Picks class; does not emit class from that source |
| Both found, class newer | `-Xprefer:source` | `-implicit:class` | Picks source; emits class |
| Both found | `-Xprefer:source` | `-implicit:none` | Picks source; does not emit class for implicit source |

When `-implicit` is omitted, `javac` defaults to emitting class files for implicitly found sources. If annotation processing is active and a source is discovered late, the compiler may warn that a file was compiled without undergoing annotation processing normally. To avoid relying on implicit behavior in builds with processors, consider **explicitly listing** every source that needs annotation processing and explicitly setting the `-implicit` mode.

`-Xprefer:source` is also useful if an annotation processor needs to inspect annotations with `SOURCE` retention; compiled class files do not retain annotations of that kind. Even so, whether a processor runs and sees annotations depends on source handling, processor path, and compilation setup, not just `-Xprefer`.

## 9. Observing Which File javac Chose

When diagnosing an unexpected build result, **do not guess from the program's stdout**. The runtime classpath can mask compilation decisions. Combine three verification checks:

### 9.1. Using -verbose

```bash
javac --release 17 -verbose -cp lib --source-path source-src -Xprefer:source -implicit:class -d out client-src/demo/Client.java
```

`javac -verbose` reports information such as parsed source files, loaded types, and written class files. In the log, locate the exact path `source-src/demo/Greeting.java` or `lib/demo/Greeting.class` and the output files. **Log wording/formatting depends on the JDK version**, so do not write tests matching a verbatim log line from the current compiler.

### 9.2. Inspecting the Generated Class File Itself

After compiling into `out`:

```bash
javap -c -classpath out demo.Greeting
```

Because the two versions have distinct constant strings `SOURCE` and `BINARY`, `javap -c` output helps determine which implementation produced the artifact. You can also run `java -cp out demo.Client` directly if all necessary dependencies reside in `out`.

If `out` lacks `Greeting.class`, `javap -classpath out demo.Greeting` will not find that type. Do not casually add `lib` to `javap`'s classpath without noticing: if you run `-classpath out:lib`, `javap` can read the binary file from `lib`, misleading you into thinking it came from `out`.

### 9.3. Checking Each Classpath Root in Order

A program may compile against source yet run from an old JAR because the runtime classpath places that JAR ahead of the new output directory. Record:

- Compile classpath, source path, and the full path order;
- Compile output directory and the actual list of `.class` files;
- Runtime classpath, module path, and dependencies;
- Compiler version, `-Xprefer`, `-implicit`, and mtimes/hashes of both candidates.

If you need to know where a class was loaded from by the JVM at runtime, depending on the Java version you can use class-loading logging such as `-Xlog:class+load=info` on HotSpot. This is a **runtime tool**, not a `javac` option; read the log and inspect the class source path rather than relying solely on class name.

## 10. Cases Easily Confused with Source/Class Selection

### 10.1. Two JARs Containing the Same Class Name

If both `lib/old.jar` and `lib/new.jar` contain `demo.Greeting`, that is a classpath issue with **two binary candidates**. `-Xprefer:source` does not choose between two JARs. Check classpath ordering, classloaders, module configuration, and remove duplicate dependencies.

### 10.2. Source Is Not in Any Path Searched by javac

If `Greeting.java` exists in the repository yet is neither on `--source-path` nor explicitly listed, the compiler will not necessarily find it. `-Xprefer:source` **does not force the compiler to scan every directory on disk**.

Example:

```bash
javac --release 17 -cp lib -Xprefer:source -d out-only-binary client-src/demo/Client.java
```

In the example, `lib` contains only class files; no source path points to `source-src`. The compiler will use `Greeting.class` from `lib` if no other source candidate exists in the search paths. The prefer flag does not fabricate source candidates from an unconfigured directory.

### 10.3. A Java File Explicitly Named on the Command Line

This command requests compiling `Greeting.java` explicitly, independent of `lib/demo/Greeting.class`'s timestamp:

```bash
javac --release 17 -cp lib -d out-explicit client-src/demo/Client.java source-src/demo/Greeting.java
```

Then place the new output before `lib` on the runtime classpath to run the newly compiled version. If you pass **two source files** both declaring public `demo.Greeting` at once, that is a duplicate definition error, not an `-Xprefer` problem.

### 10.4. Compiler Reports Errors Due to New Source vs. Old Binary

If `source-src/demo/Greeting.java` has a different API than the binary, switching from `newer` to `source` can cause the client to be checked against a different API, leading to compile or runtime linkage errors. This does not contradict Java rules; it indicates the build is mixing two dependency versions. Lock versions, perform a clean build, and ensure binaries match the chosen sources.

### 10.5. -d out Is Not a Classpath

The command `javac -d out Client.java` only specifies the output directory. To use classes compiled in a prior run inside `out`, pass `-cp out` (along with other dependencies) in the next compilation. Do not assume a file's presence in the output directory guarantees the compiler reads it from the classpath.

### 10.6. Picking Source by mtime Does Not Mean Picking the Right Content

Git checkouts, archive extraction, clock synchronization, and caching can change mtime even when byte contents are unchanged. `-Xprefer:newer` is an mtime-based strategy, **not** a hash-comparison or semver-reading algorithm. For important builds, manage dependencies and source inputs via a build system with checksums, avoiding reliance on accidental file modification order.

## 11. Limitations with Java Modules (JPMS)

The experiments above use package-based source/class lookup in the **unnamed module**. When `module-info.java` is present, module resolution and package readability/exports apply before the compiler searches for related types:

- Modules on `--module-path` typically supply **compiled class files**; the compiler does not automatically look for substitute source files merely because an identically named file exists somewhere.
- Sources for one or more modules being compiled can be supplied via explicit files, `--source-path` (single module), or `--module-source-path` (multiple modules), depending on the mode and project layout.
- Certain lookups within **the module being compiled** also consider the output module per rules described in `javac` documentation, differing from the simple classpath setup in this lesson.
- `-Xprefer` only matters where lookups yield both source and class candidates; it should not be used to solve split packages, module readability, or broken module dependency graphs.

When working with JPMS, consult **Searching for Module, Package and Type Declarations** in the exact version's `javac` documentation, along with `--module-path`, `--module-source-path`, and `--patch-module` if applicable. This lesson highlights the classpath case because it directly demonstrates `-Xprefer` and `-implicit` behavior.

## 12. Practical Workflow to Select and Verify the Right Source

1. **Identify the type to resolve** and check whether it is an explicitly listed source or an implicitly looked-up dependency.
2. **Record compile inputs:** JDK version, cwd, ordered classpath/sourcepath, source files, binary dependencies, `-Xprefer`, and `-implicit`.
3. **Locate both candidates:** is the source under the right source-path root? Does the class file/JAR have the right package and binary name? Are there duplicate classes under another root?
4. **Decide the policy:** keep default `newer` if mtime is acceptable; pick `-Xprefer:source` when intentionally preferring source and understanding the consequences.
5. **Decide class emission:** use `-implicit:class` to keep binaries synced for implicit sources; use `-implicit:none` when there is a clear reason and runtime dependencies are managed accordingly.
6. **Compile into an isolated output directory**, avoiding leftover classes from other experiments.
7. **Verify the compilation decision** with `-verbose`, output listings, and `javap`; do not conclude from runtime logs alone.
8. **Inspect the runtime classpath** in exact order and run the program/tests.
9. **For long-term build stability**, favor explicit source sets, locked dependencies, and a build tool managing each source set, rather than relying on mtime to resolve differing API versions.

## 13. Self-Check Exercises and Answers

**Question 1.** `source-src/demo/Greeting.java` is newer than `lib/demo/Greeting.class`. The compiler finds both when processing `Client.java`, with no `-Xprefer` set. Which does it prefer?

**Answer:** `-Xprefer:newer` is the default, so it chooses **source** because the source mtime is newer, and may then emit a class file for it per `-implicit`.

**Question 2.** The class is newer than the source, yet you want to ensure the compiler reads source so an annotation processor sees `SOURCE`-retention annotations. What should you choose?

**Answer:** `-Xprefer:source` for the implicit lookup case having both source/class. Also verify processor configuration and how source files are supplied, because choosing source does not replace configuring annotation processing.

**Question 3.** Does `-Xprefer:source -implicit:none` mean "the compiler will not use source"?

**Answer:** False. The compiler can still read source for type checking. `-implicit:none` only suppresses emitting class files for **implicitly** found sources.

**Question 4.** Does `javac -cp lib -Xprefer:source Client.java` automatically find `source-src/demo/Greeting.java`?

**Answer:** No, if `source-src` is not on the appropriate source lookup path. `-Xprefer` only selects among candidates the compiler actually found.

**Question 5.** Compilation chose source and generated `out/demo/Greeting.class`, yet running with classpath `lib:out` prints `BINARY`. Why?

**Answer:** The runtime classpath lists `lib` first. The JVM loads the class file from `lib`; this is a runtime class-loading rule, separate from `javac`'s compile-time source/class selection.

**Question 6.** Two JARs both contain `demo.Greeting`. Does `-Xprefer:source` pick the newer JAR?

**Answer:** No. Those are two same-named binaries, not a source/class pair. Check classpath order, dependency resolution, and module/classloader configuration.

**Question 7.** Why can a build using `-Xprefer:newer` still be non-reproducible despite identical source commit and compiler version?

**Answer:** The mtimes of source/class files, classpath/sourcepath, and binary dependencies may differ. Those inputs must be recorded or managed by a controlled build.

## 14. Official References

- **JDK 21 — The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — sections `-Xprefer`, `-implicit`, `--source-path`, `--class-path`, `-verbose`, and **Searching for Module, Package and Type Declarations**.
- **JDK 21 — The java Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html — classpath/runtime and running classes.
- **JDK 21 — The javap Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html — viewing class file output, methods, and bytecode.
- **JLS Java SE 21:** https://docs.oracle.com/javase/specs/jls/se21/html/ — type declaration semantics, imports, type names, and binary compatibility.
- **JVMS Java SE 21:** https://docs.oracle.com/javase/specs/jvms/se21/html/ — class file definitions, symbolic references, and class loading/linking.

Key point to remember: **`-Xprefer` chooses between source and class when the compiler implicitly looks up a type and finds both; `-implicit` decides whether to emit a class from an implicitly found source; and the runtime classpath determines which class file the JVM loads at runtime.** To predict the result accurately, examine all three layers.