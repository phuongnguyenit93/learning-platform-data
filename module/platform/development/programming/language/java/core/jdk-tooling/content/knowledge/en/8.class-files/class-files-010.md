# Inspecting Class Files in Java

A class file is a binary artifact produced by the Java compiler, typically with a `.class` extension. It contains bytecode, information about the class, fields, methods, data types, references to other classes, and various attributes used by the JVM. When a program encounters version compatibility errors, linkage errors, or unexpected behavior, inspecting the class file helps determine what the compiler generated.

The primary tool in the JDK for reading the structure and disassembling a class file is `javap`. This tool displays metadata and bytecode in text form so developers can inspect compiled artifacts.

## 1. What is a class file?

Java source code in a `.java` file is compiled by `javac` into a class file. A class file contains bytecode in the standard JVM format, rather than native machine code for a specific CPU.

A class file may contain:

- Class name, superclass, and implemented interfaces.
- Access flags for the class, fields, and methods.
- Constant pool with constants, class names, method names, descriptors, and symbolic references.
- Bytecode for each method.
- Exception handler information.
- Annotations, generic signatures, inner classes, records, or module metadata.
- Debug attributes such as source line numbers and local variable names, if the compiler generated them.

The JVM loads the class file, verifies its format and bytecode, links the symbolic references, and executes the bytecode. The JVM can interpret bytecode or compile frequently executed code into machine code using the JIT compiler.

A class file does not necessarily contain all of the original source code. Comments, whitespace formatting, and local variable names may be absent if the compiler did not store debug information. Therefore, `javap` is a tool for inspecting structure and bytecode, not a tool for recovering exact source code.

## 2. Finding the class file to inspect

When compiling with the `-d` option, `javac` places class files into the output directory following the package structure.

For example:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── App.java
└── out/
    └── com/
        └── example/
            └── App.class
~~~

If a class is in package `com.example`, the fully qualified name of the class is `com.example.App`. When using `javap` with a classpath, pass this fully qualified name instead of a slash-separated package path.

Inspect the contents of the output directory with:

~~~powershell
Get-ChildItem -Recurse out
~~~

You can list the contents of a JAR with:

~~~powershell
jar --list --file app.jar
~~~

If the class is inside a JAR, `javap` can read it directly via the classpath; you do not necessarily have to extract the JAR first.

## 3. Basic javap syntax

General syntax:

~~~text
javap [options] class...
~~~

Example of inspecting a compiled class in the `out` directory:

~~~powershell
javap -classpath out com.example.App
~~~

`-classpath` (or `-cp`) specifies where `javap` looks for classes. If omitted, the tool uses the environment's default classpath.

The default output displays the class declaration and public members. For example, you can see the class name, superclass, constructors, and public methods. To view private members or bytecode, use the detailed options described in the following sections.

Important options:

| Option | Purpose |
|---|---|
| `-p` or `-private` | Displays all class members, including private ones |
| `-c` | Disassembles method bytecode |
| `-l` | Displays the line number table and local variable table if present |
| `-s` | Displays internal type signatures/descriptors |
| `-constants` | Displays constant values of constant fields |
| `-v` or `-verbose` | Displays detailed information such as the constant pool, flags, version, and attributes |
| `-classpath` or `-cp` | Specifies the classpath to search for classes |
| `--module-path` | Specifies the module path |
| `--module` | Selects the module containing the class to inspect |
| `--multi-release` | Selects the entry version in a multi-release JAR |

Multiple options can be combined in a single invocation, for example `javap -p -c -l -classpath out com.example.App`.

## 4. Practical example: compiling and inspecting a class

Create the file `src/com/example/App.java`:

~~~java
package com.example;

public class App {
    private static final int BONUS = 10;
    private final String label;

    public App(String label) {
        this.label = label;
    }

    public int measure() {
        return label.length() + BONUS;
    }

    public static void main(String[] args) {
        String label = args.length == 0 ? "Java" : String.join(" ", args);
        App app = new App(label);
        System.out.println("score=" + app.measure());
    }
}
~~~

Compile with JDK 17 or later, enabling full debug information:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 17 -g -d out src/com/example/App.java
~~~

Run the application:

~~~powershell
java -cp out com.example.App Java
~~~

Output:

~~~text
score=14
~~~

Now inspect the public declaration:

~~~powershell
javap -classpath out com.example.App
~~~

Display private members as well:

~~~powershell
javap -p -classpath out com.example.App
~~~

You will see the `BONUS` field, `label` field, constructor, `measure()` method, and `main(String[])` method. Without `-p`, private members such as `label` may not appear in the default declaration output.

## 5. Inspecting bytecode with javap -c

The `-c` option disassembles the bytecode of methods:

~~~powershell
javap -c -classpath out com.example.App
~~~

The output looks similar to:

~~~text
public int measure();
  Code:
     0: aload_0
     1: getfield      #...  // Field label:Ljava/lang/String;
     4: invokevirtual #...  // Method java/lang/String.length:()I
     7: bipush        10
     9: iadd
    10: ireturn
~~~

The constant pool indices in `#...` and offsets may vary across compiler versions or when source code changes. The snippet above illustrates the bytecode flow of the `measure()` method:

1. `aload_0` pushes the `this` reference onto the operand stack.
2. `getfield` reads the `label` field.
3. `invokevirtual` calls `String.length()`.
4. `bipush 10` pushes the constant 10 onto the stack.
5. `iadd` adds the two integer values.
6. `ireturn` returns the integer result to the caller.

Bytecode operates on the operand stack and local variable slots. Reading bytecode helps determine which instructions the compiler turned an expression into, which methods are called, and how control branches execute.

`javap -c` does not display the original source code. It displays JVM instructions in mnemonic form, which is sufficient to analyze execution flow but does not recover comments or original formatting.

## 6. Inspecting metadata with javap -verbose

`-verbose` (abbreviated `-v`) displays extensive internal details of the class file:

~~~powershell
javap -verbose -classpath out com.example.App
~~~

Some key sections:

- `Classfile`: path or location of the class file being read.
- `minor version` and `major version`: class file format version.
- `flags`: access flags such as public, final, super, or interface.
- `this_class` and `super_class`: current class and superclass.
- `interfaces`: list of interfaces implemented by the class.
- `fields` and `methods`: counts and descriptions of fields and methods.
- `Constant pool`: constants, class names, field/method names, descriptors, and symbolic references.
- `Code`: bytecode, stack/local limits, and exception table of a method.
- `Attributes`: additional metadata such as SourceFile, LineNumberTable, StackMapTable, or RuntimeVisibleAnnotations.

For example, to check the version, look for two lines similar to:

~~~text
minor version: 0
major version: 61
~~~

For a standard Java 17 class file, the major version is 61. If the class uses preview features, the minor version may be 65535; the corresponding runtime must be launched with the appropriate preview option.

The `Constant pool` is especially useful when inspecting method references, class names, descriptors, or constants used by bytecode. However, it is a binary structure normalized by the compiler; not every entry should be interpreted as a source code string.

## 7. Inspecting signatures, fields, and debug information

### 7.1. Internal descriptors with -s

The `-s` option displays internal descriptors for fields and methods. Descriptors use JVM notation to represent types:

| Notation | Java Type |
|---|---|
| `I` | int |
| `J` | long |
| `Z` | boolean |
| `V` | void |
| `Ljava/lang/String;` | java.lang.String |
| `[I` | int[] |
| `[Ljava/lang/String;` | String[] |

For example, the method `public int measure()` has descriptor `()I`: takes no parameters and returns int. The method `main(String[] args)` has descriptor `([Ljava/lang/String;)V`: takes a String array and returns void.

Run:

~~~powershell
javap -s -p -classpath out com.example.App
~~~

Descriptors are useful when debugging linkage errors, comparing binary APIs, or analyzing bytecode with generics and overloads.

### 7.2. Debug information with -l

The `-l` option displays the debug tables present in the class file:

~~~powershell
javap -l -classpath out com.example.App
~~~

Common tables:

- `LineNumberTable` maps bytecode offsets back to source lines.
- `LocalVariableTable` records local variable names, types, and scope ranges within a method.
- `LocalVariableTypeTable` can store generic type information for local variables.

This information depends on how the code was compiled. For example, `javac -g` requests full debug information; `javac -g:none` disables debug information. If a class was compiled without a local variable table, `javap -l` cannot infer the original variable names.

### 7.3. Constants with -constants

The `-constants` option displays the values of constant fields:

~~~powershell
javap -constants -p -classpath out com.example.App
~~~

It is useful when checking static final fields whose constant values are recorded by the compiler. Not every final field is a compile-time constant; values computed at runtime may not appear as a constant value attribute.

## 8. Inspecting classes inside a JAR

You can use a JAR directly as the classpath:

~~~powershell
javap -classpath app.jar -p -c com.example.App
~~~

If the JAR has multiple library dependencies, pass the appropriate classpath list. For example on Windows:

~~~powershell
javap -classpath "app.jar;lib/*" -verbose com.example.App
~~~

On Linux/macOS, the classpath separator is a colon:

~~~bash
javap -classpath "app.jar:lib/*" -verbose com.example.App
~~~

To verify whether the class is actually inside the archive, use:

~~~powershell
jar --list --file app.jar
~~~

`javap` reads classes by fully qualified name. If the package or class name does not match the path inside the JAR, the tool will not find the class.

For multi-release JARs, you can instruct `javap` to view the entry for a specific release using `--multi-release N`. This is useful when a single JAR contains different implementations under `META-INF/versions`.

## 9. Inspecting modules and module-info.class

For modular projects, the `module-info.class` class file stores the compiled module descriptor. You can use `javap -verbose` to read module attributes:

~~~powershell
javap -verbose mods/com.example.app/module-info.class
~~~

The verbose output can display the `Module` attribute, including the module name, required modules, exported or opened packages, and provider information if present.

To view the module description in a more readable form, use the `jar` tool:

~~~powershell
jar --describe-module --file app.jar
~~~

If modules are placed on the module path, `javap` also supports specifying the module path and the module to inspect. For example:

~~~powershell
javap --module-path mods --module com.example.app com.example.app.Main
~~~

Distinguish between the two tasks:

- `javap` inspects class files and class bytecode.
- `jar --describe-module` displays the module description from a modular JAR.

If the application encounters module resolution errors, you need to check both the module descriptor and the placement of modules on the module path.

## 10. Reading class file versions and resolving compatibility errors

The major version indicates the class file version that the JVM must support. Some common milestones:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

For example, if `javap -verbose` shows `major version: 61`, the class file was created in the Java 17 format. A Java 11 runtime only supports up to major version 55, so it cannot load this class file.

A common error is `UnsupportedClassVersionError`. How to resolve it:

1. Check the major version using `javap -verbose`.
2. Check the actual runtime using `java -version`.
3. If an older runtime must be supported, recompile with `javac --release N` where N is the target release.
4. Check library dependencies; a dependency may have been compiled for a newer Java version than the application.
5. Run tests on the actual target runtime.

`--release` helps restrict the source language, class file target, and Java Platform APIs when compiling with a newer JDK. Checking the major version alone is not enough to prove application compatibility, because the class file may call APIs or depend on libraries that do not exist on the older runtime.

## 11. Class file structure and common attributes

A class file has a binary structure defined by the JVM Specification. At a high level, the structure consists of:

1. Magic number: the first four bytes with hexadecimal value `CAFEBABE`.
2. Minor and major version: the class file version.
3. Constant pool: constants and symbolic references.
4. Access flags, this class, superclass, and list of interfaces.
5. Field table and method table.
6. Attribute tables at the class, field, method, or code level.

Some attributes commonly seen in verbose output:

| Attribute | Meaning |
|---|---|
| `SourceFile` | Source file name recorded by the compiler |
| `LineNumberTable` | Maps bytecode offsets to line numbers |
| `LocalVariableTable` | Local variable information when debug data is present |
| `StackMapTable` | Data used for bytecode verification |
| `Signature` | Generic signature of a class, field, or method |
| `RuntimeVisibleAnnotations` | Annotations readable at runtime |
| `BootstrapMethods` | Bootstrap methods for invokedynamic or dynamic constants |
| `NestHost` and `NestMembers` | Nest-based access control information |
| `Record` | Metadata of a record class |
| `PermittedSubclasses` | List of permitted subclasses of a sealed class |
| `Module` | Module descriptor metadata |

Not every class file has every attribute. Their presence depends on the Java features used, the compiler, and the compilation options.

## 12. Common errors when inspecting class files

| Symptom | Common cause | Resolution |
|---|---|---|
| `Error: class not found` | Incorrect classpath or fully qualified class name | Check directory/JAR and package; use the correct `-classpath` |
| `javap` only shows public methods | Private member display mode is not enabled | Use `-p` or `-private` |
| Bytecode is not shown | Only the default command was used | Add `-c` |
| Local variable names are missing | Class was not compiled with local variable debug information | Recompile with `-g` and view with `-l` |
| Source line numbers are missing | Missing LineNumberTable or inspecting an artifact stripped of debug info | Recompile with appropriate debug info |
| `UnsupportedClassVersionError` | Runtime does not support the class's major version | Check `major version` and compile with an appropriate `--release` or upgrade the runtime |
| Class not found in JAR | Incorrect class name or the archive does not contain that package | Use `jar --list` to check entries |
| Verbose output is too long | Using `-v` on a large class or many dependencies | Use narrower options such as `-c`, `-s`, `-l`, or inspect a specific class |
| Module descriptor is hard to read | Viewing raw attributes or wrong module path | Use `jar --describe-module` and inspect `module-info.class` |

## 13. Class file inspection workflow for debugging or review

When verifying an artifact, follow this order:

1. Identify the exact JAR file or output directory that the application actually uses.
2. Use `jar --list` if the class is inside an archive.
3. Use `javap -classpath ...` to confirm the class and public API.
4. Use `javap -p` if you need to inspect private fields or methods.
5. Use `javap -c` to read the bytecode of relevant methods.
6. Use `javap -verbose` to view version, constant pool, flags, and attributes.
7. Use `javap -s` or `-l` when you need descriptors or debug mappings.
8. Cross-check the major version against the runtime and inspect dependencies.
9. Run tests on the exact runtime, module path, and classpath of the deployment environment.

You do not need to start with verbose output for every issue. Choose options based on the question: for API issues, check signatures and the constant pool; for execution flow issues, check bytecode; for compatibility issues, check the major version; for debugging issues, check attributes.

## 14. Checklist before confirming a class file

- [ ] Inspecting the exact artifact used by the application.
- [ ] Confirmed class name, package, and classpath/module path.
- [ ] Inspected class and member declarations with `javap`.
- [ ] Used `-c` if bytecode verification is needed.
- [ ] Used `-verbose` to check major/minor version when needed.
- [ ] Checked debug attributes if the debugger needs line numbers or variable names.
- [ ] Checked the module descriptor if the application uses JPMS.
- [ ] Cross-checked the class file version against the target runtime.
- [ ] Checked dependencies and tested on a compatible environment.

`javap` is the first tool to use when you need to look inside a compiled class file. Combine `-c` to view bytecode, `-verbose` to view structure and version, `-p` to view all members, and `-l`/`-s` to inspect debug data or descriptors. Reading the right type of information helps find bugs faster and verify artifacts before release.
