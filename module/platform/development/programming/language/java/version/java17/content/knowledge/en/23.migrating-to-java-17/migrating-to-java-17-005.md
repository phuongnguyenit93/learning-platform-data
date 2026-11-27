# Detecting Internal APIs, Removed APIs, and Invalid JVM Options When Upgrading to Java 17

When upgrading an application to Java 17, you need to identify dependencies relying on JDK internal APIs, deprecated or removed APIs, and JVM options that are no longer supported. These dependencies can prevent source code from compiling, cause the application to fail at startup, or surface only when executing a rarely used feature branch.

Distinguish three situations:

- **Internal API:** an API belonging to the JDK implementation rather than a stable Java SE contract for applications. Examples include internal `sun.*` or `com.sun.*` packages.
- **Deprecated / for-removal API:** an API that still exists yet is marked as discouraged; some are also flagged for scheduled removal.
- **Removed API or JVM option:** a component no longer present in JDK 17. Source code or startup scripts relying on it must be replaced.

This lesson focuses on auditing projects and dependencies using JDK 17 tools, understanding JPMS strong encapsulation, selecting replacements, and validating JVM configuration after migration.

## 1. Why audit before upgrading?

An application running on an older JDK will not necessarily run on JDK 17. It may:

- Import an internal class that an older JDK permissively exposed.
- Use Reflection to access private members of an un-opened JDK package.
- Call APIs that have been deprecated or removed.
- Pass JVM options valid only in an earlier release.
- Depend on an old library that uses such APIs internally, even if the application source does not mention them.

These dependencies often hide inside third-party libraries, build plugins, agents, frameworks, Docker scripts, or environment configuration flags.

### 1.1. Three risk groups

| Group | Example | Possible symptoms |
|---|---|---|
| Internal API | Using classes in internal JDK packages | Compile errors, `IllegalAccessError`, linkage errors, or Reflection failures |
| Deprecated / for removal | Calling an API marked deprecated | Compiler warnings, runtime warnings; may need replacement before a future JDK |
| Removed API / JVM option | Using removed classes, modules, or flags | `cannot find symbol`, `ClassNotFoundException`, `Unrecognized VM option` |

Not every warning means the application will fail immediately on Java 17. Still, warnings signal risks to evaluate and plan replacements for.

### 1.2. Inspect source, dependencies, and startup configuration

An audit should cover:

1. Application source code.
2. Direct and transitive dependencies.
3. Plugins and annotation processors executed at build time.
4. Java agents, native libraries, and frameworks.
5. Dockerfiles, shell scripts, service definitions, and deployment JVM configuration.
6. Tests, integration tests, and production-only profiles.

Compiling the source code alone is not enough. A dependency may use Reflection or dynamic class loading so that failures appear only at runtime.

## 2. What are JDK internal APIs?

Java SE defines public APIs supported for applications. Alongside them, the JDK contains many classes and packages serving internal implementations of the compiler, runtime, networking, security, collections, and other subsystems.

Packages named `sun.*` or `com.sun.*` are common signals to inspect, though you should not draw conclusions from prefixes alone. Certain `com.sun.*` APIs are officially documented in the JDK; verify the owning module, API docs, and `jdeps` output.

Examples of dependencies application code should avoid:

~~~java
import sun.misc.Unsafe;
import sun.reflect.Reflection;
~~~

Internal APIs can change across JDK versions, be encapsulated in unexported modules, or become more strongly encapsulated over time. Applications receive no compatibility guarantees comparable to public Java SE APIs.

### 2.1. How do internal APIs differ from public APIs?

| Criterion | Java SE public API | JDK internal API |
|---|---|---|
| Contract | Specified in the Java SE/JDK API | Tied to JDK implementation details |
| Compatibility | Compatibility commitments under Java policy | Subject to change or closure at any time |
| Module access | Public packages exported per module descriptor | Many packages unexported to applications |
| Recommendation | Use in applications | Avoid depending on them; seek replacement APIs |

For example, using `java.nio.file.Files` to read a file uses a public API. Relying on an internal class to inspect HotSpot's file descriptor structure couples your code to implementation details.

### 2.2. Not every `sun` API shares the same status

One example to understand accurately is `sun.misc.Unsafe`. In HotSpot/OpenJDK 17, this class still resides in the `jdk.unsupported` module and is retained as a special internal API supporting certain foundational libraries. That does not make it a stable or recommended Java SE API for new application code.

If a library still uses `Unsafe`, check the library version and migration guidance provided by that library itself. Do not replace it with ad-hoc deep Reflection into JDK internals.

## 3. Strong encapsulation in Java 17

The Java Platform Module System (JPMS) establishes module and package boundaries. Modules can export packages to other modules; unexported packages are treated as implementation details for normal access.

JEP 403, implemented in JDK 17, completes strong encapsulation of JDK internal elements. A few special internal APIs retain compatibility exceptions, but applications should not treat those exceptions as long-term contracts.

Impact when upgrading:

- Source references to unexported JDK packages may be rejected by the compiler.
- Compiled bytecode accesses may fail with linkage access errors.
- Deep reflection into closed packages may fail when calling `setAccessible(true)` or `trySetAccessible()`.
- Legacy options that previously relaxed access in earlier JDKs may cease to have effect.

### 3.1. --illegal-access is no longer a workaround on JDK 17

In JDKs prior to 17, the `--illegal-access` option offered a compatibility mode permitting certain illegal reflective accesses to JDK packages. From JDK 17 onward, this option is obsolete and no longer opens packages under the old mechanism; the JVM emits a warning that the option is ignored.

Example legacy configuration:

~~~bash
java --illegal-access=permit -jar app.jar
~~~

Do not retain this option expecting it to restore legacy permissions on Java 17. Remove it from scripts once you confirm the application no longer relies on the old mode, and replace internal accesses with supported APIs.

If a temporary migration exception is required, use `--add-exports` or `--add-opens` naming the specific source package and target module, as shown next. These are explicitly granted permissions; they do not convert internal APIs into stable public APIs.

## 4. Distinguish --add-exports and --add-opens

Both options adjust module boundaries, but they address two distinct needs.

| Option | Purpose | Use case |
|---|---|---|
| `--add-exports` | Export a package to a target module | Code must reference public types/members in an unexported package |
| `--add-opens` | Open a package for runtime deep reflection | Frameworks need Reflection to access private fields/methods |
| `--add-reads` | Add a readability edge between modules | A module must read another module not declared in its module graph |

### 4.1. --add-exports syntax

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
~~~

General syntax:

~~~text
--add-exports source-module/package=target-module
~~~

In this example:

- `java.base` is the source module.
- `sun.nio.ch` is the package to export.
- `ALL-UNNAMED` targets all classes in the unnamed module, typically classpath applications.

`--add-exports` can be passed to `javac` when compiling code referencing public types in that package, and to `java` when running code requiring that access.

Export only the exact package and consuming module. Avoid wildcards or sweeping exports of internal packages.

### 4.2. --add-opens syntax

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

General syntax:

~~~text
--add-opens source-module/package=target-module
~~~

This option serves runtime Reflection. It allows the target module to perform deep reflection on the opened package under JPMS rules.

`--add-opens` does not replace `--add-exports` when compiling source code importing public types. Conversely, `--add-exports` does not grant deep reflection into private members.

### 4.3. ALL-UNNAMED is not the default choice for every case

`ALL-UNNAMED` grants permission to all code residing in unnamed modules. If the application has an explicit module name, specify that exact target module:

~~~bash
java --add-opens java.base/java.lang=com.example.application -m com.example.application/com.example.Main
~~~

The broader the target module scope, the wider the exposed surface. Prioritize updating dependencies to use supported APIs; where temporarily impossible, open only required packages and plan to remove the exception.

### 4.4. These options are controlled compatibility workarounds

Using `--add-exports` or `--add-opens` can keep an older dependency running during transition. However, they carry limitations:

- They apply only to the named packages and modules.
- They do not guarantee the internal API will survive in future JDKs.
- They cannot fix APIs that have already been removed.
- They do not resolve logic bugs in incompatible dependencies.
- They weaken encapsulation and increase maintenance risk.

Do not add an option merely because an exception mentions a module. First identify the source module, package, caller module, and the exact denied operation.

## 5. Detect internal APIs with jdeps

`jdeps` analyzes class file and JAR dependencies. On JDK 17, `--jdk-internals` detects dependencies on JDK internal APIs.

### 5.1. Scan a JAR

~~~bash
jdeps --jdk-internals app.jar
~~~

You can scan multiple artifacts or compiled class directories:

~~~bash
jdeps --jdk-internals build/libs/
~~~

For multi-release JARs, specify the target release version:

~~~bash
jdeps --jdk-internals --multi-release 17 app.jar
~~~

Output identifies:

- Which application classes depend on internal APIs.
- Which internal APIs are referenced.
- Which module owns each API.
- Migration suggestions if the JDK recognizes a replacement.

### 5.2. Analyze transitive dependencies

Even if your application never imports internal APIs directly, third-party dependencies still might. Scan JARs across the dependency graph, not just artifacts built by your team.

For example, after gathering resolved dependencies:

~~~bash
jdeps --jdk-internals library-a.jar
jdeps --jdk-internals library-b.jar
~~~

If output flags a third-party library:

1. Identify the version currently in use.
2. Read the library's release notes and migration guide.
3. Upgrade to a version supporting JDK 17 if available.
4. If no fix exists yet, evaluate replacing the library or isolating the module access exception.
5. Add tests running on JDK 17 covering the affected functional path.

### 5.3. Limitations of jdeps

`jdeps` analyzes dependencies inferable from bytecode. It cannot guarantee detection of all dynamic accesses:

- Class names concatenated from strings and loaded via `Class.forName`.
- Reflection using package or member names.
- Native code calling into the JVM via JNI.
- Dependencies loaded at runtime from plugins or external folders.
- Code generated or loaded after application startup.

Therefore, `jdeps` is one part of an audit, not absolute proof that an application has zero internal API dependencies.

## 6. Detect deprecated and for-removal APIs

An API marked `@Deprecated` may still work. The annotation signals that the API is discouraged; it does not automatically mean the API has been deleted.

Since Java 9, `@Deprecated` provides two attributes:

- `since`: the version in which deprecation began.
- `forRemoval`: whether the API is slated for removal.

Example:

~~~java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
}
~~~

Distinction:

| Status | Meaning | How to handle |
|---|---|---|
| Deprecated, forRemoval = false | Discouraged; no announced removal plan yet | Identify a replacement API and plan updates |
| Deprecated, forRemoval = true | API is flagged for scheduled removal | Prioritize migration before the next JDK upgrade |
| Removed | API has been deleted from the JDK | Replace dependency/API; module flags cannot fix this |

### 6.1. Compiler warnings for deprecated APIs

Run `javac` with lint enabled:

~~~bash
javac --release 17 -Xlint:deprecation -d out src/example/*.java
~~~

The compiler reports locations using deprecated APIs. For APIs marked for removal, also enable:

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal -d out src/example/*.java
~~~

`-Werror` can turn warnings into errors in builds once the project is ready for strict enforcement:

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal -Werror -d out src/example/*.java
~~~

Avoid enabling `-Werror` abruptly on a large codebase with many untriaged warnings. Collect warnings first, resolve project-owned warnings, and then enforce the rule in CI.

### 6.2. Scan bytecode with jdeprscan

`jdeprscan` inspects class files, JARs, or directories for usage of deprecated Java platform APIs.

Scan a JAR against Java 17 APIs:

~~~bash
jdeprscan --release 17 app.jar
~~~

Focus exclusively on APIs marked for removal:

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

List deprecated APIs for the chosen release:

~~~bash
jdeprscan --release 17 --list
~~~

Scan a directory of compiled classes:

~~~bash
jdeprscan --release 17 build/classes/
~~~

`jdeprscan` is helpful when source code is unavailable or when auditing pre-compiled libraries. It does not replace compiler warnings: source compilation pinpoints exact source lines and refactoring context more clearly.

### 6.3. Check annotations and Javadoc

When a warning appears, consult the API Javadoc for your exact target JDK version:

- Since which version has the API been deprecated?
- Is `forRemoval` set to `true`?
- Does the documentation specify a replacement API?
- Does the replacement share the same behavior and security constraints?
- Is the replacement available in Java 17 or only in a newer JDK?

Do not pick a replacement API merely because its name looks similar. Review its contract, exceptions, thread-safety, security behavior, and compatibility conditions.

## 7. Examples of deprecated or for-removal APIs in JDK 17

Several APIs remain present in Java 17 but should not be introduced into new code.

### 7.1. Security Manager

JEP 411 deprecates the Security Manager for future removal. In Java 17, APIs such as `System.setSecurityManager` and `System.getSecurityManager` still exist but are deprecated for removal.

Legacy code might contain:

~~~java
System.setSecurityManager(new SecurityManager());
~~~

On JDK 17, using the Security Manager produces warnings tied to its deprecated-for-removal status. Installing a Security Manager is also subject to JDK constraints and may no longer fit modern application architectures.

Remediation:

- Identify which security policies the application relied on the Security Manager to enforce.
- Move permission enforcement to appropriate OS/container security, process isolation, service identities, filesystem permissions, and network policies.
- If a third-party library installs a Security Manager itself, upgrade or replace the library.
- Do not delete existing protections before identifying the security requirements they satisfy.

Do not equate removing the Security Manager with discarding sandboxing or authorization controls. Replacements should follow the application's threat model.

### 7.2. Applet API

JEP 398 deprecates the Applet API for removal in JDK 17. Applets are an obsolete browser-hosted Java deployment model; modern browsers no longer support Java plugins for that model.

If source code still references `java.applet.Applet` or `AppletContext`:

- Identify the actual functionality users need.
- Migrate functionality to a web application, desktop application, or appropriate service.
- Decouple reusable Java logic from Applet lifecycle and API specifics.
- Do not attempt to revive legacy browser plugins via JVM options.

In Java 17, the API may still be present, marked deprecated for removal. That differs from an API that has already been completely deleted.

### 7.3. Distinguish deprecated from removed

An API deprecated for removal still compiles on Java 17 while the API remains present. A removed API has no symbol left for the compiler to link against.

For instance, `Object.finalize()` is a legacy API deprecated for removal starting in JDK 18, not a removed API in Java 17. When targeting Java 17, verify exact status against your target release rather than projecting newer JDK changes backward onto JDK 17.

## 8. APIs and components removed prior to Java 17

When upgrading to JDK 17 from much older releases, some components may have disappeared back in JDK 11, 14, or 15. This is why you must check the full span of releases the application is skipping across.

### 8.1. Java EE and CORBA modules

Java EE and CORBA modules formerly bundled in the JDK were removed from the JDK in Java 11. Example modules:

- `java.xml.bind` (JAXB).
- `java.xml.ws` (JAX-WS).
- `java.xml.ws.annotation`.
- `java.activation`.
- `java.corba`.
- `java.transaction`.

If an application relied on packages such as `javax.xml.bind` simply because they used to ship with the JDK, compiling on Java 17 will report missing packages.

How to handle depends on need:

1. If the application still requires JAXB/JAX-WS, add maintained external API and implementation dependencies compatible with Java 17.
2. Identify which package namespace ecosystem your application uses: `javax.*` or `jakarta.*`.
3. Do not bulk-rename packages using find/replace; different JAXB/Jakarta versions have different namespaces and binary compatibility.
4. If the functionality is no longer needed, remove the dependencies and related code.

Removed modules cannot be restored via `--add-modules`. You must supply external libraries or replace the functionality.

### 8.2. Nashorn JavaScript Engine

Nashorn and the `jjs` tool were removed in JDK 15. Java 17 still includes the `javax.script` package, but no longer guarantees a built-in default JavaScript engine in the JDK.

Legacy code:

~~~java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
~~~

May return `null` if no compatible JavaScript engine is present on the classpath or module path.

If the application genuinely needs to execute JavaScript:

- Choose a JavaScript engine maintained independently of the JDK.
- Declare the engine dependency explicitly.
- Verify JSR 223 compatibility if continuing to use `ScriptEngineManager`.
- Evaluate sandboxing, host access controls, and resource limits of the engine.
- Write tests covering scripts, interoperability, and real behavior.

If Nashorn was only used to parse strings or JSON, consider native Java APIs or dedicated libraries rather than pulling in an unnecessary scripting engine.

### 8.3. Pack200

The Pack200 API and associated tools were removed from JDK 14. If build or deployment scripts still invoke `pack200`/`unpack200`, those commands will no longer exist on Java 17.

Replace packaging pipelines with supported artifact formats and tools, typically standard JARs with modern compression and transfer mechanisms. Do not expect a JVM option to restore removed command-line tools.

### 8.4. CMS Garbage Collector

The Concurrent Mark Sweep (CMS) collector was removed from HotSpot in JDK 14. Legacy configuration:

~~~bash
java -XX:+UseConcMarkSweepGC -jar app.jar
~~~

is no longer valid on Java 17 and will terminate JVM startup with an unrecognized option error.

Select a currently supported collector based on workload and latency/throughput goals. On Java 17, common choices include G1 (default on many server configurations), Parallel GC, ZGC, and Shenandoah depending on the JDK distribution. Check which collectors are included by your JDK vendor and deployment setup before choosing.

Do not swap CMS for another collector simply by renaming the flag; benchmark throughput, pause times, allocation rates, and footprint on representative workloads.

## 9. Detect legacy or invalid JVM options

JVM options can live in many places:

- `java` commands in shell scripts.
- `JAVA_TOOL_OPTIONS` or `JDK_JAVA_OPTIONS`.
- Docker `ENTRYPOINT`/`CMD`.
- Kubernetes manifests, Helm values, or service definitions.
- Build tools, test tasks, application servers, or monitoring agents.
- Migration scripts, batch jobs, and internal tooling.

A removed flag can prevent a process from starting. An obsolete flag may be recognized with a warning or no longer carry the effect the old configuration intended.

### 9.1. Recognize Unrecognized VM option errors

Example:

~~~text
Unrecognized VM option 'UseConcMarkSweepGC'
Error: Could not create the Java Virtual Machine.
Error: A fatal exception has occurred. Program will exit.
~~~

This occurs before application code runs. Verify flags against the exact Java binary used in that environment, because developer machines, CI, and production may run different JDKs.

Check versions:

~~~bash
java -version
javac -version
where java
~~~

On Linux/macOS, use `which java` instead of `where java`. When multiple JDKs are present, verify the actual executable path rather than relying solely on environment variables or command names.

### 9.2. Inspect JVM flags recognized by the JVM

You can print flags and their final values:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Filter by flag name on Linux/macOS:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep -i metaspace
~~~

On Windows PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String -Pattern 'Metaspace'
~~~

This output helps verify whether a flag exists and its active value. However, a flag appearing in the list does not prove it remains appropriate or effective as expected. Read the documentation and warnings for your exact JDK vendor.

### 9.3. Distinguish removed, obsolete, and deprecated flags

| Status | Symptom | How to handle |
|---|---|---|
| Removed / unrecognized | JVM reports `Unrecognized VM option` | Remove and replace with a supported configuration |
| Obsolete / ignored | JVM warns the option is obsolete or ignored | Remove from config; do not rely on old behavior |
| Deprecated | JVM warns the flag is deprecated though still accepted | Identify a replacement flag or mechanism; plan removal |
| Supported | JVM accepts and applies the flag | Still verify suitability for your workload and vendor |

Options can change status across JDK releases. Do not copy a "still works" flag list from a different JDK version without testing on the target runtime.

### 9.4. Common legacy JVM options

| Legacy option | Status / relevance on Java 17 | Resolution |
|---|---|---|
| `-XX:+UseConcMarkSweepGC` | CMS was removed in JDK 14 | Select a supported collector and re-benchmark |
| `-XX:+UseParNewGC` | CMS-related collector removed | Remove legacy config; review remaining GC flags |
| `-XX:PermSize` / `-XX:MaxPermSize` | PermGen was removed in JDK 8 | Remove PermGen flags; if metadata sizing is needed, inspect `-XX:MaxMetaspaceSize` |
| `--illegal-access` | Obsolete and ignored since JDK 17 | Remove option; fix dependencies or apply targeted module permissions during transition |
| `-XX:+UseBiasedLocking` | Biased locking disabled by default and deprecated since JDK 15 | Do not rely on this flag for tuning; measure workload and use supported configs |
| `-XX:+PrintGCDetails` / `-XX:+PrintGCDateStamps` | Legacy GC logging flags; Unified Logging is current | Migrate to `-Xlog:gc*` |

This table highlights common cases, not an exhaustive list of all JVM options. Flag status depends on the JDK release and vendor; verify directly on the target runtime.

### 9.5. Replace legacy GC logging with Unified Logging

Legacy scripts may include:

~~~bash
java -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:gc.log -jar app.jar
~~~

Java 17 uses Unified JVM Logging. Example current configuration:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

You can bound file size and rotation count:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Consult JDK 17 `-Xlog` documentation and size log rotation for your environment's disk capacity. Do not keep both legacy and unified logging flags if they duplicate logs or create confusing configurations.

### 9.6. Beware of IgnoreUnrecognizedVMOptions

The JVM offers `-XX:+IgnoreUnrecognizedVMOptions` to skip unrecognized options. This is not a migration fix.

If enabled in production, a critical flag could be silently ignored while the process still starts. For example, an expected heap limit or collector setting might not take effect.

During migration:

- Never add this option merely to hide flag errors.
- If an existing launcher already passes it, determine why and inspect all supplied flags.
- Remove invalid flags and verify the JVM boots with the intended configuration.
- Retain ignore mechanisms only when there is a specific, controlled, and tested compatibility requirement.

## 10. Project audit workflow when upgrading to Java 17

A repeatable workflow surfaces issues early and assigns clear dependency ownership.

### Step 1: Verify the actual JDK

Run in both build and runtime environments:

~~~bash
java -version
javac -version
jdeps --version
jdeprscan --version
~~~

If the project uses toolchains, verify which toolchain the build tool selects. Do not assume `java` on your terminal `PATH` matches the JDK used by Gradle/Maven.

### Step 2: Scan for internal APIs

On compiled artifacts:

~~~bash
jdeps --jdk-internals --multi-release 17 app.jar
~~~

Repeat for major dependencies, especially frameworks, bytecode libraries, ORMs, serializers, agents, and networking libraries.

Record:

- Artifact and version.
- Classes depending on internal APIs.
- Internal packages used.
- Whether a Java 17-compatible replacement version exists.
- Whether to upgrade a dependency or edit application source.

### Step 3: Scan for deprecated APIs

~~~bash
jdeprscan --release 17 app.jar
jdeprscan --release 17 --for-removal app.jar
~~~

Combine with compiling source using:

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal ...
~~~

When a build tool compiles the code, configure the equivalent compiler options inside the build tool rather than running only a standalone `javac` command.

### Step 4: Locate JVM options across all deployment configurations

Search repositories and deployment configs for keywords:

- `--illegal-access`
- `--add-exports`, `--add-opens`
- `UseConcMarkSweepGC`, `UseParNewGC`
- `PermSize`, `MaxPermSize`
- `PrintGCDetails`, `PrintGCDateStamps`, `Xloggc`
- `UseBiasedLocking`
- `IgnoreUnrecognizedVMOptions`

Then inspect environment variables and launch arguments injected by CI, containers, orchestrators, and service managers.

Do not delete options based solely on text search matches. Flags can appear in documentation or unused test scripts. Trace the actual execution path before editing.

### Step 5: Inspect dependencies and plugins

Review dependency graphs for the application, processors, and plugins. A build-time processor or plugin can depend on JDK internal APIs even if the runtime application artifact never uses them.

With Gradle, inspect specific dependency configurations:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration annotationProcessor
~~~

With Maven, inspect the dependency tree and plugin configuration:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Upgrade processors/plugins according to each vendor's Java 17 support matrix.

### Step 6: Run tests on JDK 17

At minimum, run:

- Compilation across all source sets.
- Unit tests and integration tests.
- Packaging and startup tests on the final artifact.
- Features using Reflection, serialization, scripting, XML binding, or native libraries.
- Startup/shutdown and scheduled jobs.
- Smoke tests inside the exact container/base image used in production.

An application can compile cleanly yet fail only when a framework initializes or a rare endpoint is invoked.

### Step 7: Verify logs and JVM configuration

Confirm:

- No `Unrecognized VM option` errors remain.
- No obsolete/ignored option warnings appear beyond intentionally accepted cases.
- No migration-related `IllegalAccessError`, `InaccessibleObjectException`, or `NoClassDefFoundError` failures occur.
- Flags such as heap sizing, GC, and logging genuinely take effect.
- Container startup commands match the tested configuration.

## 11. Handling dependencies that need internal access

If an audit finds an older library requiring internal package access, do not immediately add sweeping `--add-opens` flags.

### 11.1. Prioritize in order

1. Upgrade the library to a version supporting Java 17.
2. Replace internal APIs with public Java SE APIs.
3. Replace the library if upstream is unmaintained.
4. If migration time is needed, grant minimal module access to the exact package and module.
5. Document the exception, owner, and removal timeline.

### 11.2. Choose the right permission

| Error / need | What to evaluate |
|---|---|
| Source cannot access public types in an unexported package | `--add-exports` at compile and runtime if needed |
| Framework calls `setAccessible` on private members | `--add-opens` for the framework module at runtime |
| Module does not read the module containing the API | `requires` or `--add-reads`, then check exports |
| Class or module was removed | Replace dependency/API; add-exports/opens cannot help |
| JVM flag was removed | Remove and replace configuration; module options are unrelated |

### 11.3. Do not open all of java.base

Opening numerous internal packages to `ALL-UNNAMED` weakens encapsulation across the entire application.

If a specific framework needs a specific package, grant access only to that module:

~~~bash
java --add-opens java.base/java.lang=com.example.framework -jar app.jar
~~~

The target module name must match the module actually containing the code needing access. If the framework runs in the unnamed module, `ALL-UNNAMED` may be necessary, while recognizing that access is granted to all unnamed modules in the process.

### 11.4. Document module access exceptions

Each exception should capture:

| Field | Example content |
|---|---|
| Source package | `java.base/java.lang` |
| Target module | Framework module or `ALL-UNNAMED` |
| Option | `--add-opens` or `--add-exports` |
| Causing dependency | Artifact name and version |
| Reason | Framework needs access to a specific member |
| Plan | Target replacement version or migration issue |
| Removal criteria | Once the dependency no longer requires access |

This record tells operations why the flag exists and keeps legacy exceptions from propagating into systems that no longer need them.

## 12. Configure builds to check Java 17 continuously

### 12.1. Gradle toolchain and compiler lint

Groovy DSL example:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.compilerArgs += [
        '-Xlint:deprecation',
        '-Xlint:removal'
    ]
}
~~~

Toolchains select the right JDK for compilation tasks. `options.release = 17` restricts APIs and language level to Java 17. Lint surfaces deprecation and removal warnings in build logs.

To turn warnings into build errors once existing warnings are cleared, `-Werror` can be added per project policy.

### 12.2. Maven Compiler Plugin

Configuration example:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <showWarnings>true</showWarnings>
                <compilerArgs>
                    <arg>-Xlint:deprecation</arg>
                    <arg>-Xlint:removal</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Choose a Maven Compiler Plugin version compatible with the Maven/JDK used in your build. The example above illustrates Java 17 setup; your project may pin another centrally managed plugin version.

### 12.3. Integrate scans into CI

A pipeline can run the following checks on built artifacts:

~~~bash
jdeps --jdk-internals --multi-release 17 build/libs/app.jar
jdeprscan --release 17 build/libs/app.jar
jdeprscan --release 17 --for-removal build/libs/app.jar
~~~

Scan outputs can be archived as build artifacts and compared across releases. Once the project resolves existing findings, CI gates can block newly introduced internal APIs or for-removal APIs.

Do not treat every scan finding inside third-party dependencies as an application source error. Categorize by owner and track corresponding dependency upgrades.

## 13. Common internal API replacement patterns

There is no single drop-in replacement for every internal API. Identify the behavior your code needs and choose the matching public API.

| Legacy internal API | Common need | Public replacement path |
|---|---|---|
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | Base64 encoding and decoding | `java.util.Base64` |
| `sun.reflect.Reflection.getCallerClass` | Inspecting the caller on the stack | `StackWalker` |
| Certain atomic operations via `sun.misc.Unsafe` | Field access and atomic updates | `VarHandle`, `AtomicInteger`, `AtomicLong`, `AtomicReference` depending on case |
| `sun.misc.Cleaner` | Attaching cleanup actions to objects | `java.lang.ref.Cleaner` |
| File access via internal classes | Reading, writing, and manipulating files | `java.nio.file.Files`, `Path`, `FileChannel` |

Base64 replacement example:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String encoded = Base64.getEncoder()
        .encodeToString("Java 17".getBytes(StandardCharsets.UTF_8));

byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

Caller inspection replacement using StackWalker:

~~~java
StackWalker walker = StackWalker.getInstance();

String caller = walker.walk(frames -> frames
        .skip(1)
        .findFirst()
        .map(StackWalker.StackFrame::getClassName)
        .orElse("<unknown>"));
~~~

Using VarHandle for a field:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int increment() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
~~~

These examples illustrate migration directions and are not always 100% semantically identical to legacy internal APIs. Especially with `Unsafe`, verify memory ordering, alignment, atomicity, and lifecycle semantics before replacing.

## 14. Read runtime errors to identify the problem category

The following exceptions may appear during an upgrade:

| Error | Common meaning | Investigation path |
|---|---|---|
| `IllegalAccessError` | Bytecode attempted to access a forbidden type/member | Check exports, module graph, and dependencies |
| `InaccessibleObjectException` | Reflection could not enable deep access | Check whether the package is opened to the caller |
| `ClassNotFoundException` | Class not found during dynamic loading | Check dependencies/runtime classpath and removed APIs |
| `NoClassDefFoundError` | JVM could not define or link a required class | Check missing dependencies, class initialization, and incompatible libraries |
| `NoSuchMethodError` | Bytecode invoked a method absent in the loaded class version | Check version conflicts and binary compatibility |
| `Unrecognized VM option` | JVM rejected a passed flag | Check JVM version and remove/replace the flag |
| `NoSuchFieldError` | Bytecode referenced a field absent in the runtime class | Check dependency version mismatches |

Do not assume every error above is caused by Java 17 itself. For instance, `NoSuchMethodError` often stems from two incompatible library versions coexisting on the runtime classpath. Inspect the stack trace, class loader, and dependency origins before altering JVM options.

## 15. Migration checklist for a release

Use this checklist to track upgrade tasks:

- [ ] Build tools and runtime genuinely use JDK 17.
- [ ] Source compiles with `--release 17`.
- [ ] Ran `jdeps --jdk-internals` on application artifacts and key dependencies.
- [ ] Ran `jdeprscan --release 17` and `--for-removal`.
- [ ] Addressed warnings from `-Xlint:deprecation` and `-Xlint:removal`.
- [ ] Reviewed legacy Java EE/CORBA modules, Nashorn, Pack200, and CMS if previously used.
- [ ] Audited JVM options across scripts, containers, CI, and environment variables.
- [ ] Removed `--illegal-access` from Java 17 configurations.
- [ ] Every remaining `--add-exports`/`--add-opens` has an explicit package, target module, owner, and rationale.
- [ ] Zero `Unrecognized VM option` errors with the exact production launch command.
- [ ] Executed unit tests, integration tests, startup/shutdown, and smoke tests on JDK 17.
- [ ] Verified runtime dependencies, plugins, agents, and annotation processors.
- [ ] Archived scan outputs and remaining exceptions for follow-up in subsequent releases.

This checklist is a migration tracking aid. Applicable items depend on your architecture; not every project uses scripting engines, Java EE modules, native libraries, or the module path.

## 16. Hands-on exercises

### Exercise 1: Detect internal APIs

A JAR was built on an older JDK. Write the command to check dependencies on JDK internal APIs when running on Java 17.

**Answer:**

~~~bash
jdeps --jdk-internals --multi-release 17 app.jar
~~~

### Exercise 2: Scan for-removal APIs

Write the command to find APIs deprecated for removal in an artifact.

**Answer:**

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

### Exercise 3: Distinguish exports and opens

A framework uses Reflection to read private fields in an application package. Which directive should be considered?

**Answer:** `opens` the package to the framework module, or `--add-opens` at runtime during migration. `exports` only grants access to public APIs per access modifiers; it does not grant deep reflection.

### Exercise 4: Handle --illegal-access

A Java 17 script still runs with `--illegal-access=permit`. Should this option be retained for compatibility?

**Answer:** No. Since Java 17, the option is obsolete and ignored. Identify the dependency performing internal access, upgrade/replace it, or grant narrow module permissions temporarily if needed.

### Exercise 5: CMS flag

An application launches with `-XX:+UseConcMarkSweepGC` and the JVM reports `Unrecognized VM option`.

**Answer:** CMS was removed from HotSpot in JDK 14. Choose a supported collector in JDK 17 and re-benchmark the workload rather than attempting to restore the flag.

### Exercise 6: API no longer in the JDK

A Java 8 application imports `javax.xml.bind.JAXBContext`, and compiling on Java 17 reports a missing package.

**Answer:** JAXB has not been bundled in the JDK since Java 11. If still needed, declare external JAXB API and implementation dependencies compatible with Java 17; check `javax`/`jakarta` namespaces and dependency compatibility.

### Exercise 7: Does --add-opens fix a removed API?

**Answer:** No. `--add-opens` only opens an existing package for runtime Reflection. Removed APIs or modules require replacement dependencies or code changes.

### Exercise 8: Why does compilation succeed yet runtime fails?

A library calls `Class.forName` with an internal class name assembled from configuration. `jdeps` reported no static reference.

**Answer:** `jdeps` analyzes dependencies inferable from bytecode; dynamic accesses may not appear as static dependencies. Run integration tests and inspect actual class-loading and Reflection code paths.

## 17. Key takeaways

When upgrading to Java 17, classify issues clearly:

1. **Internal APIs:** detect with `jdeps --jdk-internals`; replace with public APIs or upgrade dependencies.
2. **Deprecated APIs:** detect with compiler lint and `jdeprscan`; prioritize `forRemoval = true` APIs.
3. **Removed APIs/modules:** replace the dependency or feature; module access flags cannot restore them.
4. **Obsolete/removed JVM options:** audit startup scripts and test directly against JDK 17.
5. **JPMS access exceptions:** use `--add-exports` or `--add-opens` only for necessary packages and modules, with a removal plan.

Java 17's strong encapsulation surfaces implementation couplings that never had stability guarantees. A sound migration updates source and dependencies, audits JVM options across all environments, and verifies everything with tests and scan tools on the target JDK itself.

## 18. References

- [Oracle Java SE 17 — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): dependency analysis and `--jdk-internals`.
- [Oracle Java SE 17 — jdeprscan](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): scanning for deprecated API usage.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, lint, and compiler options.
- [Oracle Java SE 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): JVM options, module access, and Unified Logging.
- [Oracle Java SE 17 — JDK Migration Guide](https://docs.oracle.com/en/java/javase/17/migrate/): changes and guidance for moving applications to JDK 17.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation in JDK 17 and `--illegal-access` status.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): status change for the Security Manager.
- [JEP 398 — Deprecate the Applet API for Removal](https://openjdk.org/jeps/398): status of the Applet API in JDK 17.
- [JEP 363 — Remove the Concurrent Mark Sweep (CMS) Garbage Collector](https://openjdk.org/jeps/363): removal of CMS.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): removal of Nashorn.
- [JEP 374 — Disable and Deprecate Biased Locking](https://openjdk.org/jeps/374): biased locking status since JDK 15.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): Java EE and CORBA modules removed in JDK 11.
- [JEP 367 — Remove the Pack200 Tools and API](https://openjdk.org/jeps/367): removal of Pack200.
