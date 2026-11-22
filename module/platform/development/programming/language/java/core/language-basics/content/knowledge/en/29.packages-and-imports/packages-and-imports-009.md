# Distinguishing Packages, Classpath, and Modules at an Introductory Level — Java 17+

## 1. Three concepts answering three different questions

A Java project with many classes and libraries needs to organize names, locate compiled code, and optionally define which parts are allowed to depend on one another. Three common concepts are:

| Concept | Question solved | Example |
|---|---|---|
| **Package** | What **name** does this type have, and which name group does it belong to? | `package com.example.library;`, type `com.example.library.Greeter` |
| **Classpath** | **Where** do the JVM/compiler find traditional classes and JARs? | `java -cp out-cp com.example.app.Main` |
| **Module** | **Which modules** does a named code unit **depend on, and which packages does it expose**? | `module com.example.app { requires com.example.library; }` |

**In summary:** a package is a **namespace**; the classpath is a **search path for classes/libraries**; a module is a **unit of dependency organization and API boundary** in the Java Platform Module System (JPMS, introduced in Java 9).

They do not replace one another: a program using the classpath still has packages; a named module also contains packages; and a module's `.class` files must still be found by the JVM through an appropriate mechanism (typically the **module path**).

## 2. Package: organizing type names

~~~java
package com.example.library;

public final class Greeter {
    private Greeter() {}

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

- `Greeter` is the class's simple name.
- `com.example.library` is the package.
- `com.example.library.Greeter` is the **fully qualified name** of the top-level class.
- Another class in package `com.example.other` can still have the simple name `Greeter` without sharing the same fully qualified name.

In a file in another package, you can write:

~~~java
import com.example.library.Greeter;

// Then:
String message = Greeter.hello("Lan");
~~~

Or omit the import and write `com.example.library.Greeter.hello("Lan")`.

**Imports only assist name lookup in source code**. An `import` line does not tell the JVM which disk location to search for a library, does not create a classpath, and does not instantiate objects. The compiler still needs to locate the class via appropriate paths and build configuration.

Packages are also tied to `package-private` access: the two names `com.example` and `com.example.library` are **not the same package**, even though they look like a parent/child hierarchy. `import com.example.*;` does not automatically import types from `com.example.library`.

## 3. Classpath: specifying where to find classes and JARs

After compiling, Java produces `.class` files. When running in a **non-modular** setup, the classpath specifies the **root directories** and/or **JARs** where tools look for those classes.

Example compiled output layout:

~~~text
out-cp/
└── com/
    └── example/
        ├── library/
        │   └── Greeter.class
        └── app/
            └── Main.class
~~~

The command:

~~~bash
java -cp out-cp com.example.app.Main
~~~

is interpreted as:

1. Find the main class with the fully qualified name `com.example.app.Main`.
2. Search from the **classpath root `out-cp`**, mapping package segments to the path `com/example/app/Main.class`.
3. When `Greeter` is needed, locate `com/example/library/Greeter.class` from the appropriate classpath.

**Do not** choose `-cp out-cp/com/example/app` for a main class in package `com.example.app`: that is not the root corresponding to the fully qualified class name.

A classpath can contain multiple entries. The separator between entries varies by operating system:

| Environment | Example classpath with directory and JAR | Separator |
|---|---|---|
| Linux/macOS | `out-cp:lib/tools.jar` | `:` |
| Windows | `out-cp;lib\\tools.jar` | `;` |

The entries above only illustrate syntax: `lib/tools.jar` is not a required library or a file created in this lesson. For the hands-on example, only `-cp out-cp` is used.

**Distinction:** `classpath` is not a package name, and placing a JAR on the classpath does not declare a named module in your application code.

## 4. Classpath and the unnamed module

In the Java 9+ module system, classes loaded by the application class loader from the traditional classpath belong to that class loader's **unnamed module**.

For a class like `Main` run with `java -cp out-cp ...`, the expression:

~~~java
Main.class.getModule().getName()
~~~

returns `null` (an unnamed module has no module name). This **does not mean the class has no package**: `Main.class.getPackageName()` can still be `com.example.app`.

| Expression | In the example's classpath run |
|---|---|
| `Main.class.getName()` | `com.example.app.Main` |
| `Main.class.getPackageName()` | `com.example.app` |
| `Main.class.getModule().getName()` | `null` |

A simple program **does not require creating `module-info.java`**. Packages and the classpath still work in Java 17+ without turning an entire project into named modules.

## 5. Module: named unit, dependencies, and API boundaries

The Java Platform Module System (JPMS) lets you create a **named module**, described in a `module-info.java` file.

~~~java
module com.example.library {
    exports com.example.library;
}
~~~

and the consuming module:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Meaning:

- `module com.example.library` sets the **module name** to `com.example.library`. A module name can resemble a package prefix, but **module name and package name are two separate concepts**.
- `exports com.example.library;` allows modules that read the library module to **access eligible public types and public members** in that API package.
- `requires com.example.library;` declares that the app module **depends on / reads** the library module.
- `module-info.java` is a **module declaration**, not the `Main` class and not a replacement for `package` declarations in class files.

A module can contain **multiple packages**. Every package does not have to become its own module. A module only exposes packages it has `exports`-ed (or conditionally exposed via other syntax), so **a `public class` in an unexported package is not enough for another module to access it under JPMS rules**.

**Note:** `exports` exposes API at the Java level; `opens` enables deep reflective access in appropriate cases and is not equivalent to `exports`. This introductory lesson uses only `requires` and `exports`.

## 6. How does the module path differ from the classpath?

The **module path** specifies locations for the module system to find **named modules**, such as compiled module directories or modular JARs.

~~~bash
java --module-path out-mod --module com.example.app/com.example.app.Main
~~~

- `out-mod`: location of compiled named modules.
- `com.example.app` before `/`: the **module name** containing the entry point.
- `com.example.app.Main` after `/`: the **main class name**, which still has its own package.
- JPMS uses module descriptors to check `requires` and `exports` relationships.

Comparison table:

| Aspect | Classpath | Module path |
|---|---|---|
| Primary purpose | Locate classes/JARs of traditional applications | Locate named modules |
| Run command | `java -cp out-cp com.example.app.Main` | `java --module-path out-mod --module com.example.app/com.example.app.Main` |
| Module descriptor file required in the example? | No; `module-info.java` is omitted when compiling the classes | Yes, `module-info.java` for both named modules |
| Checks `requires`/`exports` | Does not enforce named module boundaries for classes on the classpath | Yes, under JPMS |
| Do packages exist? | Yes | Yes |

The module path **is not merely another way of writing the classpath**: placing code on the module path with a valid descriptor can change readability and accessibility between modules.

## 7. Shared source structure for both execution modes

To distinguish them accurately, we use **the same set of source files**, then compile in two modes. Structure:

~~~text
project/
└── src/
    ├── com.example.library/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── library/
    │               └── Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

In the example:

- There are **two named modules** to test module mode.
- There are **two packages** containing classes: `com.example.library` and `com.example.app`.
- When running in classpath mode, we compile only the two files `Greeter.java` and `Main.java`, **without compiling the two `module-info.java` files**.
- When running in module path mode, we compile the descriptors as well using `--module-source-path src`.

This makes it clear that packages still exist in both cases; the difference shows up in **how modules are declared/resolved** and **how the program is invoked**.

## 8. Complete Java 17+ source syntax

Create the exact **four files** following the structure in section 7.

**File 1 — `src/com.example.library/module-info.java`:**

~~~java
module com.example.library {
    exports com.example.library;
}
~~~

**File 2 — `src/com.example.library/com/example/library/Greeter.java`:**

~~~java
package com.example.library;

public final class Greeter {
    private Greeter() {}

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

**File 3 — `src/com.example.app/module-info.java`:**

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

**File 4 — `src/com.example.app/com/example/app/Main.java`:**

~~~java
package com.example.app;

import com.example.library.Greeter;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        System.out.println("main class=" + Main.class.getName());
        System.out.println("library class=" + Greeter.class.getName());
        System.out.println("message=" + Greeter.hello("Lan"));
        System.out.println("app module=" + Main.class.getModule().getName());
        System.out.println("library module=" + Greeter.class.getModule().getName());
    }
}
~~~

In both run modes, the two class-name lines keep the exact same packages. The two `module=...` lines highlight the difference: **unnamed module** when running via classpath and **named modules** when running via module path.

## 9. Approach 1 — compiling/running via classpath

Run from the `project` directory containing `src`. Use **JDK 17 or later**; no Maven/Gradle, external libraries, or preview features are needed.

**Bash (Linux/macOS):**

~~~bash
mkdir -p out-cp
javac --release 17 -encoding UTF-8 -d out-cp src/com.example.library/com/example/library/Greeter.java src/com.example.app/com/example/app/Main.java
java -cp out-cp com.example.app.Main
~~~

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force -Path out-cp | Out-Null
javac --release 17 -encoding UTF-8 -d out-cp .\src\com.example.library\com\example\library\Greeter.java .\src\com.example.app\com\example\app\Main.java
java -cp out-cp com.example.app.Main
~~~

The `javac` command lists only the **two source files with classes**, without any `module-info.java`. `out-cp` is the target directory holding classes by package name and serves as the **classpath root** at runtime.

### Exact expected stdout — classpath

~~~text
main class=com.example.app.Main
library class=com.example.library.Greeter
message=Hello, Lan
app module=null
library module=null
~~~

`Main.class.getModule()` and `Greeter.class.getModule()` both return the runtime module descriptor of their respective **unnamed module**; `getName()` returns `null`. Both classes still have their packages and fully qualified names as printed in the first two lines.

## 10. Approach 2 — compiling/running via named modules

Still from the `project` directory, using the exact same four source files above.

**Bash (Linux/macOS):**

~~~bash
mkdir -p out-mod
javac --release 17 -encoding UTF-8 --module-source-path src -d out-mod -m com.example.library,com.example.app
java --module-path out-mod --module com.example.app/com.example.app.Main
~~~

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force -Path out-mod | Out-Null
javac --release 17 -encoding UTF-8 --module-source-path src -d out-mod -m com.example.library,com.example.app
java --module-path out-mod --module com.example.app/com.example.app.Main
~~~

`--module-source-path src` specifies the source path containing module-named directories; `-m` selects which modules to compile; `-d out-mod` outputs compiled classes organized by module.

The output layout looks like:

~~~text
out-mod/
├── com.example.library/
│   ├── module-info.class
│   └── com/example/library/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

JPMS resolves `requires com.example.library` from the app and checks `exports com.example.library` from the library.

### Exact expected stdout — module path

~~~text
main class=com.example.app.Main
library class=com.example.library.Greeter
message=Hello, Lan
app module=com.example.app
library module=com.example.library
~~~

Compared to Approach 1, the **first three lines stay the same**, differing only in the module information of the classes. This illustrates that the same packaged source code can be compiled and run under two different deployment models.

## 11. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| A package is just a directory | A package is a namespace; directories are a file organization convention that usually matches package names |
| Just declaring `package` lets the JVM find the class automatically | You must compile and provide the appropriate class/JAR locations |
| `import` replaces classpath | Imports resolve names at compile time and do not supply library files |
| Using `-cp out-cp/com/example/app` with `com.example.app.Main` | The classpath must be the root containing `com/example/app`, i.e., `out-cp` |
| A module is a class | A module is a named unit containing packages and a descriptor |
| A module must have exactly one package | One module can contain multiple packages |
| If the package is `com.example.app`, the module must have the same name | The two names are independent concepts; matching names in the example is only for clarity |
| A `public class` in a package inside a named module is always visible from any module | The module must also export the package and satisfy readability rules |
| `requires` automatically imports classes into source code | You still need `import` or fully qualified names when using types from another package |
| `exports` turns a package into a classpath directory | `exports` declares a module's API and does not replace paths for locating modules |
| Running via classpath yet expecting `getModule().getName()` to print the module name declared in ignored `module-info.java` files | Classes compiled/placed on the classpath in the example belong to the unnamed module |
| Confusing `--module-path` with `--module-source-path` | Module path locates compiled named modules; module source path locates module source code for the compiler |

## 12. Which approach should you choose when starting Java?

- Small Java lessons and non-modular apps: **use clear packages and the classpath**, learning `javac -d out` and `java -cp out package.Main` first.
- When reading a project with `module-info.java`: identify the **module name**, basic `requires` and `exports`; know how to locate the module path and entry point.
- When using an IDE/Maven/Gradle: build tools may configure the classpath/module path automatically, yet the three concepts remain **distinct**.
- When encountering "cannot find symbol", "ClassNotFoundException", "NoClassDefFoundError", or module access errors: check in order **package/import names**, compilation/class lookup, and if using JPMS, **module descriptors/readability/exports**. Do not conclude from a single error message that package, classpath, and module are the same thing.

**Scope limits of this lesson:** JPMS also includes `opens`, `uses`, `provides ... with`, automatic modules, strong encapsulation, and mixed classpath/module path scenarios. At an introductory level, focus on the core roles of `requires` and `exports` without building complex module systems prematurely.

## 13. Exercises with answers

**A.** What are the simple name and package of `com.example.data.User`?  
**Answer:** simple name `User`, package `com.example.data`.

**B.** Given `Greeter.class` at `out-cp/com/example/library/Greeter.class`, what should the classpath root be?  
**Answer:** `out-cp`, not `out-cp/com/example/library`.

**C.** Must the two packages `com.example.app` and `com.example.library` reside in two separate modules?  
**Answer:** **No**; one module can contain multiple packages. This example uses two modules to illustrate `requires` and `exports`.

**D.** Which `module-info.java` declares that the application module depends on the library?

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

**E.** If the library removes the line `exports com.example.library;` while the app still needs to publicly reference `Greeter` under the named-module model, is there a problem?  
**Answer:** **Yes**. The app cannot directly access APIs in an unexported package under JPMS rules, even though `Greeter` is declared `public`.

**F.** In the example's classpath run, what does `Main.class.getModule().getName()` return?  
**Answer:** `null`, because the class belongs to the unnamed module.

**G.** Why doesn't `import com.example.library.Greeter;` replace `requires com.example.library;` in the named module `com.example.app`?  
**Answer:** `import` lets you write short names in source code; `requires` declares readability/dependency at the module level. They serve two different responsibilities.

## 14. Checklist and conclusion

- [ ] Distinguish `package`, `classpath`, and `module` by function.
- [ ] Understand that a fully qualified type name consists of package + simple name.
- [ ] Know the classpath root of classes compiled into a package directory structure.
- [ ] Know that `import` does not supply missing classes/JARs.
- [ ] Recognize `module-info.java`, `module`, `requires`, and `exports`.
- [ ] Understand that a named module can include multiple packages.
- [ ] Distinguish the classpath's unnamed module from named modules run via the module path.
- [ ] Know the purpose of `--module-source-path` when compiling module sources.
- [ ] Know the entry point syntax `java --module-path ... --module name/package.Main`.
- [ ] Run the same two source classes in classpath mode and the four-file set in module path mode, and verify stdout.
- [ ] Avoid treating package, classpath, and module as three names for a single feature.

**Conclusion:** **Packages name and group types**, the **classpath specifies where to find classes/JARs**, and **modules declare dependency units and exposed API packages**. In Java 17+, you can start with packages + classpath and learn `module-info.java` when encountering modular applications; understanding each concept's exact responsibility makes compiler/runtime errors clearer and project organization cleaner.