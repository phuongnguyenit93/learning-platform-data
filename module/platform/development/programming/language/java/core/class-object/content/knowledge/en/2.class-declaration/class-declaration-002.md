# Class Naming, File Naming, and Rules for Public Classes in Java

When declaring a Java class, the **class name** is the identifier of the type, the **source file name** is where the `.java` code is stored, and the `public` modifier indicates the accessibility of that type from outside the package. These three elements are related but distinct: not every class has to match the file name, and `public` does not automatically make a class accessible from every module.

This lesson explains naming syntax and conventions, the relationship between a top-level class and a source file, how classes work with `package`, the difference between top-level and nested classes, along with compilable and runnable Java 17+ examples.

## 1. Multiple Ways to Identify a Class

Consider the file **`src/com/example/school/Student.java`**:

~~~java
package com.example.school;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

This is a **class declaration snippet**, not a standalone runnable program with `main`.

| Component | Value in Example | Meaning |
| --- | --- | --- |
| Simple name | `Student` | Type name without specifying the package |
| Fully qualified name | `com.example.school.Student` | Type name including the package |
| Package | `com.example.school` | Scope for organizing classes and controlling package-private access |
| Source file | `Student.java` | File containing the class declaration |
| Common source path | `src/com/example/school/Student.java` | Mirrors the package from the source root directory |

`Student` and `student` are two different names because Java is **case-sensitive**. Two classes with the same simple name `Student` can exist in two different packages, such as `com.example.school.Student` and `com.example.sports.Student`; the two types have different fully qualified names.

From the JVM's perspective, the class name with its package matters when loading/running the program. From the `javac` compiler's perspective, the file name is especially important if the top-level class is `public`.

## 2. Syntax Rules for Class Names

A class name must be a valid **Java identifier**. In Java 17:

- The name may consist of letters and various Java-recognized Unicode characters, digits in non-leading positions, as well as certain characters such as `_` and `$`.
- It cannot start with a digit: `Customer2` is valid, while `2Customer` is invalid.
- Do not use Java keywords such as `class`, `public`, or `int` as class names. Certain names such as `record` and `var` have restricted usage rules as type names.
- A standalone underscore character **`_`** is no longer a valid identifier as of Java 9; `_Customer` remains syntactically valid.
- Java distinguishes between `User`, `user`, and `USER`; although they can coexist if there is no name collision, such naming is very hard to maintain.

Valid examples (invalid lines have been commented out):

~~~java
class Customer { }
class Customer2 { }
class _Customer { }
class customer { }     // valid, does not follow class convention

// class 2Customer { } // invalid: starts with a digit
// class class { }     // invalid: collides with a keyword
// class _ { }         // invalid in Java 17
// class record { }    // invalid: record cannot be used as a type name
~~~

This snippet has no `main` and is used to illustrate **identifier names**. `$` or special Unicode letters may be valid, but should not be used arbitrarily because they reduce readability and can easily cause confusion when searching or working across operating systems.

### 2.1. Convention: UpperCamelCase

Java typically names classes, interfaces, enums, and records using **UpperCamelCase**: the first letter of each word is capitalized, with no spaces or hyphens.

| Name | Assessment | Reason |
| --- | --- | --- |
| `Student` | Recommended | Noun denoting the type |
| `BankAccount` | Recommended | Clearly states the object and scope |
| `PaymentRequest` | Recommended | Easy to infer responsibility |
| `HttpClient` | Recommended | Readable word combination |
| `student` | Compiles | But does not follow the class convention |
| `bank_account` | Compiles | Does not follow UpperCamelCase |
| `Bank-Account` | Does not compile | The `-` character is not part of an identifier |
| `Data` | Vague | Does not describe a specific object |
| `String` | Confusing | Can shadow the standard type name `java.lang.String` |

Other names in Java have their own conventions: methods/fields are usually `lowerCamelCase` such as `getName` and `totalPrice`; constants are usually `UPPER_SNAKE_CASE` such as `MAX_SIZE`; packages usually use lowercase such as `com.example.school`.

**The compiler only enforces syntax rules**; it does not force you to write in UpperCamelCase. However, you should choose names tied to business domain concepts and avoid cryptic abbreviations or names that differ only by a single uppercase letter.

## 3. A Public Top-Level Class Must Match the File Name When Using javac

A **top-level class** is a class declared directly inside a compilation unit, outside all other classes. In a `.java` source workflow with the `javac` compiler, if a top-level class has the `public` modifier, **the source file must carry the exact class name followed by the `.java` suffix**.

**File `Customer.java`:**

~~~java
public class Customer {
}
~~~

This is a valid declaration. However, if you save the same content under the name **`Order.java`** and run:

~~~bash
javac Order.java
~~~

then a typical compilation error is:

~~~text
Order.java:1: error: class Customer is public, should be declared in a file named Customer.java
~~~

Line numbers, formatting, and wording may vary depending on the JDK. Fix this by renaming the file to `Customer.java` or renaming the class to `Order`, depending on your intent. If you rename the class, you must also update its constructors, references, and related imports.

**Technical distinction:** the Java specification describes compilation unit organization mechanisms that depend on the host system; the rule that a file takes the name of its public type is standard behavior in practice with **`javac`** and typical Java build tools. The statement "every class must have a file with a matching name" is inaccurate because package-private classes and nested classes have different cases.

### 3.1. No Two Differently Named Top-Level Public Types in the Same File

**File `First.java`, invalid example:**

~~~java
public class First {
}

public class Second {
}
~~~

The compiler requires the `Second` type to be declared in `Second.java`. Split them into two files:

~~~text
First.java    -> public class First
Second.java   -> public class Second
~~~

The same principle also applies in practice to top-level `public interface`, `public enum`, `public record`, and `public @interface`: the file name corresponds to the public type name. For example, `public enum OrderStatus { NEW, PAID }` should be saved in `OrderStatus.java`.

**Do not confuse with Java modifiers:** a top-level class can only have `public` or default access (no modifier written, called *package-private*). You cannot declare `private class X` or `protected class X` at the top level.

### 3.2. Exception: Non-`public` Classes Are Not Required to Match the File Name

A `package-private` top-level class (without `public`) **does not have to carry the same name as the file**. For example, in **`Shapes.java`**:

~~~java
class Circle {
    double radius;
}

class Rectangle {
    double width;
}
~~~

The command `javac Shapes.java` generates `Circle.class` and `Rectangle.class`. If a file contains a top-level `public class Cart` and a non-public helper, the file name must be `Cart.java`; the helper does not need a separate file.

This is a **file-naming exception** to keep in mind when naming classes. The lesson on *multiple top-level classes in the same file* will clarify how multiple classes are compiled, the benefits of package-private helpers, and cases where the compiler cannot automatically locate a helper residing in a differently named file. For multi-file source code, placing each independent top-level type in its own file is generally still more convenient for IDEs, source search, and build tools.


## 4. Public Nested Classes Do Not Need Separate Files

A **nested class** is declared inside another class. It can be `public` without being subject to the file-naming rule for top-level public types.

**File `Library.java`:**

~~~java
public class Library {
    public static class Book {
        private final String title;

        public Book(String title) {
            this.title = title;
        }

        public String getTitle() {
            return title;
        }
    }
}
~~~

This is a valid class declaration snippet without `main`. `Library` is the top-level class, so the file name is **`Library.java`**. `Book` is a **static nested class** and is accessed by the name `Library.Book`; there is no need to create `Book.java`.

Similarly:

~~~java
class Outer {
    public class Inner {
    }
}
~~~

`Inner` here is a **non-static inner class**, tied to an instance of `Outer`. It is also not a top-level class. If the compiler creates bytecode files named such as `Library$Book.class`, this is a compiler-generated **`.class`** file name, not a requirement for a `Book.java` source file name.

You should check the declaration location before applying the rule "`public` must match the file name": **`public` on a top-level type** differs from **`public` on a member nested type**.

## 5. Public and Packages: Class Access Scope

A `public` top-level type can be used from other packages if the remaining access conditions allow it. A top-level type without `public` can only be accessed directly within the same package, commonly called **package-private**.

**File `src/com/example/school/StudentRules.java`:**

~~~java
package com.example.school;

class StudentRules {
    static boolean validId(String id) {
        return id != null && !id.isBlank();
    }
}
~~~

`StudentRules` is package-private, so classes in `com.example.school` can use it, whereas a class in `com.example.billing` cannot reference it directly under normal access rules. Two packages are not automatically treated as one just because they are in the same project or under the same root directory.

For a public type, you can write the fully qualified name `com.example.school.Student` or `import com.example.school.Student;` if the compiler sees the class on the classpath/module path and access permissions allow it.

**Named modules:** when `module-info.java` is present, `public` alone is not enough for code in another module to access the class. The package containing the public class also needs to be appropriately declared with `exports` by its module; the consuming module must have an appropriate `requires` relationship. The public class file-naming rule still applies when compiling source code with `javac`.

From a design perspective, `public` is suitable for APIs intended to be used from other packages. Helpers serving only internal implementation should usually be kept package-private, reducing dependencies from external code.

## 6. Runnable Example: Two Public Classes, Two Files, One Package

Create the following directory structure:

~~~text
project/
└── src/
    └── com/
        └── example/
            └── academy/
                ├── StudentCard.java
                └── App.java
~~~

**File `src/com/example/academy/StudentCard.java`:**

~~~java
package com.example.academy;

public class StudentCard {
    private final String studentId;
    private final String studentName;

    public StudentCard(String studentId, String studentName) {
        this.studentId = studentId;
        this.studentName = studentName;
    }

    public String label() {
        return studentId + " - " + studentName;
    }
}
~~~

**File `src/com/example/academy/App.java`:**

~~~java
package com.example.academy;

public class App {
    public static void main(String[] args) {
        StudentCard card = new StudentCard("SV-17", "Lan");

        System.out.println("Student: " + card.label());
        System.out.println("Class: " + card.getClass().getSimpleName());
    }
}
~~~

Open a terminal in the `project` directory. Using JDK 17+, execute:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/com/example/academy/StudentCard.java src/com/example/academy/App.java
java -cp out com.example.academy.App
~~~

Skip `mkdir out` if the directory was already created earlier. `javac -d out` creates the package directories underneath the `out` output root. The last pair of commands runs from the `project` directory; paths are passed explicitly so they do not depend on shell wildcard expansion.

**Exact stdout:**

~~~text
Student: SV-17 - Lan
Class: StudentCard
~~~

The compiled bytecode is located at:

~~~text
out/
└── com/
    └── example/
        └── academy/
            ├── StudentCard.class
            └── App.class
~~~

Explanation:

1. The two top-level public classes reside in two matching files: `StudentCard.java` and `App.java`.
2. Both declare `package com.example.academy;`, so `App` refers to `StudentCard` by its simple name without needing an `import`.
3. The `main` method of `App` calls the `StudentCard(...)` constructor and then prints the label from the `label()` method.
4. `card.getClass().getSimpleName()` returns `"StudentCard"` for the class created in the example.
5. `java -cp out com.example.academy.App` is how to run using the **fully qualified name** of the main class; `java App` will not find this class properly when it is in a named package.

`-encoding UTF-8` is used for reading the source code; `-d out` specifies the root directory for storing `.class` files; `-cp out` sets the classpath root at runtime. These are command-line options and do not change class naming syntax.

## 7. Packages and Directory Structure

Standard practice usually organizes source code as:

~~~text
src/main/java/com/example/shop/Product.java
~~~

and declares at the top of the file:

~~~java
package com.example.shop;

public class Product {
}
~~~

`src/main/java` is the common source root in Maven/Gradle, while `com/example/shop` mirrors the package. **It is the `package` declaration in the source code that determines which package a class belongs to**; directory names themselves cannot override the package declaration. When compiling source code with `javac` using explicit paths, the compiler can accept a non-conventional source layout, but a layout matching the package helps IDEs, build tools, source paths, compiled classes, and humans work more reliably.

### 7.1. The Unnamed Package When No Package Is Declared

**File `Hello.java`:**

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

This is a complete program with no `package` declaration, so it belongs to the **unnamed package**. Run:

~~~bash
javac Hello.java
java Hello
~~~

Stdout:

~~~text
Hello, Java!
~~~

This example is suitable when first learning Java. Multi-class projects should use named packages; code in a named package cannot directly import classes from the unnamed package.

### 7.2. Two Classes with the Same Simple Name in Two Packages

You can have `com.example.shop.User` and `com.example.admin.User`. When both need to be referenced in the same file, use their fully qualified names to avoid collisions. Java does not provide import aliases using the aliasing syntax found in some other languages.

~~~java
// Variable declaration illustration, assuming both User types already exist:
com.example.shop.User customer;
com.example.admin.User administrator;
~~~

Conversely, two top-level classes with the same simple name in the **same package** will collide even if they are placed in two different source directories.

## 8. Common Errors and How to Diagnose Them

| Situation | Why It Is Wrong or Error-Prone | How to Fix |
| --- | --- | --- |
| `public class Payment` saved in `Invoice.java` | Public top-level type and file name do not match | Save as `Payment.java` or rename the class |
| Two top-level `public` classes in `Main.java` | Cannot simultaneously satisfy the file-naming rule | Split each public type into its own file |
| `private class Helper` at the top level | `private` does not apply to top-level classes | Remove the modifier or convert it into a nested member class |
| `public class account` in `Account.java` | Java is case-sensitive | Change to `Account` and update references consistently |
| `public class Order` renamed to `Purchase` while the constructor remains `Order(...)` | A constructor must match the class name | Refactor to rename the class and constructor together |
| `class InternalTool` cannot be called from another package | Package-private access is limited to the same package | Keep it internal or make it public if required by the API |
| Source placed properly, but running `java Main` when the class belongs to `com.example.Main` | Wrong fully qualified name/classpath at runtime | Run `java -cp out com.example.Main` |
| Class named `String` or `Object` | Easily causes conflicts or shadows standard type names | Choose a specific business domain name |
| Only letter case differs in file names between Windows/Linux | Filesystem case sensitivity behavior may differ | Keep exact casing in both code and file names |

A *compile-time* error such as `class Customer is public, should be declared in a file named Customer.java` differs from a *runtime* error such as `Could not find or load main class`. The first relates to source code organization; the latter relates to the class name at runtime, classpath, bytecode, or module configuration.

You should not randomly change `public` to fix a classpath error, because this modifier controls API access, not where the JVM looks for bytecode.

## 9. API Design Example: Public and Package-Private in the Same File

**File `InvoiceService.java`:**

~~~java
package com.example.billing;

public class InvoiceService {
    public long total(long base, long tax) {
        return InvoiceMath.sum(base, tax);
    }
}

class InvoiceMath {
    static long sum(long first, long second) {
        return Math.addExact(first, second);
    }
}
~~~

This is an illustrative snippet without `main`. `InvoiceService` is an API usable by other packages when all other access conditions are met. `InvoiceMath` only serves implementation within `com.example.billing`, so it does not need to be `public`. Having one public top-level class and one package-private class in the same file is valid. When the helper grows large enough or needs independent testing, `InvoiceMath` can be extracted into `InvoiceMath.java`; extracting it does not require adding `public`.

## 10. Self-Check

**Question 1.** The file `Shop.java` declares `public class Store`. Is the command `javac Shop.java` valid?

**Answer:** No. The public top-level class `Store` must be in `Store.java` for `javac`.

**Question 2.** Can `class A` and `class B` (non-public) both reside in `Helpers.java`?

**Answer:** Yes. They are two top-level package-private classes; neither name needs to match the file name.

**Question 3.** `public class Outer` has `public static class Nested`. Do you have to create `Nested.java`?

**Answer:** No. `Nested` is a nested class, while `Outer` is the top-level public class that determines the file name `Outer.java`.

**Question 4.** Can a `public class User` be declared in package `com.example.api` and another `public class User` in `com.example.domain`?

**Answer:** Yes. Their two fully qualified names are `com.example.api.User` and `com.example.domain.User`, so they are two different types.

**Question 5.** Class `App` belongs to `package com.example.app;` and is compiled into `out/com/example/app/App.class`. What is the command to run it with classpath root `out`?

**Answer:** `java -cp out com.example.app.App` if `App` has an appropriate `main` entry point.

When creating a new class, check five points: **a valid and meaningful type name**, **the correct package declaration**, **the top-level `public` type matching the file name exactly**, **only one top-level `public` type per file**, and **consistent source/classpath structure when building or running**. These practices help keep Java source code clearly organized and avoid most basic errors related to class names and file names.
