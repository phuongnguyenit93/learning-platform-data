# Implicit Import of `java.lang` in Java

## 1. Meaning of implicit import

In Java, every compilation unit (typically a `.java` file) is automatically given an **on-demand import** of accessible types from the **`java.lang`** package by the language. As a result, developers routinely use familiar class names such as `String`, `Object`, `System`, `Math`, `Integer`, and `Thread` **without having to write** `import java.lang.String;` or `import java.lang.*;`.

For example, the following program has no `import` declarations at all:

```java
public class Hello {
    public static void main(String[] args) {
        String message = "Hello, Java!";
        System.out.println(message);
        System.out.println(Math.max(7, 12));
    }
}
```

Save the code in **`Hello.java`** and run it with JDK 17 or later:

```bash
javac -encoding UTF-8 Hello.java
java Hello
```

Exact stdout:

```text
Hello, Java!
12
```

`String`, `System`, and `Math` all belong to `java.lang`. `javac` resolves these simple names to their corresponding types when no other name shadows or conflicts with them under Java's name-lookup rules.

**Important:** "implicit import" is a **compile-time name-resolution rule**; it does not mean the JVM initializes or loads every class in `java.lang` as soon as the program starts. Nor does it add any external libraries to the classpath.

## 2. What common types are in `java.lang`?

This package provides many fundamental types of the Java language and runtime.

| Type (written as simple name) | Fully qualified name | Typical role |
| --- | --- | --- |
| `Object` | `java.lang.Object` | Root class of ordinary classes; provides `toString()`, `equals()`, `hashCode()` |
| `String` | `java.lang.String` | Immutable character strings |
| `StringBuilder` | `java.lang.StringBuilder` | Builds/modifies character sequence content sequentially |
| `System` | `java.lang.System` | `System.out`, `System.err`, `System.currentTimeMillis()`, and system utilities |
| `Math` | `java.lang.Math` | Static math operations like `max`, `abs`, `sqrt`, constant `PI` |
| `Integer`, `Long`, `Double`, `Boolean`, ... | `java.lang.Integer`, ... | Wrapper classes for primitive values; supports conversion/boxing |
| `Throwable`, `Exception`, `RuntimeException`, `Error` | Corresponding `java.lang.*` | Core hierarchy of exceptions and errors |
| `Thread`, `Runnable` | `java.lang.Thread`, `java.lang.Runnable` | Basic task execution and concurrency support |
| `Enum`, `Record` | `java.lang.Enum`, `java.lang.Record` | Base classes in the type system for enums and records |

Some short syntax examples placed inside a method:

```java
String text = "java";
String upper = text.toUpperCase(); // "JAVA"

int max = Math.max(3, 8); // 8
double root = Math.sqrt(81); // 9.0

Integer number = Integer.valueOf("42"); // 42
StringBuilder builder = new StringBuilder("Java");
builder.append(" 17"); // "Java 17"
```

All the type names above can be used directly. However, **static methods and fields** still generally require the class name in front, such as `Math.sqrt(81)` or `System.out.println(...)`. The implicit import of the **type `Math`** does not automatically put the method name `sqrt` into scope so that you can call `sqrt(81)` alone.

## 3. Distinguishing `java.lang` from other packages

Other packages in the standard library are **not implicitly imported merely because they belong to the JDK**. For example:

```java
// java.util.List: must import when you want to use the simple name List.
import java.util.List;
import java.util.ArrayList;
```

After importing:

```java
List<String> names = new ArrayList<>();
names.add("An");
```

The following two lines have the exact same type meaning without any import statements:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");
```

| Type name | Usable directly as a simple name normally? | How to handle |
| --- | --- | --- |
| `String` | Yes, via implicit `java.lang` | `String text = "hi";` |
| `Math` | Yes, via implicit `java.lang` | `Math.max(1, 2)` |
| `List`, `ArrayList` | Not via `java.lang` | `import java.util.List;`, `import java.util.ArrayList;` |
| `LocalDate` | Not via `java.lang` | `import java.time.LocalDate;` |
| `Files`, `Path` | Not via `java.lang` | `import java.nio.file.Files;`, `import java.nio.file.Path;` |
| `Method` (reflection) | Not via `java.lang` | `import java.lang.reflect.Method;` |
| `MethodHandles` | Not via `java.lang` | `import java.lang.invoke.MethodHandles;` |

**Subpackages are not imported along with a parent package.** `java.lang.reflect`, `java.lang.invoke`, and `java.lang.management` are different packages from `java.lang`, even though their names start with `java.lang.`. Therefore:

```java
// Method is not automatically available from implicit java.lang import:
java.lang.reflect.Method[] methods = String.class.getMethods();
System.out.println(methods.length > 0); // true
```

If you want to refer to `Method` by its short name, you need `import java.lang.reflect.Method;`. The snippet above is an example meant inside a method, not a standalone runnable file.

## 4. Writing the simple name and fully qualified name for the same type

Because of the implicit import, the following two declarations normally refer to the same type:

```java
String left = "Java";
java.lang.String right = "Java";
System.out.println(left.equals(right)); // true
```

- `String` is the **simple name** of `java.lang.String`.
- `java.lang.String` is the **fully qualified name** of the type.
- There are not two different `String` types in the snippet above; the import only helps resolve the short name.
- Writing `import java.lang.String;` is valid in normal situations, though **redundant**, because Java already provides an on-demand import for this package.

**Name resolution does not depend solely on imports.** Types declared in the same package, nested types in scope, or explicit import declarations can affect what a short name means. Therefore, if a project defines its own `String` or `System` type, simply reading the name is not enough to conclude it is the `java.lang` type.

This example illustrates a case of a **custom type with the same name** in the current package:

```java
package demo;

class String {
    // Only to illustrate name collision; do not use this name in real projects.
}

class Example {
    java.lang.String message = "Hello"; // Explicitly specify standard String
}
```

This is **a separate illustrative file**, not combined into the programs below. With the same-package name, `String` can no longer be assumed to mean `java.lang.String` where it is shadowed. In real programs, name custom types clearly and avoid colliding with fundamental platform types.

If you try to import two top-level types with the same simple name using two different single-type import statements, the compiler may report a conflict. When you must use both types with the same name, use the fully qualified name to make it clear.

## 5. `import java.lang.*` does not mean `import static java.lang.Math.*`

These are two different mechanisms:

```java
import java.lang.*; // Redundant in normal code; imports types from the package.
```

```java
import static java.lang.Math.max; // Allows calling max(...) directly
```

Standalone file example:

```java
import static java.lang.Math.max;

public class StaticImportDemo {
    public static void main(String[] args) {
        System.out.println(max(5, 9));      // From static import
        System.out.println(Math.min(5, 9)); // Math is available via java.lang
    }
}
```

Save as **`StaticImportDemo.java`** and run:

```bash
javac -encoding UTF-8 StaticImportDemo.java
java StaticImportDemo
```

Output:

```text
9
5
```

`import java.lang.*` is **not** a command that imports every method or field of every class in `java.lang`. `import static` makes static members that satisfy accessibility rules directly referable by name, though you must still avoid name collisions and overuse that reduces clarity.

## 6. Java 17+ program in a named package

Create **`src/lesson/LangAutoImportDemo.java`**:

```java
package lesson;

import java.util.ArrayList;
import java.util.List;

public class LangAutoImportDemo {
    public static void main(String[] args) {
        // java.lang: no import needed.
        String text = "Java";
        StringBuilder builder = new StringBuilder(text);
        builder.append(" 17");
        System.out.println("Text: " + builder);

        System.out.println("Max: " + Math.max(4, 9));
        System.out.println("Abs: " + Math.abs(-7));
        System.out.println("PI > 3: " + (Math.PI > 3.0));

        Integer value = Integer.valueOf("42");
        System.out.println("Parsed: " + value);

        Object marker = new Object();
        System.out.println("Object: " + marker.getClass().getSimpleName());

        // java.util: must import to use short names in this file.
        List<String> items = new ArrayList<>();
        items.add("One");
        items.add("Two");
        System.out.println("List: " + items);

        // Fully qualified name works without importing the type.
        java.lang.String fullName = "ready";
        System.out.println("Full-name String: " + fullName);
        System.out.println("Runtime String: " + String.class.getName());
    }
}
```

From the root directory containing `src`, using JDK 17 or later. **Create the `out` directory if it does not exist** before using `-d out`: on Bash/Linux/macOS run `mkdir -p out`; on Windows PowerShell run `New-Item -ItemType Directory -Force out | Out-Null` (CMD: `if not exist out mkdir out`). Then run the following compile/run commands on both Windows and Linux/macOS:

```bash
javac -encoding UTF-8 -d out src/lesson/LangAutoImportDemo.java
java -cp out lesson.LangAutoImportDemo
```

`-d out` lets `javac` create the directory tree matching the package name inside `out`. `lesson.LangAutoImportDemo` is the fully qualified name of the class containing `main` when invoking `java`.

**Exact stdout** (successful compilation prints no messages):

```text
Text: Java 17
Max: 9
Abs: 7
PI > 3: true
Parsed: 42
Object: Object
List: [One, Two]
Full-name String: ready
Runtime String: java.lang.String
```

The code uses the simple names `String`, `StringBuilder`, `System`, `Math`, `Integer`, and `Object` without explicit imports. Conversely, `List` and `ArrayList` belong to `java.util`, so the file explicitly imports those types.

## 7. Relationship with the `java.base` module, classpath, and compilation

In Java 9+ (including Java 17), package `java.lang` belongs to the foundational module **`java.base`**. Every Java module reads `java.base` **implicitly** under the module system. This is a **different** mechanism from importing type names in source code:

- **Implicit package import:** allows writing `String` instead of `java.lang.String`.
- **Readability of module `java.base`:** allows module code to use public APIs exported from the base module without writing `requires java.base;` in `module-info.java`.
- **Classpath/module path:** determines whether classes and modules outside the base platform can be found. `import` by itself does not download dependencies or tell the compiler where to look.
- **Runtime:** types are loaded/initialized according to runtime rules, not automatically executed by an import line.

These module details do not need to be covered in every basic Java lesson, but they help avoid confusing the automatic availability of `java.lang` with class-lookup and execution mechanisms.

## 8. Common errors and misconceptions

| Statement/error | Correct explanation |
| --- | --- |
| "You must write `import java.lang.String;` before using `String`." | Not needed; `java.lang` is implicitly imported on demand. |
| "You don't need to import any types because they are all in the JDK." | False; `java.util.List`, `java.time.LocalDate`, etc. require imports to use simple names (unless an appropriate name is already in scope). |
| "`java.lang.reflect.Method` automatically becomes `Method`." | False; a subpackage is distinct from its parent package and must be imported separately or written with its fully qualified name. |
| "Because `Math` is imported, you can call `sqrt(9)` directly." | False; normally use `Math.sqrt(9)` or a static import. |
| "`import java.lang.*;` makes the JVM load all classes." | False; imports only affect compile-time name resolution. |
| "The name `String` in every file must refer to `java.lang.String`." | False; simple names are still subject to scope rules and collisions/shadowing. |
| "`int` and `boolean` are classes in `java.lang`." | False; they are **primitive types** of the language, not imported classes. |
| "`java.lang` is imported because the program is always in the default package." | False; the implicit import also applies to files with `package lesson;` and to any other named packages. |

**Key takeaway:** Java automatically allows using short names for eligible types in **`java.lang`**, but does not implicitly import other packages or subpackages. `import` resolves **names in source code**; to know the exact class being used, examine the package, scope, and type resolved at compile time.