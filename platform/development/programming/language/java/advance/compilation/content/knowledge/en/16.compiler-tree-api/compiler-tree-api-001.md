# Role of the Compiler Tree API in Java Source Code Analysis

The **Compiler Tree API** is the JDK's public set of interfaces that allows a program to inspect the **Abstract Syntax Tree (AST)** of Java source code used by the compiler. It is especially useful when building **static analysis tools**, code rule checkers, IDE support plugins, syntax pattern detectors, source-location collectors, report generators, or processors that need to correlate declarations with source code.

Instead of searching Java source using strings or regular expressions, a tool using the Tree API can ask language-level questions: “Is this a `MethodTree`?”, “Which method is this `return` inside?”, “Which method does this statement call?”, “Which line in the file is this name written on?”. When combining the syntax tree with the compiler's **semantic analysis** results, you can also ask “Which `Element` does this name resolve to?” and “What is the actual type of this expression?”.

This lesson belongs to the topic of **syntax trees** in Java compilation, focusing on APIs documented by the JDK in the two packages `com.sun.source.tree` and `com.sun.source.util`. Examples prefer Java 17 and above.

## 1. Where Does the Compiler Tree API Sit in the `javac` Pipeline?

A simplified model of compilation is:

```text
Java source (.java)
       |
       v
Lexical analysis / Parsing
       |
       v
AST: CompilationUnitTree, ClassTree, MethodTree, ...
       |             ^
       |             |
       |        Compiler Tree API
       v
Enter + symbol / type attribution + semantic checks
       |
       v
Correlating AST with Element, TypeMirror, Scope
       |
       v
Internal transformations / syntax desugaring
       |
       v
Bytecode generation (.class)
```

The diagram is a **generalized model for learning**, not a guarantee of the exact names and order of every internal `javac` phase across all JDK versions. The JavaCompiler API allows obtaining a `JavacTask` and explicitly calling `parse()`, `analyze()`, `generate()` when appropriate; the Tree API provides abstractions to observe the constructed tree and relate it to the semantic model.

### Distinguishing three data layers

| Layer | Typical APIs | Questions answered |
| --- | --- | --- |
| **Syntax** | `CompilationUnitTree`, `ClassTree`, `MethodTree`, `ExpressionTree`, `Tree.Kind` | Which language constructs does the source contain? |
| **Semantics** | `Element`, `TypeMirror`, `Scope`, `Trees.getElement`, `Trees.getTypeMirror` | Which symbol does a reference point to and what is the actual type? |
| **Class file/bytecode** | `javap`, JVM class-file structures | What bytecode, descriptors, and attributes did the compiler emit? |

The Compiler Tree API is **not a bytecode API** and **not a string-based Java parser**. The AST carries the structure of the source program, whereas bytecode is the result after compilation and may contain details such as synthetic members, bridge methods, or desugaring that the source AST does not expose in the same form.

## 2. Packages and Modules to Use

Java 17 distributes the related APIs in module **`jdk.compiler`**:

- `com.sun.source.tree`: interfaces representing AST nodes — `Tree`, `CompilationUnitTree`, `ClassTree`, `MethodTree`, `VariableTree`, `IfTree`, `MethodInvocationTree`, etc.
- `com.sun.source.util`: utilities for traversing, determining paths, mapping source locations, and accessing compiler information — `JavacTask`, `TreeScanner`, `TreePathScanner`, `TreePath`, `Trees`, `SourcePositions`, `TaskListener`.
- `com.sun.source.doctree`: AST for Javadoc documentation content; accompanied by `DocTrees` utilities.
- `javax.tools` in module `java.compiler`: compiler interface, file manager, diagnostic collector, `JavaFileObject`.
- `javax.lang.model` and its subpackages in `java.compiler`: declaration and type model of the program at the semantic level.

**Do not assume the `com.sun` prefix means these are unsupported internal APIs**. The `com.sun.source.tree`/`com.sun.source.util` packages are **publicly exported by `jdk.compiler`** with official API documentation. By contrast, most concrete classes in `com.sun.tools.javac.*` are compiler implementation details and should not be used as stable APIs for analysis tools.

If writing a **modular** application with `module-info.java`, declare:

```java
module com.example.analyzer {
    requires jdk.compiler;
}
```

For an ordinary classpath program using a full JDK, you can import the exported APIs of `jdk.compiler`; the runnable examples in this lesson do not require creating a module descriptor.

**Environment requirement:** you must use a JDK/runtime image that includes `jdk.compiler`. Minimal custom runtimes may lack the compiler. `ToolProvider.getSystemJavaCompiler()` can return `null`; production code must check for that before creating a task.

## 3. What Is an AST and What Information Do Nodes Carry?

An **AST** represents meaningful syntactic constructs and does not try to preserve every textual detail such as spacing, whitespace counts, regular comments, or semicolons as separate nodes.

Given source:

```java
public class Calculator {
    public int doubleIt(int x) {
        return x + x;
    }
}
```

A simplified view of the AST:

```text
CompilationUnitTree
└── ClassTree: Calculator
    └── MethodTree: doubleIt
        ├── return type: PrimitiveTypeTree(INT)
        ├── parameter: VariableTree(x : int)
        └── BlockTree
            └── ReturnTree
                └── BinaryTree(PLUS)
                    ├── IdentifierTree(x)
                    └── IdentifierTree(x)
```

This is an **illustrative diagram**, not the `toString()` output of an AST node. The actual tree also contains modifier nodes, member lists, and other syntactic details.

| Interface | Represents |
| --- | --- |
| `CompilationUnitTree` | A compilation unit (source file), package, imports, type declarations, line map |
| `ClassTree` | Class, interface, enum, or record declaration and its corresponding members/structures |
| `MethodTree` | Method/constructor declaration, parameters, return type, body, thrown types |
| `VariableTree` | Field, parameter, or local variable declaration |
| `BlockTree` | Block of statements |
| `IfTree` / `ForLoopTree` | Control-flow structures |
| `ReturnTree` | Return statement |
| `MethodInvocationTree` | Method invocation expression |
| `IdentifierTree` | Simple name reference |
| `MemberSelectTree` | Member access through an expression such as `obj.method` |
| `BinaryTree` | Two-operand operation such as `a + b` |
| `LiteralTree` | Numeric, string, boolean, or null literal |
| `ErroneousTree` | Syntax-error portion that the compiler still represents in a tree during error recovery |

`Tree.Kind` classifies nodes, for example `CLASS`, `METHOD`, `VARIABLE`, `METHOD_INVOCATION`, `PLUS`, `RETURN`. `Tree.Kind` names should not be treated as the same thing as `ElementKind` or JVM opcodes: they describe different layers.

### An AST is not a complete token stream

For example, the two snippets:

```java
int total = 1 + 2;
```

and:

```java
int total=1+2; // compute sum
```

normally yield the same corresponding AST structure in the main semantic nodes, despite differing in whitespace/comments. If a tool needs to **preserve every formatting byte, comments, and whitespace** to write a formatter or make zero-diff source edits, you must add a suitable text/token/trivia model. The Compiler Tree API does not on its own provide a concrete syntax tree preserving every character.

## 4. Two Traversal Styles: `TreeScanner` and `TreePathScanner`

### `TreeScanner<R,P>`

`TreeScanner` walks subtrees and calls visitor methods such as `visitClass`, `visitMethod`, `visitVariable`, `visitMethodInvocation`. For simple structural counting needs, it can suffice:

```java
new TreeScanner<Void, Void>() {
    @Override
    public Void visitMethod(MethodTree method, Void unused) {
        System.out.println(method.getName());
        return super.visitMethod(method, unused);
    }
}.scan(unit, null);
```

This is a **code fragment**, assuming a `CompilationUnitTree unit` variable and imports. Calling `super.visitMethod(...)` continues traversing descendants inside the method. If you intentionally omit the `super` call, you can stop descending into the method body.

### `TreePathScanner<R,P>`

`TreePathScanner` extends `TreeScanner` and maintains a **`TreePath` to the current node**. It is useful when you need to:

- Know which method/class a statement belongs to along its ancestor path.
- Look up `Trees.getElement(getCurrentPath())`.
- Look up the type of an expression with `Trees.getTypeMirror(getCurrentPath())`.
- Construct a diagnostic that needs the node's position in the compilation unit.

Example:

```java
new TreePathScanner<Void, Void>() {
    @Override
    public Void visitMethod(MethodTree method, Void unused) {
        TreePath path = getCurrentPath();
        // path links compilation unit → ancestors → method node.
        return super.visitMethod(method, unused);
    }
}.scan(unit, null);
```

This is also a **snippet**, not a standalone runnable program. `getCurrentPath()` only has a valid context **inside a visitor callback while the scanner is running**; do not call it before starting the scan expecting a path to some node.

**Important:** When starting from a `CompilationUnitTree`, `scanner.scan(unit, null)` is a valid way to establish the initial path context. For a standalone child node without its compilation unit, start with `scanner.scan(TreePath, ...)` or build a valid path; directly scanning a lone node may not provide sufficient ancestor/source information.

## 5. Complete Java 17 Example: Listing Methods and Source Lines

This example **does not write a source analyzer with regex**. It asks `javac` to parse the file into an AST, uses `TreePathScanner` to find `MethodTree` nodes, and uses `SourcePositions` to convert start positions into line numbers.

### 5.1. Create the source structure

```text
project/
├── TreeInspector.java
└── src/
    └── demo/
        └── Sample.java
```

**`src/demo/Sample.java`**, keeping blank lines so line numbers in the output match:

```java
package demo;

public class Sample {
    public int add(int a, int b) {
        return a + b;
    }

    public int twice(int number) {
        return add(number, number);
    }
}
```

In the layout above, `add` is declared starting on **line 4**, and `twice` on **line 8** (counting the first line of source as 1).

### 5.2. Write `TreeInspector.java`

```java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.LineMap;
import com.sun.source.tree.MethodTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class TreeInspector {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java TreeInspector path/to/Source.java");
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler (jdk.compiler) is unavailable");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, null, null)) {

            Iterable<? extends JavaFileObject> sources =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(Path.of(args[0])));

            JavacTask task = (JavacTask) compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    sources);

            Trees trees = Trees.instance(task);
            SourcePositions positions = trees.getSourcePositions();

            for (CompilationUnitTree unit : task.parse()) {
                LineMap lines = unit.getLineMap();

                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitMethod(
                            MethodTree method, Void unused) {
                        long offset =
                                positions.getStartPosition(unit, method);

                        if (offset >= 0
                                && method.getReturnType() != null) {
                            long line = lines.getLineNumber(offset);
                            System.out.println(
                                    "method=" + method.getName()
                                    + " line=" + line);
                        }

                        return super.visitMethod(method, unused);
                    }
                }.scan(unit, null);
            }

            boolean hasErrors = diagnostics.getDiagnostics()
                    .stream()
                    .anyMatch(d -> d.getKind()
                            == Diagnostic.Kind.ERROR);

            if (hasErrors) {
                System.err.println("Source contains parse errors");
            }
        }
    }
}
```

**Walkthrough:**

1. Obtain `JavaCompiler` via `ToolProvider`. If the runtime image has no compiler, stop with a dedicated message.
2. `getStandardFileManager(...)` provides `JavaFileObject` instances for the input file; `try-with-resources` ensures the file manager is closed.
3. `getTask(...)` creates a compiler task from the source files. The arguments `List.of("--release", "17", "-proc:none")` parse at Java 17 level and disable annotation processing for the example.
4. With the `javac` implementation in `jdk.compiler`, the returned task can be **cast to `JavacTask`** to call `parse()`. This is specific to the JDK compiler integration, not a guarantee that every third-party `JavaCompiler` returns a `JavacTask`.
5. `Trees.instance(task)` provides lookup operations bound to the task; `getSourcePositions()` yields AST node positions inside the compilation unit.
6. `task.parse()` returns `CompilationUnitTree` instances. The example **only parses**, without calling `analyze()` or `generate()`, so it does not check full type semantics or emit a class file for `Sample`.
7. `TreePathScanner` automatically traverses child nodes; override `visitMethod` to find method declarations.
8. `method.getReturnType() != null` filters out constructor declarations (constructors have no return type) if present. The example source does not explicitly write a constructor.
9. Only a non-negative `offset` is converted to a line number; source positions may be absent on some nodes.
10. Compiler diagnostics are collected in the collector; the program only prints a general warning if an `ERROR` is encountered, rather than relying on diagnostic wording.

### 5.3. Compile and run

In the `project` directory, with **JDK 17+**:

```sh
javac --release 17 -encoding UTF-8 TreeInspector.java
java TreeInspector src/demo/Sample.java
```

**Exact stdout for the two files above:**

```text
method=add line=4
method=twice line=8
```

Running `TreeInspector` on a newer JDK while targeting source `--release 17` does not change the source lines. `TreeInspector.class` is generated by the tool compilation command; meanwhile `Sample.class` is **not** created merely by the program's `task.parse()` call.

**If the input source has syntax errors:** the compiler may produce `ErroneousTree` nodes and report `Diagnostic.Kind.ERROR`. Scan output may miss nodes or have incomplete positions; the example program only demonstrates checking `hasErrors`. A real analysis tool should stop or mark the result as **partial** when diagnostics contain errors, rather than reporting the AST result unconditionally as complete.

### 5.4. Limitations of line measurement

`SourcePositions.getStartPosition(unit, tree)` returns the **starting character position** of the node in the compilation unit, or `-1`/`Diagnostic.NOPOS` when undefined. `LineMap.getLineNumber(offset)` converts a valid position to a line number.

Several cases to keep in mind:

- Compiler-synthesized nodes may not have a source position.
- Implicit constructors or members created after a compiler phase do not necessarily have a corresponding source declaration.
- Positions apply to a **specific source file**; do not mix an offset from unit A with the `LineMap` of unit B.
- Character positions follow API/source semantics; do not treat them as UTF-8 byte offsets in the file.
- When needing to highlight an entire range, also fetch `getEndPosition`, while checking for the possibility of a missing end position.
- Line/column follow `LineMap`/diagnostic conventions, usually **1-based**; do not feed them directly into a 0-based editor API without converting.

## 6. `parse()`, `analyze()`, and `generate()`: Choosing the Right Level

`JavacTask` provides methods for high-level work phases:

| Method | Role | When appropriate |
| --- | --- | --- |
| `parse()` | Parses syntax, returns `CompilationUnitTree` | Inspecting methods, expressions, statement structures, source lines |
| `analyze()` | Completes semantic analysis | Needing `Element`, `TypeMirror`, type rules/symbol resolution |
| `generate()` | Generates output code/class files | Needing the compiler to actually emit class files after the appropriate phases |
| `CompilationTask.call()` | Runs compilation as a single task and returns `Boolean` success | Tool only needs compilation results; does not manually coordinate Tree API phases |

Calls must respect the task state; do not arbitrarily call `task.call()` **after** manually driving phases in a manner not guaranteed by the API. Create a **new task** for another compilation run or to repeat parsing/analysis.

### Why is `parse()` not enough for types?

Given the code:

```java
import java.util.List;

class Example {
    void consume(List<String> values) {
        System.out.println(values.size());
    }
}
```

The AST can tell that a `MethodInvocationTree` represents `values.size()` and an `IdentifierTree` is named `values`. However, to confirm **which parameter `values` is**, what the expression type is, and which method `size` resolves to, the compiler needs symbol/type analysis.

If you only compare `node.toString().equals("size()")` or the text name of a method invocation, mistakes happen easily when a method name is overloaded, inherited, present across different classes, or shadowed.

**Learning rule:** use parse-only for **syntactic** queries; use analysis + `Trees`/language model for **semantic** queries.

## 7. Relating the AST to `Element` and `TypeMirror`

Once appropriate semantic analysis data is available from `JavacTask.analyze()`, `Trees` serves as the bridge between the tree and the language-element model:

- `Trees.getElement(TreePath)`: retrieves the **`Element`** declaration corresponding to the node/path, if any.
- `Trees.getTypeMirror(TreePath)`: retrieves the **`TypeMirror`** representing the type of the node/path, when determinable.
- `Trees.getPath(Element)`: retrieves the `TreePath` to the corresponding source declaration if the compiler has the source tree.
- `Trees.getTree(Element)`: retrieves the AST declaration associated with `Element` if the source tree is present.
- `Trees.getScope(TreePath)`: queries the scope at an appropriate location.
- `JavacTask.getElements()` and `getTypes()`: utilities for the semantic model.

An **integration fragment** example, assuming you created `JavacTask task`, retrieved `CompilationUnitTree unit` from `task.parse()`, then called `task.analyze()`, and obtained `Trees trees`:

```java
task.analyze();

new TreePathScanner<Void, Void>() {
    @Override
    public Void visitMethod(MethodTree method, Void unused) {
        TreePath path = getCurrentPath();
        Element symbol = trees.getElement(path);

        if (symbol instanceof ExecutableElement executable
                && method.getReturnType() != null) {
            System.out.println(
                    executable.getSimpleName()
                    + " returns "
                    + executable.getReturnType());
        }
        return super.visitMethod(method, unused);
    }
}.scan(unit, null);
```

This is a **snippet, not a standalone Java file**: add imports for `javax.lang.model.element.Element` and `ExecutableElement`, and ensure `task`, `unit`, and `trees` belong to the same compiler task. This code illustrates how to use the language model after `analyze()`; avoid casting `Element` to `ExecutableElement` before checking with `instanceof`.

### `TreePath` matters because a name alone cannot identify a symbol

Two places both having `IdentifierTree("value")` can refer to two different variables in different scopes. `TreePath` carries the **ancestor context** from the compilation unit to the node, so `Trees.getElement` can resolve the exact element at that location once the compiler completes attribution.

Do not assume calling `getElement` on any arbitrary node must return a non-null result. For nodes not representing a symbol, when the compiler has not yet analyzed, when source has errors, or when data comes from a binary dependency without a source tree, the API may return `null` or lack complete information. Real analysis code needs a policy for handling **unresolved** cases instead of throwing `NullPointerException`.

### `TypeMirror` differs from the text of a `Tree`

`Tree` describes source syntax, such as `List<String>` or an arithmetic expression. `TypeMirror` describes the semantic type inferred/resolved by the compiler, which may include type arguments, wildcards, intersection types, error types, and inference results.

For example `int result = 1 + 2;`: the addition AST contains a `BinaryTree(PLUS)` with two `LiteralTree` nodes, whereas the expression's `TypeMirror` can be `int`. When expressions involve generics/overloads, the inferred type cannot necessarily be read merely from `node.toString()`.

## 8. `TreeVisitor` and Writing Static Analysis Rules

Each `Tree` can be visited via `TreeVisitor`. The most convenient approach is usually subclassing `TreeScanner` or `TreePathScanner` and overriding the visitor method for the right node type.

### Example: counting method invocations

```java
final class InvocationCounter
        extends TreeScanner<Void, Void> {
    private int count;

    @Override
    public Void visitMethodInvocation(
            MethodInvocationTree invocation, Void unused) {
        count++;
        return super.visitMethodInvocation(invocation, unused);
    }

    int getCount() {
        return count;
    }
}
```

This is a **class snippet** requiring imports `com.sun.source.tree.MethodInvocationTree` and `com.sun.source.util.TreeScanner`. To use it, create `InvocationCounter counter`, call `counter.scan(unit, null)`, and read `counter.getCount()`.

**Limitation:** Counting syntactic invocations differs from counting runtime calls. A call in source code may execute many times in a loop, not execute due to a condition, or dispatch to a different implementation. The AST only reflects invocation expressions written/generated into the tree of the analyzed source; it does not simulate runtime execution.

### Example: finding `return` statements inside a method

`TreePathScanner` can override `visitReturn(ReturnTree node, ...)` and use the ancestor path to determine the enclosing method. When lambdas or nested/local classes are present, the rule's scope must be decided explicitly; not every `return` beneath a method's subtree is necessarily a direct return of that method itself.

For example, a lint system can:

- Warn on overly long methods based on source range and AST structure.
- Warn on using a legacy API when the **resolved symbol** points to that API, rather than matching text names.
- Count nested loops and branch depth.
- Find empty `catch` blocks that might swallow exceptions.
- Check annotations on declarations.
- Detect `if` statements whose condition is always a boolean literal in the AST.

However, do not promise that the Tree API automatically proves a program is free of concurrency bugs, resource leaks, or security flaws. Advanced analyses require **control-flow/data-flow**, program models, and/or additional analysis libraries.

## 9. Emitting Diagnostics Tied to AST Locations

A useful analysis tool does not merely print method names to the console; it also wants to report **exact source locations**. Two common approaches:

1. Use `SourcePositions` + `CompilationUnitTree.getLineMap()` to obtain file, line, and column; then store results for IDEs/CI.
2. Use the utility `Trees.printMessage(Diagnostic.Kind kind, CharSequence msg, Tree t, CompilationUnitTree root)` when inside an appropriate compiler environment; diagnostics are thereby attached to the node's position.

Diagnostics during parsing/analyzing can also be sent to a `DiagnosticCollector<JavaFileObject>` when creating `JavaCompiler.CompilationTask`.

Example of safely iterating over compiler diagnostics:

```java
for (Diagnostic<? extends JavaFileObject> d :
        diagnostics.getDiagnostics()) {
    String sourceName = d.getSource() == null
            ? "<unknown>" : d.getSource().getName();

    System.out.println(
            d.getKind() + " " + sourceName
            + ":" + d.getLineNumber());
}
```

This is a **snippet**, assuming `DiagnosticCollector`/imports. A `Diagnostic` might not be tied to a specific source or might lack a position; `getLineNumber()` may be `Diagnostic.NOPOS`. Do not use negative positions to highlight a nonexistent line.

### Parse errors and recoverable trees

When source code has errors such as missing braces or incomplete declarations, `javac` can **partially recover** to produce an AST and diagnostics. `ErroneousTree` is a node type representing portions of source that the compiler could not parse into the expected construct.

For an IDE, an incomplete AST still has value for code completion. For a CI tool requiring strict reliability, however, you may choose not to run certain semantic rules if `Diagnostic.Kind.ERROR` is already present. In any case, **`parse()` returning a tree does not mean the source is valid**.

## 10. Role of `TaskListener` and When to Scan the Tree

`com.sun.source.util.TaskListener` can observe compiler-level events emitted by `JavacTask`, via `started(TaskEvent)` and `finished(TaskEvent)`. `TaskEvent.Kind` includes kinds related to parse, enter, analyze, and generate. This is useful if you want to run analysis at a suitable phase or integrate into a longer compilation process.

**Skeleton example:**

```java
task.addTaskListener(new TaskListener() {
    @Override
    public void started(TaskEvent event) {
    }

    @Override
    public void finished(TaskEvent event) {
        if (event.getKind() == TaskEvent.Kind.PARSE) {
            // Can inspect the compilation unit of the event
            // via appropriate APIs and at a valid stage.
        }
    }
});
```

This is a **snippet**; it requires imports `TaskListener` and `TaskEvent`, plus a `task` variable of type `JavacTask`. Do not put logic that writes bytecode or mutates compiler internal state inside callbacks without a clear safety contract.

### Choosing the timing based on the information needed

- **After parse:** sufficient for syntactic rules; an AST can exist even when source has errors.
- **After analyze:** suitable for querying `Element`, `TypeMirror`, scope, and symbol-based validation; errors must be handled.
- **Before/after generate:** suitable if the goal is observing progress and class outputs, though bytecode should be inspected with proper class-file tools.

You do not need to register a `TaskListener` for every tool. If you only want a simple one-pass source scan, an example like `TreeInspector` calling `task.parse()` directly is easier to read and test.

## 11. Using the Tree API in an Annotation Processor

JSR 269 `javax.annotation.processing` typically passes an annotation processor a set of annotated `Element`s; the Processor API **focuses on the language model** and does not directly describe every syntactic detail inside method bodies. When an annotation processor needs source/AST locations:

```java
Trees trees = Trees.instance(processingEnv);
TreePath path = trees.getPath(element);
if (path != null) {
    Tree declaration = path.getLeaf();
    // Analyze the declaration AST via an appropriate TreePathScanner.
}
```

This is a **snippet** inside `AbstractProcessor` with `processingEnv` and `Element element`; not a standalone file. Use `Trees.instance(ProcessingEnvironment)` when the compiler provides the corresponding Tree API.

**Notes:**

- `getPath(element)` may return `null` if the element comes from a **binary dependency** without a source tree, or if the source tree is unavailable.
- An annotation processor can be invoked across multiple rounds; generated sources in later rounds have new ASTs. Do not assume one round's `getRootElements()` contains all declarations in history.
- Do not retain compiler tree/`Element` references across different compiler invocations; collect stable data when needed.
- Use `Filer` to create source/class files according to the processor protocol; the Tree API **is not responsible for writing modified source code** to disk.
- If you need a Javadoc AST, use `DocTrees`/`DocTreePathScanner` for doc comments; do not parse Javadoc text with regex as a substitute for the entire model.

### AST and source-level lint differ from annotation validation

An annotation processor that only needs to check `@NotBlank` on a field can use `Element`/`TypeMirror` without needing the Tree API. The Tree API is valuable **when requirements depend on location/syntax/source body**, such as checking whether an annotated method has a specific `return` statement or performs a disallowed call.

Do not use the Tree API merely to replace an `Element.getSimpleName()` query already supported by the Processor API: choose the smallest abstraction that satisfies the requirement.

## 12. Limitations and Compatibility Issues

### Public APIs vs. compiler internals

- `com.sun.source.tree`, `com.sun.source.util`, and `com.sun.source.doctree` are exported by module `jdk.compiler` and have official documentation.
- `com.sun.tools.javac.tree.JCTree`, `com.sun.tools.javac.code.Symbol`, and many other compiler internal types are **not** similar public contracts. Using them may require `--add-exports`, break across JDK upgrades, and depend deeply on implementation details.
- `Tree` is a read/query interface; there is by default no public mutation API for arbitrarily modifying the AST and having the compiler recompile it stably.
- If the goal is **source code refactoring**, design a rewrite system based on source ranges/text edits with validation, or use a framework with its own rewrite contract.

### The JDK compiler is not every Java compiler

`JavaCompiler` is an SPI; a third-party Java compiler may implement `javax.tools.JavaCompiler` without returning a `com.sun.source.util.JavacTask`. With the code:

```java
JavacTask task = (JavacTask) compiler.getTask(...);
```

this cast relies on the `javac` implementation inside `jdk.compiler`. In a tool meant to support multiple compilers, check the type with `instanceof` or explicitly document the dependency on JDK `javac`, rather than assuming all `JavaCompiler` implementations are compatible with the Tree API.

### Newer Java code and compiler versions

AST node kinds expand as Java adds new syntax (records, switch expressions, pattern matching, etc.). If an analyzer runs on different JDKs, the node kinds received or traversal behavior may change. Use the right JDK version and `--release` matching the project; test when upgrading toolchains.

A tree scanner written for Java 17 can encounter newer syntax when run on a newer JDK without a release restriction. Do not try to force unfamiliar nodes into older types based on `toString()`; design the visitor to ignore or handle unsupported node kinds according to tool policy.

### No guarantee that AST output matches source formatting

`Tree.toString()` is only a representation for inspection/debugging. You should not:

- Compare it as a durable serialization format.
- Reparse it to build an authoritative dependency graph.
- Expect it to preserve comments, whitespace, or token offsets.
- Use text output as the sole evidence for resolving overloaded methods.

If you need to persist data, define your tool's own schema: file URI, kind, resolved symbol name, source range, finding category, and message.

## 13. Common Misconceptions

**“The Compiler Tree API is only for printing tree diagrams.”** No. The AST can be traversed by construct type, correlated with source positions, and after semantic analysis with `Element`/`TypeMirror`; it is the foundation for many static analysis tools.

**“`parse()` already checks all types.”** False. Parsing mainly builds the AST; querying compiler-resolved symbols/types requires appropriate semantic phases, typically calling `analyze()`.

**“An identifier name alone tells which variable it is.”** False. Scope, shadowing, overloaded methods, generics, and imports require symbol resolution. Use `TreePath` + `Trees.getElement` in the appropriate phase.

**“`TreeScanner` and `TreePathScanner` are identical.”** No. `TreePathScanner` maintains the path to the current node, useful for semantic/source-aware rules; `TreeScanner` is simpler when only counting/traversing structure.

**“All AST nodes have a line position.”** No. Synthetic/error/recovered nodes may lack a source position; check `Diagnostic.NOPOS` or negative values before using.

**“A parsed AST means the source code compiles successfully.”** False. The compiler can produce an AST alongside error diagnostics; class-file output also depends on analyze/generate.

**“`Trees.getPath(element)` always returns a tree.”** False. For an element from a `.class` library without source in the compilation task, the tree may not exist.

**“Because of `com.sun`, either everything is an internal API or everything is safe.”** Both extremes are wrong. Use packages exported and officially documented by `jdk.compiler`, and avoid unexported compiler implementation classes.

**“The Tree API automatically modifies source files.”** False. It is an inspection/traversal API and semantic bridge; there is no guarantee that mutating the source AST will make the compiler emit corresponding new source.

**“Having a method invocation node means the method definitely executes.”** False. The AST describes the program; it does not simulate every control branch and runtime dispatch.

**“Using the compiler API compiles source in a secure sandbox.”** False. The compiler/annotation processors can access the filesystem or execute code in the host JVM. For untrusted source code, execute and control resources in an isolated environment; the Tree API is not a sandbox mechanism.

## 14. Checklist for Choosing and Using the Tree API Correctly

- [ ] Does the requirement call for **syntax**, **semantic type/symbol**, or **bytecode** analysis? Did you choose the right API layer?
- [ ] Running on a JDK with module `jdk.compiler` and checking that `ToolProvider` is non-`null`?
- [ ] If the application is modular, does `module-info.java` include `requires jdk.compiler;`?
- [ ] Using public packages `com.sun.source.tree/util` instead of internals `com.sun.tools.javac.*`?
- [ ] Using `JavacTask.parse()` to obtain `CompilationUnitTree` and scanning at the appropriate tree level?
- [ ] Using `TreePathScanner` when an ancestor path and symbol lookup are needed?
- [ ] Calling `analyze()` before semantic queries for `Element`/`TypeMirror` in the appropriate task?
- [ ] Checking for null/unresolved results from `Trees.getElement/getPath`?
- [ ] Checking valid source positions and mapping accurately with `CompilationUnitTree.getLineMap()`?
- [ ] Collecting compiler diagnostics and handling erroneous source/partial trees?
- [ ] Avoiding assumptions that every AST node or binary dependency has a source tree?
- [ ] Distinguishing parser errors, semantic errors, and analyzer tool errors?
- [ ] Closing `StandardJavaFileManager` and not misusing task lifecycles?
- [ ] Testing on the target JDK/compiler version with the Java syntax that must be supported?
- [ ] Preserving source formatting when applying edits, rather than re-emitting `Tree.toString()` as the source file?

**Conclusion:** The Compiler Tree API turns “reading source code as plain text” into “analyzing **the Java structure understood by the compiler**”. `com.sun.source.tree` provides the AST shape, `TreeScanner`/`TreePathScanner` traverse the tree, `Trees` connects nodes to **source positions** and the **symbol/type model**, and `JavacTask` lets you choose parse or analyze levels. It is an important tool for static analysis/lint/IDEs, though you must clearly understand the limits of syntax-only checks, semantic information, error recovery, and the difference between public APIs and compiler internals.

## Official References

- Java SE 17, module **`jdk.compiler`** and list of exported packages: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/module-summary.html
- Java SE 17, package **`com.sun.source.tree`**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html
- Java SE 17, package **`com.sun.source.util`**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/package-summary.html
- Java SE 17, **`JavacTask`** (`parse`/`analyze`/`generate`): https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html
- Java SE 17, **`TreePathScanner`**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html
- Java SE 17, **`Trees`** and **`SourcePositions`**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html
- Java SE 17, **`JavaCompiler`** (`javax.tools`): https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
