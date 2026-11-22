# Connecting Tree Nodes to Element and TypeMirror with Trees

In Java code analysis tools, the **syntax tree (AST)** tells *how the code was written*, the **element model (`Element`)** tells *which declaration a name refers to*, and the **type model (`TypeMirror`)** tells *what type the compiler inferred or checked*. These three layers of information are closely related yet cannot substitute for one another.

For example, in the statement `int count = names.size();`:

- The `MethodInvocationTree` node represents the call syntax `names.size()`.
- `Trees.getElement(TreePath)` can tell which `size` method was resolved; the result is typically an `ExecutableElement` with `ElementKind.METHOD`.
- `Trees.getTypeMirror(TreePath)` on **the path to the entire call expression** returns the result type `int`.
- The `IdentifierTree` node for `names`, in contrast, links to the local variable's `VariableElement` and has the usage type `java.util.List<java.lang.String>`.

The ability to connect these three representations is the foundation of linters, API checkers, code navigation, refactoring, and annotation processors performing deep source analysis. The public APIs used here are **`com.sun.source.util.Trees`** and **`TreePath`** in JDK module `jdk.compiler`, combined with `com.sun.source.tree`, `javax.lang.model.element`, and `javax.lang.model.type`. These are documented APIs for the compiler's syntax tree; there is no need to rely on internal `com.sun.tools.javac.*` classes.

This lesson uses Java 17+ and the examples were compiled and run on JDK 24 targeting `--release 17`.

## 1. Tree, Element, and TypeMirror Answer Different Questions

| Object | Description | Example | Appropriate question |
| --- | --- | --- | --- |
| `Tree` | Syntactic node in source | `IdentifierTree`, `MethodInvocationTree`, `VariableTree` | “Which construct did the code author write?” |
| `CompilationUnitTree` | Compilation unit, typically corresponding to a Java file | import, package, top-level declarations | “Which source file is the node in?” |
| `TreePath` | Path from the source unit through parents to a current node | path to `names` inside `names.size()` | “What context does this node belong to?” |
| `Element` | Declaration/symbol after name resolution | class, method, field, local variable | “Which declaration does this name bind to?” |
| `TypeMirror` | Type in the language model | `int`, `List<String>`, type variable | “What type does the expression or declaration have?” |
| `Trees` | Bridge between representations | `getElement`, `getTypeMirror`, `getPath` | “How do I get from syntax to symbol or type?” |

These models are not identical:

- **`Tree` is not a runtime object**. It describes source, not a class instance at runtime.
- **`Element` is not `Class<?>` or `java.lang.reflect.Method`**. It is a compile-time representation.
- **`TypeMirror` is not `java.lang.reflect.Type`**. It includes types the compiler infers from source, including generics/wildcards/type variables as well as error or incomplete forms.
- A `Tree` does not necessarily have a corresponding `Element`, yet can still have an expression type.
- An `Element` may come from the classpath/module path and **have no corresponding source tree** in the current compilation task.

Key point: **determine whether you are asking about syntax, declaration, or expression type** before choosing an API.

## 2. TreePath Matters Because a Node Needs Context

`Tree` represents a node; looking at the node alone is not enough to determine all semantics. The same identifier `size` can appear in methods of many classes, in a local variable, or in a call after generic inference. Context from parent nodes, scope, receiver, and imports participates in resolution.

`TreePath` carries a chain of relationships:

```text
CompilationUnitTree
    |
    +-- ClassTree Example
           |
           +-- MethodTree run
                  |
                  +-- VariableTree count
                         |
                         +-- MethodInvocationTree names.size()
                                |
                                +-- MemberSelectTree names.size
                                       |
                                       +-- IdentifierTree names
```

The model above only shows noteworthy parts and does not list every intermediate AST node. When the scanner is at `MethodInvocationTree`, `getCurrentPath()` returns the path to the call. When the scanner is at `IdentifierTree names`, the path goes to **that identifier itself**.

Core API:

```java
Element element = trees.getElement(path);
TypeMirror type = trees.getTypeMirror(path);
```

These two lines are an **illustrative snippet where `Trees trees` and `TreePath path` already exist**, not a standalone program. Results can differ between two paths even when the nodes are in the same statement.

**Do not construct a `TreePath` arbitrarily while holding only a `Tree` reference**. Use `TreePathScanner` to maintain the path during traversal, or APIs like `Trees.getPath(element)` / `TreePath.getPath(compilationUnit, tree)` when sufficient information is available.

## 3. Core APIs of Trees

Commonly used methods of `com.sun.source.util.Trees`:

| API | Result | Notes |
| --- | --- | --- |
| `Trees.instance(JavacTask)` | Bridge to a compiler task using javac | Used in compiler API tools explicitly calling parse/analyze |
| `Trees.instance(ProcessingEnvironment)` | Bridge for the annotation processing environment | Used inside a processor when the implementation supports Trees |
| `trees.getElement(TreePath)` | `Element` associated with the tree node | May be `null` if there is no symbol or it is unresolved |
| `trees.getTypeMirror(TreePath)` | `TypeMirror` of the tree node | May be `null` or an error type when information is insufficient |
| `trees.getPath(Element)` | Path to the element's declaration | May be `null` when there is no corresponding source |
| `trees.getPath(CompilationUnitTree, Tree)` | Path to a node belonging to the given unit | Use only when the unit and node are clearly known |
| `trees.getTree(Element)` | Declaration tree corresponding to the element | May be `null` for elements without source |
| `trees.getSourcePositions()` | Query utility for tree source offsets | Used with unit and `LineMap` to get line/column |
| `trees.printMessage(...)` | Diagnostic attached to a `Tree` | Useful when highlighting a specific expression/syntax |

**Note on parameter types:** `Trees.getTypeMirror` here accepts a **`TreePath`**, not an `Element` or a standalone `Tree`. `Element.asType()` also returns a `TypeMirror`, yet returns **the type associated with the declaration**; it does not substitute for the concrete type of an expression at a use site.

Some methods can throw `IllegalArgumentException` if passed a `TreePath` unsuitable for the requested object; the APIs can also return `null` when information is unavailable. Analysis tools should handle both cases intentionally instead of blindly casting or calling `toString()` unchecked.

## 4. Workflow with JavaCompiler: parse → analyze → scan

When using `javax.tools.JavaCompiler`, there are two common modes of operation:

1. **Compiling Java files normally:** the compiler performs analysis and generates class files automatically.
2. **Writing a source analysis tool:** obtain a `JavacTask`, call `parse()` and `analyze()`, then use `Trees` to query node semantics.

The second mode is suited for demonstrating *Tree → Element/TypeMirror*. Parsing syntax alone does not guarantee complete symbols/types: the compiler may not have resolved names, generics, overloads, or imports yet. `analyze()` instructs the compiler to perform semantic analysis for the task.

```text
JavaCompiler + JavaFileObject
            |
            v
JavacTask.parse()  ---> CompilationUnitTree
            |
            v
JavacTask.analyze() ---> symbol/type attribution
            |
            v
Trees.instance(task)
            |
            v
TreePathScanner.scan(compilationUnit, null)
            |
            +--> getCurrentPath()
                   |
                   +--> trees.getElement(path)
                   +--> trees.getTypeMirror(path)
```

`parse()` returns the syntactic source units; `analyze()` returns the analyzed declaration elements, though we do not need its return value when only analyzing the parsed `CompilationUnitTree`s. Do not call `generate()` if the goal is solely analysis. In a real tool, configure diagnostics and classpath/module path for accurate resolution.

## 5. Complete Example: Retrieving Element and TypeMirror from a Tree Node

Create the file **`TreesBridgeDemo.java`**:

```java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.net.URI;
import java.util.List;
import javax.lang.model.element.Element;
import javax.lang.model.type.TypeMirror;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class TreesBridgeDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String text;

        Source(String name, String text) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    public static void main(String[] args) throws Exception {
        String code = """
                import java.util.List;
                class Example {
                    void run() {
                        List<String> names = List.of("Ada");
                        int count = names.size();
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(null, null, null)) {
            JavacTask task = (JavacTask) compiler.getTask(
                    null,
                    files,
                    null,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new Source("Example", code)));

            Iterable<? extends CompilationUnitTree> units = task.parse();
            task.analyze();

            Trees trees = Trees.instance(task);

            for (CompilationUnitTree unit : units) {
                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitIdentifier(
                            IdentifierTree node, Void unused) {
                        if (node.getName().contentEquals("names")) {
                            Element symbol =
                                    trees.getElement(getCurrentPath());
                            TypeMirror type =
                                    trees.getTypeMirror(getCurrentPath());

                            System.out.println(
                                    "identifier=" + node.getName());
                            System.out.println(
                                    "element-kind=" + symbol.getKind());
                            System.out.println(
                                    "element-name=" + symbol.getSimpleName());
                            System.out.println(
                                    "expression-type=" + type);
                        }
                        return super.visitIdentifier(node, unused);
                    }

                    @Override
                    public Void visitMethodInvocation(
                            MethodInvocationTree node, Void unused) {
                        if (node.getMethodSelect().toString()
                                .equals("names.size")) {
                            Element method =
                                    trees.getElement(getCurrentPath());
                            TypeMirror resultType =
                                    trees.getTypeMirror(getCurrentPath());

                            System.out.println(
                                    "call=" + node.getMethodSelect());
                            System.out.println(
                                    "target-kind=" + method.getKind());
                            System.out.println(
                                    "target-name=" + method.getSimpleName());
                            System.out.println(
                                    "call-type=" + resultType);
                        }
                        return super.visitMethodInvocation(node, unused);
                    }
                }.scan(unit, null);
            }
        }
    }
}
```

This is **a standalone runnable program** on JDK 17+. Run in the directory containing the file:

```bash
javac --release 17 TreesBridgeDemo.java
java TreesBridgeDemo
```

Stdout **verified on JDK 24 with `--release 17`**:

```text
call=names.size
target-kind=METHOD
target-name=size
call-type=int
identifier=names
element-kind=LOCAL_VARIABLE
element-name=names
expression-type=java.util.List<java.lang.String>
```

The lines appear in scanner traversal order: `visitMethodInvocation` prints first, then calls `super.visitMethodInvocation` to descend into child nodes, where `visitIdentifier` encounters `names`.

The output is data **from the compiler processing the `Example` source**, not the result of running `Example.run()`. In this lab, class `Example` has no `main`; the program actually executed is `TreesBridgeDemo`, which **does not execute** `names.size()` like a normal Java application. The compiler analyzes the call semantics and gives us the symbol/type.

### Exact line-by-line analysis

| Stdout line | API | Meaning |
| --- | --- | --- |
| `call=names.size` | `MethodInvocationTree.getMethodSelect()` | Form of the method-selection expression in source |
| `target-kind=METHOD` | `trees.getElement(path).getKind()` | Compiler links the call to a method declaration |
| `target-name=size` | `Element.getSimpleName()` | Name of the resolved declaration |
| `call-type=int` | `trees.getTypeMirror(path)` | Type of the **entire call expression** `names.size()` |
| `identifier=names` | `IdentifierTree.getName()` | Identifier name appearing in source |
| `element-kind=LOCAL_VARIABLE` | `trees.getElement(path).getKind()` | The name `names` points to a local variable declaration |
| `element-name=names` | `Element.getSimpleName()` | Name of the variable symbol |
| `expression-type=List<String>` | `trees.getTypeMirror(path)` | Type of the expression referencing `names` from compile-time info |

**Conditions for output:** the program uses the exact Java source and verified JDK. `TypeMirror.toString()` for generic types may differ in formatting across compiler implementations; therefore, production tools should query `TypeKind` and use `Types`/`Elements` for type comparisons instead of comparing hardcoded `toString` strings.

## 6. Why Do getElement and getTypeMirror Not Return the Same Thing?

Consider:

```java
List<String> names = List.of("Ada");
int count = names.size();
```

On the path of **`IdentifierTree names`**:

- `getElement` links to the local variable `names`. It is a **`VariableElement`**.
- `getTypeMirror` gives the type of the `names` expression, here `List<String>`.

On the path of **`MethodInvocationTree names.size()`**:

- `getElement` links to the selected `size()` method, here having `ElementKind.METHOD`.
- `getTypeMirror` gives **the result type of the call**, which is `int`.

With a generic method call like `List.of("Ada")`, the difference is even clearer: an `ExecutableElement` describes the generic declaration and its type parameters; the type of **the call expression after type inference** can be `List<String>`. Do not take `methodElement.asType()` directly and assume it is the result type **after all type inference at the call site**.

Similarly, `Tree.toString()` giving a source-like representation can be handy for debugging, yet is insufficient to identify overloaded methods: two methods with the same name can have different parameter lists. Read the actual `ExecutableElement`, parameter types, owner, and signature when needed.

### Element has several concrete subtypes

`Element` is the general interface. Common forms:

- `TypeElement`: class, interface, enum, record, annotation type.
- `ExecutableElement`: method, constructor, and certain executable-related declarations.
- `VariableElement`: field, local variable, formal parameter, enum constant.
- `PackageElement`: package declaration.
- `ModuleElement`: named module.

Do not cast every result of `getElement` to `ExecutableElement`. Check `getKind()` or `instanceof` before casting. When source contains errors, symbols may not be as expected; handle `null` and error states.

### TypeMirror also has several subtypes

- `PrimitiveType` (e.g., `int`) has `TypeKind.INT`.
- `DeclaredType` (e.g., `java.util.List<java.lang.String>`) holds type argument information.
- `ArrayType`, `TypeVariable`, `WildcardType`, `ExecutableType`, `NoType`, and `ErrorType` serve different constructs.

`TypeMirror.toString()` is useful for logging, yet for accurate semantic checks use `TypeMirror.getKind()`, the appropriate sub-interface, and `Types.isSameType(...)` or `Types.isAssignable(...)`. Subtyping and assignability cannot always be inferred from string names.

## 7. TreePathScanner vs. TreeScanner

Both help traverse the tree, yet serve different goals.

| Scanner | Manages current path? | When is it sufficient? |
| --- | --- | --- |
| `TreeScanner<R,P>` | Does not provide `getCurrentPath()` | Only need to count/observe AST shape |
| `TreePathScanner<R,P>` | Yes, via `getCurrentPath()` when initialized properly | Need to call `Trees.getElement` / `getTypeMirror` on nodes |

An example that only counts `MethodInvocationTree`s can use `TreeScanner`. When needing to ask which method declaration a call links to, **`TreePathScanner` is usually more convenient** because it maintains the path.

Important note from the Java API: to establish the current path, start with **`scan(TreePath, p)`** or **`scan(CompilationUnitTree, p)`**. `scan(Tree, p)` is for traversing child nodes once a path exists or for the special initialization case from a compilation unit. Do not arbitrarily call `scan(methodInvocationTree, null)` on a brand-new scanner and expect `getCurrentPath()` to always be valid.

In the runnable example:

```java
new TreePathScanner<Void, Void>() {
    // overrides ...
}.scan(unit, null);
```

`unit` is a `CompilationUnitTree`, so the scanner can initialize the root path and follow child nodes. In the annotation processor later, we start from **`TreePath` of the root element**, so we use `scan(path, null)`.

### Calling super to descend into children

In an override:

```java
@Override
public Void visitMethodInvocation(
        MethodInvocationTree node, Void unused) {
    // Inspect the current node ...
    return super.visitMethodInvocation(node, unused);
}
```

`super.visitMethodInvocation` allows the scanner to continue visiting child nodes. If you just `return null` after handling a call, you may accidentally **skip child identifiers/expressions**, causing missing analysis data.

Intentionally pruning a subtree may suit certain tools, yet the intent must be explicit. That is not the default when wanting to inspect all calls.

## 8. From Element Back to Tree: getPath(Element) and getTree(Element)

`Trees` also supports the reverse direction: from a resolved `Element` to its declaration path or source tree:

```java
TreePath declarationPath = trees.getPath(element);
```

If `declarationPath != null`, you can read `declarationPath.getLeaf()` to find the tree node representing the declaration and `getCompilationUnit()` to find the source unit. You can use `trees.getTree(element)` to get the declaration tree when appropriate.

However, **a source tree is not guaranteed to always exist**:

- `java.util.List` from the JDK is known to the compiler via modules/class files, yet the task analyzing the `Example` source does not necessarily contain this class's declaration AST.
- A method used from a library JAR without source can have a completely valid `ExecutableElement`, while `trees.getPath(methodElement)` returns `null`.
- For elements generated by a processor or compiler, source/path may not exist, or may not correspond to a snippet of user-written source.

Therefore, distinguish:

```java
Element symbol = trees.getElement(useSitePath);
TreePath declaration = symbol == null ? null : trees.getPath(symbol);
```

This is an **illustrative code fragment in a context that already has `trees` and `useSitePath`**, not a complete Java file. `useSitePath` describes **the use site**, whereas `declaration` describes **the declaration site** if present. The two paths differ, even though both point to the same symbol.

This is the principle behind an IDE's **Go to Definition** feature: from the current identifier → symbol → declaration location. When no source accompanies a dependency, the IDE may open bytecode/decompiled source or metadata per the IDE's own design, not because `Trees` generates source.

## 9. Using Trees in an Annotation Processor

`Trees` has an overload:

```java
Trees trees = Trees.instance(processingEnv);
```

Inside `AbstractProcessor`, `processingEnv` is initialized when the processor receives its environment. With a compatible `javac`, `Trees` can be used to inspect the syntax inside elements seen by annotation processing.

A structural pattern:

1. Obtain an `Element` from `RoundEnvironment.getRootElements()` or the set of annotated elements.
2. Retrieve `TreePath path = trees.getPath(element)`.
3. Check that path is non-`null`: elements from the classpath may have no source AST.
4. Use `new TreePathScanner<...>() {...}.scan(path, null)` to traverse starting from the declaration site.
5. In each `visit...`, call `trees.getElement(getCurrentPath())` or `trees.getTypeMirror(getCurrentPath())` when semantic information is needed.

Do not assume **every** processor implementation across all compilers supports `com.sun.source.util.Trees`; this API applies to the compiler tree model used by the implementation. Check and provide an appropriate message if a tool does not support it.

### 9.1. Complete processor: TreeInspectorProcessor.java

Create the file **`TreeInspectorProcessor.java`**:

```java
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.TypeMirror;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class TreeInspectorProcessor extends AbstractProcessor {
    private Trees trees;

    @Override
    public synchronized void init(ProcessingEnvironment environment) {
        super.init(environment);
        trees = Trees.instance(environment);
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return false;
        }

        for (Element root : round.getRootElements()) {
            TreePath path = trees.getPath(root);
            if (path == null) {
                continue;
            }

            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitIdentifier(
                        IdentifierTree node, Void unused) {
                    if (node.getName().contentEquals("data")) {
                        Element symbol =
                                trees.getElement(getCurrentPath());
                        TypeMirror type =
                                trees.getTypeMirror(getCurrentPath());

                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.NOTE,
                                "identifier " + symbol.getSimpleName()
                                    + " = " + type);
                    }
                    return super.visitIdentifier(node, unused);
                }

                @Override
                public Void visitMethodInvocation(
                        MethodInvocationTree node, Void unused) {
                    if (node.getMethodSelect().toString()
                            .equals("data.size")) {
                        Element method =
                                trees.getElement(getCurrentPath());
                        TypeMirror type =
                                trees.getTypeMirror(getCurrentPath());

                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.NOTE,
                                "call " + method.getSimpleName()
                                    + " returns " + type);
                    }
                    return super.visitMethodInvocation(node, unused);
                }
            }.scan(path, null);
        }
        return false;
    }
}
```

The lab uses `@SupportedAnnotationTypes("*")` so the processor receives the annotation types dispatched by the compiler and processes root elements; this is for technical demonstration, **not a recommendation that production processors claim all annotations**. `return false` indicates the processor does not claim the annotation types it merely observes.

`@SupportedSourceVersion(RELEASE_17)` matches the `--release 17` parameter below. Do not switch to a newer Java source version without checking the processor's actual supported source version.

### 9.2. Source inspected by the processor

Create the file **`Sample.java`**:

```java
import java.util.List;

class Sample {
    void check() {
        List<String> data = List.of("A");
        int length = data.size();
    }
}
```

There is no `main` because this example mainly demonstrates the compiler/processor reading expressions. It is still valid Java source.

### 9.3. Compiling and running the processor

In the directory containing both files:

```bash
javac --release 17 -d proc TreeInspectorProcessor.java
javac --release 17 -processorpath proc -processor TreeInspectorProcessor -proc:only Sample.java
```

The first command compiles the processor into the `proc` directory. The second command **runs the processor inside javac**, without generating `Sample.class` due to `-proc:only`.

Diagnostic summary **verified on JDK 24, `--release 17`**:

```text
Note: call size returns int
Note: identifier data = java.util.List<java.lang.String>
```

Both compilation commands return exit code **0** in this case. The `NOTE` diagnostics are printed by the compiler (typically to stderr); they are not stdout of a `Sample.main` program.

Why does it work?

- `trees.getPath(root)` provides the syntactic location of class `Sample`.
- `TreePathScanner.scan(path, null)` descends into method `check` and its expressions.
- At `data.size()`, `trees.getElement` gives the method's element and `getTypeMirror` gives the result type `int`.
- At identifier `data`, `getElement` gives the local variable and `getTypeMirror` gives type `List<String>`.
- `Messager.printMessage(NOTE, ...)` in the lab prints info for observation; a real processor can use these results to check policy and emit `WARNING`/`ERROR` as appropriate.

**Careful:** because the example processor does not attach `NOTE` to an `Element`, the printed diagnostic lacks a specific source location. To highlight a `Tree` directly, you can use `Trees.printMessage(...)` with `CompilationUnitTree`, as shown next. For errors attached to declarations, `Messager.printMessage(kind,msg,element)` remains useful.

## 10. Attaching Diagnostics to a Specific Tree

In an annotation processor, `Messager` supports attaching messages to `Element`, `AnnotationMirror`, and `AnnotationValue`. When the issue lies in **a syntactic expression** (for instance a disallowed call), `Trees` provides:

```java
trees.printMessage(
    Diagnostic.Kind.WARNING,
    "Avoid this call in this context",
    getCurrentPath().getLeaf(),
    getCurrentPath().getCompilationUnit()
);
```

The snippet above is an illustration **inside a TreePathScanner visitor**, where `trees` and `getCurrentPath()` are valid. `CompilationUnitTree` identifies the leaf's source unit; the compiler can attach the diagnostic to the corresponding position. You do not need to manually compute line/column numbers to emit a basic positioned message.

Distinction:

| Mechanism | Target to attach location | When appropriate |
| --- | --- | --- |
| `Messager.printMessage(kind,msg,element)` | Declaration/Element | Errors on an entire class, method, or field |
| `Messager.printMessage(...,element,annotationMirror,value)` | Annotation value | Specific annotation validation |
| `Trees.printMessage(kind,msg,tree,unit)` | Tree inside a source unit | Errors on expressions/calls/source syntax |

**Do not conclude Trees is read-only.** It also supports source-aware utilities like `getSourcePositions()` and `printMessage(...)`, forming the basis for code checkers with good developer experience.

## 11. Getting Line/Column from AST with SourcePositions and LineMap

If you need to save locations for an IDE, JSON report, or navigation system:

```java
CompilationUnitTree unit = path.getCompilationUnit();
long start = trees.getSourcePositions()
                  .getStartPosition(unit, path.getLeaf());

long end = trees.getSourcePositions()
                .getEndPosition(unit, path.getLeaf());

if (start >= 0) {
    long line = unit.getLineMap().getLineNumber(start);
    long column = unit.getLineMap().getColumnNumber(start);
}
```

The snippet above **only illustrates inside a method having variables `path` and `trees`**, and is not a standalone program; `end` can be used to record the range. Unknown offsets may be represented by negative values per the API contract. Do not try to use offsets as indexes into a different `String` whose content or normalization changed, because positions will be wrong.

`TreePath` has `getCompilationUnit()` and `getLeaf()`; both objects must belong to the same compiler tree model context. Do not combine a `Tree` from compilation unit A with unit B to query positions.

### Cases where positions are missing

- Tree or Element originating from a symbol inside a JAR, with no corresponding source.
- Generated source, synthetic nodes, or nodes for which the compiler does not retain detailed positions.
- Code with syntax/semantic errors causing the tree structure to differ from expectations.

Tools should have a fallback: record the symbol name, source URI if known, or emit the diagnostic at an appropriate parent position. Do not treat `-1` as a valid line number.

## 12. How Do Source Errors and Compiler State Affect Semantics?

If calling only `parse()` without `analyze()`, the syntax tree can still be traversed to find method invocations, identifiers, and literals; however, `getElement`/`getTypeMirror` may lack complete semantic information.

If source has errors such as:

```java
class Broken {
    void f() {
        MissingType name = null;
        name.go();
    }
}
```

This snippet is **intentionally uncompilable** because `MissingType` is undefined. The compiler may produce `ErrorType` for some nodes, omit symbols, or report diagnostics; calling `getTypeMirror(path)` does not guarantee a valid DeclaredType. Handle it:

```java
Element symbol = trees.getElement(path);
TypeMirror type = trees.getTypeMirror(path);

if (symbol == null || type == null) {
    // Insufficient semantic information at this location.
}
```

The code above is an illustrative fragment where `trees` and `path` exist. Distinguish `type == null` from `type.getKind() == TypeKind.ERROR`; an `ErrorType` is still a TypeMirror object, but represents an erroneous type.

Do not run a linter and declare “no issues” simply because type queries return `null` when the source program already has errors. Collect compiler diagnostics and decide whether to proceed with type-dependent rules.

## 13. Generics: Element.asType and Trees.getTypeMirror Differ

Consider:

```java
import java.util.List;

class GenericUse {
    void consume() {
        List<String> words = List.of("A");
        String first = words.get(0);
    }
}
```

The `words.get(0)` call node binds to the `get(int)` method declaration on `List<E>`. However, at this specific call, the receiver is `List<String>`, so **the call expression's type** is `String`.

When code analysis needs to check the type of **the result at the use site**, it usually uses:

```java
TypeMirror resultType = trees.getTypeMirror(callPath);
```

Whereas `ExecutableElement` from:

```java
Element method = trees.getElement(callPath);
```

describes **the method declaration**. Calling only `method.asType()` typically yields the declaration/generic signature form, not necessarily the result type at each invocation.

For complex operations, `javax.lang.model.util.Types` supports `asMemberOf`, `isSameType`, `isAssignable`, and other type transformations; properly identify the receiver type and context. Do not compare two `TypeMirror`s using `toString()` if the decision affects tool correctness.

### Generic types can appear at multiple levels

| AST location | Possible corresponding Element | Notable TypeMirror |
| --- | --- | --- |
| `List<String> words` (declaration) | `VariableElement` of `words` | Variable type `List<String>` |
| `words` (identifier) | The same `VariableElement` | Expression type `List<String>` |
| `words.get(0)` (invocation) | `ExecutableElement` of `get` | Result type `String` |
| `"A"` (literal) | Usually no declaration Element | Literal type `String` |
| `words.get` (member selection) | Method Element | Method/member-related type at selection site |

For a literal, `getElement(path)` usually returns `null` because a literal does not reference a variable or method declaration; that **does not mean the literal has no type**. `getTypeMirror(path)` can still return a primitive type or `java.lang.String`.

## 14. Common Errors and How to Fix Them

| Symptom | Cause | How to resolve |
| --- | --- | --- |
| `getCurrentPath()` is `null` | Started `TreePathScanner` from a subtree without a root path | Use `scan(unit, null)` or `scan(path, null)` |
| `trees.getElement(path)` returns `null` | Node does not link to a symbol or compiler has not analyzed enough | Check node kind, call `analyze()` at the right time, handle null |
| `getTypeMirror(path)` returns ErrorType | Source or dependency has semantic errors | Collect diagnostics, do not assume a valid type |
| Receiving an unexpected symbol | Querying path to member select instead of invocation or vice versa | Identify exact leaf and verify node type |
| Knowing only `MethodInvocationTree.toString()` | Text comparison without resolving overloads | Use `getElement` and `ExecutableElement` |
| Wanting result type yet reading `method.asType()` | Confusing generic declaration with expression type | Use `getTypeMirror` on the invocation path |
| Cannot open source declaration | Symbol comes from class file/module, `getPath(Element)` is null | Handle the no-source case |
| Scanner does not descend into identifier | Overrode `visitMethodInvocation` without calling `super` | Traverse children when appropriate |
| Reporting wrong line/column | Pairing tree with wrong compilation unit | Use `path.getCompilationUnit()` and source positions from same task |
| NPE when traversing broken code | Missing null checks for Element/TypeMirror | Branch on missing information |
| Compiling processor cannot find `Trees` | Incompatible JDK/compiler implementation or module config | Use a JDK with `jdk.compiler` and proper config; verify API support |
| Using classloader to get TypeMirror | Confusing compile-time type with runtime reflection | Use the `javax.lang.model.type` model |
| Analyzing source against wrong libraries | Classpath/module path differs from project environment | Use the same dependencies, release, and options |

**Do not fix this by blindly casting** an Element to TypeElement or a TypeMirror to DeclaredType. Check `ElementKind`/`TypeKind`, then use the corresponding API.

## 15. Verification with JavacTask vs. Processor: Key Differences

| Aspect | JavacTask analyzing String source | Annotation processor |
| --- | --- | --- |
| Entry point | `JavaCompiler.getTask` → cast `JavacTask` | `AbstractProcessor.init/process` |
| Obtaining Trees | `Trees.instance(task)` | `Trees.instance(processingEnv)` |
| Root for traversal | `CompilationUnitTree` from `parse()` | `TreePath` from `getPath(rootElement)` |
| Semantic analysis | Call `task.analyze()` before querying | Compiler coordinates phases/rounds |
| Compiler interaction | Explicitly calls parse/analyze | Receives `RoundEnvironment` |
| Diagnostics | DiagnosticListener/Collector or `Trees.printMessage` | `Messager` and `Trees.printMessage` |
| Example goal | Standalone code checking tool | Build-time validation or source analysis |

**Do not manually call `JavacTask.analyze()` from an annotation processor** as if the processor had authority to drive all compiler phases. Inside a processor, the compiler already drives processing rounds and the element/type model; you use the objects it provides.

### Appropriate testing

- `TreesBridgeDemo` lab: run `java TreesBridgeDemo` and check both symbol and type.
- `TreeInspectorProcessor` lab: run `javac -processor ... -proc:only Sample.java` and inspect the notes from the compiler.
- Erroneous code lab: collect compiler diagnostics, verify the tool does not crash and does not emit type-dependent judgments when types are unresolved.
- Generic overload lab: change argument types and observe which method overload `Element` points to and how the invocation's `TypeMirror` changes.

## 16. Exercises with Answers

**Exercise 1: Tree and Element**

In source `service.run()`, how do `MethodInvocationTree` and `ExecutableElement` differ?

**Answer:** MethodInvocationTree describes the call structure at the source site; ExecutableElement represents the method declaration chosen by the compiler when resolving the call. One method can have many call-site Trees yet share a single declaration Element.

**Exercise 2: Why is TreePath required?**

Can you call `trees.getTypeMirror(identifierTree)` when holding only an IdentifierTree?

**Answer:** No; the Trees signature requires a `TreePath`. Use TreePathScanner to obtain the current path or build a valid path from the source unit/element.

**Exercise 3: Type of names.size()**

`names` has type `List<String>`. What type does `getTypeMirror` return at `names.size()`, and what declaration kind does `getElement` return?

**Answer:** The result type is `int`, and the element is the `size` method (`ElementKind.METHOD`).

**Exercise 4: Generic declaration and use site**

With `List<String> words` and `words.get(0)`, is calling `getElement(callPath).asType()` guaranteed to equal type `String`?

**Answer:** No. The Element describes the method declaration (which may be generic), whereas `getTypeMirror(callPath)` describes the expression type at the call site after semantic resolution.

**Exercise 5: Node without an Element**

Can a `LiteralTree` representing `42` have a `TypeMirror` of `int` even though `getElement` returns `null`?

**Answer:** Yes. A literal has a type yet does not reference a named declaration.

**Exercise 6: Reverse lookup**

`getElement` returns a method in a JDK library, and `trees.getPath(element)` returns null. Does the method not exist?

**Answer:** No. The symbol may come from a class file/module for which the current task has no source tree. Null on reverse lookup does not invalidate that the method was resolved.

**Exercise 7: Scanner scope**

A new scanner receives `scan(methodTree, null)` and `getCurrentPath()` is invalid. How to fix?

**Answer:** Start from a CompilationUnitTree or a valid TreePath, then traverse down to the node using the scanner.

**Exercise 8: Processor emitting Notes**

The processor example prints `Note: call size returns int` and `Note: identifier data = ...`. Was the Sample program executed to produce that output?

**Answer:** No. The notes are emitted during javac's annotation processing phase; `Sample` has no `main` and the command includes `-proc:only`.

**Exercise 9: Null checks and type errors**

If source is missing a type import, should the tool cast every `TypeMirror` to `DeclaredType` to continue processing?

**Answer:** No. Check for `null` and `TypeKind.ERROR`, collect diagnostics, and only apply rules when semantic information is sufficient.

## 17. Checklist for Writing Analysis Tools with Trees

- [ ] Running on a JDK with the corresponding compiler/tree API.
- [ ] Mode identified: standalone JavacTask or annotation processor.
- [ ] Properly configured `--release`, classpath, or module path.
- [ ] Using `CompilationUnitTree` or a valid `TreePath` to initialize the scanner.
- [ ] Inside the scanner, using `getCurrentPath()` at the node being queried.
- [ ] Calling `getElement` only on tree nodes that can associate with a declaration.
- [ ] Calling `getTypeMirror` only after the compiler has sufficient semantic information.
- [ ] Checking for null and `ErrorType` when source code has errors.
- [ ] Distinguishing declaration type `Element.asType()` from expression type `Trees.getTypeMirror()`.
- [ ] Not comparing generic types as text when semantic comparison is needed.
- [ ] Using `Trees.getPath(Element)` for Go to Definition, accepting when source is absent.
- [ ] Using `getSourcePositions` and `LineMap` within the same compilation unit.
- [ ] Calling `super.visit...` when needing to traverse the full subtree.
- [ ] When emitting diagnostics, attaching to the exact Tree/Element and severity.
- [ ] Testing generics, overloaded methods, missing imports, external libraries, and generated code.
- [ ] Not using internal `com.sun.tools.javac.*` when `com.sun.source.util` satisfies the requirement.

## 18. Summary and Reference Documentation

**`Tree` is syntax; `Element` is symbol/declaration; `TypeMirror` is type in the compiler model.** To connect them reliably, obtain a **`TreePath`** from `TreePathScanner` or from `Trees.getPath(...)` methods, then call `Trees.getElement(path)` and `Trees.getTypeMirror(path)` once semantic information is available.

On the same line of code, **the path to the identifier** may return `VariableElement` and `List<String>`, while **the path to the method invocation** returns `ExecutableElement` and `int`. When writing code analysis, pick the path at the right level and handle null/error types instead of using string matching as a complete semantic solution.

Official documentation:

1. [Java SE 17 — Trees](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html): `getElement`, `getTypeMirror`, `getPath`, `getTree`, `printMessage`.
2. [Java SE 17 — TreePath](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePath.html): AST path and compilation unit.
3. [Java SE 17 — TreePathScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html): AST traversal with parent context.
4. [Java SE 17 — JavacTask](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html): `parse`, `analyze`, and compiler task.
5. [Java SE 17 — Element](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html): declaration model.
6. [Java SE 17 — TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html): type model.
7. [Java SE 17 — Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html): comparing and inferring type relationships in tools.

**Workflow takeaway:** *Source node → TreePath → Trees → Element/TypeMirror → semantic checks*. Following this exact chain identifies declarations and types accurately instead of merely analyzing characters of Java code.
