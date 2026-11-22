# Choosing the Right Tools When Designing a Java Toolchain

In the **Toolchain Design** topic, choosing tools means picking the right tool for the right job and the required output. Not every task requires a new tool: `javac` compiles source code, `java` runs programs, Maven or Gradle orchestrates builds, an IDE supports development, and diagnostic tools are only added when there is a specific question to answer.

This lesson helps you choose the right tools in the JDK and the Java ecosystem, distinguish between tools with similar capabilities, combine them into a repeatable workflow, and avoid installing too many overlapping tools.

The commands are cross-checked against the built-in help of Zulu/OpenJDK 24.0.2 on Windows 11. Java examples use syntax and APIs compatible with Java 17+. The sample pipeline has been run to verify compile, run, JAR, Javadoc, bytecode, dependency analysis, JShell, custom runtime image, application image, signing, and JVM diagnostics.

## 1. Start from the question, not from a list of tools

Before choosing a tool, clearly define the desired output:

- Do you need to turn source code into `.class` files or a JAR?
- Do you need to run a program, test an expression, or debug a process?
- Do you need a dependency graph, API documentation, or module dependencies?
- Do you need to package an application for other developers, or create an installer for end users?
- Do you need to inspect certificates, signatures, bytecode, or performance?
- Do you need reproducible builds on a local machine, in CI, or across multiple operating systems?

Each output has a corresponding group of suitable tools. Choosing tools by task keeps commands shorter, logs easier to understand, and results easier to verify.

For example, if you only want to inspect the bytecode of a class, `javap` is appropriate. If you want to see which modules a library depends on, `jdeps` is appropriate. If you want to create an installer for end users, `jpackage` is appropriate; `jar` only creates an archive.

## 2. Task-to-tool selection map

| Task | Suitable Tool | Primary Output |
|---|---|---|
| Compile Java source | `javac` | `.class` |
| Run class/JAR/module | `java` | Java process |
| Test code quickly | `jshell` | Interactive result |
| Package or inspect a JAR | `jar` | JAR archive |
| Generate API documentation | `javadoc` | HTML documentation |
| View bytecode/class API | `javap` | Class signature/disassembly |
| Analyze dependencies/modules | `jdeps` | Dependency report |
| Find deprecated APIs | `jdeprscan` | Deprecated API report |
| Create a custom runtime image | `jlink` | Java runtime image |
| Package desktop/server applications | `jpackage` | Application image/installer |
| Manage keystores/certificates | `keytool` | Keystore/certificate |
| Sign and verify JARs | `jarsigner` | Signed JAR/verification result |
| Diagnose a running JVM | `jcmd` | Threads, heap, flags, JFR, and other reports |
| Analyze recordings | `jfr` | Flight Recorder report |
| Inspect threads/heap/GC | `jstack`, `jmap`, `jstat` | Thread dump, heap, GC statistics |
| List Java processes | `jps` | PID and process info |
| Monitor with a GUI | `jconsole` | JVM monitoring |
| Serve static files for testing | `jwebserver` | Local HTTP server |
| Manage dependencies and lifecycle | Maven or Gradle | Build/test/package/publish |
| Write, refactor, debug | IDE | Source navigation/debugging |
| Automated testing | JUnit/TestNG + build tool | Test results |
| Quality analysis | Checkstyle/PMD/SpotBugs/Error Prone | Static analysis report |

This table is a starting point. Some tasks can use multiple tools, but there should be one primary tool per goal, adding another tool only when it provides complementary information.

## 3. Distinguishing JDK tools, build tools, IDEs, and environment managers

These four groups are often collectively called "Java tools", but they solve different problems:

| Group | Examples | Responsibilities |
|---|---|---|
| JDK tools | `javac`, `java`, `jar`, `javadoc`, `jcmd` | Compile, run, package, inspect, and diagnose |
| Build tools | Maven, Gradle | Dependencies, lifecycle, task graph, test, package, and publish |
| IDE | IntelliJ IDEA, Eclipse, VS Code | Edit, navigate, refactor, debug, and build integration |
| JDK/environment managers | SDKMAN!, mise, asdf, jabba, OS package managers | Install/switch JDKs and manage the developer environment |

For example, `javac` can compile a standalone Java file, but it does not replace Maven/Gradle for managing dependencies, resources, test lifecycles, plugins, and publication in a large project. An IDE can invoke Maven/Gradle, but the build script remains the shared configuration for CI and other developers.

## 4. `javac` and `java`: compile then run

Use `javac` when you need to compile source code directly or verify exact compiler options:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out src/com/example/Main.java
~~~

- `--release 17` restricts language rules, APIs, and the class-file target to Java 17.
- `-encoding UTF-8` fixes the source encoding.
- `-Xlint:all` enables common compiler warnings.
- `-Werror` treats warnings as errors.
- `-d out` sets the output directory.

Use `java` to run a class, JAR, module, or source-file mode:

~~~text
java -cp out com.example.Main
java -jar app.jar
java --module-path mods -m com.example.app/com.example.app.Main
java Main.java
~~~

Source-file mode is suitable for small examples, scripts, or quick experiments on Java 11+. For applications with multiple source files, dependencies, and tests, switch to Maven/Gradle.

Do not confuse the compile target with the runtime. `javac --release 17` generates Java 17-compatible classes; it does not turn the running `java` process into Java 17. The actual runtime is determined by the selected `java` executable.

## 5. `jshell`: quickly testing APIs and ideas

`jshell` is Java's REPL. Use it when you need to test an expression, API, collection, regex, stream, or small snippet without creating a project.

Launch:

~~~text
jshell
~~~

Example:

~~~java
var names = java.util.List.of("Ada", "Linus", "Grace");
names.stream().map(String::toUpperCase).toList()
~~~

You can run a script file and load a classpath:

~~~text
jshell --class-path lib/example.jar probe.jsh
~~~

Use `jshell` to explore APIs and create short bug reproductions. Once the logic is stable, move it into source code and automated tests in your project. A REPL does not replace unit tests, build scripts, or dependency management.

## 6. `jar`: packaging and inspecting archives

Use `jar` when you need to create, list, update, extract, or view the module descriptor in a JAR.

Create an executable JAR:

~~~text
jar --create --file app.jar --main-class com.example.Main -C out .
~~~

List contents and describe the module:

~~~text
jar --list --file app.jar
jar --describe-module --file app.jar
~~~

Extract the manifest for inspection:

~~~text
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

`jar` creates archives; it does not resolve transitive dependencies, run tests, or build installers. When a project uses Maven/Gradle, let the build tool configure the JAR task and manifest, and use `jar` to inspect the result.

## 7. `javadoc`: generating API documentation

Use `javadoc` to generate HTML documentation from packages, modules, and source comments.

Example:

~~~text
javadoc -quiet -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example
~~~

- `-d docs` sets the output directory.
- `-sourcepath src` specifies the source location.
- `-subpackages` selects the package hierarchy.
- `-Xdoclint:all` checks Javadoc syntax and content.
- `-Werror` fails the build if warnings remain.

For Maven/Gradle projects, configure the Javadoc task/plugin in the build so documentation is generated automatically alongside releases. Choose `javadoc` when you need API docs; usage READMEs and architecture documentation usually still need to be written separately.

## 8. `javap`, `jdeps`, and `jdeprscan`: three different questions

These three tools are often mistakenly used interchangeably:

**`javap`** answers: what methods, fields, and bytecode does a compiled class contain?

~~~text
javap -classpath app.jar -public com.example.Main
javap -classpath app.jar -c -p com.example.Main
javap -verbose -classpath app.jar com.example.Main
~~~

Use `-c` to view bytecode, `-p` to include private members, and `-verbose` to inspect class-file details.

**`jdeps`** answers: which packages or modules does a class/JAR depend on? Does it use JDK internal APIs?

~~~text
jdeps --summary app.jar
jdeps --print-module-deps app.jar
jdeps --jdk-internals app.jar
~~~

`jdeps --print-module-deps` is useful when preparing the module list for `jlink`. Static analysis may miss dependencies loaded dynamically via reflection, service loaders, plugins, or class names constructed from configuration; verify further with tests/runtime.

**`jdeprscan`** answers: does the binary reference APIs deprecated in a given Java release?

~~~text
jdeprscan --release 17 app.jar
~~~

Choose `javap` to inspect a class, `jdeps` to analyze dependencies, and `jdeprscan` to scan for deprecated APIs. Do not use one report as a substitute for the others.

## 9. `jlink` and `jmod`: working with modules and runtime images

`jlink` creates a runtime image containing only the required modules. It is useful when distributing a modular application with a smaller runtime than the full JDK.

Example:

~~~text
jlink --module-path "%JAVA_HOME%\jmods;mods" --add-modules com.example.app --output runtime
~~~

For modular applications, you can use `jdeps --print-module-deps` to find initial module dependencies, then verify service bindings, reflection, and runtime paths before linking.

`jlink` operates on the module graph. JARs on the classpath or automatic modules cannot be linked like regular named modules; modularize dependencies or use another distribution method.

`jmod` creates, lists, extracts, describes, or hashes JMOD archives. JMODs typically appear in JDK/runtime build pipelines and advanced module workflows. Most regular Java applications do not need to create JMODs manually.

## 10. `jpackage`: packaging applications for end users

Use `jpackage` when you need an application image or native installer with an accompanying launcher and runtime.

Example creating an application image from a JAR:

~~~text
jpackage --type app-image --name SampleApp --input dist --main-jar app.jar --main-class com.example.Main --dest packages
~~~

An `app-image` is a packaged application directory; it is not yet an installer. Depending on the OS and installed native tools, `jpackage` can produce package types such as `msi`, `exe`, `deb`, `rpm`, `dmg`, or `pkg`.

Choose `jpackage` for applications distributed as desktop/server packages. Choose `jlink` when the primary goal is a runtime image. `jpackage` can invoke `jlink` to build the bundled runtime. For modular applications, use `--module`; for classpath applications, use `--main-jar` and `--main-class`.

If the goal is a native executable without a JVM runtime, that is a different approach, such as GraalVM Native Image. Native Image is not a default JDK command and has its own compatibility and build requirements.

## 11. `keytool` and `jarsigner`: certificates vs. JAR signatures

Use `keytool` to create and manage keystores, key pairs, certificate requests, certificates, and truststores.

Common commands:

~~~text
keytool -genkeypair -alias release -keyalg RSA -keysize 3072 -keystore release.p12 -storetype PKCS12
keytool -list -v -keystore release.p12
keytool -printcert -file publisher.cer
keytool -importcert -alias publisher -file publisher.cer -keystore truststore.p12
~~~

Use `jarsigner` to sign and verify JARs:

~~~text
jarsigner -keystore release.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar release
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

`keytool` manages keys/certificates; `jarsigner` signs or verifies JARs. A self-signed certificate allows checking digests/signatures, but does not automatically establish a trust chain for users. Releases need an appropriate certificate/key identity, fingerprint, timestamp, and trust policy.

Do not store passwords or private keys in POMs, source repositories, committed scripts, or CI logs. Use a secret store and secure credential input mechanisms. A JAR signature is also different from a detached PGP signature created by GPG.

## 12. `jcmd`: the starting point for JVM diagnostics

When a Java application is running, `jcmd` sends diagnostic commands to the JVM process. First, list processes:

~~~text
jcmd -l
~~~

View the commands supported by the JVM:

~~~text
jcmd <pid> help
~~~

Some examples:

~~~text
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> Thread.print -l
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

`jcmd` offers more commands than standalone diagnostic tools and is usually a helpful starting point. Available commands depend on the JVM/version and attach permissions. It usually needs to run under the same user as the target process; containers, service accounts, and attach-disabled JVMs can restrict access.

Diagnosing production processes requires a clear goal, choosing low-impact commands first, and recording the timestamp and commands executed. Heap dumps or histograms can increase pauses and consume significant disk/memory.

## 13. Choosing between `jstack`, `jmap`, `jstat`, `jps`, `jconsole`, and `jhsdb`

| Tool | Use When | Example |
|---|---|---|
| `jps` | You need to find Java processes and PIDs | `jps -lv` |
| `jstack` | You need a standalone thread dump | `jstack -l <pid>` |
| `jmap` | You need a heap histogram or heap dump | `jmap -histo:live <pid>` |
| `jstat` | You need to observe GC/heap statistics over time | `jstat -gcutil <pid> 1000 5` |
| `jconsole` | You need a GUI for MBeans, memory, threads, and monitoring | `jconsole` |
| `jhsdb` | You need advanced serviceability-level JVM/core dump debugging | `jhsdb hsdb` |

On newer JDKs, check `jcmd` diagnostic commands before picking a separate tool. For example, `jcmd <pid> Thread.print -l` produces a thread dump; `jcmd <pid> GC.heap_dump filename=heap.hprof` can create a heap dump.

Heap dumps can contain tokens, passwords, request payloads, and user data in memory. Store them in a protected location, restrict access permissions, and delete them according to retention policies. Do not take a heap dump in production just to "take a look".

## 14. JFR and `jfr`: data-driven performance recording

Java Flight Recorder (JFR) records JVM and application events such as allocations, GC, threads, locks, class loading, and selected system events.

Start a recording from a running process:

~~~text
jcmd <pid> JFR.start duration=60s filename=app.jfr
~~~

View summary and events:

~~~text
jfr summary app.jfr
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample app.jfr
~~~

JFR is useful when you need to understand a period of high CPU, unusual GC activity, or lock contention. Use a recording configuration tailored to your question and evaluate overhead for your workload. Java Mission Control (JMC) provides a UI for analyzing recordings; JMC may need to be installed separately depending on the JDK distribution.

Choose JFR for profiling/recording over a time window. Choose a thread dump when you need a snapshot of thread states at a single point in time. Both outputs complement each other.

## 15. `jwebserver`: static server for local development

`jwebserver` is a simple HTTP server bundled with the JDK for serving static files during development or testing.

Example:

~~~text
jwebserver --bind-address 127.0.0.1 --port 8000 --directory public
~~~

Open `http://127.0.0.1:8000/` to inspect files in the `public` directory. The server binds to loopback by default; you can change the bind address when genuinely needed.

This is a quick testing utility, not a production web server. For APIs, authentication, TLS, routing, or real workloads, choose a framework/server suited to your application's requirements.

## 16. Maven or Gradle?

Both Maven and Gradle manage dependencies, build lifecycles, compilation, testing, JARs, publication, and plugins. Choose one primary build system per project unless there is a specific integration reason.

| Criterion | Maven | Gradle |
|---|---|---|
| Configuration | Convention-based POM XML | Groovy DSL or Kotlin DSL |
| Lifecycle | Standard lifecycle phases | Flexible task graph |
| Dependencies | POM, BOM, scopes | Configurations, variants, rich metadata |
| Build logic | Plugins and lifecycle conventions | Deeply customizable task/plugin model |
| Wrapper | Maven Wrapper | Gradle Wrapper |
| Best suited for | Convention-driven projects, Maven ecosystem | Custom builds, multi-project, and variant-aware builds |

Use Maven when a project follows Maven conventions and you want a familiar lifecycle and broad ecosystem POM compatibility. Use Gradle when you need a flexible task graph, complex build logic, or variant modeling. Both build Java well; base your decision on project needs, team skills, and required plugins.

Do not choose Gradle solely because build scripts look shorter, nor Maven solely because XML is familiar. Test a vertical slice covering compile, test, package, dependency, and publish to evaluate.

## 17. Wrappers and toolchains are part of build tool selection

Commit the wrapper so everyone uses the same build tool version:

~~~text
./mvnw -version
./gradlew --version
~~~

The wrapper pins the Maven/Gradle distribution; it does not pin the JDK by itself. To select the JDK for compiling/testing, use Maven Toolchains or Gradle Java Toolchains. To select the JVM running Maven/Gradle itself, configure `JAVA_HOME`, the IDE runner, or appropriate daemon JVM criteria.

A project should explicitly declare its Java target using `--release` or equivalent configuration. Do not rely on the default JDK installed on a developer's machine.

## 18. Choosing a test framework and test runner

The JDK provides the compiler and runtime, but does not bundle a mainstream unit-test framework like JUnit.

Common choices:

- **JUnit Jupiter:** the standard default choice for modern Java unit tests.
- **TestNG:** suitable for teams with existing suites or specific TestNG feature needs.
- **Mockito:** supports mocking/stubbing collaborators; it is not a test runner.
- **Testcontainers:** runs real dependencies/services in containers for integration tests.

Maven Surefire typically runs unit tests in the `test` phase; Maven Failsafe typically orchestrates integration tests in the `integration-test` and `verify` phases. The Gradle Java Plugin provides the `test` task; the `check` task aggregates verification tasks, while `build` typically combines `check` and `assemble`. Separate tasks can be created for integration tests.

Choose a framework based on test style, ecosystem, extensions, and integration capabilities. Avoid adding multiple test frameworks to the same project without a migration or compatibility reason.

## 19. Choosing static analysis and formatters by goal

Different tools check different classes of issues:

| Goal | Example Tools |
|---|---|
| Compiler warnings | `javac -Xlint:all` |
| Code style/rules | Checkstyle |
| Source-level rule analysis | PMD |
| Bytecode bug patterns | SpotBugs |
| Compile-time bug checks | Error Prone |
| Formatting | google-java-format or Spotless |
| Quality dashboard/gate | SonarQube |

You do not need to enable every tool at once. Pick one standard formatter, one style rule set, and analyzers capable of catching bugs that the compiler and tests do not cover. Pin versions and rule configurations in the build so local and CI runs yield consistent results.

`javac -Werror` is useful once the team has warnings under control; enabling it on a legacy project may break the build due to existing warnings. Roll it out incrementally and address warnings deliberately.

## 20. Choosing an IDE for your team's workflow

An IDE speeds up reading and modifying code, but should not become the sole place where build configuration lives.

- IntelliJ IDEA: Java navigation, refactoring, debugging, and Maven/Gradle integration.
- Eclipse: long-standing Java tooling, workspaces, and plugin ecosystem.
- Visual Studio Code with Extension Pack for Java: lighter editor with Java language server, debugging, and project integration.

When evaluating an IDE, test opening the project via the wrapper, importing dependencies, running tests, debugging, and viewing Javadocs. Check Project SDK, Maven Runner JRE, Gradle JVM, and build delegation settings. Terminal/CI builds must produce results equivalent to IDE-delegated builds.

Do not commit files containing absolute SDK paths from a single developer's machine unless they are part of project policy.

## 21. Choosing a JDK manager and installation method

JDK managers are useful when switching between multiple Java releases or vendors:

- SDKMAN! is commonly used on Linux/macOS and compatible shells.
- mise or asdf manages multiple runtime/tool versions.
- jabba provides a cross-platform JDK management workflow.
- OS package managers such as winget, Homebrew, or Scoop can install JDKs.

Choose one primary mechanism for installing/switching JDKs per machine to prevent multiple managers from modifying `PATH` at the same time. Record the project's JDK requirement in toolchain configuration and CI; a workstation's version manager file is an environment convenience, not a replacement for the project build contract.

If your organization requires a specific vendor, patch level, or license, select an approved distribution and document that policy clearly.

## 22. Choosing tools in CI and containers

CI needs reproducible environments and visible proof of which JDK is in use. GitHub Actions example:

~~~yaml
steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'
      cache: maven

  - name: Show toolchain
    run: |
      java -version
      javac -version
      ./mvnw -version

  - name: Verify
    run: ./mvnw -B -ntp clean verify
~~~

With Gradle, use `./gradlew --no-daemon clean check` and declare Java toolchains in the build. For multiple supported runtimes, use a CI matrix to run tests on each version.

In Docker, choose a base image with the right JDK/JRE for its role. The build stage typically needs a JDK and build tool; the runtime stage can use a JRE or a custom image created with `jlink`. Paths and processes inside a container follow the image's OS, not automatically the host's.

When strict build reproducibility is required, pin the image digest, JDK distribution/patch, wrapper, plugins, and dependency versions.

## 23. Sample workflow: from source to runtime image

Suppose a small project has its source at `src/com/example/tools/HelloToolchain.java` and its main class is `com.example.tools.HelloToolchain`.

Compile for Java 17:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d classes src/com/example/tools/HelloToolchain.java
~~~

Create the JAR and run it:

~~~text
jar --create --file dist/hello-toolchain.jar --main-class com.example.tools.HelloToolchain -C classes .
java -jar dist/hello-toolchain.jar
~~~

Sample stdout:

~~~text
JAVA_TOOLCHAIN_OK
~~~

Generate Javadoc, inspect bytecode, and analyze dependencies:

~~~text
javadoc -quiet -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example.tools
javap -classpath dist/hello-toolchain.jar -c com.example.tools.HelloToolchain
jdeps --print-module-deps dist/hello-toolchain.jar
~~~

For a sample using only the Java base module, `jdeps` outputs:

~~~text
java.base
~~~

Test the API in JShell:

~~~text
jshell --class-path dist/hello-toolchain.jar --feedback concise probe.jsh
~~~

Create a minimal runtime image for the sample:

~~~text
jlink --add-modules java.base --output runtime-image --strip-debug --no-header-files --no-man-pages
~~~

Run with the runtime image:

~~~text
runtime-image/bin/java -jar dist/hello-toolchain.jar
~~~

Stdout remains `JAVA_TOOLCHAIN_OK`. For real applications, derive the module list from dependency analysis and then verify dynamic loading/service binding before release.

## 24. Sample workflow: packaging and diagnostics

Create an application image on Windows:

~~~powershell
jpackage --type app-image --name HelloToolchain --input dist --main-jar hello-toolchain.jar --main-class com.example.tools.HelloToolchain --dest packages --app-version 1.0.0
~~~

This command creates an application image with a launcher and runtime. The final installer type depends on the OS and native packaging tools.

Find the JVM process and inspect its state:

~~~text
jcmd -l
jcmd <pid> VM.version
jcmd <pid> Thread.print -l
~~~

Capture a 60-second JFR recording and read its summary:

~~~text
jcmd <pid> JFR.start duration=60s filename=app.jfr
jfr summary app.jfr
~~~

If certificates and JAR signatures are required, use `keytool` to prepare keys/certificates and `jarsigner` to sign/verify. Separate the signing step from compile/package so artifacts are only signed after their contents are finalized.

## 25. Choosing tools by real-world scenario

| Scenario | Start With | Add When Needed |
|---|---|---|
| Learning Java, testing APIs | `jshell` | IDE or small project |
| Compiling a standalone example | `javac` + `java` | `jar` if an archive is needed |
| Developing a multi-module app | Maven/Gradle + IDE | JUnit, static analysis |
| Publishing a Java library | Maven/Gradle | Sources/Javadoc, signing, SBOM |
| Inspecting an unfamiliar class | `jar --list`, `javap` | `jdeps`, `jdeprscan` |
| Shrinking the distributed runtime | `jdeps` + `jlink` | Runtime testing on each OS |
| Creating a desktop installer | `jpackage` | OS-specific native packagers |
| Hangs or deadlocks | `jcmd Thread.print` | Multiple thread dumps over time, JFR |
| Abnormal CPU/GC | JFR | JMC, `jstat`, application metrics |
| Abnormal memory growth | `jcmd GC.heap_info` | Histogram/heap dump, heap analyzer |
| TLS/certificate errors | `keytool` | Truststore inspection, TLS debug |
| JAR signature errors | `jarsigner -verify` | Certificate chain/fingerprint validation |
| Testing static file serving | `jwebserver` | Production web server/framework |

Start with the least intrusive tool that can answer the question. Only take heap dumps, run long profiler recordings, or modify runtime images when you have a clear goal and an appropriate storage location for the output.

## 26. Common poor choices

### Using `jar` instead of Maven/Gradle

`jar` does not resolve dependencies, compile source sets, run tests, or publish component metadata. Use it for simple archives or inspection; use a build tool for projects with a lifecycle.

### Using `javap` to find dependencies

`javap` inspects a single class. Use `jdeps` to inspect package/module dependencies and `jdeprscan` to find deprecated APIs.

### Using `jlink` to create an installer

`jlink` creates a runtime image. Use `jpackage` to create an application image or installer.

### Using `jpackage` to create a JVM-independent native executable

`jpackage` packages the application together with a runtime image or existing runtime. A standalone native executable is a separate problem, such as GraalVM Native Image.

### Using JFR when you only need a thread dump

JFR records events over a time window. Use `jcmd <pid> Thread.print -l` when you need a snapshot of threads at a single point in time.

### Taking a heap dump before identifying the memory problem

Heap dumps can be large, contain sensitive data, and cause pauses. Check metrics, `GC.heap_info`, histograms, or JFR first; only dump when you have a specific question and sufficient storage space.

### Using IDE settings instead of build configuration

IDE settings only reflect a single workstation. Put JDK, compiler release, dependency, and test configuration into Maven/Gradle/CI.

### Adding multiple overlapping formatters/analyzers

Tools with overlapping rules can produce duplicate warnings, hard-to-maintain configurations, and inconsistent results. Choose tools for clearly complementary capabilities.

### Using a JDK manager instead of Maven/Gradle toolchains

A JDK manager selects the JDK on the machine; Maven/Gradle toolchains select the project's compiler and test launcher. Both layers need to be configured for their respective roles.

## 27. Criteria for evaluating a tool before adding it to the toolchain

Before adding a tool, answer:

1. **Goal:** what specific problem does the tool solve?
2. **Output:** what file, report, package, or process change does it produce?
3. **Compatibility:** which JDKs, OSes, architectures, and build tools does it support?
4. **Automation:** can it run in CI without GUI interaction?
5. **Reproducibility:** can its version, configuration, and inputs be pinned?
6. **Security:** what permissions does it require, what data does it read, and where are secrets stored?
7. **Maintenance:** who updates versions, handles warnings, and resolves plugin conflicts?
8. **Overlap:** does the tool duplicate functionality the project already has?
9. **Cost:** what is the impact on build time, RAM, disk, licensing, and operational overhead?
10. **Team fit:** can the team debug and maintain it?

A tool should only be added when its practical benefits outweigh the cost of installation, configuration, upgrades, and support.

## 28. Java toolchain design checklist

- [ ] Source, artifacts, runtime, and distribution environments are defined.
- [ ] JDK tools are used for their intended tasks: compile, run, package, inspect, docs, or diagnostics.
- [ ] One primary build tool is used and its wrapper is committed.
- [ ] Java toolchain and target release are pinned.
- [ ] The IDE uses the same project build configuration as CLI/CI.
- [ ] An appropriate test framework and test runner are in place.
- [ ] Formatters/static analyzers are chosen by goal, avoiding overlapping rules.
- [ ] There is a way to inspect JARs, bytecode, and dependencies when needed.
- [ ] `jlink`/`jpackage` are used for the right output type.
- [ ] Certificates/private keys are protected; signatures are verified according to trust policy.
- [ ] JVM diagnostics are targeted, low-impact, and stored securely.
- [ ] CI runs the wrapper and prints Java/build tool versions.
- [ ] Runtimes/installers are tested on every supported OS.
- [ ] Tool versions and configurations are recorded for reproducible builds.
- [ ] Each new tool has an owner responsible for maintenance.

## 29. References

- Oracle JDK 24 — JDK Tools and Utilities: https://docs.oracle.com/en/java/javase/24/docs/specs/man/index.html
- Oracle JDK 24 — `javac`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Oracle JDK 24 — `java`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — `jshell`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jshell.html
- Oracle JDK 24 — `jar`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle JDK 24 — `javadoc`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html
- Oracle JDK 24 — `javap`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javap.html
- Oracle JDK 24 — `jdeps`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- Oracle JDK 24 — `jdeprscan`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html
- Oracle JDK 24 — `jlink` and `jpackage`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html and https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Oracle JDK 24 — `jcmd` and JFR: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html and https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html
- Oracle JDK 24 — `keytool` and `jarsigner`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html and https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html
- Oracle JDK 24 — `jwebserver`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jwebserver.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Maven Wrapper: https://maven.apache.org/wrapper/
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- JUnit 5 — User Guide: https://junit.org/junit5/docs/current/user-guide/
- GraalVM — Native Image: https://www.graalvm.org/latest/reference-manual/native-image/

Choosing the right tools means choosing the right layer of work: JDK tools for compile/run/inspect/diagnostics, Maven or Gradle for lifecycle and dependencies, an IDE for development, test/static-analysis tools for quality, and CI/toolchains for consistency. Start with the required output, pick the smallest toolset that meets the requirements, and verify the results on the actual runtime and target platform.