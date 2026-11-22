# Publishing the minimum Java version and end-of-support timeline for older versions

## 1. Context of publishing a Java support policy

During **Java Advance Compatibility Migration**, a library or application may need to upgrade the JDK to use new APIs, meet security requirements, upgrade frameworks, switch build tools, or simplify operations. However, product consumers cannot always switch JDKs at the same time.

A Java library with a published API may be used by many groups: long-compiled client applications, independently distributed plugins, services running in separate containers, batch jobs, or partner systems. When a product raises its minimum Java level without notice, users may only discover the problem after deployment, through startup failures, class linkage errors, or incompatible dependencies.

Therefore, publishing the **minimum Java version** and the **end-of-support date for older Java versions** is part of API evolution, not merely a build environment change announcement. The announcement must help consumers know:

- From which product version onward is what minimum Java required?
- Which Java versions are tested, officially supported, and still receiving patches?
- Which product versions still run on older Java during the transition period?
- On what date does regular support end, and on what date does patch publishing for the legacy line end completely?
- What do users need to do, by what milestones, and where can they find the migration documentation?
- What is the expected behavior if they continue running on an unsupported JDK?

A short statement like “Java 21 is now supported” is not sufficient, because it fails to clarify whether Java 17 is still supported, whether the runtime needs Java 21 or only the build needs Java 21, and until what date patches for the legacy product branch will be maintained.

## 2. Concepts that must be distinguished

### 2.1. Minimum required Java version

The **minimum required Java version** is the lowest Java version that a product release requires within the published scope.

For a Java library, this is usually the minimum runtime level of applications using the library and may be tied to the platform APIs the library uses. For a deployed application, this may be the runtime needed to launch the artifact or the minimum Java base image that deployment must provide.

Illustrative example:

> Library 3.x requires Java 21 or higher to run. Library 2.x continues to provide releases compatible with Java 17 during the published support window.

The phrase “or higher” describes the minimum version requirement; it does not itself create a commitment that **every** future Java version is certified. Tested versions and the official support scope must be published separately.

### 2.2. Minimum supported vs. tested vs. recommended

| Term | Content | How to phrase in documentation |
|---|---|---|
| Minimum required Java | The lowest version that the release requires to run or be used. | “Minimum runtime: Java 21.” |
| Supported Java versions | Java versions covered by the support policy and eligible for bug fixes under published terms. | “Supported and tested: Java 21.” |
| Recommended Java | The Java version recommended for new deployments. | “Recommended deployment runtime: Java 21 with current security updates.” |
| Build JDK | The JDK running Maven, Gradle, plugins, and build steps. | “Build tool runs on JDK 21.” |
| Compiler toolchain | The JDK used to compile source code. | “Compile toolchain: JDK 21.” |
| Bytecode/API target | The bytecode and Java API level that the artifact is permitted to reference. | “Compile with --release 17 for the Java 17 compatible branch.” |
| End of regular support | Milestone ending regular bug fixes or technical support per policy. | “Java 17 maintenance support ends on the specified date.” |
| End of life / end of support | Milestone ending all remaining forms of support per official announcement. | “No further maintenance releases after this date.” |

The concepts above are related but not identical. A project can use JDK 21 to build a Java 17-compatible library using compiler --release 17. Conversely, building with JDK 17 does not prove the library has been tested across every distribution or every Java 17 execution environment.

### 2.3. Java version is not synonymous with product version

Two release timelines must be interpreted separately:

1. **Java/JDK version:** such as Java 17 or Java 21, along with vendor and patch level.
2. **Product version:** such as library 2.x or 3.x, with its own support policy and maintenance schedule.

When writing “discontinuing Java 17 support”, specify **which product version** it applies to. A 3.x release may require Java 21, while the 2.x branch still receives Java 17-compatible patches until an announced date.

Without distinguishing the two timelines, users may misunderstand that Java 17 ceases to exist or that every product in the organization drops Java 17 support on the same day.

## 3. Why is announcing the minimum Java version an API change?

From a library perspective, the minimum Java version is part of the conditions for consuming the artifact.

When raising the minimum:

- Class files may be generated with a bytecode version that older JVMs cannot read.
- Source code may use JDK APIs that exist only in newer Java releases.
- New dependencies and frameworks may have raised their minimum Java version.
- Plugins or runtime agents may require a different JDK than before.
- Some APIs may be removed or change behavior, forcing consumers to modify code or configuration.
- The transition may change module packaging, classpath, module path, and reflection behavior.

For shared libraries, this change can be a **breaking change** even if every public method keeps the exact same signature. Consumers on older Java cannot run the new artifact if bytecode or dependencies require newer Java.

For example, a class compiled for Java 21 has class-file major version 65, while a Java 17 JVM only supports class-file versions up to 61. Running that artifact on Java 17 can result in UnsupportedClassVersionError before the application can execute any business logic.

Do not compare only public API code to conclude that a JDK support change is backward compatible. The minimum environment required to run an artifact is a practical part of the release contract.

## 4. Determining minimum Java through technical evidence

Before announcing, distinguish the **desired level**, the **configured level**, and the **verified level**.

### 4.1. Inventorying constraints

An inventory should gather:

| Component | Key question | Evidence |
|---|---|---|
| Source code | Does the code use syntax/language features supported only in newer releases? | Compiler settings and building from source. |
| Java API | Does it call JDK APIs that do not yet exist in the proposed minimum Java version? | Compiling with --release and API analysis. |
| Class file | Which JVM version does the published bytecode target? | Compiler target and javap -verbose. |
| Direct dependencies | What minimum Java does each library require? | Release notes, metadata, class-file inspection, and tests. |
| Transitive dependencies | Does any library pull in JARs that only run on newer Java? | Dependency graph/runtime classpath. |
| Framework | Does the selected framework version require newer Java? | Compatibility matrix and release documentation. |
| Build tool / plugin | Which JDK do Gradle, Maven, plugins, and annotation processors use? | Wrapper, toolchain, and CI logs. |
| Runtime | Which Java does the host/container/application server actually execute? | java -version, image digest, process runtime. |
| Consumer | Which Java and library versions are client applications using? | Inventory, feedback, appropriate telemetry. |

If the library itself runs on Java 17 yet a runtime dependency mandates Java 21, the actual minimum of the combined product cannot be published as Java 17 without replacing the dependency or providing a compatible configuration.

### 4.2. Reading the bytecode target

You can use javap to view the major version of a class file:

~~~bash
javap -verbose -classpath my-library.jar com.example.LibraryEntry
~~~

In the output, look for major version. Common examples:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Inspecting a single class file is reference information, insufficient to prove the entire JAR is compatible; other classes and dependencies may have higher bytecode.

### 4.3. Do not merely lower the bytecode target

When using a modern javac, consider the --release option when needing to produce artifacts compatible with older Java. This option restricts language features, bytecode, and platform APIs available in the chosen release.

Example:

~~~bash
javac --release 17 -d out src/main/java/com/example/LibraryEntry.java
~~~

If you only lower the bytecode target while still compiling against APIs present only in a newer JDK, the code may compile successfully yet hit NoSuchMethodError or NoClassDefFoundError on the older runtime. --release reduces that risk within the scope of compiler-controlled platform APIs.

However, --release does not automatically verify third-party dependencies, reflection, native code, optional modules, service providers, or runtime behavior. The final verification step still requires running tests using the exact published minimum Java.

### 4.4. Minimum versions of applications and libraries can differ

Example:

~~~text
Library core     : minimum Java 17
CLI distribution : minimum Java 21
Server runtime   : minimum Java 21
Build pipeline   : JDK 21
~~~

This can be a valid configuration if the product publishes each artifact separately. If packaged together without clarification, consumers may mistakenly assume every artifact is Java 17 compatible.

Therefore, the policy must tie Java requirements to the exact artifact, module, or deployment target rather than a single generic label for the entire repository.

## 5. Designing a Java support policy

### 5.1. Defining the scope of responsibility

Before announcing an end-of-support date, the product team needs to decide the following scopes:

- Which product lines are supported on each Java release?
- Are all OpenJDK distributions supported or only a tested subset?
- Are the latest security patches within the same major release required?
- Which operating systems, CPU architectures, and container images fall within the support scope?
- Do patch/minor versions of the legacy line receive bug fixes, security fixes, or only best-effort support?
- On what date do new features stop, on what date do regular bug fixes stop, and on what date does all support stop?
- Are there commercial exceptions or extended support contracts?

Do not promise “supports Java 17, 21, and every new JDK” if CI only tests Java 21. Support definitions must come with concrete commitments regarding testing, bug handling, and security updates.

### 5.2. Illustrative support matrix

The following table is a **hypothetical scenario**, not the actual support schedule of any project:

| Product line | Minimum Java | Java validated in CI | Support status | Change policy |
|---|---:|---|---|---|
| Library 2.x | 17 | 17 and 21 | Maintenance until published deadline | Receives only policy-eligible bug fixes; no new APIs requiring Java 21 are added. |
| Library 3.x | 21 | 21 | Active | May use Java 21 and dependencies/frameworks requiring that Java level. |
| Library 1.x | Per prior release notice | No longer in current matrix | End of life per separate policy | No commitment to publish new patches. |

Note:

- “Minimum 17” does not automatically mean every Java 18, 19, 20, or future Java release has been tested.
- “Supported 17 and 21” indicates the two levels the organization commits to supporting within the matrix scope; other releases require separate interpretation.
- A JDK vendor or update version can affect reliability. Specify distribution support scope when necessary.
- Different product versions can support different Java versions over a period of time.

### 5.3. Support tiers

A product may use these tiers:

**Active support:** receives scheduled development, functional support, bug fixes, and patches.

**Maintenance support:** continues receiving a subset of fixes, usually focused on critical bugs and security; no new features promised.

**Extended support (if applicable):** conditional support for consumers needing more time. Scope, timeline milestones, and enrollment steps must be published rather than assuming every customer receives it by default.

**End of life (EOL):** no further releases or support within the defined scope. EOL does not make old artifacts immediately stop running, but the organization no longer commits to testing, supporting, or publishing patches for them.

The labels Active, Maintenance, Extended, and EOL must have official organizational definitions. Do not use the same phrase “end of support” to refer to both halting new features and halting all patches.

## 6. Establishing announcement and end-of-support milestones

A good policy does not just state an end date; it must give consumers enough information and transition time.

### 6.1. Timeline milestones

| Milestone | Meaning | Content that should be announced |
|---|---|---|
| Announcement date | Announcing the direction to raise minimum Java. | Old/new Java versions, affected product lines, rationale, and contact point. |
| Deprecation / transition period | Period recommending migration and maintaining old API/line. | Migration guide, test matrix, compatibility points needing fixes. |
| Preview / release candidate | Allowing consumers to try builds requiring new Java before GA. | How to download preview, test conditions, and feedback channel. |
| GA of new major | Releasing the new product line with the new minimum Java level. | Release notes, requirements, breaking changes, and rollback. |
| End of regular maintenance | Stopping regular maintenance for the branch supporting older Java. | Types of fixes still accepted, if any, and final deadline. |
| EOL of old line | Stopping remaining support commitments for the legacy line. | Patch policy, security, archived docs, and upgrade options. |

### 6.2. Example announcement with specific dates

Suppose a library currently has a 2.x line requiring Java 17 and wants to release a 3.x line requiring Java 21. A hypothetical schedule could be:

| Date (illustrative) | Event |
|---|---|
| 01/02/2027 | Plan announced: Library 3.x will require Java 21; Library 2.x continues supporting Java 17 through its deadline. |
| 01/05/2027 | Library 3.x preview released and testing phase opened for consumers. |
| 01/08/2027 | Library 3.0 GA with minimum runtime Java 21. |
| 31/12/2027 | Final day of maintenance support for Library 2.x under the hypothetical policy. |
| 01/01/2028 | Library 2.x transitions to EOL; no promise of new patches. |

**This is an illustrative schedule to explain how to publish; it is not an actual support schedule for Java, any JDK vendor, or any product.** In practice, dates must be approved by the product owner, considering release cycles, security requirements, testing time, and consumer contracts.

Announcements should use specific dates with a timezone if the milestone has operational effect. Avoid “next month”, “next quarter”, or “ending support soon” in official release notes because those phrases become ambiguous over time.

### 6.3. Do not confuse JDK vendor EOL with product EOL

JDK vendors have their own maintenance lifecycles per distribution and support tier. A library-developing organization may drop support for a Java release earlier or later than a specific JDK vendor's maintenance milestone, depending on its own policies and obligations.

Therefore, do not write “Java 17 EOL on date X” merely because **your own product** stops supporting Java 17 on that date. Write clearly:

> “Starting on date X, our Library 2.x branch ceases receiving maintenance patches for the Java 17 environment.”

If citing a vendor's JDK support schedule, state the vendor, distribution, support model, and source documentation current at the time of publication.

## 7. Linking Java policy with product versioning

Raising minimum Java can break a consumer's ability to run even if the public API stays unchanged. In libraries published under Semantic Versioning, this is typically a change worth considering for a major release.

Example:

~~~text
2.8.x: minimum Java 17, maintenance branch
3.0.0: minimum Java 21, new active branch
~~~

Note that SemVer is a convention for communicating compatibility levels, not something that automatically creates binary compatibility. If a consumer on Java 17 loads 3.0.0, the “3.0.0” label does not enable a Java 17 JVM to read Java 21 bytecode.

A release policy must distinguish:

- Major release: changes capable of breaking the published contract, including required runtime level when applicable.
- Minor release: new features while preserving the compatibility level committed to by the branch.
- Patch release: bug/security fixes without arbitrarily raising minimum Java inside a branch declared compatible.

Not every project must use SemVer. Even if choosing a different versioning model, the principle is that **every artifact must have clear Java requirements and users must recognize breaking changes before upgrading versions**.

### 7.1. Supporting multiple branches simultaneously

A project may maintain two branches during a transition period:

~~~text
release/2.x  ── Java 17 baseline ── bugfix/security maintenance ── EOL
release/3.x  ── Java 21 baseline ── feature + maintenance ────────>
~~~

With this model, assign owners and backport criteria. If a security patch is fixed in 3.x while 2.x is still supported, the team must evaluate backport feasibility without introducing Java 21 APIs into Java 17 code.

Backports may need different implementations because Java APIs, frameworks, or dependencies differ across the two branches. Do not blindly cherry-pick and only verify the build on the newer JDK.

### 7.2. When maintaining two branches is not possible

If resources are insufficient, you may decide to maintain only one branch, but the notice period must reflect the risk to consumers. Options may include:

- Extending the lead time before the EOL date.
- Providing a compatible transition release so consumers reduce upgrade steps.
- Publishing a migration guide and configuration verification tools.
- Allowing conditional, scoped support with specific owners.
- Explicitly announcing the possibility that security bugs are no longer patched on the old branch.

Do not uphold a support promise that the team lacks capacity to fulfill, especially for security incidents and production operations.

## 8. Configuring builds to reflect the published Java level

Paper policy must align with artifact builds and CI.

### 8.1. Gradle: compile JDK and release target

Suppose a library continues supporting the Java 17 runtime while the build tool runs on JDK 21. With Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Meaning:

- Gradle locates the Java 21 compiler per toolchain configuration.
- --release 17 restricts language features, class-file target, and JDK APIs for the compiled code.
- This is **not sufficient** to assert that all runtime dependencies are Java 17 compatible.

In the 3.x branch requiring Java 21, the release target can be raised to 21:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
~~~

This is an example for the Java plugin and corresponding compilation tasks. Mixed Kotlin/Scala/Groovy projects or code generated via annotation processors may require additional configuration and checks for each artifact type.

### 8.2. Maven: compiler release

With Maven, one way to declare the release level:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

When the minimum Java policy switches to 21 for the new branch, the corresponding configuration can be:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

The compiler plugin and JDK/toolchain must support the chosen release. Maven launched with one JDK does not necessarily use that same JDK to compile if the project uses Maven Toolchains or compiler forks.

Note that you should not use a newer build JDK and assume the older runtime is always compatible simply because source/target are set to an older value. The release level and actual dependencies are the details that must be verified.

### 8.3. Compiler release is a necessary condition, not a sufficient condition

Add verification for:

1. Class files in the artifact, not just the main class.
2. Runtime dependencies and fat/uber JAR packaging.
3. Auto-generated code and code in separately built modules.
4. Classes inside multi-release JARs if used.
5. Reflection, native bindings, service loaders, and framework integration.
6. Runtime testing on the lowest published Java version.

A multi-release JAR can contain version-specific classes under META-INF/versions. When using this technique, the base portion must obey the minimum Java level, and behavior on each Java release must be tested. That is a conditional mechanism, not an automatic way to support every JDK.

## 9. Designing a CI matrix for the support policy

The minimum Java version is only trustworthy when verified in a reproducible pipeline.

### 9.1. Levels that should be checked

For a library publishing support for Java 17 and Java 21, CI can separate:

- Building the artifact with release target 17.
- Running unit/integration tests on Java 17.
- Running unit/integration tests on Java 21.
- Testing with supported dependency/framework versions.
- Binary compatibility tests against already-released libraries, if backward binary support for old clients is promised.

On the 3.x branch requiring Java 21, CI at minimum needs to run on Java 21. If announcing support for additional Java releases, include those releases in the matrix with appropriate testing levels and publish any differing limitations.

### 9.2. General conceptual CI example

~~~yaml
strategy:
  matrix:
    java: ["17", "21"]

steps:
  - name: Select Java
    # Use the JDK setup step appropriate for the CI platform.
    # Distribution and version come from the matrix.
  - name: Record runtime version
    run: java -version
  - name: Run tests
    run: ./gradlew test
~~~

This is an **illustrative skeleton**, not a complete workflow runnable verbatim. Real CI requires adding source checkout, concrete JDK setup steps, wrapper executable permissions, appropriate caching, and OS-specific execution conditions.

What matters is that the java -version command and the JVM executing tests reflect the Java of the matrix cell. With Gradle, if test tasks use a toolchain different from the runner JDK, verify the actual launcher. Same with Maven Surefire/Failsafe when fork or toolchain configurations exist.

### 9.3. Verifying usability from consumers

Besides the library's internal tests, create a simple client fixture:

1. Build the library with the current release configuration.
2. Include the artifact in an independent client application.
3. Compile and run the client application with the minimum Java version.
4. Exercise published API paths and verify behavior.
5. If the migration commits to binary compatibility, run the old client binary without recompiling.

If everything is only built and tested with JDK 21, Java 17 compatibility bugs can be missed. A release target of 17 also does not prove app servers, containers, and dependencies operate on JDK 17.

### 9.4. Early error tracking

Some common signals:

| Symptom | Possible cause | Resolution direction |
|---|---|---|
| UnsupportedClassVersionError | Artifact or dependency compiled for a newer Java than runtime. | Check major version, runtime JDK, and built release level. |
| NoSuchMethodError / NoClassDefFoundError | Dependency version skew or calling an API absent in runtime. | Inspect runtime classpath, dependency tree, and API target. |
| InaccessibleObjectException | Reflection restricted by module/encapsulation boundaries. | Upgrade dependencies/frameworks and verify appropriate migration paths. |
| Tests fail only on minimum JDK | New APIs, differing behavior, incompatible agents, or native dependencies. | Re-run on the minimum environment, isolate the source of difference. |
| Works locally, fails in production | Deployment image/runtime differs from tested JDK. | Record exact image digest, java -version, and execution command. |

These errors are investigation hints, not the sole diagnosis. Inspect actual stack traces and artifacts before concluding.

## 10. Publishing information where consumers can easily find it

The minimum Java policy must have one authoritative source and be repeated consistently where consumers make upgrade decisions.

### 10.1. README or System Requirements page

There should be a prominent section:

~~~text
System requirements

Product 3.x:
  Minimum Java runtime: 21
  Java versions validated in CI: 21
  Recommended: current security-patched Java 21 distribution

Product 2.x:
  Minimum Java runtime: 17
  Java versions validated in CI: 17 and 21
  Maintenance support ends: 31 Dec 2027 (illustrative only)
  EOL: 01 Jan 2028 (illustrative only)
~~~

Dates in the example are illustrative data only. A real README needs approved dates and scope, plus links to the migration guide.

### 10.2. Release notes and changelog

Place breaking requirements right at the top of release notes, not buried inside a list of changes:

> **Breaking requirement:** Product 3.0 requires Java 21 at runtime. Consumers running on Java 17 must remain on the supported 2.x line until they can migrate. See the support matrix and migration guide for dates and steps.

Also record the rationale for raising the minimum level, the features/dependencies driving the change, and notable constraints such as frameworks, database drivers, or container images.

### 10.3. Dependency metadata and distribution ecosystem

For some ecosystems, artifact metadata or dependency resolution mechanisms can help toolchains recognize compatibility requirements. However, do not assume JAR/Maven POM metadata always has standard fields checked by every client to prevent using the wrong Java release.

Some manifest information describes the JDK that built the artifact, rather than necessarily the minimum runtime requirement. Therefore, the support matrix documentation and testing on the minimum JDK remain the commitments that must be maintained.

If internal rules exist to block incompatible dependencies, document the mechanism and tool scope. Do not claim “the build tool automatically blocks older Java” if the resolver actually still downloads the JAR and only fails at runtime.

### 10.4. Channels that must stay synchronized

- README / system requirements page.
- Compatibility matrix and support policy.
- Release notes, changelog, and major version announcements.
- Migration guide / upgrade guide.
- Docker image, Helm chart, or deployment template documentation.
- SDK/client documentation and artifact download pages.
- Issue trackers, notification channels for integration teams, and relevant partners.

Every channel should point back to one authoritative source to avoid having documentation say “Java 17 supported” when recent release notes have already switched to “minimum Java 21”.

## 11. Guidance for consumers before the end-of-support date

Notices are only useful if users know what concrete actions they must take.

### 11.1. Inventorying actual runtimes

Consumers need to identify:

- Java versions in terminals, IDEs, CI runners, build containers, and deployment runtimes.
- Current base images and the JDK/JRE actually used to run processes.
- Library/framework versions and transitive dependency lists.
- Separately deployed batch jobs/plugins or services.
- Change windows and permissions to upgrade JDKs in production environments.

Do not rely solely on JAVA_HOME on developer machines to conclude production satisfies the new Java level.

### 11.2. Trial upgrades in isolated environments

A workflow for consumers could be:

1. Run the current application on the target Java version, when the current product supports it.
2. Upgrade required accompanying dependencies and frameworks.
3. Recompile if the new API has source breaking changes.
4. Run unit tests, integration tests, regression tests, and data tests.
5. Check TLS, locale, charset, timezone, reflection, serialization, and performance.
6. Upgrade images/containers/CI using the exact tested configuration.
7. Deploy canary or staged rollouts, monitoring errors and latency.
8. Maintain a rollback plan aligned with schema and data changes.

Upgrading the build JDK and runtime can be split into separate steps if release levels and dependencies permit. Verify each step rather than upgrading everything at once without baselines.

### 11.3. Consumers unable to upgrade yet

If a system still depends on older Java due to frameworks, vendor software, or infrastructure constraints, consumers need guidance on:

- Which product branch still under maintenance to keep using.
- Which patches continue to be provided and until when.
- How to report bugs/security issues during the transition period.
- Whether extended support, adapters, or internal LTS versions exist, if policy allows.
- What operational and security risks must be accepted past the EOL deadline.

Do not merely write “upgrade immediately to the new Java” without clarifying valid options during the transition window, especially for systems with long release cycles.

## 12. Official announcement templates

Below is an **illustrative content template** to adapt to actual schedules and versions.

### Minimum Java upgrade notice

~~~markdown
# Notice: Java baseline change in Product 3.0

Starting with Product 3.0, the minimum runtime requirement is Java 21.
Product 2.x remains the supported maintenance line for Java 17 until
31 December 2027. Product 2.x reaches EOL on 1 January 2028.

Impact:
- Applications running Product 3.0 on Java 17 are not supported.
- Consumers using Java 17 should continue on an eligible Product 2.x
  maintenance release until their migration is ready.
- Applications upgrading to Product 3.0 should validate runtime,
  dependencies, framework and deployment images on Java 21.

Action required:
1. Inventory Java versions in developer, CI and runtime environments.
2. Run the migration test matrix on Java 21.
3. Update build toolchains and deployment images.
4. Upgrade Product dependencies and verify API compatibility.
5. Complete rollout before the published maintenance EOL.

See:
- Compatibility matrix
- Migration guide from 2.x to 3.x
- Release notes for Product 3.0
- Support contact / issue tracker

Dates above are illustrative; use approved product dates when publishing.
~~~

In a real environment, this can be written in Vietnamese and `Product` replaced with the project name. What matters is that the heading, impact, actions, timeline milestones, and documentation links are all present.

### 12.1. Notice of EOL date change

If an EOL milestone must change, do not merely edit a date silently in the README.

Announce:

- Old milestone and new milestone.
- Affected branches and Java releases.
- Reason for change and support tier during the extended/shortened period.
- Which consumers need to act earlier.
- Publication date and policy approver.

If the EOL date is shortened, communication must account for consumer preparation time and signed commitments. Do not use schedule changes as an indirect way to force upgrades without a risk mitigation plan.

## 13. Exceptions and security risk management

In enterprises, some applications cannot upgrade the JDK before the deadline due to third-party software dependencies or strictly governed change cycles. Exceptions need clear boundaries and accountability.

An exception record should include:

| Field | Content |
|---|---|
| Consumer / workload | Service or application requesting to remain on legacy Java. |
| Current version | Product version, Java version, JDK distribution, and patch level. |
| Upgrade blocker | Framework, vendor SDK, operating system, infrastructure, or other constraint. |
| Support scope | Security fixes, critical bugfixes, best effort, or unsupported. |
| Owner | Team responsible for migration and approving the exception. |
| Exception expiry | Expiration date, non-auto-renewing. |
| Mitigations | Segmentation, monitoring, privilege restriction, connection controls, or other suitable measures. |
| Exit plan | Steps to remove blocking dependencies, upgrade the JDK, and re-validate. |

An exception cannot turn an out-of-patch runtime into a secure runtime through an approval document alone. Security support from the JDK vendor and operational safeguards must be evaluated separately.

### 13.1. Security and support costs

When deciding to maintain legacy Java support, the product team must assess:

- Ability to receive security updates for the runtime and dependencies.
- Backport effort when the new branch uses APIs/frameworks absent in legacy Java.
- Ability to re-run CI, build reproducibility, and testing on the legacy runtime.
- Security or operational risks of continuing to ship patches for a less-tested platform.
- Customer commitments and compliance requirements.

An EOL policy should reflect real risks and resources, not merely the technical preferences of the development team.

## 14. Managing rollout and rollback when raising the Java baseline

Announcing a new requirement must go hand in hand with safe deployment capability.

### 14.1. Pre-deployment checks

Before releasing the build requiring the new Java:

1. Confirm the artifact was built with the exact release target and dependency graph.
2. Run tests on the minimum Java of the new product line.
3. Inspect Docker base images or host-provisioned runtimes.
4. Check startup flags, GC, agents, native libraries, TLS, and reflection.
5. Evaluate data and protocol compatibility with services not yet upgraded.
6. Prepare rollback at the artifact/image level, not just changing the JAVA_HOME variable.
7. Verify documentation and release notes clearly state the breaking requirement.

### 14.2. Do not assume runtime rollback equals rolling back the entire change

Rolling back to an old artifact may fail if database schemas, events, or data have already changed. Conversely, merely re-running an old image on the new JDK may also be unsupported.

Determine in advance which combinations of artifact + JDK + dependencies + configuration are permitted on rollback. If blue/green or canary needs to be supported, services running on two Java releases must communicate over compatible data contracts throughout the transition period.

### 14.3. Measuring migration progress

The product team should track:

- Percentage of consumers upgraded to the new minimum Java.
- Percentage of production workloads still running on legacy Java, when valid measurement sources exist.
- Number of consumers still depending on maintenance product versions.
- CI results on minimum Java and supported Java releases.
- Number of framework/dependency/native-library blockers.
- Active exceptions and completion deadlines for each case.
- Number of post-rollout errors related to JDK/dependencies.

Do not collect unnecessary personal information or configuration secrets. For externally distributed libraries, telemetry is often incomplete; combine consumer surveys, issue trackers, and integration team feedback rather than treating “no observed usage” as conclusive proof no customers remain.

## 15. Common communication mistakes

| Unsuitable practice | Risk | Better announcement approach |
|---|---|---|
| “Upgrading to Java 21.” | Unclear whether build JDK or runtime JDK, and from which product onward. | State minimum runtime, build requirements, and applicable product lines. |
| “Supports Java 17+.” | Easily misread as supporting all future Java releases. | State minimum required and the list of tested/supported Java releases. |
| “Java 17 ends support on date X.” | Confuses product policy with JDK vendor lifecycle. | Specify which product branch ends support for Java 17 on date X. |
| Stopping legacy branch patches immediately upon new GA. | Consumers have not upgraded yet; security and operational risks. | Announce maintenance window and EOL ahead of GA whenever possible. |
| Slipping runtime changes into a patch release silently. | Clients fail unexpectedly when updating dependencies. | Choose versioning and release notes reflecting the breaking requirement. |
| Setting only a low compiler target. | Dependencies may still use newer bytecode/APIs. | Inspect artifacts/dependencies and run tests on minimum JDK. |
| Testing only on the latest JDK. | Fails to catch regressions on the declared minimum Java. | Require minimum-runtime testing in CI. |
| README and changelog state different things. | Consumers do not know which source is accurate. | Keep the support matrix authoritative and synchronize channels. |
| Omitting timezone or effective date. | Ambiguity around support deadlines and rollout schedules. | Use exact dates, timezone if relevant, and describe support tiers. |
| Granting open-ended exceptions. | Legacy branches persist indefinitely. | Attach owner, deadline, support tier, mitigations, and exit plan. |

## 16. Documentation set accompanying every minimum Java upgrade

For a Java baseline change impacting consumers, the announcement package should include:

1. **Support matrix:** product version, minimum Java, tested releases, support status.
2. **Release notes:** breaking requirement and rationale for raising the Java level.
3. **Migration guide:** steps to upgrade JDK, dependencies, build tools, frameworks, and deployment.
4. **Lifecycle notice:** announcement date, GA date, maintenance end, and EOL of the legacy branch.
5. **Compatibility evidence:** build/test results on minimum Java, toolchain versions, and artifact identity.
6. **FAQ:** what consumers still on older Java must do and how long they can defer.
7. **Support route:** where to send questions, how to report bugs, and the exception request process.
8. **Ownership:** team accountable for updating schedules, responding, and handling policy changes.

A key requirement is that all documents point to the same policy without contradicting one another. If Java 17 support ends on the 2.x branch on an announced date, do not leave old documentation continuing to claim that branch is “fully supported” past the deadline.

## 17. Decision and publication workflow

A practical workflow can follow this sequence:

### Step 1 — Propose the new baseline

Clearly state why Java needs upgrading: new dependency/framework requirements, platform features, operational safety, maintenance cost, or technology standardization strategy. Record the target Java version and affected artifacts.

### Step 2 — Gather compatibility evidence

Verify source, bytecode, JDK APIs, dependencies, toolchains, CI, and runtimes. Determine whether Java must be raised for the entire product or if an older-Java-compatible artifact can be preserved.

### Step 3 — Assess consumers

Group consumers by current Java level, upgradeability, release cadence, and security requirements. Determine the number of affected systems and minimum transition duration.

### Step 4 — Choose versioning and support policy

Decide which product line carries the new baseline, which branch receives backports, maintenance end date, and EOL. Establish an exception policy if needed, with clear scope and owners.

### Step 5 — Approve timeline milestones

Evaluate CI operational capacity, support capacity, contracts, and consumer deployment schedules. Do not publish dates the team cannot meet.

### Step 6 — Publish the announcement

Update the support matrix, release notes, migration guide, and announcement channels. State exact versions, minimum runtime, supported/tested releases, and effective dates.

### Step 7 — Execute and support the transition

Release previews if needed, collect feedback, resolve blockers, and test on the target JDK. Track consumers remaining on the legacy branch and distribute patches per policy.

### Step 8 — Confirm end of support

At the published milestone, update legacy branch status, resolve exceptions, archive documentation appropriately, and remind consumers of residual risks. If schedules change, issue an official announcement instead of editing silently.

## 18. Conclusion

Publishing the minimum Java version and end-of-support timeline for older versions is a commitment to consumers regarding **artifact usability**, **support scope**, and **transition window**. Raising the baseline can break actual compatibility even when Java API signatures remain unchanged, because runtime, bytecode, dependencies, and frameworks are part of execution conditions.

A clear policy must distinguish required Java level, tested releases, build JDK, bytecode target, actively maintained product branches, and EOL dates. That policy must be verified via CI on minimum Java, reflected consistently across the support matrix, release notes, and migration guide, and accompanied by an announcement schedule, legacy branch support plan, and guidance for consumers not yet upgraded.

When this information is published ahead of time and tracked through the end of the transition period, teams can evolve APIs and the Java platform in a controlled manner, while consumers have solid grounds to plan upgrades, testing, deployments, and risk management.
