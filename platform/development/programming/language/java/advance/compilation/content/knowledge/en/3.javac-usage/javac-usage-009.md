# Distinguishing javac from java's Direct Source-File Execution Mode

Java has two common ways to run a program written in a **.java** file:

1. **Compile beforehand with javac**, producing **.class** files, then run the compiled class with **java**.
2. **Run the source file directly with java**, commonly called **source-file mode** or **source-code launcher**: the **java** command compiles the source itself on launch and then executes the program.

Both ways execute Java code via the JVM. The difference lies in **compilation workflow, where compilation artifacts are stored, dependency management, reusability, and level of build control**. Direct source execution mode was introduced in **Java 11** (JEP 330); the basic examples below are compatible with **Java 17+**. Expanded capabilities in newer Java versions are distinguished in section 8.

## 1. Understanding the Roles of Both Commands

**javac** is the Java compiler. It reads source code, checks syntax/types, and compiles into bytecode stored in **.class** files. If compilation succeeds, class files can be run repeatedly without recompiling when the source does not change.

**java** is the program launcher. When given a **class name**, it locates and loads compiled classes for the JVM to execute. When given a **.java file path** in source-file mode, the launcher itself actively invokes an in-memory compilation mechanism before running. Therefore **java Hello.java** still has a compilation step, just integrated into a single command.

Side by side:

~~~text
Pre-compiled:
Hello.java --[javac -d out]--> out/Hello.class --[java -cp out Hello]--> JVM --> Result

Running source file:
Hello.java --[java Hello.java]--> compile for this run (in memory)
                                  --> JVM --> Result
~~~

In particular, **java Hello** and **java Hello.java** have different meanings:

- **java Hello**: launches the class named **Hello** already compiled and found on the classpath (or corresponding module configuration).
- **java Hello.java**: reads **source file Hello.java**, compiles it to run, and then launches that source's entry-point class.

**java** can launch a class name, JAR, named module, or source file; only the **java File.java** form in source-file mode is discussed in this lesson.

## 2. Runnable Example on Java 17+: Same Source, Two Paths

Create **Hello.java** in a new directory:

~~~java
public class Hello {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Xin chào, " + name + "!");
    }
}
~~~

### Approach A — Using javac Then java

From the directory containing **Hello.java**, run:

~~~bash
javac -d out Hello.java
java -cp out Hello Mai
~~~

Standard output:

~~~text
Xin chào, Mai!
~~~

After **javac -d out Hello.java**, the machine additionally has file **out/Hello.class** (directory separator depends on the OS). The **-d out** option specifies the directory receiving class files; **-cp out** tells the launcher where to find compiled classes. **Hello** in the second command is the class name, not the source file name. **Mai** is a program argument, going into **args[0]**.

You can run again:

~~~bash
java -cp out Hello An
~~~

Output:

~~~text
Xin chào, An!
~~~

The subsequent run **does not automatically re-invoke javac**. It continues using the class already present in **out**. If you edit **Hello.java** without recompiling, **java -cp out Hello** still executes the old bytecode.

### Approach B — Using java to Run Source Directly

Still from the directory containing **Hello.java**, run:

~~~bash
java Hello.java Mai
~~~

Standard output:

~~~text
Xin chào, Mai!
~~~

This command handles the compilation needed for the run itself and then launches the program. In standard source-file mode, the launcher **does not write a Hello.class file in the source directory** for reuse like running javac does. If the new directory had no class files yet, after **java Hello.java** no **Hello.class** written by that command will appear.

Run again:

~~~bash
java Hello.java An
~~~

Output:

~~~text
Xin chào, An!
~~~

Every launch in source-file mode has the launcher repeat the required compilation process; do not treat this as a build mechanism with reusable artifacts. If source code is edited between two runs, the next run uses the edited source contents, provided the code is valid.

**Learning point:** stdout and program behavior can be identical; what differs is **the workflow for creating and consuming bytecode**.

## 3. Practical Comparison Table

| Criterion | javac then java class name | java running source file |
| --- | --- | --- |
| Typical command | javac -d out Hello.java; java -cp out Hello | java Hello.java |
| Input to start | Source file for javac; class name for java | Source file path for launcher |
| Compilation | Explicit, performed by javac | Implicit when launcher prepares to run |
| Output .class files | Yes, written to disk per configuration | Running classes compiled in memory; does not emit reusable .class files |
| Subsequent runs | Uses existing classes until recompiled | Compiles for each launch |
| Output control | Has **-d**, controls class directory | Not an artifact-emitting tool via **-d** |
| Error checking | Can verify compilation without running | Compile and run are in one invocation; invalid code does not run |
| Annotation processing | javac supports processor configuration | Source-file mode disables annotation processing per launcher docs |
| Multiple source files | Supports explicit listing, source path, module source path, and build tools | Java 17/21 mainly targets one launched source file; newer versions expand scope |
| Packaging and deployment | Suitable for JAR/modules, build pipelines, and CI | Suitable for small examples, scripts, experiments, and learning |
| Target bytecode control | Supports **--release**, **--target**, and compiler options | **--source** lets launcher pick language/API level; does not replace all javac options |
| External dependencies | Specified at compile time and at runtime | Can supply classpath/module path accordingly; must understand source-file discovery limits per JDK |

Running a source file directly **does not mean skipping the compiler**, **does not mean executing Java code like a statement-by-statement interpreter**, and **does not guarantee faster execution**. It prioritizes the brevity of a single command invocation; compilation cost still occurs.

## 4. Command Rules and How Arguments Are Passed

### 4.1. Placing JVM/Launcher Options Before the Source File Name

Example:

~~~bash
java -Xmx128m Hello.java Mai
~~~

**-Xmx128m** before **Hello.java** is a JVM option; **Mai** after the file name is a program argument. If written as:

~~~bash
java Hello.java -Xmx128m
~~~

then the string **-Xmx128m** is passed into **args[0]** of the application, not interpreted as the JVM heap limit.

Similarly, when running a compiled class:

~~~bash
java -cp out Hello Mai
~~~

**-cp out** is a launcher option; **Hello** is the class name; **Mai** is the argument.

### 4.2. How Is Source-File Mode Triggered?

On a supporting JDK, when the first application argument points to **an existing file with the .java extension**, the launcher selects source-file mode:

~~~bash
java Hello.java
~~~

You can use **--source** to select the language/API level for source compilation, e.g.:

~~~bash
java --source 17 Hello.java Mai
~~~

On a JDK supporting source version 17, this command runs the source at the compatibility level defined by **--source 17**; when using the source launcher, this option also affects available platform APIs. Do not treat **java --source 17** as a mechanism for creating class files compatible with Java 17 environments: to create artifacts for deployment, use **javac --release 17**.

For source files lacking a **.java** extension, **--source** is also the signal for the launcher to recognize source-file mode. When learning fundamentals, prefer **.java** because it is clearer and more portable.

### 4.3. Distinguishing Easily Confused Commands

| Command | True meaning |
| --- | --- |
| **javac Hello.java** | Compiles, by default writes Hello.class next to source if -d is omitted |
| **javac -d out Hello.java** | Compiles and writes class into out |
| **java Hello** | Runs class Hello already on the appropriate classpath |
| **java -cp out Hello** | Runs class Hello inside out |
| **java Hello.java** | Compiles source to run immediately |
| **java --source 17 Hello.java** | Runs source mode with the corresponding source language/API level |
| **java -jar app.jar** | Runs a JAR-packaged program with an appropriate entry point |
| **java -m my.module/pkg.Main** | Runs the main class belonging to a resolved named module |

**Do not replace the class name with a .class file name** in the class-launching command: use **java Hello**, not **java Hello.class**.

## 5. Differences in Files, Classpath, and Reuse

### 5.1. javac Emits Bytecode Explicitly

With a source file belonging to a package:

~~~java
// src/demo/Greeter.java
package demo;

public final class Greeter {
    public static String message(String name) {
        return "Hello, " + name;
    }
}
~~~

The command:

~~~bash
javac -d out src/demo/Greeter.java
~~~

creates **out/demo/Greeter.class**. Java stores class files according to the package tree when an output directory is specified. Using **-d out** separates sources from build outputs. This compile command has not run the program yet, and **Greeter** does not need **main** to be a valid library class.

When multiple classes need to use each other, javac can compile a group of sources and locate dependent code via source/classpath configuration. Build tools like Maven or Gradle additionally manage incremental builds, tests, resources, dependencies, and packaging.

### 5.2. Source-File Mode Needs Classpath When Using Already-Compiled Classes

Create two more files with structure:

~~~text
work/
├── Main.java
└── src/
    └── demo/
        └── Greeter.java
~~~

Contents of **src/demo/Greeter.java** as in section 5.1. Contents of **Main.java**:

~~~java
import demo.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message("Mai"));
    }
}
~~~

Compile the library class first:

~~~bash
javac -d out src/demo/Greeter.java
~~~

Then either approach can be chosen:

~~~bash
# Option A: compile the whole program then run the class
javac -cp out -d out Main.java
java -cp out Main
~~~

~~~bash
# Option B: run only Main.java in source-file mode
java -cp out Main.java
~~~

Both approaches produce stdout:

~~~text
Hello, Mai
~~~

The example proves source-file mode is **not barred from using libraries**: dependent class **demo.Greeter** is already on classpath **out**; the source launcher compiles **Main.java** to run and loads **Greeter.class**. On Windows, a classpath with multiple entries is normally separated by **;**; on Linux/macOS it is **:**. The command above has only one entry, so it works across operating systems.

**Important limitation of Java 17/21:** source-file mode does not automatically scan and compile all **.java** files in a project. If you skip compiling **Greeter.java** and invoke **java Main.java**, you cannot by default expect the launcher to find source file **src/demo/Greeter.java** the way Gradle or javac configured with sourcepath does. Java 25 has major expansions for finding dependent sources; see section 8.

### 5.3. When Reuse Is Needed for CI/CD and Distribution

For a sufficiently large program, the standard workflow is usually:

~~~text
source code
   |
   v
javac or build tool --> class directory / JAR / modular artifact
   |
   +--> run tests, inspect bytecode, package
   |
   v
java -cp ... Main     or     java -jar app.jar     or     java -m ...
~~~

Source-file mode has no equivalent distribution-artifact creation step. Its purpose is shortening feedback loops for experiments, examples, and small utilities. For release builds, explicitly built and verified classes/JARs are required.

## 6. Checking Version Compatibility: --release and --source

Suppose a development machine has JDK 21 installed while the application must run on Java 17. Compile the artifact for the target version:

~~~bash
javac --release 17 -d out Hello.java
java -cp out Hello Mai
~~~

**javac**'s **--release 17** controls syntax, available standard Java APIs, and class-file format compatible with Java 17. This is the standard choice when building for an older JDK. Do not use only **-source 17** and assume the class file is compatible with Java 17, because **-source** alone does not guarantee that full goal.

The source-launcher command:

~~~bash
java --source 17 Hello.java Mai
~~~

differs in purpose: it **compiles and runs immediately on the active JVM**, without emitting a set of class files to carry over to JVM 17. If the current machine is JDK 21, execution still takes place on JDK 21. To test genuinely on Java 17, you must run with the actual Java 17 runtime (or matching CI image).

**Note:** A JDK only supports certain older source versions. Before using **--release N** or **--source N**, inspect the current JDK with **javac --help**, **java --help**, **javac -version**, and **java -version**.

## 7. Compilation Errors, Class Order, and Specific Limits of Source-File Mode

### 7.1. Compilation Errors Occur Before the Program Runs

If you change in **Hello.java**:

~~~java
System.out.println(unknownName);
~~~

without declaring variable **unknownName**, both **javac Hello.java** and **java Hello.java** detect a compilation error. With the javac workflow, the error appears in the compile step; with the source launcher, the error appears inside the launch command so main never executes. Exact messages and line numbers depend on the file/JDK; do not assume a fixed stderr string.

### 7.2. File Names and Top-Level Class Order in Java 17/21

With **javac**, the normal rule is that a **public top-level class** must reside in a file of the same name (**public class Hello** in **Hello.java**). With the Java 17/21 source launcher, e.g.:

~~~java
// StartHere.java
class Entry {
    public static void main(String[] args) {
        System.out.println("Entry chạy");
    }
}

class Helper {
    static int value() {
        return 42;
    }
}
~~~

runs via:

~~~bash
java StartHere.java
~~~

stdout:

~~~text
Entry chạy
~~~

In Java 17/21, the source-file launcher selects the **first top-level class** in the file as the class to run; that class must contain a valid **public static void main(String[] args)** method. Remaining top-level classes in the same file can be used as helpers. File name **StartHere.java** is not required to match top-level class name **Entry** in this example because **Entry is not public**. When moving to normal javac builds, still use standard file names and class layout to avoid confusion.

Order matters: swapping **Helper** ahead of **Entry** in Java 17/21 source will make the launcher look for main in the first class and fail to launch because Helper lacks main, even though Entry is further down. Do not rely on the launcher arbitrarily searching the whole file for a class with main.

### 7.3. Annotation Processors and javac Options

**javac** supports controlling compilation with options such as:

~~~bash
javac -d out -Xlint:all Hello.java
~~~

If annotation processors exist, javac can configure the processor path, processors, and annotation processing rounds. Conversely, source-file mode **disables annotation processing**; there is no mechanism to pass every javac option through the **java Hello.java** command. Projects depending on code generation or compile-time processing such as many Lombok/MapStruct setups should use an appropriate javac/Gradle/Maven build rather than expecting the source launcher to generate code.

**java Hello.java** also does not replace **javac -d out**, **javac -h ...**, or the JAR packaging step.

### 7.4. Packages, Modules, and Classpath

- The Java 17/21 source launcher compiles the source file in the **unnamed module**, even though classes in the source can declare a normal **package**. This differs from creating an explicit named module with **module-info.java** and compiling via module source path.
- **javac** can compile modules via **--module-source-path**, and modular applications can run with **java --module-path ... -m module/class**.
- Do not assume that merely running a .java file applies JPMS rules, exports, and requires for the entire project like a full modular build.
- You can use **-cp / --class-path** or module-path options supported by the launcher for appropriate dependencies, yet you must still distinguish **source code needing compilation** from **compiled classes/JARs**.

## 8. Differences Across JDK Versions

This lesson uses standard Java 17+ syntax; however, **the capabilities of the source launcher have evolved across JDK releases**. Therefore when learning “direct source-file execution”, always state the JDK in use.

| Version | Key points to remember |
| --- | --- |
| Java 8 and earlier | No source-file mode via **java File.java** as shown; use javac then java |
| Java 11 | JEP 330 introduces launching a single source file with java |
| Java 17/21 | Single-file source launcher model: compiles the specified source file, does not automatically compile all dependent source files in a source tree |
| Java 25+ | JEP 458 expands the source launcher: can locate and compile needed .java files in the same source tree; supports using module-info.java in the source tree per this version's rules |

The two-file example in section 5 is designed to run reliably on Java 17/21 by compiling **Greeter.class** first. On JDK 25+, the source launcher can compile dependent source code when the source tree is laid out appropriately; that **does not turn java File.java into a full build system**, does not emit reusable .class artifacts, and does not enable annotation processing. When writing documentation or CI, explicitly state the **minimum JDK version** instead of implicitly relying on features of the newest JDK release.

In addition, language changes in newer Java releases (such as shorter entry points or program syntax) are a separate topic from **the mechanism by which source is compiled and executed**. For a fair comparison on Java 17, the examples in this lesson use traditional **public static void main(String[] args)**.

## 9. When to Choose Which Approach?

**Use javac (usually via Gradle/Maven) when:**

- There are multiple packages, multiple modules, dependencies, resources, or generated code.
- You need to verify the compile step separately, run unit/integration tests, lint, or annotation processing.
- You must package an application/library into a stable artifact for CI/CD or deployment.
- You need to build for another Java version, use **--release**, or control compiler options.
- You want to reuse built class files across multiple runs without recompiling.

**Use java File.java when:**

- Learning Java and wanting to run self-contained examples with one command.
- Writing small scripts/utilities on machines with a compatible JDK installed.
- Needing quick experiments with source code before needing JAR/class outputs.
- Having pre-compiled dependencies and knowing how to pass the appropriate classpath.

There is no rule that “javac is faster in all circumstances”: the source launcher saves steps, while pre-building avoids repeated compilation across subsequent runs. Actual performance also depends on source size, dependencies, JVM warm-up, and measurement method. To evaluate program speed after startup, separate **compile/startup time** from **logic execution time**.

## 10. A Few Scenarios and How to Reason About Them

**Scenario A:** A learner changes a line in **Hello.java**, runs **java -cp out Hello**, and still sees the old output.

**Cause:** running the old **Hello.class**. You must re-run **javac -d out Hello.java** or use **java Hello.java** to test the new source contents.

**Scenario B:** **java Hello** reports main class not found, yet **java Hello.java** runs.

**Common cause:** class **Hello** has not been compiled yet or is not on the classpath searched by the launcher. The Java source launcher can compile from the source file without requiring an existing class.

**Scenario C:** **javac Main.java** fails due to a missing library, yet the learner thinks **java Main.java** will automatically download the dependency.

**Explanation:** both commands need access to the dependency. The source launcher does not automatically download every JAR from Maven Central and does not replace Gradle/Maven. You must supply the classpath/module path or use a build tool.

**Scenario D:** A project uses an annotation processor generating code at compile time.

**Handling:** use javac or a build tool configured with the annotation processor. Source-file mode does not run annotation processing.

**Scenario E:** Must ship a JAR that runs on Java 17, yet the developer machine uses JDK 21.

**Handling:** use a standard build with **javac --release 17** (or matching Gradle/Maven config), test on runtime 17, and package. **java --source 17 File.java** is not an artifact release step.

## 11. Short Practice Exercises

1. Create **Hello.java** from section 2. Run **java Hello.java A** and record stdout.
2. Run **javac -d out Hello.java** and then **java -cp out Hello B**; verify file **out/Hello.class** was created.
3. Change the printed text in the source, **without recompiling**, run **java -cp out Hello B** and then **java Hello.java B**; explain why the outputs differ.
4. Try **java -Xmx128m Hello.java A** and **java Hello.java -Xmx128m**; observe **args[0]**.
5. Create **Greeter.java** and **Main.java** as in section 5; compile the helper and compare the two ways of launching main.
6. If using JDK 25+, try organizing dependent source code per that version's source-tree rules and compare against Java 17/21 limits.

**Self-check questions:**

- Why does **java Hello.java** not produce a build artifact equivalent to **javac -d out Hello.java**?
- Does **java Hello.java** “skip compilation”?
- How does **-cp out** behave when running a class compared to when the source launcher needs to use a pre-compiled library?
- Why can **java -cp out Hello** run old code after editing **Hello.java**?
- When must **javac --release 17** be used, and why does **java --source 17** not replace it?
- Which limits of the Java 17/21 single-file source launcher were expanded in newer JDKs?

## 12. Official Documentation for Reference

- **Oracle Java 17 – The java Command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle Java 21 – The java Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **Oracle Java 21 – The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Oracle Java 25 – The java Command:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **OpenJDK JEP 330 – Launch Single-File Source-Code Programs:** https://openjdk.org/jeps/330
- **OpenJDK JEP 458 – Launch Multi-File Source-Code Programs:** https://openjdk.org/jeps/458

**Key takeaway:** **javac** creates class files for build control and reuse; **java File.java** compiles source itself on launch for convenient direct testing and running. Both ultimately run bytecode on the JVM, yet must be chosen based on **project scale, build requirements, dependencies, and JDK version**.