# Prerequisites and Hands-On Practice with a Small Project — Java Compilation

## 1. Lesson Objectives

After this lesson, you can explain how Java turns source code into a runnable program, use the JDK toolset to compile and run a multi-file project, recognize whether an error occurs at compile time or runtime, and inspect the bytecode output. The exercise requires no IDE, Maven, Gradle, or external libraries; thus every compiler step is clearly visible.

**Scope:** fundamentals of Java compilation with JDK 17 or later. Build tools and advanced optimization mechanisms are mentioned only where relevant.

## 2. The Big Picture: From .java to a Running Program

A typical Java program goes through these steps:

~~~text
App.java + ScoreUtils.java
        |
        v
javac: read source code, parse syntax, resolve names, check types,
       process annotations if any, generate bytecode
        |
        v
App.class + ScoreUtils.class
        |
        v
java: start JVM, load/link/initialize classes as needed
        |
        v
execute bytecode (interpreter and/or JIT-compiled machine code)
        |
        v
console output
~~~

- **Source code (.java)** is text written according to Java language syntax.
- **javac** is the JDK's Java compiler. It checks the program and usually emits one .class file per class, record, interface, or generated type. A single source file can also produce multiple .class files due to nested classes.
- **Bytecode (.class)** is an instruction and metadata format for the JVM, not Windows/Linux/macOS machine code. This format allows the same artifact to run across compatible JVMs.
- **JVM** performs class loading, bytecode verification, and linking as needed; at runtime the JVM may interpret or JIT-compile hot sections into machine code. JIT happens at runtime, distinct from the preceding javac step.
- **JDK** includes javac, java, javap, and development tools. Having only a Java runtime environment does not guarantee you have the javac command.

Core distinction: **javac can succeed while the program still fails at runtime**, for example due to a missing class on the classpath or using an incompatible set of .class files. Conversely, a type error in source code is usually caught by javac before the program runs.

### What javac Actually Checks

| Conceptual phase | Question to answer | Error example |
| --- | --- | --- |
| Token/syntax analysis | Are statements, braces, and declarations valid? | Missing ; or } |
| Name/symbol resolution | Do referenced classes, variables, and methods exist and remain accessible? | cannot find symbol |
| Type and constraint checking | Are parameter types, return types, generics, and access scopes compatible? | incompatible types |
| Annotation processing (if processors exist) | Is new source generated or are additional checks run? | Processor or generated code errors |
| Bytecode generation | Write class definitions, methods, and instructions into .class | Output is not created if compilation fails |

This is a learning model, not a guarantee that javac always executes sequentially in exactly five independent phases. Internal compiler details can vary by JDK version.

## 3. Prerequisite Knowledge Before Practicing

**Basic Java:** know how to declare classes, static methods, local variables, for-each loops, List, method calls, and int/double types. When reading code, track parameter types and return types because that is the contract javac checks.

**Files, directories, and packages:** with a package demo.compilation declaration, placing sources in src/demo/compilation is an easy-to-manage convention. The filename of a public top-level class must match the class name: public class App belongs in App.java. Package names are case-sensitive.

**Terminal:** know how to navigate to the project root directory, enter commands, and read exit codes and error messages. The javac command accepts source file paths; the java command accepts a **fully-qualified class name**, not a .class file path when running in standard classpath mode.

**Classpath:** a list of locations where the JVM or javac searches for classes and libraries. With output directory out, the classpath must point to **out**, i.e., the root directory of the package tree, rather than pointing directly to out/demo/compilation. Compile-time classpath and runtime classpath are two separate configurations and must be supplied properly to each command.

**Versions:** the JDK used to compile, target language/API level, and JVM version used to run can differ. For this example, use JDK 17+ and require only Java 17 features/APIs.

### Check the Environment

Run the following commands in the terminal:

~~~sh
java -version
javac -version
javap -version
~~~

Expectation: all three commands work and the JDK version is at least 17. The exact version string depends on your machine's distribution/updates, so matching a fixed string is unnecessary. If javac is not found, check that a JDK is installed and check PATH/JAVA_HOME settings. On machines with multiple JDKs, ensure java and javac point to the intended toolchain.

## 4. Mini Project: Summing and Averaging Scores

Create a project named **compilation-lab** with two classes. App orchestrates the program; ScoreUtils contains the summing logic. Separating classes makes compile-time dependencies between files and the role of the classpath visible.

~~~text
compilation-lab/
└── src/
    └── demo/
        └── compilation/
            ├── App.java
            └── ScoreUtils.java
~~~

The out directory will be created by javac when running commands with the -d option.

### File 1: src/demo/compilation/ScoreUtils.java

~~~java
package demo.compilation;

import java.util.List;

public final class ScoreUtils {
    private ScoreUtils() {
        // Utility class does not need instantiation.
    }

    public static int total(List<Integer> scores) {
        int sum = 0;
        for (int score : scores) {
            sum += score;
        }
        return sum;
    }
}
~~~

The contract of the total method is: accept List<Integer>, return int. The loop automatically unboxes each Integer to int. The example uses small values; if the sum could exceed int range, a real application needs an appropriate type and overflow-handling policy.

### File 2: src/demo/compilation/App.java

~~~java
package demo.compilation;

import java.util.List;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        List<Integer> scores = List.of(8, 9, 10);
        int total = ScoreUtils.total(scores);

        System.out.println("Count: " + scores.size());
        System.out.println("Total: " + total);
        System.out.println("Average: " + (total / (double) scores.size()));
    }
}
~~~

**Why does the code compile?** Java finds List in the standard library, along with ScoreUtils in package demo.compilation. The call ScoreUtils.total(scores) takes List<Integer> and returns int; the (double) cast turns division into floating-point division. The main method has the proper signature for the Java launcher to invoke.

**Assumption:** the list has at least one element so the average calculation is meaningful. This example uses a fixed list of three scores, so division by zero does not occur.

## 5. First Compilation and Running the Program

Open a terminal in the compilation-lab directory (the directory containing src).

With Bash on macOS/Linux, you can create the output directory via:

~~~sh
mkdir -p out
~~~

With PowerShell on Windows, the corresponding command is:

~~~powershell
New-Item -ItemType Directory -Path out -Force
~~~

Compile **both source files**; explicitly listing both files works in both Bash and PowerShell:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/compilation/ScoreUtils.java src/demo/compilation/App.java
~~~

On success, javac normally prints nothing to the terminal and produces:

~~~text
out/
└── demo/
    └── compilation/
        ├── App.class
        └── ScoreUtils.class
~~~

Run with the classpath pointing to the out directory and the fully-qualified class name:

~~~sh
java -cp out demo.compilation.App
~~~

**Expected output** of the exact two source files above:

~~~text
Count: 3
Total: 27
Average: 9.0
~~~

How to read the options:

| Command or option | Effect |
| --- | --- |
| javac | Compiles Java source code into .class bytecode |
| -encoding UTF-8 | Decodes source files using UTF-8, avoiding machine default encoding dependency |
| --release 17 | Compiles against Java 17 language level, bytecode, and public APIs |
| -d out | Places the root directory for emitted .class files in out, preserving package layout |
| java -cp out | Adds out to the application classpath at runtime |
| demo.compilation.App | Name of the class containing main, including package and class name |

The command java -cp out demo.compilation.App does **not** require App.java to still exist, because the JVM executes bytecode from .class files. However, if you edit .java without re-running javac, runtime output still comes from the old .class files.

## 6. Inspecting Generated Bytecode

Use javap, the tool for reading information from .class files:

~~~sh
javap -classpath out -p demo.compilation.ScoreUtils
javap -classpath out -c demo.compilation.App
javap -classpath out -verbose demo.compilation.App
~~~

In the first command, you will see a method declaration equivalent to public static int total(java.util.List<java.lang.Integer>). The -p option also displays private members. In the second command, you see bytecode instructions such as invokestatic, invokevirtual, getstatic, or invokedynamic (depending on JDK and expression form); this is **not** Java source syntax.

With the -verbose command, find the line **major version: 61**. When compiling with --release 17, major version 61 corresponds to Java 17's class-file format. This is one verification signal for target bytecode level; it does not by itself prove external libraries or the runtime environment are compatible.

Look for the call to ScoreUtils.total in the instruction list/constant pool: class App records a reference to a method in another class. Thus, runtime still requires a compatible version of ScoreUtils.class on the classpath.

## 7. Compiling Classes Separately: Compile-Time Classpath

When compiling classes one at a time, compilation of App needs to see the compiled ScoreUtils.

Start with ScoreUtils:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/compilation/ScoreUtils.java
~~~

Then compile App separately and supply the classpath:

~~~sh
javac -encoding UTF-8 --release 17 -cp out -d out src/demo/compilation/App.java
java -cp out demo.compilation.App
~~~

Output remains the same three Count/Total/Average lines as in section 5. The -cp out argument in the javac command lets the compiler look up ScoreUtils.class. In the java command, -cp out lets the JVM look up both App.class and ScoreUtils.class.

If App needs an external JAR, you must configure dependencies so the compiler sees the library API during compilation and the JVM finds a compatible version at runtime. Maven/Gradle manage many of those steps automatically, yet the essence remains compiling with dependencies and running with the appropriate runtime classpath/module path.

**Do not confuse them:** -d specifies **where to write** .class files; -cp specifies **where to find** existing classes. The two options do not replace each other.

## 8. Intentional Experiments: Seeing Clearly Which Stage Fails

Perform the following experiments **one by one**, starting from working code. Before each new experiment, restore both source files to section 4 if modified. Work in a project copy or under version control for easy rollback.

### Experiment A — Wrong Method Name: Compile-Time Error

In App.java, change just one line:

~~~java
int total = ScoreUtils.totals(scores);
~~~

Keep the method name in ScoreUtils as total, then recompile both sources with the command from section 5. javac will report an error like **cannot find symbol** for the totals call, because no method with that name exists. Diagnostic line/column details may vary by JDK.

**Fix:** change totals back to total, recompile, and run. This error is caught before main executes.

### Experiment B — Wrong Parameter Type: Compile-Time Error

Suppose App declares:

~~~java
List<String> scores = List.of("8", "9", "10");
int total = ScoreUtils.total(scores);
~~~

ScoreUtils.total requires List<Integer>. List<String> is incompatible with List<Integer> because Java generics are invariant in type arguments. javac catches the type mismatch at the call site, even though the strings look like digits. To fix, use Integer data or perform controlled conversion to an integer list before calling.

### Experiment C — Missing Classpath or Wrong Package Root

Suppose only App.java is being compiled individually while ScoreUtils.class resides in out. If -cp out is omitted and javac also cannot find ScoreUtils source via the source path, the compiler cannot resolve the dependent class.

Correct configuration:

~~~sh
javac -encoding UTF-8 --release 17 -cp out -d out src/demo/compilation/App.java
~~~

At runtime, if the classpath points to the wrong root, the JVM may report **ClassNotFoundException** in certain class-loading mechanisms or **NoClassDefFoundError** when a dependent class is not found during linking/execution. The Java launcher may also report **Could not find or load main class** if the main class itself is not found. These errors belong to runtime/class loading and are not the same as source syntax errors.

### Experiment D — Old .class and Changed Method Signature

This is an advanced yet very realistic demonstration of the difference between source checks and runtime linkage.

1. Return to the working baseline, compile both files, and run to confirm.
2. In ScoreUtils.java, change only the return type from **int** to **long** in the total method declaration; keep the method body returning sum (Java automatically converts int to long).
3. Recompile only ScoreUtils.java, **without recompiling App.java**:

~~~sh
javac -encoding UTF-8 --release 17 -cp out -d out src/demo/compilation/ScoreUtils.java
java -cp out demo.compilation.App
~~~

You will encounter a runtime error such as **NoSuchMethodError** for the total method with the old descriptor returning int. The old App.class still references the previously compiled signature. In bytecode, the return type is part of the method descriptor; the new binary signature does not match.

If App.java is recompiled with its old code, javac catches the issue at compile time instead: a long value cannot be automatically assigned to the int variable total. For a consistent fix, change App.java to:

~~~java
long total = ScoreUtils.total(scores);
~~~

Then recompile **both files** and run. The text output remains Count: 3, Total: 27, Average: 9.0. Lesson: changing a library API can break un-rebuilt binary clients even when both sides compiled independently without error.

## 9. How Does Java Compilation Differ from Java Execution?

| Criterion | Compile time | Runtime |
| --- | --- | --- |
| Typical tool | javac | java launcher + JVM |
| Primary inputs | .java and needed dependencies | .class/JAR and runtime dependencies |
| Output | .class or error diagnostics | Program execution or exceptions/errors |
| Common errors | Syntax, types, names, visibility | Missing classes/JARs, binary changes, data errors, exceptions |
| Class lookup config | javac's classpath/module path | JVM's classpath/module path |
| Optimization tech | Compiler analysis and bytecode emission | JVM interpreter/JIT, depending on runtime |

**JIT does not replace javac:** JIT operates on intermediate bytecode during execution (according to JVM mechanisms). Bytecode may be interpreted before or instead of being JIT-compiled.

**Not every .java file needs a manual javac step:** since Java 11, java has a single-file source-code execution mode (source-file mode). The launcher still performs the related compilation work behind the scenes. That mode is convenient for simple examples, but does not replace understanding multi-class project compilation and classpaths.

**Not every edit alone suffices for re-running:** ensure .class files are updated. Some IDEs/build tools do this automatically, making it easy for learners to overlook the underlying mechanism.

## 10. JDK Versions, --release, and Compatibility

Suppose you develop with JDK 21 yet want artifacts to run on Java 17. The practice command uses --release 17 to instruct javac to check against Java 17 public APIs and syntax while emitting the corresponding class-file version. If you accidentally call an API introduced only in a newer Java version, --release 17 helps the compiler reject it.

Distinguish these concepts:

- **JDK version running javac:** the actual compiler/toolchain version.
- **Target source/bytecode level:** the language level and emitted class-file format; --release combines the associated constraints.
- **Runtime version:** the JVM actually loading and executing .class files. A JVM older than the required class-file level may throw UnsupportedClassVersionError.
- **Dependency compatibility:** external libraries must also have compatible bytecode/APIs. Using --release for your own source does not automatically make a JAR compiled with a newer Java run on an older Java.

Using only -source and -target is not always enough to stop source code from referencing newer platform APIs when compiling with a newer JDK; targeting Java 17, --release 17 is usually the better option. Do not treat the path to JDK 17 and --release 17 as synonymous: one selects the tool, the other constrains the compilation target.

## 11. Common Errors and Rapid Isolation

| Symptom | Common cause | Check first |
| --- | --- | --- |
| javac: command not found / is not recognized | Missing JDK or wrong PATH | javac -version; JDK path |
| error: cannot find symbol | Typo, missing import/dependency, class not visible | Method/class name, package, compile classpath |
| incompatible types | Call, variable assignment, or generics type mismatch | Actual type vs. declared type in method signature |
| class ... is public, should be declared in a file named ... | Public top-level class does not match filename | Filename and class name |
| package ... does not exist | Missing JAR/class or wrong package | Compile-time classpath/module path |
| Could not find or load main class | Wrong fully-qualified class name or runtime classpath | java -cp out demo.compilation.App |
| NoClassDefFoundError | JVM missing dependent class during loading/linking | Runtime classpath and packaged artifacts |
| NoSuchMethodError | Caller and dependency are binary-incompatible | Synchronized rebuild, check JAR versions |
| UnsupportedClassVersionError | .class newer than running JVM | java -version and --release level |
| Running still shows old results after editing .java | .class not recompiled or running wrong artifact | Clean old output in practice project and rebuild |

Read **the first meaningful diagnostic line**, file location, and source line; fix the root cause before chasing cascading errors. For runtime failures, read the exception/error type, stack trace, and run configuration. Avoid tweaking the classpath randomly or mixing multiple versions of the same library.

### Watch Out for Stale Output

If compilation fails yet out still holds App.class from an earlier run, the java command may continue running the old version and create the illusion that broken code still “works”. In exercises, make sure the build succeeds from current sources before drawing conclusions. When testing a clean build, delete only the out folder of **the sample project** and re-run javac; never arbitrarily delete folders in real projects.

## 12. Self-Check Exercises

Practice step by step and predict the outcome before using the terminal:

1. Compile both sources and run the program. Note the three stdout lines matching section 5. Open out to confirm the paths of both .class files.
2. Use javap to read the total method and find the call to it from App. Explain why the JVM still needs ScoreUtils.class even though App.class was created.
3. Change the score list to List.of(6, 7, 8). Predict and verify the result: Count: 3, Total: 21, Average: 7.0. Observe the difference if you forget to recompile.
4. Rename totals to a non-existent method name. Read the javac error and fix it. Use an IDE only once you understand the corresponding terminal commands.
5. Compile each file individually per section 7, then explain the different roles of -cp and -d.
6. If using a JDK newer than 17, keep --release 17, try calling an API available only in a newer Java version, and observe the compiler rejecting it. No need to force a specific API if your machine's JDK is unsuitable.

**Completion criteria:** you can independently run the project from two .java files, know the corresponding .class and package locations, explain what the compiler checks, distinguish compile-time from runtime errors, use --release/-encoding/-d/-cp, and understand why synchronized rebuilding is needed after API changes.

## 13. Applying This Mindset to Real Projects

In large applications, Maven/Gradle typically manage locating sources, downloading dependencies, invoking the compiler, storing bytecode, running tests, and packaging JARs. When encountering a build failure, boil it down to foundational questions:

- **Which source is being compiled?** The right file/module/source set or a different copy?
- **Which JDK is chosen as compiler?** Does it match the required Java level and --release/sourceCompatibility?
- **Which dependencies are visible at compile time?** Missing classpath entry, import, or wrong version?
- **Which artifact is actually running?** Are the .class/JAR path and entry point accurate?
- **Which dependencies are visible at runtime?** Missing JAR or mismatch with compile-time API?
- **Is there stale bytecode?** Clean-rebuild the necessary scope to eliminate stale outputs.

Understanding the **source → javac → bytecode → JVM** cycle helps you read errors at the right layer, troubleshoot with evidence, and avoid relying blindly on a specific IDE or build tool.
