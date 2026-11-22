# Simple Names and Fully Qualified Class Names in Java

## 1. Simple name and fully qualified name

Java organizes classes, interfaces, enums, records, and other types into **packages**. For a top-level type, there are two common ways to name it:

- **Simple name**: the name declared right after `class`, `interface`, `enum`, or `record`; for example `ArrayList`, `String`, `Student`.
- **Fully qualified name** (in the context of this lesson, the name with its package): the package name plus a dot and the type name; for example `java.util.ArrayList`, `java.lang.String`, `com.example.model.Student`.

```java
// Simple name:
ArrayList<String> names;

// Fully qualified name:
java.util.ArrayList<String> others;
```

Both can refer to the **same type**, if the simple name `ArrayList` is resolved by Java to `java.util.ArrayList` (usually via `import`).

A **package** is neither an object nor a place holding runtime state; it creates a namespace to organize types and avoid name collisions. By Java convention, package names are usually lowercase, such as `com.example.app`, while class names are PascalCase like `OrderService`.

**Distinction:** a dotted fully qualified name in Java source code differs from a `.java` file name or a *binary name* for nested types. For `java.util.Map.Entry`, the canonical name in Java is `java.util.Map.Entry`, whereas `Class.getName()` for this type returns `java.util.Map$Entry`.

## 2. Packages, class declarations, and file locations

Example:

```java
package com.example.model;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

The snippet above is the complete content of **`Student.java`**. The class's simple name is `Student`; its fully qualified name is `com.example.model.Student`. In a typical source file, `package` (if present) goes at the top after comments and before `import` statements and top-level type declarations.

Basic rules:

- A top-level `public class Student` must be declared in a source file named **`Student.java`**.
- `package com.example.model;` sets the package based on the **source code declaration**, not automatically from the directory name.
- A directory layout matching the package, such as `src/com/example/model/Student.java`, is a convention and standard organization that helps compilers, build tools, and the classpath locate classes in the right place.
- Compiling with `javac -d out ...` places class files into a package-based directory structure, such as `out/com/example/model/Student.class`.
- Run a class with `main` inside a package using the **fully qualified class name**, such as `java -cp out com.example.app.Main`; `java -cp out Main` will not find that class name.

Do not confuse the *simple name* of the class `Student` with the *variable name* `student` when writing `Student student = new Student("An");`.

## 3. `import` enables writing simple names

If a source file is in a different package from the class you want to use, you usually add one or more `import` declarations:

```java
package com.example.app;

import java.util.ArrayList;
import java.util.List;

public class Demo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("Java");
        System.out.println(words); // [Java]
    }
}
```

In this example, `List` is a simple name standing for `java.util.List`; `ArrayList` stands for `java.util.ArrayList`.

**`import` does not create objects, copy code, or load classes in the runtime sense.** It is a declaration that helps the compiler recognize short names where applicable. No `import` is needed if you write the fully qualified name directly in code:

```java
java.util.List<String> words = new java.util.ArrayList<>();
words.add("Java");
```

Both forms use the exact same types from `java.util`.

Common forms:

| Syntax | Meaning |
| --- | --- |
| `import java.util.List;` | Imports a specific type; lets you use `List` as a simple name when there is no conflict |
| `import java.util.*;` | Imports on demand the directly accessible types in package `java.util` |
| `import static java.lang.Math.max;` | Allows calling the static member `max` by its short name |
| `import static java.lang.Math.*;` | Static import on demand for accessible static members of `Math` |
| `java.sql.Date` | Uses the fully qualified name at the point of use; independent of any `Date` import |

`import java.util.*;` **does not import subpackages** of `java.util`, such as `java.util.concurrent`. The `*` symbol also does not mean importing the entire Java library.

Types in `java.lang` such as `String`, `Object`, `System`, and `Math` are **implicitly imported on demand**; types in the **same package** can also be referred to by their simple names when there is no conflict. Thus you do not need to write `import java.lang.String;` in ordinary programs.

## 4. When a simple name is not enough to identify a type

`java.util.Date` and `java.sql.Date` have the same simple name `Date` but are two different types. Within a compilation unit, you can import one type and write the fully qualified name for the other:

~~~java
import java.util.Date;

class Dates {
    Date general = new Date(0L);
    java.sql.Date database = new java.sql.Date(0L);
}
~~~

Two **single-type imports** for two different types with the same simple name cause an error; two wildcard imports can make the short name ambiguous where used. The lesson on import conflicts analyzes these cases in depth. Here it suffices to remember that the fully qualified name identifies a type unambiguously.

## 5. Name lookup rules: some important scenarios

The compiler resolves a simple type name based on **the syntactic context and active declarations/imports**, rather than simply searching for a random class with the same name across the entire classpath.

Common scenarios:

1. **A type already declared or in an appropriate scope** can be referred to by its simple name according to scope and accessibility rules.
2. **Types in the same package** can be used without an import.
3. **A single-type import** such as `import java.util.List;` provides a short name for one specific type; conflicting imports can cause a compilation error.
4. **An on-demand import** such as `import java.util.*;` provides types as needed; if multiple candidates share the same simple name, you may have to specify the fully qualified name.
5. **`java.lang`** is implicitly imported; however, names may still collide with program-defined types in the relevant context.

This is a practical reading guide and **does not replace the full name-resolution order** in the Java Language Specification. When a simple name points to an unintended type, check the current package, declarations in the same scope, explicit imports, and wildcard imports; then use the fully qualified name to confirm your intent.

**Distinguish access rights from importing:** a `package-private` class does not become accessible from another package merely by adding `import`. Imports do not bypass `public`, `protected`, package access, or `private` restrictions.

## 6. Standalone Java 17+ example demonstrating both styles

Create the directory and file **`src/study/NameResolutionDemo.java`** with the following content:

```java
package study;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Map;
import static java.lang.Math.max;
import static java.lang.Math.PI;

public class NameResolutionDemo {
    public static void main(String[] args) {
        // List and ArrayList are simple names thanks to import.
        List<String> names = new ArrayList<>();
        names.add("An");
        names.add("Binh");
        System.out.println("Names: " + names);

        // java.util.ArrayList is the fully qualified name for the same type.
        java.util.List<String> other = new java.util.ArrayList<>();
        other.add("Java");
        System.out.println("Other: " + other);

        // Two Date classes from different packages, avoiding simple name collision.
        Date utilDate = new Date(0L);
        java.sql.Date sqlDate = new java.sql.Date(0L);
        System.out.println("Util Date class: " + utilDate.getClass().getName());
        System.out.println("SQL Date class: " + sqlDate.getClass().getName());

        // Nested type: Map.Entry has a multi-part canonical name.
        Map.Entry<String, Integer> entry = Map.entry("apple", 2);
        System.out.println("Entry: " + entry.getKey() + "=" + entry.getValue());

        // java.lang is implicitly imported; max and PI come from static imports.
        System.out.println("Max: " + max(3, 5));
        System.out.println("PI > 3: " + (PI > 3.0));
        System.out.println("Simple class: " + names.getClass().getSimpleName());
        System.out.println("Full class: " + names.getClass().getName());
    }
}
```

**Compile and run** (JDK 17+, from the root directory of the example containing `src/study/NameResolutionDemo.java`):

**Create the root `out` directory before `javac -d out` if it does not exist yet**: on Bash/Linux/macOS run `mkdir -p out`; on Windows PowerShell run `New-Item -ItemType Directory -Force out | Out-Null`. `javac` can create directories *inside* `out` according to the package, but will not create a missing target `out` directory itself.

```bash
javac -encoding UTF-8 -d out src/study/NameResolutionDemo.java
java -cp out study.NameResolutionDemo
```

These two commands are the same in PowerShell, CMD, bash, or zsh. The `out` directory is where `javac` creates the `study/NameResolutionDemo.class` tree; you can let the compiler create the directory structure inside `out`. Use `study.NameResolutionDemo` because the `NameResolutionDemo` class is in package `study`.

**Exact stdout** (when compilation succeeds, `javac` prints nothing):

```text
Names: [An, Binh]
Other: [Java]
Util Date class: java.util.Date
SQL Date class: java.sql.Date
Entry: apple=2
Max: 5
PI > 3: true
Simple class: ArrayList
Full class: java.util.ArrayList
```

The `getClass().getSimpleName()` and `getClass().getName()` results here are read from the actual `ArrayList` object. Do not rely on `getSimpleName()` as the sole verification mechanism when two classes in different packages share the same name, because package information is stripped.

### Nested type names and binary names

For example, `Map.Entry` is a nested interface with the simple name `Entry`; in Java code, you can write `java.util.Map.Entry` without ever directly referring to the `$` character.

```java
System.out.println(java.util.Map.Entry.class.getCanonicalName());
// java.util.Map.Entry

System.out.println(java.util.Map.Entry.class.getName());
// java.util.Map$Entry
```

This snippet illustrates the difference inside a method; the complete program is above. `getCanonicalName()` and `getName()` differ when handling names of certain nested types. If you use reflection APIs such as `Class.forName`, you need to understand the **binary** name format that the API expects.

## 7. Do not confuse `import` with `classpath` or modules

`import` only resolves how **type names are written** in a source file. To compile and run, the compiler and JVM must still find the class definitions on the corresponding classpath or module path.

- **`package`** defines a type's namespace; simply declaring `package study;` does not install a library or download an external `.jar`.
- **`import`** lets you write simple names; it does not specify where to find `.class` files and does not add libraries to the classpath.
- **`classpath`**, e.g., `javac -cp libs/example.jar ...`, specifies dependency locations at compile time. `java -cp ...` specifies class locations at runtime.
- In applications using the **Java Platform Module System** (JPMS), the ability to use a type is also subject to module rules such as `requires` and `exports`; imports do not replace module declarations.
- Types in the **unnamed package** (no `package` declaration) cannot be imported by code in a named package in the usual way; real projects should use named packages.

If you see errors like `cannot find symbol`, `package ... does not exist`, or `ClassNotFoundException`, distinguish **name resolution issues in code** from **missing classes/libraries at compile or run time**.

## 8. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| `List` and `java.util.List` are always two different types | If `List` resolves to `java.util.List`, they are the same type |
| You must import a class from another package to use it | You can write the fully qualified name without importing |
| `import java.util.*;` also imports `java.util.concurrent.*` | Wildcard imports apply only to a single package/type according to specific rules and do not extend to subpackages |
| Two classes named `Date` from two packages are automatically equivalent | `java.util.Date` and `java.sql.Date` are two different classes |
| Importing lets you use `private` or package-private classes from anywhere | Access rules still apply |
| Having an import means the JVM is guaranteed to find the class at runtime | The dependency must be on the corresponding classpath/module path |
| `Class.getName()` always equals the canonical name written in Java | Nested types may use `$` in their binary name |
| Running a packaged class using just its simple name after `java` | Use the fully qualified name, e.g., `java -cp out study.NameResolutionDemo` |

**Key takeaway:** simple names keep code concise; fully qualified names identify a type unambiguously. `package` organizes namespaces, `import` assists short-name resolution, and classpath/module path determine where class definitions are found.