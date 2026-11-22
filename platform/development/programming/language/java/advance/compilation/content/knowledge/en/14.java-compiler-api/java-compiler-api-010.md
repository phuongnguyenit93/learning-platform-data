# Distinguishing Standard APIs from Internal javac Implementation Classes

## 1. Objectives and Key Takeaway

When writing Java compilation tools, a question arises very early: **should you call javax.tools.JavaCompiler, use com.sun.source.*, or import com.sun.tools.javac.* directly?** These three groups do not share the same compatibility commitment.

- **Standard Java SE APIs**: public interfaces and classes such as javax.tools.JavaCompiler, javax.tools.ToolProvider, javax.tools.JavaFileObject, javax.annotation.processing, and javax.lang.model. They describe the programming *contract* for compilers, file managers, diagnostics, and annotation processing.
- **Public JDK APIs, tied to javac**: typified by com.sun.source.tree and com.sun.source.util, exported by module jdk.compiler. They are documented by the JDK for inspecting syntax trees, traversing the AST, and observing javac phases, yet **not all of them belong to the Java SE standard**.
- **Internal javac implementation classes**: com.sun.tools.javac.api.JavacTool, com.sun.tools.javac.tree.JCTree, com.sun.tools.javac.util.Context, com.sun.tools.javac.comp.Attr... They serve how javac implements the compiler, and many packages are not publicly exported to normal applications. You should not design long-lived applications depending directly on them.

This lesson explains **how to distinguish them by module, export level, documentation, and API contract**, rather than identifying by package name prefix. You will build a Java 17 program compiling in-memory source with standard APIs, inspect diagnostics, try the JDK's public Tree API, understand why importing internal APIs is rejected, and learn how to design an adapter layer if javac-specific functionality is truly needed.

**Principle:** if requirements are met by standard APIs, prefer standard APIs. Use JDK-specific APIs only when that capability is genuinely needed and support boundaries are identified. Do not confuse a class having a public modifier inside the JDK with an API committed to your application.

## 2. Three API Layers and Corresponding Modules

~~~text
Application / build tool / IDE integration
                 |
                 | Standard Java SE API
                 v
           module java.compiler
    javax.tools.JavaCompiler
    javax.tools.JavaFileObject
    javax.annotation.processing.*
    javax.lang.model.*
                 |
                 | Service provider / compiler implementation
                 v
           module jdk.compiler
    +-----------------------------------+
    | Public JDK-specific APIs          |
    | com.sun.source.tree.*             |
    | com.sun.source.util.*             |
    +-----------------------------------+
    | Internal javac implementation     |
    | com.sun.tools.javac.api.*         |
    | com.sun.tools.javac.tree.*        |
    | com.sun.tools.javac.comp.*        |
    | com.sun.tools.javac.util.*        |
    +-----------------------------------+
                 |
                 v
             .class files
~~~

Comparison table:

| Group | Example | Containing Module | Practical Commitment Level |
| --- | --- | --- | --- |
| Java SE compiler API | javax.tools.JavaCompiler, ToolProvider, DiagnosticListener | java.compiler | Standard API, suited for contract-level compiler integration |
| Java SE annotation processing API | javax.annotation.processing.Processor, AbstractProcessor | java.compiler | Standard API for processors and processing rounds |
| Java SE language model | javax.lang.model.element.TypeElement, javax.lang.model.util.Types | java.compiler | Standard type/declaration model |
| JDK public compiler Tree API | com.sun.source.tree.CompilationUnitTree | jdk.compiler | Public JDK API, specialized for javac syntax trees |
| JDK public compiler utility API | com.sun.source.util.JavacTask, TreePathScanner, Trees | jdk.compiler | Exported JDK-specific API; not a backend-neutral JavaCompiler interface |
| Javac internal implementation | com.sun.tools.javac.api.JavacTool, JCTree, Context | jdk.compiler | Internal, not generally exported to applications; prone to change |

**Two misconceptions to eliminate:**

1. Every package starting with com.sun is internal? **No.** com.sun.source.tree and com.sun.source.util are public APIs exported by module jdk.compiler.
2. Every public class inside module jdk.compiler can be imported? **No.** JPMS also checks module exports. A public class in an unexported package still cannot be used by other applications via normal compile-time access.

## 3. java.compiler Is the Contract, jdk.compiler Is the Execution Provider

Module **java.compiler** contains standard APIs that a tool can call to request compilation or implement annotation processing. Having the JavaCompiler API itself **does not mean every runtime image has a compiler implementation**.

In a standard JDK, module **jdk.compiler** supplies a compiler implementation, and javac is the command-line tool using that compilation system. If the application runs on a stripped runtime image without a compiler provider, the following statement can return null:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
~~~

Therefore, proper code should check for null and output a message when the compiler is unavailable, instead of assuming every JVM has javac.

### How to Read Module Descriptors

On a JDK with the relevant modules, you can inspect:

~~~sh
java --describe-module java.compiler
java --describe-module jdk.compiler
~~~

In the output, look for exported packages and requires/provides relationships. With typical JDK 17+, java.compiler exports packages javax.tools, javax.annotation.processing, and javax.lang.model; jdk.compiler exports packages com.sun.source.tree, com.sun.source.util and contains the implementation serving JavaCompiler.

Some internal com.sun.tools.javac.* packages may receive **qualified exports** to certain JDK modules, yet that **does not** turn them into general exports for classpath applications or all named modules. Nor should the list of qualified exports in one JDK release be treated as a stable contract for newer releases.

### Module Descriptor When Creating a Modular Tool

If you create an explicit named module using only javax.tools and other standard APIs in java.compiler, module-info.java can declare:

~~~java
module demo.compiler.client {
    requires java.compiler;
}
~~~

This is an illustrative descriptor snippet; building requires organizing matching sources/module paths.

If the tool also actively uses com.sun.source.*, it must read **jdk.compiler**, for instance:

~~~java
module demo.javac.inspector {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

The key point is that both **requires** relationships and package **exports** matter. Adding requires jdk.compiler **does not allow** calling any unexported com.sun.tools.javac.* package.

## 4. What Problem Does javax.tools.JavaCompiler Solve?

javax.tools.JavaCompiler is the standard public interface for requesting a compiler to compile a program. You can supply sources via files or JavaFileObject, options, file managers, and diagnostic listeners, and receive a CompilationTask.

Main components:

| API | Role |
| --- | --- |
| ToolProvider.getSystemJavaCompiler() | Retrieves the system Java compiler if available |
| JavaCompiler.getTask(...) | Creates a compilation task |
| JavaCompiler.CompilationTask.call() | Executes compilation and returns Boolean |
| JavaFileObject | Abstracts source or class files |
| SimpleJavaFileObject | Convenient base class for creating custom JavaFileObjects |
| StandardJavaFileManager | Standard location/file manager, typically used with try-with-resources |
| DiagnosticCollector | Receives Diagnostics for structured application handling |
| Diagnostic.Kind | Distinguishes ERROR, WARNING, NOTE, and other diagnostic kinds |
| JavaCompiler.getStandardFileManager(...) | Retrieves the standard file manager from the compiler |

Usually, when writing source-testing applications, compile-level IDE integrations, or a tool taking Java sources and producing .class files, this is a more stable entry point than calling the internal JavacTool class directly.

### Advantages of Calling via Interface

~~~text
Application code
     |
     v
javax.tools.JavaCompiler
     |
     +-- javac implementation in the JDK
     |
     +-- another implementation if provided appropriately by the environment
~~~

The application binds to the **JavaCompiler contract**, not to javac's internal constructors or fields. When the compiler changes internal algorithms, code using only standard APIs is generally less impacted.

Distinguish clearly: **the interface itself is standard**, yet options passed to getTask can be **compiler-specific**. For example, many javac options are supported by the javac tool, yet not every JavaCompiler implementation is required to accept all javac flags. Check the compiler provider and options before relying on specific behavior.

## 5. Java 17 Project: Compiling In-Memory Sources

This example uses **only Java SE APIs** and standard java.* classes; it does not import com.sun.tools.javac.*. It compiles a valid Java class from a String, detects syntax-invalid source with DiagnosticCollector, and verifies that .class was generated.

Create directory:

~~~text
compiler-api-lab/
└── CompilerApiDemo.java
~~~

### Complete File CompilerApiDemo.java

~~~java
import java.io.IOException;
import java.io.StringWriter;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompilerApiDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String qualifiedName, String code) {
            super(URI.create("string:///" + qualifiedName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static boolean compile(JavaCompiler compiler, Path output,
            String name, String code,
            DiagnosticCollector<JavaFileObject> collector) throws IOException {
        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavaCompiler.CompilationTask task = compiler.getTask(
                    new StringWriter(), files, collector,
                    List.of("--release", "17", "-proc:none",
                            "-d", output.toString()),
                    null, List.of(new Source(name, code)));
            return Boolean.TRUE.equals(task.call());
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println("Compiler found: " + (compiler != null));
        if (compiler == null) {
            return;
        }

        Path output = Path.of("build", "classes");
        Files.createDirectories(output);

        String validCode = "package demo.gen; public class Hello {"
                + " public static String text() { return \"Hello\"; } }";
        String invalidCode = "package demo.gen; public class Broken {"
                + " public static void test() { int x = ; } }";

        DiagnosticCollector<JavaFileObject> goodDiagnostics =
                new DiagnosticCollector<>();
        boolean valid = compile(compiler, output,
                "demo.gen.Hello", validCode, goodDiagnostics);
        System.out.println("Valid compilation: " + valid);
        System.out.println("Hello.class exists: "
                + Files.isRegularFile(
                        output.resolve("demo/gen/Hello.class")));

        DiagnosticCollector<JavaFileObject> badDiagnostics =
                new DiagnosticCollector<>();
        boolean invalid = compile(compiler, output,
                "demo.gen.Broken", invalidCode, badDiagnostics);
        System.out.println("Invalid compilation: " + invalid);

        boolean errorPresent = badDiagnostics.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
        System.out.println("Error diagnostic present: " + errorPresent);
    }
}
~~~

This is a complete Java 17 program whose public class matches the filename. It creates the build/classes directory inside the project when running. Source code using Strings is supplied to the compiler via Source extends SimpleJavaFileObject; therefore there is no need to write Hello.java and Broken.java to disk beforehand.

### Compile and Run the Compiler-Controller Program

From the compiler-api-lab root, create the output directory for class CompilerApiDemo. Pick one command:

~~~bash
# Bash (Linux/macOS)
mkdir -p out
~~~

~~~powershell
# PowerShell (Windows)
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Then:

~~~sh
javac --release 17 -encoding UTF-8 -d out CompilerApiDemo.java
java -cp out CompilerApiDemo
~~~

**Exact stdout when running on JDK 17+ with system javac and project write permissions:**

~~~text
Compiler found: true
Valid compilation: true
Hello.class exists: true
Invalid compilation: false
Error diagnostic present: true
~~~

If the runtime image lacks a compiler provider, the first line is false and the program exits early; in that environment, do not expect the next four lines.

### Why Is the Output Reliable?

- ToolProvider returns an object of type JavaCompiler or null; code checks before calling.
- SourceFile uses a URI of the form string:///demo/gen/Hello.java and Kind.SOURCE so the compiler knows the logical source filename.
- JavaCompiler.getTask receives a source unit, file manager, options, and diagnostics, and creates the task.
- --release 17 instructs javac to use Java 17 language/API level and target bytecode; -proc:none disables annotation processing because the example tests only the Compiler API.
- StandardJavaFileManager is closed automatically by try-with-resources.
- Valid source produces build/classes/demo/gen/Hello.class. The compiler returns Boolean.TRUE on success.
- Invalid source has int x = ; so syntax is invalid; compile returns false and DiagnosticCollector receives at least one ERROR.
- The demo does not assume **exact error count, exact message lines, or implementation class names** of the compiler. Those details may change across JDKs.

### Why Not Print compiler.getClass().getName() as Standard Output?

The line:

~~~java
System.out.println(compiler.getClass().getName());
~~~

may reveal the specific implementation, such as javac's class name. This is only diagnostic information; **do not use implementation names to branch business logic** or expect stable output across different compilers/JDKs. The JavaCompiler interface is the type you should use.

### No Reflection Needed to Call the Compiler

If you already have a JavaCompiler, call getTask and call directly. Do not call Class.forName to locate an internal class and reflectively invoke its methods merely because you saw the implementation in a stack trace.

## 6. Key Points to Understand Deeply About the JavaCompiler API

### One CompilationTask Is Not a Standalone javac Process

CompilationTask represents a compilation job executed by the compiler implementation. In the example, the program calls task.call() synchronously. It does not require spawning a new OS process or running the javac shell command. However, the implementation may use internal resources at will; do not assume performance or thread independence that the API does not guarantee.

**Tasks must follow a one-shot contract.** If wanting to compile new sources, create a new task. Likewise, manage the file manager's lifecycle properly.

### Structured DiagnosticCollector

When javac reports errors:

~~~java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : badDiagnostics.getDiagnostics()) {
    System.out.println(diagnostic.getKind());
}
~~~

This is an illustrative snippet **inserted inside main after the failing compile pass**, not a standalone Java file. Diagnostic also provides source, line, column, code, and message depending on the compiler. When displaying to learners, use getMessage(Locale), getLineNumber(), and getSource() appropriately. Do not hardcode that every diagnostic has a source position, because some errors belong to configuration rather than a specific file.

### StandardJavaFileManager and JavaFileObject

The file manager is the layer reading/writing JavaFileObject. You can use a standard file manager to handle source files from disk, or supply JavaFileObject from memory. For finer control, JavaFileManager can be wrapped by ForwardingJavaFileManager; yet that is **extending via standard interfaces**, still without needing to call com.sun.tools.javac.util.Context directly.

### Caution When Compiling Untrusted Sources

Even though the example only compiles a String, do not mistake compilation for a **security sandbox**. Some compiler plugins or annotation processors can execute code during the build; the compiler can read/write files according to process permissions. For untrusted sources, use OS/container-level isolation, and control options, output directories, and dependencies; the JavaCompiler API itself does not provide a sandbox.

## 7. Public Tree API of the JDK: com.sun.source.*

Many tools need to **inspect the AST** rather than just knowing compilation success. The JDK provides public packages, notably:

- **com.sun.source.tree**: interfaces describing syntax trees, such as Tree, CompilationUnitTree, ClassTree, MethodTree, VariableTree.
- **com.sun.source.util**: utility APIs such as JavacTask, Trees, TreePath, TreeScanner, TreePathScanner, TaskEvent, TaskListener.

These packages are **publicly exported by module jdk.compiler**. They must not be equated with com.sun.tools.javac.tree.JCTree merely because they share the com.sun prefix.

**Distinguish accurately:**

- com.sun.source.*: API published by the JDK to access javac's syntax tree model. **JDK-specific**, not identical to Java SE javax.tools interfaces.
- com.sun.tools.javac.*: mostly internal implementation, used by javac itself and certain JDK tools granted qualified exports; not a stable extension interface for ordinary applications.

### Example Reading AST Without Touching JCTree

In the same compiler-api-lab directory, create **TreeApiDemo.java**:

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.JavacTask;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class TreeApiDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.out.println("No system compiler");
            return;
        }

        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(null, null, null)) {
            Iterable<? extends JavaFileObject> inputs =
                    files.getJavaFileObjectsFromStrings(
                            List.of("CompilerApiDemo.java"));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, null,
                    List.of("-proc:none"), null, inputs);

            if (!(task instanceof JavacTask)) {
                System.out.println("JavacTask unavailable");
                return;
            }

            for (CompilationUnitTree unit
                    : ((JavacTask) task).parse()) {
                System.out.println("Top-level declarations: "
                        + unit.getTypeDecls().size());
            }
        }
    }
}
~~~

Compile and run from the compiler-api-lab root (out already exists):

~~~sh
javac --release 17 -encoding UTF-8 -d out TreeApiDemo.java
java -cp out TreeApiDemo
~~~

**Stdout on javac/JDK 17+ used for the lesson:**

~~~text
Top-level declarations: 1
~~~

CompilerApiDemo.java has one top-level class declaration; nested classes reside inside and therefore do not increase the count of top-level declarations. Calling parse() reads syntax structure; the example does not call CompilationTask.call() to additionally generate .class files.

### Why Must You Check instanceof JavacTask?

JavaCompiler.CompilationTask is a standard interface. There is no contract that **every compiler implementation** returns an object implementing com.sun.source.util.JavacTask. With modern system javac, this cast works; if wanting to write tools that can run on other compiler implementations, handle the JavacTask unavailable case as in the example.

### Limits of the Syntax Tree API

The Tree API helps traverse nodes, identify positions, or inspect source structure; it does not commit to internal fields, memory layouts, optimization flags, or implementation classes inside javac. If needing to check types corresponding to each Tree, appropriate Trees, TreePath, and javax.lang.model can be used. Do not assume objects representing Tree can be cast to JCTree.

**Public does not mean Java SE portable:** the Tree API is a public JDK API, yet the presence of jdk.compiler and behavior of the javac system are environmental requirements of the tool.

## 8. When Are javax.annotation.processing and javax.lang.model Needed?

If the goal is **inspecting declarations/types and generating code during compilation**, many problems can be solved completely with standard annotation processing.

A processor typically extends:

~~~java
public final class MyProcessor
        extends javax.annotation.processing.AbstractProcessor {
    @Override
    public boolean process(
            java.util.Set<? extends javax.lang.model.element.TypeElement> types,
            javax.annotation.processing.RoundEnvironment round) {
        return false;
    }
}
~~~

This is an **illustrative skeleton**, not a fully configured processor or runnable class (it needs package, supported annotation types and source version, init/config if needed). It highlights the return type of process and the two standard parameters.

Related API set:

| Need | Standard API to Prefer |
| --- | --- |
| Get annotated elements | RoundEnvironment.getElementsAnnotatedWith(...) |
| Inspect class/interface/field/method | javax.lang.model.element |
| Inspect types/generics/subtypes | javax.lang.model.type and javax.lang.model.util.Types |
| Look up packages, types, annotations | javax.lang.model.util.Elements |
| Generate new sources or resources | javax.annotation.processing.Filer |
| Report compilation errors | javax.annotation.processing.Messager |
| Read -A compiler options | ProcessingEnvironment.getOptions() |

Unlike runtime Reflection, the language model represents code being compiled. For types that do not yet have .class files, using TypeElement/TypeMirror makes more sense than trying Class.forName.

**Standard API boundary:** javax.annotation.processing is designed to read the model, emit diagnostics, and generate new outputs. It does not provide a general contract to mutate arbitrary AST nodes or inject arbitrary statements into an already-written method. Some specific tools do this using compiler internals, yet that is a different strategy from standard annotation processing.

## 9. Which Classes Are Truly Internal?

Some names you may encounter when reading javac source, stack traces, or deep compiler-integration projects:

| Package/class | Role in Implementation | Why Avoid Direct Dependency? |
| --- | --- | --- |
| com.sun.tools.javac.api.JavacTool | A concrete implementation of JavaCompiler | Name/instantiation and internal members are not part of JavaCompiler contract |
| com.sun.tools.javac.tree.JCTree | javac's private AST implementation tree | Node types and fields may change across JDK releases |
| com.sun.tools.javac.util.Context | Internal service/context registry | Lifecycle and keys depend on javac |
| com.sun.tools.javac.comp.Attr | Attribution/type checking processor | Implementation detail, not a standard extension interface |
| com.sun.tools.javac.main.JavaCompiler | javac internal orchestration component | Easily coupled to phase ordering and compiler state |

The classes listed above **do not carry the same commitment level as javax.tools.JavaCompiler or com.sun.source.tree.Tree**. Even when an internal class is currently public, module jdk.compiler may still not export that package to applications.

### Testing with an Intentionally Failing Example

Create **InternalProbe.java**:

~~~java
import com.sun.tools.javac.api.JavacTool;

public final class InternalProbe {
    JavacTool tool;
}
~~~

**This is an example intentionally designed not to compile under normal configurations.** It is not part of a successfully running program.

On JDK 17+ with jdk.compiler, try:

~~~sh
javac InternalProbe.java
~~~

The diagnostic may state roughly:

~~~text
package com.sun.tools.javac.api is not visible
(package com.sun.tools.javac.api is declared in module jdk.compiler,
 which does not export it to the unnamed module)
~~~

When using:

~~~sh
javac --release 17 InternalProbe.java
~~~

a newer javac may display **package ... does not exist** instead of **is not visible**, because --release restricts the set of visible platform APIs. **Do not treat the verbatim diagnostic text as an API definition:** both cases show the source code depends on an API outside the permitted compilation contract.

If wanting to use standard interfaces instead of internal classes:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
~~~

The snippet above shows illustrative lines inside a valid method; not a complete class. This style uses the public API contract and does not need to know what name the compiler implementation uses.

### Why Is a Public Class Still Reported as Not Visible?

A package in another module is only accessible if both **module readability** and **package exports** permit it. A class having a public modifier is a separate condition and does not cross module boundaries. Java module jdk.compiler publicly exports com.sun.source.* yet does not generally export all of com.sun.tools.javac.*.

Some internal packages receive qualified exports to selected JDK modules. That serves the JDK's own design, without turning the API into a public extension point for all applications.

## 10. --add-exports and --add-opens Are Not Sustainable Design Solutions

When searching how to use JCTree or JavacTool, you may encounter command-line options:

- **--add-exports**: adds a package export at runtime or compile-time per configuration, granting access to public types in a package not otherwise exported to the caller module.
- **--add-opens**: grants permission to open a package for deep reflection at runtime.
- **--add-reads**: adds a readability relationship between modules when needed.

The options above serve many special compatibility, migration, or debugging scenarios. Yet they **create no binary/source compatibility commitment** for fields/methods of the compiler implementation.

For example, if forcing an application to depend on JCTree, merely a new JDK changing internal AST structures, constructors, fields, or methods can make the build fail, even though --add-exports is still passed accurately.

**Do not confuse --add-opens with --add-exports:** reflective access permission does not automatically make a source import valid; and permission to import a public class does not equate to permission for deep reflection into private fields.

**Note on --release:** javac does not allow certain forms of opening access to internal platform modules alongside --release. Therefore "adding --add-exports to make errors disappear" may not work with a toolchain locked to target Java 17. The right way for our exercises is **not depending on internals**.

## 11. Why Does Code Calling Internals Break Easily When Upgrading JDKs?

### Source compatibility

Internal APIs may change constructors, method names, or types. Plugin Java source code compiling on an older JDK may fail immediately when compiled on a new JDK.

### Binary compatibility

A compiled plugin may contain method/field references pointing to internal members. If a new JDK changes binary signatures or related layouts, runtime may report NoSuchMethodError, NoSuchFieldError, IllegalAccessError, or other linkage errors. There is no guarantee the error type stays the same.

### Runtime access

In a JDK with a module system and strong encapsulation, code may compile due to special flags yet fail at runtime if launchers/test runners do not grant corresponding permissions. IDE/Gradle/Maven tools that fork separate JVMs also need proper process configuration; do not assume javac command flags are automatically forwarded to the process running the plugin.

### Portability

Standard Java SE defines the javax.tools API, without requiring every Java compiler implementation to possess class com.sun.tools.javac.api.JavacTool. When code depends on one specific implementation, it restricts supported runtimes/toolchains itself.

### Maintenance and build security

Tools intervening in compiler implementation can run with build process permissions, affecting caches, diagnostics, and debuggability. A new plugin or annotation processor JAR is also a dependency executed during the build: only use trusted sources, tested versions, and clear JDK support declarations.

## 12. When Should Tools Use Each API Layer?

| What Do You Want to Do? | Recommended Choice | Note |
| --- | --- | --- |
| Compile Java source from application | javax.tools.JavaCompiler | Portable contract; check for null provider |
| Retrieve diagnostics with line/column | DiagnosticCollector and Diagnostic | Structured data, do not parse stderr with regex |
| Read class/method/field declarations at compile time | javax.lang.model via annotation processing | Fits the language model |
| Generate new source files from annotations | AbstractProcessor + Filer | Do not modify existing source inputs |
| Traverse if/for/method/class syntax | com.sun.source.tree + TreePathScanner | JDK javac-specific public API |
| Observe parse/analyze/generate events | com.sun.source.util.TaskListener | Scoped within JDK compiler public utility APIs |
| Modify internal AST nodes or alter attribution | No equivalent general Java SE API | Consider changing architecture; if using internals must lock toolchain/separate tests |
| Call compiler implementation via concrete class | Do not use if JavaCompiler interface suffices | Avoid JavacTool directly |

**Decision point:** choose the highest-level interface capable of meeting requirements. An annotation processor does not need JCTree if it only reads TypeElement, inspects TypeMirror, validates, and generates Java sources. A "compile code" application does not need to know javac uses Context or Attr.

### Is the Public AST API Enough to Modify the AST?

The public Tree API primarily supports **observing/traversing trees**. It does not provide a standard Java SE interface to alter every Tree node, restructure statements, and force the compiler to use the modified tree. If wanting to refactor source, many tools choose to parse and then generate **new source text** or use a dedicated refactoring library, instead of manipulating internal fields of JCTree.

## 13. A Perspective on JSR 199 and JSR 269

Two standards frequently mentioned in the compiler ecosystem:

- **JSR 199 — Java Compiler API**: foundation of javax.tools.JavaCompiler, JavaFileManager, JavaFileObject, and DiagnosticListener; helps applications integrate compilation as a structured task.
- **JSR 269 — Pluggable Annotation Processing API**: foundation of javax.annotation.processing and related language models; lets the compiler run processors across rounds.

They solve two different problems:

~~~text
Application A wants to invoke the compiler itself
    -> JavaCompiler.getTask(...).call()
             |
             v
            javac
             |
             +-- May run annotation processors
             |       -> AbstractProcessor.process(...)
             |       -> Filer generates new sources
             |
             +-- Compiles sources and generated sources into .class
~~~

The fact that the JavaCompiler API allows callers to request compilation **does not mean the caller automatically becomes an annotation processor**. Conversely, an annotation processor loaded by the compiler **does not necessarily have to create and invoke a new JavaCompiler itself** to generate files; it uses Filer and rounds of the current invocation.

### Using com.sun.source Alongside Standard APIs

A tool running on a JDK with javac can:

1. Use javax.tools.JavaCompiler to create a task.
2. If the task supports JavacTask, use the public API com.sun.source.util.JavacTask to parse or observe source.
3. Use com.sun.source.tree to traverse nodes.
4. Use javax.lang.model / Trees when needing to correlate the AST with the type model.

That is combining **standard APIs + JDK public APIs**, not evidence that one should keep casting tree objects to com.sun.tools.javac.tree.JCTree.

## 14. Common Errors When Migrating from Internals to Public APIs

### Error A — Cannot find symbol in javax.tools

Someone imports JavaCompiler yet calls a method specific to JavacTool, causing the compiler to report no such method. This is a sign you are using a feature **outside the JavaCompiler contract**. Check what standard APIs actually support; if needing javac-specific Tree APIs, use the corresponding public interfaces instead of forcing JavaCompiler into an internal implementation.

### Error B — package com.sun.tools.javac.* is not visible

Not a missing Maven dependency error. The package may exist right inside jdk.compiler yet not be exported to the caller module. Do not add a copy JAR of a JDK module to the classpath. Replace with javax.tools/com.sun.source or change design.

### Error C — getSystemJavaCompiler() returns null

The program may be running on a runtime image lacking a compiler provider. Check JDK/runtime image and module jdk.compiler. If the tool requires compiling Java, document the requirement for a **JDK with compiler implementation** instead of casting null.

### Error D — ClassCastException when casting CompilationTask to JavacTask

Not every compiler provider supports JavacTask. Check instanceof; if AST features exist only on javac, publish a toolchain requirement for javac, or have a fallback when another backend is used.

### Error E — IllegalAccessError / InaccessibleObjectException

Code depends on an internal package, or reflects into it, yet module flags forbid it at runtime. This is a module boundary. --add-exports/--add-opens may change outcomes in test environments yet do not create a stable public API.

### Error F — NoSuchMethodError after JDK upgrade

A library/plugin compiled against an old internal class may call a method with which the new JDK no longer maintains compatibility. Investigate **JDK version + plugin + bytecode dependencies**, rather than assuming this is an application source logic bug.

### Error G — Compiling the same source yields different diagnostics

The standard JavaCompiler interface permits multiple compiler implementations; diagnostic messages and positions/phrasing may differ. Check Diagnostic.Kind, code, source/line when available; do not depend on the entire printed English sentence.

## 15. Designing a Stable Compiler Integration Layer

Suggested architecture:

~~~text
Tool application
       |
       v
CompilationService (application-defined interface)
       |
       +-- StandardCompilationService
       |       javax.tools.JavaCompiler
       |       DiagnosticCollector
       |       JavaFileManager
       |
       +-- JavacInspectionService (optional feature)
               com.sun.source.util.JavacTask
               com.sun.source.tree.*
~~~

For features requiring javac-specific APIs, place them in a small clearly named module/component, write tests across supported JDK versions, and include capability checks. Do not let compiler internals leak into hundreds of business classes.

**If forced to use com.sun.tools.javac internals** for a specialized tool, treat it as an intentional architectural risk: lock the supported JDK scope, maintain a test matrix on every upgrade, document JVM/compiler flags, and anticipate implementation changes that may force code edits. It is not the default path for programs needing portable compiler integration.

### Concrete Principles

1. **Program to interface:** use JavaCompiler, JavaFileObject, DiagnosticListener, and the standard file manager.
2. **Handle absence of provider:** getSystemJavaCompiler() may be null.
3. **Treat options as capabilities:** do not assume an arbitrary backend accepts every javac-specific flag.
4. **Isolate JDK-specific APIs:** use com.sun.source.* in the layer needing AST; do not push down to JCTree.
5. **Test generated output:** verify .class files are created and runnable per goal, not only checking task.call()==true.
6. **Surface diagnostics:** return source/line/kind details instead of only Boolean.
7. **Keep classpath/module path explicit:** compile tasks may depend on library artifacts; avoid relying on undefined environments.
8. **Do not compile arbitrary untrusted code with broad permissions:** the compiler and plugins are part of the build attack surface.

## 16. Practice Exercises

**Exercise 1 — Classify APIs.** Place JavaCompiler, DiagnosticCollector, AbstractProcessor, TypeMirror, JavacTask, CompilationUnitTree, JavacTool, JCTree, and Context into three groups: standard Java SE, public JDK compiler APIs, and javac internals. Explain the criteria using module exports and documentation, not just package names.

**Exercise 2 — Compiler API.** Run CompilerApiDemo. Explain why a String source can be compiled into .class even without Hello.java on disk before compiling, and why Invalid compilation is false.

**Exercise 3 — Diagnostics.** Extend CompilerApiDemo to print Diagnostic.Kind, source name, and line number when there is an ERROR. Do not test by matching an entire fixed English error sentence.

**Exercise 4 — Runtime image.** Propose handling when ToolProvider.getSystemJavaCompiler() is null. What should the application report and what runtime environment does it require?

**Exercise 5 — AST.** Run TreeApiDemo. Why is the Top-level declarations result 1 even though CompilerApiDemo contains the nested class Source? State the difference between top-level declarations and member declarations.

**Exercise 6 — Internal API.** Try compiling InternalProbe without special flags. Read the diagnostic from javac. Why is JavacTool a public class yet the source still cannot import it in normal mode?

**Exercise 7 — Modules.** Write a descriptor for a tool using javax.tools. If the tool wants to import com.sun.source.util.JavacTask, which module requirement must be added?

**Exercise 8 — Redesign a plugin.** A plugin currently uses JCTree merely to find annotated methods and generate an auxiliary class. Propose migrating to AbstractProcessor, RoundEnvironment, TypeElement, Filer, and Messager. Which parts no longer need internal APIs?

**Exercise 9 — Portability.** Another JavaCompiler implementation returns a CompilationTask that is not a JavacTask. What should the program do if it only needs compilation? And what should it do if AST features are mandatory?

**Exercise 10 — JDK upgrade.** When an internal plugin hits NoSuchFieldError after a JDK upgrade, identify the data needing collection: plugin/JDK version, flags, class/member names, dependency graph, and compatibility version tests.

## 17. Checklist Before Using Compiler APIs

- Understand that java.compiler contains Java SE contracts for compiler, diagnostics, annotation processing, and language model.
- Understand that jdk.compiler provides javac's implementation and the JDK's public syntax tree APIs.
- Know that com.sun.source.* is not synonymous with com.sun.tools.javac.*.
- Do not confuse the public modifier with cross-module export access permission.
- Have used JavaCompiler.getTask(...) and CompilationTask.call() in a runnable example.
- Have checked that ToolProvider.getSystemJavaCompiler() may be null.
- Have used DiagnosticCollector instead of parsing stderr to learn compilation errors.
- Have used JavaFileObject for in-memory sources and a file manager with a clear lifecycle.
- Know that JavacTask is a JDK-specific API and do not force every CompilationTask to be a JavacTask.
- Understand that JCTree/Context/JavacTool are implementation details carrying compatibility risks.
- Know that --add-exports and --add-opens do not promote an internal API into a Java SE API.
- When needing to generate sources from annotations, prefer JSR 269 and Filer.
- When needing to observe the AST, consider com.sun.source.tree/util before internals.
- Have a strategy to test compilation, diagnostics, outputs, and JDK versions on supported toolchains.

### Standard Documentation for Further Study

- **Java SE 17 API**, module java.compiler: javax.tools.JavaCompiler, ToolProvider, JavaFileObject, StandardJavaFileManager, DiagnosticCollector; javax.annotation.processing; javax.lang.model.
- **JDK 17 API**, module jdk.compiler: com.sun.source.tree and com.sun.source.util (including JavacTask, Trees, TreePathScanner).
- **Java Platform Module System**: how requires, exports, and opens determine accessibility between modules.
- **JSR 199** and **JSR 269**: standard compiler API and annotation processing.
- **javac documentation** for the JDK in use: options --release, -proc:none, -d, --module-path, and restrictions when using internal platform APIs.

**Conclusion:** javax.tools/annotation processing/language model are standard contracts for Java tools; com.sun.source.* is the JDK's public syntax tree API; whereas com.sun.tools.javac.* is an internal implementation without the same support commitment. Choosing the right API layer for your needs will make compiler-integration tools easier to test and less likely to break on JDK upgrades.