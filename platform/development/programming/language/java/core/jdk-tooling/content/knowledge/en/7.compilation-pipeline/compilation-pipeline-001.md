# Source code in the Java compilation pipeline

Source code is the input to the Java compilation process. It is text containing package declarations, imports, classes, interfaces, enums, records, methods, and other language constructs. The `javac` compiler reads source files, checks syntax and types, resolves dependent types, and then generates bytecode in `.class` files.

Understanding source code structure and how the compiler locates source files helps you organize projects clearly, troubleshoot compilation errors faster, and know exactly what needs to be included in a build.

## 1. Where does source code fit in the compilation pipeline?

A simplified Java pipeline:

~~~text
.java file
   |
   v
Read characters and parse syntax
   |
   v
Resolve names and check types
   |
   v
Process annotations (if configured)
   |
   v
Generate bytecode
   |
   v
.class file
   |
   v
JVM loads and executes
~~~

At a high level, the compiler performs the following tasks:

1. **Read and parse:** decode the source file, recognize package/import/declarations, and build the syntax structure.
2. **Enter symbols and resolve types:** locate classes, interfaces, methods, and fields, and check whether referenced names exist, are accessible, and are used with the correct types.
3. **Process annotations:** if an annotation processor is configured or enabled, the compiler invokes the processor; the processor may generate additional source files or resources for subsequent rounds.
4. **Semantic and flow analysis:** check type rules, access control, definite assignment, and language constraints.
5. **Generate class files:** produce bytecode and metadata in `.class` files.

This is a conceptual description to understand the role of source code. Internal compiler details may vary across versions and are not APIs that applications should depend on.

## 2. Java source files and compilation units

A Java source file typically has the `.java` extension. A compilation unit may consist of:

- A `package` declaration (optional).
- `import` declarations (optional).
- One or more top-level type declarations such as a class, interface, enum, record, or annotation interface.

Example:

~~~java
package com.example;

import java.time.LocalDate;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("Java", "JDK");
        System.out.println(LocalDate.now());
        System.out.println(names);
    }
}
~~~

In the example:

- `package com.example;` places the `Main` type in the `com.example` package.
- `import` allows using the simple names `LocalDate` and `List` instead of their fully qualified names.
- `public class Main` declares a public class.
- `main` is the application entry point in the traditional launch model.

Source files do not contain bytecode. After compilation, the compiler generates the corresponding class file, such as `com/example/Main.class` when using an output directory with package structure.

### 2.1. File names and type names

By common convention with `javac`, a top-level type declared as public resides in a file whose name matches the type name:

| Declaration | File name |
|---|---|
| `public class Main` | `Main.java` |
| `public interface Repository` | `Repository.java` |
| `public record User` | `User.java` |
| `public enum Status` | `Status.java` |

A file may contain other non-public top-level types, but it is best to keep each public type in its own file so the structure is easy to navigate and maintain.

File names are case-sensitive on many systems. `Main.java` and `main.java` should not be treated as interchangeable.

### 2.2. Packages and directory structure

Packages group related types and prevent name conflicts. For the `com.example.service` package, the directory structure is typically:

~~~text
src/
└── com/
    └── example/
        └── service/
            └── UserService.java
~~~

Top of `UserService.java`:

~~~java
package com.example.service;

public class UserService {
    public String name() {
        return "User service";
    }
}
~~~

During compilation, `javac` uses directory paths to locate source files and organize class files by package. Subpackages are separate packages; `import com.example.*` does not automatically import types in `com.example.service`.

If there is no `package` declaration, the type belongs to the unnamed package. This can be used for very small examples, but real projects should place types in named packages to manage dependencies and avoid conflicts.

### 2.3. Imports

Common import forms:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.*;
import static java.lang.Math.PI;
import static java.lang.Math.max;
~~~

- Importing a specific type lets you use its simple name.
- Package import with `*` applies to types directly in that package, excluding subpackages.
- Static import allows referencing static members without writing the type name at each usage.
- Imports only help the compiler resolve names; they do not bundle libraries into the application or make a dependency available at runtime.

Types in `java.lang` such as `String`, `System`, and `Math` are imported implicitly, so `import java.lang.*` is not required.

## 3. Multiple source files in a single compilation

In real applications, a class often uses types declared in other files. Example structure:

~~~text
project/
└── src/
    └── com/
        └── example/
            ├── Greeting.java
            └── Main.java
~~~

`Greeting.java`:

~~~java
package com.example;

public class Greeting {
    public String message() {
        return "Hello from source code";
    }
}
~~~

`Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        Greeting greeting = new Greeting();
        System.out.println(greeting.message());
    }
}
~~~

Compile both files:

~~~bash
javac -encoding UTF-8 -d out src/com/example/Greeting.java src/com/example/Main.java
~~~

Run:

~~~bash
java -cp out com.example.Main
~~~

Output:

~~~text
Hello from source code
~~~

`javac` compiles the source files in the same pass and automatically resolves references between them. The order of file names on the command line does not determine dependency order.

## 4. Source path and class path

The compiler needs to find the types referenced by the source code. They can come from other source files or from compiled class files/JARs.

| Path | Used to find |
|---|---|
| `--source-path` or `-sourcepath` | Additional `.java` source files |
| `--class-path`, `-classpath`, or `-cp` | Class files and JAR libraries |
| `--module-path` | Compiled modules |
| `--module-source-path` | Source files of one or more modules |

For example, if `Main.java` references `Greeting` but you only pass `Main.java` to the compiler, set the source root:

~~~bash
javac -encoding UTF-8 -sourcepath src -d out src/com/example/Main.java
~~~

The compiler searches for `Greeting.java` following the package path under `src` and can compile it as a source dependency.

If `Greeting` has already been compiled into class files in the `lib-classes` directory, use the class path:

~~~bash
javac -cp lib-classes -d out src/com/example/Main.java
~~~

When there are multiple JARs or directories, separate paths using the OS-specific separator:

~~~bash
# macOS / Linux
javac -cp "lib/a.jar:lib/b.jar" -d out src/com/example/Main.java
~~~

~~~powershell
# Windows PowerShell
javac -cp "lib/a.jar;lib/b.jar" -d out src/com/example/Main.java
~~~

Do not confuse source path with class path: one locates source code; the other locates compiled types and libraries. If no source path is specified in non-modular mode, the compiler may search for source files on the class path according to default rules, but explicit configuration is usually clearer and more reliable.

## 5. Source code encoding

Java files are text. The compiler must decode the bytes in a file into characters before parsing. If an editor saves in UTF-8 but the compiler reads using a different default charset, Vietnamese characters or non-ASCII characters may become corrupted.

You should standardize on UTF-8 across the project and declare it explicitly when compiling:

~~~bash
javac -encoding UTF-8 -d out src/com/example/Main.java
~~~

An example with Vietnamese text:

~~~java
public class VietnameseText {
    public static void main(String[] args) {
        System.out.println("Xin chào Java");
    }
}
~~~

Save the file as UTF-8 and compile:

~~~bash
javac -encoding UTF-8 VietnameseText.java
java VietnameseText
~~~

Output:

~~~text
Xin chào Java
~~~

The `-encoding` option controls how `javac` reads source files. It does not determine the encoding of output data that the program writes to the terminal; that depends on how the application outputs data and the console environment.

## 6. Source directory and output directory

You should separate source code from generated class files:

~~~text
project/
├── src/
│   └── com/example/
│       ├── Greeting.java
│       └── Main.java
└── out/
    └── com/example/
        ├── Greeting.class
        └── Main.class
~~~

Use `-d` to specify the output directory:

~~~bash
javac -encoding UTF-8 -d out src/com/example/Greeting.java src/com/example/Main.java
~~~

If `-d` is omitted, `javac` typically writes class files next to the source files. This can mix generated files into the source directory, making project management, packaging, and cleaning builds harder.

Other useful options:

| Option | Role |
|---|---|
| `-d directory` | Output directory for class files |
| `-s directory` | Directory for source files generated by annotation processors |
| `-encoding UTF-8` | Charset for reading source files |
| `-g` | Generate debug information |
| `-Xlint:all` | Enable additional warnings |
| `-Werror` | Stop compilation if warnings occur |

## 7. Module source code

In projects using the Java Platform Module System, a module may contain a `module-info.java` file to declare the module name, required modules, and exported packages.

Example:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/Main.java
~~~

`module-info.java`:

~~~java
module com.example.app {
    exports com.example;
}
~~~

`Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from module");
    }
}
~~~

Compile the module:

~~~bash
javac --module-source-path src -d out -m com.example.app
~~~

Run the module:

~~~bash
java --module-path out -m com.example.app/com.example.Main
~~~

When compiling a module, the compiler considers the module declaration and dependent modules on the module path. When compiling multiple modules at once, the source tree structure must follow the module source path. Do not place `module-info.java` inside a package like a regular Java class.

## 8. Annotations and generated source code

Annotations can provide metadata to the compiler, frameworks, or build tools. Example:

~~~java
@Override
public String toString() {
    return "Example";
}
~~~

Some libraries use annotation processors to generate source code or metadata during compilation. A processor can read annotations and the program model, then create new source files for the compiler to process in the next round.

Common options:

- `-processor`: specify annotation processors.
- `--processor-path`: where to find processors on the class path.
- `--processor-module-path`: where to find processors on the module path.
- `-proc:none`: disable annotation processing.
- `-s generated-sources`: directory where processor-generated source files are placed.

Generated source files are part of the compilation pipeline, but should be distinguished from developer-maintained source code. You should not edit generated files directly if the next build will regenerate them.

## 9. Diagnosing errors from source code

Source code errors are typically detected before class files are generated.

| Error type | Example | Meaning |
|---|---|---|
| Syntax error | Missing `;` or `}` | Source structure is syntactically invalid |
| Symbol not found | Calling an undeclared or unimported class/method | The compiler cannot resolve the name |
| Type mismatch | Assigning a `String` to an `int` variable | Incompatible data types |
| Insufficient access | Using a `private` member from another class | Access control rule violation |
| Package/path error | Declared package and source tree location do not match | The compiler cannot find the expected source or type name |
| Encoding error | Corrupted characters when reading source | File charset and compiler charset do not match |

Type error example:

~~~java
public class TypeError {
    public static void main(String[] args) {
        int count = "three";
    }
}
~~~

The compiler reports incompatible types because a string cannot be directly assigned to an `int` variable. This differs from a runtime error: the program has not produced a valid class file for that compilation.

You can enable additional warnings:

~~~bash
javac -Xlint:all -encoding UTF-8 -d out src/com/example/Main.java
~~~

If you want warnings to also fail the build, add `-Werror` after resolving existing warnings:

~~~bash
javac -Xlint:all -Werror -encoding UTF-8 -d out src/com/example/Main.java
~~~

## 10. Practical workflow

For a project containing `Main.java` and `Greeting.java` in the `com.example` package, you can follow this order:

1. **Organize the source tree:** set `src` as the source root with subdirectories matching the package.
2. **Check file names:** ensure each public type matches the name of the file containing it.
3. **Check package/imports:** the package declaration matches the intended package; imports point to accessible types.
4. **Standardize encoding:** save source files as UTF-8.
5. **Compile:** use `javac -encoding UTF-8 -Xlint:all -d out ...`.
6. **Read diagnostics:** fix syntax, symbol, type, and access control errors.
7. **Verify output:** confirm class files are generated following the package structure in `out`.
8. **Test run:** use `java -cp out com.example.Main` to verify the application launches.

As a project grows, let Maven, Gradle, or an IDE manage source sets and compilation tasks, while still understanding the `source-path`, `class-path`, module path, and output directory concepts used by the compiler.

## 11. Takeaways

Source code is the Java-language description of a program; the compiler reads compilation units, resolves dependent types, checks syntax/semantics, and produces class files. Packages and imports govern how types are named and referenced. Directory structure should reflect packages/modules. Encoding, source path, class path, and output directory determine where the compiler reads inputs and writes outputs.

When encountering build errors, check source files, packages, imports, encoding, and type lookup paths before investigating bytecode or the JVM runtime.

References: [The javac Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), sections *Source Files*, *Arrangement of Source Code*, *Configuring a Compilation*, and *Annotation Processing*; [Java Language Specification, Chapter 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html).