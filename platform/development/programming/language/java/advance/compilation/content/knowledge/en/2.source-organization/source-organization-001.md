# Source Files, Type Declarations, and `public` Class Naming Rules in Java

A Java program is typically written in `.java` files. To organize source code and compile properly, you need to distinguish **source files**, **compilation units**, **top-level type declarations**, **nested types**, and **`.class` bytecode files**. The filename rule tied to a top-level `public` type is one of the rules most prone to causing `javac` errors.

## 1. What Does a `.java` File Contain?

An ordinary source file (`ordinary compilation unit`) has the general structure:

```java
// Comments (if any)
package com.example.compilation; // At most one package declaration, if any

import java.util.List;         // Imports, if any
import static java.lang.Math.max;

// Top-level type declarations
public class App {
    // Members and nested types inside App
}

class Helper {
    // Non-public top-level type
}
```

This is a **structural template**, not a standalone runnable program. Points to remember:

- The `package` declaration precedes `import` statements and type declarations (excluding comments and annotations applying to the package). If there is no `package`, the file belongs to the **unnamed package**.
- `import` statements follow `package` (if present) and precede all top-level type declarations. `import` lets you use simple names of types/members; it does not copy code into the file and creates no inheritance relationship.
- A compilation unit can contain **multiple top-level types**. For source files on a filesystem used by `javac`, at most **one top-level type can have the `public` modifier**, and the filename must match that type.
- Top-level types include `class`, `interface`, `enum`, `record` (Java 16+), and annotation interface `@interface`. A type declared **inside** another type is a nested type and follows different rules.
- One `.java` file can generate **multiple `.class` files**. The source filename and the number of bytecode files do not have a one-to-one relationship.

In Java, the term **top-level** describes a declaration placed directly inside the compilation unit, outside any other class/interface/enum/record. Putting `public` on a method or nested class does not make it a top-level type.

## 2. Filename Rule for Top-Level `public` Types

Under standard Java compilation with `javac`, if a file has a top-level `public` type named `X`, the source file must be named exactly `X.java`. This applies to all forms of top-level types:

| Declaration | Source filename |
| --- | --- |
| `public class App` | `App.java` |
| `public interface Service` | `Service.java` |
| `public enum Status` | `Status.java` |
| `public record Point(int x, int y)` | `Point.java` |
| `public @interface Audited` | `Audited.java` |

Valid example — file `Greeting.java`:

```java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Xin chao Java");
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 Greeting.java
java Greeting
```

Output:

```text
Xin chao Java
```

If you keep the same contents but save it as `Hello.java`, `javac Hello.java` reports an error along the lines of: `class Greeting is public, should be declared in a file named Greeting.java`. On case-sensitive filesystems, `Greeting.java` and `greeting.java` are two different names. Always use a name matching **the exact uppercase and lowercase characters**.

Two top-level `public` types in the same file are invalid under normal file organization:

```java
// Invalid if both are placed in Application.java
public class Application {
}

public interface Command {
}
```

Split them into `Application.java` and `Command.java`. You cannot fix the error by naming the file `ApplicationCommand.java`, because each `public` type still requires its own filename.

**What if there is no top-level `public` type?** Java allows the file to have a different name from the package-private types inside it. For example, `Utilities.java` can contain `class Parser` and `class Formatter` (neither `public`). However, placing each top-level type in a file of the same name remains the practical choice that makes it easier for IDEs, readers, and the compiler's source-file lookup mechanism.

## 3. Distinguishing Top-Level Modifiers from Modifiers Inside a Type

A normal top-level type can be declared `public` or with no access modifier (called **package-private**). Top-level types may not be declared `private`, `protected`, or `static`.

```java
// Invalid at top-level:
private class InternalOnly {
}
```

Note: `final`, `abstract`, `sealed`, and other applicable modifiers are separate from **access modifiers**; which modifiers can be used also depends on the type kind and inheritance relationships.

Valid example — file `Main.java` has two top-level types, but only one `public` type:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Ket qua: " + Calculator.twice(21));
    }
}

class Calculator {
    static int twice(int value) {
        return value * 2;
    }
}
```

Run commands:

```bash
javac Main.java
java Main
```

Output:

```text
Ket qua: 42
```

`javac` generates `Main.class` and `Calculator.class` even though the source only has `Main.java`. `Calculator` can be accessed by code in the same package under package-private rules; it does not become `public` just by sharing a file with `Main`.

In contrast, nested types are declared **inside** another type and can have appropriate access modifiers:

```java
// File Outer.java
public class Outer {
    public static class Nested {
        public String message() {
            return "nested";
        }
    }

    public static void main(String[] args) {
        System.out.println(new Outer.Nested().message());
    }
}
```

```bash
javac Outer.java
java Outer
```

Output:

```text
nested
```

There is no need to create `Nested.java` for `public static class Nested`: the required filename is only `Outer.java` because `Outer` is the top-level `public` type. Typically the compiler generates `Outer.class` and `Outer$Nested.class`. In Java code, refer to the nested type as `Outer.Nested`; the `$` character is part of the binary name representation of the nested type.

## 4. `package` and Source Paths: Language Rules vs. Tool Conventions

Suppose the project has:

```text
project/
└── src/
    └── com/
        └── example/
            └── compilation/
                └── App.java
```

Contents of `src/com/example/compilation/App.java`:

```java
package com.example.compilation;

public class App {
    public static void main(String[] args) {
        System.out.println("Goi tu package");
    }
}
```

The full name of the type is `com.example.compilation.App`. The `package` declaration determines the type's logical package; the directory structure `com/example/compilation/` is a **very important Java toolchain convention** for locating source code consistently. It is not a Java statement that creates a package by moving files on disk.

From the `project` directory, create the `out` directory first, then run:

```bash
mkdir out
javac -encoding UTF-8 -d out src/com/example/compilation/App.java
java -cp out com.example.compilation.App
```

Output:

```text
Goi tu package
```

After compilation, the generated file location is:

```text
out/
└── com/
    └── example/
        └── compilation/
            └── App.class
```

Here:

- `-d out` is the root directory holding output bytecode; `javac` creates subdirectories matching the package, but the `out` directory must already exist.
- `-cp out` passes **the classpath root** to the run command; do not pass the path to `App.class`.
- `java com.example.compilation.App` (with the right classpath) requires the fully qualified class name including the package. `java App` will not find the type just compiled in this package.
- Do not guess the package from the file path or vice versa; read the `package` statement and verify the source path and build configuration for consistency.

In projects using Maven/Gradle, production code is typically in `src/main/java/` and test code in `src/test/java/`; the build tool configures source paths, classpath, and output directory. The `src/com/example/.../` example above is intentionally a minimal standalone `javac` example.

## 5. Multiple Type Declarations in One File: Valid but with Trade-Offs

Example `Names.java` without a `public` type:

```java
class FirstName {
    static String value() {
        return "An";
    }
}

class LastName {
    static String value() {
        return "Nguyen";
    }
}
```

Compiling `javac Names.java` creates `FirstName.class` and `LastName.class`; it does **not** create `Names.class` because there is no type declaration named `Names`. Multiple non-`public` top-level types can exist in one file as long as type names do not collide within the same package.

However, when `App.java` only references `FirstName` and `Names.java` has not yet been compiled, `javac`'s automatic source lookup by type name may fail to discover a type inside a differently named file. You can explicitly specify both source files, configure the source path properly, or organize `FirstName.java` to hold `class FirstName`. In project codebases, **one primary top-level type per file of the same name** makes searching, navigation, and incremental compilation more predictable.

```bash
javac Names.java
```

Do not confuse **one primary top-level type per file** (a design convention) with **at most one top-level `public` type per file** (a standard compilation rule).

## 6. How Tools Locate Sources and Emit Bytecode

Three concepts commonly confused:

| Concept | What is it used for? | Example |
| --- | --- | --- |
| Source file | Provides declarations and Java code bodies | `src/com/example/compilation/App.java` |
| Fully qualified type name | Identifies a type by package and simple name | `com.example.compilation.App` |
| Output class file | Stores bytecode for the JVM and class loader | `out/com/example/compilation/App.class` |

With the `javac` compiler, `-sourcepath` (if used) specifies where to look for dependent source files; `-classpath` / `-cp` specifies where to look for already-compiled classes and libraries. When compiling a directly specified set of source files, `javac` can compile the types those files declare. How the compiler searches for sources depends on configured paths, so **matching the filename to the top-level type name** is an especially useful organizational rule.

`.class` files do not correspond one-to-one with `.java` files: extra top-level types, nested types, anonymous classes, or compiler-generated class constructs can produce multiple `.class` files. Distinguish **source filename** errors at compile time from **classpath/fully-qualified-name** errors at runtime.

## 7. Source Files with Special Roles

In addition to ordinary compilation units, the Java ecosystem has two important conventional filenames:

- `package-info.java`: commonly used for Javadoc and package-level annotations. Can contain a `package` declaration (and package annotations); not the place to put `public class PackageInfo`.
- `module-info.java`: describes a named module in the Java Platform Module System, using `module`, `requires`, `exports`, ... syntax instead of an ordinary Java class declaration.

Example contents of `module-info.java`:

```java
module com.example.demo {
    exports com.example.demo.api;
}
```

This is **a module descriptor snippet**, which only compiles in a project containing the corresponding `com.example.demo.api` package; it is not a standalone program with `main`. These two special filenames do not replace the rule for naming ordinary source files after their top-level `public` type.

Java 11+ also supports running a simple single source file via `java Greeting.java` (source-file mode). This launch mode compiles the source code in memory and runs the appropriate class; it **does not change** the `public` type naming rule when organizing and compiling regular projects with `javac`. For instance, the commands `javac Greeting.java` followed by `java Greeting` in section 2 clearly illustrate the two phases of compilation and execution.

## 8. Common Errors and How to Handle Them

| Symptom | Typical cause | Fix |
| --- | --- | --- |
| `class X is public, should be declared in a file named X.java` | File does not match the top-level `public` type | Rename the file to `X.java`, or intentionally rename/redesign the type |
| File contains two top-level `public` types | Both types require separate filenames | Split into two properly named files |
| `modifier private/protected/static not allowed here` | Applied a member/nested-type modifier to a top-level type | Use `public` or package-private at top level; or make the type genuinely nested |
| `class, interface, enum, or record expected` near `import` | Placed `import` after a type declaration or malformed compilation unit structure | Move all `import` statements before top-level types |
| `duplicate class: p.X` | Multiple declarations with the same fully qualified name in one compilation run | Check duplicate packages and type names across files |
| `Could not find or load main class ...` | Wrong classpath or passed simple name instead of fully qualified name | Verify `-d`/`-cp`, package, and class name containing `main` |

An error like `cannot find symbol` is **not necessarily** caused by a missing `import`: check the type name, package, compiled source files, source path, and classpath in order. `import com.example.*` only imports types directly inside that package; it does not automatically import types inside subpackages.

## 9. Self-Verification Practice

**Exercise 1 — predict output files.** File `Example.java` contains `public class Example` and `class Support`, both in the unnamed package. When `javac Example.java` succeeds, at minimum these types generate `Example.class` and `Support.class`. This shows the number of declared types differs from the number of source files.

**Exercise 2 — classify valid vs. invalid.** Evaluate each case:

1. `Thing.java` contains `public interface Thing`: **valid**.
2. `Thing.java` contains `public record Thing(int n) {}`: **valid** in Java 17+.
3. `Thing.java` contains `public class Other {}`: **invalid** when compiled with `javac` because the names do not match.
4. `Toolset.java` contains `class Parser {}` and `class Printer {}`: **valid**, though separating files can improve maintainability.
5. `Outer.java` contains `public class Outer { public static class Inner {} }`: **valid**; `Inner` is a nested type.

**Exercise 3 — organize a package yourself.** Create `src/com/example/compilation/Runner.java` with `package com.example.compilation;`, a `public class Runner` containing `main`, and a package-private helper in the same file. Compile with `javac -d out` (after creating `out`), run with `java -cp out com.example.compilation.Runner`, and observe the `.class` files inside the package directory under `out`.

## 10. Checklist When Creating or Editing Java Files

- Distinguish **top-level** and **nested** types accurately before applying the filename rule.
- If there is a top-level `public` type, the filename must be **type name + `.java`**, matching case; at most one such type per file.
- Non-`public` top-level types have package-private scope; `private`, `protected`, and `static` are not valid top-level modifiers.
- Place `package`, then `import`, then type declarations in the exact order. Keep packages and source directory trees consistent with the build tool.
- Understand that the compiler can generate multiple `.class` files from one `.java` file; invoke programs using the right classpath and fully qualified class name when a package is present.
- As code grows, prefer placing each primary top-level type in a file of the same name so readers and tool source lookup remain predictable.

**Key takeaway:** The `X.java` filename rule applies directly to a **top-level `public X` type** in standard Java source organization. Package-private types and nested types have their own rules. Reading declaration positions accurately will explain most errors involving filenames, `package`, and `.class` files.