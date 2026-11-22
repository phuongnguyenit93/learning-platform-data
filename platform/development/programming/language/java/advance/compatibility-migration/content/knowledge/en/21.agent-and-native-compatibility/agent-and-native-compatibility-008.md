# Native Access Permissions and Per-Version Configuration Requirements

In **Java Advance Compatibility Migration**, applications using JNI (Java Native Interface), the Foreign Function & Memory API (FFM), native libraries, Java agents, or instrumentation tooling must be evaluated specifically when upgrading the JDK. Code calling `System.loadLibrary()` may previously have run without warnings, yet on newer JDKs emit warnings about native access permissions. FFM code calling `Linker.downcallHandle()` may require enabling native access. Under stricter modes, the JVM rejects the operation with `IllegalCallerException`.

However, not every error involving `.dll`, `.so`, `.dylib`, agents, or reflection is fixed with the same JVM flag. `--enable-native-access`, `--illegal-native-access`, `--add-opens`, `-javaagent`, and `-XX:+EnableDynamicAgentLoading` serve **different purposes**. Applying the wrong flag can mask the true root cause or grant far broader privileges than necessary.

This lesson explains what native access is, how it evolved across JDK releases, how to grant permissions per module, how to locate components requesting access, example configurations for classpath/module path/Gradle/Maven, and how to verify on the real target runtime. The goal is not “silencing every warning,” but **granting intentional permissions to trusted code, preserving JVM integrity, and holding compatibility evidence per JDK release**.

## 1. What Is Native Access and Why Is It Controlled?

Regular Java code is governed by the JVM for type safety, memory management, and object access. When a program invokes native code or uses APIs capable of manipulating off-heap or process memory directly outside the JVM, the runtime can no longer verify every safety invariant.

Examples:

- JNI loads a native library via `System.loadLibrary` or `System.load`.
- A Java class declares a method with modifier `native` and binds it to a native function.
- The FFM API links Java calls to functions in a C library or constructs unsafe memory views.
- A native library manipulates raw pointers, buffers, or invokes system APIs impacting the process.
- A Java agent uses instrumentation or native JVMTI to observe or alter JVM execution.

Native code can be valid and indispensable—such as video processing, database drivers with native libraries, compression, machine learning, smart cards, or OS integration. Yet bugs in native code can cause **memory corruption**, JVM crashes, resource leaks, or unintended code execution. Native access permission is therefore treated as a deliberate configuration decision by the application deployer rather than something granted automatically to every library.

**Enabling native access is not a sandbox.** It identifies modules permitted to execute risky native operations; an authorized module must still rely on safe, tested native libraries.

## 2. Distinguishing JNI, FFM, Java Agents, and JVMTI

| Mechanism | Role | Examples | Relation to Native Access |
|---|---|---|---|
| JNI | Java calls native methods or native code interacts with JVM | `native int calculate(int)`, `System.loadLibrary` | Starting in JDK 24, JNI operations fall under restricted access per JEP 472 |
| FFM API | Java API for off-heap memory access and native function calls | `java.lang.foreign.Linker`, `MemorySegment` | Certain methods are marked restricted; must be enabled per module |
| Java Instrumentation Agent | Instruments classes at startup or runtime | `-javaagent:agent.jar` | Has separate rules for dynamic agent loading; distinct from JNI/FFM |
| Native JVMTI agent | Native agent integrated at JVM tooling level | `-agentlib:...`, `-agentpath:...` | Inspect separate agent/JVM policies rather than assuming identical JNI flags |
| Reflection / JPMS | Accessing metadata and Java members across module boundaries | `setAccessible(true)` | Controlled by `opens` / `--add-opens`, not resolved by native access |
| Classpath / module path | Defines how code/modules are loaded | `-cp`, `-p` | Determines whether the target is `ALL-UNNAMED` or a named module |

An application may use multiple mechanisms simultaneously. When seeing a warning or exception, identify **which JVM**, **which module's code**, **which operation**, and **which flag actually applies**.

## 3. Why Do Native Access Rules Change Across JDK Releases?

Java does not enforce one immutable policy across all releases. Key milestones include:

| JDK Milestone | Key Changes to Know | Migration Notes |
|---|---|---|
| JDK 8/11/17 | JNI is widely used; JEP 472-style native access restrictions do not run like JDK 24 | Do not copy new flags verbatim to old JDKs if launchers do not support them |
| JDK 17–21 | FFM progressed through incubator/preview phases with changing APIs per release | FFM code must match exact releases, sometimes needing `--enable-preview` in preview eras |
| JDK 21 | JEP 451 begins warning when agents load dynamically in many cases | This governs **dynamic agent loading**, not JNI/FFM native access flags |
| JDK 22 | JEP 454 finalizes the FFM API under `java.lang.foreign` | Several FFM methods remain restricted and require `--enable-native-access` |
| JDK 24 | JEP 472 prepares to restrict JNI; aligns warnings for both JNI and FFM | Introduces `--illegal-native-access=allow/warn/deny`; defaults to `warn` in JDK 24 |
| JDK 25/26 | Restricted native operations policy continues defaulting to `warn` per those release docs | Test with `deny` to prepare for stricter future defaults |
| Future releases | JEP 472 documentation anticipates `deny` eventually becoming default | **Do not hard-assume a specific future JDK number** until target release notes confirm it |

These rows highlight key milestones rather than an exhaustive catalog of vendor-specific JNI/JVMTI changes. Before upgrading production, read **release notes and `java` launcher documentation for the exact JDK/update/build deployed**. Never treat JDK 24 defaults as permanent promises for JDK 27 or later.

### 3.1. JDK 22 Milestone: Finalized FFM API Does Not Mean Every Method Is Safe

Finalizing the FFM API in JDK 22 lets code use `java.lang.foreign` APIs without preview flags merely to unlock the final API. Nevertheless, operations such as creating downcall handles or loading native libraries via FFM remain marked **restricted** because they can bypass Java safety guarantees.

Distinguish clearly:

- Whether an API exists in a given Java release.
- Which exact syntax that release uses.
- Which methods are marked restricted in that release's docs.
- Whether the calling module holds native access.

An FFM program can compile cleanly yet still emit warnings or fail at runtime due to missing permissions.

### 3.2. JDK 24 Milestone: Native Restrictions Apply to JNI Too

Under JEP 472, operations such as `System.loadLibrary`, `System.load`, `Runtime.loadLibrary`, `Runtime.load`, and initial binding of `native` methods fall under native access control. When a module lacks access, behavior is governed by `--illegal-native-access`.

The default `warn` mode permits execution while emitting a warning, typically at most once per module under this mechanism. Therefore, **an app still running does not mean it is ready for when `deny` becomes the default**.

## 4. Two Key Options: `--enable-native-access` and `--illegal-native-access`

### 4.1. `--enable-native-access`: Granting Access to Specific Modules

Typical launcher syntax:

~~~text
--enable-native-access=module1,module2,...
~~~

Named module example:

~~~bash
java --enable-native-access=com.example.nativebridge \
     --module-path mods \
     --module com.example.app/com.example.Main
~~~

Here, `com.example.nativebridge` is the module executing the restricted JNI/FFM operation. It **need not be the module holding `main`**. Identify the caller of the restricted operation before configuring flags.

For classpath-based applications:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     -cp "app.jar:lib/*" \
     com.example.Main
~~~

`ALL-UNNAMED` grants native access to code across **unnamed modules** (typically the classpath). This scope is broad: it covers more than just a single JAR containing JNI. On Windows, classpath lists use `;` instead of `:`.

Never pass native shared library filenames as the value to `--enable-native-access`. This flag takes **Java module names or `ALL-UNNAMED`**, not `libmylib.so` or DLL names.

### 4.2. `--illegal-native-access`: Controlling Behavior When Access Is Missing

Starting in JDK 24, behavior can be selected via:

~~~text
--illegal-native-access=allow
--illegal-native-access=warn
--illegal-native-access=deny
~~~

| Mode | Behavior When Calling Module Lacks Native Access | Appropriate Usage |
|---|---|---|
| `allow` | Permits execution without warning from this mechanism | Consider only for short-term transition, never as a final solution |
| `warn` | Permits execution while warning for the calling module | Helps discover code needing configuration updates |
| `deny` | Rejects unauthorized restricted operations, potentially throwing `IllegalCallerException` | Use in testing environments to catch every module needing permission before stricter future defaults |

This option sets **policy for un-enabled modules**. When native access is genuinely needed, the durable fix is **enabling the exact calling module**, not setting JVM-wide `allow` indefinitely.

### 4.3. Combining Both Options Effectively

A useful verification setup on JDKs supporting both flags:

~~~bash
java --enable-native-access=com.example.nativebridge \
     --illegal-native-access=deny \
     --module-path mods \
     --module com.example.app/com.example.Main
~~~

Meaning: module `com.example.nativebridge` is allowed restricted native operations; any other un-enabled module attempting them is blocked. If a test fails, verify whether that module truly needs native access or a dependency is doing something unexpected.

For classpath apps:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp "app.jar:lib/*" com.example.Main
~~~

The second form is easier to adopt yet grants broader privileges. Never confuse it with allowing only a single JAR.

## 5. Classpath vs. Module Path Governs Permission Granularity

JPMS distinguishes **named modules** from **unnamed modules**. Native access is configured per module, not per individual Java package or method.

| Code Placement | Name Used to Enable | Scope |
|---|---|---|
| Classpath | `ALL-UNNAMED` | All code in unnamed modules |
| Module path, explicit named module | `com.example.nativebridge` | Only the named module specified |
| Module path, automatic module | Module name resolved by runtime for that JAR | That specific automatic module |
| Dynamic module layer | API can grant access to a module in the layer under required conditions | Depends on layer design and JDK support |

For a classpath library where tighter scoping is wanted, consider moving that JAR onto the module path. An unmodularized JAR can be treated by the JVM as an **automatic module**. However, moving from classpath to module path can introduce module naming issues, split packages, readability gaps, or `ServiceLoader` failures. Never move purely to narrow a flag without full integration testing.

Automatic module names need not match Maven/Gradle coordinates. Inspect module metadata with:

~~~bash
jar --describe-module --file native-wrapper.jar
~~~

If a JAR update alters filenames or module names, launcher options may need updating too. Prefer libraries publishing a stable `Automatic-Module-Name` or full `module-info.class`.

### 5.1. Do Not Confuse Native Access with Package Access

`--enable-native-access=com.example.nativebridge` does not export another module's packages and does not allow `setAccessible(true)` into private JDK fields.

Conversely, `--add-opens=java.base/java.lang=ALL-UNNAMED` opens a package for deep reflection within scope, yet **never grants JNI/FFM restricted native operations**.

If a framework uses both deep reflection and a native library, the application may face **two distinct issues**. Each needs its own root-cause check and fix; do not paste both flags reflexively on any startup failure.

## 6. Minimal JNI Example

Java code can declare a native method:

~~~java
package com.example.nativebridge;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    private NativeMath() {}

    public static native int twice(int input);
}
~~~

This class needs a native shared library built for the target OS/architecture implementing the matching JNI function. Consumer example:

~~~java
package com.example.app;

import com.example.nativebridge.NativeMath;

public final class Main {
    public static void main(String[] args) {
        System.out.println(NativeMath.twice(21));
    }
}
~~~

Generate the JNI header with the compiler inside a prepared build environment:

~~~bash
javac -h native-headers \
      -d classes \
      src/com/example/nativebridge/NativeMath.java
~~~

The generated header declares the C/C++ JNI signature to implement. Compiling and linking the native binary depends on your OS and C toolchain; this Java snippet **does not ship a native library automatically** until compiled and installed.

### 6.1. Distinguishing Three Categories of JNI Errors

| Symptom | Typical Cause | Investigation |
|---|---|---|
| Warning about restricted native access | Calling JNI module lacks enablement under JDK policy | `--enable-native-access` for the exact calling module |
| `IllegalCallerException` on restricted operation in `deny` mode | Caller lacks native access | Configure permission and identify calling module |
| `UnsatisfiedLinkError` | Native library missing, unloadable, or symbol mismatch | `java.library.path`, OS/arch, ABI, exported symbols |
| JVM crash such as `SIGSEGV` | Memory bug in native code or ABI mismatch | Core dump, `hs_err` log, native debugger, safety tests |
| `UnsupportedClassVersionError` | Java bytecode requires newer JDK | Class-file version vs runtime JDK |

**Never try fixing an `UnsatisfiedLinkError` caused by missing paths or symbols with `--enable-native-access`.** They are unrelated layers.

### 6.2. Locating Native Libraries

Typically `System.loadLibrary("native_math")` instructs the runtime to look up an OS-named library, such as `libnative_math.so` on Linux or `native_math.dll` on Windows. Search behavior depends on launcher, JVM, library logic, and OS policy.

Illustrative launch configuration:

~~~bash
java -Djava.library.path=/opt/app/native \
     --enable-native-access=ALL-UNNAMED \
     -cp app.jar com.example.app.Main
~~~

`java.library.path` helps locate native libraries in standard library loads yet **does not grant native access**; `--enable-native-access` grants access yet **does not locate or fix native binaries**. Verify both layers.

## 7. FFM Example on JDK 22+

Using the finalized FFM API on JDK 22 or newer, code can resolve a native symbol and derive a method handle to invoke the function.

Illustrative Java API example:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class NativeFFM {
    public static void main(String[] args) throws Throwable {
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup =
                    SymbolLookup.libraryLookup(
                            Path.of("/opt/app/native/libnative_math.so"),
                            arena);

            MemorySegment symbol = lookup.find("twice").orElseThrow();

            MethodHandle twice = Linker.nativeLinker().downcallHandle(
                    symbol,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT));

            int result = (int) twice.invokeExact(21);
            System.out.println(result);
        }
    }
}
~~~

This assumes the native library exports matching C function `int twice(int)`, the ABI matches, the file exists on Linux, and the JDK supports the exact API shown. It will not run verbatim on Windows or macOS without adapting library paths/filenames.

Operations like `SymbolLookup.libraryLookup` and `Linker.downcallHandle` perform restricted native access. On applicable runtimes, grant permission to the module holding the caller:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     -cp classes NativeFFM
~~~

If packaged as a named module, replace `ALL-UNNAMED` with the **actual module name** executing restricted operations.

### 7.1. Native Permission Does Not Guarantee FFM Memory Safety

FFM expresses memory lifetimes, layouts, and foreign calls far more cleanly than hacks built on internal APIs. Still, building a downcall handle with a wrong `FunctionDescriptor` or passing bad pointers will crash the JVM or corrupt memory.

When migrating from JNI to FFM:

- Verify calling conventions and ABIs.
- Check platform `int`/`long` widths, alignment, and struct padding.
- Audit ownership and lifetimes of native `MemorySegment`s and `Arena`s.
- Ensure native functions never retain pointers past contract lifetime.
- Test callbacks/upcalls, thread safety, and native error propagation.
- Test on every supported OS/architecture.
- Record every module needing native access permission.

Never assume turning on the flag proves FFM code is correct.

## 8. Finding Which Module Needs Access from Warnings

On JDK 24+, native access warnings normally name the restricted method and caller module. Illustrative message:

~~~text
WARNING: A restricted method in java.lang.System has been called
WARNING: java.lang.System::load has been called by ...
WARNING: Use --enable-native-access=... to avoid a warning
~~~

Exact wording can change across JDK updates, so do not write rigid verbatim parsers. Extract these facts:

1. Which restricted method was called?
2. Which JAR owns the calling Java class?
3. Is the caller in a named module or an unnamed module?
4. Which JVM process emitted the warning?
5. Which execution path triggered it?
6. Was native access already configured on that JVM?
7. Do other libraries/JARs also require permissions?

Never sweep `--illegal-native-access=allow` across the whole JVM and ignore the source. Running cleanly under `warn` hides technical migration debt that will break later.

## 9. Distinguishing `--enable-native-access` from `--enable-preview`

These flags serve distinct purposes:

- `--enable-preview`: unlocks **preview language/API features** of a specific Java release when compiler/runtime require it.
- `--enable-native-access`: permits selected modules to invoke **restricted native operations**.

In JDKs prior to FFM finalization, FFM samples lived in incubator/preview APIs with release-dependent activation mechanics. On JDK 22+, finalized FFM APIs no longer require preview flags **merely to use the final API**, yet restricted FFM methods still require native access.

Never take FFM code written for JDK 21 and expect it to compile verbatim on JDK 22/25; packages and API signatures changed across incubator/preview stages. Consult code and docs matching your **exact target JDK**.

## 10. Java Agents: Dynamic Attach Is Not JNI/FFM Policy

In the **Agents and Native Code** module, keep native access policy separate from **dynamic agent loading**.

A Java instrumentation agent passed at JVM startup:

~~~bash
java -javaagent:monitor-agent.jar -jar application.jar
~~~

By contrast, tooling can attach an agent dynamically into a running JVM via the Attach API or observability agents. JEP 451 (JDK 21) introduced warnings for **dynamic agent loading** to prepare for stricter future defaults.

Flags documented in supporting releases include:

~~~text
-XX:+EnableDynamicAgentLoading
-XX:-EnableDynamicAgentLoading
~~~

These govern **dynamic loading of Java agents**, without granting JNI or FFM native access. When diagnosing:

| Symptom | Issue Layer |
|---|---|
| Warning when agent attaches after JVM boot | Dynamic agent loading, JEP 451 |
| JNI load/native bind warning on JDK 24+ | Native access, JEP 472 |
| FFM restricted method warning | Native access of FFM-calling module |
| `InaccessibleObjectException` when agent reflects into JDK internals | JPMS `opens` / reflective access |
| `libagent.so` not found | Native library path / ABI |
| Agent rejects class-file version | Agent's JDK / bytecode parser support |

One instrumentation tool can emit **multiple independent warnings**. Never slap both `-XX:+EnableDynamicAgentLoading` and `--enable-native-access=ALL-UNNAMED` onto every JVM merely because an agent exists.

### 10.1. Native Agents Differ from Java Agents

- `-javaagent:...` loads a Java instrumentation agent per its manifest/capabilities.
- `-agentlib:name` or `-agentpath:path` loads native agents/tooling libraries via JVMTI.
- Restricted JNI/FFM calls executed from Java code must obey the JDK's native access policy.
- Agent loading policies and JVMTI privileges operate via distinct mechanisms—never extrapolate one flag to cover another.

When errors come from monitoring agents, check vendor-certified agent releases and official configuration for the target JDK first.

## 11. Java SE Module Names vs. Automatic Modules

A native library may publish under Maven coordinates:

~~~text
com.example:native-bridge:2.4.0
~~~

yet its actual JPMS module name might be `com.example.nativebridge` or something else. `--enable-native-access` accepts the **module name**, not `group:artifact:version`.

With an explicit module descriptor:

~~~java
module com.example.nativebridge {
    exports com.example.nativebridge.api;
}
~~~

Invoking restricted native operations inside this module can require:

~~~bash
java --enable-native-access=com.example.nativebridge \
     --module-path mods \
     --module com.example.app/com.example.Main
~~~

`exports` does not grant native access; module descriptors define API visibility, while native access is explicitly granted by the launcher or equivalent controller.

For automatic module JARs, confirm the derived module name via `jar --describe-module`. Never guess from filenames when `Automatic-Module-Name` or JAR versions evolve.

## 12. Manifests and Delivery Mechanisms for Native Access Permissions

Beyond CLI options, supporting JDKs provide additional delivery options.

### 12.1. Manifest Attribute for Executable JARs

A manifest may declare:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Enable-Native-Access: ALL-UNNAMED
~~~

Per supporting JDK docs, this manifest attribute applies to executable JARs and accepts `ALL-UNNAMED`; it **does not allow naming arbitrary named modules** through the manifest attribute.

Placing this in an executable JAR grants classpath-wide access intentionally. Where least privilege matters, using the module path paired with targeted launcher flags fits better.

### 12.2. Environment Variables, Argument Files, and Runtime Images

Native access options can pass to launchers through JDK-supported mechanisms such as:

- Command-line flags to `java`.
- `JDK_JAVA_OPTIONS` in appropriate environments.
- Launcher `@options.txt` argument files.
- Custom runtime images built via `jlink` with configured launcher options via supporting plugins.
- Native launchers embedding the JVM via the JNI Invocation API passing launch options at VM creation.

Never scatter flags simultaneously across scripts, environment variables, and JAR manifests without tracking scope. Centralize configuration inside **version-controlled release definitions** with clear owners and verification.

### 12.3. Dynamic Module Layers

Frameworks constructing dynamic module layers can use APIs like `ModuleLayer.Controller.enableNativeAccess(Module)` (finalized in JDK 22) when conditions permit. Calling that controller method is itself restricted and requires the framework module to already hold native access.

This targets plugin/layer-managing frameworks specifically. Regular applications do not write dynamic permission code just to call a classpath JNI wrapper; launcher configuration is cleaner.

## 13. Gradle: Targeting the Exact JVM Process

Separate JVMs may run in a single build:

- Gradle daemon running plugins and build scripts.
- `JavaCompile` running the compiler toolchain.
- `Test` worker running unit/integration tests.
- `JavaExec` running an app or CLI utility.
- Production application runtime.
- Java agents active across one or more processes above.

Sample **JDK 24+** config to catch any un-permitted native access during tests:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs(
        "--enable-native-access=ALL-UNNAMED",
        "--illegal-native-access=deny"
    )
}
~~~

This applies solely to configured `Test` worker JVMs. Neither the Gradle daemon nor deployed production images inherit these args automatically.

For a `JavaExec` task:

~~~kotlin
tasks.withType<JavaExec>().configureEach {
    jvmArgs(
        "--enable-native-access=ALL-UNNAMED",
        "--illegal-native-access=deny"
    )
}
~~~

Avoid applying flags globally if only one task needs native access. If task A executes JNI while task B does not, scope flags to task A alone.

### 13.1. `application` Plugin

When using Gradle's `application` plugin, default JVM arguments for generated launch scripts can be configured as:

~~~kotlin
plugins {
    application
}

application {
    mainClass.set("com.example.Main")
    applicationDefaultJvmArgs = listOf(
        "--enable-native-access=ALL-UNNAMED",
        "--illegal-native-access=deny"
    )
}
~~~

This assumes the target runtime JDK recognizes those options. Whether production uses classpath or module path decides between `ALL-UNNAMED` vs named modules. Remember build JDKs can differ from runtime JDKs; never pass `--illegal-native-access=deny` to older JDKs lacking that option.

### 13.2. Watch Out for the Gradle Daemon

If a warning originates from a **Gradle plugin** calling native code inside the daemon, adding `jvmArgs` on `Test` tasks will not fix it. Conversely, daemon JVM flags do not automatically grant native access to forked test JVMs.

Read stack traces/warnings to identify process IDs, launch commands, Gradle/JDK versions, and caller modules. Upgrade plugins to supported releases rather than loosening permissions across the whole build.

## 14. Maven: Test Plugins and App Runtimes Are Separate Processes

In Maven, the JVMs running Maven core, compilation, and forked tests can differ. In Maven Surefire, pass JVM options to forked test JVMs via configuration:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version><!-- choose a compatible plugin version --></version>
  <configuration>
    <argLine>
      --enable-native-access=ALL-UNNAMED --illegal-native-access=deny
    </argLine>
  </configuration>
</plugin>
~~~

This is a **configuration skeleton**: replace the placeholder version with a valid release verified against your JDK. If Maven runs non-forked tests or another plugin manages integration tests, place options where that plugin supports them.

If Maven Failsafe executes integration tests, configure Failsafe similarly. Never assume Surefire's `argLine` configures other plugins or production packaging.

Wrappers (`mvnw`/`gradlew`) pin build tool distributions—they **never propagate native access options to every JVM spawned during the build**.

## 15. Containers and Deployment: Permissions Must Reach Production Runtime

Local test settings do not carry over into production containers automatically. Example Dockerfile with a matching runtime JDK:

~~~dockerfile
FROM eclipse-temurin:25-jre

WORKDIR /app
COPY app.jar /app/app.jar
COPY native/ /opt/app/native/

ENTRYPOINT [
  "java",
  "--enable-native-access=ALL-UNNAMED",
  "--illegal-native-access=deny",
  "-Djava.library.path=/opt/app/native",
  "-jar",
  "/app/app.jar"
]
~~~

This is illustrative. Production images must also verify approved base image digests, file permissions, non-root users where appropriate, native system library dependencies, ABI compatibility, OS architecture, and secrets management.

During deployment verification, confirm:

1. The runtime JDK supports every configured launcher flag.
2. Containers run the exact JDK feature/update/vendor tested in CI.
3. Native libraries match Linux/Windows/macOS and CPU architecture.
4. OS-level dependencies (e.g., `libc`) exist with matching ABI.
5. The Java process has read/execute permissions on native binaries.
6. Flags reach the intended JVM processes, including workers and batch subprocesses.
7. Any newly emitted warnings are collected and monitored.

Enabling flags inside a container cannot rescue a native library compiled for the wrong OS or CPU architecture.

## 16. Finding Code Requiring Native Access with `jnativescan`

Starting in JDK 24, `jnativescan` statically inspects JARs to find calls to restricted methods and `native` method declarations.

Example:

~~~bash
jnativescan --class-path app.jar
~~~

To print only modules identified as needing native access:

~~~bash
jnativescan --class-path app.jar --print-native-access
~~~

When JARs sit on the module path:

~~~bash
jnativescan --module-path mods \
    --add-modules com.example.nativebridge \
    --print-native-access
~~~

Supporting versions also accept `--release` to match restricted methods/classes for a target release, useful when analyzing multi-release JARs:

~~~bash
jnativescan --release 24 --class-path app.jar
~~~

Before scripting around it, check:

~~~bash
jnativescan --help
jnativescan --version
~~~

**Limitations:** this is static analysis. It can miss calls constructed via reflection, dynamic class loading, JNI callbacks, or un-scanned JARs. A clean `jnativescan` report does not prove an app never touches native code. Moreover, the tool does not ship in older JDKs—do not assume it exists in a Java 17 pipeline.

### 16.1. Scanning the Full Dependency Set

When an app bundles libraries in `lib/`, scan every direct and transitive JAR that may wrap JNI/FFM:

- Codecs, compression, image/video processors.
- Database clients/drivers with native components.
- ML inference engines and native BLAS libraries.
- Terminal/console libraries and OS-specific helpers.
- Java agents, profilers, and instrumentation toolkits.
- JNI wrappers embedded inside third-party SDKs.
- JARs dynamically loaded by plugin systems.

Ignore JARs absent at runtime just because they share a Maven group. Scan the **resolved dependency graph** and actual deployment artifacts.

## 17. Observing Native Libraries with JFR and Runtime Logs

JDK Flight Recorder emits events such as:

~~~text
jdk.NativeLibraryLoad
jdk.NativeLibraryUnload
~~~

These reveal which native libraries actually load/unload along executed paths. They do not replace `jnativescan`, and zero events in one session do not prove uncovered code paths skip native calls.

During triage, record:

- Process name, JDK build, and launch flags.
- Timestamp of native library load.
- Involved JAR, class, and module.
- Native library path, OS, and CPU architecture.
- Stack traces and warnings if emitted.
- Test scenario triggering the load/bind.
- Error class and outcome after permission adjustment.

Sanitize sensitive file paths, credentials, or user identifiers before posting logs into public tickets.

## 18. Distinguishing Native Access Warnings from Load/ABI Errors

| Symptom | What to Investigate | Fixed by `--enable-native-access`? |
|---|---|---|
| `WARNING: restricted method ...` | Which module invokes restricted JNI/FFM APIs | Yes, when legitimately needed on the calling module |
| `IllegalCallerException` on restricted method | `deny` mode active without module permission | Yes, once verified |
| `UnsatisfiedLinkError: no ... in java.library.path` | Missing binary or search path mismatch | No; fix library paths or packaging |
| `UnsatisfiedLinkError` resolving JNI method | Symbol, signature, ABI, or name mangling bug | No; fix native implementation |
| `wrong ELF class` or architecture mismatch | 32/64-bit, ARM/x64, or OS mismatch | No |
| Missing transitive `.so`/`.dll` dependency | OS dynamic linker missing native system libs | No |
| `InaccessibleObjectException` | Module openness / deep reflection | No; handle via `opens`/`--add-opens` |
| Agent attach warning | JEP 451 / dynamic agent loading | Not fixed directly; review agent policy |
| `SIGSEGV` / `EXCEPTION_ACCESS_VIOLATION` | Native memory corruption or ABI bug | No; investigate native crash |
| `UnsupportedClassVersionError` | Java bytecode newer than JVM | No; align JDK/artifact versions |

Failures caused purely by missing permission **can be fixed by flags**, yet verify that enabling permission does not merely let execution proceed into a deeper native crash. Permission unlocks execution; it does not certify native code safety.

## 19. Preparing for `deny` Mode Verification

On JDK 24+ and releases supporting the option, test strictly under control:

~~~bash
java --illegal-native-access=deny \
     -cp "app.jar:lib/*" com.example.Main
~~~

No module receives native access here. Any path calling restricted JNI/FFM fails immediately. Locate the true caller module and enable it intentionally:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp "app.jar:lib/*" com.example.Main
~~~

Prefer named modules over `ALL-UNNAMED` on modular deployments. Recommended rollout steps:

1. Capture baseline on the target JDK in default mode, saving warnings.
2. Use `jnativescan` and dependency inventory to map callers.
3. Run tests with `--illegal-native-access=deny` to uncover all missing call paths.
4. For each module, evaluate whether native access is truly needed or can be replaced/removed.
5. Enable minimal required modules and re-test.
6. Run full native integration suites: load, calls, callbacks, error paths, and cleanup.
7. Propagate identical config across tests, app launchers, and production deployments.
8. Watch warnings when bumping JDK patch updates or libraries.
9. Record review conditions so temporary broad flags are revisited rather than copied forever.

Even if all tests pass, conclusions hold strictly for **the tested JDK, OS, architecture, native libraries, drivers, and code paths**.

## 20. Security and Operational Guarantees Flags Cannot Solve

Native code sits partly outside Java's type and memory safety guarantees. Even trusted native libraries break or misbehave when environments change.

Beyond flags, check:

- Provenance, checksums, and signatures of native binaries and Java wrappers.
- CPU architecture, OS ABI, system library versions, and static vs dynamic linking.
- Filesystem permissions to read/load libraries.
- Ownership/lifetime of pointers, buffers, and allocators/arenas.
- JNI/FFM threading model, reentrancy, and synchronization.
- Input validation before handing untrusted inputs to native functions.
- Error propagation and resource cleanup if native calls fail.
- Crash dump capture and access controls protecting sensitive memory dumps.
- Concurrency and shutdown hooks.
- Agent/profiler compatibility with newer JDKs/runtimes.
- Latency, throughput, and memory footprint after swapping wrappers or backends.

If migrating away from `sun.misc.Unsafe` toward FFM/`VarHandle`, match the API to the real use case. `VarHandle` addresses controlled memory access; FFM addresses off-heap memory and native calls—neither replaces the other unconditionally. Never cling to internal APIs just because a compatibility flag hides warnings.

## 21. Test Matrix Across Real JDKs and Runtimes

Applications claiming multi-JDK support need an **evidence matrix**, never assumptions extrapolated from one run.

| Combination | Verification Focus |
|---|---|
| JDK 17 + current JNI | Confirm JNI runs as expected; loader paths, native ABI |
| JDK 21 + agents/instrumentation | Dynamic agent loading warnings, startup vs attach timing |
| JDK 22 + final FFM | Source API alignment, restricted methods, and `--enable-native-access` |
| JDK 24 + JNI/FFM | JEP 472 warnings, `--illegal-native-access=deny`, module enablement |
| JDK 25/26 + native stack | Release policies/defaults, runtime tests, JAR/modules, and OS ABI |
| Future JDKs | Read release notes first; do not assume JDK 24 defaults stay constant |

When targeting only one JDK and OS, test deeply on that exact stack. When shipping a library or SDK to external consumers, state support matrices and minimum JDKs explicitly.

### 21.1. Critical Test Cases

- First-time loading of the native library.
- Normal calls, boundary values, error paths, and `null` inputs.
- Native callbacks and upcalls if used.
- Memory arena creation/destruction, ownership, and leak tests.
- High-concurrency multi-threaded execution.
- Booting with granted permissions vs intentionally omitted permissions in test sandboxes.
- Discovering native binaries across every supported OS/architecture.
- Failure behavior when native binaries are absent or ABI-incompatible.
- Authorized agent attach workflows where supported.
- Regression monitoring for warnings/errors post-JDK bump.
- Latency, CPU, and memory comparisons against baseline.

Never run destructive negative tests meant to force crashes or memory corruption in production. Keep those inside isolated sandboxes with safe fixtures.

## 22. Recording Native Access Exceptions in Migration Records

Sample record:

~~~yaml
nativeAccess:
  component: "example-native-wrapper"
  javaArtifact: "com.example:native-bridge:2.4.0"
  targetJdk:
    feature: 25
    vendorBuild: "fill from java -version"
  execution:
    mode: "module-path"
    module: "com.example.nativebridge"
  requiredOperations:
    - "System.loadLibrary"
    - "JNI native method binding"
  approvedLaunchOptions:
    - "--enable-native-access=com.example.nativebridge"
    - "--illegal-native-access=deny"
  checks:
    jnativescan: "NOT_YET_RUN"
    integrationTest: "NOT_YET_RUN"
    nativeAbiTest: "NOT_YET_RUN"
  limitations:
    - "windows-arm64-not-tested"
  owner: "platform-team"
~~~

This is a **record template**, not evidence of a passing run. In practice, add commit SHA, Java/native artifact checksums, OS, CPU, dependency graph, logs, test timestamps, reports, owners, and permission review dates.

When forced to grant `ALL-UNNAMED` because a library lacks a stable module name, document the broader scope, justification, and plan to tighten once modularized.

## 23. Decision Workflow for Native Access Permissions

### Step 1: Lock Target JDK Details

Record Java feature/update/build, vendor, OS, architecture, and runtime/container images. Never pick flags from blog posts written for another JDK.

### Step 2: Locate Native Callers

Identify JNI declarations, `System.loadLibrary`, FFM restricted calls, native-wrapper dependencies, and instrumentation agents—including dynamically loaded components.

### Step 3: Classify Errors Properly

Separate missing native access from library paths, native ABI bugs, `--add-opens`, and agent attach policies.

### Step 4: Verify Policy for the Exact Release

Read launcher docs, JEPs, and release notes for your target JDK. Confirm supported flags and active defaults.

### Step 5: Pick Target Modules

Prefer named modules over classpath-wide `ALL-UNNAMED` whenever architecture permits. Enable only modules with documented technical need.

### Step 6: Test with `deny` Mode in Test Environments

Where the JDK supports `--illegal-native-access=deny`, pair it with exact module enablements and exercise critical JNI/FFM flows.

### Step 7: Validate Native Binaries

Confirm library paths, OS/arch/ABI, signatures, memory lifetimes, and crash handling. Permission flags never certify native binary health.

### Step 8: Align Every Launcher

Verify test JVMs, app launchers, worker containers, batch jobs, and helper processes each carry **the exact options they need**. Never blanket-copy permissions across unrelated processes.

### Step 9: Save Evidence and Evolve Under Control

Store support matrices, logs, test reports, dependency versions, enabled permissions, and accepted exceptions. When future JDKs tighten defaults, you will have full context without guesswork.

## 24. Common Misconceptions

**“All JNI is banned starting in Java 24.”** False. JEP 472 prepares restriction mechanisms, defaulting to warnings for un-enabled modules in JDK 24; behavior depends on mode and release.

**“Zero warnings means native code is safe.”** False. Native libraries can still suffer memory, ABI, or logic bugs; warnings cover only access policy.

**“`--enable-native-access` eliminates every `UnsatisfiedLinkError`.”** False. Search paths, symbols, architectures, and OS native libraries require separate verification.

**“`--enable-native-access=ALL-UNNAMED` grants access only to `app.jar`.”** False. It enables all unnamed modules, normally broader than one JAR.

**“Setting `--illegal-native-access=allow` completes migration.”** False. It suppresses warnings/enforcement globally rather than declaring scoped permissions for the future.

**“`--add-opens` is the same as `--enable-native-access`.”** False. One governs deep reflection/package openness; the other governs restricted native operations.

**“`--enable-preview` suffices for every FFM call.”** False. Preview gating and native permissions are distinct; finalized FFM in JDK 22+ still enforces restricted methods.

**“Every Java agent needs `--enable-native-access`.”** False. Dynamic agent loading and native JNI/FFM operations are separate policies.

**“`-XX:+EnableDynamicAgentLoading` grants JNI permissions.”** False. That flag governs dynamic agent loading policy.

**“Enabling the main module is always enough.”** False. Permission must target the caller module executing the restricted operation, which may reside in a dependency.

**“Flags set on the Gradle daemon propagate to tests and production.”** False. Each JVM process has independent launch configuration.

**“JDK 24 flags will definitely run on JDK 17.”** False. Supported launcher flags differ by release.

**“Working on Linux x64 means native libraries run on Windows or ARM too.”** False. Native binaries and ABIs depend tightly on OS/architecture.

**“Clean `jnativescan` output proves zero native code is used.”** False. Static analysis covers only scanned artifacts and statically visible call patterns.

## 25. Pre-Release Checklist

- [ ] Recorded exact JDK feature/update/build, vendor, OS, and CPU architecture.
- [ ] Reviewed release notes and launcher options for the target JDK.
- [ ] Distinguished JNI, FFM, Java agents, JVMTI, and JPMS reflection.
- [ ] Inventoried direct, transitive, native dependencies, and agents.
- [ ] Identified classes/modules invoking restricted JNI/FFM operations.
- [ ] Executed `jnativescan` or equivalent checks where supported by the JDK.
- [ ] Covered static scan blind spots with runtime tests.
- [ ] Scoped `--enable-native-access` to named modules wherever feasible.
- [ ] Documented broad scope and justification if using `ALL-UNNAMED`.
- [ ] Verified `--illegal-native-access` support on the target JDK.
- [ ] Tested `deny` mode in test environments on supporting JDKs.
- [ ] Distinguished native permission errors from `UnsatisfiedLinkError` and native crashes.
- [ ] Confirmed `.so`/`.dll`/`.dylib` binaries, search paths, and ABIs match deployment targets.
- [ ] Verified FFM/JNI memory lifetimes, concurrency, and error propagation.
- [ ] Verified agent attach policies separately where applicable.
- [ ] Configured test, `JavaExec`, app, and container JVMs individually per need.
- [ ] Tested across every OS/JDK pair in the support matrix.
- [ ] Archived Java/native checksums, logs, test reports, and owners.
- [ ] Planned remediation ahead of stricter future JDK defaults.
- [ ] Avoided leaving broad `allow` mode or unreviewed workarounds as sign-off criteria.

## 26. Official References

Always verify against documentation matching your exact target JDK:

- **JEP 454 — Foreign Function & Memory API (JDK 22):** https://openjdk.org/jeps/454
- **JEP 472 — Prepare to Restrict the Use of JNI (JDK 24):** https://openjdk.org/jeps/472
- **JEP 451 — Prepare to Disallow the Dynamic Loading of Agents (JDK 21):** https://openjdk.org/jeps/451
- **JDK 25 — Restricted Methods:** https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html
- **JDK 24 — `jnativescan` command:** https://docs.oracle.com/en/java/javase/24/docs/specs/man/jnativescan.html
- **JDK 26 — `java` launcher:** https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html

These links confirm option meanings and scope on those releases. When adopting another JDK, read that release's docs without assuming legacy flags or defaults stay identical.

## Conclusion

**Native access permission is a per-JDK, per-module configuration decision—never a generic flag curing every native failure.** Even with FFM finalized since JDK 22, restricted methods remain gated; JEP 472 in JDK 24 brings JNI into the unified warning/restriction model alongside FFM, using `--enable-native-access` to grant permission and `--illegal-native-access` to govern missing permissions.

A durable migration separates JNI, FFM, reflection, Java agents, and native library loading; traces actual caller modules; prefers narrow configuration; validates under strict modes supported by the target JDK; and verifies native binaries, ABIs, OSs, and data separately. **Never equate vanishing warnings with safety or true compatibility.** When permissions are explicitly recorded, scoped tests pass, and artifacts remain traceable, applications evolve smoothly onto newer JDKs without relying on broad transitional allowances.
