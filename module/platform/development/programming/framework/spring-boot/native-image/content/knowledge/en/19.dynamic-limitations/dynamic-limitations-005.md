# Java Agents and Instrumentation: Version-by-Version Support Lookup

Java agents and instrumentation are commonly used to observe or modify bytecode while an application runs. APM tools, profilers, coverage tools, mocking libraries, and some frameworks may use `java.lang.instrument`, `ClassFileTransformer`, the Attach API, or the JVM Tool Interface (JVMTI). When migrating Spring Boot to GraalVM Native Image, you cannot assume tools that work on the JVM will continue working in a native executable.

The key is to distinguish three mechanisms: **JVM Java agents**, the **Native Image Tracing Agent used to collect reachability metadata**, and **GraalVM Native Image runtime class loading**. Each has a different goal and scope of support. This lesson explains how to check support by JDK/GraalVM version, identify each mechanism's limitations, and choose an appropriate testing approach for native Spring Boot applications.

## 1. What Are Java Agents and Instrumentation?

A Java agent is a component loaded by the JVM to observe or transform class bytecode. Agents typically implement one of two entry points:

- `premain(...)`: invoked by the JVM when the agent is loaded at startup via `-javaagent`.
- `agentmain(...)`: invoked by the JVM when the agent is loaded into a running JVM, if the implementation supports dynamic attach.

The `java.lang.instrument.Instrumentation` API allows an agent to register a `ClassFileTransformer`, query instrumentation capabilities, and in some cases redefine/retransform already-loaded classes.

An agent typically contains these components:

~~~text
audit-agent.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/agent/
    └── AuditAgent.class
~~~

Minimal manifest for an agent loaded at JVM startup:

~~~text
Premain-Class: com.example.agent.AuditAgent
Can-Retransform-Classes: false
~~~

Example of a simple agent logging application class names as the JVM loads them:

~~~java
package com.example.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class AuditAgent {

    public static void premain(
            String agentArgs,
            Instrumentation instrumentation) {

        instrumentation.addTransformer(
                new ClassFileTransformer() {
                    @Override
                    public byte[] transform(
                            Module module,
                            ClassLoader loader,
                            String className,
                            Class<?> classBeingRedefined,
                            ProtectionDomain protectionDomain,
                            byte[] classfileBuffer) {

                        if (className != null
                                && className.startsWith("com/example/")) {
                            System.out.println("Loading: " + className);
                        }

                        // null means do not modify bytecode.
                        return null;
                    }
                },
                false
        );
    }
}
~~~

Compile the agent with a compatible JDK, package the JAR with the manifest above, and run the JVM application:

~~~bash
java -javaagent:target/audit-agent.jar -jar target/application.jar
~~~

The JVM loads the agent and calls `premain` before calling the application's `main`. If the agent fails to start or `premain` throws an uncaught exception, the JVM may terminate before the application begins.

The example agent only logs; it does not transform bytecode. A real agent may use libraries like Byte Buddy or ASM to generate new bytecode, in which case you must also check compatibility across the library, JDK, and runtime environment.

## 2. Distinguishing Mechanisms Commonly Called "Agents"

The names look similar, but the options below are not interchangeable:

| Mechanism | How Loaded | Goal | Where Typically Used |
| --- | --- | --- | --- |
| Java agent | `-javaagent:agent.jar` | Calls `premain`, provides `Instrumentation` to transform classes | JVM at startup |
| Dynamic Java agent | Attach API, `jcmd`, or equivalent tools | Calls `agentmain` inside a running JVM | JVM after startup |
| Native/JVM TI agent | `-agentlib:lib` or `-agentpath:path` | Loads a native library implementing JVMTI | JVMs supporting JVMTI |
| Native Image Tracing Agent | `-agentlib:native-image-agent=...` | Observes dynamic accesses on the JVM and generates Native Image metadata | JVM during configuration collection |
| Native Image runtime class loading | `-H:+RuntimeClassLoading` at build time | Allows certain class loaders to define classes from bytecode while the native executable runs | Native Image from GraalVM 25.1 onward, experimental |

In particular, `native-image-agent` **is not a Java agent an application attaches to instrument the native executable itself**. It is a GraalVM tool that runs on a regular JVM to observe dynamic accesses such as reflection, resources, JNI, and dynamic proxies, then generates metadata for the native build process.

Similarly, `-H:+RuntimeClassLoading` only enables defining classes from bytecode at runtime. It does not create a full JVM inside the native executable and does not supply `Instrumentation`, `ClassFileTransformer`, the Attach API, or JVMTI.

## 3. Java Instrumentation on the JDK: Version-by-Version Lookup

`java.lang.instrument` belongs to the Java SE platform. However, whether an implementation provides agent startup or dynamic attach also depends on the specific JVM. When checking, separate two questions:

1. Does the JDK/JVM support loading agents via `-javaagent` at startup?
2. Does the JVM allow the Attach API to load agents into a running process, and what is that version's default policy?

### Notable Milestone: JDK 21

Starting in JDK 21, HotSpot emits a warning when a Java agent or JVM TI agent is loaded dynamically into a running JVM. This change comes from JEP 451 in preparation for an integrity-by-default policy. Loading an agent at startup with `-javaagent` or `-agentlib` does not trigger this warning.

On HotSpot, `-XX:+EnableDynamicAgentLoading` explicitly opts in to dynamic agent loading and suppresses the warning. You can use `-XX:-EnableDynamicAgentLoading` to test whether an application or library relies on dynamic attach.

### JDK Lookup Table

| JDK Version | Startup Agent | Dynamic Attach | What to Verify |
| --- | --- | --- | --- |
| JDK 8–20 | HotSpot supports `-javaagent` and `-agentlib` | Usable if the JVM implementation supports the Attach API | Check vendor, Attach API, OS permissions, and agent manifest |
| JDK 21–25 | `-javaagent` at startup remains supported on HotSpot | HotSpot warns on dynamic load; `-XX:+EnableDynamicAgentLoading` is opt-in | Check warnings, flags, and JDK vendor guidance |
| JDK 26 or newer releases | Do not infer from version number alone | Policy may change by JEP/release and vendor | Read Javadoc, release notes, and run smoke tests on the exact JDK |

This table outlines HotSpot policy milestones to guide lookup; it does not replace a specific distribution's documentation. The Java SE specification describes dynamic attach as implementation-specific, so do not assume every JVM behaves identically.

### How to Detect Dynamically Loaded Agents

If a JVM application prints warnings similar to:

~~~text
WARNING: A Java agent has been loaded dynamically
WARNING: Dynamic loading of agents will be disallowed by default in a future release
~~~

Identify which library invokes the Attach API. On HotSpot, you can test with:

~~~bash
java -XX:-EnableDynamicAgentLoading -jar target/application.jar
~~~

If the application or tests fail, a dependency may be loading an agent dynamically. `-Djdk.instrument.traceUsage` helps trace usage of the instrumentation API in scenarios supported by the JDK.

Prefer configuring agents upfront at JVM startup with `-javaagent` if the environment truly needs an agent. Use `-XX:+EnableDynamicAgentLoading` once you have confirmed dynamic attach is needed and accept the opt-in; do not add the flag just to silence the warning without identifying the agent source.

## 4. Limitations of Java Agents in GraalVM Native Image

Native Image uses static analysis and a closed-world model to produce a native executable. Bytecode is no longer loaded and executed by a JVM in the usual way at runtime. Consequently, tools relying on observing or transforming bytecode inside a running JVM cannot work by default in a native executable.

According to the current Native Image Compatibility Guide, **JVMTI and bytecode-based tools are not supported in the Native Image runtime**. This directly affects the following mechanisms:

- `-javaagent` used to load an agent and obtain `Instrumentation`.
- `ClassFileTransformer` for transforming classes on load/retransform.
- Redefining/retransforming loaded classes via Java Instrumentation.
- The Attach API and tools relying on attaching agents to a running process.
- JVMTI agents loaded via `-agentlib` or `-agentpath`.
- Profilers, debuggers, or coverage tools depending on JVM bytecode and JVMTI.

Do not pass `-javaagent:...` to a native executable command expecting it to work like `java -jar`. A native executable is not a HotSpot JVM packaged differently.

### How Does This Affect Spring Boot?

A Spring Boot application running on the JVM might have an APM agent, coverage agent, or library Java agent attached. When moving to native:

- A JVM agent does not automatically become part of the native executable.
- Spring AOT generating context-initialization code does not recreate runtime bytecode transformation capabilities.
- Native Image may need reachability metadata for dynamic accesses, but metadata is not equivalent to instrumentation.
- A library generating proxies or dynamic classes must be evaluated separately: class generation may have options depending on the GraalVM version, but that does not mean agents redefining classes are supported.

Therefore, inspect the **actual mechanism the library uses**, rather than looking only at the library name or old JVM command lines.

## 5. Native Image Tracing Agent: Metadata Collector, Not a Runtime Agent

GraalVM provides the Native Image Tracing Agent to run the application on a JVM and record dynamic accesses that static analysis may not infer automatically, such as:

- Reflection: looking up classes, constructors, methods, or fields.
- Dynamic proxies: creating interface proxies.
- JNI: accessing types/members from native code.
- Classpath resources and resource bundles.
- Certain forms of dynamically defined classes, via version-specific experimental options.

Run a Spring Boot JAR on a GraalVM JDK with the tracing agent:

~~~bash
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config/ \
  -jar target/application.jar
~~~

On Windows, use `java.exe` from the GraalVM JDK and adjust paths for the OS. The `-agentlib` option must appear before `-jar`, the main class name, or application arguments.

After the application exits, the agent writes metadata to the configuration directory. You can run multiple times across different business flows to increase coverage:

~~~bash
# First run generates the metadata set.
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config/ \
  -jar target/application.jar

# Subsequent runs append metadata to the existing set.
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=config-merge-dir=target/native-agent-config/ \
  -jar target/application.jar
~~~

Run scenarios that exercise dynamic access paths: login, request handling, config reading, serialization, plugin invocation, proxy creation, and error branches. The agent only observes what actually runs; it does not prove every branch of the application was captured.

### Reviewing Metadata Before Building

Do not ship the entire output to production without reviewing it. Do the following:

1. Identify which classes/members/resources were added.
2. Check for extraneous metadata from test frameworks, devtools, or libraries not needed in production.
3. Compare across multiple runs to spot gaps.
4. Verify class, member, and resource names match current source/dependencies.
5. Place the reviewed metadata where the Native Image build reads it.

In newer GraalVM versions, unified metadata may reside in `reachability-metadata.json` under `META-INF/native-image/`. Older releases may produce multiple files such as `reflect-config.json`, `resource-config.json`, `proxy-config.json`, `jni-config.json`, or `serialization-config.json`. Inspect the actual output and schema of your exact GraalVM version rather than mechanically renaming files according to outdated guides.

## 6. Changes Across GraalVM Versions: Metadata and Dynamic Class Loading

GraalVM evolves its metadata formats and gradually expands compatibility. Check your exact release line, especially when the native build plugin is upgraded independently of the JDK.

| GraalVM Native Image | Metadata Tracing | Runtime Dynamic Class Loading | Java Agent/JVMTI in Native Runtime |
| --- | --- | --- | --- |
| 22.x | Typically separate metadata files by category; check specific release docs | No new runtime class loading feature like 25.1; some versions have experimental predefined-class support | JVMTI and bytecode tools are unsupported |
| 23.x | Shifted toward `reachability-metadata.json`; older separate files deprecated yet still accepted | Do not infer general runtime class loading from metadata format changes | Unsupported |
| 24.x | Uses `reachability-metadata.json` and release schema; some missing-registration diagnostic options available | Still check dynamic class loading limits per release; predefined classes remain a separate experimental path | Unsupported |
| 25.0 LTS | Uses unified reachability metadata; check schema and agent options for 25.0 | Not identical to new features announced in 25.1 | Unsupported |
| 25.1 onward | Tracing agent and reachability metadata continue to be updated | Has early/experimental runtime class loading via `-H:+RuntimeClassLoading` | Still does not mean Java Instrumentation or JVMTI is supported |

This table is a reference guide, not a certification matrix for every patch, platform, and distribution. GraalVM has LTS lines and feature/innovation releases; a feature may appear in a feature release before reaching an LTS line.

### What's New in GraalVM 25.1

GraalVM 25.1 introduced an early version of dynamic class loading for libraries/tools that generate JVM bytecode at runtime, such as certain Byte Buddy use cases. Enable it with the build option:

~~~text
-H:+RuntimeClassLoading
~~~

This is an **experimental** feature requiring experimental VM options to be unlocked per release documentation:

~~~bash
native-image \
  -H:+UnlockExperimentalVMOptions \
  -H:+RuntimeClassLoading \
  -H:-UnlockExperimentalVMOptions \
  -jar target/application.jar
~~~

This feature lets a class loader define classes from bytecode via `ClassLoader.defineClass`. It does not give Native Image JVMTI, does not provide `Instrumentation`, and does not let agents transform/retransform already-loaded classes.

Limitations to check before enabling:

- A class loader cannot redefine the same binary name within that same loader.
- Parallel class loading is not yet supported.
- `URLClassLoader` and loading classes from JDK/application class loaders may require additional configuration.
- Static analysis may have eliminated methods or static fields that dynamically defined classes need to access; you may need to preserve packages via `-H:Preserve=package=...`.
- Image size and memory usage may increase.
- Runtime class loading cannot be combined with predefined classes.

If a library uses Byte Buddy to **create new classes**, this feature may be relevant. If a library uses a Java agent to **transform existing classes** via `Instrumentation.redefineClasses` or `retransformClasses`, `-H:+RuntimeClassLoading` cannot satisfy that requirement.

## 7. Predefined Classes and Experimental Tracing Agent Options

Another path for legacy applications is predefined classes: the tracing agent observes classes generated/defined during a JVM run and saves their bytecode so Native Image can include them in build metadata; when the native runtime encounters a class with the same name and bytecode, the predefined class can be supplied.

Common option in supporting releases:

~~~bash
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config/,experimental-class-define-support \
  -jar target/application.jar
~~~

This is an **experimental** option. Output may contain an `agent-extracted-predefined-classes` directory alongside corresponding metadata.

Do not treat predefined classes as a general-purpose JVM class loader:

- It depends on classes actually observed and captured during tracing.
- It does not guarantee that arbitrary new classes, differing bytecode, or production-only classes will work.
- GraalVM documentation describes it as best-effort for legacy projects, with no guarantee of success.
- In current documentation, predefined classes cannot be combined with `-H:+RuntimeClassLoading`.

When possible, prefer generating code/proxies at build time or using AOT-integrated APIs/frameworks. Only consider predefined classes after verifying release support and proving the real use case with native integration tests.

## 8. Solution Selection Matrix by Use Case

Before deciding how to proceed, identify what operation the agent or library actually requires:

| Need | JVM | Native Image | Recommended Approach |
| --- | --- | --- | --- |
| Load a Java agent at startup to transform bytecode | `-javaagent` | Not supported as a JVM runtime | Move instrumentation to compile/build time or use a native-compatible integration |
| Attach an agent to a running JVM | Attach API / `agentmain`, JDK-dependent | JVMTI/Attach unsupported under the JVM agent model | Use native observability or keep this workload on the JVM |
| Bytecode-based profiler/coverage | Typically Java agent/JVMTI | Does not work like a standard JVM | Run coverage on the JVM; use native profilers for native binaries |
| APM agent using `ClassFileTransformer` | Typically `-javaagent` | Does not work automatically in native runtime | Use a vendor SDK/agent explicitly supported for Native Image |
| Collect reflection/resource metadata | Run app with tracing agent | Metadata used during native build | Run `native-image-agent` on the JVM and review output |
| Create proxy classes from bytecode at runtime | JVM supported per class loader/framework | Can try `RuntimeClassLoading` on GraalVM 25.1+ | Verify experimental feature, preserve metadata, and test on target |
| Redefine/retransform loaded classes | `Instrumentation` if JVM supports it | Not solved by RuntimeClassLoading | Redesign or keep this workload on the JVM |
| Generate classes before native build | Build-time code generation/annotation processing | Generated classes can be analyzed and compiled | Prefer build-time generation and feed output to native build |

### Example: Byte Buddy Can Be Used in Two Different Ways

A library using Byte Buddy might:

1. Create new proxy classes from bytecode at runtime via a class loader.
2. Install an agent to alter the bytecode of an already-loaded class.

These two use cases are not the same. GraalVM 25.1 runtime class loading targets the first case, within experimental limits. The second case relies on `Instrumentation`/JVMTI and is not supported as on the JVM.

Read the stack trace and the APIs the library calls. Look for keywords such as `ClassLoader.defineClass`, `ClassFileTransformer`, `Instrumentation`, `redefineClasses`, `retransformClasses`, `VirtualMachine.attach`, or `JVMTI` to pinpoint the actual requirement.

## 9. Configuring and Checking Versions in Maven/Gradle

The JDK alone does not determine the outcome. A native Spring Boot project also involves the Spring Boot version, GraalVM distribution, Native Build Tools plugin, builder image, and target OS/architecture.

### Record Actual Versions

Run these commands on the exact build environment:

~~~bash
java -version
native-image --version
./mvnw --version
./mvnw dependency:tree
~~~

With Gradle:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
~~~

Record at least:

| Component | Information to Record |
| --- | --- |
| JDK | Vendor, version, build number |
| GraalVM | Distribution, Native Image version, LTS/feature release |
| Spring Boot | Framework version and plugin version |
| Native Build Tools | Maven/Gradle plugin version |
| Agent | Name, version, APIs used (`java.lang.instrument`, JVMTI, or tracing agent) |
| Build environment | OS, architecture, compiler/linker |
| Runtime target | OS, architecture, libc/container image |

Do not infer the Native Image version solely from `java -version`. A GraalVM JDK can be updated separately, and a build plugin might invoke a different toolchain than the Java runtime on `PATH`.

### Passing RuntimeClassLoading to Maven

For projects already using `native-maven-plugin`, add build arguments to the existing plugin configuration:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-H:+UnlockExperimentalVMOptions</buildArg>
            <buildArg>-H:+RuntimeClassLoading</buildArg>
            <buildArg>-H:-UnlockExperimentalVMOptions</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

The configuration above is only for GraalVM versions that support this option. Do not add it as a way to enable Java agents; it only unlocks experimental runtime class loading.

### Passing RuntimeClassLoading to Gradle

Groovy DSL example:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-H:+UnlockExperimentalVMOptions")
            buildArgs.add("-H:+RuntimeClassLoading")
            buildArgs.add("-H:-UnlockExperimentalVMOptions")
        }
    }
}
~~~

Verify the DSL API against your Native Build Tools plugin version. For Kotlin DSL, use the plugin's corresponding typed API.

If the project does not need runtime class loading, do not add this option just because a library has "dynamic" in its name. First identify whether the library uses `defineClass` or `Instrumentation`.

## 10. Process for Checking Support by Version

When an agent or library reports incompatibility, follow this sequence:

1. **Identify the agent type:** `-javaagent`, `-agentlib`, `-agentpath`, Attach API, or `native-image-agent`.
2. **Identify the APIs the agent calls:** `Instrumentation`, `ClassFileTransformer`, JVMTI, `ClassLoader.defineClass`, reflection, or JNI.
3. **Record exact toolchain details:** JDK vendor/version, GraalVM Native Image version, Spring Boot, and Native Build Tools plugin.
4. **Read Java Instrumentation Javadoc:** confirm manifest entries, `premain`/`agentmain`, startup options, and dynamic attach policy.
5. **Read the exact-version Native Image Compatibility Guide:** check Debugging and Monitoring, JVMTI, and bytecode-based tools.
6. **Read the exact-version Native Image Tracing Agent docs:** confirm options, metadata output format, and experimental agent options.
7. **If defining classes at runtime is needed:** read Run-Time Class Loading docs and release notes; verify whether `-H:+RuntimeClassLoading` is available.
8. **Create a small smoke test:** exercise the exact operation the agent needs, not just executable startup.
9. **Run tests inside the native binary:** verify both success flows and error paths.
10. **Document version-specific findings:** which versions were tested, what works, what does not, and remaining limitations.

### Official Documentation Pages to Consult

- Java SE `java.lang.instrument` API: https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html
- JEP 451 — Prepare to Disallow the Dynamic Loading of Agents: https://openjdk.org/jeps/451
- GraalVM Native Image Compatibility Guide: https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/Compatibility/
- GraalVM Tracing Agent: https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/AutomaticMetadataCollection/
- GraalVM Runtime Class Loading: https://www.graalvm.org/dev/reference-manual/native-image/runtime-class-loading/
- GraalVM 25.1 release notes: https://www.graalvm.org/release-notes/25.1/
- GraalVM JDK 23 release notes: https://www.graalvm.org/release-notes/JDK_23/

Read documentation with a specific version selector and choose the matching release before applying examples. `latest` or `dev` pages may describe features not yet available in the LTS line your project uses.

## 11. Diagnosing Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JVM runs with `-javaagent`, native reports agent unsupported | Agent relies on Java Instrumentation/JVMTI | Confirm APIs used by the agent; find a native-compatible integration or move to build-time instrumentation |
| `premain` is not called | Agent JAR missing `Premain-Class`, wrong path, or not using a JVM launcher | Check manifest, run command, and JVM logs |
| Dynamic attach prints warning on JDK 21+ | Agent loaded into a running JVM | Locate source of Attach API call; prefer `-javaagent` at startup or deliberate opt-in |
| Native executable has no `Instrumentation` | Native runtime does not implement the JVM agent model | Do not try loading agents with `-javaagent`; use native-compatible observability |
| `native-image-agent` produces incomplete metadata | Tracing scenarios did not traverse dynamic branches | Run multiple scenarios, merge outputs, and review metadata |
| Metadata from older GraalVM not recognized as expected | Schema/format differences across releases | Check `reachability-metadata.json` and your current toolchain's schema |
| Byte Buddy class generation fails in native | Runtime class loading not enabled or missing setup/preserve | Verify GraalVM 25.1+, experimental options, class loader, and limits |
| `ClassLoader.defineClass` works but redefining classes fails | Runtime class loading does not provide `Instrumentation.redefineClasses` | Redesign the use case; dynamic class definition and class retransformation are different mechanisms |
| Agent works in JVM tests but native tests have no coverage | Test agent only instruments the JVM test process | Run coverage on the JVM or use native-aware tooling |
| Native build succeeds yet APM shows no traces | APM relies on a bytecode agent or lacks native integration | Use library/SDK-level instrumentation or a vendor agent built specifically for Native Image |

### Pull Request Review Checklist

- [ ] Does the agent truly require `Instrumentation`/JVMTI?
- [ ] Is the agent loaded at startup or attached after startup?
- [ ] Is `native-image-agent` being confused with an application agent?
- [ ] Is runtime class loading being confused with bytecode transformation?
- [ ] Does the GraalVM release support the exact feature needed?
- [ ] Have experimental options been documented and tested on target?
- [ ] Has metadata tracing covered the required business paths?
- [ ] Has the native executable been tested with the exact intended APM/profiler/monitoring integration?

## 12. Practice Exercise: Testing an Agent on the JVM and Evaluating the Native Path

Build a small Java agent following Section 1, then use the same Spring Boot application to compare both modes.

**Part A — JVM**

1. Package the agent with a manifest containing `Premain-Class`.
2. Run the Spring Boot JAR with `java -javaagent:... -jar ...`.
3. Verify `premain` is invoked and the transformer sees application classes.
4. Try a JVM test using an instrumentation tool to record invoked methods or classes.
5. On JDK 21 or newer, specifically test dynamic attach warnings if any dependency uses the Attach API.

**Part B — Native Image**

1. Build the application using Spring AOT and GraalVM Native Image.
2. Run the native executable and verify `-javaagent` is not a mechanism for instrumenting the native runtime.
3. Run the application on the JVM with `-agentlib:native-image-agent=config-output-dir=...` to collect reachability metadata for dynamic access paths.
4. Review metadata and rebuild the native executable.
5. If the application generates classes via `ClassLoader.defineClass`, create a test branch with GraalVM 25.1+ and `-H:+RuntimeClassLoading`; verify the feature's limits independently.
6. Record results for each mechanism: startup agent, dynamic attach, tracing metadata, runtime class loading.

### Self-Check Questions

1. How do `premain` and `agentmain` differ in timing?
2. How does `-javaagent` differ from `-agentlib` and `-agentpath`?
3. What did JEP 451 change for dynamic agent loading starting in JDK 21?
4. Why can a Java agent running smoothly on the JVM fail inside Native Image?
5. What metadata does the Native Image Tracing Agent produce and in which process does it run?
6. Why can't the tracing agent prove by itself that all dynamic accesses have been captured?
7. How does `reachability-metadata.json` differ from the separate metadata files in older GraalVM releases?
8. What operation does `-H:+RuntimeClassLoading` in GraalVM 25.1 support?
9. Why does runtime class loading not imply support for `Instrumentation.redefineClasses`?
10. When should build-time bytecode weaving be preferred over a load-time Java agent?

**Acceptance criteria:** distinguish Java agents, JVMTI agents, the Native Image Tracing Agent, and runtime class loading; look up limits by JDK/GraalVM release; explain dynamic attach changes since JDK 21; accurately identify experimental features from GraalVM 25.1; and propose appropriate testing and alternatives for Spring Boot Native Image applications.
