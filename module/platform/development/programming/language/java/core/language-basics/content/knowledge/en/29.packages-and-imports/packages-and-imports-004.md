# Single-Type Import and On-Demand Import with `*` — Java 17+

## 1. What problem does `import` solve?

Every Java type belongs to a package (except types in the *unnamed package*). When using a type located outside the current package, you can write its **fully qualified name** or use `import` to write its **short name** in source code.

~~~java
java.util.List<String> names = java.util.List.of("An", "Binh");
~~~

Equivalent when declaring an appropriate import:

~~~java
import java.util.List;

// Inside a class:
List<String> names = List.of("An", "Binh");
~~~

`import` assists with **compile-time name lookup**; it does not create objects, automatically execute code in the imported class, or copy library source code into the file.

## 2. Two syntaxes to recognize

| Syntax | Name | Meaning |
|---|---|---|
| `import java.util.List;` | **Single-type-import declaration** | Allows using the short name `List` for **one specific type** |
| `import java.util.*;` | **Type-import-on-demand declaration** | Allows using short names of **accessible types** in package `java.util` when resolving names |
| `java.util.List.of(...)` | Fully qualified type name, not an import | No `import` declaration needed for `List` |
| `import static java.lang.Math.PI;` | Single-static-import | Imports a **static member**; different from importing a type |
| `import static java.lang.Math.*;` | Static-import-on-demand | Imports static members on demand; not `import java.lang.Math.*;` |

The `*` in `import java.util.*;` **does not mean** copying or instantiating all classes in the package. The compiler only uses import declarations to resolve names that appear in code.

In Java 17, only a **standalone** `*` at the end of an import-on-demand declaration is valid: there is no syntax like `import java.util.L*;` to filter by prefix.

## 3. `*` does not recursively search subpackages

`import java.util.*;` allows using types directly accessible from `java.util` such as `List` and `Map`, but it does not automatically bring `java.util.concurrent.TimeUnit` into short-name scope:

~~~java
long seconds = java.util.concurrent.TimeUnit.MINUTES.toSeconds(1); // 60
~~~

To use `TimeUnit` without a prefix, declare `import java.util.concurrent.TimeUnit;`. The lesson on subpackages further analyzes types like `AtomicInteger`, `Method`, and the difference between subpackages and nested types.

## 4. When to use short names vs. fully qualified names?

~~~java
import java.util.List;

List<String> a = List.of("A");
java.util.List<String> b = java.util.List.of("B");
~~~

Both use the type `java.util.List`.

- Use **single-type import** when only a few types are needed: it makes exact dependencies easy to spot.
- Use **import-on-demand** when working with many types in the same package: fewer import lines, though it is harder to see every type used at a glance.
- Use **fully qualified names** when you need to disambiguate between types with the same name, or at a single occurrence.
- IDEs often add, collapse, or sort imports automatically; this is a code formatting choice and does not change the behavior of the types themselves.

**Neither form of import changes the features of `List` or the structure of the object.** The difference lies mainly in name resolution.

## 5. When two packages have types with the same name

~~~java
import java.util.List;
import java.awt.*;

// Inside a class:
List<String> names = List.of("An"); // java.util.List
~~~

An explicit single-type import selects `List` even when a wildcard also covers `java.awt.List`. With two wildcards `java.util.*` and `java.awt.*`, the name `List` can become ambiguous; two single-type imports for different types with the same simple name cause an error right at the import declarations. Java has no "last import wins" rule. Use a qualified name when you must specify which type you mean; the lesson on handling two classes with the same name goes deeper into precedence rules.

## 6. Importing nested types and `java.lang`

A nested type (*member type*) can be imported directly:

~~~java
import java.util.Map.Entry;

// Inside a class:
Entry<String, Integer> item =
        java.util.Map.entry("An", 10);
~~~

`Entry` is a nested type of `Map`; here `Map.entry(...)` is written using `Map`'s fully qualified name because the example only imports `Entry`.

Common types such as `String`, `System`, `Integer`, and `Math` belong to `java.lang`, and accessible types in `java.lang` are **implicitly imported on demand** by Java; you usually do not need to write `import java.lang.String;`.

Types declared in the **same package** can also use short names when not shadowed or conflicted under Java's rules.

## 7. Placement of `package` and `import`

The standard order in a `.java` file:

~~~java
package demo;

import java.util.List;
import java.time.*;

public class Example {
    // ...
}
~~~

1. The `package` declaration (if any), after comments and whitespace.
2. The `import` declarations, before any top-level type declarations.
3. The `class`, `record`, `interface`, `enum`... declarations of the file.

Do not place `import` inside a method body or after a top-level class declaration. A semicolon `;` is required at the end of every `package`/`import` declaration.

A file may have **at most one package declaration**. A package name is not a file path automatically created by `import`; at runtime, the classpath and fully qualified class name must still match the compiled `.class` file.

## 8. Standalone runnable Java 17+ program

Create a file named **`ImportKindsDemo.java`** in your working directory with the full contents:

~~~java
package demo;

import java.util.List;       // Import one specific type.
import java.util.*;          // Other types in java.util as needed.
import java.time.*;          // Another package, separate import-on-demand.
import java.util.Map.Entry;  // Specific nested type.

public final class ImportKindsDemo {
    private ImportKindsDemo() {}

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        ArrayList<String> copy = new ArrayList<>(names);
        copy.add("Chi");

        LocalDate date = LocalDate.of(2026, 10, 16);
        Map<String, Integer> scores = Map.of(
                "An", 10, "Binh", 20);
        Entry<String, Integer> pair = Map.entry("Chi", 30);

        System.out.println("names=" + names);
        System.out.println("copy=" + copy);
        System.out.println("date=" + date);
        System.out.println("score An=" + scores.get("An"));
        System.out.println("entry=" + pair.getKey() + ":" + pair.getValue());

        System.out.println("max=" + Collections.max(copy));
        System.out.println("length=" + "Java".length());
        System.out.println("qualified="
                + java.util.List.of("X", "Y").size());
        System.out.println("time unit="
                + java.util.concurrent.TimeUnit.MINUTES.toSeconds(2));
    }
}
~~~

How to read the import lines: `List` is selected via the explicit declaration; `ArrayList`, `Map`, and `Collections` via `java.util.*`; `LocalDate` via `java.time.*`; `Entry` via the nested-type import; `String` is `java.lang.String`, known implicitly; `TimeUnit` is used via its **fully qualified name**, without importing `java.util.concurrent`.

**Compile** from the directory containing `ImportKindsDemo.java`. The `-d .` option places the `.class` file into the matching package directory (`demo/`); you do not have to pre-create a `demo` source directory to run this single-file example.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 -d . ImportKindsDemo.java
java -cp . demo.ImportKindsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 -d . .\ImportKindsDemo.java
java -cp . demo.ImportKindsDemo
~~~

### Exact expected stdout

~~~text
names=[An, Binh]
copy=[An, Binh, Chi]
date=2026-10-16
score An=10
entry=Chi:30
max=Chi
length=4
qualified=2
time unit=120
~~~

The output does not depend on `Map.of` iteration order, because the program **only looks up the entry by key** `"An"` rather than printing the whole map directly. No `--enable-preview` is needed.

## 9. Common mistakes and fixes

| Mistake | Why is it wrong? | How to fix |
|---|---|---|
| Writing `import java.util.*;` and assuming `TimeUnit` is included | Does not include subpackage `concurrent` | Import separately or use the fully qualified name |
| `import java.util.L*;` | Not valid Java syntax | `import java.util.List;` or `import java.util.*;` |
| Importing both `java.util.*` and `java.awt.*`, then using `List` | Two types with the same name cause ambiguity | Single-type import or qualified name |
| Two single-type imports for two different `List` types | Declaration conflict | Import only one, and use the fully qualified name for the other |
| Placing `import` inside `main` | Imports may only appear at the top of a compilation unit | Place after `package`, before the class |
| Thinking wildcards load classes at runtime immediately | Import is a compile-time name-resolution mechanism | Do not infer class loading from import syntax |
| Thinking `java.lang.String` must always be imported | `java.lang` is implicitly imported on demand | Use `String` directly |
| Running `java Demo` when the class is in `package demo` | Missing fully qualified binary name | `java -cp . demo.ImportKindsDemo` |
| Confusing `import static` with type import | One imports static members | Choose the right syntax for what is being used |

## 10. Exercises with answers

**A.** Write an import specifically for `ArrayList` from package `java.util`.  
**Answer:** `import java.util.ArrayList;`

**B.** With `import java.time.*;`, can you use `LocalDate` directly?  
**Answer:** **Yes**, because `LocalDate` belongs to package `java.time`.

**C.** With `import java.util.*;`, can you use `TimeUnit` directly?  
**Answer:** **No**, because `TimeUnit` belongs to `java.util.concurrent`; add `import java.util.concurrent.TimeUnit;` or write the fully qualified name.

**D.** Given `import java.util.List;` and `import java.awt.*;`, which type does an unqualified `List` select?  
**Answer:** `java.util.List`, according to the explicit single-type import declaration.

**E.** Without importing `List`, can you declare `java.util.List<String> names;`?  
**Answer:** **Yes**, using the fully qualified name requires no import.

**F.** Does importing `java.util.*` make Java load every class in that package at startup?  
**Answer:** **No**; wildcard imports participate in name resolution within the compilation unit and do not instruct the JVM to load all classes.

## 11. Checklist and conclusion

- [ ] Distinguish single-type import `import a.b.Type;` from type-import-on-demand `import a.b.*;`.
- [ ] Know that wildcard `*` does not include subpackages and does not filter by prefix.
- [ ] Know how to use a fully qualified type name when avoiding imports.
- [ ] Recognize simple-name collisions and ambiguous imports.
- [ ] Do not treat the order of import lines as a precedence order.
- [ ] Distinguish type imports from `import static`.
- [ ] Understand the placement of `package`, `import`, and top-level types in a file.
- [ ] Understand that `java.lang` is implicitly imported on demand.
- [ ] Know `javac -d .` and the `package.Class` form when running a packaged program.
- [ ] Compile and run `ImportKindsDemo.java` on JDK 17+ and verify the exact stdout.

**Conclusion:** `import package.Type;` brings **one specific type** into short-name usage; `import package.*;` allows resolving **accessible types directly in that package** as needed. `*` does not recursively import subpackages and does not preload all classes; when names collide, use an explicit single-type import or the fully qualified type name.