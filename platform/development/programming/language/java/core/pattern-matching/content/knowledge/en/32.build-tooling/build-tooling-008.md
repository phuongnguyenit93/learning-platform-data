# Inspecting Bytecode After Compilation

## 1. Goal: Seeing What the Compiler Generated from Pattern Matching

When programming in Java 21, source code can use `instanceof` type patterns, record patterns, `switch` with `when`, sealed interfaces, and pattern variables whose scope depends on control flow. After `javac` compiles the code, the JVM **does not execute the Java source syntax directly**; instead, it executes the instructions in the **class file**. Therefore, inspecting bytecode is a useful skill when:

- You want to understand how the compiler represents a type check or record deconstruction.
- You want to verify that a module was actually compiled at the Java 21 level, rather than merely running on a Java 21 JVM.
- You want to inspect record structure, `permits` subtypes, synthetic methods, or bootstrap methods related to `switch`.
- You want to distinguish operations that are actually present in the bytecode from assumptions like "patterns do not call accessors."
- You want to investigate runtime errors caused by **class file version incompatibility**, missing dependencies, or a build process using the wrong compiler.

The primary tools are **`javac`** (compiler) and **`javap`** (displays class file structure and bytecode instructions). They come bundled with the JDK; there is no need to download a third-party decompiler to perform the basic steps.

**Important limitation:** `javap` shows the compiled bytecode, **not the machine code after JIT optimization**, and it is not direct proof that one expression is faster or slower than another. A call present in bytecode may be inlined by the JIT at runtime; a branch may be optimized based on runtime information. To draw conclusions about performance, you need a profiler or a proper benchmark.

## 2. Preparing the Right Toolchain

This guide uses features that are **finalized as of Java 21**:

- Type patterns in `instanceof` have been finalized since Java 16.
- Records and sealed interfaces were finalized in Java 16 and Java 17, respectively.
- **Record patterns** and **pattern matching for `switch`** were finalized in Java 21 (JEP 440, JEP 441).

Check the tools in your terminal:

```bash
java -version
javac -version
javap -version
```

The commands must use **a matching JDK toolchain**. If `java` and `javac` point to different installations, the program may compile into class files that the current runtime does not support.

For JDK 21, the corresponding class file level is **major version 65**. Java 17 is **major 61**. You can check the class file version using `javap -verbose` instead of guessing from folder names or IDE versions.

When you want to guarantee Java 21 APIs and language level, compile with:

```bash
javac --release 21 -encoding UTF-8 -g PatternBytecodeInspectionDemo.java
```

Options:

- `--release 21`: instructs the compiler to target the source level, class file format, and platform APIs of Java 21. It **does not turn an older `javac` into a Java 21 compiler**.
- `-encoding UTF-8`: reads source files containing Vietnamese consistently.
- `-g`: includes debug information (such as source line numbers and local variables), making it easier to cross-reference `javap` output.

`--enable-preview` is not needed for the finalized patterns used in this guide. Do not enable preview as a catch-all fix for compile errors, because it has its own versioning policy and can produce class files that will not run in other environments.

## 3. Complete Java 21 Sample Program

Create a file named exactly **`PatternBytecodeInspectionDemo.java`**:

```java
public class PatternBytecodeInspectionDemo {
    record Point(int x, int y) {}

    record Box(String label, Point point) {}

    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}

    record Rectangle(int width, int height) implements Shape {}

    // Record pattern: component deconstruction.
    static int sumWithPattern(Object value) {
        if (value instanceof Point(int x, int y)) {
            return x + y;
        }
        return -1;
    }

    // Type pattern: only binds the object,
    // then calls accessors inside the if body.
    static int sumWithTypePattern(Object value) {
        if (value instanceof Point point) {
            return point.x() + point.y();
        }
        return -1;
    }

    // Nested record pattern.
    static String boxLabel(Object value) {
        if (value instanceof Box(
                String label, Point(int x, int y))) {
            return label + ":" + (x + y);
        }
        return "no match";
    }

    // Pattern switch, when guard, and sealed hierarchy.
    static String describe(Shape shape) {
        return switch (shape) {
            case Circle(int radius) when radius >= 10 ->
                    "large circle:" + radius;

            case Circle(int radius) ->
                    "circle:" + radius;

            case Rectangle(int width, int height) ->
                    "rectangle:" + (width * height);

            case null ->
                    "null shape";
        };
    }

    public static void main(String[] args) {
        Point point = new Point(2, 3);

        System.out.println(sumWithPattern(point));
        System.out.println(sumWithTypePattern(point));
        System.out.println(sumWithPattern("other"));

        System.out.println(boxLabel(
                new Box("B", new Point(1, 2))));
        System.out.println(boxLabel(new Box("B", null)));

        System.out.println(describe(new Circle(12)));
        System.out.println(describe(new Circle(3)));
        System.out.println(describe(new Rectangle(2, 4)));
        System.out.println(describe(null));
    }
}
```

Compile and run:

```bash
javac --release 21 -encoding UTF-8 -g PatternBytecodeInspectionDemo.java
java PatternBytecodeInspectionDemo
```

**Expected standard output:**

```text
5
5
-1
B:3
no match
large circle:12
circle:3
rectangle:8
null shape
```

Explanation of each output group:

1. Both sum methods receive `Point(2,3)` and return `5`. One uses a record pattern, and the other uses a type pattern and calls the accessors explicitly.
2. The string `"other"` is not a `Point`, so `sumWithPattern` returns `-1`.
3. `Box("B", Point(1,2))` matches the nested pattern and returns `B:3`; `Box("B", null)` does not match the nested `Point(...)` pattern and returns `no match`.
4. `Circle(12)` matches the `radius >= 10` guard and produces `large circle:12`. `Circle(3)` fails the guard and then matches the unguarded `Circle` case, producing `circle:3`.
5. `Rectangle(2,4)` produces `rectangle:8`. The `null` selector is handled specifically by `case null`.

This program keeps the data small and the output deterministic so the reader can **verify the source behavior before analyzing the bytecode**. Do not compare performance by counting the number of printed bytecode lines.

## 4. Step One: Observing the Generated .class Files

After running `javac`, the main class and nested types typically appear under names such as:

```text
PatternBytecodeInspectionDemo.class
PatternBytecodeInspectionDemo$Point.class
PatternBytecodeInspectionDemo$Box.class
PatternBytecodeInspectionDemo$Shape.class
PatternBytecodeInspectionDemo$Circle.class
PatternBytecodeInspectionDemo$Rectangle.class
```

The `$` in the binary name represents nested member types, not a special pattern symbol. Do not manually edit class files or rename those files. In practice, the number and names of class files also depend on the classes declared in the program.

In PowerShell, you can list them with:

```powershell
Get-ChildItem -Filter 'PatternBytecodeInspectionDemo*.class'
```

In a POSIX shell:

```bash
ls PatternBytecodeInspectionDemo*.class
```

When compiling in a Maven/Gradle project, class files are usually placed in the build output directory (for example, `target/classes` or `build/classes/java/main`), not necessarily in the current directory. In that case, use `javap`'s `-classpath` option to point to the output being inspected; avoid accidentally inspecting class files from an older build.

## 5. javap Options to Remember

| Option | Meaning | When to use |
| --- | --- | --- |
| `javap ClassName` | Lists accessible member signatures using default visibility | Quick preliminary check of class structure. |
| `-p` / `-private` | Shows private members as well | Inspecting compiler-generated methods and structures. |
| `-c` | Disassembles method code into JVM instructions | Tracing `instanceof`, `checkcast`, invocations, branches, and switches. |
| `-l` | Displays line number and local variable info if present in the class file | Tracking pattern variables and source lines; combine with `javac -g`. |
| `-s` | Displays internal JVM type descriptors of fields/methods | Checking JVM-level signatures, such as `I` and `Ljava/lang/String;`. |
| `-v` / `-verbose` | Detailed output: class version, constant pool, attributes, bootstrap methods, and code | Investigating class file version, `Record`, `PermittedSubclasses`, and `BootstrapMethods`. |
| `-classpath <path>` | Specifies the path to look up classes to display | Avoiding reading the wrong file or stale build output. |

The most common command for reading methods:

```bash
javap -c -p -l PatternBytecodeInspectionDemo
```

If you need to inspect the version, constant pool, and bootstrap methods:

```bash
javap -v -p PatternBytecodeInspectionDemo
```

Verbose output can be very long. Prioritize inspecting the relevant class, method, and attributes first, rather than drawing conclusions from a truncated snippet.

**Nested type names must be quoted properly when running in a shell.** In PowerShell and many POSIX shells, use single quotes to prevent `$` from being treated as a variable name:

```bash
javap -p -c 'PatternBytecodeInspectionDemo$Point'
javap -v -p 'PatternBytecodeInspectionDemo$Shape'
javap -v -p 'PatternBytecodeInspectionDemo$Box'
```

If you pass `PatternBytecodeInspectionDemo$Point` unquoted in a shell that interpolates `$`, the name may be altered, causing `javap` to report that the class was not found or to open an unintended class.

## 6. Step Two: Inspecting Bytecode for instanceof and Type Patterns

Given:

```java
if (value instanceof Point point) {
    return point.x() + point.y();
}
```

The compiler must implement the following semantics: verify that the value has the appropriate type, obtain a reference of that type, and perform two accessor calls. In bytecode generated by `javac`, instructions or instruction groups you may encounter include:

- **`instanceof`**: checks the runtime type and produces the corresponding boolean result.
- **`checkcast`**: checks/casts the reference to the required type at locations chosen by the compiler.
- **`invokevirtual`**: typically the record class accessor calls, e.g., `Point.x()`, `Point.y()`.
- **`iadd`**: integer addition of two `int` values.
- **`ifeq`, `ifne`, `goto`**: control-flow branches corresponding to the check result.
- **`ireturn`**: returns an `int` value.

These are **signs to look for**, not a guarantee of an exact instruction sequence or fixed order. The compiler is allowed to choose different lowering strategies as long as it adheres to the language and JVM specifications.

To inspect:

```bash
javap -c -p PatternBytecodeInspectionDemo
```

Locate the `sumWithTypePattern` method, match the `instanceof` instruction with the failure branch returning `-1`, and then inspect the accessor calls. For `sumWithPattern`, the record pattern must **preserve deconstruction semantics** via accessors as specified, though the bytecode implementation may use different local variables or control-flow structures than the manual version.

Do not guess a variable's source type from an `aload` instruction alone: in the JVM, `aload` pushes a reference from a local slot onto the operand stack; determining the static type may require checking descriptors, stack-map frames, and related cast/type-check steps.

## 7. Step Three: Record Patterns and Accessor Calls

The pattern:

```java
if (value instanceof Point(int x, int y)) {
    return x + y;
}
```

differs from a bare `instanceof Point` type test. When a record pattern matches, component deconstruction in Java 21 uses the **accessors** `x()` and `y()`; then the component patterns are tested and the variables `x` and `y` are bound.

Compare the two methods:

```bash
javap -c -p -l PatternBytecodeInspectionDemo
```

A sound reading workflow:

1. Identify the boundaries of `sumWithPattern` and `sumWithTypePattern` in the disassembly.
2. Locate subtype checks, accessor invocations, and failure branches.
3. With `javac -g`, use `LineNumberTable` and `LocalVariableTable` to help cross-reference variable names and source lines.
4. Do not claim "record patterns do not call getters" just because `.x()` does not appear in the Java source.
5. Do not claim two versions have the same or different runtime cost simply because their bytecode line counts are similar.

### Compiler-Generated Record Accessors

Inspect the record class:

```bash
javap -p -c 'PatternBytecodeInspectionDemo$Point'
javap -v -p 'PatternBytecodeInspectionDemo$Point'
```

You can observe:

- Fields associated with the components and the `x()`/`y()` methods.
- The constructor accepting the components.
- Record methods such as `equals`, `hashCode`, and `toString`; the compiler typically uses `invokedynamic` and `java.lang.runtime.ObjectMethods` to support these auto-generated methods.
- The **`Record` attribute** describing the components in the class file.

**Note:** A record can declare custom accessors with custom logic. Calling an accessor does not mean "field read is always cheap"; it can perform computation, have side effects, or throw an exception. If an accessor throws an exception during record pattern matching, Java 21 specifies that it is wrapped in a `MatchException` with the original cause. Direct accessor calls outside a pattern may expose a different exception type. When investigating error behavior, inspect the source, class file, and tests rather than just counting opcodes.

### Nested Patterns May Traverse Multiple Levels

The pattern:

```java
if (value instanceof Box(
        String label, Point(int x, int y))) {
    return label + ":" + (x + y);
}
```

requires accessing the `label` and `point` components of `Box`, and then further deconstructing `x` and `y` of `Point` if the nested pattern matches. When `point == null`, the nested `Point(...)` does not match. This differs from simply checking `value instanceof Box box` and then accessing an arbitrary field.

In the bytecode, look for calls to the accessors of `Box` and `Point`, type/component checks, and branches leading to `"no match"`. Do not assume every accessor is called for every input: when a matching step fails, subsequent steps may be skipped according to pattern semantics.

## 8. Step Four: Decoding Pattern switch and when Guards

The method:

```java
static String describe(Shape shape) {
    return switch (shape) {
        case Circle(int radius) when radius >= 10 ->
                "large circle:" + radius;
        case Circle(int radius) ->
                "circle:" + radius;
        case Rectangle(int width, int height) ->
                "rectangle:" + (width * height);
        case null -> "null shape";
    };
}
```

has two logical steps to recognize in bytecode: **selecting the matching type/pattern** and **evaluating the guard**. The guard only applies after the `Circle` pattern matches; if `radius < 10`, the subsequent `Circle` branch may be selected.

With Java 21 `javac`, when disassembling a pattern-matching `switch`, you may encounter:

- **`invokedynamic`** using the JVM bootstrap mechanism, where **`java.lang.runtime.SwitchBootstraps.typeSwitch`** is the name to look for in `BootstrapMethods`.
- Branches such as **`tableswitch`** or **`lookupswitch`** to dispatch to the compiled cases.
- Record component checks and guard comparisons using integer manipulation and conditional branch instructions.
- Fallback branches or defensive code to maintain safety if the runtime type hierarchy no longer matches compile-time assumptions.

The command:

```bash
javap -v -p PatternBytecodeInspectionDemo
```

lets you inspect the **constant pool**, `InvokeDynamic` entries, `BootstrapMethods`, and how they relate to the `describe` method. Combine it with:

```bash
javap -c -p PatternBytecodeInspectionDemo
```

to trace control flow at the JVM level.

**Do not assume `switch` always generates a single `tableswitch`** or always has the same opcode ordering. Compilation depends on the selector/case shape, `javac` algorithms, and compiler version. The goal is to recognize semantics, not to memorize a fixed listing and treat it as the Java standard.

### A False Guard Is Not an Exception

If `Circle(3)` matches the record pattern but `radius >= 10` is false, `switch` tries the next case. If an accessor or guard **throws an exception**, the semantics differ: it does not turn the exception into `false` and continue. Bytecode may include exception handlers to support pattern semantics; to confirm, check the `Exception table` and related code in `javap -v`, and use controlled fault-injection input tests.

## 9. Step Five: Inspecting Sealed Hierarchies and Record Metadata

Given:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(int radius) implements Shape {}
record Rectangle(int width, int height) implements Shape {}
```

the command:

```bash
javap -v -p 'PatternBytecodeInspectionDemo$Shape'
```

can display the **`PermittedSubclasses` attribute**, listing the permitted direct subtypes according to the class file. This is evidence of hierarchy boundaries at the binary level, not a listing of all runtime objects currently in existence.

For a record:

```bash
javap -v -p 'PatternBytecodeInspectionDemo$Circle'
```

look for:

- The class extending `java.lang.Record`.
- The **`Record`** attribute describing the `radius` component.
- Constructor signature, `radius()` accessor, and auto-generated record methods.
- `NestHost`/`InnerClasses` or nested-type metadata, depending on the class file structure.

What to distinguish: `PermittedSubclasses` belongs to `sealed` types, while the `Record` attribute describes **component structure**. They do not substitute for each other and do not prove that component values are valid according to business rules.

## 10. Class File Version, Debug Info, and Runtime Compatibility

Use:

```bash
javap -v PatternBytecodeInspectionDemo
```

Look for information such as:

```text
major version: 65
```

For a program compiled with `--release 21`, this is the expected result. Sections such as `flags`, `this_class`, `super_class`, `Constant pool`, `SourceFile`, and `BootstrapMethods` help explain the generated class file.

**Misconceptions to avoid:**

- Having a Java 21 runtime (`java -version`) **does not guarantee** that all running classes were compiled at Java 21; they may have been built with `--release 17`.
- `major version: 65` confirms that the class file format corresponds to Java 21; it **does not confirm** that every branch/guard is logically correct.
- Class files built for Java 21 generally **will not run on a Java 17 JVM**; loading an unsupported class can trigger `UnsupportedClassVersionError`.
- `LineNumberTable` is not a one-to-one mapping from each Java statement to an opcode. The compiler may emit multiple instructions from a single expression or merge multiple source operations.
- Pattern variables are typically represented using local slots/stack and branches; source variable names only appear in debug metadata if present, not as independent "JVM variables" separate from storage slots.
- Running `javap -c` does not reveal execution time, JIT inlining frequency, or final machine code.

### When You Need to Inspect Pattern Variables and Scope

Compile with `-g` as shown in Section 2, then run:

```bash
javap -c -l -p PatternBytecodeInspectionDemo
```

Look for `LocalVariableTable`, if present, to see the **local slot**, start offset, and bytecode length where the variable name is recorded in debug info. This helps with lookup, but **flow scoping per the Java specification** remains a source-level rule; the debug range is not the formal definition of language scope.

If compiled without `-g`, local variable name metadata may be absent. Therefore, not seeing `radius` or `point` in `javap` **does not mean the compiler did not use a local variable**.

## 11. Applying This in Maven, Gradle, and CI

### Maven

In a Maven project with an appropriately configured `maven-compiler-plugin` and a JDK supporting Java 21, you can declare the compilation level:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Exact configuration also depends on the plugin version and project toolchain. After building, you can inspect the generated class file:

```bash
javap -classpath target/classes -v com.example.PatternBytecodeInspectionDemo
```

The command above assumes the project places the class in the `com.example` package. If the class is in another package, use its **actual fully qualified name**; do not use the example path literally as if it were an existing class.

### Gradle

Example Gradle **Groovy DSL** configuration to select a Java 21 toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

This is a configuration snippet, not a complete `build.gradle`; the project must apply the appropriate Java plugin and use a Gradle version that supports the JDK/toolchain in use. After building, inspect the corresponding output:

```bash
javap -classpath build/classes/java/main -v com.example.PatternBytecodeInspectionDemo
```

For both Maven and Gradle, **verify that you are actually inspecting the right build output**, rather than pointing to `.class` files in an old location. CI should also pin or record the `java`/`javac` versions, `--release` configuration, and any post-compilation bytecode plugins such as bytecode enhancement/instrumentation if present.

### A Practical CI Workflow

1. Build with the pinned JDK and `--release`.
2. Run unit tests to verify pattern and guard **semantics**.
3. When compatibility matters, check the class file version and key attributes.
4. For deep bug investigations, save the disassembly corresponding to the **released artifact**, not output from another workspace.
5. Do not turn a specific bytecode listing into a rigid golden test if compiler/JDK updates are allowed; check **meaningful invariants** such as version, metadata, and behavior.

## 12. Comparing Bytecode Is Not Enough to Conclude Performance

A common question: "Between `Point(int x, int y)` and `Point point` followed by `point.x()`/`point.y()`, which is faster?"

`javap` helps reveal **the calls/branches present in the class file**. However:

- The JVM can inline very small accessors, eliminating some redundant operations when enough information is available.
- Record patterns with multiple guarded cases may call accessors repeatedly along different paths; actual frequency depends on the data.
- Opcode count does not directly represent CPU cycles; cache, JIT, runtime object types, allocation, and branch prediction can all matter.
- Microbenchmarks lacking warm-up, suffering from dead-code elimination, or testing a single input can easily lead to wrong conclusions.

To test performance, use **JMH** or an appropriate profiler, standardizing workload, data, JDK, warm-up, iteration count, and true/false guard paths. Use `javap` to **form hypotheses and explain** benchmark results, not as a substitute for benchmarking.

If a custom accessor has side effects, treat that as a **correctness and maintainability** issue before optimizing: a record pattern can call the accessor for deconstruction, so refactoring source code without considering accessor behavior can change observed results or exceptions.

## 13. Common Pitfalls When Reading javap Output

| Symptom | Misinterpretation | How to handle |
| --- | --- | --- |
| `radius` not seen in `javap -c` output | "The compiler did not create a pattern variable" | Compile with `-g` and check `-l`/`LocalVariableTable`; distinguish metadata from executable bytecode. |
| `invokedynamic` appears | "The program must be slow because it's dynamic" | Check the associated bootstrap (`typeSwitch`, `ObjectMethods`, `StringConcatFactory`, etc.) and measure at runtime if needed. |
| No `tableswitch` matching the documentation example | "The compiler skipped the switch" | Look for the actual dispatch structure; the compiler may lower syntax in multiple ways. |
| Accessor calls appear | "Record patterns are always slow" | The JIT may inline them; check the workload and profiler. |
| `ClassNotFound` when running `javap` on a nested type | "No class file was generated for the record" | Quote names containing `$`, and check the classpath and output directory. |
| Major version 65 appears | "This code will definitely run on any Java version" | The runtime must support Java 21 class files and all dependencies. |
| `PermittedSubclasses` missing on a regular class | "`javac` built it wrong" | That attribute is for `sealed` types; check the root `sealed` class/interface. |
| No explicit null branch visible as a separate case in bytecode | "The source does not handle null" | The compiler may compile null checks/dispatch differently; compare source and tests. |
| Bytecode from IDE differs from CI | "Same source means identical output" | Verify compiler version, flags, annotation processors, bytecode instrumentation, and the artifact itself. |

## 14. Self-Check

**Exercise 1.** You need to know whether a class file actually targets Java 21 or Java 17. Which command is appropriate, and which field should you read?

**Answer:** Use `javap -v ClassName` and check **`major version`**. A value of `65` corresponds to Java 21; `61` corresponds to Java 17. Verify this alongside the build toolchain and `--release`.

**Exercise 2.** You see `record Point(int x, int y)` and source code using `case Point(int x, int y)`. Why should you inspect both `Point.class` and the class containing the `switch`?

**Answer:** The `Point` class shows the record components, accessors, and `Record` metadata; the class containing the `switch` shows the dispatch logic, checks/matching, and how accessors are called during classification. Inspecting only one of the two is not enough to understand the full path.

**Exercise 3.** In `javap -v`, `BootstrapMethods` shows `java.lang.runtime.SwitchBootstraps.typeSwitch`. Must every pattern switch generate the exact same opcode listing on every JDK?

**Answer:** No. `typeSwitch` is an important mechanism that `javac` can use, but the exact bytecode shape is not a source-syntax contract. The compiler and its lowering strategy can change as long as the specified semantics are preserved.

**Exercise 4.** Why do some variable names appear when compiled with `-g` but disappear from the output when compiled without `-g`?

**Answer:** Local variable names and ranges may be stored in `LocalVariableTable` for debugging. The absence of metadata does not prove the variable does not exist in JVM computation.

**Exercise 5.** Why shouldn't you conclude that a record pattern is slower solely because the bytecode shows two accessor calls?

**Answer:** Bytecode is input to the runtime; the JIT can inline and optimize it, and actual cost depends on the workload. You need benchmarks/profilers and behavior checks to make a decision.

## 15. Pre-Completion Investigation Checklist

1. Verified `java`, `javac`, `javap`, and matching `--release`/toolchain?
2. Successfully run the Java program and verified **stdout** before reading the disassembly?
3. Inspecting the exact **class file** from the target build, not a stale file?
4. Used `javap -c -p` on the method containing `instanceof`/record patterns/`switch`?
5. Used `javap -v` to check `major version`, `Record`, `PermittedSubclasses`, and `BootstrapMethods` when relevant?
6. Quoted nested type names containing `$` when running in the shell?
7. If investigating scope/debug info, used `javac -g` and `javap -l` without equating debug ranges to language rules?
8. Distinguished between type patterns, record accessors, false guards, null selectors, and exceptions?
9. Avoided using opcode counts as absolute conclusions about performance?
10. Tied analysis results back to **behavioral tests and build artifact checks** instead of looking only at bytecode listings?

## 16. Official References

- **Oracle JDK 21 `javap` tool:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html
- **Oracle JDK 21 `javac` tool:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Java Virtual Machine Specification 21 – Class File Format (`4):** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **Java Language Specification 21 – Patterns (`14.30):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- **JEP 440 – Record Patterns:** https://openjdk.org/jeps/440
- **JEP 441 – Pattern Matching for switch:** https://openjdk.org/jeps/441

**Key takeaway:** After compilation, `javap` helps you observe **class file version, bytecode, record metadata, sealed subtypes, and dispatch mechanisms**. Connect `instanceof`/`checkcast` to type checks, accessors to deconstruction, `invokedynamic`/bootstrap to certain `switch` compilation strategies, and debug tables to source cross-referencing. However, only **the compiler, behavioral tests, and profiling** together can fully answer whether the code is correct, compatible, and fast enough.
