# Traversing CompilationUnitTree with TreeScanner and TreePathScanner in Java

## 1. Goal: Reading Java Syntax Structure Without Writing Your Own Parser

When developing Java source analysis tools — such as cataloging methods, finding API calls, checking code rules, or collecting declaration locations — searching text strings with regex is unreliable. The same word can appear in a comment, string literal, generic type, method call, or declaration. An **Abstract Syntax Tree (AST)** represents program structure as typed nodes.

The Java Compiler Tree API in module **`jdk.compiler`** provides:
- `com.sun.source.tree.CompilationUnitTree`: the root node of a compilation unit, typically corresponding to a Java source file; contains package, imports, top-level declarations, and source metadata.
- `com.sun.source.tree.Tree`: the common interface for AST nodes; `Tree.Kind` denotes the node kind.
- `com.sun.source.util.TreeScanner<R,P>`: a visitor that recursively traverses child nodes and can pass state `P` and return result `R`.
- `com.sun.source.util.TreePathScanner<R,P>`: extends `TreeScanner` while maintaining **the path from the compilation unit to the current node** during traversal.
- `com.sun.source.util.TreePath`: a node plus its chain of ancestors in the AST.
- `com.sun.source.util.Trees` and `SourcePositions`: provide source positions and a bridge to the compiler's symbol/type model once analysis has progressed far enough.

**Core distinction:** `TreeScanner` is sufficient when you want to count, traverse, and inspect nodes structurally. `TreePathScanner` is appropriate when a rule needs to know **which class/method/expression a node is inside**, needs to call `Trees.getElement(TreePath)` or `Trees.getTypeMirror(TreePath)`, or needs to navigate to ancestors.

This is a compiler API, not Java reflection: it operates on **source/AST at analysis time**, even when the program has not run. The `com.sun.source.*` interfaces are documented compiler APIs, unlike directly depending on internal `com.sun.tools.javac.*` classes which have different stability and encapsulation constraints.

## 2. What Is CompilationUnitTree?

An example source file:

~~~java
package demo;
class Sample {
    void greet() {
        System.out.println("hi");
    }
    int add(int a, int b) {
        return a + b;
    }
}
~~~

Each compilation unit can contain a package declaration, imports, one or more type declarations, and source metadata. Conceptual tree shape:

~~~text
COMPILATION_UNIT
├── PACKAGE demo
└── CLASS Sample
    ├── METHOD greet
    │   └── BLOCK
    │       └── EXPRESSION_STATEMENT
    │           └── METHOD_INVOCATION System.out.println("hi")
    └── METHOD add
        └── BLOCK
            └── RETURN
                └── PLUS a + b
~~~

The diagram is intentionally simplified: a real AST may also include `MODIFIERS`, `IDENTIFIER`, `MEMBER_SELECT`, `PRIMITIVE_TYPE`, `VARIABLE`, `LITERAL`, and other nodes. **Do not** use the diagram to claim a node has only one child type or that the tree stays identical across every `javac` version.

Some methods of `CompilationUnitTree`:

| Method | Meaning |
| --- | --- |
| `getSourceFile()` | `JavaFileObject` representing the input source file |
| `getPackageName()` | Package name tree, may be `null` for an unnamed package |
| `getImports()` | The `ImportTree`s |
| `getTypeDecls()` | Top-level declarations, including other module/source forms depending on context |
| `getLineMap()` | Map from character positions in source to line/column |
| `getModule()` | Module declaration info when the compilation unit is `module-info.java` |
| `getPackage()` | `PackageTree` describing the package declaration |

A compilation unit does not necessarily contain only one public class; files like `package-info.java` or `module-info.java` must also be handled according to source kind. A tool should not assume “a file has exactly one `ClassTree`”.

## 3. Comparing TreeScanner and TreePathScanner

| Criterion | `TreeScanner<R,P>` | `TreePathScanner<R,P>` |
| --- | --- | --- |
| Recursively visits children via `visitXxx` | Yes | Yes, extends TreeScanner |
| Automatically maintains current `TreePath` | No | Yes, via `getCurrentPath()` |
| Used to count class/method/invocation | Very suitable | Also capable |
| Needs to inspect parent/ancestor node | Pass a stack or state manually | Use `getCurrentPath().getParentPath()` |
| Uses `Trees.getElement(path)` | Must construct/look up path separately | More convenient |
| Starting from `CompilationUnitTree` | `scan(unit, state)` | `scan(unit, state)` |
| Starting from a subtree with an existing path | Can scan Tree, but carries no context | `scan(TreePath, state)` |
| Overhead | Lighter because it does not maintain path context | Usually adds path bookkeeping overhead |
| Can use generic `R`, `P` | Yes | Yes |

Two generic parameters:
- `R`: the visitor's result type, e.g., `Void`, `Integer`, a collection of data.
- `P`: the state passed through each `scan` / `visit` step, e.g., configuration or a collector object.

For example, `TreeScanner<Void, Void>` means **neither a return value nor a traversal parameter is used**; results are stored in fields of the scanner. For tools that need to accumulate values via `R`, you must understand how `TreeScanner.reduce(R,R)` merges results from nodes; do not assume every visitor automatically sums child values.

**Important rule:** when overriding `visitMethod`, `visitClass`, or `visitMethodInvocation`, usually call `super.visitXxx(node, p)` to continue traversing child nodes. If you do not call `super`, you are **blocking descent into that subtree**, which may be intentional for optimization/pruning or may cause missing analysis results.

## 4. Complete Java 17+ Example: Both Scanners on the Same Source

The example was verified with `javac 24.0.2 --release 17` and ran successfully. This Java program invokes the Java Compiler API to **parse source**, without needing to run the `Sample` application.

Structure:

~~~text
project/
  Sample.java
  AstWalk.java
~~~

### 4.1. File Sample.java — source to analyze

~~~java
package demo;
class Sample {
    void greet() {
        System.out.println("hi");
    }
    int add(int a, int b) {
        return a + b;
    }
}
~~~

This is the source that the scanners will read. The first line is `package demo;`; the class name is `Sample`, with two methods `greet` and `add`.

### 4.2. File AstWalk.java — AST traversal tool

~~~java
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.TreeScanner;
import com.sun.source.util.Trees;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class AstWalk {
    private static final class CountScanner extends TreeScanner<Void, Void> {
        int classes;
        int methods;
        int calls;

        @Override
        public Void visitClass(ClassTree node, Void unused) {
            classes++;
            return super.visitClass(node, unused);
        }

        @Override
        public Void visitMethod(MethodTree node, Void unused) {
            methods++;
            return super.visitMethod(node, unused);
        }

        @Override
        public Void visitMethodInvocation(
                MethodInvocationTree node, Void unused) {
            calls++;
            return super.visitMethodInvocation(node, unused);
        }
    }

    private static final class ContextScanner
            extends TreePathScanner<Void, Void> {
        private final SourcePositions positions;

        ContextScanner(SourcePositions positions) {
            this.positions = positions;
        }

        @Override
        public Void visitMethod(MethodTree node, Void unused) {
            TreePath path = getCurrentPath();
            CompilationUnitTree unit = path.getCompilationUnit();

            long offset = positions.getStartPosition(unit, node);
            long line = offset < 0
                    ? -1
                    : unit.getLineMap().getLineNumber(offset);

            var parentKind =
                    path.getParentPath().getLeaf().getKind();

            System.out.println("METHOD " + node.getName()
                    + " parent=" + parentKind + " line=" + line);
            return super.visitMethod(node, unused);
        }

        @Override
        public Void visitMethodInvocation(
                MethodInvocationTree node, Void unused) {
            var parentKind = getCurrentPath()
                    .getParentPath().getLeaf().getKind();

            System.out.println("CALL " + node.getMethodSelect()
                    + " parent=" + parentKind);
            return super.visitMethodInvocation(node, unused);
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run this tool on a JDK");
        }

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(null, null, null)) {
            var inputs = files.getJavaFileObjects(
                    Path.of("Sample.java").toFile());

            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, null,
                    List.of("--release", "17", "-proc:none"),
                    null, inputs);

            for (CompilationUnitTree unit : task.parse()) {
                System.out.println(
                        "UNIT " + unit.getSourceFile().getName());

                CountScanner counts = new CountScanner();
                counts.scan(unit, null);
                System.out.println("COUNT classes=" + counts.classes
                        + " methods=" + counts.methods
                        + " calls=" + counts.calls);

                SourcePositions positions =
                        Trees.instance(task).getSourcePositions();

                new ContextScanner(positions).scan(unit, null);
            }
        }
    }
}
~~~

The entire example uses `com.sun.source.tree` and `com.sun.source.util` in module `jdk.compiler`. An application running on a custom JRE image must ensure module `jdk.compiler` is present; `ToolProvider.getSystemJavaCompiler()` can be `null` when running in a runtime without a Java compiler.

Differences directly in the code:
- `CountScanner` does not use a path. It updates three counters when encountering `ClassTree`, `MethodTree`, and `MethodInvocationTree`.
- `ContextScanner` uses `getCurrentPath()` to retrieve **`CompilationUnitTree` and the parent node of the method/call**, without manually maintaining an ancestor stack.
- `SourcePositions.getStartPosition(unit, node)` returns the **offset** in source; `LineMap.getLineNumber(offset)` converts the offset to a **line number**, starting at 1.
- The `task.parse()` call takes the sources provided by the file manager. The program does not call `task.analyze()` because the goal is solely **traversing syntactic structure**.
- `-proc:none` disables annotation processing in the sample task, keeping results independent of any processors that might be on the classpath.

### 4.3. Compile and run

From the `project` directory containing both files:

~~~bash
javac --release 17 -encoding UTF-8 AstWalk.java
java AstWalk
~~~

**Exact stdout** of the example:

~~~text
UNIT Sample.java
COUNT classes=1 methods=2 calls=1
METHOD greet parent=CLASS line=3
CALL System.out.println parent=EXPRESSION_STATEMENT
METHOD add parent=CLASS line=6
~~~

There is no stdout from `Sample.greet()`: the tool only **parses and scans**, without executing the analyzed class. Visitor order follows the AST traversal of the sample source: method `greet` appears before `add`.

If you replaced `CountScanner` with `ContextScanner` for counting, the program could still count, yet there is no reason to pay for path bookkeeping if the tool only needs total node counts.

## 5. From Source to CompilationUnitTree: Compiler API

Building the AST in the sample code involves four steps:

1. `ToolProvider.getSystemJavaCompiler()` obtains the `JavaCompiler` from an environment with a compiler.
2. `StandardJavaFileManager` turns `Sample.java` into a `JavaFileObject`.
3. `JavaCompiler.getTask(...)` creates the compile task; cast to `JavacTask` to call `parse()`.
4. `task.parse()` returns `CompilationUnitTree` instances; each unit is passed to `scanner.scan(unit, null)`.

`JavacTask` has key phases:

| Call | Effect |
| --- | --- |
| `parse()` | Parses syntax, builds `CompilationUnitTree` |
| `analyze()` | Performs semantic analysis, resolves symbols/types, runs related compiler phases |
| `generate()` | Executes the step emitting output class files after preceding phases |
| `Trees.instance(task)` | Provides a bridge to the AST, positions, and compiler language-model representation |

Do not equate `task.parse()` with `javac` having finished type-checking. An AST can be produced even when code has unresolved type names; depending on the error kind, the parser also creates `ErroneousTree`. If a rule needs to conclude “which method does this method really call”, **AST character strings are insufficient**; proper symbol resolution and type attribution are needed.

**Do not arbitrarily call `parse()`, `analyze()`, or `generate()` multiple times on the same task.** The task API is stateful and phase-ordered; a tool should clearly decide whether it needs only parsing or semantic analysis. Any diagnostics emitted by the compiler must be collected/managed in real applications.

For multi-file source, you can pass multiple `JavaFileObject`s into the task and traverse each `CompilationUnitTree` separately. Do not keep a `TreePath` from one task to draw symbol conclusions in another task, because classpath, compiler state, and symbol tables may differ.

## 6. TreeScanner: Traversing and Aggregating Nodes Syntactically

`TreeScanner<R,P>` implements `TreeVisitor<R,P>` and performs recursive traversal. Typical methods:
- `visitCompilationUnit(CompilationUnitTree, P)`
- `visitClass(ClassTree, P)`
- `visitMethod(MethodTree, P)`
- `visitVariable(VariableTree, P)`
- `visitMethodInvocation(MethodInvocationTree, P)`
- `visitIdentifier(IdentifierTree, P)`
- `visitMemberSelect(MemberSelectTree, P)`
- `visitBlock(BlockTree, P)`

A `TreeScanner` **does not keep the current TreePath**. If you write a rule needing to know “which method is this method invocation inside”, a simple way is passing context `P` down from the parent visitor. However, if the rule involves multiple ancestors, nested classes, or needs compiler symbols, `TreePathScanner` will be clearer.

### 6.1. Using fields to count

The `CountScanner` example in section 4 uses `TreeScanner<Void, Void>` and three fields. Creating a new instance per unit avoids accidentally accumulating counts across multiple files. If you want project-wide totals, intentionally use a shared collector and clearly define whether nested classes, anonymous classes, or generated constructs are counted.

For a `ClassTree` declaring a constructor, `visitMethod` can also count the constructor (it is represented via `MethodTree`). Therefore, do not label them “methods” without clarifying whether constructors are included. In the section 4 fixture, parse-only sees two explicitly written methods, without needing to infer implicit constructors inserted in later compiler phases.

### 6.2. `R`, `P`, and `reduce`

Suppose you want to return the node count instead of using fields:

~~~java
// Idea sketch: not a standalone Java class.
TreeScanner<Integer, Void> scanner = new TreeScanner<>() {
    @Override
    public Integer reduce(Integer left, Integer right) {
        return (left == null ? 0 : left)
                + (right == null ? 0 : right);
    }

    @Override
    public Integer visitMethod(MethodTree node, Void p) {
        Integer children = super.visitMethod(node, p);
        return 1 + (children == null ? 0 : children);
    }
};
~~~

Understand that `TreeScanner` by default uses `reduce` to combine results from child visitors; with `R=Integer`, to actually sum them you must override `reduce`. That is why you cannot assume “`scan` returns the total node count” without defining an aggregation strategy.

### 6.3. Intentional pruning

Sometimes only class signatures are needed, without reading method bodies:

~~~java
@Override
public Void visitMethod(MethodTree node, Void state) {
    recordSignature(node);
    return null; // do not call super -> do not traverse child nodes
}
~~~

This is an **illustrative snippet inside a scanner subclass**, assuming `recordSignature` exists. With this pattern, invocations inside method bodies are **never visited**. That can be a valid optimization, or a bug if the goal is cataloging API calls.

## 7. TreePathScanner: Knowing the Parent Node and Context

`TreePathScanner` inherits traversal from `TreeScanner` while maintaining the path via `TreePath`. Inside a visitor:

~~~java
@Override
public Void visitMethodInvocation(
        MethodInvocationTree node, Void unused) {
    TreePath current = getCurrentPath();
    TreePath parent = current.getParentPath();

    // current.getLeaf() is the current invocation.
    // parent.getLeaf() is the parent node, if the path has a parent.
    // current.getCompilationUnit() returns the root of the source file.
    return super.visitMethodInvocation(node, unused);
}
~~~

The snippet above sits **inside a TreePathScanner subclass**, not as a standalone program.

`TreePath` provides key information:

| Method | Meaning |
| --- | --- |
| `getLeaf()` | The AST node identified by the current path |
| `getParentPath()` | Path to the parent node; may be `null` at the root |
| `getCompilationUnit()` | Compilation unit at the root of the path |
| `TreePath.getPath(unit, node)` | Finds the path of a node inside unit, if the node actually belongs to that tree |
| `TreePath.getPath(path, node)` | Finds the path of a node inside the subtree pointed to by path |

**Inside a visitor, `getCurrentPath()` is only valid while the scanner is inside a properly initialized `scan` call.** Do not save a scanner reference and call `getCurrentPath()` outside traversal assuming it still points to the last visited node.

### 7.1. Initializing traversal properly

Two common ways to start:

~~~java
// Traverse the entire source file:
new ContextScanner(positions).scan(compilationUnit, null);
~~~

~~~java
// Traverse a subtree when a valid TreePath already exists:
new ContextScanner(positions).scan(existingPath, null);
~~~

These are **illustrative lines inside a method**; the variables must exist. The `TreePathScanner.scan(Tree, P)` API allows starting directly with a `CompilationUnitTree` as root. When wanting to start at **a specific method or expression**, build a valid path from the root or use an existing `TreePath`; do not call `scan(arbitraryMethodTree, null)` on a new scanner expecting it to know ancestors automatically.

Example finding the path from the root:

~~~java
TreePath path = TreePath.getPath(compilationUnit, methodTree);
if (path != null) {
    new ContextScanner(positions).scan(path, null);
}
~~~

The snippet above assumes `methodTree` belongs to that `compilationUnit`. Re-locating the path with `getPath` may have to walk the tree to find the node; in a large scan pass, using `getCurrentPath()` is usually more efficient than calling `TreePath.getPath` repeatedly for every node.

### 7.2. Reading ancestors safely

Example identifying the nearest enclosing method:

~~~java
// Sketch inside visitMethodInvocation:
TreePath p = getCurrentPath().getParentPath();
while (p != null && !(p.getLeaf() instanceof MethodTree)) {
    p = p.getParentPath();
}
String ownerMethod = p == null
        ? "<outside-method>"
        : ((MethodTree) p.getLeaf()).getName().toString();
~~~

The snippet above is not standalone source; `<outside-method>` is **a string literal in Java code**. The loop must check `p != null` because an invocation can sit inside a field initializer or initializer block rather than a method. With nested classes, a method invocation may belong to a constructor, lambda, or anonymous class; the definition of “enclosing method” must match the analyzer's requirements.

Importantly, **`TreePath` describes AST structure**, and does not by itself tell “which package that symbol is declared in” or “which overload the method resolved to”. For semantic answers, you need `Trees` and compiler attribution.

## 8. Binding the AST to File, Line, and Column Positions

A useful rule needs to return **locations** so users can fix code. Formula:

1. `Trees.instance(task).getSourcePositions()` retrieves `SourcePositions`.
2. `getStartPosition(unit, tree)` returns the source offset of the node.
3. `unit.getLineMap().getLineNumber(offset)` returns the line.
4. `unit.getLineMap().getColumnNumber(offset)` returns the column.

Example:

~~~java
SourcePositions positions = Trees.instance(task).getSourcePositions();
long start = positions.getStartPosition(unit, node);
if (start >= 0 && unit.getLineMap() != null) {
    long line = unit.getLineMap().getLineNumber(start);
    long column = unit.getLineMap().getColumnNumber(start);
    System.out.println(line + ":" + column);
}
~~~

The snippet above **is not a standalone program**, because `task`, `unit`, and `node` must exist beforehand. Offsets can be **`Diagnostic.NOPOS` (usually -1)** for trees without a defined source position. Therefore, check before converting to line/column. LineMap reflects the positions read by the compiler; do not infer positions using `String.length()` on source whose encoding or newlines changed.

`getEndPosition(unit, node)` is also useful for rule highlighting, though not every node always has a valid end position. When building IDE plugins/code actions, preserve encoding, line endings, and file identity.

If only the file name is needed: `unit.getSourceFile().getName()`; in a custom file manager environment, the name may be a URI or path provided by JavaFileObject, so do not always assume a standard filesystem path.

## 9. TreePathScanner and Symbol/Type Resolution

`TreePathScanner` does not perform type-checking by itself. It **holds the path context** so APIs like `Trees` can query semantic information once the compiler has completed the necessary phases.

Example skeleton for symbol lookup:

~~~java
// Inside an active TreePathScanner scan:
TreePath path = getCurrentPath();
Element symbol = trees.getElement(path);
TypeMirror type = trees.getTypeMirror(path);
~~~

This is an **excerpt**, assuming imports for `javax.lang.model.element.Element`, `javax.lang.model.type.TypeMirror`, and a valid `Trees trees` instance from `Trees.instance(task)`. There is no guarantee `symbol`/`type` will be useful when calling only `parse()`: many results require attribution via `task.analyze()`. Even after analyze, they may be `null` or represent error values for invalid source or tree kinds that do not correspond to a symbol.

Comparing use cases:

| Question | Can parse + scan alone work? | May semantic analysis be needed? |
| --- | --- | --- |
| How many `class` declarations does a file have? | Yes | Not required |
| What name does a method declare? | Yes | Not required |
| Is there an expression calling method `foo()`? | Yes, syntactically | Yes, if you need to know which `foo` it is |
| Which `print` overload is called? | Insufficient | Yes, needs symbol resolution |
| Does the expression have type `String` or `Object`? | Insufficient | Yes |
| Which method/class is this node syntactically inside? | Yes, via TreePath | Not required |
| Which declaration does a method reference point to? | Insufficient | Yes |

**Do not replace `TreePath` with guessed string names** when determining the actual method called. `a.toString()` and `b.toString()` look identical by name, yet may resolve to different declarations.

### 9.1. When analyze is needed

With the compiler task in section 4, you can design a two-phase pipeline:

~~~java
JavacTask task = /* task created from JavaCompiler */;
Iterable<? extends CompilationUnitTree> units = task.parse();
task.analyze();

// Then iterate over units and use Trees.instance(task)
// to query symbol/type when appropriate.
~~~

This is **pseudocode illustrating the workflow**, not a standalone runnable file. At this point, diagnostics must be handled if the source has errors. `analyze()` may trigger annotation processing and related compilation steps depending on task/options; if the tool only scans syntax, semantic analysis is unnecessary.

Distinguish **CompilationUnitTree**, which holds the AST, from **Trees**, which is the service accessing compiler information. `TreePathScanner` traverses the tree, and `Trees` provides the bridge to elements/types/source positions.

## 10. Java 17+ Cases: record, lambda, nested class, and method references

When scanning real source code, many constructs do not sit in simple positions like in the example:

~~~java
record Person(String name) {
    String upper() {
        return name.toUpperCase();
    }
}
~~~

This is valid Java 17 source when placed in an appropriate file. It reminds us that `ClassTree` is not only for traditional classes; kinds/type constructs such as records and interfaces must be handled by `Tree.Kind` and a visitor appropriate to the source level. Projects using newer Java may introduce new syntax and tree kinds; when using `javac --release 17`, only constructs valid for Java 17 source should be assumed.

Lambda example:

~~~java
Runnable r = () -> System.out.println("hello");
~~~

This is a statement inside a method, **not a standalone file**. The `System.out.println` invocation can still be seen by `visitMethodInvocation` if the scanner recursively traverses through `LambdaExpressionTree`. However, to determine the enclosing method, you may need to inspect the path and lambda boundaries instead of assuming the immediate parent node is a `MethodTree`.

Method reference example:

~~~java
java.util.function.Supplier<String> s = "x"::toUpperCase;
~~~

It uses `MemberReferenceTree`, **not `MethodInvocationTree`**. If you write an “all calls” analyzer and only override `visitMethodInvocation`, you will miss method references. Precisely define which constructs should be counted.

Nested/local/anonymous classes can introduce multiple `ClassTree` nodes in a single `CompilationUnitTree`, including class declarations inside methods or `new` expressions. If counting top-level classes, inspect the path or use `unit.getTypeDecls()` rather than counting every `visitClass`.

## 11. Accessing Parent Nodes: Most Common Mistakes

Several mistakes occur very easily:

**Mistake A — calling `getCurrentPath()` in TreeScanner.** This method belongs to `TreePathScanner`, not `TreeScanner`. If you need the path, switch subclass or maintain context in a controlled way yourself.

**Mistake B — starting TreePathScanner from a child node without a path.** Start directly at `CompilationUnitTree` or via `scan(TreePath, p)` from a valid path. Do not assume a method tree knows its compilation unit on its own.

**Mistake C — `getParentPath()` can be `null`.** At the root compilation unit, there is no ancestor. When writing general rules, always guard against `null`.

**Mistake D — forgetting `super.visitXxx`.** The scanner skips descendants beneath the overridden node; method calls or expressions are missed.

**Mistake E — traversing the same subtree twice.** If you manually call `scan(child,p)` and then also call `super.visitXxx`, the child can be visited twice. This causes double-counting even when the tree has no duplicate nodes.

**Mistake F — confusing method invocation with method declaration.** `MethodTree` is a declaration, `MethodInvocationTree` is a call, `NewClassTree` is object instantiation, and `MemberReferenceTree` is a method reference. Distinguish node kinds accurately.

**Mistake G — confusing text with symbol.** `node.getMethodSelect().toString()` is a syntactic representation and does not prove the right overload was resolved. When a symbol is needed, use compiler attribution and `Trees.getElement`.

**Mistake H — implicitly counting compiler-generated nodes.** The parser may not show a default constructor; later phases may transform the tree. Do not mechanically compare `MethodTree` counts between parse-only and other compiler states.

**Mistake I — retaining TreePath after task/AST has changed.** A path is tied to a specific tree and compiler task. Do not cache paths from an older invocation and combine them with a new task.

**Mistake J — relying unconditionally on absolute source positions.** Offsets can be undefined; check `NOPOS`, file identity, and `LineMap`.

## 12. Designing a Multi-File Analysis Tool

An analyzer used in CI typically has a pipeline:

~~~text
Input .java files + compiler options + source/module/classpath
                |
                v
JavaCompiler / JavacTask.parse()
                |
        CompilationUnitTree (each file)
                |
                +--> TreeScanner: structural metrics
                |
                +--> TreePathScanner: location + ancestor context
                |
                +--> (if needed) task.analyze() + Trees:
                     symbols, types, source positions
                |
                v
          Diagnostic / JSON / report
~~~

Do not mix syntactic and semantic metrics without labeling them clearly: “5 syntactic method calls” differs from “5 calls to method signature X”. An analyzer should:
- Obtain `JavaFileObject` and compiler options from the exact build configuration, avoiding analyzing with a different JDK/source level than CI.
- Create separate collectors or manage unified state across multiple units.
- Use `TreePathScanner` when a rule needs ancestors, recording file + line + kind consistently.
- Guard against `null` and `NOPOS`, and distinguish parse errors from semantic errors.
- Determine whether to analyze generated sources, tests, module-info.java, or only owned source.
- Use parse-only for purely syntactic rules, and analyze when symbol resolution is required.
- Test with nested/local classes, lambdas, method references, records, annotations, and syntax errors in source.
- Check performance: do not call `TreePath.getPath(unit,node)` repeatedly on every node when the scanner already maintains the path.
- Do not assume the AST/`Tree.Kind` of a newer JDK compiler matches an older JDK identically, especially with preview features.

### 12.1. Do not mutate the AST with a scanner alone

`TreeScanner` and `TreePathScanner` are **read/traversal visitors**; they do not perform code transformation themselves. To emit diagnostics, use `Trees.printMessage` or `Messager` in the appropriate context (annotation processors have `Messager`), and handle output separately. To modify source, you need a rewrite/text-edit system with offset mapping and token/trivia preservation; do not mutate `javac` implementation nodes under assumptions not guaranteed by the API.

`com.sun.source.util.Plugin`, `TaskListener`, and JSR 269 are compiler integration mechanisms different from an external tool calling `JavacTask.parse()`. All can access the AST in context, yet permissions and lifecycles differ; this lesson focuses on traversing `CompilationUnitTree`.

## 13. Extending the Example: Finding a Method in a Specific Class

A practical scanner might want only the `add` method in `Sample`. There are two strategies:

1. With `TreeScanner`: override `visitClass`, read the class name via `ClassTree.getSimpleName()`, and pass context down to `visitMethod` via `P` or a stack.
2. With `TreePathScanner`: inside `visitMethod`, walk up the path until the nearest `ClassTree`; check the class name. This helps when there are nested classes, anonymous classes, or methods across multiple levels.

Snippet checking the nearest class from inside `visitMethod`:

~~~java
TreePath p = getCurrentPath().getParentPath();
while (p != null && !(p.getLeaf() instanceof ClassTree)) {
    p = p.getParentPath();
}
if (p != null) {
    ClassTree owner = (ClassTree) p.getLeaf();
    String className = owner.getSimpleName().toString();
    // Use className together with node.getName() in the rule.
}
~~~

This is an **excerpt inside TreePathScanner**, not a standalone Java class. For an anonymous class, `getSimpleName()` may be an empty name; if full identity is needed, use appropriate path/symbol resolution and compiler analysis instead of relying solely on simple name.

If you only want top-level class names, use `unit.getTypeDecls()` and filter declarations that are `ClassTree`; there is no need to scan all method bodies to find them. **Choosing the minimal API sufficient to answer the question** is how to keep an analyzer easy to understand.

## 14. Sample Questions and Exercises

**Question 1.** Why does `TreeScanner` in the sample code count `calls=1` even though there are two methods?  
**Answer:** `greet()` contains the `System.out.println` call; `add()` only has an addition and a return statement, with no `MethodInvocationTree`.

**Question 2.** Why does `TreePathScanner` print `parent=EXPRESSION_STATEMENT` for `System.out.println`?  
**Answer:** The invocation is an expression placed as a statement; the immediate parent node of the invocation is `ExpressionStatementTree`. Method `greet` is a **further ancestor**, not the immediate parent.

**Question 3.** When should you choose `TreeScanner<Void, Void>`?  
**Answer:** When you only need to count, catalog, or inspect nodes syntactically and do not need to walk up ancestors or look up symbols via TreePath.

**Question 4.** A method invocation appears inside a lambda. Is `getCurrentPath().getParentPath()` always a `MethodTree`?  
**Answer:** No. The parent path may be an expression statement, return, lambda body, or another expression. You must walk up multiple levels if you need the enclosing method.

**Question 5.** To determine which overload is actually called, is `MethodInvocationTree.getMethodSelect().toString()` alone sufficient?  
**Answer:** No. Semantic analysis and `Trees.getElement(path)` on a valid path are required.

**Question 6.** `getStartPosition` returns `-1`; should it be mechanically converted to line `-1`?  
**Answer:** No. That is the case where no source position is defined; you must guard and skip or report an unknown position.

**Question 7.** Can you start TreePathScanner with `scan(methodTree, null)` on a new scanner and still have the compilation unit ancestors?  
**Answer:** You must not rely on that. Start from `CompilationUnitTree` or `scan(TreePath, p)` when the path is complete.

**Question 8.** What can go wrong if you forget to call `super.visitMethod` in a scanner?  
**Answer:** The scanner will not traverse the method body, missing invocations, variables, and expressions inside the method.

**Question 9.** Source contains a nested class and an anonymous class. Can `visitClass` count both of them?  
**Answer:** Yes; `ClassTree` represents the corresponding class/anonymous class declarations. If you only need top-level types, filter using `unit.getTypeDecls()` or the context path.

**Question 10.** Does `CompilationUnitTree` directly hold JVM reflection `Class<?>` objects?  
**Answer:** No. It is a source AST. `Class<?>` belongs to runtime reflection; when you need compile-time symbols/types, use the Java Compiler Model and `Trees`.

## 15. Official Documentation

- [Java 17 — CompilationUnitTree](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/CompilationUnitTree.html)
- [Java 17 — TreeScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreeScanner.html)
- [Java 17 — TreePathScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html)
- [Java 17 — TreePath](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePath.html)
- [Java 17 — JavacTask](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html)
- [Java 17 — Trees and SourcePositions](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html)

**Takeaway:** `CompilationUnitTree` is the root of a source AST; `TreeScanner` traverses and aggregates nodes; `TreePathScanner` does so **while carrying the path from the root to the current node**. Start scans properly, call `super.visitXxx` when descending into children, check parent/null/source positions, and query symbols/types only after the compiler has sufficient semantic information.
