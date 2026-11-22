# Controlling Debug Information with -g

When Java compiles source code into `.class`, the JVM needs bytecode to execute, while programmers often need extra data to know **which source line is running**, **what name a local variable has**, or **where to set a breakpoint**. This auxiliary data is called **debug information**. The `javac` compiler can write it into the classfile, and the **`-g`** option decides which kinds of debug information are generated.

`-g` belongs to the **compilation phase**. It does not itself enable debug mode in the JVM, does not open a debugger connection port, does not print extra logs, and does not automatically fix program bugs. IDEs or debuggers at runtime use the generated information to correlate bytecode with source code.

This lesson focuses on four questions: what debug information consists of, how `-g` and `-g:none` differ, how to inspect with `javap`, and which configuration to choose in development or release builds.

## 1. Why is debug metadata valuable?

Suppose a program throws `ArithmeticException`. You want to read the stack trace with filename and line number. When paused at a breakpoint, you want the debugger to display the `total` variable inside a loop. The JVM can execute bytecode without source variable names, yet Java-level debugging becomes harder if that information is stripped.

~~~text
DebugInfoDemo.java (source code)
          |
          | javac with the corresponding -g option
          v
DebugInfoDemo.class
    |-- bytecode and structures needed by the JVM
    |-- SourceFile: source file information (if generated)
    |-- LineNumberTable: maps bytecode positions to source lines
    |-- LocalVariableTable: local variable names and scopes
          |
          +--> JVM executes the program
          +--> debugger/javap reads metadata for analysis
~~~

Three main groups:

| Group in `-g:...` | Typically Related Classfile Attribute | Meaning |
| --- | --- | --- |
| `source` | `SourceFile` | Records the source filename used for compilation, e.g. `DebugInfoDemo.java` |
| `lines` | `LineNumberTable` | Maps bytecode offsets of a method to line numbers in the source |
| `vars` | `LocalVariableTable` | Describes names, types, slots, and live ranges of local variables |

With generics, `LocalVariableTypeTable` may also appear to represent generic type signatures. This is not a fourth `-g:` keyword.

These tables **are optional metadata**. Classfiles contain many other components serving loading, verification, and execution; disabling debug metadata does not strip all class, method, field, constant names, or bytecode verification data.

## 2. Syntax and defaults of `javac`

With `javac` on modern JDKs, you can use:

| Command | Debug Data Requested to Be Written |
| --- | --- |
| `javac Demo.java` | Defaults to **line** and **source file** info, without requiring the local variable name table |
| `javac -g Demo.java` | All debug information: `lines`, `vars`, and `source` |
| `javac -g:none Demo.java` | Generates none of these optional debug information groups |
| `javac -g:lines Demo.java` | Line data only |
| `javac -g:source Demo.java` | Source filename data only |
| `javac -g:vars Demo.java` | Local variable data only |
| `javac -g:lines,source Demo.java` | Includes line and source data, without requiring variable names |
| `javac -g:lines,vars,source Demo.java` | Selects all three groups, serving the same purpose as `-g` |

After the colon, multiple keywords are separated by commas **without spaces**. `none` is a standalone option to disable debug groups: do not combine `none` with `lines` or `vars`.

**Omitting `-g` differs from passing `-g:none`.** The normal default of `javac` still writes `lines` and `source`. This explains why a program built with defaults can report line numbers in stack traces even when the author never specified `-g`.

`-g` also differs from runtime debugger attachment modes, such as JDWP. One determines metadata inside `.class`, while the other determines how debugging tools interact with the JVM.

## 3. Complete experiment on Java 17+: one source, four compilation modes

Create **`DebugInfoDemo.java`**, saved in UTF-8:

~~~java
public final class DebugInfoDemo {
    private DebugInfoDemo() {
    }

    public static int sumUpTo(int limit) {
        int total = 0;
        for (int i = 1; i <= limit; i++) {
            total += i;
        }
        return total;
    }

    public static void main(String[] args) {
        int limit = 4;
        int sum = sumUpTo(limit);
        System.out.println("Tổng từ 1 đến " + limit + " = " + sum);
    }
}
~~~

Variables `total`, `limit`, `sum`, and `i` are useful names to inspect inside the local variable table. The program sums 1+2+3+4, requiring no libraries outside the JDK. For easy comparison, each configuration stores its classfile in a separate directory.

In the directory containing the source code, prepare four directories:

~~~sh
mkdir out-default
mkdir out-full
mkdir out-none
mkdir out-selected
~~~

Run directory creation once; if the directories already exist, skip that step. The directory after `javac`'s `-d` option must exist. Compile the exact same source code:

~~~sh
javac -encoding UTF-8 -d out-default DebugInfoDemo.java
javac -encoding UTF-8 -g -d out-full DebugInfoDemo.java
javac -encoding UTF-8 -g:none -d out-none DebugInfoDemo.java
javac -encoding UTF-8 -g:lines,source -d out-selected DebugInfoDemo.java
~~~

Run each compiled artifact:

~~~sh
java -cp out-default DebugInfoDemo
java -cp out-full DebugInfoDemo
java -cp out-none DebugInfoDemo
java -cp out-selected DebugInfoDemo
~~~

**Each `java` command prints one line:**

~~~text
Tổng từ 1 đến 4 = 10
~~~

All four classes execute the exact same algorithm, since the source code did not change. What we are examining here is the **metadata** inside each `.class`. Identical results do not prove that all classfile details or application performance are identical across every environment.

### Using `javap` to inspect evidence

`javap` is a JDK tool for displaying information from classfiles; it does not run the `main` method. `-l` displays line and variable tables, and `-p` includes `private` methods:

~~~sh
javap -l -p -classpath out-default DebugInfoDemo
javap -l -p -classpath out-full DebugInfoDemo
javap -l -p -classpath out-none DebugInfoDemo
javap -l -p -classpath out-selected DebugInfoDemo
~~~

Expected table:

| Compiled Build | `LineNumberTable` | `LocalVariableTable` | `SourceFile` |
| --- | --- | --- | --- |
| Default | Present | Usually absent | Present |
| `-g` | Present | Present | Present |
| `-g:none` | Absent | Absent | Absent |
| `-g:lines,source` | Present | Absent | Present |

To clearly inspect `SourceFile` alongside other attributes, use verbose mode `-v`:

~~~sh
javap -v -p -classpath out-default DebugInfoDemo
javap -v -p -classpath out-full DebugInfoDemo
javap -v -p -classpath out-none DebugInfoDemo
javap -v -p -classpath out-selected DebugInfoDemo
~~~

Look for the **attribute names** `SourceFile`, `LineNumberTable`, and `LocalVariableTable` in the output. In the build with full `-g`, you can see names like `limit`, `total`, or `sum` in the variable table. Merely finding the string `sum` somewhere in the constant pool **is not enough** to conclude `LocalVariableTable` is present.

To view JVM instructions, use:

~~~sh
javap -c -p -classpath out-full DebugInfoDemo
javap -c -p -classpath out-none DebugInfoDemo
~~~

`-c` displays JVM instruction opcodes. `-g` does not turn bytecode into Java source and does not alter arithmetic operations. With the same tool and source in the experiment, instructions executing the calculation are expected to match; debug metadata is the intentional difference.

## 4. Reading each kind of information accurately

### `source`: source name, not source content

`SourceFile` typically records the original Java filename. For instance, `DebugInfoDemo.class` can record `DebugInfoDemo.java`. This metadata **does not contain the full source text** and does not guarantee where the debugger can locate the saved source file. IDEs need the actual source file or a matching, version-aligned source attachment.

Generating only `source` without `lines` lets the debugger know the filename yet still lacks mapping to line numbers during execution. Thus these two groups are normally used together.

### `lines`: bytecode positions and line numbers

`LineNumberTable` maps positions inside a method's bytecode to source line numbers. Stack traces can leverage it to display locations like:

~~~text
at demo.Example.fail(Example.java:17)
~~~

This is an illustrative example, **not output from `DebugInfoDemo`**. Actual line numbers vary with file content. Without line information, stack traces may omit line numbers or display `Unknown Source`.

Do not assume one Java line corresponds to exactly one JVM instruction. One Java line can compile into multiple instructions; mapping metadata only serves positioning.

### `vars`: name, type, slot, and scope

`LocalVariableTable` lets tools inspect local variable names/scopes such as `total` and `i`. In `sumUpTo`, variable `i` lives within the loop, whereas `total` persists across iterations. Each entry specifies the code range over which that variable remains valid.

Enabling `-g:vars` does not guarantee the debugger sees **every variable at every breakpoint**. A variable might not have entered scope yet, may have left scope, lack an assigned value, or be hard to observe due to runtime optimizations. A class field differs from a local variable; field names must be retained by the classfile for linkage/access mechanisms to work and do not vanish with `-g:none`.

## 5. Demonstrating stack traces with and without line numbers

Create **`FailureLocationDemo.java`**:

~~~java
public class FailureLocationDemo {
    static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }

    public static void main(String[] args) {
        try {
            divide(12, 0);
        } catch (ArithmeticException ex) {
            StackTraceElement frame = ex.getStackTrace()[0];
            System.out.println("Phương thức: " + frame.getMethodName());
            System.out.println("Có số dòng: " + (frame.getLineNumber() > 0));
        }
    }
}
~~~

The code intentionally divides an integer by 0 and catches the exception to inspect the frame at the failure location. Default command:

~~~sh
javac -encoding UTF-8 FailureLocationDemo.java
java FailureLocationDemo
~~~

Typical output:

~~~text
Phương thức: divide
Có số dòng: true
~~~

**Recompile** with `-g:none` and run the same class:

~~~sh
javac -encoding UTF-8 -g:none FailureLocationDemo.java
java FailureLocationDemo
~~~

Result:

~~~text
Phương thức: divide
Có số dòng: false
~~~

`getLineNumber()` yields no positive line number if the classfile lacks line information. The method is still invoked and the exception still occurs; only source location metadata for diagnostics is lost. The example avoids hardcoding a specific line number because learners may add/remove lines in the code.

If using an IDE or build tool, ensure `java` executes the exact class just compiled, not a stale class on the classpath. An old classfile can cause the experiment to yield unexpected results.

## 6. Distinguishing `-g:vars` and `-parameters`

Many people assume `-g` lets Reflection know real parameter names. The two metadata types are different:

- `-g:vars` emits **local variable** information in `LocalVariableTable` to aid debuggers. Parameters may appear as method variables.
- `-parameters` emits **MethodParameters** so the Reflection API recognizes declared parameter names via `Parameter.getName()` and `isNamePresent()`.

Create **`ParameterNameDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNameDemo {
    public static void greet(String person) {
    }

    public static void main(String[] args) throws Exception {
        Method method =
                ParameterNameDemo.class.getDeclaredMethod("greet", String.class);
        Parameter parameter = method.getParameters()[0];

        System.out.println("Có tên thật: " + parameter.isNamePresent());
        System.out.println("Tên tham số: " + parameter.getName());
    }
}
~~~

Using only `-g`:

~~~sh
javac -encoding UTF-8 -g ParameterNameDemo.java
java ParameterNameDemo
~~~

Stdout:

~~~text
Có tên thật: false
Tên tham số: arg0
~~~

Add `-parameters` and **recompile**:

~~~sh
javac -encoding UTF-8 -g -parameters ParameterNameDemo.java
java ParameterNameDemo
~~~

Stdout:

~~~text
Có tên thật: true
Tên tham số: person
~~~

You can use `javap -v -p ParameterNameDemo` to see `MethodParameters` in the second build. Local variable metadata for debugging and parameter name metadata for reflection **do not substitute for each other**. This is worth noting when frameworks use reflection to bind API parameters or configurations.

## 7. Choosing `-g` in development and release builds

| Goal | Possible Configuration | Trade-off |
| --- | --- | --- |
| Normal build, preserving useful stack traces | Default | Does not include full local variable names |
| Deep debugging in IDE | `-g` or `-g:lines,vars,source` | Adds metadata, may increase classfile size |
| Keeping source locations while reducing variable info | `-g:lines,source` | Harder for debuggers to display local variable names |
| Stripping optional debug tables | `-g:none` | Stack traces lose line numbers, making failure investigation harder |

**Do not treat `-g:none` as a complete security or anti-decompilation measure.** Classfiles still contain bytecode, signatures, constants, and structural names required by the JVM. Reducing debug info can make files smaller, yet does not mean algorithms run faster or implementation secrets stay hidden.

In production, line numbers are usually very helpful for diagnosing errors from logs/stack traces. Any decision to drop `lines` must weigh system observability, operational scale, and artifact distribution requirements.

### Gradle configuration example

A project using the Java plugin and Gradle Groovy DSL can configure compilation tasks:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.debug = true
    options.debugOptions.debugLevel = 'lines,vars,source'
}
~~~

This is **Gradle configuration**, not standalone runnable Java code. It applies only within builds having `JavaCompile` tasks. Other plugins and profiles can alter settings, so verify actual outputs with `javap`.

Maven and IDEs have equivalent options, though configuration locations/syntax depend on plugin and version. Do not assume IDEs always invoke the same compiler command as Gradle/Maven CLIs; in many projects the IDE delegates building to external tools.

## 8. Common misconceptions

| Claim | Accurate Understanding |
| --- | --- |
| “Not writing `-g` means zero debug info.” | Default `javac` typically emits `lines` and `source`. |
| “`-g` enables debugging in the JVM.” | `-g` generates compile-time metadata; interactive debugging is a separate step. |
| “`-g:none` removes all names from `.class`.” | It controls only optional debug metadata, not removing required class structure. |
| “Having `SourceFile` gives tools all the source code.” | `SourceFile` typically records only the source filename; the `.java` file must be located separately. |
| “`-g:vars` makes Reflection know parameter names.” | `-parameters` is what writes parameter name metadata for Reflection. |
| “Losing lines in stack traces means the code cannot run.” | The program still runs; only location metadata for diagnostics is missing. |
| “Smaller classfiles mean faster bytecode.” | Size differences may come solely from debug tables and say nothing about speed. |
| “With metadata, every variable can be read.” | Live ranges, pause points, and JVM optimizations still matter. |

If the IDE fails to show variable names or breakpoints miss lines, check:

1. **Running artifact:** Confirm the exact newly built `.class` or JAR is on the right classpath, not an older version.
2. **Metadata in class:** Use `javap -l -p` to inspect `LineNumberTable` and `LocalVariableTable`; use `javap -v -p` for full attribute details.
3. **Matching source version:** A source file edited after building may not match metadata in the class.
4. **Variable scope:** A loop variable need not exist before or after the loop.
5. **Correct debugger process/thread:** Having metadata does not guarantee execution actually reached the breakpoint.
6. **Actual compiler config:** Build tools/IDEs can override `-g` options differently from what you expect.
7. **Runtime optimizations:** JIT and debugger rendering can make certain values hard to inspect even when metadata was emitted.

## 9. Practice exercises and self-check questions

**Exercise 1 — Comparing classfiles.** Compile `DebugInfoDemo.java` with default, `-g`, `-g:none`, and `-g:lines,source`. Use `javap -v` to record the presence of `SourceFile`, `LineNumberTable`, and `LocalVariableTable`. Then run all four builds to confirm the sum output.

**Exercise 2 — Line-number debugging.** Use `FailureLocationDemo.java` with default and `-g:none`. Compare boolean `getLineNumber() > 0`. Explain why division still fails while line information changes.

**Exercise 3 — Inspecting local variables.** Compile with `-g`, run `javap -l -p`, and locate `total` and `i` in `sumUpTo`. Read the range, slot, and type columns and explain why debuggers need them.

**Exercise 4 — Reflection.** Run `ParameterNameDemo.java` both ways and explain the meaning of `isNamePresent()`. Locate `MethodParameters` using `javap -v` after adding `-parameters`.

**Exercise 5 — Build decision.** A production application needs full file and line numbers in stack traces while minimizing local variable name metadata. Choose `-g:lines,source` and explain the drawback of `-g:none`.

Answer six questions yourself:

1. **Which phase does `-g` affect?** — The compilation phase with `javac`.
2. **Is omitting `-g` synonymous with `-g:none`?** — No; defaults normally still include line and source info.
3. **Which attribute stores local variable info?** — `LocalVariableTable`, sometimes alongside `LocalVariableTypeTable` for generic signatures.
4. **Which command inspects attributes?** — `javap -l` for line/variable tables, `javap -v` for full classfile details.
5. **How does `-parameters` differ from `-g:vars`?** — It enables Reflection to read declared parameter names, not just debuggers.
6. **Does `-g:none` break bytecode execution?** — No; it removes optional debug metadata.

**Connecting knowledge:** Compilation configuration can strongly affect runtime diagnosability. Understanding `-g` helps you trace the exact relationship **source code → classfile → debugger/stack trace**, avoiding mistaking missing metadata for a JVM or Java code bug.