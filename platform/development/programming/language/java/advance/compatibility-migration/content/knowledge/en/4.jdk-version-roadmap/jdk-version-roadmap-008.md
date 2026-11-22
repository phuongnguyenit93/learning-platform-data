# Upgrading JDK 21 to 25: Auditing Cumulative Changes Across Intermediate Releases

Upgrading from JDK 21 to JDK 25 spans four feature releases: JDK 22, 23, 24, and 25. Each brings changes to APIs, the language, the JVM, tooling, and runtime behavior. Reading only the JDK 25 release notes can miss changes introduced in an intermediate release that directly impact the application.

JDK 22, 23, and 24 are feature releases between milestones 21 and 25. Many organizations do not deploy production on each intermediate release, yet still need to understand their cumulative changes to pinpoint causes when building, testing, or running on JDK 25. JDK 25 is an LTS milestone in many vendors' support schedules; support lifetimes, patches, and update policies still depend on the vendor and JDK distribution chosen by the organization.

This lesson builds a systematic audit roadmap: identify per-release changes, assess impacts on source code and dependencies, verify JVM configuration, and validate the application on JDK 25.

## 1. Scope of an upgrade from 21 to 25

A JDK upgrade involves at least four compatibility layers:

1. **Source compatibility:** whether code still compiles against the new compiler, new APIs, and language changes.
2. **Binary compatibility:** whether class files, libraries, annotation processors, agents, and bytecode tools can read or load new formats and APIs.
3. **Behavioral compatibility:** whether the application continues working correctly when the JVM, garbage collector, thread scheduler, security, or standard libraries change.
4. **Operational compatibility:** whether startup scripts, container images, JVM flags, native libraries, monitoring, and release workflows remain valid.

Not every JDK change affects every application. For example, an application using pure Java without Security Manager, JNI, or ZGC may feel little impact from certain runtime shifts. Conversely, a system using native libraries, frameworks relying on deep reflection, agent instrumentation, or virtual threads requires deeper verification.

Separate three concepts in the plan:

- **Build JDK:** the compiler and tooling used to generate artifacts.
- **Test JDK:** the runtime executing unit tests, integration tests, and compatibility checks.
- **Production JDK:** the runtime actually running the application.

These three environments may share the same version, yet do not assume so by default. For example, you may build with JDK 25 while using release option 21 to emit bytecode and restrict APIs to Java 21, then test on both JDK 21 and JDK 25. If the product supports only JDK 25, both build target and runtime can move to 25 once dependencies are verified.

## 2. Change map from JDK 22 to JDK 25

The table below highlights representative changes likely to impact migration. It is not an exhaustive list of every JEP in each release; use it to guide inventory and testing.

| Release | Notable changes | Impacts to audit |
|---|---|---|
| JDK 22 | Foreign Function & Memory API finalized; unnamed variables and patterns finalized; multiple language and tool APIs remain in preview | Native interop code, libraries using Unsafe, source code using preview features, bytecode analysis tools |
| JDK 23 | Generational ZGC becomes default mode; sun.misc.Unsafe memory-access methods deprecated for removal; multiple language features remain preview | GC configuration, native/low-level dependencies, warning logs, frameworks and plugins |
| JDK 24 | Class-File API and Stream Gatherers finalized; Security Manager permanently disabled; ZGC drops non-generational mode; virtual threads no longer pin solely due to synchronized; JNI and Unsafe emit additional warnings | Security Manager, native access, GC flags, virtual-thread diagnostics, bytecode manipulation libraries |
| JDK 25 | Scoped Values, Module Import Declarations, Compact Source Files, and Flexible Constructor Bodies finalized; Applet API and remaining 32-bit x86 ports removed; warnings added on final-field mutation via reflection | Frameworks using reflection, legacy applet code, 32-bit hosts, source code and libraries depending on removed APIs |

When reading release notes, classify every change into three groups:

- **Breaking or removal:** APIs, ports, or runtime capabilities removed or rendered non-functional.
- **Behavioral or default change:** APIs remain present, yet behavior, defaults, or warnings changed.
- **New capability:** new features that usually cause no errors if unused; evaluate only when adopting them.

This classification avoids upgrading by toggling all new features simultaneously. First make the application run stably on JDK 25; only then decide whether to adopt new APIs or optimizations.

## 3. JDK 22: finalized native APIs and preview features

### 3.1. Foreign Function & Memory API finalized

JEP 454 finalized the Foreign Function & Memory API (FFM). This API provides a Java mechanism to work with off-heap memory and call native functions without necessarily hand-writing JNI wrappers.

Crucially for migration, pre-JDK 22 FFM versions went through multiple incubator or preview rounds and can differ markedly in packages, types, memory lifecycles, and how native calls are declared. If an application or library uses an older experimental preview, do not simply swap the JDK and assume compatibility. Upgrade the library or migrate code to the finalized API.

The example below illustrates off-heap memory allocation with Arena:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ForeignMemoryExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(100);

            segment.set(ValueLayout.JAVA_INT, 0, 42);
            int value = segment.get(ValueLayout.JAVA_INT, 0);

            System.out.println(value);
        }
    }
}
```

Arena manages memory region lifetimes. When the arena closes, the region is freed according to the API mechanism. This differs from holding an arbitrary native address and managing lifetimes manually. When migrating from JNI or Unsafe to FFM, clarify who owns memory, when memory expires, and whether data can be accessed concurrently.

FFM does not automatically replace every JNI use case. Libraries needing complex callbacks, long-standing native integrations, or custom ABIs still require careful testing. Nevertheless, for appropriate native calls and memory operations, FFM is Java's standard path to reduce reliance on internal APIs.

### 3.2. Unnamed Variables and Patterns

JEP 456 finalized unnamed variables and patterns. The underscore symbol can be used for variables or patterns whose values the program does not need to reference.

Example:

```java
try {
    process();
} catch (IOException _) {
    logFailure();
}
```

This feature primarily improves readability and removes unused variables. When upgrading the compiler, check source levels and code analysis libraries if they parse Java syntax themselves. An outdated parser may fail to recognize new syntax even when the JDK compiler supports it.

### 3.3. Class-File API in preview

JEP 457 introduced the Class-File API in preview. This API aims to read, generate, and transform class files using a standard JDK API.

If the project uses ASM, Byte Buddy, Javassist, or custom bytecode tools, verify whether library versions support the new class files and JDK. Class-File API preview does not mean existing libraries must switch to it immediately. It is an opportunity to evaluate long-term direction, not a reason to swap all bytecode tooling in one migration.

The Class-File API became standard only in JDK 24. Therefore, experimental code written on JDK 22 must be updated to the final API if the project chooses to use it.

### 3.4. Stream Gatherers and concurrency features in preview

JDK 22 introduced Stream Gatherers in preview via JEP 461. Gatherers let developers define custom intermediate operations in the Stream API. This feature continued evolving before stabilizing in JDK 24.

Structured Concurrency and Scoped Values also continued in preview in JDK 22. Other language features such as flexible constructor bodies, implicitly declared classes, and instance main methods also had preview rounds.

When auditing source code, search for:

- The **--enable-preview** option in compiler and runtime configs.
- Annotations or APIs belonging to preview packages.
- Test, IDE, and build plugin configurations enabling preview.
- Internal libraries packaging class files compiled with preview features.

Preview features are tied to a specific release. Class files or source code using JDK 21 previews cannot be assumed automatically compatible with JDK 25 previews. If production policy forbids preview APIs, remove or replace them before completing migration.

### 3.5. Tooling and documentation changes

JEP 458 allows launching multi-file source programs directly from the launcher in certain cases without manual pre-compilation. This improves developer and scripting ergonomics; it does not alter standard production application packaging.

JEP 467 supports Markdown in documentation comments. If the project runs Javadoc pipelines or comment linters, confirm tool versions handle the new format properly. This typically has low runtime impact.

## 4. JDK 23: ZGC default change and Unsafe warnings

### 4.1. Generational ZGC becomes default

JEP 474 makes Generational ZGC the default mode when selecting ZGC. Generational ZGC separates objects by age to exploit the fact that most objects are short-lived.

JDK 21 already shipped Generational ZGC, yet operators had to opt in explicitly via flags. Starting in JDK 23, applications selecting ZGC use generational mode by default. This means an unchanged JVM config can yield different GC behavior after changing the JDK, even with zero code edits.

Verify:

- Whether startup scripts enable **-XX:+UseZGC**.
- Whether flags toggling generational mode remain from JDK 21.
- Whether dashboards assume legacy GC log names or structures.
- How heap size, allocation rate, pause times, and throughput shift under real workloads.
- Whether libraries or agents rely on GC implementation details.

By JDK 24, non-generational ZGC mode was removed. Therefore, legacy configurations forcing that mode must be audited and removed. Never copy all JVM flags verbatim from JDK 21 to JDK 25; validate every flag against the target runtime.

### 4.2. Memory-access methods in sun.misc.Unsafe deprecated for removal

JEP 471 deprecated for removal the memory-access methods in **sun.misc.Unsafe**. This is a critical warning for frameworks, serializers, high-performance libraries, concurrency utilities, and native interop code.

Not the entire Unsafe class is removed immediately. The scope centers on memory-access methods specified in the JEP. Still, dependencies calling those methods may keep running while emitting warnings, and then face tighter restrictions in later JDKs.

Remediation varies by intent:

| Current need | Replacement direction to consider |
|---|---|
| Type-safe field or array access | VarHandle |
| Off-heap memory allocation and access | Foreign Function & Memory API |
| Invoking native functions | Foreign Function & Memory API or explicitly managed JNI |
| Bytecode or runtime internals manipulation | Standard APIs, Class-File API, or updated libraries |
| Using Unsafe via third-party dependency | Upgrade dependency to a release addressing warnings |

Do not write a custom wrapper around Unsafe and consider the issue resolved. Wrappers still depend on the deprecated API. Identify which library invokes those methods, check the vendor roadmap, and plan replacement.

### 4.3. Auditing dependencies and source compatibility

JDK 23 kept language features in preview, including primitive types in patterns, **instanceof**, and **switch**; module import declarations; flexible constructor bodies; plus structured concurrency and scoped values.

These features can change between preview rounds. If project source uses them, re-verify against the exact release. If using only Java 21 language level, most apps need no code changes due to these previews.

For dependencies, inspect libraries generating or analyzing bytecode, annotation processors, compiler plugins, agents, and reflection-driven frameworks. Libraries compiled earlier are not guaranteed to work properly on the new runtime.

## 5. JDK 24: major changes in Security Manager, native access, and runtime

### 5.1. Security Manager permanently disabled

JEP 486 permanently disables the Security Manager. Applications can no longer rely on this mechanism to enforce permission policies inside the JVM.

If an application or library calls **System.setSecurityManager**, enables Security Manager via legacy startup options, or expects permission checks to be enforced, treat this as a mandatory migration item. Calling **System.setSecurityManager** can no longer install a Security Manager and can throw **UnsupportedOperationException**; **System.getSecurityManager** does not provide an active Security Manager.

Search source code and configuration for:

- **System.setSecurityManager(...)** and **System.getSecurityManager()**.
- **java.security.Policy** and legacy policy files.
- Custom **SecurityManager** subclasses.
- **-Djava.security.manager** options in scripts.
- Frameworks or libraries relying on Security Manager permission checks.

Security Manager is not a suitable sandbox for modern applications. If the goal is restricting process privileges, move controls to OS and infrastructure boundaries: dedicated service accounts, least-privilege filesystem permissions, container isolation, network policies, and secret access controls. These must be designed per the system's threat model rather than a mechanical API rename.

### 5.2. JNI and native access begin emitting warnings

JEP 472 prepares restrictions on JNI usage. JDK 24 warns when an application performs native access without the owning module declaring the corresponding permission. The goal is surfacing places where code steps outside JVM safety boundaries and preparing for stricter policies in future releases.

If the application uses JNI or libraries loading native libraries:

1. Inventory call sites of **System.load**, **System.loadLibrary**, and native methods.
2. Identify the module owning each native access call.
3. Upgrade native libraries and wrappers to support current permission mechanisms.
4. Configure explicit native access permissions for required modules.
5. Monitor warnings on JDK 24 and confirm behavior on JDK 25.

For classpath applications not split into named modules, **--enable-native-access=ALL-UNNAMED** can grant native access to unnamed modules. For modular applications, name specific modules requiring permission, e.g., **--enable-native-access=com.example.nativebridge**. Scope permissions narrowly rather than granting broadly to all modules if architecture permits restriction.

This option does not make a wrong-architecture or wrong-ABI native library compatible. It only addresses JVM native-access authorization.

### 5.3. ZGC drops non-generational mode

JEP 490 removes non-generational ZGC mode. This follows making generational mode default in JDK 23.

If deployment configs ever disabled generational ZGC, remove those flags and confirm the target JVM boots normally. Audit every place storing JVM flags: Dockerfiles, Helm charts, systemd units, scripts, environment variables, pipelines, and service manager configs.

Do not judge GC from a single short benchmark. Compare workloads matching production allocation rates, live sets, concurrency, and run duration.

### 5.4. Virtual threads no longer pin solely due to synchronized

JEP 491 changes how virtual threads interact with monitors. Prior to JDK 24, virtual threads could pin to carrier threads when entering certain **synchronized** blocks; if blocking operations ran inside, scalability could suffer.

Starting in JDK 24, virtual threads can unmount from carriers in these monitor scenarios, so using synchronized by itself no longer causes the old pinning behavior. This helps virtual-thread applications, though not every cause of pinning disappears. Native methods and certain operations outside the JVM still require checking.

If code was previously rewritten from synchronized to **ReentrantLock** solely to dodge monitor pinning, re-evaluate designs via benchmarking and profiling. Blanket rewrites are unnecessary if the current structure is sound. Meanwhile, monitor contention still carries cost: eliminating pinning does not make heavily contended locks free.

### 5.5. Unsafe emits runtime warnings

Following deprecation for removal of **sun.misc.Unsafe** memory-access methods in JDK 23, JEP 498 adds runtime warnings when they are invoked. This is a signal to locate dependencies still calling these APIs.

Warnings may originate from third-party libraries rather than business code. Capture stack traces or caller info whenever possible, then upgrade dependencies or replace integrations. Do not suppress warnings before identifying the caller and remediation plan.

### 5.6. Class-File API and Stream Gatherers finalized

Two notable finalizations in JDK 24:

- JEP 484 finalized the Class-File API, offering a standard API to parse, generate, and transform class files.
- JEP 485 finalized Stream Gatherers, enabling custom intermediate transformations for Streams.

If the project trialed earlier previews, migrate to the finalized APIs and verify signature, package, semantic, and compiler-config changes. If unused, there is no need to adopt them just because they stabilized.

For the Class-File API, prioritize checking bytecode libraries and instrumentation agents. These tools are sensitive to class-file versions, bytecode structure, and JVM changes. An application may boot normally yet fail when an agent transforms classes or a framework generates proxies.

### 5.7. Ahead-of-Time Class Loading & Linking

JEP 483 introduces Ahead-of-Time Class Loading & Linking to reduce startup and warm-up overhead in suitable scenarios. This can help short-lived apps, serverless functions, or workloads needing fast readiness.

This is a performance optimization, not a requirement to run on JDK 24 or 25. Before adopting it, measure baseline startup time and memory footprint, build caches matching the exact app and runtime, and compare in the target deployment environment. Do not reuse caches generated from configurations incompatible with the target runtime.

### 5.8. Other JDK 24 changes

JDK 24 also adds post-quantum cryptographic algorithms such as ML-KEM and ML-DSA to the JDK security libraries. If the app selects providers or algorithms explicitly by name, review provider lists, security policies, and partner interoperability. Adding new algorithms does not automatically switch existing systems to use them.

JDK 24 removed the Windows 32-bit x86 port. If the organization still operates 32-bit workstations, runners, or deployment devices, re-evaluate supported architectures and plan migration to suitable 64-bit platforms.

## 6. JDK 25: target milestone and changes to handle

### 6.1. Language features and APIs finalized

JDK 25 finalized several features after multiple preview rounds:

| Feature | Status in JDK 25 | Significance |
|---|---|---|
| Scoped Values | Final (JEP 506) | Shares immutable data across execution scopes, suited to certain concurrency models |
| Module Import Declarations | Final (JEP 511) | Imports modules to reduce scattered imports in source files |
| Compact Source Files and Instance Main Methods | Final (JEP 512) | Writes small programs with less boilerplate structure |
| Flexible Constructor Bodies | Final (JEP 513) | Allows certain statements before superclass constructor invocations |

Adopting these features in existing apps is optional. If source already used earlier previews, check the finalized API and drop preview flags when moving to the standard version. If unused, existing source style can remain unchanged.

Structured Concurrency remains in preview in JDK 25. Primitive types in patterns, **instanceof**, and **switch** also remain in preview. Vector API remains incubator. Do not treat these APIs as stable production contracts unless the project accepts release-to-release churn risk.

### 6.2. Applet API removed

JEP 504 removes the Applet API. Applications or libraries still referencing **java.applet** may fail to compile on JDK 25. These are usually remnants of legacy desktop/web software, obsolete browser plugins, or unmaintained libraries.

Search for references such as:

- **java.applet.Applet**.
- **AppletContext**, **AppletStub**, and related types.
- Code initializing or passing data around applet lifecycles.
- Legacy dependencies kept solely for applet support.

If the capability is still needed, choose an alternative deployment model such as a web app, desktop app, or service. Simply deleting imports to make builds pass is insufficient if business flows rely on applet lifecycles.

### 6.3. Remaining 32-bit x86 ports removed

After Windows 32-bit x86 removal in JDK 24, JDK 25 removes the remaining 32-bit x86 ports. 32-bit Java runtimes should be treated as a separate compatibility track, not just a JDK swap.

Inventory:

- Servers or devices still running 32-bit OSes.
- CI runners, build hosts, and test environments.
- Native libraries offering only 32-bit binaries.
- Install scripts or package managers fetching JDKs for legacy architectures.
- Memory constraints or external software requiring 32-bit processes.

If the product still depends on 32-bit, migrate JVM, native dependencies, and OS together to a supported 64-bit combination. Changing only the JDK cannot resolve 32-bit native dependencies or end-of-life OSes.

### 6.4. Preparing for restrictions on mutating final fields via reflection

JEP 500 prepares to give the **final** keyword stronger integrity for fields. JDK 25 warns when deep reflection mutates final fields in unsupported cases and sets the stage for stricter enforcement ahead.

Serialization frameworks, dependency injection containers, ORMs, mocking libraries, and config binders may use reflection to write fields after object construction. If those frameworks mutate final fields, watch for JDK 25 warnings and upgrade to versions supporting proper instantiation.

Design practices to prefer:

- Construct objects via constructors or factories.
- Use official framework APIs instead of manual field-mutating reflection.
- Use library-supported serialization mechanisms.
- Keep final fields immutable after object construction.
- Grant special access only to code strictly requiring it, under appropriate JVM policies and module scope.

Do not blindly strip `final` off every field merely to silence warnings. Identify which framework mutates the field, because stripping `final` can weaken object invariants and thread safety.

### 6.5. Garbage collection and object layout changes

JDK 25 introduces performance and GC enhancements to evaluate on real workloads:

- **Compact Object Headers (JEP 519):** introduces a mechanism reducing object header size in supported configurations. Because this alters object memory layout, verify libraries relying on internal memory layout, agents, and heap analyzers before enabling.
- **Generational Shenandoah (JEP 521):** adds generational mode to Shenandoah. Evaluate only if the system uses or plans to test Shenandoah.
- **G1 throughput improvements (JEP 522):** improves throughput by reducing certain synchronization points. Real gains depend on workload, heap, and configuration.
- **AOT command-line ergonomics and method profiling (JEP 514, JEP 515):** streamlines ahead-of-time workflows and aids warm-up optimization.

These features are optimization opportunities after migration stabilizes. Do not toggle multiple GC, object layout, and AOT changes simultaneously and attribute performance shifts to the JDK alone. Change one group at a time, measure identical workloads, and save exact JVM flags.

### 6.6. JFR and cryptography

JDK 25 expands observability in Java Flight Recorder, including CPU-time profiling, cooperative sampling, and method timing/tracing. These enhancements aid diagnosing CPU, latency, and method behavior. Verify that JFR analysis tools used by operations support the new events.

JDK 25 also adds the Key Derivation Function API (JEP 510). If the app derives cryptographic keys, evaluate this standard API alongside system key-management policies. Never alter algorithms, key sizes, or secret storage workflows merely because the JDK added a new API.

## 7. Cross-cutting checks across all four intermediate releases

### 7.1. Removed, deprecated, or access-restricted APIs

Compile an inventory of APIs with special lifecycles. Deprecated does not mean deleted immediately, yet **forRemoval** signals a need to plan replacement.

Priority audit areas:

| Area | Change in 21 → 25 roadmap | Required action |
|---|---|---|
| Security Manager | Permanently disabled in JDK 24 | Find code and configs still enabling or checking permissions |
| Applet API | Removed in JDK 25 | Find dependencies and source referencing java.applet |
| sun.misc.Unsafe | Memory-access methods deprecated for removal in 23, runtime warnings in 24 | Identify callers, upgrade, or migrate to standard APIs |
| JNI/native access | JDK 24 begins warnings and prepares tightening | Inventory native calls and declare permissions for needed modules |
| Final field reflection | JDK 25 warns ahead of future restrictions | Upgrade frameworks and remove unsupported final-field mutation |
| 32-bit x86 | Ports removed across JDK 24 and 25 | Check OS, JVM, runners, and native dependencies |

Beyond the items above, run analysis tools across artifacts and dependencies to spot internal JDK APIs. Packages like **sun.*** or **com.sun.*** are not always stable public APIs. If the application depends on them, find replacement APIs or upgrade the owning library.

### 7.2. Preview, incubator, and standard APIs

Preview and incubator features exist to allow experimentation, gather feedback, and refine designs before stabilization. They carry no long-term compatibility commitment.

Along the 21 → 25 path, some features passed through preview rounds before finalizing—such as Scoped Values, Module Import Declarations, Flexible Constructor Bodies, and compact source files. Others remain preview or incubator in JDK 25.

Migration rules:

1. Locate every place enabling **--enable-preview**.
2. Identify which source code and class files genuinely depend on preview features.
3. Check the feature's status in JDK 25: finalized, still preview, or withdrawn from the release.
4. If finalized, migrate code to the final API and drop preview flags if no longer needed.
5. If still preview, keep only if the project accepts API churn and schedules per-release updates.
6. If withdrawn, replace with stable APIs or an alternative design.

Do not enable **--enable-preview** globally just to make an experimental module compile. Isolate experimental source sets or modules so preview scope stays controlled.

### 7.3. Bytecode and class-file versions

Each Java release corresponds to a class-file version. JDK 21 emits major version 65; JDK 22 emits 66; JDK 23 emits 67; JDK 24 emits 68; JDK 25 emits 69.

Newer runtimes usually run older bytecode if used APIs remain compatible. Older runtimes cannot run class files compiled for newer releases. Hence, explicitly establish the minimum supported runtime version.

Use **--release** to lock source compatibility, bytecode target, and allowed standard APIs together:

```shell
javac --release 21 -d out src/com/example/Main.java
```

If building with JDK 25 while wanting artifacts to keep running on Java 21, keep **--release 21**. If moving the product completely to Java 25, set release target 25 once dependencies and runtime are validated.

Do not set only source and target flags assuming APIs are restricted. **--release** instructs the compiler to enforce the target release's API surface, reducing accidental new-API calls while emitting older bytecode.

### 7.4. Build tools, plugins, and third-party libraries

Upgrading runtime can expose build-tool failures before application code even runs. Inspect:

- Maven or Gradle wrappers and compiler plugins.
- Annotation processors such as Lombok or custom processors.
- Test engines, mocking frameworks, and proxy generators.
- Bytecode libraries such as ASM, Byte Buddy, or Javassist.
- Code coverage, static analysis, mutation testing, and security scanners.
- Web frameworks, DI, ORM, logging, and serialization.
- JDBC drivers, database clients, and message broker clients.
- Java agents, profilers, APMs, and monitoring agents.
- Native Image or specialized toolchains if used by the project.

Do not update only the JDK while leaving multi-year-old plugins untouched. Conversely, avoid upgrading unrelated dependencies in the same change. Identify minimum JDK 25-supporting versions, upgrade directly coupled groups, and run tests to isolate causes.

Check JDK support documentation from dependency vendors. A library may compile cleanly yet misbehave on the new runtime, or require extra reflection/native access flags.

### 7.5. Reflection, instrumentation, and class loading

Java frameworks often use reflection to generate proxies, inject dependencies, serialize objects, or invoke methods dynamically. Agents may transform bytecode at startup. These mechanisms are sensitive to:

- Module strong encapsulation.
- Package open/export permissions via **--add-opens** or **--add-exports**.
- Final-field mutation restrictions.
- Class-file versions and bytecode attributes.
- How the JVM loads and links classes.
- Native access permissions if agents call JNI.

Do not add **--add-opens** wholesale to mask all errors. Read warnings, identify which module and package need opening, check framework upgrades, and grant the minimal required scope. Broad package opens hide internal API reliance and raise future upgrade costs.

### 7.6. Threading and concurrency

If using virtual threads, verify blocking behavior, monitors, native calls, and thread-local data. JDK 24 improved monitor pinning with synchronized, yet applications can still hit lock contention, bounded pools, long native calls, or external resource limits.

If trialing Structured Concurrency or Scoped Values from preview, verify finalized APIs in JDK 25. Scoped Values finalized, whereas Structured Concurrency remains preview. Do not treat them as having identical stability.

If the application uses ThreadLocal for context propagation, do not rewrite everything to Scoped Values solely because the API finalized. Evaluate context semantics, lifetimes, mutability, and framework integration first.

### 7.7. GC, memory, and performance

Performance can shift even with unchanged code. Record JDK 21 baselines and compare against JDK 25 using identical data and conditions.

Metrics to track:

- Startup time and time to steady state.
- Throughput and p50/p95/p99 latency.
- Heap occupancy, allocation rate, and live set.
- GC pauses, concurrent cycles, and CPU overhead.
- Native memory, direct buffers, and thread counts.
- CPU utilization, context switching, and lock contention.
- Error rates, timeouts, and retries on integration paths.

If using ZGC, watch the default generational switch in 23 and non-generational removal in 24. If using G1 or Shenandoah, evaluate JDK 25 performance shifts via representative benchmarks. Avoid changing the default collector or heap flags concurrently with the JDK upgrade unless clearly justified.

### 7.8. Security and cryptography

Audit:

- JCA/JCE providers and algorithms explicitly named by the app.
- TLS handshakes, trust stores, certificate chains, and proxies.
- Keystore formats, key algorithms, and key sizes.
- Native libraries or external JVM security providers.
- Legacy Security Manager policies.
- JNI/native access and module permissions.
- Secrets, tokens, and credentials passed via environment variables or files.

A newer JDK may introduce algorithms without partner systems supporting them yet. Test interoperability at both ends. Do not change production cryptographic algorithms solely because a JDK provider added a new one.

## 8. Recommended migration workflow

### Phase 1: Capture baseline on JDK 21

Before changing anything, preserve the current state:

1. JDK 21 vendor and build version.
2. Maven/Gradle wrapper, compiler plugins, and build plugins.
3. Dependency tree and framework versions.
4. JVM flags, GC, heap, module flags, and native access flags.
5. Container base image or deployment OS.
6. Unit tests, integration tests, startup times, and performance metrics.
7. Existing warnings, especially deprecation, reflection, and native code.

Baselines must be detailed enough for comparison. Simply noting "build passed" makes isolating runtime or performance shifts difficult.

### Phase 2: Inventory risks in source and dependencies

Locate specific dependencies on:

- **System.setSecurityManager** and policy classes.
- **java.applet**.
- **sun.misc.Unsafe** and internal packages.
- JNI, **System.load**, **System.loadLibrary**, and FFM.
- **--enable-preview** and preview APIs.
- **--add-opens**, **--add-exports**, and reflective access.
- Frameworks mutating final fields.
- Virtual threads, **synchronized**, and blocking native calls.
- Generational/non-generational ZGC flags.
- Agents and bytecode manipulation libraries.

Categorize each hit by severity:

| Severity | Meaning | Examples |
|---|---|---|
| High | Can break builds or startup, or remove an active security mechanism | Applet API removed, Security Manager disabled, 32-bit JDK gone |
| Medium | Can trigger warnings, behavior shifts, or errors on specific code paths | JNI native access, Unsafe, final-field reflection, ZGC flags |
| Low | Mainly affects tooling, syntax, or new optional optimizations | Markdown Javadoc, multi-file launcher, new JFR events |

Actual risk depends on whether the app uses that component. Never flag an item high-risk merely because a JEP exists; find concrete evidence in source, dependency trees, configs, and runtime logs.

### Phase 3: Update build tools and constrained dependencies

Before shifting production runtime, update tooling required to run on JDK 25:

- Pick Maven/Gradle and plugin versions supporting JDK 25.
- Update compiler, test engines, and annotation processors.
- Update frameworks and agents dealing with reflection, bytecode, or native access.
- Check native dependencies per OS/architecture.
- Keep dependency locks or management for reproducible builds.

You may temporarily retain **--release 21** during this phase if runtime 21 must remain supported. That separates toolchain failures from new source/API target failures.

### Phase 4: Add JDK 25 to CI

Create a CI job using JDK 25 and run the existing test suite. If possible, keep a JDK 21 job to verify backward compatibility during transition.

Deploying production onto JDK 22, 23, and 24 is unnecessary. Still, if an unexplained error surfaces on JDK 25, intermediate releases can help bisect which release changed behavior. When bisecting, record each JDK's vendor/build and test the exact same artifact or commit.

### Phase 5: Resolve warnings before they become errors

Run the application and tests on JDK 25 and collect warnings on:

- Unsafe memory access.
- JNI/native access.
- Final-field mutation.
- Deprecated or for-removal APIs.
- Preview features and module access.
- Unsupported GC flags.

For each warning, record caller, owning dependency, impact, upgrade or replacement path, and owner. Do not suppress warnings globally before tracing their root source.

### Phase 6: Integration testing in real deployment environments

Run on the exact target OS, architecture, container image, and service account. Verify especially:

- Native libraries pick the right variant and load cleanly.
- Modules have needed native and package access.
- Framework reflection/serialization/ORM operate properly.
- Virtual threads and blocking calls hit target throughput.
- GC and memory usage meet SLOs.
- TLS, database, messaging, and file I/O work.
- Monitoring agents, profilers, and JFR still collect telemetry.
- Startup scripts, health checks, and shutdown hooks work.

### Phase 7: Canary and rollout

Deploy a fraction of workload on JDK 25 first. Compare errors, latency, CPU, memory, GC, startup, and retry rates against baseline. Expand traffic only when metrics stay within accepted bounds.

Preserve rollback capability by retaining known-good JDK 21 artifacts, images, and configs. If bytecode targets, dependencies, or data schemas changed, confirm rollback is not blocked by incompatible changes.

## 9. Commands and inspection utilities

### 9.1. Confirm actual toolchains

Run inside the exact terminal or container used by CI/production:

```shell
java -version
javac -version
mvn -version
./gradlew --version
```

Not every project uses both Maven and Gradle. The goal is confirming runtimes of the build tool, compiler, and application JVM. A host may hold multiple JDKs; **JAVA_HOME** and **PATH** do not necessarily point to the same installation.

### 9.2. Find dependencies using internal JDK APIs

Use jdeps to detect JDK internal dependencies:

```shell
jdeps --jdk-internals application.jar
```

If results point to third-party libraries, identify the artifact and upgrade or replace it. Do not automatically treat every **com.sun** package as an error; read results accurately and check whether the API is publicly supported.

### 9.3. Check deprecated or for-removal APIs

Use jdeprscan to scan artifacts against the target release:

```shell
jdeprscan --release 25 --for-removal application.jar
```

Results serve as investigation signals rather than replacing compilation and tests. Some dependencies load dynamically or reflectively and escape full static detection.

### 9.4. Check class-file versions

Use javap to inspect class file details:

```shell
javap -verbose -classpath application.jar com.example.Main
```

Look for **major version** in output. Compare against the minimum runtime supported by the product. For multi-release JARs, inspect versioned entries as well.

### 9.5. Monitor GC and runtime

Enable GC logging during test runs if needed:

```shell
java -Xlog:gc* -jar application.jar
```

For profiling, run Java Flight Recorder on a representative workload and analyze with JDK 25-compatible tools. Record full JVM flags, heap sizes, and container limits for meaningful comparison.

Do not leave verbose logging enabled indefinitely in production without sizing storage and operational cost. Use controlled configs, collect over bounded windows, and protect log files under organizational data policies.

## 10. Common failure scenarios when moving to JDK 25

### Scenario 1: Build fails because Applet API is missing

**Possible cause:** source or dependency still references **java.applet**, removed in JDK 25.

**Remediation:** locate the owning module, check whether applet functionality is needed, then redesign architecture or upgrade the dependency. If the old library is unmaintained, evaluate removing or replacing it.

### Scenario 2: Application fails to enable Security Manager

**Possible cause:** scripts pass Security Manager flags or code calls **System.setSecurityManager**.

**Remediation:** drop assumptions that the JVM enforces Security Manager. Move privilege controls to OS/container/network policies and redesign code relying on permission checks.

### Scenario 3: Warning when loading a native library

**Possible cause:** module lacks native access declaration, library uses JNI, or the new runtime warns on native behavior.

**Remediation:** identify module and caller, update dependencies, grant scoped native access. Separately verify OS, architecture, and library ABI.

### Scenario 4: Warnings or errors from Unsafe

**Possible cause:** serializers, concurrency utilities, memory-mapping tools, or high-performance frameworks still call **sun.misc.Unsafe** memory-access methods.

**Remediation:** trace stack and dependency versions, upgrade libraries, check migration paths to VarHandle or FFM. Do not merely filter warnings out of logs.

### Scenario 5: GC behaves differently after enabling ZGC

**Possible cause:** JDK 23 made generational mode default and JDK 24 removed non-generational mode.

**Remediation:** audit JVM flags, benchmark identical workloads, compare pauses, throughput, CPU, and memory. Tune based on data instead of restoring removed flags.

### Scenario 6: Framework or serializer warns when writing final fields

**Possible cause:** framework uses deep reflection to mutate final fields post-construction.

**Remediation:** update the framework, use constructors or supported serialization APIs, and verify object invariants. Pinpoint which dependency needs remediation before future restrictions tighten.

### Scenario 7: Agent or framework fails to process class files

**Possible cause:** agent, ASM, Byte Buddy, or similar tool lacks support for the new class-file version or runtime.

**Remediation:** upgrade agents and bytecode libraries, check vendor compatibility matrices, run integration tests with real startup options. Temporarily removing an agent in test helps isolate issues, yet is not a production fix for mandatory agents.

### Scenario 8: Application runs yet performance regresses

**Possible cause:** GC mode, JIT warm-up, heap/container sizing, dependencies, or workload shifted vs baseline.

**Remediation:** compare JFR, GC logs, allocations, CPU, lock contention, and latency. Change one configuration group at a time to isolate effects.

## 11. Checklist for completing JDK 21 to 25 migration

### Source code and APIs

- [ ] Audited Security Manager usage and removed assumptions relying on it.
- [ ] Audited **java.applet** references and handled affected dependencies.
- [ ] Inventoried **sun.misc.Unsafe** and internal JDK APIs.
- [ ] Audited **--enable-preview** and active preview APIs.
- [ ] Audited reflection mutating final fields.
- [ ] Audited JNI, FFM, and native access.

### Build and dependencies

- [ ] Maven/Gradle wrappers and plugins support JDK 25.
- [ ] Annotation processors, test engines, mocking frameworks, and compiler plugins are compatible.
- [ ] Bytecode libraries and Java agents support the target runtime.
- [ ] Frameworks, JDBC drivers, and integration libraries verified.
- [ ] **--release** matches the minimum runtime the product commits to support.
- [ ] Artifact builds are reproducible and dependencies locked per project process.

### Runtime and deployment

- [ ] JVM flags audited for JDK 25.
- [ ] Legacy ZGC flags audited; no remaining requests for non-generational mode.
- [ ] Native libraries match target OS, architecture, and ABI.
- [ ] Container base images and OSes meet 64-bit requirements.
- [ ] Startup, shutdown, health check scripts, and service accounts verified.
- [ ] TLS, trust stores, databases, and messaging verified.

### Testing and release

- [ ] Unit tests and integration tests pass on JDK 25.
- [ ] Tests exercising reflection, serialization, proxies, and instrumentation executed.
- [ ] Native library loading and native function calls verified.
- [ ] GC, memory, startup, and throughput compared against JDK 21 baseline.
- [ ] Deprecation, Unsafe, JNI, and final-field mutation warnings have assigned owners.
- [ ] Canary meets SLO thresholds.
- [ ] Rollback artifacts, images, and configs preserved.

## Conclusion

Upgrading JDK 21 to JDK 25 requires auditing all four intermediate releases because key changes landed before the final milestone. JDK 22 finalized FFM; JDK 23 made Generational ZGC default and deprecated Unsafe memory-access methods; JDK 24 disabled Security Manager, adjusted virtual threads, finalized Class-File API and Stream Gatherers, and began warning on JNI; JDK 25 finalized several preview APIs, removed the Applet API, and continued dropping 32-bit platforms.

Start from the JDK 21 baseline, inventory source and dependencies, update toolchains, run CI on JDK 25, address warnings, and test inside the real deployment environment. Broaden rollout only after behavior, performance, and operations are confirmed. This approach pinpoints exactly which change affects the app while keeping migration verifiable, repeatable, and reversible if needed.
