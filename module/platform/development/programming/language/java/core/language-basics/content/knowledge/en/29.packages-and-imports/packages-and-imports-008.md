# Handling Two Classes with the Same Name and Limits of `import` in Java

## 1. Why can two classes share the same name?

In Java, the **simple name** is the last part of a class name, such as `Result`. The **fully qualified name** combines the package name with the type name, such as `com.example.payment.Result` and `com.example.network.Result`.

Two classes with the same simple name can exist in two different packages. A problem only arises when source code needs to resolve the short name `Result` and there are multiple candidates. `import` lets you use the short name of an accessible type; it **does not rename the class, create an alias, or copy code**, nor does it force the JVM to load the class at the moment the import is written.

Examples of valid and distinct types:

```text
com.example.payment.Result
com.example.network.Result
java.util.Date
java.sql.Date
```

When facing a name collision, the surest approach is to use the **fully qualified name** at the point of use.

## 2. Distinguishing conflicts from single-type imports vs. on-demand imports

~~~java
package com.example.app;
import java.util.List;            // Single-type import
import java.util.*;               // Type-import-on-demand
import static java.lang.Math.PI;  // Static member import
~~~

Import declarations only help **resolve names in source code**; they do not create aliases, bypass access controls, or cause Java to load classes at runtime. The `*` does not automatically include subpackages.

This lesson focuses on the difference between **two single-type imports** for two different types with the same simple name (an error at the import lines) and **two wildcard imports** providing two candidates with the same name (ambiguous when that name is used). To use both types, explicitly import at most one type and write the qualified name for the other, or write qualified names for both.

## 3. Runnable example: two Result classes in different packages

Create the directory structure:

```text
src/
└── com/
    └── example/
        ├── payment/
        │   └── Result.java
        ├── network/
        │   └── Result.java
        └── app/
            └── Main.java
```

**File `src/com/example/payment/Result.java`:**

```java
package com.example.payment;

public class Result {
    public String origin() {
        return "payment";
    }
}
```

**File `src/com/example/network/Result.java`:**

```java
package com.example.network;

public class Result {
    public String origin() {
        return "network";
    }
}
```

**File `src/com/example/app/Main.java`:**

```java
package com.example.app;

import com.example.payment.Result;
import com.example.network.*;

public class Main {
    public static void main(String[] args) {
        Result payment = new Result();
        com.example.network.Result network = new com.example.network.Result();

        System.out.println("simple=" + payment.origin());
        System.out.println("qualified=" + network.origin());
    }
}
```

Here, `import com.example.payment.Result;` brings **one specific type** into short-name scope. `import com.example.network.*;` only imports on demand, so `Result` does not become ambiguous: a single-type import declaration takes precedence over an import-on-demand declaration. The `network.Result` class is still used normally when written with its fully qualified name. If you only use the fully qualified name for the network type, you can omit `import com.example.network.*;` altogether.

**Compile and run with JDK 17+** from the directory containing `src` (paths with `/` are accepted by Java on Windows, Linux, and macOS). Create the `out` directory once with `mkdir out`, then:

```sh
javac -encoding UTF-8 -d out src/com/example/payment/Result.java src/com/example/network/Result.java src/com/example/app/Main.java
java -cp out com.example.app.Main
```

Exact output of the `java` command:

```text
simple=payment
qualified=network
```

The name used in `java -cp out com.example.app.Main` is the **fully qualified name of the class containing `main`**. `-d out` places the `.class` files into directories matching their packages. Importing does not replace compiling dependent classes or configuring the classpath.

## 4. Name-collision cases and how Java handles them

| Scenario | Using short name `Result` | How to handle |
| --- | --- | --- |
| `import com.example.payment.Result;` alongside `import com.example.network.*;` | Selects `payment.Result` due to the explicit import | Write `com.example.network.Result` when needing the other type |
| `import com.example.payment.*;` and `import com.example.network.*;` | **Ambiguous** if referencing `Result` when both types are accessible | Choose one explicit import or use fully qualified names |
| Two explicit `import`s for **two different types** with the same simple name | **Compile error right at the import declarations** | Keep at most one explicit import for that name |
| Same-package type and a wildcard-imported type from another package with the same name | The same-package type is selected over a type coming only from an on-demand import | Write the fully qualified name for the type from the other package |
| Member type/nested class or type name declared in a nearer scope | May shadow imported names depending on position and declaration kind | Check scope or use a clearly qualified type name |

### 4.1. Two explicit imports: error even without creating an object

The following example **intentionally fails to compile**, assuming both `Result` classes from the example above exist:

```java
package com.example.app;

import com.example.payment.Result;
import com.example.network.Result; // error: two single-type imports for different types with the same simple name

public class InvalidImports {
}
```

This is a conflict at the *import declarations*, not waiting until `new Result()` is called. You must remove one import and use the fully qualified name where the second type is needed.

### 4.2. Two wildcards: error only when the short name is ambiguous

The following snippet also **intentionally fails to compile**:

```java
package com.example.app;

import com.example.payment.*;
import com.example.network.*;

public class AmbiguousUse {
    Result value = new Result(); // both packages have Result
}
```

The two wildcard declarations are allowed to coexist on their own. The error occurs at the reference `Result` because both types match equally. If changed to `com.example.payment.Result value = new com.example.payment.Result();`, it is no longer ambiguous.

### 4.3. Real-world example: java.util.Date and java.sql.Date

`java.util.Date` and `java.sql.Date` are two different types despite having the same simple name. You can write:

```java
import java.util.Date;

class Example {
    Date utilDate;
    java.sql.Date sqlDate;
}
```

This is a type-declaration snippet, not a program with `main`. You cannot import both `java.util.Date` and `java.sql.Date` with two single-type import lines and expect the compiler to tell them apart by business context. In new code, when representing a date without a time component, you should usually consider `java.time.LocalDate`; `java.sql.Date` still has a role in JDBC APIs.

## 5. Name precedence scope: what should you watch out for?

You can use the following practical guide to read code:

1. **Look for names declared in a nearer scope** (for example member types, type parameters), as they can shadow names coming from imports.
2. **Check single-type imports**, such as `import pkg1.Result;`, before on-demand imports.
3. **Types in the current package** require no import and take precedence over types coming only from wildcards in other packages.
4. **On-demand imports** and `java.lang` supply candidates when no nearer declaration exists; if multiple types with the same name remain eligible, a short-name reference can be ambiguous.
5. When in doubt, use the **fully qualified name**. Note that this is a practical guide; the exact language rules also depend on the kind of name, declaration site, and shadowing.

In particular, a **single-type import** can shadow a type with the same name declared in **another file of the same package**, whereas declaring a top-level type with the same name **in the exact same compilation unit** as that single-type import is a conflict. Therefore, do not rely on an absolute rule that "same package always beats every import".

## 6. Other limits of import

**(a) Import does not grant access.** A `public` top-level type in another package can be imported when that package is available. A top-level type without `public` is only accessible from its own package; adding an `import` does not make it `public`. `private`, `protected`, and package-private members still follow their own access rules. You might be able to import a class name yet still be unable to call constructors or methods without sufficient access.

**(b) Subpackages are separate packages.** `com.example` and `com.example.internal` have no "inheritance" of default access rights. `import com.example.*;` does not import `com.example.internal.Helper`.

**(c) Import does not replace classpath or module path.** If a library is not on the compilation path, the error cannot be solved merely by adding an import. In a project using the Java Platform Module System, the module must be allowed to read the module containing the type and the relevant package must be exported by module rules; imports do not automatically add `requires` or `exports`.

**(d) Cannot import types from the unnamed package into a named package.** If a file has `package com.example.app;`, it cannot use `import` to access a class in the unnamed/default package. Organize classes into clear named packages.

**(e) Imports are not inherited across files.** An import declared in `Main.java` applies only within that compilation unit; `Another.java` must declare its own required imports. An import does not make a program run meaningfully faster or slower merely by turning a short name into a fully qualified name.

**(f) Type import differs from static import.** `import java.lang.Math;` lets you use the type name `Math`, yet you must still write `Math.PI`. `import static java.lang.Math.PI;` lets you reference `PI` directly. Static imports also have their own name-collision and accessibility rules; they do not solve two top-level classes in different packages having the same name.

## 7. How to troubleshoot errors in a project

If `javac` reports a type name as *ambiguous*, check which `*` imports bring in types with the same name; replace one with a single-type import or use fully qualified names. If it reports a conflict at an `import` line, check for two explicit imports with the same simple name; remove one line. If it reports `cannot find symbol` or `package ... does not exist`, check package/class spelling, source locations, JARs, classpath, or module path before editing imports. If it reports an inaccessible type, check `public`/package scope/module rules rather than adding wildcards.

In an IDE, **Organize Imports** can remove unused imports and choose matching types, though you should still review them because the IDE cannot automatically decide which class is right for your business logic. For common names like `Date`, `List`, `Logger`, `Result`, and `Exception`, writing the fully qualified name on a couple of lines is often clearer than adding two sets of wildcard imports.

## 8. Key takeaways and self-check

- Can two classes `a.Result` and `b.Result` exist simultaneously? **Yes**, because their fully qualified names differ.
- Can two single-type imports `a.Result` and `b.Result` coexist in the same Java file? **No**, if they are two different types.
- Can two wildcards `a.*` and `b.*` be declared together? **Yes**; however, referring to `Result` by its short name will be ambiguous when both corresponding classes are accessible.
- Does `import a.*;` import `a.sub.Helper`? **No**.
- Does `import a.Secret;` make a package-private class `Secret` public? **No**.
- If you want to use two types with the same name in one file, how should you write it? **Explicitly import at most one type with that name and use the fully qualified name for the other**, or write fully qualified names for both.

**Most useful rule:** imports only reduce typing package names; **fully qualified names, accessibility, and build configuration** determine which type is actually referenced.