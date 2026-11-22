# Distinguishing Java SE Releases from JDK Distributions and Support Policies

When planning a Java upgrade, three separate questions must be answered: which Java SE platform version the system uses, which vendor's JDK distribution it runs, and until when that vendor commits to providing updates and support. These three pieces of information are related, yet not synonymous.

For example, two servers both report Java 21, while one runs Eclipse Temurin and the other runs Amazon Corretto. Both target the same Java SE platform version, but may differ in vendor, build release schedule, packaging, terms of use, supported platforms, and support duration. If you record only "upgraded to Java 21", the migration plan still lacks critical information for long-term operations and maintenance.

## 1. Java SE, the JDK, and JDK Distributions Are Three Distinct Concepts

### 1.1. Java SE Is the Platform and Specification

Java Platform, Standard Edition (Java SE) defines the standard Java platform that Java applications can rely upon. This scope includes the Java language, the Java Virtual Machine (JVM), standard libraries/APIs, and the relevant technical rules described in the corresponding specifications.

Versions such as Java SE 8, 11, 17, 21, or 25 are feature releases of the platform. Each feature release may add language syntax, APIs, JVM capabilities, and tools, while also removing or deprecating certain components under Java's evolution process.

Java SE answers the question: **which Java platform at the specification and standard API level is being used?** It does not by itself answer which vendor the system downloaded the installer from or how long a commercial support contract lasts.

### 1.2. The JDK Is the Development and Execution Toolkit

The Java Development Kit (JDK) is the toolkit used to develop, compile, test, package, and run Java applications. A JDK typically includes:

- `java`: launches applications on the JVM.
- `javac`: compiles Java source code.
- `javadoc`: generates API documentation.
- `jar`: creates and manipulates JAR files.
- Other diagnostic, testing, observability, and packaging tools, depending on the version and vendor.
- Standard library modules along with required runtime components.

The JDK is a concrete implementation of the Java platform. A JDK must provide behaviors and APIs within the specification scope it claims to support, and may include vendor-supplied tools or supplemental features.

### 1.3. A JDK Distribution Is the Packaged and Supplied Product

A JDK distribution (or JDK build) is an installer or binary artifact built, tested, packaged, and released by an organization. A vendor can build from the OpenJDK source code, apply its own patches or configurations, and ship for specific operating systems and architectures.

Examples of common distributions include:

- Oracle JDK.
- Eclipse Temurin.
- Amazon Corretto.
- Azul Zulu.
- Microsoft Build of OpenJDK.
- Red Hat build of OpenJDK.

This list merely illustrates products on the market; it is not a ranking and does not imply that the products share the same terms or support durations. You must verify the details for the exact vendor, version, operating system, and package type you intend to use.

OpenJDK is the open-source project and codebase of the JDK. A build from OpenJDK source still needs to be packaged, tested, released, and maintained by a specific organization or community. Therefore, the name "OpenJDK" in technical discussions may refer to the source project, a specific build, or a generic term for OpenJDK-based JDKs; when planning support, state clearly which meaning is used.

## 2. Relationship Between Java SE Releases and JDK Distributions

The relationship can be pictured as follows:

```text
Java SE feature release (e.g., Java SE 21)
    ├── Language and JVM specifications
    ├── Standard APIs
    └── Platform compatibility requirements
             │
             ▼
JDK implementation / platform source code
             │
             ├── Vendor A builds and tests
             ├── Vendor B builds and tests
             └── Vendor C builds and tests
                      │
                      ▼
             JDK distributions/builds
             ├── Installers for Linux, Windows, macOS
             ├── Packages for x64, AArch64, and supported architectures
             ├── Updates and patches
             └── Distinct terms, release schedules, and support
```

Two distributions both targeting Java SE 21 are expected to conform to the same standard platform within their declared compatibility scope. However, they do not necessarily share the same build number, release schedule, patches, default configuration, or OS support scope.

One vendor may release an update based on the latest upstream source. Another vendor may backport security patches or bug fixes to an older branch to continue supporting customers. Consequently, you cannot simply compare build numbers or release dates to conclude which build is safer or supported longer.

## 3. Distinguishing Feature Releases, Update Releases, and Build Numbers

Java now uses a regular feature release cadence. Feature releases create platform milestones such as Java 17, 21, or 25. Between these milestones, vendors ship updates to fix bugs, address security vulnerabilities, and maintain runtime quality.

A common version string is `21.0.2+13`. It can be read at a high level as:

| Component | Meaning |
|---|---|
| `21` | Feature version, identifying the Java 21 platform line. |
| `0` | Interim component in modern versioning rules; usually stays 0 in common releases. |
| `2` | Update level, indicating the update level within that feature release. |
| `+13` | Build number of the released build. |

Actual strings may include extra details such as an LTS label or vendor metadata. Read them according to the corresponding JDK's versioning rules rather than assuming every numeric segment has the same meaning across products.

### 3.1. Feature Release

A feature release such as Java 17 or Java 21 defines a platform generation. When moving from Java 17 to Java 21, the team may have to address language, API, JVM, garbage collector, tooling, framework, and dependency changes. This is generally a larger migration scope than applying a patch within the same feature release.

### 3.2. Update Release

Update releases within the same feature line usually focus on bug fixes, security, timezone data updates, certificates, standard libraries, and runtime components. The goal is to preserve compatibility within the feature release's policy, yet applications still need testing because a bug fix can expose reliance on old behavior, alter edge-case results, or change security components.

### 3.3. Build Number and Vendor Metadata

The build number identifies a specific build. Two vendors may use different build numbers for the same feature/update level due to differing build processes and release schedules. Metadata may include custom suffixes, an LTS label, or build details. When logging an incident, save the full `java -version` output rather than recording only `21`.

## 4. Do Not Confuse the JDK, Runtime Images, and the JRE

A JDK typically includes the runtime along with development tools. Previously, many vendors distributed a separate JRE for running applications. Since Java 9, the module system and runtime image creation allow packaging a runtime tailored to needs; many products now focus on distributing the full JDK or custom runtime images.

Therefore, do not assume every vendor ships a standalone JRE package for every feature release. If production only needs to run the application, an organization can use a runtime image built with `jlink`, a vendor-supplied runtime package, or a container image already containing the runtime. Verify that the runtime image has all required modules, providers, certificates, locales, timezone data, and diagnostic tools needed by the application.

Switching from a full JDK to a minimal runtime image may omit tools like `jcmd`, `jstack`, or `jmap` inside the container. This does not necessarily stop the application from starting, but it can impact incident troubleshooting. This is a packaging/operational decision that must be verified separately.

## 5. LTS Is a Support Policy, Not a Language Feature

LTS (Long-Term Support) is commonly used to designate a feature release that a vendor or distribution organization commits to maintaining longer than short-term release branches. However, the LTS label does not guarantee that every vendor offers the same support duration, update schedule, or terms of use.

Distinguish between:

- **Feature release:** a technical platform milestone, such as Java 21.
- **LTS designation:** how a vendor or distribution classifies a release line under its support policy.
- **Support lifecycle:** the actual duration and type of support a vendor commits to for a specific product.

One feature release can be distributed by many vendors, yet each vendor can announce different end-of-support dates. One vendor may provide free security updates for a period; another vendor may require a commercial subscription for certain types of support or usage environments. These conditions must be verified in the applicable terms.

LTS also does not mean a version will be supported indefinitely. When a support phase ends, a vendor may stop issuing public patches, transition to conditional extended support, or terminate all support. Phase names vary by vendor.

## 6. Components of a JDK Support Policy

When evaluating a distribution, do not only ask "is it LTS?". Read the support policy across specific dimensions.

| Policy Component | Questions to Confirm |
|---|---|
| Support duration | When are the start date, end of public updates, end of standard support, and end of extended support? |
| Security patches | Are CVE patches provided for the active feature line? What are the published cadence and turnaround times? |
| Bug fixes | Are fixes taken only from upstream, or does the vendor backport to older branches? Which bug severities are covered? |
| SLA and support channels | Are technical support, response times, escalation procedures, and production support available? |
| OS/architecture | Are builds provided for the exact OS, CPU architecture, container base image, and virtualization environment? |
| Terms of use | Under what conditions can it be used in development, testing, production, and redistribution? Are there commercial restrictions? |
| Compliance and security | Are there requirements or evidence for FIPS, crypto providers, certifications, SBOMs, or vulnerability handling? |
| Tools and features | Are diagnostic tools, Java Flight Recorder, Mission Control, or features required for operations supported? |
| Platform updates | Does the vendor maintain builds for the active OS version, architecture, and container environment? |

Some vendors use a quarterly update schedule, while others may issue out-of-band updates when needed. Terms such as CPU, PSU, Critical Patch Update, or security update are organization-specific terminology and should not be assumed to share identical scope. Read the advisories and release notes of the exact product.

## 7. OpenJDK, Vendor Builds, and Compatibility Certification

OpenJDK provides the open-source codebase to build the JDK. Vendors can use that source code to produce builds, add patches, configure builds, package installers, and provide support.

Do not equate the following three things:

1. **Using OpenJDK source:** indicates the origin or source foundation of the implementation.
2. **Releasing a JDK build:** indicates a specific artifact was built, tested, and distributed.
3. **Claiming Java SE compatibility:** indicates the product claims compliance with the platform specification and may carry corresponding test/certification evidence.

A product derived from OpenJDK does not automatically share the same support terms as every other OpenJDK-based product. Likewise, two products on the same feature release do not necessarily share the same certification level, OS/architecture scope, or service commitments.

When standard compatibility is mandatory, check the Java SE compatibility claim and the testing/certification program the vendor publishes for the exact version, rather than relying solely on the name "OpenJDK" or `java -version` output.

## 8. How Can Differences Between Distributions Affect Migration?

For a standard Java application, switching between two distributions on the same feature release and update level is generally expected to preserve Java SE platform behavior. Even so, differences exist that can affect real environments:

- Vendor-specific patches or backports.
- Default configurations for the JVM, GC, memory ergonomics, or container awareness.
- Bundled native libraries, crypto providers, security policies, and CA certificates.
- Timezone data, locales, fonts, and OS components.
- CPU architecture, OS version, and container base image support.
- Diagnostic tools, extra modules, or vendor-specific features.
- Installation methods, update mechanisms, `JAVA_HOME` layout, package signing, and OS integration.

For example, an application making HTTPS connections might work on a developer's machine yet fail inside a container due to a different truststore or CA certificates. An application relying on a specific cryptographic provider might fail to start if that provider is not packaged or configured like in the old environment. These issues are not necessarily Java SE API differences; they can stem from the distribution, OS image, or deployment configuration.

Therefore, when changing vendors or distributions, test on the exact OS/architecture and container image intended for production. If the organization relies on vendor-specific features, document that dependency and its replacement plan before switching.

## 9. Choosing a JDK Distribution for a System

No single distribution fits every organization. Selection should be grounded in technical, operational, legal, and support requirements.

### 9.1. Selection Criteria

**Platform compatibility:** confirm supported feature releases, update levels, OSes, architectures, containers, and frameworks.

**Update policy:** confirm release frequency, how security patches are delivered, vulnerability response timelines, and how the vendor backports fixes to older feature lines.

**Terms and cost:** check usage rights across development, testing, staging, production, cloud environments, and redistribution. Do not infer licensing terms from upstream source being open source; binary artifact and support service terms must be read separately.

**Operational support:** determine whether SLAs, production incident support, migration consulting, emergency patches, or long-term OS support are needed.

**Security and compliance requirements:** check crypto providers, FIPS if required, truststores, SBOMs, CVE handling processes, artifact signing, and trusted download sources.

**Standardization capability:** prefer one clear policy across local, CI, container, and production environments. If multiple distributions are needed, maintain documented justification and a test matrix for each.

### 9.2. Sample Vendor Evaluation Table

| Criterion | Vendor/Distribution A | Vendor/Distribution B | Evidence to Store |
|---|---|---|---|
| Feature release |  |  | JDK version and release notes |
| Update level |  |  | Version output and advisories |
| OS/architecture |  |  | Supported platform matrix |
| Security updates |  |  | Update schedule and CVE policy |
| Support end date |  |  | Official product lifecycle |
| License/terms |  |  | Current terms of use |
| Commercial SLA |  |  | Contract or support service page |
| Runtime/tooling |  |  | List of required tools, modules, and features |
| Container support |  |  | Base image, digest, OS packages, and architecture |
| Compliance needs |  |  | Required certifications or technical documentation |

Do not fill in end-of-support dates with a single generic date for "Java 21". Record the exact product, vendor, support tier, OS version, and applicable contract terms.

## 10. Identifying the Actual JDK in Build and Runtime Environments

A project may use multiple JDKs in the same pipeline:

- The JDK running the Gradle daemon or Maven.
- The JDK toolchain used to compile and run tests.
- The target JDK for which compatible bytecode and APIs are produced.
- The JDK inside the container or production server.
- The JDK used by CI tools, scanners, code generators, or plugins.

These JDKs may differ in feature release or vendor. Therefore, when auditing an environment, record each location rather than running only `java -version` in a developer's terminal.

### 10.1. Checking the Runtime on PATH

```bash
java -version
javac -version
```

These two commands identify the runtime and compiler invoked from `PATH`. They do not prove that Gradle or the production application uses that exact JDK.

To inspect more system information:

```bash
java -XshowSettings:properties -version
```

Useful properties include `java.vendor`, `java.runtime.version`, `java.vm.name`, `os.name`, and `os.arch`. When collecting migration evidence, save the verbatim output for before-and-after comparison.

### 10.2. Checking the JVM Running Gradle

```bash
./gradlew -version
```

The output shows the JVM used by Gradle. This JVM can differ from the JDK toolchain used by compilation tasks.

### 10.3. Declaring Toolchain and Vendor in Gradle

Kotlin DSL example:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
```

This declaration requests a Java 21 toolchain from the specified vendor. Whether Gradle automatically locates or downloads the JDK also depends on toolchain resolver configuration and the build environment. Syntax and available vendor specs must be checked against your project's Gradle version.

If you need to compile with JDK 21 while producing Java 17-compatible bytecode, configure `--release` through Gradle:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

In this scenario, the compiler can run on JDK 21 while compiling source against the Java 17 language level, bytecode, and APIs specified by `--release`. That does not automatically guarantee all application dependencies, plugins, or runtimes are Java 17 compatible; those components must still be verified separately.

### 10.4. Checking Containers and Production

For containers, inspect the image tag, digest, base OS, architecture, and JDK version inside the image. Tags like `21` or `21-jre` can be updated over time; when build reproducibility is required, manage digests and image update policies appropriately.

For production servers, check which binary the actual process runs, the service's `JAVA_HOME`, systemd/service manager configurations, container environment variables, and rollout mechanisms. The `JAVA_HOME` in an interactive login shell is not necessarily the JDK used to launch the service.

## 11. Building a JDK Support Matrix for Migration

Before upgrading, create a matrix for each environment and consumer. Example:

| Component | Feature Version | Distribution/Vendor | Update Level | Purpose |
|---|---|---|---|---|
| Developer workstation | 21 | Team-standardized distribution | Per team baseline | Writing code and running local tests |
| CI build agent | 21 | Same vendor or verified vendor | Approved update | Running Gradle/Maven and pipelines |
| Compile toolchain | 21 | Per toolchain policy | Approved update | Compiling source and tests |
| Runtime container | 21 | Verified runtime image | Per image update schedule | Running the application |
| Production host | 21 | Vendor supported by operations | Per production patch schedule | Official production operation |

This matrix is only an example. If the system has consumers still needing Java 17 or multiple CPU architectures, add corresponding rows. Each row should include an owner, verification date, download source, update policy, and end-of-support date.

A good matrix should answer:

1. Which component uses which JDK, and who owns its updates?
2. Are feature versions and update levels consistent with organizational requirements?
3. Does the distribution support the exact OS, architecture, and container?
4. Which end-of-support milestone arrives earliest across the entire build and runtime chain?
5. Are any consumers locked to an older JDK due to frameworks, plugins, or dependencies?
6. Is there a process for detecting and applying emergency security patches?

## 12. Transition Roadmap and Maintaining Updates

### Step 1: Inventory the Current State

Collect version outputs from local machines, CI, build agents, containers, and production. Record feature release, update level, vendor, OS, architecture, installation method, and owner.

### Step 2: Define Technical Targets

Select the target feature release based on language/API requirements, frameworks, dependencies, Gradle/Maven, and support timelines. Decide whether to change vendor or distribution at the same time. Changing both feature release and vendor at once makes root-cause analysis harder; split them into separate stages when project conditions allow.

### Step 3: Cross-Check Support Policies

Read the lifecycle and terms of the exact distribution. Identify public security update end dates, commercial support, extended support, and end-of-life. Save reference links along with the verification date because vendor policies can be updated.

### Step 4: Standardize Build and Runtime

Declare toolchains, compiler release, Gradle JVM, container base images, and target runtime. Ensure the pipeline cannot accidentally pick up a different JDK via `PATH`, `JAVA_HOME`, or drifting image tags.

### Step 5: Test Against Realistic Environments

Run builds, unit tests, integration tests, smoke tests, and performance checks on the target distribution. When changing vendors, also verify certificates, crypto providers, timezones, locales, native libraries, and diagnostic tools.

### Step 6: Release and Monitor

Deploy first to staging, then perform a controlled rollout. Monitor JVM errors, GC, memory, startup, TLS, logging, and business metrics. Record complete version metadata to support incident traceability.

### Step 7: Maintain the Update Cycle

Establish a schedule to review security advisories and update the JDK, container images, and OS. Define approvers, testing procedures, patch rollout timelines, and rollback plans. Do not wait until end-of-life to begin planning an upgrade.

## 13. Common Misconceptions

**"Same Java 21 means every JDK is identical."** Distributions targeting the same Java SE release must conform to the corresponding platform, yet still differ in builds, patches, packaging, OS support, tooling, and support policies.

**"OpenJDK is a single vendor."** OpenJDK is a project/codebase; many organizations can build and ship distributions from that source.

**"Java 21 LTS means all vendors support it until the same date."** LTS does not replace product-specific lifecycles. Look up the exact vendor, distribution, support tier, and terms.

**"Installing the latest JDK is enough."** You must confirm whether the latest JDK falls within compatibility bounds of your frameworks, plugins, dependencies, OS, and production environment, as well as review update policies and rollout procedures.

**"A passing build on a developer laptop proves production has the right JDK."** Build daemons, toolchains, containers, and production services may use different JDKs. Verify each environment.

**"Open source means every usage is free and comes with support."** Source code licenses, binary distribution terms, and support contracts are separate matters. Read the terms applicable to your organization and usage environment.

## 14. Checklist for Confirming Versions and Support Policies

- [ ] Documented the target Java SE feature release.
- [ ] Recorded actual JDK distribution, vendor, and update/build level.
- [ ] Distinguished the JDK running Gradle, the compile toolchain, and the production runtime.
- [ ] Checked OS, CPU architecture, container image, and native dependencies.
- [ ] Verified the distribution's Java SE compatibility claim when required by the project.
- [ ] Read the exact vendor's lifecycle, security update schedule, end-of-life, and terms of use.
- [ ] Identified SLA, commercial support, compliance, and certification requirements if applicable.
- [ ] Tested on the target distribution and production-like environment.
- [ ] Established an update schedule, owner, CVE handling process, and rollback plan.
- [ ] Saved reference sources and the verification date for support policies.

## Conclusion

A Java SE release describes the platform version; the JDK is the toolkit and runtime implementing that platform; a JDK distribution is the specific product built, packaged, and supported by a vendor. LTS status, security update schedules, terms of use, and support durations depend on each vendor and product line. During migration, record full feature version, vendor, update level, build/runtime environments, and support lifecycles. Doing so helps the team choose the right JDK for the system, avoid confusing technical compatibility with operational commitments, and proactively maintain patches throughout the application's lifecycle.
