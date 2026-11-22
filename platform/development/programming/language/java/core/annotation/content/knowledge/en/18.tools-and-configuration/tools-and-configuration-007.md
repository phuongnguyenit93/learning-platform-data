# Relating `--release`, `SourceVersion`, and JDK Compatibility in Annotation Processing

## 1. Three Versions to Separate

When compiling a project with an **annotation processor**, at least three version-related questions typically arise:

1. **Which JDK is running `javac` and the processor?** This is the *host JDK*: the compiler tool and the JVM executing the processor's code.
2. **Which Java version does the application code need to be compatible with?** The `javac --release N` option sets the language scope, platform APIs, and class file format that the application code is compiled to target.
3. **Up to which Java source level does the processor declare it understands?** `javax.lang.model.SourceVersion`, used via `@SupportedSourceVersion` or `getSupportedSourceVersion()`, describes the processor's capability to handle the source model.

These three pieces of information are **related but not equivalent**.

For example, using **JDK 21 to run `javac`**, compiling **application code targeting Java 17** with `--release 17`, and using a processor with `@SupportedSourceVersion(SourceVersion.RELEASE_17)` is a valid configuration. The host JDK does **not** need to be exactly 17, as long as the `javac` being used supports `--release 17` and the processor along with its dependencies can run on the host JDK.

Diagram:

```text
Host JDK (for example, JDK 21)
  ├── Runs javac
  ├── Runs annotation processor in the compilation process's JVM
  │      └── Processor declares SourceVersion.RELEASE_17
  │          (source-handling capability, does not configure output bytecode)
  └── javac --release 17 to compile the application
         ├── Java 17 language rules
         ├── Platform APIs corresponding to Java 17
         └── Java 17 class file version (major version 61)
                     │
                     v
            Java 17+ environment can load class files
            if dependencies and other runtime conditions are suitable
```

This lesson distinguishes **source compatibility**, **API compatibility**, **bytecode compatibility**, and **ability to run the processor** to avoid the case of "compiles successfully on the developer's machine but fails to run on the deployment machine".

## 2. What Does `javac --release N` Do?

The option:

```bash
javac --release 17 Example.java
```

instructs the compiler to target a supported Java release, including these key parts:

| Aspect | Effect of `--release 17` |
| --- | --- |
| **Syntax and language features** | Allows only Java features appropriate for release 17, without automatically enabling syntax from newer releases |
| **JDK platform APIs** | Restricts compilation to the Java SE/Java Platform APIs present in the target release as provided by `javac` |
| **Class file format** | Generates class files with the version level corresponding to Java 17, namely **major version 61** |

If the program uses a platform API that first appeared in Java 21, compiling with a newer JDK using `--release 17` is not allowed to treat that API as available in Java 17.

Similarly, if using language syntax introduced only in a release newer than 17, `--release 17` must reject it even though the host JDK can understand that syntax.

**Do not confuse with separate `-source` and `-target`:** `-source 17` controls syntax and `-target 17` controls the class file level, but using only those two options on a newer JDK does not automatically provide the properly scoped platform API guardrail like `--release 17`. Therefore, when building an artifact to run on a specific Java version, `--release` should generally be used.

Also keep in mind:

- `--release N` is only valid when **the running `javac` supports N**; an older JDK cannot compile for a future release that it does not know about.
- `--release 17` **does not bring along** Java 17-compatible third-party libraries. Dependencies may require higher bytecode, use unavailable APIs, or have different runtime contracts.
- `--release 17` **does not force the application's runtime JVM to be Java 17**, but rather creates an artifact targeting that level. Newer JDKs can usually run Java 17 bytecode, yet libraries, modules, configuration, and application behavior still need to be tested.
- The `--release` option does not automatically download/install JDK 17 on the machine.

### When Does `--release` Differ from "Compiling with JDK 17"?

Compiling on JDK 17 with the appropriate configuration and compiling on JDK 21 with `--release 17` can both produce Java 17-level class files. However, the **host JDK, compiler implementation, detailed errors/warnings, plugins, annotation processors, and build dependencies** may differ.

`--release` is an explicit way to target the API and class-file level of the target release. It **does not replace** testing the artifact on an actual runtime JDK within the support matrix.

## 3. What Is `SourceVersion` Used For?

`SourceVersion` is an enum in:

```java
import javax.lang.model.SourceVersion;
```

The constants `SourceVersion.RELEASE_8`, `RELEASE_11`, `RELEASE_17`, etc. represent the Java language versions modeled by the API in the corresponding JDK. When a new JDK is released, the enum may gain additional constants for the new release.

An annotation processor typically declares:

```java
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;

@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ExampleProcessor
        extends javax.annotation.processing.AbstractProcessor {
    // ...
}
```

The snippet above **only illustrates the configuration annotation**, does not have a complete processor body, and is not a standalone runnable example.

What it does:

- Announces **the latest source version that the processor claims to support**.
- The compiler/processing tool can compare it against the version being used and emit a **warning** if the processor declares a level lower than the requested source version.
- Gives the processor author a technical commitment: the processor should be capable of understanding valid `Element`, `ElementKind`, `TypeMirror`, or source constructs within the scope it declares.

**It does not:**

- set `javac` to `--release 17` mode;
- generate Java 17 bytecode;
- verify that runtime dependencies are compatible with Java 17;
- prevent the compiler from producing its own warnings or errors;
- guarantee that the processor works properly with all new syntax merely by changing the constant number.

### A Very Important Comparison

| Configuration | Who reads it? | The actual question |
| --- | --- | --- |
| `javac --release 17` | Compiler | "Which Java version must the code being compiled conform to in terms of source/platform API/class file?" |
| `@SupportedSourceVersion(RELEASE_17)` | Annotation processing infrastructure | "Up to which version does the processor declare support for the source model?" |
| `javac -version` | Build/CI configurator | "Which JDK does the compiler actually being run belong to?" |
| `java -version` | Deployer/CI | "Which `java` runtime is running in this environment?" |
| `javap -verbose SomeClass` | Bytecode inspection tool | "What class-file version does the actual artifact have?" |

A processor with `RELEASE_17` can **run on a JDK 21 host**. If the application is compiled with `--release 21`, that processor may trigger a warning for declaring a source version lower than the requested level; the declaration does not automatically downgrade the application code to Java 17.

## 4. The Host JDK Determines the Ability to *Run* the Processor

An annotation processor is **Java code that is actually loaded and executed during compilation**. It is distinct from the application code being analyzed by the compiler.

Suppose:

- The processor is compiled with **Java 21 class files (major 65)**.
- CI is running `javac` with **JDK 17**, whose JVM only understands class files up to Java 17 (major 61).

In that configuration, the processor **cannot be loaded normally by JVM 17**. You may encounter an error such as `UnsupportedClassVersionError` even when the application is being compiled with `--release 17`.

Conversely, if a processor is compiled into Java 17 bytecode and does not require higher APIs/dependencies, a JDK 21 host can normally run it when compiling an application for Java 17. The crucial condition is that **the processor + its dependencies must be compatible with the actual host JVM**.

Therefore, it is necessary to distinguish between two artifacts:

```text
processor.jar
   ├── bytecode of the processor and dependencies
   └── runs in javac's host JVM

application.jar
   ├── application bytecode generated by javac
   └── runs on the deployed target Java runtime

A build command can configure the target release of these two
artifacts DIFFERENTLY.
```

**`--release` specified on the application compile command does not automatically recompile the processor to run on an older host.** If the processor already exists on `processorpath`, the JVM must be able to load the processor's bytecode before the processor processes the application source code.

### Which Java Version Is the Processor Compiled With?

When publishing a processor yourself as a library, decide the **minimum host JDK** that the tool needs to support. If you want the processor to run on JDK 17+, you can compile the processor itself with `--release 17` on a compiler that supports that release, verify its dependencies, and then test it on an actual JDK 17.

If the application targets Java 8 but the build team runs the processor on JDK 17, you can compile the application with `--release 8` and use a processor that runs on host 17. However, the **APIs understood by the processor** and `@SupportedSourceVersion` must still suit the code being processed; one should not infer that the processor must have Java 8 bytecode just because the application's output is Java 8.

## 5. Relationship Between Java Modules, Classpath, and Processor Path

When using `javac`, there are two path roles to distinguish:

- **Application classpath/module path:** needed by the compiler to locate code/libraries referenced by the application source.
- **Processor path/processor module path:** used by the annotation processing infrastructure to **locate and load processor code**.

In the Java 17+ example below, the processor is compiled separately into the `processor-classes` directory and then provided to the application compilation step via:

```bash
-processorpath processor-classes -processor lesson.CheckApiProcessor
```

`-processorpath` specifies the path containing the processor; `-processor` explicitly selects the processor class to run. So that the compiler also sees **the `CheckApi` annotation type** used by the application source, the example additionally places `processor-classes` on **`-cp`** when compiling the application.

This is the separation between **code executed at build time** and **code referenced by the application**. Another build system may package the annotation API and the processor into two separate JARs; in that case, the annotation API goes on the compile classpath, and the processor implementation goes on the processor path.

### Do Not Rely Solely on Processor Auto-Discovery

A processor can be registered using an appropriate service file, or specified explicitly via `-processor`. This guide uses `-processor` to **avoid depending on the auto-discovery mechanism** and prevent discrepancies across JDK/build tool versions.

Starting with certain newer JDK versions, the default configuration for automatic processor activation may change. Whether using Maven, Gradle, or invoking `javac` directly, **explicitly declare the required processor and dependencies** for a stable build, instead of expecting every compiler to always automatically run processors present on the classpath.

## 6. Complete Java 17+ Example: Two-Stage Processor and Application Compilation

We use **JDK 17 or newer that supports `--release 17`**. The example has a processor running at build time and an application running at runtime. The processor declares support for `SourceVersion.RELEASE_17`, while both compile commands explicitly use `--release 17`.

Structure:

```text
project/
└── src/
    └── lesson/
        ├── CheckApiProcessor.java
        └── Demo.java
```

### File 1: `src/lesson/CheckApiProcessor.java`

```java
package lesson;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface CheckApi {}

@SupportedAnnotationTypes("lesson.CheckApi")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class CheckApiProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(CheckApi.class)) {

            if (element.getKind() == ElementKind.CLASS) {
                TypeElement type = (TypeElement) element;
                System.out.println("PROCESSOR: "
                        + type.getQualifiedName());
            }
        }

        return true;
    }
}
```

**Role of each component:**

- `CheckApi` is an internal annotation for the example, used only at compile time due to `SOURCE` retention.
- `@SupportedAnnotationTypes("lesson.CheckApi")` registers the annotation type that the processor handles.
- `@SupportedSourceVersion(RELEASE_17)` declares the source version scope supported by the processor; it **does not replace** `--release`.
- `roundEnv.getElementsAnnotatedWith(CheckApi.class)` retrieves the elements directly carrying the annotation.
- `ElementKind.CLASS` selects classes, while `TypeElement.getQualifiedName()` prints the qualified name.
- `roundEnv.processingOver()` avoids printing again during the final processing round.
- `return true` indicates that the processor has handled/claimed the supported annotation in the corresponding round.

### File 2: `src/lesson/Demo.java`

```java
package lesson;

@CheckApi
public class Demo {
    public static void main(String[] args) {
        System.out.println("APPLICATION: running");
    }
}
```

### Compile and Run Commands

Inside the `project` directory, create two output directories and then run the commands. The commands below use **Bash** on Linux/macOS or a compatible shell:

```bash
mkdir -p processor-classes app-classes
javac --release 17 -encoding UTF-8 -d processor-classes src/lesson/CheckApiProcessor.java
javac --release 17 -encoding UTF-8 -cp processor-classes -processorpath processor-classes -processor lesson.CheckApiProcessor -d app-classes src/lesson/Demo.java
java -cp app-classes lesson.Demo
```

If using PowerShell on Windows, you can replace the `mkdir -p` line with:

```powershell
New-Item -ItemType Directory -Force processor-classes, app-classes
```

The remaining `javac`/`java` commands are essentially the same.

**Stdout of the second application compilation step:**

```text
PROCESSOR: lesson.Demo
```

**Stdout of the final program execution step:**

```text
APPLICATION: running
```

The first processor compilation step does not print any additional messages if successful. The application compilation step invokes `-processor lesson.CheckApiProcessor`, so the processor is explicitly activated and emits the line `PROCESSOR: ...`. The final program runs `Demo.main` and prints `APPLICATION: running`.

**Key takeaway:** the annotation processor **ran during compilation**, not when `Demo.main` executed. The `Demo.class` file is compiled at the Java 17 level, while `@CheckApi` has `SOURCE` retention so that usage of the marker is not retained as a runtime annotation.

## 7. Verifying the Result: Compiler, Runtime, and Bytecode

First, verify the actual tool versions:

```bash
javac -version
java -version
```

These are environment inspection commands; **there is no single fixed stdout** that applies to every machine. For example, the version may be 17 or 21, and having both `java` and `javac` on `PATH` may need to be checked if multiple JDKs are installed on the machine.

After successfully compiling the example, inspect the class file level:

```bash
javap -verbose -classpath app-classes lesson.Demo
javap -verbose -classpath processor-classes lesson.CheckApiProcessor
```

In the class file information section, the application class compiled with `--release 17` will have **major version: 61**. Here we **also intentionally** used `--release 17` when compiling the processor, so `CheckApiProcessor.class` also has major version 61.

However, this is the result of **two independent compilation commands**. If you replace the processor compilation step with another command targeting Java 21, the processor's class file may have major version 65 without changing the fact that the `Demo` application is still compiled with `--release 17`.

### Quick Verification Table

| Observation | Meaning |
| --- | --- |
| `javac -version` shows 21 | Running the JDK 21 compiler |
| Application command includes `--release 17` | Requests output compatible with Java 17 source/API/bytecode |
| `@SupportedSourceVersion(RELEASE_17)` | Processor declares support for Java 17 source level |
| `javap` on `Demo.class` shows major `61` | Application class file targets Java 17 |
| `javap` on the processor shows major `61` | Processor is built for a JVM supporting class file 61 |
| `java -cp app-classes lesson.Demo` runs on Java 17 | A practical check in that environment, not a guarantee that every other environment behaves identically |

When suspecting a mismatch, check the **actual version of every tool**, rather than just reading a `sourceCompatibility` setting in a build script.

## 8. Valid Configurations and Common Errors

| Host JDK | Application Compile | Processor | Assessment |
| --- | --- | --- | --- |
| 17 | `--release 17` | Built for Java 17 bytecode; declares `RELEASE_17` | Valid if dependencies are also compatible |
| 21 | `--release 17` | Built for Java 17 bytecode; declares `RELEASE_17` | Valid; processor runs on host 21; application targets Java 17 |
| 17 | `--release 21` | Any | Not feasible with JDK 17 `javac` because it does not know target release 21 |
| 17 | `--release 17` | Processor built for Java 21 bytecode | Cannot load the processor on JVM 17; may encounter `UnsupportedClassVersionError` |
| 21 | `--release 21` | Processor only declares `RELEASE_17` | Compiler may warn that supported source version is less than requested source 21; does not automatically downgrade the application |
| 21 | `--release 17` | Processor uses Java 21-only APIs and is compiled for 21 | Can run on host 21, but is not a processor compatible with host JDK 17 |

The table is a **conceptual matrix**: the final outcome also depends on dependencies, modules, plugins, and the exact JDK/compiler version used.

### Why Does the Compiler Warn About Supported Source Version?

When a processor supports source up to `RELEASE_17` but the application compile command requests a newer source level, `javac` may emit a warning like "Supported source version ... less than -source ...".

This is a signal that **the processor has not declared that it understands the new models/syntax**. It does not necessarily mean the annotation processor will be rejected completely; however, the project team needs to test the processor with new syntax/elements before updating `SourceVersion`.

Do not handle the warning by simply "bumping the constant `RELEASE_17` to `RELEASE_21`" in the source and skipping all tests. The processor may have `switch` logic on `ElementKind`, type-kind restrictions, or AST algorithms relying on older syntax. Updating the supported scope must be based on **actual testing**.

### When to Use `SourceVersion.latestSupported()`?

Some processors override:

```java
@Override
public javax.lang.model.SourceVersion getSupportedSourceVersion() {
    return javax.lang.model.SourceVersion.latestSupported();
}
```

This is an **illustrative snippet**, not a complete processor class. The method returns the latest source version supported by the runtime environment according to the API. It is convenient for processors that genuinely keep up with JDK evolution, but it **does not prove** that the processor logic is already compatible with all new constructs.

Compared to `@SupportedSourceVersion(RELEASE_17)`, this approach reports a support level dependent on the running environment. If you only test/guarantee Java 17, declaring `RELEASE_17` can be more honest and easier to maintain; if the processor has a strategy for supporting new versions, `latestSupported()` can be used after designing appropriate tests.

`SourceVersion.latest()` and `latestSupported()` do not necessarily play the same role: the latest version declared by the enum and the latest version supported by the current environment may differ in certain cases. Do not treat either one as a replacement for the `--release` setting.

## 9. Relationship with Maven, Gradle, and JDK Toolchains

In real projects, `javac` may be invoked indirectly via Maven, Gradle, an IDE, or CI. Even though build tools use their own configuration syntax, it is still important to clearly identify:

1. **The JDK used to run the build/compiler.**
2. **The `release` level of the application code.**
3. **The source/target and bytecode of the processor artifact**, if you develop a processor.
4. **The processor path** and the processor's dependencies.
5. **The source level declared by the processor**, such as `RELEASE_17`.
6. **The deployment runtime JDK** and the actual versions of libraries.

For example, using a Java toolchain can help select a specific JDK compiler. However, **toolchain** and **release target** address two different questions: choosing the compiler/JDK to run the build, and choosing the API/bytecode level for the generated code. Do not treat `JAVA_HOME`, `--release`, and `@SupportedSourceVersion` as three ways of writing the same setting.

If the project has a **separate module for the processor**, build and test that module as a tool that runs at build time. If the application targets Java 11 while the build system fixes the host JDK at 21, the processor can run on JDK 21 and declare source support appropriate for Java 11 while the application code is compiled with `--release 11`.

### Build Output Is Not Only Bytecode

An annotation processor can generate additional source/resources via `Filer`. When generating source for an application targeting Java 17, **the generated source content** must also use Java 17-appropriate syntax/APIs; otherwise, subsequent compilation rounds may fail regardless of whichever constant is written in `@SupportedSourceVersion`.

Similarly, if a processor writes out class files or invokes an independent auxiliary tool, you must check the target version of the generated artifact. You cannot assume that every file generated by a custom tool is automatically adjusted by `--release` if it does not go through the corresponding compilation step.

## 10. Common Misconceptions

**Mistake 1 — "`@SupportedSourceVersion(RELEASE_17)` makes class files run on Java 17."** False. That attribute specifies the source version the processor supports; the class file level is determined by the compiler target.

**Mistake 2 — "Using JDK 21 guarantees the code will not run on Java 17."** False. JDK 21 can compile an application with `--release 17`, provided the code and dependencies are compatible.

**Mistake 3 — "`-source 17 -target 17` is always equivalent to `--release 17`."** False with respect to platform API control when using a newer compiler; `--release` also restricts APIs to the target release.

**Mistake 4 — "The processor runs in a Java 17 JVM even though `javac` is running on JDK 21."** Not by default. The processor typically executes in the compiler/host environment, not the target runtime JVM.

**Mistake 5 — "If the application targets Java 8, the processor must also be built for Java 8."** Not necessarily. The processor runs on the host JDK used at compile time; the application's target is independent of the processor's bytecode, though host compatibility must be verified.

**Mistake 6 — "Bumping `SourceVersion` is enough to understand record, sealed, or new syntax."** No. You need to evaluate the new model, validation/generation logic, and testing.

**Mistake 7 — "`--release 17` automatically fixes dependencies compiled with Java 21."** No. External libraries have their own requirements; you must choose compatible dependency versions and test at runtime.

**Mistake 8 — "Only `RUNTIME` annotation retention can trigger a processor."** No. Annotation processors operate at build time; `SOURCE` retention can be sufficient, as long as the processor is configured to run.

**Mistake 9 — "Having the processor JAR on the classpath means it will always run automatically on every JDK."** Unsafe. Default auto-discovery mechanisms vary by configuration and version; you should explicitly declare the processor path/processor.

**Mistake 10 — "A successful build proves that a Java 17 runtime can run everything."** No. The build verifies source/bytecode within the compiler's scope, whereas runtime still depends on the actual JDK, libraries, and deployment environment.

## 11. Self-Check Exercises

**Exercise 1.** A project uses JDK 21 `javac`, sets `--release 17`, and the processor declares `RELEASE_17`. Which part determines that the application's class files have major version 61?

**Answer:** `--release 17` on **the application compile command**, not `SourceVersion.RELEASE_17` on the processor.

**Exercise 2.** In that same project, which JVM runs the processor code?

**Answer:** The JVM environment of the corresponding compiler/host JDK process; it does not automatically switch to Java 17 just because of `--release 17`.

**Exercise 3.** Why might a processor compiled with Java 21 fail to run when using JDK 17 `javac`?

**Answer:** The processor bytecode may be major 65, exceeding what JVM 17 supports; the JVM reports a class version error such as `UnsupportedClassVersionError`.

**Exercise 4.** A processor has `@SupportedSourceVersion(RELEASE_17)`, while the application is built with `--release 21` on JDK 21. What is noteworthy?

**Answer:** The compiler may warn that the processor only declares support up to release 17; it is necessary to verify that the processor understands the new source features, and it does not automatically downgrade the application.

**Exercise 5.** Do `Package.getName()` or `SourceVersion` help restrict Java 17 platform APIs when using JDK 21?

**Answer:** No. Controlling platform APIs according to the target release is the responsibility of `javac --release 17`.

**Exercise 6.** Why does the example have to compile `CheckApiProcessor.java` before `Demo.java`?

**Answer:** The processor must become a class that can be loaded and used by the compiler in the subsequent annotation processing step; the application source file also needs to see the `CheckApi` definition.

**Exercise 7.** If you run `javap -verbose` on `Demo.class` and see major version 61, what does that prove?

**Answer:** The class file was generated with the Java 17 bytecode level. By itself, it does not prove that all dependencies/modules and runtime behavior are compatible.

**Exercise 8.** Is changing `@Retention(SOURCE)` to `RUNTIME` on `CheckApi` a requirement for `CheckApiProcessor` to detect `Demo` at compile time?

**Answer:** No. The processor observes annotations at compile time; `SOURCE` retention is already sufficient in the example.

**Exercise 9.** Why can `SourceVersion.latestSupported()` be used while still requiring the processor to be tested on a new JDK?

**Answer:** The API returns a version level supported by the environment, but it does not guarantee that the processor's analysis/generation logic already understands all new language constructs.

**Exercise 10.** A build tool provides a JDK 21 toolchain and target `release = 17`. Are those two settings synonymous?

**Answer:** No. The toolchain selects **the JDK/compiler used for the build**; release selects **the source/platform API/class file level** of the application.

## 12. Summary

To build a maintainable annotation processor and Java application over the long term, explicitly specify **three compatibility contracts**: **the host JDK running the compiler/processor**, **`--release` for the application code or artifact to be published**, and **the `SourceVersion` that the processor declares it supports**. Also check bytecode/dependency versions, the deployment Java runtime environment, and any Java source generated by the processor.

Do not use `@SupportedSourceVersion` as a substitute for `--release`, nor use `--release` to infer that the processor was built for the exact runtime JVM of the application. When these three responsibilities are separated, diagnosing build errors and upgrading JDKs becomes clearer, more testable, and less surprising.
