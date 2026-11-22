# Updating Support Documentation, Development Environments, and Operations Guides

## 1. Why Is Documentation Part of Java Compatibility Migration?

When upgrading the JDK, engineering teams usually prioritize source code, dependent libraries, compilation, and testing. Yet a migration can only operate sustainably when people **who do not directly edit code** also know which JDK the system requires, how to set up the environment, how to deploy it, and how to handle incidents when the new release runs into problems.

Suppose a service has moved from Java 17 to Java 21:

- Source is compiled with JDK 21.
- CI has run integration tests.
- Production containers use the Java 21 runtime.
- Yet the README still states “Java 11+”.
- Developer onboarding still sets `JAVA_HOME` to JDK 17.
- A support guide instructs running a diagnostic tool on JDK 8.
- The rollback runbook only swaps the container tag, while schemas or data written by the new release are no longer compatible with the old release.

In that case, **the source code may be right, yet the release process is inconsistent**. Newcomers cannot build the project; support gives wrong instructions; on-call does not know which JVM options/agents are running; customers upgrade in the wrong order; or the runtime can be rolled back while data processing capability cannot be restored.

Within the topic **Java Advance Compatibility Migration — Release and Operations**, this lesson focuses on three groups of documentation:

1. **Support documentation:** Supported JDK/OS/architecture policy, compatibility scope, timelines, and information for customers/support.
2. **Development environment documentation:** JDK/toolchains, Maven/Gradle, IDEs, test environments, containers, native libraries, and failure reproduction procedures.
3. **Operations guides:** Preflight steps, deploy/canary, observability, incident response, rollback/roll-forward, post-deployment verification, and updating with JDK security patches.

The most important principle: **documentation must not be updated independently from artifacts and test evidence**. A claim of “Java 21 supported” needs specific conditions and how to verify them.

## 2. Expected Outcomes After This Lesson

Readers will be able to:

- Build an inventory of documents that must change when upgrading the JDK.
- Distinguish **JDK used for development/compilation**, **bytecode target**, and **production JVM**.
- Write a support matrix for JDK releases, distributions, OS, CPU architectures, and runtime images.
- Update README, IDE guides, Maven/Gradle toolchains, and CI under a single policy.
- Write release notes and migration guides that do not mislead about breaking changes.
- Standardize runbooks for deployment, canary, rollback, and handling JDK/agent/JNI/module errors.
- Provide support with a set of questions, answers, and information sufficient to triage incidents.
- Bring documentation into release gates, ownership, and the update lifecycle instead of fixing it after an incident has occurred.

## 3. Three Documentation Layers That Must Be Consistent

~~~text
                      Product support policy
                 (what the product promises)
                                |
              +-----------------+-----------------+
              |                                   |
              v                                   v
       Developer documentation              Operations runbooks
       (how to build and test)             (how to deploy and recover)
              |                                   |
              +-----------------+-----------------+
                                |
                                v
                 Release notes / Support FAQ
               (what changed and who is affected)
                                |
                                v
                   Evidence from release CI
~~~

If the product support policy states “Java 17 is the minimum,” the developer guide must not inadvertently use Java 21 source features in a public SDK module. If release notes state “Java 21 only,” the production runbook should not attempt to roll back to Java 17 without assessing compatibility.

### 3.1. Policy Is Not the Same as Recording Current Status

**Policy:** “SDK v4 supports Java 17 and Java 21 on the listed platforms.”

**Observed result:** “Build 4.2.3 passed suite X on Temurin 21.0.x, Linux amd64, image digest Y.”

Point-in-time test results support the policy but **do not replace** the policy itself. Record the committed scope, evidence, owner, and status clearly.

### 3.2. Do Not Let Documentation Become Conflicting Sources of Truth

A project may contain a README, wiki, release pages, ticket templates, Dockerfiles, and CI YAML. If each place maintains its own version table, values easily drift. Establish **a single authoritative source for the support matrix and JDK targets**, then link to it or check consistency across other documents.

## 4. Target Readers and the Questions They Need Answered

| Audience | Primary Question | Documentation to Provide |
| --- | --- | --- |
| New developer | Which JDK to install, how to build/test? | README, local setup, IDE guide |
| Migrating developer | Which modules keep the old Java minimum? | Compatibility policy, module matrix |
| Reviewer | Does this change break source/binary/runtime contracts? | Architecture decision, API policy, PR checklist |
| QA/test engineer | Which JDKs/OS/CPUs are release-blocking? | Test matrix, test profiles, evidence |
| DevOps/SRE | Which image to deploy and what to observe? | Deployment runbook, dashboards, alerts |
| On-call | What to do when the JVM fails to start or crashes? | Incident runbook, triage matrix |
| Customer support | Is the customer's current version supported? | Support matrix, FAQ, escalation paths |
| SDK customer | Does upgrading the JDK require code changes/recompilation? | Migration guide, release notes, examples |
| Security/compliance | Is the runtime patched and from clear provenance? | Patch policy, SBOM/provenance, exception register |
| Release manager | When is it ready to release and who approves? | Release gates, sign-off, rollback plan |

Content should match **the audience's required depth**: an SDK user does not need an explanation of the entire `StackMapTable`; an on-call team needs safe commands to identify the JDK build and classpath without reading all the source code.

## 5. Inventory Documentation Before Editing

When starting a migration, list all places that specify Java requirements:

- `README.md` and `CONTRIBUTING.md`.
- “Prerequisites”, “Getting Started”, and “Build from source” pages.
- Guides for IntelliJ IDEA, Eclipse, VS Code, and the Java language server.
- Maven/Gradle toolchain instructions, wrapper version, and test scripts.
- Dockerfiles, Helm/manifest/deployment templates, and environment variables.
- CI/CD pipeline documentation, runner images, and artifact publish workflows.
- Runtime prerequisites for SDKs, CLIs, desktop tools, or services.
- API compatibility policy, platform support matrix, and deprecation notices.
- Release notes, migration guides, customer FAQs, and known issues.
- Start/stop runbooks, health checks, TLS/truststore, JVM agents, and diagnostics.
- Incident response/escalation templates and operational dashboards.
- Local debug guides, log collection, heap dumps/JFR/JVM crashes.
- Support macros, help center articles, and products with separate documentation.

### 5.1. Sample Inventory Table

| Document | Audience | What Needs Updating | Owner | Release Gate |
| --- | --- | --- | --- | --- |
| Developer quick start | Developers | JDK/toolchain, IDE import | DevEx | Yes |
| SDK support matrix | Customers/support | Minimum JVM, OS, arch | Product + runtime | Yes |
| CI guide | Build engineers | Runner/toolchains, test profiles | CI owner | Yes |
| Container operations | SRE | Image digest, startup flags, agents | Platform | Yes |
| Java migration guide | Consumers | Breaking changes, actions, examples | Library owner | Yes |
| Incident runbook | On-call | Error signatures, data collection | SRE | Yes |
| Internal FAQ | Support | Triage and escalation | Support engineering | Per policy |

A page that still has links yet lacks an owner risks going stale. When updating documentation, assign who is responsible during future JDK/OS patch updates.

## 6. Choosing a Source of Truth and Synchronization Rules

A simple management structure can look like:

~~~text
docs/
  compatibility/
    support-policy.md
    supported-platforms.md
    module-java-targets.md
  development/
    prerequisites.md
    build-and-test.md
    ide-setup.md
  operations/
    deploy.md
    troubleshoot-java.md
    rollback.md
  releases/
    migration-java21.md
README.md
~~~

Filenames and locations are illustrative. The key point is that **each piece of information has an authoritative location**, while other entrypoints link to it, avoiding copying tables and only updating half of them.

### 6.1. Values That Should Be Managed Centrally

Maintain a single data source or a single policy file for:

- Minimum/runtime Java target.
- Supported JDK distributions and OS/CPU combinations.
- Release/version lifecycle and end-of-support dates.
- Per-module compiler `--release`.
- CI runtime/test matrix.
- Container base image policy.
- Owners and escalation contacts.

It is not necessary to force every repository to use one metadata format, yet these values must be **reconcilable** with build/CI. A Markdown file saying “Java 17” while `build.gradle` sets `options.release = 21` is a contradiction that needs resolving before release.

### 6.2. Docs-as-Code

When feasible, keep documentation in the same pull request as configuration changes:

1. Code and build settings change.
2. Developer guides and runbooks change in the same PR or release change set.
3. Reviewers verify alignment.
4. CI checks links, code snippets, or automatable assertions.
5. Documentation is versioned alongside the release artifact.

Parts that cannot be automated still need an owner/reviewer, such as support contracts, triage language, and rollback policy.

## 7. Write the Support Policy Before Writing “Java 21 supported”

A support policy can be broken down into:

- **Minimum supported runtime:** the lowest JVM on which the artifact is committed to run.
- **Preferred/default runtime:** the recommended JVM for new deployments.
- **Certified/tested combinations:** combinations of JDK vendor/build, OS, and CPU backed by evidence.
- **Build JDK:** the JDK used for the compiler, annotation processors, generators, or tooling.
- **Compatibility exclusions:** JVM vendors, OSes, CPUs, containers, or modes that are unsupported.
- **Deprecation/EOL timeline:** warning dates, end-of-updates dates, and end-of-support dates.
- **Exception handling:** process for requesting exceptions with an owner and expiry.

Illustrative policy example:

~~~text
Product release: Service A 5.x
Build toolchain: JDK 21
Compiled artifact target: Java 17 for shared-client module
Service runtime: Java 21 on approved Linux images
Supported production JDK vendor: approved distributions listed below
Supported architecture: linux/amd64
linux/arm64: candidate until native/agent validation is complete
Java 11 runtime: not supported for this product release
Security update policy: approved JDK patch baseline per update cycle
Support owner: runtime-platform and product engineering
~~~

This is a hypothetical configuration to illustrate format. Do not copy these platform choices into a real product without confirming vendor support, product details, and corresponding tests.

### 7.1. “Built with JDK 21” Does Not Mean “Requires Java 21”

For example, a JDK 21 compiler can compile one module with `--release 17`, generating class files and restricting Java SE APIs to Java 17. Meanwhile, another module also built with JDK 21 might use `--release 21`.

Documentation must clearly state **which module requires which runtime**. A blanket statement “uses JDK 21” is insufficient for multi-module projects or SDKs with external consumers.

### 7.2. Do Not Promise “All JVM Vendors”

Java distributions of the same release generally follow Java SE compatibility, yet differences in packaging, providers, JVM implementations, native libraries, JVM flags, and support lifecycles can still matter.

State:

- Specific vendors/distributions tested and approved.
- OS/architecture matching vendor-provided binaries.
- Supported JVM implementations/flags.
- Additional requirements when using FIPS, JFR, JNI, or native profilers.

A platform that runs during testing does not automatically become a long-term support contract.

## 8. How Should the Platform Matrix Be Published?

Template:

| Java | Distribution | OS/image | Architecture | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| Approved 17.x | Vendor A | Linux glibc image X | amd64 | Supported baseline | Legacy services |
| Approved 21.x | Vendor A | Linux glibc image Y | amd64 | Supported target | Full regression |
| Approved 21.x | Vendor B | Linux glibc image Y | amd64 | Candidate | Awaiting full validation |
| Approved 21.x | Vendor A | Linux glibc image Y | arm64 | Experimental | JNI/agent checks pending |
| Approved 21.x | Vendor A | Linux musl image Z | amd64 | Unsupported | No approved native binary |

Vendors A/B and images X/Y/Z are placeholders only. In real docs, replace them with **evidence-backed combinations**, verification dates, and links to test evidence.

### 8.1. Separate Supported, Validated, Experimental, and Unsupported

- **Supported:** within product policy, carrying support obligations.
- **Validated:** tested with a specific artifact/JDK build.
- **Experimental:** exploratory data exists without a commitment.
- **Unsupported:** out of scope or lacking suitable binaries/operational capability.

A `NOT_RUN` row in CI for a supported combination **is not a PASS**. If a suitable runner/agent is missing, report the gap explicitly.

### 8.2. The Runtime Image Is Also Part of the Environment

With containers, a label like `eclipse-temurin:21` or a similar tag can point to different patches over time. To reproduce a release, store the **image digest**, platform, and full JDK build. For multi-architecture images, record the corresponding actual platform/child image.

## 9. Documenting Minimum Java Levels and Upgrade Paths for Customers

Customers may use:

- A server application deployed by their own organization.
- An SDK/JAR embedded into their application running another JDK.
- A CLI or desktop tool distributed with a bundled JRE/JDK.
- A container image provided by the vendor.

Each type needs different wording.

**Server-managed deployment:** “Starting in 5.0, vendor-published containers run Java 21; customers calling the API over HTTP do not need to install Java themselves unless using a separate Java client component.”

**SDK/JAR:** “SDK 4.x requires a Java 17 or newer JVM. Projects built with a newer JDK must still use the appropriate release target if they intend to run on Java 17.”

**CLI tool:** “Version 3.x requires JDK 21 installed in PATH or distributed with the bundled runtime; running on Java 11 is not supported.”

Do not write a generic “Upgraded to Java 21” without stating **who has to do what**.

### 9.1. Distinguish Source, Binary, and Behavioral Compatibility

Release notes should answer:

| Compatibility Type | Question |
| --- | --- |
| Source | Do consumers rebuilding have to modify code? |
| Binary | Do pre-compiled JARs still link against the new API? |
| Runtime | Do class-file versions and Java SE APIs run on the committed JDK? |
| Data/protocol | Can JSON, XML, protobuf, serialization, and databases be read across versions? |
| Operational | Do startup flags, agents, TLS, or logging/monitoring change? |

Do not use “backward compatible” without clarifying compatibility along which dimension.

## 10. Updating README: What Should the Prerequisites Section Say?

An actionable snippet:

~~~markdown
## Prerequisites

- JDK: 21, approved distribution and patch level
- Build tool: repository Maven/Gradle Wrapper
- Container runtime: required for integration tests
- OS: developer platforms listed in supported-platforms.md

The service runs on Java 21. The shared SDK module is
compiled with --release 17 for supported Java 17 consumers.

Check your environment:

    java -version
    javac -version
    ./gradlew --version

Do not rely on the IDE Project SDK as proof of the build
or test JVM.
~~~

In real docs, replace “approved distribution and patch level” with a single version source or verifiable policy link. Choose `./gradlew` **or** `./mvnw` per repository; do not show both if the project only has one.

### 10.1. README Should Be a Short Entrypoint

README should contain:

1. Primary Java requirement.
2. Environment check commands.
3. Basic build/test commands.
4. Toolchain selection instructions.
5. Links to troubleshooting/migration/support matrix.

Avoid cramming every deep runbook into README. Readers should have a clear path from “can install and build” to “operate and troubleshoot”.

## 11. Developer Quick Start: From a Clean Machine to Passing Tests

A setup guide should follow a reproducible sequence:

1. Install the **approved JDK distribution and release**, matching OS/CPU.
2. Confirm command-line `java` and `javac` point to the right installation.
3. Set `JAVA_HOME` if the wrapper/tooling requires it, without hardcoding absolute paths in the repository.
4. Run the Maven/Gradle Wrapper pinned in the project.
5. Provision local dependencies: database/test containers, brokers, certificates per policy.
6. Configure environment variables without placing real secrets in source.
7. Import the project into the IDE and check module language levels.
8. Run compile and unit tests.
9. Run an integration smoke test checking a core endpoint/workflow.
10. Document how to reset local state and inspect error logs if tests fail.

Each step must specify **commands, prerequisites, and success criteria**, not just “install Java and run app”.

### 11.1. Detecting PATH and JAVA_HOME Mismatches

Example on POSIX shells:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
command -v java
~~~

On PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
~~~

If `JAVA_HOME` points to JDK 21 while the `java` command found in PATH is JDK 17, the guide must instruct how to unify the environment rather than saying “just install JDK 21”.

### 11.2. Do Not Rely on a Single OS-Specific Command Across All Machines

Do not treat `readlink` or `where` as the sole way across all OSes. Provide options by shell/OS and explain the expected output.

## 12. Maven: Document Exact JDK, Compiler Release, and Toolchains

Example of a module wanting to use the JDK 21 compiler while publishing a Java 17-compatible artifact:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

When using Maven Compiler Plugin, select an approved version supporting the Maven/JDK combination. If the project uses Maven Toolchains, clearly document:

- Which JDK runs the `mvnw`/Maven process itself.
- Which JDK is selected by the compiler plugin/toolchains.
- Which JVM the Surefire/Failsafe test runner executes.
- Each module's `--release`.
- Whether annotation processors and code generators require a separate JDK.

Verification commands:

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw verify
~~~

`./mvnw` is only an example for repositories with the Maven Wrapper; on Windows, `mvnw.cmd` may be used per project instructions. Do not write a single Unix command as if it runs on every Windows PowerShell installation.

### 12.1. A Common Support Error

~~~text
error: release version 21 not supported
~~~

This message usually indicates the active compiler JDK **does not support the requested target release**. Simply raising Project SDK in the IDE may not change the JDK Maven/the compiler actually uses. The support guide should ask for `mvn -version`/toolchain details rather than just an IDE screenshot.

## 13. Gradle: Distinguish Daemon JVM, Toolchain, and Target

Groovy DSL example:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

This configuration illustrates a Java 21 compiler toolchain targeting Java 17. However:

- The Gradle **daemon JVM** can differ from the compiler toolchain.
- The Gradle Wrapper version must be supported on the JVM running the daemon.
- `Test` tasks can use a separately specified Java launcher.
- Modules requiring a Java 21 runtime can have their own `options.release = 21`.
- IDE Gradle model import can diverge if the IDE's JVM settings are out of sync.

Common commands:

~~~bash
./gradlew --version
./gradlew :app:compileJava
./gradlew :app:test
~~~

Do not instruct running a command for module `app` if the actual repository uses a different module name; that is a placeholder to replace.

### 13.1. Always Document the Wrapper Version

Run `./gradlew`/`./mvnw` from the repository rather than using arbitrary developer global Gradle/Maven installs, unless the project has a different policy. The wrapper aids reproducibility yet still requires a compatible Java runtime/build environment.

## 14. IDE Setup: One Contract, Multiple Editors

The developer guide must distinguish:

| Component | Meaning |
| --- | --- |
| IDE runtime | JVM running the IDE/language server itself |
| Project SDK | JDK the IDE associates with the project |
| Module language level | Java syntax the IDE considers valid for the module |
| Gradle JVM/Maven JDK | JVM for build integration/runner |
| Compiler toolchain | JDK that actually runs `javac` or the corresponding compiler |
| Target release | Java SE API/bytecode that the artifact is released for |
| Test JVM | JVM running unit/integration tests |

### 14.1. IntelliJ IDEA

Instructions should ask to check Project SDK, Module language level, Gradle JVM or Maven runner/importer JDK, annotation processing, and required plugins. Menu names may change across IDE releases, so state **the concepts to select** and update screenshots when UI changes, instead of treating old screenshots as truth.

### 14.2. Eclipse/ECJ

Check Installed JRE/JDK, compiler compliance level, build path, Maven m2e or Gradle Buildship, and plugins relying on JDT AST. ECJ and `javac` can have different diagnostics; official builds still need to use the compiler/toolchain defined in the pipeline.

### 14.3. VS Code Java

Check the Java extension/language server, Java runtimes, Gradle/Maven import, and project language level. The JVM running the language server is not necessarily the application's Java compiler/runtime.

### 14.4. Update Examples Immediately When Changing Source Language

If a module only supports Java 17 source, documentation should not use pattern switch or record patterns that only Java 21 compiles under the official language level. If an example uses a newer Java feature, explicitly note the feature release of the example.

## 15. Environment Configuration: Do Not Copy Secrets or Personal Machine Paths

A good guide distinguishes:

- **Required public settings:** profile, local endpoints, feature flags.
- **Secrets:** credentials, tokens, private keys; use a secret manager or approved mechanism.
- **Developer overrides:** hostname/port, test fixture paths.
- **Production-owned settings:** truststore, JVM flags, agent config, container resources.

Example:

~~~text
APP_PROFILE=local
APP_HTTP_PORT=8080
APP_DB_URL=jdbc:postgresql://localhost:5432/app
JAVA_TOOL_OPTIONS=<approved-local-options-if-required>
~~~

Values are illustrative only. Do not put real passwords in README or log `JAVA_TOOL_OPTIONS` if it contains secrets. If an endpoint is provided by a mock/test container, clearly state it is not a production URL.

### 15.1. Cross-Platform Paths

Do not commit `C:\Users\Alice\jdk-21` or `/Users/bob/.sdkman/...` into shared configs. Use toolchain resolvers, environment variables, and local-only settings when appropriate.

### 15.2. Watch Out for `JAVA_TOOL_OPTIONS` and `JDK_JAVA_OPTIONS`

These variables can inject options into Java processes that developers do not see in build files. They affect `-javaagent`, module opens, memory, logging, and security. Debugging guides should require inspecting actual JVM arguments and redacting sensitive data.

## 16. Updating Local Integration-Test Prerequisites

When upgrading the JDK, developers may need auxiliary services:

- Database containers and schema migrations.
- Kafka/RabbitMQ or corresponding message brokers.
- TLS certificates for mTLS tests.
- Testcontainers/Docker runtime with appropriate permissions.
- Native libraries for JDBC compression, cryptography, image processing, or JNI.
- Multi-version test data fixtures.
- Mock HTTP servers, local cloud emulators.
- Supported coverage/mocking Java agents.

### 16.1. “Setup Succeeded” Criteria

Do not write only:

~~~bash
./gradlew test
~~~

State:

~~~text
Expected:
- Gradle/Maven process starts with approved JDK configuration.
- Unit tests complete successfully.
- Integration test service containers start.
- No tests silently skipped due to unavailable Docker.
- Test reports are available at documented locations.
- Java agent/coverage tools remain functional.
~~~

If a suite needs credentials or services that cannot be provisioned locally, provide a clear local profile and a full CI profile; do not equate “local tests pass” with “all release gates pass”.

## 17. Native Libraries and Agent Dependencies in the Developer Guide

Java source is portable, yet applications with JNI/JNA or native agents may not run on every OS/architecture:

- `.dll` on Windows.
- `.so` on Linux.
- `.dylib` on macOS.
- `amd64/x86_64` or `arm64/aarch64` architectures.
- Linux `glibc` differs from `musl` in many cases.
- Native dependencies require matching version/ABI.

Local setup documentation must state:

1. Which native artifacts are permitted.
2. Which OS/architectures are supported.
3. How to provision binaries (do not download arbitrary DLLs).
4. How to verify library presence and architecture.
5. How to test functionality that actually exercises the native path.
6. When to report lack of support instead of trying to patch with untrusted libraries.

### 17.1. A Sample Error

~~~text
java.lang.UnsatisfiedLinkError: no nativecodec in java.library.path
~~~

The support guide should distinguish missing native library, library present with right name yet missing dependency, wrong CPU ABI, different libc, and JNI symbol mismatch. Do not just suggest “add the folder to java.library.path” for every case.

### 17.2. APM/Coverage/Mockito

When changing JDKs, Java agents and bytecode tools may need upgrading. A warning about dynamic agent loading or an `Unsupported class file major version` error cannot be explained simply by changing `JAVA_HOME`. Document the agent/framework version, startup/dynamic attach timing, and target JDK.

## 18. CI/CD Documentation: Describing Actually Tested Environments

CI documentation needs to record:

- CI provider/runner OS and architecture.
- JDK distribution, feature release, and full update/build.
- JDKs running the build tool, compiler toolchain, and test JVM.
- Module `--release` settings.
- Test profiles and release-blocking matrix rows.
- Container image digests, Docker build platforms.
- Native/agent dependencies.
- Artifacts retained after tests: reports, logs, SBOMs, checksums.
- Gating policy when failed/skipped/not run.

### 18.1. Do Not Treat Runner Labels as Full Proof

A job labeled `ubuntu-latest` can change OS images when the CI provider updates. A job with variable `arch: arm64` does not prove it runs on real ARM64. For release-blocking validations, save the runtime fingerprint and actual OS/CPU.

### 18.2. Example CI Matrix at the Data Level

~~~yaml
platforms:
  - id: linux-amd64-jdk17
    jdk_release: "17"
    distribution: approved-vendor-a
    os: linux
    architecture: amd64
    profile: full
    purpose: baseline

  - id: linux-amd64-jdk21
    jdk_release: "21"
    distribution: approved-vendor-a
    os: linux
    architecture: amd64
    profile: full
    purpose: target

  - id: linux-arm64-jdk21
    jdk_release: "21"
    distribution: approved-vendor-a
    os: linux
    architecture: arm64
    profile: native-integration
    purpose: candidate
~~~

This is **illustrative data**, not a ready-made configuration for every CI provider. Real setups need confirmation of runner availability, JDK distribution support, and policy.

## 19. Release Gates: Documentation Needs Completion Criteria Too

A migration should have criteria:

| Group | Release Gate |
| --- | --- |
| Source/build | Compile with approved toolchain and appropriate target |
| Regression | Tests pass on mandatory JVMs/OS/architectures |
| API | Consumer binary/source compatibility meets contract |
| Native/agents | Integration and instrumentation work |
| Security | JDK patches, TLS/crypto, and SBOM/provenance verified |
| Operations | Image/config/health/observability confirmed |
| Documentation | README, support matrix, migration guide, and runbooks updated |
| Support readiness | FAQ, triage, known issues, and escalation ready |
| Rollback | Tested or has approved constraints |

Do not merely mark “docs done” with an unverifiable checkbox. At minimum, include document links, owner/reviewer, and release commit/version.

### 19.1. What If Documentation Is Incomplete?

An application might run properly yet still be unsafe to operate because rollback instructions are missing or support does not know the new minimum JDK. Per policy, this can be a **release blocker**, not a “will add later” task.

## 20. What Must Changelogs and Release Notes Answer?

Release notes should be concise yet complete:

1. **Which versions are affected?**
2. **What is the new minimum Java version?**
3. **What must customers do before upgrading?**
4. **Are there breaking source/binary/runtime changes?**
5. **Are there changes to container images, OS/CPU support, TLS/JVM flags, or agents?**
6. **What remains compatible?**
7. **Are there known issues or unsupported configurations?**
8. **How to verify after upgrading and how to roll back?**
9. **Links to the migration guide, support matrix, and policy effective date?**

### 20.1. Sample Release Notes

~~~markdown
### Java runtime and platform compatibility

- Runtime baseline: Java 21 for the server component.
- Shared client SDK: Java 17 remains the minimum when
  using the release artifact built with --release 17.
- Deployment image: use the published, approved image
  digest for this release.
- Updated: JDK support matrix, developer setup guide
  and operations runbook.
- Action required: review custom JVM flags, agents,
  JNI/JNA libraries, truststore and container settings.
- Verification: run the documented smoke and
  integration checks after deployment.
- Known limitations: see supported-platforms.md.
- Rollback: follow the version-specific runbook;
  database or message schema changes may affect rollback.
~~~

This is a sample rather than a universal policy. If the real minimum Java version changed from 17 to 21 for **all artifacts**, do not keep the SDK 17 sentence.

### 20.2. Avoid Ambiguous Wording

Do not just write:

> “Updated Java compatibility.”

Replace with: “The `server` module requires a Java 21 JVM starting in version 5.0; the `client-sdk` module continues to support Java 17 and 21 per the published matrix. Java 11 releases are no longer within support scope as of the stated date and version.”

## 21. Migration Guide: For Those Upgrading from an Older Version

A migration guide does not merely list changes; it is a **verifiable sequence of operations**:

~~~text
Before upgrade
  -> Confirm currently deployed release/runtime
  -> Check target support matrix
  -> Inventory JVM flags, agents, native libraries
  -> Back up data/config when required
  -> Validate deployment and rollback prerequisites

Prepare
  -> Update JDK/toolchain/runtime image
  -> Align dependencies and build target
  -> Validate security certificates/truststores
  -> Run regression and cross-version tests

Deploy
  -> Canary with approved artifact/image
  -> Health and observability checks
  -> Gradually increase traffic

After upgrade
  -> Verify core business workflows
  -> Verify logs/traces/metrics/alerts
  -> Record exact JDK/image/artifact versions
~~~

### 21.1. Every Step Needs Success Criteria

For example, “Update JDK” should include:

~~~text
Input: approved runtime image and target release
Action: deploy image to staging
Success:
  - java.version and image digest match the release plan
  - application starts and health endpoints pass
  - mandatory workflows pass
Failure: stop rollout and follow incident runbook
~~~

### 21.2. State Unsupported Upgrade Paths

If a framework or driver requires an intermediate migration, documentation must say so clearly. For example, Java 8 customers cannot upgrade directly to a new SDK version if the minimum Java is now 17 without upgrading their runtime or choosing an appropriate artifact first.

## 22. “Before and After” Comparison Template

| Item | Before Migration | After Migration | Owner |
| --- | --- | --- | --- |
| Production runtime | Java 17 image | Java 21 image | Platform |
| Java build JDK | 17 | 21 | Build/DevEx |
| SDK compile target | 17 | 17 (kept unchanged) | SDK owner |
| Framework/driver | Old version | JDK 21-compatible version | Service owner |
| APM agent | Old version | Vendor-supported version | Observability |
| JVM module flags | Old workarounds | Reviewed/removed excess flags | Platform/security |
| CI matrix | JDK 17 | JDK 17 + 21 per policy | QA/CI |
| Developer setup | Default JDK 17 | JDK 21, SDK section separate | DevEx |
| Runbook | Old health/startup | Added runtime validation/rollback | SRE |
| Support FAQ | “Java 17” | Accurately lists modules and timelines | Support |

Values are illustrative only. It is important to avoid changing every JDK reference across documentation all at once when certain artifacts must still keep a lower minimum Java version.

## 23. Operations Runbooks Start with Preflight

A runbook must work when on-call does not have the author nearby. The preflight section must answer:

- Which exact release artifact/image digest will be deployed?
- What is the JDK vendor/build inside the image?
- Do the container OS/architecture match the node pool?
- Are agent/JNI/native libraries at compatible versions?
- Have truststore/certificates and secrets been provisioned?
- Has schema/database/message compatibility been verified?
- Are feature flags and config migrations backward compatible?
- Are dashboards/alerts and sample traffic checks ready?
- If rolling back, can the old artifact read the new data?

### 23.1. A Preflight Template

~~~text
[ ] Approved release identifier and artifact checksum
[ ] Approved JDK build and immutable image digest
[ ] Correct OS / CPU architecture / libc
[ ] JVM flags and agents reviewed for target JDK
[ ] Required environment/secret references resolved
[ ] Data migration and rollback constraints reviewed
[ ] Mandatory CI regression gates passed
[ ] Monitoring dashboards and alerts functional
[ ] On-call, release manager and rollback owner assigned
[ ] Deployment window/communications approved
~~~

Each checkbox should point to evidence. “Approved JDK build” is not enough without recording a real build/release identifier.

## 24. Deployment Runbook Must Include a Runtime Verification Step

A diagram:

~~~text
Validate release artifact
           |
           v
Deploy to staging / canary
           |
           v
Verify JDK build, image, JVM arguments
           |
           v
Health + business smoke checks
           |
           v
Compare errors, latency, memory, GC, traces
           |
       Gate decision
        /      \
       v        v
  Promote     Stop / rollback / investigate
       |
       v
  Post-release evidence and sign-off
~~~

### 24.1. Example Startup Command

~~~bash
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log \
     -javaagent:/opt/agents/approved-agent.jar \
     -jar service.jar
~~~

This is a syntax example for a HotSpot/Linux-like environment, not a recommended command for every service. A real runbook needs the **exact** startup flags, agent file, and log directory write permissions for the deployment. Do not add flags/agents ad hoc to production without configuration/approval.

### 24.2. Where Do JVM Options Live?

In Kubernetes, startup options may appear in container command/args, an entrypoint script, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, or platform agent injection. Documentation must identify the authoritative location and how to inspect the config of the **actually running process**, since a chart change may not match commands run in a local shell.

## 25. Canary and Risk-Based Rollout

Upgrading the JDK can affect performance, GC, native libraries, TLS, reflection, and instrumentation. A canary should have:

1. A group of instances/replicas with **identified JDK+image+agent versions**.
2. Comparable traffic or synthetic transactions.
3. Comparison against a still-active baseline.
4. Stop/go criteria based on functional errors and SLOs.
5. An owner authorized to decide on rollback.
6. Approved timing/scope for traffic ramp-up.

### 25.1. Metrics to Watch

| Metric | Reason |
| --- | --- |
| Startup/ready time | JDK/agent/framework initialization regressions |
| HTTP 5xx/error rate | Business/communication failures |
| p95/p99 latency | JIT, GC, lock contention, or native overhead |
| CPU/memory/GC | Heap, metaspace, direct/native usage, allocation |
| Thread pool/queue depth | Concurrency/backpressure |
| TLS handshake failures | Security provider/truststore |
| DB pool failures | Driver and network compatibility |
| Traces/spans/metrics | APM auto-instrumentation still works |
| JVM crashes/OOMKills | Native/agent/GC/container issues |
| Data correctness signals | Schema/serializer/cross-version regressions |

Metrics are selected by workload. Do not define arbitrary thresholds for every product; use the SLO/error budget and baseline agreed upon by the team.

## 26. Rollback Must Be Described as a Conditional Operation

Rolling back a container image only restores the **runtime artifact**. It does not automatically reverse:

- Database schema migrations.
- Serialized data already written by the new producer.
- New message payloads in queues/topics.
- Encryption/signature format changes.
- External side effects or updated state.
- Compatibility across concurrently running client/server instances.
- Feature flags/configs changed outside the image.

A rollback runbook must state **permitted conditions**, not just a “deploy previous image” command.

### 26.1. Rollback Decision Template

~~~text
IF:
  the previous application release can read current data
  AND no incompatible schema/protocol changes have been applied
  AND the previous runtime image remains available and approved
THEN:
  rollback application deployment according to release procedure
  verify health, business behavior, tracing and error rates
ELSE:
  stop automatic rollback
  escalate to incident commander / data owner
  use documented roll-forward or data recovery procedure
~~~

This is a decision flow, not an automated script. If data has already changed, a “quick” rollback can cause data loss or trigger new errors.

### 26.2. Test Rollback Before It Is Needed

In staging with simulated/fixture data:

1. Deploy the old version and create valid data.
2. Upgrade to the new version and run scenarios that modify state.
3. Test cross-version read/write paths if policy requires.
4. Test rollback or roll-forward per scenario.
5. Record limits, recovery time, and manual steps requiring approval.

## 27. Incident Runbook: Quick Triage for JDK Migration Failures

| Symptom | Layer to Check | Evidence to Request |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Runtime lower than class-file target | `java -version`, `javap -verbose`, artifact |
| `NoSuchMethodError`/`NoSuchFieldError` | JAR/ABI mismatch | Resolved dependencies, loaded class |
| `NoClassDefFoundError` | Missing class or failed initialization | First error, classpath, `Caused by` |
| `InaccessibleObjectException` | Reflection/JPMS access | Package/module, library version, flags |
| `VerifyError` | Malformed bytecode/transformer | Class bytes, bci, agent/tool versions |
| ASM “major version unsupported” | Bytecode parser not supported yet | ASM/Byte Buddy/agent version |
| `UnsatisfiedLinkError` | JNI/native path/ABI | OS/arch/libc, native library dependencies |
| TLS handshake failure | Truststore/security policy | Provider/cert/endpoint configuration |
| JDK crash, `hs_err_pid*.log` | JVM/native/agent fatal error | Problematic frame, native libraries |
| Dynamic agent loading warning | JEP 451/policy when applicable | JDK release, agent mode, vendor docs |
| Container OOMKill | Resource limits/heap/direct/native memory | JVM args, cgroup limits, workload |

This is a **routing table**, not a substitute for full stack traces. Support/on-call must find the first error and identify the actual runtime/artifact before suggesting a fix.

## 28. Collecting Information When the JVM Fails to Start

Part of a runbook might request:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

With an appropriate JDK and permissions, you can use:

~~~bash
jcmd <pid> help
jcmd <pid> VM.command_line
~~~

`<pid>` must be replaced with the process ID of a JVM **authorized for administration**. Do not attach/debug processes belonging to other parties. The `jcmd` command is also not guaranteed to be available in every runtime image, JVM implementation, or when the attach mechanism is disabled.

### 28.1. Essential Evidence

~~~text
Application release / build SHA:
JDK distribution, java.version, java.runtime.version:
JVM implementation:
OS/image/architecture/libc:
Artifact and image checksum:
JVM startup flags and JAVA_TOOL_OPTIONS (redacted):
Agents and native libraries:
First exception or fatal error:
Container events/restart reason:
Last known good environment:
Reproduction steps:
~~~

Do not automatically send unfiltered `-XshowSettings` output, environment variables, core dumps, or heap dumps to public support channels; they may contain sensitive information.

## 29. JVM Crash and Native Failure Guide

If the JVM crashes, `hs_err_pid<id>.log` may appear on HotSpot, or other crash logs depending on the vendor. The runbook should state:

- Expected directory for storing fatal error logs.
- Write permissions and retention mechanism when a container restarts.
- How to identify the problematic frame and native module.
- When core/minidump/JFR is needed.
- Data safety rules for heap/core dumps.
- Escalation channels to the JVM vendor or native library owner.

### 29.1. Do Not Confuse Native Loading Errors with JVM Crashes

`UnsatisfiedLinkError` may simply be a Java `Error` when the loader cannot find a library or symbol. `SIGSEGV`/access violation in native code can terminate the process and requires fatal error logs/core dumps.

Do not advise users to use `try/catch(Throwable)` to “catch” all native crashes; that is not a safe mechanism for fatal signals.

### 29.2. Agents Are Runtime Dependencies Too

A `-javaagent`, coverage tool, or profiler can bring its own native/bytecode libraries. When upgrading the JDK, record the agent version, startup/dynamic loading mode, module access, permissions, and vendor compatibility. Do not evaluate solely by saying “the application JAR didn't change”.

## 30. Runbook for TLS, Truststore, and Security

Security defaults/algorithms/certificates can change between JDK releases, updates, distributions, and images.

Documentation must answer:

- Does the truststore belong to the JDK image or is it provided by the application?
- By what process are CA certificates updated?
- Are keystores, mTLS, PKCS#11/HSM, or FIPS used?
- Which security providers/algorithms are mandatory?
- Is there proxy/certificate interception in the test environment?
- When a TLS handshake fails, how is evidence collected without exposing private keys?
- Who has authority to change policies and who approves?

### 30.1. Do Not Disable TLS Verification to Get Past Migration

If a certificate is untrusted or an algorithm is disallowed, the fix must come from the proper policy/truststore/provider. Do not advise “trust all certificates”, disabling hostname verification, or blindly expanding cipher suites.

### 30.2. Debug Commands Need Safety Warnings

Flags that increase TLS logging can generate sensitive/high-volume data. In the runbook, clearly state:

~~~text
Use only in an approved test or incident context.
Enable for a bounded diagnostic window.
Redact endpoint names, tokens and sensitive certificate details.
Disable verbose logging after collecting evidence.
~~~

Do not leave verbose debug logging enabled permanently just to make it “easy to investigate”.

## 31. Operational Monitoring Must Change When JVM/Agents Change

Monitoring dashboards can rely on:

- Metric names and labels.
- GC metrics/collector names.
- JVM memory pool names.
- APM resource attributes, span names.
- Log patterns for startup/crash/agent warnings.
- Heap/direct/native memory metrics.
- Alert thresholds from the pre-migration baseline.

When changing collectors, JDK distribution, or the APM agent, a dashboard may go blank not because the application “uses no memory”, but because metric names/export modes changed.

### 31.1. Observability Checklist

- [ ] JVM/process metrics still appear.
- [ ] GC, heap, non-heap, and direct memory are tracked appropriately.
- [ ] HTTP/JDBC/messaging spans are complete and not duplicated.
- [ ] Error rates and exception logging remain accurate.
- [ ] Dashboards are not broken due to metric name/label changes.
- [ ] Alerts are actually tested with synthetic conditions when feasible.
- [ ] Agent overhead stays within budget.
- [ ] Logs and traces continue to comply with privacy policy.

An “HTTP 200” deployment is insufficient proof of operational readiness if alerting paths have disappeared.

## 32. Support FAQ Needs to Be Practical

Support teams need scenario-based answers without having to learn all build internals.

**Q: Which Java versions does the product currently support?**  
A: Refer strictly to the support matrix of the exact product release and component. State the minimum JVM, approved distributions/platforms, and effective date; avoid using one generic number for server, SDK, and CLI if they differ.

**Q: I already installed JDK 21, so why does it still report release version not supported?**  
A: Check the JVM of the Maven/Gradle daemon/compiler toolchain using the documented commands. The IDE Project SDK does not prove the build tool is using the right JDK.

**Q: Why does the application run on Windows yet fail on Linux ARM64?**  
A: Collect OS, architecture, image, JDK build, and native library information. If using JNI/JNA, binaries matching the platform/ABI are required.

**Q: Why don't tests run on Java 21 even though the app starts up?**  
A: The test agent/coverage/bytecode parser may not support the new class-file/JDK version yet. Check the error subtype and test tooling versions.

**Q: Can we add `--add-opens` to fix every error?**  
A: No. This flag only adjusts certain module access permissions; it does not resolve missing methods, malformed bytecode, or native ABI mismatches.

**Q: Can we roll back by changing the Java version in the container?**  
A: Check the release-specific rollback policy, data/protocol/schema compatibility, and approved images. Do not change JVM versions in production outside established procedures.

## 33. Support Triage Workflow

~~~text
Customer / developer reports a Java-related issue
                     |
                     v
Identify product component + release + deployment type
                     |
                     v
Check support matrix for exact JDK/vendor/OS/arch
                     |
            +--------+--------+
            |                 |
      Supported           Not supported
            |                 |
            v                 v
Collect runtime          Explain limitation,
fingerprint and logs     supported alternatives
            |
            v
Classify first failure
            |
      +-----+------+------+
      |            |      |
   Build/API    JVM/tool  Native/OS
      |            |      |
      v            v      v
Engineering    Runtime   Platform/native
owner          tooling   owner
      \            |      /
       +-----------+-----+
                   |
                   v
      Reproduce, resolve, update FAQ/runbook
~~~

### 33.1. Do Not Request Excessive Data

Support must request enough information to triage while avoiding collecting secrets, full environments, or heap dumps when unnecessary. Use organization-approved secure channels for sensitive diagnostic artifacts.

### 33.2. Distinguish Unsupported Environments from Real Bugs

If a customer is on an uncommitted platform, support should explain policy and supported alternatives. Still, a severe bug with clear evidence can be valuable input for the product roadmap. Do not use the “unsupported” label to dismiss every technical report.

## 34. Incident Template Making Escalations Actionable

~~~markdown
## Impact
- Affected service/customer/feature:
- First observed:
- Severity and business impact:

## Runtime environment
- Product release and artifact hash:
- JDK distribution/full version/build:
- JVM implementation:
- OS/base image/CPU architecture:
- Java arguments and agents (redacted):

## Symptoms
- First exception or fatal error:
- Affected class/method/library:
- Logs and correlation IDs:
- Reproduction:

## Compatibility context
- Supported matrix row:
- Last known good version:
- Differences between old/new environments:

## Mitigation and recovery
- Current workaround and risks:
- Rollback preconditions checked:
- Owner/escalation:
- Next action:
~~~

This template reduces back-and-forth questions when handing tickets between support, JVM/runtime, build, and SRE. Avoid writing “Java 21 bug” before determining the actual runtime and root cause.

## 35. Assigning Responsibilities with a Simple RACI

| Activity | Responsible | Accountable | Consulted |
| --- | --- | --- | --- |
| Define Java support policy | Product/runtime team | Product owner | Support, security |
| Configure JDK/compiler targets | Build/DevEx | Engineering lead | Library owners |
| Test compatibility matrix | QA/CI | Release manager | Platform, developers |
| Update local setup/IDE | DevEx | Engineering lead | Developer representatives |
| Update release notes/FAQ | Docs/support engineering | Product owner | Service/SDK owners |
| Write deployment/rollback runbook | SRE/platform | Operations lead | DB/security owners |
| Cross-check JDK security patches | Platform/security | Security owner | Product teams |
| Handle post-rollout incidents | On-call + owning team | Incident commander | Runtime/JDK vendor |

This RACI is only an example; organizations may use different roles. The goal is to prevent “everyone shares responsibility” from turning into nobody fixing wrong pages.

## 36. Communicating Changes to Each User Group

A communication plan can include:

| When | Audience | Content |
| --- | --- | --- |
| Before migration | Developers/QA | Toolchains, branch policy, CI matrix |
| Before release | Support/SRE/security | Minimum JDK, runbook, known issues |
| Release announcement | Customers/SDK consumers | Action required, compatibility, timeline |
| During rollout | On-call/release manager | Canary status, thresholds, rollback gate |
| After rollout | Engineering/support | Verified platforms, issues, follow-ups |
| Each JDK patch update | Platform/service owners | New image/build, regression evidence |

An announcement should only direct readers to **one correct version of the documentation**. Linking to an outdated wiki can be more dangerous than having no link.

### 36.1. Good and Bad Wording

Bad: “All teams switch to Java 21 immediately.”

Better: “Starting with release X, server runtime uses Java 21 in approved images; client SDK keeps `--release 17`; developer builds use toolchain 21. Teams verify environments per `development/prerequisites` and release gates in `compatibility/support-policy`.”

Bad: “The agent still runs.”

Better: “Agent version A has been validated on target JDK build and image B with HTTP/JDBC traces, startup smoke, and performance suite; dynamic attach is supported only per separate policy.”

## 37. Known Issues and Workaround Register

When a migration has unresolved issues, maintain a table:

| Issue | Environment | Impact | Workaround | Owner | Review Due |
| --- | --- | --- | --- | --- | --- |
| Tool A fails to parse Java 21 class files | Test JDK 21 | Coverage gate blocked | Upgrade tool to supported version | Build | Before release |
| Native library lacks ARM64 | Linux ARM64 | Feature X does not run | Temporarily withhold ARM64 support claim | Platform | Per plan |
| Reflection library needs module opens | JDK 17/21 | Init error | Package-scoped workaround; upgrade scheduled | Library owner | With expiry |
| Dashboard missing metrics after agent upgrade | JDK 21 image | Alerting gap | Update mapping/agent config | Observability | Before production |

All rows above are hypothetical scenarios. In real docs, record the issue ID, impacted versions, status, owner, update date, and fix link.

### 37.1. Workarounds Need a Removal Policy

An `--add-opens` flag, disabled checks, or manual native binary copy may have been needed during migration. Do not let them become permanent “best practices”. Workarounds need:

- Description of the cause.
- Version/JDK scope.
- Security/operational risks.
- Applicability conditions.
- Approver.
- Long-term replacement plan.
- Review/removal milestone.

## 38. Deprecation and End-of-Support Announcements

Dropping support for an older Java version is usually a **breaking support change**. When removing Java 11 from the matrix, documentation must state:

- First product release no longer supporting it.
- Announcement date and effective date.
- Whether older releases still receive security updates.
- Primary technical cause/conditions (if any).
- Recommended target JDK and approved platforms.
- Steps to upgrade applications/SDKs/CI.
- Guidance for customers unable to upgrade in time.
- Support/escalation channels.

### 38.1. Do Not Promise Support Beyond the JDK Vendor Contract

JDK distributions have different lifecycles and commercial support terms. A Java release designated LTS does not mean every vendor continues providing patches indefinitely. Product policies should be cross-checked against the vendor support actually used and the review date.

## 39. Versioning Documentation Alongside Artifacts

Customers on release 4.x may need Java 17 docs, while release 5.x requires Java 21. If the “latest” page is updated by deleting 4.x instructions, support will struggle to troubleshoot issues on older releases still in support.

You should:

1. Maintain documentation versions corresponding to product releases or compatibility branches.
2. Attach the version and **last validated date**.
3. Link from release notes to the exact version.
4. Retain legacy documentation that is still in support.
5. Clearly mark EOL/archived documents.
6. Prevent search results from leading to old runbooks without warning.

### 39.1. Avoid Mutable Commands in Release-Specific Documentation

For example, “use Docker tag `latest`” cannot guarantee reproducing an incident months later. Release runbooks should specify the approved image digest or artifact identifier. Guide pages can describe how to locate newer versions, whereas an incident record must store the actual value.

## 40. Updating Docs According to the Release Lifecycle

A cycle:

~~~text
Feature / migration proposal
           |
           v
Support-policy change drafted
           |
           v
Build + test implementation
           |
           v
Docs and runbook PR with evidence
           |
           v
Review by owners and support
           |
           v
Release gates + freeze approval
           |
           v
Publish versioned docs and release
           |
           v
Canary, operational feedback, corrections
           |
           v
Update docs at next JDK/OS/agent patch cycle
~~~

### 40.1. “Last verified” Matters More Than “Last edited”

A runbook may have just had a typo fixed yet never been executed with the new JDK. Record separately:

~~~text
Document last updated: ...
Procedure last executed/validated: ...
Validated artifact/image/JDK: ...
Owner: ...
Next review trigger: ...
~~~

If a procedure has not been rehearsed in an authorized environment, write “not yet validated”; do not call it production-ready.

## 41. Verifying Documentation Like Technical Testing

Checks that can be automated:

- Markdown lint and link checking.
- Verifying JDK versions in docs fall within the support policy.
- Building/testing code snippets marked executable.
- Checking that placeholders do not slip into release-specific instructions.
- Ensuring referenced documentation paths still exist.
- Blocking PRs that change `--release`/toolchain/runtime image without updating changelog/migration notes per policy.
- Detecting minimum JDK mismatches between module metadata and docs.
- Generating the public support matrix from an approved source when feasible.

### 41.1. Do Not Test Examples on the Wrong Runtime

For example, `List.of` only exists since Java 9; if the developer guide promises Java 8 source, that snippet will fail on floor 8. A snippet using Java 21 pattern switch should not be placed in documentation for a module keeping `--release 17`.

Test snippets must use **the compiler release appropriate to each section**; if code is illustrative only rather than standalone runnable, clearly mark dependencies/imports/placeholders.

### 41.2. Documentation QA and Runtime QA Are Two Separate Things

Passing link checks does not prove deploy commands work. Conversely, passing deployment smoke tests does not prove the support FAQ is updated. Both are required for release readiness.

## 42. PR Template for Java Compatibility Changes

~~~markdown
## Change summary
- JDK migration target and affected modules:
- Current and new minimum runtime:
- Build JDK / compiler --release:

## Platform/support impact
- Supported JDK distributions:
- OS and CPU architecture:
- Runtime/container image:
- Native libraries / agents:
- Unsupported or deprecated combinations:

## Validation
- CI matrix and run IDs:
- Integration/contract tests:
- Runtime fingerprint and artifact checksums:
- Known issues / workarounds:

## Documentation updates
- README / developer setup:
- IDE/toolchain instructions:
- Support matrix / release notes:
- Deployment / rollback runbook:
- Support FAQ:

## Release operations
- Canary and monitoring plan:
- Stop/go criteria:
- Rollback constraints:
- Owners and approvals:
~~~

Do not let the docs section become a mechanical checkbox; reviewers must cross-check actual values against CI/runbooks and the support policy.

## 43. Complete Example: Service Moving from Java 17 to Java 21

Suppose service `orders-service` has components:

~~~text
orders-service
  server runtime: Java 17 -> Java 21
  shared-client SDK: Java 17 minimum remains
  build tooling: Gradle Wrapper with supported daemon JVM
  image: approved Linux glibc image
  native dependency: compression library
  agents: tracing + metrics
  environments: dev, CI, staging, production
~~~

### 43.1. Support Policy Changes

Clearly state `orders-service` requires Java 21 starting with the new release; `shared-client` still targets Java 17. Only OS/architectures with native compression binaries and agent support are production-supported.

### 43.2. Developer Setup Changes

- Require JDK 21 compiler/toolchain for service builds.
- Document `./gradlew --version` and `java -version`.
- Adjust IDE/Gradle JVM instructions.
- Run local integration tests using DB/test containers.
- Use `--release 17` for the client SDK.
- Document native dependency setup and supported architectures.

### 43.3. CI Changes

- Add target JDK 21 test jobs.
- Retain Java 17 tests for SDK compatibility.
- Test the Linux amd64 production image.
- Add ARM64 under the candidate label until native support is complete.
- Verify tracing/metrics instrumentation.
- Store artifact SHA, image digest, JVM build, and test reports.

### 43.4. Runbook Changes

- Use the approved image digest.
- Check agent version, native compression, and truststore.
- Canary traffic, error rate, latency, GC, and traces.
- Set stop/go gates.
- Document rollback preconditions when the new service has already written data.

### 43.5. Release Notes/Support FAQ Changes

Send a clear notice:

~~~text
Server release requires Java 21 in approved runtime images.
Client SDK remains compatible with Java 17 per published
support matrix. Custom deployments must validate agents,
JNI/native libraries and JVM flags before upgrade.
Use the version-specific migration and rollback guides.
~~~

### 43.6. What Counts as Complete?

Not just a “green build”. There must be clear artifact/version support, new developers able to build the project from documentation, on-call able to rehearse the runbook, support able to triage via FAQ, CI matrix backed by evidence, and production canary passing gates.

## 44. Contrasting Example: An SDK Library Without Control Over Customer JVMs

For an SDK, risk lies in the consumer's runtime rather than a team-controlled service runtime:

- The library can compile with JDK 21 while keeping `--release 17`.
- Consumers can run on Temurin, Corretto, Zulu, or other distributions per policy.
- Different consumers use Windows/Linux/macOS.
- A new transitive dependency might be compiled with Java 21 class files and break Java 17 compatibility.
- A `multi-release JAR` can use runtime-specific implementations yet the public API must stay consistent.
- Annotation processors/code generators may need a different JDK than the SDK's runtime.

Therefore, the SDK migration guide needs:

1. Minimum Java runtime by artifact version.
2. Dependency compatibility and public API change policy.
3. Build tool setup for Maven/Gradle consumers.
4. Compatibility test results at the minimum runtime.
5. How to detect `UnsupportedClassVersionError` and `NoSuchMethodError`.
6. Guidance for consumers using JPMS/module path if supported.
7. Policy on library versions, end-of-support, and migration paths.

Do not write “the server's JDK is 21 so SDK customers must also use 21” when the SDK artifact is kept Java 17-compatible.

## 45. Common Mistakes When Updating Documentation

**“Updating only README is enough.”** Insufficient if the support matrix, CI, Dockerfile, and rollback runbook still contain old versions.

**“The build JDK and runtime JDK are the same.”** Not necessarily. Compiler toolchain and bytecode target can differ from the production JVM.

**“The Java version in the IDE is the source of truth.”** Insufficient; check Maven/Gradle daemon/compiler and test launcher.

**“Testing one distribution means supporting all vendors.”** Cannot be inferred when OS, JVM implementation, agent, native, and security differences remain.

**“Supporting Linux means supporting every Linux image.”** Wrong if libc, architecture, certificates, or native dependencies differ.

**“CI uses JDK 21 so production also uses that exact build.”** Uncertain when image tags/runner versions can change.

**“Adding an `--add-opens` flag to every environment prevents incidents.”** Can grant unnecessary access and fails to fix other API/bytecode errors.

**“You can roll back by swapping the image without checking data.”** Wrong when schemas/protocols/persistent state changed.

**“The agent loaded, so observability is still fine.”** Uncertain; test traces, metric labels, alerts, and overhead.

**“LTS JDKs are always supported and patched indefinitely.”** Depends on vendor/support policy.

**“The support table says PASS without logs, which is still acceptable.”** Lacks concrete runtime and artifact evidence.

**“The more commands in a runbook, the better.”** Wrong if commands target the wrong OS, lack permissions, expose secrets, or can cause downtime.

**“A debug workaround should stay permanently because it helps safety.”** Wrong; workarounds can introduce security/compatibility risks.

**“Updating docs after release is fine too.”** For runtime minimum/rollback changes, this can cause unnecessary errors for customers and on-call.

**“Docs edited means the procedure was tested.”** Those are two different states; last-validated evidence is required.

## 46. Release Checklist: Documentation and Operations

- [ ] Have an authoritative support policy tied to the product release.
- [ ] Java minimum/runtime targets are stated separately per component/module.
- [ ] JDK distribution/OS/CPU/platform support is verified, not assumed.
- [ ] JDK patch/build and container digest are recorded in release evidence.
- [ ] Developer prerequisites match the active toolchain.
- [ ] README has commands to verify `java`/`javac`/wrapper and working links.
- [ ] Maven/Gradle instructions distinguish daemon/compiler/`--release`/tests.
- [ ] IDE guide is updated for versions supported by the organization.
- [ ] Local integration prerequisites, test containers, and secrets are described.
- [ ] JNI/JNA/native/agent dependencies have OS/architecture-appropriate instructions.
- [ ] CI matrix and mandatory release gates are published.
- [ ] Test reports accurately record PASS/FAIL/NOT_RUN/SKIPPED.
- [ ] Release notes state action required, breaking support changes, and known issues.
- [ ] Migration guide includes before/during/after steps and success criteria.
- [ ] Runbook includes preflight and artifact/JDK/image verification.
- [ ] Canary/rollout has stop/go thresholds and an owner.
- [ ] Monitoring, dashboards, metrics, traces, and alerts are confirmed.
- [ ] Rollback preconditions cover schema/protocol/data compatibility.
- [ ] Incident triage guides cover classpath, bytecode, JNI, TLS, and agents.
- [ ] Safe log/dump collection and secret redaction procedures exist.
- [ ] Support FAQ and escalation ownership are updated.
- [ ] Workarounds have owners, risks, and expiries.
- [ ] Deprecation/EOL notices include effective dates and migration paths.
- [ ] Versioned docs remain available for supported releases.
- [ ] Link checks/snippet tests or manual reviews are completed per policy.
- [ ] Runbook records the last execution/verification and evidence.
- [ ] Triggers exist to update docs when JDK patches/OS images/vendors/agents change.

A checklist is not a completion certificate; each critical box must have corresponding documentation, CI evidence, or an approver.

## 47. Technical Sources to Cross-Check Before Publishing

Support documentation should be grounded in **the exact JDK release, distribution, and tool versions**:

- **JDK Release Notes and Java SE Platform docs:** API, module, security, and runtime changes.
- **Java Virtual Machine Specification:** class-file versions, loading/linkage/initialization.
- **`javac` Tool Guide:** `--release`, source/target, and API restrictions.
- **Gradle Java Compatibility Matrix and Toolchains docs:** build daemon differing from compiler/test toolchain.
- **Maven Compiler Plugin, Toolchains, Surefire/Failsafe docs:** compiler JDK, release target, and test forks.
- **IDE/vendor Java support docs:** Project SDK, module language level, language server, and plugins.
- **JDK distribution vendor support pages:** release lifecycles, OS/CPU architectures, and full builds.
- **Container platform docs:** image digests, multi-platform manifests, cgroups/namespaces.
- **Java Instrumentation/JVMTI docs:** startup/dynamic agents, native profilers.
- **JDK troubleshooting guides:** `jcmd`, JFR, fatal error logs, NMT, and JNI checks.
- **Security/TLS provider documentation:** truststores, certificates, algorithm constraints.
- **Framework/JDBC/APM/native library compatibility matrices:** supported integration combinations.

Vendor documentation and support matrices change over time. Do not state “latest version” or “vendor X always supports platform Y” in a guide without a review date; record the exact versions/sources at release time and the re-verification process.

## 48. Conclusion

Updating support documentation, development environments, and operations guides is a **mandatory engineering task** of Java Advance Compatibility Migration, not a step to polish the README after the code is finished. Java compatibility is not just whether `javac` compiles: it covers the executing JVM, class-file target, distribution, OS/architecture, native libraries, agents, security, data, and operational behavior.

A responsible migration must **publish exact support scope**, help developers reproduce environments, let QA/CI prove production combinations, give SRE the ability to deploy and recover per runbook, and help support explain requirements and route failures accurately. These documents must stay synchronized with artifacts, JVM builds, image digests, and actual testing.

Manage support policies, READMEs, toolchains, release notes, migration guides, runbooks, and FAQs as part of the release lifecycle: with owners, versioning, reviews, verification, and update schedules when JDK security patches or runtime images change. That way, upgrading the JDK does not stop at **“the application runs”**, but achieves something more important: **those who build, operate, and use the system clearly know the support conditions, how to verify them, and how to respond when incidents happen**.