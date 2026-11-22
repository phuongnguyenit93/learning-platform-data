# Choosing the Target Version Based on Application and Ecosystem Requirements

When planning a Java migration, choosing the target version is an architectural and operational decision. The latest version is not automatically the best choice; the oldest version the application still runs on is not always a safe choice either. The target version must simultaneously meet application requirements, support durations, frameworks, libraries, build tools, deployment platforms, and the organization's operational capabilities.

This lesson is part of **Java Advance Compatibility Migration**, under the **Versions and Roadmap** chapter. The content focuses on how to identify a target Java version that can be deployed and maintained long-term, how to evaluate ecosystem constraints, and how to turn that decision into a verifiable migration roadmap.

## 1. Why Can't You Choose a Java Version with Just One Number?

A requirement like "upgrade the application to Java 25" may refer to multiple different goals:

- Using JDK 25 to run Gradle or Maven.
- Using the JDK 25 compiler to compile source code.
- Compiling bytecode and constraining APIs to Java 25.
- Running the production application on JVM 25.
- Upgrading frameworks, libraries, and tools to support the Java 25 platform.
- Using a language or runtime feature available only in a newer Java version.

These goals are related, yet do not have to change all at once. For example, a team can use JDK 25 on CI to compile the application with release 21, then deploy the artifact on JVM 21. Another team can keep the Java 17 artifact unchanged and upgrade only the production runtime to Java 21.

Therefore, before picking a target number, identify precisely which components must change and which compatibility contracts must be preserved.

A Java application is affected by multiple layers:

~~~text
Business requirements and application features
                 |
                 v
Source code + Java APIs used
                 |
                 v
Compiler + build tool + annotation processors
                 |
                 v
Bytecode + framework + dependencies
                 |
                 v
JVM + operating system + container + deployment platform
                 |
                 v
Monitoring, security, support, and production operations
~~~

A target version is only feasible when the critical layers are all compatible. A framework that does not yet support the new version, an unverified JDBC driver, or a monitoring agent that does not run on the new JVM can block the migration even if the source code compiles cleanly.

## 2. Understanding Java's Release and Support Lifecycle

### 2.1. Feature Releases and LTS

Java releases on an approximately six-month cadence. Feature releases introduce language, API, JVM, and standard library changes on each cycle. Among these, certain releases are designated by vendors as Long-Term Support (LTS) and receive longer maintenance under their policies.

LTS generally suits systems that require:

- Stable operation over many years.
- Planned security patching and periodic updates.
- Lower frequency of major migrations.
- Clear support from frameworks, libraries, and vendors.
- Time for testing, approval, and rollout across multiple environments.

Non-LTS feature releases are not the wrong choice. Some organizations proactively update regularly to gain new improvements and avoid accumulating a large version gap. However, that strategy requires strong automated test pipelines, fast deployment capability, and a steady upgrade cadence.

### 2.2. LTS Is Not an Identical Support Commitment Across All JDKs

The LTS label does not automatically guarantee that every Java distribution is supported for the same duration. You must check the policy of the exact JDK vendor you use.

Vendors can differ in:

- End date of free security updates.
- Commercial support duration.
- Which versions receive backported patches.
- Terms of use in production environments.
- Level of support for operating systems and CPU architectures.
- Update distribution channels and vulnerability advisories.
- Technical support commitments and response times.

Therefore, deciding "choose Java 21 LTS" is not enough. You must specify which distribution, which update source, which support policy, and who owns tracking that lifecycle.

Examples of common JDK distributions include Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK, and Red Hat build of OpenJDK. Each distribution has its own policies, platform scope, and support model. Do not infer one distribution's support timeline from another distribution's information.

### 2.3. How to Read a Support Schedule

When evaluating a version, distinguish:

| Concept | Meaning |
|---|---|
| GA release | When the version is officially released |
| Public update | Updates released broadly to the public |
| Security update | Security patches for the release branch |
| End of public updates | End of public updates under the vendor's policy |
| End of support | End of support under a specific contract or policy |
| Extended support | Additional support phase, potentially with conditions or fees |
| Container image lifecycle | Lifecycle of the packaged OS and JDK image |

A version may still run fine yet no longer receive patches in the channel the organization uses. Conversely, a new version may have reached GA while some libraries or deployment platforms lack stable compatible releases.

**As of late 2026**, Java 25 is a new LTS milestone, while Java 26 belongs to the feature release cadence. This is an example of distinguishing release types; when making real-world decisions, you must still verify the support status of your exact JDK vendor and the platforms your application uses.

## 3. Distinguishing Four Versions in the Pipeline

A common planning mistake is recording only a single "Java Version" field. In practice, at least four configurations must be recorded.

| Component | Role | Question to Answer |
|---|---|---|
| JDK running the build tool | JVM running Gradle/Maven and build plugins | Do the Gradle/Maven wrappers support this JDK? |
| Compiler toolchain | JDK providing `javac` for compilation tasks | Which JDK does the actual compiler come from? |
| Target release | Restricts syntax, platform APIs, and bytecode | Which Java version must the artifact support from? |
| Production runtime | JVM executing the application | Which JVMs does the deployment platform supply and support? |

These versions may be the same or different.

Example:

~~~text
JDK running Gradle:    25
Compiler toolchain:    25
Target release:        21
Production runtime:    21
~~~

The configuration above can work if Gradle and all plugins support running on JDK 25, source code and dependencies do not exceed Java 21 APIs, and the artifact is tested on JVM 21.

If the target release is 25, the bytecode may not run on JVM 21. If you upgrade only the production runtime to 25 while keeping a Java 21 artifact, the application still needs testing because JVM and standard library behaviors can change.

### 3.1. Target Release Must Reflect the Lowest Java Level Required

Suppose a library is used by multiple services:

- Service A still runs Java 17.
- Service B runs Java 21.
- Service C has moved to Java 25.

If the library publishes an artifact compatible only with Java 25, Services A and B cannot use that artifact on their current runtimes. If the library keeps a Java 17 target release, all three services can share the artifact when dependencies and APIs are compatible.

This shows that a library's target version is often governed by the consumer with the lowest runtime requirement. For a standalone application, the team can choose a different target based on that application's own deployment environment.

### 3.2. Do Not Confuse Source Compatibility with Runtime Compatibility

A project can compile successfully with a newer compiler yet fail to run on an older runtime if it uses newer APIs or emits newer bytecode.

With JDK 9 and newer, the **--release** option is usually the clearest way to simultaneously constrain language features, platform APIs, and class file version to the target release.

~~~bash
javac --release 21 -d out src/com/example/Main.java
~~~

Configuring release correctly still does not prove every dependency is compatible. Third-party libraries may be compiled for a higher Java version or use APIs absent in the target runtime.

## 4. Starting from Application Requirements

The right Java version depends on the application's characteristics and goals.

### 4.1. Which Features Does the Application Need?

Identify which features or APIs genuinely drive the upgrade:

- Records to represent immutable data types.
- Pattern matching or switch expressions to clarify logic.
- Virtual threads to handle high concurrency under a blocking model.
- Foreign Function & Memory API when modern native interop is needed.
- Garbage collector, JIT, or startup time improvements.
- Security APIs, TLS, or new algorithms.
- Platform APIs for data processing, date/time, or I/O.

Do not upgrade merely to "use new syntax". Identify measurable benefits or concrete technical requirements. A new feature may require changes to application design, resource limits, observability configuration, or error handling.

For example, virtual threads can help an I/O-bound application handle more blocking tasks with lower thread overhead in some cases. Yet switching to virtual threads does not automatically speed up CPU-bound workloads, nor does it remove limits from connection pools, databases, external APIs, or inappropriately synchronized code regions.

### 4.2. Performance and Load Requirements

When the goal is performance improvement, do not choose a version based solely on generic benchmarks. Characterize the actual workload:

- CPU-bound vs. I/O-bound.
- Concurrent request count.
- Heap size and container memory limits.
- Garbage collector pause frequency and duration.
- Startup and warm-up time.
- Throughput, p95/p99 latency, and error rate.
- CPU, RAM, and infrastructure cost per request.

A new version may improve one workload type while not improving another. Run benchmarks with identical data, configuration, resource limits, and load conditions for a fair comparison.

### 4.3. Security and Compliance Requirements

A system may be forced to upgrade because:

- The current JDK branch is reaching end of patch support.
- Internal security policy requires a supported version.
- Cryptographic or TLS standards no longer accept legacy configurations.
- Rules govern provenance, signing, or runtime update processes.
- The current OS or container image has reached end-of-life.
- Security reviews require removing internal APIs or vulnerable libraries.

In this situation, the target version must have a clear security update channel and meet audit requirements. Simply picking a higher version number without specifying the vendor and patching policy leaves an operational gap.

### 4.4. Product Lifespan and Rate of Change

An internal service may deploy frequently and upgrade the JDK on short cycles. A core system, on-premises customer software, or an application deployed in constrained environments may need longer support windows.

Consider:

- Expected years to maintain the version.
- Product release frequency.
- Ability to upgrade the runtime independently of business releases.
- Number of environments and customers requiring coordination.
- Change approval lead time.
- Rollback and side-by-side deployment capability.
- Team capacity to track Java changes every six months.

Long-lived applications typically need a long-term supported baseline and a periodic review schedule. Continuously delivered products can track feature releases if the organization has strong testing capabilities.

## 5. Evaluating the Entire Ecosystem

A Java version is viable only when the critical components surrounding the application support it.

### 5.1. Frameworks and Application Platforms

Check the primary framework and extensions:

- Spring Framework and Spring Boot.
- Jakarta EE application servers.
- Quarkus, Micronaut, or Helidon.
- Hibernate, JPA providers, and integration modules.
- Security, serialization, validation, and messaging frameworks.

Read official compatibility matrices or release notes to see which framework version supports the target JDK. Do not assume that because a framework supports Java 21, every plugin and extension of it also supports Java 21.

For multi-module frameworks, verify runtime, build plugins, test support, and integrations. An application might run locally yet fail to build on CI because a build plugin does not yet support the new JDK.

### 5.2. Build Tools and Plugins

Build tools also have their own version requirements. Confirm:

- Gradle Wrapper or Maven Wrapper can run on the target JDK.
- Compiler plugins support the required toolchain and release.
- Annotation processors are compatible with the new compiler.
- Testing, coverage, static analysis, and packaging plugins work properly.
- Code generation, bytecode enhancement, or instrumentation plugins support the new class file version.
- IDE and developer setups align with CI.

Do not upgrade the JDK before checking whether the build tool itself can run on it. If the Gradle Wrapper does not support the new JDK, the build can fail before the compiler is even invoked.

### 5.3. Libraries and Dependencies

Dependencies can constrain the minimum or maximum tested Java version. Inspect:

- Internal libraries and third-party libraries.
- JDBC drivers and database clients.
- Kafka, AMQP, and messaging clients.
- HTTP clients, cloud SDKs, and authentication libraries.
- JSON/XML serializers and data formatting libraries.
- Logging, metrics, tracing, and monitoring agents.
- Cryptography, TLS, and certificate libraries.
- Native libraries and JNI bindings.

Distinguish **which JDK compiled a library** from **which minimum runtime the library requires**. A library built with a new JDK using an older release target can still run on an older runtime. Conversely, a library built targeting a newer release can force the entire application to upgrade its runtime.

Read artifact metadata, support documentation, and release notes. When information is missing, run a small test on the target JDK instead of guessing.

### 5.4. Agents and Observability Tools

Agents often hook into class loading, bytecode, or JVM startup. Examples:

- APM agents.
- Java profilers.
- Code coverage agents.
- Security agents.
- OpenTelemetry Java agent.
- Organization-developed monitoring or diagnostic agents.

Agents can depend on internal APIs, bytecode formats, attach mechanisms, or JVM options. Therefore, verify that the agent version supports the target JDK and test both startup and operation in a real runtime.

An application running successfully without agents does not prove the production system is compatible.

### 5.5. Operating System, Containers, and Infrastructure

Check the real deployment environment:

- Linux distribution or Windows Server.
- x86-64, ARM64, and supported architectures.
- Container base image and update policy.
- Kubernetes, PaaS platforms, or application servers.
- Serverless runtimes and vendor-imposed JDK version limits.
- JNI, native executables, and system libraries.
- CA certificates, timezone database, locales, and fonts.
- Memory limits, cgroups, file descriptors, and OS permissions.

A JDK may exist for an operating system yet lack vendor support on the specific architecture or platform in use. Container images also have their own lifecycles; upgrading the JDK while keeping an end-of-life base image does not fully satisfy security requirements.

### 5.6. Android and Native Image Cases

Not every Java product runs on a traditional server JVM.

For Android, review the Android Gradle Plugin, D8/R8, minimum Android API level, desugaring, and the subset of Java APIs supported by the Android platform. Having Java 21 or Java 25 as the build machine JDK does not mean Android devices run a matching JVM.

For GraalVM Native Image, verify the GraalVM version, Native Image builder, framework integration, reachability metadata, reflection configuration, and native library support. A dependency working on the HotSpot JVM may need extra configuration or may not yet work in a native executable.

## 6. Building a Compatibility Matrix Before Selecting a Version

Create a table per application or module group. Every component should list its current version, target requirement, and support evidence.

| Component | Current | Requirement to Verify | Outcome |
|---|---|---|---|
| JDK distribution | Active distribution | Are releases and patch channels available for target? | Pass/Block |
| Build tool | Current Gradle/Maven | Can it run on the build JDK? | Pass/Block |
| Compiler | Current toolchain | Does it support the target release? | Pass/Block |
| Framework | Spring/Jakarta/other | Which framework version supports target? | Pass/Block |
| Dependencies | Key libraries | Minimum runtime and compatibility matrix? | Pass/Block |
| Test tooling | JUnit, Mockito, coverage... | Does it run with the new JDK and bytecode? | Pass/Block |
| Agents | APM, tracing, security | Does it support the target JVM? | Pass/Block |
| Native components | JNI, drivers | Are binaries available for the right platform? | Pass/Block |
| Deployment | OS, container, cloud | Is a supported runtime available? | Pass/Block |
| Operations | Monitoring, backup, rollback | Are operational procedures ready? | Pass/Block |

Three statuses can be used:

- **Pass:** supported by documentation or sufficiently reliable test evidence.
- **Block:** an incompatible component exists or the platform does not provide the needed runtime.
- **Unverified:** insufficient evidence yet; must be checked before committing to the roadmap.

Do not treat "unverified" as "pass". A useful matrix stores evidence links, documentation versions, check dates, and the owner responsible for verification.

## 7. Selecting a Version Based on System Constraints

### 7.1. Independent, Easily Deployable Applications

A service with its own container, controlled dependencies, and automated CI/CD pipelines usually has more flexibility.

You can favor a newer LTS if:

- Frameworks and dependencies already support it.
- Suitable container image updates exist.
- Agents and operational tools have been verified.
- A representative staging environment exists.
- Rollouts can proceed instance-by-instance or by service group.
- A rollback path to the previous image and artifact exists.

In this case, choosing a newer version extends the interval before the next migration, though you must still weigh the cost of upgrading the ecosystem.

### 7.2. Applications Heavily Dependent on External Systems

An application integrated with an application server, database, middleware, message broker, proprietary agent, or cloud SDK can be constrained by the slowest-moving component.

Select a version supported by the entire dependency chain. If a component is not yet compatible, determine:

- Is there a drop-in upgrade?
- Can that component be replaced independently?
- Does the vendor have a support roadmap?
- Can one module temporarily remain on the old runtime?
- Does keeping the old runtime violate security policy?

If there is no workaround, that version is not yet a viable target for the current deployment wave.

### 7.3. Libraries Shared Across Multiple Applications

A library consumed by multiple applications must consider the lowest runtime level that consumers need to support.

Example:

~~~text
Consumer A: Java 17
Consumer B: Java 21
Consumer C: Java 25

Shared library:
  Release target: Java 17
~~~

If the library does not need new features, keeping a Java 17 target release preserves shared usability. If it needs features exclusive to Java 21, the team must coordinate upgrading the consumer baseline or supplying separate compatible artifacts/branches.

An advanced option is a Multi-Release JAR: keeping the base implementation for lower Java versions and providing replacement classes inside version-specific directories. Use this only when benefits are clear, as it increases packaging, testing, and diagnostic complexity. Verify the exact classes each runtime selects.

### 7.4. Legacy Systems

A legacy application may rely on:

- Removed or deprecated APIs.
- Unmaintained old libraries.
- Frameworks that do not support newer JDKs.
- Reflection into internal packages.
- Legacy JVM options.
- Discontinued native libraries or agents.
- Incompatible build scripts.

In this situation, do not jump straight to the latest version by default. Identify barriers layer by layer, prioritize replacing dependencies or removing internal APIs, and then target a well-supported version.

If multiple intermediate stops are needed, document the technical reason for each stage. Not every Java version has to be deployed to production; some stages may serve solely to upgrade frameworks or build tools when specifically required.

## 8. Decision Process for Selecting the Target

### Step 1 — Establish the Current Baseline

Record:

- Active JDK distribution and version.
- JDK running the build tool.
- Compiler toolchain and target release.
- Bytecode version of the artifact.
- Primary frameworks and dependencies.
- OS, container, cloud runtime, and CPU architecture.
- Agents, native libraries, and operational tools.

Do not collect data only from a developer's laptop. Verify CI, staging, and production configurations.

### Step 2 — Define Business and Technical Goals

Examples:

- Retire an unsupported runtime.
- Meet security requirements.
- Reduce operational cost.
- Improve throughput or latency.
- Adopt a new API.
- Standardize runtimes across services.
- Close the gap between developer and CI JDKs.

Each goal needs measurable criteria. If the goal is merely "use newer Java", the team lacks grounds to weigh costs and benefits.

### Step 3 — Identify Candidate Versions

Usually compare a few meaningful options:

- Current LTS well-supported by the ecosystem.
- Newer LTS if frameworks and dependencies are ready.
- A feature release if the organization follows a rapid-update strategy and needs a specific feature.
- An intermediate baseline if a legacy system cannot jump directly.

There is no need to survey every Java version ever released. List only options capable of meeting goals with a realistic deployment path.

### Step 4 — Check the Compatibility Matrix

For each candidate, check:

1. Is the JDK distribution approved by the organization and still supported?
2. Can the Gradle/Maven wrapper run on the build JDK?
3. Do frameworks and application servers support that runtime?
4. Do critical dependencies support that runtime and bytecode?
5. Are agents, profilers, and security tools compatible?
6. Do containers, OSes, CPU architectures, and cloud platforms provide a suitable runtime?
7. Do test frameworks and build plugins work?
8. Can the version be patched and maintained for the expected duration?

Any unclear answer must be logged as a verification item.

### Step 5 — Evaluate Migration Benefits and Costs

Do not compare Java features alone. Estimate:

- Number of dependencies needing upgrades.
- Number of modules requiring source edits.
- Scope of framework or configuration changes.
- Regression testing effort.
- Image and infrastructure update costs.
- Impact on customers or consumers.
- Operational and rollback risks.
- Remaining support lifespan of the target.

A version with more features that demands upgrading the entire framework and middleware stack may cost more than it returns right now.

### Step 6 — Test on a Representative Slice

Pick a module or service with representative dependencies, traffic, and deployment topology. Perform:

- Build with the planned toolchain.
- Check target release and bytecode.
- Run unit, integration, and contract tests.
- Start the application on the target JVM.
- Test database, messaging, HTTP, TLS, and authentication.
- Run monitoring agents and security tools.
- Measure performance under representative workload.
- Test deploy, restart, shutdown, and rollback.

A simple test running one plain Java class is not enough to prove the application's ecosystem is compatible.

### Step 7 — Lock Target and Record Conditions

The final decision should record:

- Target Java version.
- JDK vendor and distribution.
- Build JVM and compiler toolchain.
- Bytecode target release.
- Minimum production runtime.
- Frameworks and dependencies requiring upgrades.
- Unverified components.
- Support milestones and next review date.
- Testing criteria and rollback plan.

If blockers remain, the decision should clearly document conditions for approval instead of presenting the target as ready.

## 9. Example Configuration Separating Toolchain and Target Release

Suppose the organization wants to build with JDK 25 while some services still need to support Java 21. You can separate the compiler toolchain from the target release.

### 9.1. Gradle

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

This configuration specifies:

- The compiler toolchain uses JDK 25.
- Source code is compiled under Java 21 restrictions.
- Bytecode is emitted for release 21.
- Production runtime must support at least Java 21, provided dependencies and libraries also meet that requirement.

Also verify whether the Gradle wrapper version can run on JDK 25. The JDK running the Gradle daemon and the compiler toolchain are two separate settings.

### 9.2. Maven

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

The release configuration does not automatically pick the JDK running Maven. Manage the build environment's JDK, Maven version, Compiler Plugin, and other plugins separately.

### 9.3. Verifying the Artifact

Inspect class files with:

~~~bash
javap -verbose -classpath app.jar com.example.Main
~~~

Look up the class major version. For example:

| Java release | Major version |
|---|---:|
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Checking one representative class does not prove every class in the JAR has the same version. Bundled dependencies may be compiled against a different release. For multi-module or multi-JAR applications, check all critical artifacts.

## 10. Building a Risk-Based Migration Roadmap

A good roadmap splits changes into verifiable stages.

### Stage A — Preparation

- Inventory JDKs, frameworks, dependencies, agents, and deployment environments.
- Confirm the JDK distribution's support lifespan.
- Pick target candidates and build the compatibility matrix.
- Add missing tests for critical business flows.
- Capture performance and production error baselines.

### Stage B — Standardize the Build Environment

- Upgrade Gradle/Maven wrapper if needed.
- Configure build JDK and compiler toolchain.
- Define target release.
- Update plugins and annotation processors.
- Ensure CI reproduces artifacts consistently.

### Stage C — Update the Ecosystem

- Upgrade frameworks and dependencies per compatibility matrix.
- Replace unmaintained libraries.
- Update JDBC drivers, messaging clients, and SDKs.
- Update agents, profilers, and security tools.
- Resolve internal APIs or incompatible reflection.

### Stage D — Run on the Target Runtime

- Use the artifact built for the chosen release.
- Deploy to a staging environment matching production configuration.
- Verify startup, shutdown, health checks, and integrations.
- Run business, contract, and regression tests.
- Measure CPU, memory, GC, throughput, and latency.

### Stage E — Controlled Rollout

- Deploy via canary or service groups if architecture permits.
- Monitor error rates, latency, saturation, and JVM logs.
- Confirm dashboards and alerts remain functional.
- Retain previous artifacts and images for rollback.
- Expand only after stability criteria are met.

### Stage F — Lifecycle Review

After migration completes, record the new baseline and review schedule. Do not wait until the JDK reaches end-of-life to plan the next upgrade.

## 11. Common Selection Strategies

| Strategy | Suitable When | Points to Note |
|---|---|---|
| Choose latest LTS supported by the ecosystem | Application needs a long lifecycle and frameworks are ready | Verify support policy of the exact vendor |
| Keep current LTS, upgrade runtime first | Need to minimize risk and isolate runtime changes from source | May require a follow-up upgrade later |
| Upgrade toolchain while keeping target release | Want to standardize CI while supporting older consumers | Control APIs and dependencies per release |
| Follow periodic feature releases | Organization has strong CI and frequent deployments | Requires continuous upgrade and testing cadence |
| Choose lowest shared baseline | Library consumed by multiple apps on different versions | May restrict using newer APIs |
| Migrate in multiple stages | Legacy app with many dependencies and constraints | Must clearly manage intermediate states |

No single strategy suits every system. Base the decision on goals, acceptable risk level, ecosystem readiness, and maintenance duration.

## 12. Common Mistakes When Selecting a Target Version

### Choosing the Latest Version Without Checking Frameworks

The compiler may accept the source code while frameworks or plugins do not yet support the new runtime. Check the compatibility matrix and test the full application.

### Looking Only at the LTS Label

LTS does not automatically ensure your distribution still receives patches or is supported on your deployment platform. Check the exact vendor, edition, OS, and support agreement.

### Confusing the Build JDK with the Production Runtime

The CI JDK does not prove production runs the same version. Record the build JVM, compiler toolchain, target release, and runtime separately.

### Ignoring Transitive Dependencies

Your code may not call an old API directly, yet a dependency or agent may use internal APIs, native libraries, or incompatible bytecode. Audit the full critical dependency chain.

### Picking a Target Based on Features Without Real Need

New features deliver value only when solving a concrete problem. Without performance, security, or maintainability needs, migration cost can exceed benefits.

### Testing Only on Developer Machines

Developer laptops can differ from production in JDK vendor, OS, architecture, containers, certificates, locales, agents, and memory limits. Test on a representative environment.

### Waiting Until Just Before End-of-Support to Upgrade

Migrations often require updating frameworks, dependencies, images, tests, and deployment procedures. Starting too late shrinks time to resolve blockers and raises outage risk.

### Upgrading Every Module at Once

Modules may have different dependency profiles and release cadences. Group them by runtime, framework, and risk level, then migrate each group on a suitable roadmap.

## 13. Target Version Decision Template

The following template can be used in technical docs or migration proposals:

~~~text
APPLICATION
  Name:
  Business criticality:
  Deployment model:
  Expected maintenance horizon:

CURRENT BASELINE
  JDK distribution:
  Build JVM:
  Compiler toolchain:
  Compiler release:
  Production runtime:
  Framework:
  Main dependencies:
  OS / container / architecture:
  Agents / native components:

TARGET DECISION
  Target Java release:
  JDK distribution and vendor:
  Build JVM:
  Compiler toolchain:
  Compiler release:
  Minimum production runtime:
  Reason for selecting this target:

ECOSYSTEM COMPATIBILITY
  Build tool:
  Framework:
  Dependencies:
  Test tools:
  Agents:
  Native components:
  Deployment platform:
  Vendor support policy:

APPLICATION REQUIREMENTS
  Required Java features:
  Security requirements:
  Performance goals:
  Compatibility contract:
  Minimum supported consumer runtime:

VALIDATION
  Build and bytecode checks:
  Unit and integration tests:
  Contract and regression tests:
  Runtime smoke tests:
  Performance checks:
  Operational checks:

RISKS AND CONDITIONS
  Known blockers:
  Unverified components:
  Required upgrades:
  Owner and due date:

ROLLOUT
  Pilot module/service:
  Staging criteria:
  Production rollout:
  Monitoring window:
  Rollback artifact and runtime:

LIFECYCLE
  Support source:
  Support end date:
  Next review date:
  Upgrade owner:
~~~

A good decision can explain why this version was chosen, why other candidates were unsuitable, which components are verified, and which conditions remain to be fulfilled.

## 14. Key Takeaways When Finalizing a Java Version

Before approving a target, ensure you can answer:

1. Which feature or technical requirement in the application motivates the upgrade?
2. Is the target version LTS or a feature release, and until when does the JDK vendor commit support?
3. Are the build JDK, compiler toolchain, target release, and production runtime defined separately?
4. Do frameworks, build tools, dependencies, test tooling, agents, and native libraries already support it?
5. Do the OS, container, CPU architecture, and deployment platform provide a compatible runtime?
6. Which older consumers or environments must the application remain compatible with?
7. Do build, test, startup, integration, performance, and operational evidence exist on the target?
8. Who tracks security patches and when will the next migration start?

The decision can be summarized in three principles:

- **Meets application needs:** the version must deliver the required APIs, performance, and security level for the product.
- **Supported by the ecosystem:** frameworks, dependencies, build tools, agents, and deployment platforms must have a clear compatibility path.
- **Maintainable in practice:** the vendor offers a suitable support policy, the organization can apply updates, and the roadmap can be tested, deployed, and rolled back.

Only when these three conditions are backed by documentation and testing is the target version truly ready for migration.
