# Organizing Classes with `package` and Using `import` in Java

## Learning Objectives

After this lesson, you will be able to:

- Explain what a `package` is, why classes need to be grouped by functionality, and how package names relate to a project's directory structure.
- Declare a package in the right position in a `.java` file, recognize a class's fully qualified name, and know how to run a class inside a package.
- Distinguish single-type `import` (`single-type import`), on-demand `import` (`on-demand import`), `static import`, and how to use fully qualified names without importing.
- Understand `public` and package-private access scopes, as well as the boundary between a package and a subpackage.
- Independently compile and run a Java 17+ project with multiple files/classes/packages, and diagnose common class organization, import, and classpath errors.

## 1. `package`: Placing Classes into a Namespace

Java allows multiple classes to coexist in a program. As the number of classes grows, if all classes have simple names such as `User`, `Service`, and `Utils`, organizing them and avoiding name collisions becomes difficult.

A **package** is Java's way of grouping related types (classes, interfaces, enums, records, annotations, etc.) into a **namespace**. For example:

- `com.example.school.model.Student`: student model.
- `com.example.school.service.StudentService`: business logic processing service.
- `com.example.school.app.Main`: program entry point.

For the class `com.example.school.model.Student`:

- `Student` is the **simple name**.
- `com.example.school.model` is the **package name**.
- `com.example.school.model.Student` is the **fully qualified name**.

The two classes `com.example.school.model.Student` and `com.example.school.api.Student` can share the same simple name `Student` because they belong to two different packages. When using both types at the same time, the developer must specify which type is being referenced.

Packages help categorize source code, establish default access boundaries, and avoid name conflicts. However, a package **does not automatically become a separate library, does not install dependencies on its own, and is not a security mechanism**.

### Package Naming Conventions

- Typically use **lowercase**, with components separated by dots: `com.example.school.model`.
- Projects with an organization-managed domain name typically use the reversed domain name to reduce the chance of naming collisions, for example `org.example.project`. `com.example` is only an illustrative name.
- Group by clear responsibilities, such as `model`, `service`, and `app`, rather than placing all classes into one very large package.
- Names are case-sensitive; `com.example.Model` is different from `com.example.model`. You should avoid naming a package the same as a common type name, which can cause confusion.
- **Do not use** Java keywords (`class`, `public`, `package`, etc.) as package components. Each component must be a valid identifier.

Packages whose names share the same prefix do not necessarily have any special access relationship. For example, `com.example.school` and `com.example.school.model` are **two different packages**, not parent/child in the sense of inheriting access permissions.

## 2. Declaring `package` in a Source File

Syntax:

~~~java
package com.example.school.model;

public class Student {
}
~~~

This is a minimal `Student.java` file that can be compiled independently. There can be at most one `package` declaration in each compilation unit (a standard Java source file). When present, `package` must appear **before `import` statements and type declarations**, except for whitespace or comments at the top of the file.

Typical structure:

~~~java
package com.example.app;

import java.util.List;
import static java.lang.Math.max;

public class Main {
    // Fields, constructors, and methods
}
~~~

The snippet above illustrates the ordering of elements; the body of `Main` does not yet contain a `main` method to run directly.

If a file does **not** have a `package` statement, its top-level types belong to the **unnamed package** (commonly called the *default package*). This can be convenient for a single-file learning example, but it should not be used to organize a multi-package application. In particular, code in a **named package** cannot import or directly reference a top-level type in the unnamed package by either its simple name or its fully qualified name.

A common filename rule with `javac`: a `public` top-level type must be saved in a file with the exact same name and casing, such as `public class Student` in `Student.java`. A Java file may contain additional non-`public` top-level types, but splitting large types into separate files is usually easier to read and maintain.

## 3. Directory Structure Matching Packages

Java projects typically place source files according to the components of their package names. A small example with two packages and three classes:

~~~text
school-demo/
├── src/
│   └── com/
│       └── example/
│           └── school/
│               ├── model/
│               │   ├── Student.java
│               │   └── StudentLabels.java
│               └── app/
│                   └── Main.java
└── out/                 (created during compilation)
~~~

The path `src/com/example/school/model/Student.java` corresponds to the line `package com.example.school.model;`. The `src` directory is the **source root** we chose; it is not part of the package name.

This is an important organizational convention for IDEs, build tools, and locating source files. When passing filenames directly to `javac`, the source file location is not always enforced by the compiler to match the package, but you should organize it properly from the start. When compiling with `-d out`, the `.class` files are placed under the corresponding package structure inside `out`.

## 4. Complete Java 17+ Example: Multiple Packages Sharing Classes

This example illustrates three points: classes in the same package can refer to each other by name without importing; classes in another package are imported via their fully qualified names; and `static` members can also be imported.

### File 1 — `src/com/example/school/model/Student.java`

~~~java
package com.example.school.model;

public final class Student {
    private final String name;

    public Student(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

`Student` is a `public` top-level class in the `com.example.school.model` package. Its constructor and `name()` method are also declared `public` so that code from other packages can use them. The `name` field is `private`, helping to hide internal state.

### File 2 — `src/com/example/school/model/StudentLabels.java`

~~~java
package com.example.school.model;

public final class StudentLabels {
    private StudentLabels() {
        // Do not instantiate: provides static utilities only
    }

    public static String display(Student student) {
        return "Student: " + student.name();
    }
}
~~~

`StudentLabels` and `Student` are in the **same package**, so `StudentLabels.java` can use the name `Student` **without** `import com.example.school.model.Student;`. Code is not permitted to access `student.name` directly because that field is `private`; it calls the `public name()` method.

### File 3 — `src/com/example/school/app/Main.java`

~~~java
package com.example.school.app;

import com.example.school.model.Student;
import com.example.school.model.StudentLabels;
import java.util.List;

import static java.lang.Math.max;

public class Main {
    public static void main(String[] args) {
        Student student = new Student("Lan");

        System.out.println(StudentLabels.display(student));

        List<String> topics = List.of("package", "import");
        System.out.println("Topics: " + String.join(", ", topics));

        System.out.println("Max: " + max(3, 8));

        System.out.println("Day: " + java.time.DayOfWeek.MONDAY);
    }
}
~~~

Notable lines:

- The two `import com.example.school.model....` statements allow writing `Student` and `StudentLabels` instead of always using their fully qualified names.
- `import java.util.List;` brings the `List` type name into the simple-name scope of this file. `List.of(...)` creates an unmodifiable list in Java 9+.
- `import static java.lang.Math.max;` allows calling `max(3, 8)` instead of `Math.max(3, 8)`.
- `String` and `System` belong to `java.lang`, a package automatically imported on demand by Java; you do not have to write `import java.lang.String;`.
- `java.time.DayOfWeek.MONDAY` uses the **fully qualified name** without needing an `import java.time.DayOfWeek;` statement.

### Compiling and Running

Open a terminal in the **`school-demo`** directory, where the `src` directory is located. The commands below work in both Bash and PowerShell; `mkdir out` is only needed if `out` does not already exist:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/com/example/school/model/Student.java src/com/example/school/model/StudentLabels.java src/com/example/school/app/Main.java
java -cp out com.example.school.app.Main
~~~

Output from the **`java` command**:

~~~text
Student: Lan
Topics: package, import
Max: 8
Day: MONDAY
~~~

Explanation:

1. `javac` compiles all three files together, so it can locate the mutually dependent types.
2. `-encoding UTF-8` specifies how to decode the source files; `-d out` specifies the root directory for `.class` files. The `out` directory must already exist.
3. After compilation, `out/com/example/school/model/` contains `Student.class` and `StudentLabels.class`; `out/com/example/school/app/` contains `Main.class`.
4. `java -cp out` sets the **classpath root** to `out`; `com.example.school.app.Main` is the **fully qualified name of the class containing `public static void main(String[] args)`**. Running `java Main` will not find the right class because the class belongs to a named package.

You can compile `Main.java` separately if its dependent classes have already been compiled and are on the appropriate classpath; in this example, compiling all three files in a single command is the easiest way to verify.

## 5. How Does `import` Work?

The `import` statement is a **compile-time name resolution** mechanism. It allows writing type names or `static` members in a shorter form within a source file. It does **not**:

- Create a new object or invoke a constructor.
- Copy source code or download libraries from the Internet.
- Automatically make `private`/package-private classes accessible.
- Replace providing the dependent JARs/modules on the appropriate classpath/module path.
- Automatically turn packages with similar names into a single package.

`import` statements are declared at the **source-file level**, after `package` and before top-level types; do not place them inside a class or method body.

### 5.1. Importing a Specific Type: Single-Type Import

~~~java
import java.util.List;
import java.util.ArrayList;
~~~

Then you can write:

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
~~~

This is an **illustrative snippet** used inside a method body or an initializer block of a class, not a standalone program. Without importing, you can write it in full:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Lan");
~~~

Both forms have equivalent meaning here. Importing simply makes names clearer and more concise; the compiler still needs to know what type `java.util.List` is. In production code, **single-type import** is generally easier to read and makes dependencies easier to control when the number of used types is not excessively large.

### 5.2. On-Demand Import: Type-Import-on-Demand

~~~java
import java.util.*;
~~~

This allows using the simple names of **accessible types belonging directly to `java.util`** when those names are referenced, such as `List`, `Map`, and `ArrayList`.

However, `*` is **not recursive**: `import java.util.*;` does not import types belonging to `java.util.concurrent`, because `java.util.concurrent` is a separate package. To use `ExecutorService` by its simple name, you must import `java.util.concurrent.ExecutorService` or `java.util.concurrent.*`.

Java **does not support** the form `import com.example.**;` to include all subpackages, nor does it have an `import ... as Alias` syntax like some other languages.

### 5.3. Static Import: Importing `static` Member Names

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
~~~

Then, inside a method body, you can write:

~~~java
double circumference = 2 * PI * 3;
int larger = max(5, 9);
System.out.println(circumference);
System.out.println(larger);
~~~

This illustrative snippet outputs to stdout:

~~~text
18.84955592153876
9
~~~

`PI` is a `static` field of `Math`; `max` is a `static` method of `Math`. You can replace them with `Math.PI` and `Math.max(...)` without static imports. The form `import static java.lang.Math.*;` also exists, but selective importing helps readers recognize the source of short names. **Static import does not apply to instance fields/methods** because those members require a receiver object for the call.

### 5.4. Automatically Available Packages

In a compilation unit belonging to a named package, the names of accessible types in the same package can be used directly; types in `java.lang` are also implicitly imported on demand. Therefore:

- `StudentLabels` uses `Student` without an import because both are in `com.example.school.model`.
- `Main` uses `String` and `System` without declaring an import for `java.lang`.
- However, in `Main`, `Student` belongs to a **different package**, so you need to import it or use its fully qualified name.

You can import an accessible nested type via its enclosing type name, such as `import java.util.Map.Entry;`, if you want to use `Entry` directly. This is a **member type**, not a `Map` subpackage.

## 6. Name Collisions When Importing: Quick Identification

`package` allows two types to have the same simple name but different fully qualified names, such as `java.util.Date` and `java.sql.Date`. Within the same compilation unit, **you cannot single-type import both**:

~~~java
import java.util.Date;
import java.sql.Date; // Error: two single-type imports with the same name Date.
~~~

A common approach is to import only the frequently used type and write the **fully qualified name** for the second type; for example, `Date` and `java.sql.Date` at the usage site. If you use two on-demand imports, `java.util.*` and `java.awt.*`, the name `List` can become ambiguous. Explicitly choose `java.util.List` or import the specific type.

The key takeaway in this lesson: importing only affects **name usability within the source file**; it does not change package identity or access permissions. Handling *simple names*, *qualified names*, shadowing, and ambiguity cases is the dedicated focus of the lesson on class name collisions.


## 7. Packages and Access Control

Packages are an important boundary in **Java's access checking**. Several concepts should be distinguished:

| Element | Can Be Used from Another Package? |
| --- | --- |
| `public` top-level type | Yes, if the type is visible and other access/module conditions are satisfied |
| Top-level type without `public` (package-private) | Not directly accessible from another package |
| `public` member of an accessible type | Yes, under normal access conditions |
| Member without an access modifier (package-private) | Only from types in the same package |
| `private` member | Restricted by Java's private rules; does not become public when imported |
| `protected` member | Accessible within the same package and in appropriate inheritance cases in another package |

Note: since Java 11, `private` rules also involve nested classes belonging to the same *nest*; for learning packages, the important thing is that `import` does not alter access permissions.

For example, the following type **does not have `public`**:

~~~java
package com.example.school.model;

class InternalCode {
    static String value() {
        return "internal";
    }
}
~~~

Code in `com.example.school.model` can use `InternalCode` if normal access conditions are met. Code in `com.example.school.app` cannot directly reference this package-private type via `import`, even if attempting to use its fully qualified name. Even `com.example.school.model.extra` is a **different package**, so it does not automatically inherit the package-private access permissions of `com.example.school.model`.

With the `public Student` type in the main example, if `public` is omitted from the constructor, code in the `app` package cannot call `new Student("Lan")` on a constructor that only has package-private access. To instantiate an object from another package, both the type and the constructor/method you need to use must be accessible.

**Limitation with the Java module system:** in an application using **named modules** (Java 9+), access also depends on `requires` and `exports` in `module-info.java`. Being `public` does not mean every external module can see that package. An import does not replace module declarations. The examples in this lesson use the standard classpath and do not require module configuration.

## 8. Package, Classpath, and Directory: Three Different Concepts

Beginners often confuse `package`, `import`, and `classpath`:

| Concept | Role |
| --- | --- |
| `package com.example.school.app;` | Places the class in the `com.example.school.app` namespace |
| `import com.example.school.model.Student;` | Allows the compiler to resolve the short name `Student` in the file |
| `-cp out` / `-classpath out` | Tells the tool where to find compiled classes/libraries at runtime (and optionally at compile time with `javac -cp`) |
| `-d out` | Tells `javac` where to place the generated `.class` files |
| Dependency/JAR/module path | Provides the actual required classes from external libraries/modules |

If `Main.class` is located at `out/com/example/school/app/Main.class`, Java needs **`out`** as the classpath root, and then uses the class name **`com.example.school.app.Main`**. Do not pass the file path `out/com/example/school/app/Main.class` in place of the class name to the `java` command.

If you use an IDE, Maven, or Gradle, those tools typically manage source roots, the classpath, and compilation for you. However, the fundamentals of package names, imports, access control, and fully qualified names remain the same. A syntactically valid import can still fail if the library defining that type has not been added to the corresponding dependencies.

## 9. Common Errors and How to Fix Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `class, interface, enum, or record expected` around `import` | Placing `import` in the wrong position, such as inside a class or after a type declaration | Place `package` at the top, followed by `import`, and finally type declarations |
| `package ... does not exist` | Wrong package name, missing source/compiled class files, or missing classpath/dependency | Verify the package in the file, input paths, and dependencies |
| `cannot find symbol: class Student` | Missing import, wrong name, wrong package, or the compiler cannot locate the type | Check the fully qualified name, imports, and classpath/source files |
| `... is not public ... cannot be accessed from outside package` | The top-level type is package-private | Use an appropriate public API, or adjust the design/access modifier if genuinely needed |
| `... has private access` | Accessing a `private` field or method directly | Use the class's public API instead of trying to import it |
| `reference to List is ambiguous` | Two on-demand imports bring in types with the same name | Import the specific type or use its fully qualified name |
| `class Main is public, should be declared in a file named Main.java` | Filename does not match the `public` type | Rename the file to `Main.java` with exact casing |
| `Could not find or load main class ...` | Wrong fully qualified name when invoking `java`, wrong classpath root, or not yet compiled | Run `java -cp out com.example.school.app.Main` after compiling successfully |
| Importing `java.util.*` but `ExecutorService` cannot be found | `*` does not import subpackages | Import `java.util.concurrent.ExecutorService` |
| Import is present, but running throws `NoClassDefFoundError` | The dependent class is missing from the runtime classpath/module path, or there is a linkage issue | Check the actual JARs/modules at runtime; imports only assist compilation |

When diagnosing issues, first read the **first error** from the compiler, then check the package name and classpath directory. One import error can trigger many cascading errors. You should not fix every reported error line before addressing the root cause.

## 10. Self-Check Questions

**Question 1.** The file `src/org/example/model/Book.java` has the line `package org.example.model;`. What is the fully qualified name of the top-level `public class Book`?  
**Answer:** `org.example.model.Book`. `src` is only the source root and is not part of the fully qualified name.

**Question 2.** Can `com.example.model.Book` automatically access a package-private type in `com.example.model.internal`?  
**Answer:** No. The two package names are different, regardless of any prefix relationship.

**Question 3.** Does `import java.util.*;` allow using `ExecutorService` directly?  
**Answer:** No. You must import `java.util.concurrent.ExecutorService` or use its fully qualified name because `java.util.concurrent` is a different package.

**Question 4.** Once you have `import com.example.school.model.Student;`, does the import statement create a `Student` object?  
**Answer:** No. An import only shortens how a type name is referenced. An object is created when executing an instantiation operation such as `new Student("Lan")`.

**Question 5.** If you want to run `Main.class` compiled at `out/com/example/school/app/Main.class`, what command should you type in the project root directory?  
**Answer:** `java -cp out com.example.school.app.Main`.

**Question 6.** In the complete example, why can `StudentLabels` use `Student` without an import, whereas `Main` needs an import?  
**Answer:** `StudentLabels` belongs to the same package `com.example.school.model` as `Student`; `Main` belongs to `com.example.school.app`, a different package.

## Key Takeaways

- **`package` determines which namespace a class belongs to**; package names typically mirror the source directory structure and determine a class's fully qualified name.
- **`import` only lets you use short names in a Java file**; it does not load libraries, create objects, or change access permissions.
- Types in the **same package** and types in `java.lang` can be referenced by their simple names without writing regular imports.
- **A subpackage is a different package**; wildcard imports are not recursive, and package-private access does not extend to subpackages.
- **Compiling and running** require the correct source files, output root/classpath, and fully qualified class name; a syntactically valid import still does not replace an actual dependency.
