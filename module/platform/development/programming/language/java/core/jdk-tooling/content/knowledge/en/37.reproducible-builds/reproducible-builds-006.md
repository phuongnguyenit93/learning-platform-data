# Checksum Verification for Java Artifacts

A checksum is a hash value computed from all the bytes of a file. In Java build and release workflows, checksums help verify whether a received artifact matches, byte for byte, the artifact that was built or published.

For artifacts such as JAR, WAR, ZIP, or distribution files, the typical workflow is:

1. Build the artifact from pinned sources and dependencies.
2. Compute the SHA-256 of the artifact.
3. Store the checksum alongside release metadata or a manifest.
4. When downloading, copying, or deploying the artifact, recompute the SHA-256.
5. Compare the actual digest with the expected digest and fail CI if they differ.

In reproducible builds, checksums also help compare results from two independent builds. If the same source, toolchain, and build conditions produce a byte-for-byte identical artifact, the SHA-256 of both files must be identical.

## 1. What Is a Checksum?

A checksum is a representative value computed from file contents using an algorithm. With a cryptographic hash such as SHA-256, an input of arbitrary length produces a fixed 256-bit digest, typically represented as 64 hexadecimal characters.

For example, a file containing exactly three ASCII bytes:

~~~text
abc
~~~

Has the SHA-256:

~~~text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Changing even a single byte will almost certainly produce a completely different digest. Therefore, checksums are very useful for detecting corrupted, replaced, or mismatched files compared to the published artifact.

### What does a checksum verify?

- Whether the file has the exact byte contents described by the expected checksum.
- Whether two artifacts are byte-for-byte identical.
- Whether a downloaded file was corrupted during transfer or storage.
- Whether two builds produced the same artifact.

### What does a checksum NOT verify?

A checksum does not prove who created the file. If an attacker replaces both the artifact and the checksum file downloaded from the same untrusted source, the two files can still match.

To authenticate the origin, you must obtain the checksum through a trusted channel or verify a digital signature/provenance. Checksums and digital signatures solve two different questions:

- Checksum: do the file contents match the expected digest?
- Digital signature: was the digest or metadata signed by a trusted identity?

## 2. Choosing a Hash Algorithm

Commonly used algorithms:

| Algorithm | Digest length | Recommendation |
|---|---:|---|
| MD5 | 128 bit | Do not use for integrity checks requiring tamper resistance |
| SHA-1 | 160 bit | Avoid using for security purposes |
| SHA-256 | 256 bit | Common choice for artifact verification |
| SHA-384 | 384 bit | Can be used when required by policy |
| SHA-512 | 512 bit | Suitable when the system has standardized on this algorithm |

For Java application CI, SHA-256 is usually the simplest choice and is widely supported by the JDK, Linux, macOS, and Windows.

Do not use MD5 or SHA-1 to verify artifacts in release workflows that have security requirements. If a legacy system requires them to detect transfer errors, keep SHA-256 as the primary verification digest.

## 3. Generating Checksums on Linux

GNU coreutils provides the sha256sum command.

Compute the hash for a single file:

~~~bash
sha256sum build/libs/application.jar
~~~

Create a manifest:

~~~bash
sha256sum build/libs/application.jar > SHA256SUMS
~~~

The manifest content looks like:

~~~text
<sha256-digest>  build/libs/application.jar
~~~

Verify the file against the manifest:

~~~bash
sha256sum --check SHA256SUMS
~~~

When valid, the output looks like:

~~~text
build/libs/application.jar: OK
~~~

When the file changes or the digest does not match, the command returns a non-zero exit code. CI can use this exit code directly to stop the pipeline.

### Verifying multiple artifacts

~~~bash
sha256sum build/libs/*.jar > SHA256SUMS
sha256sum --check SHA256SUMS
~~~

The manifest contains one line per JAR. If any file does not exist or its contents differ from the digest, the verification step fails.

Run the verification command from a directory where the paths in the manifest can be resolved. If you create the manifest with relative paths, you must keep the same working directory when verifying.

## 4. Generating Checksums on macOS

macOS typically includes the shasum command:

~~~bash
shasum -a 256 build/libs/application.jar
~~~

Create a manifest:

~~~bash
shasum -a 256 build/libs/application.jar > SHA256SUMS
~~~

Verify:

~~~bash
shasum -a 256 -c SHA256SUMS
~~~

When valid, the output looks like:

~~~text
build/libs/application.jar: OK
~~~

Do not confuse shasum -a 256 with the default SHA-1 of some older shasum commands. Always specify algorithm 256 explicitly.

## 5. Generating Checksums on Windows

PowerShell includes Get-FileHash:

~~~powershell
Get-FileHash -LiteralPath '.\build\libs\application.jar' -Algorithm SHA256
~~~

The output includes:

- Algorithm: SHA256.
- Hash: hexadecimal digest.
- Path: file path.

You can use certutil when manual verification is needed:

~~~powershell
certutil -hashfile .\build\libs\application.jar SHA256
~~~

### PowerShell script to generate and verify checksums

The following script writes the digest to a sidecar file. When run in the publish step, it generates the checksum. When run in the verify step, it reads the digest provided from a trusted source and compares it against the current artifact.

~~~powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$Artifact,

    [Parameter(Mandatory = $true)]
    [string]$ChecksumFile
)

if (-not (Test-Path -LiteralPath $Artifact -PathType Leaf)) {
    Write-Error "Artifact not found: $Artifact"
    exit 2
}

$actual = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()

if (-not (Test-Path -LiteralPath $ChecksumFile -PathType Leaf)) {
    $actual | Set-Content -LiteralPath $ChecksumFile -Encoding ascii -NoNewline
    Write-Output "Checksum manifest created: $ChecksumFile"
    exit 0
}

$expected = (Get-Content -LiteralPath $ChecksumFile -Raw).Trim().ToLowerInvariant()

if ($expected -notmatch '^[0-9a-f]{64}$') {
    Write-Error "Invalid SHA-256 checksum file."
    exit 2
}

if (-not [string]::Equals(
    $actual,
    $expected,
    [System.StringComparison]::Ordinal
)) {
    Write-Error "Checksum mismatch for $Artifact"
    exit 1
}

Write-Output "SHA-256: $actual"
Write-Output "Checksum OK"
exit 0
~~~

In a real pipeline, separate the checksum generation step and the verification step. If the sidecar does not exist yet, the script above creates it; if the sidecar already exists, it verifies. Do not use generating a sidecar from the just-downloaded artifact itself as proof of that artifact's authenticity.

If you need a manifest containing multiple artifacts, you can store JSON or CSV with path, algorithm, and digest, then verify each entry in a CI script.

## 6. Java 17+ Example: Computing SHA-256 with MessageDigest

The JDK provides MessageDigest in the java.security package. You can use this API when an application needs to verify a file before importing, deploying, or processing it.

For large files, read using a buffer instead of Files.readAllBytes, because reading the entire file at once can consume a lot of heap.

### ChecksumVerifier.java

~~~java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ChecksumVerifier {
    private ChecksumVerifier() {
    }

    public static void main(String[] args) {
        if (args.length != 2 || !args[1].matches("(?i)[0-9a-f]{64}")) {
            System.err.println(
                    "Usage: ChecksumVerifier <file> <expected-sha256-hex>");
            System.exit(2);
            return;
        }

        try {
            byte[] expected = HexFormat.of().parseHex(args[1]);
            byte[] actual = sha256(Path.of(args[0]));

            System.out.println(
                    "SHA-256: " + HexFormat.of().formatHex(actual));

            if (MessageDigest.isEqual(actual, expected)) {
                System.out.println("Checksum OK");
            } else {
                System.out.println("Checksum MISMATCH");
                System.exit(1);
            }
        } catch (IOException | NoSuchAlgorithmException
                | IllegalArgumentException ex) {
            System.err.println(
                    "Checksum verification failed: " + ex.getMessage());
            System.exit(2);
        }
    }

    private static byte[] sha256(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return digest.digest();
    }
}
~~~

Explanation:

- MessageDigest.getInstance("SHA-256") creates the digest calculator.
- Files.newInputStream opens the file for sequential reading.
- An 8192-byte buffer avoids loading the entire file into RAM.
- digest.update(buffer, 0, count) updates the hash for each chunk read.
- digest.digest() returns the 32 bytes of SHA-256.
- HexFormat converts the digest to a hexadecimal string.
- MessageDigest.isEqual compares the two byte arrays.
- Exit code 0 means the checksum matches, 1 means the digest does not match, and 2 means invalid input or a read error.

HexFormat was introduced in Java 17. If the project supports an older Java version, you can convert the byte array to hexadecimal using a custom helper or an approved library.

## 7. Running the Java Verifier with a Known Test Vector

Create a file containing exactly three ASCII bytes abc. Do not add a BOM, newline, or whitespace, because any extra byte changes the digest.

Expected SHA-256 digest:

~~~text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Compile:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/ChecksumVerifier.java
~~~

Run with the correct digest:

~~~bash
java -cp build/classes com.example.ChecksumVerifier artifact.txt ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Output:

~~~text
SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
Checksum OK
~~~

Run with an incorrect digest:

~~~bash
java -cp build/classes com.example.ChecksumVerifier artifact.txt 0000000000000000000000000000000000000000000000000000000000000000
~~~

Output:

~~~text
SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
Checksum MISMATCH
~~~

The second run returns exit code 1. A wrong digest must not be treated as an ignorable warning in CI.

If you pass a checksum that does not have 64 hexadecimal characters, the program prints usage and returns exit code 2.

## 8. Checking Whether Two Builds Are Reproducible

Checksums are a fast way to compare the output of two independent builds.

Workflow:

1. Check out the same commit.
2. Build in two clean workspaces.
3. Use the same JDK/toolchain, dependencies, and build configuration.
4. Compute the SHA-256 of the artifact in each workspace.
5. Compare the two digests.
6. If they differ, investigate which bytes differ before concluding the build is not reproducible.

Example on Linux:

~~~bash
sha256sum build-a/application.jar
sha256sum build-b/application.jar
~~~

You can compare directly:

~~~bash
cmp build-a/application.jar build-b/application.jar
~~~

cmp returns exit code 0 when the two files are byte-for-byte identical and non-zero when there is a difference.

On Windows:

~~~powershell
Get-FileHash .\build-a\application.jar -Algorithm SHA256
Get-FileHash .\build-b\application.jar -Algorithm SHA256

fc.exe /b .\build-a\application.jar .\build-b\application.jar
~~~

If the two digests match, the two artifacts have the same byte content with very high practical confidence. If they differ, the checksum only tells you that they are different; you need a diff tool to find the root cause.

### Why can the same source still produce different checksums?

Some common causes:

- File timestamps inside the ZIP/JAR change.
- Entry ordering in the archive is unstable.
- The build embeds the current time into the manifest or generated resources.
- Generated files contain absolute workspace paths.
- Build numbers or random identifiers change.
- Locale, timezone, or line endings differ.
- JDK, compiler, plugin, or dependency versions differ.
- Dependencies resolved from a repository change over time.
- File permissions or archive metadata differ.
- Artifacts are signed at different times.

If checksums differ, do not rush to conclude that the source code is different. Extract both archives and compare entries, timestamps, metadata, and generated files.

You can use diffoscope or unzip/zipinfo to inspect archives. Hashing is the difference-detection step; diffing is the root-cause investigation step.

## 9. Configuring Builds to Produce Deterministic Archives

Checksums only verify reproducibility after the build has produced output. For two builds to produce the same digest, you must eliminate non-deterministic factors.

### Maven

Maven archive plugin versions that support output timestamps can use the property:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

The value must remain stable across builds of the same source revision. In real projects, it can be derived from a normalized commit timestamp instead of using the current time.

Make sure the packaging plugin versions support this property. A single property in the POM does not automatically make every plugin or generated resource deterministic.

### Gradle

For archive tasks, you can disable preserving original file timestamps and enable reproducible entry ordering.

Groovy DSL:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Kotlin DSL:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

These settings stabilize archive metadata. They do not resolve all sources of nondeterminism in code generation, dependency resolution, or the build environment.

### Standardizing the build environment

For a meaningful comparison, pin:

- JDK vendor and version.
- Build tool and plugin versions.
- Dependency versions and repository content.
- Locale and timezone.
- Environment variables that affect the build.
- Source revision and generated inputs.
- File encoding and line endings.
- Timestamps embedded into the artifact.

You can use containers or digest-pinned build images to reduce environment differences. You still need to compare actual outputs using checksums.

## 10. Creating a Checksum Manifest for a Release

After building and packaging, create a manifest for the exact artifacts to be published.

Example:

~~~bash
sha256sum application.jar application-sources.jar > SHA256SUMS
~~~

Publish together:

~~~text
application.jar
application-sources.jar
SHA256SUMS
~~~

On the download side:

~~~bash
sha256sum --check SHA256SUMS
~~~

If a release contains multiple files, a manifest lets you verify all artifacts against a single list. Do not modify or repackage artifacts after generating the manifest; if the bytes change, you must generate a new digest.

### When to compute the checksum

Compute the checksum after the artifact has completed all transformation steps:

1. Compile.
2. Package.
3. Repackage or shade, if applicable.
4. Sign the JAR if required by the workflow.
5. Compute the checksum of the final file.
6. Publish the artifact and checksum manifest.

If you compute the checksum before signing the JAR, signing changes the file and the old digest will no longer match the released artifact.

## 11. Integrating Checksum Verification into CI

### GitHub Actions

Example workflow verifying a manifest already generated or downloaded from trusted release metadata:

~~~yaml
- name: Verify artifact checksums
  shell: bash
  run: sha256sum --check SHA256SUMS
~~~

If the workflow builds the artifacts in a previous job, you can generate the manifest:

~~~yaml
- name: Generate SHA-256 manifest
  shell: bash
  run: sha256sum build/libs/*.jar > SHA256SUMS
~~~

The job consuming the artifacts must download both the files and the manifest, then run the verify step.

### GitLab CI

~~~yaml
stages:
  - build
  - verify

build:
  stage: build
  script:
    - ./gradlew clean build
    - sha256sum build/libs/*.jar > SHA256SUMS
  artifacts:
    paths:
      - build/libs/
      - SHA256SUMS

verify:
  stage: verify
  script:
    - sha256sum --check SHA256SUMS
~~~

### Jenkins Pipeline

~~~groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh './gradlew clean build'
                sh 'sha256sum build/libs/*.jar > SHA256SUMS'
            }
        }

        stage('Verify checksum') {
            steps {
                sh 'sha256sum --check SHA256SUMS'
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'SHA256SUMS',
                             allowEmptyArchive: true
        }
    }
}
~~~

The Bash examples assume the runner has sha256sum. For Windows runners, use PowerShell Get-FileHash and a digest comparison script.

### Rules for a CI gate

- Missing artifact: fail.
- Missing manifest when verification is required: fail.
- Malformed digest: fail.
- Digest mismatch: fail.
- Algorithm does not comply with policy: fail.
- Unable to read file or manifest: fail.
- Only pass when every file is verified successfully.

Do not use "the command produced output" to determine pass. Rely on the exit code and the digest comparison result.

## 12. Checksums and Digital Signatures

A checksum is not a digital signature. If the manifest sits next to the artifact on the same untrusted download source, an attacker can replace both.

To authenticate origin:

- Obtain the checksum from signed release metadata.
- Verify the signature of the manifest or artifact.
- Use provenance/attestation systems to confirm build identity and source revision.
- Protect publish permissions and permissions to modify release metadata.

For a signed JAR, you can verify the signature:

~~~bash
jarsigner -verify -strict -verbose -certs application.jar
~~~

This command checks the JAR signature and certificates according to jarsigner's policy. It answers a different question from SHA-256. You can use both steps: verify the digest to check byte content against the manifest, and verify the signature to check the signature/certificates.

Do not treat a checksum fetched from the same suspected mirror as independent proof of authenticity.

## 13. Common Mistakes When Verifying Checksums

### Different hashes even though files look the same

Hashes are computed over bytes, not displayed text. Differences in newlines, encoding, BOM, whitespace, archive timestamps, or metadata all produce different digests.

### Computing the checksum before the build finishes

If the artifact is later repackaged, signed, or has its metadata modified, the old digest will no longer match. Compute the hash after the final transformation step.

### Using the wrong file or wrong path

The manifest may point to a different artifact with the same name. Check the working directory, path, and published artifact name.

### Using the wrong algorithm

A SHA-256 manifest must be verified with SHA-256. Do not compare an MD5 or SHA-1 digest against a SHA-256 value.

### Comparing only against a checksum provided by the same untrusted source

An attacker can replace both the file and the digest. Obtain the expected checksum from a trusted channel or verify a signature.

### Using Files.readAllBytes for large files

This loads the entire file into the heap. Use InputStream and buffered MessageDigest.update calls to handle large files.

### Creating a test vector with an extra newline or BOM

A file containing abc and a file containing abc with a newline are two different inputs. When testing known vectors, control the exact bytes written.

### Comparing the checksum of a signed artifact with an unsigned artifact

Signing changes the bytes of the JAR. Compute the checksum after signing completes and verify against the exact artifact being distributed.

### Treating checksums as equivalent to reproducible builds

Checksums only compare files. Reproducible builds also require independent builds from the same source/configuration to produce byte-identical output.

## 14. Checksum Verification Workflow in a Java Project

1. Choose SHA-256 as the standard algorithm.
2. Identify the exact artifacts to protect: JAR, WAR, ZIP, or distribution.
3. Complete compiling, packaging, repackaging, and signing.
4. Generate a manifest containing the digest of the final artifact.
5. Publish the artifact and manifest according to the release workflow.
6. On the consumer/CI side, obtain the expected digest from a trusted source.
7. Recompute the SHA-256 of the received artifact.
8. Compare the digests and fail if they differ.
9. When testing reproducible builds, build the same commit in independent workspaces.
10. Compare the checksums of the two artifacts and investigate if they differ.
11. Archive the manifest, logs, and build provenance as evidence.
12. Periodically verify the toolchain and checksum policy.

## 15. Pre-Publish Checklist

- [ ] Use SHA-256 or a stronger algorithm per policy.
- [ ] Build is complete and the artifact is no longer modified.
- [ ] Checksum is computed on the exact file to be published.
- [ ] Manifest records the exact artifact names and paths.
- [ ] A verification step exists on the consumer or CI side.
- [ ] CI fails when the checksum is wrong or the manifest is missing.
- [ ] Known test vector has been verified.
- [ ] Large files are processed via streaming.
- [ ] For reproducible builds, outputs from two independent builds have been compared.
- [ ] Timestamps and archive entry ordering are normalized.
- [ ] Expected checksum is obtained from a trusted source.
- [ ] Signatures/provenance are verified when origin authentication is required.

## 16. Commands to Remember

~~~bash
# Linux: calculate SHA-256
sha256sum build/libs/application.jar

# Linux: create and verify manifest
sha256sum build/libs/application.jar > SHA256SUMS
sha256sum --check SHA256SUMS

# macOS: calculate and verify SHA-256
shasum -a 256 build/libs/application.jar
shasum -a 256 build/libs/application.jar > SHA256SUMS
shasum -a 256 -c SHA256SUMS

# Compare two independent build outputs
sha256sum build-a/application.jar build-b/application.jar
cmp build-a/application.jar build-b/application.jar

# Windows PowerShell
Get-FileHash -LiteralPath .\build\libs\application.jar -Algorithm SHA256

# Windows command-line alternative
certutil -hashfile .\build\libs\application.jar SHA256

# Compile the Java 17 verifier
javac --release 17 -d build/classes src/com/example/ChecksumVerifier.java

# Verify an artifact using Java
java -cp build/classes com.example.ChecksumVerifier application.jar <expected-sha256-hex>

# Verify a signed JAR separately
jarsigner -verify -strict -verbose -certs application.jar
~~~

Checksums are a simple yet critical byte-content verification step in builds and releases. Use SHA-256, generate the manifest after the artifact is finalized, verify via exit codes in CI, and obtain expected digests from a trusted source. When checking reproducible builds, run independent builds from the same source revision and compare checksums; if they differ, investigate the metadata and build environment instead of simply changing the expected digest.

## References

- [MessageDigest — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
- [HexFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html)
- [Get-FileHash — Microsoft PowerShell](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/get-filehash)
- [sha256sum — GNU Coreutils](https://www.gnu.org/software/coreutils/manual/html_node/sha2-utilities.html)
- [JAR Tool — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [jarsigner Tool — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Reproducible Builds](https://reproducible-builds.org/)
