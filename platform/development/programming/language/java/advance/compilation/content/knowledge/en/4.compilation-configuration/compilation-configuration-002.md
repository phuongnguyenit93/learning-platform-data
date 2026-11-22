# Implicit Source Dependency Compilation and the `javac` `-implicit` Option

In a Java project, a compilation command might list only a single `.java` file, yet `javac` still needs to read additional types used by that file. If it finds the source code of a dependent type, the compiler can **implicitly compile** that source code and emit extra `.class` files even though the file was not listed on the command line. The `-implicit:class` or `-implicit:none` option controls **whether `.class` files are generated for implicitly discovered source files**.

Understanding this mechanism properly is important when organizing source code, writing manual compilation commands, diagnosing why an output directory contains extra or missing classes, working with annotation processors, and designing reproducible build workflows. This lesson applies directly to `javac` on Java 17+; the examples were verified using JDK 21.

## 1. Distinguishing explicitly specified sources from implicitly discovered sources

Consider the command:

```bash
javac -sourcepath src -d out src/demo/App.java
```

Here `src/demo/App.java` is the **explicit input**: the caller requested compiling it. If `App` uses `demo.Greeting`, the compiler needs the declaration of `Greeting` to check names, access modifiers, parameter types, and return types. It can locate either a compiled `Greeting.class` or `src/demo/Greeting.java` via search paths.

When the compiler reads `Greeting.java` for type information even though that file was not listed in the command, it is an **implicitly discovered source** (implicitly referenced/loaded source). Under default behavior, `javac` also generates `Greeting.class`. However, **being read for type analysis** and **having a class file emitted** are two distinct behaviors that must be separated.

Examples of dependencies that can cause the compiler to look up type information:

- `new Greeting()`, invoking a static method `Greeting.message()`, or accessing a field;
- `extends BaseClass`, `implements Interface`, method signatures, and parameter types;
- types not appearing directly on the current source line yet required to resolve an inheritance hierarchy or a call.

The dependency graph needed for type checking can be wider than the list of files the user passed to `javac`.

```text
Command: javac ... App.java
                     |
                     v
                  App.java  (explicit source)
                     |
            needs Greeting declaration
                     |
             +-------+--------+
             |                |
       Greeting.class    Greeting.java
       (if class chosen) (if source chosen)
                              |
                      -implicit:class
                      -> may emit Greeting.class
                              |
                      -implicit:none
                      -> does not emit Greeting.class implicitly
```

The diagram shows the conceptual flow; whether the compiler picks `.java` or `.class` also depends on locations, modification timestamps, and search options.

## 2. What do `-implicit:class` and `-implicit:none` actually do?

| Mode | Source File Named Directly in Command | Source File Discovered Implicitly by Compiler | Key Takeaway |
| --- | --- | --- | --- |
| Without passing `-implicit` | Compiled and emits `.class` per command | Emits `.class` by default too | Output files can appear from sources absent from the command list |
| `-implicit:class` | Compiled and emits `.class` | Permitted to emit `.class` | Explicitly states intent to use automatic behavior |
| `-implicit:none` | Still compiled and emits `.class` | Does not emit `.class` for implicitly loaded sources | Does **not** forbid the compiler from reading or analyzing dependent source code |

The easiest point to confuse: **`-implicit:none` does not mean “other source files are forbidden”, nor is it equivalent to “type-check only within a single file”.** The compiler can still read and analyze a dependent source to verify the program is valid; only class-file generation for implicit sources is suppressed.

Moreover, `-implicit:none` does not make classes already on `-classpath` vanish, does not stop an annotation processor from generating sources in its own flow, and does not guarantee a complete set of class outputs to run the program. To control explicit inputs, manage the `.java` file list, source path, and classpath together.

Both values are a single `javac` option; you can write:

```bash
javac -implicit:class ...
javac -implicit:none ...
```

There is no `-implicit:true` or `-implicit:false` in this syntax.

## 3. Runnable Java 17+ example: one input and one dependent source

Create the directory structure:

```text
example/
└── src/
    └── demo/
        ├── App.java
        └── Greeting.java
```

Contents of `src/demo/App.java`:

```java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

Contents of `src/demo/Greeting.java`:

```java
package demo;

public final class Greeting {
    private Greeting() {
    }

    static String message() {
        return "Hello from Greeting";
    }
}
```

In the `example` directory, create **three empty output directories** with the three commands below (works in Bash, PowerShell, or Command Prompt):

```text
mkdir out-class
mkdir out-none
mkdir out-explicit
```

Each run of the example should start from empty outputs: stale class files left over from another trial can skew conclusions.

### Case A: allowing implicit class file generation

```bash
javac -encoding UTF-8 -sourcepath src -d out-class -implicit:class src/demo/App.java
java -cp out-class demo.App
```

Exact stdout:

```text
Hello from Greeting
```

Inside an initially empty output directory, two files appear:

```text
out-class/demo/App.class
out-class/demo/Greeting.class
```

`App.java` is the explicit source; `Greeting.java` was discovered only because `App` needed type `Greeting`. `-implicit:class` permits the compiler to emit `Greeting.class` alongside `App.class`.

### Case B: suppressing class file generation for implicit sources

```bash
javac -encoding UTF-8 -sourcepath src -d out-none -implicit:none src/demo/App.java
```

The compilation command **succeeds**, yet starting from an empty output directory only this appears:

```text
out-none/demo/App.class
```

`Greeting.java` supplied enough information to check and compile `App`, yet `Greeting.class` was not generated. If run:

```bash
java -cp out-none demo.App
```

the program will fail when needing `Greeting`, typically with `NoClassDefFoundError: demo/Greeting` (full stack trace text may vary across JDKs). **Successful compilation does not mean there are enough class files to run.** This failure stems from the runtime classpath lacking `Greeting.class`, not from `-implicit:none` making `App`'s Java bytecode invalid.

### Case C: explicitly specifying both sources

```bash
javac -encoding UTF-8 -sourcepath src -d out-explicit -implicit:none src/demo/App.java src/demo/Greeting.java
java -cp out-explicit demo.App
```

Exact stdout:

```text
Hello from Greeting
```

This time both appear:

```text
out-explicit/demo/App.class
out-explicit/demo/Greeting.class
```

`-implicit:none` does **not** suppress `Greeting`'s output because `Greeting.java` was listed explicitly. This is the clearest distinction between *implicitly discovered dependent sources* and *sources the caller asked to compile*.

## 4. Where does `javac` look for dependent sources?

Common paths when compiling classpath-based Java (without module layout yet):

| Option | Role |
| --- | --- |
| `-sourcepath src` or `--source-path src` | Where to look for extra `.java` files following package structure when type declarations are needed |
| `-classpath libs` / `-cp libs` | Where to look for library `.class` files and compiled types |
| `-d out` | Destination for writing output class files; does **not automatically** add `out` to the classpath |
| `-implicit:class` / `-implicit:none` | Whether to emit `.class` files for **implicitly discovered sources** |

With the example option `-sourcepath src`, when needing `demo.Greeting`, the compiler looks up the source at the corresponding path `src/demo/Greeting.java`; from there it parses the type declaration. The path to the source must match the package name.

If you do **not** configure a separate source path during classpath compilation, `javac` can also search for `.java` files on the user classpath. That is why running a command in a different directory or with a different `CLASSPATH` can pick up an unexpected set of dependent sources. Setting `-sourcepath` and `-classpath` explicitly reduces unexpected inputs.

When **both source and class** of the same type exist and participate in lookup, `javac` defaults to using the one with the newer modification time (`-Xprefer:newer`). The advanced option `-Xprefer:source` prefers the source. In CI environments, mere timestamp differences between two machines can cause the compiler to choose different inputs if sources/classes overlap. Never treat file modification times as a stable dependency-resolution mechanism: separate outputs, control the classpath, and use clean builds when investigating.

Note on Java modules (JPMS): builds with `module-info.java` add `--module-path`, `--module-source-path`, and module-specific rules. The `-sourcepath src` example here illustrates a project **without module declarations**; do not mechanically apply classpath lookup formulas to multi-module builds.

## 5. Implicit compilation differs from incremental compilation

**Implicit compilation (implicit source compilation)** is compiler behavior when needing a dependent source the caller did not specify directly. **Incremental compilation** is a build-tool strategy deciding which set of sources to invoke the compiler on after edits. The two mechanisms are related yet not identical.

Suppose a project has `App.java` depending on `Greeting.java`. If the command lists only `App.java`, `-implicit:class` mode can emit `Greeting.class` as well, even when the script did not intentionally list `Greeting.java`. When the script switches to `-implicit:none`, the output set can lack `Greeting.class`. A previous run leaving class files in the output directory masks this bug; a clean build can fail at runtime.

Tools like Gradle/Maven typically manage source sets, paths, compiler options, annotation processors, and outputs themselves. Do not assume they always invoke `javac` with just a single source, nor enable `-implicit:none` globally merely hoping for a “faster build”. Incremental optimization must rely on actual plugin mechanisms and configs. Changing `-implicit` alters the set of emitted artifacts, yet **does not replace the build tool's dependency tracking**.

To compare outputs, test separately in empty `out-class`, `out-none`, and `out-explicit` directories as in the example. Do not experiment on top of the class directory of an active build.

## 6. Annotation processing: an area needing caution

Annotation processing can inspect declarations and generate additional source files across processing rounds. A source file discovered **implicitly** by the compiler might appear after annotation processing has already run; when `-implicit` is unspecified, the compiler may warn that the source was compiled without undergoing annotation processing like explicit sources. Specifying `-implicit:class` or `-implicit:none` stops that default missing-`-implicit` warning from appearing solely due to an omitted `-implicit` value.

Points to distinguish:

- `-implicit:none`: controls **class files of implicitly discovered sources**, not a switch to disable annotation processing.
- `-proc:none`: disables annotation processing.
- `-proc:only`: runs annotation processing without executing the subsequent bytecode compilation step.
- `-processor`, `-processorpath`, or `--processor-module-path`: selects processors and processor lookup paths per the corresponding mechanism.

If an annotation processor needs to see `SOURCE` annotations on dependent files, relying solely on the compiler implicitly loading sources may be insufficient. Include sources requiring processing in the explicit compilation units or structure the build per the processor's documentation. **Do not interpret the disappearance of warnings upon passing `-implicit` as a guarantee that the processor processed all dependent files.**

From JDK 23 onward, automatic discovery/execution of annotation processors has been tightened compared to some older versions; therefore declare processor configuration explicitly and verify on the project's exact JDK. This does not alter the core meaning of `-implicit:class` / `-implicit:none`.

## 7. How to diagnose implicit compilation results

When a source “mysteriously gets compiled” or “the compiler reports success yet a class is missing”, follow these steps in order:

1. **Record the full `javac` command.** Clearly separate the directly listed `.java` files, `-sourcepath`, `-classpath`, `-d`, `-implicit`, annotation processors, and the JDK in use.
2. **Identify the missing or extra type.** For example, does `demo.Greeting` have a `.java` on the source path, a `.class` on the classpath, or both?
3. **Check outputs from a clean directory.** If `Greeting.class` already existed, you cannot conclude the current compilation run created it.
4. **Observe `javac -verbose`.** When needed, add `-verbose` to the command to inspect which files are read, parsed, and written; verbose log contents vary by JDK and environment, so do not treat verbose output as an invariant test assertion.
5. **Compare `-implicit:class` and `-implicit:none`.** Change only this option between two trials sharing identical sources/classpath and empty output directories. Compare generated files, not merely exit code 0.
6. **Try listing the source explicitly.** If moving `Greeting.java` from implicit source to explicit input makes `Greeting.class` appear even with `-implicit:none`, the cause is confirmed.
7. **Check runtime separately.** `java -cp ...` needs visibility of all dependent classes at execution time; the runtime classpath is not inferred merely from compile-time source paths.

Common symptoms:

| Symptom | What to Check |
| --- | --- |
| Adding `-implicit:none` causes `Greeting.class` to be missing | `Greeting.java` was only found implicitly by the compiler; compile it explicitly or supply `.class` |
| `javac` reports `cannot find symbol` for `Greeting` | Source is not under the matching package on source path, class is not on classpath, or path/casing is wrong |
| Machine A emits extra classes, Machine B does not | Different classpath/sourcepath, pre-existing `.class` files, `.java`/`.class` timestamps, compiler/JDK, or build invocation |
| Compile passes yet `java` throws `NoClassDefFoundError` | Class missing at runtime; inspect outputs and runtime classpath, including `-implicit:none` cases |
| Warnings appear regarding implicit compilation and annotation processing | Check sources passed to command, annotation processing schedule, and `-implicit`; do not just silence the warning |
| Editing `Greeting.java` changes `App.class`/outputs even though command names only App | Compiler read the dependent source; inspect `-sourcepath`, `-Xprefer`, and implicit mode |

## 8. Common scenarios during project maintenance

**Small projects running `javac` directly.** If convenience is desired, `-implicit:class` with an explicit source path can be acceptable. However, to ensure complete runtime results, verify that required classes were emitted to output or reside on the classpath. The set of implicitly discovered dependencies is not an official build manifest.

**CI scripts wanting an explicit input list.** You can use `-implicit:none` to prevent generating classes from implicitly discovered sources, while providing all `.java` files needing compilation in the explicit list or prebuilt classes in valid dependencies. `-implicit:none` **alone does not guarantee** the script avoids sources outside the list; the compiler can still read those sources for type checking. To prevent unintended sources, constrain `-sourcepath` and `-classpath` appropriately.

**Stale outputs already present.** Do not use “compilation succeeded” as proof of completeness. If the compiler finds an old `Greeting.class` or runtime accidentally picks it up, missing-artifact errors may appear only after cleaning the build or running on CI. Reproduce with a clean output directory and explicit classpath.

**Projects with annotation processors.** A source name appearing on the lookup path does not guarantee it undergoes the same annotation processing rounds as directly listed sources. Verify generated sources and generated classes are produced per the processor's contract; avoid tweaking `-implicit` merely to treat symptoms without understanding the compile flow.

## 9. Practice exercise with answers

Using the two files `App.java` and `Greeting.java` from section 3, with three empty output directories, predict the outcome and then run each command:

1. `javac -sourcepath src -d out-class -implicit:class src/demo/App.java` — will produce **two** class files: `App.class` and `Greeting.class`.
2. `javac -sourcepath src -d out-none -implicit:none src/demo/App.java` — will produce **one** class file: `App.class`. Try running from `out-none` to see the runtime error due to missing `Greeting`.
3. `javac -sourcepath src -d out-explicit -implicit:none src/demo/App.java src/demo/Greeting.java` — will produce **two** class files; runs and prints `Hello from Greeting`.

Follow-up question: if `Greeting.java` contains a syntax error while being referenced by `App.java`, does `-implicit:none` “ignore” the error? **No:** the compiler must read the dependent source to obtain type declarations; source errors can fail compilation even when the compiler does not emit `Greeting.class`. Therefore `-implicit:none` controls *output*, not *source readability* or *type-verification scope*.

Another question: why does `javac -implicit:none App.java Greeting.java` still emit `Greeting.class`? Because `Greeting.java` is an **explicit** source, not part of the “implicitly referenced source files” group controlled by the option.

## 10. Principles of application

When inspecting a Java build, always ask three separate questions: **(1) which sources was the compiler directly instructed to compile; (2) which additional sources/classes did the compiler locate to resolve types; (3) which class files were actually written to output?** `-sourcepath`/`-classpath` primarily answer question (2); `-implicit:class` and `-implicit:none` partly control question (3); the `.java` input list determines question (1).

For controllable and reproducible builds, keep toolchains, paths, source inputs, and clean outputs consistent; avoid relying on stale files or timestamps. For Gradle/Maven, inspect the compiler configuration of the plugin version in use before adding manual flags. Standard reference documentation: [`javac` in JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), sections **`-implicit`**, **Additional Source Files**, and **Searching for Module, Package and Type Declarations**.