# Skipping Artifact Verification: Verifying a JAR Before Release and Deployment

**Skipping artifact verification** is an anti-pattern that occurs when a team treats a successful build as proof that the generated file is correct and ready for release. A build can compile and pass unit tests while the final JAR is still missing classes or resources, has an incorrect manifest, uses incompatible bytecode, contains unexpected dependencies, gets corrupted during upload, or differs from the file that was tested.

An artifact is the concrete output of the build process: a JAR, WAR, ZIP distribution, runtime image created by jlink, installer created by jpackage, native executable, or container image. Users and production environments receive this artifact, so you must verify the exact file or image that will be released.

The key principle is **testing and verifying the exact artifact that will be deployed**. Record the artifact identity, inspect its structure and metadata, confirm integrity, run smoke tests on the packaged bundle, and only then sign, upload, or release it.

## 1. Why Is Skipping Artifact Verification Dangerous?

Unit tests usually run against classes and resources in the project's build directory. They do not necessarily run against the actual JAR after Maven/Gradle packages it. Packaging plugins, resource filtering, shading, manifests, classifiers, module descriptors, and copy/upload steps can all alter the output.

Some failures only appear after packaging:

- The JAR is missing Main-Class, preventing `java -jar` from launching.
- Resources or configuration files are not included in the archive.
- META-INF/services is lost or overwritten when creating a fat JAR.
- The JAR carries an old version because the pipeline picked the wrong file from `target/` or `build/`.
- The artifact was built with a newer JDK than the production runtime supports.
- Dependencies are missing, have duplicate classes, or are packaged incorrectly.
- The file is truncated, corrupted, or altered during storage, upload, or download.
- The file that was tested differs from the file that gets signed or deployed.
- The artifact has the right name and version but was built from the wrong commit.
- A dependency or binary was replaced in the repository.

A `BUILD SUCCESS` line only confirms that the tasks executed in the build completed under the current configuration. It does not prove on its own that all requirements for the artifact's contents, compatibility, provenance, and runnability are met.

## 2. Distinguishing Source, Intermediate Output, and Release Artifact

| Type | Example | Meaning |
|---|---|---|
| Source | src/main/java/... | Maintained source code |
| Compiled output | target/classes, build/classes/java/main | Classes and resources after compilation |
| Test output | target/test-classes, build/classes/java/test | Classes used for testing |
| Artifact | target/app-1.2.3.jar, build/libs/app-1.2.3.jar | File to be distributed or deployed |
| Release metadata | checksum, signature, SBOM, attestation | Evidence describing the artifact and how it was produced |

Unit tests on `target/classes` may PASS while the release JAR is missing `application.yml`. Similarly, inspecting individual source or class files does not prove that an uploaded ZIP/JAR file is intact.

After packaging, verify the artifact from the exact output path. When functional testing is needed, run the packaged JAR/WAR or distribution in a production-like environment.

## 3. Identifying the Artifact Before Verification

A single filename is not enough to identify a build. Record the necessary attributes:

- Artifact name and file type.
- Group, artifact, version, and classifier if using Maven coordinates.
- Commit or source revision.
- JDK/compiler version and target release.
- Build tool and packaging plugin version.
- Operating system, architecture, and build profile when relevant.
- File size and SHA-256.
- Build run, workflow, or release ID.
- Manifest, module name, or package version.

Example:

~~~text
groupId:       com.example
artifactId:    artifact-lab
version:       1.2.3
classifier:    none
extension:     jar
sourceCommit:  4f82a1c
javaRelease:   17
file:          artifact-lab-1.2.3.jar
~~~

If there are multiple files with the same name across different directories or jobs, record the exact path and hash to avoid picking the wrong one. Do not rely on a `latest.jar` name or a leftover file from a previous build.

## 4. Checking Existence, Size, and Path

The first step is to confirm that the expected file was actually created and is non-empty.

PowerShell:

~~~powershell
$artifact = 'target\artifact-lab-1.2.3.jar'
if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
    throw "Artifact not found: $artifact"
}

$file = Get-Item -LiteralPath $artifact
if ($file.Length -le 0) {
    throw "Artifact is empty: $artifact"
}

$file | Select-Object FullName, Length, LastWriteTimeUtc
~~~

Bash:

~~~bash
artifact="target/artifact-lab-1.2.3.jar"
test -s "$artifact" || {
  echo "Artifact missing or empty: $artifact" >&2
  exit 1
}
stat "$artifact"
~~~

A size of 0 is an obvious error; a non-zero size is still not enough. A file may exist yet contain a corrupted archive, a JAR from the wrong project, or an old build. You can set reasonable size thresholds for a product, but those thresholds must be based on the actual artifact and updated in a controlled manner.

## 5. Checking JAR and ZIP Structure

A JAR is based on the ZIP format. It contains entries such as classes, resources, and the `META-INF` directory. The `jar --list` command lets you view the list of entries:

~~~bash
jar --list --file target/artifact-lab-1.2.3.jar
~~~

Check for required components, for example:

~~~text
META-INF/MANIFEST.MF
com/example/HelloApp.class
application.yml
META-INF/services/com.example.Plugin
~~~

Entry names use `/` even when running on Windows. If the application requires service providers, native libraries, templates, or configuration files, verify that they are actually present in the archive.

`jar --list` shows which entries are declared in the archive. To test decompression and data CRCs, you can use:

~~~bash
unzip -t target/artifact-lab-1.2.3.jar
~~~

In Java, you can open each entry and read the entire stream to force the ZIP library to decompress and verify the CRC. For signed JARs, reading entries using a `JarFile` created with `verify=true` also triggers digest verification for signed entries.

Do not confuse listing entries with verifying every payload byte. An archive may list cleanly yet fail when reading a specific entry.

## 6. Checking the Manifest

The JAR manifest resides at `META-INF/MANIFEST.MF`. It contains metadata and certain configurations used by the Java launcher or runtime.

Example:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Implementation-Title: artifact-lab
Implementation-Version: 1.2.3
Build-Commit: 4f82a1c
~~~

Different attributes have different meanings:

- `Manifest-Version`: manifest format version.
- `Main-Class`: class containing the `public static void main(String[] args)` method to run with `java -jar`.
- `Implementation-Title` and `Implementation-Version`: implementation metadata provided by the publisher.
- `Specification-Version`: specification/package version when the project follows a convention for using it.
- `Automatic-Module-Name`: automatic module name when the JAR is used on the module path.
- `Class-Path`: list of additional libraries in manifest syntax.
- `Multi-Release: true`: marks a multi-release JAR with version-specific classes/resources.

`Implementation-Version` does not automatically prove the JAR contents match that version. It is metadata written by the build; it must be compared against the expected version/commit from the release pipeline.

Inspect the manifest with:

~~~bash
jar --extract --file target/artifact-lab-1.2.3.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

In PowerShell, replace `cat` with `Get-Content`. If you do not want to extract into the workspace, you can read the manifest via `java.util.jar.JarFile`.

## 7. Distinguishing Main-Class, Module Name, and Artifact Version

Three types of metadata are often confused:

- `Main-Class` identifies the entry point for `java -jar`.
- `Automatic-Module-Name` or `module-info.class` identifies the module identity when using the module path.
- `Implementation-Version` is the version metadata written into the manifest by the project.

A library JAR may not have a `Main-Class` because it is not a standalone application. A modular JAR has `module-info.class` yet may still not declare a main class. Do not mark QA as FAIL simply because a library JAR cannot be run with `java -jar`; check the artifact's actual contract.

For a modular JAR, inspect the module descriptor:

~~~bash
jar --describe-module --file target/library-1.2.3.jar
~~~

Check `exports`, `requires`, `uses`, and `provides` as well if the module API or service loading is part of the release contract.

## 8. Checking Class File Version and Java Compatibility

Bytecode has a class-file major version. A runtime that does not support that major version will throw `UnsupportedClassVersionError`.

Common milestones:

| Java release | Class-file major version |
|---:|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Use `javap -verbose` to inspect the class version:

~~~bash
javap -verbose -classpath target/artifact-lab-1.2.3.jar com.example.HelloApp
~~~

Look for the `major version` line. For Java 17, the value must be `61`.

Compiling with a newer JDK does not mean the artifact is compatible with an older runtime. Use `javac --release 17` or configure the corresponding compiler plugin/toolchain to verify syntax, bytecode, and Java SE APIs against the target release.

Example:

~~~bash
javac --release 17 -d classes src/com/example/HelloApp.java
~~~

Check at least one representative class; for complex products, inspect the entire artifact or use build tooling to ensure all modules target the same release. Multi-release JARs must be evaluated across each class branch under `META-INF/versions/`.

## 9. Checking Dependencies and Classpath

A JAR may contain application classes yet be missing runtime libraries. `jdeps` analyzes static dependencies of classes and JARs:

~~~bash
jdeps -s target/artifact-lab-1.2.3.jar
~~~

You can also use:

~~~bash
jdeps --jdk-internals target/artifact-lab-1.2.3.jar
~~~

`jdeps` helps detect package/module dependencies and usage of internal JDK APIs. This is static analysis; reflection, service loading, JNI, dynamically constructed class names, or runtime plugins may not appear completely.

Know what kind of package is being released:

- **Thin JAR:** contains application classes/resources; dependencies are provided via classpath or runtime launcher.
- **Fat/uber JAR:** bundles classes/resources from multiple dependencies.
- **Distribution ZIP:** contains JARs, libraries, scripts, and configuration.
- **Modular application:** uses module path and module descriptors.
- **Runtime image:** contains a custom runtime built with `jlink`.

If a fat JAR is required, verify that dependencies are actually inside the archive. If using a thin JAR, verify that the accompanying distribution or classpath includes all required libraries. Check `META-INF/services` after shading because improper merging of service files can drop providers.

## 10. Checking Application Resources and Contents

Some errors only appear at runtime because resources were not packaged:

- `application.properties`, YAML, or XML files.
- Templates, schemas, and migration files.
- Certificates or truststores packaged by design.
- Native libraries for each OS/architecture.
- Service provider configurations.
- Dependency licenses and notices.
- Default data files.

Cross-check the list of required resources against `jar --list`. For critical resources, write a smoke test that opens the resource via the classloader:

~~~java
try (var input = HelloApp.class.getResourceAsStream("/application.properties")) {
    if (input == null) {
        throw new IllegalStateException("application.properties is missing");
    }
}
~~~

Testing against source files on the filesystem does not guarantee the classloader can read the resource from the JAR. Run tests against the packaged artifact.

## 11. Verifying Behavior with a Smoke Test on the JAR

After inspecting the structure, run the artifact itself:

~~~bash
java -jar target/artifact-lab-1.2.3.jar
~~~

For applications with arguments, configuration, and dependencies, use a small set of inputs representing critical execution paths. Verify the exit code, required stdout/stderr, and expected side effects.

PowerShell example:

~~~powershell
$output = & java -jar $artifact --self-check 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Packaged application failed: $output"
}
$output
~~~

For a library without a main class, create a test harness or integration test that consumes the JAR as a dependency. The goal is to verify the public API and resources from the exact packaged file.

A smoke test does not replace unit/integration tests. It adds evidence that the distributed package actually starts or is consumed properly.

## 12. Hashes and Checksums: Verifying Integrity

SHA-256 produces a fingerprint of all bytes in a file. If a single byte changes, the hash will almost certainly differ.

PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath $artifact
~~~

Linux:

~~~bash
sha256sum "$artifact"
~~~

macOS:

~~~bash
shasum -a 256 "$artifact"
~~~

Compare hashes after upload/download:

~~~bash
sha256sum artifact-before-upload.jar
sha256sum artifact-after-download.jar
~~~

Both hashes must match if the two files have identical bytes. Also compute the hash after the signing step if signatures are added after the build, because signing a JAR modifies the archive.

**A checksum only confirms integrity when the expected value comes from an independent trusted source.** If both the artifact and the checksum file can be replaced together in an untrusted storage location, an attacker can replace both.

## 13. JAR Digital Signatures: Verifying the Publisher

JAR signing uses `jarsigner` to sign entries in the archive. During verification, the tool checks the signatures and digests of signed entries.

Sign using a PKCS12 keystore:

~~~bash
jarsigner -keystore release-signing.p12 -storetype PKCS12 app.jar release-key
~~~

Verify the signature and trust chain using a truststore containing verified public certificates:

~~~bash
jarsigner -verify -strict -keystore trusted-publishers.p12 -storetype PKCS12 app.jar
~~~

A `jar verified` message indicates that the signature was checked. In a release environment, you must also verify that the certificate or public key belongs to the right publisher according to your organization's trust process.

A JAR signed with a self-signed certificate can have a mathematically valid signature without proving the publisher's identity. Only trust a certificate after verifying its fingerprint through an independent channel and adding it to a managed truststore.

Never store private signing keys in a repository or CI logs. Use a secret store, HSM, or organization-managed signing service. Modifying any signed entry can invalidate the signature; sign last, after all packaging and archive modifications are complete.

## 14. Distinguishing Checksum, Signature, SBOM, and Provenance

| Evidence | Question Answered | Does Not Prove on Its Own |
|---|---|---|
| SHA-256 | Does the file have the exact expected bytes? | Who created the file |
| Digital signature | Was the file signed by a trusted key/certificate? | That the code is safe or vulnerability-free |
| SBOM | Which components/dependencies does the artifact declare? | That the artifact has valid provenance or wasn't tampered with |
| Build provenance/attestation | From which source, workflow, and environment was the artifact built? | That all code in the artifact is safe |
| Vulnerability scan | Do any components match known vulnerabilities? | That the artifact is the right version or runs correctly |

These verification layers complement one another. A file with a matching hash can still contain malicious code if the hash came from an untrusted source. A valid signature can still belong to an inappropriate publisher. A good SBOM helps inventory dependencies but does not replace content and runtime verification.

## 15. Verifying Provenance and Artifact Attestation

Provenance describes where an artifact was built and by what process. Useful details include repository, commit, workflow, builder identity, build parameters, and the artifact digest.

GitHub Actions can generate an artifact attestation after building:

~~~yaml
permissions:
  contents: read
  id-token: write
  attestations: write

steps:
  - name: Build
    run: ./mvnw --batch-mode clean verify

  - name: Attest release artifact
    uses: actions/attest@v4
    with:
      subject-path: target/artifact-lab-1.2.3.jar
~~~

Verify the artifact with GitHub CLI in GitHub Actions:

~~~bash
gh attestation verify target/artifact-lab-1.2.3.jar -R "$GITHUB_REPOSITORY"
~~~

GitHub Actions provides the `GITHUB_REPOSITORY` variable in the form `owner/repository`. When verifying, check that the repository, workflow identity, commit, and subject digest match the expected release.

Attestation provides signed provenance evidence. Keep verification policies explicit and only accept trusted builders/workflows/repositories. Attestation does not replace runtime testing, artifact signatures, or vulnerability scanning.

## 16. SBOM and Checking Dependencies Inside the Artifact

A Software Bill of Materials (SBOM) lists the software components in an artifact, commonly using SPDX or CycloneDX. An SBOM helps teams know which libraries an application contains and cross-reference them when new CVEs emerge.

A release process should:

1. Generate the SBOM from the exact artifact or build graph.
2. Store the SBOM alongside the release and link it by digest.
3. Scan dependencies and packages against security policies.
4. Check licenses and prohibited components.
5. Create an attestation for the SBOM if the pipeline supports it.
6. Update the SBOM whenever the artifact changes.

Do not generate an SBOM for the source tree and assume it accurately describes the final fat JAR. Shading, packaging plugins, and dependency bundling can make the artifact's contents differ from the initial dependency list.

## 17. Protecting Downloaded Dependencies

Not verifying output artifacts is one problem; trusting every downloaded dependency is also a risk.

Gradle supports dependency verification using checksums and signatures in `gradle/verification-metadata.xml`. You can generate initial metadata:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Or generate both checksum and PGP signature metadata when sources provide signatures:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

You must review the generated metadata and verify checksums from a trusted source before committing. Bootstrapping can record fingerprints of compromised dependencies if the current repository is already compromised.

Gradle dependency verification protects dependencies and plugins downloaded through dependency resolution. It does not automatically verify artifacts produced by the build itself. Mutable dependencies such as SNAPSHOTs also have their own rules and are not verified like immutable release dependencies. Therefore, an output artifact verification step is still required.

## 18. Maven: verify, package, and deploy in the Right Order

The Maven default lifecycle has these main phases:

- `compile`: compiles source code.
- `test`: runs unit tests.
- `package`: packages the JAR/WAR.
- `verify`: runs additional checks to verify the package meets quality criteria.
- `install`: installs the artifact into the local repository.
- `deploy`: publishes the artifact to the remote repository.

For normal builds, use:

~~~bash
./mvnw --batch-mode clean verify
~~~

`verify` runs the preceding phases in order, including `compile`, `test`, and `package`. However, testing the final artifact only happens if the project configures appropriate checks, such as integration tests or smoke tests running against the packaged JAR/WAR.

Before deploying, confirm the right file was created:

~~~bash
test -s target/artifact-lab-1.2.3.jar
jar --list --file target/artifact-lab-1.2.3.jar
java -jar target/artifact-lab-1.2.3.jar
~~~

Do not assume that `mvn verify` ran a smoke test on the JAR just from the phase name. Check the actual plugins/tasks and the artifact path used by tests.

## 19. Gradle: assemble, check, and build

The Gradle Java plugin provides common tasks:

- `compileJava`: compiles main source.
- `test`: runs tests.
- `jar`: creates the JAR.
- `assemble`: builds project artifacts.
- `check`: runs verification checks.
- `build`: combines `assemble` and `check` by plugin convention.

Run:

~~~bash
./gradlew clean build
~~~

Then confirm the output file:

~~~bash
test -s build/libs/artifact-lab-1.2.3.jar
jar --list --file build/libs/artifact-lab-1.2.3.jar
~~~

If you need to test the packaged artifact, add a smoke/integration test task that depends on the `jar` task, and run that task in the pipeline. Ensure the task uses the exact file produced by the current build.

You can check the toolchains detected by Gradle:

~~~bash
./gradlew javaToolchains
~~~

A successful build and successful dependency verification still do not automatically confirm that the local JAR was packaged properly; separate output verification is needed.

## 20. Checking Artifacts After Upload and Download

A common mistake is testing a file in the workspace but uploading the wrong file, or having the downloaded file differ in bytes from the original file.

A pipeline should:

- Upload the exact artifact path, using `if-no-files-found: error`.
- Store the SHA-256 alongside build metadata.
- Download the artifact in the release/deploy job.
- Recompute the SHA-256 after download.
- Compare against the hash generated by the trusted build step.
- Run a smoke test or signature check on the downloaded file if the release stage has a suitable environment.
- Deploy the exact verified file.

GitHub Actions example:

~~~yaml
- name: Verify artifact exists
  shell: bash
  run: |
    test -s target/artifact-lab-1.2.3.jar
    jar --list --file target/artifact-lab-1.2.3.jar

- name: Create checksum
  shell: bash
  run: |
    sha256sum target/artifact-lab-1.2.3.jar > target/artifact-lab-1.2.3.jar.sha256

- name: Upload verified artifact
  uses: actions/upload-artifact@v7
  with:
    name: artifact-lab-1.2.3
    path: |
      target/artifact-lab-1.2.3.jar
      target/artifact-lab-1.2.3.jar.sha256
    if-no-files-found: error
~~~

In the download job, verify the checksum before using it:

~~~bash
sha256sum --check target/artifact-lab-1.2.3.jar.sha256
~~~

The checksum file must come from the same build that produced the artifact and be protected by appropriate provenance/signatures. If someone can replace both the JAR and the checksum, that comparison provides no origin authentication.

## 21. Checking Container Artifacts and Runtime Images

For Docker/OCI images, checking the JAR alone is not enough. The deployment artifact is the image digest, including the base image, runtime, filesystem, and entrypoint.

Recommended steps:

- Pin the base image by version or digest.
- Confirm the architecture and OS match.
- Scan the image and dependencies.
- Inspect the entrypoint, command, environment, and exposed ports.
- Run the container with a production-like configuration.
- Verify the image digest after push/pull.
- Sign the image or generate an attestation if the pipeline supports it.

For a runtime image created by `jlink`, check the included modules:

~~~bash
runtime-image/bin/java --list-modules
~~~

For an installer created by `jpackage`, check the version, architecture, installed files, and actual launcher. Native artifacts must be tested on the target OS/architecture; a JAR running on the build machine does not prove a Windows or macOS installer works properly.

## 22. Detecting Stale Artifacts and Non-Reproducible Builds

Stale artifacts can remain in `target/`, `build/`, caches, or a self-hosted runner's workspace. A pipeline might upload an old file even though the current compile step succeeded.

Reduce risk by:

- Running `clean` before a release build.
- Recording the exact output path.
- Using explicit versions/classifiers.
- Avoiding overly broad wildcards when uploading.
- Recording the commit SHA and build run ID in metadata.
- Comparing the hash of the tested file with the uploaded/deployed file.
- Using a clean workspace or ephemeral runner for releases.
- Not rebuilding another artifact after QA if you can deploy the exact verified file.

Reproducible builds ensure two builds from the same source and controlled environment produce byte-for-byte identical artifacts. Timestamps, entry ordering, locale, timezone, plugin versions, and dependencies can affect the result. Configure reproducible archives when tools support it and compare SHA-256 across independent builds.

Differing hashes do not automatically prove tampering; they can result from timestamp metadata or different environments. What matters is finding the cause and identifying which artifact is being released.

## 23. Checking Version, Classifier, and Release Identity

Maven artifacts are typically identified by GAV: `groupId`, `artifactId`, `version`; `classifier` and `extension` further distinguish variants. Gradle publications also have coordinates and variant attributes.

For example, the same version can have:

~~~text
artifact-lab-1.2.3.jar
artifact-lab-1.2.3-tests.jar
artifact-lab-1.2.3-sources.jar
artifact-lab-1.2.3-javadoc.jar
~~~

Do not deploy `tests.jar` or `sources.jar` in place of the runtime binary. Check the artifact classifier, extension, and repository metadata.

Release versions should be immutable. Do not overwrite an already-published release with a different file while keeping the same version. If the contents change, publish a new version or a new build identity according to team policy. SNAPSHOTs are suitable for continuously changing development; do not treat a SNAPSHOT as a stable release artifact.

## 24. Practical Example: Building and Verifying a JAR with Java 17+

This example creates a small application, packages it into a JAR, and then verifies its hash, manifest, class entry, and readability of all entries. The verifier uses `JarFile` in verify mode to trigger digest checking for signed entries if the archive is signed.

Directory structure:

~~~text
artifact-lab/
├── src/
│   └── com/example/HelloApp.java
├── tools/
│   └── ArtifactVerifier.java
├── MANIFEST.MF
├── classes/
└── artifact-lab-1.2.3.jar
~~~

File `src/com/example/HelloApp.java`:

~~~java
package com.example;

public final class HelloApp {
    public static void main(String[] args) {
        System.out.println("ARTIFACT_LAB version=1.2.3");
    }
}
~~~

File `MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Implementation-Title: artifact-lab
Implementation-Version: 1.2.3
Build-Commit: demo-commit

~~~

Compile and package on Bash, Linux, or macOS:

~~~bash
mkdir -p classes tools
javac --release 17 -d classes src/com/example/HelloApp.java

jar --create \
  --file artifact-lab-1.2.3.jar \
  --manifest MANIFEST.MF \
  -C classes .
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force classes, tools | Out-Null
javac --release 17 -d classes src\com\example\HelloApp.java
jar --create --file artifact-lab-1.2.3.jar --manifest MANIFEST.MF -C classes .
~~~

File `tools/ArtifactVerifier.java`:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Enumeration;
import java.util.HexFormat;
import java.util.Locale;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ArtifactVerifier {
    public static void main(String[] args) throws Exception {
        if (args.length != 5) {
            throw new IllegalArgumentException(
                    "Usage: ArtifactVerifier <jar> <sha256> <main-class> <version> <required-entry>");
        }

        Path artifact = Path.of(args[0]).toAbsolutePath().normalize();
        String expectedHash = args[1].toLowerCase(Locale.ROOT);
        String expectedMain = args[2];
        String expectedVersion = args[3];
        String requiredEntry = args[4];

        if (!Files.isRegularFile(artifact) || !Files.isReadable(artifact)) {
            throw new IllegalStateException(
                    "Artifact is missing or unreadable: " + artifact);
        }
        if (Files.size(artifact) == 0) {
            throw new IllegalStateException("Artifact is empty: " + artifact);
        }

        String actualHash = sha256(artifact);
        if (!MessageDigest.isEqual(
                expectedHash.getBytes(StandardCharsets.US_ASCII),
                actualHash.getBytes(StandardCharsets.US_ASCII))) {
            throw new SecurityException("SHA-256 mismatch: expected "
                    + expectedHash + " but got " + actualHash);
        }

        int entriesRead = 0;
        try (JarFile jar = new JarFile(artifact.toFile(), true)) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("JAR manifest is missing");
            }

            Attributes attributes = manifest.getMainAttributes();
            String actualMain = attributes.getValue(Attributes.Name.MAIN_CLASS);
            String actualVersion =
                    attributes.getValue(Attributes.Name.IMPLEMENTATION_VERSION);

            if (!expectedMain.equals(actualMain)) {
                throw new IllegalStateException("Main-Class mismatch: " + actualMain);
            }
            if (!expectedVersion.equals(actualVersion)) {
                throw new IllegalStateException(
                        "Implementation-Version mismatch: " + actualVersion);
            }
            if (jar.getJarEntry(requiredEntry) == null) {
                throw new IllegalStateException(
                        "Required entry is missing: " + requiredEntry);
            }

            Enumeration<JarEntry> entries = jar.entries();
            byte[] buffer = new byte[8192];
            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                if (entry.isDirectory()) {
                    continue;
                }

                try (InputStream input = jar.getInputStream(entry)) {
                    while (input.read(buffer) != -1) {
                        // Read every entry to check decompression, CRC and signed digests.
                    }
                }
                entriesRead++;
            }
        }

        System.out.println("ARTIFACT=" + artifact.getFileName());
        System.out.println("SHA256=" + actualHash);
        System.out.println("MAIN_CLASS=" + expectedMain);
        System.out.println("IMPLEMENTATION_VERSION=" + expectedVersion);
        System.out.println("REQUIRED_ENTRY=" + requiredEntry);
        System.out.println("ENTRIES_READ=" + entriesRead);
        System.out.println("ARTIFACT_VERIFY=PASS");
    }

    private static String sha256(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Compile the verifier:

~~~bash
javac --release 17 -d tools tools/ArtifactVerifier.java
~~~

Inspect structure and bytecode:

~~~bash
jar --list --file artifact-lab-1.2.3.jar
javap -verbose -classpath artifact-lab-1.2.3.jar com.example.HelloApp
jdeps -s artifact-lab-1.2.3.jar
~~~

Generate hash and run the verifier on Bash:

~~~bash
HASH=$(sha256sum artifact-lab-1.2.3.jar | awk '{print $1}')

java -cp tools ArtifactVerifier \
  artifact-lab-1.2.3.jar "$HASH" \
  com.example.HelloApp 1.2.3 com/example/HelloApp.class
~~~

On PowerShell:

~~~powershell
$artifact = 'artifact-lab-1.2.3.jar'
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant()
java -cp tools ArtifactVerifier $artifact $hash com.example.HelloApp 1.2.3 'com/example/HelloApp.class'
~~~

Run the packaged JAR itself:

~~~bash
java -jar artifact-lab-1.2.3.jar
~~~

Application output:

~~~text
ARTIFACT_LAB version=1.2.3
~~~

In a test build on Azul OpenJDK 24.0.2, the verifier returned:

~~~text
ARTIFACT=artifact-lab-1.2.3.jar
SHA256=f2fe60fa31c1d377897b5ffdcafbc93c1898fb9707011aec04b380ca0a2a0689
MAIN_CLASS=com.example.HelloApp
IMPLEMENTATION_VERSION=1.2.3
REQUIRED_ENTRY=com/example/HelloApp.class
ENTRIES_READ=2
ARTIFACT_VERIFY=PASS
~~~

The hash may change on rebuild because the archive may contain different timestamps or metadata. When re-running, compute the hash from the exact artifact of that build and compare it against the value stored in trusted metadata.

## 25. Testing That the Verifier Detects a Modified Artifact

After generating the checksum, copy the artifact and modify a byte or append data to the copy. Run the verifier with the original expected hash:

~~~powershell
Copy-Item artifact-lab-1.2.3.jar tampered.jar
[System.IO.File]::AppendAllText('tampered.jar', 'tampered')
java -cp tools ArtifactVerifier tampered.jar $hash com.example.HelloApp 1.2.3 'com/example/HelloApp.class'
~~~

The verifier must exit with an error:

~~~text
java.lang.SecurityException: SHA-256 mismatch
~~~

In CI, such a negative test confirms that the verification step actually fails when bytes change. Never use the modified file for deployment.

## 26. Testing JAR Signatures in Practice

To test the signing flow in a development environment, you can create a temporary keystore:

~~~bash
keytool -genkeypair -alias artifact-demo -keyalg RSA -keysize 3072 -validity 365 -storetype PKCS12 -keystore signer.p12 -storepass changeit -keypass changeit -dname "CN=Artifact Lab"
~~~

Sign the JAR:

~~~bash
jarsigner -keystore signer.p12 -storetype PKCS12 -storepass changeit -keypass changeit artifact-lab-1.2.3.jar artifact-demo
~~~

To test trust in a lab, export the certificate and import it into a separate truststore:

~~~bash
keytool -exportcert -alias artifact-demo -keystore signer.p12 -storetype PKCS12 -storepass changeit -rfc -file signer.cer
keytool -importcert -alias artifact-demo -file signer.cer -keystore truststore.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

Verify:

~~~bash
jarsigner -verify -strict -keystore truststore.p12 -storetype PKCS12 -storepass changeit -verbose -certs artifact-lab-1.2.3.jar
~~~

In the lab, the self-signed certificate is trusted because the public certificate was imported into a separate truststore. This illustrates the verification mechanism. In production, only import certificates/keys after verifying the publisher fingerprint through an independent channel; never use example passwords or self-signed test keys as a release identity.

After signing, recompute the SHA-256. The signed JAR has different bytes from the pre-signing JAR because signature metadata was added to the archive.

## 27. Testing on the Exact Target Runtime and Environment

An artifact may run on a developer's JDK yet fail in production due to differences in runtime version, modules, OS, architecture, environment variables, or dependencies.

At a minimum, confirm:

- The minimum Java runtime supported by the application.
- The OS/architecture of binaries or native libraries.
- Required modules if using the module path or `jlink`.
- Environment variables, file permissions, and working directory.
- Non-JDK dependencies and native dependencies.
- TLS, truststore, and certificate configurations if the application makes network connections.
- Container or installer entrypoint and command.

If the release supports Java 17 and 21, run smoke tests on both runtimes. If releasing a Windows installer, test the launcher on Windows; if releasing for macOS ARM64, test on that architecture. Cross-platform compilation does not replace runtime testing on each platform.

## 28. Anti-Patterns to Avoid

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Looking only at BUILD SUCCESS | Unknown whether the final JAR is correct | Inspect and smoke test the artifact |
| Testing only classes in target/classes | Missing resources/manifest go undetected | Test the JAR after packaging |
| Uploading a broad wildcard of target/** | May upload stale or extra files | Select specific artifact paths |
| Using the name latest.jar | Hard to determine build identity | Use version, commit, and digest |
| Storing checksums only beside the artifact in an untrusted location | Both files can be replaced | Sign metadata or use attestation |
| Treating a self-signed certificate as a verified publisher | May trust the wrong key | Verify fingerprint and trust anchor |
| Running only jdeps | Misses dynamic/reflection dependencies | Combine with smoke/integration tests |
| Running only vulnerability scans | Does not prove the file is the right release | Combine with hash, signature, provenance |
| Rebuilding after QA and deploying the new build | Deploys untested bytes | Deploy the exact verified artifact |
| Overwriting a release version | Same coordinates with different contents | Use immutable releases and new versions |
| Trusting a checksum generated from an unknown-origin artifact | Fingerprint may have been wrong from the start | Obtain expected digest from a trusted build/release |
| Using a runtime image to build | Missing compiler/tooling | Use a JDK in the build stage |

## 29. Pre-Release Artifact Verification Workflow

A pipeline can implement the steps in order:

1. **Clean build:** remove old outputs and build from a specific commit.
2. **Test source:** run unit tests and static analysis.
3. **Package:** create the JAR/WAR/distribution or image.
4. **Verify file:** confirm path, size, file type, and version.
5. **Verify structure:** list archive, read entries, confirm resources/manifest.
6. **Verify compatibility:** check bytecode, dependencies, modules, and runtime.
7. **Smoke test:** run the artifact itself or a test harness using it.
8. **Integrity:** generate and store the SHA-256 from the verified file.
9. **Security:** check signatures, SBOM, dependencies, and vulnerabilities.
10. **Provenance:** generate/verify attestation per release policy.
11. **Publish:** upload the exact verified file without rebuilding.
12. **Post-download check:** recompute hash and verify before deployment.

Not every project needs every step at the same level. Small internal artifacts may use structure checks, hashes, and smoke tests; public or production releases require additional signing, provenance, SBOMs, and dependency controls per organizational policy.

## 30. Artifact Review Checklist for Java Projects

- [ ] Artifact path and name match the project, version, classifier, and extension.
- [ ] Artifact was built from the expected commit/build run.
- [ ] File exists, is readable, and has a reasonable size.
- [ ] JAR/ZIP can be listed and all entries can be read.
- [ ] Manifest has correct metadata; `Main-Class` is correct if it is an executable JAR.
- [ ] Required classes/resources/service providers are present in the archive.
- [ ] Target bytecode is compatible with supported Java runtimes.
- [ ] Dependencies, modules, and native libraries are fully provided.
- [ ] `jdeps` and appropriate static checks have been run.
- [ ] Smoke tests run against the packaged artifact itself.
- [ ] SHA-256 is stored and verified after upload/download.
- [ ] Signature is verified against a truststore containing trusted publisher keys.
- [ ] SBOM and vulnerability scan comply with release policy.
- [ ] Provenance/attestation confirms the right source and workflow.
- [ ] Deployed artifact has the same digest as the QA-verified file.
- [ ] Release version is not overwritten with different bytes.

Artifact verification is part of the build/release contract. When a team verifies the contents, metadata, compatibility, hash, signature, and behavior of the exact file to be released, packaging errors and artifact tampering can be caught before reaching users.

## References

- Oracle JDK 27 — [The jar Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html).
- Oracle JDK 26 — [JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html).
- Oracle JDK 26 — [The jarsigner Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html).
- Oracle JDK 26 — [The javap Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html).
- Oracle JDK 26 — [The jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html).
- Oracle JDK 26 — [The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- Apache Maven — [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html).
- Gradle 9 — [Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html).
- GitHub Docs — [Using Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations).
- GitHub Docs — [Establishing Build Provenance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).
