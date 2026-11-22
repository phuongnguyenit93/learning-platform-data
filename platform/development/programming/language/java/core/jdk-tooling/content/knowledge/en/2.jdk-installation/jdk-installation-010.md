# Updating the JDK Safely

## 1. What Is a JDK Update?

**Updating the JDK safely** is the process of moving the Java Development Kit currently in use to an appropriate release while verifying that the development environment, build system, application, and deployment environment continue to work properly.

A JDK update may include security patches, runtime bug fixes, and updates to the compiler, standard library, or bundled tools. Because the JDK directly affects application compilation and execution, it is necessary to control the download source, version, configuration, and test results.

There are two common types of changes:

- **Update within the same feature release:** for example, moving from Java 21.0.4 to 21.0.5. This change is typically intended to receive security patches and bug fixes within the same Java 21 line.
- **Upgrade to a different feature release:** for example, moving from Java 17 to Java 21. This is a larger change that may affect the language, bytecode, APIs, modules, build tools, and library compatibility.

Updates within the same feature release usually have a narrower compatibility scope, but they still require testing. You should not assume that every new JDK release is completely impact-free for your application.

## 2. Why Update the JDK?

Keeping the JDK at an appropriate update level helps you:

- Receive security patches for the JVM, standard library, and bundled components.
- Fix bugs in the runtime, compiler, garbage collector, and JDK tools.
- Reduce risks from issues publicly disclosed by the vendor.
- Maintain compatibility with newer frameworks, libraries, and build tools.
- Maintain a supported development environment.
- Reduce the gap between the JDK used for development, testing, and deployment.

The JDK is a foundational component. If an application uses TLS, certificate handling, cryptography, serialization, timezones, or networking, a JDK update can affect the behavior of these components. You should review the vendor's release notes and security advisories before deploying.

## 3. Distinguishing Updates, Upgrades, and Vendor Changes

The following three changes have different scopes:

| Change | Example | Key Considerations |
|---|---|---|
| Patch update | Java 21.0.4 to 21.0.5 | Security patches, bug fixes, and changes within the same feature release |
| Feature upgrade | Java 17 to Java 21 | APIs, syntax, bytecode, modules, GC, tools, and library compatibility |
| Vendor change | Eclipse Temurin 21 to Oracle JDK 21 | Support policy, licensing, builds, platforms, and distribution differences |

You should not combine all three changes at once unless necessary. Whenever possible, change one factor at a time so it is easier to isolate the root cause if an error occurs.

An organization may choose the same feature release while still requiring a specific vendor to standardize support and maintenance processes. Clearly document both the vendor and the full version in the environment documentation.

## 4. Identifying the Currently Used JDK Before Updating

Before making changes, you need to know which JDK the machine and project are using. A machine may have multiple JDKs installed, while the terminal, IDE, Maven, and Gradle may be using different paths.

Run the basic commands:

```bash
java --version
javac --version
```

On Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
```

On Linux or macOS:

```bash
echo "$JAVA_HOME"
type -a java
type -a javac
command -v java
command -v javac
```

Check both the runtime launcher and the compiler. If `java` and `javac` come from two different directories, the machine may be running one JDK while compiling with another.

Check the actual JVM being executed:

```bash
java -XshowSettings:properties -version
```

Look for the `java.home` property in the output. This property indicates the runtime directory of the running JVM. It helps detect cases where `JAVA_HOME` and the actual runtime do not match.

For Maven:

```bash
mvn -version
```

For Gradle:

```bash
./gradlew --version
```

On Windows, use `gradlew.bat --version`. These commands show which JVM Maven or Gradle is using. A project may also configure a separate compiler toolchain, so you must check the build configuration as well.

## 5. Preparing Before Updating

Before installing a new release, establish a baseline of the current state so you can compare and roll back if needed.

### 5.1. Recording Versions and Paths

Record the following:

- JDK vendor name.
- Current feature release and update number.
- JDK installation path.
- Current value of `JAVA_HOME` and `PATH` order.
- Output of `java --version` and `javac --version`.
- JVM version used by Maven or Gradle.
- JDK selected in the IDE.
- JDK and image currently used in CI or containers.

You can save the output of the check commands into a maintenance log file. Do not include sensitive information or passwords in this file.

### 5.2. Checking Compatibility Requirements

Read the project configuration and identify:

- The minimum Java version supported by frameworks and libraries.
- The Java release the project uses for compilation.
- The JDK version running the build tool.
- The runtime version in staging and production environments.
- The versions of Maven Compiler Plugin, Gradle Wrapper, and other plugins.
- Whether annotation processors, agents, native libraries, and testing tools depend on the JDK.

If upgrading to a new feature release, check the compatibility matrix of Gradle, Maven plugins, frameworks, and libraries. A new JDK may require upgrading build tools before the project can compile.

### 5.3. Reading Release Notes and Security Advisories

Use the official documentation from the JDK vendor you are using. Focus on:

- Security vulnerabilities fixed and their severity.
- JVM, compiler, GC, networking, and TLS bugs resolved.
- Behavioral changes that could affect the application.
- Deprecated or removed APIs.
- Default changes to cryptographic algorithms, certificates, locales, or timezones.
- Known issues and platform limitations.

Do not just read the version number. Release notes help determine whether the update affects features that your application uses.

## 6. Downloading and Verifying the JDK Installer

Only download the JDK from a trusted website or software repository of the vendor or organization. Verify the exact:

- Vendor approved by the project.
- Required feature release and update version.
- Operating system and CPU architecture (x64 or ARM64).
- Appropriate package type (installer, archive, or package).
- Support policy and terms of use applicable to that environment.

### 6.1. Verifying the Checksum

If the vendor publishes a SHA-256 hash, compute the checksum of the downloaded file and compare it exact-match against the official value.

Windows PowerShell:

```powershell
Get-FileHash .\jdk-installer.msi -Algorithm SHA256
```

Linux:

```bash
sha256sum jdk-installer.tar.gz
```

macOS:

```bash
shasum -a 256 jdk-installer.pkg
```

Checksums help detect corrupted files or mismatches with the expected release. The reference value must be obtained from an official channel or a verified internal distribution channel.

If the vendor provides a digital signature, verify the signature according to their instructions. Do not bypass signature warnings or disable operating system security protections just to install the JDK.

## 7. Installing the New Release in a Reversible Way

If the machine needs to maintain multiple projects or requires rollback capability, install the new release into a separate directory instead of immediately overwriting the active JDK.

Example:

```text
C:\Dev\Java\jdk-21.0.4
C:\Dev\Java\jdk-21.0.5

/opt/jdks/jdk-21.0.4
/opt/jdks/jdk-21.0.5
```

This layout lets you switch back to the previous release by changing the path configuration. Do not delete the old release until the new release has been tested and accepted.

### 7.1. Windows

You can use the vendor's official installer or a package manager approved by your organization.

Typical procedure:

1. Close applications currently using the JDK if required by the installer.
2. Run the verified installer.
3. Choose a separate installation directory if you need to keep the old release.
4. Complete the installation following the vendor's instructions.
5. Check that the new JDK directory contains components such as `bin` and `conf`.
6. Update `JAVA_HOME` and `PATH` for the terminal session or appropriate user configuration.
7. Open a new terminal and verify the version.

Do not assume the installer always preserves the old release. Upgrade behavior, removal of old versions, and `PATH` registration vary between vendors and installer types.

### 7.2. Linux

You can install using your distribution's package manager or an official archive. If using a package manager, check the package name and repository before updating.

With an archive, extract it into a separate directory, such as `/opt/jdks/jdk-21.0.5`. Then select the JDK using `JAVA_HOME` and `PATH`:

```bash
export JAVA_HOME=/opt/jdks/jdk-21.0.5
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
```

If the system uses `update-alternatives`, update both the `java` and `javac` selections. Check `JAVA_HOME` separately because the alternatives mechanism does not necessarily update this variable.

### 7.3. macOS

Install the package or archive from the vendor. Many JDKs are placed under:

```text
/Library/Java/JavaVirtualMachines/
```

List installed releases:

```bash
/usr/libexec/java_home -V
```

Select a specific JDK for the current shell session:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
```

The `-v 21` option selects feature release 21; if multiple distributions of the same feature release are installed, inspect the list and choose the exact JDK required by the project.

## 8. Updating Project and Build Tool Configurations

After installing the JDK, check the configuration used by each tool. Changing the terminal `PATH` does not automatically change the JDK in the IDE, Maven, Gradle, or CI.

### 8.1. Maven Configuration

Check the JVM running Maven:

```bash
mvn -version
```

If the project uses Maven Toolchains, check `~/.m2/toolchains.xml` and the plugins configured to use the toolchain. Update the JDK path when the new release is installed in a different location.

If the project sets a target release in `pom.xml`, confirm that the value is still correct:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

`maven.compiler.release` specifies the target Java version for compilation. It does not necessarily determine the JDK used to run Maven.

### 8.2. Gradle Configuration

Check the JVM running Gradle:

```bash
./gradlew --version
```

If using Java Toolchains, confirm that the toolchain still points to the appropriate JDK:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

If only applying a patch update within the same feature release, the feature version configuration may not need to change. However, Gradle might pick a different JDK of the same feature release if multiple are installed. When a fixed vendor or path is required, configure it according to Gradle's toolchain mechanism and project policy.

### 8.3. IDE Configuration

Check separately:

- Project SDK or Installed JDK.
- Module SDK if the project has multiple modules.
- JDK running Maven or Gradle inside the IDE.
- Run/Debug configurations.
- JDK used by the IDE for code analysis and running tests.

For example, IntelliJ IDEA may use Project SDK 21 while the Gradle JVM is still JDK 17. In that case, builds from the terminal and builds from the IDE can produce different results.

After changing the JDK, you may need to reload the project or restart the IDE so that background processes and configurations are reloaded.

## 9. Testing After Updating

Do not conclude that an update succeeded just because `java --version` prints the expected version number. You need to verify everything from the compiler to the runtime and the actual application.

### 9.1. Verifying Tools

Run:

```bash
java --version
javac --version
javadoc --version
jar --version
```

Check the actual paths and confirm that the commands come from the new JDK. If the project uses Maven or Gradle, also check the JVM version reported by the build tool.

### 9.2. Clean Build and Running Tests

With Maven:

```bash
mvn clean verify
```

With Gradle:

```bash
./gradlew clean build
```

Run the project's actual build system. Read the entire output, including warnings about deprecated APIs, module access, annotation processors, or incompatible plugins.

A successful build is only one step. You must run unit tests, integration tests, and system-specific tests.

### 9.3. Testing the Actual Application

Focus on areas that are easily affected when changing the JDK:

- Application startup, class loading, and module loading.
- TLS connections, certificates, truststores, and keystores.
- Encryption, digital signatures, and cryptographic providers.
- Database connections, HTTP clients, DNS, and networking.
- Timezones, locales, date/time formatting, and character encoding.
- Serialization and data compatibility across versions.
- Garbage collection, heap usage, and CPU usage.
- Agents, profilers, monitoring, and native libraries.
- Packaging of JARs, runtime images, or application installers.

Run smoke tests in a staging environment configured closely to production. If the application has performance requirements, compare latency, throughput, CPU, and memory against the pre-update baseline.

### 9.4. Verifying Bytecode and Target APIs

If using a new JDK to compile for an older runtime, check the release configuration and test on the actual target runtime.

Example:

```bash
javac --release 17 -d out src/com/example/Main.java
```

`--release 17` instructs the compiler to use the language features, bytecode, and public APIs of Java 17. However, you still need to test the application on an actual Java 17 runtime to catch runtime or dependency differences.

## 10. Phased Rollout

For critical systems, update in phases rather than changing all machines at once.

A controlled rollout process:

1. **Developer workstation:** update one test machine and verify the IDE, terminal, and build.
2. **CI:** update a representative pipeline or job; run full builds and tests.
3. **Staging:** deploy the application using the new JDK in a production-like environment.
4. **Canary or small group:** if the architecture allows, update a subset of instances and monitor errors, logs, and metrics.
5. **Production rollout:** expand after metrics and tests meet the agreed criteria.
6. **Post-deployment review:** monitor alerts, performance, application errors, and connection issues over an appropriate period.

Define acceptance criteria and rollback conditions in advance. For example: builds and tests must pass, no new startup errors occur, error rates do not increase significantly, and performance stays within agreed thresholds.

## 11. Preparing a Rollback Plan

A safe update plan always includes a way to revert to a version known to work well.

Before deploying:

- Retain the old JDK installer or archive according to retention policy.
- Keep the old JDK directory intact during the validation period for the new release.
- Record `JAVA_HOME`, `PATH`, and IDE/build configurations before making changes.
- Record container image tags or digests before updating.
- Ensure CI can re-run with the old JDK.
- Identify the owner and the conditions that trigger a rollback.

If a critical issue occurs, revert to the recorded JDK configuration and image. Then re-verify `java --version`, the compiler, and Maven/Gradle, and run smoke tests to ensure the rollback has actually taken effect.

Do not uninstall the old JDK or delete old caches, images, and configurations immediately after installing the new release. Maintain rollback readiness until the update is confirmed stable.

Note: Rolling back the JDK does not automatically revert data changes already written by the application. If the update was accompanied by application or schema changes, a separate rollback plan is needed for those components.

## 12. Updating the JDK in CI and Containers

CI and container environments are common places for discrepancies between developer machines and production.

For CI:

- Use an explicitly declared JDK version in the pipeline.
- Check both the JDK running the agent and the JDK compiler toolchain.
- Avoid relying on aliases that change over time if reproducible builds are required.
- Run tests on the supported production runtime version.
- Archive build results and the JDK version for traceability when errors occur.

For Docker:

- Choose a base image with the right vendor, feature release, and operating system.
- When high reproducibility is required, pin the image digest instead of relying only on a floating tag.
- Update images according to the security maintenance schedule.
- Rebuild the application image and verify OS-dependent native layers or agents.
- Do not assume a running container uses the same JDK as the host machine.

Example of checking the JDK inside a running container:

```bash
docker exec <container-name> java --version
```

This command runs the Java launcher inside the container. Replace `<container-name>` with the actual container name or ID.

## 13. Common Errors When Updating the JDK

| Symptom | Common Cause | Resolution |
|---|---|---|
| `java --version` still shows the old version | `PATH` prioritizes the old JDK directory or the terminal has not been reopened | Check `PATH` order and open a new terminal |
| `javac` does not match `java` version | The two commands are resolved from different directories | Check paths of both commands and align the JDK |
| Maven or Gradle still uses the old JDK | The build tool has its own JVM or toolchain configuration | Check `mvn -version`, `gradlew --version`, and toolchains |
| IDE does not recognize the new JDK | Project SDK or build runner has not been updated | Select the new JDK and reload the project |
| Installer fails or cannot install | Wrong architecture, installation permissions, package conflict, or corrupted download | Verify checksum, OS, architecture, and vendor instructions |
| Application fails to start | Incompatible dependency, agent, native library, or configuration | Read the stack trace, release notes, and inspect affected components |
| TLS or HTTPS connections fail | Truststore, certificates, algorithms, or security policies changed | Check the certificate chain, truststore, and TLS configuration |
| Performance changes after update | Differences in GC, JIT, workload, or runtime configuration | Compare metrics and profiles against the baseline |
| Rolled back but still running the new JDK | `PATH`, IDE, daemon, or container still uses the old configuration | Inspect each process and restart necessary components |

A common mistake is checking only the terminal version while ignoring the JVM launched by the IDE or build daemon. Verify in the exact environment where the application actually runs.

## 14. Checklist for a JDK Update

You can use the following checklist for each maintenance cycle:

- [ ] Identify the reason for the update and the target version.
- [ ] Confirm the vendor, feature release, update version, and architecture.
- [ ] Read the release notes and security advisories.
- [ ] Record the current JDK, paths, and configurations.
- [ ] Check compatibility requirements of frameworks, libraries, and plugins.
- [ ] Download the installer from a trusted source.
- [ ] Verify the checksum or digital signature.
- [ ] Install the new release in a way that preserves the old release.
- [ ] Update `JAVA_HOME`, `PATH`, IDE, and build toolchains.
- [ ] Verify `java`, `javac`, Maven, and Gradle.
- [ ] Run a clean build, unit tests, and integration tests.
- [ ] Run smoke tests and performance checks on staging.
- [ ] Update CI and container images.
- [ ] Roll out in phases and monitor metrics.
- [ ] Confirm rollback conditions and keep the old JDK for the required period.
- [ ] Record the results, final version, and update date.

## 15. Summary

Updating the JDK safely is more than just running a new installer. You need to know exactly which JDK is currently in use, verify the source and integrity of the installer, read the release notes, check compatibility, and verify that the application works on the new runtime.

Key principles:

- Distinguish patch updates from feature upgrades and vendor changes.
- Record the current state before making changes.
- Download the JDK from a trusted source and verify the checksum or signature.
- Keep the old release so you can roll back during the validation phase.
- Properly update configurations for the terminal, IDE, Maven, Gradle, CI, and containers.
- Run builds, tests, smoke tests, and performance checks.
- Roll out in phases, monitor post-deployment, and document the results.

This process helps Java teams adopt JDK patches and improvements while maintaining control over compatibility, reproducibility, and system stability.
