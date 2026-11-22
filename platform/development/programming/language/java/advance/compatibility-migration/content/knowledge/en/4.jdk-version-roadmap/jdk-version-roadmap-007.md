# Upgrading JDK 17 to 21: Default Behaviors and Library Compatibility

Upgrading from JDK 17 to JDK 21 brings significant benefits: platform updates, performance and security improvements, new Java APIs, and the option to adopt virtual threads for high-concurrency I/O systems. However, changing the JDK running an application is not just changing a value in `JAVA_HOME`. Default behaviors of several APIs changed across JDK 18–21; libraries, frameworks, build plugins, annotation processors, and test tools must also support the new JDK.

In particular, a project can compile cleanly yet still fail at startup, when generating proxies via reflection, when running a test agent, or when reading text files whose encoding relied on OS defaults. A dependency may support JDK 21 at the bytecode level yet not support the framework version currently in use. A plugin may fail to run on JDK 21 even when the application is configured to compile targeting Java 17.

To keep the migration controlled, clearly define compatibility targets, identify changes from JDK 17 to 21, inventory libraries per classpath, upgrade build tools and plugins according to support matrices, and verify the artifact on the target runtime. This lesson focuses on practical differences of JDK 17 → 21 and how to assess compatibility across the entire library ecosystem.

## 1. Define the exact upgrade target

Before changing anything, separate the concepts often conflated as "Java version":

| Component | Role | What to confirm |
|---|---|---|
| JDK running Gradle/Maven | JVM launching the build process and build plugins | Do the Wrapper, plugins, and build logic run on JDK 21? |
| JDK compiler/toolchain | Compiler compiling source | Does the compiler understand the target language and APIs? |
| Source/API target | Language, bytecode, and Java API level the artifact commits to support | Does the artifact still need to run on Java 17? |
| JDK runtime | Actual JVM launching the application | Do containers, servers, CI, and production actually run JDK 21? |
| Framework/dependencies | Libraries and platform loaded by the application | Do their versions support JDK 21 and work together? |

Two migration directions have distinct targets:

**Path A — move runtime to Java 21:** the application will run on JDK 21 and may use Java 21 APIs. The compiler can set `--release 21` if maintaining execution on Java 17 is unnecessary.

**Path B — use JDK 21 to build while still supporting Java 17 runtime:** the compiler runs on JDK 21 while keeping source/API target at Java 17, typically via toolchains and `--release 17`. This suits libraries or products releasing artifacts that must run on runtime 17 as well. However, processors, plugins, and build tools must still run on JDK 21; and the artifact must be tested on both runtime 17 and 21.

Do not conclude a project has "moved to Java 21" merely because `java -version` prints 21. Record the build JDK, compiler JDK, API/bytecode level, and artifact runtime JDK separately.

## 2. Notable changes from JDK 17 to JDK 21

JDK 21 accumulates changes from releases 18, 19, 20, and 21. Not all of them alter behavior of running applications. Categorize them into default changes, new APIs, optional features, preview features, and tooling changes.

### 2.1. Default charset switches to UTF-8

**Point of attention:** audit every text stream.

The most broadly impactful default-behavior change is JEP 400, introduced in JDK 18. On JDK 17, the JVM default charset typically depended on the OS locale and configuration. For instance, Windows machines might use a local code page while Linux machines usually used UTF-8. Starting in JDK 18, UTF-8 becomes the default charset for Java APIs that use the default charset, unless a JDK-defined compatibility mechanism is configured.

This can change how code relying on the default charset reads or writes data. APIs to audit include:

- `new String(byte[])` and `String.getBytes()` without passing a charset.
- `FileReader` and `FileWriter` using constructors that omit charset.
- `InputStreamReader` and `OutputStreamWriter` without passing a charset.
- `Scanner` or `Formatter` when calling overloads that rely on the default charset.
- Text file reading/writing libraries whose documentation states they use the default charset.
- Scripts, config files, CSVs, logs, import/export data, and files exchanged with legacy systems.

Common example:

```java
// Depends on the JVM default charset.
String content = new String(bytes);
byte[] output = content.getBytes();

// Explicitly specify the protocol/file encoding.
String utf8Content = new String(bytes, StandardCharsets.UTF_8);
byte[] utf8Output = content.getBytes(StandardCharsets.UTF_8);
```

For files, specify the charset directly at the read/write API:

```java
Path path = Path.of("data", "customers.csv");

String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);

try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    // Read line by line and process data.
}
```

`Files.readString(Path)` and `Files.writeString(Path, ...)` have defaulted to UTF-8 since their addition in JDK 11. Do not assume every older API shares the same rule. Read the Javadoc for the exact overload used.

Some APIs follow separate rules and do not use the default charset. For example, `Properties.load(InputStream)` interprets bytes as ISO-8859-1 per API contract; `Properties.load(Reader)` depends on how the Reader was constructed. Therefore, do not apply blanket edits based solely on class names. Confirm actual data encoding and API contracts.

The console also warrants separate inspection: console charset may depend on the terminal environment and need not match the default charset used for files. On supporting JDKs, `Console.charset()` reports the console charset. When exchanging data across protocols, files, or messages, use the contract-specified encoding—usually UTF-8—instead of treating the console or default charset as the standard.

When testing, use data with Vietnamese diacritics, non-ASCII characters, emoji if business rules allow, and invalid byte sequences. Test reads, writes, round-trips, and receiving systems. A file may display properly on the generating machine yet appear corrupted when opened elsewhere.

JDK 18+ provides the `native.encoding` property reflecting the environment's native encoding on supporting implementations. Some JDK builds provide compatibility mode `file.encoding=COMPAT`; this should only be a transitional measure after verifying with the specific vendor/JDK. The sustainable fix is specifying explicit charsets at data boundaries.

### 2.2. Virtual threads become a standard feature

JDK 21 finalized virtual threads via JEP 444. A virtual thread is a lightweight JVM-managed thread suited to the thread-per-task I/O model. Applications can spawn large numbers of concurrent tasks without maintaining an equal number of platform threads.

Example using an executor that creates a virtual thread per task:

```java
try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> response = executor.submit(() -> callRemoteService());
    System.out.println(response.get());
}
```

This is a standard API in JDK 21. Nevertheless, adopting virtual threads is an execution-architecture change, not a switch that automatically accelerates every application.

Points to evaluate:

- Virtual threads suit I/O-waiting workloads; they do not speed up CPU-bound computation.
- Do not create small pools of virtual threads to limit virtual thread count the way platform thread pools do. Instead, bound real resources such as connection pools, remote concurrency, or semaphores.
- Virtual threads should not be held inside long-lived synchronization blocks while waiting on I/O.
- In JDK 21, a virtual thread can pin its carrier thread when blocking inside `synchronized` or executing native/foreign calls. Audit these sections if applying virtual threads under high load.
- Monitor `jdk.VirtualThreadPinned` events with Java Flight Recorder when investigating pinning.
- `ThreadLocal` retains per-thread semantics. Creating very many virtual threads with large ThreadLocal payloads can grow memory substantially.
- Virtual threads are daemon threads; applications must manage task/executor lifecycles and shutdown explicitly rather than relying on a virtual thread to keep the JVM alive.

If the application currently uses a thread pool to protect a scarce resource, keep resource limiting at the right boundary. Do not switch an entire pool to virtual threads and accidentally let thousands of concurrent requests hit the same database or external service.

Web frameworks, JDBC drivers, HTTP clients, logging contexts, tracing agents, and libraries using ThreadLocal must be verified when moving to the virtual thread model. A library supporting JDK 21 does not mean it is already optimized or safe for virtual threads.

### 2.3. Dynamic agent loading emits a new warning

JEP 451 in JDK 21 introduces a warning when a Java agent is dynamically loaded into a running JVM via the attach mechanism. This affects certain test tools, mocking libraries, profilers, debuggers, or observability tools using Byte Buddy/Instrumentation to attach agents after JVM startup.

For example, a test suite may run cleanly on JDK 17 yet start printing warnings when a library self-attaches an agent on JDK 21. A warning does not necessarily mean the test failed, yet signals that this loading mechanism may be restricted in future JDKs.

Handle this in order:

1. Identify exactly which library or plugin is attaching the agent.
2. Check whether a newer version supports loading the agent at JVM startup.
3. Prefer configuring the agent via `-javaagent` at process startup if supported by the tool.
4. If dynamic attach is legitimately required, evaluate `-XX:+EnableDynamicAgentLoading` within the exact test/tooling scope and document the decision.
5. Do not add global opt-in flags just to silence warnings before tracing their origin.

Check components such as Mockito, Byte Buddy, profilers, coverage agents, APM agents, test frameworks, and test runners. Not all agents are impacted identically: agents passed via `-javaagent` at startup differ from agents dynamically attached later.

### 2.4. Strong encapsulation of JDK internals already applied in JDK 17

JEP 403 completed strong encapsulation of JDK internals in JDK 17. Hence when moving from 17 to 21, this is not a brand-new change. Still, older libraries may still rely on internal packages or unsupported reflection, and JDK 21 can expose newly exercised dependencies.

Common symptoms:

- `InaccessibleObjectException` when a library invokes `setAccessible(true)` on an unopened member.
- `IllegalAccessError` or `IllegalAccessException` when accessing unexported/unopened classes or members.
- Warnings or errors referencing `sun.*`, `com.sun.*`, or other internal APIs.
- Proxy/bytecode libraries failing to define classes or access constructors/methods via reflection.

The `--illegal-access` option stopped being a reliable way to broaden access starting in JDK 17; do not use it as a migration fix. `--add-opens` can open a specific package to a specific module, yet it is a scoped compatibility measure that must be documented. Prioritize upgrading libraries, switching to public APIs, or changing integration style.

When `--add-opens` is unavoidable, record which package, which module needs access, the underlying error, environment scope, and removal deadline. Avoid opening JDK packages wholesale in production just to make the application boot.

### 2.5. New APIs and language features finalized in JDK 21

JDK 21 promoted several features from preview in earlier releases to standard features:

| Feature | JEP | Migration significance |
|---|---:|---|
| Record Patterns | 440 | Enables deconstructing records in pattern matching; check compiler and source-analysis tools if used |
| Pattern Matching for switch | 441 | Extends switch with patterns; watch source levels and code analysis/formatting tools |
| Virtual Threads | 444 | Standard lightweight thread API; can change concurrency model when intentionally adopted |
| Sequenced Collections | 431 | Adds interfaces and first/last/reversed operations for ordered collections |
| Generational ZGC | 439 | ZGC enhancement opt-in for evaluation; not a mandatory default for all apps |
| Key Encapsulation Mechanism API | 452 | Adds cryptographic API; check providers and use cases if adopted |

New features do not automatically alter existing source behavior. Risk typically appears when projects begin using new APIs, raise the compiler/source level, or upgrade libraries to adopt new APIs.

JDK 21 also ships preview/incubator features such as String Templates, Structured Concurrency, Scoped Values, Unnamed Patterns and Variables, Unnamed Classes and Instance Main Methods, and Vector API at their respective preview/incubator stages. They do not carry the same stability guarantees as standard APIs. Do not ship preview features to production without explicitly accepting preview flags, version lock-in, and change risks in subsequent JDKs.

### 2.6. Sequenced Collections and custom collection code

JEP 431 adds `SequencedCollection`, `SequencedSet`, and `SequencedMap`, introducing methods such as `getFirst()`, `getLast()`, and `reversed()` to applicable ordered collection types.

For normal applications, these are additive APIs. However, libraries defining custom collections or classes implementing interfaces extending `List`, `Deque`, `SortedSet`, or `Map` may face source compatibility issues if they already declared same-named methods or complex type relationships.

When upgrading the compiler to Java 21, recompile custom collection implementations and check:

- Methods colliding in name/signature with the new methods.
- Default methods and conflicts when multiple interfaces supply the same method.
- Element-ordering contracts of custom collections.
- Semantics of reversed views and mutations through views.
- Collection libraries, ORMs, or frameworks providing collection wrappers/proxies.

If a library was pre-compiled yet runs on JDK 21, verify binary compatibility and runtime behavior. If source is recompiled, verify source compatibility as well.

### 2.7. Locale, timezone, Unicode, and environment data

The JDK bundles locale, Unicode, timezone, and certificate/security-algorithm data updated across releases. Do not assume string formatting, date/time output, or locale data will match identically between two vendors or two JDK updates.

Areas to verify:

- `DateTimeFormatter`, `NumberFormat`, `DecimalFormat`, `DateFormat`, and locale data.
- Decimal formatting, thousands separators, currency symbols, and month/day names.
- `ZoneId`, DST rules, and regional timezone data.
- Unicode normalization, case conversion, collation, and supplementary character handling.
- CA certificate stores, TLS protocols, cipher suites, and disabled cryptographic algorithms.

Do not compare locale-formatted strings as if they were a stable wire protocol. When storing or exchanging data across systems, use deterministic formats such as ISO-8601 for timestamps and explicit locales/charsets. For timezones, store instants via `Instant` or offset timestamps where appropriate, converting to display timezones only at the UI layer.

JDK 17 and 21 updates from different vendors can ship different timezone/CA data. Record vendor, build number, and patch level, not just "Java 21".

### 2.8. Garbage collectors and performance behavior

G1 remains the common default HotSpot garbage collector in both JDK 17 and 21. Generational ZGC arrived in JDK 21 as an opt-in choice requiring deliberate enabling and testing, not a mandatory requirement of upgrading the JDK.

Do not assume performance will automatically improve on a newer runtime. Performance depends on workload, heap sizing, container limits, CPU, allocation rate, GC, JIT profile, libraries, and startup pattern. JDK 21 can change JIT optimizations and internal runtime behavior; some paths may speed up while others shift in latency or memory footprint.

Compare before and after migration on the same workload:

- Startup time and warm-up time.
- Throughput and latency percentiles (p50, p95, p99).
- CPU, heap, non-heap, allocation rate, and GC pause count/duration.
- Thread counts, connection pools, queue depth, and timeouts.
- Error rates, retries, and resource utilization under sustained load.

If changing GC or JVM flags alongside the JDK upgrade, record them as separate changes. Do not mix multiple variables and attribute the entire result to the JDK.

### 2.9. Deprecated APIs or components already removed before Java 17

Some components are often mistaken as removed during 17 to 21, yet had actually been removed in earlier versions:

| Component | Change milestone | Significance when upgrading 17 to 21 |
|---|---|---|
| Nashorn JavaScript Engine | Deprecated JDK 11, removed JDK 15 | Already absent in JDK 17; if JS engine is still needed, a separate solution is required |
| Java EE/CORBA modules | Removed JDK 11 | Not a new change in JDK 21 |
| Pack200 | Removed JDK 14 | Not a new change in JDK 21 |
| RMI Activation | Removed JDK 17 | Already absent when running on JDK 17 |
| Applet API | Deprecated for removal since JDK 17 | Plan removal if still depended upon |
| Security Manager | Deprecated for removal since JDK 17 | Still deprecated in JDK 21; do not build new features on it |
| Finalization | Deprecated for removal since JDK 18 | Audit `finalize()` and move to explicit resource management |

Distinguishing change milestones avoids blaming JDK 21 wrongly. If an application already ran stably on JDK 17, items removed in JDK 11/15/17 were likely already handled or unreached. Even so, a new library or another build profile might inadvertently re-activate a legacy dependency.

## 3. Compatibility layers of a library

A library claiming "supports Java 21" can mean multiple things. Check each layer below.

### 3.1. Bytecode compatibility

Each Java release defines a class file major version. Java 17 uses major version 61; Java 21 uses major version 65. An older JVM cannot load class files compiled for a major version higher than it supports.

| Java release | Class file major version |
|---|---:|
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |

If the application is compiled with JDK 21 targeting 21, the artifact cannot run on JDK 17. To keep runtime 17 support, compile targeting release 17 and avoid APIs added in 18+.

With `javac`, `--release` constrains language level, bytecode, and platform APIs:

```bash
# Compile with JDK 21 while producing an artifact targeting Java 17.
javac --release 17 -d build/classes src/main/java/example/App.java

# Compile and use Java 21 APIs.
javac --release 21 -d build/classes src/main/java/example/App.java
```

Setting only `sourceCompatibility` and `targetCompatibility` may not prevent using newer APIs from the JDK running the compiler. Configure toolchains and `--release` matching your support target.

For third-party libraries, inspect artifact class file versions when in doubt. Run `javap -verbose` on specific classes or `jdeps` to aid dependency analysis. However, valid bytecode versions only prove the JVM can parse class format at that level; they do not prove compatibility with APIs, modules, reflection, or runtime behavior.

### 3.2. Source compatibility and API compatibility

Source compatibility answers: does existing source still compile with the new compiler? API compatibility answers: do classes/methods/fields called by the application still exist and keep a compatible contract?

Common issues:

- Deprecated APIs removed or changed in signature.
- New overloads making previously valid calls ambiguous upon recompilation.
- New default methods causing conflicts with custom interfaces/classes.
- Generic signatures or annotation processing changing type inference.
- Libraries implementing JDK interfaces affected when interfaces gain methods.
- Frameworks changing packages, modules, lifecycles, or configuration contracts.

If a dependency is consumed only as a binary without recompiling, source compatibility of the dependency is not the only factor. Binary compatibility, linkage, and runtime behavior still need verification on JDK 21.

### 3.3. Runtime behavior compatibility

A library may compile and load cleanly yet behave differently due to reliance on default charset, locale, timezone, TLS, reflection, thread scheduling, GC, or JVM options. This is why integration/regression tests on the target runtime are essential.

Read library release notes across versions from the baseline to the target version. Focus on:

- Java version support and minimum runtime.
- Breaking changes, behavior changes, and deprecated APIs.
- Reflection, proxies, bytecode generation, and JPMS.
- Threading, executors, ThreadLocal, and virtual thread support.
- Charset, locale, date/time, serialization, and protocols.
- TLS, cryptography, native libraries, and OS support.
- Transitive dependency shifts or supported framework versions.

Do not read only the final version's release notes. When crossing multiple major versions, read intermediate major-version migration guides to catch mandatory transition steps.

### 3.4. Framework compatibility

Frameworks maintain dedicated compatibility matrices with JDKs, build tools, and foundational libraries. For example, a web framework may require a newer Spring Framework; an ORM may change bytecode enhancement; a test framework may require newer Mockito/Byte Buddy; a framework plugin may require newer Gradle/Maven.

For every critical framework, verify:

- Does the framework version declare Java 21 support?
- Is that framework version compatible with existing libraries?
- Does the framework require upgrading BOMs, plugins, or drivers together?
- Are there package/API/config changes forcing source edits?
- Are there limitations around virtual threads, native image, reflection, or modules?
- Is the supported framework version still within vendor maintenance?

Do not treat a "Java 21 compatible" badge on a product page as proof for the entire stack. Cross-check exact versions of frameworks, JDK, build plugins, and managed dependencies.

### 3.5. Bytecode, reflection, and proxy libraries

This library group is especially sensitive to compiler/JDK changes:

- ASM and bytecode reading/writing libraries.
- Byte Buddy and dynamic subclass/proxy tools.
- CGLIB and proxy libraries.
- Javassist or class-instrumentation libraries.
- ORM enhancement and dependency injection frameworks.
- Coverage agents, mocking frameworks, APMs, and profilers.

An older bytecode library may fail to understand new class files or new bytecode constructs generated by the compiler. A proxy library may reflect deeply into the JDK or framework classes. When upgrading the JDK, check minimum versions of bytecode libraries and whatever pulls them in.

If errors appear only during tests, separate application runtime libraries from test-only mocking/coverage/agent libraries. Production dependencies do not necessarily need changes to fix an outdated test agent.

### 3.6. Annotation processors and compiler plugins

Annotation processors execute inside the compiler and may use compiler APIs or internal APIs. Processors like Lombok, MapStruct, QueryDSL, Hibernate metamodel generators, and custom processors must be verified individually.

Questions to answer:

- Does the processor support JDK 21 and the corresponding compiler API?
- Is the processor version aligned with its runtime/API library?
- Does the compiler plugin run on JDK 21?
- Does generated source compile under the project's source/API target?
- Does the processor handle records, sealed types, generics, and new annotations properly?
- Is output deterministic and reproducible on clean builds?

Do not upgrade only runtime dependencies. When failures occur during annotation processing, the component needing an upgrade may be on the processor path or compiler plugin.

### 3.7. JDBC drivers, clients, and integration libraries

JDBC drivers, HTTP clients, messaging clients, and vendor SDKs must be tested against both the JDK and real server/service versions. These libraries frequently use TLS, sockets, threads, native libraries, or serialization.

Check:

- Does the driver support Java 21 and the running database version?
- Do TLS/ciphers/protocols and truststores remain compatible?
- Do connection pools behave properly if the app changes threading model?
- Do timeouts, retries, interruption, and cancellation behave properly?
- Does the SDK pull in conflicting transitive dependencies or logging APIs?
- Do native/JNI libraries provide binaries matching OS/architecture/container?

Do not upgrade a driver or SDK solely because a newer version supports JDK 21. Check compatibility with server versions, schemas, protocols, and the rest of the stack.

### 3.8. Serialization and data contracts

JSON/XML/serialization libraries may alter handling of records, constructors, reflection, module access, enums, date/time, and unknown fields. A small shift can alter wire payloads even while code compiles.

Build a representative test dataset containing:

- Legacy payloads stored or sent by previous releases.
- Null values, missing fields, new fields, and unknown fields.
- Dates/times, timezones, decimals, and Unicode characters.
- Enums, polymorphic types, generic collections, and nested objects.
- Data in legacy formats requiring backward compatibility.

Compare JSON/XML structurally and by contract rather than raw string equality if field order or whitespace is outside the contract. Test both serialization and deserialization directions.

## 4. Inventorying libraries and identifying target versions

### 4.1. Catalog by classpath

Do not merge all dependencies into one flat list. For each module, capture at least:

| Classpath/configuration | Content | Example |
|---|---|---|
| Compile | Libraries needed to compile main code | `compileClasspath` |
| Runtime | Libraries loaded when running the application | `runtimeClasspath` |
| Test compile/runtime | Test frameworks, mocks, test containers, and test dependencies | `testCompileClasspath`, `testRuntimeClasspath` |
| Annotation processor | Processors generating source or resources | `annotationProcessor`, `kapt`, KSP |
| Build/plugin | Plugins, buildscripts, and plugin dependencies | Gradle plugin DSL, `buildEnvironment`, Maven plugin realm |
| Generator task | Generators run as separate tasks/goals | OpenAPI, Protobuf, Avro, jOOQ |

A library can appear in multiple classpaths with different versions. Record both requested versions and selected versions after conflict resolution, BOMs, constraints, or dependency management.

### 4.2. Cross-reference official support sources

For each critical dependency, look up:

- The vendor's Java/JDK support matrix.
- Release notes and migration guides for the target version.
- Minimum supported Java version.
- Required Gradle/Maven or framework plugin versions.
- Key transitive dependencies and co-upgraded versions.
- Maintenance and security policy of the release branch.

Clearly separate three states:

- **Vendor-supported:** vendor declares support for that version combination.
- **Project-verified:** the project ran builds/tests on the target combination and archived evidence.
- **Unknown:** no documentation or test environment yet to verify.

Do not merge "vendor-supported" and "project-verified" into one status. A vendor-supported library can still conflict with other configurations or dependencies inside the app.

### 4.3. Prioritize dependencies to check first

Components to audit early:

1. Core frameworks and BOMs managing dependencies.
2. Build tools, compiler plugins, packaging plugins, and internal plugins.
3. Bytecode, reflection, proxy, instrumentation, and agent libraries.
4. Annotation processors and generators.
5. ORMs, JDBC drivers, connection pools, and database migration tools.
6. JSON/XML, date/time, logging, and security libraries.
7. Test frameworks, mocking, coverage, and test containers.
8. Native/JNI libraries, external system clients, and vendor SDKs.

This is an inspection priority order, not a mandatory upgrade order. Actual dependency graphs may dictate a different upgrade sequence.

## 5. Upgrading build tools and plugins alongside the JDK

### 5.1. Gradle

The Gradle Wrapper must be compatible with the JDK running Gradle. Using a JDK as a compilation toolchain can differ from running Gradle itself on that JDK. Thus, when moving to JDK 21, check Gradle's official compatibility matrix for both purposes.

Check:

- `gradle-wrapper.properties` and Gradle Wrapper version.
- `plugins {}` in root and subprojects.
- `pluginManagement` in settings.
- `buildscript` classpaths.
- `gradle/libs.versions.toml` if using a version catalog.
- `buildSrc` and included builds/convention plugins.
- Compiler toolchains and `options.release`.
- Test JVMs, forked Java processes, and tasks using custom JDKs.

Useful inspection commands:

```bash
./gradlew --version
./gradlew projects
./gradlew buildEnvironment
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency <artifact> --configuration runtimeClasspath
```

`buildEnvironment` does not show the full plugin DSL. Inspect plugin declarations and plugin resolution separately.

### 5.2. Maven

The Maven Wrapper and Maven plugins must run on JDK 21. Check Maven version, Compiler Plugin, Surefire/Failsafe, Enforcer, JaCoCo, Spring Boot plugin, shade/assembly, code generators, and internal plugins.

Inspection commands:

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree -Dverbose
./mvnw dependency:resolve-plugins
```

In multi-module Maven builds, inspect parent POMs, profiles, and plugin management. Inherited plugin versions may not appear in the POM of the module currently building.

### 5.3. Compiler and test JVMs

The JDK running Gradle/Maven is not necessarily the JDK used for compiling/testing. Verify separately:

- JDK of the build daemon/process.
- JDK toolchain used for compilation.
- JDK used to run unit/integration tests.
- JDK used to run the application inside containers.
- JDK used for generators or separately forked processes.

If tests run on JDK 17 while production runs JDK 21, passing tests do not prove runtime 21 compatibility. If builds run on JDK 21 while tests still run on 17, failures from agents or test frameworks that only appear on JDK 21 will be missed.

## 6. Migration workflow from JDK 17 to JDK 21

### Step 1: Capture baseline on JDK 17

Freeze commit, JDK vendor/build version, Wrapper, frameworks, dependency graph, and current build/test outcomes. Archive pre-existing warnings and failures to distinguish them from new regressions.

### Step 2: Choose compatibility policy

Decide whether the product will run solely on Java 21 or must continue supporting Java 17. If keeping Java 17, define compiler `--release 17`, runtime test matrix, and allowed API boundaries. If moving fully to 21, set the cutoff when artifacts stop supporting runtime 17.

### Step 3: Verify build tool with JDK 21

Choose Gradle/Maven and plugin versions supporting execution on JDK 21. Update the Wrapper separately, run lightweight configuration tasks and basic builds. Do not upgrade frameworks/dependencies simultaneously before confirming the build tool works.

### Step 4: Update frameworks and foundational dependencies

Consult BOMs/framework matrices to pick compatible versions. Upgrade coherently grouped dependencies together, record before/after dependency graphs, and avoid arbitrarily overriding BOM-managed versions without evaluation.

### Step 5: Update compiler plugins, processors, and generators

Upgrade annotation processors, bytecode libraries, generators, and compiler plugins for JDK 21. Re-run generation on a clean build, inspect output diffs, and compile all generated sources.

### Step 6: Handle default behavior changes

Audit default charsets, reflection/JPMS, dynamic agent loading, locale/timezone, TLS, and JVM options. Update source code to use explicit charsets and formats. For agents, identify attaching tools and move to startup agent configuration where possible.

### Step 7: Run tests on the real JDK 21

Run compile, unit, integration, contract, smoke, and packaging tests on JDK 21. Tests must exercise production-representative artifacts and runtimes rather than running only from an IDE or development classpath.

### Step 8: Evaluate performance and canary release

Compare performance against baseline, run soak tests when needed, deploy artifacts into representative environments, and roll out incrementally. Prepare rollback before shifting production traffic.

## 7. Library verification matrix

A verification table should clearly surface evidence sources and test scope:

| Component | Current version | Target version | JDK 21 support | Tested on JDK 21 | Risks/notes |
|---|---|---|---|---|---|
| Core framework | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | BOM, migration guide |
| ORM | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | Reflection, proxies, JDBC |
| JDBC driver | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | DB/server version, TLS |
| JSON/XML | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | Records, reflection, formats |
| Bytecode/proxy | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | ASM, Byte Buddy, JPMS |
| Test/mock/agent | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | Dynamic attach, `-javaagent` |
| Annotation processor | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | Compiler API, generated source |
| Build plugin | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | Gradle/Maven compatibility |
| Native/JNI | ... | ... | Yes/No/Unknown | Pass/Fail/Not run | OS, architecture, binaries |

Do not leave `...` in formal reports. If data is missing, record "unknown" and assign an owner. A "Yes" in the support column needs a URL/document or release note; a "Pass" needs a build/test run, commit, and environment.

## 8. Critical test suite for JDK 17 → 21

### 8.1. Charset and text data

- Read/write UTF-8 files with Vietnamese text and non-ASCII characters.
- Import/export CSV, JSON, XML, properties, and legacy config files.
- Send/receive messages and HTTP payloads with explicit encodings.
- Verify data written by JDK 17 and read by JDK 21, and the reverse direction if rollback must be supported.
- Audit APIs still relying on the default charset.

### 8.2. Reflection, proxies, and bytecode

- Framework startup and proxy/bean creation.
- ORM enhancement, lazy loading, entity proxies, and serialization.
- Mocking frameworks, coverage agents, profilers, and instrumentation.
- Run tests with modules/packages having restricted access.
- Check for warnings/errors: `InaccessibleObjectException`, `IllegalAccessError`, and class loading issues.

### 8.3. Agents and test infrastructure

- Run the test suite on JDK 21 and observe dynamic agent loading warnings.
- Determine whether agents load via `-javaagent` or dynamic attach.
- Verify versions of Surefire/Failsafe, Gradle test workers, and test launchers.
- Run parallel tests and check cleanup, thread leaks, and file/socket leaks.

### 8.4. Threading and virtual threads

If the app does not yet use virtual threads, check libraries making assumptions about platform threads or ThreadLocal. If deliberately adopting virtual threads, test I/O load, connection limits, synchronized blocking, native calls, and JFR pinning events.

### 8.5. TLS, locale, and time

- TLS connections to databases, brokers, HTTP services, and identity providers.
- Verify truststores, CAs, ciphers/protocols, and expired certificates.
- Check number/date-time formatting under business locales.
- Check timezones and DST in regions with rule changes.
- Compare serialization contracts and timestamps across systems.

### 8.6. Performance and operations

- Compare startup, throughput, p95/p99, CPU, heap, GC, and thread count.
- Check container memory/CPU limits and JVM ergonomics.
- Run endurance/soak load to catch memory leaks or connection exhaustion.
- Verify logs, metrics, traces, health checks, and graceful shutdown.

## 9. Common failures and root-cause tracing

| Symptom | Possible cause | Investigation path |
|---|---|---|
| Vietnamese text in files is corrupted after migration | API uses default charset; JDK 17 and 21 have different defaults | Search for overloads omitting charset; inspect input/output bytes |
| Tests emit agent warnings | Test tool attaches an agent dynamically | Upgrade tool; review `-javaagent` startup config and JEP 451 |
| `InaccessibleObjectException` | Library reflects into unopened JDK/module package | Trace stack trace; upgrade library or replace API; use limited `--add-opens` |
| Compile error in processor | Outdated annotation processor/compiler plugin | Inspect processor path, compiler JDK, and supported versions |
| `UnsupportedClassVersionError` | Artifact or dependency has newer bytecode than runtime | Inspect class file versions and actual launched JDK |
| Build breaks before compiling | Gradle/Maven/plugin fails to run on JDK 21 | Verify Wrapper, plugins, and build-process JDK |
| App boots yet API output is wrong | Changed runtime behavior, locale, charset, TLS, or framework behavior | Run integration/contract tests and compare with baseline |
| Performance degrades | JIT/GC, heap sizing, container, workload, or new dependency | Compare profiles and metrics under identical conditions |
| Tests pass yet production fails | Tests ran on a different JDK or image than production | Run final artifact on target runtime/container |

When investigating, identify which layer failed: build tool, compiler, processor, runtime dependency, JVM, container, or external system. An error inside a Gradle task is not necessarily an application code bug; a unit test failure can also come from a test agent rather than a production library.

## 10. Example: resolving a charset bug when moving to JDK 21

Suppose a batch job reads CSV files produced by a legacy Windows system. On JDK 17, the batch host's default charset happened to match the file encoding so Vietnamese data displayed correctly. After moving to JDK 21, the default charset is UTF-8; if incoming files still use Windows-1258 or another code page, text may become garbled or produce replacement characters.

Remediation workflow:

1. Save a representative input file and confirm actual encoding via the upstream contract or byte-inspection tools.
2. Identify the file-reading API in use: `FileReader`, `InputStreamReader`, a CSV library, or another wrapper.
3. Check whether that API uses the default charset; do not guess from library names.
4. Define the file charset in the integration contract. If the sender can migrate to UTF-8, agree on timing and cutover.
5. If legacy encodings must still be accepted, specify the exact charset on that read stream; never change the JVM-wide default charset just to handle one file.
6. Create tests with Vietnamese text, special characters, invalid bytes, and large files.
7. Verify output files, database records, and payloads forwarded downstream.
8. Canary-test on JDK 21 and confirm other text streams remain unaffected.

Example reading a legacy file once encoding is confirmed:

```java
Charset sourceCharset = Charset.forName("windows-1258");
try (BufferedReader reader = Files.newBufferedReader(path, sourceCharset)) {
    // Parse CSV using the encoding specified by the data contract.
}
```

The charset name in the example is illustrative only. Confirm the exact encoding of the real source. Do not force one default code page across all files if sources have different contracts.

## 11. Example: test warning from dynamic agent loading

Suppose unit tests ran without warnings on JDK 17, yet on JDK 21 logs warn that an agent was dynamically attached. Tests may still pass, yet the team needs to know which tool performs this action.

Tracing steps:

1. Check test logs, test runtime dependencies, and test-runner plugins.
2. Identify which mocking/coverage/profiling library uses Instrumentation or Byte Buddy.
3. Read documentation for current and newer versions on how agents are loaded.
4. Configure the agent at JVM startup via `-javaagent` if supported and appropriate.
5. Consider `-XX:+EnableDynamicAgentLoading` only after understanding why dynamic attach is needed and scoping it narrowly.
6. Run the test suite on JDK 21, confirm warnings are deliberately handled, and verify test behavior remains intact.

Do not delete tests or disable coverage just to silence warnings. Also avoid adding a global flag undocumented, as it hides outdated tools during future upgrades.

## 12. Release decisions and rollback

Before releasing to production, identify which artifact was tested, which commit built it, and which JDK runtime and container image are used. Store checksums and test results for traceability.

Deploy via canary, rolling, or blue-green strategies depending on architecture. Monitor error rates, latency, CPU, memory, GC, restarts, connection pools, and integration errors. Define abort thresholds prior to rollout. If breached, halt traffic expansion and execute the prepared rollback plan.

JDK rollback must also consider artifact and data compatibility. An artifact compiled targeting 21 cannot run back on JDK 17. If rolling back to runtime 17 may be required, retain artifacts compiled targeting 17 or the corresponding prior release. Schema/database changes must remain compatible between old and new versions; do not assume swapping container images alone suffices.

If the final goal is Java 21, retain a JDK 17-compatible release artifact for fast recovery during rollout. Once migration stabilizes, update runbooks, dependency matrices, CI configurations, runtime images, and version support policies.

## 13. Completion dossier for JDK 17 → 21 migration

A migration should be closed only when the following evidence can be handed over:

1. **Version targets:** build JDK, compiler/toolchain, source/API target, and target runtime.
2. **Baseline:** JDK 17 commit, build logs, dependency graph, plugin/generator inventory, and initial test results.
3. **Compatibility matrix:** frameworks, libraries, plugins, processors, agents, drivers, and native libraries; with official support sources and verification statuses.
4. **Behavior change register:** charset, dynamic agent loading, reflection/JPMS, virtual threads if applicable, locale/timezone, TLS, and JVM flags.
5. **Migration change record:** upgraded versions/configs, rationale, commits, and owners.
6. **Verification report:** compile, unit, integration, contract, smoke, performance, security, and final artifact/container tests.
7. **Release record:** artifact checksum, JDK vendor/build, container image, rollout plan, and abort thresholds.
8. **Recovery plan:** prior artifact, prior runtime, data compatibility, and recovery validation steps.
9. **Follow-up:** deprecated APIs, workarounds, remaining risks, and remediation deadlines.

### Pre-closure checklist

- [ ] Determined whether the project moves runtime to 21 or continues supporting runtime 17.
- [ ] Configured build-running JDK, compiler/toolchain, and runtime separately.
- [ ] Build tool and all plugins run cleanly on JDK 21.
- [ ] Dependency graph audited across compile/runtime/test/processor classpaths.
- [ ] Critical frameworks and dependencies have documented Java 21 support.
- [ ] Bytecode/proxies/reflection/agents and annotation processors verified.
- [ ] APIs relying on default charset audited and given explicit encodings.
- [ ] Tests cover multilingual text data, locales, timezones, and TLS per business needs.
- [ ] Dynamic agent loading warnings traced and handled intentionally.
- [ ] If using virtual threads, verified pinning, ThreadLocal, and resource bounds.
- [ ] Final artifact executed on the exact target JDK/container.
- [ ] Performance compared against baseline under identical conditions.
- [ ] Rollback artifact compatible with prior runtime and data recovery plan ready.
- [ ] Compatibility matrix, runbooks, and operational docs updated.

Upgrading JDK 17 to 21 succeeds when the entire combination of build tools, compiler, frameworks, dependencies, agents, and runtime operates according to the chosen support target. Auditing default changes like UTF-8, identifying library constraints, and verifying on the final artifact helps migrations avoid bugs that only appear in live runs. Compatibility evidence and a rollback plan are prerequisites for bringing JDK 21 into production under control.
