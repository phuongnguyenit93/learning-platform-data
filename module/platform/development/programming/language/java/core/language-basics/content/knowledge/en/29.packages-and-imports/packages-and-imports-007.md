# Imports Do Not Automatically Include Subpackages in Java

## 1. Main rule: each package is its own namespace

In Java, a **package** groups related types and creates a namespace. The dots in a package name represent a naming structure, but **do not create an inheritance relationship or "cascading import" relationship** between a parent package and its subpackages.

For example:

- `java.util` and `java.util.concurrent` are **two different packages**.
- `java.util.concurrent` and `java.util.concurrent.atomic` are also **two different packages**.
- `java.lang` and `java.lang.reflect` are **two different packages**.

When writing:

```java
import java.util.*;
```

the compiler can resolve simple names of **accessible types declared directly in package `java.util`**, such as `List`, `ArrayList`, `Map`, and `Scanner`. However, that statement **does not automatically import types in the subpackage `java.util.concurrent`** such as `TimeUnit` or `ExecutorService`, nor does it import `AtomicInteger` from `java.util.concurrent.atomic`.

**Rule to remember:** `import p.*;` does not mean "import `p` and all subpackages". The `*` character here is **not a recursive directory search wildcard**.

## 2. Example: `java.util.*` does not bring `TimeUnit` into scope

Consider the code:

```java
import java.util.*;

class Example {
    void demo() {
        List<String> words = new ArrayList<>(); // Valid
        // TimeUnit.SECONDS.toMillis(2);       // ERROR: missing import for TimeUnit
    }
}
```

`List` and `ArrayList` belong directly to package `java.util`. Meanwhile, `TimeUnit` belongs to `java.util.concurrent`, so `import java.util.*;` does not make the name `TimeUnit` recognized.

There are two proper ways to handle this.

**Approach 1 — Import the type directly:**

```java
import java.util.*;
import java.util.concurrent.TimeUnit;

// Inside a method:
long millis = TimeUnit.SECONDS.toMillis(2); // 2000
```

**Approach 2 — Use the fully qualified name without adding an import:**

```java
import java.util.*;

// Inside a method:
long millis = java.util.concurrent.TimeUnit.SECONDS.toMillis(2); // 2000
```

These snippets are **illustrative code**, not standalone programs. If you need multiple types from the same subpackage, you can use:

```java
import java.util.concurrent.*;
```

That statement lets you use `TimeUnit` and `ExecutorService` by their short names, but **still does not automatically import `java.util.concurrent.atomic.AtomicInteger`** or types in other subpackages of `java.util.concurrent`.

## 3. Several other common examples

| Imported | Types usable by short name via that import | Types **not** automatically imported |
| --- | --- | --- |
| `import java.util.*;` | `List`, `ArrayList`, `Map` | `java.util.concurrent.TimeUnit` |
| `import java.util.concurrent.*;` | `TimeUnit`, `ExecutorService` | `java.util.concurrent.atomic.AtomicInteger` |
| `import java.security.*;` | `MessageDigest`, `SecureRandom`, `KeyPair` | `java.security.cert.Certificate` |
| `import java.nio.file.*;` | `Path`, `Files` | `java.nio.file.attribute.BasicFileAttributes` |
| Implicit `java.lang.*` import | `String`, `System`, `Math`, `Integer` | `java.lang.reflect.Method`, `java.lang.invoke.MethodHandles` |

A concrete reflection example:

```java
// String can be used directly because it belongs to java.lang:
String text = "Java";

// Method belongs to package java.lang.reflect and does not automatically become a short name:
// Method m = String.class.getMethod("length"); // ERROR if Method is not imported

java.lang.reflect.Method m = String.class.getMethod("length");
```

The last illustrative snippet needs to be inside a method declaring `throws NoSuchMethodException` or handling the exception appropriately. You can replace the fully qualified name with `import java.lang.reflect.Method;` at the top of the file. The key point: **the implicit `java.lang` import does not cascade into subpackages either**.

These standard packages may belong to the same module (such as `java.base`), but being in the same module **does not cause imports to cascade to other packages**.

## 4. Complete Java 17+ program

The example below demonstrates at the same time an **on-demand import on a parent package**, **explicit imports from subpackages**, and a **fully qualified name instead of an import**.

Create **`src/lesson/ImportSubpackageDemo.java`** with this content:

```java
package lesson;

import java.util.*;
import java.util.concurrent.TimeUnit;
import java.lang.reflect.Method;

public class ImportSubpackageDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {

        // ArrayList, List, and Map belong directly to java.util.
        List<String> words = new ArrayList<>();
        words.add("Java");
        words.add("core");
        System.out.println("Words: " + words);

        // TimeUnit belongs to java.util.concurrent:
        // requires a separate import despite java.util.*.
        long millis = TimeUnit.SECONDS.toMillis(3);
        System.out.println("Millis: " + millis);

        // AtomicInteger is in another subpackage,
        // here the fully qualified name is used instead of importing.
        java.util.concurrent.atomic.AtomicInteger counter =
                new java.util.concurrent.atomic.AtomicInteger(4);
        System.out.println("Counter: " + counter.addAndGet(2));

        // String belongs to java.lang, which is implicitly imported.
        String name = "Java";
        System.out.println("Name: " + name);

        // Method belongs to java.lang.reflect;
        // requires a separate import at the top of the file.
        Method method = String.class.getMethod("substring", int.class);
        System.out.println("Method: " + method.getName());

        // Entry is a nested member type inside Map, NOT a subpackage.
        Map.Entry<String, Integer> entry = Map.entry("id", 7);
        System.out.println("Entry: "
                + entry.getKey() + "=" + entry.getValue());
    }
}
```

From the directory containing `src`, with **JDK 17 or later**. **Before running `javac -d out` for the first time, create the `out` directory**: on Bash/Linux/macOS run `mkdir -p out`; on PowerShell run `New-Item -ItemType Directory -Force out | Out-Null` (CMD: `if not exist out mkdir out`). Once `out` exists, compile and run on Windows PowerShell/CMD or Linux/macOS:

```bash
javac -encoding UTF-8 -d out src/lesson/ImportSubpackageDemo.java
java -cp out lesson.ImportSubpackageDemo
```

`-d out` tells `javac` to generate the directory structure for `.class` files according to the package; `lesson.ImportSubpackageDemo` is the fully qualified name of the class containing `main`.

**Exact stdout** (a successful `javac` command prints no lines):

```text
Words: [Java, core]
Millis: 3000
Counter: 6
Name: Java
Method: substring
Entry: id=7
```

**Explanation of output:**

1. `List`, `ArrayList`, and `Map` are recognized via `import java.util.*;`.
2. `TimeUnit` is recognized via `import java.util.concurrent.TimeUnit;`, not via the wildcard on `java.util`.
3. `AtomicInteger` uses its **fully qualified name** `java.util.concurrent.atomic.AtomicInteger`, so no separate import is needed.
4. `String` is usable via the implicit `java.lang` import, while `Method` requires a separate import from `java.lang.reflect`.
5. `Map.Entry` is a **nested type** (member type) inside `Map`, not a class in a package named `java.util.Map`.

There is no need to add `import java.util.concurrent.*;` to the example because one type `TimeUnit` is explicitly imported, while `AtomicInteger` is referenced by its fully qualified name. That presentation clearly shows the difference between the three mechanisms.

## 5. Difference between subpackages and nested types

Dots in a Java name can appear in a **package name** or in a **member type name**. Those are two distinct constructs.

**Subpackage:**

```java
java.util.concurrent.TimeUnit
```

Here `java.util.concurrent` is the package containing class `TimeUnit`. It is not imported by `import java.util.*;`.

**Nested type:**

```java
java.util.Map.Entry
```

Here `Map` is an interface in `java.util`, while `Entry` is a member interface nested inside `Map`. You can write:

```java
import java.util.Map;

// Inside a method:
Map.Entry<String, Integer> item = Map.entry("key", 10);
```

Or import the member type directly:

```java
import java.util.Map.Entry;

// Inside a method:
Entry<String, Integer> item = java.util.Map.entry("key", 10);
```

In particular, `import java.util.Map.*;` is a form of **type-import-on-demand** for accessible member types of `Map` — completely different from `import java.util.*;`, which selects top-level types from package `java.util`. Do not mistake the dot between `Map` and `Entry` for a subpackage of `java.util`.

When reading a multi-part name, clearly determine whether each segment is a **package, top-level type, or member type**, rather than guessing that every segment between dots is a directory level.

## 6. No inheritance of access rights between parent and child packages

The naming relationship between `com.example` and `com.example.feature` **does not create an internal access relationship**. A member or top-level class with **package-private** access (no access modifier written) is only accessible from code in the **exact same package**, not automatically opened to code in a package sharing the same prefix.

Two-file illustrative example:

**`src/com/example/Helper.java`**

```java
package com.example;

class Helper {
    static void ping() {
        System.out.println("ping");
    }
}
```

**`src/com/example/feature/Feature.java`**

```java
package com.example.feature;

// import com.example.Helper; // ERROR: Helper is not public

public class Feature {
    public static void main(String[] args) {
        // com.example.Helper.ping(); // Access ERROR
        System.out.println("Feature");
    }
}
```

This is an example **explaining access rights**, separate from the program in section 4. Even if you write the fully qualified name `com.example.Helper`, the package-private rule still prevents `Feature` from accessing it. `import` or placing a folder inside `com/example` **does not change access modifiers**.

If it needs to be used from another package, expose the type appropriately (usually `public`), and the members to be called must also have corresponding accessibility.

## 7. How to self-check when the compiler reports an unrecognized name

A common situation is writing `import java.util.*;` yet `TimeUnit` is still reported as not found. Check in order:

1. **Identify the type's true fully qualified name:** `TimeUnit` is `java.util.concurrent.TimeUnit`, not `java.util.TimeUnit`.
2. **Verify importing the right package:** write `import java.util.concurrent.TimeUnit;` or `import java.util.concurrent.*;`, not just `import java.util.*;`.
3. **Try the fully qualified name at the point of use:** `java.util.concurrent.TimeUnit.SECONDS.toMillis(3)`. If valid, the issue is likely name lookup/import.
4. **Check access rights:** is the class/member accessible from the current package? Imports do not bypass access rules.
5. **Check the classpath or module path if it is an external library:** imports only resolve names; they do not download libraries or add paths. With the module system, appropriate readability/exports relationships are required.
6. **Do not add imports just to mask collisions:** when two types with the same simple name come from different packages, use an appropriate single-type import or fully qualified names.

**Intentional error example** (not a standalone runnable program):

```java
import java.util.*;

// Inside a method:
// TimeUnit.SECONDS.toMillis(1); // Missing import java.util.concurrent.TimeUnit
// AtomicInteger n = new AtomicInteger(0); // Missing import java.util.concurrent.atomic.AtomicInteger
```

You do not need to memorize every package name, but you must look up the exact **package that directly declares the type** rather than inferring from a prefix.

## 8. Common errors and misconceptions

| Misconception | Correct conclusion |
| --- | --- |
| "`import a.b.*;` also imports `a.b.c.*;`." | **False.** Each package is a separate namespace; wildcards are not recursive. |
| "`java.lang` is implicitly imported, so `java.lang.reflect.Method` is imported too." | **False.** Subpackages are not automatically imported. |
| "`import java.util.concurrent.*;` brings in `AtomicInteger` too." | **False.** `AtomicInteger` is in `java.util.concurrent.atomic`. |
| "Writing the fully qualified name still requires adding an `import`." | **False.** The fully qualified name refers directly to the type without importing it. |
| "`Map.Entry` is a subpackage of `Map`." | **False.** `Entry` is a member type nested inside `Map`. |
| "Package `com.example.sub` can access all package-private members in `com.example`." | **False.** The two packages are different. |
| "`import` loads all classes into memory before running." | **False.** Import is a compile-time name-resolution mechanism and does not initialize all classes. |
| "Having an `import` means no dependency/classpath is needed anymore." | **False.** The compiler/JVM must still find an accessible type definition. |

**Key takeaway:** `import package.*` only applies to eligible types **directly inside that package**; it does not automatically include subpackages sharing the same prefix. To use a type from a subpackage, **import the exact subpackage/type** or **write the type's fully qualified name**.