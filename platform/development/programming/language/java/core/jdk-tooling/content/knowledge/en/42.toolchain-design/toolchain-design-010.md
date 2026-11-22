# Documenting Decisions in Java Toolchain Design

When designing a Java toolchain, a development team must select and coordinate many components: JDK vendor and version, the JVM running the build tool, compiler, Java API/bytecode target, test runtime, Maven or Gradle, wrapper, plugins, dependencies, packaging tools, runtime image, and CI environment. Each choice can affect build reproducibility, compatibility, performance, security, operational cost, and future upgrade paths.

**Documenting decisions** helps readers understand what the team chose, why they chose it, which alternatives were considered, and which trade-offs were accepted. For choices with long-term impact, a common approach is to use an **Architecture Decision Record (ADR)**. An ADR is a short document that records an important decision along with its context and consequences.

A decision is only valuable when others can understand and verify it. Saying “we use Java 17 because it is stable” is not enough. A useful record needs to state compatibility requirements, the actual JDK used, the rationale for choosing it, how to verify the build, and the conditions that require the team to revisit the decision.

## 1. Why document toolchain decisions?

Failing to document decisions often leads to:

- New team members not knowing why the project requires a specific JDK.
- Developer machines and CI using different JDKs, producing different build results.
- The team changing Maven/Gradle or plugins without realizing the impact on artifacts.
- An old decision being re-debated because no one can find the original rationale.
- Security updates being delayed because it is unclear who is responsible for tracking the JDK and plugins.
- Runtime images or installers not being reproducible due to missing module lists and build commands.
- Version upgrades causing compatibility errors without a baseline for comparison.

A good ADR helps answer quickly: what issue needs a decision, which constraints and criteria matter, which options were considered, what the team chose and why, what the consequences are, what evidence confirms the decision is implemented correctly, and what conditions trigger a review of the decision.

An ADR stores the rationale and scope of a decision. Build configurations, pipelines, and code are where the decision is enforced. Both types of artifacts need to link to each other.

## 2. When should you create a decision record?

You do not need an ADR for every small change. Document a decision when a choice is hard to reverse or costly to change; affects multiple modules, teams, services, or environments; impacts security, reliability, performance, compatibility, or cost; chooses between tools or platforms with different operational consequences; establishes a shared standard for building, testing, packaging, or releasing; or is likely to make someone ask “why does the project do it this way?” in the future.

Examples of decisions worth documenting in a Java toolchain:

| Decision | Why it matters |
|---|---|
| Choosing JDK vendor and version | Affects runtime, support, security patches, and native behavior |
| Choosing Maven or Gradle | Affects build model, plugin ecosystem, and maintenance |
| Requiring Wrapper usage | Standardizes build tool version across developers and CI |
| Choosing Java release target | Defines the minimum API and bytecode the application supports |
| Choosing test runtime matrix | Defines which JDKs are tested |
| Choosing packaging or shading plugins | Affects artifact contents and runtime behavior |
| Choosing jlink/jpackage | Affects runtime image, installer, and OS support |
| Choosing repository and signing flow | Affects distribution, verification, and artifact traceability |

You do not need an ADR for renaming a variable or updating a small test if it does not change technical conventions.

## 3. Distinguishing decisions, configuration, and operational documentation

| Document type | Main question | Example |
|---|---|---|
| Decision record / ADR | Why was this option chosen? | Why the project uses Gradle Wrapper and a Java 17 toolchain |
| Build configuration | How is the build actually configured? | build.gradle.kts, pom.xml, wrapper properties |
| Runbook | What should be done during operations or troubleshooting? | How to check the JDK on CI, how to update the wrapper |

An ADR is not a copy of pom.xml or build.gradle. Do not turn an ADR into a step-by-step installation guide or a full list of dependencies. Record the decision, rationale, and consequences; link to configurations, pipelines, or runbooks as implementation evidence.

Meeting notes record what was discussed. An ADR records the conclusion that was decided. A long meeting does not replace a clear decision.

## 4. Java toolchain components to document separately

The term “Java version” is often too vague. A project may use multiple Java versions for different purposes. When documenting a decision, separate the following layers:

| Component | Question to document |
|---|---|
| Build JVM | Which JDK runs Maven or the Gradle daemon? |
| Compiler toolchain | Which JDK provides javac for compilation? |
| Release target | Which Java version is the target API and bytecode? |
| Test launcher | Which JDK do unit/integration tests run on? |
| Production runtime | Which JDK/runtime is the application supported on? |
| jlink toolchain | Which JDK creates the custom runtime image? |
| jpackage toolchain | Which JDK creates the application image/installer? |
| OS/architecture | Which Windows/Linux/macOS and x64/ARM64 targets is the artifact built for? |
| Build tool | Which Maven/Gradle version is pinned via Wrapper? |
| Plugin | Which plugins affect compile, test, package, and publish? |

In particular, these three concepts are not interchangeable:

- The JDK toolchain determines the Java toolset used by tasks.
- The compiler release option determines API and bytecode compatibility.
- JAVA_HOME usually selects the default Java for a process or tool, but does not necessarily override the project's own toolchain configuration.

For example, Gradle can run on a supported JVM, use JDK 17 to compile, yet configure release 11 to ensure the code only uses Java 11 APIs. These are three related but distinct decisions.

## 5. Process for documenting a decision

### Step 1: Define the question to decide

Write a question narrow enough to make clear where the decision applies.

Good: “How will this Java service project pin its Gradle version and select the JDK compiler toolchain so that developers and CI produce the same kind of artifact?”

Too broad: “How should we modernize the entire Java platform?”

An ADR should contain one independent decision. If a choice can be changed separately without changing the rest, consider splitting it into another ADR.

### Step 2: Record context with facts

Context describes the state and problem before choosing a solution. Record verifiable data: current JDK and build tool; number of build environments and supported OSes; minimum Java version required by users; plugins or dependencies with compatibility limits; build times, build failures, or differences between local and CI; security policy, support windows, and upgrade schedules; constraints on network, JDK installation permissions, artifact repositories, or native tools.

Separate facts from opinions. “CI is using JDK 21.0.x while developer machines use JDK 17” is a fact. “CI is poorly configured” is a judgment that does not identify the cause.

### Step 3: Identify decision drivers and hard constraints

Decision drivers are criteria that make an option valuable. Examples: must support at least Java API 17; builds must be reproducible between developers and CI; the JDK needs appropriate security updates and vendor support; packaging plugins must be compatible with the build tool; artifacts must run on Linux x64 and Linux ARM64; pipelines must not download dependencies from unapproved repositories.

Distinguish hard constraints from criteria that can be traded off. If an option fails a mandatory requirement, eliminate it before scoring. Do not let a high performance score compensate for violating a security requirement.

### Step 4: List options actually considered

Include the current approach, the proposed option, and a reasonable alternative. Include “keep the status quo” in the list if it is a realistic option.

Examples: using system Maven/Gradle and each machine's JAVA_HOME; using Maven Wrapper or Gradle Wrapper to pin the build tool; using Wrapper combined with project-level Java toolchains; using a digest-pinned container build image providing a standard JDK; or using a centrally managed JDK on CI runners.

Do not list artificial options just to make the decision look more thoroughly compared.

### Step 5: Compare using criteria and evidence

You can use a pros/cons table or a weighted matrix. First eliminate options that fail hard constraints. Then compare the remaining choices against observable criteria.

The example matrix below only illustrates how to record comparisons; weights and scores must be determined by the team from actual requirements.

| Criterion | Example weight | Evaluation question |
|---|---:|---|
| Reproducibility | 30% | Do two environments build with the same toolchain? |
| Compatibility | 25% | Does it meet Java release, plugin, and runtime targets? |
| Security/support | 20% | Is there a process for updating the JDK, plugins, and checksums? |
| Operations | 15% | How easy is it to install, debug, upgrade, and support? |
| Build performance | 10% | Do build time and caching meet targets? |

If using a 1–5 scale, record score definitions and evidence. Scores are not absolute truth; they help visualize trade-offs. Do not use a single composite number to hide hard constraints or serious risks.

### Step 6: Run a trial before accepting

For high-impact choices, create a spike or proof of concept:

1. Build a representative module.
2. Run unit tests and integration tests.
3. Produce the artifact in the expected format.
4. Run the artifact on the target runtime.
5. Verify the build locally and on CI.
6. Measure build time, cache hits, image size, or startup if those are drivers.
7. Verify checksums, download sources, and reproducibility.
8. Record any errors and limitations discovered.

Link logs, pull requests, benchmarks, or test reports in the ADR. Do not paste thousands of log lines into the decision record.

### Step 7: Finalize the decision and state trade-offs clearly

The Decision must be a specific declarative statement, for example: “The project uses a pinned-version Gradle Wrapper; Java compile tasks use a Java 17 toolchain and release target 17.”

The Rationale answers why this option fits the context and drivers. Consequences record both benefits and costs: maintaining the wrapper, applying JDK patch updates, configuring toolchains for developers, and checking CI on version upgrades.

### Step 8: Review, accept, and track implementation

Record who has decision authority, who is responsible for implementation, and the acceptance date. Once approved, update build/pipeline configurations and verify that the implementation matches the ADR.

Do not mark it Accepted just because the file was created. Proposed means it is awaiting review; Accepted means the decision has been approved.

## 6. How to evaluate toolchain options

A comparison table should evaluate the project's actual needs. For example, when choosing how to manage the build tool:

| Option | Pros | Costs/risks |
|---|---|---|
| System-installed build tool | Installed once on a machine | Versions can drift between machines and CI |
| Wrapper in repository | Build tool version is declared with the project | Requires reviewing wrapper files and distribution downloads |
| Wrapper + toolchain | Pins both the build tool and the JDK used by tasks | Requires configuring and managing JDK provisioning |
| Container build image | OS/JDK/tool environment can be pinned by digest | Image needs rebuilding and scanning; local workflow adds a container layer |

When choosing a JDK vendor, compare support policy, release cadence, platform coverage, license, update process, performance, and how binaries are verified. Do not pick a vendor just because the name is familiar.

When choosing a Java release target, look at the actual deployment runtime, APIs needed by the code, dependency bytecode, framework support, and product support lifetime. A lower release target does not automatically make an application run on all older JDKs if a dependency requires a newer runtime.

When choosing jlink/jpackage, specify the JDK creating the runtime image, root modules, locales, service bindings, OS/architecture, native dependencies, and installer format. Do not just write “use JDK 25” if build, test, and runtime use different versions.

## 7. Evidence to collect before recording a decision

### Verify Java and the build tool

Linux/macOS:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
./gradlew --version
./gradlew -q javaToolchains
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
~~~

Maven Wrapper:

~~~bash
./mvnw -version
~~~

Windows:

~~~powershell
.\mvnw.cmd -version
~~~

Record both the JDK running the build tool and the JDK actually selected by compiler/test tasks. Recording only `java -version` output from a terminal is not enough to describe the full toolchain.

### Inspect build configuration

With Gradle:

~~~bash
./gradlew tasks
./gradlew dependencies
./gradlew clean check
~~~

With Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
~~~

The effective POM and dependency tree help identify plugins, dependencies, and configurations applied after inheritance. Do not include outputs containing credentials or repository secrets in an ADR.

### Record artifact details

After building, record the artifact name, version, and classifier; SHA-256 digest; compiler release and class file version; build and runtime JDK vendor/version; OS/architecture and build image digest; dependency/SBOM reference; test reports and smoke test results.

Evidence must point to the exact commit and artifact tested. A link to “latest build” is not sufficient to trace historical decisions.

## 8. Where to store decision records?

For a single project's decisions, the simplest approach is to store Markdown files in the repository:

~~~text
project/
  docs/
    adr/
      README.md
      0001-standardize-java-toolchain.md
      0002-select-runtime-image-modules.md
      0003-publish-artifacts-to-repository.md
~~~

The README in `docs/adr` should be a short index: ADR number, title, status, and links. Name files by sequence number and decision topic for easy searching.

The advantages of storing them in the source repository are that decisions travel alongside code and build configuration; they have Git history and pull request review; ADRs can be linked to issues, commits, releases, and pipelines; and anyone editing the build can read the decision before making changes.

Organization-wide decisions may need an architecture register or a documentation system with appropriate access control. Wherever stored, there should be a canonical location, clear ownership, and links from relevant repositories.

Do not store tokens, passwords, private keys, personal data, or system outputs containing secrets in an ADR. Reference the secret manager name or policy instead of secret values.

## 9. ADR template for Java toolchains

The template below is concise enough for regular use while still capturing context and consequences. Each ADR should cover only one primary decision.

~~~markdown
# ADR-NNNN: [Decision title as a declarative statement]

- Status: Proposed
- Date: YYYY-MM-DD
- Deciders: [Roles/people with decision authority]
- Owner: [Person tracking implementation]
- Scope: [Project/module/CI/release]
- Related: [Related issues, PRs, or ADRs]

## Context and problem

[Describe the current state, problem, and verifiable constraints.]

## Decision drivers

- [Mandatory requirement]
- [Compatibility criterion]
- [Security, operations, or performance]

## Options considered

### Option A

- Pros:
- Cons:

### Option B

- Pros:
- Cons:

### Option C

- Pros:
- Cons:

## Decision

[Clearly state the chosen option and its scope.]

## Rationale

[Explain why this option fits better than the alternatives.]

## Consequences

### Positive

- [Concrete benefits]

### Negative and accepted trade-offs

- [Accepted costs/risks]

## Implementation and validation

- [Configuration or repository path]
- [Verification commands]
- [Required tests/metrics]
- [Artifact or evidence links]

## Rollback and review triggers

- [How to revert or replace]
- [Conditions requiring a review of the decision]

## References

- [Official documentation]
~~~

If the team prefers a lighter template, you can keep four minimal sections: Title, Status, Context, Decision, and Consequences. Add options tables, deciders, evidence, and review triggers when complexity warrants it.

## 10. Complete ADR example: standardizing Gradle Wrapper and Java toolchain

The following example is a hypothetical scenario to illustrate how to write an ADR. It is not a claim that every project should use Gradle or Java 17.

~~~markdown
# ADR-0007: Pin Gradle Wrapper and Java 17 compile toolchain

- Status: Accepted
- Date: 2026-11-10
- Deciders: Java service maintainers
- Owner: Build engineering
- Scope: Main Java service and CI build

## Context and problem

Developer machines and CI runners have used different Gradle and JDK
installations. The same commit can therefore be built with different
compiler APIs or build plugin behavior. The service contract requires
the application to use Java 17 APIs and produce Java 17-compatible
class files.

The project already uses Gradle Kotlin DSL. Replacing the build system
would create migration work without addressing the immediate source
of toolchain drift.

## Decision drivers

- A project must declare its Gradle version.
- Compile tasks must use a Java 17 toolchain.
- Compile output must target the Java 17 API and bytecode level.
- Local and CI builds must run the same verification tasks.
- JDK patch updates must follow the approved security update process.

## Options considered

### System-installed Gradle and JAVA_HOME

Pros:
- Minimal repository configuration.

Cons:
- Build tool and JDK versions can differ by workstation or runner.
- A developer may build with a version that CI does not use.

### Gradle Wrapper without a Java toolchain

Pros:
- Gradle version is standardized.
- Small configuration change.

Cons:
- Compiler selection can still depend on the machine environment.

### Gradle Wrapper plus Java toolchain and release target

Pros:
- Build tool version is declared by the repository.
- Compile tasks select the required Java language version.
- The release setting prevents accidental use of APIs newer than Java 17.

Cons:
- The team must provision and update a matching JDK.
- The Gradle daemon JVM and compile toolchain must be documented separately.

## Decision

Use the Gradle Wrapper for every project build. Configure Java compile
tasks to use a Java 17 toolchain and release target 17. CI must use the
approved JDK distribution and immutable build image. Test and release
jobs must run the same verification task set.

## Rationale

The project already uses Gradle. Wrapper plus toolchain addresses both
build-tool drift and compiler selection while preserving the existing
build model. The release setting enforces the Java 17 API and bytecode
contract.

## Consequences

### Positive

- Developer and CI builds use the declared Gradle distribution.
- Compile tasks request Java 17.
- The compiler rejects accidental use of APIs newer than Java 17.
- Toolchain updates can be reviewed as explicit repository changes.

### Negative and accepted trade-offs

- JDK provisioning becomes part of developer and CI setup.
- A toolchain language version alone does not pin a vendor or patch.
- The Gradle daemon JVM still needs its own supported version policy.
- JDK patch updates require a build and regression review.

## Implementation and validation

- Commit Gradle Wrapper files and the distribution checksum.
- Configure Java toolchain language version 17.
- Configure JavaCompile release 17.
- Run ./gradlew --version and ./gradlew -q javaToolchains.
- Run ./gradlew clean check on local and CI.
- Verify the artifact class file version and run smoke tests on Java 17.
- Record the CI image digest and JDK vendor/version with each release.

## Rollback and review triggers

Create a new ADR if the service changes its minimum Java runtime,
the build tool becomes unsupported, a required plugin cannot run on
the selected toolchain, or a security/support change requires another
JDK distribution. Preserve this accepted ADR and link the replacement.

## References

- Gradle Wrapper documentation
- Gradle JVM toolchains documentation
- Java compiler --release documentation
~~~

### Corresponding illustrative Gradle configuration

File `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

This configuration requests a Java 17 toolchain for Java tasks and restricts the API/bytecode to release 17. It does not pin the JDK patch version or vendor. If the organization requires a specific vendor, configure the appropriate vendor/toolchain resolver and document that policy in the ADR. If strict patch pinning is required, manage the JDK distribution in a controlled CI image or provisioning system.

The file `gradle/wrapper/gradle-wrapper.properties` must declare the distribution URL of the approved Gradle version. You should verify the distribution checksum according to the supported Wrapper procedure.

### Verification commands

Linux/macOS:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean check
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat clean check
~~~

Check the class file version:

~~~bash
javap -verbose -classpath build/classes/java/main com.acme.Main
~~~

For Java 17, the class file major version is 61. This is a bytecode check; you still need to test and run the artifact on a Java 17 runtime to confirm dependencies and actual behavior.

## 11. Documenting Maven toolchain decisions

Maven Wrapper and Maven Toolchains solve two different problems:

- Maven Wrapper specifies the Maven distribution used by the project.
- Maven Toolchains allow compatible plugins to use a selected JDK independently of the JVM running Maven.

For example, Maven Wrapper can be invoked as follows:

~~~bash
./mvnw -version
~~~

Windows:

~~~powershell
.\mvnw.cmd -version
~~~

The output helps identify the Maven version and the Java runtime running Maven. It does not by itself prove which JDK the compiler plugin used.

A Maven toolchain can be declared in the user's or build agent's `toolchains.xml` file. Example JDK configuration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/temurin-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

The path above is a Linux example; Windows machines need the corresponding JDK path. Do not commit a developer's local path into the project. CI needs a reproducible provisioning path or image.

In `pom.xml`, configure the Compiler Plugin to use the release target:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

To select a toolchain, the project must configure the Maven Toolchains Plugin and the executing plugins must support toolchains. Check the documentation for the version of the plugin in use; do not assume every plugin automatically uses the selected JDK.

A Maven ADR should specify the Maven Wrapper version, the JDK running Maven, the JDK compiler toolchain, the release target, `toolchains.xml` provisioning, plugin versions, and how CI verifies the selection.

## 12. Managing ADR status and decision history

A decision record typically has the following statuses:

| Status | Meaning |
|---|---|
| Proposed | Under consideration, not yet accepted |
| Accepted | Approved and currently in effect |
| Rejected | Considered but not chosen |
| Deprecated | No longer recommended or no longer suitable |
| Superseded | Replaced by another ADR |

Once a decision is accepted, preserve its content and rationale as history. If the context changes, create a new ADR explaining the new decision and link the old ADR. Mark the old ADR as Superseded and record the number of the replacement ADR.

Do not rewrite history to make it look like the team always chose the new option. Fixing typos or clarifying wording is acceptable; changing the decision, rationale, or scope must go through proper review history.

Example link:

~~~text
ADR-0007: Pin Gradle Wrapper and Java 17 toolchain
Status: Superseded by ADR-0014

ADR-0014: Move the service build to Java 25 toolchain
Status: Accepted
Supersedes: ADR-0007
Reason: The service runtime baseline and supported dependencies changed.
~~~

Keeping old ADRs helps readers understand when each decision was in effect and why the team changed direction.

## 13. Tracking decision implementation

An Accepted ADR that is not implemented does not solve the problem. Each decision should have corresponding tasks and evidence:

| Decision | Implementation work | Evidence |
|---|---|---|
| Pin Maven/Gradle | Commit Wrapper files and checksum | Wrapper version in CI logs |
| Choose JDK compiler | Configure toolchains/toolchain resolver | Toolchain listing and compiler logs |
| Choose release target | Configure `--release` | `javap` class version and compatibility tests |
| Choose test matrix | Configure CI matrix | Test reports by JDK/OS |
| Choose runtime image | Configure jlink/jpackage | Module list, image digest, and smoke tests |
| Choose artifact repository | Configure publish credentials and repository | Published coordinates, checksum, signature |
| Choose security cadence | Establish review/update schedule | Update PRs, scan reports, and release metadata |

You can add owner, due date, and status columns in an issue tracker. The ADR only links to the work; do not turn the document into a long progress-tracking table.

### Conformance checks

In pull requests that change the toolchain, reviewers should ask:

- Does the change align with Accepted ADRs?
- Are the Wrapper version and checksum updated together?
- Do the compiler/test/runtime JDKs match the decision?
- Was the release target changed unintentionally?
- Are plugins and dependencies compatible?
- Does CI verify the right toolchain and artifact digest?
- If the decision changed, has a new ADR been created and linked?

If the implementation needs to diverge from an ADR, document the reason and new decision instead of letting configuration drift away from documentation.

## 14. When should a toolchain decision be reviewed?

An ADR does not mean the technology will be kept forever. Define triggers as soon as the decision is accepted:

- The JDK vendor ends support or changes its license policy.
- The Java release target no longer meets dependency or product requirements.
- The build tool/plugin is no longer supported or has a security issue.
- The CI image/base image no longer receives patches.
- Build time or cache performance exceeds thresholds.
- The runtime image is no longer compatible with the target OS/architecture.
- A security advisory requires upgrading the JDK or a plugin.
- The team changes distribution format, from JAR to jpackage/container.
- A dependency forces raising the Java baseline.

When a trigger occurs, re-evaluate the context and options. If the change is significant, create a new ADR. Do not upgrade a version just because a newer release exists; verify compatibility, support, security, and trial results.

## 15. Common mistakes when documenting decisions

| Mistake | Why it is unhelpful | How to fix |
|---|---|---|
| Writing only “use Java 17” | Unclear whether it is build JVM, compiler, or runtime | Document each toolchain layer separately |
| Omitting context | Readers do not understand the original problem | State current state, constraints, and evidence |
| Omitting rejected options | Unclear what the team considered | Record real alternatives and reasons |
| Listing only pros | Hides operational costs | Record trade-offs and accepted risks |
| Writing “latest version” | Results change over time | Pin a specific version and decision date |
| Naming a vendor without an update policy | Unclear who updates it and when | Record owner, cadence, and security triggers |
| Confusing `--release` with JDK toolchain | May compile with an unintended JDK | Document compiler JDK and API target separately |
| ADR not linked to configuration | Implementation cannot be verified | Link build files, CI, and test evidence |
| Editing an old ADR after changing direction | Loses history of why the decision changed | Create a new ADR and supersede the old one |
| Writing an ADR as long as a design specification | Hard to find the conclusion | Keep the decision concise and link detailed docs |
| Creating an ADR for every minor change | Increases documentation overhead | Only document decisions with significant impact |

## 16. Checklist before accepting a decision record

- [ ] Title clearly states the decision.
- [ ] Project/module/environment scope is defined.
- [ ] Context includes verifiable facts and constraints.
- [ ] Build JVM, compiler toolchain, release target, and runtime are distinguished.
- [ ] Hard constraints and decision drivers are clearly stated.
- [ ] Current option and realistic alternatives are included.
- [ ] Rationale and positive/negative trade-offs are included.
- [ ] Versions of JDK, build tool, plugins, and dependencies are recorded accurately when needed.
- [ ] Trial evidence is included, or a reason why a trial could not be run.
- [ ] Owner and deciders are listed.
- [ ] Implementation tasks and validation criteria are defined.
- [ ] Rollback/review triggers are defined.
- [ ] Links to build configuration, CI, issues, and official documentation are included.
- [ ] No secrets or sensitive data are included.
- [ ] Proposed/Accepted/Rejected status is clear.
- [ ] If replacing an old decision, the new ADR links the old ADR and states the reason.

## 17. Key takeaways

- Document decisions to record what was chosen, why it was chosen, and which consequences were accepted.
- ADRs fit toolchain decisions with long-term impact or effects across multiple environments.
- One ADR should focus on one independent decision.
- Context must describe facts, problems, and constraints; Decision must clearly state the choice.
- Compare options using hard constraints, decision drivers, and trial evidence.
- Record benefits, costs, risks, owner, and review triggers.
- Distinguish build JVM, compiler toolchain, release target, test runtime, and production runtime.
- Maven/Gradle Wrapper pins the build tool; Maven/Gradle toolchains control the task JDK; `--release` controls the API and bytecode target.
- ADRs explain why; build files and CI enforce the decision.
- An Accepted ADR is valuable history; when changing direction, create a new ADR and link the old decision.
- Track implementation through tests, pipelines, artifact digests, and reviews.
- Do not record secrets in decision records.

## Official References

- [Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Maven Toolchains Guide](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Gradle Wrapper Basics](https://docs.gradle.org/current/userguide/gradle_wrapper_basics.html)
- [Gradle JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [The javac Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Architectural Decision Record Process — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)
- [Architecture Decision Record Templates](https://github.com/architecture-decision-record/architecture-decision-record/blob/main/skills/architecture-decision-record-skill/reference/templates.md)
- [Documenting Architecture Decisions — Government Digital Service](https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html)
- [Architecture Decision Record — Martin Fowler](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html)
