# Writing Class Files

When compiling Java source code, `javac` generates **class files** with the `.class` extension. These are binary files containing bytecode and metadata that the Java Virtual Machine (JVM) uses to load, verify, and execute the program.

For example, source code declaring the class `com.example.App` is typically represented by a class file at the path:

```text
com/example/App.class
```

A `.class` file is neither Java source code nor a native executable specific to Windows, macOS, or Linux. Bytecode can run on different operating systems as long as the JVM environment is compatible with the class file version, APIs, and dependencies used by the program.

## 1. Role of Class Files in the Compilation Pipeline

A basic Java workflow can be described as follows:

```text
.java source code
      |
      v
javac: syntax parsing, type checking,
       dependency resolution, and compilation
      |
      v
.class class file (bytecode + metadata)
      |
      v
JVM: class loading, verification, and linking
      |
      v
Program execution
```

`javac` is responsible for translating source code into class files. When running the program, the JVM locates and loads the required class files from the classpath or module path. The JVM can interpret bytecode or compile hot code paths into machine code using the JIT compiler.

It is important to distinguish between:

- `.java`: a text file containing source code written by the developer.
- `.class`: a binary file containing a compiled class definition.
- `.jar`: a ZIP archive used to distribute multiple class files, resources, and metadata.
- Machine code: CPU instructions generated during execution/JIT compilation or provided by native libraries.

A successful compilation only means that the compiler produced output according to its configuration. It does not guarantee that all dependencies are present at runtime or that the application logic works correctly.

## 2. Compiling and Inspecting Your First Class File

Create a file named `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, class file!");
    }
}
```

From the directory containing the file, run:

```sh
javac Hello.java
```

If there are no errors, the current directory will now contain:

```text
Hello.java
Hello.class
```

Normally, `javac` prints no output when compilation succeeds. You can verify the generated file using an OS command:

```sh
ls -l Hello.class
```

On PowerShell:

```powershell
Get-Item .\Hello.class
```

Run the program:

```sh
java Hello
```

Output:

```text
Hello, class file!
```

The `javac` command takes a source file name with the `.java` extension; the `java` command takes the class name to launch, without the `.class` extension.

## 3. Where Class Files Are Written

There are two common ways to determine where `javac` writes its output.

### 3.1. Without -d

If `-d` is not specified, the compiler usually places the class file in the same directory as its corresponding source file.

For example:

```text
project/
└── src/
    └── com/
        └── example/
            └── App.java
```

Compile from the `project` directory:

```sh
javac src/com/example/App.java
```

The default output sits next to the source file:

```text
project/
└── src/
    └── com/
        └── example/
            ├── App.java
            └── App.class
```

With this approach, to run a class in the `com.example` package, the classpath must point to the root directory of the package structure, which in this example is `src`:

```sh
java -cp src com.example.App
```

This default compilation approach works for small experiments, but it mixes source code and build output. For real projects, they should be kept in separate directories.

### 3.2. Using -d to Specify the Output Directory

The `-d` option specifies the root directory where class files are written:

```sh
javac -d out src/com/example/App.java
```

The `out` directory must exist before invoking `javac`. The compiler creates subdirectories corresponding to the packages beneath this directory.

On macOS/Linux, you can create the directory with:

```sh
mkdir -p out
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
```

After compilation, the directory structure looks like:

```text
project/
├── src/
│   └── com/example/App.java
└── out/
    └── com/
        └── example/
            └── App.class
```

Run the class by putting the output root directory on the classpath:

```sh
java -cp out com.example.App
```

If a class does not belong to any package (the default package), the class file is written directly in the output directory, for example `out/Hello.class`.

**Key takeaway:** `-d` is the root directory for bytecode, not the path to a single `.class` file. For the `com.example` package, the compiler automatically creates the `com/example` path under the output directory.

## 4. A Single Source File Can Produce Multiple Class Files

There is no rule that one `.java` file always corresponds to exactly one `.class` file. A single source file can declare multiple top-level classes, nested classes, enums, or records; the compiler can generate multiple corresponding class files.

Example `App.java`:

```java
package com.example;

public class App {
    public static void main(String[] args) {
        Helper helper = new Helper();
        Formatter formatter = new Formatter();

        System.out.println(formatter.format(helper.message()));
    }

    static class Formatter {
        String format(String value) {
            return "[" + value + "]";
        }
    }
}

class Helper {
    String message() {
        return "class files";
    }
}
```

Compile:

```sh
mkdir -p out
javac -d out App.java
```

If the file is saved in the current directory and declares a package as in the example, place it in the proper location or run the command from the appropriate source layout. Upon successful compilation, the corresponding class files include:

```text
out/
└── com/
    └── example/
        ├── App.class
        ├── App$Formatter.class
        └── Helper.class
```

The name `App$Formatter.class` is how the compiler represents a nested class in its binary name. The `$` character can also appear in Java identifiers written by developers, so you should not rely solely on this character to infer that a class is definitely a nested class.

Run the main class:

```sh
java -cp out com.example.App
```

Output:

```text
[class files]
```

Local classes and anonymous classes can also generate their own class files. The internal names of these class files may contain compiler-generated numbers or symbols; those names should not be treated as a stable API for referencing in source code.

## 5. Packages Determine the Output Directory Structure

A class's fully qualified package name is mapped to a directory path. For example:

| Fully qualified class name | Class file path under output root |
|---|---|
| `com.example.App` | `com/example/App.class` |
| `com.example.util.Texts` | `com/example/util/Texts.class` |
| `org.acme.data.RecordMapper` | `org/acme/data/RecordMapper.class` |
| `Hello` in the default package | `Hello.class` |

If a class declares `package com.example.util;`, its output path must reflect that package. At runtime, the classpath must point to the parent directory of `com`, not directly to `com/example/util`.

For example, given:

```text
out/com/example/util/Texts.class
```

The correct classpath is `out`, and the fully qualified class name is `com.example.util.Texts`:

```sh
java -cp out com.example.util.Texts
```

If the classpath mistakenly points to `out/com/example`, the JVM will look in the wrong path and typically throw `ClassNotFoundException` or `NoClassDefFoundError`, depending on how the class is requested to be loaded.

## 6. What Does a Class File Contain?

A class file is a binary format defined by the Java Virtual Machine Specification. Its structure consists of the following main sections:

1. **Magic number:** the first four bytes have the hex value `CAFEBABE`, used to identify the class file format.
2. **Minor and major version:** indicates the class file format version and certain special version states.
3. **Constant pool:** a table of constants containing strings, class names, method names, type descriptors, field/method references, and other required values.
4. **Access flags:** access modifiers and property flags of the class.
5. **This class and super class:** the current class and its direct superclass.
6. **Interfaces:** the interfaces implemented by the class.
7. **Fields:** information about the class's fields.
8. **Methods:** information about methods, constructors, and their bytecode.
9. **Attributes:** additional metadata, such as source file information, local variable tables, annotations, generic signatures, stack maps, and other attributes.

High-level diagram:

```text
Class file
├── Magic number
├── Minor / major version
├── Constant pool
├── Access flags
├── This class / Super class
├── Interfaces
├── Fields
├── Methods
│   └── Code attributes (bytecode)
└── Other attributes
```

Not every method has a `Code` section: `abstract` or `native` methods do not have a regular bytecode body in the class file. Some generic type information is stored as signature metadata; generic type parameters are generally erased during type erasure before runtime.

Class files are not plain text that can be edited with a regular text editor. Modify the source code and recompile, or use specialized tools when you need to analyze bytecode.

## 7. Inspecting Class Files with javap

The JDK provides the `javap` tool to inspect the structure of compiled classes. For example:

```sh
javap -classpath out com.example.App
```

This command displays the members exposed by the class, such as constructors and methods.

To view detailed class file information:

```sh
javap -verbose -classpath out com.example.App
```

You can also inspect method bytecode:

```sh
javap -c -classpath out com.example.App
```

Some useful options:

| Option | Description |
|---|---|
| `-c` | Disassembles and displays bytecode in methods |
| `-p` | Shows private classes and members as well |
| `-s` | Prints internal type signatures |
| `-l` | Prints line number and local variable tables if available |
| `-verbose` | Prints detailed information such as constant pool, flags, version, and attributes |

For example, the beginning of `javap -verbose` output might contain:

```text
Classfile .../App.class
  Last modified ...; size ...
  SHA-256 checksum ...
  Compiled from "App.java"
public class com.example.App
  minor version: 0
  major version: 61
```

Timestamps, sizes, and checksums depend on the actual file. For Java 17, the class file major version is 61; for Java 21, it is 65. Do not confuse the class file major version number with the JDK version number printed by `java -version`.

## 8. javac Options That Affect Output

In addition to `-d`, several options directly affect the generated files or metadata inside class files:

| Option | Effect |
|---|---|
| `-d <dir>` | Specifies the directory for writing class files |
| `-s <dir>` | Specifies the directory for writing source files generated by annotation processors |
| `-h <dir>` | Specifies the directory for writing C header files for native methods |
| `--release <N>` | Targets language, bytecode, and platform APIs for Java release N |
| `-g` | Generates all debugging information |
| `-g:none` | Generates no debugging information |
| `-g:lines,vars,source` | Generates only specific kinds of debugging information |
| `-parameters` | Stores method parameter names in class files |
| `-encoding UTF-8` | Specifies the character encoding used when reading source files |
| `-proc:none` | Disables annotation processing |
| `-implicit:none` | Does not generate class files for implicitly compiled source files |

Example of separating class files and generated source files:

```sh
javac -d out -s generated-sources -parameters src/com/example/App.java
```

`-d` and `-s` serve different roles. `-d` receives class files; `-s` receives source code generated by annotation processors. When annotation processing is used, the compiler may need to compile the generated code in the same pass or in subsequent processing rounds.

If native methods are used and C headers need to be generated, the `-h` option can specify the header output directory. This is a separate output and does not replace class files.

## 9. Overwriting and Leftover Stale Class Files

When recompiling a class into the same output directory, `javac` can overwrite an existing class file with the same name. However, the compiler is not a tool that cleans the entire output directory.

For example, suppose `App.java` initially declares:

```java
public class App {
    static class OldHelper {
    }
}
```

After the first compilation, the output directory may contain:

```text
App.class
App$OldHelper.class
```

Later, the developer removes `OldHelper` from the source code and recompiles `App.java`. The old `App$OldHelper.class` file may still remain in the output directory because the compiler does not delete class files that are no longer generated in the current pass.

Stale files can cause confusion when packaging or running the program, especially if the classpath contains multiple output directories. Therefore, for a clean build, delete the output directory before recompiling.

macOS/Linux:

```sh
rm -rf out
mkdir -p out
javac -d out src/com/example/App.java
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force out
javac -d out src/com/example/App.java
```

Only delete build directories owned by the project after verifying the exact path. Never run broad delete commands on your working directory or directories containing source data.

Gradle and Maven typically provide a `clean` task to remove managed build outputs before recompiling:

```sh
./gradlew clean compileJava
mvn clean compile
```

On Windows, the Gradle Wrapper can be invoked with `gradlew.bat clean compileJava`.

## 10. Distinguishing Class Files from Other Compiler Outputs

A single compilation can produce several different kinds of files:

- `.class` class files: compiled class definitions, typically located under `-d`.
- `.java` generated source files: annotation processor outputs, typically located under `-s`.
- `.h` native headers: outputs for JNI, which can be placed under `-h`.
- Resource files: typically managed by build tools or packaged separately; `javac` does not automatically copy all application resources into the class file directory.
- JARs: created by the `jar` tool or a build tool from class files and resources, not the default output of the `javac` command.

For example, if a project has `src/main/resources/application.properties`, a plain `javac` command will not automatically copy this file to `out`. A build tool needs a separate resource-processing step.

To package class files and resources, you can use Gradle/Maven or the `jar` command. A simple example once `out` exists:

```sh
jar --create --file app.jar -C out .
```

The command above packages the contents of the `out` directory into a JAR. It does not automatically add external dependencies or create launch configurations if they have not been declared.

## 11. Complete Practical Workflow

Suppose you have a small project:

```text
project/
└── src/
    └── com/
        └── example/
            ├── App.java
            └── Message.java
```

`Message.java`:

```java
package com.example;

public class Message {
    public String text() {
        return "Build output is ready";
    }
}
```

`App.java`:

```java
package com.example;

public class App {
    public static void main(String[] args) {
        Message message = new Message();
        System.out.println(message.text());
    }
}
```

Create the output directory, compile, and run on macOS/Linux:

```sh
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/com/example/Message.java src/com/example/App.java
java -cp out com.example.App
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
javac --release 17 -encoding UTF-8 -d out src/com/example/Message.java src/com/example/App.java
java -cp out com.example.App
```

Output:

```text
Build output is ready
```

Key output structure:

```text
out/
└── com/
    └── example/
        ├── App.class
        └── Message.class
```

You can inspect the compiled class:

```sh
javap -classpath out com.example.App
javap -verbose -classpath out com.example.App
```

This workflow demonstrates separating source code and class files, selecting a target platform version, and running a class with the appropriate classpath.

## 12. Common Errors When Writing Class Files

| Symptom | Common cause | Resolution |
|---|---|---|
| `javac` reports it cannot write a class file | Output directory does not exist, lacks write permissions, or path is invalid | Create the proper directory, check write permissions, and pass a valid path to `-d` |
| Cannot find `.class` after compiling | Looking in the wrong directory; compiler wrote next to source or under the output root | Check whether `-d` was used and search according to the package structure |
| `ClassNotFoundException` | Classpath does not point to the package root directory or a JAR is missing | Add the correct output root and dependencies to the classpath |
| `NoClassDefFoundError` | A required class is missing or cannot be loaded at runtime | Check runtime dependencies and classpath; identify the missing class in the error message |
| `UnsupportedClassVersionError` | The running JVM is older than the class file version | Use a newer JVM or compile with the appropriate `--release` |
| Old class files still appear after modifying/deleting a class | The compiler does not clean all old outputs | Run clean, delete the build directory, and recompile |
| Missing class file for a nested class | Only part of the output was copied or packaged | Keep all generated class files, including files with `$` in their names |
| Program is missing configuration files at runtime | Resources are not automatically copied by `javac` | Configure a resources task or include resources in the JAR |

When troubleshooting, identify which stage the error occurs in: the compiler cannot write the file, the JVM cannot find the class, or the JVM finds the class but cannot load/define it. These three situations have different causes and fixes.

## 13. Class File Checklist

- [ ] Selected the right source directory and working directory.
- [ ] Used `-d` to separate output from source code when needed.
- [ ] Confirmed the output root directory exists and is writable.
- [ ] Verified packages map correctly to the directory structure.
- [ ] Kept all class files for nested classes and dependent classes.
- [ ] Generated class files with a bytecode version compatible with the runtime.
- [ ] Distinguished class file outputs from generated sources, native headers, and resources.
- [ ] Cleaned old outputs when needed to ensure a clean build.
- [ ] Inspected class files with `javap` when diagnosing issues.
- [ ] Pointed the runtime classpath/module path to the right root directory and required libraries.

Class files are the direct product of the Java compilation step. Understanding how `javac` names, organizes, and writes these files helps you control your build pipeline, avoid interference from stale class files, and accurately diagnose issues across compilation, packaging, and execution.