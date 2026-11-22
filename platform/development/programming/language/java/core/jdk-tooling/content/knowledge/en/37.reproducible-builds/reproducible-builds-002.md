# Pinning the Exact JDK Version for Java Builds

Pinning a JDK version means every build machine uses the exact same identified JDK build, rather than merely requesting "Java 17" or "latest Java". A JDK must be identified by multiple pieces of information: Java feature/update/build version, distribution/vendor, VM implementation, operating system, CPU architecture, package type, and installer checksum.

For example, two machines may both report Java 17, but one uses Temurin 17.0.15 while the other uses Corretto 17.0.15+6-LTS. They share the same feature version, yet come from different distributions and may be different builds. If the compiler, annotation processor, or runtime has behavior that depends on a patch or vendor, build and test results can differ.

JDK pinning is one part of reproducible builds. It clearly defines the compiler/runtime, but you still need to pin Gradle/Maven, plugins, dependencies, container images, OS/architecture, and other environmental factors.

## 1. What Needs to Be Pinned for a JDK?

A JDK installation can be described by the following fields:

| Attribute | Example | Why it is needed |
|---|---|---|
| Feature version | `17` | Selects the main Java release line |
| Full runtime version | `17.0.15+6-LTS` | Distinguishes update and build |
| Distribution/vendor | Amazon Corretto | Distinguishes packaging and vendor patches |
| VM implementation | HotSpot | Distinguishes HotSpot, OpenJ9, and other VMs |
| Vendor build/version | `Corretto-17.0.15.6.1` | Identifies the specific vendor build |
| OS and architecture | Windows x64, Linux amd64, Linux arm64 | Selects the right binary |
| libc/platform variant | glibc or musl | Avoids using an incompatible package |
| Package type | JDK, JRE, JDK with jmods | Ensures required compiler/tools are present |
| Archive checksum | SHA-256 of the downloaded file | Verifies the exact installer |
| Container image digest | `sha256` of the image manifest | Pins the image containing the JDK |

Do not just record "Java 17". If build reproducibility is required at the patch/build level, specify both the runtime version and the vendor. If you need to prove the binaries are identical, the checksum or image digest is the final verification layer.

### 1.1. Reading Java's Version String

Since Java 9, the version number follows the format:

~~~text
FEATURE.INTERIM.UPDATE.PATCH
~~~

The components mean:

- `FEATURE`: feature release, for example 17 or 21.
- `INTERIM`: interim release.
- `UPDATE`: compatible update release, typically containing bug fixes and security fixes.
- `PATCH`: emergency patch release.
- The part after `+` is the build number; information after `-` may contain additional vendor-specific identifiers.

For example, `17.0.15+6-LTS` has feature 17, update 15, build 6, and additional information `LTS`. Vendors may format the additional part differently.

### 1.2. Distinguishing Version Properties

| Command/Property | Content |
|---|---|
| `java --version` | Version, vendor, runtime, and VM |
| `javac --version` | Compiler version, usually showing only the version number |
| `java.version` | Product version |
| `java.runtime.version` | Full runtime version, including the build identifier |
| `java.vm.name` | VM name |
| `java.vm.version` | VM version |
| `java.vendor` | Vendor string provided by the runtime |
| `os.arch` | Architecture reported by the JVM |
| `java.home` | Directory of the running Java runtime |

For the Corretto JDK used in the hands-on example:

~~~text
java.version = 17.0.15
java.runtime.version = 17.0.15+6-LTS
java.vendor = Amazon.com Inc.
java.vm.name = OpenJDK 64-Bit Server VM
java.vm.version = 17.0.15+6-LTS
os.arch = amd64
~~~

Note: Gradle may normalize the vendor to `Amazon Corretto`, whereas the JVM system property returns `Amazon.com Inc.`. These are two different metadata fields. When writing checks, compare the right type of value against its corresponding source.

You can view system properties without writing any code:

~~~bash
java -XshowSettings:properties -version
~~~

In the output, look for `java.version`, `java.runtime.version`, `java.vendor`, `java.vm.version`, `java.home`, and `os.arch`.

A JDK also has a `release` file directly in its installation directory. This file usually contains `JAVA_VERSION`, `IMPLEMENTOR`, `IMPLEMENTOR_VERSION`, `OS_ARCH`, and other build metadata. It is a useful diagnostic source when identifying an installed package.

## 2. Major Version Pinning vs. Exact Build Pinning

The declarations below vary in strictness:

| Configuration | Pin level | Limitation |
|---|---|---|
| `17` | Feature version | Allows many Java 17 updates/builds |
| `17.0` | Feature/interim | Does not fully specify update/build |
| `17.0.15` | Version up to update | Does not specify build number or vendor |
| `17.0.15+6-LTS` | Full runtime version | Still needs vendor, package, OS, and binary specified |
| Vendor + full runtime version + checksum | Very strict | Requires artifact management and pin updates |
| Container image digest containing a verified JDK | Pins image bytes | Depends on platform/manifest and image provenance |

A version file containing only `17` can be useful for selecting a consistent feature version, but it is not enough to reproduce a build that requires an exact patch. Similarly, a container tag like `jdk:17` or `jdk:17.0.15` can still be updated or moved by the provider. The image digest is an immutable identifier for the image contents.

### 2.1. Version Files in the Repository

You can store the full version in `.java-version`:

~~~text
17.0.15+6
~~~

This file indicates the desired version, but does not specify the vendor on its own. Therefore, CI and JDK management tools still need to declare the distribution, for example `corretto`.

GitHub Actions `setup-java` supports reading `.java-version`, `.tool-versions`, and `.sdkmanrc` via `java-version-file`. If the file only contains a version, configure the distribution separately to avoid each machine picking a different vendor.

A project manifest should record at a minimum:

- Distribution and vendor.
- Full `java.runtime.version`.
- VM implementation/version.
- OS/architecture/package variant.
- SHA-256 of the archive or digest of the image.
- Download source and signature verification policy.

Do not put a single developer's `JAVA_HOME` path into a shared manifest. Installation paths can differ across Windows, Linux, macOS, and CI; version/vendor/checksum are what can be cross-checked across machines.

## 3. Installing and Verifying a Local JDK

Download the JDK from the vendor's official website/repository and choose the right OS, architecture, and package type. Extract it into a directory whose name includes the full version, for example:

~~~text
/opt/jdks/amazon-corretto-17.0.15.6
~~~

On Windows, you can use a dedicated path such as:

~~~text
C:\jdks\amazon-corretto-17.0.15.6
~~~

Avoid using a generic directory like `C:\Java\current` if it gets silently replaced during updates. A versioned path makes it clear which package the build is using.

### 3.1. Setting JAVA_HOME Temporarily

PowerShell:

~~~powershell
$env:JAVA_HOME = "C:\jdks\amazon-corretto-17.0.15.6"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

java --version
javac --version
~~~

Linux/macOS:

~~~bash
export JAVA_HOME=/opt/jdks/amazon-corretto-17.0.15.6
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
~~~

The paths are examples only; point to the verified JDK directory on your machine. Open a new terminal after changing user/system-level environment variables.

### 3.2. Verifying the Archive Checksum

After downloading the file, compute its SHA-256:

PowerShell:

~~~powershell
Get-FileHash .\amazon-corretto-17.0.15-windows-x64.zip -Algorithm SHA256
~~~

Linux:

~~~bash
sha256sum amazon-corretto-17.0.15-linux-x64.tar.gz
~~~

macOS:

~~~bash
shasum -a 256 amazon-corretto-17.0.15-macosx-x64.tar.gz
~~~

If the vendor publishes a digital signature, verify the signature using a public key obtained from an official source, for example:

~~~bash
gpg --verify jdk-archive.tar.gz.asc jdk-archive.tar.gz
~~~

Compare the checksum against the value published by the vendor for the exact file, version, OS, and architecture. Do not treat a checksum fetched from the same untrusted mirror as independent proof of authenticity.

After verification, store the checksum alongside the release information or place the archive in a controlled internal artifact repository. When reinstalling, fetch the exact verified artifact rather than downloading a file with the same name from an arbitrary source.

## 4. Pinning the JDK in Gradle

Gradle Java Toolchains are very useful for selecting the JDK for compilation, testing, execution, and Javadoc. However, it is important to understand the API's limitations:

- `languageVersion` selects the Java feature version, for example 17.
- `vendor` selects the vendor recognized by Gradle.
- `implementation` selects the VM type such as HotSpot or OpenJ9.
- `JavaToolchainSpec` does not have a dedicated property to require an exact `java.runtime.version` or build number.

Therefore, configuring `languageVersion = 17` and `vendor = AMAZON` is not enough to pin `17.0.15+6-LTS`. Gradle might select another JDK that still satisfies the major version and vendor. For an exact pin, restrict the set of JDKs Gradle can discover to the managed installation and verify the full runtime version during the build.

### 4.1. Selecting Major Version and Vendor

In `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.AMAZON)
    }
}
~~~

The configuration above selects an Amazon JDK 17. It does not restrict the update or build number on its own.

### 4.2. Exposing Only the Pinned JDK to Gradle

In the project's `gradle.properties`:

~~~properties
org.gradle.java.installations.auto-detect=false
org.gradle.java.installations.auto-download=false
org.gradle.java.installations.paths=/opt/jdks/amazon-corretto-17.0.15.6
~~~

On Windows, use the local JDK path:

~~~properties
org.gradle.java.installations.auto-detect=false
org.gradle.java.installations.auto-download=false
org.gradle.java.installations.paths=C:/jdks/amazon-corretto-17.0.15.6
~~~

When auto-detection and auto-download are disabled, Gradle is only allowed to use toolchains from the declared paths. The path must point to a JDK installation directory containing `bin/java` and `bin/javac`.

This prevents Gradle from picking a different JDK on a developer machine or runner. It also means each machine/runner must have the exact JDK installed before building.

You can check which toolchains Gradle detects with:

~~~bash
./gradlew -q javaToolchains
~~~

### 4.3. Checking the Full Runtime Version in the Build

Gradle provides `JavaInstallationMetadata.javaRuntimeVersion`, which contains the full runtime version including the build number. The `vendor` metadata is the vendor name normalized by Gradle; it does not necessarily match `System.getProperty("java.vendor")`.

In `gradle.properties`, store the version and vendor name returned by Gradle:

~~~properties
jdkRuntimeVersion=17.0.15+6-LTS
jdkGradleVendor=Amazon Corretto
~~~

Add a verification task in `build.gradle.kts`:

~~~kotlin
val expectedRuntime = providers.gradleProperty("jdkRuntimeVersion")
val expectedVendor = providers.gradleProperty("jdkGradleVendor")

tasks.withType<JavaCompile>().configureEach {
    inputs.property("pinnedJdkRuntimeVersion", expectedRuntime)
}

tasks.withType<Test>().configureEach {
    inputs.property("pinnedJdkRuntimeVersion", expectedRuntime)
}

tasks.withType<JavaExec>().configureEach {
    inputs.property("pinnedJdkRuntimeVersion", expectedRuntime)
}

tasks.register("verifyPinnedJdk") {
    // Metadata version is checked at every build invocation.
    outputs.upToDateWhen { false }

    doLast {
        val compiler = javaToolchains.compilerFor {
            languageVersion.set(JavaLanguageVersion.of(17))
            vendor.set(JvmVendorSpec.AMAZON)
        }.get()

        val launcher = javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
            vendor.set(JvmVendorSpec.AMAZON)
        }.get()

        listOf(
            "COMPILER" to compiler.metadata,
            "LAUNCHER" to launcher.metadata
        ).forEach { (role, metadata) ->
            check(metadata.javaRuntimeVersion == expectedRuntime.get()) {
                role + " expected " + expectedRuntime.get() +
                    " but found " + metadata.javaRuntimeVersion
            }

            check(metadata.vendor == expectedVendor.get()) {
                role + " expected Gradle vendor " + expectedVendor.get() +
                    " but found " + metadata.vendor
            }

            println(role + "_RUNTIME_VERSION=" + metadata.javaRuntimeVersion)
            println(role + "_GRADLE_VENDOR=" + metadata.vendor)
        }
    }
}
~~~

The task checks both the compiler and the launcher. If a machine has Java 17 but the wrong update or build, the task will fail. When the expected version changes, that declaration also becomes an input of the compile, test, and `JavaExec` tasks so changing the pin invalidates the corresponding up-to-date/build cache results.

This point matters because Gradle marks the full runtime version/vendor in `JavaInstallationMetadata` as internal metadata; you should not assume patch/build numbers automatically participate in every task cache key. Declare the pin as a task input and run the exact-version check on every build.

Successful check output on Gradle 9.2.1 with Corretto 17.0.15+6-LTS:

~~~text
COMPILER_RUNTIME_VERSION=17.0.15+6-LTS
COMPILER_GRADLE_VENDOR=Amazon Corretto
LAUNCHER_RUNTIME_VERSION=17.0.15+6-LTS
LAUNCHER_GRADLE_VENDOR=Amazon Corretto
~~~

You can test that the guard rejects a different version by running the task with an incorrect expected version:

~~~bash
./gradlew -PjdkRuntimeVersion=17.0.15+99 verifyPinnedJdk
~~~

Expected error output:

~~~text
COMPILER expected 17.0.15+99 but found 17.0.15+6-LTS
~~~

The build must fail when the runtime version does not match. Do not ignore this error or change the expected version just to make the build green; install the pinned JDK or update the pin through the review process.

### 4.4. Verifying the Gradle Daemon Separately

The project toolchain does not determine which JVM runs the Gradle Daemon. If you also need to pin the Daemon, launch Gradle with `JAVA_HOME` pointing to the verified JDK or set `org.gradle.java.home` to the exact installation.

Gradle's Daemon JVM criteria can pin the Java feature version and vendor, but it does not replace checking the full patch/build version. After changing the JDK path, stop the old daemon:

~~~bash
./gradlew --stop
./gradlew --version
~~~

`./gradlew --version` displays the Gradle version and the JVM running Gradle. Also use `java --version` or a runtime identity probe to confirm the full version.

### 4.5. Pinning the Gradle Wrapper

The JDK is not the only component of the build environment. Use the Gradle Wrapper to pin the Gradle distribution in `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.2.1-bin.zip
~~~

You can add `distributionSha256Sum` from Gradle's official checksums page to verify the downloaded Wrapper archive. The Gradle Wrapper version and the JDK version are two separate pins.

## 5. Pinning the JDK in Maven

Maven can run on one JDK while using a different JDK as the toolchain for the compiler, Surefire, Failsafe, and other toolchain-aware plugins.

Maven Toolchains use two parts:

1. `toolchains.xml` describes the JDKs installed on the machine and their version/vendor.
2. `maven-toolchains-plugin` in the POM requests a matching toolchain.

### 5.1. Declaring the JDK in toolchains.xml

The default file is located at `~/.m2/toolchains.xml`. Example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17.0.15+6-LTS</version>
            <vendor>Amazon.com Inc.</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/amazon-corretto-17.0.15.6</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

`jdkHome` must point to the exact verified JDK. `version` and `vendor` are the tokens Maven matches against.

### 5.2. Requiring the Exact Version in the POM

Example configuration for the Maven Toolchains Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>17.0.15+6-LTS</version>
                <vendor>Amazon.com Inc.</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

For a single version, Maven requires the value in the POM to match the token in `toolchains.xml` exactly. For example, version `17` does not match token `17.0.15`; a version range like `[17,18)` can match more builds. If you need an exact patch/build, use the full version string in both places.

Vendor is also matched exactly, case-insensitively. If CI generates `toolchains.xml` automatically, check the vendor/version values generated by the tool before setting the requirement in the POM. For example, GitHub `setup-java` may write a distribution name like `corretto`, whereas a file generated by Maven discovery may write `java.vendor` like `Amazon.com Inc.`.

### 5.3. Maven Runtime and Maven Toolchain Are Two Different JDKs

`mvn --version` shows the JDK running Maven. The toolchain selected afterward can be a different JDK. Check both:

~~~bash
mvn --version
mvn -t ~/.m2/toolchains.xml -B -ntp clean verify
~~~

On Windows, use the appropriate toolchains file path for the machine. Do not commit a `toolchains.xml` containing a single developer's absolute paths to the repository; CI should generate the file from the installed JDK or mount a separate toolchain configuration.

If you use `maven-compiler-plugin`, also configure `release` to constrain the target API and bytecode. `maven.compiler.release` does not replace Maven Toolchains and does not pin the JDK patch.

## 6. Pinning the JDK in GitHub Actions CI

GitHub Actions `setup-java` lets you select a specific distribution and version. Example with Amazon Corretto:

~~~yaml
steps:
  - uses: actions/checkout@v4

  - name: Install pinned JDK
    id: setup-java
    uses: actions/setup-java@v6
    with:
      distribution: corretto
      java-version: '17.0.15+6'
      force-download: true
      cache: gradle

  - name: Verify JDK identity
    run: |
      java --version
      javac --version
      java -XshowSettings:properties -version

  - name: Build
    run: ./gradlew --no-daemon clean check
~~~

`java-version` supports specific versions in JEP 322 format, including update and build numbers. `force-download: true` forces a fresh download of the JDK instead of using one already in the tool cache. `setup-java` automatically verifies checksums when the distribution publishes official checksums; package signature verification depends on the distribution.

In strict security workflows, pin the GitHub Action itself by a reviewed full commit SHA instead of only a major tag like `v6`. The action version and the JDK version are two independent components to manage.

### 6.1. Using a Shared Version File

You can read the version from `.java-version`:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: corretto
    java-version-file: .java-version
    force-download: true
~~~

The `.java-version` file lets developers and CI read the same version. The vendor still must be specified separately via `distribution`. If you share a version file across multiple tools, verify that all version managers understand the same version syntax.

### 6.2. Verifying the Installed Version

The action exposes a `version` output containing the actual version installed. Print that output to the logs and cross-check it against `java.runtime.version`, vendor, and architecture. Do not look only at the input `17.0.15+6`; verify the actual JDK after the action finishes.

If the build runs across multiple OSes/architectures, pin each corresponding package separately and keep the matrix explicit.

## 7. Pinning the JDK in Docker/Containers

A Docker image tag is convenient for selecting a version, but tags can be updated. A `sha256` digest identifies immutable image contents.

To get the digest of a pulled image:

~~~bash
docker pull amazoncorretto:17.0.15
docker image inspect --format '{{index .RepoDigests 0}}' amazoncorretto:17.0.15
~~~

The second command returns the repository digest. Use that exact full digest string in the `FROM` line of your Dockerfile so builds always reference the same image content. Do not invent or guess digests.

For multi-stage builds, pin both the builder and runtime images. If the build must be reproducible across multiple CPUs, pin the platform such as `linux/amd64` or `linux/arm64` and use the matching manifest digest. A multi-architecture manifest digest and a platform-specific image digest have different scopes; specify the platform explicitly in the pipeline.

An image digest pins the entire image filesystem, including the JDK, OS libraries, and other files. This is stronger than pinning `java.runtime.version` alone, though you still need to record the image source, signature/provenance, and image update process.

## 8. Java Identity Probe: Checking the JDK at Runtime

A small program can verify the exact runtime before running a workload or during a smoke test. Create `JdkIdentityProbe.java`:

~~~java
public final class JdkIdentityProbe {
    public static void main(String[] args) {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Expected runtime version, vendor and architecture"
            );
        }

        String version = System.getProperty("java.runtime.version");
        String vendor = System.getProperty("java.vendor");
        String arch = System.getProperty("os.arch");

        System.out.println("JAVA_VERSION=" + System.getProperty("java.version"));
        System.out.println("JAVA_RUNTIME_VERSION=" + version);
        System.out.println("JAVA_VENDOR=" + vendor);
        System.out.println("JAVA_VM_VERSION=" + System.getProperty("java.vm.version"));
        System.out.println("OS_ARCH=" + arch);

        if (!version.equals(args[0])
                || !vendor.equals(args[1])
                || !arch.equals(args[2])) {
            throw new IllegalStateException(
                "JDK identity does not match the pinned values"
            );
        }

        System.out.println("JDK_PIN=PASS");
    }
}
~~~

Compile and run with the pinned JDK:

~~~powershell
$JdkHome = "C:\jdks\amazon-corretto-17.0.15.6"

& "$JdkHome\bin\javac.exe" --release 17 -d out JdkIdentityProbe.java
& "$JdkHome\bin\java.exe" -cp out JdkIdentityProbe "17.0.15+6-LTS" "Amazon.com Inc." "amd64"
~~~

Output from testing with Amazon Corretto 17.0.15+6-LTS on Windows x64:

~~~text
JAVA_VERSION=17.0.15
JAVA_RUNTIME_VERSION=17.0.15+6-LTS
JAVA_VENDOR=Amazon.com Inc.
JAVA_VM_VERSION=17.0.15+6-LTS
OS_ARCH=amd64
JDK_PIN=PASS
~~~

The probe checks the executing runtime. If a build compiles with one JDK and runs tests with another, you need to check both the compiler toolchain and the test launcher/toolchain as in the Gradle example earlier.

## 9. Checksums, Signatures, and Provenance

A version string identifies a JDK, but it does not prove the installer file is an untampered binary from the vendor. For builds requiring supply-chain control:

1. Obtain the JDK from an official release source or an internal artifact repository.
2. Select the right version, vendor, OS, architecture, and package type.
3. Download the checksum from trusted release metadata.
4. Verify the SHA-256 before extracting.
5. Verify the digital signature if the vendor provides a signature and public key.
6. Record the checksum, URL/source, version, and download timestamp in an artifact record.
7. Never replace a stored archive with another file of the same name.
8. In CI, record the container image digest and JDK source.

A checksum only proves the downloaded file matches the checksum value you trust. If both the file and the checksum come from a compromised source, the checksum alone is not enough to prove origin. Digital signatures and provenance provide stronger verification of the publisher.

## 10. JDK Pinning and Reproducible Builds

Pinning the JDK is a necessary condition, but it does not guarantee every build produces byte-for-byte identical artifacts. Other factors can cause outputs to differ:

| Component | How to control |
|---|---|
| Gradle/Maven version | Use the Wrapper and pin the distribution |
| Plugin versions | Declare explicit versions; avoid dynamic versions |
| Dependencies | Gradle dependency locking/verification or Maven dependency management |
| Compiler JDK | Pin full runtime version, vendor, installation path, and checksum |
| Annotation processors | Pin versions and configuration |
| OS/architecture | Use runners/container images with explicit digests and platforms |
| Locale/timezone | Configure consistently |
| Environment variables | Explicitly declare variables that affect the build |
| Timestamps/archive metadata | Use reproducible archive mechanisms and fixed timestamps if supported by plugins |
| Native tools | Pin compiler, linker, and package versions separately |

`--release` helps control the target language/API/bytecode, but it does not select a specific JDK. `sourceCompatibility` and `targetCompatibility` also do not pin the vendor or patch version. You need to combine toolchains, exact-version guards, and compiler options.

## 11. Safe Process for Updating a JDK Pin

You should not keep a pinned JDK forever. Pin precisely so builds are reproducible; update on a schedule to receive security fixes and bug fixes.

A controlled update process:

1. Select a JDK update released by the vendor and approved by the organization.
2. Record the full runtime version, vendor, implementation, architecture, and package.
3. Verify the archive checksum/signature or image digest.
4. Update `.java-version`, manifests, Gradle/Maven toolchains, and CI.
5. Update the expected runtime version in the exact-version guard.
6. Run a clean build, unit/integration tests, and smoke tests on the new JDK.
7. Compare artifacts, class-file versions, test output, and performance baselines where appropriate.
8. Store SBOM/provenance and document the reason for the upgrade.
9. Merge the new pin after CI confirms it passes.
10. Retain old pin information to reproduce past releases when investigating issues.

Do not switch from a pinned version to `latest` to receive patches automatically. Have a pull request update the pin, checksum, and image digest so reviewers can see exactly which JDK changed.

## 12. Common Issues and Troubleshooting

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Both machines run Java 17 but builds differ | Different update/build/vendor | Compare `java.runtime.version`, vendor, and checksum |
| `java --version` is right but compiler differs | `PATH` points to a `javac` outside `JAVA_HOME` | Use `JAVA_HOME/bin/javac`, check `Get-Command javac` or `which javac` |
| Gradle picks the wrong patch within the same major | Toolchain spec only requests major/vendor | Restrict installation paths and check `JavaInstallationMetadata.javaRuntimeVersion` |
| Gradle task does not rerun after changing patch | Patch metadata is not treated as an explicit input of every task | Add full runtime version to task inputs and run an exact-version guard |
| Gradle cannot find a JDK after disabling auto-detection | Wrong installation path or no valid JDK | Check `org.gradle.java.installations.paths`, `bin/java`, and `bin/javac` |
| Maven reports no matching toolchain | Version/vendor token does not match exactly | Compare the POM with `toolchains.xml`, including the build suffix |
| Maven runs on the right JDK but compiler is wrong | Maven runtime and compiler toolchain are two different JVMs | Check toolchain plugin selection and `mvn --version` |
| CI picks a newer version than expected | Only major version requested or `latest` used | Use an exact version and verify action output/runtime properties |
| Docker build changes even though tag is unchanged | Registry moved the tag to a different digest | Pin repository digest and platform |
| Checksum mismatch | Corrupted download, wrong architecture, or altered file | Re-download from official source, verify signature and release metadata |
| Installed JDK is actually a JRE | Package lacks `javac`/Javadoc | Install the proper JDK package |
| Same version but different binaries | Different vendor build or archive bytes | Compare vendor/build metadata and SHA-256 |
| Build cache returns stale output | Cache key does not include the exact JDK pin | Add full runtime version to task inputs/cache key and update key when upgrading |

### 12.1. Quick Diagnostic Commands

Check Java runtime and compiler in the shell:

~~~bash
java --version
javac --version
java -XshowSettings:properties -version
~~~

PowerShell:

~~~powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
Get-FileHash "$env:JAVA_HOME\release" -Algorithm SHA256
~~~

Gradle:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew verifyPinnedJdk
~~~

Maven:

~~~bash
mvn --version
mvn -t ~/.m2/toolchains.xml -B -ntp validate
~~~

Docker:

~~~bash
docker image inspect --format '{{index .RepoDigests 0}}' amazoncorretto:17.0.15
~~~

Compare runtime version, vendor, path, and digest together. `java --version` alone is not enough to verify the compiler, test toolchain, or image used in another build step.

## 13. Pre-Lockdown JDK Pinning Checklist

- [ ] Full feature, update, and build numbers are recorded.
- [ ] Distribution/vendor and VM implementation are specified.
- [ ] Correct OS, architecture, libc variant, and package type are selected.
- [ ] JDK archive checksum/signature is verified.
- [ ] Version pin is stored in the repository or build manifest.
- [ ] Gradle toolchain is restricted to the verified installation.
- [ ] Gradle exact-version guard checks both compiler and launcher metadata.
- [ ] Full JDK version is included in task inputs/cache keys where needed.
- [ ] Maven toolchains version/vendor match `toolchains.xml` exactly.
- [ ] Gradle/Maven runtime JVM is pinned separately if the build engine also needs an exact JDK.
- [ ] CI installs the right distribution and exact version, then verifies runtime identity.
- [ ] Container images are pinned by digest and explicit platform.
- [ ] Gradle/Maven Wrapper and plugin versions are also pinned.
- [ ] A schedule exists for security patch updates with new checksums/digests.
- [ ] Builds can be reproduced from stored archives/images without relying on floating tags.

## 14. Key Takeaways

Pinning a JDK for reproducible builds requires specifying the full runtime/build version, vendor, implementation, architecture, and binary checksum. A major version like Java 17 only identifies the feature release and does not distinguish different patches or builds.

Gradle Toolchains select major version and vendor/implementation; to pin an exact patch, restrict JDK installation paths, check `JavaInstallationMetadata.javaRuntimeVersion`, and include the full version in task inputs. Maven Toolchains can match exact full version tokens. CI must select the exact distribution/version, and containers should be pinned by image digest.

Pinning does not mean stopping updates. Update the JDK through a controlled review process, changing the version, checksum, and digest together and re-running builds and tests. This lets the team reproduce older builds while still moving proactively to new security patches.

References:

- [JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322)
- [Runtime.Version — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html)
- [Gradle Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle JavaInstallationMetadata API](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaInstallationMetadata.html)
- [Gradle JavaToolchainSpec API](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaToolchainSpec.html)
- [Maven Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Maven Toolchains Plugin Usage](https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html)
- [GitHub Actions setup-java](https://github.com/actions/setup-java)
- [Docker Docs — Validate image inputs and require digests](https://docs.docker.com/build/policies/validate-images/)
