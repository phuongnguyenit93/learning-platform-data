# Declaring `package` and Matching Directory Structure in Java

> **Java core — language-basics / Packages and imports**  
> **Requirements:** JDK 17+, no external libraries.  
> **Goals:** Declare `package` in the right place in a Java file; organize `.java` files into matching directories; compile with `javac -d`, run using the fully qualified class name and classpath; distinguish packages from directories, imports, and access rights.

## 1. `package` defines a class's namespace

A *package* groups related Java types and creates a namespace, helping prevent name collisions between classes in an application. For example:

~~~java
package vn.learn.demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

Here the fully qualified class name (*fully qualified name*, FQN) is `vn.learn.demo.Main`, not just `Main`. The declaration `package vn.learn.demo;` separates parts with dots and **ends with a semicolon**.

Each `.java` file can have at most **one** `package` declaration. Without this declaration, top-level types in the file belong to the *unnamed package* (often called the *default package*). This is convenient for very small experiments, but is discouraged for multi-file programs or code that needs to be reused from named packages.

**Package names are case-sensitive.** By convention, package names are lowercase, such as `vn.learn.demo` or reversed domain names like `com.example.app`. Java keywords cannot be used as any part of a package name.

## 2. Order of `package`, `import`, and type declarations

In a Java file with a package, the typical layout is as follows:

~~~java
// Comments and whitespace can be written here.
package vn.learn.demo;

import java.util.Arrays;
import vn.learn.demo.tools.Counter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Arrays.toString(new int[] {1, 2}));
    }
}
~~~

Rules to remember:

1. `package ...;` is the compilation unit's package declaration, placed **before all `import` declarations and top-level types**; comments/whitespace may appear before it.
2. If `import` statements are needed, they go **after `package`** and **before class/interface/enum/record declarations**.
3. A file may contain matching top-level types, but when there is a `public class Main` in standard organization, save the file as `Main.java`.
4. `import` does not change the package containing `Main`; it only lets you use the short name of an imported type or static member.
5. `java.lang` is imported automatically for familiar types such as `String` and `System`.

**Incorrect order:**

~~~java
// WRONG — cannot place import before package declaration:
// import java.util.List;
// package vn.learn.demo;
~~~

The name in `package` is not a quoted string literal. Writing `package "vn.learn.demo";` will not compile.

## 3. Matching source directory structure

The standard convention is to replace dots in the package name with directory separators. For `vn.learn.demo`, `Main.java` should be placed at:

`src/vn/learn/demo/Main.java`

Example source structure and compilation output:

~~~text
project/
├── src/
│   └── vn/
│       └── learn/
│           └── demo/
│               ├── Main.java
│               ├── Greeter.java
│               └── tools/
│                   └── Counter.java
└── out/                      (directory containing .class files after compilation)
~~~

| Declaration in file | Recommended source path |
| --- | --- |
| `package vn.learn.demo;` | `src/vn/learn/demo/Main.java` |
| `package vn.learn.demo;` | `src/vn/learn/demo/Greeter.java` |
| `package vn.learn.demo.tools;` | `src/vn/learn/demo/tools/Counter.java` |

`src` is the **source root directory** in the example, not part of the package name. `Main.java` declares `vn.learn.demo`, not `src.vn.learn.demo`.

**This is an important tooling organization convention**, not a strict syntax rule that makes `javac` unable to compile any Java file in the wrong directory when the file path is explicitly passed. However, following this structure helps the compiler, IDE, and build tools locate source files accurately and avoid confusion in larger projects.

## 4. Java 17+ example with three files across two packages

Create the exact three files below under the `project` directory. This is **one unified runnable example** requiring no external libraries.

**File 1 — `src/vn/learn/demo/Greeter.java`**

~~~java
package vn.learn.demo;

// Without public: top-level class is directly accessible only within the package.
final class Greeter {
    private Greeter() {
    }

    static String hello(String name) {
        return "Xin chào, " + name;
    }
}
~~~

**File 2 — `src/vn/learn/demo/tools/Counter.java`**

~~~java
package vn.learn.demo.tools;

public final class Counter {
    private int value;

    public Counter(int initial) {
        this.value = initial;
    }

    public int value() {
        return value;
    }

    public void add(int amount) {
        value += amount;
    }
}
~~~

**File 3 — `src/vn/learn/demo/Main.java`**

~~~java
package vn.learn.demo;

import vn.learn.demo.tools.Counter;

public final class Main {
    public static void main(String[] args) {
        System.out.println("mainPackage=" + Main.class.getPackageName());
        System.out.println("greeting=" + Greeter.hello("Lan"));

        Counter counter = new Counter(2);
        System.out.println("start=" + counter.value());
        counter.add(3);
        System.out.println("afterAdd=" + counter.value());

        System.out.println("toolsPackage=" + Counter.class.getPackageName());
        System.out.println("counterClass=" + Counter.class.getName());
    }
}
~~~

Why does the example work?

- `Main` and `Greeter` declare the **same** `package vn.learn.demo;`, so `Main` can use the package-private class `Greeter` without an import.
- `Counter` is in a **different** package, `vn.learn.demo.tools`, so `Main` must use its fully qualified name or a valid `import`. `Counter` and its constructor/methods used from outside the package are declared `public`.
- `getPackageName()` shows the package name at runtime; `Counter.class.getName()` gives the fully qualified class name.
- `Counter`'s `private int value` cannot be accessed directly from `Main`; `value()` and `add(...)` provide the API.

## 5. Compiling to the output directory and running with classpath

Run commands from the **`project`** directory containing `src`. First create the output directory `out` if it does not already exist.

With **Bash/Linux/macOS**:

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out src/vn/learn/demo/Greeter.java src/vn/learn/demo/tools/Counter.java src/vn/learn/demo/Main.java
java -cp out vn.learn.demo.Main
~~~

With **Windows PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/vn/learn/demo/Greeter.java src/vn/learn/demo/tools/Counter.java src/vn/learn/demo/Main.java
java -cp out vn.learn.demo.Main
~~~

**Expected stdout of `java -cp out vn.learn.demo.Main` (exact):**

~~~text
mainPackage=vn.learn.demo
greeting=Xin chào, Lan
start=2
afterAdd=5
toolsPackage=vn.learn.demo.tools
counterClass=vn.learn.demo.tools.Counter
~~~

The `javac` command compiles into `.class` files under `out`:

~~~text
out/
└── vn/
    └── learn/
        └── demo/
            ├── Main.class
            ├── Greeter.class
            └── tools/
                └── Counter.class
~~~

**Command breakdown:**

| Part | Purpose |
| --- | --- |
| `javac` | Compiles Java source into `.class` bytecode |
| `-encoding UTF-8` | Reads source containing Vietnamese text with the correct encoding |
| `-d out` | Sets the **output root directory**, where `javac` creates the matching package tree |
| `java -cp out` | Puts the compiled classes' root directory on the classpath |
| `vn.learn.demo.Main` | Fully qualified name of the class containing `main`, not a file path |

With `javac -d out`, the `out` directory must exist; the compiler creates the **nested package directories inside** as needed. When running, the classpath must point to the **root above `vn`** (`out`), not directly to `out/vn/learn/demo`. When using `java -cp out ...`, do not pass the `.class` extension.

## 6. Subpackages do not automatically belong to the same package for access

The name `vn.learn.demo.tools` looks like it sits "under" `vn.learn.demo`, but for access control, Java treats them as **two different packages**.

~~~java
// Assume this is placed in package vn.learn.demo:
class InternalHelper {
    static String code() {
        return "internal";
    }
}
~~~

A class in `vn.learn.demo.tools` **cannot automatically** call `InternalHelper.code()` because `InternalHelper` is a package-private top-level class of another package.

| Case | Result |
| --- | --- |
| Two classes declaring `package vn.learn.demo;` | Same package; can access applicable package-private members |
| One class in `vn.learn.demo`, one in `vn.learn.demo.tools` | Different packages; do not automatically have package-private access |
| `import vn.learn.demo.tools.Counter;` | Allows using short name `Counter` if the type and members are validly accessible |
| `import vn.learn.demo.*;` | Does not automatically import types in `vn.learn.demo.tools` |
| `private` field of `Counter` | Cannot be accessed directly from an external class without permission |

**Import does not grant extra access permissions.** For example, `import vn.learn.demo.tools.Counter;` does not allow `Main` to read `counter.value` because the field is still `private`.

A `public` class and `public` constructor can be used across packages when the environment/module allows it. For introductory programs without `module-info.java` like the example above, the classpath is the simplest mechanism.

## 7. Common errors with packages, paths, and run commands

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `Could not find or load main class Main` | `Main` belongs to a named package, not the unnamed package | Use `java -cp out vn.learn.demo.Main` |
| `ClassNotFoundException: vn.learn.demo.Main` | Wrong classpath root or class not compiled yet | Check `out/vn/learn/demo/Main.class`, use `-cp out` |
| `package ... does not exist` during compilation | Missing source files/dependencies or wrong classpath passed to `javac` | Compile all required files, check package names |
| `cannot find symbol` for `Counter` | Missing import or wrong type name used | `import vn.learn.demo.tools.Counter;` or fully qualified name |
| `... is not public; cannot be accessed from outside package` | Package-private class or member called from another package | Design a valid public API or place internal code in the same package |
| `class Main is public, should be declared in a file named Main.java` | File name does not match the public top-level class | Name it `Main.java` |
| Running `java -cp out/vn/learn/demo Main` | Mistakenly chose a **package subdirectory** as the classpath root | Choose the root `out` and the fully qualified class name |
| `mkdir out` not run yet, `javac -d out` fails | Output directory does not exist yet | Create `out` before compiling |
| Moving `Main.java` to another package while keeping `java ...vn.learn.demo.Main` | Package name in source, output directory, and FQN are out of sync | Update the declaration, source location, and run command |

Java is case-sensitive in package and class identifiers. Especially on operating systems with case-sensitive filesystems, `Demo` and `demo` are different names.

**Do not fix errors by blindly deleting the `package` declaration.** When the error is in the classpath or directory tree, removing `package` changes the fully qualified name and structure of the entire program.

## 8. Practice checklist and exercises

**Checklist for running a multi-package program:**

1. Every file declares the right `package ...;` before `import` statements and classes.
2. The `src` tree reflects the package name segment by segment, e.g., `vn/learn/demo`.
3. `Main.java` contains `public class Main` and a valid `main` method.
4. Types used across packages have appropriate access modifiers; `import` does not replace `public`.
5. Create the `out` directory and use `javac -d out` to compile all source files.
6. Run `java -cp out vn.learn.demo.Main` from the project root and verify the exact stdout.

**Exercise 1.** Create `src/com/example/hello/Main.java` with `package com.example.hello;`. Compile using `javac -d out` and run with the corresponding FQN.

**Exercise 2.** Create an additional `src/com/example/hello/Message.java` in the same package; omit `public` on `Message` and call a package-private method from `Main`.

**Exercise 3.** Move `Message` to `com.example.hello.util`. Explain why `Main` now needs a type accessible from another package and may need an `import`.

**Exercise 4.** Try running `java -cp out Main` after adding a package declaration. Read the error, then fix it to use the fully qualified class name.

**Exercise 5.** Change `package vn.learn.demo.tools;` in `Counter.java` to another package. Update the source path, `import`, and run command accordingly; predict the `.class` output tree.

### Key takeaway

**`package` determines a type's fully qualified name; the source structure `src/a/b/C.java` should match `package a.b;`.** Use `javac -d out` to organize `.class` files by package, then run with `java -cp out a.b.C`. `import` only lets you use short names without changing packages or access rights; a subpackage is still a separate package.