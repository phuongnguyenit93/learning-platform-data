# Top-Level Classes and Multiple Classes in One Java Source File

A Java source file (`.java`) **can declare multiple top-level classes**. However, in a typical Java project compiled with `javac`, **at most one top-level type per file may be declared `public`**, and if present, **the file name must match the exact name of that `public` type** (case-sensitive). The remaining classes can coexist in the file if they are declared with default package access.

This is core knowledge when reading code with multiple `class` declarations in a single file, when organizing packages, or when seeing the compiler generate multiple `.class` files even though only one `.java` file was compiled.

## 1. What Is a Top-Level Class?

A **top-level class** is a class declared **directly within a Java compilation unit** (`compilation unit`), meaning it is not inside the body of another class/interface/record and is not inside a method or block.

Illustrative example:

```java
package demo;

public class Main {       // Top-level class #1
    public static void main(String[] args) {
        Helper.greet();
    }
}

class Helper {            // Top-level class #2
    static void greet() {
        System.out.println("Xin chào Java");
    }
}
```

Both `Main` and `Helper` are top-level classes. `Helper` does not become a nested class simply because it is written below `Main`. The two classes are in **the same package `demo`**, with their own type names and identities: `demo.Main` and `demo.Helper`.

The example above is a valid source file if saved as `Main.java` following the appropriate package structure. It will be examined and run in full in the following section.

A typical Java source file has the layout:

```text
package ...;             // optional, at most one declaration
import ...;              // zero or more import declarations
                          // top-level declarations:
public class X { ... }
class Y { ... }
class Z { ... }
```

Each top-level declaration can also be an `interface`, `enum`, `record`, or annotation type (`@interface`), in addition to a regular `class`. The file naming rule and the single `public` top-level declaration rule apply similarly to these kinds of top-level types when compiled under the common `javac` source-file model.

**Distinguishing scope:** "top-level" refers to **declaration location**, whereas `public` refers to **accessibility**. A top-level class may be `public` or non-`public`; it does not automatically have `public` just because it sits outside other classes.

## 2. The One `public` Top-Level Type per File Rule

Valid example, file `Main.java`:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Main chạy");
    }
}

class FirstHelper {
}

class SecondHelper {
}
```

There are three top-level classes, but only `Main` is `public`. This is a valid Java compilation unit.

An **invalid** example, even though both classes have their own code:

```java
// File: Main.java — INVALID
public class Main {
}

public class Helper {
}
```

The `javac` compiler rejects this because `Helper` is a `public` top-level type that is not in a file named `Helper.java`. It cannot be fixed by renaming `Main.java` to `Helper.java`: then the `Main` class would fail to match the file name instead. The fix is to **split them into `Main.java` and `Helper.java`**, or remove `public` from one of the classes if access is only needed within the same package.

The name of the `public` type must match the file name:

| File name | Top-level declarations | Result |
| --- | --- | --- |
| `Main.java` | `public class Main { }` | Valid |
| `Main.java` | `class Main { } class Helper { }` | Valid |
| `Utilities.java` | `class Launcher { } class Helper { }` | Valid (no `public` type) |
| `Main.java` | `public class Launcher { }` | Error: file name does not match `Launcher` |
| `Main.java` | `public class Main { } public class Helper { }` | Error: multiple `public` top-level types in the file |
| `Main.java` | `public interface Main { } class Helper { }` | Valid, if `Main` is the intended interface name |

The examples above examine declaration and naming rules; running with `java` also requires an appropriate `main` entry-point method or another supported launch mechanism.

**Note on naming:** Java is case-sensitive; you should use file names and type names that match character for character, even on operating systems with case-insensitive file systems.

## 3. Runnable Example: One File with Three Top-Level Classes

Create the file **`src/demo/catalog/CatalogApp.java`** with the *entire* content below:

```java
package demo.catalog;

import java.util.List;

public class CatalogApp {
    public static void main(String[] args) {
        List<Book> books = List.of(
                new Book("Java 17"),
                new Book("Clean Code")
        );

        for (Book book : books) {
            CatalogPrinter.print(book);
        }
        System.out.println("Tổng: " + books.size());
    }
}

class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    String getTitle() {
        return title;
    }
}

final class CatalogPrinter {
    private CatalogPrinter() {
        // Utility class: prevent instantiation from outside.
    }

    static void print(Book book) {
        System.out.println("Sách: " + book.getTitle());
    }
}
```

Compile and run with JDK 17+ from the directory containing `src`:

```bash
javac -encoding UTF-8 -d out src/demo/catalog/CatalogApp.java
java -cp out demo.catalog.CatalogApp
```

**Exact stdout output:**

```text
Sách: Java 17
Sách: Clean Code
Tổng: 2
```

Reading the example:

- `CatalogApp`, `Book`, and `CatalogPrinter` are **three top-level classes** declared together in **one file `CatalogApp.java`**.
- `CatalogApp` is the only `public` class, so the file name must be `CatalogApp.java`.
- `Book` and `CatalogPrinter` do not have `public` before `class`, so they have **package-private access**. Types in the same package `demo.catalog` can use them, even when declared in another file.
- `Book.title` is `private` and is only accessed directly from `Book` itself; `CatalogPrinter` uses the `getTitle()` method instead of accessing `title`.
- The `Book(String title)` constructor and the `getTitle()` method have no access modifier written, so they also have package-private access. That works because the calls in the example are all in the same package.
- `CatalogPrinter` has `final`, meaning the class cannot be subclassed; `final` does **not** change the class's package-private access scope.
- `List` is a standard library type imported via `import java.util.List;`. The `import` statement provides convenience for writing the type name; it does not move `List` into the current package.

After the `javac -d out` command, the compilation output consists of the files corresponding to the top-level classes:

```text
out/
└── demo/
    └── catalog/
        ├── CatalogApp.class
        ├── Book.class
        └── CatalogPrinter.class
```

These are three separate bytecode files. **One `.java` file does not equate to one `.class` file.** In the example above, `javac` compiles all three top-level classes contained in the source file, and `-d out` tells it to place the bytecode inside the `out` directory according to package. On Windows, the actual path separator is usually `\`; the diagram uses `/` for readability.

When running, the name `demo.catalog.CatalogApp` is the **fully qualified name** of the class containing `main`; `java` does not run based on the compiled `CatalogApp.java` source file name, but instead loads the specified class on the classpath and invokes the appropriate entry point.

## 4. What Access Scope Does a Non-`public` Top-Level Class Have?

If you omit the `public` access modifier on a top-level class, the class has **package access** (commonly called **package-private**, or *default/package-level access*). This is not a `default` keyword written before `class`.

```java
package demo.catalog;

class Book {
    // Types belonging to the demo.catalog package can reference Book.
}
```

Practical implications:

- `Book` can be used in **other classes within the same package `demo.catalog`**, even when declared in a different `.java` file.
- Source code in another package **cannot directly reference `demo.catalog.Book`** as an accessible type. Adding `import demo.catalog.Book;` does not change access permissions.
- A package is determined by the **`package` declaration**, not by sharing a `.java` file. Matching directories to package names is an important source layout convention and aligns with build tools/compilers.
- A `public` top-level class can be used from another package if the type and the required members also have appropriate access and are placed on the classpath/module path properly. A class being `public` does not automatically turn every constructor/field/method inside it into `public`.

Example with the same package across two separate files:

**`src/lesson/App.java`**

```java
package lesson;

public class App {
    public static void main(String[] args) {
        Message message = new Message();
        System.out.println(message.text());
    }
}
```

**`src/lesson/Message.java`**

```java
package lesson;

class Message {
    String text() {
        return "Cùng package";
    }
}
```

Commands:

```bash
javac -encoding UTF-8 -d out src/lesson/App.java src/lesson/Message.java
java -cp out lesson.App
```

Stdout:

```text
Cùng package
```

`App` and `Message` can interact because both belong to `lesson`, **not because they are in the same file** (they are in two different files). Keep `Message` non-`public` when it is an implementation detail needed only within the package.

## 5. What If a File Has No `public` Top-Level Type?

**It is still valid.** In this case, the `.java` file name is not required to match the name of any class in the file. All top-level classes can carry package-private scope.

Create the file **`Utilities.java`** in the working directory, without a `package` declaration:

```java
class Launcher {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}

class Greeter {
    static String message() {
        return "Chào Java";
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 Utilities.java
java Launcher
```

Stdout:

```text
Chào Java
```

After compilation, `Launcher.class` and `Greeter.class` exist. **There is no `Utilities.class`** just because the source file is named `Utilities.java`: `.class` files take their names from the declared classes. You run `java Launcher` because **`Launcher`** is the class containing the `public static void main(String[] args)` method, not because of the `Utilities.java` file name.

An example without a `package` declaration uses the **unnamed package**. This is a convenient approach for small lessons; for multi-file projects, you should declare packages explicitly and structure directories accordingly.

Note: build tools, IDEs, and project conventions typically expect each significant top-level type to have a file whose name matches the type, even for non-`public` types. This is a **code organization convention**, distinct from Java's syntax rules for files without `public`.

## 6. How Does a Top-Level Class Differ from a Nested Class?

Placing two declarations side by side at the file level creates **two independent top-level classes**:

```java
class Outer {
}

class Neighbor {
}
```

In contrast, placing a declaration **inside a class body** creates a **member class (nested class)**:

```java
class Outer {
    static class Nested {
    }

    private static class HiddenNested {
    }
}
```

Comparison:

| Characteristic | Top-level class | Member/nested class |
| --- | --- | --- |
| Location | Directly in the file/compilation unit | Inside the body of another type |
| Example source name | `Neighbor` | `Outer.Nested` |
| `private`, `protected` | **Not allowed** as an access modifier of a top-level class | Can be used with a member class depending on context |
| `static` | **Not allowed** for a top-level class | Can be used for a static nested class |
| Typical bytecode name format | `Neighbor.class` | `Outer$Nested.class` |
| Relationship | Not a member of the class preceding it | Is a member of the enclosing type |

A top-level class can use valid modifiers such as `public`, `abstract`, `final`, or `sealed` (subject to their respective constraints), but **cannot be declared directly as `private`, `protected`, or `static`**.

Invalid examples at the file level:

```java
private class Secret { }      // INVALID: top-level cannot be private
protected class Child { }     // INVALID: top-level cannot be protected
static class Tool { }         // INVALID: top-level cannot be static
```

If you genuinely need a `private` or `static` implementation class, consider making it a nested class inside the enclosing type, or use a package-private top-level class when the goal is simply to hide it from other packages. Do not automatically turn top-level classes in the same file into nested classes.

**Differences among types of nested classes:** a non-`static` member class is tied to an instance of the enclosing class; a static nested class does not need an enclosing instance to be instantiated in the way a member class does. Local classes (declared in a block/method) and anonymous classes also differ from top-level classes. Having multiple declarations in a file **does not automatically determine** the class kind; the declaration location does.

## 7. How Is a File with Multiple Classes Compiled?

For the `CatalogApp.java` program in section 3:

1. `javac` reads the compilation unit containing `package`, `import`, and the three top-level declarations.
2. The compiler checks the syntax, type definitions, access permissions, and dependencies of these declarations.
3. It generates appropriate bytecode for each class (`CatalogApp.class`, `Book.class`, `CatalogPrinter.class`).
4. When running `java -cp out demo.catalog.CatalogApp`, the JVM loads classes and dependencies as needed; the `main` method in `CatalogApp` creates `Book` objects and calls `CatalogPrinter`.

The `.class` files are **compilation outputs of types**, not one-to-one with each `new` line (object creation). One class can be used to create very many objects at runtime while still having a single type definition.

When nested/local/anonymous classes are present, the compiler typically generates additional `.class` files named in the form `Outer$Nested.class` or with other internal suffixes. Therefore, you should not predict the number of `.class` files solely from the number of `.java` files. For the simple three **top-level class** example, the three `.class` file diagram in section 3 is sufficient.

One detail about ordering: top-level declarations in the same file **are not required to be written in order of use**. In the `CatalogApp` code, `CatalogApp` calls `Book` before the `class Book` part appears in the text, yet `javac` still analyzes the entire compilation unit. There is no need to move `Book` above `CatalogApp` in order to compile.

## 8. When Should You Write Multiple Classes in One File?

Placing multiple top-level classes in one file **is permitted by the language**, though it should be based on purpose and maintainability:

- **Reasonable:** short learning examples, small sample programs, or one `public` type together with a few short package-private helpers directly related only to that type.
- **Consider splitting files:** classes that are long, have separate responsibilities, are widely used across the package, are tested/maintained independently, or make the file difficult to navigate.
- **Common in large projects:** one corresponding file per significant top-level type; a helper class tightly tied to only one class can become a member class if an enclosing relationship is truly needed.
- **Keep the API clear:** declare `public` only on types that are genuinely API needing access from outside package scope; use package-private for internal implementation details when appropriate.

Suppose `App.java` initially contains:

```java
package example;

public class App {
    public static void main(String[] args) {
        Helper.sayHello();
    }
}

class Helper {
    static void sayHello() {
        System.out.println("Hello");
    }
}
```

As `Helper` grows larger, it can be split into **two files in the same package**, preserving the same behavior:

**`src/example/App.java`**

```java
package example;

public class App {
    public static void main(String[] args) {
        Helper.sayHello();
    }
}
```

**`src/example/Helper.java`**

```java
package example;

class Helper {
    static void sayHello() {
        System.out.println("Hello");
    }
}
```

Compile the two files after deleting the `class Helper` part from `App.java`:

```bash
javac -encoding UTF-8 -d out src/example/App.java src/example/Helper.java
java -cp out example.App
```

Stdout:

```text
Hello
```

`Helper` does not need to be changed to `public` to be used from `App` because both classes still belong to the `example` package. **Do not leave two declarations of `example.Helper`** (one in `App.java` and one in `Helper.java`) in the same compilation source set, because they share the same fully qualified type name and cause a duplicate definition error.

## 9. Common Errors and Self-Checks

| Symptom / misconception | Actual cause | How to resolve |
| --- | --- | --- |
| "One `.java` must contain only one `class`." | Confusing a source file with a class declaration. | Multiple top-level classes can be declared; follow the `public` rule. |
| Compiling `Main.java` reports that `Helper` must be in `Helper.java`. | `Helper` is declared `public` in the wrong file name. | Split into `Helper.java` or remove `public` if used only in the package. |
| Having both `public class Main` and `public class Helper` in one file. | Both top-level types are `public`. | Split the source files or reduce access appropriately. |
| Writing `private class Helper` outside any class. | A top-level class does not accept the `private` modifier. | Use `class Helper` (package-private), or design a nested class. |
| Writing `static class Helper` outside any class. | `static` is only suitable for nested member classes, not top-level classes. | Remove `static` or move the declaration inside an enclosing type. |
| `java Utilities` does not run even though compiling `Utilities.java` succeeded. | The source file name is not necessarily the name of the class containing `main`. | Run with the exact class name, such as `java Launcher`. |
| Code in another package cannot access `Helper`. | `Helper` is a package-private top-level class. | Design a `public` API if needed; place it in the appropriate `Helper.java` file. |
| Multiple `.class` files appear after compiling one `.java` file. | One compilation unit contains multiple types or nested types. | This is normal output. |
| `duplicate class` after splitting a helper into its own file. | An old declaration with the same fully qualified name remains in the source set. | Keep only one definition of the type in the package. |
| Running `java CatalogApp` for a class in `package demo.catalog;`. | Missing the fully qualified name of the class in the run command. | Use `java -cp out demo.catalog.CatalogApp`. |

The errors above are the types commonly detected by `javac` at compile time; detailed messages may vary by JDK version and how compilation is run.

## 10. Practice Questions

**Question 1.** Contents of `Main.java`:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("OK");
    }
}

class Tool {
}

class Storage {
}
```

Is it valid, and how many top-level classes are there? **Valid.** There are three top-level classes, and only `Main` is `public`. If compiled successfully, `javac Main.java` produces `Main.class`, `Tool.class`, and `Storage.class`; `java Main` prints `OK`.

**Question 2.** The file `Helpers.java` contains `class A { } class B { }`, without `public`. Must the file name be changed to `A.java`? **No.** The file has no `public` top-level type, so the name `Helpers.java` is valid with `javac` in the standard model.

**Question 3.** `Outer.java` contains `public class Outer { static class Inner { } } class Helper { }`. Is `Inner` a top-level class? **No.** `Inner` is a static nested class because it is inside `Outer`; `Helper` is the top-level class alongside `Outer`.

**Question 4.** When moving `class Helper` from the end of `App.java` to `Helper.java` while still using `package example;` in both, is it necessary to add `public` to `Helper`? **No**, if only classes in `example` use `Helper`. Two classes in the same package can still access a package-private type even when in different files.

**Question 5.** What determines which class the `java` command must run: the `.java` file name or the name of the class that has the `main` method? **The name of the class to launch**, along with the full package name if there is a package; the classpath/module path must contain the corresponding bytecode.

## Key Takeaways

- A **top-level class** resides directly within a compilation unit, not inside another type or method.
- **A `.java` file can contain multiple top-level classes**, though with common Java compilation, there is **at most one `public` top-level type** and the file name must match that `public` type.
- A **non-`public` top-level class is package-private**, usable from types in the same package even when located in a different source file.
- A top-level class **cannot be `private`, `protected`, or `static`**; those modifiers must be understood in the context of member/nested classes when valid.
- **Source files, classes, and bytecode files are different concepts:** one `.java` file can contain multiple classes; compilation can produce multiple `.class` files; running a program uses the name of the class containing the entry point.
