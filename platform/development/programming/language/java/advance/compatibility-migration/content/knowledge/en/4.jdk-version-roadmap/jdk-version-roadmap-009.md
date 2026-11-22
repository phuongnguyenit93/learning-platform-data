# Evaluating a Newer JDK Using Version-Specific Documentation

When considering upgrading a Java application to a newer JDK, the first step is not reading a generic overview of the latest Java release. Identify the exact target JDK, then read the documentation matching that exact version and vendor. Every release can add APIs, alter runtime behavior, remove JVM flags, adjust security defaults, or place new requirements on libraries and build tools. Something true for the current JDK may be false for the version your project plans to adopt.

Version-specific documentation evaluation answers concrete questions: which features exist in the target JDK, which changes impact the application, which components must upgrade together, which risks require testing, and which conditions must be met before shifting the runtime environment.

## 1. Identify the exact target JDK before reading documentation

"Upgrade Java" is too vague a description for planning. First specify:

- **Feature release:** e.g., JDK 17, JDK 21, or JDK 25.
- **Vendor and distribution:** e.g., Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK, or another distribution.
- **Update release:** full version number, release date, or build corresponding to the planned environment.
- **Platform:** operating system, CPU architecture, container environment, or server host.
- **Usage scope:** JDK used to compile, JDK used in production, or both.
- **Current baseline:** JDK and update versions currently used in build, test, staging, and production.

For example, "moving from Java 17 to Java 21" still needs narrowing to a specific distribution, update release, and deployment platform. OpenJDK distributions generally share a common source base and Java specification, yet can differ in release cadences, support policies, installers, CA certificates, build options, management tools, and commercial support commitments.

Distinguish a **feature release** from an **update release**. A feature release introduces a set of language, API, JVM, and tooling changes. An update release focuses primarily on bug fixes and security patches, yet can still affect behavior in specific scenarios. Therefore, feature release docs are the starting point; release notes and security advisories of the exact update/build must still be checked before deploying.

Do not assume every vendor shares the same LTS policy or support window. LTS is a label and support commitment defined by the vendor/distribution policy. Check the support schedule of the exact vendor and JDK line your organization will operate.

## 2. Select the right documentation set for the target version

No single document describes the full impact of a new JDK. Combine multiple sources, each answering a distinct set of questions.

### 2.1. Migration Guide

The target version's Migration Guide is usually the first document to read. It focuses on changes that engineers upgrading from earlier releases must know, such as:

- Features or modules removed, deprecated, or changed in status.
- Default changes in the compiler, JVM, standard libraries, and tools.
- Legacy command-line options no longer supported or no longer effective.
- Changes in encapsulation, reflection, security, networking, and serialization.
- Behavioral shifts that may require source or configuration edits in legacy apps.
- Guidance for replacing removed APIs or options.

A Migration Guide typically does not list every fixed bug or every detail of individual update releases. Use it to build an investigation list, then check release notes and specialized documents accordingly.

### 2.2. Release Notes for the exact JDK and vendor

Release Notes describe the contents of a specific release. Read sections covering changes, known issues, resolved bugs, security fixes, and platform- or vendor-specific notes.

When reviewing, pay attention to:

- Changes that can affect applications relying on older APIs or behavior.
- Whether a bug fix changes outcomes in a case the application currently depends on.
- Whether JVM, GC, compiler, TLS, certificate, or charset options changed.
- Whether limitations, known issues, or workarounds apply to your OS/architecture.
- Whether an update fixes a vulnerability while disabling weak algorithms, protocols, or configs the application still uses.

Do not read one vendor's release notes and assume all packaging and support details match another vendor. The Java specification core is shared, yet installation, updates, support, and certain operational notes can differ.

### 2.3. JEP — Java Enhancement Proposals

A JEP describes the goals, scope, and design of a major change in OpenJDK. JEPs help explain why a feature was added, altered, or removed, which design alternatives were weighed, and the feature's limitations.

When evaluating via JEPs, verify:

1. Which status the JEP holds and which release integrated it.
2. Whether the target version actually contains that change.
3. Which parts are design goals versus actual implemented behavior.
4. Whether subsequent JEPs or release notes modified, finalized, or restricted the feature.

A proposed, preview, or incubator JEP does not mean the API is stable or enabled by default in the target JDK. Do not plan solely from JEP titles without checking status and actual release documentation.

### 2.4. API Documentation and Java specifications

Version-exact Javadoc confirms classes, interfaces, methods, constructors, exceptions, modules, and API status. When an application relies on a specific API, read the docs for the exact target JDK rather than only reading the newest Javadoc page.

Relevant sources include:

- Java SE API Specification/Javadoc for the standard library.
- Java Language Specification for language syntax and semantics.
- Java Virtual Machine Specification for bytecode, class files, and JVM behavior.
- Module system documentation when using JPMS.
- Tool documentation such as `javac`, `java`, `javadoc`, `jdeps`, `jdeprscan`, `jlink`, `jpackage`, and `jshell`.

API docs answer "which APIs exist and what are their contracts"; migration guides and release notes answer "what changed between versions". Use both for a complete assessment.

### 2.5. Framework and library support documentation

A Java SE-compatible JDK does not mean the entire application runs on that JDK. Check support matrices and release notes for Spring Boot, Spring Framework, Hibernate, Jackson, Netty, Tomcat/Jetty, logging frameworks, test frameworks, JDBC drivers, build plugins, and other libraries in use.

For each component, verify:

- Minimum version supporting the target JDK.
- Recommended version and known limitations.
- Co-upgrade requirements or configuration changes.
- Compatibility of agents, annotation processors, bytecode enhancers, and build plugins.
- Changed behaviors or deprecated/removed APIs.
- Whether the version carries security patches and remains supported.

Do not infer compatibility merely because dependencies download or a Gradle build succeeds. A library may compile cleanly yet fail under new runtime checks on modules, reflection, TLS, or API changes.

## 3. Read documentation along the path from current to target version

If a project upgrades across multiple feature releases, read changes from every intermediate version. A change may have appeared earlier and only become an error once the application moves to the final target.

For example, moving from JDK 11 to JDK 21 means not reading only JDK 21 docs. Review important changes from 12 through 21, identifying which impact the app directly versus which were already addressed previously. Likewise, moving from JDK 17 to JDK 25 requires checking the intermediate feature releases rather than comparing only the endpoints.

A systematic approach:

1. Record the full current and target versions.
2. List the feature releases lying between the two milestones.
3. Gather Migration Guides and Release Notes for each milestone traversed.
4. Flag changes likely affecting APIs, bytecode, runtime, security, builds, and deployment.
5. Read JEPs/API docs deeply for changes directly tied to active source code or configs.
6. Check release notes for the exact vendor/update build when preparing for release.

You do not need to log every new feature of every release. Understand enough changes relevant to your system and preserve references so reviewers can verify.

## 4. Change categories to audit in JDK documentation

### 4.1. Java language and compiler

Read changes concerning syntax, the type system, inference, annotation processing, compiler diagnostics, and compilation rules. Identify the source level and bytecode target your project uses.

Questions to answer:

- Does existing source compile under the new compiler?
- Are there new warnings or compile errors from rule changes?
- Do annotation processors, Lombok, MapStruct, QueryDSL, or code generators support the target compiler?
- Are there new APIs or syntax the team intends to adopt, and do they fit the Java baseline other modules must support?
- Are preview features or incubator APIs in use?

Preview features may change or be removed in later releases. When trialing preview features, enable them via that release's exact flags for both compile and run, and do not treat them as stable production APIs. Incubator modules must also be evaluated separately for churn and module/runtime requirements.

### 4.2. Standard libraries and removed APIs

Check new APIs, deprecated APIs, APIs deprecated for removal, and removed APIs. A method may still exist while discouraged; another API may have vanished completely in the target version.

Look for dependencies on:

- Packages or modules once shipped in the JDK that moved to external libraries or were removed.
- Internal APIs in `sun.*`, `com.sun.*`, or implementation details outside the Java SE contract.
- Reflection accessing non-public fields/methods of the JDK or third-party libraries.
- APIs with changed nullability, exceptions, ordering, defaults, or semantics.
- Tools and runtime components no longer bundled as before.

Historical examples show removals can affect more than one line of code: several Java EE/CORBA modules left in JDK 11; Nashorn left in JDK 15; stronger encapsulation shifts landed in later versions. These are only historical milestones, not an exhaustive list for your target JDK. Always verify against the exact version's migration guide.

### 4.3. JVM, bytecode, and module system

Read changes regarding class file versions, verifier, class loading, garbage collection, JIT, memory model, CDS, container awareness, and the module system. Pay special attention when the application uses:

- Java agents or instrumentation/bytecode transformation tools.
- Deep reflection, dynamic proxies, JNI, or native libraries.
- OSGi, JPMS, custom classloaders, or plugin architectures.
- Non-standard JVM flags or deprecated/removed flags.
- Libraries depending on internal JDK APIs.

A newer JDK may keep public APIs intact while changing access rights to internal implementations. If the application relies on those internals, switching runtimes can cause `IllegalAccessError`, `InaccessibleObjectException`, or other linkage failures. Seek public API fixes or library upgrades; use package-opening flags only with clear justification, scope, and removal plans.

### 4.4. Security and network protocols

Read notes on TLS, cipher suites, certificates, keystores/truststores, cryptographic algorithms, LDAP, serialization, deserialization filters, authentication, and security providers. Security updates may disable weak algorithms or change defaults, preventing legacy partner systems from connecting.

Verify:

- TLS versions and cipher suites negotiated by servers/clients.
- Certificate chains, CAs, hostname verification, and certificate validity windows.
- Hash algorithms, signatures, key sizes, and cryptographic providers.
- Authentication mechanisms for HTTP, LDAP, databases, and message brokers.
- Handling of serialized data from untrusted sources.
- Security properties and config files such as `java.security`.

Do not fix errors by disabling certificate checks or broadly re-enabling weak algorithms. First identify the specific change in release notes, inspect both endpoints' configs, and coordinate partner upgrades.

### 4.5. Charset, locale, timezone, and data formatting

Read changes involving default charsets, locale data, timezone databases, date/time formatting, Unicode, and number formatting rules. A default change can alter files or data produced on a newer version even with unchanged source code.

For instance, JEP 400 standardized UTF-8 as the default charset starting in JDK 18 in the described environments. If an application previously relied on the OS default charset, upgrading can alter file reads/writes. Explicitly specify charsets for contracted protocols and files, such as `StandardCharsets.UTF_8`, instead of relying on defaults.

Also verify:

- Whether timestamps are stored in UTC or local time.
- Daylight saving time handling and updated timezone databases.
- How locales affect parsing/formatting of dates, decimals, and currency.
- Unicode normalization and non-ASCII characters.
- Serialization of dates/times, enums, and high-precision numbers.

### 4.6. Garbage collectors, performance, and resources

A newer JDK may alter defaults or refine G1, ZGC, Shenandoah, JIT, thread scheduling, memory ergonomics, and how the JVM detects container limits. Do not assume performance improves merely because a newer JDK has strong benchmarks.

Check active JVM flags, heap sizing, metaspace, direct memory, thread pools, startup times, throughput, pause times, and footprint. An old flag may no longer have effect; a new default may shift CPU or RAM consumption inside containers.

Evaluate with representative workloads and matched test conditions: data, concurrency, CPU/memory limits, instance count, warm-up, GC logs, and metrics. Compare not just average response time, yet also p95/p99, throughput, allocation rate, GC pauses, startup, and resource consumption.

### 4.7. JDK tools and application packaging

Inspect build, debugging, packaging, and runtime tools. Changes to `javac`, `java`, `javadoc`, `jdeps`, `jdeprscan`, `jlink`, `jpackage`, JShell, or monitoring tools can impact pipelines and operational procedures.

If building custom runtime images with `jlink`, verify module closure and service bindings. If using `jpackage`, verify installers, service integration, and OS differences. If packaging containers, verify base images, libc, CA certificates, timezone data, fonts, user permissions, and CPU architectures.

## 5. Using JDK tools to verify findings from documentation

Documentation explains what can change; tooling shows what the application actually depends on. The following commands are common examples; check available options in your active JDK before running.

### 5.1. Verify the real environment

~~~bash
java -version
javac -version
./gradlew --version
~~~

For Maven, check the Maven version and the JDK running the Maven process. In CI, containers, and production, record real versions rather than relying solely on developer workstations.

### 5.2. Find dependencies on internal APIs

~~~bash
jdeps --jdk-internals path/to/application.jar
~~~

`jdeps` can detect references to internal JDK APIs in scanned bytecode. Output helps pinpoint libraries or classes needing replacement. It cannot detect every dynamic reflective access, string-constructed class name, JNI call, or runtime-only behavior. Combine it with source searches, dependency audits, and integration tests.

### 5.3. Find deprecated APIs in bytecode

~~~bash
jdeprscan --release <target-release> path/to/application.jar
~~~

`jdeprscan` helps scan references to deprecated APIs for a given release, depending on tool version. Options like `--for-removal` can be added when appropriate. Read `jdeprscan --help` on the active JDK to confirm syntax and coverage. Results do not replace reading migration guides: several behavioral or config changes do not manifest as deprecated API references.

### 5.4. Compile against the target version's APIs

With `javac`, `--release` selects language level, bytecode, and platform APIs matching a compiler-supported target release:

~~~bash
javac --release <target-release> -d out @sources.txt
~~~

In Gradle, configure a Java toolchain for the build JDK and configure the release target for the compiler. In Maven, use the matching compiler plugin config. Distinguish:

- **JDK/toolchain:** which compiler and tools actually run.
- **Source level:** which Java syntax is accepted.
- **Target bytecode:** which runtime class files target.
- **Release/API baseline:** which Java SE APIs may be referenced at compile time.

Setting only `source` and `target` does not constrain callable platform APIs. If the goal is ensuring bytecode never calls APIs newer than the baseline, use `--release` or your build tool's equivalent.

## 6. Mapping documentation findings to the application

Reading documentation without tying it to current code/config produces only a generic list of changes. Create a findings table so every change either links to concrete evidence in the system or is explicitly marked unknown.

| Field | Content to record |
|---|---|
| Current/target JDK | Feature release, vendor, update/build, and platform |
| Documentation source | Migration Guide, Release Notes, JEP, API docs, or vendor note |
| Change item | Specific title, section, or JEP number |
| Impact domain | Source, binary, API, JVM, security, network, data, build, or deployment |
| Trace in application | Relevant class, dependency, config, JVM flag, schema, or endpoint |
| Usage status | Actively used, present on classpath only, unverified, or unused |
| Impact | Build failure, runtime failure, behavioral shift, security, or operations |
| Action | Edit code, upgrade dependency, change config, coordinate with partner, or accept under controls |
| Verification | Unit, integration, contract, performance, security, or deployment test |
| Owner/status | Verifier, priority, and completion evidence |

Illustrative examples:

| Documentation finding | Trace to search for | Remediation direction |
|---|---|---|
| Stronger encapsulation of internal APIs | Reflection, internal package imports, agents | Replace with public APIs or upgrade libraries; runtime tests |
| Default charset changed | `FileReader`, `FileWriter`, `new String(bytes)` omitting charset | Specify charset per contract; test files with non-ASCII chars |
| TLS/security defaults changed | HTTP clients, JDBC, truststores, cipher configs | Verify TLS negotiation and certificates in real environments |
| API removed | Source code, dependency bytecode, generated code | Upgrade or replace API; compile and test with target JDK |
| JVM option changed | `JAVA_TOOL_OPTIONS`, startup scripts, container args | Verify flags and measure performance on representative workloads |

These examples illustrate the mapping method, not conclusions about any specific target JDK. The chosen target version dictates which changes actually apply.

## 7. Assessing impact severity and prioritizing work

Not every item in release notes carries equal risk. Evaluate using four factors:

1. **Relevance:** does the application use the mentioned API, flag, or behavior?
2. **Impact:** if affected, does it cause a build failure, startup failure, single-feature error, data corruption, or system-wide outage?
3. **Detectability:** do existing tests reproduce it, or does it surface only under load, rare data, or production environments?
4. **Recoverability:** can we roll back, can the old version read newly written data, and can we redeploy safely?

Changes can be classified as:

- **Must resolve before migration:** evidence shows the app depends on removed/changed behavior or APIs with no compatibility path.
- **Requires verification testing:** potentially impacted without confirmed failure yet; must be tested on the target JDK.
- **Requires external coordination:** change involves providers, consumers, databases, vendors, or platforms outside team control.
- **Not applicable:** verified unused or outside deployed configuration/distribution. Record rationale and evidence.
- **Unknown:** missing code, runtime, owner, or config facts; never silently mark as "not applicable".

Prioritize changes affecting security, data integrity, startup ability, inter-system connectivity, and rollback safety. A deprecation warning might not break immediately, yet if marked for removal on a near horizon, schedule remediation before further upgrades.

## 8. Validation testing on the target JDK

After reviewing docs and listing findings, run the application on the exact target JDK. Do not merely compile with a newer compiler while running production on the old runtime—or vice versa—when the migration goal changes both.

A validation suite can include:

- **Build tests:** compile all modules, annotation processors, generated sources, test sources, and packaging tasks.
- **Unit tests:** focus on APIs, date/time handling, charsets, serialization, reflection, and runtime-dependent logic.
- **Integration tests:** databases, message brokers, HTTP services, object storage, identity providers, and key adapters.
- **Contract tests:** request/response payloads, event schemas, file formats, and supported provider/consumer versions.
- **Data migration tests:** reading old data, writing new data, backfills, message replays, and rollback checks.
- **Security tests:** TLS, certificates, authentication, authorization, crypto providers, and deserialization.
- **Performance tests:** startup, throughput, p95/p99 latency, GC pauses, memory, and CPU in production-equivalent environments.
- **Operational tests:** health checks, shutdown, restarts, rolling deploys, logging, metrics, tracing, alerts, and backup/restore.

Use representative data and production-like environments. Tests with empty databases or mocks can miss failures caused by historical data, certificates, quotas, network policies, or real vendor configurations.

If the system has multiple providers/consumers, test version combinations that can coexist during rollout and rollback—for example, new provider with old consumer, old provider with new consumer, and new/new pairs. Combinations impossible under deployment architecture need not be tested, yet document the exclusion rationale.

## 9. Common mistakes when reading JDK documentation

**Reading only "What's New" feature highlights.** Overview pages focus on headline features rather than compatibility changes. Read the migration guide and release notes.

**Reading docs for the latest release instead of the target release.** Latest Javadoc may describe APIs absent from the JDK your project is deploying. Open docs for the exact target release.

**Reading JEPs without checking implementation status.** A JEP may be proposed, preview, incubator, or revised across releases. Confirm it actually shipped in your target JDK and in what state.

**Comparing source code only.** JVM configs, build plugins, agents, container images, certificates, and database drivers can also be affected.

**Treating deprecation warnings as immediate breakage.** Deprecated does not always mean removed, yet check severity, removal timelines, and replacement plans.

**Treating zero compile errors as full compatibility.** Binaries, runtime behavior, security, data, and performance each require separate evidence.

**Ignoring vendor updates.** The same feature release does not guarantee identical support policies, patches, installers, or operational notes across vendors.

**Failing to preserve sources and decisions.** When reviewers cannot tell which doc section backs a conclusion, verifying or updating assessments when the target JDK shifts becomes difficult.

## 10. Checklist for evaluating a newer JDK

Before proposing an upgrade, confirm:

- [ ] Identified current and target JDKs including vendor, feature release, update/build, and platform.
- [ ] Checked support policies and lifecycles of the exact distribution.
- [ ] Read Migration Guide and Release Notes for the target version.
- [ ] Read intermediate release notes if crossing multiple feature releases.
- [ ] Verified relevant JEPs shipped in the target JDK and checked their exact status.
- [ ] Cross-checked API docs and language/JVM specifications where relevant.
- [ ] Checked compatibility matrices for frameworks, libraries, drivers, plugins, and agents.
- [ ] Audited deprecated/removed APIs, internal APIs, reflection, and JVM flags.
- [ ] Audited TLS, certificates, crypto, charsets, locales, timezones, and serialization.
- [ ] Checked build toolchains, bytecode targets, container images, and deployment configs.
- [ ] Executed builds/tests on the target JDK and tested critical integrations.
- [ ] Documented risks, evidence, owners, mitigations, and rollback criteria.

## 11. Outputs of the evaluation step

The result should not merely state "the new JDK brings many improvements" or "the application seems compatible". Produce an assessment directly actionable for decision-making:

1. **Target baseline:** JDK, vendor, update/build, OS/architecture, and build/runtime roles.
2. **References:** links or internal paths to Migration Guides, Release Notes, JEPs, API docs, vendor support matrices, and framework docs.
3. **Relevant change list:** each entry paired with version, doc section, and impact domain.
4. **Application evidence:** affected dependencies, classes, configs, JVM options, schemas, or runtime traces.
5. **Compatibility assessment:** source, binary, behavior, security, data, performance, and operations.
6. **Remediation plan:** code/config edits, dependency upgrades, external coordination, and rollout sequence.
7. **Test plan:** environments, datasets, version combinations, pass/fail criteria, and owners.
8. **Decision:** ready to upgrade, conditional on prerequisites, or deferred due to proven blockers.

Every conclusion must distinguish verified facts, documentation-based findings, and open questions. If compatibility of a library is unknown, mark it "unverified" and specify which release notes to check or tests to run. Never turn the absence of observed errors into proof that no risk exists.

Evaluating a newer JDK from version-specific documentation turns vague impressions about features into evidence-based engineering decisions. When targets are pinned precisely, documentation is read for the exact release, and every change is traced to code, dependencies, data, and runtime environments, teams can predict impacts, focus testing effectively, and choose a safer upgrade path.
