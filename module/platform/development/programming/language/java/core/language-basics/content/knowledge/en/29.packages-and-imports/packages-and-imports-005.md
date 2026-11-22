# Static Import for Static Members (Java 17+)

## 1. What is static import?

`static import` allows using the **short name** of an accessible `static` member from another class or interface, instead of always writing `TypeName.memberName`. This is a **compile-time** name-resolution syntax; it does not create a copy of the member, does not turn the member into a local variable, and does not change the method's behavior or performance.

For example, replace `Math.PI` and `Math.pow(2, 3)` with `PI` and `pow(2, 3)` when the corresponding import declarations are present. Both forms still access the exact same members of `java.lang.Math`.

## 2. Syntax and placement

`import static` declarations go **after the `package` line (if any), before type declarations**, at the same level as regular `import` statements:

```java
package lesson;

import java.util.List;              // import the type name List
import static java.lang.Math.PI;    // a single static field
import static java.lang.Math.pow;   // a static method (all overloads with the same name)
import static java.lang.Math.*;     // all accessible static members, on demand
```

The two lines `import static java.lang.Math.PI;` and `import static java.lang.Math.*;` are placed side by side here to illustrate syntax; in real code only use the declarations you need and avoid redundant imports.

There are two main forms:

| Form | Syntax | Meaning |
| --- | --- | --- |
| Single static import | `import static pkg.name.TypeName.MEMBER;` | Brings the name of one static member into short-name lookup scope |
| Static import on demand | `import static pkg.name.TypeName.*;` | Allows looking up accessible static members of that type by short name |

`*` does not import subpackages, does not automatically import members of all classes in a package, and does not import instance members. `static import` does not replace `package`, `classpath`, `module path`, or compiling the class that defines the member.

## 3. Complete example with Math

Create `src/lesson/CircleDemo.java`:

```java
package lesson;

import static java.lang.Math.PI;
import static java.lang.Math.pow;
import static java.lang.Math.max;

public class CircleDemo {
    public static void main(String[] args) {
        double radius = 2.0;
        double area = PI * pow(radius, 2);
        System.out.printf(java.util.Locale.ROOT, "area=%.2f%n", area);
        System.out.println("max=" + max(3, 7));
    }
}
```

Run from the directory containing `src` (Java 17+). **Before using `javac -d out` for the first time, create the `out` directory**: on Bash/Linux/macOS use `mkdir -p out`; on PowerShell use `New-Item -ItemType Directory -Force out | Out-Null` (CMD: `if not exist out mkdir out`). Then compile and run:

```sh
javac -d out src/lesson/CircleDemo.java
java -cp out lesson.CircleDemo
```

Exact output:

```text
area=12.57
max=7
```

`PI` is a `public static final` field, while `pow` and `max` are `public static` methods. The calculation is equivalent to `Math.PI * Math.pow(radius, 2)`; `max(3, 7)` is equivalent to `Math.max(3, 7)`. `Locale.ROOT` ensures the decimal separator in the output is a period regardless of system locale.

## 4. Static import for custom members and nested types

Not only JDK APIs: you can import a static field, a static method, and a static member type from a class you wrote yourself.

Create `src/lesson/util/Toolbox.java`:

```java
package lesson.util;

public final class Toolbox {
    private Toolbox() {}

    public static final int LIMIT = 3;

    public static String label(String name) {
        return "Hi, " + name;
    }

    public static class Token {
        public String text() {
            return "token";
        }
    }
}
```

Create `src/lesson/ToolboxDemo.java`:

```java
package lesson;

import static lesson.util.Toolbox.LIMIT;
import static lesson.util.Toolbox.label;
import static lesson.util.Toolbox.Token;

public class ToolboxDemo {
    public static void main(String[] args) {
        System.out.println("limit=" + LIMIT);
        System.out.println(label("Java"));
        System.out.println(new Token().text());
    }
}
```

Compile both files and run:

```sh
javac -d out src/lesson/util/Toolbox.java src/lesson/ToolboxDemo.java
java -cp out lesson.ToolboxDemo
```

Output:

```text
limit=3
Hi, Java
token
```

`LIMIT`, `label`, and `Token` are all static members of `Toolbox`; `Token` is a **static nested class type**, so it can be used as a type name after a static import. If desired, these three imports could be replaced with `import static lesson.util.Toolbox.*;`; importing individual names is usually easier to read and better at controlling conflicts.

## 5. Which members can be imported?

- **Static fields**: constants like `PI`, `MAX_VALUE`, and other `public static` fields. `final` is not a strict requirement.
- **Static methods**: `Math.max`, `Math.pow`, interface static methods such as `List.of`. Importing by method name allows the compiler to consider all appropriate overloads.
- **Accessible static member types**: for example, `Toolbox.Token` is a static nested class; member types of interfaces are also static by language rule.

Access rules still apply: a `private` member in another class, a `package-private` member outside its package, or a `protected` member without valid access in the current context will not become legal just by adding a static import. You cannot static import **instance** methods or fields; for instance, `import static java.lang.String.length;` is invalid because `length()` is an instance method. To use it, you must call `"abc".length()`.

## 6. Name resolution, collisions, and common traps

**Name collisions:** When multiple on-demand imports bring in applicable methods or fields with the same name, using the short name can be ambiguous. For example, if you use both `import static java.lang.Math.*;` and `import static java.lang.StrictMath.*;`, calling `sqrt(9.0)` by its short name will conflict; you can write `Math.sqrt(9.0)` explicitly or import only the one `sqrt` you need. Methods with the same name still undergo Java's overload selection mechanism.

**Names in nearer scope:** Declarations with the same name in the class or local variables can shadow a statically imported field; member methods can also take precedence during call resolution. When reading code where a short name's origin is hard to trace, writing `ClassName.member` explicitly is safer.

**Import ordering:** `import static` is a file-level declaration; placing it inside a class or method body causes a syntax error. `import java.lang.Math;` only brings the type name `Math` into scope and still requires writing `Math.PI`; to use `PI` by itself, you must write `import static java.lang.Math.PI;`. Java automatically recognizes many types in `java.lang`, but does not automatically static-import their members.

**Wildcards:** `import static some.Type.*;` does not copy all names into local variables, does not import instance members, and is not a mechanism for loading classes immediately at runtime. Overusing wildcards across multiple utility classes can make code harder to read and increase the risk of ambiguous names.

**Dependencies:** Static imports do not create special access permissions; the imported type must be compilable/resolvable from source code or libraries present on the classpath/module path. Renaming or removing a static member in a library can cause code using the import to fail compilation.

## 7. When should you use it?

Consider static imports when a group of operations genuinely appears repeatedly and their origin remains clear: mathematical operations `PI`/`pow`, assertion functions in test code, or enum constants whose context is immediately obvious. Prefer importing **individual names** and avoid importing the same name from two sources.

Keep prefixes like `Math.`, `Collections.`, `Objects.`, or `ClassName.` when stating the origin helps readers quickly understand meaning, especially in business code. Static import is a **readability** choice, not a requirement for calling static members.

## 8. Self-check

1. Is `import java.lang.Math;` enough to write `sqrt(4)`? **No**; write `Math.sqrt(4)` or `import static java.lang.Math.sqrt;`.
2. Can you `import static` an instance method? **No**; an object must provide a receiver for the call.
3. Is `import static lesson.util.Toolbox.Token;` valid when `Token` is a `public static class`? **Yes**, if `Toolbox` is accessible and on the compilation path.
4. When a name collision occurs due to static imports, what is the clearest fix? **Qualify the call with the type name**, or narrow down the imports.

Key takeaway: `static import` shortens names of accessible static members; Java's scope, access control, overloading, and compilation rules still apply as usual.