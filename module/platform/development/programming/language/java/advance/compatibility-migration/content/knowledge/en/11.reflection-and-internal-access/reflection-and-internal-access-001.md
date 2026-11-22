# Distinguishing Supported APIs from sun.*, com.sun.*, and jdk.internal.* Packages

When upgrading Java, calls to JDK APIs generally need to be examined from two angles: **whether the class or method exists in the current JDK**, and **whether the application is permitted to depend on that API long-term**. These two questions are not equivalent. A class that exists at runtime, can be imported, and can even be invoked when a JVM flag is added may still belong to an internal API with no compatibility guarantee.

In long-lived projects, source code or third-party libraries may use packages starting with `sun.*`, `com.sun.*`, or `jdk.internal.*`. These are signals worth investigating, yet **you should not conclude that every `com.sun.*` package is an internal API**. Certain JDK APIs named `com.sun.*` are published and supported within the scope of the JDK, such as the HTTP server API or the compiler syntax tree API. Conversely, many `sun.*` and `jdk.internal.*` packages are not intended for ordinary applications and may change or be restricted when upgrading Java.

This lesson explains how to identify supported APIs, important exceptions, the impact of the Java Platform Module System (JPMS), how to detect internal dependencies with tools, and approaches for migrating code with lower risk.

## 1. "Present in the JDK" Does Not Mean "Supported"

The JDK includes more components than the Java SE API set developers commonly use. Beyond familiar packages like `java.lang`, `java.util`, `java.nio`, or `java.net`, a JDK distribution also includes compilers, debuggers, monitoring tools, implementation classes, native integration, and JDK-specific utilities.

Four tiers can be distinguished as follows:

| Tier | Example | Commitment Level |
|---|---|---|
| Standardized Java SE APIs | `java.util.List`, `java.nio.file.Files`, `java.lang.invoke.MethodHandles` | Backed by an API contract via the Java SE specification and corresponding documentation |
| Documented JDK-specific APIs outside Java SE | `com.sun.source.tree`, `com.sun.net.httpserver`, some `com.sun.management` | Have an API contract within the JDK scope, though portability across JDKs and environments must be considered |
| Implementation or internal APIs | Many `sun.*`, `com.sun.*.internal.*`, `jdk.internal.*` | Should not be treated as a stable public contract for applications |
| Temporary access mechanisms | `--add-exports`, `--add-opens`, or APIs in `jdk.unsupported` | Can help legacy code run, but do not create a stability commitment for internal APIs |

Do not apply a simplistic rule such as “starting with `com.sun` is wrong” or “if it compiles/imports, it is safe.” Conclusions must be based on **the official documentation of the target JDK version, the module owning the package, export/open policy, and the API contract**.

The concept of “supported” also needs to be placed in a specific scope:

- **Java SE portable API:** usually suitable for applications intending to run across multiple Java SE-compliant JDKs.
- **Documented JDK-specific API:** may be appropriate for tools or applications intentionally tied to the JDK, though not necessarily portable to every Java environment.
- **Implementation detail:** may exist, yet offers no guarantees for application code, even if the compiler currently allows access.

## 2. Three Easily Confused Package Families

### 2.1. sun.*

Many `sun.*` classes originate from the JDK or HotSpot implementation. For example, legacy code often references `sun.misc.Unsafe`, `sun.security.x509`, or utilities never published as Java SE APIs.

Characteristics to keep in mind:

- A package may exist in one JDK yet be absent in another JDK or vendor distribution.
- Signatures and behavior may change without following public API compatibility rules.
- JPMS may not export or open the package to applications.
- Certain **critical internal APIs** remain accessible via the `jdk.unsupported` module to aid migration; that does not make them stable Java SE APIs.

For instance, `sun.misc.Unsafe` can be found in `jdk.unsupported` on many modern JDKs. Nevertheless, it remains a high-risk API and should not be chosen as the default approach in new projects.

### 2.2. com.sun.*

`com.sun.*` requires the most careful classification. Both **documented JDK APIs** and **implementation internals** share this prefix.

Examples:

| Package/API | Context | How to Evaluate |
|---|---|---|
| `com.sun.net.httpserver.HttpServer` | HTTP server API in the `jdk.httpserver` module | Documented JDK API, not part of the universal Java SE APIs |
| `com.sun.source.tree.Tree` | Compiler Tree API in the `jdk.compiler` module | Documented JDK API intended for code analysis tools |
| `com.sun.source.util.JavacTask` | API supporting analysis with the compiler | Public API documented within the JDK scope |
| `com.sun.management.OperatingSystemMXBean` | Management API extension in `jdk.management` | Documented JDK-specific management API |
| `com.sun.tools.javac.tree.JCTree` | Internal AST structure of javac | Should not be treated as a stable contract like `com.sun.source.tree` |
| `com.sun.org.apache.xerces.internal.*` | Internal XML implementation classes bundled in the JDK | Do not depend on directly as an application API |

From the table, it is clear: **the `com.sun` prefix does not determine whether an API is supported**. You must identify the specific package and consult the API documentation for the release in use.

In particular, `com.sun.source.*` and `com.sun.tools.javac.*` are not synonymous. One provides documented compiler APIs; the other contains internal structures that tools such as annotation processors or AST transformers may rely on and easily break across JDK upgrades.

### 2.3. jdk.internal.*

The `jdk.internal.*` packages clearly signify internal JDK implementation purposes. Components inside them should not be imported by ordinary applications or accessed via reflection.

For example, class names starting with `jdk.internal.misc` indicate access to JDK internals. Even if found in the runtime image, applications should not rely on the existence or layout of these classes.

Issues that can occur:

- The compiler reports the package is not visible because the module does not export it.
- Runtime throws `IllegalAccessError` or other linkage errors.
- Reflection throws `InaccessibleObjectException` because the package is not open.
- Internal classes or fields change across JDK versions.

Do not “fix” this by switching from `sun.misc.*` to `jdk.internal.*` simply because they serve the same role inside the JDK. That merely swaps one internal dependency for another, rather than migrating to a supported API.

## 3. How to Identify Supported APIs

Instead of judging by package name alone, verify five pieces of information.

### 3.1. Does the API Have Official Documentation and a Public Contract?

Look up the API documentation for the target JDK. A documented API specifying behavior, usage scope, exception conditions, and official module/package is a far more reliable choice than an implementation class found through a decompiler.

If the API belongs to Java SE, you also have standardization backing it. If it is JDK-specific, clearly document the JDK dependency requirement and supported deployment environments.

### 3.2. Which Module Owns the Package?

For example:

- `java.util` belongs to `java.base`.
- `com.sun.net.httpserver` belongs to `jdk.httpserver`.
- `com.sun.source.tree` belongs to `jdk.compiler`.
- `com.sun.management` has APIs in `jdk.management`.
- `sun.misc.Unsafe` resides in `jdk.unsupported` on JDKs that include this module.

Knowing the module helps verify whether it is included in the runtime image, whether it resolves, and whether the package is appropriately exported/opened.

### 3.3. Is the Package Exported to the Caller?

A named module can export a package to all modules or only to a specified set of modules. An unexported package is not an API that an application can access directly from outside under JPMS rules.

However, **being exported does not automatically turn every class into a Java SE contract**. A package exposed in the `jdk.unsupported` module is a good example to consider: access permission and API stability are two separate matters.

### 3.4. Is the API Implementation- or Vendor-Dependent?

If using a JDK-specific API, verify which JDK vendors and runtimes provide and support it. A custom runtime image might omit optional JDK modules such as `jdk.httpserver`, even if the application builds on a full JDK.

### 3.5. Is There a Public API Alternative?

When discovering an internal API, ask what technical purpose it serves: Base64, reflection, memory access, certificates, XML parsing, class loading, management, or compiler ASTs. There is usually a documented Java SE/JDK API or a maintained library alternative.

## 4. Differences Between Module Readability, exports, and opens

Since Java 9, JPMS introduces module boundaries. Three concepts are frequently confused:

- **Readability:** module A can read module B in the module graph.
- **Exports:** a package in module B can be accessed by module A at the public API level, provided other Java access rules also allow it.
- **Opens:** a package permits deep reflection from other modules within the declared scope.

Application module example:

~~~java
module com.example.orders {
    requires java.sql;

    exports com.example.orders.api;
    opens com.example.orders.model;
}
~~~

Here `requires java.sql` concerns readability, `exports` exposes the public API in the `api` package, and `opens` permits reflective access to the `model` package.

For applications running on the classpath, classes normally belong to the unnamed module. They do not require `module-info.java` to run, yet they must still abide by whether internal packages of **JDK named modules** are exported/opened to the caller.

Comparison table:

| Scenario | `exports` | `opens` |
|---|---|---|
| Compiling code accessing a public type via import | Needs the package appropriately exported | Does not substitute for regular export |
| Normal code accessing a public method | Needs access per Java/JPMS rules | Not the primary mechanism |
| Reflection calling a public member of a public type in an exported package | May suffice if other Java conditions hold | Not necessarily required |
| `setAccessible(true)` on a private field of a package in a named module | Export alone is usually insufficient | Needs the package appropriately opened or an allowed mechanism |

This explains why swapping `--add-exports` for `--add-opens` or vice versa without understanding the error usually does not work.

## 5. Example: Same Application, Different Reflection Behavior

Illustrative example:

~~~java
import java.lang.reflect.Field;

public class ReflectionExample {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
~~~

On modern JDKs with strong encapsulation, `setAccessible(true)` here can fail with a message similar to:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

This is neither a missing-class error nor a source syntax error. The issue is that the application attempts to access a private member inside `java.base` from outside the module.

The right fix is not to open `java.lang` by default. Examine **why the application needs to read private data of `String`**. If the goal is merely string manipulation, use public methods on `String`. For legacy serializer libraries requiring deep reflection, prioritize upgrading to a JDK-compatible version first.

A JVM-level workaround:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp "app.jar:lib/*" com.example.Main
~~~

The flag can allow deep reflection under specific conditions, while also widening access to the package. It provides no guarantee that the private layout of `String` will remain unchanged in the future.

## 6. --add-exports and --add-opens Do Not Make Internal APIs Stable

During a transition period, JVM options can help a legacy dependency keep running.

### 6.1. --add-exports

Example of a legacy library using a public type in an unexported package:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
     -cp "app.jar:lib/*" com.example.Main
~~~

This option grants access to public types of the specified package for unnamed modules. It does not automatically allow accessing private members via deep reflection.

If source code directly imports an internal package, the compile step may also require a corresponding export configuration. A compile configuration can differ from the runtime configuration; a successful compilation alone does not prove that classes will load validly on the production JVM.

### 6.2. --add-opens

Example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp "app.jar:lib/*" com.example.Main
~~~

This option enables deep reflection within the specified scope. It does not replace a removed public API or guarantee that private field/method structures still exist.

### 6.3. What Does ALL-UNNAMED Mean?

`ALL-UNNAMED` targets unnamed modules, which typically include code loaded from the classpath. This is useful in legacy applications without `module-info.java`. However, it also means access is granted to **all** unnamed modules under that mechanism, not just one specific JAR.

If the system is already modularized, you can specify an explicit target module name instead of `ALL-UNNAMED` to narrow the scope when the architecture and tooling support it.

### 6.4. Limitations and Risks

- Flags change access-permission configuration, not the API itself.
- Internal packages can change, so old flags do not guarantee the library continues to work.
- Flags must be kept consistent across local development, CI, integration tests, and production.
- A workaround must not remain hidden indefinitely in an IDE setting or personal launch script.
- The long-term goal remains updating the library or removing the dependency on internals.
- With javac, using `--release` imposes restrictions alongside `--add-exports` on system modules; do not rely on “forcing an old release while opening JDK internals” to produce portable artifacts.

## 7. Java 8, Java 9, Java 16, and Java 17: Why Do Migrations Fail?

When upgrading the JDK, especially from JDK 8 to newer releases, internal API access behavior undergoes significant changes:

| Stage | Impact on Legacy Applications |
|---|---|
| JDK 8 | No JPMS yet; many libraries accessed internals without being blocked by module boundaries |
| JDK 9 | JPMS introduced, distinguishing modules/exports/opens; transitional relaxation mechanisms existed for some reflective access |
| JDK 11 | Several Java EE/CORBA modules previously provided by JDK 8 were removed; appropriate dependencies must be added |
| JDK 16 | Strong encapsulation became the default more broadly, exposing more deep reflection errors |
| JDK 17 | JEP 403 tightened strong encapsulation for many JDK internals; `--illegal-access` can no longer be relied upon to restore prior relaxation |

This does not mean every `sun.*` API vanished in JDK 17. Certain critical internals are still provided via `jdk.unsupported`. However, **accessibility** does not equate to a **supported compatibility contract**.

An application may run on JDK 11 with illegal reflective access warnings and then fail when moving to JDK 17. Eliminating warnings by silencing logs does not solve the underlying issue; the access path or dependency must be fixed.

## 8. Common Internal API Replacement Examples

Replacements must be chosen based on **actual functionality**, not similar class names. The following table outlines preferred directions:

| Legacy Dependency or Purpose | Replacement Direction | Notes |
|---|---|---|
| `sun.misc.BASE64Encoder` / internal decoders | `java.util.Base64` | Choose Basic, URL-safe, or MIME depending on the data format |
| `sun.misc.Unsafe` for concurrent field reads/writes | `VarHandle`, `Atomic*`, `java.util.concurrent` | Check memory ordering and atomicity |
| `sun.misc.Cleaner` or internal resource cleanup mechanisms | `java.lang.ref.Cleaner` and `AutoCloseable` | Prefer explicit resource closing; cleaner is only a backstop |
| `sun.security.x509.*` for certificate manipulation | `java.security`, `java.security.cert`, `javax.net.ssl`, and a maintained X.509 library | Java SE provides reading/verification APIs, though certificate issuance may require a dedicated library |
| `com.sun.org.apache.xerces.internal.*` | `javax.xml.parsers`, `org.w3c.dom`, `javax.xml.transform`, or public XML libraries | Avoid depending on the parser implementation bundled inside the JDK |
| `com.sun.tools.javac.tree.JCTree` for traversing source | `com.sun.source.tree` / `com.sun.source.util` and `javax.lang.model` | Tree APIs are designed for analysis; mutating internal ASTs may have no public equivalent |
| Internal direct-buffer or off-heap APIs | `ByteBuffer`, `VarHandle`, Foreign Function & Memory API, or suitable libraries | Choice depends on Java level, native memory needs, and region lifecycle |
| Internal thread/class-loading helpers | `Thread`, `ClassLoader`, `ServiceLoader`, `MethodHandles` | Not every internal primitive has a 1-to-1 replacement |

The table indicates **migration directions**, not that every replacement API is bit-for-bit semantically identical. For concurrent code, native memory, cryptography, and serialization, differences in ordering, lifecycle, or security can be critical.

## 9. Example: Migrating from sun.misc.BASE64Encoder to java.util.Base64

Legacy code may depend on an internal encoder to generate Base64. The modern solution is the Java SE API `java.util.Base64`.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class TokenEncoding {

    public static String encode(String input) {
        byte[] raw = input.getBytes(StandardCharsets.UTF_8);

        return Base64.getEncoder().encodeToString(raw);
    }

    public static String decode(String encoded) {
        byte[] raw = Base64.getDecoder().decode(encoded);

        return new String(raw, StandardCharsets.UTF_8);
    }
}
~~~

`Base64` has been available since Java 8. If the legacy format includes line breaks or uses URL-safe characters, choose:

- `Base64.getMimeEncoder()` or `getMimeDecoder()` when MIME-style line handling is required.
- `Base64.getUrlEncoder()` or `getUrlDecoder()` for the URL-safe alphabet.
- `Base64.getEncoder()` for the Basic format without line wrapping.

Do not swap out the encoder while ignoring legacy formats in databases, tokens, or external protocols. Write round-trip tests and test with real data from earlier versions, as whitespace or padding differences can prevent clients from reading payloads.

## 10. Example: Replacing Unsafe with VarHandle Where Appropriate

Some older libraries use `sun.misc.Unsafe` to perform compare-and-swap on fields. Java provides `VarHandle` since Java 9 alongside other concurrency primitives in `java.util.concurrent`.

Visit counter class example:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class VisitCounter {
    private volatile int count;

    private static final VarHandle COUNT;

    static {
        try {
            COUNT = MethodHandles.lookup()
                    .findVarHandle(
                        VisitCounter.class,
                        "count",
                        int.class
                    );
        } catch (ReflectiveOperationException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    public void increment() {
        COUNT.getAndAdd(this, 1);
    }

    public int value() {
        return (int) COUNT.getVolatile(this);
    }
}
~~~

The example illustrates an atomic operation on a field using a public API. In many applications, `AtomicInteger` or `LongAdder` is simpler:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class SimpleCounter {
    private final AtomicInteger count = new AtomicInteger();

    public void increment() {
        count.incrementAndGet();
    }

    public int value() {
        return count.get();
    }
}
~~~

Do not replace every `Unsafe` operation mechanically. `Unsafe` spans many distinct capabilities: native memory, array layouts, object field offsets, fences, constructor bypassing, and specialized primitives. A migration must carefully examine exact memory ordering, race conditions, lifecycle, and the supported Java baseline.

## 11. Cleaner, Native Resources, and Object Lifecycle

Legacy code sometimes relies on internal cleanup APIs to release resources when an object becomes unreachable. `java.lang.ref.Cleaner` (since Java 9) can be considered when fallback cleanup is needed, yet the primary principle is **explicit resource closing**.

Example favoring `AutoCloseable`:

~~~java
public final class ResourceClient implements AutoCloseable {
    private boolean closed;

    public void use() {
        if (closed) {
            throw new IllegalStateException("Client is closed");
        }
        // Operate on the resource
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            // Release actual resources here
        }
    }
}
~~~

Caller side:

~~~java
try (ResourceClient client = new ResourceClient()) {
    client.use();
}
~~~

Cleaner can help when someone forgets to close a resource, but it does not guarantee immediate or timely execution for business correctness. If resource cleanup is a safety requirement, design clear ownership and close semantics.

## 12. Compiler APIs: com.sun.source Differs from com.sun.tools.javac

Within Reflection and Internal APIs, tools that read Java source code are often a source of confusion because they share the `com.sun` prefix.

A source analysis tool can use documented APIs:

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreeScanner;
~~~

APIs in `jdk.compiler` provide access to the source tree model within the published contract. An appropriate compiler/JDK is required, and declaring `requires jdk.compiler;` may be necessary when writing a named module.

Meanwhile, types such as:

~~~java
import com.sun.tools.javac.tree.JCTree;
~~~

typically belong to the javac implementation. An annotation processor or plugin accessing them can fail when the compiler changes internal fields or AST representations, even if business source code has not changed.

Example risk:

~~~text
java.lang.NoSuchFieldError: ...
    at some.processor.compiler.InternalAdapter...
~~~

The error may be caused by an older processor version not supporting the new JDK. Do not attempt to fix it by unconditionally adding a package export; if an internal field has disappeared, an export flag cannot restore that field.

When source generation is needed, prefer the annotation processing APIs `javax.annotation.processing`, `javax.lang.model`, and `Filer`. When syntax analysis is needed, use `com.sun.source.*` within the supported API scope or a maintained parser library. When deep AST transformation is required, explicitly document the compiler version dependency and the corresponding tool upgrade plan.

## 13. Do Not Equate javax.* and jakarta.* with JDK Internals

During framework migrations, you may encounter `javax.*` or `jakarta.*` packages. These do not fall into the same classification as `sun.*` and `jdk.internal.*`.

- Some `javax.*` packages belong to Java SE APIs, such as `javax.net.ssl` or `javax.crypto`.
- Other `javax.*` packages belong to APIs formerly in Java EE or external libraries and may no longer be bundled in modern JDKs.
- `jakarta.*` belongs to the Jakarta EE ecosystem and its corresponding dependency artifacts.
- Moving from `javax.persistence` to `jakarta.persistence` is a version/framework change, not an indication that the former package was a JDK internal.

For example, an application using JAXB via `javax.xml.bind` on JDK 8 must add an appropriate dependency when upgrading to JDK 11+. `--add-opens` cannot recreate a removed API. At the same time, you cannot blindly convert every `javax` to `jakarta` without checking framework compatibility.

Accurate API classification prevents misdiagnosing dependency errors as module access errors.

## 14. Auditing Source Code and Dependencies with Static Search

The first step of a migration is searching for references to notable package families in source code and configuration:

~~~bash
rg -n "sun\\.|com\\.sun\\.|jdk\\.internal\\." src build.gradle settings.gradle pom.xml
~~~

`rg` is an example using ripgrep; paths and shell escaping must be adapted to the project. Search results are only a list of suspects, not a list of confirmed errors.

When auditing, categorize each match:

1. **Direct import:** application code directly imports `sun.*`, `com.sun.*`, or `jdk.internal.*`.
2. **Reflection string:** `Class.forName("...")` or class names in configuration files.
3. **Code generation:** templates and generated sources referencing internal types.
4. **Dependency bytecode:** external JARs containing static references to internal classes.
5. **Documentation/test data:** package names appearing only in comments, sample logs, or test data.

Do not delete or rewrite code simply because a regex matched a `com.sun` string: it could be a documented JDK API or not even a code reference.

### 14.1. The jdeps Tool

`jdeps` supports static dependency analysis of classes/JARs and is particularly useful for detecting internal JDK APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

With dependencies on the classpath, you can run:

~~~bash
jdeps --recursive --jdk-internals \
      --class-path "lib/*" \
      app.jar
~~~

When the artifact is a multi-release JAR, specify the appropriate release:

~~~bash
jdeps --multi-release 17 \
      --jdk-internals \
      library.jar
~~~

Depending on JAR structure and tool version, supply the full classpath or module path to resolve dependencies. For executable fat JARs containing nested JARs (such as framework packaging formats), consider how to extract/analyze the nested JARs; `jdeps` does not automatically emulate every custom launcher or class loader.

### 14.2. Limitations of jdeps

Static analysis does not capture all reflection or dynamic class loading. For example:

~~~java
String name = System.getProperty("internal.helper.class");
Class<?> helper = Class.forName(name);
~~~

A class name present only in runtime configuration may create no static bytecode reference. `jdeps` cannot infer every actual configuration value. Supplement it with runtime testing, log inspection, and configuration file reviews.

Nor does `jdeps` prove an API is “stable” simply because it reports no internal dependency. It analyzes specific dependency patterns and does not replace reading official API documentation.

## 15. An Inventory Process Suitable for Large Projects

Multi-module systems should build an inventory table instead of making scattered fixes by stack trace:

| Field | Meaning |
|---|---|
| Source | Module, class, dependency, or template containing the reference |
| Symbol | Specific package/class/method |
| API Type | Java SE, JDK documented, internal, undetermined |
| Evidence | Import, jdeps output, stack trace, reflection config |
| Purpose | Base64, bytecode, native memory, XML, compiler AST... |
| Current/Target JDK | For example, 8 -> 17 or 17 -> 21 |
| Risk | Compile failure, reflection error, semantic change |
| Resolution | Public API, upgrade library, workaround, remove |
| Owner | Responsible team/code owner |
| Status | Not analyzed, in progress, verified |

Separating **direct dependencies** from **transitive dependencies** is crucial. If an internal symbol resides inside a framework JAR, the application may not be able to edit the import; look for a framework/agent release compatible with the new JDK.

The inventory table should also note cases where `com.sun.*` belongs to a documented JDK API to avoid false positives and prevent forcing teams to replace APIs unnecessarily.

## 16. When a Stack Trace Reports an Access Error: How to Investigate?

An effective diagnostic workflow includes:

### Step 1: Identify the Root Exception

Read the deepest `Caused by` or the first failure when the JVM loads classes/initializes libraries. Distinguish:

- `InaccessibleObjectException`: deep reflection is restricted.
- `IllegalAccessError`: bytecode/linkage is not permitted to access a type/member.
- `NoSuchMethodError` or `NoSuchFieldError`: runtime version differs or an internal API changed.
- `ClassNotFoundException`: class cannot be found by the active class loader.
- `UnsupportedClassVersionError`: class-file version is incompatible.

### Step 2: Identify the Caller

Which class is accessing the JDK internal API? Application code, an annotation processor, a Java agent, or a third-party JAR? If it is a dependency, record the artifact/version and check the maintainer's release notes or compatibility matrix.

### Step 3: Identify the Restricted Module and Package

A message such as “module `java.base` does not open `java.lang` to unnamed module” identifies the target module, package, and caller. Do not guess package names and add arbitrary flags.

### Step 4: Prioritize Upgrading or Replacing the API

If a library version supporting the target JDK exists, prioritize upgrading the library. If it is in-house code, replace it with a public API. Consider overrides only when no immediate fix exists and the risk is acceptable.

### Step 5: Re-Verify the Artifact on the Target Runtime

Test startup, object creation flows, serialization, ORM, reflection, class loading, and error paths. An access error may appear only on rarely invoked paths or when specific data conditions are triggered.

## 17. Build and Runtime May Differ in How They See Internals

Three environments must be separated:

1. **JDK running the build tool** (Gradle/Maven daemon, plugins).
2. **JDK used to compile source** (javac/toolchain).
3. **JDK running the application or tests** (production/test JVM launcher).

An annotation processor may depend on `com.sun.tools.javac.*` and fail when run on a newer compiler, even if generated bytecode targets an older Java version. Conversely, application source may compile successfully while a runtime framework uses reflection on JDK internals and fails.

Example Gradle configuration to select JDK 17 and the target release:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`options.release` controls source syntax, class-file target, and the public API surface for the target release at the compiler level. However, it **does not prove that all dependencies and reflective code are compatible** and does not replace testing on the target JVM.

Module-opening options used for the build process, test process, and production launch may reside in different configuration locations. Do not confuse flags for the Gradle daemon with flags passed to the application in a container.

## 18. Distinguishing Unexported Package Errors from Removed Class Errors

The following two errors can appear at the same point in a migration but require different resolutions.

### 18.1. Package Exists but Is Not Exported

For example, when code imports an internal package:

~~~java
import jdk.internal.misc.Unsafe;
~~~

The compiler may report that the package is not visible because `java.base` does not export that package to the current module. The root cause is **access policy**. Preferred resolution: use a public API, rather than forcing the package open just to make the build pass.

### 18.2. Class/API Does Not Exist in the New JDK

For example, an API previously distributed in an older JDK has been removed. The compiler reports cannot find symbol, or runtime throws `ClassNotFoundException`. The issue here is a **missing class/dependency**, not a locked package.

If the component has left the JDK, the fix is to add a dependency or replace the library. `--add-exports` and `--add-opens` cannot bring back a removed class.

## 19. Checking Bytecode Libraries, Agents, and Generated Code

Not every dependency on JDK internals appears in handwritten source code. The following components must be audited separately:

- **Annotation processor:** may access javac internals or generate imports to unsuitable APIs.
- **Bytecode generator:** may require a specific class-file version, JDK API, or runtime behavior.
- **Java agent/profiler:** may instrument JDK classes and require module opens/exports or a compatible agent version.
- **ORM/serialization framework:** may perform deep reflection on JDK classes or private application members.
- **Build plugin:** may run on a different JDK than the application and rely on internal APIs when manipulating ASTs.
- **Shaded JAR:** may obscure package origins or bundle older class versions.

An application with no direct `sun.*` imports can still fail because of transitive dependencies. Therefore, a JDK upgrade plan must include reviewing versions of frameworks, agents, test runners, and build plugins—not only searching inside `src/main/java`.

When a dependency is updated, verify behavior as well. A new version may eliminate internal access while also changing semantics, data formats, or configuration.

## 20. Policy for Temporary Workarounds

If an internal dependency cannot be removed immediately, a controlled workaround may be needed. A tracking record should include:

~~~yaml
internalApiException:
  owner: platform-team
  component: legacy-serializer
  jdkTarget: "17"
  symptom: "InaccessibleObjectException during serialization"
  package: "java.base/java.lang"
  temporaryRuntimeFlag:
    - "--add-opens=java.base/java.lang=ALL-UNNAMED"
  justification: "No compatible dependency release currently deployed"
  mitigation: "Limit usage; integration-test on target JDK"
  removalPlan: "Upgrade serializer and remove runtime flag"
  status: "temporary"
~~~

The values in the example only illustrate the governance workflow, not a workaround to apply by default. Do not expose secrets or sensitive information in reports.

Avoid:

- Adding bulk `--add-opens` flags from a list copied off the internet without corresponding errors.
- Accepting “starts up” as the sole criterion; a rarely exercised reflection branch may still fail.
- Keeping flags on a local machine while forgetting CI, containers, or production.
- Allowing an unsupported dependency to remain indefinitely with no owner or replacement plan.
- Relying on internal APIs in new code simply because a workaround exists for an old library.

## 21. Example Migration Workflow for a Legacy Application

Suppose a Java 8 application uses:

- `sun.misc.BASE64Encoder` in an in-house utility class.
- A parser library with static references to `com.sun.org.apache.xerces.internal.*`.
- An older annotation processor accessing `com.sun.tools.javac.tree.JCTree`.
- An older serializer using deep reflection on private fields belonging to the JDK.

The goal is to move the runtime to JDK 17 without yet converting the application to named modules.

### Phase 1: Build an Inventory

Use source/config searches and `jdeps --jdk-internals` on the relevant artifacts/JARs. Identify the four distinct components; do not lump them together as a single “JPMS error.”

### Phase 2: Remove Easily Replaced Direct Dependencies

Migrate Base64 to `java.util.Base64`. Check existing data formats. For XML, use `javax.xml.parsers` or a public parser library to avoid internal Xerces classes.

### Phase 3: Upgrade Compiler-Related Toolchain

Find an annotation processor compatible with javac/JDK 17. If the tool actively mutates internal ASTs, upgrade the tool version or replace the mechanism. Do not expect `--add-exports` to fix differences in `JCTree` structure.

### Phase 4: Upgrade Frameworks and Serializers

Find a serializer version that does not require deep reflection on private JDK members. If upgrading is not yet possible, define temporary `--add-opens` only for packages with clear evidence, documenting the scope and removal plan.

### Phase 5: Run on JDK 17

Verify a clean build, startup, mapping, XML, serialization, and business workflows; compare results against the baseline. Run in an environment with the same JVM flags and dependencies as production.

Results should be reported per resolved API/dependency. Do not record merely “Build success,” since most internals risks lie at runtime or in tool dependencies.

## 22. Sample Audit Summary

You can create a table:

| Result | Evidence | Decision |
|---|---|---|
| `java.util.Base64` used instead of internal encoder | Source diff and data tests | Completed |
| JDK internals dependency in parser removed | `jdeps` and XML tests | Completed |
| Newer annotation processor runs on target JDK | Clean compilation and generated source | Completed or needs further testing |
| Serializer still requires temporary `--add-opens` | Stack trace, integration tests, launch configuration | Assigned owner and removal plan |
| `com.sun.net.httpserver` API is in use | `jdk.httpserver` module documentation and compatibility policy | Assessed as a documented JDK-specific API, not automatically classified as internal |
| A `jdk.internal.*` helper remains in code | Source inspection and build error | Incomplete, API replacement needed |

The row for `com.sun.net.httpserver` illustrates an important exception: a quality migration report must state **why an API is accepted or rejected**, rather than mechanically applying prefix rules.

## 23. Key Principles to Remember

- **The API contract matters more than the package name.** Java SE APIs, documented JDK APIs, and JDK internals have different support scopes.
- **`sun.*` and `jdk.internal.*` are high-risk signals**, yet you still need to identify the specific symbol, module, and usage purpose.
- **Do not conclude that all `com.sun.*` packages are internal.** `com.sun.source.*`, `com.sun.net.httpserver`, and certain `com.sun.management` APIs are examples of documented JDK APIs.
- **Export/open does not mean a stable API.** JPMS controls access; documentation and specifications define the scope of the API contract.
- **`jdk.unsupported` does not make Unsafe a safe default choice.** It exists to satisfy transitional and specialized compatibility needs.
- **Use public API replacements whenever possible.** `Base64`, `VarHandle`, `Atomic*`, `Cleaner`, `java.security.cert`, and documented compiler APIs are often suitable paths depending on the need.
- **`jdeps` is an auditing tool, not absolute proof.** Dynamic reflection, service loading, and native code require additional verification.
- **Prefer upgrading dependencies over opening modules in bulk.** Overrides must have a clear reason, scope, and removal plan.
- **The build tool, compiler, and runtime may use different JDKs.** Verify all three along with the final artifact.
- **Compatibility must be verified through behavior.** Successful compilation is not enough to prove that serializers, agents, XML parsers, or compiler plugins behave correctly on a new JDK.

When performing Java Advance Compatibility Migration, recognizing supported APIs is an important step to reduce reliance on JDK implementation details. The sustainable approach is to **identify the exact API contract, classify each symbol rather than looking only at prefixes, replace internals with public APIs where appropriate, and test all execution paths on the target JDK**. By doing so, the team not only eliminates immediate errors but also lowers risk for subsequent Java upgrades.
