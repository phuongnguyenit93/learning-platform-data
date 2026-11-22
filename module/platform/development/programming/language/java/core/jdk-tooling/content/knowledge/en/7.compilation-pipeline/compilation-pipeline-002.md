# Source Parsing in Java

## 1. What is source parsing?

**Source parsing** is the syntactic analysis phase of source code. After reading the text and recognizing tokens, the compiler checks how the tokens combine according to the Java language grammar, and then builds a structure representing the program.

For example:

~~~java
int total = price + tax;
~~~

The parser must recognize this as a local variable declaration consisting of the `int` type, the name `total`, an assignment operator, an addition expression, and a semicolon terminating the statement. The parser must also determine the boundaries of the expression and the statement according to the Java grammar.

The parsing phase answers the question: **do the tokens form a valid Java structure, and what components does that structure consist of?**

Source parsing is one step in the compilation pipeline:

~~~text
Java source (.java)
        |
        v
Lexical analysis / scanning
        |
        v
Tokens
        |
        v
Parsing
        |
        v
Abstract Syntax Tree (AST)
        |
        v
Symbol entry, annotation processing,
semantic analysis and flow checks
        |
        v
Desugaring and bytecode generation
        |
        v
.class files
~~~

This is a high-level model for understanding the compilation flow. Internal details and the ordering of certain tasks may vary by compiler, but it is important to maintain a clear boundary between token recognition, syntactic analysis, semantic checking, and bytecode generation.

## 2. From source text to tokens

Before the parser analyzes structure, the compiler must recognize the lexical units in the source. This phase is commonly called lexical analysis, scanning, or lexing.

For the code snippet:

~~~java
int count = 10 + 20;
~~~

A high-level token sequence is:

| Text | Token type |
|---|---|
| int | Keyword / primitive type keyword |
| count | Identifier |
| = | Assignment operator |
| 10 | Integer literal |
| + | Additive operator |
| 20 | Integer literal |
| ; | Semicolon / separator |

Whitespace and comments make source code easier to read, but typically do not become independent syntax nodes in the AST. However, compilers and analysis tools can still store source positions to report errors, support IDE navigation, or link nodes back to the original text.

It is important to distinguish tokens from syntax. The `+` token by itself is just an operator. It is the parser that determines which expression it belongs to, what its left and right operands are, and which statement that expression resides in.

For example, the following two snippets can produce an equivalent expression structure despite different formatting:

~~~java
int result = a + b * c;
~~~

~~~java
int result=a+b*c;
~~~

The parser relies on the grammar and operator precedence to understand that multiplication is grouped before addition. Whitespace does not determine the evaluation order of an expression.

## 3. Grammar determines valid structure

The Java Language Specification defines the language grammar. The parser uses these syntactic rules to recognize compilation units, package declarations, imports, classes, interfaces, methods, fields, statements, expressions, and other constructs.

Some examples of the relationship between tokens and grammar:

- A **compilation unit** may contain a package declaration, import declarations, and top-level type declarations.
- A **class declaration** has modifiers, a class name, an optional type parameter declaration, superclass/interfaces, and a class body.
- A **method declaration** has modifiers, a return type, a name, a parameter list, and a method body or a semicolon where applicable.
- A **statement** can be a block, local variable declaration, expression, `if`, `for`, `while`, `return`, `throw`, `try`, and other control structures.
- An **expression** can consist of literals, variable names, method invocations, field accesses, operators, object creations, lambdas, or conditional expressions.

The parser must apply precedence and associativity to group expressions accurately. For example:

~~~java
int value = a + b * c;
~~~

The structure is interpreted equivalently to:

~~~java
int value = a + (b * c);
~~~

And parentheses can change the grouping:

~~~java
int value = (a + b) * c;
~~~

Syntax can be valid even when the program does not yet make sense in terms of types or symbols. Checking those belongs to later stages.

## 4. Abstract Syntax Tree (AST)

After syntactic analysis, the compiler represents the source using an abstract syntax tree, called an **Abstract Syntax Tree (AST)**. Each node represents a syntactically meaningful component such as a compilation unit, class, method, variable, statement, expression, or type.

For example:

~~~java
int total = price + tax;
~~~

The AST can be visualized at a high level as follows:

~~~text
VariableDeclaration
├── Type: int
├── Name: total
└── Initializer: Addition
    ├── Identifier: price
    └── Identifier: tax
~~~

An AST is not simply a character-by-character copy of the file. It organizes the source by syntactic relationships and typically omits presentation details such as whitespace, newlines, and comments. Therefore, an AST is useful for compilers and tools that need to understand program structure.

Common nodes in a Java tree:

| Source element | Typical AST node |
|---|---|
| package demo; | Package declaration / package name |
| import java.util.List; | Import tree |
| class User { ... } | Class tree |
| int age; | Variable tree |
| void run() { ... } | Method tree |
| if (ready) { ... } | If statement tree |
| a + b | Binary expression tree |
| new User() | New class expression tree |
| return value; | Return statement tree |

An AST can be traversed to find all methods, count method invocations, locate literals, check code patterns, or build static analysis tools. IDEs also use syntactic structure to provide navigation, completion, refactoring, and error highlighting.

A compiler's AST does not necessarily preserve full original formatting. If you need to modify source while preserving comments, whitespace, and style, you need additional source position information or a parser capable of retaining concrete syntax/trivia. You should not assume that converting an AST back to source will reproduce the original file verbatim.

## 5. Parse errors vs. semantic errors

A syntax error occurs when tokens cannot be organized into a structure conforming to the grammar.

Example of a syntax error:

~~~java
class Example {
    void run() {
        int total = ;
    }
}
~~~

After the assignment operator, the parser expects an initializer expression but encounters a semicolon. The compiler may report the error at that position or at a related token, depending on how the parser detects errors and its recovery mechanism.

Another program may be syntactically valid yet have a type error:

~~~java
class Example {
    void run() {
        int total = "hello";
    }
}
~~~

The declaration, assignment, and literal are all organized into a valid Java structure. However, a string cannot be assigned to an `int` variable; this error is detected during semantic analysis/type checking, after the parser has built the syntactic structure.

Another example:

~~~java
class Example {
    void run() {
        UnknownType value;
    }
}
~~~

The variable declaration syntax can be parsed successfully, but the compiler cannot find the `UnknownType` type when performing symbol and type resolution steps.

| Error type | Example | Phase typically detected |
|---|---|---|
| Syntax error | Missing `;`, missing `)`, invalid block structure | Parsing |
| Unknown symbol/type | Using an undeclared class or variable | Symbol resolution / semantic analysis |
| Type mismatch | Assigning `String` to `int` | Type checking |
| Definite assignment / flow error | Reading a local variable that may not have been assigned | Flow analysis |
| Runtime exception | Dividing an integer by 0 at runtime | Runtime |

The boundaries above are a classification for learning and diagnosis. A specific diagnostic is sometimes detected in a dependent step or at a different stage of the compiler; read the error message and location rather than relying solely on the phase name.

## 6. How does the parser handle errors?

When encountering invalid syntax, the parser typically generates a diagnostic containing information such as:

- Source file name.
- Line and column where the error occurred.
- Relevant source position or snippet.
- Diagnostic kind, for example `ERROR` or `WARNING`.
- A message explaining the structure the compiler expected or the offending token.

The compiler may attempt to recover from an error to continue analyzing and report additional errors. For example, the parser may skip a token or resynchronize at a `;`, a `}`, or the start of the next construct. Because of this, a syntactically invalid file can produce multiple diagnostics; subsequent errors are sometimes just consequences of the first error.

When fixing errors, you should address the first diagnostic with a reliable location and then recompile. A single missing brace above can cause the parser to misinterpret many lines below.

Diagnostics do not always point to the exact character that needs to be inserted. The reported location is usually where the compiler realized the token sequence no longer conforms to the grammar. The offending token may appear after the point where the error actually began.

## 7. Observing the parse phase with javac

**javac** is the Java compiler included with the JDK. When running a normal `javac` command, the compiler performs multiple steps of the compilation pipeline, including parsing, resolution, and checking, then generates bytecode if no blocking errors occur.

Basic command:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/Greeting.java
~~~

Meaning:

- **--release 17:** compile against Java 17 APIs and bytecode.
- **-encoding UTF-8:** specify the encoding of the source file.
- **-d out:** place generated `.class` files in the `out` directory.
- **src/demo/Greeting.java:** source file to compile.

The command above is a complete compilation, not a parser-only command. If you want to observe only the post-parse AST in a Java tool, you can use the Compiler Tree API.

You should not rely on internal classes such as `com.sun.tools.javac.parser.Parser` for building long-term tools. These internal classes are implementation details, can change across JDK versions, and are generally not guaranteed stable APIs.

## 8. Using JavacTask.parse() to parse source without semantic analysis

The JDK provides the Java Compiler API and Compiler Tree API in the **jdk.compiler** module. **JavacTask.parse()** lets you ask the compiler to parse source and return **CompilationUnitTree** instances.

Key points:

- **parse()** builds the syntactic structure and emits syntax diagnostics.
- **analyze()** instructs the compiler to perform semantic analysis steps such as resolution and type checking.
- **generate()** requests class file generation.
- Calling only `parse()` lets a tool observe syntax without proactively requesting the `analyze`/`generate` steps.

The complete example below feeds in-memory source, parses it, and prints compilation unit information:

~~~java
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.JavacTask;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;
import java.net.URI;
import java.util.List;

public class ParseSourceDemo {

    private static final class SourceFile extends SimpleJavaFileObject {
        private final String content;

        private SourceFile(String className, String content) {
            super(
                    URI.create("string:///"
                            + className.replace('.', '/')
                            + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE
            );
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A full JDK with jdk.compiler is required.");
        }

        String source = """
                package demo;

                import java.util.List;

                class Greeting {
                    String message() {
                        return "hello";
                    }
                }
                """;

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        JavaFileObject sourceFile = new SourceFile("demo.Greeting", source);

        JavacTask task = (JavacTask) compiler.getTask(
                null,
                null,
                diagnostics,
                List.of("--release", "17", "-proc:none"),
                null,
                List.of(sourceFile)
        );

        int compilationUnitCount = 0;

        for (CompilationUnitTree unit : task.parse()) {
            compilationUnitCount++;

            String packageName = unit.getPackageName() == null
                    ? "<default>"
                    : unit.getPackageName().toString();

            System.out.println("Package: " + packageName);
            System.out.println("Imports: " + unit.getImports().size());

            for (Tree declaration : unit.getTypeDecls()) {
                if (declaration instanceof ClassTree type) {
                    System.out.println(
                            "Top-level type: " + type.getSimpleName());
                }
            }
        }

        long syntaxErrors = diagnostics.getDiagnostics().stream()
                .filter(diagnostic ->
                        diagnostic.getKind() == Diagnostic.Kind.ERROR)
                .count();

        System.out.println("Compilation units: " + compilationUnitCount);
        System.out.println("Syntax errors: " + syntaxErrors);
    }
}
~~~

Save it as **ParseSourceDemo.java**, then compile and run with JDK 17 or later:

~~~bash
javac --release 17 ParseSourceDemo.java
java ParseSourceDemo
~~~

Output:

~~~text
Package: demo
Imports: 1
Top-level type: Greeting
Compilation units: 1
Syntax errors: 0
~~~

The program creates a `JavaFileObject` from an in-memory source string, passes that file to the compiler, and calls `JavacTask.parse()`. It iterates over each compilation unit and reads the package name, import list, and top-level types.

The example does not call `task.analyze()` or `task.generate()`. Thus, the program only demonstrates parsing and checking syntax diagnostics. The `import java.util.List` in the sample source does not require type resolution at this step; checking whether the import exists and is used properly belongs to a later analysis phase.

`ToolProvider.getSystemJavaCompiler()` requires the JDK's compiler. If the program runs in a runtime image that stripped the compiler module or in a runtime-only environment, the result may be `null`. Source-parsing tools should therefore run in an environment that includes `jdk.compiler`.

## 9. Traversing the AST with the Compiler Tree API

Nodes in the AST are represented by interfaces in the `com.sun.source.tree` package. For example:

- **CompilationUnitTree:** a parsed source file.
- **ClassTree:** a class, interface, enum, or record declaration.
- **MethodTree:** a method or constructor declaration.
- **VariableTree:** a variable, field, or parameter declaration.
- **BlockTree:** a block of statements.
- **IfTree:** a conditional statement.
- **MethodInvocationTree:** a method call.
- **BinaryTree:** a binary operator expression.
- **LiteralTree:** a literal such as a number, string, boolean, or `null`.

To traverse multiple node types, use **TreeScanner**. Here is an example illustrating how to count method declarations in a parsed compilation unit:

~~~java
import com.sun.source.tree.MethodTree;
import com.sun.source.util.TreeScanner;

class MethodCounter extends TreeScanner<Integer, Void> {

    @Override
    public Integer visitMethod(MethodTree node, Void unused) {
        Integer nested = super.visitMethod(node, unused);
        return 1 + (nested == null ? 0 : nested);
    }

    @Override
    public Integer reduce(Integer left, Integer right) {
        if (left == null) {
            return right;
        }
        if (right == null) {
            return left;
        }
        return left + right;
    }
}
~~~

This is an illustrative class, not a standalone program. Once you have a **CompilationUnitTree unit**, you can use:

~~~java
int methodCount = new MethodCounter().scan(unit, null);
~~~

`TreeScanner` automatically traverses child nodes. Each time a method is encountered, `visitMethod` adds one and continues traversing the elements inside the method. Depending on your goal, you can override other visitor methods to find fields, method invocations, literals, or control structures.

If you need the source position of a node, you can use **Trees.instance(task)** and **SourcePositions** in the Compiler Tree API. These positions are useful when building diagnostics, analysis reports, or linking results to an editor. Keep in mind that positions are calculated relative to the source file and the compiler's coordinate system; tools should use the position API rather than guessing from formatted strings.

## 10. When should you parse source with the javac API?

Source parsing is useful for tools that work directly with Java structure:

- **Static analysis:** finding code patterns, checking conventions, or detecting notable constructs.
- **Source inspection:** listing packages, classes, methods, fields, and annotations.
- **Code metrics:** counting methods, statements, or syntactic constructs.
- **Refactoring tools:** identifying nodes and source positions before making changes.
- **Documentation tools:** extracting declarations and source structure to generate reports.
- **Build tooling:** checking or analyzing source during the build process.
- **IDE tooling:** supporting navigation, symbol search, completion, and error display.

If you only need to compile an application, use `javac` or a build tool like Gradle/Maven. There is no need to write a custom parser for ordinary Java compilation.

If you need full analysis of types, method overloads, generics, annotation processing, or symbol relationships, parsing alone is not enough. You will need the appropriate `analyze` steps and must manage the classpath/module path so the compiler can find dependencies. Tools must also consider that annotation processors can execute code during compilation; untrusted annotation processing should not be enabled in a secure source analysis tool.

## 11. Common errors when working with source parsing

| Symptom | Possible cause | Resolution |
|---|---|---|
| Parser reports an error at `;` | The preceding expression or construct is incomplete. | Check the token immediately before the reported error position. |
| Multiple errors appear after a brace error | The parser is recovering from a malformed block structure. | Fix the first error and re-parse. |
| Source is syntactically valid but `javac` still fails | The error is in symbol resolution, type checking, flow, or a later phase. | Read the diagnostic kind and distinguish parsing from analysis. |
| Compiler cannot find a system compiler | Running on a runtime lacking `jdk.compiler` or without a system compiler. | Run the tool with a full JDK that includes the compiler module. |
| AST is missing comments or formatting | The AST focuses on syntactic structure, not a lossless copy of the source. | Store source positions or choose a parser that preserves trivia if needed. |
| Source parses cleanly but tool fails during analysis | Classpath, module path, release, or dependencies are incorrect. | Configure the compiler environment and corresponding dependencies. |
| Vietnamese source or Unicode characters are corrupted | Reading the file with the wrong encoding. | Specify the appropriate encoding, such as UTF-8, when reading source. |
| Using internal `javac` classes breaks after upgrading JDK | Depending on implementation details with no compatibility guarantee. | Prefer the public Java Compiler API and Compiler Tree API. |

A useful diagnostic principle is to identify which step the compiler stopped at. Syntax errors require fixing the source grammar; symbol/type errors require checking dependencies and semantics; bytecode generation or runtime errors require examining later steps.

## 12. Checklist for analyzing Java source

- [ ] Distinguished between source text, tokens, and AST.
- [ ] Understood that the parser checks grammar and builds the syntactic structure.
- [ ] Distinguished syntax errors from symbol/type/flow errors.
- [ ] Understood that the parser can recover and emit multiple diagnostics.
- [ ] Learned that a compilation unit contains package, imports, and type declarations.
- [ ] Used public APIs when programmatic source parsing is needed.
- [ ] Distinguished `JavacTask.parse()`, `analyze()`, and `generate()`.
- [ ] Configured the appropriate JDK/compiler module, release, and encoding.
- [ ] Used an AST visitor/scanner instead of regex to parse complex Java structures.
- [ ] Considered source positions, comments, and formatting if the tool needs to edit or re-render source.

Source parsing transforms Java text into a structure that compilers and tools can understand. Once you have a solid grasp of tokens, grammar, the AST, and the boundary with semantic analysis, reading diagnostics, building source analysis tools, and handling compilation errors becomes much more accurate.