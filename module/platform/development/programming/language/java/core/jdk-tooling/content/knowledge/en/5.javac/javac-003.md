# Compiling Multiple Sources with javac

## 1. Why compile multiple Java files at once?

A Java application is typically split into multiple classes and multiple source files so that each component has a clear responsibility. For example, a data management class may be used by a service class, while the main class calls the service class to run the application. In that case, one source file can reference a type declared in another file.

**javac** is the Java compiler. It takes one or more **.java** source files, parses syntax, checks types and relationships between classes, and then generates bytecode in **.class** files. When files depend on each other, you can pass all of them into a single javac invocation. The compiler resolves declarations and references among them in the same compilation pass; normally, you do not need to manually compile them in order.

Compiling multiple sources at once is useful when:

- A program consists of multiple classes across different packages.
- The main class uses utility classes or model classes in other files.
- Multiple classes have mutual type references and need to be compiled in a single pass.
- You want to control the output directory, Java version, and library dependencies with one consistent command.

Successful compilation only produces bytecode. To run the application, the runtime still needs to find the main class and all dependent libraries.

## 2. Basic Syntax

General syntax:

~~~bash
javac [compiler options] <source-file-1.java> <source-file-2.java> ...
~~~

Simple example:

~~~bash
javac First.java Second.java Third.java
~~~

The command above instructs javac to compile all three files in a single invocation. If one file uses a class declared in another file, include that source file in the list or configure the path so javac can find it.

A practical command usually includes additional options:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/com/example/model/Message.java src/com/example/service/GreetingService.java src/com/example/app/Main.java
~~~

Meaning:

- **--release 17**: compiles targeting Java 17 compatibility, including syntax, bytecode format, and platform APIs supported in that release.
- **-encoding UTF-8**: reads source code as UTF-8.
- **-d out**: writes the **.class** files into the **out** directory.
- The remaining paths are the source files to compile.

You can specify relative paths from the current terminal directory or absolute paths. When using relative paths, run the command from the project root directory so the paths remain consistent.

## 3. Package and Source Directory Structure

Suppose a project has three classes:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           ├── model/
│           │   └── Message.java
│           ├── service/
│           │   └── GreetingService.java
│           └── app/
│               └── Main.java
└── out/
~~~

Each file declares a package corresponding to the logical location of the class:

**Message.java**

~~~java
package com.example.model;

public class Message {
    public String text() {
        return "Hello";
    }
}
~~~

**GreetingService.java**

~~~java
package com.example.service;

import com.example.model.Message;

public class GreetingService {
    public String greeting(String name) {
        return new Message().text() + ", " + name + "!";
    }
}
~~~

**Main.java**

~~~java
package com.example.app;

import com.example.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        System.out.println(new GreetingService().greeting("Java"));
    }
}
~~~

The package name determines the fully qualified name of the class. For example, the Main class has the fully qualified name **com.example.app.Main**. The source directory structure should mirror the package so it is easy for humans to manage and for javac to locate dependent sources by package convention.

If a file declares a top-level public class, the filename must match that class name. For example, the public class **GreetingService** must reside in **GreetingService.java**. A mismatched filename or package declaration can cause compilation errors or type-not-found errors.

## 4. Approach 1: Listing All Sources in One Command

From the **project** directory, run:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/com/example/model/Message.java src/com/example/service/GreetingService.java src/com/example/app/Main.java
~~~

This command explicitly compiles all three files. Because all sources are passed in the same invocation, javac can resolve references among **Main**, **GreetingService**, and **Message** without needing to generate bytecode for each class beforehand.

After compilation, the output directory has the following structure:

~~~text
out/
└── com/
    └── example/
        ├── model/
        │   └── Message.class
        ├── service/
        │   └── GreetingService.class
        └── app/
            └── Main.class
~~~

The **-d out** option tells javac to place the bytecode in the target directory and create subdirectories matching the packages. When running the application, the classpath must point to the root directory containing the package tree—namely **out**—not directly to **out/com/example/app**.

Run the program:

~~~bash
java -cp out com.example.app.Main
~~~

Output:

~~~text
Hello, Java!
~~~

Note: the main class name when running must be its fully qualified name including the package. Do not append the **.class** extension, and do not pass a file path instead of a class name when using normal class execution mode.

## 5. Approach 2: Using -sourcepath to Locate Dependent Sources

It is not always necessary to list every source file. When one class references another whose source resides in a known directory tree, you can use **-sourcepath**:

~~~bash
javac --release 17 -encoding UTF-8 -sourcepath src -d out src/com/example/app/Main.java
~~~

In the example above:

- **src** is the root of the source tree.
- **Main.java** is the source file directly requested for compilation.
- javac finds **GreetingService.java** and **Message.java** based on package names and type references.
- **-d out** places the generated class files into the output directory.

Source paths are mapped by package name. For the class **com.example.service.GreetingService**, javac looks for the corresponding path under the source root, namely **src/com/example/service/GreetingService.java**.

When **-sourcepath** is not specified, javac may use the user classpath to search for sources according to the compiler's rules. In a clearly structured project, declaring **-sourcepath** explicitly makes it easier to understand and control where sources are searched.

This approach is convenient for small projects or learning examples. For larger projects, explicit compilation or using a build system provides better control over the source set, dependencies, and reproducible builds.

## 6. Distinguishing -sourcepath, -classpath, and -d

These three options solve three different problems:

| Option | Purpose | Example |
|---|---|---|
| **-sourcepath** | Locate **.java** source files that the compiler needs to read | **-sourcepath src** |
| **-classpath** or **-cp** | Locate compiled classes and dependent JAR libraries | **-cp lib/library.jar** |
| **-d** | Choose where to write the generated **.class** files | **-d out** |

Example when the source uses a library packaged as a JAR:

~~~bash
javac --release 17 -cp "lib/library.jar" -d out src/com/example/app/Main.java
~~~

Here, the classpath tells javac where the classes and APIs in the JAR referenced by the source are located. It does not replace sourcepath if uncompiled **.java** files need to be found.

All three can be combined:

~~~bash
javac --release 17 -encoding UTF-8 -sourcepath src -cp "lib/*" -d out src/com/example/app/Main.java
~~~

The **\*** in **lib/*** allows the classpath to include the JAR files in the **lib** directory. This wildcard applies to JARs directly inside that directory; it does not recursively search all subdirectories.

If **-cp** is specified, remember that the default classpath may be overridden. When you need both compiled classes in **out** and libraries in **lib**, add both to the classpath.

The separator for multiple classpath entries depends on the operating system:

| Operating System | Separator | Example |
|---|---|---|
| Windows | Semicolon **;** | **out;lib/*;tools/helper.jar** |
| Linux and macOS | Colon **:** | **out:lib/*:tools/helper.jar** |

Quoting the classpath prevents the shell from interpreting wildcard characters before Java receives the string.

## 7. Useful javac Options When Compiling Multiple Sources

### Selecting the Java version with --release

~~~bash
javac --release 17 -d out src/com/example/app/Main.java
~~~

**--release 17** instructs the compiler to generate bytecode and only allow platform APIs supported in Java 17. This is the right approach when using a newer JDK to compile an application that needs to run on Java 17.

**--release** has been available since JDK 9. If you need to support a JDK older than JDK 9, you must check the compatibility options available in that compiler version.

### Selecting the encoding

~~~bash
javac -encoding UTF-8 -d out src/com/example/app/Main.java
~~~

**-encoding UTF-8** specifies the character encoding used to read source files. You should standardize on UTF-8 across the entire project, especially when source code contains Vietnamese or non-ASCII characters. If a source file is saved in one encoding but the compiler reads it with a mismatched encoding, strings and comments may become garbled.

### Displaying warnings

~~~bash
javac -Xlint:all -d out src/com/example/app/Main.java
~~~

**-Xlint:all** instructs the compiler to report additional warnings. You can use **-Werror** to turn warnings into errors in quality-control workflows once the project has addressed the necessary warnings:

~~~bash
javac -Xlint:all -Werror -d out src/com/example/app/Main.java
~~~

You should not enable **-Werror** unexpectedly in an older project that has not been checked for warnings, as new warnings can cause the build to fail.

### Inspecting the compilation process

~~~bash
javac -verbose -d out src/com/example/app/Main.java
~~~

**-verbose** prints additional information about files being loaded and classes being compiled. This is a useful diagnostic tool when you need to know where the compiler is looking for sources or classes; the output can be very long.

## 8. Using an Argument File When There Are Many Source Files

A project with dozens or hundreds of sources can produce a very long command. In that case, put the options and paths into an argument file, such as **sources.txt**:

~~~text
--release
17
-encoding
UTF-8
-d
out
src/com/example/model/Message.java
src/com/example/service/GreetingService.java
src/com/example/app/Main.java
~~~

Then invoke:

~~~bash
javac @sources.txt
~~~

The **@** character tells javac to read arguments from the specified file. An argument file can contain compiler options and source file names; each line is one argument in this simple example.

If a path contains spaces, enclose that individual path in double quotes according to argument file syntax. When creating the file, use an encoding suitable for the environment running javac. Relative paths inside the file are resolved against the working directory where the command is invoked; keep the execution directory consistent to avoid file-not-found errors.

Argument files help avoid shell or OS command-line length limits and allow you to save the set of sources to compile for reuse. When a project has many dependencies and needs incremental compilation, Maven or Gradle is usually more suitable than managing file lists manually.

## 9. Compiling Sources That Depend on External Libraries

Suppose a class uses a type provided by **library.jar**. javac must have that library on the classpath during compilation:

~~~bash
javac --release 17 -cp "lib/library.jar" -d out src/com/example/app/Main.java
~~~

If the program also depends on other project classes, add the directory containing compiled classes to the classpath. For example:

~~~bash
javac --release 17 -cp "out;lib/*" -d out src/com/example/app/Main.java
~~~

The example above uses the Windows separator. On Linux or macOS, replace the semicolon with a colon:

~~~bash
javac --release 17 -cp "out:lib/*" -d out src/com/example/app/Main.java
~~~

Successful compilation does not mean the program will run if the runtime cannot find the libraries. At runtime, the classpath must also include the **out** directory and the required JARs:

Windows:

~~~bat
java -cp "out;lib/*" com.example.app.Main
~~~

Linux or macOS:

~~~bash
java -cp "out:lib/*" com.example.app.Main
~~~

Make sure the libraries are present at both the compile step and the run step. The runtime classpath is not automatically inherited from the previous javac command.

## 10. Verifying Compilation Results

After compiling, verify that the output directory contains the class files organized by package:

~~~text
out/com/example/model/Message.class
out/com/example/service/GreetingService.class
out/com/example/app/Main.class
~~~

On Windows, you can use:

~~~bat
dir /s /b out\*.class
~~~

On Linux or macOS:

~~~bash
find out -name "*.class"
~~~

Run the main class using its fully qualified name:

~~~bash
java -cp out com.example.app.Main
~~~

If the application has external libraries, add the JARs to the runtime classpath. If using Java modules, compilation and execution must follow the corresponding module path and module structure; do not arbitrarily mix classpath and module path.

## 11. Common Errors and How to Fix Them

### error: file not found

javac cannot find the specified source path. Check the current working directory, filename, **.java** extension, and OS-specific directory separators. If using relative paths, confirm that the command is being run from the intended project root directory.

### package ... does not exist or cannot find symbol

The compiler cannot find the imported type or package. Check that:

- The source file declares a package matching the directory structure.
- Dependent source files are included in the command list or can be found via **-sourcepath**.
- Compiled classes or JAR libraries are on **-cp**.
- Package names, class names, and letter casing are exact.

If the dependency is uncompiled source code, **-cp** alone does not replace **-sourcepath**. If the dependency is a JAR or compiled class, add it to the classpath.

### class ... is public, should be declared in a file named ...

The filename does not match the top-level public class name. Rename either the file or the class so they match. For example, **public class GreetingService** must be declared in **GreetingService.java**.

### duplicate class

The same class may be declared in multiple files, or the same source may be included multiple times from different directories. Check the package, class name, and source list. Do not compile two versions of a class with the same fully qualified name at the same time.

### incompatible types or cross-class reference errors

Check method signatures, return types, constructors, access modifiers, and imports. Compiling multiple sources in the same command lets javac see all declarations in one pass, but it cannot fix type mismatches or invalid circular inheritance designs.

### Unsupported release

The current compiler does not support the requested release. Check the version with **javac -version** and use a JDK that supports that **--release** level. For example, to use **--release 17**, use javac from JDK 17 or later.

### ClassNotFoundException or NoClassDefFoundError at runtime

This is usually a runtime issue. Check whether the classpath root directory contains the compiled package tree, whether the main class name includes its full package, and whether dependent libraries are on the runtime classpath. Do not point the classpath directly at a nested package subdirectory when invoking the main class by its fully qualified name.

### Compiles successfully but runs old code

The output directory may still contain stale **.class** files, or you may be running from a different classpath. Compile into a clean output directory, check the timestamps and locations of the class files, and make sure the `java` command uses that exact directory. For larger projects, use a build tool to manage cleaning old outputs and recompiling affected parts.

## 12. When Should You Use Maven or Gradle?

Invoking javac directly is suitable for lessons, small programs, standalone examples, or when you want to understand the compiler workflow. When a project has many modules, libraries, resources, tests, plugins, and environment configurations, manual source lists and classpaths become hard to maintain.

Maven and Gradle help manage:

- Source lists and source set structures.
- Library dependencies and versions.
- Incremental compilation, task ordering, and output directories.
- Testing, JAR packaging, and CI build pipelines.
- Target Java version and project toolchains.

Even when using a build tool, understanding **javac**, **-sourcepath**, **-cp**, **-d**, and **--release** remains helpful when reading build logs or troubleshooting compilation errors.

## 13. Multi-Source Compilation Checklist

- [ ] Running the command from the correct project root directory.
- [ ] Each source has a valid package and filename.
- [ ] All required sources are listed or **-sourcepath** is declared.
- [ ] Compiled classes and JARs are on **-cp** if the sources need them.
- [ ] **-d** is used to manage where bytecode is saved.
- [ ] Encoding is standardized, usually UTF-8.
- [ ] Java compatibility level is selected with **--release**.
- [ ] Generated **.class** structure is verified by package.
- [ ] Runtime classpath includes the output directory and all required libraries.
- [ ] Main class is run by its fully qualified name and output is verified.
