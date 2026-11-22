# Cross-Referencing Bytecode, Library Versions, and Source Code When Traces Do Not Match

## 1. The Problem: The Stack Trace Points to a Line That Does Not Match the Open Code

A Java exception might log:

~~~text
java.lang.IllegalStateException: failed to create invoice
    at com.example.billing.InvoiceService.create(InvoiceService.java:87)
    at com.example.billing.InvoiceController.submit(InvoiceController.java:32)
~~~

This is an **illustrative trace**, not output from the program run in the hands-on section. You open `InvoiceService.java` in your IDE, but line 87 is just a comment, a different call, or the current file only has 75 lines. Several causes are possible:

- The JVM is running **class files compiled from an older version of the code**.
- The class was loaded from **a different JAR** than the one you think.
- Multiple versions of the same dependency exist, and **runtime selected a different version** than the one used at compile time.
- The build generates/transforms bytecode, performs shading, obfuscation, or instruments classes.
- `SourceFile` / `LineNumberTable` information in the class is missing, outdated, or no longer maps intuitively to the open source file.
- The outermost exception is only a **wrapper**, while the line actually throwing the error is in `Caused by`.
- The executing code belongs to a lambda, bridge method, proxy, or dynamically generated class; the file and method in the trace do not have a simple one-to-one mapping to a current Java source line.

**Do not edit code based on the line numbers shown in the IDE without verifying the artifact actually running.** A stack trace reflects information that the runtime obtains from bytecode/exception objects and metadata of the loaded class; it does not automatically update to match your current Git checkout.

Objectives of this lesson:

1. Understand why bytecode does or does not contain source-line metadata.
2. Use `javap` to cross-reference `LineNumberTable` with a stack trace.
3. Identify the exact class/JAR version, class loader, module, and runtime dependency.
4. Distinguish source-line mismatch issues from version/binary compatibility errors.
5. Handle tricky scenarios: fat JARs, multi-release JARs, shading, obfuscation, generated code, and async.
6. Establish a verifiable diagnostic workflow using build IDs, artifacts, and reproducible tests.

## 2. Three Layers of Information That Must Always Be Separated

An investigation typically involves three layers:

| Layer | What Does It Contain? | Key Question |
| --- | --- | --- |
| **Source** | `.java` files, Git commits, generated sources, lines in the IDE | Is this the exact source used to produce the running class? |
| **Artifact/bytecode** | `.class` files, JAR, WAR, executable JAR, image, module; constant pool, bytecode, debug attributes | Which class file was compiled, packaged, and distributed? |
| **Runtime** | JVM, class loaders, module path/classpath, container, JDK, and actual dependencies | Which version of the class did the JVM load when the exception occurred? |

Example:

~~~text
Git commit A         -> javac -> Service.class (line 87)
                             -> app-old.jar
                             -> production JVM

Git commit B         -> IDE shows Service.java (line 87 has changed)
~~~

If runtime is still running `app-old.jar`, opening commit B in the IDE does not change the line numbers in production stack traces. Switching Git branches or recompiling on a local machine does not prove that the server is using the new class either.

**The proper chain of evidence** must go from logs -> deployment/runtime identity -> actually loaded class file -> corresponding source/build, rather than working backward from the "latest source" and forcing the trace to fit.

## 3. What Information Does the JVM Use to Display Source Lines?

A class file has the following relevant structures/attributes:

- **`SourceFile` attribute:** the source file name recorded by the compiler, typically `Service.java`, not an absolute path to the repository.
- **`Code` attribute:** the executable bytecode of each specific method.
- **`LineNumberTable`:** a mapping from the **starting index of a bytecode instruction (`start_pc`)** to a **source line number**. Multiple instructions can belong to the same line; one source line can have multiple bytecode locations.
- **`LocalVariableTable`:** information about certain local variables (when emitted) to aid debugging; not required for a stack trace to display `file:line`.
- Class/method metadata, descriptors, constant pool, and flags, which help identify the method executed by the JVM even if the source is no longer on the machine.

A stack trace might show:

~~~text
at com.example.app.PriceService.compute(PriceService.java:114)
~~~

This means the runtime can attribute that frame to `PriceService.java` line 114 according to metadata attached to the loaded class. It **does not guarantee** that every operation on line 114 is the root cause, nor does it guarantee that the currently checked-out source is the compiled file.

In particular, within a complex expression or multiple instructions corresponding to the same line, a stack trace usually only pinpoints the **line**, without automatically identifying which exact subexpression caused the exception.

### 3.1. `File.java:line` Is Not an Absolute Path

`StackTraceElement.getFileName()` typically returns a file name such as `OrderService.java`, not `src/main/java/com/example/OrderService.java`. You need to combine the fully qualified class name, package, module, and artifact to know which file is actually involved.

An `Outer$Inner` class usually comes from `Outer.java`; a lambda may appear as `lambda$process$0` in a class's frame. Do not infer a source file name by appending `.java` to a synthetic class name.

### 3.2. `Unknown Source` and Negative Line Numbers

If a class lacks `SourceFile` or `LineNumberTable`, the frame may display `Unknown Source` or only the file name without a line number. In the `StackTraceElement` API, `getFileName()` may be `null` and `getLineNumber()` may return a negative number.

Some classes do not preserve stack traces due to custom constructors, stripped debug info, obfuscators/bytecode transformers, or special runtime/optimization mechanisms. **Do not guess line numbers** when metadata is absent; verify the loaded class and rebuild with debug info when appropriate.

## 4. Runnable Java 17 Example: Line Numbers Come from the Class File, Not the IDE

Below is a standalone program demonstrating a stack trace with source-line metadata. Save it as **`BytecodeTraceDemo.java`** with the first line being the class declaration itself (do not insert a blank line at the top) if you want the line number output to match the sample.

~~~java
public class BytecodeTraceDemo {
    static void verify(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative value: " + value);
        }
    }

    static void service() {
        verify(-3);
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalArgumentException error) {
            System.out.println(error.getClass().getSimpleName() + ": " + error.getMessage());
            for (StackTraceElement element : error.getStackTrace()) {
                if (element.getClassName().equals(BytecodeTraceDemo.class.getName())) {
                    System.out.println(element.getMethodName() + " -> "
                            + element.getFileName() + ":" + element.getLineNumber());
                }
            }
        }
    }
}
~~~

From the directory containing the source with JDK 17+:

~~~bash
javac --release 17 BytecodeTraceDemo.java
java BytecodeTraceDemo
~~~

Verified stdout with `javac` storing line number information by default:

~~~text
IllegalArgumentException: negative value: -3
verify -> BytecodeTraceDemo.java:4
service -> BytecodeTraceDemo.java:9
main -> BytecodeTraceDemo.java:14
~~~

Direct cross-reference with the source:

- `verify`, line **4**: creates/throws `IllegalArgumentException`.
- `service`, line **9**: calls `verify(-3)`.
- `main`, line **14**: calls `service()` inside `try`.

In this case, the trace shows the path from where the exception originated back to callers in the same class. If you add a comment before line 4 **and recompile**, the new line numbers will reflect the new source. However, if you edit the source and **do not recompile the running class**, the output from the old bytecode remains `4`, `9`, `14`: that is a minimal example of source and artifact drifting out of sync.

### 4.1. Experiment: Disabling Debug Metadata

Recompile the same file with:

~~~bash
javac --release 17 -g:none BytecodeTraceDemo.java
java BytecodeTraceDemo
~~~

Verified stdout:

~~~text
IllegalArgumentException: negative value: -3
verify -> null:-1
service -> null:-1
main -> null:-1
~~~

The class/method names are still known to the JVM, but the file name and line numbers are lost in this experiment because the bytecode no longer has the corresponding debug attributes. **`-g:none` does not remove the exception-throwing logic**; it only reduces the ability to correlate the trace with source.

To restore line/source information, recompile, for example:

~~~bash
javac --release 17 -g:lines,source BytecodeTraceDemo.java
java BytecodeTraceDemo
~~~

The line numbers return as in the default example for the given source file.

Note: overwriting `BytecodeTraceDemo.class` with a new build after each compile command replaces it; if you want to compare two artifacts simultaneously, compile them into **two different build directories** using `-d` and specify the corresponding classpath. That is also what you should do when investigating two real-world versions.

## 5. Reading Bytecode and LineNumberTable with `javap`

`javap` is the disassembler/inspector tool bundled with the JDK. Useful options:

| Command/Option | Purpose |
| --- | --- |
| `javap -c -l ClassName` | Print bytecode and line/local-variable tables when present |
| `javap -c -l -p ClassName` | Include private/package-private methods |
| `javap -v ClassName` | Print more detailed class file info: version, constant pool, attributes |
| `javap -classpath path/to/app.jar -c -l -p package.Class` | Inspect a specific class from a JAR |
| `javap -c -l -p path/to/Foo.class` | Directly inspect a class file via an appropriate path |

With the `BytecodeTraceDemo` example after compiling with metadata:

~~~bash
javap -c -l -p BytecodeTraceDemo
~~~

The relevant `LineNumberTable` sections of the output contain mappings such as:

~~~text
static void verify(int);
    ...
    LineNumberTable:
      line 2: 0
      line 3: 0
      line 4: 4
      ...

static void service();
    ...
    LineNumberTable:
      line 8: 0
      line 9: 0
      ...

public static void main(java.lang.String[]);
    ...
    LineNumberTable:
      line 12: 0
      line 14: 0
      ...
~~~

These are **simplified illustrative excerpts**, not the full `javap` output; bytecode offsets outside the verified portions may vary by compiler/options. For the Java 17 test above, the mappings `line 4: 4`, `line 9: 0`, and `line 14: 0` were verified in practice.

**Meaning of `line 4: 4`:** the instruction at bytecode offset 4 is associated with source line 4. It does not mean "line 4 corresponds to bytecode line 4" or a machine memory address. If multiple instructions belong to line 4, the table usually records only the starting offsets needed for mapping.

In some JDK versions, running `javap -l` **without `-c`** may only print a warning and omit the line number table as expected; use `javap -c -l` or `javap -v` to see the complete data. Do not treat running a command with the wrong options and not seeing the table as proof that the class lacks metadata.

### 5.1. Step-by-Step Cross-Referencing Bytecode with Source

1. Obtain the **actual class file** from the artifact of the failing environment.
2. Run `javap -c -l -p` with the right classpath or path to the class file.
3. Locate the method name from the frame, including its descriptor/overload if multiple methods share the same name.
4. Inspect `LineNumberTable` for that method; confirm whether the line mentioned in the stack trace exists in the metadata.
5. Open the source of the **build that produced this class**, at that exact line; inspect the entire expression and nearby call sites.
6. If the source does not match while `LineNumberTable` matches the trace, you are very likely looking at the wrong source revision, or the class was generated/transformed after compilation.
7. If `LineNumberTable` in the retrieved artifact does not match the trace, you very likely retrieved the **wrong artifact/classloader/JAR**, or runtime has bytecode instrumentation/transformation; go back to verifying the loaded class.

If source line 100 contains multiple calls, read the bytecode/operand stack or split the expression into named steps in a reproducing test to find out where the null/exception comes from. Do not edit code based solely on offsets or the line table.

### 5.2. `-g`, `--release`, and Runtime Version Are Different Concepts

- `-g:lines,source` instructs the compiler to emit source/line-number info.
- `-g:none` disables debug info emitted by `javac`.
- `--release 17` compiles targeting Java 17 APIs and bytecode; it **does not lock third-party dependency versions**, does not guarantee the deployment used the right JAR, and does not guarantee the current application release is the version you are viewing.
- `java -version` only reports the JDK/JRE where **that command** runs; to diagnose a real server, you must verify the runtime of the actual process/server.
- A class file has a `major version` matching the Java target, but that version does not encode a Git commit or Maven artifact version.

A program can be compiled with `--release 17`, run on JDK 21, use a newer Java-compatible library version, and still have stack trace line numbers from a class compiled with old source. These factors are independent.

## 6. Finding the Exact JAR/Class Loaded by the JVM

Before comparing source, answer: **where did the failing class come from?** In a large application, there may be multiple class loaders, nested JARs, a module path, plugins, or the same class name across multiple versions.

### 6.1. Checking `CodeSource` via API

The following Java snippet is a **fragment**, assuming `InvoiceService` is an application class reachable from where it runs:

~~~java
Class<?> type = InvoiceService.class;
var domain = type.getProtectionDomain();
var codeSource = domain == null ? null : domain.getCodeSource();
System.out.println(codeSource == null
        ? "unknown"
        : codeSource.getLocation());
~~~

If `CodeSource` exists, the returned URL can point to the classes directory or JAR containing the class. However:
- `getCodeSource()` can be `null`.
- For JDK modules, custom loaders, nested/fat JARs, or dynamically generated classes, the displayed location may not reflect a "normal" JAR file that can be opened directly.
- `CodeSource` is not complete proof of a Git commit/source revision.
- Server paths and deployment details should not be logged publicly.

Reading `getClassLoader()` and `getModule()` can also help distinguish where a class was loaded from. Some JDK classes have a `null` classloader (bootstrap), which is not an error.

### 6.2. JVM Class Loading Logs

With a JVM supporting Java 9+ unified logging, you can enable class loading logs in a diagnostic environment:

~~~bash
java -Xlog:class+load=info -cp path/to/app.jar com.example.Main
~~~

This is a **reference** command: `path/to/app.jar` and `com.example.Main` are path/class name placeholders that must be replaced with the actual artifact; for applications launched via `java -jar`, module path, or an app server, startup differs. Class loading logs can reveal the source from which a class was loaded.

Consider log volume and sensitive information, and do not leave verbose debug logging enabled in production long-term. Logging class loads for a runtime you start **does not automatically prove** another runtime in production uses the same set of classes, unless configuration/artifacts are verified.

### 6.3. Inspecting Inside a JAR

Reference command examples:

~~~bash
jar tf path/to/library.jar
javap -classpath path/to/library.jar -c -l -p com.example.lib.Parser
~~~

`jar tf` lists packaged entries. `javap` reads classes from the classpath you specify. Do not confuse `javap` finding a class in a JAR with the runtime definitely **having loaded that exact class**: the actual class loader and resolution order decide.

One JAR can contain `com/example/lib/Parser.class` with the same name as another JAR. If two versions exist, verify artifact identity, checksums, classloader location, and actual load results before concluding.

## 7. Distinguishing Compile-Time Dependencies from Runtime Dependencies

A common bug occurs when the IDE or build compiles against library **v2**, while runtime runs the same library name at **v1**.

Hypothetical scenario example:

~~~text
Compile:
    app.class -> lib-api 2.0, has method parse(String, int)

Runtime:
    app.class -> lib-api 1.4, only has parse(String)

When the call is resolved:
    java.lang.NoSuchMethodError
~~~

A `NoSuchMethodError` is usually a sign of a **binary linking/runtime compatibility mismatch**, not a checked exception from normal input handling. The application frame at the call line may look completely valid in v2 source, yet the JVM cannot find a method with the matching name/descriptor on the runtime class.

Errors to distinguish:

| Symptom | Common Explanation | Check |
| --- | --- | --- |
| `NoSuchMethodError` | Runtime type lacks a method with the descriptor called by bytecode | `javap -p -s` on the runtime dependency class; check versions |
| `NoSuchFieldError` | Field expected at compile time does not exist at runtime | Check field descriptor and dependency version |
| `IncompatibleClassChangeError` | Class/interface/static/instance or binary structure is incompatible | Check API changes and actual loaded class file |
| `AbstractMethodError` | Runtime dispatch finds no matching implementation | Check interface/implementation ABI and mixed versions |
| `ClassNotFoundException` | Attempted to load a class by name, but the loader could not find it | Classpath/module path, plugin loading, artifact layout |
| `NoClassDefFoundError` | Class needed during linking/initialization could not be defined/used; may also relate to an earlier init error | Check cause, initial init error, classloader, and dependencies |
| `UnsupportedClassVersionError` | Class file was compiled for a higher JVM version than runtime supports (or unsupported) | Process `java -version` and `javap -verbose` on the class |
| `ExceptionInInitializerError` | Static initializer threw an exception | Check `<clinit>`, cause, and class initialization state |

In many cases, linkage errors are `LinkageError`/`Error` and should not be "fixed" with `catch (Exception)` and returning a fallback. Broad catching can hide the root cause and let the system continue in a broken state. **Resolving artifact/dependency compatibility is the primary fix**.

### 7.1. Is the Method Descriptor More Important Than the Method Name?

Yes. Bytecode references a method by **name, class/interface, and descriptor** (parameters/return type). Two library versions that both have a method named `parse` but with different descriptors can still cause `NoSuchMethodError`.

Use:

~~~bash
javap -classpath path/to/library.jar -p -s com.example.lib.Parser
~~~

`-s` displays internal type signatures (descriptors) alongside signatures, which is helpful for overloads, generic erasure, primitive/reference type changes, or return type changes. `javap -c -v` on the calling class lets you inspect the constant pool and `invoke` instruction target when needed.

Generic source may look similar due to type erasure, yet bridge methods and actual descriptors still affect linking. Therefore, do not conclude "the method exists so the JVM is wrong to throw NoSuchMethodError" merely by searching for the text `parse` in the IDE.

## 8. Tracing Dependencies via Maven/Gradle

In a Maven project, commonly used commands:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dverbose
~~~

These are **reference commands for Maven projects with the appropriate plugin**; exact options depend on the `maven-dependency-plugin` version. Inspect the dependency tree under the right module/profile configuration, considering dependency mediation, scope, exclusions, and parent/BOM management. A clean compile-time tree **is not enough** to prove an application server is not supplying an extra runtime JAR.

In a Gradle project:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency group:name --configuration runtimeClasspath
~~~

These are **reference commands**; replace `group:name` with the actual dependency. On Windows, the wrapper is usually `gradlew.bat`. `dependencyInsight` shows why a version was selected, conflict resolution, and the dependency chain in the inspected configuration. Actual configuration names vary by plugin and project type; choose the configuration corresponding to the runtime artifact under investigation.

### 8.1. Why Is a Dependency Tree Still Not Enough?

Because runtime can:
- Have **provided** dependencies supplied by an application server.
- Be packaged as a fat/uber JAR different from the IDE's classpath.
- Have plugins and child classloaders loading a different version.
- Have a cached container image or an accidentally deployed wrong version.
- Have duplicate classes across multiple JARs; classpath/module resolution picks an unexpected class.
- Use shaded/relocated classes with changed namespaces.
- Run multiple instances/versions concurrently during a rollout.

Therefore, combine **dependency tree + contents of released artifact + runtime class loading evidence**. Do not rely on a single source to draw conclusions.

### 8.2. Compare Dependencies in the Right Environment

A build run with profile `prod` can differ from `dev`; Gradle `runtimeClasspath` differs from `testRuntimeClasspath`; the IDE may add workspace libraries that the production JAR does not contain. Verification must record:
- Actual build command/profile/environment.
- Lockfile/BOM/version catalog or resolved dependency versions.
- Build artifact hash and container image digest.
- How the package is built and how the process is started.
- Appropriate JDK/runtime architecture/version.
- Classloader hierarchy when using plugins/app servers.

Do not assume that `mvn test` passing locally proves production is running those exact classes.

## 9. Classpath, Module Path, and Class Loader Decide Which Class Is Chosen

### 9.1. Classpath and Duplicate Classes

On the **traditional class path** (unnamed module), if multiple JARs contain the same FQCN and can be resolved by one loader, classpath order and loader rules can determine which version is used. However, real-world Java class loading is also affected by **parent delegation**, custom class loaders, and runtime embedding. Do not formulate a simplistic rule like "the first JAR wins in every scenario" for all deployments.

Example structure on Linux/macOS:

~~~bash
java -cp "lib/legacy.jar:lib/new.jar:app/classes" com.example.Main
~~~

On Windows, the classpath separator is usually `;` instead of `:`. This is a hypothetical command example; do not run it verbatim without the listed artifacts.

With plugin loaders, application servers, or hot reload, the same class name can be loaded by **two different classloaders**, resulting in two distinct runtime classes even when the displayed name is identical. In particular, a `ClassCastException` like "`com.example.Widget cannot be cast to com.example.Widget`" can relate to differing classloader identities.

### 9.2. Named Modules

On the module path, the Java Platform Module System enforces explicit module resolution and readability/exports. Having the same package/class in multiple modules can cause resolution/access issues under JPMS rules, unlike a flat classpath. When a stack trace includes a prefix like `my.module/com.example.Service`, use it as a clue to the module containing the frame. Do not just strip the prefix and guess the library.

Useful tools include `java --list-modules`, `jar --describe-module --file path/to.jar`, or inspecting `module-info.class`. These commands are meaningful only when applied to the actual running module/artifact.

### 9.3. Java Launcher `-jar` vs. `-cp`

When running `java -jar executable.jar`, the launcher uses the classpath mechanism from the JAR manifest or its own launcher; simply appending `-cp` externally is unlikely to behave the same as running the main class with `-cp`. With Spring Boot executable JARs or frameworks using nested-JAR class loaders, the runtime has its own class-loading logic.

**Do not arbitrarily switch `java -jar` to `java -cp` just to debug** and treat it as the same environment: you may inadvertently alter the classpath and mask the very bug under investigation. Record the actual command line and reproduce using the original packaging.

## 10. Hashes, Build IDs, and Artifact Verification

When a trace does not match source, the reliable approach is to build a "chain of evidence":

~~~text
Log/trace + error timestamp
          |
          v
Deployment ID / pod / instance / build ID
          |
          v
Exact binary artifact or container image
          |
          v
JAR/class file loaded by the classloader
          |
          v
Corresponding source commit + build config + generated sources
          |
          v
Compare stack frame and LineNumberTable
~~~

At the artifact layer, you can use a SHA-256 checksum to identify a JAR file. Example command in PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "C:\deploy\app.jar"
~~~

The command above is an **operational sample**, with an illustrative path. On Unix systems, `sha256sum app.jar` can be used. Checksums verify whether files **have identical bytes**; they do not by themselves prove which source commit was used unless the organization stores build provenance relationships.

Reproducible builds can aid source tracing, but you should not assume every project produces byte-identical JARs upon rebuild: timestamps, tool versions, packaging order, generated code, and metadata can introduce differences. If a hash cannot be reproduced, check the build manifest, CI release record, commit ID, and inspect the specific class file.

### 10.1. What Should Be Stored in Build Metadata?

Attributes with high diagnostic value:
- Git commit SHA and dirty/clean status at build time.
- Build number, pipeline/job ID, timestamp, and build environment.
- Application version and JDK compiler version.
- Artifact checksum and image digest.
- Resolved dependency versions or lockfile.
- Module/component name and generated source info when applicable.

Do not stamp `1.0-SNAPSHOT` onto every image and expect to tell two deployments apart. For critical releases, linking **build ID -> immutable artifact -> commit** is the foundation for trace correlation.

## 11. Shading, Relocation, and Obfuscation: Class Names May No Longer Match Source

When Maven Shade/Gradle Shadow or a bytecode transformation tool **relocates** packages, the trace may show the renamed package. For example, in dependency source it is `com.vendor.json.Parser`, while runtime may contain `com.myapp.shaded.vendor.json.Parser`. Searching the repository for a file under the new package may yield nothing, because the class came from a dependency whose namespace was rewritten at build time.

Questions to check:
- Is there a shade/relocate configuration?
- Which package/class was renamed from what to what?
- Which dependency version does the source JAR correspond to?
- Was debug metadata preserved or altered through transformation?
- Did the stack trace occur before or after agent instrumentation?

If an obfuscator is used, method/class names may be shortened to `a.b.c`; line numbers may be stripped or altered. Some ecosystems provide a **mapping file** to decode them; you need the exact mapping **from the deployed build**. A mapping from another release can produce plausible-looking but completely wrong results.

**Do not treat obfuscated method names as original Java method names.** If the application has a deobfuscation workflow, apply the matching mapping file and verify the result against the corresponding class/JAR.

### 11.1. Bytecode Instrumentation

Monitoring agents, AOP, runtime weaving, or coverage tools can add wrappers and alter call paths. Depending on the tool, bytecode is instrumented while original line numbers are partially preserved, or tool-generated frames may appear. Traces from an instrumented runtime can differ from running the same source **without** the agent.

When reproducing a bug, note:
- Java agents in the startup command.
- Build-time weaving/annotation processing.
- Proxy generators / Byte Buddy / CGLIB / aspect configurations.
- Runtime differences in instrumentation versions.

Do not disable the agent and declare the bug fixed if the cause could lie in instrumentation or timing differences.

## 12. Multi-Release JARs: Same Class Name, Multiple Bytecode Versions

A **multi-release JAR** can contain a class at the root path alongside version-specific implementations:

~~~text
META-INF/MANIFEST.MF
com/example/Codec.class
META-INF/versions/9/com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
~~~

This is an illustrative layout; the JAR must be properly configured as multi-release—not every JAR with a `META-INF/versions` directory is treated as a multi-release JAR.

When running on a compatible runtime, the JVM can select the versioned class matching the runtime version. That means:
- The base version's source may differ from the versioned implementation.
- `javap` without the right version option may read a different class version than runtime.
- The same JAR running on Java 11 vs. Java 17 can execute different bytecode.

You can inspect entries:

~~~bash
jar tf path/to/library.jar
~~~

With a JDK supporting the multi-release option, you can use a tool like:

~~~bash
javap --multi-release 17 -classpath path/to/library.jar -c -l -p com.example.Codec
~~~

This command is for **reference**; verify the actual JAR and Java/toolchain version in use. The goal is to inspect the Java 17 class version rather than defaulting to the base entry.

### 12.1. Do Not Confuse the Java Target with a Java-Specific Entry

A class in `META-INF/versions/17` does not mean the current source is compiled with `--release 17` across every module. It means an alternate implementation exists in the JAR for compatible runtimes. Check the `Multi-Release: true` manifest attribute and actual load path. If the stack trace matches the versioned class while the IDE opens the base implementation source, line numbers and logic can differ significantly.

## 13. Generated Sources, Annotation Processors, and Code Generation

Frameworks and build tools can generate:
- Java sources in `target/generated-sources`, `build/generated`, or an equivalent generated directory;
- class bytecode directly without a corresponding `.java` file;
- implementations for interfaces, mappers, serializers, proxies;
- lambda/synthetic/bridge methods.

If a frame points to `com.example.generated.MapperImpl.map(MapperImpl.java:...)`:
1. Check whether that class is a generated class.
2. Locate the generated source **produced in the actual production build**.
3. Verify the processor/plugin version and configuration.
4. Open the generated file if available, not just the source `Mapper` interface.
5. Check what inputs the caller passes into the generated code.
6. If the generated file is regenerated from newer source, line numbers may drift; do not use it to infer production line numbers.

For directly generated bytecode, there may be no source to open. In that case, `javap -c -l -v`, bytecode inspection, and generator configuration are the primary tools.

### 13.1. Lambdas and Bridge Methods

A trace may contain `lambda$process$0` or a compiler-generated bridge method. When searching in the IDE, look for the **enclosing method of the lambda** and the source line recorded in `LineNumberTable`; do not try to find a file named `lambda$process$0.java`.

Generics can produce bridge methods to preserve polymorphism after type erasure. A method may exist in bytecode without being explicitly written in source. Use `javap -v -p` to identify flags like `ACC_BRIDGE`/`ACC_SYNTHETIC` and inspect the target method it invokes when needed.

## 14. JDK/JRE Version and Stack Trace Formatting

The JDK version affects:
- Methods/frames inside the standard library.
- Handling of class file versions.
- Module/class loading mechanisms.
- Helpful `NullPointerException` messages where supported.
- JIT optimizations and stack capture behavior in certain special cases.

Do not hardcode line numbers from JDK internals like `java.util.Objects.java:123` as universal truth across versions. The same JDK method can sit on different lines across releases/updates.

### 14.1. JIT Optimizations Are No Excuse to Ignore Basics

The JIT may inline or optimize many calls, but that does not mean every mismatched line number is caused by the JIT. The JVM strives to preserve exception/stack trace semantics in a diagnosable way, while specific optimizations and edge cases can make traces differ from expectations. For instance, some JVMs optimize repeatedly thrown exceptions by omitting stack traces under specific conditions.

If a trace repeated under heavy load is missing frames, consider:
- Does the bytecode have a line number table?
- Does the `Throwable` have stack trace recording enabled?
- Is the logger truncating exceptions?
- Is a JVM flag/optimization altering stack info?
- Was an exception instance created once and rethrown many times?

**Only reason about the JIT after ruling out common causes** such as the wrong artifact, wrong source revision, or missing debug info.

## 15. The Root Cause Lies in `Caused by`, Not Necessarily the Outer Trace

Example:

~~~text
java.util.concurrent.CompletionException: task failed
    at java.base/java.util.concurrent.CompletableFuture...
    at com.example.app.ApiHandler.handle(ApiHandler.java:61)
Caused by: java.lang.NoSuchMethodError: ...
    at com.example.app.Adapter.callLibrary(Adapter.java:42)
    ...
~~~

This is an **illustrative trace with ellipsis**, not a real stack. The outermost exception comes from how the future/callback propagates errors; the cause is `NoSuchMethodError`, suggesting a runtime dependency ABI mismatch.

Proper investigation:
1. Inspect both the outer exception and the cause, not just frames mentioning `CompletableFuture`.
2. At `Adapter.callLibrary:42`, identify the method call the bytecode is executing.
3. Run `javap -c -v` on the **deployed `Adapter` class** to see the target method descriptor.
4. Run `javap -p -s` on the **library class loaded by runtime** to check whether that method exists.
5. Compare dependency versions and the runtime class loader.
6. Confirm artifact/build IDs and fix packaging/dependency resolution instead of merely changing `catch`.

If the cause is an `IOException` or a regular business exception, the workflow differs: inspect input/state rather than blindly assuming an ABI mismatch for every failure.

### 15.1. `... N more` and Suppressed Traces

`Throwable.printStackTrace()` can elide frames shared between an outer exception and its cause as `... N more`. It does not mean the class file is missing N lines. `Suppressed` usually represents cleanup errors in `try-with-resources`; that section has its own stack. A logger may also truncate traces due to configuration; distinguish **Java's duplicate-frame compression** from **log truncation**.

If logs truncated the cause or suppressed exceptions, add safe telemetry and capture again on a suitable reproduction. Never invent a cause from a single isolated trace line.

## 16. Tracing Binary Compatibility via Bytecode, Not Just Source API

Suppose `Service` in the app was compiled against library version B. In source B, there is:

~~~java
public String find(String key, int limit) { ... }
~~~

This is an **illustrative signature**, not a standalone Java class. However, runtime loads version A, which only has `find(String)`. Even though the called method in app source is named `find`, the JVM must resolve it according to the descriptor recorded in the constant pool and bytecode.

### 16.1. What Should Be Compared?

- FQCN of the referenced class/interface.
- Method/field name.
- Parameters and return type in the JVM descriptor.
- `static` vs. instance; class vs. interface.
- Access modifiers and module accessibility.
- Bridges/erasure if generics are involved.
- Actual API version and binary-incompatible changes.

Reference commands:

~~~bash
javap -classpath path/to/app.jar -c -v com.example.app.Service
javap -classpath path/to/lib.jar -p -s com.example.lib.Client
~~~

The output is long; look only for the exact method ref and implementation resolved by the JVM. The key is reading the **actual class file in the artifact**, not just `Client.java` from a dependency sources JAR that might not match.

### 16.2. Why Does a "Clean Rebuild" Sometimes Help but Remain Insufficient?

A clean build deletes stale class outputs and helps catch source/bytecode mismatches in the workspace. However, if the deployment pipeline still points to an old artifact, or the container image still holds an old JAR, a local clean build does not change runtime. Only declare the issue resolved when:
- The new artifact has a clear identity.
- The deployed runtime actually loads it.
- The mismatch is gone from classloading evidence.
- Tests/reproduction run against a production-equivalent artifact.

## 17. Fat JARs, Executable JARs, Containers, and Application Servers

In modern deployments, "the class is inside `app.jar`" is rarely simple:
- A Spring Boot executable JAR can place application classes under `BOOT-INF/classes` and dependencies under `BOOT-INF/lib`, usually loaded by a custom launcher.
- A WAR is unpacked or loaded by an application server's application classloader, while the server may also provide shared libraries.
- A container image may contain multiple JAR versions, with startup scripts selecting a specific one.
- A plugin architecture has multiple classloaders with different precedence rules.
- A release may run multiple replicas at different versions during a rolling update.

When a trace does not match, identify the **specific instance that emitted the log** by pod/container/process/build ID. A single service URL does not guarantee every request hits the same version during a rollout.

### 17.1. What Is Needed Beyond `jar tf`?

`jar tf app.jar` can show the layout, but it is not enough if:
- The JAR contains nested JARs under special directories.
- Bytecode is transformed at class load time.
- The launcher selects dependencies by layer/classloader.
- External config or plugins supply additional classes.
- Runtime loads classes from a directory outside the JAR.

In those cases, combine the build manifest, classloading diagnostics, `CodeSource`/classloader, and the startup command of the **actual process**. Copying a single JAR to another machine and running it with a different launcher command may yield results that do not represent the deployment.

## 18. Practical Investigation Workflow by Priority

### Phase A — Preserve Evidence

Record:
- Full exception class, message, stack trace, cause, suppressed.
- Timestamp, instance/pod, request/operation ID, and thread.
- Application/service version, build ID, image digest.
- JDK/runtime version of the actual process.
- Action performed, inputs **with sensitive data masked**, transaction/job state.

Do not edit the original log; you may annotate application frames in a copy for analysis.

### Phase B — Verify the Origin of the Class

1. Find the application frame closest to the error in the **relevant cause**.
2. Identify the FQCN, module, and classloader.
3. Extract the actual class file from the artifact and verify its JAR/source origin.
4. Compare the checksum/artifact ID against CI release records.
5. Check for duplicate classes or dependency conflicts.

If at this step the loaded class does not belong to the expected release, this is an **artifact/deployment problem** to fix first, not a question of "what is written on line 87."

### Phase C — Cross-Reference Bytecode and Source

1. Run `javap -c -l -p` on the exact class file to obtain `LineNumberTable`.
2. Use `javap -v` when you need the constant pool, major version, or flags.
3. For linkage errors, run `javap -p -s` and analyze descriptors.
4. Open the source at the right commit/release and any relevant generated sources.
5. Read the caller/inputs and determine whether the line is a throw site or a call site.
6. Account for shading, instrumentation, multi-release JARs, and obfuscation mappings.

### Phase D — Verify the Root Cause Experimentally

1. Reproduce on a production-like artifact.
2. Compare behavior against the suspected artifact/version.
3. If swapping a dependency, use a test targeting the exact missing method/ABI.
4. For source/line metadata issues, compile with `-g:lines,source` when needed and confirm the trace.
5. For concurrency/async bugs, use coordinated tests rather than arbitrary sleeps.
6. Check side effects/state after the exception; matching bytecode **does not** mean data was rolled back.

### Phase E — Conclude and Prevent

Report clearly:
- Which class/JAR/commit actually ran.
- Why the source in the IDE did not match.
- Evidence: artifact hash, classloading source, `LineNumberTable`, dependency resolution, or reproducer.
- Root cause and fix.
- Prevention: build provenance, dependency locking, clean/reproducible builds, artifact pinning, canary checks, or compatibility tests.

Avoid writing only "fix line 87" if production was actually running the wrong JAR.

## 19. Symptom -> Inspection Guide Table

| Phenomenon | What to Check First | Tools / Evidence |
| --- | --- | --- |
| Trace points to a line larger than the current source file | Wrong source revision, different generated source | Build ID, Git commit, packaged source |
| Line exists, but the statement is unrelated | Stale class/JAR, shifted source layout, instrumentation | `javap -c -l`, artifact hash |
| `Unknown Source` or `null:-1` | Missing debug info, generated/obfuscated class | `javap -v`, compile options |
| Source in IDE has the method, but runtime throws `NoSuchMethodError` | Wrong library version/descriptor | Runtime class origin, `javap -p -s` |
| `NoClassDefFoundError` only in production | Missing runtime dependency or class init failure | Cause, dependency tree, class loader |
| `ClassCastException` with the same class name on both sides | Two class loaders or duplicate APIs | Class identity, loader/module evidence |
| Trace contains `lambda$...` | Synthetic method generated from a lambda | Enclosing source method, line table |
| Trace contains relocated class names | Shading/obfuscation | Relocation config, mapping, dependency version |
| Different class behavior on JDK 11 vs. 17 | Multi-release JAR/JDK/library selection | Manifest, versioned entries, `javap --multi-release` |
| Logs from replica A match, replica B does not | Mixed deployments | Pod/image digest/build ID |
| Trace only shows a Future wrapper | Root error is in the task's cause | `getCause()`, trace of each throwable |
| Full cause is missing | Log truncation / cause lost when wrapping | Logger config, preserve throwable |
| Rebuilt, yet old trace still appears | Deployed/running old artifact, cache/launcher | Process command, artifact hash, class load log |

This table is a **guide**, not a deterministic conclusion. One symptom can have multiple causes; verifying with the actual class/runtime is the decisive step.

## 20. Anti-Patterns That Commonly Mislead Investigations

### 20.1. "The trace says line 55, let's edit line 55 in the open source file"

Wrong if the source is not from the same build version. Verify the artifact, `LineNumberTable`, and commit.

### 20.2. "The IDE compiles, so production has that method"

A successful compile only proves the compiler saw the method on the compile classpath. The production JVM may load a different binary. For `NoSuchMethodError`, check the runtime descriptor.

### 20.3. "The dependency tree shows the new version, so runtime must be using it"

An app server may supply a shared JAR, or there may be a shaded dependency, plugin loader, or fat JAR carrying another version. Combine with runtime classloading evidence.

### 20.4. "`javap` didn't print the table with `-l`, so the class has no line numbers"

Depending on the option combination, the command may emit a warning; run `javap -c -l` or `-v` on the right class before concluding.

### 20.5. "`FileName.java` means the file lives at that path in the project"

The file name does not include a path; FQCN/module/classloader is what identifies it accurately.

### 20.6. "The top frame always points to the bug to fix"

The top frame may be a library detecting bad input; the nearby application frame may be the call site. The outermost exception can also wrap a deeper cause.

### 20.7. "`javap` on `library.jar` proves the JVM loaded that exact JAR"

No: `javap` only reads the path you specify. Runtime may use a different JAR with a duplicate FQCN. Verify `CodeSource`/load logs or the process's actual artifact.

### 20.8. "Just catch the exception to solve the mismatch"

Catching `LinkageError` does not change the binary ABI. Broad catching can mask deployment issues and leave the system in an unsafe state. Fix the classpath/dependency and test compatibility.

### 20.9. "A clean build means it is deployed"

No. Build output, container image, rollout, and process runtime are separate steps. Verify evidence for each step.

### 20.10. "No source is visible, so it must be a JDK bug"

Generated code, missing line tables, obfuscation, fat JARs, or the wrong source version are far more likely. Investigate from evidence, not guesses.

## 21. Automated Testing for Binary-to-Source Consistency

A pipeline can add the following checks:

1. **Unit tests and integration tests** on the exact target JDK; do not stop at compiling.
2. **Explicit dependency locking or BOM** to reduce version drift.
3. **Duplicate class detection** when building/deploying packages with multiple JARs.
4. **Smoke tests on the packaged artifact**, executed with the same launcher/entrypoint as production.
5. **Build metadata** embedded in or published alongside the artifact to trace commit/image digest.
6. **Binary compatibility checks** when a library's public API changes, especially in shared modules.
7. **Line number metadata policy** for modules needing diagnostics: do not accidentally strip `SourceFile`/`LineNumberTable`.
8. **Reproducibility checks** or checksums for release artifacts.
9. **Class origin diagnostics** enabled temporarily and under control when needed.
10. **Canary and rollout verification** to avoid unnoticed replicas running different versions.

Example test for an error from `BytecodeTraceDemo`:

~~~java
IllegalArgumentException error =
        org.junit.jupiter.api.Assertions.assertThrows(
                IllegalArgumentException.class,
                () -> BytecodeTraceDemo.verify(-3));

StackTraceElement top = error.getStackTrace()[0];
org.junit.jupiter.api.Assertions.assertEquals(
        "BytecodeTraceDemo", top.getClassName());
org.junit.jupiter.api.Assertions.assertEquals(
        "verify", top.getMethodName());
~~~

This is a **non-standalone JUnit 5 fragment**: it requires the JUnit 5 dependency and the `BytecodeTraceDemo` class from the runnable example. Business-behavior tests should not hardcode line number `4`, because adding a comment at the top of the file will break the test even though the logic is intact. When intentionally verifying **debug metadata in a release artifact**, you can check `line > 0`/presence of `LineNumberTable` in a dedicated CI stage; confirm that this is a genuine technical requirement.

### 21.1. Testing Binary Version Mismatches

Create two variants of an API in two different JARs and run an app compiled against v2 on a runtime classpath containing only v1. If v1 lacks the called method, the test can reproduce `NoSuchMethodError`. Such an experiment should run in an isolated process/loader and **must never alter shared workstation or repository libraries** just to prove a point. Conclusions must be based on descriptors and the actual JAR loaded.

## 22. Production Diagnostic Checklist

- [ ] Captured the **full** exception, cause, suppressed, thread, and relevant context.
- [ ] Identified the **instance/process** emitting the log, not just the service name.
- [ ] Retrieved deployment version, build ID, commit, and artifact/image digest.
- [ ] Found the right application frame in the **trace of the relevant cause**.
- [ ] Identified FQCN/package/module/classloader.
- [ ] Inspected the actual class/JAR loaded at runtime, not just IDE dependencies.
- [ ] Checked for duplicate classes, classpath/module-path issues, or special container loaders.
- [ ] Compared `LineNumberTable` using `javap -c -l -p` or appropriate metadata.
- [ ] Cross-referenced source at the right commit and generated sources if needed.
- [ ] For linkage errors, checked runtime method/field descriptors via `javap -p -s`.
- [ ] Checked shading, obfuscation mappings, multi-release JARs, and instrumentation.
- [ ] Distinguished missing debug info from source/JAR mismatches.
- [ ] Checked the runtime JDK version when analyzing class file versions and JDK libraries.
- [ ] Reproduced using a production-equivalent artifact before declaring the fix complete.
- [ ] Added tests and safeguards against version drift/misdeployment.
- [ ] Protected sensitive data in logs, artifact metadata, and diagnostic steps.

### Hands-On Exercise

You receive a trace from a Java API:

~~~text
java.util.concurrent.CompletionException: java.lang.NoSuchMethodError: '...'
    at ...CompletableFuture...
Caused by: java.lang.NoSuchMethodError: ...
    at com.example.order.OrderGateway.send(OrderGateway.java:96)
    ... 3 more
~~~

The source in your IDE shows that `OrderGateway.java:96` is just a log statement, and Maven/Gradle shows the new version of the client library.

Proceed in order:

1. Identify the deployment that emitted the log and the hash of the running artifact.
2. Locate the `OrderGateway` class from the actual JAR/classloader instead of relying on the IDE copy.
3. Run `javap -c -l -p` to cross-reference line 96 of **that class file** with the source at the matching commit.
4. Run `javap -c -v` on the caller to find the method reference causing `NoSuchMethodError`, then run `javap -p -s` on the runtime-loaded dependency version to compare descriptors.
5. Check dependency conflicts, shared libraries, shaded/nested JARs, module path, and actual classpath.
6. If the system has multiple replicas, compare versions/artifacts across all instances; do not conclude from a single host.
7. Write an integration test running from the packaged artifact to ensure the method ABI is valid and stack trace/`LineNumberTable` metadata is intact.
8. Document the root cause with evidence: exactly which JAR/class drifted, why the new source did not match, and the pipeline/deployment fix.

**Key takeaway:** When a stack trace does not match source code, the first question is not "which line is wrong?" but **"which exact bytecode is the JVM executing, where was it loaded from, and which source was it built from?"** Only when all three layers—source, artifact, and runtime—align do line numbers in a trace become reliable evidence for fixing a bug.