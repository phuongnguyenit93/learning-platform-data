# Reading `javac` Messages and Fixing from the Root Error (Java 17+)

## 1. Objective

When compiling Java with `javac`, a single mistake in the source code sometimes generates multiple error messages on different lines. The skill to develop is **reading the message, identifying the initial cause, fixing that cause, and recompiling**; do not mechanically edit every flagged line if those lines are merely consequences.

After this lesson, you will be able to read the error location, message, and `symbol`/`location` details; distinguish syntax, identifier, type, access, and dependency errors from runtime exceptions; and use `javac` to reproduce and verify fixes on JDK 17+.

## 2. What Does a `javac` Message Tell You?

Example source code with an **intentional error** in the file `SumDemo.java`:

```java
public class SumDemo {
    public static void main(String[] args) {
        int left = 3;
        int right = 4;
        int sum = left + right;
        System.out.println(smu);
    }
}
```

Compile with:

```sh
javac -encoding UTF-8 SumDemo.java
```

The compiler will report that variable `smu` cannot be found because the program declared the name `sum`. An illustrative message sample (spacing, `^` marker, line numbers, and exact wording may vary by JDK):

```text
SumDemo.java:6: error: cannot find symbol
        System.out.println(smu);
                           ^
  symbol:   variable smu
  location: class SumDemo
1 error
```

Components to read:

| Component | How to Interpret |
| --- | --- |
| `SumDemo.java:6` | File and line related to where the compiler detected the error |
| `error` | Diagnostic severity: an error preventing successful compilation |
| `cannot find symbol` | Could not resolve the name in that context |
| Code line and `^` | The region/token `javac` is pointing at; not guaranteed to be where the cause started |
| `symbol: variable smu` | Kind of member or identifier being looked up |
| `location: class SumDemo` | Context in which the compiler is searching |
| `1 error` | Number of errors listed at the end of this compilation pass |

For other errors, `javac` may provide `required`/`found`, method signatures, candidate overloads, reasons a method is inapplicable, or another source path. This data helps compare **current code** against **what the compiler requires**.

Note: the line number is usually where the compiler *notices* the problem, not necessarily the line that needs to be edited. For instance, a missing `;` at the end of the previous line may cause the first token on the next line to be flagged.

## 3. A 6-Step Process for Fixing from the Root Error

1. **Reproduce the error with a clear compilation command.** Confirm the right JDK, the right directory, and the right set of files being compiled. Keep the full output, not just a single copied `error` line.
2. **Read the first group of errors in context.** Start from an early syntax or identifier error; inspect a few lines before and after the `^` marker, braces, quotes, declared names, `package`, and `import`.
3. **Find the smallest common cause.** One missing `}` can cause many declarations to be misinterpreted; an uncompiled type name or wrong import can cascade into many errors where that type is used.
4. **Fix one real cause**, keeping changes minimal. Avoid mass-renaming identifiers or adding casts/imports by guesswork just to reduce the error count.
5. **Re-run the exact same `javac` command.** Read the new diagnostic set; cascading errors may vanish on their own. If independent errors remain, handle them one by one.
6. **Run with `java` after compilation succeeds**, and check output/behavior. Compiling with `javac` does not mean the program is free of exceptions or logic bugs.

This is a priority method, not a rule that *the first printed error is always the root error*: compiler recovery after syntax errors, compilation order across multiple files, and dependency errors can cause diagnostics to appear at the point of consequence. Rely on evidence, try one small fix, and recompile.

## 4. Fixing the `cannot find symbol` Example Properly

In `SumDemo.java` above, change `smu` to `sum`. The complete valid program:

```java
public class SumDemo {
    public static void main(String[] args) {
        int left = 3;
        int right = 4;
        int sum = left + right;
        System.out.println("sum=" + sum);
    }
}
```

Create the `out` directory once, then compile and run from the directory containing `SumDemo.java`. The following commands work in PowerShell, CMD, and bash:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out SumDemo.java
java -cp out SumDemo
```

**Exact output of the `java` command:**

```text
sum=7
```

- `-encoding UTF-8`: read source files using UTF-8 encoding, avoiding issues when Vietnamese characters are present.
- `--release 17`: compile targeting the Java 17 language and API (when supported by the compiler). Use JDK 17+ to run the commands in this lesson.
- `-d out`: place `.class` files in the output directory; this directory must already exist.
- `-cp out`: add the directory containing compiled classes to the runtime classpath.

When `javac` compiles successfully, it normally **prints nothing**. The string `sum=7` is the program's stdout, not a compiler message. In the debugging workflow, only run `java` after the `javac` command succeeds to avoid accidentally running stale `.class` files.

## 5. Common Error Categories and How to Find the Root

| Sign in Diagnostic | Root Cause to Check | Correct Fix Direction |
| --- | --- | --- |
| `';' expected`, `')' expected`, `illegal start of expression` | Missing `;`, `)`, `}`, broken syntax structure, or unclosed quote | Read back a few lines, balance brackets/braces, fix the first syntax issue |
| `reached end of file while parsing` | Usually a missing closing `}` or incomplete construct | Match `class`, method, `if`, and loop blocks |
| `cannot find symbol` | Misspelled/wrong-case name, undeclared identifier, out of scope, missing type/library | Check declaration, scope, full name, package, and classpath |
| `package ... does not exist` | Wrong `import`, missing dependency/source in compile command, unavailable module | Check actual package, JAR/source, classpath/module path |
| `incompatible types` | Incompatible assignment/return/argument passing | Compare source and target types; fix data or API |
| `method ... cannot be applied`, `no suitable method found` | Wrong argument count, order, types, or unsuitable overload | Match method signature against the call site |
| `has private access`, `is not public ... cannot be accessed` | Violating `private`, package-private, `protected`, or non-public type visibility | Fix API design/scope intentionally; do not loosen access arbitrarily |
| `class ... is public, should be declared in a file named ...` | File name does not match the `public` top-level type name | Rename the file to match the public class |
| `duplicate class` or duplicate definition | Multiple sources compiling the same fully qualified type name or duplicate declarations | Inspect files/classes and build configuration |
| `bad class file`, `class file has wrong version` | Library compiled with a newer Java version than the current compiler/runtime, or invalid file | Check actual JDK, dependency versions, and build output |

The phrases in the first column are **common message patterns**, not guaranteed character-for-character strings on every JDK. Do not decide on a fix based solely on keywords: read the types, parameters, scope, and location as well.

### 5.1. Missing Punctuation Causing an Error on the Next Line

Example that is **deliberately invalid and cannot run**:

```java
public class SyntaxDemo {
    public static void main(String[] args) {
        int count = 2
        System.out.println(count);
    }
}
```

The root cause is the missing `;` after `2`, even though `javac` may point to the start of the `System.out.println` statement below. Add `;`; do not delete the `println` statement just because it was flagged.

Fixed version:

```java
public class SyntaxDemo {
    public static void main(String[] args) {
        int count = 2;
        System.out.println("count=" + count);
    }
}
```

Save in `SyntaxDemo.java`:

```sh
javac -encoding UTF-8 --release 17 -d out SyntaxDemo.java
java -cp out SyntaxDemo
```

Output:

```text
count=2
```

### 5.2. Type Mismatches and Method Calls

The following **deliberately invalid** snippet triggers a type error:

```java
String quantity = "5";
int next = quantity + 1; // String + int produces a String, cannot be assigned directly to int
```

If `quantity` represents a valid integer, fix it at the data source: `int quantity = Integer.parseInt("5"); int next = quantity + 1;`. If the goal is string concatenation, the result variable must have type `String`. The fix depends on the **meaning** of the data; blind casting does not resolve the difference between a number and a string.

For the call `Math.max(2, "3")`, a `String` argument does not satisfy any numeric overload. The root error is passing the wrong type, not a missing `import java.lang.Math` (`Math` is already in `java.lang`). Replace `"3"` with the number `3` when you want the larger number.

### 5.3. Multi-File Source Code and Cascading Errors

Suppose `src/lesson/Calculator.java` declares:

```java
package lesson;

public class Calculator {
    public static int doubleOf(int n) {
        return n * 2;
    }
}
```

And `src/lesson/App.java`:

```java
package lesson;

public class App {
    public static void main(String[] args) {
        System.out.println("value=" + Calculator.doubleOf(3));
    }
}
```

Compile both files into the same output directory, then run:

```sh
javac -encoding UTF-8 --release 17 -d out src/lesson/Calculator.java src/lesson/App.java
java -cp out lesson.App
```

Output:

```text
value=6
```

If `package lesson;` is mistyped as `package lessons;` in one file, or `Calculator.java` is omitted from compilation without providing its compiled class on the classpath, the type/identifier errors in `App.java` may just be consequences. Check the **actual package, fully qualified type name, source/JAR, and command configuration** before editing every call to `Calculator`.

When fixing dependencies, recompile all related parts to avoid using stale `.class` files. In larger projects, let Maven/Gradle manage the classpath and source sets, while still reading the actual `javac` errors during the compile step.

## 6. Using `javac` Options to Narrow Down Diagnostics

Some useful options for Java 17+:

```sh
javac -encoding UTF-8 --release 17 -Xdiags:verbose -Xmaxerrs 20 -d out SumDemo.java
```

- `-Xdiags:verbose`: requests a more detailed diagnostic level; useful for generic inference or overload resolution. This is an extra `javac` option.
- `-Xmaxerrs 20`: limits the number of errors printed in a single invocation; it does **not** fix errors and may hide messages beyond the threshold.
- `-Xlint:all`: enables many helpful warnings (unchecked, deprecation, raw types, etc., depending on version); warnings are still distinct from errors.
- `-Werror`: causes compilation to fail when warnings occur; enable only when the project wants a strict policy.
- `javac -version`: checks which compiler is running; `java -version`: checks the runtime. Both commands should be verified when multiple JDKs are installed.

You can run `javac -X` or `javac --help` separately to see the options supported by your current JDK. Use a larger `-Xmaxerrs` to discover independent errors after fixing a root syntax error, but do not rely on increasing the diagnostic count as a way to fix bugs.

**Checking compilation command status:** In PowerShell, `$LASTEXITCODE` holds the exit code of the `javac` command just run; `0` indicates success. In bash, run `echo $?` immediately after `javac` to see the exit code. Do not run another command in between before checking.

## 7. Distinguishing Compile Errors, Warnings, and Runtime Errors

| Stage | Sign | What to Investigate |
| --- | --- | --- |
| **Compile error** (`javac`) | `error:`, program fails to compile | Syntax, types, name resolution, access, dependencies, configuration |
| **Warning** (`javac`) | `warning:`, compilation may still succeed | Error-prone behavior, deprecated APIs, generics/raw types, `-Xlint` |
| **Runtime exception/error** (`java`) | `Exception in thread "main"`, stack trace, or launcher message | Data, runtime conditions, call stack, runtime classpath, logic |
| **Logic bug** | Runs without errors but prints wrong results | Testing and analyzing algorithm/data, not just reading `javac` |

Example that **compiles validly but fails at runtime**:

```java
public class RuntimeDemo {
    public static void main(String[] args) {
        String message = null;
        System.out.println(message.length());
    }
}
```

Compiling with `javac -d out RuntimeDemo.java` and running `java -cp out RuntimeDemo` throws `NullPointerException`; this is not a `javac` diagnostic. Exact stack trace details can vary across JDK releases, so do not treat stack trace text as fixed output. Here, fix the null logic and input checks—do not keep adding imports.

Do not mistake `error: could not find or load main class` from the **`java` launcher** for an error detected by the `javac` parser. Check the fully qualified `main` class name, `-cp` path, and generated `.class` files.

## 8. Common Mistakes When Fixing Errors

- **Looking only at the `^` marker:** the position is only where the compiler detected the symptom; always read preceding syntax.
- **Fixing many errors at once:** easily introduces new bugs and makes it hard to tell which change resolved the cause. Prefer small changes and recompile.
- **Misspelling names due to Java's case sensitivity:** `total`, `Total`, and `TOTAL` are three different identifiers.
- **Adding unrelated imports:** `cannot find symbol` also occurs when a local variable name is mistyped or out of scope; an import cannot create that variable.
- **Editing the classpath instead of syntax errors, or vice versa:** diagnostics about libraries require checking the right dependency; a `';' expected` diagnostic is usually syntax.
- **Forgetting the public class file name:** `public class SumDemo` must reside in `SumDemo.java` (case-sensitive on corresponding filesystems).
- **Running stale `.class` files after a failed compile:** only run after the current compilation step truly succeeds.
- **Hiding errors by deleting lines:** the program compiles but loses functionality. Re-check requirements and expected output.

## 9. Practice Checklist

When faced with a flood of messages, ask yourself:

1. Are the `javac` command, JDK version, package, source files, source paths, and libraries all correct?
2. What file, line, error type, identifier, and context does the first diagnostic report?
3. Is there a missing bracket/brace, semicolon, declaration name, or `import` on an earlier line?
4. Do multiple errors mention the same missing type/variable/method? If so, which is the originating error?
5. Can I fix **one cause** and recompile to verify?
6. Once compile errors are gone, does the program run and produce the right output?

**Remember:** `javac` reports where the compiler can no longer continue parsing or checking code against Java rules; you need to trace back to the construct, declaration, or configuration that caused that error. Fixing the root cause, recompiling, and verifying by running the code is far more reliable than counting remaining messages.