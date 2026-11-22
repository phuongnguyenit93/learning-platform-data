# Simple Names, Fully Qualified Names, and Handling Class Name Conflicts in Java

When a program has many classes, the question “Which class is `Student`?” cannot be answered with just the single word `Student`. Java organizes classes by **package** and has rules to determine which type a **simple name** refers to. Understanding these rules helps you write `import` statements correctly, distinguish classes with the same name from two libraries, read compiler errors, and avoid conflicts as a project grows.

This lesson focuses on class names and declared reference types in Java; similar rules apply in many places to interfaces, enums, records, and annotations. The examples use **Java 17 or later**.

## 1. Simple Names and Fully Qualified Names

Given the declaration:

~~~java
package com.example.school;

public class Student {
}
~~~

- **Simple name:** `Student` — a single identifier without the package part.
- **Fully qualified name:** `com.example.school.Student` — consists of the package name and the top-level class name.
- **Package name:** `com.example.school` — not a class, but the namespace containing the class.

The following two lines can both refer to the same class, if `Student` at that location is resolved by Java to `com.example.school.Student`:

~~~java
Student student = new Student();
com.example.school.Student another = new com.example.school.Student();
~~~

*This is an illustrative snippet placed inside a scope that already has access to the `Student` class; the two statements by themselves are not a complete Java file.*

The first form is short and easy to read, but depends on the scope of the name `Student`. The second form explicitly specifies the package, so it is useful when multiple classes with the same name appear in the program.

| Form | Example | Meaning |
| --- | --- | --- |
| Simple name | `Student` | Java determines the appropriate type based on declarations, scope, and imports |
| Fully qualified name of a top-level class | `com.example.school.Student` | Explicitly specifies which package the `Student` class belongs to |
| Simple name of a member class | `Entry` | Can be used when the member type is in scope or suitably imported |
| Hierarchical name of a member class | `java.util.Map.Entry` | The canonical name of the member type `Entry` in `Map` |

In Java documentation, a **qualified name** is a name whose components are joined by dots; the **fully qualified name** and **canonical name** usually coincide for a named top-level class in a package. For nested types, you also need to distinguish the **binary name** (see Section 8); not every string returned by reflection APIs is a valid name to write directly in source code.

## 2. Why Can Multiple Classes Have the Same Name?

For example, a project has two classes:

~~~text
school.Student
company.Student
~~~

They both have the **simple name** `Student`, but reside in **two different packages**, and therefore are two different types. In a program, both can be used validly:

~~~java
school.Student learner = new school.Student("An");
company.Student employee = new company.Student("Binh");
~~~

Two objects are not of the same type just because their simple names are the same. The compiler must know the **exact class** to check constructors, methods, fields, access permissions, and assignments.

Conversely, you cannot define two top-level classes with the **same name in the same package** of a program: for example, two separate declarations that are both `school.Student` will cause a type conflict at compile time or in source organization. Nor can you declare two top-level classes both named `Student` in the same compilation unit and treat them as two separate types.

Packages help partition the namespace. Dots between package components indicate a hierarchical naming structure, but do not mean that a subpackage automatically inherits access permissions or types from its parent package.

## 3. Simple Name Resolution: Why Does the Compiler Choose Exactly One Type?

A file can declare a `package`, followed by `import` statements before the class declaration. What matters in this lesson is **which type `Student`, `List`, or `Date` refers to at each location**, rather than re-teaching directory organization.

Common sources of names include: types declared in the lexical scope (member/local types), types in the same package, `single-type import`, `type-import-on-demand`, and types in `java.lang`. They are **not a fixed-order fallback algorithm**: the JLS defines specific rules for scope, shadowing, imports, and ambiguity. For example, a single-type import can take precedence over on-demand imports where there is no closer conflicting declaration.

~~~java
import java.util.List;
import java.awt.*;

class NameResolution {
    List<String> names; // java.util.List, not java.awt.List
}
~~~

This is a valid illustrative class; it has no `main` to run. `java.awt.*` does not by itself turn `List` into an ambiguous name when there is an explicit single-type import `java.util.List`.

Conversely, **two single-type imports** for two different types with the same simple name are rejected immediately at compile time, while two on-demand imports can lead to ambiguity when the colliding name is actually used. When you need two types with the same name, choose the fully qualified name for at least one type.

Imports apply only within the **compilation unit in which they are declared**: importing `school.Student` in one file does not make another file in the same package automatically import `school.Student`. A wildcard import `java.util.*` also does not include the subpackage `java.util.concurrent`. These details help you accurately diagnose “cannot find symbol” or “reference is ambiguous” instead of adding imports arbitrarily.


## 4. Complete Example: Two Student Classes in Different Packages

Create the four directories/files according to this structure:

~~~text
name-demo/
└── src/
    ├── school/
    │   └── Student.java
    ├── company/
    │   └── Student.java
    └── app/
        └── NameConflictDemo.java
~~~

### File `src/school/Student.java`

~~~java
package school;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String description() {
        return "School: " + name;
    }
}
~~~

### File `src/company/Student.java`

~~~java
package company;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String description() {
        return "Company: " + name;
    }
}
~~~

Both files declare `public class Student`, but they are in two separate packages and have **two different fully qualified names**. Java allows both to exist in the same application.

### File `src/app/NameConflictDemo.java`

~~~java
package app;

import school.Student;

public class NameConflictDemo {
    public static void main(String[] args) {
        Student learner = new Student("An");
        company.Student employee = new company.Student("Binh");

        System.out.println(learner.description());
        System.out.println(employee.description());
        System.out.println(learner.getClass().getName());
        System.out.println(employee.getClass().getName());
    }
}
~~~

Here, `import school.Student;` causes `Student` in the first two lines of `main` to be interpreted as `school.Student`. To use the other type in the same file, write `company.Student` when declaring the variable and creating the object.

Open a terminal in the **`name-demo`** directory and run:

~~~bash
javac -encoding UTF-8 -d out src/school/Student.java src/company/Student.java src/app/NameConflictDemo.java
java -cp out app.NameConflictDemo
~~~

Exact stdout:

~~~text
School: An
Company: Binh
school.Student
company.Student
~~~

Command explanation:

- `javac` compiles the three files; `-d out` places the `.class` files into the output directory tree by package, for example `out/school/Student.class`, `out/company/Student.class`, `out/app/NameConflictDemo.class`.
- `java -cp out app.NameConflictDemo` puts `out` on the classpath and runs the class with the fully qualified name `app.NameConflictDemo`.
- The `getClass().getName()` method returns the name of the runtime type; for these two top-level classes, the results are `school.Student` and `company.Student`.
- You cannot properly run the `app.NameConflictDemo` class by just typing `java NameConflictDemo` by default in the output structure above: the JVM requires the fully qualified name of the main class in package `app`.

The source path `src/school/Student.java` and the `package school;` declaration correspond according to **project organization conventions**, helping the compiler and build tools locate classes. The package name is determined by the `package` line in the source, not merely by the name of the folder containing the file. With the appropriate compilation configuration, `javac -d` lays out the output by package.

## 5. When Two Imports Have the Same Simple Name

Suppose in `src/app/NameConflictDemo.java` we write:

~~~java
import school.Student;
import company.Student;
~~~

**This is an intentional error example; do not merge these two lines into the runnable program in Section 4.** Two different single-type import statements both bring the simple name `Student` into one compilation unit. The compiler will report an error, **even if the name `Student` has not been used yet**.

Java **does not support import aliases** such as the syntax `import company.Student as CompanyStudent;`. There are three straightforward ways to handle this:

1. Import the frequently used type: `import school.Student;`.
2. Write the fully qualified name for the other type: `company.Student`.
3. If the code constantly has to use two types with the same name and becomes hard to read, consider the design or class names based on business meaning, but only rename them when you control the source code and have a clear reason.

You can use **both types by their fully qualified names**, without importing either type:

~~~java
school.Student learner = new school.Student("An");
company.Student employee = new company.Student("Binh");
~~~

These lines illustrate how to write this inside a method that already has access to both classes; in the example in Section 4, both classes are `public`.

## 6. The Asterisk Does Not Automatically Resolve Conflicts

Another case is:

~~~java
import java.util.*;
import java.sql.*;

class AmbiguousExample {
    Date value;
}
~~~

**This code snippet intentionally causes a compile-time error**: both `java.util` and `java.sql` have a public `Date` class. The two `*` import lines do not cause an error by themselves; when the simple name `Date` is used, the compiler does not have a single type to choose from and reports that the reference is **ambiguous**.

The fix is to specify the choice explicitly. As a complete example, create the file **`DateNameDemo.java`**:

~~~java
import java.util.Date;

public class DateNameDemo {
    public static void main(String[] args) {
        Date generalDate = new Date(0);
        java.sql.Date sqlDate = new java.sql.Date(0);

        System.out.println(generalDate.getClass().getName());
        System.out.println(sqlDate.getClass().getName());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac DateNameDemo.java
java DateNameDemo
~~~

Stdout:

~~~text
java.util.Date
java.sql.Date
~~~

The line `import java.util.Date;` allows using `Date` in short form to refer to `java.util.Date`; `java.sql.Date` is written in full where needed. This is an example of class name resolution; in modern applications, the `java.time` API is usually more appropriate for representing dates and times, and the two `Date` types should not be swapped arbitrarily.

If you write `import java.util.Date;` alongside `import java.sql.*;`, a simple reference to `Date` usually resolves to the **explicit single-type import** `java.util.Date`, provided no other declaration in a higher scope changes the result. The problem with `*` imports is the possibility of conflicts arising when two peer sources both supply a name that is being used.

A more readable approach when working with large libraries is to prefer **explicit imports** instead of always using `*`, although explicit imports must still avoid duplicate simple names between two single-type imports.

## 7. Same-Package Names, java.lang, and Shadowing

### Classes in the Same Package

If `app/Helper.java` declares:

~~~java
package app;

public class Helper {
    public static String label() {
        return "OK";
    }
}
~~~

Then another file that also has `package app;` can usually write `Helper.label()` without needing `import app.Helper;`, because `Helper` is a type in the same package. In code in another package, to access the `Helper` type, the class must have an appropriate access level and you can use `import app.Helper;` or the name `app.Helper`.

### Classes in java.lang

`String`, `Object`, `System`, and `Math` are familiar simple names used without needing imports:

~~~java
String text = "Java";
System.out.println(text);
~~~

In essence, these names belong to the `java.lang` package; when needed for clarity, `java.lang.String` is also a valid type name.

### When a Name Is Shadowed by a Closer Declaration

A simple name does not always refer to the expected class. A member class or a local type can **shadow** a name provided by an import. Example illustrating scope:

~~~java
class Outer {
    static class Item {
    }

    void use() {
        Item value = new Item();
        System.out.println(value.getClass().getSimpleName());
    }
}
~~~

`Item` in `use()` refers to `Outer.Item`. If there is also a `some.library.Item` type on the classpath, the existence of that type does not change the meaning of `Item` in the `use()` method. To use the type from the library within a permitted scope, you can write the fully qualified name `some.library.Item` (assuming it is an existing and accessible class).

**Note:** the `Outer` example is an illustration of how names are looked up within a class's scope; it does not run on its own because it has no `main`. The detailed rules on scope, shadowing, and obscuring are stated in the Java Language Specification, Chapter 6. When encountering a confusing conflict, read the `package` declaration, `import` statements, enclosing classes, and local types before assuming the compiler “picks randomly”.

## 8. Nested Classes: Canonical Name Differs from Binary Name

The top-level class `school.Student` has the source-code name `school.Student`. However, a member class written with a dot in Java can have a **binary name** using `$` in `.class` files and reflection APIs.

Complete example: create **`src/demo/TypeNameDemo.java`** in a standalone example directory.

~~~java
package demo;

public class TypeNameDemo {
    static class Nested {
    }

    public static void main(String[] args) {
        Class<?> type = Nested.class;

        System.out.println(type.getSimpleName());
        System.out.println(type.getCanonicalName());
        System.out.println(type.getName());
    }
}
~~~

In the parent directory containing `src`, run:

~~~bash
javac -d out src/demo/TypeNameDemo.java
java -cp out demo.TypeNameDemo
~~~

Stdout:

~~~text
Nested
demo.TypeNameDemo.Nested
demo.TypeNameDemo$Nested
~~~

The three APIs answer three different questions:

| API | For `TypeNameDemo.Nested` | Meaning |
| --- | --- | --- |
| `getSimpleName()` | `Nested` | The simple name of the class |
| `getCanonicalName()` | `demo.TypeNameDemo.Nested` | The canonical name, which can be used when writing the type name in Java in a valid context |
| `getName()` | `demo.TypeNameDemo$Nested` | The binary name that the Java runtime uses for the member class |

You should not copy `demo.TypeNameDemo$Nested` into source code to replace the standard type syntax `demo.TypeNameDemo.Nested`. For local classes, anonymous classes, and certain special types, `getCanonicalName()` can even return `null`, because not every runtime type has a canonical name.

The `$` in the output above is the binary naming convention for member classes, **not a package separator**. The path `out/demo/TypeNameDemo$Nested.class` can also appear after compilation.

## 9. Troubleshooting Workflow When the IDE or javac Reports Type Name Errors

When encountering `cannot find symbol`, `reference to ... is ambiguous`, or a class whose name is right but whose import does not work, you should check in a logical order:

1. **Identify the intended class:** note the fully qualified name of the type, such as `school.Student`; do not rely only on the short name.
2. **Check the package in the declaring file:** `package school;` differs from `package company;`. Ensure the file has been included in compilation or the library is on the classpath/module path.
3. **Check access permissions:** a top-level type from another package usually must be `public`; with named modules, the package must also be exported and the consuming module must read the module containing the type.
4. **Check the import in the right file:** `import school.Student;` must appear after `package` and before the class declaration, in the file that uses it; an import in a neighboring file has no effect in its place.
5. **Check for conflicts:** are there two single-type imports named `Student`? Are there `*` imports from two packages that both contain `Student`? Is there a member class or local type with the same name?
6. **Try the fully qualified name:** write `school.Student` directly at the usage site to verify the type being referenced. If it still fails, the issue may be a missing dependency, an incorrect name declaration, or access permissions.
7. **Check the run command:** after compiling with packages, use `java -cp out app.NameConflictDemo` instead of just the simple name.

Distinguish the causes: **name not found** is usually due to a missing definition, import, or lookup path for the type; **ambiguous name** occurs when multiple qualified types can match the short name; **not accessible** is due to modifiers or module/package boundaries. Writing the fully qualified name can resolve name ambiguity, but **does not bypass** access rules or automatically provide a missing dependency.

## 10. Naming Conventions and Common Mistakes

| Habit or Misconception | Problem | Correct Approach |
| --- | --- | --- |
| Putting all classes into the unnamed package | Hard to manage large projects; cannot import a type from the unnamed package into a named package | Declare explicit packages for project code |
| Using the same class names `Util`, `Manager` in many places unintentionally | Hard for readers to distinguish meaning; imports easily conflict | Name classes by role with clear packages |
| Thinking `import x.*` includes all subpackages | Cannot find classes in `x.y` | Import the exact package/type needed |
| Writing two different single-type imports that share the same simple name | Compile error directly on the import | Import one type, and use the fully qualified name for the other |
| Thinking `import` creates an instance or loads code immediately | Confuses name-organization syntax with object creation/runtime loading | `new` creates instances; `import` only assists with name referencing |
| Thinking using a fully qualified name bypasses `private` or module exports | Access error even though the class path is accurate | Check modifiers and module configuration |
| Running a main class in a package using an arbitrary short name | The JVM may report that the main class cannot be found | Use the full name with an appropriate classpath |
| Using the `Class.getName()` result of a nested class as Java source syntax | Confuses the binary name `Outer$Inner` with the canonical name `Outer.Inner` | Use the appropriate type name in Java; distinguish reflection APIs |

Useful conventions: package names are written in lowercase, typically using a reversed domain name such as `com.example.school`; class names use PascalCase such as `BankAccount`, `StudentRepository`. Conventions help reduce conflicts, but **do not change** the language rules for simple names and fully qualified names.

A type can be known under multiple name forms in Java tools. Nevertheless, in ordinary source code, choose the short name when it is **clear and unambiguous**, and use the fully qualified name when you genuinely need to distinguish two classes.

## 11. Self-Practice

**Question 1.** In `package shop.inventory; public class Product {}`, which is the simple name and which is the fully qualified name?

**Question 2.** Given `a.User` and `b.User`. In the same `Main.java` file, write a valid way to create one object of each class without any imports.

**Question 3.** Why do the two lines `import a.User;` and `import b.User;` in the same file cause an error even if `User` has not been used yet?

**Question 4.** Does `import java.util.*;` make `ExecutorService` in `java.util.concurrent` directly usable? Explain.

**Question 5.** When `Class.getName()` for the member class `app.Outer.Inner` returns `app.Outer$Inner`, which name should be used to refer to that type in an ordinary Java variable declaration?

**Short answers:**

1. `Product` is the simple name; `shop.inventory.Product` is the fully qualified name.
2. Write `a.User first = new a.User();` and `b.User second = new b.User();`, assuming both types have an accessible no-argument constructor.
3. The two single-type imports attempt to bring the same simple name `User` from two different types into one compilation unit.
4. No; subpackages are not imported recursively. You need `import java.util.concurrent.ExecutorService;` or the fully qualified name.
5. Use `app.Outer.Inner` in source code, provided that class and member are accessible; `$` belongs to the binary name.

## 12. Reference Materials

- [Java Language Specification 17, Chapter 6 — Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html): names, scope, shadowing, qualified/canonical/binary names.
- [Java Language Specification 17, Chapter 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): packages, compilation units, imports, and access scope.

**Remember:** *Simple names* keep code concise; *fully qualified names* clarify which type is being referenced. `package` creates a namespace, `import` brings an appropriate name into the scope of a source file, and when class names collide, Java requires you to specify an unambiguous type.
