# Packages Organize Type Names and Prevent Name Collisions — Java 17+

## 1. A package is a namespace for Java types

A **package** is a **namespace** and a way to group related types in a Java application: class, interface, enum, and record. When a project has many classes, packages help readers know which feature a class belongs to and allow types with the **same simple name** to coexist validly if they are in different packages.

For example:

~~~text
com.example.sales.Report
com.example.support.Report
~~~

Both are classes with the simple name `Report`, but their **fully qualified names have different packages**. Therefore, Java can distinguish a sales report from a support report without forcing every class to have a unique simple name across the entire project.

| Concept | Example | Meaning |
|---|---|---|
| Package name | `com.example.sales` | The namespace containing the type |
| Simple name | `Report` | The class name at its declaration site |
| Qualified type name | `com.example.sales.Report` | Specifies the exact type along with its package |
| Another qualified name | `com.example.support.Report` | A different type, even though the simple name is the same |

The package name is declared **in Java code**, not automatically derived from the directory name. Source directories are usually arranged to match the namespace for convenient building and management.

## 2. Namespaces determine type identity

The two types `com.example.sales.Report` and `com.example.support.Report` share the same **simple name** `Report` but have different fully qualified names, so they are **two distinct types**. Given the source code:

~~~java
package com.example.sales;

public class Report {
    public String kind() { return "sales"; }
}
~~~

`package` defines the namespace and is placed before `import` declarations and top-level types. By convention, packages are named in lowercase by domain or reversed domain name; source structure and full syntax are practiced in the next lesson.

## 3. Source tree corresponding to package names

~~~text
project/
└── src/
    └── com/example/
        ├── sales/Report.java
        ├── support/Report.java
        └── app/Main.java
~~~

Both `Report.java` files coexist thanks to the two different namespaces. The package name is determined by the declaration in code; **matching directories to packages** is a practical organization convention that helps tools locate source files. `javac -d out` creates the `.class` tree by package inside `out`; `out` is the classpath root when running.

## 4. Two types with the same simple name still do not collide

In `src/com/example/support/Report.java`, another `public class Report` can be declared:

~~~java
package com.example.support;

public class Report {
    public String kind() { return "support"; }
}
~~~

The condition to avoid collision is **having different fully qualified type names**. If two top-level types have the same fully qualified name in the same compilation environment, they cannot be treated as two separate classes sharing the same name. The two types in the example also carry their own behavior: `kind()` returns `"sales"` and `"support"`, respectively.

## 5. Using both classes in a third source file

~~~java
package com.example.app;

import com.example.sales.Report;

class Main {
    Report sales = new Report();
    com.example.support.Report support =
            new com.example.support.Report();
}
~~~

Importing lets you shorten the name of **one specific type**; the other class uses its qualified name. An import does not change a class's identity, copy code, create objects, or add libraries to the classpath. Java does not support `import ... as ...`.

## 6. Sharing a package prefix still means different packages

`com.example`, `com.example.sales`, and `com.example.sales.audit` are not the same package just because their names share a nested prefix. Therefore, `import com.example.*;` does not automatically import `com.example.sales.Report`. Packages have a naming relationship, but they do not inherit package-private access. The lessons on wildcard imports and subpackages will analyze this limitation in detail.

## 7. Grouping types by responsibility

`sales` and `support` represent functional areas, helping readers find the right type. A package does not replace API design or modules; it only provides a namespace and participates in certain access rules. Choose packages by related responsibility and keep naming consistent instead of dumping every class into one large package.

## 8. Packages and access levels are related but serve different roles

Packages primarily organize **namespaces**. Java also uses the concept of **same package** when checking certain access permissions.

| Declaration | Basic meaning |
|---|---|
| `public class Report` | Can be referenced from other packages if access/classpath/module conditions are met |
| `class Helper` (no modifier, top-level) | **Package-private**: only types in the same package are allowed access |
| `public void print()` | Public method when the caller has access to both the class and the method |
| `void internal()` (no modifier) | Package-private method |
| `private int count` | Private member; other top-level classes in the same package cannot automatically access it |

For example, a class `com.example.sales.InternalHelper` not declared `public` at the top level will **not be accessible** from `com.example.support`. The names `com.example.sales` and `com.example.sales.audit` are also not the **same package** under package-private rules.

Packages do not replace `private`, `public`, `protected`, or Java module rules. At the same time, sharing a namespace does not mean "having an absolute security mechanism": it is a language rule for organizing types and checking access rights.

## 9. Complete, runnable Java 17+ example

Create **the exact three files** following the directory structure in section 3. Each class has its own package and public class; the two `Report.java` files do not conflict because their fully qualified names differ.

**File 1 — `src/com/example/sales/Report.java`:**

~~~java
package com.example.sales;

public final class Report {
    private final String title;

    public Report(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("blank sales title");
        }
        this.title = title.strip();
    }

    public String describe() {
        return "sales:" + title;
    }
}
~~~

**File 2 — `src/com/example/support/Report.java`:**

~~~java
package com.example.support;

public final class Report {
    private final String ticket;

    public Report(String ticket) {
        if (ticket == null || ticket.isBlank()) {
            throw new IllegalArgumentException("blank ticket");
        }
        this.ticket = ticket.strip();
    }

    public String describe() {
        return "support:" + ticket;
    }
}
~~~

**File 3 — `src/com/example/app/Main.java`:**

~~~java
package com.example.app;

import com.example.sales.Report;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        Report sales = new Report(" Q1 ");
        com.example.support.Report support =
                new com.example.support.Report("Ticket-7");

        System.out.println("sales=" + sales.describe());
        System.out.println("support=" + support.describe());
        System.out.println("sales type=" + sales.getClass().getName());
        System.out.println("support type=" + support.getClass().getName());
        System.out.println("simple names="
                + sales.getClass().getSimpleName() + ","
                + support.getClass().getSimpleName());
        System.out.println("same class="
                + (sales.getClass() == support.getClass()));
        System.out.println("sales package="
                + sales.getClass().getPackageName());
        System.out.println("support package="
                + support.getClass().getPackageName());
    }
}
~~~

`Main` uses `import com.example.sales.Report;` for sales and the **fully qualified type name** for support. The two variables hold objects of different types, even though both classes have the simple name `Report`.

### Compiling and running via CLI

**Requirements:** JDK 17 or later. Run from the project directory containing the `src` folder. Use `-d out` to compile `.class` files into the package path inside `out`. No Maven/Gradle, external libraries, or preview features are required.

**Bash (Linux/macOS):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/com/example/sales/Report.java src/com/example/support/Report.java src/com/example/app/Main.java
java -cp out com.example.app.Main
~~~

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out .\src\com\example\sales\Report.java .\src\com\example\support\Report.java .\src\com\example\app\Main.java
java -cp out com.example.app.Main
~~~

The compiled files are located at:

~~~text
out/
└── com/
    └── example/
        ├── sales/Report.class
        ├── support/Report.class
        └── app/Main.class
~~~

`out` is the **classpath root**. When running, use `com.example.app.Main` (the class name with its package), not `java Main` or `java -cp out Main`.

### Exact expected stdout

~~~text
sales=sales:Q1
support=support:Ticket-7
sales type=com.example.sales.Report
support type=com.example.support.Report
simple names=Report,Report
same class=false
sales package=com.example.sales
support package=com.example.support
~~~

**Explanation:** The two types have the same simple name, but `getClass().getName()` outputs different fully qualified names, and `same class=false`. `getClass().getPackageName()` confirms the two namespaces. Each class executes its own `describe()` behavior.

## 10. Common mistakes

| Mistake | Why is it wrong? | How to fix |
|---|---|---|
| Treating two `Report` classes from two packages as one type | Different packages mean different types | Use the fully qualified name to distinguish them |
| Creating two top-level `Report` classes in the same package | Duplicate type name in the same namespace | Rename one type or move it to an appropriate package |
| Putting two single-type imports for both `Report` classes in the same file | Competing simple names cause a compile error | Import one, and write the fully qualified name for the other |
| Thinking `import com.example.*;` includes `com.example.sales` | Wildcards do not recursively import packages sharing a prefix | Import the exact package |
| Placing `package` after `import` or inside a class | Violates compilation unit syntax | Place `package` at the top of the file |
| Naming the file `Foo.java` while declaring `public class Bar` | Violates the file-naming rule for a public top-level type | Name the file `Bar.java` |
| Running `java Main` when the class is `com.example.app.Main` | The launcher cannot find the right class name | `java -cp out com.example.app.Main` |
| Setting the classpath to `out/com/example/app` | Wrong classpath root for the package path | Use `-cp out` |
| Believing the directory determines the package regardless of source declaration | The namespace comes from the Java declaration | Keep directory paths and package names in sync |
| Treating `com.example.sales` and `com.example.sales.audit` as the same package | Sharing a prefix does not mean being the same package | Identify the exact package name |
| Thinking `import` makes the JVM run a constructor immediately | Import is a compile-time name lookup mechanism | Objects are only created by corresponding instantiation behavior |

## 11. Exercises and answers

**A.** Can two types `org.acme.account.User` and `org.acme.audit.User` exist in the same program?  
**Answer:** **Yes**, because they belong to different packages and have different fully qualified type names.

**B.** Given `com.example.sales.Report`, what are the simple name and the package?  
**Answer:** The simple name is `Report`; the package is `com.example.sales`.

**C.** If a file already has `import com.example.sales.Report;`, how do you instantiate support's `Report`?  
**Answer:**

~~~java
com.example.support.Report support =
        new com.example.support.Report("Ticket-7");
~~~

**D.** Does `import com.example.*;` automatically import the class `com.example.sales.Report`?  
**Answer:** **No**. You must import `com.example.sales.Report` directly or use its fully qualified name.

**E.** After compiling `com.example.app.Main` into `out/com/example/app/Main.class`, what command should you run from the project directory?  
**Answer:**

~~~bash
java -cp out com.example.app.Main
~~~

**F.** In package `com.example.sales`, can a top-level `class Helper` without `public` be called from `com.example.support`?  
**Answer:** **No**, because `Helper` has package-private access and the two packages are different.

## 12. Checklist and conclusion

- [ ] Understand that packages create **namespaces** and group related types.
- [ ] Distinguish **simple names** from **fully qualified type names with packages**.
- [ ] Explain why two `Report` classes in two packages do not conflict.
- [ ] Place the `package ...;` declaration in the right position with valid syntax.
- [ ] Organize source directories to match package names.
- [ ] Use `import` or a fully qualified name when using types from another package.
- [ ] Know that Java has no `import ... as ...` and no "last import wins" rule.
- [ ] Understand that `package.*` does not include other packages sharing the same prefix.
- [ ] Recognize package-private access and distinguish it from the namespace role.
- [ ] Compile with `javac -d out` and run using the fully qualified main class name.
- [ ] Run all three Java 17+ files and verify the exact stdout.

**Conclusion:** Packages organize code into **distinct namespaces**. `com.example.sales.Report` and `com.example.support.Report` do not collide in fully qualified type name even though both are referred to shortly as `Report`. To use the right class, keep package names, source paths, `import`/qualified names, and the classpath consistent when compiling and running programs.