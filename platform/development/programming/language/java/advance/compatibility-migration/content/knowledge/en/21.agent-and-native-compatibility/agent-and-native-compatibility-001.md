# ASM, Byte Buddy, and Bytecode Readers Must Support New Class Files

During **Java Advance Compatibility Migration**, an application may compile normally on a new JDK and the JVM itself may load the application's classes, yet Gradle, Maven, coverage tools, mocking, instrumentation, or a Java agent fail with:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
```

Another error can come from Byte Buddy:

```text
Java 21 (65) is not supported by the current version of Byte Buddy
```

The issue is not necessarily in your source code, not necessarily caused by a wrong `JAVA_HOME`, and does not mean Java 21 cannot run the application. **A library analyzing or transforming bytecode is reading a class file formatted for a newer version than that library version understands.**

**ASM** is a low-level toolkit for reading, analyzing, and writing Java class files. **Byte Buddy** is a higher-level library for generating classes, creating proxies, and instrumentation, backed by bytecode parsing components underneath. Tools such as JaCoCo, Mockito, monitoring agents, framework proxies, build plugins, and various compiler/analysis plugins may depend on these libraries directly or indirectly.

This lesson explains class file formats, version compatibility, root-cause layers when upgrading the JDK, identifying which component reads bytecode, upgrading ASM/Byte Buddy properly, and re-testing agents without relying on error-hiding workarounds.

## 1. Distinguishing Three Types of Compatibility

When someone says "a library supports Java 21," ask precisely **what kind of support**:

| Scope | Question | Example |
|---|---|---|
| JVM runtime | Can the JVM load and execute this class file? | JDK 17 cannot load class files compiled for Java 21 |
| Bytecode parser/reader | Can the library parse this class file's structure? | An outdated ASM throws `Unsupported class file major version 65` |
| Bytecode writer/transformer | Can the library emit or transform valid classes for this version? | An agent reads a class yet generates invalid `StackMapTable` or attributes |
| Framework integration | Does the framework version invoke the parser/transformer properly? | Mocking or coverage fails even though source compiles cleanly |
| Tool/process compatibility | Which JVM runs the tool hosting the parser? | A newer Gradle daemon JDK runs a plugin bundling an old ASM |

These are separate contracts. **A new JVM supporting new class files does not mean every ASM/Byte Buddy library inside the same process also supports them.**

### 1.1. Compiling, Loading, and Reading Bytecode Are Three Distinct Operations

Suppose:

```text
javac JDK 21
     |
     v
App.class (major version 65)
     |
     +--> JVM JDK 21: can load matching-version classes
     |
     +--> Old ASM: may fail to parse major 65
     |
     +--> Old Byte Buddy: may reject class file model
     |
     +--> Old JaCoCo agent: may fail to instrument
```

A system may run normally yet break once `-javaagent`, coverage, or inline mocking is enabled. Conversely, builds sometimes fail at the configuration phase because Gradle/Groovy/ASM parses new class files inside a plugin.

### 1.2. Old Bytecode on a New JVM Differs from New Bytecode on an Old JVM

Java maintains strong backward compatibility: newer JVMs generally load class files from older supported Java releases. The reverse does not hold: a Java 17 JVM cannot load Java 21 class files.

A bytecode reader is a separate library with its own support lifecycle. An older parser does not necessarily understand new constant pool tags, attributes, versions, or structures, even when the current JVM understands them.

## 2. Class File Major and Minor Versions

A Java class file is a binary format beginning with the magic number `0xCAFEBABE`, minor version, major version, and tables such as constant pool, fields, methods, and attributes.

Class file header:

```text
u4 magic
u2 minor_version
u2 major_version
u2 constant_pool_count
...
```

**Major version** generally indicates the Java release the class file targets. **Minor version** can carry extra semantics, including preview markers in Java releases with preview features.

### 2.1. Common Major Versions Table

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |

For subsequent releases, consult the class file / JVMS specification for your exact target JDK. Never patch a parser by bumping a single major-version constant and assuming the entire format is supported.

### 2.2. Determining Version from the Error

For example:

```text
Unsupported class file major version 65
```

reports that the class file has major version 65, corresponding to Java 21. It **does not prove the current JVM is Java 21**: the class file may have been compiled by another module, a new dependency, a build plugin, a Java agent, or an annotation processor.

Identify **which class is being read**, from which artifact, by which parser, inside which JVM.

### 2.3. Preview Classes and Minor Version

Class files compiled with preview features carry a special minor version (typically `65535`) and require matching runtime conditions, including `--enable-preview` on the matching release.

Preview bytecode introduces another compatibility axis:

- The JVM must match the exact release with preview features enabled.
- Parsers must understand relevant constructs/formats.
- Transformers must preserve and handle preview metadata accurately.
- Merely editing major/minor bytes does not yield a valid class.

Avoid publishing preview bytecode in broadly distributed libraries unless consumers accept those constraints.

## 3. Distinguishing JVM `UnsupportedClassVersionError` from ASM Errors

Two errors frequently get confused because both mention "class file version."

### 3.1. JVM Fails to Load the Class

Example:

```text
java.lang.UnsupportedClassVersionError:
  com/example/App has been compiled by a more recent
  version of the Java Runtime ...
```

This arises when the JVM is asked to load a class file with a higher major version than it supports. Standard fixes:

1. Run on a sufficiently new JVM.
2. Or recompile the class targeting an older release if sources and dependencies allow.
3. Inspect bytecode across every runtime dependency, not only application classes.

Upgrading ASM will not make JDK 17 execute Java 21 bytecode.

### 3.2. ASM Fails to Read the Class File

Example:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
```

Here, the JVM itself may easily support executing the class; yet an older ASM `ClassReader` rejects the Java 21 class file.

Steps:

1. Identify the exact ASM version being invoked.
2. Identify the library, framework, or plugin bundling that ASM version.
3. Upgrade to an ASM version supporting the target class file release.
4. Test both parsing and bytecode transformation, not just startup.

### 3.3. Byte Buddy Rejects the Java / Class File Version

Byte Buddy maintains its own understanding of Java versions and class file structures. If an outdated Byte Buddy lacks support for the target release, failures appear during proxy generation, class instrumentation, or version resolution.

The fix is upgrading Byte Buddy together with **the owning library** (such as Mockito or an agent), rather than bumping an isolated artifact blindly in the dependency graph.

### 3.4. Errors Looking Like Version Mismatches with Different Causes

Not every `ClassReader` or `ClassFormatError` exception stems from an old parser. A class file may be corrupted, transformed incorrectly, packaged inconsistently, or carry invalid bytecode verifier metadata.

Inspect stack traces, class code sources, artifact checksums, and the failing lifecycle phase before concluding.

## 4. What Is ASM and Where Does It Appear?

ASM is a low-level library capable of:

- Reading class file contents (`ClassReader`).
- Visiting bytecode structures via `ClassVisitor`, `MethodVisitor`, and companion visitors.
- Reading or constructing object trees via the ASM Tree API.
- Emitting and writing bytecode (`ClassWriter`).
- Performing dataflow/stack-frame analysis via the ASM Analysis API.
- Handling metadata, instructions, and attributes supported by that ASM release.

Example reading a class:

```java
import java.io.IOException;
import java.io.InputStream;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.Opcodes;

public final class AsmInspector {
    public static void main(String[] args) throws IOException {
        try (InputStream in =
                AsmInspector.class.getResourceAsStream("/com/example/App.class")) {
            if (in == null) {
                throw new IOException("Không tìm thấy class resource");
            }

            ClassReader reader = new ClassReader(in);

            reader.accept(
                    new ClassVisitor(Opcodes.ASM9) {
                        @Override
                        public void visit(
                                int version,
                                int access,
                                String name,
                                String signature,
                                String superName,
                                String[] interfaces) {
                            System.out.println("Class: " + name);
                            System.out.println("Class file version: " + version);
                        }
                    },
                    ClassReader.SKIP_CODE);
        }
    }
}
```

This illustrates the ASM 9 API. Compiling requires an `org.ow2.asm:asm` dependency. `Opcodes.ASM9` is the **ASM visitor API level**, not a guarantee that every 9.x release understands every future Java release.

### 4.1. Why Must ASM Update When Java Adds Class File Features?

A new Java release can:

- Increment the major version.
- Define new constant pool tags or attributes.
- Change the layout or semantics of existing metadata.
- Introduce new constructs like records, sealed classes, or preview features.
- Add verifier rules or stack-map requirements.

Parsers must know when structures are valid, how to read lengths/layouts, and how to preserve attributes across transformations. Merely skipping the major-version check lets old parsers misread attributes and write broken class files.

### 4.2. `ClassReader.SKIP_CODE` Does Not Bypass Version Checks

Tools needing only annotations or class names often pass `SKIP_CODE`. However, the `ClassReader` constructor already rejects newer class files before any visitor runs.

Thus, skipping method instructions does not prevent `Unsupported class file major version` errors.

### 4.3. ASM Visitor API Level Differs from Max Supported Class File Version

ASM defines constants like `ASM7`, `ASM8`, and `ASM9` representing the visitor API level. Incremental releases within the same ASM major line add support for newer Java class file versions.

Never assume:

```text
Opcodes.ASM9 == Java 9
```

or:

```text
I see ASM9 so it surely supports all Java 9+.
```

Check release notes and test the real parser against class files compiled for the target release.

## 5. What Is Byte Buddy and Why Does It Rely on Bytecode Reading?

Byte Buddy provides a higher-level API than ASM for generating or modifying Java classes, commonly used in:

- Mocking and test instrumentation.
- Runtime proxy generation.
- Java agents for tracing, metrics, profiling, and APM.
- Method interception and advice.
- Class transformation at load time or retransform time.
- Framework code generation.

Illustrative example **creating a class with Byte Buddy**:

```java
import net.bytebuddy.ByteBuddy;
import net.bytebuddy.dynamic.loading.ClassLoadingStrategy;
import static net.bytebuddy.matcher.ElementMatchers.named;
import static net.bytebuddy.implementation.FixedValue.value;

public final class ByteBuddyExample {
    public static class Greeting {
        public String message() {
            return "original";
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> generated = new ByteBuddy()
                .subclass(Greeting.class)
                .method(named("message"))
                .intercept(value("instrumented"))
                .make()
                .load(
                        ByteBuddyExample.class.getClassLoader(),
                        ClassLoadingStrategy.Default.WRAPPER)
                .getLoaded();

        Greeting instance =
                (Greeting) generated.getDeclaredConstructor().newInstance();
        System.out.println(instance.message());
    }
}
```

A Byte Buddy distribution may shade/repackage an internal ASM copy or bundle its own parsing components depending on version and packaging. Thus, the dependency graph for `org.ow2.asm:asm` **does not always reveal the parser Byte Buddy actually uses**.

### 5.1. Upgrading External ASM Does Not Upgrade Shaded ASM Inside Byte Buddy

When Byte Buddy uses a shaded/repackaged ASM copy, merely declaring:

```groovy
implementation 'org.ow2.asm:asm:<new-version>'
```

does not update Byte Buddy's internal parser. Upgrade Byte Buddy itself or the parent library/tool shipping Byte Buddy.

Similarly, a build plugin may embed ASM in its own JAR. Upgrading ASM on your application's runtime classpath rarely changes Gradle or Maven plugin classpaths.

### 5.2. Never Treat Experimental Mode as a Production Solution

Some Byte Buddy versions include an experimental toggle for not-yet-supported Java versions, often configured via properties such as `net.bytebuddy.experimental`. This does not guarantee new bytecode is understood or transformed safely.

For production migrations, choose a release officially published as supporting your target JDK. Limit experimental flags to controlled investigation with strict tests and a real upgrade plan.

### 5.3. Byte Buddy Versions Also Affect Generated Classes and the Verifier

Even if an upgraded version accepts input class files, emitted bytecode must remain valid:

- Stack map frames.
- Method descriptors.
- Access flags and method visibility.
- Nestmate, record, and sealed-class constraints.
- Constructor and override semantics.
- Classloading strategies.
- Runtime package and module access.

Hence, tests must exercise **actual proxy and instrumentation behavior**, not merely check `ClassFileVersion.ofThisVm()` or verify Byte Buddy classes load.

## 6. When Do Java Agents Read and Transform Classes?

A Java instrumentation agent can be attached at startup:

```bash
java -javaagent:monitoring-agent.jar -jar app.jar
```

or attached dynamically where permitted by the runtime environment.

A Java agent normally implements one of two entry points:

```java
public static void premain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst) {
    // Register transformer when the JVM starts.
}
```

or:

```java
public static void agentmain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst) {
    // Entry point for dynamic attach.
}
```

A transformer receives class bytes for inspection or modification before the JVM defines the class (or during supported retransformation calls).

### 6.1. An Agent Can Prevent the Whole Application from Starting

Example:

```text
java -javaagent:old-agent.jar -jar app.jar
```

The agent loads an outdated ASM/Byte Buddy copy, sees a newer class file major version, and throws an exception. When transformers fail or unhandled startup errors abort `premain`, the application may refuse to boot or silently leave target classes uninstrumented.

Temporarily disabling the agent in a controlled test environment isolates the issue:

```text
Without agent: application runs
With old-agent: ClassReader/Byte Buddy error
```

Never adopt "drop the agent permanently" as a default fix when the agent provides mandatory security instrumentation, monitoring, or coverage. Upgrade the agent to a compatible release and verify its function.

### 6.2. `ClassFileTransformer` and Transformation Safety

Skeleton example:

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ExampleAgent {
    public static void premain(
            String agentArgs,
            Instrumentation instrumentation) {

        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                // Example only observes without modifying bytecode.
                // The parser used here must support the new class file version.
                return null;
            }
        });
    }
}
```

Returning `null` signals no class modification in that callback. Whenever a transformer uses ASM/Byte Buddy, the agent's own parser/writer must support actual target class files. Packaging an agent for distribution also requires configuring its JAR manifest and entry points.

### 6.3. Retransformation and Redefinition Differ from Initial Load

Some agents transform classes only on initial load. Others retransform or redefine already-loaded classes. With `Instrumentation`, check:

- Whether the JVM reports `isRetransformClassesSupported()` and related capabilities.
- Whether the transformer registered as retransform-capable.
- JVM schema constraints on redefinition.
- Whether transformations preserve valid bytecode and attributes.
- Whether mutating live classes introduces side effects.

An ASM/Byte Buddy version able to read newer classes is necessary, yet **does not guarantee every redefinition operation is allowed by the JVM**.

### 6.4. Dynamic Agents and Changing Runtime Policies

Newer JDKs introduce warnings or restrictions around dynamic agent loading; JDK 21 warns in dynamic attach scenarios in preparation for stricter defaults later. Verify runtime-specific policies and how your agents attach.

That is **distinct** from parser major-version failures. If attach itself is disallowed, upgrading ASM fixes nothing; if the agent attaches yet the parser throws, changing attach policy is not the root cause.

## 7. Tools That Pull Bytecode Readers Indirectly

A project may declare neither ASM nor Byte Buddy directly while still relying on them:

| Component | Why it reads/writes bytecode | What to inspect |
|---|---|---|
| JaCoCo | Instruments classes for coverage | Does the JaCoCo/agent version support target class files? |
| Mockito inline mock maker | Byte Buddy instrumentation and dynamic generation | Are Mockito and Byte Buddy aligned? |
| Byte Buddy Agent | Attaches and transforms classes | Agent version, runtime policy, parser |
| APM / tracing agents | Instruments JDBC, HTTP, framework classes | Did vendor publish JDK support for this agent release? |
| Spring or framework proxies | Generates/analyzes classes in certain modes | Embedded framework/ASM versions |
| Hibernate enhancement | Build/runtime entity bytecode enhancement | Hibernate enhancer/provider support |
| Gradle/Groovy/Kotlin plugins | Parses class files, metadata, or compiler inputs | Gradle wrapper, plugins, bundled parsers |
| Annotation processors | Reads class metadata or compiler internals | Processor compatibility with compiler JDK |
| Obfuscators / shrinkers | Parses and rewrites classes | Does parser/writer support target class files? |
| Static analyzers | Scans bytecode for rule violations | Tool/plugin release supporting the new JDK |

Not every tool uses ASM or Byte Buddy in every release. Focus on **every intermediary component reading or rewriting class files**, even when ASM is absent from application dependencies.

### 7.1. Coverage Failures Are Very Common

Typical failure:

```text
org.jacoco.agent...:
  Error while instrumenting com/example/App
Caused by: java.lang.IllegalArgumentException:
  Unsupported class file major version 65
```

Tests run when coverage is off. With coverage enabled, an outdated JaCoCo agent encounters major version 65 and fails.

Pick a JaCoCo version supporting the target Java release and check build-tool plugin integration. Never downgrade `targetCompatibility` to Java 17 solely to appease coverage when the project requires Java 21.

### 7.2. Mockito Inline Fails Even When Unit Tests Compile

Mockito creates mocks via subclassing or inline instrumentation depending on version and settings. When a mock maker relies on a Byte Buddy release lacking support for the new Java version, `Mockito.mock(...)` fails while compilation and non-mock tests pass.

Inspect nested causes for Byte Buddy/ASM references, then upgrade Mockito and companion dependencies together. Avoid pinning arbitrary Byte Buddy versions without confirming compatibility with your Mockito release.

### 7.3. Frameworks and Build Plugins Have Separate Classloaders

Gradle plugins run inside the Gradle daemon and do not necessarily share the project's `implementation` or `runtimeClasspath`. Hence:

```groovy
dependencies {
    implementation 'org.ow2.asm:asm:...'
}
```

is unlikely to override the ASM copy inside a build plugin. Upgrade the plugin or Gradle wrapper, or adjust build-logic dependencies at the plugin layer.

In Maven, plugin dependencies run in isolated class realms too. Updating `<dependencies>` on the application POM does not swap ASM bundled inside a Maven plugin.

## 8. Maven: Locating ASM/Byte Buddy in the Dependency Graph

### 8.1. Application Dependencies

Run:

```bash
mvn dependency:tree
```

Locate ASM:

```bash
mvn dependency:tree -Dincludes=org.ow2.asm:asm
```

Locate Byte Buddy:

```bash
mvn dependency:tree -Dincludes=net.bytebuddy:byte-buddy
```

These identify dependency paths and resolved versions in the project. To inspect companion ASM artifacts (`asm-commons`, `asm-tree`, `asm-analysis`), query those artifacts explicitly or inspect the full tree.

### 8.2. Maven Plugin Dependencies Live Elsewhere

If an error happens inside a plugin goal, check the plugin version and plugin dependencies. The application's runtime dependency tree may omit the ASM version held by the plugin.

A Maven build using a newer compiler plugin alongside an old bytecode-analysis plugin can pass compilation and fail afterward. Upgrade the **failing plugin**, not merely the application BOM.

### 8.3. Centralized Version Management

If the application directly depends on ASM or Byte Buddy, use `dependencyManagement` or a BOM/platform to align versions. Keep in mind:

- Bumping `asm` never automatically updates libraries containing **shaded ASM**.
- All ASM modules (`asm`, `asm-tree`, `asm-commons`) should match the same release; never mix generations.
- Never force-override transitive dependencies without verifying framework/agent compatibility.
- After resolution, inspect **the final packaged artifact**.

## 9. Gradle: Finding Parsers in the Right Configuration

### 9.1. Inspecting Resolved Dependencies

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Locate ASM:

```bash
./gradlew dependencyInsight \
  --dependency asm \
  --configuration runtimeClasspath
```

Locate Byte Buddy:

```bash
./gradlew dependencyInsight \
  --dependency byte-buddy \
  --configuration testRuntimeClasspath
```

When errors hit test mocking, `testRuntimeClasspath` matters more than `runtimeClasspath`. When errors hit a Gradle plugin at configuration time, application classpaths won't show the plugin's parser.

### 9.2. Keep Build and Test Layers Distinct

A build may mix versions across layers:

```text
Gradle daemon JVM: JDK 17
JavaCompile toolchain: JDK 21
options.release: 21
Test JVM: JDK 21
JaCoCo agent: old version, parser does not support major 65
```

Here, `./gradlew --version` identifies only Gradle's own JVM, not the `JavaCompile` toolchain or JaCoCo's parser.

Upgrading the Gradle wrapper may be required so the build engine supports newer Java versions, yet **does not automatically upgrade JaCoCo, Mockito, or build plugins**.

### 9.3. Toolchain and JaCoCo Configuration Example

Illustrative Groovy DSL showing placement:

```groovy
plugins {
    id 'java'
    id 'jacoco'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}

jacoco {
    // Choose a version published as supporting the target JDK's class files.
    toolVersion = providers.gradleProperty('jacocoVersion').get()
}
```

Here `jacocoVersion` is a project property managed under your dependency policy rather than hardcoding an aging literal. Verify Gradle/JaCoCo compatibility and JDK 21 support before picking the version.

When targeting a JDK other than 21, adjust the values accordingly and ensure the Gradle wrapper supports that compiler toolchain.

### 9.4. Never Force the Entire Graph Before Knowing the Source

A hasty override:

```groovy
resolutionStrategy.force 'org.ow2.asm:asm:<version>'
```

will not touch shaded ASM, will not touch parsers inside Gradle plugin classloaders, and can leave companion ASM modules mismatched.

Prefer dependency constraints/platforms and upgrading the owning component once you pinpoint the faulty artifact.

## 10. Shaded ASM and Multiple Parsers in One Application

Shading packages and relocates a dependency's classes into an internal namespace. One process might load simultaneously:

```text
org.objectweb.asm.ClassReader
net.bytebuddy.jar.asm.ClassReader
vendor.agent.internal.asm.ClassReader
```

These illustrate scenarios where **multiple libraries ship private parser copies**; exact namespaces vary by vendor and version.

If the stack trace points to:

```text
vendor.agent.internal.asm.ClassReader
```

upgrading `org.ow2.asm:asm` on the application classpath will not replace that parser.

### 10.1. Identifying Ownership

Inspect:

- Stack trace package names across parsers, frameworks, and agents.
- Which JAR holds that class.
- Manifest and implementation version metadata.
- Dependency graphs for that exact process/classloader.
- Actual deployed APM, coverage, or mock agent artifacts.

For loaded classes, print code source details where permitted:

```java
Class<?> type = org.objectweb.asm.ClassReader.class;

System.out.println(type.getClassLoader());
System.out.println(
        type.getProtectionDomain().getCodeSource() == null
                ? "<no code source>"
                : type.getProtectionDomain().getCodeSource().getLocation());
```

`CodeSource` may be null or indirect under custom classloaders, so combine this with class-loading logs and archive inspection.

### 10.2. Avoid "Pinning an Old ASM Because One Feature Uses It"

If plugins/frameworks share one process, forcing an old ASM version breaks components reading newer bytecode. Conversely, forcing ASM far ahead of an older framework can trigger API incompatibilities if internals changed.

Prefer framework/plugin releases officially supporting your target JDK and let the framework coordinate tested dependencies.

## 11. Reading Class File Versions Without Relying on ASM

When an old ASM throws on new classes, read major/minor versions directly from the first eight bytes of a `.class` file using pure Java SE:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassVersionReader {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ClassVersionReader <path-to-class>");
        }

        try (DataInputStream in =
                new DataInputStream(Files.newInputStream(Path.of(args[0])))) {

            int magic = in.readInt();
            if (magic != 0xCAFEBABE) {
                throw new IOException("Not a Java class file");
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();

            System.out.println("major = " + major);
            System.out.println("minor = " + minor);
        }
    }
}
```

Compile and run:

```bash
javac ClassVersionReader.java
java ClassVersionReader build/classes/java/main/com/example/App.class
```

This technique **reads only the header**; it neither validates the rest of the class file nor guarantees ASM/Byte Buddy can transform it.

### 11.1. Using `javap`

The JDK ships `javap` to inspect class files:

```bash
javap -verbose \
  -classpath build/classes/java/main \
  com.example.App
```

Look for:

```text
major version: 65
```

Use `javap` from a sufficiently recent JDK. If the `javap` on `PATH` belongs to an older JDK than the class file, `javap` itself can fail; check which JDK provides `javap`.

### 11.2. Inspecting Classes Inside Dependency JARs

A dependency JAR may contain newer class files than the rest of the app. First list contents:

```bash
jar tf lib/example-library.jar
```

Then run `javap -classpath lib/example-library.jar -verbose <ClassName>` on target classes.

For multi-release JARs, watch for versioned entries under:

```text
META-INF/versions/11/...
META-INF/versions/17/...
META-INF/versions/21/...
```

Versioned entries are not duplicate-class bugs. JVMs and tools select classes per the `Multi-Release` manifest attribute, so **readers and transformers must understand or be configured for MR-JARs**. Scanning every entry blindly and faulting on the highest version leads to false diagnostics.

## 12. Errors Can Still Happen Even When Source Target Is Lowered

Suppose your build sets:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

yet still throws:

```text
Unsupported class file major version 65
```

Possible causes include:

1. A project dependency contains Java 21 bytecode.
2. Test classes compile under a different setting than main sources.
3. A build plugin or compiled Gradle script targets Java 21.
4. A plugin scans the entire JDK runtime or dependencies instead of only main outputs.
5. A multi-release JAR includes Java 21 entries.
6. Classes generated by an annotation processor or code generator use another config.
7. An agent instruments JDK/framework classes compiled at newer major versions.
8. Stale files remain in build outputs or incremental caches.

Therefore, **never assume the project's compiler target bounds every class encountered by parsers**. Pinpoint the exact class failing to parse and its owning artifact.

### 12.1. `--release` Does Not Downgrade Dependency Bytecode

`--release 17` controls Java language/API targets and output bytecode for sources compiled by that task. It never converts a dependency JAR built for Java 21 into a Java 17 JAR.

If a dependency requires Java 21, a Java 17 application needs an older compatible version, a backport build, or a raised runtime baseline.

### 12.2. Gradle/Maven Plugins Have Separate Classpaths

`JavaCompile.options.release` does not touch Gradle plugin class files loaded inside the daemon. Similarly, Maven Compiler Plugin `<release>` does not downgrade dependencies of other Maven plugins.

Determine whether the failure hits during **configuration**, **compile**, **test instrumentation**, **packaging**, or **application runtime** before touching target settings.

## 13. Test Matrix When Upgrading JDKs

A compatibility test suite should exercise every class-file processing path:

| Test Path | Goal | Success Signal |
|---|---|---|
| Source compile | Aligned compiler and language target | Expected class files produced |
| Load classes on target JVM | JVM supports major/minor versions and deps | Zero `UnsupportedClassVersionError` |
| ASM parse | Reader understands new class files | `ClassReader` and visitors finish representative inputs |
| Byte Buddy proxy | Generates and loads valid subclasses | Proxies instantiate and execute cleanly |
| Byte Buddy agent | Transformer compatible with target classes | Load/retransform works with intact behavior |
| JaCoCo coverage | Agent instruments new classes | Tests pass and coverage reports generate |
| Mockito inline | Mock maker uses compatible parser | Mocks and verifications pass |
| Framework enhancement | ORM/proxy/AOP processes new classes | Real integration tests pass |
| Multi-release JAR | Picks version matching runtime | Runtime and parsers resolve right class |
| Production startup | Final agent, plugins, and launcher | Zero linkage/transform errors |
| Functional verification | Transformed bytecode preserves semantics | Business outputs remain accurate, not just exception-free |

You need not enable unused tools, yet must verify every component active in your build or runtime.

### 13.1. Building a Synthetic Probe Class for Parsers

To catch parser incompatibilities early, compile a probe JAR on the target JDK and pass it through your ASM/Byte Buddy/agent tooling. Include representative Java features rather than an empty class:

- Plain classes, interfaces, and generic signatures.
- Records and sealed classes if used by the project.
- Lambdas, `invokedynamic`, and method references.
- Annotations and framework-read metadata.
- Nested and inner classes.
- Preview features if enabled in the project.
- Agent-instrumented classes.
- Multi-release JARs if present in dependencies.

Parsing an empty class proves nothing about handling newer bytecode features cleanly.

## 14. Symptoms and Root-Cause Routing

| Symptom | Common Phase | Investigation |
|---|---|---|
| `Unsupported class file major version 65` in `org.objectweb.asm.ClassReader` | Build/plugin/agent parser | Upgrade component supplying ASM, not just the JVM |
| Byte Buddy reports unsupported Java release | Mocking/proxy/agent | Upgrade Byte Buddy and owning library |
| `UnsupportedClassVersionError` | JVM class loading | Upgrade runtime JVM or lower target/dependency bytecode |
| `ClassFormatError` | Class loader/verifier | Inspect transform output and class file validity |
| `VerifyError` | JVM verifier | Check stack frames, writer/transformer, target version |
| Fails with coverage enabled, passes without | JaCoCo/test instrumentation | Upgrade JaCoCo/agent and check instrumented classes |
| Gradle plugin fails evaluating build script | Gradle daemon/plugin | Check wrapper/plugin compatibility and bundled parser |
| Mockito fails inside `mock()` | Inline/subclass mock maker | Check Byte Buddy version and test JVM |
| Agent works on old JDK, fails on new JDK | Runtime instrumentation | Check agent release, JDK support, module/attach policy |
| `InaccessibleObjectException` | JPMS reflection | Check `opens`/`exports`; do not confuse with bytecode version |
| `NoSuchMethodError` inside ASM/Byte Buddy | Dependency ABI mismatch | Resolve version/classpath conflicts, not just major class version |

Always inspect full stack traces rather than short CI error summaries.

## 15. Practical Migration Workflow

### Step 1 — Inventory Every Component Reading or Writing Bytecode

Catalog ASM, Byte Buddy, JaCoCo, Mockito, APM agents, Hibernate enhancers, annotation processors, Gradle/Maven plugins, obfuscators, and proxy generators.

Record modules and execution phases:

```text
Gradle daemon:  plugin A -> ASM embedded
JavaCompile:    annotation processor B
Test JVM:       Mockito -> Byte Buddy
Test JVM:       JaCoCo agent
Application:    monitoring-agent.jar
Runtime:        framework proxy/enhancer
```

### Step 2 — Record Runtime and Compiler Targets

Capture:

- Vendor and full release of build/daemon JDK.
- Compiler toolchain JDK and `--release`.
- Test worker JDKs.
- Production/container JDK.
- Major/minor version of the failing class.
- Parser/transformer library versions where identifiable.

### Step 3 — Pinpoint the Exact Failing Class File

From stack traces, locate the class being parsed or instrumented. Use `javap -verbose` or raw header inspection to read major/minor versions. If it belongs to a dependency, identify the resolved artifact and version.

### Step 4 — Identify Who Owns the Parser

If stack traces show `org.objectweb.asm.ClassReader`, check the ASM version on that exact classloader. If it shows Byte Buddy, JaCoCo, or a plugin bundling shaded ASM, locate the owning component.

Never rely solely on the application runtime dependency tree when the error originates inside a plugin classloader.

### Step 5 — Select Officially Supported Versions

Upgrade:

- Gradle wrapper and plugins if the build engine or plugins lack support for the new JDK.
- ASM modules when the application owns ASM directly.
- Byte Buddy alongside Mockito, frameworks, or agents that bundle/manage it.
- JaCoCo agent/plugin if coverage fails.
- Vendor APM/monitoring agents if production instrumentation fails.

**Never hardcode a single static version table across all JDKs** without verifying release notes and artifacts. Class-file support can land in minor updates while JDK releases advance continuously.

### Step 6 — Align Dependencies and Eliminate Stale Copies

Verify both dependency graphs and packaged deployment artifacts. When a JAR bundles shaded parsers, upgrade the owning agent/plugin directly rather than merely adding a newer ASM jar alongside it.

Where multiple unshaded ASM jars appear in one classloader, resolve conflicts and keep all companion ASM modules aligned on one version.

### Step 7 — Test Parsing, Instrumentation, and Behavior

Exercise every path invoking bytecode tools:

- Build and compilation tasks.
- Mocked unit tests.
- Coverage instrumentation.
- Framework proxies and entity enhancement.
- Agent startup and runtime hooks.
- Reflection and JPMS modules where applicable.
- Preview classes and MR-JARs if used.

Printing `--version` does not substitute for feeding real compiled class files through parsers and transformers.

### Step 8 — Inspect Final Artifacts and Roll Out

Ensure CI and production run identical agent/plugin versions as local environments. Record agent/JAR checksums, JDK vendor/updates, and verified versions.

For mandatory agents, also confirm monitoring coverage or policy enforcement after upgrading: an agent that "does not crash" by silently skipping instrumentation is still a functional failure.

## 16. End-to-End Example: Upgrading from Java 17 to Java 21

Suppose a system looks like:

```text
Application: Java 17, Spring-based services
Build: Gradle
Testing: JUnit + Mockito + JaCoCo
Production: OpenTelemetry/APM Java agent
Target: Java 21
```

After upgrading the compiler toolchain to 21, tests fail with:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
```

A structured resolution workflow:

1. Verify the offending class carries major version 65 using `javap`.
2. Read the stack trace to determine whether JaCoCo, Mockito, a Gradle plugin, or an agent owns the parser.
3. If coverage failed: check JaCoCo version and upgrade to a release supporting Java 21 class files.
4. If `Mockito.mock` failed: check Mockito/Byte Buddy compatibility and upgrade both cleanly.
5. If build configuration failed: inspect the Gradle wrapper and plugin parsers rather than only application dependencies.
6. If production failed only with the agent attached: select an agent release published with Java 21 support.
7. Verify `runtimeClasspath`, `testRuntimeClasspath`, plugin classpaths, and final packaged JARs.
8. Re-run tests, proxies, coverage, agent startup, and instrumented execution paths.
9. Pin verified versions in CI and add regression gates for future JDK upgrades.

Never "fix" this by lowering `targetCompatibility` to Java 17 when the application genuinely targets Java 21 features. If Java 17 runtimes must still be supported, adopt an explicit release-target and dependency policy instead.

## 17. Why You Must Never Edit Major Version Bytes Manually in `.class` Files

A dangerous idea is hex-editing a binary class file to change major version 65 down to 61 so older parsers accept it.

This is unsafe because:

- Class files may hold attributes or constant pool entries undefined in older versions.
- The JVM verifier enforces rules coupled to class file version.
- Instructions, descriptors, or metadata may be invalid under older semantics.
- Bytecode may invoke Java APIs available only on the newer runtime.
- Outdated parsers may misparse structures and write corrupted classes back out.
- Mutating built binaries breaks artifact provenance and code signing.

**Never patch class version bytes manually to "fake compatibility."** To run on an older runtime, recompile with a compatible toolchain/`--release` and verify all dependencies; to let parsers read new classes, upgrade the parsers.

## 18. When Is Uninstrumented Fallback Acceptable?

In controlled diagnostics, temporarily disabling agents or coverage in test runs isolates root causes. Treat fallbacks according to policy:

- **Coverage agents:** disabling coverage reveals whether functional tests pass, yet pipelines must still block releases requiring coverage.
- **Mocking/instrumentation:** changing mock makers alters test semantics; verify appropriateness carefully.
- **APM/tracing agents:** running agent-free during local diagnosis is fine, never in production where telemetry is mandatory.
- **Security agents:** disabling security agents removes active controls; never treat disabling them as an operational workaround.

Once the parser/agent mismatch is confirmed, upgrade to supported versions and restore full testing and observability pipelines.

## 19. Pre-Upgrade Checklist

- [ ] Identified target Java release and matching class file major/minor versions.
- [ ] Distinguished JVM `UnsupportedClassVersionError` from ASM `Unsupported class file major version`.
- [ ] Located the exact parser in the stack trace and its owning artifact.
- [ ] Audited both direct and shaded ASM/Byte Buddy copies.
- [ ] Audited JaCoCo, Mockito, tracing/APM, and other Java agents.
- [ ] Audited Gradle/Maven plugin classpaths separately from application classpaths.
- [ ] Confirmed Gradle wrapper / daemon JDK compatibility with the compiler JDK.
- [ ] Checked `--release`, test JVMs, and production runtimes rather than `JAVA_HOME` alone.
- [ ] Audited dependency class files and multi-release JAR entries.
- [ ] Evaluated preview feature usage and special minor versions if applicable.
- [ ] Selected library versions officially documented as supporting the target JDK.
- [ ] Tested parsers, writers, proxies, and transformations on representative bytecode.
- [ ] Tested coverage, mocking, and agents before and after startup.
- [ ] Confirmed instrumentation is active rather than silently skipped.
- [ ] Checked reflection/JPMS compatibility and dynamic attach policies where relevant.
- [ ] Pinned versions, artifact checksums, and runtime images in CI/CD.
- [ ] Avoided manual major-byte edits or experimental flags as production solutions.
- [ ] Documented owners and upgrade paths for future JDK releases.

## 20. Conclusion

A new Java release updates more than compilers and JVMs; it can advance the class file format that the entire tooling ecosystem reads. A JVM supporting new class files does not guarantee outdated ASM, Byte Buddy, JaCoCo, Mockito, build plugins, or Java agents can parse and transform that bytecode. "Unsupported class file major version" errors are therefore **signals of parser/transformer incompatibility**, not necessarily broken Java source code.

In Java Advance Compatibility Migration, inspect class file major/minor versions, identify the exact parser invoked, upgrade the owning tooling to officially supported releases, align dependencies, and verify instrumentation, proxies, coverage, and runtime execution end-to-end. Separating **Gradle/build JDKs**, **compiler toolchains**, **JVM classloading**, and **bytecode readers** pinpoints the true root cause instead of randomly swapping JDKs or downgrading targets.
