# Distinguishing the java.compiler Module from the Implementation in jdk.compiler

In Java 9+, the **Java Compiler API** is organized under the module system. Two names frequently appear close together yet carry different responsibilities:

- **`java.compiler`**: the **Java SE standard** module defining the **interfaces, classes, and API contracts** used to invoke the compiler, receive diagnostics, model Java elements/types, and write annotation processors.
- **`jdk.compiler`**: the **JDK** module providing the **javac implementation**, the system compiler program, the corresponding service providers, and the **Compiler Tree API** for reading source code syntax trees.

An easy-to-remember analogy: **`java.compiler` is the contract; `jdk.compiler` is one party implementing that contract and additionally providing AST analysis tools**. Having the contract does not necessarily mean having an implementation in the current runtime image. And not every class appearing in the `jdk.compiler` module is a public API recommended for use.

## 1. Why Does Java Separate the API and Implementation?

An IDE manager, build tool, grading system, or code analysis tool needs a structured way to ask a compiler to compile source code. Rather than depending directly on internal classes of a specific javac version, Java provides common interfaces such as **`javax.tools.JavaCompiler`**.

A Java SE deployment environment can provide the API portion without **bundling a compiler**. For instance, an application running on a custom runtime image built with `jlink` containing only the needed modules. The absence of a compiler is a packaging choice, not a defect in the interface.

This separated design provides:

1. **Stable boundaries** for code using the Java Compiler API.
2. **Substitutability of implementations** where compilers conforming to the SPI exist.
3. **Avoiding forcing every runtime** to carry full javac code.
4. **Distinguishing standard Java SE tools** from JDK extensions for syntax tree analysis.
5. **Encapsulation** for implementation packages that javac needs to change freely as it evolves.

Consequently, the right dependency practice is: use `javax.tools` when only compilation and diagnostics are needed; choose `com.sun.source.*` when the problem requires ASTs; avoid touching internal `com.sun.tools.javac.*`.

## 2. Direct Comparison Table

| Criterion | Module java.compiler | Module jdk.compiler |
| --- | --- | --- |
| Nature | Standard Java SE API and SPI | JDK compiler implementation and syntax tree API |
| Guarantees a compiler implementation? | **No** | Provides the JDK's javac |
| Characteristic packages | `javax.tools`, `javax.lang.model.*`, `javax.annotation.processing` | `com.sun.source.tree`, `com.sun.source.util`, `com.sun.source.doctree` |
| Consumers | IDEs, build tools, JavaCompiler clients, annotation processors | The javac compiler, AST analysis tools, javac plugins |
| Compiler interface | Defines `javax.tools.JavaCompiler` | Provides the implementation of `javax.tools.JavaCompiler` |
| JDK-specific extensions | Not required to express basic compiler APIs | Includes the Tree API and concrete implementation |
| Module dependencies | Java platform dependencies | **`requires transitive java.compiler`** |
| Runtime image lacking jdk.compiler | API may still exist | Lacks this javac implementation |
| Stability scope | Java SE API | Documented public exported Tree API; internal packages lack the same guarantee |
| Client module-info.java | Usually `requires java.compiler;` | `requires jdk.compiler;` when using the Compiler Tree API |

**Do not equate module names with package names.** `java.compiler` is a module name; `javax.tools` is a package. Similarly, `jdk.compiler` is a module while Java source can use its exported packages such as `com.sun.source.tree`. A module name is not an import statement.

**Do not equate the `jdk.compiler` module with the entire `com.sun.tools.javac` namespace.** A few legacy entry points are exported, yet most classes in implementation subpackages are internal and have no compatibility guarantee.

## 3. Packages in java.compiler

The official module description page for `java.compiler` lists its exported packages:

| Package | Function |
| --- | --- |
| `javax.tools` | Invoking the compiler programmatically, supplying file objects and file managers, handling diagnostics |
| `javax.annotation.processing` | Declaring and executing annotation processing via `Processor`, `RoundEnvironment`, `ProcessingEnvironment`, `Filer`, and `Messager` |
| `javax.lang.model` | General concepts of the Java language model |
| `javax.lang.model.element` | Representing packages, classes, methods, fields, parameters, and annotations in the element model |
| `javax.lang.model.type` | Representing types, primitives, declared types, executable types, type variables, etc. |
| `javax.lang.model.util` | Utilities for working with `Elements`, `Types`, and model objects |

These are **APIs**, not the detailed parser implementation code of javac. For example, `javax.lang.model.element.TypeElement` represents a Java type declaration at the language model level; it **is not** an AST node containing every token, parenthesis, and expression structure.

### 3.1. Important interfaces/classes in javax.tools

- **`JavaCompiler`**: interface of the compiler invoked via the API.
- **`JavaCompiler.CompilationTask`**: a compilation task that can be executed via `call()`.
- **`ToolProvider`** in the `javax.tools` package: entry point to the available system Java compiler.
- **`JavaFileObject`** and **`SimpleJavaFileObject`**: abstractions for source or class files.
- **`JavaFileManager`** and **`StandardJavaFileManager`**: manage sources, class outputs, and input file paths.
- **`Diagnostic`**, **`DiagnosticListener`**, **`DiagnosticCollector`**: receive structured diagnostic kinds, messages, and positions.
- **`Tool`**: general interface for a tool invokable from Java.

These APIs enable a program to embed compilation logic **without having to parse stderr strings from the javac command**. Still, the result of a compilation task also depends on processors, classpath, file manager, compiler version, and specific options.

### 3.2. Annotation processors also rely on java.compiler

A processor is typically written with:

~~~java
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import java.util.Set;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class CheckProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        return false;
    }
}
~~~

This is an example of **a syntactically complete processor class without processing logic**, not an application with a main method to run directly. `AbstractProcessor`, `RoundEnvironment`, and `TypeElement` all come from `java.compiler`.

**Do not import implementation classes from `com.sun.tools.javac.processing` just to write an annotation processor.** The `javax.annotation.processing` API and language model keep processors decoupled from javac internals.

## 4. What jdk.compiler Actually Adds

The `jdk.compiler` module defines **the system Java compiler implementation** and the command-line `javac` equivalent. It provides service providers for:

- **`javax.tools.JavaCompiler`**, i.e., the implementation of the Java Compiler SPI.
- **`javax.tools.Tool`**, to invoke the tool via the API.
- **`java.util.spi.ToolProvider`**, to locate command-line tools by name, such as `javac`.

In addition, this module exports public packages for syntax tree access:

| Public exported package | Function |
| --- | --- |
| `com.sun.source.tree` | Interfaces representing the AST of Java code (classes, statements, expressions, types, etc.) |
| `com.sun.source.doctree` | Syntax trees of JavaDoc documentation comments |
| `com.sun.source.util` | `JavacTask`, `TreePath`, `TreePathScanner`, `Trees`, `SourcePositions`, and utilities for traversing/analyzing trees |

The `jdk.compiler` module documentation also lists package **`com.sun.tools.javac`** containing the **legacy javac API** entry point. Do not infer from this that all subpackages `com.sun.tools.javac.api`, `com.sun.tools.javac.code`, `com.sun.tools.javac.comp`, `com.sun.tools.javac.parser`... are exported public APIs. Many packages are only conditionally opened/exported to JDK modules or are not exported to application modules.

**Proper classification:**

1. **`javax.tools.`***: standard API in `java.compiler`.
2. **`com.sun.source.`***: public Compiler Tree API in `jdk.compiler`, documented yet dependent on javac/JDK.
3. **`com.sun.tools.javac.`***: mostly implementation internals; do not use as a default API dependency.

### 4.1. The requires transitive relationship

In `jdk.compiler`'s module descriptor, its dependency on `java.compiler` is **transitive**. Therefore, a module requiring `jdk.compiler` can also read `java.compiler` under JPMS readability rules.

~~~text
module tool.ast
    |
    | requires jdk.compiler
    v
jdk.compiler
    |
    | requires transitive java.compiler
    v
java.compiler
~~~

This **does not reverse**. A module declaring only `requires java.compiler;` is not automatically granted the `jdk.compiler` implementation or the Tree API.

## 5. Inspecting Modules in the Current JDK

The following commands help identify which components the JDK actually contains:

~~~bash
java -version
javac -version
java --describe-module java.compiler
java --describe-module jdk.compiler
~~~

On JDK 21, the module description output shows `java.compiler` exports `javax.tools` and `javax.lang.model.*`; while `jdk.compiler` exports `com.sun.source.*`, `requires java.compiler transitive`, and `provides javax.tools.JavaCompiler`.

**Do not treat version numbers and every output line as immutable**: `java --describe-module` may display additional requires, exports, or service providers depending on the JDK version. What needs to be verified is the access and service structure, not the exact formatting of every line.

Example module summary in JDK 21 contains lines conveying:

~~~text
java.compiler:
  exports javax.tools
  exports javax.annotation.processing
  exports javax.lang.model...

jdk.compiler:
  requires java.compiler transitive
  exports com.sun.source.tree
  exports com.sun.source.util
  provides javax.tools.JavaCompiler ...
~~~

This is an **illustrative summary**, not a verbatim stdout transcript.

To list all modules in the runtime:

~~~bash
java --list-modules
~~~

A runtime image built with `jlink` can contain `java.compiler` without containing `jdk.compiler`. Therefore, do not assume "the `java` command runs" means "javac is available in the same runtime image".

## 6. Runnable Example 1: Observing the Modules of API and Implementation

Create **ModuleProbe.java**:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
import com.sun.source.tree.Tree;

public class ModuleProbe {
    public static void main(String[] args) {
        System.out.println(JavaCompiler.class.getModule().getName());
        System.out.println(ToolProvider.class.getModule().getName());
        System.out.println(Tree.class.getModule().getName());

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println(compiler != null);

        if (compiler != null) {
            System.out.println(
                compiler.getClass().getModule().getName()
            );
        }

        System.out.println(
            java.util.spi.ToolProvider
                .findFirst("javac")
                .isPresent()
        );
    }
}
~~~

Compile and run with a **full JDK 17+**, e.g., JDK 21:

~~~bash
javac ModuleProbe.java
java ModuleProbe
~~~

**Verified standard output on OpenJDK 21:**

~~~text
java.compiler
java.compiler
jdk.compiler
true
jdk.compiler
true
~~~

Line-by-line explanation:

1. Interface `JavaCompiler` belongs to `java.compiler`.
2. Class `javax.tools.ToolProvider` also belongs to `java.compiler`.
3. Interface `com.sun.source.tree.Tree` belongs to `jdk.compiler`.
4. The system compiler is present on a full JDK, so the non-null check evaluates to `true`.
5. The actual compiler implementation object is a class in module `jdk.compiler`.
6. `java.util.spi.ToolProvider.findFirst("javac")` finds the javac tool via the service provider, so `isPresent()` is `true`.

This is **a demonstration of module ownership**, not a recommendation for applications to depend on the concrete class name returned on line 5. A different compiler implementation may use a different implementation class.

### 6.1. Two ToolProvider classes sharing the same simple name

There are **two different ToolProvider APIs** in different packages:

| Full name | Module | Role |
| --- | --- | --- |
| `javax.tools.ToolProvider` | `java.compiler` | Accesses the system compiler via `getSystemJavaCompiler()` |
| `java.util.spi.ToolProvider` | `java.base` | General service API for command-line tools, providing `findFirst("javac")` |

Do not confuse them:

~~~java
// Correct: returns JavaCompiler or null
javax.tools.JavaCompiler compiler =
        javax.tools.ToolProvider.getSystemJavaCompiler();

// Correct: returns Optional<ToolProvider> for the javac tool
var commandTool =
        java.util.spi.ToolProvider.findFirst("javac");
~~~

The above is **a code snippet placed inside a method**, not a standalone program. They share the name "ToolProvider" yet **differ in package, module, return type, and purpose**.

**`javax.tools.ToolProvider` is not the javac implementation**: it is the API class used to locate the compiler provided in the current runtime.

## 7. Runnable Example 2: Calling JavaCompiler via the Standard API

This example does not need to import `com.sun.tools.javac.*` or `com.sun.source.*`. It uses the interfaces in `java.compiler`, accepts an in-memory Java source, compiles it, and collects diagnostics.

Create **ApiCompile.java**:

~~~java
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class ApiCompile {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.out.println("No system Java compiler");
            return;
        }

        String source =
                "public class Sample { int number = 42; }";

        JavaFileObject input = new SimpleJavaFileObject(
                URI.create("string:///Sample.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(
                    boolean ignoreEncodingErrors) {
                return source;
            }
        };

        Path output =
                Files.createTempDirectory("java-compiler-demo-");

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(
                        diagnostics, null, null)) {

            Boolean ok = compiler.getTask(
                null,
                manager,
                diagnostics,
                List.of("-proc:none", "-d", output.toString()),
                null,
                List.of(input)
            ).call();

            System.out.println("compiled=" + ok);
            System.out.println(
                "diagnostics=" + diagnostics.getDiagnostics().size()
            );
            System.out.println(
                "class-file=" +
                Files.exists(output.resolve("Sample.class"))
            );
        }
    }
}
~~~

Commands:

~~~bash
javac ApiCompile.java
java ApiCompile
~~~

**Verified stdout on OpenJDK 21:**

~~~text
compiled=true
diagnostics=0
class-file=true
~~~

Component explanation:

- `SimpleJavaFileObject` models the `Sample.java` file in memory.
- `JavaCompiler.getTask(...)` creates a compilation task; `call()` executes the task.
- `StandardJavaFileManager` handles the compiler's physical output. The example creates a temporary directory with `Files.createTempDirectory` and closes the manager after use.
- `DiagnosticCollector` receives structured errors/warnings; the valid sample emits no diagnostics under the test configuration.
- `-proc:none` prevents annotation processors from running unintentionally; this is a **task** option, not another module.

**Note:** `JavaCompiler` and the interfaces used live in `java.compiler`, yet because it runs on a JDK containing `jdk.compiler`, `ToolProvider` can locate an implementation to perform compilation. You do not need to import the concrete name `com.sun.tools.javac.api.JavacTool` to execute the task.

This example **can run standalone**; `Sample.class` is written into a new temporary directory rather than into the project's output directory.

### 7.1. When the compiler is unavailable

The checked code:

~~~java
JavaCompiler compiler =
        ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    System.out.println("No system Java compiler");
    return;
}
~~~

This is a **valid handling path** under the API contract. `getSystemJavaCompiler()` can return null when the current platform provides no compiler. Do not write production tools assuming every Java machine has a system compiler.

Once again: **lacking a compiler implementation** differs from **lacking the `javax.tools.JavaCompiler` interface**. The interface can exist in `java.compiler` while no service providing an implementation exists.

## 8. Runnable Example 3: Compiler Tree API Resides in jdk.compiler

If you only need to compile and collect diagnostics, `javax.tools` is enough. However, if you want to **read the AST** to write a static analyzer, assist an IDE, or inspect method/expression structure, you can use the **Compiler Tree API** from `jdk.compiler`.

Create **InspectTree.java**:

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;

import java.net.URI;
import java.util.List;

import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class InspectTree {
    public static void main(String[] args) throws Exception {
        String text =
                "class Sample { int answer = 2 + 3 * 4; }";

        JavaFileObject input = new SimpleJavaFileObject(
                URI.create("string:///Sample.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(
                    boolean ignoreEncodingErrors) {
                return text;
            }
        };

        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.out.println("Compiler unavailable");
            return;
        }

        JavacTask task = (JavacTask) compiler.getTask(
                null,
                null,
                null,
                List.of("-proc:none"),
                null,
                List.of(input)
        );

        for (CompilationUnitTree unit : task.parse()) {
            for (Tree declaration : unit.getTypeDecls()) {
                System.out.println(declaration.getKind());
            }

            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitVariable(
                        VariableTree variable, Void unused) {
                    if (variable.getName()
                            .contentEquals("answer")) {
                        System.out.println(
                            variable.getInitializer().getKind()
                        );
                    }
                    return super.visitVariable(variable, unused);
                }
            }.scan(unit, null);
        }
    }
}
~~~

Compile and run with a full JDK 17+:

~~~bash
javac InspectTree.java
java InspectTree
~~~

**Verified stdout on OpenJDK 21:**

~~~text
CLASS
PLUS
~~~

The parsed tree contains one class declaration, and the initializer of variable `answer` has an outer `PLUS` operator: `2 + (3 * 4)`. The demo program only calls **parse()**; it has not called `analyze()` or `generate()`, so it does not claim full type checking or bytecode generation for the input.

In the example, the task is obtained via `javax.tools.JavaCompiler.getTask(...)` and cast to `com.sun.source.util.JavacTask`, a javac-specific API for accessing parse/analysis. This is valid when the actual provider supports `JavacTask` (such as javac in the tested JDK); **do not assume every external JavaCompiler implementation returns a JavacTask**.

**Why is `java.compiler` alone insufficient?** Because interfaces `CompilationUnitTree`, `Tree`, `VariableTree` and utilities `JavacTask`, `TreePathScanner` belong to module `jdk.compiler`. You need a JDK/runtime containing that module to compile and run a tool based on the Tree API.

## 9. Declaring module-info.java for the Client

### 9.1. Using only the standard API

If the application module only calls JavaCompiler and collects diagnostics:

~~~java
module example.compilerclient {
    requires java.compiler;
}
~~~

The compiler client can import:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
~~~

These are illustrative module declarations and import snippets; to form a runnable modular project, you still need a package containing the main class, a source tree, and build commands. **`requires java.compiler` only grants permission to read the API**, and does not guarantee the final JVM contains `jdk.compiler`.

### 9.2. Using the Compiler Tree API

If the application needs `com.sun.source.tree` and `com.sun.source.util`, the module descriptor can declare:

~~~java
module example.asttool {
    requires jdk.compiler;
}
~~~

The JDK module `jdk.compiler` declares `requires transitive java.compiler`, so `example.asttool` can read `java.compiler`'s APIs via transitive readability.

Even so, declaring both modules in the descriptor to clarify direct source dependencies can also align with design conventions:

~~~java
module example.asttool {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

Do not confuse `requires` with "downloading a module from the network". The module must exist in the configured JDK/module path/runtime image for resolution to succeed.

### 9.3. Testing compilation with module path

If organizing source as:

~~~text
src/
└── example.asttool/
    ├── module-info.java
    └── example/
        └── asttool/
            └── Main.java
~~~

Where `Main.java` belongs to package `example.asttool`, uses the Tree API, and has a main method, you can compile in modular mode:

~~~bash
javac --module-source-path src -d mods -m example.asttool
java --module-path mods -m example.asttool/example.asttool.Main
~~~

This is a **command pattern for a modular structure**, not a full project written here. Do not add `--add-exports` if only using the **com.sun.source.tree/util** packages publicly exported by `jdk.compiler`.

## 10. API-Only Runtime Image: Verifying with jlink

**`java.compiler` existing** does not prove **a compiler implementation exists**. You can verify this yourself with a custom runtime image.

Create **ProviderProbe.java**:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class ProviderProbe {
    public static void main(String[] args) {
        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();

        System.out.println(
            JavaCompiler.class.getModule().getName()
        );
        System.out.println(
            compiler == null
                ? "compiler absent"
                : "compiler present"
        );
    }
}
~~~

On a full JDK:

~~~bash
javac -d out ProviderProbe.java
java -cp out ProviderProbe
~~~

**Verified stdout on OpenJDK 21:**

~~~text
java.compiler
compiler present
~~~

Next, create a runtime image containing **`java.base` and `java.compiler`** while intentionally **excluding `jdk.compiler`**:

~~~bash
jlink --add-modules java.base,java.compiler --output runtime-api
~~~

On Linux/macOS:

~~~bash
./runtime-api/bin/java -cp out ProviderProbe
~~~

On Windows:

~~~powershell
.\runtime-api\bin\java.exe -cp out ProviderProbe
~~~

**Verified stdout on OpenJDK 21 with the minimal runtime image:**

~~~text
java.compiler
compiler absent
~~~

From this:

1. Class `javax.tools.JavaCompiler` can still be loaded because the image contains `java.compiler`.
2. `getSystemJavaCompiler()` returns **null** because the image lacks the system javac provider from `jdk.compiler`.
3. An application using only the API does not automatically become a JDK.
4. If the application truly needs to run javac, package a runtime with an appropriate compiler implementation or design a way to use an external compiler.

This is an experiment on **runtime module composition**, not a recommendation that every application build its own custom image. When a runtime is minimized, module availability must be verified in the actual deployment artifact.

**Note:** `jdk.compiler` also has other supporting module requirements, such as `jdk.zipfs` in certain JDKs for reading JARs; let `jlink` resolve dependencies accurately rather than assuming two modules suffice in every case.

## 11. Service Provider: Who Provides the Compiler?

`java.compiler` defines the **SPI** `javax.tools.JavaCompiler`. Module `jdk.compiler` holds the implementation and declares the corresponding service provider. When a compiler is present, clients can go through the supported entry paths:

~~~text
Application
   |
   +-- javax.tools.ToolProvider.getSystemJavaCompiler()
   |               |
   |               v
   |        javax.tools.JavaCompiler  (API)
   |               ^
   |               |
   |          implementation in jdk.compiler
   |
   +-- java.util.spi.ToolProvider.findFirst("javac")
                   |
                   v
            javac tool as a command-line provider
~~~

These two access paths **do not return the same interface**:

- `getSystemJavaCompiler()` returns **`JavaCompiler`** or null; suitable when `getTask`, file managers, and diagnostics are needed.
- `java.util.spi.ToolProvider.findFirst("javac")` returns **`Optional<ToolProvider>`**; suitable when you want to invoke the tool with command-line-like arguments within the same JVM.

Illustrative code snippet:

~~~java
var javacTool = java.util.spi.ToolProvider
        .findFirst("javac");

if (javacTool.isPresent()) {
    System.out.println("javac tool is available");
}
~~~

**Do not use `new com.sun.tools.javac.api.JavacTool()` as a replacement for the public entry points.** Concrete classes may not be exported or may change across JDKs, whereas the application can use standard services/APIs.

## 12. Limitations When Calling javac via the API

**Not every option of the native javac launcher works verbatim through `JavaCompiler.getTask`.** The `jdk.compiler` module documentation describes several limitations by design:

| Case | Native javac launcher | `JavaCompiler` API |
| --- | --- | --- |
| `-J...` to set JVM options for javac process | Works with the native launcher | Not used in `getTask`; set VM options on the JVM running the tool |
| Classpath wildcards like `libs/*` | Native launcher expands wildcards per its own rules | Does not automatically expand wildcards in the API; list concrete JARs |
| Argument file `@args.txt` | Supported by the launcher | `JavaCompiler` interface does not recognize argument-file syntax like the launcher |
| `JDK_JAVAC_OPTIONS` | Can affect the native launcher | API does not automatically apply this environment variable |
| `--help` and `--version` | Used to obtain launcher info | Not used as compilation options in `JavaCompiler.getTask` |
| Classpath/module path | Per tool options | Depends on file manager; standard manager supports standard options |

Therefore, when porting a build script using the `javac` command to a program calling `JavaCompiler`, do not simply copy every argument string and expect identical behavior. For classpaths, file managers, and annotation processors, replicate the build configuration accurately.

**Practical point:** to pass JVM arguments to the process running the compiler API, configure **the host application's JVM** rather than putting `-J...` into the compilation task's options list.

## 13. Why Does com.sun.source.* Differ from com.sun.tools.javac.*?

Both contain "sun", yet **the package name prefix does not determine the level of support**. What matters is **the module descriptor and API documentation**.

**`com.sun.source.tree` and `com.sun.source.util`**:

- Publicly exported by `jdk.compiler`.
- Documented with Javadoc for syntax tree interfaces and utilities.
- The intended choice when writing tools that depend on javac ASTs.

**`com.sun.tools.javac.api`, `com.sun.tools.javac.comp`, `com.sun.tools.javac.parser`...**:

- Many subpackages are **not exported** to regular applications.
- Focused on javac's internal implementation structure.
- May change APIs, structure, and semantics across JDK releases without the compatibility guarantees of Java SE APIs.
- May trigger a JPMS compile error **package ... is not visible** when applications try to import them.

When attempting to use an internal package, one might pass a flag such as:

~~~bash
javac --add-exports jdk.compiler/com.sun.tools.javac.parser=ALL-UNNAMED ...
~~~

This is an **example of encapsulation-opening syntax**, not advice or a complete command. Using internals may also require handling runtime exports/opens and risks implementation breakage. An ordinary learning tool should **not** take this route just to obtain an AST: the Tree API is already available through `com.sun.source.*`.

### 13.1. A legacy entry point does not mean all internals are public

Module `jdk.compiler` exports package **`com.sun.tools.javac`** for a legacy entry point. Yet that prefix does not "carry over" export access to **`com.sun.tools.javac.api`** or **`com.sun.tools.javac.util`**. JPMS exports by **exact package**, not by an entire subpackage tree.

Rely on:

~~~bash
java --describe-module jdk.compiler
~~~

to see public exports/qualified exports in a specific JDK. A package that is only **qualified exported to jdk.javadoc** cannot automatically be used by an arbitrary application.

## 14. API Selection Table by Need

| Need | Choose API | Module read by application |
| --- | --- | --- |
| Compile source in memory or from files | `JavaCompiler`, `JavaFileObject`, `JavaFileManager` | `java.compiler` |
| Collect structured errors/warnings | `DiagnosticCollector`, `Diagnostic` | `java.compiler` |
| Write an annotation processor | `AbstractProcessor`, `TypeElement`, `Elements`, `Types` | `java.compiler` |
| Check whether javac exists | `ToolProvider.getSystemJavaCompiler()` | `java.compiler` (provider must exist at runtime) |
| Invoke javac tool CLI-style from Java | `java.util.spi.ToolProvider.findFirst("javac")` | API in `java.base`; requires provider present |
| Traverse Java source AST | `JavacTask`, `TreePathScanner`, `Tree` | `jdk.compiler` |
| Analyze Javadoc tree | `com.sun.source.doctree` | `jdk.compiler` |
| Manipulate javac internal resolver/representations | **Avoid** `com.sun.tools.javac.*` internals if public alternatives exist | Unstable implementation coupling |

If you need portable deployment across any Java SE runtime that might be slimmed down, declaring only `requires java.compiler` is not enough: you must **check for the provider**. If the tool requires ASTs, depending on `jdk.compiler` is a deliberate architectural decision requiring distribution of an appropriate JDK/runtime.

## 15. Common Errors and How to Diagnose Them

### 15.1. ToolProvider.getSystemJavaCompiler() returns null

**Symptom:** the application can still import `javax.tools.JavaCompiler`, yet the compiler variable is null.

**Common cause:** the application is running on a runtime image lacking the module providing javac, such as a `jlink` image containing only `java.base` and `java.compiler`.

**Resolution:** verify `java --list-modules` in **the runtime actually running the application**, add the module/provider to the runtime image if needed, or design support for an external compiler. Do not try fixing source by adding `com.sun.tools.javac.*` imports.

### 15.2. com.sun.source.tree.Tree not found

**Symptom:** javac reports package `com.sun.source.tree` does not exist or module is not read.

**Possible causes:** compiler/runtime lacks `jdk.compiler`, the tool's module descriptor is missing `requires jdk.compiler;`, or module path configuration is wrong.

**Resolution:** check the JDK, `module-info.java`, and module graph. Do not confuse this with classes in `javax.tools`, because the Tree API is not in `java.compiler`.

### 15.3. Package com.sun.tools.javac.api is not visible

**Cause:** importing an internal implementation package that module `jdk.compiler` does not publicly export to applications.

**Resolution:** switch to `javax.tools` or `com.sun.source.*`. Do not choose `--add-exports` as the default approach to bypass JPMS encapsulation.

### 15.4. ClassCastException when casting CompilationTask to JavacTask

**Cause:** code assumes every `JavaCompiler` provider is javac. The `CompilationTask` interface does not require other compilers to return `JavacTask`.

**Resolution:** only cast when you know the actual provider supports the Compiler Tree API; document the JDK/javac requirement for AST features. If the tool permits multiple compilers, provide a fallback path not relying on `JavacTask`.

### 15.5. Compiles in the IDE, but runtime has no compiler

**Cause:** the IDE uses a JDK for compiling, whereas the production artifact runs on a minimal custom runtime image.

**Resolution:** check **both the build JDK and the runtime image**, not just the compiler version on a developer workstation.

### 15.6. JavaCompiler API rejects -J or @argfile

**Cause:** confusing API method options with native launcher flags.

**Resolution:** place JVM options on the host process; pass javac options supported by the API directly; resolve classpath file lists yourself if needed.

### 15.7. Tree API parses source, but that does not mean full compilation

**Cause:** code calls `JavacTask.parse()` yet treats the AST as proof that all types, symbols, and bytecode are valid.

**Resolution:** distinguish the `parse()`, `analyze()`, and `generate()` phases. Analyzing the tree in the parse phase can involve source that has not passed semantic checks.

## 16. Process for Designing Solid JavaCompiler Tools

1. **Determine the required API level.** If only compilation/diagnostics are needed, start from `javax.tools`. If ASTs are needed, consider `com.sun.source.*`.
2. **Declare the right module dependencies.** `requires java.compiler;` for the standard compiler API; `requires jdk.compiler;` when the Tree API is needed.
3. **Check for the implementation at runtime.** `getSystemJavaCompiler()` may be null.
4. **Use the file manager intentionally.** Manage classpath/module path, source objects, and outputs.
5. **Pass API-compatible options.** Do not blindly copy launcher-only flags.
6. **Collect diagnostics via the API** rather than parsing stderr message strings when programmatic processing is needed.
7. **Keep a boundary between the compiler and JDK internals.** Do not use internal implementation types if public APIs suffice.
8. **Test on the final runtime image.** For jlink/containers, confirm the provider module is properly packaged.
9. **Test with invalid inputs.** Invalid Java source can still produce diagnostics/partial ASTs; the application must handle compilation task false.
10. **Document compatibility clearly.** A javac-based AST tool does not automatically run on every other Java SE compiler.

## 17. Practice Exercises

**Exercise 1 — Read the module graph.** Run `java --describe-module java.compiler` and `java --describe-module jdk.compiler` on your JDK. Find the exports, requires transitive, and provides lines. Explain why requiring `jdk.compiler` implies readability of APIs from `java.compiler` while the reverse is not true.

**Exercise 2 — Run ModuleProbe.** Create `ModuleProbe.java` from section 6. Predict the six stdout lines, then run on JDK 17+. If different, record the JDK vendor, version, and module list.

**Exercise 3 — Use the standard API.** Run `ApiCompile.java` from section 7. Replace the String source with a syntactically invalid Java program; observe `compiled=false` and the diagnostic count. Expand the loop to print `Diagnostic.getKind()`, `getLineNumber()`, and `getMessage(Locale.ENGLISH)`.

**Exercise 4 — Use the AST.** Run `InspectTree.java` from section 8. Change the expression to `(2 + 3) * 4` and print the kind of the initializer. Predict why the result differs even though the literals are the same.

**Exercise 5 — Runtime without a compiler.** Run `ProviderProbe.java` on a full JDK and on a `jlink` image containing only `java.base,java.compiler`. Compare `compiler present` and `compiler absent`.

**Exercise 6 — Avoid internal APIs.** A tool currently imports `com.sun.tools.javac.api.JavacTool` and `com.sun.tools.javac.tree.JCTree`. Propose a replacement path using `JavaCompiler` and `JavacTask`/`Tree` respectively, while noting the limitations of replacement if the tool needs implementation characteristics absent from public APIs.

**Exercise 7 — Querying the CLI tool.** Write a program that calls `java.util.spi.ToolProvider.findFirst("javac")` and handles `Optional.empty()`. Explain why this approach does not return a `JavaCompiler.CompilationTask`.

## 18. Self-Check Questions

- Does `java.compiler` contain the `JavaCompiler` interface or the javac implementation?
- Which services and Tree API packages does `jdk.compiler` provide?
- How do the two `ToolProvider` classes in `javax.tools` and `java.util.spi` differ?
- Why can a program import `javax.tools.JavaCompiler` yet `getSystemJavaCompiler()` still return null?
- Does `requires jdk.compiler;` establish a read relationship to `java.compiler`? Why?
- Does `com.sun.source.tree` have the same API status as `com.sun.tools.javac.parser`?
- Why does the JavaCompiler API not accept every launcher option such as `-J` and `@argfile`?
- Does `JavacTask.parse()` mean the source is type-valid?
- Should a new IDE plugin depend on the concrete class `com.sun.tools.javac.api.JavacTool`?
- What must a runtime image that wants to compile Java source package besides the API module?

## 19. Official References

- **Oracle Java SE 21 — Module java.compiler:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/module-summary.html
- **Oracle JDK 21 — Module jdk.compiler:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/module-summary.html
- **Java SE 21 — javax.tools package:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/package-summary.html
- **Java SE 21 — JavaCompiler API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html
- **Java SE 21 — javax.tools.ToolProvider:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html
- **Java SE 21 — java.util.spi.ToolProvider:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/spi/ToolProvider.html
- **JDK 21 — JavacTask / Tree API:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html
- **JDK 21 — Compiler Tree package:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html
- **JDK 21 — javac tool guide:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

**Key takeaway:** `java.compiler` defines the **Java Compiler API contract** and language model. `jdk.compiler` provides the **javac implementation** and public Compiler Tree APIs. If you only need compilation and diagnostics: start from `javax.tools`. If you need ASTs: explicitly depend on `com.sun.source.*` in `jdk.compiler`. Avoid `com.sun.tools.javac.*` internals, and always verify that a compiler provider actually exists in the runtime image.