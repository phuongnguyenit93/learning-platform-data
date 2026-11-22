# Using `javac` to Check Syntax and Compile-Time Errors in Java Pattern Matching

## 1. Why is `javac` the First Verification Step?

When writing Java code—especially with **type patterns**, **record patterns**, `switch` expressions, and `when`—developers easily confuse three categories of issues:

1. **Syntax/parsing errors**: writing a Java construct with invalid grammar, such as a missing `;`, a missing `}`, a malformed `case` label, or a misplaced `yield`.
2. **Compile-time semantic errors**: the code can be parsed, but is **invalid with respect to types, scope, or language rules**; for example, a record pattern with the wrong number of components, a `case` branch that is dominated, or a non-exhaustive `switch` expression.
3. **Runtime or business logic errors**: the code compiles successfully, but at runtime throws a `NullPointerException`, mishandles input, returns unexpected results, or violates domain rules.

**`javac`** (the Java compiler) checks both syntax **and** many other compile-time rules, then generates `.class` bytecode if successful. Therefore, saying “run `javac` to check syntax” is shorthand; more accurately, it **compiles and checks compile-time validity**, rather than just running a bracket/punctuation parser.

An important lesson: **`javac` reporting no errors does not prove the program is correct at runtime.** Compiling and running/testing are two different steps:

~~~text
.java source code
    |
    v
javac: syntax parsing + type/language checks + dependency resolution
    |
    +-- Errors -> diagnostics, non-zero exit code
    |
    +-- Success -> .class bytecode
                         |
                         v
                    java: run the program
                         |
                         v
                    test runtime behavior
~~~

This article targets **Java 21+**, because record patterns and pattern matching for `switch` are finalized in Java 21; in Java 17, `instanceof` type patterns are finalized, but many `switch` pattern syntaxes were still in preview or did not yet exist in their finalized form.

## 2. Check the JDK and Compiler Version Before Analyzing Errors

Open a terminal or PowerShell and check:

~~~bash
java -version
javac -version
~~~

The two commands serve different purposes:

- `java`: the Java launcher/runtime for **running** a class or program.
- `javac`: the compiler included in the **JDK** for compiling source code into `.class` files.

If the terminal reports `javac: command not found` or PowerShell reports `javac is not recognized`, you cannot yet conclude that the Java file has a syntax error: the issue may be that **the JDK is not installed** or `PATH` does not point to the right toolchain. Use JDK 21 or later to compile the examples in this article.

Especially on machines with multiple JDKs installed, `java -version` and `javac -version` can differ due to `PATH`/`JAVA_HOME`. When a file uses Java 21 features but the actual compiler is too old, messages like “source release ... not supported” or “preview feature ...” may reflect an **environment** issue rather than invalid code.

**Rule of thumb:** check the **compiler version** first, then pin source compatibility in the build command. Do not look only at the JRE version running the application.

## 3. Minimal Command: Compiling a Single `.java` File

Suppose the file is named **`Hello.java`**:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
~~~

From the directory containing the file, run:

~~~bash
javac Hello.java
java Hello
~~~

Output:

~~~text
Hello Java
~~~

If compilation succeeds, `javac` usually **prints no success message**; it creates `Hello.class`. With the command above, the class file is placed next to the source file by default. If there are errors, the compiler prints diagnostics and exits with a **non-zero exit code**.

**File/class rule:** when there is a **top-level public class `Hello`**, the source must be placed in a file named **`Hello.java`**. Running `javac Hello.java` is not the same as launching a Java source file directly with `java Hello.java`; when doing serious compile-time verification, invoke `javac` to get diagnostics and control the output.

## 4. Recommended Command for Java 21: Release, Encoding, and Output Directory

In small projects, avoid scattering `.class` files among source files:

~~~bash
mkdir out
javac --release 21 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
java -cp out JavacPatternSyntaxDemo
~~~

Meaning of each component:

| Component | Purpose |
| --- | --- |
| `javac` | Uses the actual Java compiler |
| `--release 21` | Checks source against Java 21 rules, targets Java 21 bytecode, and restricts JDK/Java SE APIs to those supported in that release |
| `-encoding UTF-8` | Decodes the `.java` file as UTF-8, important for comments and Vietnamese strings |
| `-d out` | Places output class files under the `out` directory |
| `JavacPatternSyntaxDemo.java` | Path to the source file to compile |
| `java -cp out JavacPatternSyntaxDemo` | Runs the compiled class; `-cp` specifies the runtime classpath |

Creating the `out` directory beforehand with `mkdir out` keeps the command consistent across environments and avoids relying on tool-specific directory creation behavior.

**Notes on `--release`:**

- `--release 21` differs from just using `-source 21 -target 21`. `--release` also restricts the **platform APIs** available to the target release.
- Do not combine `--release` with `--source` or `--target` in the same command, as these options conflict according to the `javac` documentation.
- The JDK compiler must support the chosen release; an older JDK **cannot** compile Java 21 code simply by adding `--release 21`.
- Record patterns and pattern matching for `switch` are finalized in Java 21, so **`--enable-preview` is not needed** for the examples here.
- `--release 17` is not a way to validate Java 21 code; it enforces Java 17 syntax/types and APIs, so many Java 21 constructs will be rejected.

In PowerShell, you can check the exit code of the last command:

~~~powershell
javac --release 21 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
if ($LASTEXITCODE -ne 0) {
    throw "Compile failed (exit code $LASTEXITCODE)"
}
java -cp out JavacPatternSyntaxDemo
~~~

Do not run `java` against stale class output if `javac` just failed: it can create the illusion that the new code works while the JVM is actually executing bytecode from a previous compilation.

## 5. Valid Example: Java 21 Record Patterns and `switch`

Create a file named **`JavacPatternSyntaxDemo.java`** with the following code:

~~~java
public class JavacPatternSyntaxDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static String describe(Shape shape) {
        return switch (shape) {
            case null -> "Không có hình";

            case Circle(var r) when r <= 0 ->
                "Bán kính không hợp lệ";

            case Circle(var r) ->
                "Hình tròn r=" + r;

            case Rectangle(var w, var h)
                    when w <= 0 || h <= 0 ->
                "Kích thước không hợp lệ";

            case Rectangle(var w, var h) -> {
                int area = w * h;
                yield "Hình chữ nhật S=" + area;
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(3)));
        System.out.println(describe(new Circle(0)));
        System.out.println(describe(new Rectangle(2, 5)));
        System.out.println(describe(new Rectangle(0, 7)));
        System.out.println(describe(null));
    }
}
~~~

Compile and run:

~~~bash
mkdir out
javac --release 21 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
java -cp out JavacPatternSyntaxDemo
~~~

**Output:**

~~~text
Hình tròn r=3
Bán kính không hợp lệ
Hình chữ nhật S=10
Kích thước không hợp lệ
Không có hình
~~~

What the compiler verifies:

1. `Shape` is a sealed interface and permits only `Circle` and `Rectangle`.
2. `Circle(var r)` has exactly one component; `Rectangle(var w, var h)` has exactly two.
3. `var r`, `var w`, and `var h` are inferred from the record component types (all `int` here).
4. Pattern variables are only used where they are definitely matched, including the guard and the corresponding `case` body.
5. The guarded `case` precedes the unguarded `case` for the same record, avoiding dominance.
6. The `switch` expression covers both subtypes of `Shape`, and handles a null selector with `case null`.
7. The branch with a block `{ ... }` uses `yield` to produce the value of the `switch` expression.

**What `javac` cannot determine:** in a real business system, whether a negative radius should throw an exception instead of returning a message; whether the `int` area can overflow; and whether the displayed text meets requirements. These require tests and design decisions.

## 6. Diagnosing Syntax Errors: Missing Punctuation or Invalid Structure

An example that **intentionally fails to compile**:

~~~java
public class SyntaxError {
    static int calculate() {
        int n = 1
        return n;
    }
}
~~~

The compiler typically points near the end of the line missing `;` with the message:

~~~text
error: ';' expected
~~~

Fix:

~~~java
public class SyntaxError {
    static int calculate() {
        int n = 1;
        return n;
    }
}
~~~

Common syntax errors:

- Missing `;` at the end of a variable declaration or a statement that requires a semicolon.
- Missing `}`, causing the parser to report an error near the end of the file (e.g., `reached end of file while parsing`).
- Malformed `case` label structure; for example, `case String s when ...` with `->` placed incorrectly.
- Writing `yield` directly after the arrow like `case 1 -> yield 10;`; in a `switch` expression, use `case 1 -> 10;` or `case 1 -> { yield 10; }`.
- Forgetting `;` **after the entire `switch` expression** when used as an initializer or a `return` expression statement.

Fix the **first error** first. A single missing brace or semicolon can cause the parser to lose sync and report cascading errors that are not the root cause.

Exact messages and line/column positions can vary across JDK versions; inspect the **source code near the `^` marker and the few lines immediately preceding it**, rather than reading only the message text.

## 7. Non-Syntax Compile-Time Errors: Invalid Record Pattern Structure

The compiler recognizes `Point(...)` syntactically as a record pattern, but it also checks **component count and type compatibility**.

### 7.1. Wrong Number of Components

~~~java
record Pair(int left, int right) {}

// INTENTIONALLY INVALID: Pair has 2 components, pattern only has 1.
// if (value instanceof Pair(var a)) {
//     System.out.println(a);
// }
~~~

A possible diagnostic is:

~~~text
incorrect number of nested patterns
required: int,int
found:    int
~~~

Fix:

~~~java
if (value instanceof Pair(var a, var b)) {
    System.out.println(a + b);
}
~~~

You cannot omit a component from the pattern just because you do not need it. You can give it an ignored name such as `ignored` in the corresponding position: `Pair(var a, var ignored)`.

### 7.2. Wrong Component Type

~~~java
// INTENTIONALLY INVALID: the first component of Pair is int.
// if (value instanceof Pair(String a, int b)) { ... }
~~~

A possible diagnostic is:

~~~text
incompatible types: int cannot be converted to java.lang.String
~~~

Do not conflate `int` with `String` just because both can be formatted as text. Fix it with `Pair(int a, int b)` or `Pair(var a, var b)`.

**Takeaway:** errors in this section belong to **type checking and pattern validity**, not necessarily parser errors. Running `javac` verifies both categories in a single pass.

## 8. Other Compile-Time Errors: Non-Exhaustive `switch`

A `switch` **expression** must cover all possible values according to language rules. For example:

~~~java
// INTENTIONALLY INVALID; Object can be many types other than String.
static String onlyString(Object value) {
    return switch (value) {
        case String s -> s;
    };
}
~~~

The compiler may report:

~~~text
the switch expression does not cover all possible input values
~~~

Add the appropriate branches:

~~~java
static String className(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "String: " + s;
        default -> "Other type";
    };
}
~~~

**Why was there no `default` in the main program in Section 5?** Because the selector `Shape` is a sealed hierarchy with two permitted subtypes, and the `switch` handles both; the compiler can prove exhaustiveness. In the broad `Object` example above, `String` alone is not enough.

**Do not confuse exhaustiveness with null-safety:** for a reference selector, an exhaustive `switch` without `case null` can still throw a `NullPointerException` when given null. Checking for this kind of bug requires runtime tests, and safety cannot be inferred from `javac` succeeding alone.

## 9. Dominance Errors: A General Branch Shadows a Guarded Branch

Code can be token-valid yet have the wrong `case` order:

~~~java
// INTENTIONALLY INVALID: general String case precedes the guarded case.
static String classify(Object value) {
    return switch (value) {
        case String s -> s;
        case String s when s.isBlank() -> "blank";
        default -> "other";
    };
}
~~~

The compiler may report:

~~~text
this case label is dominated by a preceding case label
~~~

Because the first `case String s` already matches every non-null `String`, the guarded `String` branch below it can never be reached. Fix:

~~~java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s -> s;
        default -> "other";
    };
}
~~~

Note that `String s when s.isBlank()` applies only after the type pattern matches and the variable `s` is in scope in the guard. If you reference a variable before its pattern declaration, the compiler reports a scope/cannot-find-symbol error.

**Read diagnostics by root cause:** `dominated case`, `non-exhaustive switch`, and `incompatible types` are all compile-time issues, but each has a **different** fix. Do not try to silence all of them by blindly adding a `default`.

## 10. `--release` and Errors from Using Wrong-Version Syntax

Code with Java 21 record patterns and `switch` patterns requires a compiler that understands the Java 21 language. For example:

~~~bash
javac --release 21 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
~~~

If you change it to:

~~~bash
javac --release 17 -encoding UTF-8 -d out JavacPatternSyntaxDemo.java
~~~

you are requesting **Java 17 syntax and APIs**, which lack the finalized Java 21 record/switch patterns. The compiler will reject features incompatible with that release; this is a **configuration/language-level** error, not a problem with the record's data.

Distinguish between these options:

| Option | Meaning |
| --- | --- |
| `--release 21` | Source rules, target bytecode, and platform APIs for Java 21 |
| `-source 21` | Java 21 language rules (does not bind platform APIs the way `--release` does) |
| `-target 21` | Target class file version, does not check Java 21 APIs |
| `--enable-preview` | Enables preview features **for the matching compiler/release version**; not needed for finalized record patterns/pattern switch in Java 21 |
| `-encoding UTF-8` | How characters in source files are decoded; does not affect language level |

Do not use `--enable-preview` as a “universal fix” for syntax errors. It only applies to features **currently in preview in the corresponding release** and has strict version rules; it cannot make an older compiler support new syntax.

If a module must support Java 17, **rewrite the code** using features supported by Java 17 or intentionally update the product/runtime requirements—do not just tweak command-line flags.

## 11. Using `javac` Diagnostics Effectively

When you need more detailed messages:

~~~bash
javac --release 21 -encoding UTF-8 -d out \
  -Xdiags:verbose -Xmaxerrs 50 JavacPatternSyntaxDemo.java
~~~

The command above uses Bash line continuation `\`. In **Windows PowerShell**, write the same command on a single line:

~~~powershell
javac --release 21 -encoding UTF-8 -d out -Xdiags:verbose -Xmaxerrs 50 JavacPatternSyntaxDemo.java
~~~

Meaning:

- `-Xdiags:verbose`: requests **more detailed** diagnostic formatting when the compiler has extra context.
- `-Xmaxerrs 50`: sets the maximum number of errors displayed; useful when multiple files fail, though you should still read the first error first.
- `-Xlint:all`: enables a broad set of Java lint warnings; helps spot risks such as unchecked/deprecation warnings, but **does not turn valid syntax into a syntax error**.
- `-Werror`: treats warnings as errors, useful if CI policy requires zero warnings; does not automatically make business logic correct.

Example of running lint checks separately:

~~~bash
javac --release 21 -encoding UTF-8 -Xlint:all -d out JavacPatternSyntaxDemo.java
~~~

Do not enable `-Werror` before understanding which warnings exist, as projects with annotation processors, third-party dependencies, or legacy code may emit warnings that need a dedicated remediation plan.

**Important:** `-proc:none` only **disables annotation processing**; it is not “parse-only”. `-proc:only` runs annotation processors without full class compilation; it is also **not an option that guarantees checking all semantic errors and stopping**. The `javac` CLI has no single standard flag that turns full compilation into “parse syntax only and guarantee no output”. If you need pure syntax checking for editors/tooling, look at the Compiler API or an IDE parser; if you need to verify the code builds, compile it for real.

## 12. Missing Classpath: Dependency Errors Are Not Syntax Errors

Example:

~~~java
import com.example.library.Widget;

public class UsesWidget {
    Widget widget;
}
~~~

If the library containing `Widget` is not on the classpath, `javac` may report:

~~~text
package com.example.library does not exist
cannot find symbol
~~~

This is an **unresolved dependency** error, not necessarily a syntax error in the Java file.

For a standard Java project (without modules), pass the classpath:

~~~bash
javac --release 21 -cp "lib/*" -d out src/UsesWidget.java
~~~

On Windows, when specifying multiple classpath entries, the default path separator is **`;`**; on Linux/macOS, it is **`:`**. Use the separator for your OS, for example:

~~~powershell
javac --release 21 -cp "lib/*;out" -d out src/UsesWidget.java
~~~

With named modules, you may need `--module-path` instead of or alongside the classpath according to the module graph. Do not replace valid imports with dummy code just to silence the compiler; check **dependencies, versions, package names, classpath/modulepath, and source path**.

If the project uses Gradle or Maven, an official build command (e.g., `mvn compile` or `gradle compileJava`) typically configures dependencies automatically. Still, invoking `javac` directly remains useful for isolating a minimal example without complex dependencies.

## 13. Compiling Multi-File Code and Checking Package Structure

Example project:

~~~text
src/
  demo/
    Point.java
    Main.java
out/
~~~

In `Point.java` and `Main.java`, if `package demo;` is declared, the source files must match the package and public top-level types must live in files of the same name:

~~~java
// src/demo/Point.java
package demo;

public record Point(int x, int y) {}
~~~

~~~java
// src/demo/Main.java
package demo;

public class Main {
    public static void main(String[] args) {
        Point p = new Point(2, 3);
        System.out.println(p);
    }
}
~~~

Commands:

~~~bash
mkdir out
javac --release 21 -encoding UTF-8 -d out src/demo/Point.java src/demo/Main.java
java -cp out demo.Main
~~~

Output:

~~~text
Point[x=2, y=3]
~~~

`-d out` places `demo/Point.class` and `demo/Main.class` under the output tree. When running, use the **fully qualified class name** `demo.Main` rather than `Main` when the class belongs to a package.

If you compile only one file that references a type in another file, the compiler may locate the source automatically via the source path/classpath in some cases; to avoid surprises when creating standalone examples, list all source files explicitly or use the project's build system.

## 14. Runtime Errors Cannot Be Eliminated by `javac` Alone

Valid code:

~~~java
Object input = null;

String result = switch (input) {
    case String s -> "Text: " + s;
    default -> "Other";
};
~~~

In Java 21, the snippet above **compiles**, because by source rules the `switch` expression is exhaustive with `default`. However, at runtime the selector is null and **there is no `case null`**, resulting in a **`NullPointerException`**, not `"Other"`.

Fix if null is a valid input:

~~~java
String result = switch (input) {
    case null -> "No input";
    case String s -> "Text: " + s;
    default -> "Other";
};
~~~

Beyond NPEs, the compiler also cannot verify:

- Whether `width * height` overflows `int` for large values.
- Whether a localized string is displayed as the user expects.
- Whether a method handles all boundary cases and domain states.
- Whether performance/latency meets requirements.
- Whether multithreaded code has race conditions.

Therefore, combine **compilation + unit tests + runtime checks**. For record patterns and `when`, write tests covering pattern matches, guard true/false cases, null selectors, null nested components, and error paths.

## 15. 8-Step Workflow for Debugging Compiler Errors

1. **Verify the toolchain**: run `javac -version` and `java -version`; confirm the JDK supports the target language level.
2. **Verify source files and compile command**: matching public class/record names, packages, paths, and classpath.
3. **Pin the release**: use `--release 21` for Java 21 examples, rather than `-target` alone.
4. **Read the first error**: locate `file:line:column`/the `^` marker and inspect the context a few lines above.
5. **Classify the error**: parsing, type/flow scoping, record pattern arity, dominance/exhaustiveness, missing dependency, or preview/release mismatch.
6. **Fix the smallest root cause**: missing `;` → add `;`; wrong components → compare with the record declaration; case dominance → reorder cases; non-exhaustive → add appropriate branches.
7. **Re-run `javac`**: do not rely on old error counts after modifying the source; enable `-Xdiags:verbose` if needed.
8. **Run the program/tests**: verify stdout, exceptions, guard branches, and edge-case data; a clean compile is only the first gate.

Quick classification table:

| Diagnostic/symptom | Error category | What to check |
| --- | --- | --- |
| `';' expected` | Parsing/syntax | Missing statement terminator, structure before the error line |
| `reached end of file while parsing` | Parsing/syntax | Missing `}`/`)` or incomplete code block |
| `incorrect number of nested patterns` | Record pattern structure | Number of record components and pattern positions |
| `incompatible types` | Type checking | Component/static expression types |
| `cannot find symbol` | Name resolution/dependency | Variable name, imports, scope, classpath |
| `switch expression does not cover ...` | Exhaustiveness | Missing types/values |
| `case label is dominated` | Dominance | Order of type patterns, general cases, and guards |
| `source release ... not supported` | Toolchain | `javac -version` and language level |
| `package ... does not exist` | Classpath/modulepath | Dependencies, paths, module configuration |
| No compile error, but runtime NPE | Runtime | Null selector, null component, code branch |

The messages above are **illustrative examples**, not verbatim guarantees across every JDK version. Adding `-Xdiags:verbose` and reading the source location will give you the exact details for your compiler.

## 16. Common Misconceptions

| Misconception | Why it is wrong | Correct practice |
| --- | --- | --- |
| `javac` only checks syntax | It also checks types, scope, exhaustiveness, and APIs/dependencies | Classify compile-time errors by their actual cause |
| `javac` succeeding means no bugs remain | Runtime/logic/concurrency bugs can still exist | Run unit and integration tests |
| Seeing no output from `javac` means it didn't run | Successful compilation is typically silent | Check the exit code and class output |
| `--target 21` is enough for Java 21 syntax/APIs | `--target` only controls the class file target version | Prefer `--release 21` |
| JDK 17 + `--release 21` will support Java 21 | An older compiler does not know newer releases | Install and select JDK 21+ |
| Enabling `--enable-preview` fixes all pattern errors | Preview only applies to specific features/versions | Use Java 21 finalized features; avoid preview unless needed |
| `-proc:none` means syntax-check only | It only disables annotation processing and still compiles | Use `javac` to verify builds; use a parser API if you truly only need parsing |
| A `default` branch is always null-safe | A `switch` on a null reference selector can still throw NPE | Use `case null` or check before the `switch` |
| Adding `default` is always the best fix for non-exhaustive `switch` | It can hide newly added sealed subtypes | Add domain-specific cases and leverage exhaustiveness checking |
| `cannot find symbol` means a syntax error | It may be a missing dependency or out-of-scope variable | Check imports, classpath, and name resolution |
| Only running `java` after editing source | You may be executing stale bytecode | Recompile and check the exit code before running |
| Using a Java 21 file with `--release 17` to “test compatibility” without changes | Java 17 does not support many Java 21 syntaxes | Write source code compatible with the target release |

## 17. Practice Exercises

**Exercise 1 — Actual syntax error.** What is missing in the snippet below? Predict the diagnostic type and fix it.

~~~java
static int answer() {
    int x = 40
    return x + 2;
}
~~~

**Exercise 2 — Record pattern arity.** Given `record RGB(int r, int g, int b) {}`, why does `obj instanceof RGB(var r, var g)` fail to compile? If you do not need `b`, how can you write it?

**Exercise 3 — Dominance.** Given the two branches `case String s` and `case String s when s.isBlank()`, which one should come first? Is reordering enough, or should you also address a null selector?

**Exercise 4 — Exhaustive `switch`.** Given `sealed interface Task permits Print, Save {}` and two records implementing it, write a `switch` expression returning a string for both subtypes. Explain why the compiler may not require `default` and why you should still decide on a null policy.

**Exercise 5 — Tooling.** A machine has `java -version` 21 but `javac -version` 17. What should you check before compiling a program that uses record patterns? Should you use `--enable-preview` to fix it?

**Exercise 6 — Bugs the compiler does not catch.** A method accepts `Object` and uses a `switch` with `default` but no `case null`. The compiler accepts it. With null input, what happens at runtime? Write a test verifying the new behavior after adding `case null`.

**Suggested answers:**

~~~java
// 1
static int answer() {
    int x = 40;
    return x + 2;
}

// 2: include all three component patterns
if (obj instanceof RGB(var r, var g, var ignoredB)) {
    System.out.println(r + g);
}

// 3: guarded branch before the general String branch
case String s when s.isBlank() -> "blank";
case String s -> s;
~~~

- Exercise 4: the compiler knows the permitted subtypes of the sealed hierarchy; when all are handled, the `switch` expression can be exhaustive. A null reference still needs an explicit policy.
- Exercise 5: check `PATH`/`JAVA_HOME` and select JDK 21+ for the compiler; Java 21 record patterns and `switch` patterns are finalized, so `--enable-preview` is not needed.
- Exercise 6: missing `case null` can cause a runtime `NullPointerException`. Add explicit null handling and test `classify(null)` with an assertion.

## 18. Key Takeaways

- **`javac` is a compile-time gate**: it checks syntax, types, scope, pattern structure, dominance/exhaustiveness, and API/dependency resolution; it does not guarantee runtime correctness.
- **Start with `javac -version`**, use `--release 21` to compile Java 21 code, `-encoding UTF-8` for Unicode, and `-d out` to separate class output.
- **Read the first error** and classify it accurately: missing punctuation ≠ wrong component type ≠ missing dependency ≠ non-exhaustive `switch`.
- **Use diagnostic flags when needed** (`-Xdiags:verbose`, `-Xlint:all`, `-Xmaxerrs`), but do not treat them as a substitute for tests.
- **Compile successfully before running** code with `java`, and verify results, exceptions, and edge cases.
- With Java 21 pattern matching, **case order, record component arity, flow scoping, null handling, and exhaustive `switch`** are key error sources that the compiler or tests help catch.

### References

- [Oracle Java SE 21 — The javac Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `javac` command syntax, `--release`, `-d`, `-cp`, `-proc`, and diagnostic options.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): case patterns, `when`, dominance, and exhaustiveness.
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstruction and component patterns in Java 21.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
