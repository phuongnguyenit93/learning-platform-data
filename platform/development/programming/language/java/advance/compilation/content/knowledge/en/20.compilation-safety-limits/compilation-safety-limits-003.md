# Allow Only Trusted Processors, Plugins, and Dependencies

## 1. Why Is This a Security Boundary of Java Compilation?

Compiling Java does not merely read source files and emit bytecode. A real build can **execute third-party programs before the application ever runs**:

- **Annotation processor** (JSR 269) runs inside or alongside the compilation process to analyze annotations and generate code, resources, or diagnostics.
- **Compiler plugin** can hook into the compilation pipeline, inspect or modify syntax trees, check code, or generate bytecode. Some plugins use internal compiler APIs.
- **Gradle/Maven build plugins**, scripts, tasks, and code generators run during build configuration or execution; their privileges typically match those of the account running the build.
- **Library dependencies** usually sit on the classpath for the compiler to read, yet you must distinguish libraries used by the program from libraries loaded and *executed* by processors/plugins/tasks. Plugins and processors can also bring transitive dependencies of their own.

A processor can access files, environment variables, system properties, the network, and whatever permissions the OS grants to the process. A Gradle plugin can execute code during project configuration, even before the compile task begins. Therefore, "only compiling, not running the application yet" **is not a security boundary**.

For example, if CI provides an artifact-publishing token, an untrusted processor or plugin running in the build can read whatever that token grants access to. The fact that application source code does not call the processor directly does not restrict these effects.

**Goal:** place only vetted code and tools onto classpaths/execution stages **with execution privileges**, pin and verify exact approved artifacts, reduce build privileges, and maintain mechanisms to detect and handle anomalous dependencies.

## 2. What Does "From a Trusted Source" Mean?

No single attribute such as "downloaded from Maven Central" suffices to prove every version of an artifact is safe. Multiple factors must be combined:

| Question to answer | Appropriate evidence/measure |
|---|---|
| **Who published it?** | Project owner, official repository, approved organization/publisher; verify identity and project history |
| **Is it the exact approved artifact?** | Group/artifact/version, checksum or signature verification; reviewed verification metadata |
| **Could it change unexpectedly?** | Explicit version, version locking, avoiding dynamic versions and SNAPSHOTs in controlled release paths |
| **What dependencies does it pull in?** | Inspect the dependency graph and transitive artifacts, including processor/plugin runtimes |
| **What execution privileges does it have?** | Processor path, compiler plugin, buildscript/plugin classpath, CI credentials, network/file access |
| **Has risk been evaluated?** | Vulnerability advisories, security notices, changelogs, tested updates, license policies if required by the organization |
| **Is it traceable and recoverable?** | Lockfiles, build manifest/SBOM, changelogs, version-upgrade process, rollback capability |

**Integrity differs from trustworthiness:** a checksum confirms that the current artifact matches previously recorded bytes; if the checksum was generated from a malicious artifact without a vetting step, the checksum still "matches" without proving the artifact is safe. Signatures must likewise bind to a **trusted publisher key and identity**, not merely "has a signature."

A library with a name very similar to an official one may be *typosquatting*. Avoid relying on popularity, download counts, logos, or URLs submitted in a pull request as sole evidence.

## 3. Classifying Dependencies by Execution Capability

Answer "where does this dependency go?" before adding it to the build.

| Location | Role | Typical risk |
|---|---|---|
| `implementation` / `api` | Participates in application compile/runtime | Code usually does not execute during compilation just by being on the classpath; still carries runtime and build-tooling risks if loaded |
| `compileOnly` | Available to compiler for type checking; not packaged as a runtime dependency under standard Java configs | Missing at runtime if the application actually uses that class when running |
| Gradle `annotationProcessor` | Set of processors and dependencies needed for processors to operate | Has execution privileges when JavaCompile runs |
| `plugins { ... }` | Gradle plugin applied in the build | Can execute code at configuration time, before compilation |
| `buildscript { dependencies { classpath ... } }` | Tools used by buildscript/legacy plugins | Executable from build logic |
| Tools invoked by `Exec`/`JavaExec` tasks | External compilers, generators, linters, schema tools | Privileges matching the spawned process; can write files/make network calls |
| `testRuntimeOnly` / `testImplementation` | Code used by the test runtime | Third-party code executes when running tests |

**Separating the annotation API from the processor implementation** is an important step. Source code usually only needs the annotation types to compile; the processor implementation must go on `annotationProcessor`, rather than stuffing the processor into `implementation` out of habit. This makes classpaths cleaner and reduces the chance of processors being implicitly triggered from the compile classpath.

On newer JDK versions, `javac`'s default discovery behavior can change; configuring processors explicitly via the build tool is easier to control than expecting every processor on the classpath to run automatically.

## 4. Java 17 Example with an Explicitly Specified Processor

The example uses **AutoValue 1.11.0** as concrete dependency coordinates to illustrate the technique. Mentioning these coordinates **does not mean that version or artifact has been vetted by your organization**. Before using it in a real system, independently verify the publisher source, transitive dependencies, checksums, vulnerabilities, and project allowlist policy.

Suppose the structure is:

~~~text
trusted-processor-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/
    ├── Person.java
    └── App.java
~~~

The project uses a **project-managed Gradle Wrapper** and JDK 17+; verify and pin an appropriate Gradle Wrapper version. Do not copy unfamiliar wrapper URLs or unreviewed "install Gradle" scripts.

### 4.1. Centralizing Repository Sources in settings.gradle

File `settings.gradle` (Groovy DSL):

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "trusted-processor-demo"
~~~

Here, `RepositoriesMode.FAIL_ON_PROJECT_REPOS` makes the build fail if a project attempts to declare its own repository (e.g., a URL injected into `build.gradle`). This is **resolution-source control**: the build uses only centrally configured repositories for regular dependencies. `pluginManagement.repositories` controls where **plugins** are searched; plugin repositories and module-dependency repositories are two separate scopes.

The configuration above is only a **starting baseline**. Additional resolution mechanisms such as `buildscript`, included builds, init scripts, local repositories, or internal organizational repositories require corresponding policies. Simply putting `mavenCentral()` does not automatically create an allowlist for **every artifact** on Maven Central.

### 4.2. Placing the Processor on the Appropriate Classpath

File `build.gradle`:

~~~groovy
plugins {
    id "java"
}

dependencies {
    compileOnly "com.google.auto.value:auto-value-annotations:1.11.0"
    annotationProcessor "com.google.auto.value:auto-value:1.11.0"
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Here `java` is Gradle's built-in plugin, not an external plugin downloaded from the plugin portal. The annotation API is used when compiling source; the annotation processor is provided to the compiler via its dedicated configuration. Both dependencies use explicit versions, though **a pinned version only limits unintended changes and does not verify artifact contents**.

If a module needs another processor, do not just copy coordinates from a blog post. Verify group/artifact names in vetted source documentation; check processor compatibility with your JDK and compiler, as well as all transitive dependencies it downloads.

### 4.3. Consumer Requiring Generated Code to Be Usable

File `src/main/java/example/Person.java`:

~~~java
package example;

import com.google.auto.value.AutoValue;

@AutoValue
public abstract class Person {
    public abstract String name();

    public static Person of(String name) {
        return new AutoValue_Person(name);
    }
}
~~~

File `src/main/java/example/App.java`:

~~~java
package example;

public final class App {
    public static void main(String[] args) {
        System.out.println(Person.of("An").name());
    }
}
~~~

When processing `@AutoValue`, the processor generates the `AutoValue_Person` implementation in package `example`. The call in `Person.of` forces the compiler to validate the generated class during the build. If the processor does not run and no stale class leaked into the output, compilation must fail because `AutoValue_Person` is not found.

Run from the project root with the configured Gradle Wrapper:

~~~bash
./gradlew clean classes
java -cp build/classes/java/main example.App
~~~

On Windows PowerShell, use `.\gradlew.bat clean classes`. Once dependencies resolve successfully and the processor runs properly, the output **of the java command** is:

~~~text
An
~~~

You can inspect the generated source at the Gradle Java plugin's default location:

~~~text
build/generated/sources/annotationProcessor/java/main/example/AutoValue_Person.java
~~~

This path can change if the build reconfigures the generated-sources directory. **Do not** manually copy old generated files into the source directory or into version control to make tests appear green. The goal is a clean compilation that genuinely executes the selected processor.

## 5. Locking Versions and Verifying Integrity with Gradle

### 5.1. Avoiding Dynamic Versions

Examples such as `1.+`, `latest.release`, and version ranges allow the build to resolve different artifacts over time. For executable processors/plugins, unplanned changes are especially dangerous. Use explicitly reviewed versions, and manage upgrades via reviewed pull requests.

When transitive dependencies of configurations need locking, Gradle supports dependency locking. Example in `build.gradle`:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

After deciding on the approved dependency/version list, you can run in a controlled test build:

~~~bash
./gradlew compileJava --write-locks
~~~

Lockfiles are generated from **the configurations resolved** during that command; run the relevant tasks/configurations when locking all plugin/test/processor paths. Commit the appropriate lockfiles and review lockfile changes on every upgrade. Locking prevents silent changes to **resolved versions**, yet does not by itself verify checksums or publisher trust.

### 5.2. Dependency Verification

Gradle supports checksum/signature verification metadata for resolved artifacts; the file typically lives at `gradle/verification-metadata.xml`. To **initialize verification metadata in a supervised environment**, an illustrative command is:

~~~bash
./gradlew --write-verification-metadata sha256 compileJava
~~~

Automatically generating metadata from downloaded bytes **does not prove the source is safe**. Before approving, cross-check the artifact and SHA-256 against a trusted publisher source or independently reviewed records; verify transitive dependencies as well. Then commit the reviewed metadata and run builds normally in CI so Gradle enforces artifact checks per policy. Understand the verification coverage and exemptions of your Gradle version, especially regarding plugin resolution and custom repositories.

Also do not trust an internal cache merely because an artifact is present there. Remote caches and repository proxies require write permissions, quarantine workflows, and auditing; approved checksums must be preserved when mirroring artifacts.

### 5.3. Inspecting the Dependency Graph

In the example above, you can inspect the configuration containing the processor:

~~~bash
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencyInsight --configuration annotationProcessor --dependency auto-value
~~~

Inspect transitive artifacts rather than only directly declared dependencies. For build plugins, check the dependencies and code pulled in by the plugin at configuration time. Do not judge trustworthiness solely because `dependencies` output shows no conflicts.

## 6. Restricting Repositories and Plugins Under Organizational Policy

A practical strategy is maintaining an approved source set, favoring an internal proxy/mirror with artifact acceptance rules, along with group/module-level allowlists when needed. Key measures:

1. **Separate plugin resolution from dependency resolution.** Changing `repositories` in a project does not necessarily control the source of Gradle plugins.
2. **Do not accept arbitrary URLs from PRs.** An unfamiliar repository added ahead of trusted repositories can introduce same-named artifacts or alter resolution order.
3. **Pin used plugin IDs/versions.** The plugin DSL can resolve plugin markers and implementation/transitive artifacts; these must also be vetted.
4. **Review init scripts, included builds, and build logic.** Groovy/Kotlin code executed during a Gradle build is executable code, even if it does not appear as a dependency in `build.gradle`.
5. **Never run `curl ... | sh` or download compiler extensions from short links.** If tools must be installed, use verifiable releases from approved sources and verify checksums/signatures per policy.
6. **Prohibit snapshot/dynamic dependencies in release pipelines** unless clear source governance and artifact identification mechanisms are in place.

A repository allowlist is a layer for reducing the attack surface, **not a substitute** for version review, integrity verification, or checking each artifact's provenance.

## 7. Running Compilation with Least Privilege

When processors/plugins can execute code, the next line of defense is limiting impact even if a dependency is compromised.

| Resource | Recommended control |
|---|---|
| **CI credentials** | Regular compile/test jobs have no publish/deploy tokens; grant short-lived tokens only to jobs that must publish |
| **File system** | Isolated workspace, mount only needed files; restrict writable areas outside permitted build outputs/caches |
| **Network** | Restrict egress where appropriate; fetch dependencies from controlled proxies and separate download from execution stages when possible |
| **Build agents** | Use ephemeral agents/VMs/containers for untrusted PRs; avoid running as administrator/root unless necessary |
| **Caches** | Separate read/write permissions on remote caches; prevent untrusted builds from writing to caches used for releases |
| **Secrets in logs/artifacts** | Do not print tokens, sensitive environment variables, or full config files; control access to logs/artifacts |
| **Workflow triggers** | For PRs from untrusted sources, avoid workflows that grant write/publish permissions or expose secrets while executing PR build logic |

**Important:** containers, sandboxes, offline mode, or repository verification do not provide absolute isolation if the build account still has a path to read secrets or reach the external network. Design privileges around the job's actual capabilities. Also do not assume "a dependency is just a normal library, so it cannot run during the build": plugins, test runners, or codegen tasks may load and execute that code.

If you must trial an unapproved processor for analysis, do so in an isolated environment using an account with no production data/secrets; never put it straight into release CI.

## 8. Approval Workflow for New Processors/Plugins

A repeatable workflow:

1. **Confirm the need:** what problem does the processor/plugin solve? Can built-in JDK/Gradle features reduce third-party code execution instead?
2. **Confirm identity:** trace Maven coordinates/plugin IDs back to official release pages and source repositories; check maintainers, change history, and signs of takeover.
3. **Choose the right version:** review release notes, Java/Gradle compatibility, vulnerability history, and support status. Do not blindly pick "latest" without testing.
4. **Evaluate the full dependency tree:** examine transitive artifacts, processor paths, and plugin implementation paths; identify which scopes execute code.
5. **Verify provenance/integrity:** check checksums/signatures via trusted channels; update verification metadata and lockfiles under review.
6. **Trial in a low-privilege environment:** clean build, test compilation and generated outputs, observe anomalous network/file access when appropriate monitoring tools are available.
7. **Review diffs:** all changes to build scripts, plugin repositories, lockfiles, verification metadata, wrappers, and source generators must be inspected.
8. **Release under scoped privileges:** only approved CI jobs hold publish credentials; monitor and record build components for incident response.
9. **Upgrade periodically:** track security advisories, bug fixes, tested updates, and maintain a rollback path.

When a suspicious artifact is detected, stop using that version, identify which builds/jobs used it, revoke tokens if exposure is possible, inspect logs and outputs, purge relevant caches, and rebuild from verified dependencies. Do not resolve an incident merely by changing a version string in source.

## 9. Misconceptions That Easily Cause Vulnerabilities

**"Maven Central or the Gradle Plugin Portal are unconditionally trustworthy sources."** They are common distribution channels, yet artifacts can still be published by compromised accounts or unvetted publishers. Always verify identity and the exact artifact.

**"Compilation does not run code."** False for annotation processors, compiler plugins, Gradle plugins, buildscripts, and code-generation tools. That is why build-time dependencies must be controlled as well.

**"Locking versions is enough."** Lockfiles pin versions, yet do not protect against an artifact whose bytes were altered at the same coordinates or against locking a malicious version. Integrity/provenance verification and review are required.

**"If the checksum matches, the artifact is safe."** A checksum only confirms that the artifact matches previously accepted bytes; if those bytes were accepted from an unverified source, the trust step is still missing.

**"Adding a processor to implementation is always equivalent to annotationProcessor."** No. The two configurations have different semantics; place processors where the compiler searches for and executes them, while avoiding unnecessarily putting processor implementations into the application runtime.

**"Using `--offline` makes processors safe."** Offline mode restricts new downloads via Gradle, yet does not stop malicious code already on the classpath from reading files or taking other actions permitted by the environment.

**"Only release PRs need least privilege."** An ordinary PR can still alter build logic or compiler plugins. Avoid granting secrets/high privileges to jobs validating untrusted PRs.

**"Passing unit tests proves a processor is safe."** Green tests demonstrate expected behavior, not the absence of unintended operations or access to sensitive data. Source control, privilege restrictions, and security review remain necessary.

## 10. Checklist Before Introducing Third-Party Compilation Tools into a Project

- [ ] Verified the publisher and exact coordinates of processors/plugins and their direct/transitive dependencies.
- [ ] All versions are pinned/locked per policy; no dynamic versions/SNAPSHOTs outside approved exceptions.
- [ ] Artifact integrity and provenance are independently checked; verification metadata is reviewed rather than unconditionally auto-approved.
- [ ] Plugin repositories, dependency repositories, included builds, init scripts, and tool installers are within governance scope.
- [ ] `annotationProcessor` is separated from `compileOnly`/`implementation`; executable code is not placed on the wrong classpath.
- [ ] A fixture compiles and exercises generated code against the expected JDK/toolchain and classpath; build output is clean.
- [ ] CI build/test runs with least privilege and no release secrets; untrusted PRs run in an isolated environment.
- [ ] Write permissions on repositories/caches/artifacts are restricted; logs and generated outputs contain no secret data.
- [ ] Dependency updates go through review, vulnerability checks, testing, and have rollback/incident-response procedures.

**Final principle:** in Java compilation, processors and build plugins are **code executed within the software build environment**. Allow only tools from vetted sources, bind exact artifacts and versions, restrict build-process privileges, and verify code-generation results in a clean build. No single checking tool replaces all of these control layers.