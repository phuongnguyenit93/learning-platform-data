# JDK Tool Map

The Java Development Kit (JDK) is a toolkit for writing, compiling, running, inspecting, packaging, securing, and diagnosing Java applications. The JDK is more than just a compiler. Each command addresses a specific part of the development lifecycle; choosing the right tool helps you find issues faster and avoid running high-impact commands unnecessarily.

This guide groups commands by practical tasks, explains their inputs and outputs, indicates when to use them, and connects them into a complete workflow. Examples and syntax are based on JDK 26. Many core commands also exist in earlier JDK releases, though options and behavior may vary by version, vendor, and operating system.

## 1. JDK Map by Lifecycle

~~~text
Explore and write
  jshell, jdb
        |
        v
Compile and run
  javac, java
        |
        v
Inspect and document
  jar, javap, javadoc, serialver
        |
        v
Analyze dependencies and modules
  jdeps, jdeprscan, jnativescan, jmod, jimage
        |
        v
Package and distribute
  jar, jlink, jpackage
        |
        v
Secure artifacts and certificates
  keytool, jarsigner
        |
        v
Operate and diagnose
  jcmd, jfr, jstat, jps, jconsole, jhsdb
~~~

Six questions to help you choose a tool:

1. Want to write or test code? Use `jshell`; debug step by step with `jdb`.
2. Want to turn source code into a runnable program? Use `javac` to compile and `java` to run.
3. Want to know what a build file contains? Use `jar`, `javap`, `jdeps`, `jmod`, or `jimage` depending on the file type.
4. Want to distribute an application? Use `jar`, `jlink`, or `jpackage`.
5. Need to verify or sign an artifact? Use `keytool` and `jarsigner`.
6. Need to know what the JVM is doing? Use `jcmd`, JFR/`jfr`, `jstat`, `jconsole`, or `jhsdb`.

Some tools appear in multiple stages. For example, `jar` both creates archives and inspects their contents; `jdeps` both assists with dependency reviews and helps prepare the module set for `jlink`.

## 2. Distinguishing JDK Tools from External Tools

JDK commands typically reside in the `bin` directory of the selected JDK:

~~~text
<JDK_HOME>/
  bin/
    java
    javac
    jar
    jcmd
    jlink
    ...
  conf/
  include/
  jmods/
  legal/
  lib/
~~~

On Windows, executables usually have the `.exe` suffix, such as `java.exe` and `javac.exe`.

| Group | Examples | Part of the JDK? |
|---|---|---|
| Compile/run | java, javac, jshell | Yes |
| Archive/inspect | jar, javap, javadoc | Yes |
| Dependency/module | jdeps, jmod, jimage, jlink | Yes |
| Package | jpackage | Yes |
| Security | keytool, jarsigner | Yes |
| JVM diagnostics | jcmd, jfr, jstat, jps, jconsole | Yes |
| Build automation | Maven, Gradle | No, installed separately |
| IDE | IntelliJ IDEA, Eclipse, VS Code extensions | No, installed separately |
| Profiling UI | JDK Mission Control (JMC) | Distributed separately; do not assume it is always included in the JDK |
| Container | Docker, Podman, Kubernetes | No |
| Source control | Git | No |

JDK tools provide foundational operations. Maven and Gradle orchestrate lifecycles, dependencies, plugins, tests, and build automation. IDEs assist with writing code and integrating tools. They complement each other rather than replacing one another.

## 3. Selecting the Right JDK Before Running Tools

A machine may have multiple JDKs installed. The `java` command on `PATH` and the JDK used by your IDE or CI may differ. Before investigating, identify the exact executable.

Linux/macOS:

~~~bash
java --version
javac --version
command -v java
echo "$JAVA_HOME"
~~~

Windows PowerShell:

~~~powershell
java --version
javac --version
Get-Command java -All
$env:JAVA_HOME
$env:PATH -split ';'
~~~

If you want to invoke a specific JDK directly, use the full path to its `bin` directory. Do not rely on `java --version` output in a terminal to conclude that Maven, Gradle, your IDE, or a service is using the same runtime.

Check tool help:

~~~bash
java --help
javac --help
jar --help
jlink --help
jpackage --help
~~~

Not every tool uses the same help syntax. For `jcmd`, query the JVM itself:

~~~bash
jcmd <pid> help
jcmd <pid> help JFR.start
~~~

For `jlink`, view the plugins supported by the current JDK:

~~~bash
jlink --list-plugins
~~~

Read the help output of the exact JDK you are running, because options can be added, changed, or deprecated between releases.

## 4. Interactive Exploration and Prototyping: jshell

`jshell` is a REPL (Read-Eval-Print Loop) that lets you enter Java expressions, statements, and declarations without creating a full project.

~~~text
$ jshell
jshell> int x = 7
x ==> 7

jshell> int y = 5
y ==> 5

jshell> System.out.println(x * y)
35

jshell> /exit
~~~

Use `jshell` to try out APIs and small expressions, check how a class or method behaves, demonstrate Java to learners, or quickly prototype a calculation. `jshell` does not replace a project build with dependencies, tests, modules, and production configuration. When testing code that depends on external libraries, provide the appropriate classpath or module path.

Useful REPL commands:

| Command | Purpose |
|---|---|
| /help | View help |
| /vars | List declared variables |
| /methods | List declared methods |
| /types | List declared types |
| /list | List snippets |
| /reset | Clear session state |
| /save file.jsh | Save snippets |
| /open file.jsh | Load snippets |
| /exit | Exit |

## 5. Compiling and Running: javac, java

`javac` compiles Java source code into bytecode in `.class` files. `java` launches the application on the JVM.

### javac

~~~bash
javac -d out src/com/acme/Main.java
~~~

Commonly used options:

| Option | Purpose |
|---|---|
| -d | Output directory for class files |
| -cp or -classpath | Classpath containing dependencies |
| --module-path | Module path |
| --release 17 | Restrict APIs and bytecode to Java 17 |
| -g | Generate debug information |
| -parameters | Retain method parameter names in metadata |
| -Xlint | Enable compiler warnings |
| -Werror | Treat warnings as errors in supported configurations |

`--release` is an important option when compiling for an older Java release than the JDK running the compiler. It combines language rules, class file target version, and the platform APIs of that release. Setting only `-source` and `-target` does not provide the same level of API checking.

### java

Run a class on the classpath:

~~~bash
java -cp out com.acme.Main
~~~

Run an executable JAR with a `Main-Class` manifest attribute:

~~~bash
java -jar app.jar
~~~

Run a modular application:

~~~bash
java --module-path mods -m com.acme.app/com.acme.Main
~~~

Specify runtime options:

~~~bash
java -Xms256m -Xmx1g -jar app.jar
~~~

`-Xms` and `-Xmx` set the initial heap size and maximum heap limit, respectively. These are example settings, not default values suitable for every application.

### Classpath and Module Path

- The classpath locates classes and resources using the traditional class loader mechanism.
- The module path locates named modules and enforces module resolution, readability, exports, and encapsulation.
- An application can combine the module path with the classpath, but you must understand the boundary between named modules and the unnamed module.

Errors such as `ClassNotFoundException`, `NoClassDefFoundError`, `UnsupportedClassVersionError`, and `InaccessibleObjectException` usually require checking versions, the classpath/module path, and actual dependencies.

## 6. Archiving and Inspecting Contents: jar

`jar` creates, lists, updates, and extracts Java Archives. A JAR is based on the ZIP format and typically contains classes, resources, and metadata in `META-INF`.

Create a JAR:

~~~bash
jar --create --file app.jar -C out .
~~~

Create an executable JAR:

~~~bash
jar --create --file app.jar --main-class com.acme.Main -C out .
~~~

List files:

~~~bash
jar --list --file app.jar
~~~

Extract:

~~~bash
jar --extract --file app.jar --dir extracted
~~~

Validate an archive:

~~~bash
jar --validate --file app.jar
~~~

Read a module descriptor:

~~~bash
jar --describe-module --file app.jar
~~~

Use `jar` when you need to inspect an archive, manifest, module descriptor, or resource contents. `jar --validate` checks archive structural issues supported by the tool; it does not run unit tests, verify all dependencies, or prove that the application works correctly.

## 7. Bytecode Analysis: javap

`javap` disassembles class files to inspect bytecode and metadata. It is useful for checking compiler output, APIs, class version, access modifiers, the constant pool, or method invocations.

~~~bash
javap -classpath app.jar com.acme.Main
javap -classpath app.jar -c com.acme.Main
javap -classpath app.jar -verbose com.acme.Main
javap -classpath app.jar -p com.acme.Main
~~~

Combine `javap -verbose` with `UnsupportedClassVersionError` to determine the class file major version. For example, Java 17 uses major version 61. `javap` helps you observe bytecode, but it does not replace tests or a debugger.

## 8. Generating API Documentation: javadoc

`javadoc` generates HTML API documentation from source files and Javadoc comments.

~~~bash
javadoc -d docs/api -sourcepath src -subpackages com.acme
~~~

Javadoc comment:

~~~java
/**
 * Calculates a discount for an order.
 *
 * @param amount original amount in currency units
 * @param percent discount percentage from 0 to 100
 * @return amount after discount
 * @throws IllegalArgumentException if the inputs are invalid
 */
public static double discounted(double amount, double percent) {
    if (amount < 0 || percent < 0 || percent > 100) {
        throw new IllegalArgumentException("Invalid discount");
    }
    return amount * (1.0 - percent / 100.0);
}
~~~

Good API documentation explains contracts, parameters, return values, exceptions, and usage examples. Do not include secrets or internal data in publicly published Javadoc.

## 9. Supporting Tools in the Inspect Group

| Tool | Used for | Example |
|---|---|---|
| serialver | Computing/displaying serialVersionUID for Serializable classes | serialver com.acme.Model |
| jdb | Debugging Java with breakpoints, stepping, and variable inspection | jdb com.acme.Main |
| javap | Inspecting bytecode and metadata | javap -c -verbose com.acme.Main |
| jar | Inspecting archives and manifests | jar --list --file app.jar |
| javadoc | Generating API documentation | javadoc -d docs/api ... |

`serialver` is only useful when the application genuinely uses compatible Java serialization. Do not add `serialVersionUID` to every class if there is no serialization requirement.

`jdb` is a command-line debugger. Remote debugging may require opening a JDWP port; do not expose debug ports on untrusted networks. Prefer local debugging or controlled environments.

## 10. Dependency and Module Analysis: jdeps

`jdeps` analyzes dependencies of classes, packages, JARs, and modules. It helps detect external dependencies, required JDK modules, and references to internal APIs.

~~~bash
jdeps --summary app.jar
jdeps --list-deps app.jar
jdeps --print-module-deps app.jar
jdeps --recursive --verbose:class app.jar
jdeps --missing-deps app.jar
~~~

For applications using multi-release JARs, specify the corresponding release with `--multi-release`. For external dependencies, provide the classpath or module path to avoid inaccurate conclusions.

`jdeps` relies on static analysis. Reflection, `ServiceLoader`, dynamically generated class names, JNI, plugins, and resource loading may not be fully detected. Verify with integration tests and runtime evidence before trimming a module set.

### Deprecated API Checker: jdeprscan

`jdeprscan` scans JARs or class files for usage of APIs deprecated in a given Java release:

~~~bash
jdeprscan --release 17 app.jar
~~~

Use the results to plan JDK upgrades and API replacements. Deprecated does not mean an API has already been removed; read the warnings and migration documentation for the specific API.

### Native API Checker: jnativescan

`jnativescan` scans JARs for usage of native functionality that the tool can identify:

~~~bash
jnativescan --class-path "lib/*" app.jar
~~~

It helps review native access and prepare for native access policies in newer JDKs. Scan results do not prove that all native behavior has been detected; check JNI/JNA, dynamic loading, and actual native dependencies.

## 11. Module Packaging Internals: jmod and jimage

`jmod` creates and lists JMOD files. JMOD is a module archive format used in JDK/module tooling workflows, particularly as input to `jlink`. It is not a standard application format for end users to download and run like a JAR.

~~~bash
jmod describe module.jmod
jmod list module.jmod
jmod create --class-path out --module-version 1.0 module.jmod
~~~

`jimage` inspects the contents of the internal module image file of a JDK or runtime image:

~~~bash
jimage list "$JAVA_HOME/lib/modules"
~~~

`jimage` is useful when investigating modules or resources inside a runtime image. It is not a replacement for `jar` for inspecting regular JAR archives.

## 12. Dependency Map Connected to a Runtime Image

~~~text
Application source + dependencies
             |
             v
       javac / build tool
             |
             v
       JAR / module output
             |
             v
        jdeps analysis
             |
             v
 Review reflection / services / JNI
             |
             v
      jlink --add-modules
             |
             v
     Custom runtime image
             |
             v
        jpackage
             |
             v
 Application image / installer
~~~

Modular app example:

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.acme.app --output build/runtime
~~~

Verify the runtime:

~~~bash
build/runtime/bin/java --version
build/runtime/bin/java --list-modules
build/runtime/bin/java --validate-modules
~~~

Package an app image from the created runtime:

~~~bash
jpackage --type app-image --name MyApp --module-path mods --module com.acme.app/com.acme.Main --runtime-image build/runtime --dest build/packages
~~~

`jlink` creates a custom runtime; `jpackage` creates an application image or native installer. Native packages must be built on the target platform; do not assume `jpackage` supports cross-platform packaging. Runtime images must be rebuilt when JDK security updates require it.

## 13. Security and Artifact Signing: keytool, jarsigner

`keytool` manages keystores, private/public keys, certificate chains, and trusted certificates. It is commonly used to generate key pairs, inspect certificates, import CAs, and manage truststores.

Create a PKCS12 keystore and key pair:

~~~bash
keytool -genkeypair -alias release -keyalg RSA -keysize 3072 -validity 365 -keystore release.p12 -storetype PKCS12
~~~

List entries:

~~~bash
keytool -list -keystore release.p12 -storetype PKCS12
~~~

Print a certificate:

~~~bash
keytool -printcert -file certificate.pem
~~~

Import a certificate:

~~~bash
keytool -importcert -alias company-ca -file company-ca.pem -keystore truststore.p12 -storetype PKCS12
~~~

`jarsigner` signs and verifies JARs:

~~~bash
jarsigner -keystore release.p12 -storetype PKCS12 app.jar release
jarsigner -verify -verbose -certs app.jar
~~~

Order matters: complete shading, resource merging, and manifest edits first, then sign the final artifact. Modifying archive contents after signing can invalidate the signature.

Never commit keystores, private keys, or passwords to a repository. Use a secret manager, HSM, or signing service according to policy. Signatures verify integrity and identity against a certificate chain; you still need to manage trust anchors, certificate expiration, revocation, and private keys.

## 14. Diagnosing a Running JVM: jcmd

`jcmd` sends diagnostic commands to a JVM. It is usually the best starting point when investigating a running process.

List visible JVMs:

~~~bash
jcmd -l
~~~

View commands supported by the JVM:

~~~bash
jcmd <pid> help
~~~

Get version, command line, flags, system properties, and uptime:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> VM.uptime
~~~

Get heap info:

~~~bash
jcmd <pid> GC.heap_info
~~~

Thread dump:

~~~bash
jcmd <pid> Thread.print -l
~~~

Class histogram:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Heap dump:

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Commands do not have the same level of impact. Thread dumps can produce large output; class histograms can take time; heap dumps can cause pauses, trigger a full GC, and produce large files containing sensitive data. Check disk space and impact before running them in production.

`jcmd` typically needs to run on the same host and under the same effective user/group as the JVM. In containers, run it in the appropriate PID namespace and environment. Failing to attach does not necessarily mean the JVM has crashed.

## 15. Flight Recorder: JFR and jfr

Java Flight Recorder (JFR) collects runtime events such as CPU samples, allocations, GC, threads, monitor contention, sockets, and file I/O. JFR is well suited for analyzing behavior over time.

Start a time-bounded recording:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=2m filename=incident.jfr
~~~

View summary:

~~~bash
jfr summary incident.jfr
~~~

Print events:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.CPULoad,jdk.JavaMonitorWait,jdk.SocketRead incident.jfr
~~~

View available views:

~~~bash
jfr view all-views incident.jfr
~~~

You can use JDK Mission Control to analyze recordings through a graphical interface. JMC is a separate analysis tool; check its installation method and version for your environment.

`settings=profile` typically collects more data than `default`; consider duration and overhead. JFR only records events that are enabled and meet their threshold. Not seeing an event in a recording does not prove the event did not occur.

## 16. Monitoring and Process Inspection

| Tool | Purpose | When to use |
|---|---|---|
| jps | Lists instrumented JVMs | Finding Java processes in a local environment |
| jstat | Monitors JVM statistics | Quick periodic checks of GC/heap |
| jconsole | GUI JMX monitoring/management | Inspecting memory, threads, MBeans, and runtime |
| jcmd | Diagnostic commands | Collecting detailed data from a JVM |
| jfr | Reading/displaying Flight Recorder data | Analyzing event timelines |
| jhsdb | Serviceability Agent and postmortem debugging | Low-level investigation of processes/core dumps |

`jstat` example:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

This samples every second, 10 times. Use the right options and read the output headers to understand each column; meanings depend on the subcommand and JDK version.

Launch JConsole:

~~~bash
jconsole
~~~

JConsole connects to a JVM via JMX. Remote JMX requires proper authentication, TLS, and network access configuration; do not expose JVM management ports to public networks.

`jps` only lists JVMs visible to the instrumentation mechanism; it does not replace OS process listings. `jcmd -l` is often more useful when you need a list of JVMs for diagnostic commands.

## 17. Other Diagnostic Tools and Notes

| Tool | Role | Notes |
|---|---|---|
| jstack | Prints Java thread stacks | `jcmd Thread.print` is usually more flexible |
| jmap | Process memory/heap information | `jcmd GC.*` is usually a better starting point |
| jinfo | Process configuration information | `jcmd VM.*` provides corresponding diagnostic commands |
| jhsdb | Low-level analysis of JVM processes/cores | May require elevated privileges and a matching JDK |
| jstatd | Daemon for remote monitoring via jstat | Requires security and network exposure review |
| jdb | Command-line debugger | JDWP ports must be secured |
| jwebserver | Simple HTTP server for static files | For development/testing; does not replace a production web server |

`jstack`, `jmap`, and `jinfo` are still present in the JDK 26 tool reference, but for modern workflows you should prefer the corresponding `jcmd` commands and consult the documentation of your active JDK. Do not run heavy memory dump commands just to collect data "for completeness."

`jwebserver` can start a simple server:

~~~bash
jwebserver --port 8000 --directory public
~~~

Do not use this simple server as a replacement for a reverse proxy, authentication, TLS termination, or a production web server.

## 18. Other Specialized Tools

| Tool | Purpose | Scope |
|---|---|---|
| rmiregistry | Creates an RMI registry | Applications using Java RMI |
| serialver | Displays serialVersionUID | Java serialization |
| javaw | Launches an application without opening a console | Windows |
| kinit, klist, ktab | Manages Kerberos tickets/key tables | Certain platforms, enterprise setups |
| jabswitch, jaccessinspector, jaccesswalker | Java Accessibility Bridge tools | Windows |

Not every JDK vendor or distribution includes every optional tool or module. Some commands are Windows-only; some require additional JDK modules or native dependencies. Always check the tool reference for your exact OS and JDK.

## 19. Tool Selection Map by Question

| Question | Start with | Then if needed |
|---|---|---|
| Source fails to compile? | `javac --release`, `-Xlint` | Check dependencies with `jdeps` |
| Class/JAR fails to run? | `java --version`, `java -cp/-jar` | `jar --list`, `javap -verbose` |
| Which files are in a JAR? | `jar --list` | `jar --extract`, `jar --validate` |
| What is the bytecode target? | `javap -verbose` | Compare with runtime `java --version` |
| Which JDK dependencies are needed? | `jdeps --print-module-deps` | Test reflection/services/JNI |
| Where are deprecated APIs used? | `jdeprscan` | Replace APIs and compile/test on target JDK |
| Need a custom runtime? | `jdeps` | `jlink`, then `java --list-modules` |
| Need an installer? | `jpackage` | Test app image and install on target OS |
| Certificate/trust error? | `keytool -list`, `-printcert` | Check truststore and TLS |
| Need to sign a JAR? | `jarsigner` | `jarsigner -verify` |
| High CPU? | OS process/thread metrics | `jcmd`, JFR, JMC |
| Application hung? | Multiple thread dumps | `jcmd Thread.print -l`, JFR |
| Growing heap/OOM? | `GC.heap_info`, GC logs | Histogram, heap dump, JFR |
| High RSS but stable heap? | OS memory + NMT | Check direct buffers/JNI/native |
| JVM crash? | Fatal error log and OS logs | `jhsdb`, debugger/core dump |

This map is a starting point. Once you have evidence, choose specific commands based on the version, environment, and expected impact.

## 20. End-to-End Example: Using Multiple JDK Tools on a Small Project

This example demonstrates compiling, running, archiving, inspecting, analyzing dependencies, and generating API documentation. The program is compatible with Java 17+.

Structure:

~~~text
jdk-tool-map/
  src/
    com/acme/toolmap/ToolMapDemo.java
  out/
  build/
  docs/
~~~

File `src/com/acme/toolmap/ToolMapDemo.java`:

~~~java
package com.acme.toolmap;

/**
 * Small application used to demonstrate the JDK tool workflow.
 */
public final class ToolMapDemo {

    private ToolMapDemo() {
    }

    /**
     * Starts the demonstration application.
     *
     * @param args command-line arguments (unused)
     */
    public static void main(String[] args) {
        System.out.println(
            "JDK_TOOL_MAP_OK java=" + Runtime.version().feature()
        );
    }
}
~~~

### Compile

~~~bash
javac --release 17 -d out src/com/acme/toolmap/ToolMapDemo.java
~~~

### Run from class directory

~~~bash
java -cp out com.acme.toolmap.ToolMapDemo
~~~

Stdout when running on Java 17:

~~~text
JDK_TOOL_MAP_OK java=17
~~~

On newer JDKs, the number will be the feature version of the running runtime. Thus stdout depends on the selected JDK; on Java 17 specifically, the output above is exact.

### Create executable JAR

~~~bash
jar --create --file build/tool-map-demo.jar --main-class com.acme.toolmap.ToolMapDemo -C out .
~~~

### Run JAR

~~~bash
java -jar build/tool-map-demo.jar
~~~

### Inspect archive

~~~bash
jar --list --file build/tool-map-demo.jar
jar --validate --file build/tool-map-demo.jar
~~~

### Inspect bytecode

~~~bash
javap -classpath build/tool-map-demo.jar -verbose com.acme.toolmap.ToolMapDemo
~~~

### Analyze dependencies

~~~bash
jdeps --summary build/tool-map-demo.jar
jdeps --print-module-deps build/tool-map-demo.jar
~~~

### Generate API docs

~~~bash
javadoc -d docs/api -sourcepath src -subpackages com.acme.toolmap
~~~

These steps produce different forms of evidence: compiler output, runtime output, archive listing, bytecode metadata, dependency reports, and HTML documentation. One successful step does not automatically prove the other steps are all correct.

## 21. CI/CD Workflow Combining Tools into a Pipeline

~~~text
Checkout source
     |
     v
Select pinned JDK + build tool
     |
     v
javac / Maven / Gradle compile
     |
     v
Unit and integration tests
     |
     v
jar / WAR / application package
     |
     v
jar --validate + jdeps + jdeprscan
     |
     v
Smoke test with java
     |
     v
jlink / jpackage if required
     |
     v
keytool / jarsigner / checksum / SBOM
     |
     v
Publish immutable artifact
     |
     v
Deploy same artifact digest
~~~

Not every project needs to run every tool on every build. Choose gates based on artifact type and risk requirements:

- Library: compile, test, jar, javadoc, dependency checks, signing, and metadata publishing.
- CLI/service: compile, test, package, smoke test, dependency scan, and runtime compatibility.
- Modular application: `jdeps`, `jlink`, module validation, and runtime smoke test.
- Desktop installer: `jpackage` per OS/architecture, test installation, and verify native integration.
- Production service: JFR/diagnostic tooling and incident evidence-collection procedures.

Build tools like Maven and Gradle typically orchestrate plugins and test lifecycles; JDK tools are the underlying tools invoked by build tools or scripts. Record exact toolchains and versions for reproducibility.

## 22. Common Errors When Using JDK Tools

| Error | Possible cause | Resolution |
|---|---|---|
| `java` and `javac` have different versions | `PATH`/`JAVA_HOME` point to different JDKs | Check executable paths and versions |
| `javac` cannot find a class | Missing classpath/module path | Check `-cp`, `--module-path`, and dependencies |
| `java -jar` reports missing `Main-Class` | Manifest has no entry point | Recreate JAR with `--main-class` or configure manifest |
| `UnsupportedClassVersionError` | Runtime is older than class file | Use `javap -verbose`, upgrade runtime, or compile with appropriate `--release` |
| `jdeps` reports missing dependencies | Dependency classpath/module path not provided | Pass all dependencies during analysis |
| Runtime image missing modules | Dynamic dependencies not detected statically | Review reflection/`ServiceLoader`/JNI and run integration tests |
| `jpackage` fails to build package | Host OS missing prerequisites or wrong package type | Build on target OS and check tool requirements |
| `jcmd` attach fails | Wrong user, PID namespace, or attach disabled | Run in matching environment/user and read attach error |
| JFR missing expected events | Recording settings/threshold do not enable the event | Choose appropriate settings/events and re-record in a controlled way |
| `jarsigner` verify fails | JAR modified after signing or untrusted certificate | Sign last and verify the certificate chain |

## 23. Safety When Running Tools

Some commands only read files; others attach to processes, create large dumps, open network listeners, or modify artifacts. Assess impact before running them.

- `jcmd GC.heap_dump` can create large files containing sensitive data.
- `jcmd GC.class_histogram` can affect performance depending on heap size and object count.
- JFR `profile` settings have overhead; choose appropriate duration and settings.
- Remote JMX/JDWP requires authentication, encryption, and network restrictions.
- `jwebserver` is not a production web server.
- `keytool` and `jarsigner` involve private keys; protect keystores and passwords.
- Do not expose command lines, system properties, heap dumps, or core dumps containing secrets.
- Do not run write/packaging commands on already-signed release artifacts without a re-release process.

## 24. Checklist for Selecting and Using JDK Tools

- [ ] Identify JDK vendor, full version, OS, and architecture.
- [ ] Confirm the exact executable in `JAVA_HOME/bin` or `PATH`.
- [ ] Read `--help` or the manual for the exact JDK.
- [ ] Understand the command's inputs, outputs, and impact.
- [ ] Distinguish JDK tools from Maven, Gradle, IDEs, and JMC.
- [ ] Choose the tool based on the question and type of evidence needed.
- [ ] Provide the correct classpath/module path when analyzing.
- [ ] Verify artifacts with the appropriate archive, bytecode, and dependency tools.
- [ ] Test runtime images/installers on the target OS.
- [ ] Protect keys, dumps, logs, and configuration details.
- [ ] Record versions, commands, results, and artifact digests in CI.
- [ ] Do not infer overall application quality from a single successful command.

## 25. Key Takeaways

- The JDK is a toolkit for development, packaging, and diagnostics, not just `java` and `javac`.
- `jshell` tests snippets; `javac` compiles; `java` runs applications.
- `jar` creates and inspects archives; `javap` reads bytecode; `javadoc` generates API docs.
- `jdeps` analyzes dependencies; `jdeprscan` finds deprecated APIs; `jnativescan` scans for native access.
- `jmod` manipulates JMOD files; `jimage` inspects internal module images; `jlink` creates custom runtimes.
- `jpackage` builds application images or native installers on the target platform.
- `keytool` manages keys/certificates; `jarsigner` signs and verifies JARs.
- `jcmd` queries the JVM; JFR/`jfr` analyzes events; `jstat`/`jconsole` monitor; `jhsdb` supports postmortem debugging.
- Maven and Gradle are build automation tools outside the JDK.
- Not every tool is available on every OS or JDK distribution.
- Read the manual for the exact version, check inputs/outputs, and assess impact before running.
- Choose commands based on the question to answer, preserve evidence, and confirm results with appropriate tests.

## Official References

- [JDK 26 Tool Specifications — Complete Tool Index](https://docs.oracle.com/en/java/javase/26/docs/specs/man/index.html)
- [The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [The jar Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [The javap Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)
- [The javadoc Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html)
- [The jshell Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jshell.html)
- [The jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The jdeprscan Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html)
- [The jnativescan Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jnativescan.html)
- [The jlink Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jfr Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [The jstat Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jstat.html)
- [The keytool Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html)
- [The jarsigner Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
