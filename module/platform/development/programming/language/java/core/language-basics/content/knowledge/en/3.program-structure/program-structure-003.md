# Filename Rules for Public Classes in Java

## 1. The Rule to Remember

With the standard source-file compilation workflow using **`javac`** (JDK 17+), a **top-level class declared `public`** must reside in a `.java` file whose **base name matches the class name**, with exact case matching.

~~~java
// File Greeting.java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Xin chao Java");
    }
}
~~~

The class name is `Greeting`, so the filename must be **`Greeting.java`**. Do not name it `Hello.java`, `greeting.java`, or `Greeting.class`.

If you save the same code in `Hello.java` and run:

~~~bash
javac --release 17 Hello.java
~~~

You will get an error similar to:

~~~text
Hello.java:2: error: class Greeting is public, should be declared in a file named Greeting.java
public class Greeting {
       ^
1 error
~~~

**How to fix:** rename the file to `Greeting.java` **or** change the declaration `public class Greeting` to `public class Hello` and update all references to the class name.

This rule applies to the **source filename and top-level public type declaration at compile time**. It is different from a class-not-found error at runtime and is not fixed by manually renaming the `.class` file.

## 2. Top-Level, Public, and Package-Private

A **top-level class** is a class declared directly in a compilation unit, not nested inside another class or interface.

~~~java
// File Catalog.java
public class Catalog {   // top-level public class
}

class CatalogItem {       // top-level package-private class
}
~~~

In this example, `Catalog.java` is valid because there is **one** top-level public class named `Catalog`; the class `CatalogItem` is not `public`, so it does not need a separate file just because its name differs from the source filename.

| Case | Valid when compiled with javac? | Reason |
|---|---|---|
| `public class A` in `A.java` | Yes | Name matches |
| `public class A` in `B.java` | No | Top-level public class name differs from filename |
| `class A` in `B.java` | Yes | Top-level class is not public |
| `public class A` and `class B` in `A.java` | Yes | Only `A` is public |
| `public class A` and `public class B` in `A.java` | No | Two top-level public types cannot both satisfy the naming rule |

Omitting `public` at the top level gives **package-private** access, meaning appropriate code in the same package can reference it. That does not prevent the class from having a `main` method or producing a bytecode file.

A class **nested inside** another class (*nested class*) is not a top-level class, so it is not subject to this "one dedicated filename" rule in the same way.

## 3. Compiling and Running a Properly Named Public Class

Save the first example in `Greeting.java` and open a terminal in the directory containing the file. Check the JDK:

~~~bash
java -version
javac -version
~~~

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 Greeting.java
java -cp . Greeting
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\Greeting.java
java -cp . Greeting
~~~

Output:

~~~text
Xin chao Java
~~~

After compiling, the directory normally contains:

~~~text
Greeting.java
Greeting.class
~~~

- `javac` takes the **source filename** `Greeting.java`.
- `java` in **class mode** takes the **class name** `Greeting`, not `Greeting.java` or `Greeting.class`.
- `-cp .` specifies the current directory as the classpath root.
- `--release 17` asks the compiler to produce Java 17-compatible code within the capabilities of the JDK in use; the compiler must support that release.

Try putting the content of `Greeting.java` into `Welcome.java` while keeping `public class Greeting`. The compiler will reject it. If you change the declaration to `public class Welcome`, you can run:

~~~bash
javac --release 17 Welcome.java
java -cp . Welcome
~~~

and receive the same output line. **The class name and filename must be changed together.**

## 4. Files Without a Public Class: Source Name Need Not Match the Runnable Class Name

Create the file **`Examples.java`**:

~~~java
class Printer {
    static void show(String text) {
        System.out.println(text);
    }
}

class Runner {
    public static void main(String[] args) {
        Printer.show("Da chay Runner");
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 Examples.java
java -cp . Runner
~~~

Output:

~~~text
Da chay Runner
~~~

Normally `javac` generates **`Printer.class`** and **`Runner.class`**, even though the source file is named **`Examples.java`**. No class named `Examples` is declared, so `java Examples` is not the right command to run.

Conclusions from the example:

1. One source file can contain multiple non-`public` top-level classes.
2. One source file can produce multiple `.class` files.
3. The `main` method can reside in a non-public top-level class; that class can still be selected to launch in Java 17.
4. Although the rule allows a filename to differ from package-private class names, projects are usually easier to maintain when files are organized by their primary class name.

## 5. Do Not Write Two Top-Level Public Classes in the Same File

**Invalid** example in `Alpha.java`:

~~~java
public class Alpha {
}

public class Beta {
}
~~~

`javac Alpha.java` will report an error because `public class Beta` requires the file **`Beta.java`**.

The standard fix is to split them into two files:

**`Alpha.java`:**

~~~java
public class Alpha {
    public static void main(String[] args) {
        Beta.hello();
    }
}
~~~

**`Beta.java`:**

~~~java
public class Beta {
    public static void hello() {
        System.out.println("Hello from Beta");
    }
}
~~~

From the directory containing both files:

~~~bash
javac --release 17 Alpha.java Beta.java
java -cp . Alpha
~~~

Output:

~~~text
Hello from Beta
~~~

Not every class needs `main`: `Alpha` serves as the entry point, and `Beta` is a collaborating class. The filename rule still applies to both because both are **top-level public classes**.

## 6. With a Package, the Filename Still Matches the Simple Class Name

Create a project:

~~~text
project/
└── src/
    └── demo/
        └── Launcher.java
~~~

**`src/demo/Launcher.java`:**

~~~java
package demo;

public class Launcher {
    public static void main(String[] args) {
        System.out.println("Package demo OK");
    }
}
~~~

Here:

- Source filename: **`Launcher.java`**.
- Simple class name: **`Launcher`**.
- Fully qualified class name: **`demo.Launcher`**.
- `demo` is the package name; do not name the file `demo.Launcher.java`.

From the `project` directory:

**Bash:**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/demo/Launcher.java
java -cp out demo.Launcher
~~~

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out .\src\demo\Launcher.java
java -cp out demo.Launcher
~~~

Output:

~~~text
Package demo OK
~~~

After compilation, the bytecode file is located at **`out/demo/Launcher.class`**. The run command uses `demo.Launcher`; the classpath must point to **`out`**, not `out/demo`.

Mirroring packages in the source directory structure is a good convention and convenient for build tools. However, the **base filename rule for a public class** is still `Launcher.java`: the package name is not prepended to the filename.

## 7. Public Nested Classes Do Not Need a Separate File

Create **`Outer.java`**:

~~~java
public class Outer {
    public static class Inner {
        public static String greeting() {
            return "Inner";
        }
    }

    public static void main(String[] args) {
        System.out.println(Inner.greeting());
    }
}
~~~

Run:

~~~bash
javac --release 17 Outer.java
java -cp . Outer
~~~

Output:

~~~text
Inner
~~~

`Outer` is the top-level public class, so the file is named `Outer.java`. `Inner` is a **nested public class**, so it does not need an `Inner.java` file. The compiler normally generates the class files `Outer.class` and `Outer$Inner.class`.

If you move `public class Inner` **outside** the body of `Outer`, it becomes a top-level class; at that point, two public classes require two separate files.

## 8. The Rule Also Applies to Other Top-Level Public Types

In Java 17, it is not only `class` that requires a matching filename:

| Top-level declaration | Filename |
|---|---|
| `public class Account` | `Account.java` |
| `public interface Payment` | `Payment.java` |
| `public enum Status` | `Status.java` |
| `public record Point(int x, int y)` | `Point.java` |
| `public @interface Tracked` | `Tracked.java` |

Example **`Point.java`**:

~~~java
public record Point(int x, int y) {
}
~~~

Run `javac --release 17 Point.java` to compile. If you keep `public record Point` and rename the source file to `Coordinate.java`, the naming error will appear.

Do not infer that every interface, enum, or record must be `public`. A top-level type without the `public` modifier can use package-private access just like ordinary classes.

## 9. Distinguishing Compile Errors from Launch Errors

| Symptom | Phase | What to fix |
|---|---|---|
| `class X is public, should be declared in a file named X.java` | `javac` | Rename the source file or the top-level public type |
| Two top-level public types in one source file | `javac` | Split into two source files |
| `Could not find or load main class` | `java` locating class | Check fully qualified name, classpath root, and bytecode file |
| `Main method not found` | `java` locating entry point | Add a valid `main` method to the class you intend to run |
| Running shows old output after editing source | Runtime | Save source, recompile, and check the right classpath |
| `UnsupportedClassVersionError` | JVM loading bytecode | Check the runtime and release build level; this is not a source naming error |

**Remember:** the filename error happens **before running**, during the `javac` compilation step. Changing the classpath or adding `-cp` will not resolve this error.

Conversely, a properly named public class that compiles cleanly can still fail to launch if the package/classpath is wrong or `main` is missing.

## 10. Common Points of Confusion

**Case sensitivity.** `public class Order` requires `Order.java`. On case-sensitive systems, `order.java` can be a completely different file. Always use exact casing to avoid issues when moving projects to Linux.

**Filename and package name are separate.** `public class App` in `package demo;` still lives in `App.java`; when running in class mode, use `demo.App`.

**Class with `main` that is not public.** This does not require the source file to bear the class's name. For instance, `Runner` in `Examples.java` can still run if it has a valid `main` and the right classpath.

**Public class without `main`.** Compilation is still valid; a library class does not necessarily have its own entry point.

**One source file producing multiple bytecode files.** Multiple top-level classes or nested classes can cause `javac` to emit multiple `.class` files. Do not manually rename bytecode outputs to work around a public class naming error.

**`java File.java` differs from `java ClassName`.** Java 11+ supports source-file launching with its own rules. In this lesson, to verify the filename rule for top-level public types, run `javac File.java` first, then `java ClassName`. Do not use source-file mode behavior as evidence to contradict the `javac` source-file compilation rule.

## 11. Exercises with Answers

### Exercise A — choose the filename

~~~java
public class PaymentService {
}
~~~

**Answer:** place it in `PaymentService.java`, with exact case. Do not use `paymentservice.java`.

### Exercise B — one public and one package-private class

File **`Demo.java`**:

~~~java
class Helper {
    static int twice(int x) { return x * 2; }
}

public class Demo {
    public static void main(String[] args) {
        System.out.println(Helper.twice(6));
    }
}
~~~

Compile:

~~~bash
javac --release 17 Demo.java
java -cp . Demo
~~~

**Answer:** valid; prints **`12`**. `Demo` is the top-level public class matching the filename, and `Helper` is not public so it can stay in the same file.

### Exercise C — distinguish two issues

File **`Hello.java`** contains:

~~~java
package demo;
public class Welcome {
    public static void main(String[] args) {
        System.out.println("Hi");
    }
}
~~~

**Answer:** `javac Hello.java` reports a naming error because it must be **`Welcome.java`**. After fixing the source name and compiling with `-d out`, the run command must use **`java -cp out demo.Welcome`** because the class belongs to package `demo`.

### Exercise D — two top-level public classes

File `A.java` has both `public class A` and `public class B`. State how to fix it.

**Answer:** split into `A.java` and `B.java`, each keeping its corresponding public class. If `B` only needs to be used inside the package and the design permits, another option is to remove `public` from `B`; do not arbitrarily change a public API when other code depends on it.

### Exercise E — nested class

Given `public class Outer` containing `public static class Inner`, is it necessary to create `Inner.java`?

**Answer:** **no**. `Inner` is not a top-level type; `Outer.java` is the file that must match the name of `Outer`.

## 12. Checklist

- [ ] Explain why a top-level `public class X` requires the file `X.java`.
- [ ] Distinguish a top-level class, a package-private class, and a nested public class.
- [ ] Know when multiple classes can live in one file and when they must be split.
- [ ] Avoid confusing the `.java` filename with the class name used in the `java` command.
- [ ] Run the `Greeting.java` and `demo.Launcher` examples on JDK 17+.
- [ ] Know the rule for top-level `public interface`, `public enum`, `public record`, and `public @interface`.
- [ ] Read the `should be declared in a file named...` error and fix the root cause.
- [ ] Distinguish source-naming errors at compile time from classpath/main errors at launch time.

**Conclusion:** The central rule when compiling with `javac` is that **the `.java` source filename must match the name of the top-level `public` type declared inside it**. Non-public top-level classes and nested classes do not follow this requirement in the same way. When running compiled classes, `java` takes the class name (including the package if present), so you must distinguish the source name, class name, and bytecode location.
