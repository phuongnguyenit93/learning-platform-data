# When Should You Accept Java Source Code Instead of Installing a Precompiled JAR?

## 1. What Is the Real Design Question?

In a Java application with runtime extensibility, the host wants to add new behavior without modifying or recompiling the entire main application. There are two ways to accept extensions:

- **Accept a precompiled JAR:** the plugin developer writes Java code, compiles/tests/packages it in advance, and the host receives an artifact containing bytecode and resources (for example, a ServiceLoader provider).
- **Accept Java source code:** the host or a designated build service receives **.java** files or structured source snippets, **compiles them into bytecode** suitable for the environment, and only then loads and invokes the resulting class.

Regardless of the choice, **the JVM executes bytecode; it does not directly execute Java source syntax like a typical scripting language**. "Accepting source" adds a compilation stage before class loading; it does not replace the class loader, API/SPI, version control, or trust policy.

A common misconception is that "to install plugins at runtime, you must accept source." This is **false**. A JAR can also be discovered and loaded while the application is running if the host designs an appropriate class loader or module layer and plugin lifecycle. Conversely, a system can **accept source for review/building in CI** and then release a JAR, completely eliminating the need for JavaCompiler in the production process.

Therefore, two decisions should be separated:

1. **Input format** to accept: source code to compile, or a prebuilt bytecode artifact?
2. **Where and when to compile**: before deployment (CI/build service), at plugin installation time, or whenever rules change at runtime?

Accepting source code makes sense when there is a **genuine need to change/adjust code** and the ability to manage the compilation step as well. If you only need to load a stable implementation, a JAR is usually simpler and carries fewer operational responsibilities.

## 2. Two Processing Pipelines: Source and JAR

~~~text
Option A: accept JAR
Plugin developer
  └─ write source → build/test/sign → plugin.jar
                                   |
                                   v
Host: verify artifact → load JAR → check SPI → instantiate → invoke
                          (loader or ModuleLayer)

Option B: accept Java source
Source provider
  └─ .java source + dependency/version/compile options
                                   |
                                   v
Host or build service: validate → JavaCompiler/javac → .class
                                    |                  |
                                 diagnostics     verify output
                                                       |
                                                       v
                      load via loader/layer → check SPI → invoke
~~~

The difference lies in **the input and compilation responsibility**, not in whether the JVM can be extended at runtime. Both must address class namespaces, API boundaries, dependency linking, execution permissions, lifecycle, and error reporting.

### Quick Decision Matrix

| Criterion | Accept source then compile | Install prebuilt JAR |
| --- | --- | --- |
| Behavior generated from frequently changing config/rules | Useful if Java source is a required output | Requires a JAR rebuild pipeline on every change |
| Plugin is a stable release provided by another team | Usually unnecessary | More suitable |
| Running where no JDK/compiler is present | Must build elsewhere | Works with a runtime that has sufficient modules/dependencies |
| Need to re-inspect source and build artifact against current API | Advantageous if a controlled toolchain exists | Only suitable when a compatible artifact exists |
| Requirement for fast startup/install, minimal build dependencies | Disadvantage when compiling at install time | More suitable |
| Need to manage annotation processing, compiler flags, dependencies | Host/build service must handle this | Responsibility mainly lies in the plugin build pipeline |
| Need to isolate untrusted code | **Does not solve safety on its own** | **Does not solve safety on its own** |
| Need to swap already-loaded classes | Must load output using a new loader/layer | Also must manage a new loader/layer |

Do not use a single row in the table alone to make a decision. For example, "wanting to audit source" is a good reason to **accept source**, but not yet a sufficient reason to **compile source inside the JVM serving users**.

## 3. Cases Where You Should Accept Java Source Code

### 3.1. The Host Must Generate Implementations from Dynamic Data

A rule engine or generator system can generate Java classes based on business configuration, schemas, DSLs compiled to Java, controlled templates, or function definitions supplied by internal teams.

For example: an order processing platform generates an adapter for a new schema; each schema version results in an implementation of the same **OrderTransformer** interface. If a **Java class** is strictly required to plug into the system and update at runtime, JavaCompiler can be a reasonable stage.

Conditions for choosing this approach:
- It must genuinely compile to a class or module; a configuration table or interpreter cannot meet the requirement.
- Change timing and version lifecycle are clear.
- Toolchain, dependencies, generated source code, and compilation output can be verified/reproduced.
- Source can only access host APIs published in the contract.

**If rules are only simple expressions**, consider configuration, a restricted DSL, a rule engine, or precompiled callbacks first. Building a runtime Java compiler just to replace an `if` condition can introduce unnecessary cost and risk.

### 3.2. Need to Compile Against the Current API Version and Environment

Sometimes an extension's source is compatible with a changed API version, while the prepackaged JAR depends on old signatures. If you own the source and have thorough tests, rebuilding against the current API can produce a compatible artifact.

For example: the host just changed an internal interface, and internal providers need to be recompiled before activation. This is a reason to **accept source**, though it should still typically be done in a **build/test pipeline** rather than on every production request.

**No guarantee of automatic compatibility:** recompilation only resolves issues where the source actually compiles against the new API. If API semantics, nullability requirements, concurrency, data formats, or transactions changed, the source still needs to be updated and behavior-tested. Compiler success does not prove the runtime contract still holds.

### 3.3. Plugin Is a Custom Build per Tenant or Deployment

A multi-customer product may require custom algorithms provided by a trusted deployment team. Accepting source enables clear versioning, diff inspection, building into multiple independent artifacts, and rolling back to previous versions.

When choosing this solution, each version needs a **version ID, hash, compile/test status, target API, and activation permissions**. Do not recompile any source snippet on every request if a corresponding artifact already exists. A model worth considering is **compiling at the version publishing step**, then loading only approved results.

### 3.4. Goal Is Review, Testing, or Reproducible Builds

Accepting source code helps inspect implementations, run static analysis, audit dependencies, and rebuild with a deterministic toolchain. However, the need for review does not imply needing to compile inside the running application. It is usually safer and easier to operate if you:

1. Accept source in a build environment.
2. Run appropriate formatters/linters/tests/scans.
3. Compile with a fixed toolchain, producing a versioned artifact.
4. Verify checksums/signatures and deploy the artifact.
5. Have the host install the JAR / load the service provider when needed.

A good design option can **accept source at the development gate while accepting only JARs at the runtime gate**.

## 4. When Should You Only Install a Precompiled JAR?

**Prefer a prebuilt JAR** when the plugin is released by a development team or vendor, has a stable SPI interface, rarely needs direct per-run edits, and already has a build, test, and artifact verification pipeline.

Typical scenarios:

- Adding a released JDBC driver, SPI implementation, format processor, or extension adapter.
- Deploying a patch or plugin version already tested in staging.
- The runtime is minimized with **jlink**, a small container, or an environment with only runtime modules and no compiler.
- Fast startup/activation and reproducible build outputs are needed, and you do not want compiler flags/dependency resolution to become the host's responsibility.
- Wanting to use a registry, Maven repository, or artifact distribution system with checksums/signatures.

A JAR is not automatically "safe" or "compatible." A JAR's bytecode can still read files, open network connections, modify data, or crash the JVM. The host must verify provenance, version, loader/module visibility, API contract, and policy before activation.

A JAR can contain **META-INF/services** for ServiceLoader to discover providers on the classpath, or **module-info.class** with a **provides ... with ...** directive on the module path. Both discovery mechanisms must be configured properly; dropping a JAR file into a directory does not cause a running JVM to automatically find it if the host has no reload/scan mechanism.

## 5. Mandatory Prerequisites Before the Host Accepts Source

### 5.1. An Actual Compiler Must Exist, Not Just a Java Runtime

The standard **javax.tools.JavaCompiler** API lets you invoke the compiler from Java code; the implementation is usually obtained via **ToolProvider.getSystemJavaCompiler()** when running on a JDK with **jdk.compiler**. The return value **can be null** if the runtime image does not contain a system compiler.

**java.compiler** contains the JavaCompiler API; **jdk.compiler** provides the compiler implementation in standard JDKs. Applications packaged with jlink must verify included modules. In production, you should not assume "having the `java` command" means "having `javac`."

You can run the compiler in a **separate build service** and have the runtime load only verified artifacts. This is often the better option when the runtime must stay slim or has security constraints.

### 5.2. A Clear SPI Contract

Accepted source code must know which interface to implement, which DTO types to use, and which APIs it is allowed to call. Define inputs/outputs, nullability, exceptions, thread safety, timeouts, and ownership at the boundary.

On the classpath, you should place **the API/SPI in the parent loader** and implementations in child loaders. If the same interface name is defined by two different loaders as two distinct versions, the freshly compiled class still cannot be cast to the host API. With JPMS, you must clarify **module readability, exports/opens, uses/provides**, and ModuleLayer; you cannot assume placing `.class` files into a URLClassLoader will automatically add them to an existing named module.

### 5.3. Complete Build Inputs with Exact Versions

The compiler needs:
- Source files with matching packages and public types, plus related sources if compiling multiple classes.
- **Classpath or module path** containing the required dependencies, in the right versions and order.
- Target Java version, **--release**, or an appropriate source/target pair.
- Compiler options, encoding, annotation processor policy, and output directory.
- A way to collect **diagnostics**: severity, file, line/column, error code; not just a boolean success/failure.
- A mechanism to inspect class outputs and artifact provenance after compilation.

JavaCompiler **does not automatically download Maven dependencies**, does not run Gradle/Maven, and does not automatically solve every module graph issue. For complex projects using annotation processors/code generation, a build tool may be more appropriate than invoking the compiler once with a list of `.java` files.

### 5.4. Decisions on Trust and Execution Timing

If code comes from untrusted users or partners, **do not compile and execute it directly inside the host JVM** with the host process's own privileges. Accepting source does not mean you can verify its intent; after compilation, code can perform I/O, make network calls, spawn threads, hold locks, or mutate state.

You must separately design access permissions, publisher authentication, resource limits/timeouts, and an isolated environment. For untrusted content, consider a restricted-capability DSL or **a pipeline that compiles and executes in an isolated process/container**. JavaCompiler, URLClassLoader, and JAR signing **do not create a sandbox** by themselves.

## 6. Complete Java 17 Example: Compiling Source and Loading a Task

This exercise simulates a host receiving an implementation as Java source. To run standalone and clearly verify results, the example embeds trusted source in a **String**. In a real system, this source snippet would be fetched from a reviewed and verified version.

**Technical goals**:
1. The host keeps a stable **Task** interface.
2. JavaCompiler compiles the **dyn.UpperTask** source against the host's API.
3. The host loads `.class` files in the output directory using a child URLClassLoader.
4. The object is cast to **Task** and executed.
5. The host closes the file manager/loader and cleans up the temporary output directory.

This is a learning example about compiling/loading. It is not a production pipeline with sandboxing, code signing, rate limiting, or caching.

Create **src/demo/Host.java**:

~~~java
package demo;

import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class Host {
    public interface Task {
        String run(String input);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }

        String pluginSource = """
                package dyn;
                public final class UpperTask implements demo.Host.Task {
                    public String run(String input) {
                        return input.toUpperCase(java.util.Locale.ROOT);
                    }
                }
                """;

        JavaFileObject unit = new SimpleJavaFileObject(
                URI.create("string:///dyn/UpperTask.java"), JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return pluginSource;
            }
        };

        Path classes = Files.createTempDirectory("runtime-plugin-");
        try {
            DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
            try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
                List<String> options = List.of(
                        "--release", "17",
                        "-proc:none",
                        "-classpath", System.getProperty("java.class.path"),
                        "-d", classes.toString());
                boolean success = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, diagnostics, options, null, List.of(unit)).call());
                if (!success) {
                    diagnostics.getDiagnostics().forEach(System.err::println);
                    throw new IllegalStateException("Plugin compilation failed");
                }
                System.out.println("Compiled: " + success);
            }

            try (URLClassLoader child = new URLClassLoader(
                    new URL[]{classes.toUri().toURL()}, Host.class.getClassLoader())) {
                Class<?> type = child.loadClass("dyn.UpperTask");
                Task task = (Task) type.getDeclaredConstructor().newInstance();
                System.out.println("Result: " + task.run("hello"));
                System.out.println("Child defines provider: " + (type.getClassLoader() == child));
                System.out.println("Host API compatible: " + Task.class.isAssignableFrom(type));
            }
        } finally {
            try (var walk = Files.walk(classes)) {
                for (Path file : walk.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(file);
                }
            }
        }
    }
}
~~~

Explanation:

- **ToolProvider.getSystemJavaCompiler()** obtains the system compiler. If unavailable, the example fails before compiling.
- **SimpleJavaFileObject** represents an in-memory Java source file with URI **string:///dyn/UpperTask.java** matching the class name **dyn.UpperTask**; **getCharContent** supplies the entire source.
- **StandardJavaFileManager** manages standard inputs/outputs and is closed in a try-with-resources block. With **-d**, the compiler writes `.class` files into a temporary directory.
- **--release 17** requests compilation against the Java 17 platform language/APIs when the compiler supports that release; it does not guarantee compatibility of non-JDK libraries.
- **-proc:none** disables annotation processing for the example so processors on the compiler classpath are not accidentally executed. If a system genuinely needs processors, they must be defined, version-pinned, and controlled via processor path.
- **-classpath System.getProperty("java.class.path")** puts **demo.Host.Task** into the set of classes visible to the compiler in this example. When the host uses different loaders/modules, construct the classpath/module path according to the architecture; do not copy this approach verbatim without checking.
- **Boolean.TRUE.equals(...call())** distinguishes successful compilation from null/false; on failure, the code prints diagnostics and stops before the class loading step.
- URLClassLoader is created with **Host.class.getClassLoader()** as its parent: the shared **Task** interface remains defined by the parent, while the new provider exists only in the child output directory.
- **getDeclaredConstructor().newInstance()** requires an accessible no-arg constructor. In the example, `UpperTask` is a public class declaring no constructors, so Java generates a public default constructor.
- try-with-resources closes the loader, and **Files.walk** deletes temporary output in child-before-parent order. Closing the loader does not guarantee classes are immediately unloaded if references remain.

### 6.1. Compiling and Running on JDK 17 or Later

From the directory containing **src/**, create the output directory and compile the host:

~~~bash
mkdir -p out
javac --release 17 -d out src/demo/Host.java
java -cp out demo.Host
~~~

On Windows PowerShell, replace only the directory creation step with **New-Item -ItemType Directory -Force out**, while keeping the two **javac** and **java** commands unchanged.

Standard output, given the example's code and classpath:

~~~text
Compiled: true
Result: HELLO
Child defines provider: true
Host API compatible: true
~~~

The output shows **source was compiled at runtime**, the provider is defined by **the child loader**, and the `Task` interface retains **the same type identity** with the host. This is why separating loaders matters even when compilation itself succeeds.

### 6.2. Where Is Source Compiled and Where Is the Output Stored?

The example uses an in-memory URI for **source**, yet the output is still **.class files** in the temporary directory specified by **-d**. This is an **in-memory input + disk output** model, not a process executed entirely in RAM.

To stay completely in-memory, you need a custom **JavaFileManager** implementation to hold bytecode and a ClassLoader with **defineClass** reading those `byte[]` arrays. This approach is useful when temporary disk output must be avoided, but it is more complex and requires managing packages, dependencies, class identity, and lifecycle. Do not choose it just for the "in-memory" label if a well-managed temporary directory already meets your needs.

### 6.3. Limitations of the Example

- Compiles **one implementation** and instantiates it via reflection; it does not automatically manage full multi-file projects or annotation processors.
- No validation, authentication, or sandboxing for external source code.
- No caching: every execution of `main` recompiles.
- Does not run in a custom ModuleLayer or deploy a `module-info.java` for the plugin.
- No SLA for compilation time, RAM/CPU limits, timeouts, or rollback.
- Does not run arbitrary source entered from the web/customers; the source is hardcoded so the example is safe and deterministic.
- Does not turn source into a JAR automatically: if artifact distribution is needed, a separate packaging and metadata step is required.

## 7. Does Accepting Source and Compiling Fix JAR Compatibility Errors?

It can solve **some compilation or bytecode target errors** when full source and dependencies are available, but not all errors.

| Symptom when installing a JAR | How do source and recompilation help? | What else must be checked? |
| --- | --- | --- |
| **UnsupportedClassVersionError** because bytecode is newer than the JVM | Can recompile with **--release** supported by the compiler if source does not use too-new features | Are target APIs/libraries and source compatible with the older Java version? |
| **NoSuchMethodError** after a library change | Can recompile, catching stale signatures at build time | Do all runtime dependencies have the right versions and behavior? |
| **ClassNotFoundException** due to missing dependency | Recompiling alone does not create the missing library | Source dependencies, compile path, and runtime path |
| **ClassCastException** across loaders | Source can still produce two copies of the API in two loaders | API/SPI type identity and parent delegation |
| **IllegalAccessError** or JPMS constraints | Recompiling only helps if the access design is fixed properly | `module-info.java`, `requires`, `exports`/`opens`, and layers |
| Incorrect business results | Nothing guaranteed by successful compilation | Contract tests and integration tests |
| Initialization failure or missing environment configuration | Compiler may pass while the plugin still fails at runtime | Config, resources, native libraries, permissions, and lifecycle |

If a plugin already has a compatible JAR, demanding source and recompiling may produce an untested combination of versions. **Reproducibility** and proving that the running artifact corresponds to the exact source/flags/dependencies matter more than the feeling that "building on this machine probably makes it compatible."

## 8. Classpath, Module Path, and Post-Compilation Loading Strategy

### 8.1. Classpath Plugins

In a simple program, source compiles with **-classpath** to reference the host API. A child URLClassLoader then loads the compiled classes. Parent-first delegation lets them share a single SPI definition, while each plugin can have its own loader and packages.

Avoid:
- Placing a duplicate copy of the SPI into the child loader and using child-first, giving the same interface two identities.
- Letting the host API directly reference implementation classes that only exist in the child loader.
- Holding static references to an old ClassLoader after loading a new version.
- Merging multiple incompatible JARs/versions into a single global classpath.

When installing a prebuilt JAR, the host can likewise pass the JAR's URL to a URLClassLoader and discover implementations via **ServiceLoader.load(service, loader)**. **JavaCompiler does not need to participate** in this flow.

### 8.2. Named Modules and JPMS

For a plugin packaged as an **explicit named module**, you must compile with appropriate options such as **--module-path** and **--module-source-path**, declare **module-info.java** when needed, and manage a **ModuleLayer**. Simply writing bytecode to a directory and passing a URL to a loader does not turn that module into a properly resolved module.

SPI via JPMS typically uses **uses Service** in the consumer and **provides Service with Provider** in the provider; the host should invoke ServiceLoader against the appropriate layer. The implementation package can stay encapsulated without `exports`/`opens` to the host, while the provider is still instantiated by ServiceLoader through JPMS mechanisms.

If there is no operational reason to construct module graphs dynamically at runtime, compile modules in the build pipeline and install artifacts according to a defined JPMS configuration.

## 9. Runtime Compilation Cost and How to Reduce It

**Compiling has a different cost profile than loading.** The compiler must parse/resolve/type-check/generate bytecode; it may require multiple sources, annotation processors, a module graph, and file I/O. For rules that change rarely but are invoked frequently, compiling on every request increases latency, CPU, memory, and abuse risk.

Practical model:

~~~text
Approved source version
       |
       v
Build key: source hash + API version + compiler target
       + options + dependency fingerprint + processor version
       |
       v
Valid artifact already cached?
   | yes                     | no
   v                         v
Read artifact               Compile + test + verify
   |                         |
   +------------+------------+
                |
                v
        Activate selected version
                |
                v
       Invoke repeatedly, no recompilation
~~~

You should pin **release target, classpath/module path, compiler version, processor policy, dependency versions, and source hash**. Using only the source hash will break when the API or compiler flags change. Build outputs need immutable identifiers for rollback and diagnostics.

Each activated version may require **its own loader**. When swapping versions, drain traffic from the old loader, stop callbacks, close resources, and release references before expecting class unloading. **URLClassLoader.close() does not automatically unload classes** and does not terminate threads spawned by the plugin.

For many small variants, check whether an interpreter/DSL or configuration parameters passed to a prebuilt implementation are cheaper than generating many classes. "Can compile" does not mean "should compile."

## 10. Safety: Controlling Both Compilation and Execution

This is the decisive requirement if source does not come from a trusted development team:

- **Java source has the full power of Java code**, not a passive configuration file. Once classes are loaded and executed, code can access whatever resources the process permits.
- **Annotation processors and compiler plugins** are code that can run during the build stage. The example uses **-proc:none** to disable processors for the demo source; projects that use processors must pin, review, and isolate them.
- Limit source size, file count, compilation time, CPU/memory/disk, and stored version count. Validation/quotas are required before compiling.
- Do not casually mix the compiler classpath with sensitive internal libraries; expose only the APIs needed to build. However, **hiding libraries from the compiler path is not an execution-time sandbox**.
- Compile and run in an **isolated process/container** if you must accept source from untrusted parties; apply appropriate filesystem/network permissions, resource quotas, and lifecycle controls.
- Audit provenance, hashes, versions, and logs; do not store source/diagnostics containing secrets as public plain text.
- Do not treat **SecurityManager** as the default modern sandbox model; in Java 17 it is already marked deprecated for removal and has many practical limitations.

Prebuilt JARs also require appropriate trust measures. The difference is that with source, the host must also govern **the compiler/build pipeline**. Accepting source should not be marketed as "safer" merely because the code is readable.

## 11. Common Pitfalls in the Source Compilation Flow

| Error | Symptom | Proper Handling |
| --- | --- | --- |
| Running on a runtime without a compiler | `ToolProvider.getSystemJavaCompiler()` returns `null` | Install an appropriate JDK or move compilation to a build service |
| Source uses syntax/API outside target | Diagnostics report release or symbol errors | Fix source/target; pass `--release` explicitly |
| Missing classpath/module path | `cannot find symbol`, `package does not exist` | Configure exact dependencies; do not guess from the environment |
| Wrong package or binary name | `ClassNotFoundException` when loading output | File name, package, `JavaFileObject` URI, and load name must match |
| Compiles successfully but cannot cast | `ClassCastException` | Share the SPI properly via parent loader or shared module |
| Source compiles but runtime linkage fails | `NoClassDefFoundError`/`NoSuchMethodError` | Verify runtime dependencies and artifact versions |
| Overusing one loader for multiple versions with the same name | Keeps using already-loaded class or `LinkageError` | Activate versions using appropriate loaders/layers |
| Accumulating temp outputs/loaders | Disk/memory growth, unclosed resources | Close file manager/loader, clean temp files, clear references/callbacks |
| Diagnostics leak secrets | Logs contain source or sensitive paths | Redact info, attach request/version IDs instead of logging full source |
| Compiling on every request | Rapid latency/CPU increase | Cache output by all build inputs and compile per version |
| Accepting untrusted source directly in the host | Code can cause unintended side effects | Use a DSL or compile/execute in an isolated process |

**Distinguishing errors:** a compile failure is not a missing plugin; a class loading failure is not a Java source syntax error; an extension throwing an exception at runtime does not prove the compiler failed. Each stage should have distinct states and diagnostics: RECEIVED → VALIDATED → COMPILED → VERIFIED → ACTIVATED → FAILED/RETIRED.

## 12. Scenario-Based Decision Flow

~~~text
Is a JAR of the right plugin and contract version already available?
   |
   +-- Yes --> Is the JAR tested/trusted?
   |              |
   |              +-- Yes --> Install JAR via host loader/layer
   |              |
   |              +-- No --> Require proper source/provenance/tests
   |
   +-- No --> Do you need a custom Java implementation?
                    |
                    +-- No --> Look for config/DSL/existing plugin JAR
                    |
                    +-- Yes --> Is the source trusted and versioned?
                                 |
                                 +-- No --> Do not compile and run
                                 |           in the host JVM; design isolation
                                 |
                                 +-- Yes --> Must compilation happen in the host?
                                              |
                                              +-- No --> CI/build service
                                              |           produces verified JAR
                                              |
                                              +-- Yes --> Check JDK compiler,
                                                          API/dependencies,
                                                          quotas/cache,
                                                          tests, and loader
~~~

### Three Comparative Scenarios

**Scenario A: installing a released data-format provider.** A vendor delivers a JAR with a compatible SPI implementation, already tested and checksummed. The host only needs to set up the appropriate plugin loader/ServiceLoader. **Choose a JAR**; requiring runtime source compilation adds no clear value.

**Scenario B: an enterprise customer has a custom adapter reviewed by an internal team.** The adapter must differ per API version, yet updates weekly. You can **accept source**, run build/test in CI, produce a separate JAR, and release it with versioning. **No compilation is needed inside the request-serving JVM**.

**Scenario C: a generator system creates Java classes from a schema newly configured at runtime.** Each approved schema produces an implementation that must be loaded immediately, the compiler is provisioned, and execution stays within a designed boundary. You can **compile source per schema version**, cache the bytecode, and invoke only verified implementations. If schemas are controlled by untrusted users, add appropriate limits and isolation mechanisms before allowing code execution.

## 13. Checklist Before Accepting Java Source as Extension Input

1. **Clear reason for source:** the plugin genuinely needs to be generated/customized/rebuilt from source, rather than simply installing an existing JAR.
2. **Compilation stage defined:** CI, build service, plugin installation time, or runtime per version; never recompile pointlessly on every request.
3. **Compiler defined:** JDK/`jdk.compiler` module or a separate build service, release target, options, and dependency resolution.
4. **Shared API/SPI:** separate class loader/module layer and ensure assignability, null/exception contracts.
5. **Clear diagnostics:** syntax, compile, load/link, instantiation, and runtime errors are reported as separate stages.
6. **Testing and versioning:** source hash, dependency/compiler fingerprint, immutable artifacts, activation/rollback, and caching.
7. **Resource and trust limits:** input validation, processor policy, quotas, and filesystem/network isolation if source is untrusted.
8. **Lifecycle management:** close loaders/resources, stop threads/callbacks, clear old references on version swaps.
9. **Operational strategy:** logs, observability, compilation duration, concurrent versions, and security of source and diagnostics.
10. **Compared against JAR/DSL/config:** the chosen solution must solve the business need at an appropriate cost.

**Core principle:** accept Java source code when **you need control or must generate implementations before bytecode exists**; install a precompiled JAR when **you only need to distribute and activate already-built behavior**. JavaCompiler adds a runtime bytecode-generation step, but it does not eliminate responsibilities for compatibility, class loading, testing, caching, and execution safety.

## Java 17 References

- JavaCompiler: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- ToolProvider: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- ClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- URLClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
