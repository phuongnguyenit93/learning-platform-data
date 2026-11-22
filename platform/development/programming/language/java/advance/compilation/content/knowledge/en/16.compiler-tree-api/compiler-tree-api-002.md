# Using JavacTask to parse, analyze, and generate

## 1. Why Control Individual Phases of javac?

The regular `javac` command reads Java source, checks validity, and emits `.class` files. However, tools like IDEs, code indexers, linters, architecture analyzers, or build/test harnesses may need to **inspect syntax before type checking**, determine which method a call references, or emit bytecode only after all checks have completed.

The JDK provides `com.sun.source.util.JavacTask` in module **`jdk.compiler`**. This is the API for the `javac` compiler, allowing:

- `parse()` — parses source code into abstract syntax trees (ASTs), returning `CompilationUnitTree` instances.
- `analyze()` — completes semantic analysis, returning the analyzed `Element`s; after this step the compiler can provide resolved symbols and types.
- `generate()` — generates compiler outputs, typically `.class` files, as `JavaFileObject`s.
- `Trees.instance(task)` — connects the AST to the language model, `Element`, `TypeMirror`, and source positions.
- `addTaskListener(...)` — receives `PARSE`, `ENTER`, `ANALYZE`, `GENERATE` events and, when applicable, annotation processing events.

**Distinction:** `JavacTask` is a specialized implementation of `JavaCompiler.CompilationTask`. Not every compiler conforming to `javax.tools.JavaCompiler` is required to provide `JavacTask`. `ToolProvider.getSystemJavaCompiler()` on a JDK with `javac` typically returns a task that can be cast to `JavacTask`, though you should check with `instanceof`.

This lesson introduces the three phases and a Java 17+ example verified on OpenJDK 21: reading classes/methods from the AST, reading types after analysis, generating the class, and then executing it.

## 2. Reading the Three Layers of a Compilation Run Correctly

| Step | API | Data obtained | What is not yet guaranteed |
| --- | --- | --- | --- |
| **Parse** | `JavacTask.parse()` | `CompilationUnitTree`, `ClassTree`, `MethodTree`, `VariableTree`, and other nodes | All names/types are resolved; the program is semantically valid |
| **Analyze** | `JavacTask.analyze()` | Analyzed `Element`s; name, type, and constraint info | All `.class` files have been emitted |
| **Generate** | `JavacTask.generate()` | `JavaFileObject` for generated files | The program can run on every runtime/classpath |

Mental model:

```text
Java source (.java)
       |
       v
PARSE
       | CompilationUnitTree, ClassTree, MethodTree
       v
ENTER + ANALYZE
       | Element, TypeMirror, symbol resolution, diagnostics
       v
GENERATE
       | .class output / JavaFileObject
       v
Runtime (separate step, if test execution is needed)
```

The diagram is not an exhaustive description of every internal phase of `javac`. The compiler may process multiple source files, implicitly discovered sources, annotation processing rounds, ENTER, and other auxiliary work. A `parse()` or `analyze()` call may also trigger additional work required for the compiler to finish that phase.

It is especially important to remember that **`JavacTask.generate()` differs from an annotation processor's `Filer.createSourceFile(...)`**. The former creates compiler output; the latter lets a processor generate new Java source for subsequent rounds.

## 3. Where Are the APIs, and Why Should You Avoid Internals?

| Component | Module | Role |
| --- | --- | --- |
| `javax.tools.JavaCompiler`, `StandardJavaFileManager`, `DiagnosticCollector` | `java.compiler` | Create tasks, manage files and diagnostics |
| `javax.lang.model.element.Element`, `TypeElement`, `ExecutableElement` | `java.compiler` | Declarations and methods understood by the compiler |
| `javax.lang.model.type.TypeMirror`, `Types` | `java.compiler` | Java types and type-relationship checks |
| `com.sun.source.tree.*` | `jdk.compiler` | AST (syntax tree) interfaces |
| `com.sun.source.util.JavacTask`, `Trees`, `TreePathScanner` | `jdk.compiler` | Compiler phases and tree–symbol–type bridging |
| `com.sun.tools.javac.*` | Compiler implementation details | Internal classes that should not be treated as stable APIs |

The package name `com.sun.source` can easily be mistaken for internal compiler classes, yet this is the **JDK-published Tree API**. It differs from reaching deep into `com.sun.tools.javac.*`, which is subject to module encapsulation and changes across versions.

When the host program is a **named module**, it typically needs:

```java
module source.inspector {
    requires java.compiler;
    requires jdk.compiler;
}
```

This is an illustrative `module-info.java`, not an entire project. `java.compiler` provides the standard APIs, while `jdk.compiler` provides `JavacTask` and the Tree API. You do not need to blindly add `--add-exports` to use exported public APIs.

**The host tool's module is not the same as the module the tool is analyzing.** A host can use `jdk.compiler` to inspect Java 17 source code that itself does not use compiler APIs.

## 4. Safely Initializing JavacTask

The common approach is to use the JSR 199 `JavaCompiler` API:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("No system compiler");
}

try (StandardJavaFileManager files =
         compiler.getStandardFileManager(diagnostics, null, null)) {
    files.setLocationFromPaths(
            StandardLocation.CLASS_OUTPUT, List.of(outputDirectory));

    var inputs = files.getJavaFileObjectsFromPaths(
            List.of(sourceFile));

    JavaCompiler.CompilationTask compilationTask =
            compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, inputs);

    if (!(compilationTask instanceof JavacTask task)) {
        throw new IllegalStateException("Not a javac task");
    }

    var parsed = task.parse();
    task.analyze();
    var generated = task.generate();
}
```

**This is an illustrative snippet**, not runnable on its own: `diagnostics`, `outputDirectory`, `sourceFile`, and imports are not declared. A complete example is in section 6.

Key decisions:

1. `getSystemJavaCompiler()` can return `null` if the host runtime image does not include a system compiler; run with an appropriate JDK.
2. `getStandardFileManager(...)` provides a file manager capable of creating compilation units from `Path`; close the file manager when the task finishes.
3. `CLASS_OUTPUT` is where class files are written; it is not automatically the host's runtime classpath.
4. `--release 17` constrains language level, class-file format, and Java SE APIs for Java 17.
5. `-proc:none` disables annotation processing in the example, so generated sources do not change the number of classes or phases. If actual processors are needed, do not pass this flag.
6. `getTask(..., options, classes, compilationUnits)` takes distinct parameters; `options` is **not** the list of source file names; `compilationUnits` holds the source `JavaFileObject`s.
7. Casting to `JavacTask` must reflect the provider in use. For other compilers, use the standard APIs they provide rather than forcing a cast.

## 5. One Compilation Task: Choosing call() or the Three Phases

For builds that do not need intermediate analysis:

```java
boolean success = Boolean.TRUE.equals(
        compilationTask.call());
```

`call()` executes the entire task, returns success/failure, and by compilation task contract may only be called **once**.

For tools that want phase-level control:

```java
Iterable<? extends CompilationUnitTree> units =
        task.parse();
// Inspect the AST...

task.analyze();
// Read Elements and Types...

Iterable<? extends JavaFileObject> outputs =
        task.generate();
// Check outputs...
```

**Do not** follow a “`parse` → `analyze` → `generate` → `call`” sequence on the same task: `call` and the three phase methods are two different ways to drive compilation, not two cumulative compilation passes. Choose one strategy and create a **new task** if you want to run another compilation.

The phase-specific methods can throw `IOException` and `IllegalStateException` if the compiler is not in a permitted state. Do not treat a task as a stateless object on which parse/analyze/generate can be called repeatedly at will.

## 6. Complete Verified Example: PhaseDemo.java

The following program creates `example.Greeter` under a temporary directory, uses JavacTask across the three phases, reads the class/method, confirms types from the semantic model, retrieves the `Element` from `MethodTree`, generates `Greeter.class`, and uses a separate classloader to verify the method returns `Hello, Ada`.

Create the file **`PhaseDemo.java`**:

```java
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePath;
import com.sun.source.util.Trees;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class PhaseDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("javac-phase-");
        Path src = Files.createDirectories(
                root.resolve("src/example"));
        Path out = Files.createDirectories(root.resolve("out"));
        Path source = src.resolve("Greeter.java");

        Files.writeString(source, """
                package example;
                public class Greeter {
                    private final String name;
                    public Greeter(String name) {
                        this.name = name;
                    }
                    public String hello() {
                        return "Hello, " + name;
                    }
                }
                """);

        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "No system compiler in runtime image");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager fm =
                 compiler.getStandardFileManager(
                         diagnostics, null, null)) {
            fm.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(out));

            var inputs = fm.getJavaFileObjectsFromPaths(
                    List.of(source));

            JavaCompiler.CompilationTask raw = compiler.getTask(
                    null, fm, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, inputs);

            if (!(raw instanceof JavacTask task)) {
                throw new IllegalStateException(
                        "Compiler provider is not javac");
            }

            // PHASE 1: Parse into AST.
            Iterable<? extends CompilationUnitTree> parsed =
                    task.parse();
            CompilationUnitTree unit = parsed.iterator().next();

            ClassTree clazz = null;
            for (Tree declaration : unit.getTypeDecls()) {
                if (declaration instanceof ClassTree c) {
                    clazz = c;
                    break;
                }
            }
            if (clazz == null) {
                throw new IllegalStateException(
                        "No class declaration");
            }

            MethodTree helloTree = null;
            for (Tree member : clazz.getMembers()) {
                if (member instanceof MethodTree method
                        && method.getName().contentEquals("hello")) {
                    helloTree = method;
                }
            }
            if (helloTree == null) {
                throw new IllegalStateException(
                        "Missing hello method");
            }

            System.out.println(
                    "parsed=" + clazz.getSimpleName());

            // PHASE 2: Resolve declarations and types.
            task.analyze();
            TypeElement type = task.getElements()
                    .getTypeElement("example.Greeter");
            if (type == null) {
                throw new IllegalStateException(
                        "Type was not resolved");
            }

            ExecutableElement hello = null;
            for (Element element : type.getEnclosedElements()) {
                if (element.getKind() == ElementKind.METHOD
                        && element.getSimpleName()
                                .contentEquals("hello")) {
                    hello = (ExecutableElement) element;
                }
            }
            if (hello == null) {
                throw new IllegalStateException(
                        "Method was not resolved");
            }

            System.out.println(
                    "analyzed=" + type.getQualifiedName());
            System.out.println(
                    "returnType=" + hello.getReturnType());

            Trees trees = Trees.instance(task);
            TreePath methodPath =
                    TreePath.getPath(unit, helloTree);
            Element fromTree = trees.getElement(methodPath);
            System.out.println(
                    "treeElement=" + fromTree.getSimpleName());

            // PHASE 3: Generate .class.
            List<JavaFileObject> generated = new ArrayList<>();
            task.generate().forEach(generated::add);

            System.out.println(
                    "generated=" + generated.size());
            System.out.println(
                    "classExists=" + Files.isRegularFile(
                            out.resolve("example/Greeter.class")));

            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d ->
                            d.getKind() == Diagnostic.Kind.ERROR)
                    .count();
            System.out.println("errors=" + errors);
        }

        // Runtime execution step separate from the compiler.
        try (URLClassLoader loader = new URLClassLoader(
                 new URL[] { out.toUri().toURL() },
                 ClassLoader.getPlatformClassLoader())) {
            Class<?> compiled = Class.forName(
                    "example.Greeter", true, loader);
            Object instance = compiled
                    .getConstructor(String.class)
                    .newInstance("Ada");
            Object result = compiled
                    .getMethod("hello")
                    .invoke(instance);
            System.out.println("result=" + result);
        }
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac --release 17 PhaseDemo.java
java PhaseDemo
```

**Exact stdout, verified on OpenJDK 21:**

```text
parsed=Greeter
analyzed=example.Greeter
returnType=java.lang.String
treeElement=hello
generated=1
classExists=true
errors=0
result=Hello, Ada
```

The example creates a new temporary directory on each run, with `src/example` and `out` subdirectories. The program does not print the temp path and does not delete the output immediately, making manual inspection of the class file possible if desired. `URLClassLoader` is used solely to test-run the newly generated artifact; it is not a security sandbox.

### Exact explanation of the output

- `parsed=Greeter`: the `Greeter` class was found in the AST via `CompilationUnitTree.getTypeDecls()`.
- `analyzed=example.Greeter`: the compiler model now has a `TypeElement` with the matching qualified name.
- `returnType=java.lang.String`: the `hello` method was resolved and has return type `String`.
- `treeElement=hello`: `Trees.getElement(TreePath)` links the method tree in source to the semantic element.
- `generated=1`: this example has one top-level class output; do not infer every compilation produces exactly one file.
- `classExists=true`: `out/example/Greeter.class` was written.
- `errors=0`: there were no ERROR diagnostics in that compilation.
- `result=Hello, Ada`: the new class was loaded and the method returned the expected result at runtime.

If source contains nested or anonymous classes, class outputs can outnumber top-level source classes. If errors occur, the compiler may return a partial AST or emit partial outputs; do not treat the presence of an output file as sufficient proof that the build succeeded.

## 7. Parse: Reading the AST Without Resolving All Type Names Yet

`parse()` returns `CompilationUnitTree` instances representing compilation units. Each unit has:

- `getPackageName()` and package-related metadata;
- `getImports()`;
- `getTypeDecls()` for iterating over declarations;
- `getSourceFile()` pointing to the corresponding `JavaFileObject`;
- `getLineMap()` for converting offsets to line/column.

Common Tree subtypes:

| Tree | Representation in source code |
| --- | --- |
| `ClassTree` | Class/interface/record/enum declaration |
| `MethodTree` | Method or constructor declaration |
| `VariableTree` | Field, parameter, local variable declaration |
| `MethodInvocationTree` | Method invocation |
| `NewClassTree` | Object creation expression |
| `ParameterizedTypeTree` | Type using type arguments, e.g., `List<String>` |
| `IfTree`, `ForLoopTree`, `ReturnTree` | Statements |
| `ErroneousTree` | Erroneous syntax portion during parser recovery |

Suppose source has:

```java
List<String> values = List.of("A", "B");
```

The parser can construct a tree for the declaration and parameterized type, yet whether `List` is properly imported and whether `List.of` is available for the target `--release` must be verified in the analyze phase.

If the source has syntax errors, the compiler may **still return an AST containing `ErroneousTree`**, while emitting diagnostics. Do not infer from “`parse()` returned an iterable” that “the source code is definitely valid”.

### Parsing multiple files

In the example, only one `JavaFileObject` was passed, so `iterator().next()` could be used. With multiple files:

```java
for (CompilationUnitTree unit : task.parse()) {
    System.out.println(unit.getSourceFile().getName());
}
```

This is an illustrative snippet in a host that has created `task`. Do not take only the first unit when building a code indexer for an entire project. The compiler can also read additional source dependencies or generated sources depending on configuration.

## 8. Analyze: Moving from Syntax to a Semantic Model

In the analyze phase, the compiler performs name resolution, type checking, generic constraints, access control, overload resolution, and necessary checks. Related APIs:

- `task.getElements()` to query declarations such as `TypeElement`.
- `task.getTypes()` to compare types, assignability, subtyping, and erasure.
- `Trees.instance(task)` to associate an AST node with an `Element` or `TypeMirror`.
- `DiagnosticCollector` to receive type errors or unresolved name messages.

For example, a `MethodTree` named `hello`. At parse, we only know a method node with that name exists; after analyze, `ExecutableElement` lets us read its return type, parameters, modifiers, and relationships to other methods.

### How does Element differ from Tree?

| `Tree` | `Element` |
| --- | --- |
| A syntactic location/construct in source | A declaration in the semantic language model |
| Suitable for source transformations, statement and expression structure | Suitable for qualified names, modifiers, parameter/return types |
| Can exist when source is not yet properly resolved | May be missing/incomplete when source has errors |
| Traversed with `TreeScanner`/`TreePathScanner` | Traversed via `getEnclosedElements()`, `Elements` utility |
| Has source offsets when paired with `CompilationUnitTree` | Does not represent the original source text character by character |

`Element` is not `java.lang.Class<?>`. When analyzing code that has not finished compiling, do not use `Class.forName(...)` as a substitute for `Elements.getTypeElement(...)`.

### TypeMirror and Types

`Trees.getTypeMirror(TreePath)` returns the type of the corresponding node once the compiler has semantic information. For example, the expression `"Hello, " + name` in `Greeter.hello()` has type `java.lang.String`, while the expression `42` has primitive type `int`, an array has `ArrayType`, and a generic type variable has `TypeVariable`.

Do not cast every `TypeMirror` to `DeclaredType`; check `getKind()` or use type visitors. When needing to check assignability:

```java
boolean allowed = task.getTypes().isAssignable(fromType, toType);
```

This is an illustrative snippet with two resolved `TypeMirror` instances. Comparing the strings `fromType.toString()` and `toType.toString()` cannot replace semantic rules on generics, inheritance, and conversions.

## 9. TreePath, Trees, and TreePathScanner

A `Tree` represents a syntactic node, yet the node needs the context of its package, enclosing class, imports, and declarations. `TreePath` holds the path from `CompilationUnitTree` to the node; through it `Trees` can return the symbol and type of the node.

The snippet used in the example:

```java
Trees trees = Trees.instance(task);
TreePath path = TreePath.getPath(unit, helloTree);
Element method = trees.getElement(path);
```

`Trees.getElement(path)` may return `null` if the node has no corresponding element or could not be resolved. Do not cast or read `getSimpleName()` without checking for null in a real tool handling erroneous source.

### Traversing multiple nodes

A helper counting method invocations:

```java
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.TreePathScanner;

public final class CallCounter extends TreePathScanner<Void, Void> {
    private int calls;

    @Override
    public Void visitMethodInvocation(
            MethodInvocationTree tree, Void unused) {
        calls++;
        return super.visitMethodInvocation(tree, unused);
    }

    public int count() {
        return calls;
    }
}
```

This is a valid helper class, to be used inside a host that has a `CompilationUnitTree unit`:

```java
CallCounter scanner = new CallCounter();
scanner.scan(unit, null);
System.out.println(scanner.count());
```

There is no fixed count across all Java files; the number of call nodes depends on the AST. Inside the visitor, `getCurrentPath()` enables calling `Trees.getElement(...)` or `Trees.getTypeMirror(...)` after analyze:

```java
@Override
public Void visitMethodInvocation(
        MethodInvocationTree tree, Void unused) {
    Element callee = trees.getElement(getCurrentPath());
    if (callee != null) {
        System.out.println("callee=" + callee);
    }
    return super.visitMethodInvocation(tree, unused);
}
```

**This is a code fragment inside a `TreePathScanner` having a `Trees trees` field**, not a complete class. `TreePathScanner` maintains the path while traversing. Use plain `TreeScanner` when the current path is not needed.

## 10. Source Positions and Diagnostics

### DiagnosticCollector

`DiagnosticCollector<JavaFileObject>` collects structured errors and warnings:

```java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.err.println(
            d.getKind() + " " + d.getLineNumber()
            + ":" + d.getColumnNumber()
            + " " + d.getMessage(null));
}
```

This snippet assumes a host with `diagnostics`. Line/column may carry sentinel values if a diagnostic is not attached to a source position; messages may depend on version/locale. When writing tests, compare the error kind or diagnostic code and meaningful parts rather than hardcoding every sentence verbatim.

### SourcePositions

`Trees.getSourcePositions()` gives the offset of a Tree node inside a `CompilationUnitTree`:

```java
long start = trees.getSourcePositions()
        .getStartPosition(unit, helloTree);
long end = trees.getSourcePositions()
        .getEndPosition(unit, helloTree);
```

This snippet uses `trees`, `unit`, and `helloTree` from the full example. Offsets are based on character positions in source, **not** automatically UTF-8 byte offsets. A position may be unavailable and reported as a negative value. Use the line map when the position is valid:

```java
long line = unit.getLineMap().getLineNumber(start);
long column = unit.getLineMap().getColumnNumber(start);
```

Do not use offsets from an old AST to edit a file that has changed since parsing. `Tree.toString()` is only a debug representation and does not guarantee preservation of original whitespace, comments, or formatting; to write code actions, keep a source snapshot and apply controlled source edits.

## 11. TaskListener and Phase Events

`JavacTask` has `addTaskListener(...)` and `setTaskListener(...)`. The listener receives `started(TaskEvent)` and `finished(TaskEvent)` callbacks as the compiler performs operations.

Example registering in the host **before `task.parse()`**:

```java
task.addTaskListener(new com.sun.source.util.TaskListener() {
    @Override
    public void started(com.sun.source.util.TaskEvent event) {
        System.out.println("START " + event.getKind());
    }

    @Override
    public void finished(com.sun.source.util.TaskEvent event) {
        System.out.println("END " + event.getKind());
    }
});
```

Useful kinds:

| Kind | Meaning |
| --- | --- |
| `PARSE` | Parsing a source file |
| `ENTER` | Entering declarations/symbols |
| `ANALYZE` | Semantic analysis |
| `GENERATE` | Generating compiler output |
| `ANNOTATION_PROCESSING` | Annotation processing overall |
| `ANNOTATION_PROCESSING_ROUND` | One annotation processing round |
| `COMPILATION` | Overall event for a normal compilation pass |

Do not assume each kind occurs exactly once; multiple classes and multiple source files can generate multiple events. According to `TaskEvent.Kind` documentation, **`COMPILATION` is not emitted when explicitly calling `JavacTask.parse()`, `analyze()`, or `generate()`**. Hence, the absence of this event does not mean the task did not run.

Do not invoke phase methods on the same task inside a listener to try to drive the compiler mid-callback. Listener APIs are for observation, avoiding reentrant compilation or unexpected state changes.

## 12. Analyzing Erroneous Source: The AST Can Still Exist

Source with valid syntax but type errors:

```java
package demo;
public class Broken {
    int value() {
        return "a string";
    }
}
```

This is an example **intentionally written not to compile**. `parse()` can return a `ClassTree` and `MethodTree`; by `analyze()` the compiler notices `String` cannot be returned as `int` and emits an error.

Source with syntax errors:

```java
public class Unclosed {
    void run() {
        System.out.println("x");
```

This is also an example **intentionally invalid**; the parser may partially recover and create an `ErroneousTree`, but there is no contract forcing it to recover the exact same shape across every JDK.

For an IDE linter that needs to operate on code being typed, it is crucial:

- Do not ignore diagnostics just because parse returned trees.
- Do not assume `Trees.getElement(...)` is always non-null.
- If `TypeMirror.getKind() == ERROR`, the type is unresolved; it may be due to missing dependencies/classpath or generated sources not yet existing.
- Do not publish class artifacts when the task has errors and output was only partially created.
- Re-evaluate the full compilation environment when source changes; do not cache `TreePath` and symbols indefinitely.

## 13. Are Annotation Processing and generate the Same Thing?

**No.** `JavacTask.generate()` is the phase that emits compiler outputs such as `.class` files. Annotation processors run under **JSR 269**, using `Filer.createSourceFile(...)` to create new source files; the compiler can pick up that source in the next round.

| Task | API | Typical output |
| --- | --- | --- |
| Parse source into AST | `JavacTask.parse()` | `CompilationUnitTree` |
| Resolve/check types | `JavacTask.analyze()` | `Element`, `TypeMirror`, and diagnostics |
| Generate class files | `JavacTask.generate()` | `JavaFileObject` for `.class` |
| Generate Java source from annotations | `ProcessingEnvironment.getFiler().createSourceFile(...)` | New `.java` fed into compilation |
| Edit text in source files | Separate source-edit mechanism | No standard `Tree.setBody(...)` method |

In the PhaseDemo example we enabled `-proc:none`. If you want to enable an already-instantiated processor, you can do:

```java
JavaCompiler.CompilationTask raw = compiler.getTask(
        null, fm, diagnostics,
        List.of("--release", "17"), null, inputs);

raw.setProcessors(List.of(new MyProcessor()));
JavacTask task = (JavacTask) raw;
task.parse();
task.analyze();
task.generate();
```

This is an **illustrative** configuration snippet assuming `MyProcessor` exists, is already loaded in the host JVM, and can be executed; `setProcessors` must be called before starting the phases, and `-proc:none` must not be set at the same time. The processor may emit sources, classes, or resources depending on its design.

`com.sun.source.tree.Tree` is an interface for observing syntax, not a general API to arbitrarily mutate the AST and force `generate()` to write bytecode from a custom-modified tree. If you need to generate new code, use Filer or create separate source files; if you need to modify user code, use an appropriate source-rewrite tool instead of relying on javac internals.

## 14. Multiple Sources and Modules Can Make Output Count Differ from Input Count

In projects there are usually multiple files:

```java
var units = files.getJavaFileObjectsFromPaths(
        List.of(mainSource, helperSource));
```

This is an illustrative snippet; the `Path`s/`StandardJavaFileManager` must exist. `parse()` can return multiple `CompilationUnitTree`s. `generate()` can return more files than compilation units due to nested/anonymous classes or generated code; do not use a “one Java file = one class file” formula.

With implicitly discovered source dependencies, classpath, source path, `-Xprefer`, and `-implicit` can affect which files are read and which outputs are created. For reproducibility, record source inputs, JDK version, options, dependencies, and a clean output directory.

For named modules:

- `module-info.java` has a `ModuleTree`; you cannot assume every compilation unit has a `ClassTree`.
- `MODULE_SOURCE_PATH` is where source modules reside; `MODULE_PATH` is where compiled module dependencies reside.
- `requires`, `exports`, and module readability can affect analyze results.
- Output can be organized per named module. The runtime needs the right module-path/layer, not just `URLClassLoader` like the classpath demo.

**Do not mechanically copy PhaseDemo's classpath loading to run a named module**; that is a separate runtime/module-layer problem.

## 15. Building Larger Tools: Lifecycle, Caching, Concurrency, and Performance

A `JavacTask` represents **a single compilation snapshot**, not an unlimited multi-call compiler server. Design rules worth keeping:

1. Create a new task for each independent compilation/analysis; choose either `call()` or explicit phases.
2. Do not share one task across threads concurrently calling `parse/analyze/generate`; manage file managers and output directories when running in parallel.
3. Close the file manager per lifecycle; when runtime-testing new classes, close the classloader after use.
4. Do not keep `Element`, `TypeMirror`, or `TreePath` from an old task across source changes and assume they updated.
5. If only doing syntax indexing, stop at `parse` to save work; if semantic accuracy is required, run `analyze` with the full classpath/module path.
6. Only call `generate` when class files are actually needed; build artifacts are not a prerequisite for a syntax linter to work.
7. Collect diagnostics structurally; do not use `System.out` from the compiler as the sole error data source.
8. Avoid running untrusted annotation processors; a processor is code executing in the build environment and can read resources/environment.
9. Pin compiler version, options, input hashes, and outputs when reproducibility is the goal.
10. Separate the source analysis tool from the output execution environment; compiler success does not equal runtime test success.

## 16. Quick Diagnostic Table

| Symptom | Cause | How to resolve |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Host JVM has no system compiler | Run host on a JDK/runtime image containing the compiler |
| Casting task to `JavacTask` fails | Compiler provider is not `javac` | Check `instanceof` or use standard APIs |
| IDE cannot find `com.sun.source.util` | Missing `jdk.compiler` or wrong module configuration | Use a JDK with `jdk.compiler`, named module `requires jdk.compiler` |
| `parse` returns trees yet code is still broken | Parse does not check all types | Run `analyze` and read diagnostics |
| `Trees.getElement` returns null | Node is unresolved or has no element | Check phase, TreePath, and compiler errors |
| `TypeMirror` is `ERROR` | Missing dependency or incomplete source | Check classpath/module path, generated sources |
| `generate` returns fewer files | Source has errors or has few declarations | Read diagnostics, output dir, and phases |
| `IllegalStateException` | Task/phase called at wrong time or repeatedly | Create a new task, follow lifecycle |
| Class file exists yet runtime fails to load | Missing runtime classpath/module path | Configure runtime separately |
| Listener does not see `COMPILATION` | Calling phase API directly | Observe `PARSE/ENTER/ANALYZE/GENERATE` events |
| Stale `.class` remains after build failure | Output directory was not cleaned | Use a separate/clean output dir, check diagnostics |
| Using `Tree.toString()` to edit source | Does not preserve original source text | Use positions and source snapshot/rewrite tools |
| “Generate” misunderstood as annotation codegen | Confusing compiler output with Filer | Distinguish `JavacTask.generate` from `Filer` |

## 17. Self-Check Questions

**1.** Given a `ClassTree` from `parse()`, can you conclude all type names in the class are valid?

**Answer:** No. The AST represents structure; `analyze()` and diagnostics are needed for name resolution/type checking.

**2.** To find out which method the call `service.execute()` actually references, what should you use?

**Answer:** After `analyze()`, obtain a `TreePath` for the `MethodInvocationTree` and use `Trees.getElement(path)`; handle null and resolution errors.

**3.** Is `JavacTask.generate()` the API for generating Java source from an annotation?

**Answer:** No. `generate()` emits compiler output; annotation processors use `Filer` to create sources/classes/resources.

**4.** After calling `task.parse(), task.analyze(), task.generate()`, should a tool also call `task.call()` “to be sure”?

**Answer:** No. Choose either phase control or `call()` for a given task; to compile again, create a new task.

**5.** Why is `TreePathScanner` more useful than `TreeScanner` in a semantic analysis tool?

**Answer:** Because the scanner maintains the path to the current node; APIs like `Trees.getElement/getTypeMirror` typically require a `TreePath`.

**6.** `TaskEvent.Kind.COMPILATION` does not appear, whereas `PARSE` and `GENERATE` do. Is this a bug?

**Answer:** No. The documentation specifies that the COMPILATION event is not emitted when directly using JavacTask's phase methods.

**7.** After `generate()`, `Greeter.class` exists, yet `java example.Greeter` reports there is no main method. Why?

**Answer:** The `Greeter` class only has a constructor and `hello` method, without a `public static void main` entry point. The host example uses reflection to instantiate it and invoke the method.

**8.** The source was just modified, yet the tool keeps a `TypeMirror` from the previous analyze pass. What is the problem?

**Answer:** The model belongs to the previous compilation snapshot and may be stale. You need a new task/analysis or a managed incremental mechanism.

**9.** If you only want to count `if` statements in source, do you need to call generate?

**Answer:** No. `parse` and a visitor for `IfTree` are sufficient, unless the rule also needs type semantics.

**10.** Why does the PhaseDemo example print `generated=1`, yet you should not write a general test expecting every task to emit one file?

**Answer:** The number of classes depends on multiple source units, nested/anonymous classes, annotation-generated code, and other compiler outputs. The value 1 applies only to the simple tested example.

## 18. Official Sources

- **JDK 21 JavacTask:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html — `parse()`, `analyze()`, `generate()`, compiler utilities, and listeners.
- **JDK 21 Trees:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/Trees.html — `getElement`, `getTypeMirror`, `getSourcePositions`.
- **JDK 21 TreePathScanner:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html — AST visitor with current path.
- **JDK 21 CompilationUnitTree:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/CompilationUnitTree.html — compilation unit structure.
- **JDK 21 TaskEvent.Kind:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TaskEvent.Kind.html — event kinds and note on COMPILATION.
- **JDK 21 JavaCompiler API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html — `getTask` and file manager.
- **JDK 21 javac reference:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — options such as `--release`, `-proc`, classpath, and output.

**Conclusion:** `JavacTask` lets tools drive and observe compilation in the sequence **source → AST (`parse`) → semantic model (`analyze`) → class output (`generate`)**. When implementing, follow the single-task lifecycle, use `Trees`/`TreePath` for symbols and types, inspect diagnostics, distinguish annotation source generation from bytecode generation, and run only up to the phase actually needed.
