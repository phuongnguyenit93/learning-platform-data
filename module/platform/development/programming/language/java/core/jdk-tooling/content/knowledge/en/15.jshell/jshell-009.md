# Classpath in JShell

JShell is a REPL environment that lets you enter and run Java code snippets interactively. When you want to try out an externally compiled library or class, JShell needs to know where to find those class files. The classpath provides the list of directories and archives that JShell's compiler and execution engine use to locate classes.

You can set the classpath at JShell startup with `--class-path`, or update the environment mid-session using the `/env --class-path` command. This guide uses JDK 17 or later and covers how to use the classpath with class directories, JARs, and multiple dependencies, as well as how the classpath differs from the module path.

## 1. What Role Does the Classpath Play in JShell?

The classpath is a list of locations containing class files that Java needs to find when compiling or running code. Each entry is typically:

- A root directory containing a compiled package tree.
- A JAR file containing classes and resources.
- A ZIP file containing class files.

For example, if the class `com.example.Greeting` is located in:

~~~text
project/
├── out/
│   └── com/
│       └── example/
│           └── Greeting.class
└── lib/
    └── greeting.jar
~~~

then the classpath can point to the `out` directory or the `lib/greeting.jar` archive.

In JShell, after configuring the classpath, you can import the package and use the compiled classes:

~~~java
import com.example.Greeting;

System.out.println(new Greeting().message());
~~~

The classpath does not compile a library's source code automatically. External classes must already be compiled into `.class` files and placed in a directory or archive that the classpath points to.

## 2. Setting the Classpath When Starting JShell

Use the `--class-path` option:

~~~powershell
jshell --class-path out
~~~

If the class is inside a JAR:

~~~powershell
jshell --class-path lib/greeting.jar
~~~

You can also pass multiple directories or JARs in the same classpath.

On Windows, entries are separated by a semicolon:

~~~powershell
jshell --class-path "out;lib/greeting.jar;lib/logging.jar"
~~~

On Linux and macOS, use a colon:

~~~bash
jshell --class-path "out:lib/greeting.jar:lib/logging.jar"
~~~

Enclose the entire classpath value in quotes when it contains spaces or multiple entries. Example on Windows:

~~~powershell
jshell --class-path "build/classes;C:\Java Libraries\greeting.jar"
~~~

Example on Linux/macOS:

~~~bash
jshell --class-path "build/classes:/opt/java libraries/greeting.jar"
~~~

If `--class-path` is not used and the `CLASSPATH` environment variable is not set, JShell searches for classes in the current directory (`.`). The `--class-path` option overrides the environment's `CLASSPATH` value.

## 3. Compiling a Java Class and Using It in JShell

Create the source file `src/com/example/Greeting.java`:

~~~java
package com.example;

public class Greeting {
    private final String name;

    public Greeting(String name) {
        this.name = name;
    }

    public String message() {
        return "Hello, " + name + "!";
    }
}
~~~

From the project root directory, compile the class into the `out` directory:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -d out src/com/example/Greeting.java
~~~

After compilation, the file must be located at:

~~~text
out/com/example/Greeting.class
~~~

Start JShell with the `out` directory:

~~~powershell
jshell --class-path out
~~~

Enter the snippets:

~~~java
import com.example.Greeting;
Greeting greeting = new Greeting("JShell");
System.out.println(greeting.message());
~~~

Printed output:

~~~text
Hello, JShell!
~~~

This example shows that the classpath points to the root directory of the package tree. Do not point directly to the `Greeting.class` file, and do not point to the `com/example` directory; point to the parent directory that contains `com`.

## 4. Packaging Classes into a JAR and Adding It to the Classpath

For libraries distributed as JARs, the workflow is similar, except the classpath points to the archive.

From the project directory that already has `out/com/example/Greeting.class`, create the JAR:

~~~powershell
New-Item -ItemType Directory -Force -Path lib | Out-Null
jar --create --file lib/greeting.jar -C out .
~~~

Inspect the JAR contents:

~~~powershell
jar --list --file lib/greeting.jar
~~~

You should see entries similar to:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Greeting.class
~~~

Start JShell with the JAR:

~~~powershell
jshell --class-path lib/greeting.jar
~~~

Use the class:

~~~java
import com.example.Greeting;
System.out.println(new Greeting("JAR").message());
~~~

Output:

~~~text
Hello, JAR!
~~~

A JAR does not require an executable `Main-Class` manifest attribute to be used as a dependency on the classpath. JShell only needs the JAR to contain the packages and classes referenced by your snippets.

## 5. Using Multiple JARs and Transitive Dependencies

One library may depend on another library. In that case, the classpath must include both the direct library and the dependencies it requires.

Example:

~~~text
project/
├── lib/
│   ├── greeting.jar
│   ├── model.jar
│   └── logging.jar
└── out/
~~~

If `greeting.jar` uses classes from `model.jar` and `logging.jar`, add all three to the classpath.

Windows:

~~~powershell
jshell --class-path "lib/greeting.jar;lib/model.jar;lib/logging.jar"
~~~

Linux/macOS:

~~~bash
jshell --class-path "lib/greeting.jar:lib/model.jar:lib/logging.jar"
~~~

You can use a wildcard to include all JARs in a directory on the classpath:

~~~powershell
jshell --class-path "lib/*"
~~~

A classpath wildcard such as `lib/*` includes all JARs in that directory. The expansion order of the JARs is not guaranteed. If multiple versions contain the same class, class resolution may depend on the classpath order; remove duplicate JARs or specify an explicit order when deterministic results are required.

If you encounter `NoClassDefFoundError` or `ClassNotFoundException`, check both the main library and its dependencies. Adding only the first JAR may not be enough.

## 6. Updating the Classpath in a JShell Session with /env

If you already started JShell without setting a classpath, use the `/env` command:

~~~text
jshell> /env --class-path out
|  Setting new options and restoring state.
~~~

Then import the class:

~~~java
import com.example.Greeting;
System.out.println(new Greeting("updated classpath").message());
~~~

`/env` updates the execution environment and restarts the execution state. JShell runs startup scripts and replays the history of valid snippets in order. As a result, previous snippets may be re-evaluated in the new environment.

This is useful when you need to add a library after starting a session, but it can affect your active experimental state. If snippets rely on external side effects such as writing files, calling APIs, or updating databases, consider the impact of replaying them. Save important snippets with `/save` before changing the environment.

You can view the current environment settings with:

~~~text
jshell> /env
|     --class-path out
~~~

To view the syntax and other environment options:

~~~text
jshell> /help context
~~~

When updating the classpath, pass the complete list of entries you need. The new classpath value may replace the previously configured paths; do not assume a new path is automatically appended to the old one.

## 7. Complete Example: Creating a JAR and Starting JShell with a Classpath

You can run the entire workflow from the project directory using the following commands.

Create the structure:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Greeting.java
├── out/
└── lib/
~~~

Contents of `Greeting.java`:

~~~java
package com.example;

public class Greeting {
    public String message(String name) {
        return "Welcome, " + name + "!";
    }
}
~~~

Compile and package:

~~~powershell
New-Item -ItemType Directory -Force -Path out, lib | Out-Null
javac -d out src/com/example/Greeting.java
jar --create --file lib/greeting.jar -C out .
~~~

Start JShell:

~~~powershell
jshell --class-path lib/greeting.jar
~~~

Enter:

~~~java
import com.example.Greeting;
Greeting service = new Greeting();
System.out.println(service.message("Java learner"));
~~~

Output:

~~~text
Welcome, Java learner!
~~~

Exit JShell:

~~~text
jshell> /exit
~~~

If you want to use class files directly instead of creating a JAR, start with `jshell --class-path out`. Both class directories and JARs are valid classpath entries.

## 8. How Do Classpath and Module Path Differ?

Classpath and module path solve two different ways of locating code.

| Feature | Classpath | Module path |
|---|---|---|
| Input | Class directory, JAR, or ZIP | Named module, typically a modular JAR or exploded module |
| Model | Unnamed module | Named modules |
| Dependency declaration | Typically via build/classpath | Via `module-info.java` and `requires` |
| Package control | Minimal module constraints | Enforces `exports`, `opens`, and readability |
| JShell option | `--class-path` | `--module-path`, `--add-modules` |

If you want to use a standard library on the classpath, use:

~~~powershell
jshell --class-path lib/greeting.jar
~~~

If the library is a named module, use the module path and request the module to be resolved:

~~~powershell
jshell --module-path mods --add-modules com.example.greeting
~~~

Then import the package exported by the module. If the module does not export the package you need, simply adding the module to `--add-modules` does not make that package accessible. Check the module descriptor and its exports.

Do not place a modular JAR on the classpath expecting JShell to enforce all of its module rules. When you want to use JPMS, use the module path.

## 9. Important Limitations

### 9.1. Classes in the Unnamed Package Are Not Accessible

JShell cannot access classes located in the default package (unnamed package). Place library classes in a named package, such as `com.example`, compile them, and add the directory or JAR to the classpath.

### 9.2. Source Code Must Be Compiled

`--class-path` searches for class files in directories and archives. It does not automatically compile arbitrary `.java` files into a library. Compile them with `javac` or a build tool first, then add the output to the classpath.

### 9.3. Classpath Does Not Replace Module Path

A named module may require module resolution and package exports. If a library is designed as a module, configure `--module-path` and `--add-modules` instead of just adding the JAR to the classpath.

### 9.4. Duplicate Classpath Entries Can Cause Confusion

If two JARs contain the same fully qualified class name, the JVM may load the class from whichever entry is found first in classpath order. This can easily cause `NoSuchMethodError`, `NoSuchFieldError`, or inconsistent behavior when API versions differ.

Use a single consistent library version and remove older dependencies from the classpath.

### 9.5. JShell's Classpath Does Not Configure Other Applications

The classpath is set only for the current JShell process. It does not automatically update the classpath for your IDE, Maven, Gradle, or separate external `java` commands.

## 10. Common Errors When Configuring the Classpath

| Symptom | Common Cause | Solution |
|---|---|---|
| `package ... does not exist` | Classpath does not include the directory/JAR containing the package | Verify the path and package structure inside the archive |
| `cannot find symbol` | Class not compiled, wrong import, or missing dependency | Recompile, import the exact name, and add dependencies |
| `ClassNotFoundException` | Runtime cannot find the class being loaded | Check the startup classpath and class name |
| `NoClassDefFoundError` | Main class was found, but a runtime dependency is missing or failed to initialize | Add dependent JARs and inspect the root cause in the stack trace |
| `NoSuchMethodError` or `NoSuchFieldError` | Incompatible library version loaded by mistake | Check for duplicate JARs, classpath order, and API versions |
| Paths with spaces do not work | Classpath value was split into multiple arguments | Enclose the entire classpath in quotes |
| Windows cannot find the second JAR | Used `:` instead of `;` | Use a semicolon on Windows |
| Linux/macOS cannot find the second JAR | Used `;` instead of `:` | Use a colon on Linux/macOS |
| `/env` re-runs snippets | `/env` restarts the execution state and replays valid history | Save snippets; consider side effects before changing the environment |
| Cannot import default-package class | JShell cannot access classes in the unnamed package | Move the class into a named package and recompile |

## 11. Classpath Troubleshooting Workflow

When JShell cannot find a class:

1. Identify the fully qualified class name, such as `com.example.Greeting`.
2. Confirm the class has been compiled to `Greeting.class`.
3. Verify the path matching the package, such as `out/com/example/Greeting.class`.
4. Ensure the classpath points to the root `out` directory, not a nested package directory.
5. If using a JAR, list its contents with `jar --list --file`.
6. Check all dependencies required by that class.
7. Confirm the classpath separator matches your operating system and paths with spaces are quoted.
8. Use `/env` to inspect the current configuration or restart JShell with the complete classpath.
9. If the library is a named module, switch to the module path and check `module-info.java`.

You can inspect JAR contents with:

~~~powershell
jar --list --file lib/greeting.jar
~~~

And view the classpath currently used by JShell:

~~~text
jshell> /env
~~~

## 12. Checklist Before Using External Libraries in JShell

- [ ] The library has been compiled into class files.
- [ ] Classes are in a named package, not the unnamed package.
- [ ] The classpath points to the root directory of the package tree or the correct JAR.
- [ ] All required dependencies are included on the classpath.
- [ ] Multiple entries use the correct separator for your operating system.
- [ ] Paths containing spaces are enclosed in quotes.
- [ ] `--class-path` is used at startup or `/env --class-path` is used mid-session.
- [ ] Configuration has been verified with `/env`.
- [ ] Important snippets have been saved before running `/env`, as it replays history.
- [ ] If the library is a named module, module path is used instead of classpath.

The classpath lets JShell use externally compiled Java classes and libraries inside an interactive session. Point it to the root package directory or JAR, include all required dependencies, and choose the right separator for your operating system. When you need to change the classpath mid-session, use `/env --class-path` and keep in mind that JShell restarts the execution state and replays your snippet history. If a library uses JPMS, configure the module path and module resolution instead of the classpath.

## References

- Oracle, Java Shell User's Guide, JDK 17 — External Code: https://docs.oracle.com/en/java/javase/17/jshell/external-code.html
- Oracle, The jshell Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jshell.html
- Oracle, The java Command, JDK 17 — class path option: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html