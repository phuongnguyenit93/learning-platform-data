# Compiling a Program with Packages from the Right Root Directory

## 1. Objective and Main Ideas

For a Java program with packages, you need to know **where the terminal is currently located**, **which root directory the source files reside under**, **what the package names are**, and **the root containing the .class files after compilation**. These four concepts are closely related yet distinct.

After this lesson, you can:

- Create a Java 17+ project with two packages and compile it with javac without an IDE or build tool.
- Run the right commands from the **project root** or the **source root** by adjusting relative paths.
- Accurately understand -d, -cp, -sourcepath, and fully qualified class names.
- Check the .class location yourself, run the program with java, use javap, and diagnose “file not found”, “cannot find symbol”, and “Could not find or load main class” errors.

**Core rule:** from the current working directory, pass the right paths to .java files to javac; write .class files under a designated output directory; run using a classpath **pointing to the bytecode tree root** and the **fully qualified class name including package**.

## 2. Distinguishing Four Types of “Roots”

Consider the project structure:

~~~text
package-lab/                     <-- Project root
├── src/                         <-- Source root
│   └── com/
│       └── example/
│           ├── app/
│           │   └── Main.java
│           └── text/
│               └── Greeter.java
└── out/                         <-- Bytecode output root
    └── com/
        └── example/
            ├── app/
            │   └── Main.class
            └── text/
                └── Greeter.class
~~~

1. **Current working directory (CWD)**: the terminal's current directory. Relative paths in commands are resolved from CWD. The main example uses CWD = package-lab.
2. **Source root**: the directory above the source package tree. Here it is src. The package name com.example.app corresponds to the relative path com/example/app underneath src.
3. **Package**: an identifier namespace in Java code, e.g., package com.example.app;. It is a namespace, not a terminal instruction to change directories.
4. **Output root / classpath root**: the directory **above** the package tree containing .class files. Here it is out. If Main.class is at out/com/example/app/Main.class, then the classpath must contain out, not out/com/example/app.

With the -d out option, javac places bytecode into the matching package tree under out. When running with a classpath, the JVM maps the name com.example.app.Main to the path com/example/app/Main.class relative to each classpath root.

**Source rule to remember:** the file containing the public top-level class Main must be named Main.java. Placing the file in the directory branch matching the package declaration is the standard convention and makes source-discovery tools work cleanly. However, there is no rule requiring the terminal to always be inside src or inside the package directory.

## 3. Preparing a Runnable Project

Use **JDK 17 or later**. Check both the compiler tool and the runtime launcher:

~~~sh
javac -version
java -version
~~~

Create the package-lab directory with two branches src/com/example/text and src/com/example/app. Place the following two exact files into the respective branches. Even if you use an IDE to create the files, still run the compilation command in the terminal to clearly observe paths and outputs.

### src/com/example/text/Greeter.java

~~~java
package com.example.text;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The Greeter class belongs to package com.example.text; its fully qualified name is com.example.text.Greeter. The public static greet method takes a name and returns a greeting. The constructor is private because the example does not need to instantiate a Greeter object.

### src/com/example/app/Main.java

~~~java
package com.example.app;

import com.example.text.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Lan"));
    }
}
~~~

The Main class belongs to a **different** package from Greeter. The import declaration allows using the short name Greeter instead of writing the fully qualified name at every call site. javac must see the Greeter class when compiling Main.

These are **two separate .java files**, each with its own package declaration and public class. Do not merge two public classes into the same file.

## 4. Compiling from the Project Root: The Easiest Approach to Verify

Suppose the terminal is in the parent directory of package-lab; switch into the project root:

~~~sh
cd package-lab
~~~

Check the current directory with pwd (Bash/macOS/Linux) or Get-Location (PowerShell). From here, the path src/com/example/app/Main.java must exist.

Create out before compiling. Choose the command appropriate for your operating system:

~~~bash
# Bash
mkdir -p out
~~~

~~~powershell
# PowerShell
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Run the command to compile **both source files** from CWD = package-lab:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/com/example/text/Greeter.java src/com/example/app/Main.java
~~~

When successful, javac normally prints no message. Check out, and you will see:

~~~text
out/
└── com/
    └── example/
        ├── app/
        │   └── Main.class
        └── text/
            └── Greeter.class
~~~

Run the application from **the same package-lab directory**:

~~~sh
java -cp out com.example.app.Main
~~~

**Exact stdout:**

~~~text
Hello, Lan!
~~~

Step-by-step explanation:

1. CWD is package-lab, so both paths starting with src/... are resolved relative to the project root.
2. javac reads both files; package declarations provide the full name of each class.
3. -d out requests generating classes under out, organizing subdirectories by package.
4. The JVM receives -cp out and looks up com/example/app/Main.class, as well as com/example/text/Greeter.class, from the out root.
5. com.example.app.Main specifies the exact class containing main, consisting of package and class name.

| Component | Meaning |
| --- | --- |
| javac | Java compiler program |
| -encoding UTF-8 | Decodes source files using UTF-8 |
| --release 17 | Compiles targeting Java 17 syntax, platform APIs, and bytecode |
| -d out | Where javac writes .class files and creates the package tree |
| src/com/example/.../Name.java | Path to the **source file**, resolved from CWD |
| java | Java/JVM application launcher |
| -cp out | Root for looking up compiled classes when running |
| com.example.app.Main | Fully qualified class name containing the main method |

**Note:** -d expects the output root directory to exist; the example already created out. javac creates package subdirectories as needed. Both source files are listed explicitly so the compile command does not depend on differing wildcard expansion syntax between Bash and PowerShell.

## 5. Why Not Set the Classpath to out/com/example/app?

The fully qualified name of the Main class is com.example.app.Main. With a classpath, the JVM translates that name into:

~~~text
Class name:      com.example.app.Main
Required branch: com/example/app/Main.class
Classpath:       out
Result:          out/com/example/app/Main.class
~~~

If you use -cp out/com/example/app, the JVM still looks for com/example/app/Main.class **underneath** that directory. This is a common cause of the main-class-not-found error.

The following commands are **incorrect for the bytecode tree of this clean example**:

~~~sh
java -cp out/com/example/app com.example.app.Main
java -cp out Main
java -cp src com.example.app.Main
~~~

The first command picks the wrong root; the second omits the package so it looks for class Main in the default package; the third points to the .java source tree, whereas .class files were generated in out.

Fix with the verified command:

~~~sh
java -cp out com.example.app.Main
~~~

If in another project an apparently wrong command still runs, the JVM may be picking up a stale artifact or a class of the same name from another location. Inspect the actual .class being loaded instead of concluding that a wrong classpath setup is guaranteed to work.

## 6. Compiling from the Source Root src Is Also Valid

“The right root directory” means **all paths are resolved consistently from CWD**, rather than there being one single directory from which javac is forced to run.

From CWD = package-lab, switch into src:

~~~sh
cd src
~~~

Now CWD is **package-lab/src**. If out does not yet exist, it can be created in the parent directory:

~~~bash
# Bash
mkdir -p ../out
~~~

~~~powershell
# PowerShell
New-Item -ItemType Directory -Path ../out -Force | Out-Null
~~~

Compile from src:

~~~sh
javac -encoding UTF-8 --release 17 -d ../out com/example/text/Greeter.java com/example/app/Main.java
~~~

Run from **CWD = package-lab/src**:

~~~sh
java -cp ../out com.example.app.Main
~~~

Stdout is still:

~~~text
Hello, Lan!
~~~

From src, paths to source files no longer have the src/ prefix, and out is in the parent directory so ../out is used. If you still type src/com/example/app/Main.java from CWD = src, the compiler will look for src/src/com/example/app/Main.java and may report “file not found”.

Return to the project root if needed:

~~~sh
cd ..
~~~

| CWD | Main.java Source | -d | -cp at runtime | Main class |
| --- | --- | --- | --- | --- |
| package-lab | src/com/example/app/Main.java | out | out | com.example.app.Main |
| package-lab/src | com/example/app/Main.java | ../out | ../out | com.example.app.Main |

The package name and fully qualified class name **do not change** when CWD changes. Only the relative paths used in the terminal change.

## 7. How Do -cp and -sourcepath Differ from -d?

### Compiling Class by Class: The Compiler Needs to See Existing .class Files

From CWD = package-lab, create out if needed and compile Greeter first:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/com/example/text/Greeter.java
~~~

Now Greeter.class sits under out. Compile Main separately:

~~~sh
javac -encoding UTF-8 --release 17 -cp out -d out src/com/example/app/Main.java
~~~

Run:

~~~sh
java -cp out com.example.app.Main
~~~

The result is still Hello, Lan!.

In the second command, **-cp out** helps javac look up already-compiled dependent classes; meanwhile **-d out** specifies where to write the new Main.class. Both options take the same value here yet have different roles. The compiler classpath and runtime classpath are two configurations passed to two different programs; do not assume setting one side right automatically fixes the other.

### Finding Dependent .java Files with -sourcepath

Also from CWD = package-lab, we can pass only Main.java and specify where javac should search for dependent source files:

~~~sh
javac -encoding UTF-8 --release 17 -sourcepath src -d out src/com/example/app/Main.java
java -cp out com.example.app.Main
~~~

When the definition of Greeter is needed and no suitable compiled class exists yet, javac can find src/com/example/text/Greeter.java and compile the necessary source. This command works with the two sample classes.

| Option | Which kind of path does it ask for? |
| --- | --- |
| -sourcepath src | Root for the compiler to look up dependent **.java sources** |
| -cp out (when used with javac) | Root/JAR for the compiler to look up **compiled classes** and libraries |
| -d out | Root for the compiler to **write new .class files** |
| -cp out (when used with java) | Root/JAR for the **JVM** to look up classes at runtime |

In introductory lessons, explicitly passing both files as in section 4 is the easiest approach to control. For builds with many sources, let a build tool manage source sets, classpaths, and compilation order.

## 8. How Do package in Source Code and File Paths Relate?

Suppose the file remains at src/com/example/app/Main.java, but the declaration at the top of the file is changed to:

~~~java
package com.example.other;
~~~

When supplying an **explicit source file path** along with -d out, javac may still compile: the declared class name is com.example.other.Main and the bytecode will go into out/com/example/other/Main.class. At that point the name com.example.app.Main no longer points to the class just compiled.

That illustrates two principles:

- The package **declared in code** determines the Java class name; the physical path to the source file is an organizational convention and part of the source-lookup strategy.
- Because -sourcepath, IDEs, and build tools rely on package structure to locate files, keeping the two consistent is very important.

After restoring the right code, ensure no stale Main.class remains in use under a different package.

Another issue is when the public top-level class name does not match the file name. If you write public class Program inside Main.java, javac will require placing that public class in a file named Program.java. Do not confuse this file-naming rule with the package-mapping rule when outputting bytecode.

## 9. Typical Errors When Standing at the Wrong Root

### Error A — javac Reports “file not found”

Example: the terminal is in package-lab/src yet runs:

~~~sh
javac -d ../out src/com/example/app/Main.java
~~~

The relative path causes javac to look for package-lab/src/src/com/example/app/Main.java. Remove the src/ prefix or switch back to package-lab before using the command in section 4.

How to check: look at CWD first, then verify the file actually exists at the path passed to the compiler. This is a source-path selection error, not yet a Java syntax error.

### Error B — “package ... does not exist” or “cannot find symbol”

Main imports Greeter, but the compiler does not see Greeter.java/Greeter.class through the input paths or class-lookup settings. For simple examples, list both Greeter.java and Main.java explicitly in the same compile command; or compile Greeter first and use -cp out to compile Main.

Also check that the package name in the import and at the top of Greeter is spelled accurately, including uppercase/lowercase.

### Error C — “Could not find or load main class”

If you run:

~~~sh
java -cp out Main
~~~

the JVM will fail to find com.example.app.Main. Use the fully qualified name and root classpath:

~~~sh
java -cp out com.example.app.Main
~~~

A similar error appears if you set the classpath to out/com/example/app or stand in src while still passing -cp out (when out actually resides at ../out).

### Error D — “NoClassDefFoundError”

Compiling Main succeeded, yet at runtime Greeter.class or another dependency is missing. This is a runtime class-loading/linking error; check the **runtime classpath**, the actual .class set, and the JAR versions being used. An error can also relate to a class name not matching the expected location.

### Error E — “UnsupportedClassVersionError”

The bytecode version is newer than the running JVM. Check java -version and the compilation level. --release 17 instructs the compiler to target Java 17's class-file version and Java 17 platform APIs; it does not by itself guarantee all external JARs are compatible.

### Error F — Running Produces Old Content

If you edit Main.java without recompiling, the JVM may still execute the old .class. After a failed compilation, out may also retain files from a previous pass. In **practice exercise projects**, you can delete out separately, recreate it, and recompile from current sources to rule out stale results. Do not delete unfamiliar build directories in real projects without knowing how the build tool uses them.

| Symptom | Faulty Layer | First Check Direction |
| --- | --- | --- |
| file not found: src/... | Path to source | CWD and relative path |
| package ... does not exist | Package resolution at compile time | Import, dependent sources, -sourcepath, or -cp |
| cannot find symbol | Name/type resolution at compile time | Class/method name, dependencies, scope |
| Could not find or load main class | Finding startup class | Fully qualified class name, classpath root |
| NoClassDefFoundError | Class loading at runtime | Runtime classpath, required JAR/.class |
| UnsupportedClassVersionError | Bytecode compatibility | Running JDK and --release |

## 10. Using javap to Verify Which Classes Were Actually Created

From CWD = package-lab, after compiling successfully:

~~~sh
javap -classpath out com.example.app.Main
javap -classpath out com.example.text.Greeter
~~~

javap displays the full name and signatures of public members. The meaningful part of the result for Main:

~~~text
public final class com.example.app.Main {
  public static void main(java.lang.String[]);
}
~~~

Actual output may also include a Compiled from "Main.java" line at the top. For Greeter, you will see the method public static java.lang.String greet(java.lang.String). This lets you confirm the **bytecode class name** rather than relying only on source paths.

You can view deeper metadata:

~~~sh
javap -classpath out -verbose com.example.app.Main
~~~

For code compiled with --release 17, class-file **major version 61** corresponds to Java 17. Checking the version is useful, but does not replace verifying dependencies and classpath at runtime.

## 11. Projects Following the src/main/java Structure

Projects using Maven/Gradle typically place code in src/main/java instead of src:

~~~text
my-project/
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── app/
│                       └── Main.java
└── build/
    └── classes/
~~~

If Main is a standalone program needing no other sources/dependencies, standing at CWD = my-project and pre-creating build/classes, you can use:

~~~sh
javac -encoding UTF-8 --release 17 -d build/classes src/main/java/com/example/app/Main.java
java -cp build/classes com.example.app.Main
~~~

This command illustrates changing the source root and output root; **Main in the main practice exercise in section 3 depends on Greeter**, so if you want to use those exact two classes you must compile both sources or configure the compiler to locate dependencies accordingly. Do not treat this single-file example as a complete way to build every real project.

When a large application has external dependencies, annotation processors, module-info.java, multiple source sets, or JARs, use Gradle/Maven build tasks. Knowledge of CWD, source root, and classpath root still helps read errors from those tools more accurately.

## 12. Practice Exercises

1. **Predict paths yourself.** From CWD = package-lab, the path to Greeter.java is src/com/example/text/Greeter.java; from CWD = package-lab/src, the path is com/example/text/Greeter.java. Explain why the two commands differ.
2. **Compile and run.** Create the two files as in section 3, compile both from package-lab, run java -cp out com.example.app.Main, and compare against stdout Hello, Lan!.
3. **Change data.** Replace "Lan" with "Minh", recompile, and run. Stdout must be Hello, Minh!. If it does not change, look for stale .class files or check whether you are in the wrong CWD.
4. **Change terminal location.** Run from package-lab/src with -d ../out and -cp ../out, keeping the class name com.example.app.Main unchanged. Explain the three unchanging concepts yourself: package, class name, and program logic.
5. **Try separate compilation.** Compile Greeter only, then compile Main with -cp out. Explain why -cp and -d do not serve the same function even though both take out.
6. **Intentional wrong package.** Temporarily change Main's package to com.example.other. Observe where javac places .class with -d out, predict the class name needed when running java, then revert the source.
7. **Read bytecode.** Run javap -classpath out com.example.app.Main, and cross-check the full name against package in the source and the .class directory inside out.

## 13. Checklist Before Concluding Everything Is Correct

- CWD is explicitly verified with pwd or Get-Location.
- The path to each .java file is resolved from CWD and exists on disk.
- The package line in source matches the directory branch convention under the source root.
- Public top-level class has a matching file name.
- Output root already exists before using javac -d.
- All required classes/dependencies are visible to the compiler.
- The JVM uses a classpath pointing to the **root of the .class package tree**.
- java receives the fully qualified class name, e.g., com.example.app.Main.
- .class was just generated from current code, not a stale artifact.

You can remember three mappings:

~~~text
CWD + relative path              → Source .java file
Output root + package path       → Compiled .class file
Classpath root + full class name → Class for the JVM to load
~~~

When these three mappings are consistent, compiling a multi-package Java program from the project root or from the source root both work. The key lies not in a fixed terminal location, but in understanding how **source paths**, **package names**, and **classpath** work together.