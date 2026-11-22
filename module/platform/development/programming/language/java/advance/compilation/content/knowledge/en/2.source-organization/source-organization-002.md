# Packages, Source Roots, and Fully Qualified Type Names in Java

In Java, a **package** defines a type's namespace; the **source root** is the starting point where build tools locate source files; and the **fully qualified name** (FQN) identifies a type by its package name and type name. These three concepts are closely related yet not identical. Understanding them properly helps you compile, run programs, design libraries, and resolve import/classpath errors accurately.

## 1. The Three Concepts and Their Relationship

| Concept | Role | Example |
| --- | --- | --- |
| Package | Groups types into a namespace and affects package-private access | `com.acme.catalog` |
| Source root | Parent directory of the directory tree corresponding to package names; determined by the project/build tool | `src/main/java` or `src` |
| Fully qualified type name | Name distinguishing a type from types with the same short name in other packages | `com.acme.catalog.Book` |
| Output directory | Where the compiler writes `.class` files, usually organized hierarchically by package | `out` or `build/classes/java/main` |
| Classpath root | Directory/JAR that the compiler or JVM uses as a root to look up binary classes by name | `out` or `app.jar` |

For a typical source file:

~~~text
project/
└── src/main/java/                   ← source root
    └── com/acme/catalog/            ← path corresponding to package
        └── Book.java                ← compilation unit
~~~

The `Book.java` file can declare:

~~~java
package com.acme.catalog;

public class Book {
}
~~~

Then the fully qualified name of the class is `com.acme.catalog.Book`. Do **not** include `src`, `main`, or `java` in the package name: they are part of the project structure, not part of the type identifier.

A way to visualize this:

~~~text
source root      + package path          + source file
src/main/java/   + com/acme/catalog/     + Book.java

package name     + "." + simple name     = fully qualified name
com.acme.catalog + "." + Book            = com.acme.catalog.Book

classpath root   + binary path
out/             + com/acme/catalog/Book.class
~~~

Directory trees use `/` or `\` depending on the OS; package names in Java are **always** separated by dots (`.`).

## 2. The package Statement: Syntax and Meaning

The package declaration precedes imports and top-level type declarations, except for comments and annotations applying to the package.

~~~java
package com.acme.catalog;

import java.util.List;

public final class BookRepository {
    private final List<String> titles = List.of("Java", "JVM");

    public List<String> titles() {
        return titles;
    }
}
~~~

A source file may have at most one `package` declaration. All top-level classes, interfaces, enums, and records in this compilation unit belong to the declared package. If there is no `package` declaration, the types reside in the **unnamed package** (commonly called the default package).

### Naming conventions

- Prefer lowercase package names and meaningful structure: `com.example.compiler`, `org.example.parser.ast`. Typically start with a reversed domain name to avoid collisions across organizations.
- Each segment between dots must be a valid Java identifier. Do not use hyphens like `java-compiler`, do not start with a digit, and do not use keywords like `class`.
- Keep names stable because renaming a package changes fully qualified type names, imports, and classpaths, and may affect binary compatibility or serialization.
- `com.acme` and `com.acme.internal` are **two distinct packages**: having a prefix relationship in names does not grant inherited access between them.

A package is a **namespace** and part of the access control model, not an independent process, does not automatically create a module, and does not itself enforce physical directory structure.

## 3. Source Root and Source File Location

Project build tools typically prescribe source roots:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/                   ← application code
│   │       └── com/acme/app/Main.java
│   └── test/
│       └── java/                   ← test code
│           └── com/acme/app/MainTest.java
└── build/                          ← output (e.g., Gradle)
~~~

`src/main/java` is a common Maven/Gradle convention, **not a keyword or mandatory rule of the Java language**. Small projects can choose `src`, and the command-line compiler can accept explicit source file pathnames.

When organizing a project, place files declaring `package com.acme.app;` under `<source-root>/com/acme/app/`. This alignment helps IDEs, javac, test runners, and build tools locate files predictably. For package name `com.acme.app`, the source root is the directory **immediately above** `com`, not the `app` directory.

Do not infer the package from the file's location in an editor: in standard Java, **the `package` declaration determines the package**; disk location is a tool and organizational convention. Also do not treat the classpath root and source root as the same thing: the input holds `.java` files, whereas the runtime classpath must point to compiled `.class` files or JARs containing them.

## 4. Complete Example: Compiling and Running on Java 17+

Create these exact two files from the project directory:

~~~text
example/
└── src/
    └── com/
        └── acme/
            ├── catalog/
            │   └── Book.java
            └── app/
                └── Main.java
~~~

**File `src/com/acme/catalog/Book.java`:**

~~~java
package com.acme.catalog;

public final class Book {
    private final String title;

    public Book(String title) {
        this.title = title;
    }

    public String title() {
        return title;
    }
}
~~~

**File `src/com/acme/app/Main.java`:**

~~~java
package com.acme.app;

import com.acme.catalog.Book;

public final class Main {
    public static void main(String[] args) {
        Book book = new Book("Java 17");
        System.out.println(book.title());
        System.out.println(Book.class.getName());
    }
}
~~~

From the `example` directory, run (PowerShell, Command Prompt, or Unix shell; create `out` first if it does not exist):

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/com/acme/catalog/Book.java src/com/acme/app/Main.java
java -cp out com.acme.app.Main
~~~

**Exact stdout:**

~~~text
Java 17
com.acme.catalog.Book
~~~

After the compilation command:

~~~text
example/
├── src/
│   └── com/acme/...                ← two .java files
└── out/                            ← runtime classpath root
    └── com/acme/
        ├── catalog/Book.class
        └── app/Main.class
~~~

Step-by-step explanation:

1. `javac` accepts **source file paths** after options; here both `.java` files are specified.
2. `-d out` specifies the destination directory; the compiler writes `.class` files beneath it according to package names. `-encoding UTF-8` specifies the encoding for reading source code.
3. `java -cp out` adds `out` to the classpath. The JVM looks for `com.acme.app.Main` under `out/com/acme/app/Main.class`.
4. The final argument to `java` is **the fully qualified class name**, not `Main.java`, `Main.class`, or the path `out/com/acme/app/Main.class`.
5. `Main` uses `Book` from another package via an `import` declaration. The compiler still needs to locate `Book`'s definition at compile time; the JVM still needs to locate `Book.class` at runtime.

If you want to package the compiled classes into a JAR for classpath execution, you can run:

~~~bash
jar --create --file app.jar -C out .
java -cp app.jar com.acme.app.Main
~~~

This JAR contains entries `com/acme/app/Main.class` and `com/acme/catalog/Book.class`; the `com` directory sits right at the JAR root. This runs via classpath with an explicit main class name and does not require a `Main-Class` manifest entry.

## 5. Simple Names, Fully Qualified Names, and Imports

The **simple name** of `com.acme.catalog.Book` is `Book`. To use a type from another package, you can import its name:

~~~java
import com.acme.catalog.Book;

// Inside a class declaration:
Book book = new Book("Clean Code");
~~~

Or use the fully qualified name without importing:

~~~java
// Inside a class declaration:
com.acme.catalog.Book book =
        new com.acme.catalog.Book("Clean Code");
~~~

The two approaches differ only in how the name is written in source code. `import` does not copy code, does not install dependencies, does not add JARs to the classpath, and does not control class loading at runtime.

Java automatically permits using simple names for visible types in the same package and implicitly imports `java.lang` (e.g., `String`, `System`). For other packages, write imports or fully qualified names as needed. `import java.util.*;` performs import-on-demand only for types directly in `java.util`, not including `java.util.concurrent`.

### When two types share the same name

For example, `java.util.Date` and `java.sql.Date` have the same simple name. You can use:

~~~java
java.util.Date legacyDate = new java.util.Date();
java.sql.Date sqlDate = new java.sql.Date(0L);
~~~

Or import only one of the two and write the fully qualified name for the other. If two single-type imports with the same simple name collide, the compiler reports an error; with import-on-demand declarations, referencing an ambiguous name also causes a compilation error. **Fully qualified names resolve ambiguity**, provided the type is accessible and the required dependency is on the compiler's search path.

Static import is a separate concept: `import static java.lang.Math.PI;` lets you reference the static member `PI` directly; it does not change the package of the class being written.

## 6. Fully Qualified Name, Canonical Name, and Binary Name

At a basic level, the fully qualified type name of a top-level class such as `com.acme.catalog.Book` is `package + "." + type name`. For **nested types**, distinguish how they are written in source code from the binary name used in bytecode and many reflection APIs:

~~~java
package com.acme.catalog;

public class Outer {
    public static class Inner {
    }
}
~~~

| Naming form | Value |
| --- | --- |
| Simple name of nested type | `Inner` |
| Canonical name | `com.acme.catalog.Outer.Inner` |
| Binary name | `com.acme.catalog.Outer$Inner` |
| Class file path after compilation | `com/acme/catalog/Outer$Inner.class` |
| `Outer.Inner.class.getCanonicalName()` | `com.acme.catalog.Outer.Inner` |
| `Outer.Inner.class.getName()` | `com.acme.catalog.Outer$Inner` |

In Java code, we typically write `Outer.Inner`; when calling `Class.forName("com.acme.catalog.Outer$Inner")`, you must use the **binary name**. The `$` in the class file in this example represents the nested type separator. Do not replace every dot with `$`: only nested-type boundaries are compiled under this rule.

Additional note: anonymous classes and local classes do not necessarily have a canonical name; `getCanonicalName()` may return `null`. For arrays, `Class.getName()` uses descriptor notation different from type names in source code. Therefore, do not treat `getName()`, `getCanonicalName()`, and import strings as interchangeable representations in all cases.

## 7. Packages and Access Control

Access control in Java is directly tied to packages:

| Member/type | Basic scope |
| --- | --- |
| `public` top-level type | Referencable from code in other packages if module/search-path constraints also allow |
| Top-level type without `public` | Accessible only to code in the **same package** |
| Member without modifier (package-private) | Accessible only to code in the same package |
| `private` member | Restricted by Java's private access rules (including nestmate relationships) |
| `protected` member | Same package or valid inheritance cases per Java rules |

Example:

~~~java
package com.acme.catalog;

final class CatalogValidator {
    static boolean valid(String title) {
        return title != null && !title.isBlank();
    }
}
~~~

`CatalogValidator` lacks the `public` modifier, so `com.acme.catalog.Book` can use it, whereas `com.acme.app.Main` cannot. Similarly, `com.acme.catalog.internal` is a separate package: a type there also **does not** get package-private access from `com.acme.catalog`.

A Java compilation unit normally has at most **one top-level public type**, and the filename must match that public type's name, such as `public class Book` in `Book.java`. Other non-public top-level types may coexist in the same file when valid, though placing each type in its own file is usually easier to maintain.

## 8. Unnamed Package, package-info, and module-info

**Unnamed package:** if the `package` declaration is omitted, the class resides in the unnamed package. This is convenient for small experiments, but unsuitable for multi-package application/library code. Specifically, code in a **named package cannot import types from the unnamed package**. When building projects, use explicit named packages.

**`package-info.java`:** a file placed in the package directory, primarily holding Javadoc documentation and package-level annotations. Example:

~~~java
/**
 * Business domain types for the book catalog.
 */
package com.acme.catalog;
~~~

This file is not the place to declare the `Book` class and does not replace `Book.java`.

**`module-info.java` (JPMS, Java 9+):** describes a **module**, a unit grouping packages, declaring dependencies, and exporting packages. Two classes having matching packages do not mean module dependencies or access permissions are configured properly. Example describing two separate modules:

~~~java
// module-info.java of module com.acme.catalog
module com.acme.catalog {
    exports com.acme.catalog;
}
~~~

~~~java
// module-info.java of module com.acme.app
module com.acme.app {
    requires com.acme.catalog;
}
~~~

In this example, `exports` lets other modules access public types in the exported package; package `com.acme.catalog.internal` is not automatically exported just because its name shares a prefix. `requires` expresses a module dependency. When building JPMS applications, organize module-source-path/module-path and launch commands accordingly; the `java -cp` command in section 4 is for **ordinary classpath** projects, not a module-path example.

## 9. How Does the Compiler Locate Sources and Classes?

Three paths are easily confused:

- **Source path**: where `javac` can look for additional `.java` source files to compile when resolving dependent types (when configured, e.g., `-sourcepath src`). Paths to `.java` files listed directly in the compile command are always explicit inputs.
- **Compile classpath**: where `javac` looks for compiled types and JAR libraries, configured via `-classpath` or `-cp`. It is not automatically inferred from `import` statements.
- **Runtime classpath**: where the `java` command looks for classes/JARs to execute, also configured via `-cp` or via a build tool. This path can differ from the compile classpath; missing a library at runtime can cause class linkage errors.

Example with an external library named `lib/example.jar` and a source file depending on it (file paths are illustrative):

~~~bash
javac -cp lib/example.jar -d out src/com/acme/app/Main.java
java -cp out:lib/example.jar com.acme.app.Main
~~~

The separator for **multiple classpath entries** differs by OS: Unix/macOS uses `:`, Windows uses `;`; on Windows, the corresponding run argument is `out;lib/example.jar` (enclose in quotes in shells to avoid special syntax handling). This external library example only works when the JAR file and necessary dependencies actually exist. If code depends on `Book.java` from section 4, you must also compile `Book.java` or put the corresponding `Book.class`/JAR on the compile classpath.

Maven/Gradle toolchains usually set up source roots, compile classpaths, test classpaths, and output directories for you. IDEs also derive paths from project configuration. When investigating errors, inspect **the actual build configuration** rather than only looking at the file tree in the UI.

## 10. Common Errors and How to Diagnose Them

| Symptom | Common cause | Check/fix |
| --- | --- | --- |
| `package ... does not exist` | Compiler cannot find library/class containing the imported package | Verify dependencies and compile classpath, package name, paths/source files; `import` does not auto-download dependencies |
| `cannot find symbol: class Book` | Name cannot be resolved at the usage site | Check `package`, `import`, accessibility, and whether the type was compiled |
| `class Book is public, should be declared in a file named Book.java` | Public top-level type name differs from filename | Rename the file or rename the type to match |
| `Could not find or load main class com.acme.app.Main` | Wrong FQN, wrong classpath root, or missing class/dependency | Check `out/com/acme/app/Main.class`; run `java -cp out com.acme.app.Main` from the right directory |
| `NoClassDefFoundError` | A class needed at runtime is missing/unloadable or binary name mismatches | Check underlying cause and runtime classpath; compare declared package and `.class` location |
| `... is not public ... cannot be accessed from outside package` | Using a top-level package-private type from another package | Fix API visibility or move logic into an appropriate package; do not try fixing with imports |
| Ambiguous `Date` name | Multiple types with the same simple name are visible | Choose a specific import or use the fully qualified name at references |
| IDE compiles, but command line fails to run | IDE configured outputs/dependencies while `java` command lacks them | Compare classpath/module-path, source root, and working directory |

A short troubleshooting workflow:

1. Open the `.java` file and read the **exact** `package` declaration and top-level public type name.
2. Identify the source root declared by the build tool, then verify the path under the root against package segments.
3. Check whether output has the expected `.class` under the classpath root.
4. Cross-check the `javac` command (sources, compile classpath, `-d`) and `java` command (runtime classpath, main class FQN).
5. If using modules, check `module-info.java`, `requires`, `exports`, and module path; if using nested types, check canonical name vs. binary name.

## 11. Self-Check Exercises

**Exercise 1.** File `src/main/java/io/demo/tools/TextTool.java` contains `package io.demo.tools;` and `public class TextTool {}`. Identify the source root, simple name, FQN, and class file path when compiled with `-d classes`.

**Answer:** the source root under this layout is `src/main/java`; simple name `TextTool`; FQN `io.demo.tools.TextTool`; class file `classes/io/demo/tools/TextTool.class`.

**Exercise 2.** In `com.acme.app.Main`, replace `new Book("Java 17")` with `new com.acme.catalog.Book("Java 17")`, remove the `Book` import, and recompile using the command from section 4. Stdout remains unchanged because both references designate the same type.

**Exercise 3.** A class in `com.acme.catalog.internal` wants to call a package-private method in `com.acme.catalog.Book`. Is this allowed? **No**: they are two separate packages; sharing an API across package boundaries requires appropriate access visibility.

**Exercise 4.** Why does `java -cp out Main` fail to find class `Main` in section 4? Because the JVM looks for a class named `Main` in the unnamed package, whereas the compiled class is `com.acme.app.Main`. You must pass the FQN `com.acme.app.Main`.

## Key Takeaways to Apply

- `package` defines a type's **namespace**; source root and output root are determined by the project setup.
- Standard source path: `<source-root>/<package-path>/<Type>.java`; standard bytecode path: `<output-root>/<package-path>/<Type>.class`.
- `import` shortens how type names are written in source code; it does not supply dependencies.
- When running with a classpath, the JVM requires the classpath root and **the fully qualified class name**; do not pass source file paths.
- For nested types, distinguish the name used in Java source (dots) from the binary name (usually containing `$`).
- Subpackages do not inherit package-private access from parent packages; JPMS `exports`/`requires` add module boundaries.