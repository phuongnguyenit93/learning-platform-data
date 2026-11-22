# Limitations of a Newly Parsed Syntax Tree and Risks of Depending on javac Internal APIs

A Java program goes through many different tasks during compilation: reading tokens, building a syntax tree (*parse*), recording declarations, resolving names, type checking, control-flow analysis, and finally generating bytecode. **A syntax tree immediately after `parse()` only tells how the program is written structurally; it is not yet a certificate that the program is semantically valid.**

This is especially important for source-code analysis tools: IDEs, linters, refactoring tools, code generators, or compiler plugins. If a tool sees an `IdentifierTree` named `value` and immediately concludes which field it is, what type it has, or which overload call it represents, the tool has gone beyond what the parse phase guarantees.

Another risk is relying directly on implementation classes such as `com.sun.tools.javac.tree.JCTree`, `com.sun.tools.javac.code.Symbol`, `com.sun.tools.javac.comp.Attr`, or `com.sun.tools.javac.util.Context`. They are convenient for studying internals of a particular OpenJDK build, yet **are not a stable application API contract**. JDK changes, module encapsulation, or how the compiler manipulates trees can break plugins.

This lesson clearly distinguishes *syntax* from *semantics*, demonstrates the two phases `JavacTask.parse()`/`analyze()` using Java 17+, introduces the published APIs in `com.sun.source.tree`/`com.sun.source.util`, and shows how to avoid locking tools to internals.

## 1. From Source Code to AST: What Does parse Actually Do?

Consider syntactically valid source:

```java
package sample;

public class Demo {
    public int twice(int number) {
        return number * 2;
    }
}
```

The parser can recognize structures such as:

- A `CompilationUnitTree` with package declaration `sample`.
- A `ClassTree` named `Demo`.
- A `MethodTree` named `twice` with the return type written in source as `int`.
- A parameter `VariableTree` named `number`.
- A `ReturnTree` containing a `BinaryTree` representing multiplication.
- Two operands, where the name `number` is represented by the appropriate syntax node.

Conceptual diagram example:

```text
CompilationUnitTree
└── ClassTree: Demo
    └── MethodTree: twice
        ├── return type syntax: int
        ├── parameter syntax: int number
        └── ReturnTree
            └── BinaryTree: MULTIPLY
                ├── IdentifierTree: number
                └── LiteralTree: 2
```

At this point, the tree describes the **recognized syntax**, without automatically providing sufficient information to confirm:

- Which `VariableElement` the `number` reference is bound to.
- The type of every expression when considering generic inference, boxing, numeric promotion, and overloads.
- Whether an imported type name exists on the classpath/module path.
- Whether `private`, `protected` access rights, module readability, or exports are valid.
- Whether all paths return, variables are assigned before reading, and exceptions are handled.
- Whether a method reference/lambda has a compatible target functional interface.

Post-parse steps are needed to answer those questions. The parser is not a complete type checker.

## 2. "Having an AST" Does Not Equal "Compiled Successfully"

The following snippet is **syntactically valid yet semantically invalid**:

```java
class InvalidExample {
    MissingType field;
}
```

The parser can still construct a `ClassTree` and `VariableTree` for `field` with a type node written as `MissingType`. Yet the name-resolution step cannot find `MissingType`, and the compiler reports an error.

Similarly:

```java
class WrongAssignment {
    int value = "abc";
}
```

The parser recognizes an `int value` variable and a string literal. Only during type checking is it detected that `String` cannot be assigned to `int`.

Therefore, if a tool only runs `parse()` and prints "valid source", accurate wording must be "the parser read the syntactic structure at an analyzable level". Do not say "type-safe code", "compile pass", or "runnable".

Conversely, with syntactically invalid source, an IDE/compiler parser may create an **error recovery tree**. The API has `ErroneousTree` and `Tree.Kind.ERRONEOUS` to represent erroneous portions. Do not assume that merely having a `CompilationUnitTree` means there are zero syntax errors; diagnostics must be read.

## 3. Which Information Belongs to the Semantic Phase?

| Question | Is parse tree alone enough? | Phase/Mechanism Usually Needed |
| --- | --- | --- |
| Does the source declare a class named `Demo`? | Yes, for properly parsed source | AST/`ClassTree` |
| What is the method name written in source? | Yes | `MethodTree` |
| Which operator does an expression use? | Yes | `BinaryTree` and `Tree.Kind` |
| Is `List` here `java.util.List` or another class of the same name? | Not yet | Imports, symbol resolution |
| Is `value` a local variable, field, parameter, or non-existent name? | Not yet | Scope, enter/resolve/attribution |
| Which overload does `add(3)` select? | Not yet | Overload resolution and conversions |
| What type does `x + y` have? | Not enough in the general case | Type attribution |
| Is `return "x"` valid inside a method returning `int`? | Not yet | Type checking |
| What type is inferred for `var item = factory()`? | Not yet | Type inference and target typing |
| Which target is lambda `x -> x.length()` valid for? | Not yet | Target functional interface |
| Might a method be missing a return or have variables without definite assignment? | Not yet | Control/data-flow checking |
| Will bytecode be generated successfully for a class? | Not yet | Semantic/flow/generation steps |
| Which `Element` is an identifier bound to? | Not guaranteed right after parse | `Trees.getElement` after the appropriate analysis phase |

An AST can contain a `MethodInvocationTree` and method name, yet **does not mean** it already knows the exact `ExecutableElement` the compiler will select. If a class has overloads, inheritance, or generic methods, you must not resolve calls yourself by comparing string names.

### Example of Identical Syntax Yet Different Semantics

```java
void use(String x) {}
void use(Object x) {}

void caller() {
    use("hi");
}
```

This is a snippet inside a class, not a standalone Java file. The AST represents one call `use("hi")`; after overload resolution, the compiler chooses `use(String)`. Looking only at the name `use` when two declarations exist, you cannot choose by a "whichever method was written first" rule.

## 4. Public JDK APIs for Tree Analysis

Packages to prefer for `javac`-based tools:

- `com.sun.source.tree`: set of **AST interfaces** such as `Tree`, `CompilationUnitTree`, `ClassTree`, `MethodTree`, `IdentifierTree`, `BinaryTree`, `ErroneousTree`.
- `com.sun.source.util`: `JavacTask`, `TreeScanner`, `TreePathScanner`, `TreePath`, `Trees`, and utilities linking ASTs with semantics.
- `javax.tools`: `JavaCompiler`, `ToolProvider`, `JavaFileObject`, `DiagnosticCollector`, `StandardJavaFileManager`.
- `javax.lang.model.element` and `javax.lang.model.type`: abstract types `Element`/`TypeMirror` for working with declarations and types once semantics are available.

**Distinguishing the `com.sun` prefix:** `com.sun.source.tree` and `com.sun.source.util` are the **documented Tree APIs of the JDK** in module `jdk.compiler`. They are unlike `com.sun.tools.javac.*` classes belonging to the internal implementation. Nevertheless, `com.sun.source.*` is tied to JDK compiler capabilities, not a promise that every third-party Java compiler supports the exact same integration mechanism as `javac`.

For needs that only compile files and read errors, `javax.tools` from the standard Java Compiler API is usually sufficient; use the Tree API only when you truly need to traverse syntax. If exact elements/types are needed, combine the Tree API with `javax.lang.model` instead of downcasting to internal `Symbol`.

## 5. Complete Java 17+ Example: Parse First, Analyze Later

This example was compiled/run standalone with JDK 21 targeting Java 17. It creates Java source **in memory**, parses the AST, and then calls analyze to obtain the method's symbol.

Save as **`AstPhaseDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePath;
import com.sun.source.util.Trees;

public class AstPhaseDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String name, String code) {
            super(URI.create("string:///"
                    + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        DiagnosticCollector<JavaFileObject> ds =
                new DiagnosticCollector<>();

        String source = """
                package sample;
                public class Demo {
                    public int twice(int number) { return number * 2; }
                }
                """;

        try (StandardJavaFileManager fm =
                     compiler.getStandardFileManager(
                             ds, Locale.ROOT, StandardCharsets.UTF_8)) {

            JavacTask task = (JavacTask) compiler.getTask(
                    null, fm, ds,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(new Source("sample.Demo", source)));

            List<CompilationUnitTree> units = new ArrayList<>();
            for (CompilationUnitTree u : task.parse()) {
                units.add(u);
            }

            ClassTree clazz =
                    (ClassTree) units.get(0).getTypeDecls().get(0);
            MethodTree method = clazz.getMembers().stream()
                    .filter(m -> m instanceof MethodTree)
                    .map(m -> (MethodTree) m)
                    .filter(m -> m.getName().contentEquals("twice"))
                    .findFirst()
                    .orElseThrow();

            // Syntax information, obtained immediately after parse().
            System.out.println("parsedClass=" + clazz.getSimpleName());
            System.out.println("parsedMethod=" + method.getName());

            // Trigger semantic analysis.
            task.analyze();

            // Associate AST node with symbol resolved by the compiler.
            Trees trees = Trees.instance(task);
            TreePath path = TreePath.getPath(units.get(0), method);
            Element element = trees.getElement(path);

            System.out.println("resolvedKind=" + element.getKind());
            System.out.println("returnType="
                    + ((ExecutableElement) element).getReturnType());

            long errors = ds.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();
            System.out.println("errors=" + errors);
        }
    }
}
```

Compile/run from the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 AstPhaseDemo.java
java AstPhaseDemo
```

Exact stdout on JDK 21:

```text
parsedClass=Demo
parsedMethod=twice
resolvedKind=METHOD
returnType=int
errors=0
```

In this lab, `parse()` provides a `ClassTree` and `MethodTree` so we can read declaration names; **there is no need to dig into `JCTree`**. After `task.analyze()`, the example uses `Trees.getElement(TreePath)` to get the `Element` associated with the method and `ExecutableElement.getReturnType()` to get the return type.

`task.analyze()` performs semantic analysis for the task; the example does not call `generate()` and does not attempt to produce `.class` files. `-proc:none` disables annotation processing so results do not depend on processors incidentally present on search paths.

The example above knows beforehand that the input contains one valid top-level class with method `twice`. A general-purpose tool needs to check each node's type, handle possibly empty collections, check diagnostics, and handle multiple compilation units instead of casting `getTypeDecls().get(0)` blindly.

## 6. Second Example: Parse Succeeds Yet Analyze Detects Errors

To directly verify the difference, save the file **`AstErrorPhaseDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.JavacTask;

public class AstErrorPhaseDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source() {
            super(URI.create("string:///sample/Bad.java"), Kind.SOURCE);
            code = "package sample; public class Bad { MissingType field; }";
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        DiagnosticCollector<JavaFileObject> ds =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager fm =
                     compiler.getStandardFileManager(
                             ds, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavacTask task = (JavacTask) compiler.getTask(
                    null, fm, ds,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(new Source()));

            int units = 0;
            for (CompilationUnitTree unit : task.parse()) {
                units++;
            }
            System.out.println("parsedUnits=" + units);

            task.analyze();

            boolean semanticError = ds.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
            System.out.println("semanticError=" + semanticError);
        }
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 AstErrorPhaseDemo.java
java AstErrorPhaseDemo
```

Stdout verified on JDK 21:

```text
parsedUnits=1
semanticError=true
```

The `AstErrorPhaseDemo` program itself compiles successfully; **the in-memory `Bad` source** has a syntax tree yet the compiler cannot resolve the `MissingType` type. Diagnostic data is collected into `DiagnosticCollector` so there is no need to depend on exact message wording like `cannot find symbol`.

The code intentionally prints a **boolean indicating whether an error exists** rather than a fixed error count because each compiler and version may report varying semantic details. The stable conclusion here is: **an AST can exist alongside compilation errors**.

## 7. Why Should You Not Access Elements Too Early?

`Trees.getElement(TreePath)` is the bridge from syntax to **declaration elements**. Yet right after `parse()`, the compiler may not have fully entered symbols or performed attribution for the node.

Points to remember:

- `getElement(path)` may return **`null`** if the element is not available.
- For a path pointing to a node kind that cannot have a corresponding element, the API may throw **`IllegalArgumentException`**.
- `getTypeMirror(path)` can also return `null` or throw `IllegalArgumentException` if the path is inappropriate.
- With type-erroneous programs, you may encounter `ErrorType` or incomplete information; do not treat every `TypeMirror` as a `DeclaredType` that can be cast safely.
- `analyze()` helps the tool obtain semantic information in situations the compiler can analyze. It does not turn invalid source into valid source and does not guarantee every node has an `Element`/`TypeMirror`.

Therefore, an analysis tool must design two distinct operating modes: **syntax-only mode** for parsing trees and **semantic-aware mode** when symbols/types are needed. In semantic-aware mode, invoke the appropriate analysis step, read diagnostics, and check `null`/kind before deep access.

Avoid calling `getTypeMirror` on every node and assuming every node has a type. For example, a node representing a `return` statement, package element, or other syntactic construct does not always have a type mirror in the way a developer might expect.

## 8. Traversing Trees with TreePathScanner Instead of Probing Internal Fields

`TreeScanner<R,P>` allows traversing an AST; `TreePathScanner<R,P>` also maintains **the current path** to the node. This matters because `Trees.getElement` and `Trees.getTypeMirror` take a `TreePath`, not merely a standalone `Tree` node.

Example snippet used after `task.analyze()`:

```java
Trees trees = Trees.instance(task);

new TreePathScanner<Void, Void>() {
    @Override
    public Void visitIdentifier(
            com.sun.source.tree.IdentifierTree node, Void ignored) {

        TreePath path = getCurrentPath();
        Element symbol = trees.getElement(path);

        if (symbol != null) {
            System.out.println(node.getName()
                    + " -> " + symbol.getKind());
        }
        return super.visitIdentifier(node, ignored);
    }
}.scan(units.get(0), null);
```

This is a **snippet**, not a standalone file; it assumes `task`, `units`, and imports for `Trees`, `TreePathScanner`, `TreePath`, and `Element`. Do not treat the snippet's output as fixed stdout because identifier counts, synthetic nodes, and traversal order can vary by source/JDK.

Notes:

- An `IdentifierTree` represents a syntactic name; `Element` represents the resolved declaration.
- A `MemberSelectTree` like `System.out` is not necessarily a single `IdentifierTree`; visitors need to handle node kinds properly.
- `MethodInvocationTree` requires overload resolution in the semantic step; do not compare string names to guess declarations yourself.
- When the resolved method name is needed, you can obtain `Element` at the appropriate `TreePath` and check `ElementKind.METHOD`.
- `TreePathScanner` is useful for tools that want to report exact positions, yet still must check whether the source has errors.

If only syntactic statistics are needed (number of method declarations, number of `if`s, number of loops), `TreeScanner` or `TreePathScanner` after parse is usually enough. If you need "is this variable a field or a local?", you must cross the boundary into semantic-aware processing.

## 9. SourcePositions Do Not Turn an AST into Verbatim Source

`Trees.getSourcePositions()` helps obtain start/end offsets of a node in a compilation unit. `CompilationUnitTree.getLineMap()` can help convert offsets into line/column.

Conceptual example:

```java
var positions = trees.getSourcePositions();
long start = positions.getStartPosition(unit, node);
long end = positions.getEndPosition(unit, node);
```

This is a snippet with `unit` and `node` of types `CompilationUnitTree`/`Tree`. An unavailable position can be represented by a negative value/`Diagnostic.NOPOS`, so tools must check before slicing source strings.

Three layers must be separated:

1. **AST:** syntactic structures such as methods, expressions, and statements.
2. **Source text:** whitespace, line breaks, brackets, comments, and all characters the programmer wrote.
3. **Semantic model:** symbols, types, scopes, resolved overloads, and checking information.

An AST does not necessarily store every **comment** or source formatting detail. `DocTrees` has dedicated APIs for Javadoc; that does not mean arbitrary comments can all be preserved. If a formatter or refactoring tool wants to preserve trivia (comments/whitespace), it must retain original source text and design position-based edits, or use an appropriate source-preserving parser/tool.

Do not assume `tree.toString()` restores 100% of the original source bytes. `toString()` can produce a readable representation, yet is not a round-trip formatter contract.

## 10. ASTs Can Change as the Compiler Transitions Phases

As the compiler passes through enter, attribution, flow, and lowering, the implementation can add or transform internal structures to serve code generation.

Therefore, tools should not assume:

- A reference to `JCTree` or a node list stays immutable from parse to generate.
- All internal nodes already have `type` and `sym` right after parse.
- A node created in an earlier pass is guaranteed to remain with the same identity in a later pass.
- Every synthetic class/constructor/method appears in the AST like a user-written source line.
- `javac`'s internal node counts/kinds are identical across all JDKs.

The `com.sun.source.tree` interfaces help avoid manipulating many internal fields directly. Even so, a stateful analysis program should still manage the scope of `JavacTask` and `TreePath`, rather than keeping AST references as a permanent cache independent of source/compilation.

If you need to run multiple analysis passes for different versions of source, create a new compilation task for each pass and discard semantic caches tied to old tasks or maintain a clear invalidation mechanism.

## 11. Why Is com.sun.tools.javac.* Risky?

Classes such as:

- `com.sun.tools.javac.tree.JCTree`, `JCTree.JCMethodDecl`, `TreeMaker`;
- `com.sun.tools.javac.code.Symbol`, `Type`;
- `com.sun.tools.javac.comp.Enter`, `Attr`, `Resolve`;
- `com.sun.tools.javac.util.Context`, `Names`;
- other structures and visitors inside the `javac` implementation

can be very tempting because they allow reading or mutating fields directly. Yet these are **implementation details**, not stable APIs for applications. OpenJDK's `javac` documentation explicitly states that packages starting with `com.sun.tools.javac` outside specifically designated APIs are internal and subject to change at any time.

Typical consequences:

| Way of Depending | Risk |
| --- | --- |
| Casting `Tree` to `JCTree` | Not portable to other compilers; hits internal class/AST layout changes |
| Reading `JCExpression.type` or symbol fields before attribution | Value may be `null` or not yet carry the expected semantic meaning |
| Creating nodes with `TreeMaker` and inserting into compiler tree | Must re-establish owner/symbol/type/position; easily breaks compiler invariants |
| Calling `Enter`/`Attr`/`Resolve` directly | Depends on phase ordering, signatures, and internal `Context` state |
| Using reflection on private fields | Blocked by JPMS strong encapsulation; requires opening packages and still carries version risk |
| Using `--add-exports` as if it stabilizes the API | Only relaxes access permissions; does not preserve methods/fields/behavior after JDK upgrades |
| Caching symbols/types across compilation tasks | Symbols belong to a context/task and can become stale, leading to wrong resolution |
| Using internal exception/diagnostic text to identify errors | Messages/codes can change, and error paths are not designed as a protocol |

If a plugin truly needs to transform ASTs at the internal compiler layer, that is a **compiler-specific** engineering choice requiring testing against a JDK version matrix, compatibility management, and an upgrade plan. It should not be implicitly presented as part of the Java Language Specification.

## 12. JPMS: Having Access Does Not Mean the API Is Guaranteed

Since Java 9, module `jdk.compiler` encapsulates compiler packages. Tree API packages are exported according to the appropriate descriptor; many internal `com.sun.tools.javac.*` packages are not exported to applications by default.

An older tool depending on `JCTree` can hit module access errors at compile time or runtime. For migration purposes, you may encounter the flag:

```text
--add-exports jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED
```

This line **only illustrates the option** when an application running on the classpath needs access to public types in that internal package; it is not a standalone `javac`/`java` command. If deep reflection into non-public members is used, configuration may involve `--add-opens` at runtime.

The two flags have different meanings:

- `--add-exports`: extends export of a package to specified modules, allowing Java-semantics access to corresponding public types/members.
- `--add-opens`: opens a package for deep reflection to target modules under specified conditions.

**Neither guarantees source/binary compatibility** when internal classes or structures change. They also do not turn internal APIs into public supported APIs.

Prefer code that works without `--add-exports`/`--add-opens`, especially in tools shared across multiple JDKs. When an exception flag is mandatory, document supported versions clearly and apply only the minimal package/module scope.

## 13. Choosing the API Based on Actual Needs

| Goal | First-Choice Appropriate Option |
| --- | --- |
| Only compile files and receive errors | `javax.tools.JavaCompiler` + `DiagnosticCollector` |
| Count syntactic constructs | `JavacTask.parse()` + `TreeScanner`/`TreePathScanner` |
| Get class/method names as written in source | `ClassTree`/`MethodTree` |
| Know which declaration an identifier/method points to | `JavacTask.analyze()` + `Trees.getElement(TreePath)` |
| Know the type of an expression after analysis | `Trees.getTypeMirror(TreePath)` + `javax.lang.model.type` |
| Traverse declarations, generics, and member types | `javax.lang.model.element` + `TypeMirror`/`Elements`/`Types` |
| Write an annotation processor | `javax.annotation.processing`, `RoundEnvironment`, `Filer`, `Messager` |
| Read Javadoc as a tree | `DocTrees` and related doc-comment APIs |
| Need to preserve comments/whitespace when refactoring | Keep original source + source positions or a source-preserving library |
| Manipulate compiler internals directly | Only when strictly required, version-pinned, and rigorously tested |

There is no need to reach for internal `Symbol` just to get a method name, return type, or element kind. `ExecutableElement`, `TypeElement`, `VariableElement`, and `TypeMirror` usually satisfy these needs at the published API level.

## 14. Be Careful with Source Errors and Incomplete Semantic Data

A linter running on user source while typing in an IDE must tolerate **incomplete** code. What can happen:

- The compilation unit only partially parses or contains an `ErroneousTree`.
- An unfinished import leaves a symbol unresolved.
- An expression lacks sufficient context for inference to derive an appropriate type.
- An element/type mirror is unavailable or is an error type.
- A diagnostic attaches to a source without a specific line/column.
- A processor transforms/generates sources, causing the set of compilation units to change across phases.
- A missing classpath/module path causes many symbols to have cascading errors.

Generate reports on a **best-effort** principle:

1. Read all diagnostics; distinguish `ERROR`, `WARNING`, and `NOTE`.
2. Do not assert that `getElement(path)` is always non-null.
3. Check `ElementKind`/`TypeKind` before casting.
4. For unresolved errors, mark "unknown/unresolved" instead of guessing types.
5. Avoid carrying semantic results from one compilation into another when source or dependencies have changed.
6. If the tool edits code, edit only nodes guaranteed to have valid source positions; avoid editing based on unstable recovery ASTs.
7. When absolute correctness is required, do not emit semantic conclusions if the compiler has not finished the appropriate step or has reported related errors.

A common programming bug is using "element not found" as proof that "the variable was not declared". A `null` result can simply reflect *phase not ready*, an unsuitable node kind, or a compilation environment missing dependencies.

## 15. Overloads, Generics, and Lambdas Are Good Tests for the parse/analyze Boundary

### Overload

```java
static void send(Object value) {}
static void send(String value) {}

static void work() {
    send("ok");
}
```

The AST contains a `MethodInvocationTree` named `send`. Only the semantic phase applies overload resolution to choose `send(String)`. Do not use "first matching method found in the class" as a resolution algorithm.

### Generics and Target Typing

```java
List<String> names = java.util.Collections.emptyList();
```

The parser sees a generic method invocation and a variable with type `List<String>`. The compiler needs target typing and generic constraints to select a compatible type argument. A raw AST should not be treated as representing "`T` has already been inferred as `String`" without the corresponding semantic model.

### Lambda

```java
java.util.function.Function<String, Integer> f =
        s -> s.length();
```

The AST contains a lambda with parameter `s`. Here the type of `s` depends on the target functional interface. Parsing the lambda alone cannot yield a complete typed conclusion about `s` if the assignment context is ignored.

### Access Conditions

```java
package a;
public class Service {
    private void secret() {}
}
```

Another source can parse `service.secret()` as a method call, yet only within the specific class/module context and access permissions does the compiler conclude whether it is valid.

The four examples in section 15 are **illustrative snippets**, not four standalone programs to run together; they merely show that syntax and semantics are two different layers.

## 16. Testing AST Tools Without Coupling to Implementation

A test suite should include:

- **Syntax-only cases:** classes, methods, fields, nested classes, records, switches, patterns (matching the `--release` in use).
- **Semantic cases:** colliding imports, shadowing, overloads, generics, inheritance, and access permissions.
- **Invalid source cases:** syntax errors, type errors, missing classes, half-typed source.
- **Classpath/module path cases:** dependencies present and absent, named modules, and package exports.
- **Version cases:** compilers/JDKs that the tool actually claims to support.

What should be asserted?

| More Resilient to Test | Avoid Exact Assertions If Portability Is Needed |
| --- | --- |
| `CompilationUnitTree` has expected declared class/method | `JCTree` concrete class names/field layout |
| `ElementKind.METHOD` for resolved method | Internal symbol IDs, compiler context identity |
| `ExecutableElement.getReturnType()` semantically | Text of an implementation-specific diagnostic |
| Diagnostic kind `ERROR` present when source has type error | Number of `^` characters or spaces in stderr |
| Node positions valid per contract and source | Byte/AST positions across all versions without checking source |
| Correct build/task result | Exact order of every internal compiler callback |

Even a published API has preconditions and version differences; tests should run on supported JDKs/toolchains instead of inferring that any compiler runs identically.

## 17. Decision Workflow When Writing a Java Analysis Tool

1. **Identify the question.** Do you need syntax, symbols/types, or bytecode?
2. If only structure is needed, use `parse()` and the Tree API; do not pay the price of an architecture tied to internal symbols.
3. If type resolution/checking is needed, configure classpath/module path and use `analyze()` and `Trees`/`javax.lang.model`.
4. Handle diagnostics, `null`, `ErrorType`, and erroneous source instead of assuming complete semantics.
5. Access source positions via public Tree utilities, and keep source text to preserve comments/whitespace.
6. Avoid detaching/attaching nodes by casting to `JCTree`; if transformation is necessary, evaluate rewrite-supporting tools/libraries and define a contract.
7. If a requirement forces using `com.sun.tools.javac.*`, openly mark it as compiler-specific; pin versions and maintain a migration/test matrix.
8. Do not use `--add-exports`/`--add-opens` as a promise of stable internal APIs.
9. Verify output on real compilers/JDKs (for example JDK 17 and 21 where supported), rather than snapshotting log formatting.
10. When source changes, instantiate an appropriate task and invalidate old symbol/AST caches.

## 18. Self-Check Exercises

**Exercise A — Is an AST proof of type safety?** Parse `class X { MissingType x; }`. If you receive a `ClassTree`, can you conclude the Java code is valid?

**Answer:** No. Parsing determines syntactic structure; semantic checking cannot resolve `MissingType`.

**Exercise B — method name and overloads.** In code with two overloads `send(Object)` and `send(String)`, does `MethodInvocationTree` itself tell which overload to call?

**Answer:** No. Semantic resolution is needed based on argument types, conversions, and specificity.

**Exercise C — interface or internal implementation?** To read a declared method name, should you use `MethodTree.getName()` or cast to `JCTree.JCMethodDecl`?

**Answer:** Prefer `MethodTree.getName()`. It is the documented Tree API and is less implementation-dependent.

**Exercise D — when to use getElement?** Why must you not assume `Trees.getElement(TreePath)` always returns an `Element` right after `parse()`?

**Answer:** Symbols/attribution may not be ready yet, and the API can return `null` when no element exists. Query only after the appropriate semantic phase and check the result.

**Exercise E — can `--add-exports` "freeze" JCTree?**

**Answer:** No. It opens module access in the specified context; it does not prevent OpenJDK from changing internal classes.

**Exercise F — is an AST round-trippable?** Should you rewrite entire source code from `tree.toString()` and promise to preserve comments/indentation?

**Answer:** No. An AST is not a byte-for-byte record of source; original source text and trivia-preserving mechanisms are required.

**Exercise G — runnable example.** Run `AstPhaseDemo.java`; what two names are printed after parse, and what method kind/type are printed after analyze?

**Answer:** `Demo`, `twice`; after analyze, `METHOD` and `int`, with no `ERROR` diagnostic.

**Exercise H — source missing a type.** `AstErrorPhaseDemo` prints `parsedUnits=1` and `semanticError=true`. What does it illustrate?

**Answer:** A syntax tree can exist while the source still contains semantic errors. Parse status does not substitute for compiler success.

## 19. Summary and Authoritative References

A `parse()` tree only answers **"what syntactic structure does the source have?"**. It does not fully answer **"which symbol is that name, what type does the expression have, is the call valid, and can bytecode be generated?"**. When semantics are needed, use `JavacTask.analyze()` and documented APIs such as `Trees`, `TreePath`, `Element`, and `TypeMirror`, while handling diagnostics and invalid sources.

You must also distinguish **JDK-published Tree APIs** (`com.sun.source.*`) from **implementation internals** (`com.sun.tools.javac.*`). Depending directly on `JCTree`, `Symbol`, `Attr`, or `Context` creates coupling to compiler versions and runs into JPMS strong encapsulation. Permission-relaxing flags do not turn internals into stable APIs.

Authoritative references:

- [JDK 21 JavacTask](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html) — `parse`, `analyze`, and `generate` methods.
- [JDK 21 Tree API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html) — syntax-model interfaces.
- [JDK 21 Trees](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/Trees.html) — `getElement`, `getTypeMirror`, `getSourcePositions`, and semantics of possibly absent results.
- [JDK 21 TreePathScanner](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html) — traversing trees while keeping the current node path.
- [JDK 21 JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html) — compiler tasks and diagnostic listeners.
- [JDK 21 javac manual](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — supported APIs and `com.sun.tools.javac.*` internal warnings.
- [Oracle JDK Migration Guide](https://docs.oracle.com/en/java/javase/21/migrate/migrating-jdk-8-later-jdk-releases.html) — module encapsulation, `--add-exports`/`--add-opens`, and risks of depending on internal APIs.