# Output directory when compiling with javac

**Output directory** is the destination directory that the Java compiler uses to write output files. With the **javac** command, the **-d** option specifies where to store the compiled **.class** bytecode files. Separating source code and bytecode into two distinct directories makes a project easier to run, package, test, and clean.

Example:

~~~bash
javac -d build/classes src/com/example/Main.java
~~~

This command compiles the source code and writes the class files into build/classes. If the class belongs to the com.example package, javac creates the corresponding directory structure under the output directory:

~~~text
build/
└── classes/
    └── com/
        └── example/
            └── Main.class
~~~

The build/classes directory must exist before running javac; the compiler does not automatically create the root destination directory. Subdirectories corresponding to packages are created inside the destination directory when needed.

## 1. The -d option of javac

Syntax:

~~~bash
javac -d <directory> <source-files>
~~~

Where:

- **-d** is the option specifying the destination directory.
- **directory** is the output directory path.
- **source-files** is one or more .java files to compile.

Example:

~~~bash
mkdir -p build/classes
javac -d build/classes src/com/example/Main.java
~~~

In PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "build/classes" | Out-Null
javac -d "build/classes" "src/com/example/Main.java"
~~~

If a path contains spaces, enclose the path in quotes so the shell passes it as a single argument.

When -d is not specified, javac writes class files next to their corresponding source files in the default compilation mode. This can mix source code and bytecode together, especially when a project has multiple packages or multiple compilation runs. Specifying an output directory keeps the output centralized and easy to manage.

## 2. Package structure in the output directory

The destination directory path is combined with the package name declared in the source code. For example, the file src/com/example/app/Main.java:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from javac.");
    }
}
~~~

Compile:

~~~bash
mkdir -p out
javac -d out src/com/example/app/Main.java
~~~

Result:

~~~text
out/
└── com/
    └── example/
        └── app/
            └── Main.class
~~~

The source file declares package com.example.app, so the class is placed at out/com/example/app/Main.class. The package name determines the output directory structure; javac does not use the source directory name as the sole rule.

If a class does not declare a package (default package), the class file is written directly into the output directory:

~~~text
out/
└── Main.class
~~~

In real-world projects, classes should be placed in clearly named packages rather than using the default package. Packages help avoid class name collisions, organize source code, and determine the fully qualified name when running the program.

## 3. Compiling multiple source files into the same directory

A program usually has multiple classes located in different packages. Example structure:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           ├── app/
│           │   └── Main.java
│           └── util/
│               └── Greeting.java
└── build/
    └── classes/
~~~

File Greeting.java:

~~~java
package com.example.util;

public class Greeting {
    public static String message() {
        return "Hello from the output directory.";
    }
}
~~~

File Main.java:

~~~java
package com.example.app;

import com.example.util.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Create the output directory and compile both files:

~~~bash
mkdir -p build/classes
javac --release 17 -d build/classes \
    src/com/example/util/Greeting.java \
    src/com/example/app/Main.java
~~~

In PowerShell, you can write the command on a single line:

~~~powershell
New-Item -ItemType Directory -Force -Path "build/classes" | Out-Null
javac --release 17 -d "build/classes" "src/com/example/util/Greeting.java" "src/com/example/app/Main.java"
~~~

Both classes are written to the same output directory while still residing in their respective package directories:

~~~text
build/classes/
└── com/
    └── example/
        ├── app/
        │   └── Main.class
        └── util/
            └── Greeting.class
~~~

Multiple .java files can be passed in a single javac invocation. The compiler analyzes the relationships between classes in the source set and generates the corresponding bytecode. This is usually the clearest approach for small examples or simple build scripts.

## 4. Combining -d with -sourcepath

**-sourcepath** specifies where javac looks for additional source files when it needs to compile referenced classes that were not passed directly on the command line. It differs from **-d**:

- **-sourcepath**: where to find .java source code.
- **-d**: where to write .class bytecode.

With the src/com/example/app/Main.java and src/com/example/util/Greeting.java structure from the previous section, you can pass only Main.java:

~~~bash
mkdir -p build/classes
javac --release 17 -sourcepath src -d build/classes \
    src/com/example/app/Main.java
~~~

When Main references com.example.util.Greeting, javac locates the corresponding source under src and can compile that class as needed.

The sourcepath is the root for package lookup. For package com.example.util, javac looks for the corresponding file following the com/example/util/Greeting.java structure beneath each sourcepath root.

Multiple source directories can be specified, separated by the operating system's classpath separator:

~~~bash
javac -sourcepath "src:generated-src" -d build/classes src/com/example/app/Main.java
~~~

On Windows, the separator between classpath entries is a semicolon:

~~~powershell
javac -sourcepath "src;generated-src" -d "build/classes" "src/com/example/app/Main.java"
~~~

When writing cross-platform scripts, pay attention to differences in path separators and shell quoting rules. If you want commands to be readable and less dependent on the shell, you can list source files explicitly or use an argument file.

## 5. Distinguishing -d, -cp, and -sourcepath

These three options handle three different responsibilities:

| Option | Function | Example |
|---|---|---|
| **-d** | Writes class files to the destination directory | -d build/classes |
| **-cp** or **-classpath** | Finds dependent classes or JARs when compiling/running | -cp libs/library.jar |
| **-sourcepath** | Finds Java source files when javac needs additional compilation | -sourcepath src |

Example of a project using an external library:

~~~bash
javac --release 17 -cp "libs/example.jar" -d build/classes src/com/example/Main.java
~~~

Javac reads the library from the classpath, reads the source from the passed path, and writes the class files into build/classes.

A common misconception is thinking that -d build/classes automatically adds that directory to the classpath at runtime. That is not true. When running the program, you must specify the classpath separately:

~~~bash
java -cp build/classes com.example.app.Main
~~~

If external libraries are also needed:

~~~bash
java -cp "build/classes:libs/example.jar" com.example.app.Main
~~~

On Windows:

~~~powershell
java -cp "build/classes;libs/example.jar" com.example.app.Main
~~~

The class name when running is the fully qualified name including the package, not the .class file path. For example, com.example.app.Main corresponds to build/classes/com/example/app/Main.class when the classpath root is build/classes.

## 6. Naming and organizing the output directory

The output directory name is not fixed by javac. A project can use out, classes, build/classes, or another name. What matters is that all compile, run, test, and package commands consistently reference the same location.

A commonly used structure:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/
│   └── test/
│       └── java/
├── build/
│   ├── classes/
│   │   ├── main/
│   │   └── test/
│   └── libs/
└── libs/
~~~

In Gradle projects, main source output is typically located under build/classes/java/main; test code has its own output. In Maven, main bytecode is typically in target/classes and test bytecode in target/test-classes. These are build tool conventions, not mandatory names for the javac option.

If you organize a project manually, you should separate main and test outputs:

~~~bash
mkdir -p build/classes/main build/classes/test
~~~

Compile main source code:

~~~bash
javac --release 17 -d build/classes/main src/main/java/com/example/Main.java
~~~

Compile tests once the test library and main classes are on the classpath:

~~~bash
javac --release 17 -cp "build/classes/main:libs/junit.jar" \
    -d build/classes/test src/test/java/com/example/MainTest.java
~~~

The command is illustrated for a Unix-like shell. On Windows, replace the colon in the classpath with a semicolon and adjust paths if needed. Separating outputs prevents mixing test classes with runtime artifacts.

## 7. Argument files for long source lists

When there are many source files or the command line becomes too long, javac supports argument files. This file contains options and source names for javac to read as command-line arguments.

Example creating sources.args:

~~~text
--release
17
-d
build/classes
src/com/example/util/Greeting.java
src/com/example/app/Main.java
~~~

Run:

~~~bash
mkdir -p build/classes
javac @sources.args
~~~

Multiple argument files can be passed in a single command. Quoting and escaping rules inside argument files are defined by javac; when paths contain spaces, follow javac's syntax rather than copying shell syntax by default.

Argument files are useful when a project has hundreds of sources or when a script needs to keep the source list easy to inspect. If the file is generated automatically, ensure its encoding and paths are compatible with the build environment.

## 8. Output directory in modular programs

For Java Platform Module System projects, source code can contain module-info.java. When compiling modules, javac still uses -d to specify the output root. When compiling multiple modules from a module source path, the output is separated by module to avoid mixing classes from different modules.

A simple source structure:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/
        └── example/
            └── app/
                └── Main.java
~~~

module-info.java:

~~~java
module com.example.app {
}
~~~

Compile the module:

~~~bash
mkdir -p out
javac --release 17 --module-source-path src -d out \
    -m com.example.app
~~~

With a module source path like the above, output is organized under the corresponding module directory. When running modules, options such as --module-path and --module specify where to find modules and which module/class to run. Inspect the actual output structure and check module-info.class after compiling.

For a single simple module, you can also pass module-info.java directly along with the module's source files:

~~~bash
mkdir -p out
javac --release 17 -d out \
    src/com.example.app/module-info.java \
    src/com.example.app/com/example/app/Main.java
~~~

Do not arbitrarily mix outputs of different modules into the same package tree. Module names, exported packages, and the module path are distinct parts of the module model.

## 9. Other javac output directories

The -d option is primarily for class files. Several other output types have their own options:

| Option | Output |
|---|---|
| **-d directory** | .class files |
| **-s directory** | Source code generated by annotation processors |
| **-h directory** | Native headers generated for JNI |
| **-proc:only** | Run annotation processing only, without regular class compilation |
| **-proc:none** | Do not run annotation processing |

Example with an annotation processor:

~~~bash
mkdir -p build/classes build/generated-sources
javac -processorpath libs/processor.jar \
    -processor com.example.GenerateProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/com/example/Model.java
~~~

Here, class output goes into build/classes, while source generated by the processor goes into build/generated-sources. Do not confuse -s with -d: they serve two different types of artifacts.

Example generating JNI headers:

~~~bash
mkdir -p build/classes build/headers
javac -h build/headers -d build/classes src/com/example/NativeBridge.java
~~~

The header directory contains the generated header files if the source declares matching native methods. If you do not use annotation processors or JNI, there is no need to create these directories.

## 10. Cleaning the output directory and avoiding stale classes

Javac overwrites regenerated class files, but it is not a tool for cleaning the entire output directory. If a source class is deleted or renamed, the old .class file may still remain in the output directory.

For example, suppose there was previously:

~~~text
src/com/example/OldService.java
~~~

Later, if this source is renamed or deleted while reusing build/classes, the file:

~~~text
build/classes/com/example/OldService.class
~~~

may still remain from the previous compile. Stale files can cause confusion when running, packaging JARs, or testing.

For a clean build, remove the output directory and recreate it:

~~~bash
rm -rf build/classes
mkdir -p build/classes
javac --release 17 -d build/classes src/com/example/Main.java
~~~

In PowerShell:

~~~powershell
if (Test-Path "build/classes") {
    Remove-Item -Recurse -Force "build/classes"
}
New-Item -ItemType Directory -Force -Path "build/classes" | Out-Null
javac --release 17 -d "build/classes" "src/com/example/Main.java"
~~~

Only delete the exact build directory managed by the project. Do not run a broad delete command on an unverified path if that directory may still contain artifacts that need to be kept.

In a build pipeline, include an explicit clean step or use a build tool to manage output. This prevents differing results between developer machines and CI caused by leftover class files.

## 11. Packaging the output directory into a JAR

After compilation, the output directory contains bytecode and can be packaged into a JAR:

~~~bash
jar --create --file build/app.jar -C build/classes .
~~~

The -C option changes the working directory of the jar command to build/classes, and then the dot includes the contents of that directory in the archive. Package paths are preserved inside the JAR.

If Main-Class is specified in the manifest, you can create an executable JAR. Create a manifest.mf file:

~~~text
Main-Class: com.example.app.Main

~~~

The trailing blank line in the manifest is required to terminate the header section. Create the JAR:

~~~bash
jar --create --file build/app.jar --manifest manifest.mf -C build/classes .
~~~

Run:

~~~bash
java -jar build/app.jar
~~~

A JAR only contains the files present in the output directory at packaging time. If compilation missed classes or placed output in the wrong location, the JAR will also be missing the corresponding contents. If the application depends on external libraries, you need to package dependencies or configure the classpath/module path appropriately; the basic jar command does not automatically bundle all dependencies.

## 12. Complete hands-on example with Java 17+

This example includes two classes in two different packages to illustrate how javac creates a package tree inside the output directory.

Source structure:

~~~text
output-demo/
└── src/
    └── com/
        └── example/
            ├── app/
            │   └── Main.java
            └── util/
                └── Greeting.java
~~~

Create src/com/example/util/Greeting.java:

~~~java
package com.example.util;

public class Greeting {
    public static String message() {
        return "Hello from javac output directory.";
    }
}
~~~

Create src/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.util.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

From the output-demo root directory, create the output directory:

~~~bash
mkdir -p build/classes
~~~

Compile both classes:

~~~bash
javac --release 17 -d build/classes \
    src/com/example/util/Greeting.java \
    src/com/example/app/Main.java
~~~

After compilation, the directory tree:

~~~text
output-demo/
├── src/
│   └── com/
│       └── example/
│           ├── app/
│           │   └── Main.java
│           └── util/
│               └── Greeting.java
└── build/
    └── classes/
        └── com/
            └── example/
                ├── app/
                │   └── Main.class
                └── util/
                    └── Greeting.class
~~~

Run the program using the output directory as the classpath root:

~~~bash
java -cp build/classes com.example.app.Main
~~~

Exact output:

~~~text
Hello from javac output directory.
~~~

If you get ClassNotFoundException or Could not find or load main class, check:

1. Are you running from the correct root directory or using an absolute output path?
2. Does the classpath point to build/classes?
3. Is the fully qualified class name exactly com.example.app.Main?
4. Does the file build/classes/com/example/app/Main.class exist?
5. Did the compile command write to the right output directory?

If you encounter package com.example.util does not exist, check whether Greeting.java is included in the compiled source set or located under sourcepath with the correct package structure.

## 13. Common errors and how to resolve them

**Output directory does not exist**

This error commonly occurs when passing -d build/classes before the build/classes directory has been created. Create the directory before running javac. Javac does not create the root destination directory.

**Confusing -d with -cp**

-d determines where to write classes; -cp determines where to find classes/JARs. After compiling, use java -cp <output-directory> to run.

**Package declaration does not match expectations**

The output path is created based on the package declared in the source. Check the package statement and the fully qualified class name when running.

**Running by file path instead of fully qualified class name**

For compiled classes with a package, run java -cp out com.example.Main, not the path out/com/example/Main.class.

**Compiling only the main class without finding helper classes**

Pass the related source files directly or declare -sourcepath pointing to the root of the source tree.

**Using leftover stale classes**

Delete and recreate the output directory before a clean build to remove classes that were deleted or renamed in source.

**Packaging the output directory into a JAR at the wrong level**

Use jar -C build/classes . to place the contents of the output directory into the archive. If you package the build/classes directory from its parent directory, the JAR may include an extra build/classes/ path so the package path is no longer at the archive root.

**Using the same directory for source and output**

Separating src and build/classes helps control artifacts, avoid mixing up files, and simplify cleanup. Do not let generated bytecode be treated as input source in subsequent builds.

## 14. Output directory workflow

A simple, repeatable javac workflow:

1. Choose a dedicated output directory for each kind of source code, such as build/classes.
2. Create the destination directory before compiling.
3. Select the Java release with --release if you need to control the target API and bytecode.
4. Pass all source files or configure -sourcepath.
5. Use -cp for libraries required during compilation.
6. Verify the generated package tree and class files.
7. Run with the classpath pointing to the output directory.
8. Clean the output before rebuilding when you need to ensure no stale classes remain.
9. Package the output contents into a JAR when distribution is needed.

The output directory is the boundary between source code and compiled bytecode. When using javac -d consistently, packages map to a clear directory structure, the runtime classpath is easy to determine, and the build process becomes more reproducible.
