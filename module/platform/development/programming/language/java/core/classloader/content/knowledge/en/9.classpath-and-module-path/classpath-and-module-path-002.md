# Setting `-cp`, `--class-path`, and the `CLASSPATH` Variable in Java

## 1. What Is the Classpath, and What Is It Used For?

**Classpath** (*class search path*) is a list of locations that Java tools use to find **application and library classes on the classpath**, typically consisting of directories containing `.class` files, `.jar` files, or `.zip` files. It is not a path to arbitrary Java source files, nor is it the entirety of places where the JVM can find every class: the JVM also has platform loaders, the module path, and other custom class loaders.

In the classic way of launching a Java program:

~~~text
                 java launcher
                       |
           Select effective classpath
                       |
           +-----------+------------+
           |                        |
  Root class directory   JAR/ZIP containing classes
   out/classes/               lib/feature.jar
           |                        |
           +-----------+------------+
                       |
          Application/System ClassLoader
                       |
               find class by name
              demo.Main -> demo/Main.class
~~~

For example, suppose a program needs the `demo.Main` and `util.Helper` classes. If the class files are located at:

~~~text
project/
├── out/
│   ├── app/demo/Main.class
│   └── lib/util/Helper.class
└── lib/helper.jar
~~~

then the classpath can contain **`out/app` and `out/lib`**. The class name `demo.Main` is mapped relatively to `demo/Main.class`. If you only add the path `out/app/demo`, the JVM will look in the wrong location for the name `demo.Main`; **a classpath entry must be the root of the package tree**.

For a JAR, the entry directly inside the archive must also have the corresponding package path, for example `util/Helper.class`. Passing a path directly to a specific `.class` file is not the standard way to configure the classpath for a class in a package.

## 2. The Three Options `-cp`, `-classpath`, and `--class-path`

For the **`java` launcher** and **`javac` compiler**, the following three forms are equivalent option names for specifying the user classpath:

~~~bash
java -cp out/classes demo.Main
java -classpath out/classes demo.Main
java --class-path out/classes demo.Main
~~~

Using any one of the three is sufficient. General syntax:

~~~text
java [JVM options] -cp <classpath> <fully.qualified.MainClass> [app arguments]
javac -cp <classpath> -d <output-directory> <source-files>
~~~

The pointed/angle brackets in the diagram above are **descriptive notation**, not to be typed literally. `-cp` is an option for the launcher or compiler and must be placed before the main class name when running in class mode. If placed **after** `demo.Main`, it becomes an argument in the application's `String[] args` instead of configuring the launcher.

| Option | Tool | Meaning |
| --- | --- | --- |
| `-cp path` | `java`, `javac` | Short form; convenient in terminals/scripts. |
| `-classpath path` | `java`, `javac` | Long name equivalent to `-cp`. |
| `--class-path path` | `java`, `javac` | Long option form; easy to read in scripts. |
| `-d output` | `javac` | Where to **write output `.class` files**; **does not automatically** add this location to the runtime classpath. |

Distinguish between the **compile-time classpath** and the **runtime classpath**:

- `javac -cp ...`: the compiler uses these directories/JARs to check and resolve types during compilation.
- `java -cp ...`: the JVM uses these sources at runtime to find the main class and dependencies needed by the system/application loader.
- These two lists are often related but are **not automatically synchronized**. Successful compilation does not mean the runtime will find all required JARs.
- Once you specify a classpath yourself, you must explicitly include the directory containing the output classes and the required dependencies in the list.

## 3. Joining Multiple Paths: OS-Specific Separators

A classpath is **a single value** that can contain multiple entries. The separator character is defined by the **operating system**:

| Operating System | Path separator | Example |
| --- | --- | --- |
| Windows (PowerShell or cmd) | `;` | `out\app;out\lib;lib\helper.jar` |
| Linux/macOS | `:` | `out/app:out/lib:lib/helper.jar` |

Example running on Windows PowerShell:

~~~powershell
java -cp "out\app;out\lib" demo.Main
java --class-path "out\app;lib\helper.jar" demo.Main
~~~

Corresponding example on Linux/macOS:

~~~bash
java -cp "out/app:out/lib" demo.Main
java --class-path "out/app:lib/helper.jar" demo.Main
~~~

**You should enclose the entire classpath in quotes** when it contains spaces or characters that the shell might handle specially. Especially in PowerShell, `;` outside a string is used to separate commands, so a classpath string with multiple entries must be quoted.

Relative paths are resolved from the process's **current working directory**, not automatically from the directory containing `Main.class` or a `.java` source file. Changing the working directory can cause the exact same command to suddenly fail to find classes.

**Do not use `:` to join paths on Windows** (since it also appears in drive letters such as `C:`), and likewise do not copy `;` directly from Windows into a Unix shell.

## 4. When Is the `CLASSPATH` Environment Variable Applied?

`CLASSPATH` is an **environment variable** that the Java launcher and compiler can read to obtain the user classpath **when no explicit classpath option is provided**.

Practical precedence rules for classic class mode:

~~~text
Explicit -cp / -classpath / --class-path provided?
             |
       +-----+---------+
       |               |
      Yes              No
       |               |
       v               v
Use command-    Is CLASSPATH set?
line value             |
                  +----+----+
                  |         |
                 Yes        No
                  |         |
                  v         v
           Use CLASSPATH   Use "."
~~~

If `-cp` is present, it **overrides the effective user classpath value from the `CLASSPATH` variable** for that command; the two values are not automatically concatenated. If neither the option nor the variable is set, the default user classpath is the **current directory `.`**.

Example:

~~~text
CLASSPATH=out/app:out/lib
java -cp out/other demo.Main
~~~

The final invocation will **not** automatically append `out/app:out/lib` to `out/other`. If you need them, list all of them in the `-cp` value. Also note that an explicit classpath **does not automatically include `.`**, so if you need the current directory, write it explicitly:

~~~bash
java -cp ".:lib/helper.jar" demo.Main       # Linux/macOS
~~~

On Windows, it is `java -cp ".;lib\helper.jar" demo.Main`.

### Setting in Windows PowerShell

~~~powershell
$env:CLASSPATH = "out\app;out\lib"
java demo.Main
~~~

This setting applies to the **current PowerShell session** and any processes spawned by it. To remove the variable in the current session:

~~~powershell
Remove-Item Env:CLASSPATH
~~~

If you only want to view the currently active value:

~~~powershell
$env:CLASSPATH
~~~

Equivalently, in Command Prompt (`cmd.exe`):

~~~bat
set CLASSPATH=out\app;out\lib
java demo.Main
set CLASSPATH=
~~~

### Setting in Bash/zsh on Linux or macOS

~~~bash
export CLASSPATH="out/app:out/lib"
java demo.Main
unset CLASSPATH
~~~

The variable only affects Java processes launched from that environment. Changing `CLASSPATH` after the JVM has already started **does not automatically update** the classpath of the running JVM.

**Recommendation:** prefer explicit `-cp` or `--class-path` in commands, build tasks, or project scripts. A global `CLASSPATH` variable often causes hard-to-reproduce errors when multiple projects require different libraries. Oracle's `javac` documentation also recommends not setting this variable when options can be passed explicitly.

## 5. Complete Java 17+ Example: Compile Classpath and Runtime Classpath

This hands-on example consists of **two classes in two different packages**. No frameworks or dependencies outside the JDK are needed.

Create the source structure:

~~~text
example/
└── src/
    ├── util/
    │   └── Helper.java
    └── demo/
        └── Main.java
~~~

### `src/util/Helper.java`

~~~java
package util;

public class Helper {
    public static String message() {
        return "Hello from helper";
    }
}
~~~

### `src/demo/Main.java`

~~~java
package demo;

import util.Helper;

public class Main {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
~~~

**Note:** the two snippets above are **two separate source files** and must be created at their exact corresponding paths and packages.

### Running on Windows PowerShell

From inside the `example` directory:

~~~powershell
New-Item -ItemType Directory -Force out\lib, out\app | Out-Null

javac -d out\lib src\util\Helper.java
javac -cp out\lib -d out\app src\demo\Main.java

java -cp "out\app;out\lib" demo.Main
java --class-path "out\app;out\lib" demo.Main
~~~

Both `java` commands print:

~~~text
Hello from helper
~~~

Explanation:

1. The command `javac -d out\lib src\util\Helper.java` generates `out/lib/util/Helper.class`.
2. The command compiling `Main` must use `-cp out\lib` so the compiler can find the type `util.Helper`. At the same time, `-d out\app` places the main class into `out/app/demo/Main.class`.
3. When running, `java` must see **both** `out\app` (where `demo.Main` is located) and `out\lib` (where `util.Helper` is located).
4. The main class name is **`demo.Main`**, not `Main` and not `out\app\demo\Main.class`.

Try the environment variable approach in PowerShell:

~~~powershell
$env:CLASSPATH = "out\app;out\lib"
java demo.Main
Remove-Item Env:CLASSPATH
~~~

The output is still:

~~~text
Hello from helper
~~~

If you want to use `CLASSPATH` for compilation, the variable can also serve as the default classpath for `javac`; however, the example intentionally uses `-cp` at compile time to avoid depending on machine state.

### Running on Linux/macOS

From inside the `example` directory with the two source files already created:

~~~bash
mkdir -p out/lib out/app

javac -d out/lib src/util/Helper.java
javac -cp out/lib -d out/app src/demo/Main.java

java -cp "out/app:out/lib" demo.Main
java --class-path "out/app:out/lib" demo.Main
~~~

The output of each run command is:

~~~text
Hello from helper
~~~

Shell session using the environment variable:

~~~bash
export CLASSPATH="out/app:out/lib"
java demo.Main
unset CLASSPATH
~~~

Output:

~~~text
Hello from helper
~~~

**Verified:** the Java code above compiles and runs on a modern JDK on Windows with `-cp`, `--class-path`, and `CLASSPATH`. The Linux/macOS version only changes the path separator and path slashes to match the OS syntax.

## 6. Using JAR Files and the `lib/*` Wildcard

A classpath entry can be a specific **JAR**:

~~~powershell
java -cp "out\app;lib\helper.jar" demo.Main  # Windows
~~~

~~~bash
java -cp "out/app:lib/helper.jar" demo.Main   # Linux/macOS
~~~

To test the exact example from section 5, first package the compiled `util.Helper` class:

~~~powershell
New-Item -ItemType Directory -Force lib | Out-Null
jar --create --file lib\helper.jar -C out\lib .
java -cp "out\app;lib\helper.jar" demo.Main
~~~

The commands above run in Windows PowerShell and print `Hello from helper`. Equivalently on Linux/macOS:

~~~bash
mkdir -p lib
jar --create --file lib/helper.jar -C out/lib .
java -cp "out/app:lib/helper.jar" demo.Main
~~~

**If there are multiple JARs in the same directory**, the Java launcher supports a wildcard entry whose **basename is literally `*`**:

~~~powershell
java -cp "out\app;lib\*" demo.Main   # Windows
~~~

~~~bash
java -cp "out/app:lib/*" demo.Main    # Linux/macOS
~~~

Key points to understand accurately about wildcards:

- `lib/*` expands to **JARs ending in `.jar` or `.JAR` located directly inside `lib`**, and does not recursively search subdirectories for JARs.
- `lib/*` **does not automatically add** the `lib` directory itself as a classpath entry for loose `.class` files. If you have `lib/com/example/X.class`, you must add the `lib` directory itself.
- The order of JARs when expanding a wildcard is **not guaranteed**. If multiple JARs contain a class with the same binary name, the behavior may depend on the actual lookup order and lead to version errors.
- Do not use wildcards as an arbitrary file glob like `lib/special-*.jar`; specify the exact JAR names or use `lib/*` according to Java's rules.
- Enclose `lib/*` in quotes so that the **shell does not expand** the wildcard according to its own rules before the Java launcher processes it.

Similarly, you can use a wildcard in the `CLASSPATH` value, though you must still pay attention to the separator and avoid letting a library depend on an unspecified order.

## 7. What Does the Order of Entries in the Classpath Mean?

Typically, the application loader searches sources in the order specified by the effective classpath (while adhering to the parent delegation policy). If two JARs both contain `com/example/Util.class`, the defined class may come from the JAR checked first; versions with the same name but different bytecode are a common cause of linkage errors such as `NoSuchMethodError`.

Example:

~~~bash
java -cp "app:lib/api-v1.jar:lib/api-v2.jar" demo.Main
~~~

You should not rely on placing multiple versions of a library on the classpath as a version-selection mechanism. Ensure that your dependency list and versions are consistent, especially when using `lib/*` because the JAR expansion order is not guaranteed.

However, **classpath order does not override all class loader policies**: parent-first delegation may prioritize a class already defined by a parent loader, and a custom loader may use a different strategy. The classpath primarily describes the **search sources** for the relevant loader/tool; it does not change the type identity of a class already defined by another loader.

## 8. `java -jar` Does Not Use Classpath the Same Way as Class Mode

This is a case where many people run into errors:

~~~bash
java -cp "lib/*" -jar app.jar
~~~

When using **`java -jar app.jar`**, the Java launcher selects the executable JAR that has `Main-Class` in `META-INF/MANIFEST.MF`. According to the launcher documentation, standard classpath settings such as `-cp` or the `CLASSPATH` variable **are not applied as the user classpath in JAR mode**. Therefore, do not expect the example above to add all JARs in `lib/*` to the `-jar` application.

If you want to run with an explicit classpath and you know the name of the class containing `main`, use **class mode**:

~~~powershell
java -cp "app.jar;lib\*" com.example.Main  # Windows
~~~

~~~bash
java -cp "app.jar:lib/*" com.example.Main   # Linux/macOS
~~~

In a real scenario, replace `com.example.Main` with the exact binary name of the class containing `public static void main(String[] args)`.

An **executable JAR** can also declare the `Class-Path` attribute in its manifest to reference dependent JARs (typically URLs relative to the JAR's location), following the JAR manifest rules. That mechanism is different from passing `-cp` to add libraries for `-jar`.

Framework JARs that have their own launcher or nested JAR loader (for example, framework-packaged JARs) may add dependency lookup mechanisms that do not match the traditional classpath; you need to read that launcher's contract and avoid inferring behavior solely from the `.jar` filename.

## 9. How Classpath Differs from Module Path and Custom Loaders

Since Java 9, Java has the **Java Platform Module System**:

| Concept | Used For | Example Configuration |
| --- | --- | --- |
| Classpath | Classes/JARs running in classpath mode, belonging to the **unnamed module** of the corresponding loader. | `java -cp "out:lib/*" demo.Main` |
| Module path | Search path for **named modules** resolved by the module system. | `java --module-path mods --module example.module/com.example.Main` |
| Custom loader URLs | Private sources of an application-created loader. | `new URLClassLoader(urls, parent)` |

A class placed only on the **module path** does not automatically become a class on the classpath, and vice versa. A class in a JAR read by a custom `URLClassLoader` does not necessarily appear in `java.class.path`. Similarly, classes loaded by the bootstrap/platform loader are not loaded because you listed every JDK module in `-cp`.

If you are learning about parent delegation: `-cp`/ `CLASSPATH` primarily affects the search sources of the **system/application loader** when launching in class mode. It should not be treated as a directive telling the parent loader to scan the dependency sources of all child loaders.

## 10. Distinguishing the Classpath from Other Java Paths

Commonly confused options:

- **`-d output` of `javac`**: where compilation output is saved, not the runtime classpath.
- **`--source-path` of `javac`**: where the compiler can find source files when needed, distinct from where compiled classes/JARs are found.
- **`--module-path` / `-p`**: where named modules are found, distinct from `--class-path`.
- **Operating system `PATH`**: where the shell searches for the `java` or `javac` executable; it does not tell the JVM where `demo.Main` is located.
- **`JAVA_HOME`**: typically points to the JDK installation, not the classpath.
- **`CLASSPATH`**: an optional environment variable serving as the default for Java tools when not overridden; it does not determine which JDK the JVM selects.
- **`java.library.path`**: related to finding native libraries (JNI), distinct from the search path for `.class` files.

If typing `java -version` succeeds but `java demo.Main` reports that the main class cannot be found, `PATH` may already be fine while the classpath or the main class name is still wrong.

## 11. Runtime Inspection and Common Troubleshooting

### 11.1. Inspecting the Active Classpath

Inside a program:

~~~java
System.out.println(System.getProperty("java.class.path"));
~~~

This is **an illustrative one-liner** that can be placed in the `main` method to inspect the classpath search path reported by the launcher. The output is useful when debugging, but it **does not represent all** sources from the bootstrap/platform/module path or custom loaders. In particular, do not use it to conclude that a plugin loaded by its own loader is on the system classpath.

In the terminal, you can also use:

~~~bash
java -XshowSettings:properties -version
~~~

Look for the `java.class.path` property in the property settings section. In addition, `java -verbose:class ...` or an appropriate class-loading logging option helps observe the source of loaded classes, though the output is verbose and should not be used as a way to predict every potential class search path.

### 11.2. Common Classpath Mistakes

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| `Error: Could not find or load main class demo.Main` | Missing root directory containing `demo/Main.class`, wrong package, or wrong main class name. | Inspect the file tree, use `-cp out/app demo.Main`, check `package demo;`. |
| `ClassNotFoundException` | The code or loader could not find the class with the requested binary name. | Check the sources of the **searching loader**, the classpath/module path, and the binary name. |
| `NoClassDefFoundError` at runtime | The dependency is no longer visible at runtime even though compilation succeeded; it can also happen if an earlier class initialization failed. | Check the runtime classpath, the cause/stack trace, and the actual execution command. |
| `NoSuchMethodError` or `NoSuchFieldError` | The runtime selected a library version incompatible with the one used at compile time. | Check for duplicate JARs, versions, and classpath order. |
| Command works in directory A, fails in directory B | Using relative paths from the working directory. | Use absolute paths or consistently `cd` to the project root. |
| Running `-cp lib/*` cannot find the main class | The wildcard only selects JARs and does not add `out/app` or directories of loose `.class` files. | Explicitly add the main class root directory to the classpath string. |
| Setting `CLASSPATH` and then running `-cp ...` makes the variable seem ignored | The CLI option overrides the environment variable. | Use a single explicit classpath configuration containing all required entries. |
| `java -cp ... -jar app.jar` still misses dependencies | JAR mode does not take the user classpath from `-cp`. | Use manifest `Class-Path`, the app's launcher, or run in class mode. |
| Errors on Windows when copying a Linux command | Wrong separator `:` instead of `;`, or missing quotes in PowerShell. | Use `;` and wrap the entire string in quotes on Windows. |

### 11.3. Self-Check Checklist

1. **Are you running in class mode or `-jar` mode?** If `-jar`, check the manifest and the JAR packaging mechanism.
2. **Did you add the package root directory?** For example, `demo.Main` requires `<root>/demo/Main.class`.
3. **Do the compile classpath and runtime classpath match the requirements?** The runtime must be able to find the libraries actually referenced.
4. **Is there an explicit `-cp` / `--class-path`?** If so, do not expect `CLASSPATH` to be appended automatically.
5. **Did you accidentally omit `.`?** When a classpath is explicitly specified, the current directory does not appear automatically unless you add it.
6. **Is the separator appropriate for the OS and shell?** Windows uses `;`, Linux/macOS uses `:`, and the whole string should generally be quoted.
7. **Are there JARs with duplicate classes/versions?** Avoid relying on an unspecified wildcard order.
8. **Are custom loaders or a module path involved?** Classes from other sources do not necessarily belong to the user classpath.
9. **Are you using a build tool?** Maven/Gradle/IDEs usually generate the runtime classpath automatically; check the actual Java command they launch rather than guessing from machine environment variables.

## 12. Review Questions

**Question 1:** On Windows, `CLASSPATH=out\app;out\lib` is set, yet running `java -cp out\app demo.Main` results in `NoClassDefFoundError` for `util.Helper`. Why?

**Answer:** `-cp out\app` overrides `CLASSPATH`, so the system classpath does not include `out\lib`. Fix it to `java -cp "out\app;out\lib" demo.Main`.

**Question 2:** Does using `-cp lib/*` automatically find all nested JARs inside `lib/a/` and all loose `.class` files under `lib`?

**Answer:** No. The wildcard only expands JARs directly inside `lib` and is not recursive; to find loose classes, you must add the class root directory itself.

**Question 3:** Why does `javac -cp lib/helper.jar` succeed while `java -cp out/app demo.Main` fails?

**Answer:** The compiler had the JAR at compile time, whereas the JVM does not have the same dependency at runtime. Add the JAR to the runtime classpath.

**Question 4:** Are `java -jar app.jar` and `java -cp "app.jar:lib/*" com.example.Main` equivalent?

**Answer:** No. JAR mode uses the JAR's manifest/main-class and its own dependency resolution mechanism; class mode selects the main class name along with an explicit classpath.

## Official Documentation

- [Java SE 21 – The `java` Command, `--class-path` Option, Wildcards, and `-jar`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 – The `javac` Command, `-cp`, `CLASSPATH` Variable, and `-d`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java SE 21 – `ClassLoader` and Parent Delegation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
