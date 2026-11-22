# The javap Command in Java

## 1. What is javap?

`javap` is a command-line tool included with the JDK, used to read and display information from Java class (`.class`) files. It is often called a **disassembler** because it can present the bytecode instructions that the compiler wrote into the class file.

A class file contains more information than just method bodies: class name, superclass, interfaces, modifiers, fields, methods, descriptors, the constant pool, and attributes. `javap` lets you choose the level of detail to view the parts you need when learning Java, debugging, or investigating compatibility issues.

Common use cases:

- Viewing which constructors, fields, and methods a class has.
- Checking modifiers such as `public`, `private`, `static`, `final`, and `abstract`.
- Reading the bytecode of a method using the `-c` option.
- Viewing internal descriptors of fields and methods using `-s`.
- Inspecting the constant pool, class-file version, and metadata using `-v`.
- Checking line number and local variable information using `-l`.
- Viewing static final constants using `-constants`.
- Checking which directory, JAR, or module a class is loaded from.

`javap` is a class file analysis tool. It does not run programs, does not compile source code, and is not a decompiler that can restore the original Java source code verbatim.

## 2. What kinds of input does javap work with?

Typically, you pass the fully qualified class name to `javap`. This name consists of the package and the class name, for example `com.example.Calculator`.

The tool can locate classes from:

- The default classpath of the Java environment.
- Directories containing class files.
- JAR or ZIP archives containing class files.
- Modules on the module path or runtime modules, when specifying the appropriate module options.
- A direct path to a class file in supported cases.

For example, if the class is located at:

```text
project/
  out/
    com/
      example/
        Calculator.class
```

then the class name is `com.example.Calculator`. The directory that needs to be placed on the classpath is `out`, not `out/com/example`.

## 3. General Syntax

Basic syntax:

```bash
javap [options] class...
```

Where:

- `javap` is the class file analysis command.
- `options` are the options controlling the scope and level of detail of the output.
- `class...` is one or more class names to inspect.

Examples:

```bash
javap java.lang.String
javap -p com.example.Calculator
javap -classpath out -c com.example.Calculator
```

If no options are specified, `javap` mainly displays the class signature, constructors, fields, and methods at the default access scope. It does not display method bytecode.

You can view the list of options supported by the installed JDK:

```bash
javap -help
```

The help output is the authoritative source for a specific JDK version, as options may be added or changed between versions.

## 4. Configuring the classpath when using javap

If the class is outside the default classpath, specify its location using `-classpath`, `--class-path`, or the short form `-cp`.

Example:

```bash
javap -classpath out com.example.Calculator
```

The following forms are equivalent:

```bash
javap -cp out com.example.Calculator
javap --class-path out com.example.Calculator
```

If the class is inside a JAR:

```bash
javap -classpath app.jar com.example.Calculator
```

If you need to search for classes in multiple locations, pass a list of paths with the OS-dependent separator:

- Windows: semicolon (`;`).
- Linux and macOS: colon (`:`).

Example on Windows:

```powershell
javap -classpath "out;lib\utilities.jar" com.example.Calculator
```

Example on Linux/macOS:

```bash
javap -classpath "out:lib/utilities.jar" com.example.Calculator
```

The class name should be passed in package form, without appending the `.class` extension when using a class name on the classpath. If passing a direct class file path, follow the path syntax supported by your `javap` version.

A common mistake is specifying the wrong classpath root directory. For the class `com.example.Calculator` located in `out/com/example/Calculator.class`, the classpath must be `out`.

## 5. Important javap Options

The following options are the most useful when working with class files:

| Option | Function |
|---|---|
| `-help` or `--help` | Displays usage help |
| `-version` | Displays the tool version |
| `-public` | Shows only public classes and members |
| `-protected` | Shows public and protected members |
| `-package` | Shows package-private and higher members; this is the default |
| `-p` or `-private` | Shows all members, including private ones |
| `-c` | Shows bytecode of methods and constructors |
| `-s` | Shows internal type signatures (descriptors) |
| `-l` | Shows line number and local variable information if the class file contains metadata |
| `-v` or `-verbose` | Shows detailed class file information |
| `-constants` | Shows static final constants |
| `-sysinfo` | Shows system information about the class, such as path, size, date, and SHA-256 on supported JDKs |
| `-classpath`, `--class-path`, `-cp` | Specifies where to find classes |
| `--module-path` | Specifies the module path |
| `--module` | Specifies the module to analyze |
| `--system` | Specifies the location containing system modules |
| `--multi-release` | Selects the entry version in a multi-release JAR to analyze |

Multiple options can be combined, for example `-p -c -s` to view private members, bytecode, and descriptors together.

### 5.1. Showing private members with -p

By default, private members are not displayed. Use:

```bash
javap -p -classpath out com.example.Calculator
```

The `-p` option is equivalent to `-private`. It is useful when you need to inspect internal fields or methods of a compiled class.

Note: seeing a private member's name in a class file does not mean an application is allowed to access that member from normal Java code. Language and JVM access rules still apply during linking and execution.

### 5.2. Showing bytecode with -c

`-c` instructs `javap` to disassemble the code section of methods:

```bash
javap -c -classpath out com.example.Calculator
```

The output shows bytecode instructions and their corresponding offsets within the method. This is the most commonly used option when you want to understand what instructions the compiler translated a Java expression into.

### 5.3. Showing descriptors with -s

`-s` prints the internal descriptors of fields and methods:

```bash
javap -s -classpath out com.example.Calculator
```

Descriptors are useful when analyzing overloads, generic bridge methods, reflection, or bytecode tools. For example, the descriptor `(II)I` means a method takes two int parameters and returns an int.

### 5.4. Showing detailed information with -v

`-v` (or `-verbose`) displays more class-file information, including the constant pool and attributes:

```bash
javap -v -classpath out com.example.Calculator
```

Use this option when you need to inspect the class-file version, access flags, annotation metadata, method descriptors, the Code attribute, or StackMapTable. The output is significantly longer than in the default mode.

### 5.5. Showing debug information with -l

`-l` displays debug tables such as `LineNumberTable` and `LocalVariableTable` if they were written into the class file:

```bash
javap -l -classpath out com.example.Calculator
```

If the class was compiled without the corresponding debug information, `javap` cannot reconstruct local variable names or original source line mappings on its own.

### 5.6. Showing constants with -constants

`-constants` displays the values of eligible constant fields, typically `static final` fields that have compile-time constant values:

```bash
javap -p -constants -classpath out com.example.Calculator
```

Combine `-p` to also display private constant fields in the example. This option is useful when checking constants stored in the class file. It is not a tool for reading runtime values of arbitrary fields.

## 6. Hands-on Example: Creating a Class and Using javap

The following example uses Java 17 or later. Create the file `src/com/example/Calculator.java`:

```java
package com.example;

public class Calculator {
    private static final int BASE = 10;

    public static int add(int left, int right) {
        return left + right;
    }

    private static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) {
        int total = add(2, 3);
        System.out.println("total=" + total);
    }
}
```

Create the output directory. On Linux/macOS:

```bash
mkdir -p out
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
```

Compile from the project root directory:

```bash
javac --release 17 -g -d out src/com/example/Calculator.java
```

Meaning:

- `--release 17` sets the target Java SE language level, bytecode, and API to Java 17.
- `-g` instructs the compiler to generate debug information.
- `-d out` places the class file into the `out` directory following the package structure.

Run the program:

```bash
java -cp out com.example.Calculator
```

Exact stdout:

```text
total=5
```

After compilation, the class file is located at `out/com/example/Calculator.class`.

## 7. Reading javap Output in Default Mode

Run:

```bash
javap -classpath out com.example.Calculator
```

Typical output:

```text
Compiled from "Calculator.java"
public class com.example.Calculator {
  public com.example.Calculator();
  public static int add(int, int);
  public static void main(java.lang.String[]);
}
```

Meaning:

- The first line shows the source file name recorded in the metadata.
- The class declaration line shows that the class is public.
- The default constructor is generated by the compiler because the class does not declare its own constructor.
- The `add` method takes two int parameters and returns an int.
- The `main` method takes a String array and returns void.
- The `BASE` field and `twice` method do not appear because they are private.

The default output shows the structure and signatures of members within the corresponding access scope. It does not show the statements inside methods.

## 8. Viewing Private Members and Bytecode

To view all members:

```bash
javap -p -classpath out com.example.Calculator
```

The output will additionally include the `BASE` field and `twice` method:

```text
private static final int BASE;
private static int twice(int);
```

To view bytecode:

```bash
javap -p -c -classpath out com.example.Calculator
```

The `add` method section looks like:

```text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
```

How to read it:

1. `iload_0` pushes the first parameter onto the operand stack.
2. `iload_1` pushes the second parameter onto the operand stack.
3. `iadd` pops two int values, adds them, and pushes the result onto the stack.
4. `ireturn` returns the int result to the caller of the method.

The offsets are bytecode positions within the method. The compiler may generate a different instruction sequence when the source code or compiler version changes.

## 9. Viewing Descriptors, Constant Pool, and Class-file Version

You can combine options to investigate further:

```bash
javap -p -s -classpath out com.example.Calculator
javap -p -constants -classpath out com.example.Calculator
javap -v -classpath out com.example.Calculator
```

### 9.1. Descriptors

For the `add(int, int)` method, the descriptor is:

```text
(II)I
```

Reading from left to right:

- The opening parenthesis starts the parameter list.
- The first `I` is the first int parameter.
- The next `I` is the second int parameter.
- The `I` after the closing parenthesis is the int return type.

Some common descriptors:

| Descriptor | Meaning |
|---|---|
| `V` | void |
| `Z` | boolean |
| `I` | int |
| `J` | long |
| `D` | double |
| `Ljava/lang/String;` | java.lang.String |
| `[I` | int array |
| `([Ljava/lang/String;)V` | Takes a String array and returns void |

### 9.2. Constant pool

In verbose output, the `Constant pool` section lists the constants and symbolic references used by the class.

You may encounter entries such as:

- `Utf8`: UTF-8 string used by the class file for names or metadata.
- `Class`: reference to a class or interface.
- `NameAndType`: combination of a name and a descriptor.
- `Fieldref`: reference to a field.
- `Methodref` and `InterfaceMethodref`: reference to a method.
- `String`: reference to a string literal.
- `MethodHandle`, `MethodType`, and `InvokeDynamic`: metadata related to dynamic invocation.

The constant pool helps the JVM and analysis tools resolve symbolic references in bytecode.

### 9.3. Class-file version

In the `javap -v` output, look for the lines:

```text
minor version: ...
major version: 61
```

For the example compiled with `--release 17`, the major version is 61. This is the class file format version corresponding to Java 17.

Some common major versions:

| Java | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

If the runtime is too old for the class-file version, the application may encounter an `UnsupportedClassVersionError` when loading the class.

## 10. Viewing Line Number and Local Variable Information

Because the example was compiled with `-g`, you can inspect debug information:

```bash
javap -l -classpath out com.example.Calculator
```

`LineNumberTable` maps bytecode offsets to line numbers in the source code. `LocalVariableTable` can store local variable names, types, and the offset ranges in which the variables are in scope.

If recompiled without debug metadata:

```bash
javac -g:none --release 17 -d out src/com/example/Calculator.java
javap -l -classpath out com.example.Calculator
```

the output may no longer contain complete debug tables. Parameter types in method signatures can still be displayed, but local variable names cannot be inferred from bytecode.

To retain parameter names for reflection, use the compiler option `-parameters`. This is different metadata from the debug information generated by `-g`.

## 11. Analyzing Classes Inside a JAR

`javap` can read classes directly from a JAR via the classpath. For example, after packaging the output directory:

```bash
jar --create --file app.jar --main-class com.example.Calculator -C out .
```

View the structure of a class inside the JAR:

```bash
javap -classpath app.jar com.example.Calculator
```

View the bytecode of its methods:

```bash
javap -classpath app.jar -c com.example.Calculator
```

If there are multiple JAR dependencies, add them to the classpath using the OS-specific separator. Make sure the classpath points to the right artifact version; if multiple JARs contain the same class name, the output may reflect the class found first in lookup order.

For multi-release JARs, you can specify the entry version to inspect using `--multi-release`. This is useful when a JAR contains alternative classes per Java version.

## 12. Analyzing Classes in Modules

For classes belonging to JDK modules or on the module path, `javap` provides dedicated module options.

For example, view the `java.lang.String` class in the `java.base` module:

```bash
javap --module java.base java.lang.String
```

For an application module on the module path:

```bash
javap --module-path mods --module com.example.app com.example.Main
```

Where:

- `--module-path mods` specifies the location containing the modules.
- `--module com.example.app` selects the module to analyze.
- `com.example.Main` is the class to inspect inside that module.

The `--system` option lets you specify the location containing system modules when you need to analyze a specific runtime image. Only use module options when the class actually belongs to a corresponding module; the regular classpath is still sufficient for non-modular applications.

## 13. How does javap differ from other Java tools?

| Tool | Role | Main Output |
|---|---|---|
| `javac` | Compiles Java source code | Class files containing bytecode |
| `java` | Launches the application | Executes the program on the JVM |
| `javap` | Reads and analyzes class files | Class signatures, descriptors, bytecode, and metadata |
| `jar` | Packages or lists JAR contents | JAR artifact |
| `jdeps` | Analyzes class and module dependencies | Dependency report |

It is important to distinguish `javap` from a decompiler:

- `javap` displays signatures, metadata, and bytecode instructions.
- A decompiler attempts to convert bytecode back into Java code close to the original source.
- No tool can fully recover comments, formatting, stripped variable names, or every original programmer decision from a class file alone.

If the goal is to understand what instructions the compiler turned an expression into, use `javap -c`. If you need to inspect class file structure, use `javap -v`. If you need to analyze dependencies of a large application, `jdeps` is a better fit.

## 14. Common Errors When Using javap

| Symptom | Common Cause | How to Fix |
|---|---|---|
| `Error: class not found` | Classpath is missing the root directory or JAR containing the class | Check `-classpath` and the full package name |
| Private fields or methods not shown | Using the default access level | Add `-p` or `-private` |
| Bytecode not shown | Disassemble option not used | Add `-c` |
| Descriptors not shown | Signature option not requested | Use `-s` |
| Verbose output too long | Using `-v` when only part of the information is needed | Switch to `-c`, `-s`, or `-l` |
| No local variable names | Class file does not contain `LocalVariableTable` | Compile with `-g` and check again |
| Wrong class version read | Classpath has multiple JAR versions or duplicate class names | Narrow down the classpath and identify the specific artifact |
| Cannot view class in module | Wrong module path or module name specified | Check `--module-path` and `--module` |
| Class not found in JAR | Wrong package used or JAR does not contain that class | Check JAR contents with `jar --list` |

Some quick diagnostic commands:

```bash
javap -help
javap -version
javap -classpath out -p com.example.Calculator
javap -classpath out -c com.example.Calculator
javap -classpath out -v com.example.Calculator
```

## 15. Workflow for Using javap at Work

When you need to analyze a specific class, you can follow this sequence:

1. Identify the class file or JAR artifact to inspect.
2. Determine the exact package and classpath path.
3. Run in default mode to view the signature and public/protected/package-private members.
4. Add `-p` if you need to inspect private members.
5. Add `-c` to view the bytecode of the method under investigation.
6. Add `-s` to view descriptors when analyzing overloads or signature compatibility.
7. Use `-v` when you need the constant pool, class-file version, flags, and attributes.
8. Use `-l` when you need bytecode-to-line mappings or local variables.
9. If the class comes from a JAR or module, verify the exact artifact and version.
10. Cross-reference the output with the source code, compiler configuration, and runtime in use.

Avoid starting with verbose output for every case. Choosing the smallest option that answers your question keeps the output readable and prevents missing important parts.

## 16. Summary

`javap` is a JDK tool for inspecting the contents of compiled class files. It helps developers see the structure and bytecode generated from Java source code.

Options to remember:

- `javap className` views the class signature and members at the default scope.
- `-p` also shows private members.
- `-c` shows bytecode of methods and constructors.
- `-s` shows internal descriptors.
- `-v` shows the constant pool, class-file version, and attributes.
- `-l` shows debug tables if the class file contains metadata.
- `-constants` shows values of eligible constant fields.
- `-classpath` or `-cp` helps locate classes in directories and JARs.
- `--module` and `--module-path` are used when analyzing classes belonging to modules.

Combining `javap` with `javac`, `java`, and `jar` helps trace the path from source code to class file and verify exactly what the compiler produced.
