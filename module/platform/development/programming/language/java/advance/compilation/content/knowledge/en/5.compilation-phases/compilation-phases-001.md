# Overview of Processing Phases in javac

`javac` is the Java compiler that compiles **source code** (`.java`) into **class files** (`.class`) containing bytecode and metadata that the JVM can load. Between that input and output, the compiler must understand the syntax, know which declaration each name refers to, check types and language rules, process annotations (if configured), transform high-level constructs into a representation suitable for the JVM, and then generate class files.

Understanding the phases helps answer practical questions: why a missing bracket differs from `cannot find symbol`, why syntactically valid Java code is rejected due to types, how an annotation processor can generate additional source code, and why Java code that compiled successfully can still fail at runtime.

This article uses Java 17+ as the baseline for examples. Phase names such as `Parse`, `Enter`, `Attr`, `Flow`, `Lower`, and `Gen` describe the familiar tasks of OpenJDK `javac`. **Do not interpret them as a stable API mandating that the compiler must run a single linear sequence of operations for every file.** Work can happen per compilation unit, per type, per annotation processing round, and can interleave according to dependencies.

## 1. Overall Map

~~~text
.java files + javac options
           │
           ▼
Read source, recognize tokens (lexing)
           │
           ▼
Parse: build abstract syntax tree (AST)
           │
           ▼
Enter: register packages, types, declarations, and symbols
           │
           ├─────────► Annotation processing (if enabled)
           │                   │
           │                   └── generated source → parse/enter, next round
           │
           ▼
Analyze: name resolution, type checking, semantics, control flow
           │
           ▼
Transform / Lower: lower Java constructs to class file representation
           │
           ▼
Generate: generate bytecode and metadata
           │
           ▼
.class files ──► JVM loads, links, and executes when running the application
~~~

The diagram helps with orientation, but there are three points that are easy to misunderstand:

1. **Successful parsing does not mean the program is valid.** An expression can be grammatically correct yet ill-typed; a class name can be spelled correctly yet not be on the classpath.
2. **Annotation processing is a multi-round branch.** A processor can generate new source code; the compiler must continue processing the new sources before finishing compilation. Not every `javac` invocation involves annotation processing.
3. **The JVM is not the final phase inside `javac`.** `javac` produces class files; class loading, verification, linking, initialization, JIT, and execution are runtime mechanisms that happen later if the program is run.

This can be divided into three mental layers: **syntax** (is the code written with valid Java structure), **semantics** (is the code meaningful and valid according to Java rules), **output** (how valid code is represented as class files).

## 2. Inputs and Compilation Environment

A minimal invocation:

~~~bash
javac -encoding UTF-8 --release 17 -d out Hello.java
~~~

The compiler needs many things besides the contents of `Hello.java`:

| Input | Role |
| --- | --- |
| `.java` files | Contain packages, imports, types, methods, and expressions to compile |
| `--release 17` | Selects the language level, platform API, and bytecode format corresponding to Java 17 |
| `-encoding UTF-8` | Specifies the encoding for reading source files |
| `-d out` | Selects the output directory for `.class` files |
| `-cp` / `--class-path` | Provides classes and libraries not in Java platform modules or current sources |
| `--module-path` | Provides module dependencies for projects using JPMS |
| `--source-path` | Helps locate dependent sources when not all files are listed directly |
| Annotation processor configuration | Controls whether to run processors and where to load processors from |

`javac` can read multiple source files in the same pass:

~~~bash
javac -encoding UTF-8 --release 17 -d out App.java Helper.java
~~~

One invocation can process relationships between types across multiple files; it does not necessarily finish compiling `App.java` completely before starting `Helper.java`. Classpath does not mean the compiler automatically compiles every `.java` file inside a library.

It is necessary to distinguish **language/target selection** from **the JDK version running the compiler**. For example, `--release 17` on a newer JDK aims to compile with Java 17 constraints; if syntax/APIs newer than 17 are used, errors can appear right at parse or analyze. Selecting `-source 17 -target 17` alone does not provide the full Java 17 API guarantees that `--release 17` does.

## 3. Character Reading, Tokenizing, and Parsing Phases

Before understanding program meaning, the compiler reads source characters and splits them into **tokens**: keywords, identifiers, literals, operators, separators, and other syntactic components. Lexical analysis also handles language-specific rules, including interpreting Unicode escapes according to the Java Language Specification; do not treat the Java lexer like a simple word tokenizer on a text file.

Syntactically valid example:

~~~java
class Example {
    int total = 10 + 20;
}
~~~

You can picture the typical tokens: `class`, `Example`, `{`, `int`, `total`, `=`, `10`, `+`, `20`, `;`, and `}`. This part does not yet say where `total` can be accessed or whether `Example` is used validly in other code; that is semantics.

**Parsing** reads the token stream according to the Java grammar and builds an **abstract syntax tree (AST)**. The AST describes program structure: compilation unit, class declaration, variable declaration, binary expression, method invocation... It discards many surface details unnecessary for semantic analysis, while retaining source positions for error reporting.

Syntax error example — file `BrokenSyntax.java`:

~~~java
class BrokenSyntax {
    void print() {
        System.out.println("Hello")
    }
}
~~~

Missing `;` after the method call. `javac BrokenSyntax.java` will report a syntax error at the relevant location (the exact message/position may vary by JDK). The compiler may attempt error recovery to report additional errors, but an AST containing errors cannot be treated as a valid program to generate class files.

**Do not misclassify errors:** if you write `int n = "text";`, the tokens and statement structure are completely valid; the error only appears during type checking.

## 4. Enter: Registering Declarations and Symbols

Once the syntactic structure is available, the compiler needs to know **what the program declares**. The group of tasks commonly called `Enter` (and related completion steps) registers packages, classes, interfaces, members, and **symbols** into the compiler's data structures.

A symbol represents a semantic entity such as a type, variable, method, package, or module. Having the same textual name does not mean being the same symbol: `List` may be `java.util.List` or another type depending on imports and context; `value` in two different scopes may be two different variables.

Example:

~~~java
class Account {
    int balance;

    int add(int amount) {
        return balance + amount;
    }
}
~~~

The compiler must recognize that `Account` is a type, `balance` is a field, `amount` is a parameter, and `add(int)` is a method declaration. Thanks to the declaration table, the compiler can analyze references to members without depending on the ordering of methods in the class body.

The declaration registration phase does not yet prove that every expression in a method body is well-typed or that control flow is valid. In a real compiler, entering declarations and completing symbols takes multiple steps; "Enter" is a general name, not all semantics being resolved at a single moment.

### Package, import, classpath, and module

When resolving types, the compiler needs to locate declarations from the current sources, source path, classpath, module path, and properly configured Java platform APIs. Having `import java.util.List;` does not mean `List` has been loaded or the entire library is copied into the program; imports allow short names to be understood within valid scope.

With named modules, the compiler also evaluates `requires`, `exports`, and accessibility between modules. A package inside a module present on the module path may still be **unreadable or not exported** to the module being compiled.

## 5. Analyze: Name Resolution, Type Checking, and Semantic Rules

After syntax and declaration identification, the compiler performs the checks necessary to decide whether the code is valid according to the Java Language Specification. In OpenJDK `javac`, this group involves steps such as attribution (commonly called `Attr`), declaration validity checks, type inference, and flow analysis.

**Name and overload resolution:** for `Math.max(3, 4)`, the compiler must determine what type `Math` is and select the appropriate overload from the available method signatures. Overload resolution rules depend on argument types, type conversions, boxing, varargs, generics, and precedence rules according to the JLS.

**Type checking:** example:

~~~java
class WrongType {
    void demo() {
        int age = "twenty";
    }
}
~~~

The parser accepts the structure of the declaration; semantic analysis detects that `String` cannot be assigned to `int`. Messages such as `incompatible types` belong to semantic errors, not lexer errors.

**Accessibility checking:** a `private` method can only be used in locations permitted by Java's access rules. The compiler also checks inheritance, overriding, checked exceptions, generic bounds, and many other constraints.

**Type inference:** `var` and lambda syntax do not mean "no type checking." Java is still a statically type-checked language; the compiler infers the type based on the initializer or target type in valid contexts. Example:

~~~java
import java.util.function.Function;

class Inference {
    static void example() {
        var message = "ready";             // String
        Function<Integer, Integer> twice = x -> x * 2;
    }
}
~~~

The code above is valid in Java 17; the comments `String` and `Function<Integer, Integer>` describe the result of type analysis, not types determined at runtime by inspecting values.

### Flow analysis: variable state and control paths

The compiler also inspects the control paths that can reach a variable usage point or statement. Two familiar cases are **definite assignment** and **reachability**.

~~~java
class WrongFlow {
    void demo(boolean flag) {
        int result;
        if (flag) {
            result = 10;
        }
        System.out.println(result);
    }
}
~~~

Error because `result` is not guaranteed to have been assigned if `flag` is `false`. The compiler does not need to run the program to recognize that path.

Another example:

~~~java
class Unreachable {
    void demo() {
        return;
        // System.out.println("never"); // If // is removed, this is an unreachable statement
    }
}
~~~

All of these rules belong to **compile-time checks**; this differs from whether the actual program at runtime executes through a given branch. Do not interpret "flow analysis" as the compiler always proving every property of a program: it performs the checks specified by Java and cannot eliminate all logic bugs or all runtime exceptions.

## 6. Annotation Processing: Multi-Round Extension Branch

Annotation processing per `javax.annotation.processing` (JSR 269) allows a processor to **read the declaration model and annotations**, emit diagnostics, and generate additional sources/classes/resources through APIs such as `Filer`. It is commonly used to generate code from annotations, metadata, or adapters, but **this does not mean every annotation has a processor**.

Conceptual workflow:

~~~text
Initial sources recognized
          │
          ▼
Round 1: processor inspects matching elements and annotations
          │
          ├── New sources generated? ───► Round 2
          │                                 │
          │                                 └── New sources? → next round
          ▼
Final round: processingOver() = true
          │
          ▼
Compile initial sources + generated sources (if configuration allows)
~~~

Processors are invoked across multiple rounds when new sources exist; in the final round, they get a chance to finalize, though they must not assume they will be allowed to keep generating sources for a new round. Do not write processors in a way that depends on a specific number of rounds for every project. Generated source files must have valid declarations and pass through the required compiler checks before class files are created.

### Selecting the processing mode

| Option | Meaning |
| --- | --- |
| `-proc:none` | Do not run annotation processing; still compile source code |
| `-proc:only` | Run annotation processing and do not proceed to normal bytecode compilation |
| `-proc:full` | Request both annotation processing and compilation (on supported JDK versions) |
| `-processor p.MyProcessor` | Specify the processor to run |
| `--processor-path path` | Select where to search for processors on the processor-style classpath |
| `-s generated` | Select the directory to write source files generated by annotation processors |
| `-XprintRounds` | Display information about processing rounds |
| `-XprintProcessorInfo` | Display which annotations processors are asked to handle |

**Version differences:** JDK 23 changed the default implicit annotation processing policy compared to older versions; **explicitly configure processing** when a build depends on code generation, rather than assuming a processor is automatically discovered on the classpath across all JDKs. `-proc:full` is supported in appropriate JDK 17 update releases, but if compatibility with a very old JDK 17 release is needed, check `javac -help` on that specific JDK.

`-XprintRounds` only provides useful information when annotation processing actually runs. Using this option alone in a command with no processor does not guarantee seeing rounds. `-proc:only` also does not guarantee `.class` files after the command.

Standard annotation processors operate on the element model and generated files; they should not be equated with plugins that modify internal ASTs, compiler plugins, or direct bytecode manipulation. If a tool relies on internal `javac` APIs, JDK compatibility must be evaluated separately.

## 7. Lowering Language Constructs: from High-Level Java to the JVM

Java allows writing many convenient constructs that are not represented verbatim by a corresponding JVM instruction. After semantic checking, the compiler performs **desugaring / lowering** to represent those constructs in a form suitable for generating bytecode and metadata.

Conceptual examples:

| Source construct | What needs to be represented after compilation |
| --- | --- |
| Generic `List<String>` | **Type erasure** rules in descriptors/bytecode, along with metadata such as generic signatures when needed |
| Enhanced `for` | Equivalent loop suitable for arrays or `Iterable` / `Iterator` |
| Autoboxing/unboxing | Equivalent conversions between primitives and wrappers |
| `try`-with-resources | Ensures resource closing according to Java ordering/exception rules |
| Lambda / method reference | Mechanism to represent function objects, typically via `invokedynamic` and bootstrap metadata on OpenJDK `javac` |
| `record` | Class with members and behavior generated by the compiler per the record specification |
| Switch expression | Corresponding control flow and value computation in bytecode |

The list describes **common observable outcomes and mechanisms**, without claiming the compiler always transforms into an exact equivalent Java source construct or always emits a fixed sequence of instructions. Details may vary by JDK, `--release`, target, and context. For example, lambda bytecode is not always a separate anonymous class file: on OpenJDK it typically involves `invokedynamic`.

### Generics and erasure

Consider the example:

~~~java
import java.util.List;

public class GenericDemo {
    public static int count(List<String> values) {
        return values.size();
    }

    public static void main(String[] args) {
        System.out.println(count(List.of("A", "B")));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericDemo.java
java GenericDemo
~~~

Stdout:

~~~text
2
~~~

In source code, the type `List<String>` lets the compiler check element constraints. In the method descriptor in the class file, the corresponding parameter has the form `java.util.List` after erasure; generic metadata may retain signature information for tools/reflection to query. **Do not** conclude that the JVM checks every element of `List` as a `String` because generics are visible in source; most Java generics are checked at compile time.

Inspect the class file with:

~~~bash
javap -p -s -v GenericDemo
~~~

Use the output to identify descriptors, the `Signature` attribute, and instructions. Detailed output may vary across JDK versions; do not write tests by comparing the entire `javap -v` text across JDKs.

## 8. Generate: Emitting Class Files and Bytecode

The code generation phase (commonly called `Gen`) produces one or more `.class` files with the structure specified by the Java Virtual Machine Specification. In addition to method instructions, a class file may contain the constant pool, field/method descriptions, descriptors, access flags, `Code` attribute, exception table, line numbers, generic signatures, annotation metadata, and other information.

Complete example — file `Hello.java`:

~~~java
public class Hello {
    public static void main(String[] args) {
        int x = 20;
        int y = 22;
        System.out.println("Result: " + (x + y));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 Hello.java
java Hello
~~~

Exact stdout:

~~~text
Result: 42
~~~

After successful compilation, `Hello.class` is produced. You can view the bytecode with:

~~~bash
javap -c -p Hello
~~~

`javap` helps show constant-loading operations, method calls, control flow, and generated instructions; it **does not execute** the method. The compiler is allowed to optimize or re-express certain expressions according to Java semantics and the target version, so the specific bytecode contents do not necessarily match a hand-written instruction illustration.

If class files are needed in a separate directory:

~~~bash
mkdir out
javac --release 17 -d out Hello.java
java -cp out Hello
javap -classpath out -c Hello
~~~

Note that `out` must exist before using it as the `-d` directory in the example. A source file with multiple top-level or nested types can produce **multiple** `.class` files. If there are compilation errors, do not assume every class file of the invocation was created or is the latest version: check the exit code and handle stale output files carefully.

### Why can the same source code produce different class files?

Influencing factors include the `javac` version, target/release, debug options, annotation processing, compiler implementation, and changes in dependent sources. You should not rely on strict byte-for-byte identity across JDKs to prove two programs have the same semantics.

Debug information such as line numbers or local variable metadata depends on `-g` options and compiler configuration; changing metadata does not necessarily change the computational behavior of the program.

## 9. Placing Examples Alongside Phases: Where Are Errors Detected?

The following three illustrative snippets describe **error categories**, without guaranteeing that a diagnostic always appears in a single internal pass.

| Code or situation | Related work area | Why it fails |
| --- | --- | --- |
| Missing `;` / missing `}` | Lexing / parsing | Tokens cannot form a valid syntactic structure |
| `MissingType value;` when `MissingType` has no declaration | Enter / name resolution / attribution | Compiler cannot resolve the type name |
| `int x = "abc";` | Attribution / type checking | Incompatible type assignment |
| Using a local variable not guaranteed to be assigned | Flow analysis | Violates definite assignment |
| Accessing `private` from an invalid context | Semantic checks | Violates access control |
| `-proc:only` while expecting `Hello.class` | Processing/output mode | Requested command does not generate normal bytecode |
| Compiles, fails at runtime with `NoClassDefFoundError` | Runtime class loading/linking | Required class is missing at runtime or cannot be loaded |

A diagnostic message typically includes **file location, line, column, error code, and description**; an error in an early phase can restrict subsequent analysis or trigger secondary errors. Therefore, when encountering multiple diagnostics, fixing the first error with a clear cause and recompiling often eliminates cascading errors.

There is no strict separation of "an error from phase X can only appear in phase X" in the public API. For example, name resolution may involve enter, attribution, and loading symbols from the classpath, so the table is a learning map, not a detailed implementation contract.

## 10. How to Observe the Compiler Instead of Guessing the Pipeline

### 10.1. Using public options of javac

For `Hello.java` in section 8:

~~~bash
javac -version
javac --release 17 -Xlint:all -d out Hello.java
javac -verbose --release 17 -d out Hello.java
~~~

- `-Xlint:all` enables warnings in the lint categories supported by `javac`; it does not turn the compiler into a phase-by-phase explainer.
- `-verbose` displays additional information such as the compiler reading sources, loading classes, and writing output. The log lines and order may change across JDKs; do **not** treat them as a complete trace of parse/enter/attr/flow/lower.
- `javac -X` shows the extended options supported by the current `javac` version. Internal flags `-XD...` are subject to change and should not be considered a stable public contract.
- Use `-Xdiags:verbose` (if supported) when more detailed diagnostic context is needed; this does not fix errors by itself.

If you need to observe annotation processing, configure a real processor and then add:

~~~bash
javac -XprintRounds -XprintProcessorInfo -processor com.example.MyProcessor -processorpath processor-classes -d out App.java
~~~

This is a **command configuration template** that only runs when the processor class `com.example.MyProcessor` has been compiled and is present in `processor-classes`, `App.java` exists, and all dependencies are complete. Logging options do not create processors on their own.

### 10.2. Java Compiler Tree API and TaskListener

The JDK provides the `jdk.compiler` module with APIs such as `com.sun.source.util.JavacTask`, `TaskEvent`, and `TaskListener` for tools to monitor high-level events. `TaskEvent.Kind` includes `PARSE`, `ENTER`, `ANALYZE`, `GENERATE`, `ANNOTATION_PROCESSING`, `ANNOTATION_PROCESSING_ROUND`, and `COMPILATION`.

**Events do not have a one-to-one mapping to all internal passes.** In particular, there is no requirement that each class must produce exactly one event for every step name such as `Attr`, `Flow`, or `Lower`. Use events to understand the process at the supported API level; do not infer a fixed ordering of every method inside the compiler.

Java 17+ tool example for tracing a compilation — file `TraceCompiler.java`:

~~~java
import com.sun.source.util.JavacTask;
import com.sun.source.util.TaskEvent;
import com.sun.source.util.TaskListener;
import java.io.IOException;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class TraceCompiler {
    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Can JDK compiler de chay vi du");
        }

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(null, null, null)) {
            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjects("Hello.java");

            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, null,
                    List.of("--release", "17", "-proc:none"),
                    null, units);

            task.setTaskListener(new TaskListener() {
                @Override
                public void started(TaskEvent event) {
                    System.out.println("START " + event.getKind());
                }

                @Override
                public void finished(TaskEvent event) {
                    System.out.println("END   " + event.getKind());
                }
            });

            boolean success = task.call();
            System.out.println("SUCCESS " + success);
        }
    }
}
~~~

Place `TraceCompiler.java` in the same directory as `Hello.java` from section 8 and run with JDK 17+:

~~~bash
javac TraceCompiler.java
java TraceCompiler
~~~

With valid `Hello.java` source and a working compiler, the last line is:

~~~text
SUCCESS true
~~~

The `START ...` / `END ...` lines above reflect actual events and may have multiple events or differ in detailed ordering across versions; therefore a hardcoded transcript is not printed to avoid misleading learners. The example sets `-proc:none` to isolate the compilation step from implicitly installed processors in the environment. The `JavacTask` class belongs to the API for tools built on `javac`; it differs from internal implementation classes in `com.sun.tools.javac.*`.

**Important note:** the `task.call()` method triggers compilation; the listener only observes events. It is not a bytecode verifier or performance profiler. Build tools/IDEs may use the Java Compiler API in their own ways.

## 11. Things Commonly Mistaken for javac Phases

**Class loading and verification.** Bytecode generated by `javac` will be loaded and verified by the JVM according to JVM rules at runtime. `ClassNotFoundException` or `NoClassDefFoundError` at runtime usually relates to the classpath/class loader or linking, even though compilation succeeded beforehand.

**JIT.** The Just-In-Time compiler translates/lowers code at runtime to optimize on the target JVM, unlike the source compiler `javac`. `javac` does not need to run the program to produce `.class` files.

**Gradle/Maven incremental compilation.** Build tools decide which tasks to run, where to obtain sources/dependencies, and may skip a `javac` pass if nothing changed. This is a build orchestration layer **outside** the compiler's semantic pipeline. `javac` is not synonymous with an entire Gradle build.

**Packaging and deployment.** Commands to create JARs, package applications, build containers, sign artifacts, and release are separate steps. A valid class file does not guarantee the application has all dependencies needed to run.

**Runtime annotations.** Annotations with retention policy `RUNTIME` can be read via reflection; that is independent of whether there is a processor at compile time. An annotation may go unprocessed yet still exist in runtime metadata, depending on its retention.

## 12. Symptom-Based Diagnosis

| Symptom | What to check first |
| --- | --- |
| `';' expected`, `illegal start of expression` | Tokens, separators, statement structure; parsing |
| `cannot find symbol` | Spelling, imports, packages, sources, dependencies, module visibility |
| `incompatible types` | Types on both sides, generics, overloads, conversions, target type |
| `variable ... might not have been initialized` | All variable assignment branches, definite assignment |
| Processor does not generate sources | Processor configuration, module/classpath, processing options, round logs |
| Generated `.java` files seen, but no `.class` files | Whether `-proc:only` is used, whether compilation errors remain, where `-d` points |
| Class file has unexpected older/newer format | Actual JDK, `--release`/`-target`, stale output files |
| Compiles successfully, but fails on `java` | Runtime classpath/module path, main class, and dependencies |

A short diagnostic workflow:

1. Print `javac -version` and retain the **entire command** along with the working directory.
2. Recompile under controlled conditions, tracking the exit code and the first diagnostic.
3. If annotation processing is suspected, verify that the processor is actually enabled and add `-XprintRounds`.
4. If it is an output issue, verify `-d` and newly created class files; use `javap` to inspect descriptors/bytecode when appropriate.
5. If the error only occurs at runtime, check the JVM and runtime classpath; do not keep trying to fix the "parse phase" of code that already compiled properly.

## 13. Check Your Understanding

**Question 1.** Does `int n = "abc";` fail at parse or semantic analysis?  
**Answer:** The syntactic structure is valid; the error is in type checking.

**Question 2.** Why can a processor cause the compiler to read additional `.java` files in the same invocation?  
**Answer:** The processor generates sources using the annotation processing mechanism; the new sources participate in subsequent rounds and the compilation process when configured.

**Question 3.** Can `-verbose` alone be used to obtain an exact timeline of every internal pass?  
**Answer:** No. Verbose logs are not a contract for tracing all passes; use TaskListener if high-level events are needed, or tools meant specifically for internal observation with awareness of the JDK version.

**Question 4.** Why does `List<String>` in source not necessarily produce a specialized JVM type exclusively for String?  
**Answer:** Java generics are primarily based on erasure. The compiler checks generic types and generates corresponding descriptors/metadata; the JVM does not create a new `List<String>` class for each type argument.

**Question 5.** Does running `javac -proc:only` and not seeing `Hello.class` prove that the compiler failed?  
**Answer:** No. `-proc:only` requests annotation processing without proceeding to normal bytecode generation.

**Question 6.** If `java Hello` reports class not found even though `javac` succeeded, which phase is the compiler in?  
**Answer:** The compilation pass has already finished. That is an issue when the JVM starts up, finds/loads classes, or links dependencies; check the runtime classpath/module path.

## 14. Key Takeaways and Reference Documentation

- **Parse** checks syntactic structure and builds the AST; **Enter** records declaration/symbol information; **Analyze** resolves names, checks types and flow; **Lower/Generate** prepares and emits bytecode.
- **Annotation processing** only participates when properly configured/enabled; there can be multiple rounds and generated sources.
- OpenJDK `javac` phases describe one implementation; **TaskEvent.Kind** represents API-supported events, not an exhaustive list of internal functions/passes.
- `javac` creates class files; **JVM/JIT/Gradle/Maven** are separate work layers to distinguish when finding error causes.
- Use diagnostics, `-Xlint`, `-verbose`, `-XprintRounds`, `javap`, and when needed `TaskListener` to observe real results rather than guessing from a diagram.

Official documentation to cross-reference by version: [The javac Command (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), [TaskEvent.Kind (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TaskEvent.Kind.html), [Processor (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html).