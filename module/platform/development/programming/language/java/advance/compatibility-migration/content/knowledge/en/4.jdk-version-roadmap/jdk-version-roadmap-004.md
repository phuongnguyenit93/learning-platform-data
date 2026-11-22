# Reading Release Notes, Migration Guides, and Relevant JEPs

When preparing for a JDK upgrade, the three documentation sources you need to read most frequently are **release notes**, **migration guides**, and **JEPs (JDK Enhancement Proposals)**. They complement one another: release notes describe what was shipped in a specific release or update; migration guides gather changes that may affect applications and advise how to adapt; JEPs explain the goals, design, and impact of major improvements in OpenJDK.

Reading the right documentation helps the development team determine which changes actually apply to their upgrade path, which components are at risk of impact, and what needs to be verified. Reading should not stop at the list of new features. Entries covering default behaviors, removed APIs, JVM options, security, known issues, and compatibility problems often determine whether a migration is safe.

## 1. The Role of Each Documentation Type

### 1.1. Release Notes: What Changed in This Version?

Release notes are the release documentation for a specific JDK version, update, or distribution. They typically list new features, behavioral changes, bug fixes, known issues, security changes, and installation or operational notes.

Release notes help answer questions such as:

- Which changes are included in the JDK build the team plans to deploy?
- Were any JVM options, tools, APIs, or default values changed?
- Are there known issues involving the OS, architecture, GC, TLS, or build tools?
- Does the update include security fixes or security policy changes that could affect existing connections?
- Are there limits or deployment notes specific to the distribution being used?

Release notes are version-specific. When two environments both say Java 21 yet use different vendors, distributions, or build numbers, release notes may not be completely identical. Therefore, read the exact vendor's documentation for the exact update planned for production.

### 1.2. Migration Guide: What Needs to Be Done to Migrate the Application?

A migration guide explains changes that can break application assumptions when moving from one Java version to another. The document typically groups changes by topic, describing impact, how to recognize problems, and adaptation strategies.

A migration guide is particularly useful when looking for:

- APIs, packages, or modules that were removed or are no longer provided by default.
- Changes in the module system, reflection, and internal API access.
- Changes in the compiler, bytecode, JDK tools, or JVM options.
- Changes in charset, locale, timezone, serialization, and standard libraries.
- Changes in TLS, cryptographic algorithms, certificates, and security policies.
- Default behaviors that can cause legacy applications to produce different results.
- Checks or configuration steps required before deployment.

A migration guide offers a broader transition perspective than release notes. It may describe a change introduced in an earlier release, explain why it matters, and suggest how to update the application. However, do not assume every detail in a migration guide applies identically to every vendor or update. Cross-reference with the release notes and documentation of your exact JDK.

### 1.3. JEP: Why Was a Change Designed and How Does It Impact Systems?

JEP stands for *JDK Enhancement Proposal*. It is a proposal and specification document describing a JDK enhancement in the OpenJDK development process. A JEP typically explains the problem being solved, goals, scope, non-goals, design, considered alternatives, and compatibility impacts.

JEPs are helpful when release notes mention only a brief feature or change name. Reading a JEP clarifies:

- Why the change was introduced into the JDK.
- Which problems the feature solves and which it explicitly does not aim to solve.
- How the new design differs from the old behavior.
- Which APIs, behaviors, tools, or configurations are affected.
- What compatibility risks, limitations, or transition paths exist.
- Which release the feature belongs to and its implementation status.

A JEP is not a substitute for release notes or a migration guide. A JEP describes the design and process of integrating an enhancement into OpenJDK; release notes for a specific JDK build confirm what actually shipped in that build. Additionally, vendor- or distribution-specific changes may not have an associated JEP.

| Source | Focus | Use When Answering |
|---|---|---|
| Release notes | Contents of a specific release | What is new in this JDK build, what was fixed, and what issues remain? |
| Migration guide | Impact and how to migrate applications | Where could the existing application be affected and how should it adapt? |
| JEP | Goals, design, and impact of an enhancement | Why was the change made, what is its scope, and what risks exist? |

## 2. Identify the Exact Version and Distribution Before Reading

Documentation is only valuable when it matches the actual environment. Before opening release notes, explicitly identify the current version and the target version.

### 2.1. Record the JDK Used at Both Build and Runtime

Do not look only at the Java version in `build.gradle`, `pom.xml`, or README. The compiler used for building and the JVM running the application may differ. Gather details from the real environment.

Basic commands:

```bash
java -version
javac -version
```

With Gradle, check which JVM Gradle is using:

```bash
./gradlew -version
```

With Maven, inspect both the Maven runtime and the project's compiler/toolchain configuration. In containerized environments, check the image and command executed inside the container rather than checking only the JDK installed on a developer workstation.

Beyond the version number, record:

- Vendor and distribution, e.g., Oracle JDK, Eclipse Temurin, Amazon Corretto, or an OS-provided OpenJDK build.
- Full version string, build number, and security patch level.
- JDKs used to compile, test, run Gradle/Maven, and run the application.
- Operating system, CPU architecture, and container image type.
- JVM arguments, environment variables, and critical system properties.

Some details can be inspected using:

```bash
java -XshowSettings:properties -version
```

This command prints numerous system properties, including vendor, runtime version, architecture, and default charset. Save the exact output from the build or runtime environment under investigation.

### 2.2. Map the Upgrade Path

Explicitly note the source version and target version, such as Java 11 to Java 21. When crossing multiple major versions, do not read only the target version's documentation. Changes introduced in intermediate versions can still impact the application.

Example:

```text
Current JDK: 11
       |
       v
Changes from JDK 12, 13, 14, ...
       |
       v
Target JDK: 21
```

You do not necessarily have to deploy the application on every intermediate release one by one. However, when researching changes, review relevant releases along the upgrade span so you do not miss removed APIs, default changes, or security changes introduced prior to the target release.

### 2.3. Distinguish Feature Releases from Update Releases

In the modern release cadence, a feature release such as Java 21 continues receiving multiple update releases. Update releases typically include bug fixes and security patches; they can still alter behaviors or security policies relevant to the application.

Therefore, writing "upgrade to Java 21" may not be enough. You must know the exact update, build number, vendor, and image to deploy. When an issue appears in only one environment, this information helps separate differences across distributions or update levels.

## 3. How to Read Release Notes Systematically

Do not just skim the new features section. For migration purposes, read release notes in priority order based on their likelihood of affecting the application.

### 3.1. Check the Exact Vendor and Build Documentation

Locate the official release notes page of your JDK vendor. Confirm the title, version, build number, release date, and supported platforms. If the system uses container images, also check the release notes for the image or base distribution when published by the provider.

Do not mix one vendor's documentation with another vendor's runtime without noting differences. OpenJDK is the shared open-source foundation, yet vendors may package, patch, or support platforms on their own schedules.

### 3.2. Prioritize Sections Likely to Break Applications

When reading, look for the following headings or equivalent keywords:

| Section in Release Notes | What to Look For | Possible Impact |
|---|---|---|
| Removed Features / Removed APIs | Components that were removed | Compile failures, `ClassNotFoundException`, `NoClassDefFoundError`. |
| Deprecated Features / APIs | Components recommended against, especially items scheduled for removal | Migration debt and risk of breakage in future versions. |
| Changes / Compatibility | Altered behaviors or contracts | Different business outputs or integration behavior. |
| Security Changes | Algorithms, protocols, certificates, or security defaults | `SSLHandshakeException`, authentication failures, or rejected connections. |
| Tools and Utilities | Compiler, JDK tools, launcher, monitoring, or diagnostic changes | Build pipelines, scripts, or operational workflows impacted. |
| VM / Runtime Changes | JVM, GC, class loading, memory, or runtime options | Failure to start, memory changes, or latency shifts. |
| Known Issues | Known bugs and reproduction conditions | Specific features or platforms not behaving as expected. |
| Bug Fixes | Fixed bugs and before/after behavior | Application may have relied on the old behavior, even if it was a bug. |

Section names vary by vendor. If exact headings are missing, use the table of contents or search the page with related keywords.

### 3.3. Distinguish New Features, Default Changes, and Removed Behavior

Not every new item carries the same risk level. Classify each change:

- **New feature:** usually has no impact if the application does not use it. However, verify whether it changes defaults or is auto-enabled by a framework.
- **Default change:** can affect the application even without code edits, because the application relied on the old default.
- **Deprecated:** the API or feature may still work, but is no longer recommended. Check severity, warnings, and planned removal timeline.
- **Removed:** the component no longer exists; source code or binaries depending on it must be updated or replaced.
- **Bug fix:** can alter results if the application inadvertently relied on the previously buggy behavior.
- **Known issue:** identify trigger conditions and workarounds, or which update fixes the bug.

In particular, never equate "deprecated" with "removed". Likewise, never assume a "bug fix" cannot alter behavior. If the application depended on the old behavior, fixing the bug can expose an incorrect assumption in the application.

### 3.4. Trace Items Relevant to the Application Environment

While reading each item, cross-check against how the application is configured and run:

- If release notes mention TLS or cryptographic algorithms, inspect the endpoints, truststores, and certificates used by the application.
- If they mention JVM options, search for flags in Dockerfiles, scripts, deployment manifests, and service configs.
- If they mention charset, locale, or timezone, locate file read/write points, date/time parsing, and data formatting.
- If they mention modules or APIs, inspect direct and transitive dependencies, reflection, and class loading.
- If they mention GC or memory, check heap settings, container limits, and latency metrics.
- If they mention tooling, check CI pipelines, Gradle/Maven plugins, test tools, and agents.

An entry in release notes becomes a concrete risk only when a dependency path exists from the application to that change. Documenting the dependency path and verification method is far more useful than merely marking a keyword as "relevant".

## 4. How to Use a Migration Guide

Migration guides are often lengthy and organized by version or topic. An effective way to read is starting from your upgrade path, then locating the change categories matching your application's architecture and dependencies.

### 4.1. Read the Overview and Prerequisites

First, confirm the guide applies to your source version, target version, and vendor. Read prerequisites such as supported OS versions, CPU architectures, build tools, and framework minimum JDK requirements.

If the guide covers upgrading from the immediately preceding version while your system jumps from a much older version, read the intermediate guides as well. Never assume a short guide from A to B covers every change from A-5 to B.

### 4.2. Look for High-Probability Impact Topics

For a running Java application, the following areas usually warrant priority:

1. **APIs and modules:** packages, classes, or methods removed or moved out of the JDK; modules needing explicit declaration.
2. **Reflection and encapsulation:** deep access into internal classes, `--add-opens`, `--add-exports`, and illegal-access warnings.
3. **Compiler and bytecode:** source/target levels, `--release`, class file versions, annotation processors, and bytecode-processing libraries.
4. **JVM and tools:** removed options, GC changes, unified logging, diagnostic commands, and monitoring.
5. **Security and networking:** TLS, cipher suites, providers, truststores, certificates, and disabled algorithms.
6. **Data and defaults:** charset, locale, timezone, date/time formatting, serialization, and encoding.
7. **Frameworks and dependencies:** Spring versions, ORMs, JDBC drivers, HTTP clients, logging, agents, plugins, and native libraries.

Not every application is affected by every area. Use your dependency inventory, configuration, and business flows to choose which topics to read deeply.

### 4.3. Read Each Change with the Same Set of Questions

For each potentially relevant item, record:

- **What changed:** what exactly changed?
- **Since when:** in which version did the change appear, and did it evolve further in later versions?
- **Who is affected:** which APIs, modules, tools, OSes, or application patterns are impacted?
- **Default or opt-in:** does the change apply automatically, or only when enabling a feature/configuration?
- **Failure mode:** will the app fail at compile time, startup, link time, or only in a specific runtime flow?
- **Migration action:** do we need to edit source code, upgrade dependencies, adjust JVM options, update configs, or simply add tests?
- **Evidence:** which command, test, log, or environment verifies it?

For example, an entry stating an API was removed should split into two questions: does source code import that API, and do shipped binaries reference that class? Checking compilation of a single module while an old plugin loads dynamically at runtime can still miss the error.

### 4.4. Do Not Copy Guide Snippets as Automatic Solutions

A migration guide may suggest temporary options such as opening a module package or re-enabling an algorithm. Read the conditions and scope of the guidance before applying it.

For example, adding `--add-opens` can let an older library continue accessing a private field in the short term. However, it does not replace upgrading the library or migrating to a public API. Similarly, re-enabling an older TLS algorithm may restore connectivity while lowering security posture.

Every measure requires a rationale, scope, owner, and removal criteria if it is only a transitional workaround.

## 5. How to Read and Evaluate Relevant JEPs

JEPs provide deep insight into major OpenJDK changes. However, the JEP list is long; you do not need to read every JEP in a release. Focus on JEPs directly tied to the APIs, runtime, security, tools, or assumptions your application relies on.

### 5.1. Identify the JEP and Its Status

Each JEP has an ID and dedicated specification page, e.g., `JEP 400`. Upon opening a JEP, check first:

- JEP title and number.
- Owner and Contributors, if listed.
- Current Status.
- Target Release (expected or targeted JDK version).
- Links to issues, specifications, implementations, or related documents.

Status is critical. A proposal in Draft or Candidate state cannot be treated as a guaranteed feature in the target JDK. A targeted JEP still requires tracking progress; even an integrated JEP must be cross-checked against release notes and the actual build to confirm exactly what shipped.

A JEP may be revised during development. Record the document revision and status at the time of research, especially when upgrade planning spans several months.

### 5.2. Read by JEP Structure

A JEP typically includes these key sections:

| Section | How to Read | Value for Migration |
|---|---|---|
| Summary | Read to grasp the change in a few sentences | Determine whether the JEP is relevant to your application. |
| Motivation | Find the problem the JEP aims to solve | Understand the rationale and potential legacy issues in your app. |
| Goals | Identify primary objectives | Know what is guaranteed within the design scope. |
| Non-Goals | Carefully read what is not addressed | Avoid expecting the new feature to cover out-of-scope cases. |
| Description | Read workflows, APIs, and new structures | Spot integration points or altered assumptions. |
| Alternatives | Review alternatives considered | Understand trade-offs and design rationale. |
| Risks and Assumptions | Find risks, limits, and assumptions | Turn risks into concrete test items. |
| Compatibility | Review source, binary, and behavioral impacts | Spot areas that can break older applications. |
| Testing | Check how the feature was verified | Reference the kinds of evidence to collect in your own system. |

Not every JEP contains all headings or follows the exact same layout. If a section is missing, search for equivalent details in the description, linked issues, or implementation docs.

### 5.3. Distinguish a JEP from a Released Feature

A JEP describes an enhancement in OpenJDK's development process; a JEP alone does not guarantee every JDK build on the market packages or supports it identically.

When reading a JEP, distinguish:

- A JEP currently proposed or under discussion.
- A JEP targeted to a release.
- A JEP integrated into a development build's source tree.
- A feature actually present in the JDK build your application will use.
- Whether the feature is finalized or still in preview/incubator form.

For preview or incubator features, check enablement flags, compile/runtime requirements, and the likelihood of changes in subsequent versions. Do not rely on an experimental feature as a stable contract unless the product accepts that risk.

### 5.4. Illustrative JEPs Commonly Worth Reviewing During Migration

These examples demonstrate how to connect JEPs to practical application questions. This is not an exhaustive list; select JEPs based on your upgrade path and specific dependencies.

**JEP 403 – Strongly Encapsulate JDK Internals (JDK 17).** This JEP strengthens encapsulation of JDK internal APIs. If frameworks, libraries, or application code use deep reflection into internal packages, check for access warnings and failures. The long-term fix is migrating to public APIs or upgrading libraries; module-opening options should only be strictly scoped measures.

**JEP 400 – UTF-8 by Default (JDK 18).** This JEP standardizes UTF-8 as the default charset across standard environments. If the application reads or writes data relying on the default charset, inspect file formats, protocols, and data produced by legacy systems. The sustainable fix is specifying encodings explicitly in data contracts.

**JEP 444 – Virtual Threads (JDK 21).** This JEP finalizes virtual threads as a standard feature. If the application chooses to adopt virtual threads, evaluate the concurrency model, resource limits, libraries using thread-locals or native calls, and load characteristics. Upgrading to JDK 21 does not automatically switch an application to virtual threads; it is a design choice requiring dedicated testing.

**JEP 451 – Prepare to Disallow the Dynamic Loading of Agents (JDK 21).** This JEP prepares to restrict dynamic loading of Java agents in the future and emits warnings in certain cases in JDK 21. If APM tools, profilers, test runners, or frameworks attach agents after JVM startup, determine how agents load and inspect warnings. Startup agent flags and dynamic attach policies may carry different operational requirements.

When referencing these examples, open the JEP page to review goals, scope, and current status; then check the release notes of your exact JDK build. A JEP name and short summary do not substitute for verifying real runtime configuration.

## 6. Connecting the Three Documentation Sources into a Research Workflow

Reading each source in isolation generates many notes that are hard to turn into technical decisions. Connect them into a sequence: identify changes in release notes, understand impact and mitigations in the migration guide, and read JEPs when deeper design or risk explanations are needed.

```text
Identify source JDK and target JDK
              |
              v
Release notes for the exact vendor/build
              |
              v
Flag changes, known issues, security,
APIs, JVM options, and default behaviors
              |
              v
Migration guide along the upgrade path
              |
              v
Identify affected applications/dependencies
              |
              v
Relevant JEPs to understand design, scope,
status, and compatibility risks
              |
              v
Plan mitigations, evidence, and tests
              |
              v
Test on the target environment
```

### Step 1: Build a Source List Along the Upgrade Path

For example, when moving from Java 11 to Java 21, list the release notes and migration guides for the relevant version milestones, alongside documentation from your active vendor. For each milestone, record the version number and official URL.

Do not read every item with equal depth. Start with the table of contents and keywords, then read in full the entries connected to existing dependencies, configurations, or business flows.

### Step 2: Create a Change and Impact Table

Each relevant change found should be logged as a trackable row:

| Field | What to Record |
|---|---|
| Version | Version or update introducing the change. |
| Source | Release notes, migration guide, or JEP; include link and section/paragraph. |
| Change | Concise description of what changed. |
| Affected area | Module, API, framework, JVM option, security, data, or environment. |
| Application usage | Evidence that the application uses the affected part. |
| Risk | Potential compile, link, runtime, data, security, or performance failure. |
| Action | Edit code, upgrade dependency, change config, update image, or add tests. |
| Verification | Command, test, log, or metric used to confirm. |
| Status | Uninvestigated, confirmed unaffected, fix needed, fixed, or verified. |

Example of how to log an entry:

| Field | Illustrative Example |
|---|---|
| Version | JDK 18 |
| Source | JEP 400 and corresponding migration guide |
| Change | UTF-8 becomes the default charset in standard environments. |
| Affected area | CSV file reading/writing and data imports from legacy systems. |
| Application usage | A code snippet calls `new String(bytes)` without specifying a charset. |
| Risk | Accented characters may decode differently from the source data. |
| Action | Identify the file encoding and pass the charset explicitly. |
| Verification | Test sample files containing Vietnamese characters on old and new JDKs. |
| Status | Confirmed fix needed; pending testing. |

This illustrates the logging method, not a claim that every application fails when upgrading to JDK 18. Mark impact only when a dependency path is found inside your actual application.

### Step 3: Link Changes to Code and Dependencies

Search for packages, classes, methods, JVM options, or configs mentioned in the documentation. Cross-reference against source code, dependency trees, Dockerfiles, pipelines, and startup commands.

A change is deemed relevant only when evidence exists such as:

- Source code imports or calls the altered API.
- A direct or transitive dependency uses that API.
- A framework uses reflection or internal access.
- Deployment scripts pass the affected JVM option.
- Business flows connect to endpoints or process data subject to the change.
- Observability tools or agents rely on the changed runtime mechanism.

If no evidence is found yet, mark it "undetermined" instead of concluding "no impact". Runtime inspection may be needed for plugins or configs loaded dynamically that source search cannot detect.

### Step 4: Deep-Read JEPs When Changes Have Broad Impact

If release notes or a migration guide cite a JEP, open the JEP to understand its design. If no direct link exists, search OpenJDK JEPs by topic or feature number.

Read Compatibility, Risks, Non-Goals, and implementation links to confirm what actually changed. Record the status and target release so an unreleased proposal is not treated as current behavior in the plan.

### Step 5: Convert Notes into a Test Plan

Every risk must lead to at least one verification check. Examples:

| Finding from Documentation | Check to Perform |
|---|---|
| Removed API | Compile all consumers; test old artifacts if independently deployed binaries remain. |
| Encapsulated internal access | Run integration tests on the target JDK and inspect reflection warnings. |
| Changed JVM option | Start the application with the exact production command line. |
| Changed TLS policy | Test handshakes against real endpoints and the target truststore. |
| Changed default charset | Read/write sample files with explicitly defined encodings. |
| GC or memory changes | Run representative load and compare heap, pauses, and p95/p99. |
| JEP introduces new feature | Test only if the application actively uses or enables that feature. |

Once tests pass, update the status in the change table along with traceable logs, test results, or metrics. Do not mark an item complete merely because you read the docs or edited code.

## 7. Common Mistakes When Reading Upgrade Documentation

### Reading Only the Target Version's Release Notes

If an application jumps multiple major versions, a change may have appeared in an intermediate release. Reading only the target version's page easily misses an earlier change that still impacts the upgrade path.

### Using Documentation from a Different Vendor

An Oracle JDK guide can help explain general platform changes, yet may not accurately describe packaging, patches, platform support, or distribution-specific bugs in Temurin, Corretto, or another distribution. Use your actual vendor's documentation as the authoritative deployment reference.

### Treating a JEP as a Guarantee of Available Features

A Draft, Candidate, or unintegrated JEP does not prove a feature exists in your JDK build. Always check status, target release, release notes, and preview/incubator status.

### Reading Only New Features While Ignoring Removals

For migrations, Removed, Deprecated, Security, Compatibility, and Known Issues sections are usually more directly valuable than new feature lists. Specifically look for default changes and removed JVM options.

### Logging Changes Without Tracing Dependency Paths

A JEP may matter greatly to the broader ecosystem yet be irrelevant to a specific application. Conversely, a minor change in TLS or charset may directly hit a critical business flow. Use code, dependencies, configs, and testing to establish impact.

### Treating the Migration Guide as a Mandatory Checklist to Apply Wholesale

A guide may present multiple mitigations for different scenarios. Do not add every mentioned JVM option or dependency to your application. Pick solutions based on verified root cause, required scope, and security/operational policies.

## 8. Which Official Documentation Sources Should You Start From?

Prioritize sources published by the OpenJDK project or the vendor of your running JDK. Useful starting points include:

- **OpenJDK JEP Index:** [https://openjdk.org/jeps/0](https://openjdk.org/jeps/0) — look up JEPs, numbers, statuses, and links to individual enhancement specifications.
- **Oracle Java SE 21 Documentation:** [https://docs.oracle.com/en/java/javase/21/](https://docs.oracle.com/en/java/javase/21/) — entry point for the Migration Guide, tools, specifications, and runtime docs for Java 21.
- **Oracle Java SE 21 Release Notes:** [https://www.oracle.com/java/technologies/javase/21all-relnotes.html](https://www.oracle.com/java/technologies/javase/21all-relnotes.html) — update-by-update release notes for Oracle JDK 21.
- **OpenJDK JDK Project Pages:** [https://openjdk.org/projects/](https://openjdk.org/projects/) — track OpenJDK projects, releases, and development updates.

If production uses another distribution, locate that vendor's official release notes, security advisories, support matrix, and migration documentation. The URLs above are illustrative starting points for Java 21; when upgrading to another version, substitute the docs for your exact target version.

## 9. Pre-Upgrade Research Checklist

Before concluding documentation research is complete, cross-check the following items:

- [ ] Recorded the exact source and target JDKs, vendor, build, and runtime environment.
- [ ] Identified intermediate versions requiring review.
- [ ] Read release notes for the exact target vendor and update level.
- [ ] Searched Removed, Deprecated, Compatibility, Security, JVM, Tools, and Known Issues sections.
- [ ] Read the migration guide across the full upgrade span, not just from the immediately preceding version.
- [ ] Found relevant JEPs and confirmed status, target release, and preview/incubator flags if applicable.
- [ ] Classified each change as new feature, default change, deprecated, removed, bug fix, or known issue.
- [ ] Linked each relevant change to specific source code, dependencies, configs, or business flows.
- [ ] Documented the migration action and required test evidence.
- [ ] Saved source URLs and document versions so others can re-verify them.

This checklist structures the research process; it does not replace testing. An item should be checked off only with supporting evidence such as documentation links, dependency trees, compile results, integration tests, or runtime metrics.

## 10. Conclusion

Release notes, migration guides, and JEPs provide three complementary perspectives for a JDK upgrade. Release notes confirm the contents of a specific release; migration guides explain impacts and adaptation strategies; JEPs clarify the goals, design, scope, and risks of an OpenJDK enhancement.

An effective workflow begins by identifying the exact source JDK, target JDK, vendor, and build. Next, read release notes across each version milestone, use the migration guide to locate potential application-breaking areas, and open relevant JEPs to understand critical changes deeply. Finally, link every finding to real code, dependencies, and configuration, turn them into repeatable tests, and store the evidence.

Reading documentation only uncovers potential risks. Only once you determine whether the application uses the changed components and verify on the target environment does the team have solid grounds to decide on the upgrade approach and deployment readiness.
