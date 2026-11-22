# Boundary Between the Java Specification and `javac` Implementation Details

## 1. Why Distinguish Them?

When reading Java code, we commonly encounter three different questions: **whether code is valid**, **what valid code must mean**, and **how the current tool translated it**. The first two questions must largely be answered from the specification; the last requires inspecting a specific implementation, such as `javac` in a given JDK version.

For example, operand evaluation order in a Java expression belongs to the language contract; the number of emitted bytecode instructions, compiler-generated temporary variable names, and wording of error messages are not part of that same contract. Confusing these two layers easily leads to wrong conclusions when changing JDKs, switching compilers, analyzing performance, reverse-engineering bytecode, or writing source-processing tools.

**Lesson objectives:** identify what Java guarantees versus what `javac` chooses; use the specification to explain semantics and `javac`/`javap` to verify a build; avoid inferring language rules from a single bytecode observation.

## 2. Documents and Responsibility Layers

| Layer | What is specified or described | Example | What must not be inferred |
| --- | --- | --- | --- |
| **JLS — Java Language Specification** | Syntax, types, conversions, overloading, definite assignment, compile-time checks, expression evaluation, exceptions, and the Java Memory Model | Left-to-right argument evaluation order; when a compile-time error is required | A compiler must have a specific number of phases, AST structure, or diagnostic wording |
| **JVMS — Java Virtual Machine Specification** | `.class` structure, instruction set, verifier, linking, class initialization, and JVM execution semantics | Valid class file, `invokevirtual`, `invokedynamic`, constant pool | Every Java expression must always translate to the exact same instruction sequence |
| **Java SE/JDK API specifications** | Contracts of standard libraries and public APIs | Behavior of `String`, `List`, `javax.tools.JavaCompiler` | Internal classes `com.sun.tools.javac.*` are stable APIs |
| **`javac` tool documentation** | Published options and behavior of the compiler command in the corresponding JDK release | `--release`, `-g`, `-parameters`, `-Xlint` | Every optimization choice or internal pipeline is a cross-version commitment |
| **Specific `javac` implementation** | How parser, type checker, language desugaring, and code generator work in one build | How `for-each` is lowered into instructions; how synthetic variable names are structured | Another compiler or JDK version must emit identical bytecode |
| **Executing JVM, such as HotSpot** | Class loading, interpreter, JIT, memory management, and runtime optimizations of a product | May inline methods at runtime | Bytecode emitted by `javac` is already final machine code |

Core boundary: **JLS specifies the meaning of a Java program; JVMS specifies the meaning of class files on a conforming JVM; `javac` is a tool transforming source code into executable form adhering to the relevant contracts.** The two specifications have mandatory relationships, yet do not dictate a single compilation strategy.

Not everything observable in an application is defined by the JLS: file I/O, networking, time, locale, third-party libraries, and the runtime environment also depend on API contracts and actual configuration. Conversely, whether HotSpot performs JIT does not change source overload resolution rules.

## 3. One Compilation Chain, Multiple Contract Layers

```text
.java source
  │  grammar, binding, type checking, flow, source semantics (JLS)
  ▼
A compiler, e.g. javac
  │  parse / analyze / annotation processing / lowering / code generation
  │  (phase division and intermediate structures are implementation details)
  ▼
.class file
  │  format and validity per JVMS
  ▼
JVM: load → link/verify → initialize when needed → execute
  │  interpreter/JIT/GC are implementation choices within contract bounds
  ▼
Observed behavior per specification and environment
```

Phase names such as parse, enter, attribution, flow, desugar, and generate are often useful when studying `javac` architecture. However, **do not treat those phase names as mandatory Java language rules**. A conforming compiler may organize or combine steps differently.

Similarly, seeing a source construct "desugared" into a loop, iterator, or helper method only describes how a compiler implements it. The programmer-facing contract consists of the evaluation rules and observable behavior mandated by the JLS.

## 4. What Is a Language Rule, and What Is a Compiler Choice?

### 4.1. Type Checking and Mandatory Errors

Consider this invalid snippet:

```java
class WrongType {
    int count = "three";
}
```

Assigning a `String` to `int` has no valid conversion here, so it **must be detected as a compile-time error**. That is a JLS-level conclusion. Yet specific wording like "incompatible types", caret position, error codes, fix suggestions, message language, or how many errors are printed are tool diagnostic behaviors. `javac` may also change messages across releases.

**How to verify:** check assignment conversion rules in the JLS first; then run `javac` when a diagnostic log is needed to help fix code. Do not use error message wording as a specification of Java semantics.

### 4.2. Observable Execution Order

Save as `EvaluationOrder.java`:

```java
public class EvaluationOrder {
    static int next(String label, int value) {
        System.out.println(label);
        return value;
    }

    static int sum(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        int result = sum(next("left", 2), next("right", 3));
        System.out.println(result);
    }
}
```

Compile and run with JDK 17+:

```bash
javac EvaluationOrder.java
java EvaluationOrder
```

Deterministic output:

```text
left
right
5
```

Java evaluates invocation arguments from left to right (JLS `15.7.4); a conforming compiler cannot flip the output to `right` before `left` simply because that optimizes better. However, how order is preserved using the JVM stack, temporary variables, or specific optimizations can differ. This is how to separate **observable semantics** from **code-generation mechanisms**.

### 4.3. Bytecode Has No Single Fixed Shape

```java
public class BytecodeExample {
    public static int calculate(int input) {
        int plusOne = input + 1;
        return plusOne * 2;
    }

    public static void main(String[] args) {
        System.out.println(calculate(4));
    }
}
```

```bash
javac BytecodeExample.java
java BytecodeExample
javap -c -p BytecodeExample
```

Output of running `java`:

```text
10
```

`javap -c` shows instructions **actually emitted by the toolchain in use**; this is excellent evidence for studying class files. Yet do not state a rule such as "Java requires `iadd` followed by `imul` for this method" based on one observation. When changing compilers, build flags, or JDK versions, the representation may change while preserving the method's meaning.

Some compilers may precompute constants, reorder instructions when safe, merge, or eliminate intermediate variables. Only transformations preserving the relevant contracts are permitted; optimization is not a license to violate evaluation rules, exceptions, or the Java Memory Model.

### 4.4. Lowering Non-Primitive Syntax

The enhanced `for` loop has its own rules in the JLS. For arrays and `Iterable`, compilers may lower this construct into different low-level operations. When learning, ask first: how many times is the source expression evaluated, what is the iteration order, and what are the loop variable's type and conversions? Then use `javap` to inspect which instruction sequence `javac` chose.

Features such as lambdas, method references, records, and `+` string concatenation illustrate this even more clearly: a given `javac` version may use `invokedynamic`, bootstrap methods, or synthetic methods. Those are details to notice when reading bytecode, but their specific shape must not be turned into a permanent guarantee of Java syntax.

## 5. Compile-Time Semantics Differ from Optional Optimizations

Not every computation appearing in a class file as a constant is an "automatic compiler optimization". The JLS defines **constant expressions** and **constant variables** with language consequences, such as allowing certain constant computations in `case` labels and allowing certain field constant values to be embedded directly at usage sites.

Example:

```java
public class CompileTimeConstants {
    static final int BASE = 20;
    static final int DOUBLE = BASE * 2;

    public static void main(String[] args) {
        int value = 40;
        switch (value) {
            case DOUBLE -> System.out.println("match");
            default -> System.out.println("no match");
        }
    }
}
```

```bash
javac CompileTimeConstants.java
java CompileTimeConstants
```

```text
match
```

`DOUBLE` is a constant variable, and `case DOUBLE` is a valid constant label per language rules. By contrast, which instructions an ordinary expression optimizes to can depend on the compiler. When modifying a `public static final` field that is a compile-time constant in a library, **previously compiled clients may still retain the old value**; clients must be recompiled to update values embedded into binaries. Do not mistake this binary compatibility issue for a `javac` caching bug.

## 6. Java Versions: Language, API, and Class File Are Three Separate Axes

A common misconception: "emitting bytecode for an older Java guarantees it runs on an older Java". Controlling only the class file version is insufficient if code still references APIs not present on the target runtime.

| `javac` option | Primary effect | Limitation |
| --- | --- | --- |
| `--source N` | Syntax/language rules accepted at Java N level | Does not automatically lock the API set to Java N |
| `--target N` | Generated class file version | Does not automatically guarantee all called APIs exist on Java N runtime |
| `--release N` | Constrains language, class file format, and platform APIs of Java N | Does not verify compatibility of external non-platform dependencies or runtime conditions |
| Omitting these flags | Uses defaults of the running `javac` version | Defaults can change across JDKs |

Example creating `ModernApi.java`:

```java
public class ModernApi {
    public static void main(String[] args) {
        System.out.println("ab".repeat(2));
    }
}
```

With a JDK 17+ supporting `--release 8`:

```bash
javac --release 17 ModernApi.java
java ModernApi
javac --release 8 ModernApi.java
```

Running after the first compilation prints:

```text
abab
```

The `javac --release 8` command must **fail** because `String.repeat(int)` was introduced in Java 11 and does not exist in the Java 8 platform API. No verbatim diagnostic text is guaranteed. This experiment demonstrates an error tied to **per-release API contracts**, not solely syntax or the `.class` version header.

In real deployments, use `--release` matching the target, clearly record build/run JDK versions, verify external libraries, modules, preview features, OS dependencies, and run tests on the target runtime. Do not infer compatibility solely from a successful build.

## 7. Options That Change Artifacts Without Changing Source Meaning

- `-g` or `-g:lines,vars,source` requests extra debug information in class files; observable with `javap -l` or `-v`. Lacking this information does not semantically remove local variables in source code.
- `-parameters` records parameter name metadata for methods/constructors so reflection via `java.lang.reflect.Parameter` can retrieve declared names. This is a property of the built artifact, not a change in source parameter-naming rules.
- `-Xlint` enables `javac` warnings; `-Werror` turns warnings into build failures. Warnings are quality-control tools and do not themselves become JLS prohibitions.
- `-encoding` controls how `javac` decodes source files; differing encodings can alter compiler input. Explicitly specify UTF-8 in builds when reproducibility is required.
- `-classpath`/`--class-path` and `--module-path` change the type/dependency lookup environment during compilation. Do not confuse with the execution classpath/module path of the `java` command.
- `-d` changes the output directory without changing the Java semantics of the program.

In a CI pipeline, record tool versions (`javac -version`), compiler flags, annotation processors, dependency resolution, and generated sources. Two class files differing byte-for-byte do not prove one build is wrong; look for meaningful differences in behavior, ABI, metadata, or established reproducibility constraints.

## 8. Annotation Processing and the Compiler API

`javac` can run **annotation processors** during compilation; processors can generate source files, resources, or diagnostics per standard APIs. That does not mean an arbitrary annotation automatically implies "code generation"; verify which processors are present, how they are configured, and whether they execute in the JDK and build system in use.

`javax.annotation.processing` and `javax.tools` are documented public APIs for annotation processing and compiler integration. For instance, tools can call `ToolProvider.getSystemJavaCompiler()` to obtain the system compiler when running on a JDK that provides one; the result may be `null` if the environment provides no compiler. Conversely, internal packages starting with `com.sun.tools.javac` can be helpful for research/compiler plugins, yet **are not stable APIs simply because they exist in a JDK**. When depending on internals, evaluate exact-version compatibility and module encapsulation policies.

Do not treat classes generated by processors as new Java language syntax. Separate clearly: human-written source, generated source, plugins/processors, and compiler guarantees.

## 9. When Reading `javap`, Decompilers, and Stack Traces

`javap` inspects class files; decompilers attempt to reconstruct source code; stack traces and debuggers use class file info and available metadata. None of these three tool categories replaces the JLS when explaining source semantics.

For example, seeing `lambda$main$0` or synthetic variables in output does not mean the programmer defined them in source code. Likewise, not seeing a local variable in `javap -c` does not mean that variable fails to exist at the language-concept level. JVM representation centers on stack, slots, and instructions; variables, blocks, and expressions in source may not map 1-to-1.

When investigating an issue:
1. **Define the question:** source validity, artifact difference, runtime behavior, or performance.
2. **Choose the reference:** JLS for syntax/semantics; JVMS for class files/instructions; API docs for libraries; `javac` manual for flags; HotSpot/JVM docs when examining JIT/GC.
3. **Create a minimal reproducer**, recording JDK/toolchain/flags; if a runtime error, record the actual runtime.
4. **Compare observable behavior** first, then use `javap`/logs as supporting evidence.
5. **Do not generalize from a single output:** an implementation detail counts as a contract only when documented as such.

## 10. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`javac` emits bytecode like this, so the JLS requires it." | The JLS constrains semantics; bytecode also depends on the compiler and JVMS. |
| "Identical Java source must yield byte-identical `.class` files on every JDK." | No such universal guarantee exists. Compare at ABI/behavior level or establish dedicated reproducible-build criteria. |
| "`javac` error messages are verbatim Java rules." | Compile-time error rules reside in the JLS; wording, locations, and suggestions may vary. |
| "`--target 8` means APIs newer than Java 8 cannot be used." | Control APIs using `--release 8` or an equivalent process. |
| "JIT optimizing a method means `javac` already generated that optimized machine code." | `javac` normally emits class files; runtime JIT is a separate layer. |
| "Source has no helper methods so the class file cannot have any either." | The compiler may generate synthetic methods/classes conforming to the contract. |
| "Testing on my machine alone suffices to know how every JVM behaves." | One experiment supplies evidence for that toolchain/environment; general conclusions require citing the specification. |

For data race bugs, the boundary matters even more: JLS `17 (Java Memory Model) defines valid memory behaviors; compilers/JIT/CPUs are free to optimize within those bounds. One run that "appears right" does not prove unsynchronized code is safe.

## 11. Self-Check Exercises and Answers

**Exercise 1.** One `javac` version emits `invokedynamic` for string concatenation, another uses a different call sequence. Do the two automatically violate Java?

**Answer:** No. Check whether they preserve string concatenation semantics and related constraints; `invokedynamic` is simply one class-file-level implementation choice.

**Exercise 2.** Running `javac --target 8` succeeds, yet running on Java 8 hits `NoSuchMethodError` due to calling an API introduced in Java 11. Where was the mistake?

**Answer:** The class file target level alone did not constrain platform APIs. Use `--release 8` with a supporting toolchain and check target dependencies/runtime.

**Exercise 3.** A unit test asserts "javac always generates exactly three instructions for the expression `x + 1`". Is this testing a language rule or an implementation detail?

**Answer:** Testing an implementation detail. Pin the JDK/compiler version and test purpose when bytecode-level regression checking is needed; do not use it to prove the JLS.

**Exercise 4.** Where should you look up which operand evaluates first in a method call with side effects?

**Answer:** JLS `15.7 and `15.12, especially `15.7.4` on argument list evaluation order; the `EvaluationOrder` experiment merely illustrates the rule.

## 12. Authoritative References

- **Java Language Specification (JLS), Java SE 21:** https://docs.oracle.com/javase/specs/jls/se21/html/ — especially chapters 5 (conversions), 15 (expressions), 17 (memory model).
- **Java Virtual Machine Specification (JVMS), Java SE 21:** https://docs.oracle.com/javase/specs/jvms/se21/html/ — `class` format, verification, instruction set, execution.
- **JDK 21 `javac` tool reference:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — option meanings, compilation environments, annotation processing.
- **Java SE 21 API reference:** https://docs.oracle.com/en/java/javase/21/docs/api/ — public library contracts.

Links target **Java 21** for a consistent study baseline; when working on projects using another Java release, consult the matching edition of the specification and tool documentation.
