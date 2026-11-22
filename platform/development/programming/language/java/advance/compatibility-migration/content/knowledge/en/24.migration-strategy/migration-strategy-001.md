# Running the Existing Artifact on the Target JDK Before Deciding to Recompile

A Java project planning to upgrade its JDK often begins by changing the compiler version, Maven/Gradle Wrapper, plugins, and dozens of dependencies. That approach can work well, yet it also changes the **runtime, build tool, bytecode, dependency graph, and source code simultaneously**. When something breaks, pinpointing the cause becomes difficult: did the failure come from the new JVM, a newer library, JVM configuration, or binaries emitted by the newer compiler?

In **Java Advance Compatibility Migration**, a pragmatic strategy is to **run the currently released artifact on the target JDK before deciding whether recompilation is necessary**. If you run JDK 17 today and want to move to JDK 21, test the exact current release JAR/WAR and library set on the Java 21 runtime inside a controlled test environment. The initial question is concrete:

> Can the current binary and deployment bundle operate correctly on the target JDK without modifying source code or rebuilding the application?

The answer may be **yes**, **yes with runtime configuration adjustments**, **requires adding a runtime dependency or provider**, or **requires code changes and rebuilding**. Each answer leads to a different migration scope. Runtime-first does not replace longer-term upgrade work; it identifies what genuinely needs changing in an order with fewer variables and cleaner rollback.

This lesson walks through freezing the artifact, checking class-file compatibility, running on the new JDK, verifying behavior and operations, analyzing failures, and deciding when recompilation is warranted.

## 1. Why test the runtime before rebuilding?

### 1.1. Java executes bytecode, not source directly

Once compiled, Java source becomes class files or artifacts containing bytecode. The JVM executes those compiled classes. When swapping the Java runtime, the JVM does not re-invoke `javac` over the entire application source tree.

Accordingly, an application compiled for Java 17 **can** run on Java 21 without rebuilding. Compatibility still must be verified, since bytecode relies on classes, methods, interfaces, providers, resources, and runtime behaviors.

Do not confuse:

- **Source compatibility:** does the source still compile against the new compiler/APIs?
- **Binary compatibility:** do class files and symbolic references still link against the new runtime/libraries?
- **Behavioral compatibility:** do outputs, errors, and side effects match the contract?
- **Operational compatibility:** do startup, performance, security, memory, agents, and surrounding infrastructure behave steadily?
- **Build compatibility:** can the build tool and plugins run on the new JDK?

Testing the current artifact focuses on binary, behavioral, and operational compatibility. It **does not need to prove** that an older Gradle or Maven build runs on the new JDK.

### 1.2. Two migration paths carry different risk profiles

```text
Common approach:
  Change JDK + change Gradle/Maven + upgrade dependencies
      + recompile + change application image
                         |
                         v
              Test: PASS or FAIL
                         |
                         v
           Hard to isolate root cause

Runtime-first approach:
  Release artifact A + dependency set D + old JDK
                         |
                    BASELINE
                         |
                         v
  Release artifact A + dependency set D + target JDK
                         |
                   TEST / COMPARE
                         |
                         v
       Fix only what is genuinely incompatible
                         |
                         v
       Recompile when justified by reason and evidence
```

The second path does not claim every upgrade can always be broken into isolated steps. A framework or application server might mandate upgrading alongside the JDK. Mandatory co-upgrades like that must be **recorded as explicit separate variables**, never accidentally mixed into the probe.

### 1.3. When is runtime-first most useful?

This approach brings high value for:

- Long-lived, stable services upgrading the JDK primarily for security or support policy.
- Projects with legacy libraries, build plugins, or old code generators.
- Systems requiring rapid rollback and minimal business-logic changes.
- Teams wishing to separate runtime migration from build modernization.
- Shared-JDK-image services needing clarity on which services can run existing binaries unmodified.
- Historical releases difficult to reproduce from source, where release artifacts and runtime libraries still exist.
- JDK 17 → 21 upgrades, where many applications do not need Java 21 APIs immediately.

If the existing artifact already contains critical vulnerabilities or uses an end-of-life framework, running on the new JDK **is not sufficient** to declare the application supported; this approach remains a valuable diagnostic step, not an excuse to defer security remediation.

## 2. Defining the exact artifact to preserve

### 2.1. An artifact is not always a single JAR

| Deployment model | Unit to freeze for testing |
|---|---|
| Executable fat JAR | JAR, launcher/manifest, embedded libraries, and resources |
| Thin JAR | Main JAR, entire `lib/`, classpath, and startup script |
| Spring Boot executable JAR | JAR with launcher and nested libraries |
| WAR | WAR, application server/container version, and shared libraries |
| EAR | EAR modules, server library layer, and class-loader policy |
| Application distribution | `bin/` scripts, `lib/` dependencies, config templates |
| Container | Application layers, runtime image, entrypoint, and runtime config |
| Java agent | Agent JAR, manifest, attached/instrumented target JVM |
| Native-image executable | Not normal JVM bytecode; requires a different workflow |

With a thin JAR, preserving only the checksum of `app.jar` while swapping JARs inside `lib/` **fails to preserve the runtime dependency graph**. With a WAR, switching servers from Java EE's `javax.*` namespace to Jakarta EE's `jakarta.*` is a framework/platform migration larger than a JDK swap.

### 2.2. Identifying artifacts by checksum

Linux/macOS example:

```bash
sha256sum app.jar
sha256sum lib/*.jar
```

PowerShell example:

```powershell
Get-FileHash -Algorithm SHA256 .\app.jar
Get-ChildItem .\lib\*.jar |
    Get-FileHash -Algorithm SHA256
```

Save checksums in both the baseline and test environments. When using containers, record the **image digest**, not just a mutable tag such as `latest`.

When testing requires keeping the binary unchanged, do not run a build task that overwrites outputs. Pull the artifact from a release repository or verified build, then copy and verify checksums.

### 2.3. Keeping launch mechanics identical

An executable JAR may launch via:

```bash
java -jar app.jar
```

Whereas a thin JAR may use:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

On Windows the classpath separator is typically `;` instead of `:`. A Spring Boot JAR supplies its own launcher and should not be unpacked or re-pointed to another main class arbitrarily. The objective is to **preserve the running release's launcher semantics** while changing only the executing JVM.

## 3. Establishing a baseline before switching JDKs

### 3.1. What makes a baseline reproducible?

At minimum:

1. Application release ID, git commit, and artifact checksums.
2. Runtime dependency versions, including transitive dependencies.
3. Java vendor, major/update/build of the old runtime.
4. JVM flags, system properties, and relevant environment variables.
5. OS, CPU architecture, container/base image, and CPU/memory limits.
6. Framework or application server version and configuration.
7. JDBC/HTTP/queue drivers, native libraries, and Java agents.
8. Database schema, endpoint config, and TLS/truststore settings.
9. Startup/health checks, current test results, and error baseline.
10. Performance baseline: p95/p99, throughput, CPU/GC/memory.
11. Status of batch jobs, schedulers, and file imports/exports.
12. Data policy, rollback expectations, and coexisting versions.

Never store passwords, tokens, or private keys in records. Record only configuration sources and metadata needed to recreate setup through approved secret-management mechanisms.

### 3.2. Do not assume last week's results are an identical baseline

If the artifact stayed constant while the database, external services, container image, or traffic mix changed, historical runtime metrics may not compare cleanly against the new runtime.

Ideally run **baseline and target close together in time** with identical fixtures and equivalent test environments. Otherwise, explicitly note remaining differences.

### 3.3. Verify which JVM actually runs the application

```bash
java -version
```

only reports the JVM found on the shell `PATH`. Inside CI, service managers, Docker, or Kubernetes, the application may invoke a different JVM.

Prefer explicit paths:

```bash
"$TARGET_JDK/bin/java" -version
"$TARGET_JDK/bin/java" -jar app.jar
```

PowerShell:

```powershell
& "$env:TARGET_JDK\bin\java.exe" -version
& "$env:TARGET_JDK\bin\java.exe" -jar .\app.jar
```

`TARGET_JDK` variables are illustrative placeholders. Also inspect `JAVA_HOME`, `PATH`, `JAVA_TOOL_OPTIONS`, and `JDK_JAVA_OPTIONS`. Some variables silently inject JVM options outside launch scripts and invalidate "changed only the JDK" assumptions.

## 4. Understanding class-file compatibility boundaries

### 4.1. Newer JDKs generally read older class files

Example:

| Java version used to produce the class file | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

The JDK 21 JVM supports older class-file versions within compatibility bounds. Thus a JAR compiled on JDK 8 or 17 **does not automatically need recompilation** merely for Java 21 to read its class files.

Still, readable bytecode does not guarantee every method reference resolves or every runtime behavior matches.

### 4.2. The reverse direction does not work automatically

If an artifact was built for Java 21 (class-file major version 65), running it on Java 17 can fail with:

```text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime (class file version 65.0)
```

Sound options:

- Run on Java 21 or an appropriate newer runtime.
- Recompile with `--release 17` **if source and dependencies allow**.
- Ship distinct binaries aligned to the minimum supported JDK.
- Update source if it uses Java 21 APIs or language features absent in Java 17.

No JVM flag such as `--add-opens` converts a major-version 65 class file back to major version 61.

### 4.3. Inspecting bytecode when needed

```bash
javap -classpath app.jar -verbose com.example.Main
```

Output includes the `major version` field. For fat JARs or specialized framework layouts, pass the appropriate class path or extract/inspect via archive tools.

A single class does not represent the entire artifact: dependencies, generated classes, multi-release entries, or shaded code can carry different major versions.

### 4.4. Multi-release JARs are a special case

A JAR declaring `Multi-Release: true` in its manifest can contain:

```text
META-INF/versions/9/
META-INF/versions/11/
META-INF/versions/17/
META-INF/versions/21/
```

With the exact same checksum, JDK 17 and JDK 21 can load different class implementations. When behavior shifts on the new runtime, inspect multi-release JARs before blaming the bytecode compiler or JIT.

## 5. Checking the artifact before running

### 5.1. Inspect the archive and manifest

```bash
jar tf app.jar
```

Check:

- Main-Class and launcher.
- Nested JARs or classpath metadata.
- `META-INF/services/` for ServiceLoader.
- `META-INF/versions/` for multi-release JARs.
- `module-info.class` or Automatic-Module-Name.
- Native resources and packaged configuration files.
- Dependencies that were previously supplied by the older JDK.

Do not modify the archive during preflight checks; the goal is to identify items that may affect runtime behavior.

### 5.2. Analyzing static dependencies with jdeps

Example:

```bash
jdeps --jdk-internals app.jar
jdeps --recursive app.jar
jdeps --multi-release 21 --recursive app.jar
```

Some projects must supply classpath or module path entries so `jdeps` resolves dependencies accurately. Never treat empty output as proof of complete compatibility: `jdeps` checks static bytecode references and can miss reflection, JNI, runtime code generation, and class names loaded from config.

### 5.3. Migrating classpath to module path is not mandatory

A Java 8 JAR lacking a module descriptor can still run on the classpath on modern JDKs. Moving to JPMS/module path is an independent architectural change, not a prerequisite for upgrading the JDK.

If the artifact already runs on the classpath, keep that launch mode during the initial probe. Test module path only when purposefully targeted, and record it as a separate variable.

## 6. Designing an experiment that isolates variables cleanly

### 6.1. Minimum matrix

| Variable | Baseline | Runtime probe |
|---|---|---|
| App source revision | A | A |
| App artifact checksum | X | X |
| Dependency artifacts | D | D |
| Business config | C | C |
| Database/test data | S | S |
| OS/container | E | E, if feasible |
| JDK runtime | Old | Target |
| Build/recompile | No | No |

The only intended change is the JDK runtime. If changing the base image alters the CA certificate store or libc, document that difference and interpret results accordingly.

### 6.2. Do not run a build during a runtime-only probe

Running:

```bash
./gradlew clean build
java -jar build/libs/app.jar
```

on the new JDK tests **build + run**, not "running the existing artifact." Build plugins, annotation processors, the compiler, and dependency resolution can produce a different binary.

In a runtime-only probe, take the existing release binary, verify its checksum, and execute it directly. Build modernization becomes a separate phase after establishing runtime results.

### 6.3. Test in a safe environment

Never let an unverified artifact write to a production database or dispatch real payments, emails, or queue messages. Use staging or sandboxes with representative data, test accounts, and state-reset procedures.

An overly trivial smoke test misses real bugs, while destructive testing against live data is unacceptable. Govern permissions and test scope under operational policy.

## 7. First run on the target JDK

### 7.1. Preserve command-line semantics

Example:

```bash
"$TARGET_JDK/bin/java" \
  -Xms512m \
  -Xmx2g \
  -jar app.jar \
  --app.profile=staging
```

Parameters above are illustrative. In real migrations, preserve the baseline heap sizes and JVM flags rather than inventing values that make performance incomparable.

If the JVM rejects a removed option, classify it as a **runtime launch configuration issue** and record any flag adjustments. Do not modify Java source code merely to satisfy an obsolete command-line option.

### 7.2. Separate logs for each run

```text
evidence/
  baseline/
    java-version.txt
    launch-command.txt
    stdout.log
    errors.log
    test-results/
    metrics/
  target/
    java-version.txt
    launch-command.txt
    stdout.log
    errors.log
    test-results/
    metrics/
```

When evaluating multiple JDK updates or vendors, include versions in evidence paths. Keep timestamps, checksums, and environment metadata so results are reproducible.

### 7.3. Clean startup is not sufficient

A service can boot and return HTTP 200 on `/health` without ever exercising:

- ORM mapping or database writes.
- XML/JAXB/Jackson serialization.
- TLS/mTLS client handshakes.
- Native compression or cryptography.
- Queue listeners.
- Schedulers and batch jobs.
- Reflective class loading.
- ServiceLoader/providers.
- Feature-specific execution paths.
- Config reloads, retries, and graceful shutdown.

Startup success is therefore only the opening check.

## 8. Recommended verification layers

### Layer 0: JVM and startup

Confirm the JVM accepts launch flags, loads the main class/module, initializes the framework, and reports no fatal startup errors.

### Layer 1: Smoke tests

Exercise a core representative workflow set:

- Health and version endpoints.
- Read-only APIs.
- One reversible staging write workflow.
- Database/cache connectivity.
- Authentication and sandbox HTTPS calls.

### Layer 2: Integration and contract tests

Verify XML/JSON, databases, queues, REST/SOAP, transactions, OAuth/TLS, file encodings, caches/sessions, and business invariants. Compare payloads, side effects, and error mappings—not just HTTP status codes.

### Layer 3: Performance and resources

Measure startup, time to readiness, warm-up, throughput, p50/p95/p99 latency, error rate, CPU/JIT, GC, RSS memory, threads, and file descriptors. The target JDK may show stronger steady-state throughput alongside worse cold latency.

### Layer 4: Soak and failure recovery

Sustain representative load while testing long-lived connections, DNS/TLS changes, database reconnects, pod restarts, shutdowns, timeouts, and resource leaks. Incompatibilities that surface only after several hours emerge here.

Choose verification layers proportional to system risk. Simple CLI utilities need not run every layer, while a single `/health` check must never certify a production financial service.

## 9. Newer JDK runtimes may omit previously bundled APIs

### 9.1. JEP 320 and JDK 11

Beginning in JDK 11, Java EE and CORBA modules formerly bundled with the JDK—including JAXB, JAX-WS, and Activation within their defined scope—were removed from the JDK distribution.

A Java 8 binary may fail with:

```text
java.lang.NoClassDefFoundError:
  javax/xml/bind/JAXBContext
```

or:

```text
java.lang.ClassNotFoundException:
  javax.activation.DataHandler
```

Java 8 bytecode still loads on JDK 21; the failure occurs because **the runtime API/provider is missing**, not because the class files are too old.

### 9.2. Decisions after hitting missing bundled APIs

1. Identify the caller and exact missing class.
2. Check whether the API came from a legacy dependency JAR or from JDK 8 itself.
3. Choose external API/runtime implementations from the matching namespace generation.
4. Test adding the dependencies in a new verification branch.
5. Re-run XML/SOAP/attachment contract tests.
6. Migrate source to `jakarta.*` only when framework upgrades or roadmap require it.

Once runtime JARs are added or repackaged, **the deployment bundle is no longer unchanged**. Label the new run as runtime adaptation rather than continuing to claim an unmodified artifact.

### 9.3. Flags cannot restore removed modules

```bash
java --add-modules java.xml.bind -jar app.jar
```

cannot restore `java.xml.bind` on a JDK that no longer ships that module. External dependencies or source/framework migration are required.

## 10. Reflection and JDK encapsulation

### 10.1. InaccessibleObjectException

Newer JDKs enforce strong encapsulation of JDK internals. An older framework performing deep reflection into `java.base` can fail with:

```text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang" to ...
```

JDK 17 marks a major milestone under JEP 403. This runtime exception can occur even when the artifact compiled cleanly on an older JDK with valid class-file versions.

### 10.2. Workarounds provide evidence, not an end state

To confirm root cause in testing, open **only the specific needed package**:

```bash
--add-opens java.base/java.lang=ALL-UNNAMED
```

With named modules, target the specific consuming module. Avoid opening broad swaths of packages just to silence warnings. Opening reflection flags neither restores removed APIs nor guarantees long-term library support.

Sensible sequence:

- Identify the library or agent performing reflective access.
- Verify which vendor release supports the target JDK.
- Use a scoped workaround temporarily if needed for isolation.
- Record the workaround with an owner and expiration date.
- Upgrade the dependency and remove the workaround in a dedicated phase.

### 10.3. Do not blame application source for every reflection error

Exceptions often originate inside dependencies, serializers, ORMs, DI frameworks, mocking libraries, or agents. Recompiling application source **may change nothing**. Trace down the exact component initiating reflective access.

## 11. JVM flags, defaults, and startup configuration

### 11.1. Deprecated or removed flags may be rejected

Across releases, flags covering GC, memory, compilers, or module access can be removed or change defaults. If the JVM aborts immediately with `Unrecognized VM option`, classify it as a **launch configuration incompatibility**.

Document:

- Old flag.
- Old/new JDK versions.
- Declaration location: startup script, container, Helm chart, service manager.
- Vendor-supported replacement option.
- Impact on performance/monitoring after switching.

Never try to work around obsolete JVM flags by editing Java application source.

### 11.2. Watch out for hidden environment flags

Inspect `JAVA_TOOL_OPTIONS` and `JDK_JAVA_OPTIONS`. They can cause the exact same command line shown in CI logs to run with different effective flags.

On servers, Java arguments may come from service managers or container entrypoints. Inspect the **actual running JVM process command line**, not just script templates.

### 11.3. Never weaken security config without justification

If the new runtime rejects a weak TLS certificate or algorithm, do not disable validation just to pass smoke tests. Fix the certificate chain, server policy, truststore, or client library to comply with security requirements.

## 12. Charset, locale, and timezone

### 12.1. JEP 400: UTF-8 default charset since JDK 18

Especially during JDK 17 → 21 migrations, APIs relying on the default charset behave differently if the earlier environment used a non-UTF-8 encoding.

Example:

```java
String text = new String(bytes);
byte[] encoded = text.getBytes();
```

If legacy data uses another encoding, this source fails to state an explicit encoding contract. The newer runtime may garble diacritics, emit different byte output, or fail parsing.

Note that APIs such as `Files.readString(Path)` already specified UTF-8 by contract, so not every file-reading API changed behavior under JEP 400.

### 12.2. Durable fixes

```java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
```

If legacy data uses a different charset, specify that exact charset explicitly per data source. Fixing encoding code is a **well-justified reason** to recompile once a runtime-only probe exposes the discrepancy.

Do not set JVM-wide `file.encoding` merely to mask one legacy file without testing all other data flows.

### 12.3. Locale and timezone data

Upgrading the JDK can update timezone databases or Unicode/locale rules. Cases to test include:

- Date/time formatting with timezones.
- Billing or job schedules spanning daylight saving transitions.
- Locale-sensitive CSV/Excel exports.
- Case conversion and Vietnamese sorting.
- Number, decimal, and currency formatting.
- JSON/XML timestamps and long-term persisted records.

Even when a change reflects a valid upstream update to locale/tz data, assess it against business contracts and backward compatibility.

## 13. TLS, DNS, networking, and I/O

### 13.1. TLS can change even when source does not

A newer JDK or patch release can update its truststore, enabled ciphers, or security policy. Symptoms:

```text
javax.net.ssl.SSLHandshakeException
PKIX path building failed
Received fatal alert: handshake_failure
```

Before recompiling:

1. Identify the real remote endpoint and proxies.
2. Inspect certificate chains, truststores, and hostnames.
3. Compare supported TLS protocols and cipher suites.
4. Determine whether the change came from the JDK, base image, or server.
5. Update infrastructure/configuration per security policy.
6. Re-run integration tests.

### 13.2. DNS and IP family behavior

When changing JDK runtime coincides with a new OS/container image, DNS resolvers, IPv4/IPv6 preferences, or search domains can differ. A service bound to `127.0.0.1` does not automatically listen on `::1`. Check hostnames, ports, caches, network namespaces, and routing before blaming application code.

### 13.3. TCP/UDP edge cases

A single `InputStream.read(buffer)` call is not guaranteed to read an entire message; UDP does not guarantee delivery. Subtle timing or network-stack shifts can expose dormant bugs in framing, timeouts, or concurrent closes.

If failures appear after swapping JDKs, check API contracts and input assumptions. Never claim the JDK broke a contract when code merely "happened to work by timing coincidence" on the baseline.

## 14. Native libraries and agents

### 14.1. JNI/JNA and OS ABI

Pure Java bytecode may run fine on the new JVM while a native library fails to load due to a missing binary, wrong CPU architecture, or incompatible linked system libraries.

Common failures:

```text
java.lang.UnsatisfiedLinkError
```

or native JVM crashes. Check library paths, versions, checksums, OS/CPU ABI, architecture, and loader scripts. Sometimes updating the native runtime library suffices; other times the JNI/JNA bridge must change.

### 14.2. Java agents

Metrics agents, tracing agents, bytecode instrumentation, and attach tooling maintain their own JDK support matrices via ASM/Byte Buddy or JVMTI. If an agent lacks support for the target JDK, startup can crash immediately even when the application JAR is valid.

Check:

- Agent version and minimum/maximum supported JDK.
- Class-file versions the agent can instrument.
- Startup `-javaagent` vs. dynamic attach.
- Module access and security policies.
- Compatibility inside the actual container/runtime.

JDK 21 introduced JEP 451 warnings for dynamic agent loading. Distinguish new warnings from fatal errors, and never disable production observability just to silence warnings.

### 14.3. Migrating native code to FFM is not mandatory by default

The FFM API finalized in JDK 22. If your goal is simply running a Java 17 artifact on Java 21, rewriting JNI to FFM is not required. Native bridge migration introduces distinct ABI, ownership, callback, and platform testing demands—split it into a dedicated effort where appropriate.

## 15. Application servers and deployment models

### 15.1. WARs do not run standalone like JARs

When deploying a WAR, the runtime owner is the application server or servlet container. To isolate **JDK-only** impact:

- Preserve the exact WAR checksum.
- Keep the same server version if it supports both JDKs.
- Preserve shared libraries, data sources, and deployment descriptors.
- Swap only the JVM running the server.
- Deploy and run contract tests.

If the older server does not support the target JDK, a strictly isolated probe is impossible. Record the test clearly as **JDK + server migration**.

### 15.2. Java EE javax and Jakarta jakarta are not binary-compatible

A WAR built against `javax.servlet.*` will not automatically run on a container providing only `jakarta.servlet.*`. The two namespaces are distinct binary package names.

If upgrading the server forces a namespace transition, source/framework/dependency migration is required; Maven's `provided` scope cannot translate one package name into the other.

### 15.3. Executable JARs with embedded containers

A Spring Boot executable JAR packages an embedded servlet engine. Running the exact release JAR on the target JDK keeps that embedded engine fixed as part of the probe.

If you later upgrade Spring Boot's major version, serializers, embedded servers, and Servlet APIs can all change. Treat that as **framework/packaging migration** and test it separately.

## 16. Typical runtime errors and how to classify them

| Symptom | Layer to inspect | Recompile immediately? |
|---|---|---|
| `Unrecognized VM option` | JVM startup flags | No, check launch configuration |
| `UnsupportedClassVersionError` | Class-file level higher than runtime | Use newer JDK or lower build target |
| `ClassNotFoundException` | Dynamic classpath/provider/classloader | Not yet, locate missing class and loader |
| `NoClassDefFoundError` | Runtime linkage or initialization failure | Not yet, inspect root cause |
| `NoSuchMethodError` | API/implementation binary mismatch | Not yet, inspect dependency graph |
| `NoSuchFieldError` | Field descriptor/version mismatch | Not yet, inspect actual JARs |
| `AbstractMethodError` | Incompatible interface implementation | Usually fix dependency mismatch first |
| `IllegalAccessError` | Binary/module access violation | Investigate modules and class loaders |
| `InaccessibleObjectException` | Deep reflection blocked | Upgrade framework or scoped workaround |
| `ServiceConfigurationError` | SPI/provider resources | Inspect provider registration and packaging |
| `UnsatisfiedLinkError` | Native library/ABI/path | Inspect native binary first |
| `ExceptionInInitializerError` | Static initialization failure | Inspect underlying exception |
| `SSLHandshakeException` | TLS/certificate/security policy | Check truststore and endpoint |
| Corrupted text encoding | Default charset/locale | May need source fix once confirmed |
| Fat JAR runs while WAR fails | Container/classloader/provider | Inspect deployment target environment |
| High cold-start latency | JIT/GC/class loading/CPU | Measure and isolate |
| Performance regression | JVM/OS/dependency/backend | Do not edit code before gathering evidence |

This table indicates starting points for investigation. Every failure type has multiple root causes and requires the full stack trace, artifact metadata, and a clean reproduction environment.

## 17. Layered error-investigation method

### Step 1. Read the root cause

Capture the full stack trace and `Caused by` chain. Determine whether failure occurred at JVM launch, class loading, framework bootstrap, or request handling.

### Step 2. Pinpoint the exact class and method

For `NoSuchMethodError`, locate which JAR supplied the caller and which supplied the callee. For `ClassNotFoundException`, inspect dynamic lookup code and class loaders.

### Step 3. Verify actual runtime dependency versions

Identical application JAR checksums do not guarantee identical classpaths if libraries come from server or shared directories. For thin JARs, confirm every dependency stayed unchanged.

### Step 4. Identify JDK-level changes

Check removed modules/APIs, reflective access, native flags, security defaults, timezone/charset changes, and Java agents.

### Step 5. Reproduce in a minimal scenario

For example, invoke one endpoint using JAXB or a fixture containing Unicode strings. Targeted reproduction prevents wholesale framework rewrites over a single isolated bug.

### Step 6. Test the smallest evidence-backed change

If a runtime provider is missing, add that runtime dependency in a new probe branch; if source relies on implicit charset handling, fix source; if a JVM flag is obsolete, adjust startup configuration.

### Step 7. Re-run all relevant gates

A workaround that gets startup green may quietly alter behavior or security. Re-run functional, contract, resource, and performance checks across all impacted areas after every adjustment.

## 18. Runtime diagnostic tools

### 18.1. Inspecting JVM and version details

```bash
"$TARGET_JDK/bin/java" -version
"$TARGET_JDK/bin/java" -XshowSettings:properties -version
```

Properties output may contain environment paths, so scrub sensitive entries before sharing.

Against a running JVM with attach access:

```bash
jcmd <pid> help
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

Exact commands vary across JDKs and builds, and stripped runtime images may omit `jcmd`.

### 18.2. Observing class loading

On modern HotSpot JVMs:

```bash
java -Xlog:class+load=info -jar app.jar
```

shows which location supplied each loaded class. Output volume can be huge; use it in controlled diagnostics, especially on multi-classloader servers.

### 18.3. GC logging and JFR

```bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

JFR can capture startup and runtime execution profiles:

```bash
java \
  -XX:StartFlightRecording=filename=target.jfr,settings=profile \
  -jar app.jar
```

JFR and GC logs illuminate startup, allocations, GC pauses, JIT compilation, and resource pressure per JDK settings. Never treat one JFR event as sole proof of latency root cause; correlate with application metrics and downstream load.

## 19. Running the old artifact still may not satisfy support policy

### 19.1. Technical compatibility differs from vendor support

An older framework release might pass smoke and integration tests on JDK 21 while the vendor still lists that JDK as unsupported.

Distinguish:

- **Technical reality:** which test gates has the binary actually passed?
- **Support policy:** do framework and vendor support matrices cover the combination?
- **Security:** does the dependency still receive security patches?
- **Operations:** can the team troubleshoot failures if vendor support declines assistance?

Compliance-regulated systems may mandate upgrading frameworks even when runtime-only probes pass. That is a support and security requirement, not proof that an older JDK compiled code better.

### 19.2. Runtime-first is an evaluation probe, not a promise to freeze old JARs forever

After migrating the runtime safely, plan subsequent phases to upgrade Maven/Gradle, plugins, frameworks, and dependencies in line with long-term policy.

The key difference is **advancing in evidence-backed phases** rather than changing everything at once.

## 20. Choosing next steps from probe outcomes

| Outcome | Interpretation | Next action |
|---|---|---|
| Startup + contracts + SLO pass | Binary works within tested scope | Consider runtime-only rollout |
| Startup passes, many paths untested | Insufficient evidence | Add integration/contract coverage |
| Invalid JVM flag | Launch config issue | Update flags and re-test |
| Missing JAXB/JAX-WS runtime | Unbundled API/provider | Add external runtime dependency in new branch |
| Blocked reflection | Framework/agent accesses JDK internals | Newer library release or scoped `--add-opens` |
| Native library fails | OS/ABI/native dependency | Update native runtime, or adapt bridge if needed |
| TLS fails | Cert/protocol/truststore | Remediate infra/security policy |
| Garbled encoded data | Charset/locale contract | Likely needs source fix and recompile |
| Bytecode newer than JVM | Unsuitable class-file target | Upgrade runtime or compile for lower target |
| Performance regression | JIT/GC/resource/backend | Profile and isolate before editing source |
| Unsupported application server | Runtime platform | Plan server/framework migration |
| Framework policy disallows version | Support/compliance | Upgrade framework and re-verify |

A passing probe does not mean recompiling will never be needed. It proves **a specific release artifact operates on the target JDK under verified conditions**.

## 21. Three levels of post-baseline change

### 21.1. Level A — Runtime-only

Application artifact, dependencies, and business config stay untouched; only the JDK runtime changes. Certain launch flags may need adjustments for JVM startup, documented explicitly as accompanying config changes.

This carries the narrowest scope and cleanest rollback.

### 21.2. Level B — Runtime and packaging adaptation

Application source remains untouched, while changes may include:

- Adding JAXB/JAX-WS/Activation runtime dependencies.
- Upgrading a native JAR or Java agent.
- Adjusting truststores and runtime configs.
- Repackaging a thin JAR/distribution or updating runtime libraries.
- Changing the container base image to support the new JDK.

Whenever dependencies or packaging change, the deployment bundle checksum no longer matches the baseline. Classify the run as **artifact adaptation** and store separate evidence.

### 21.3. Level C — Recompile or source migration

When imports, new APIs, encoding logic, major framework upgrades, or bytecode targets must change, teams produce a newly built artifact.

Separate two cases:

- **Recompile identical source:** compiler/toolchain or packaging changes without business-code edits.
- **Source migration:** source, config, or generated code changes prior to compilation.

Level C demands broader test coverage, particularly when public APIs, serialized forms, or downstream consumer compatibility shift.

## 22. Why recompiling identical source still requires separate testing

A recompilation can alter:

- Class-file major version.
- Compiler-emitted bytecode sequences.
- Annotation processor output.
- Generated default `serialVersionUID` when omitted explicitly.
- Build-time generated resources.
- Manifest and launcher metadata.
- Resolved transitive dependencies.
- Compiler flags and parameter/debug metadata.
- Multi-release JAR entries.
- Packaging layout and service descriptors.

Not every build triggers all of these, yet recompiling introduces a new variable that requires verification.

If the unchanged binary runs cleanly on Java 21 while an old Gradle plugin fails on JDK 21, you have isolated a **build-tool migration issue**. Runtime-first probes decouple Maven/Gradle modernization from production JVM cutovers.

## 23. Compiler JDK, source level, target, and --release

### 23.1. Keep these distinct

- **Build JVM:** the JDK running Maven or Gradle.
- **Compiler JDK:** the JDK providing `javac` for compilation.
- **Language level:** Java syntax permitted in source files.
- **Target class-file level:** bytecode version emitted.
- **Java platform API level:** standard library APIs exposed to compilation.
- **Minimum runtime JDK:** lowest JVM version capable of executing the artifact.

A newer JDK can compile source targeting an older Java release when `--release` supports that target.

### 23.2. Example using --release

```bash
javac --release 17 -d out src/com/example/Main.java
```

On supporting JDKs, `--release 17` restricts language syntax, bytecode version, and platform APIs to Java 17 within compiler enforcement. Even so, it **does not** verify that third-party dependency JARs run on Java 17.

Always inspect dependencies' minimum supported JDKs and execute the packaged artifact on the lowest real target runtime.

### 23.3. Running on Java 21 does not mandate targeting 21

A service deploying on JDK 21 that still needs rollback safety to Java 17 can keep bytecode target 17. Only target Java 21 when actually adopting Java 21 language/API features or mandated by support policy.

Changing the compiler target is a compatibility commitment toward consumers, not a number to bump solely for cosmetic alignment.

## 24. Case study A — Java 17 JAR running cleanly on Java 21

Suppose a service has:

```text
Application: order-service-4.8.1.jar
Built with: JDK 17
Runtime baseline: JDK 17
Target runtime: JDK 21
Packaging: executable JAR
SHA-256: X
```

Experiment:

1. Fetch the release artifact and record checksum X.
2. Run baseline verification on JDK 17 and archive tests/metrics.
3. Deploy the identical JAR to JDK 21 staging and verify checksum X.
4. Keep config, backing services, and test fixtures constant.
5. Run startup and smoke checks.
6. Exercise ordering, sandbox payments, inventory, and batch jobs.
7. Test serialization/files/TLS, error handling, and graceful shutdown.
8. Measure cold starts, p99, CPU/GC, and run soak tests.
9. Compare all measurements against the baseline.

If every gate passes, **upgrade the runtime first while keeping the existing JAR**, then tackle build-tool and dependency modernization in a separate phase.

If only p99 rises during autoscaling scale-out, analyze warm-up and CPU limits rather than immediately recompiling source.

## 25. Case study B — Java 8 JAR failing on JAXB in Java 21

A Java 8 baseline uses `javax.xml.bind.JAXBContext`. Executing the unchanged binary on Java 21 raises:

```text
NoClassDefFoundError: javax/xml/bind/JAXBContext
```

This reflects API/runtime removal introduced in JDK 11. Proceed as follows:

1. Confirm Java 8 bytecode still loads cleanly.
2. Identify where JAXB API and runtime implementation originated at baseline.
3. Select compatible external `javax`-namespace JAXB dependencies.
4. Add those dependencies to the runtime classpath in a new branch.
5. Verify XML marshalling/unmarshalling and schema contracts.
6. Migrate source to `jakarta.xml.bind.*` separately only if newer frameworks mandate Jakarta.

You do not need to rewrite source to `jakarta.xml.bind.*` immediately solely because JDK 21 stopped bundling JAXB.

## 26. Case study C — WARs and application servers

An older WAR runs on Java/Jakarta EE server version S under Java 11 and needs to move to Java 21:

- If server S supports Java 21, test **the unchanged WAR + server S**, swapping only the JVM.
- If S lacks Java 21 support, the server must upgrade too; document this explicitly as **JDK + server migration**.
- If the newer server transitions from `javax.servlet` to `jakarta.servlet`, source/framework migration is likely required.
- If the newer server bundles updated APIs or providers, check for conflicts against JARs inside `WEB-INF/lib`.

Never conclude "the old artifact is incompatible with Java 21" when the real blocker is the application server's JDK support or a Servlet namespace transition.

## 27. Persisted data and rollback

### 27.1. Runtime-only upgrades can still alter generated data

With an unchanged JAR, changes in default charset, timezone data, or provider behavior can alter files or messages written out.

Test:

- Reading legacy files created under the old JDK.
- Writing files on the new JDK and reading them on the old JDK if rollback demands it.
- Java serialization in sessions and caches.
- Queue message schemas.
- Database date/time and decimal mappings.
- XML/JSON encoding and decoding.
- Native compression and checksum routines.

### 27.2. Two-way compatibility

- **Backward read:** the new version reads data created by the old version.
- **Forward read:** the old version reads new data written after the upgrade.

If rolling deployments or rollbacks keep both runtimes sharing state, determine whether two-way compatibility is required. Startup tests alone cannot answer that.

### 27.3. Rollback must preserve runtime and environment together

Rolling back does not mean keeping only the old JAR. If the runtime image or application server changed, retain:

- Baseline image/JDK.
- Launcher and JVM flags.
- Server/container version.
- Matching library bundles and configurations.
- A handling plan for state written while running the newer version.

If the old server cannot read state produced by the new runtime, rollback may require data migration or dual-write compatibility mechanisms.

## 28. Performance validation goes beyond a single throughput number

### 28.1. Cold vs. steady state

The JIT optimizes hot code progressively; a new JDK can follow a different warm-up curve. Measure:

- JVM/application startup time.
- Time to readiness.
- First-request latency.
- Time to steady SLO.
- Post-warmup throughput.
- p95/p99 latency across both cold and steady phases.

Strong steady throughput alongside terrible cold p99 can still violate autoscaling SLA expectations.

### 28.2. Do not confuse JIT effects with GC, OS, or backend shifts

When performance shifts:

- Inspect JIT compiler CPU usage and compilation events where justified.
- Review GC pauses and allocation rates.
- Check container CPU throttling.
- Measure DB, queue, and network latency.
- Account for class loading and lazy initialization.
- Repeat benchmarks across multiple runs rather than trusting one sample.

The exact same commit can behave noticeably differently across hardware, CPU quotas, or base images unrelated to the JDK compiler itself.

### 28.3. Decide using SLOs

Reports should track error/timeout rates and latency percentiles, not requests per second alone. Evaluate runtime changes by **user-visible behavior and operational cost**, not microbenchmarks inside an IDE.

## 29. Keep probe conclusions strictly bounded

| Evidence | Valid conclusion | Invalid conclusion |
|---|---|---|
| JVM starts | Runtime accepts launcher and loads initial code | Every business path works |
| Health returns 200 | Health handler succeeds | DB writes, queues, and serialization are healthy |
| Integration suite passes | Tested contracts succeed | Untested paths also pass |
| Staging meets perf targets | Tested workload/host meets thresholds | All production traffic patterns match |
| Identical artifact checksum | Application bytes did not change | OS, JDK, external libs, or server stayed constant |
| `jdeps` flags no internals | No static internal reference detected | Reflection or native calls are absent |
| Vendor support matrix | Combination is officially supported | Zero runtime bugs or regressions remain |

Record exact test scope, sample sizes, environment setup, and open risks. Declaring "compatible" unconditionally breeds false confidence.

## 30. Suggested technical report schema

```yaml
migration_probe:
  objective: "Run existing artifact on target JDK first"
  application:
    release: "4.8.1"
    artifact: "order-service.jar"
    sha256: "<same-hash>"
    dependency_manifest: "<manifest-reference>"
  baseline:
    jdk: "<vendor-version-build>"
    image_digest: "<baseline-digest>"
  target:
    jdk: "<vendor-version-build>"
    image_digest: "<target-digest>"
  unchanged:
    application_binary: true
    runtime_dependency_set: true
    business_config: true
  known_environment_differences:
    - "JDK runtime"
  tests:
    startup: "PASS"
    smoke: "PASS"
    contract: "PASS"
    performance: "PENDING"
  result: "INCOMPLETE"
  decision:
    branch: "more-verification-required"
    owner: "<owner>"
```

This template is illustrative. If runtime dependencies change, flip `runtime_dependency_set` to false or log a new probe run. Never mark `result` as PASS while tests remain PENDING.

## 31. Decision workflow in real projects

### Step 1 — Lock the objective

For example: "Upgrade release 4.8.1 from Java 17 to Java 21, minimizing source changes in wave one while meeting SLOs and vendor support policy."

### Step 2 — Freeze the artifact

Record checksums, manifest, dependency set, launch command, and image digest. Do not rebuild.

### Step 3 — Capture the baseline

Execute that exact artifact on the old JDK under representative fixtures/traffic and save logs and metrics.

### Step 4 — Check class files and static dependencies

Inspect class-file targets, multi-release entries, and JDK internal usage with appropriate tools.

### Step 5 — Run the frozen artifact on the target JDK

Keep application configs and external dependencies steady, explicitly documenting any required changes to JDK images or JVM flags.

### Step 6 — Test in layers

Startup → smoke → contract/integration → security/data → performance → soak/failover.

### Step 7 — Classify failures

Separate launch flags, removed JDK APIs, dependencies/providers, reflection, native/agents, TLS, charset, OS/container shifts, and performance.

### Step 8 — Choose the smallest supported fix

If config fixes it, update config. If a runtime dependency is missing, add it in a new probe branch. Recompile and modify source only when API or behavioral logic genuinely demands it.

### Step 9 — Verify support and security compliance

Ensure frameworks, dependencies, and the JDK runtime meet support and security policy; passing smoke tests does not replace compliance review.

### Step 10 — Roll out by thresholds

Deploy via canary, blue-green, or rolling rollout while monitoring errors, latency, and cost, with rollback image/JDK and data compatibility ready.

### Step 11 — Upgrade the build separately

Once the runtime cutover is validated, upgrade Maven/Gradle plugins, annotation processors, toolchains, and source targets in a dedicated, tested phase.

## 32. Common mistakes

| Mistake | Consequence |
|---|---|
| Recompiling before probing runtime | Loses isolation of JDK runtime impact |
| Hashing only the main JAR and ignoring `lib/` | Dependency graph shifts undetected |
| Switching container image families simultaneously | Diffs in CA store, libc, and OS distort comparisons |
| Assuming old class files guarantee runtime safety | JDK APIs or runtime providers may have vanished |
| Assuming `ClassNotFoundException` is a source bug | Often only a missing runtime dependency |
| Adding `--add-opens` everywhere | Hides incompatible libraries and increases risk |
| Using `--add-modules` for deleted modules | Cannot resurrect removed modules |
| Enabling trust-all TLS | Opens security holes and masks real faults |
| Running only `/health` checks | Leaves rare business paths unverified |
| Comparing only post-warmup throughput | Misses cold-start and autoscaling regressions |
| Upgrading JDK, server, and framework together | Makes variable isolation impossible |
| Bumping bytecode target to 21 solely because runtime is 21 | Breaks Java 17 rollback path |
| Skipping persisted-state checks | Rollback risks misreading written state |
| Confusing `--release` with checking third-party deps | External JARs may still demand a newer JVM |
| Ignoring vendor support just because tests pass | Compliance and maintenance exposure remain |
| Leaving workarounds permanent with no owner | Accumulates compatibility debt |
| Omitting checksums, logs, and exact versions | Renders test conclusions irreproducible |

## 33. Handover checklist

- [ ] Identified exact release artifact and retrieval source.
- [ ] Recorded SHA-256 checksums / image digests for artifact and dependencies.
- [ ] Executed no build/recompile step during the runtime-only probe.
- [ ] Verified actual executing JDK processes at both baseline and target.
- [ ] Documented JVM flags, environment variables, and OS/container deltas.
- [ ] Checked class-file major versions across code and relevant dependencies.
- [ ] Checked multi-release JAR entries if present.
- [ ] Checked static JDK internal dependencies and noted limits of `jdeps`.
- [ ] Verified startup and updated removed/legacy JVM launch flags.
- [ ] Executed business smoke and integration/contract tests.
- [ ] Checked previously JDK-bundled APIs and providers where applicable.
- [ ] Checked JPMS/reflection behavior and framework compatibility.
- [ ] Tested TLS/truststore, DNS, charset, and timezone handling.
- [ ] Checked JNI/native libraries and Java agents where used.
- [ ] Measured startup/warm-up, p95/p99 latency, throughput, CPU, GC, and memory.
- [ ] Ran soak, restart, and failure-recovery tests as risk requires.
- [ ] Verified persisted state and two-way rollback compatibility.
- [ ] Classified every failure by layer before choosing fixes.
- [ ] Separated runtime-only, runtime-adaptation, and recompile probes clearly.
- [ ] Recorded dependency/packaging changes explicitly rather than labeling them unchanged artifact.
- [ ] Reviewed vendor/framework support matrices and security policy compliance.
- [ ] Assigned owners and timelines for any temporary flags or workarounds.
- [ ] Defined canary thresholds, rollback runtime/image, and operational runbooks.
- [ ] Decided on recompilation or source migration only with explicit evidence.
- [ ] Handed over results complete with checksums, versions, test scope, and open risks.

**Conclusion:** Running the existing artifact on the target JDK before deciding to recompile is a disciplined way to **reduce moving parts and gather early evidence**. If the existing binary meets functional, operational, and support requirements, teams can cut over the runtime first and modernize build tooling and source separately. If it fails, each issue is cleanly isolated into JVM config, runtime dependencies/providers, reflection, native integration, data encoding, security, or code requiring true modification. This **verify first, modify second** mindset keeps Java compatibility migrations traceable, lower risk, and straightforward to roll back.
