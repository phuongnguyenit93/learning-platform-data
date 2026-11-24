# Distinguishing the java.compiler Module, jdk.compiler, and the Actual Compiler

## 1. Three Concepts That Are Not Synonymous

When a Java application wants to compile source code at runtime—such as a plugin system, practice sandbox, or code generator—it is necessary to distinguish **the compilation API**, **the JDK implementation**, and **the tool actually usable in the current runtime**.

| Component | Role | What Does It Contain? |
|---|---|---|
| \`java.compiler\` | Standard Java SE module defining the compilation API | \`javax.tools.JavaCompiler\`, \`ToolProvider\`, \`JavaFileObject\`, \`DiagnosticCollector\` |
| \`jdk.compiler\` | JDK module containing the compiler implementation | The \`javac\` compiler and \`com.sun.source.*\` APIs, related implementations |
| Actual compiler | Compiler chosen by the application and invokable at runtime | System compiler, external \`javac\` tool, or another compiler supporting the contract |

**Key point:** having the \`java.compiler\` module does not mean the current virtual machine contains a compiler implementation. The API only defines how to communicate; a custom runtime image may omit \`jdk.compiler\`. Therefore \`ToolProvider.getSystemJavaCompiler()\` can return \`null\`.

## 2. \`java.compiler\`: The Java Compiler API Contract

\`java.compiler\` is the standard module providing the \`javax.tools\` package. Commonly encountered types:

- \`JavaCompiler\`: interface representing a compiler that processes Java source;
- \`JavaCompiler.CompilationTask\`: compilation task invokable via \`call()\`;
- \`ToolProvider\`: way to obtain the system compiler per JDK rules;
- \`JavaFileObject\` and \`SimpleJavaFileObject\`: model for source/class files, supporting in-memory file objects;
- \`StandardJavaFileManager\`: handles standard files and paths;
- \`DiagnosticListener\`/\`DiagnosticCollector\`: receives errors, warnings, and line/column information;
- \`JavaFileManager\`: customizable to store outputs in memory.

A named module using this API declares:

\`\`\`java
module example.host {
    requires java.compiler;
}
\`\`\`

If using the classpath (unnamed module) in a regular JDK runtime, \`module-info.java\` is usually not needed.

**Distinguish \`javax.tools\` from \`javax.annotation.processing\`**: both belong to the compilation API scope, but their functions differ. One manages the compiler/file manager/diagnostics, while the other provides the annotation processing API. For plugins running new code, compiling bytecode is only one step; a separate class loader/module layer is needed to define classes and manage the lifecycle.

## 3. \`jdk.compiler\`: The javac Implementation

\`jdk.compiler\` is a JDK-specific module providing the implementation of the Java compiler. In modern JDKs, this module includes the command compiler provider and packages such as \`com.sun.source.tree\` and \`com.sun.source.util\` for syntax tree analysis.

You can inspect module information on the JDK:

\`\`\`bash
java --describe-module jdk.compiler
\`\`\`

Or:

\`\`\`bash
java --list-modules
\`\`\`

The output depends on the distribution and runtime image. For example, on a full JDK 17, the list typically includes \`java.compiler@17...\` and \`jdk.compiler@17...\`. Do not hardcode versions or exact full output because vendors, patch levels, and runtime image builds can differ.

\`jdk.compiler\` **does not mean every internal \`com.sun.tools.javac.*\` class is a stable public API**. JPMS enforces package exports; application code should use \`javax.tools\` when only compilation is needed, and use the supported \`com.sun.source.*\` public APIs when AST information is required. Avoid directly accessing internal implementation packages because module encapsulation may block them or they may change across JDK versions.

In a typical design, **the host only needs \`requires java.compiler\`** and does not need \`requires jdk.compiler\` just to call \`ToolProvider.getSystemJavaCompiler()\`. This keeps the host code dependent on the Java SE contract and allows checking for an implementation at runtime.

## 4. \`ToolProvider.getSystemJavaCompiler()\` and \`null\`

\`javax.tools.ToolProvider.getSystemJavaCompiler()\` returns the compiler provided by the current Java environment via the system compiler mechanism. When no compiler is present, the result is \`null\`.

\`\`\`java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("No system Java compiler available");
}
\`\`\`

*This snippet illustrates how to check and is not a standalone program.*

Situations that deserve special attention:

- **Full JDK**: normally has an available compiler.
- **\`jlink\` runtime image containing only runtime modules**: may include \`java.compiler\` while missing \`jdk.compiler\`; the system compiler is unavailable.
- **Minimal container**: the runtime image may lack a compiler even though the development machine has a JDK.
- **Applications running on native image or specialized runtimes**: compiler/Java module mechanics may differ from a standard JDK JVM; verify on the actual deployment environment.
- **JDK compiler module is present, but the output path is not writable**: the compiler exists, yet compilation still fails due to write permissions/paths/classpath/module path.

Before claiming a system supports runtime compilation, verify **compiler presence**, **appropriate source/target/release**, **correct dependency paths**, **sufficient file manager permissions**, and **necessary environment resources**.

## 5. Complete Java 17+ Example: Detecting and Running the System Compiler

Create file **\`CompilerProbe.java\`**:

\`\`\`java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompilerProbe {
    public static void main(String[] args) throws IOException {
        System.out.println("java.compiler present: " +
                ModuleLayer.boot().findModule("java.compiler").isPresent());
        System.out.println("jdk.compiler present: " +
                ModuleLayer.boot().findModule("jdk.compiler").isPresent());

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println("system compiler present: " + (compiler != null));
        if (compiler == null) {
            return;
        }

        Path dir = Files.createTempDirectory("compiler-demo-");
        Path source = dir.resolve("Hello.java");
        Files.writeString(source, """
                public class Hello {
                    public static String message() { return "compiled"; }
                }
                """);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(diagnostics, null, null)) {
            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjects(source.toFile());
            List<String> options = List.of(
                    "--release", "17",
                    "-d", dir.toString()
            );
            JavaCompiler.CompilationTask task =
                    compiler.getTask(null, manager, diagnostics,
                            options, null, units);

            boolean successful = Boolean.TRUE.equals(task.call());
            System.out.println("compilation successful: " + successful);
            System.out.println("class file present: " +
                    Files.exists(dir.resolve("Hello.class")));

            diagnostics.getDiagnostics().forEach(
                    d -> System.err.println(d.getKind() + ": " +
                            d.getMessage(null)));
        }
    }
}
\`\`\`

Run on **JDK 17+ with \`jdk.compiler\` and support for \`--release 17\`**:

\`\`\`bash
javac CompilerProbe.java
java CompilerProbe
\`\`\`

Output when run on a full JDK 17 with normally resolved modules:

\`\`\`text
java.compiler present: true
jdk.compiler present: true
system compiler present: true
compilation successful: true
class file present: true
\`\`\`

The program creates a temporary directory, writes \`Hello.java\`, uses the Java Compiler API to compile it into the same directory, and checks that \`Hello.class\` exists. Compiling **does not automatically run \`Hello\`**: using the class requires an appropriate loader or integration with a module layer and plugin lifecycle. To avoid accumulating temporary files in a real application, add a cleanup policy; the example keeps the directory so you can inspect the output.

Do not treat the presence of \`java.compiler\` or \`jdk.compiler\` in \`ModuleLayer.boot()\` as the sole proof. Checking \`compiler != null\` is closer to the goal, and the result of \`task.call()\` is what indicates whether a specific compilation succeeded.

## 6. Evaluating Module Presence with ModuleLayer and ModuleFinder

There are two levels of questions:

**(1) Is the module currently in the layer?**

\`\`\`java
boolean inBootLayer =
        ModuleLayer.boot().findModule("jdk.compiler").isPresent();
\`\`\`

**(2) Does the runtime image contain the module for discovery?**

\`\`\`java
boolean observable =
        java.lang.module.ModuleFinder.ofSystem()
                .find("jdk.compiler")
                .isPresent();
\`\`\`

\`ModuleFinder.ofSystem()\` searches modules in the system module image; it does not create a compiler instance or automatically resolve the module into the boot layer. The two results can differ if the module exists in the image but was not resolved into the layer being checked.

When choosing a runtime image for an application, **being able to find the module differs from the compiler actually being invokable and compiling successfully**. The host should evaluate using an appropriate feature test, especially when running in an image created with \`jlink\`.

### Example module-info.java for the Host

\`\`\`java
module example.runtimecompiler.host {
    requires java.compiler;
}
\`\`\`

The host only depends on the interfaces in \`java.compiler\`; runtime deployment determines whether a suitable implementation is present. If using the JDK compiler's \`com.sun.source.*\` packages, consider an explicit dependency \`requires jdk.compiler\`, while accepting that this is a JDK-specific dependency.

## 7. Designing a Custom Runtime Image with jlink

An example of creating an image containing the compiler:

\`\`\`bash
jlink --add-modules java.base,java.compiler,jdk.compiler \
      --output runtime-with-compiler
\`\`\`

Then use the \`java\` executable inside \`runtime-with-compiler/bin\` to run the compiled application. In real deployments, add the modules that the host and plugins actually need. Note that the compiler implementation has its own module dependencies, and \`jlink\` resolves dependencies according to the module graph.

An image without \`jdk.compiler\` may still contain \`java.compiler\` if the application needs the compile API as part of its dependency graph without having a compiler implementation to execute.

**Important limitation:** a runtime image built by \`jlink\` is not equivalent to a full JDK. It may lack the \`javac\` executable in \`bin\` even when the runtime has enough modules for the Java Compiler API to work. Distinguish **in-process compilation via \`javax.tools\`** from invoking the **external \`javac\` command**. Availability of the command-line tool must be verified separately.

## 8. Compiler API vs. \`javac\` Command and Third-Party Compilers

There are three compilation execution strategies:

| Strategy | Advantages | Constraints |
|---|---|---|
| \`ToolProvider.getSystemJavaCompiler()\` | Standard Java API; flexible diagnostics/file manager; supports in-process compilation | Depends on compiler implementation in runtime; compiler code runs inside the host process |
| Running \`javac\` via \`ProcessBuilder\` | Separate process, easier timeout/output control; uses chosen toolchain | Requires executable and matching JDK/toolchain; must handle process, environment, classpath, output |
| Third-party compiler | Fits specific runtimes or features; may offer a different API | Must verify Java support level, API, dependencies, and maintenance |

Example of running an external compiler via \`ProcessBuilder\` (illustrative snippet, not a complete program):

\`\`\`java
Process process = new ProcessBuilder(
        "/path/to/jdk/bin/javac",
        "--release", "17",
        "-d", "/safe/output",
        "/safe/source/Hello.java"
).redirectErrorStream(true).start();
\`\`\`

Read stdout/stderr promptly to avoid buffer-full deadlocks, set timeouts, check the exit code, kill the process when necessary, and use controlled paths. Do not construct shell commands by concatenating strings taken from users. \`ProcessBuilder\` accepts separate argument lists so it is easier to control than shell interpolation, yet source/target paths and filesystem permissions must still be validated.

Third parties may provide a \`JavaCompiler\` implementation or a library-specific API. Do not assume every Java compiler appears via \`ToolProvider.getSystemJavaCompiler()\`: this method uses the environment's system compiler mechanism, not a general registry for arbitrary compilers.

## 9. Relationship to Plugins and Runtime Compilation

For a runtime extensibility system, a safe workflow is typically:

~~~text
Allowed plugin source
        |
        v
Check format + size limits + permissions
        |
        v
Select appropriate compiler/toolchain
        |
        v
Compile into isolated staging area
        |
        v
Collect diagnostics and validate output
        |
        v
Verify API/dependency/module contract
        |
        v
Pass approved artifact to class loader/layer
        |
        v
Instantiate and activate plugin under control
~~~

**Compilation is not a security boundary.** JavaCompiler can trigger annotation processors or compiler plugins during compilation, depending on options and environment, and can execute code inside the host process. For untrusted sources, control the processor path; consider \`-proc:none\` when annotation processing is unnecessary, and prefer compiling in an isolated process/container with resource/permission restrictions. Supported options vary by compiler/toolchain, so verify on the target version.

For compiled bytecode, loading and execution also require separate policies; a class loader/module layer does not automatically sandbox malicious code. If the plugin's API module is shared, avoid duplicate packaging so as not to cause class identity or linkage errors.

## 10. Common Misconceptions

- **“Having \`java.compiler\` means having \`javac\`.”** False: the standard module defines the API; it does not promise a compiler executable.
- **“Just declaring \`requires java.compiler\` guarantees the compiler always works.”** False: the implementation must be provided by the runtime.
- **“\`jdk.compiler\` is a mandatory Java SE API in every runtime image.”** False: it is a JDK module and can be omitted from custom images.
- **“Having the \`jdk.compiler\` module means every compile task will succeed.”** False: source, options, dependencies, write permissions, or resources can still cause failures.
- **“Calling \`ToolProvider\` discovers every third-party compiler.”** False: it accesses the system compiler per the current environment's mechanism.
- **“Compiling source is safe as long as you don't execute the output classes.”** False: annotation processing or compiler plugins can execute code during compilation.
- **“Once compiled, the new class can be called directly.”** False: you still need the class loading/definition step and API compatibility checks.
- **“Because \`javac\` is on the dev machine, the production container has it too.”** False: each runtime must be verified independently.

## 11. Checklist Before Implementing Runtime Compilation

1. Verify the Java/runtime version and observable modules.
2. Check \`ToolProvider.getSystemJavaCompiler()\` in practice, or the chosen toolchain command.
3. Perform a compile smoke test with an appropriate \`--release\`.
4. Place source/output in an isolated staging directory with limits and cleanup.
5. Configure classpath/module path, annotation processing policy, and dependency allowlist.
6. Collect full diagnostics, error codes, and causes; do not rely solely on whether \`Hello.class\` exists.
7. For untrusted sources, isolate the process/limit resources and permissions.
8. After compilation, verify bytecode/API/modules and activate the plugin only after preflight passes.
9. Test across dev, CI, container, and custom runtime image environments.

**Takeaway:** \`java.compiler\` is **the Java Compiler API contract**, \`jdk.compiler\` is **the JDK's compiler implementation**, and **the actual compiler** is the tool the application can successfully invoke at runtime. These three layers must be verified separately when building a runtime plugin compilation feature.
