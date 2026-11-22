# Artifact Checksums in Java

An **artifact checksum** is a value computed from all the bytes of a file using a hash algorithm. By recomputing the checksum after downloading, copying, or storing an artifact, you can compare the two values to detect whether the file has been modified, corrupted, or truncated.

In Java builds and releases, an artifact can be a JAR, WAR, ZIP, native image, distribution archive, installer, container image, or any file distributed to users. Checksums are typically published alongside the artifact so recipients can verify integrity before installing or deploying.

Two goals must be distinguished:

- **Integrity:** Do the bytes of the file match the bytes described by the reference checksum?
- **Authenticity:** Does the checksum or artifact genuinely come from a trusted publisher?

SHA-256 verifies integrity when the reference digest comes from a trusted source. If an attacker can replace both the file and the checksum file on the same unprotected server, the comparison can still succeed. To authenticate the origin, you need a digital signature or a protected checksum distribution channel.

## 1. What are checksums and cryptographic hashes?

Checksum is a broad term for a value used to detect data changes. Simple checksums such as CRC32 are suitable for detecting accidental transmission errors, but they do not resist deliberate collision crafting.

A cryptographic hash function takes an input of arbitrary length and produces a fixed-length digest. Cryptographic hash algorithms are designed so that it is infeasible to find two different inputs with the same digest.

Some common algorithms:

| Algorithm | Digest length | Recommendation |
|---|---:|---|
| SHA-256 | 256 bits (64 hex characters) | Good default choice for artifacts today |
| SHA-384 | 384 bits (96 hex characters) | Use when policy requires a stronger SHA-2 |
| SHA-512 | 512 bits (128 hex characters) | Suitable when supported and a longer digest is needed |
| SHA-1 | 160 bits | Do not use for new security verification |
| MD5 | 128 bits | Do not use for security verification |
| CRC32 | 32 bits | Accidental error detection, not tamper-resistant |

SHA-256 and SHA-512 belong to the SHA-2 family. For most Java artifacts, SHA-256 is the standard choice because it is widely supported and strong enough for integrity verification.

Do not choose MD5 or SHA-1 for new release workflows. These algorithms have known collision weaknesses; an attacker can craft two different contents with the same digest in certain scenarios.

A checksum is not encryption. A hash cannot be decrypted back to recover the original file, and a digest does not hide the contents of an artifact.

## 2. Hashes operate on bytes, not filenames

SHA-256 takes a sequence of bytes. The filename, extension, and path do not participate in the calculation unless they are explicitly included in the content being hashed.

Therefore:

- Renaming `app.jar` to `release.jar` does not change the checksum.
- Changing a single byte in a JAR almost certainly produces a different digest.
- Changing timestamps or entry ordering in a ZIP/JAR can change the whole-file checksum.
- Extracting and re-archiving usually produces different file bytes, even when the contents of the inner files are identical.
- Two files with the same byte content located in different directories will have the same checksum.

An artifact's checksum is the checksum of the distributed file itself. Do not hash the extracted contents if the goal is to verify that the downloaded file is intact.

For a directory containing multiple files, you need a manifest describing the checksum of each file and its corresponding path. You cannot compute a single checksum for a directory without first defining how to normalize file ordering, filenames, permissions, and metadata.

## 3. SHA-256 and what a digest represents

SHA-256 always produces 256 bits, commonly represented as 64 hexadecimal characters. A digest looks like:

```text
ba7816bf8f01cfea414140de5dae2223
b00361a396177a9cb410ff61f20015ad
```

This is the SHA-256 of the exact three ASCII bytes `abc`, with no trailing newline.

Digests are usually written on a single line:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  app.jar
```

The filename portion is metadata in the checksum manifest format; the SHA-256 algorithm itself only hashes the bytes of the file.

A digest does not reveal file contents in a reversible way. However, for small or predictable inputs, someone can hash candidate values to match against it. For this reason, do not use checksums to store passwords; passwords require a dedicated password hashing scheme with a salt and cost factor.

## 4. When do you need artifact checksums?

Checksums are valuable across many stages of the artifact lifecycle:

| Stage | Purpose |
|---|---|
| Build | Record the fingerprint of the newly created JAR/WAR/ZIP |
| Upload | Detect file corruption during upload |
| Download | Verify the received file matches the released file |
| Artifact repository | Verify stored artifacts have not been modified |
| CI/CD | Block deployment if the checksum does not match |
| Backup/mirror | Compare copies across systems |
| Incident response | Determine whether two artifact copies are identical |
| Release audit | Store fingerprints tied to a version and commit |

For example, a release `orders-service-2.4.0.jar` is uploaded to an artifact repository. The pipeline generates `orders-service-2.4.0.jar.sha256`. When the staging environment downloads the JAR, it recomputes the SHA-256 and compares it against the published digest. Only when they match does the pipeline proceed with deployment.

Checksums do not replace tests, malware scanning, signature verification, or provenance checks. They are a step for verifying byte identity.

## 5. Generating checksums on Linux

GNU Coreutils provides the `sha256sum` command:

```sh
sha256sum app.jar
```

The output has the form:

```text
<64-hex-character-digest>  app.jar
```

Save the checksum to a sidecar file:

```sh
sha256sum app.jar > app.jar.sha256
```

Verify the file:

```sh
sha256sum --check app.jar.sha256
```

When valid, the output typically looks like:

```text
app.jar: OK
```

When the file has changed, the command reports `FAILED` and returns a non-zero exit code. CI should check the exit code to halt the pipeline.

If you want a manifest for multiple artifacts:

```sh
sha256sum app.jar app-sources.jar app.zip > SHA256SUMS
sha256sum --check SHA256SUMS
```

The manifest stores digests alongside filenames. When verifying, run from the directory containing the corresponding files or use consistent relative paths.

## 6. Generating checksums on macOS

macOS typically includes `shasum`:

```sh
shasum -a 256 app.jar
```

Create a sidecar file:

```sh
shasum -a 256 app.jar > app.jar.sha256
```

You can also use OpenSSL if installed:

```sh
openssl dgst -sha256 app.jar
```

To verify, recompute the checksum and compare it with the reference digest obtained from a trusted source. GNU `sha256sum --check` is not always pre-installed on macOS; if using a GNU manifest, you can install GNU Coreutils or use an appropriate verification script.

Do not copy a checksum from the terminal by arbitrarily stripping spaces or newlines if the manifest format requires the filename. For manual comparison, compare only the trimmed digest string and check that it has exactly 64 hex characters.

## 7. Generating and verifying checksums on Windows

PowerShell includes `Get-FileHash`:

```powershell
Get-FileHash -Path .\app.jar -Algorithm SHA256
```

The result includes:

- `Algorithm`: the hash algorithm.
- `Hash`: the hexadecimal digest.
- `Path`: the path to the hashed file.

Save only the hash digest to a sidecar file:

```powershell
$hash = (Get-FileHash -Path .\app.jar -Algorithm SHA256).Hash
$hash.ToLowerInvariant() | Set-Content -Path .\app.jar.sha256 -NoNewline -Encoding ascii
```

Verify:

```powershell
$expected = (Get-Content .\app.jar.sha256 -Raw).Trim()
$actual = (Get-FileHash -Path .\app.jar -Algorithm SHA256).Hash

if ($actual -ne $expected) {
    throw "Checksum mismatch: app.jar"
}

Write-Output "app.jar: OK"
```

Stdout when the checksum matches:

```text
app.jar: OK
```

PowerShell compares strings case-insensitively by default. If you want to validate the format before comparing, confirm that the digest contains exactly 64 hexadecimal characters.

Another option is `certutil`:

```cmd
certutil -hashfile app.jar SHA256
```

`Get-FileHash` is more convenient for PowerShell scripts because it returns an object with an explicit `Hash` property.

## 8. Java 17+ example: computing SHA-256 with MessageDigest

Java provides `MessageDigest` in the `java.security` package. The example below computes the SHA-256 of the string `abc`, converts the digest to hexadecimal, and compares it against a known reference value.

Create `ChecksumDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public class ChecksumDemo {
    public static void main(String[] args) throws Exception {
        byte[] input = "abc".getBytes(StandardCharsets.UTF_8);

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] actualBytes = digest.digest(input);

        String actual = HexFormat.of().formatHex(actualBytes);
        String expected =
                "ba7816bf8f01cfea414140de5dae2223"
              + "b00361a396177a9cb410ff61f20015ad";

        byte[] expectedBytes = HexFormat.of().parseHex(expected);
        boolean matches = MessageDigest.isEqual(
                expectedBytes, actualBytes);

        System.out.println("sha256=" + actual);
        System.out.println("matches=" + matches);
    }
}
```

Compile:

```sh
javac ChecksumDemo.java
```

Run:

```sh
java ChecksumDemo
```

Exact stdout:

```text
sha256=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
matches=true
```

`MessageDigest.getInstance("SHA-256")` obtains the algorithm implementation from a provider configured by the JVM. If the algorithm is unavailable, the API throws `NoSuchAlgorithmException`; SHA-256 is supported by standard Java platform implementations.

`HexFormat`, introduced in Java 17, converts byte arrays to hex strings and parses hex strings back. `MessageDigest.isEqual()` compares two digest byte arrays; this approach is appropriate when you want to avoid string comparison logic that short-circuits on the first differing byte.

## 9. Streaming hash for large files

Avoid using `Files.readAllBytes()` for large files because the entire file is loaded into RAM. Read with a buffer and update `MessageDigest` incrementally.

Create `Sha256File.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class Sha256File {
    public static String sha256(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];

        try (InputStream input = Files.newInputStream(path)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }

    public static boolean verify(Path path, String expected)
            throws IOException, NoSuchAlgorithmException {
        String normalized = expected.trim();

        if (!normalized.matches("(?i)[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                    "Expected SHA-256 must contain 64 hex characters");
        }

        byte[] expectedBytes = HexFormat.of().parseHex(normalized);
        byte[] actualBytes = HexFormat.of().parseHex(sha256(path));

        return MessageDigest.isEqual(expectedBytes, actualBytes);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java Sha256File <file> <expected-sha256>");
            System.exit(2);
        }

        Path file = Path.of(args[0]);
        String actual = sha256(file);
        boolean matches = verify(file, args[1]);

        System.out.println("sha256=" + actual);
        System.out.println("verified=" + matches);

        if (!matches) {
            System.exit(1);
        }
    }
}
```

Compile:

```sh
javac Sha256File.java
```

Run with an artifact and reference digest:

```sh
java Sha256File app.jar EXPECTED_SHA256
```

Output:

```text
sha256=<64-hex-character-digest>
verified=true
```

Replace `EXPECTED_SHA256` with the actual digest obtained from a trusted source. If the file does not match, the program prints `verified=false` and exits with exit code 1. If the digest argument is malformed, the program throws `IllegalArgumentException`.

An 8 KiB buffer keeps memory usage constant regardless of file size. You can increase the buffer if benchmarks show it is needed; correctness does not depend on the buffer size.

Create a separate `MessageDigest` instance for each hash computation. Do not share the same instance across multiple threads because `MessageDigest` holds mutable state across updates.

## 10. Verifying files immediately after download

A safe workflow should verify a file before extracting, running, or deploying it.

Example on Linux:

```sh
curl -fL -o app.jar https://downloads.example.com/app.jar
curl -fL -o app.jar.sha256 https://downloads.example.com/app.jar.sha256
sha256sum --check app.jar.sha256
```

If verification fails, do not deploy that file. Recheck the URL, network, artifact version, and reference checksum.

However, if both `app.jar` and `app.jar.sha256` are downloaded from the same unauthenticated source, an attacker controlling that source can replace both. You should verify the checksum via an independent trusted channel or verify a digital signature on the release metadata.

Do not run an artifact before checking its checksum. If the artifact is a script, installer, or executable, running it beforehand could execute tampered content.

## 11. Integrity is not authenticity

This is the most important point when using checksums for releases.

Suppose a publisher posts:

- `app-2.4.0.jar`
- `app-2.4.0.jar.sha256`

A user downloads both from the same server. If the JAR file was modified while the checksum file remained the old one, the check will detect it. But if an attacker replaces both the JAR and the checksum, the check can still report success.

Therefore:

- A checksum confirms that the artifact's bytes match the reference digest.
- A digital signature verifies that metadata or the artifact was signed by the corresponding private key.
- A trust policy defines which public keys or identities are accepted.
- Provenance describes which source and build process produced the artifact.

For important releases, publish checksums together with a detached signature or a signed manifest. Recipients should verify the signature using a pre-established trusted public key or identity.

Do not treat a checksum file hosted alongside the artifact on the same host as independent proof of origin.

## 12. Signing checksums or manifests with a digital signature

A release can use GPG/OpenPGP to sign the checksum file:

```sh
gpg --armor --detach-sign SHA256SUMS
```

This command creates a detached signature file, typically `SHA256SUMS.asc`. The recipient verifies the signature:

```sh
gpg --verify SHA256SUMS.asc SHA256SUMS
```

Once the signature is valid and the signer is trusted, verify the checksums in the manifest:

```sh
sha256sum --check SHA256SUMS
```

The verification order is critical:

1. Verify the signature on the manifest.
2. Check the signer's identity or key fingerprint against the trust policy.
3. Verify the artifact's checksum.
4. Only then install or deploy.

A valid signature only proves that the data was signed by the corresponding private key. If the public key is unauthenticated or compromised, conclusions about origin are untrustworthy.

In modern systems, you can use Sigstore/Cosign to sign artifacts or container images and verify certificate identities against a policy. For CI supply chains, combine signatures with provenance/attestation to know which commit, workflow, and builder produced the artifact.

## 13. Creating a checksum manifest for multiple artifacts

A release often contains multiple files:

```text
release/
├── app.jar
├── app-sources.jar
├── app-javadoc.jar
├── app.zip
└── SHA256SUMS
```

On Linux, create the manifest:

```sh
cd release
sha256sum app.jar app-sources.jar app-javadoc.jar app.zip > SHA256SUMS
```

Verify all files:

```sh
sha256sum --check SHA256SUMS
```

The manifest must contain the corresponding filename and digest for each artifact. Do not include the `SHA256SUMS` file itself in the list it hashes, as that creates a circular reference.

For releases with subdirectories, use consistent relative paths. If files are moved, the manifest may fail to locate them even though the bytes are unchanged. This is a file-location issue, not a hash algorithm error.

To produce a deterministic manifest, sort the file list according to a deterministic rule rather than relying on arbitrary filesystem order. If writing a custom script, properly handle spaces, newlines, and special characters in filenames; prefer a manifest format with defined escaping.

## 14. Generating a checksum manifest in Java

Java can compute checksums for multiple artifacts and write a UTF-8 manifest. The example below uses relative paths, sorts by name, and writes one line per file.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;

public class ChecksumManifest {
    public static void main(String[] args) throws Exception {
        Path root = Path.of("release");
        List<Path> files;

        try (var paths = Files.list(root)) {
            files = paths
                    .filter(Files::isRegularFile)
                    .filter(path -> !path.getFileName()
                            .toString().equals("SHA256SUMS"))
                    .sorted(Comparator.comparing(
                            path -> path.getFileName().toString()))
                    .toList();
        }

        StringBuilder manifest = new StringBuilder();
        for (Path file : files) {
            String hash = Sha256File.sha256(file);
            manifest.append(hash)
                    .append("  ")
                    .append(file.getFileName())
                    .append('\n');
        }

        Files.writeString(
                root.resolve("SHA256SUMS"),
                manifest.toString(),
                StandardCharsets.UTF_8);
    }
}
```

This example assumes the `Sha256File` class from the earlier section is in the same package and compiled in the same project. It only processes files directly inside the `release` directory and does not recurse into subdirectories.

For filenames containing newlines or special characters, the simple `hash  filename` format requires escaping. In production release automation, use a standard manifest format or restrict artifact naming rules to avoid ambiguity.

## 15. Verifying dependency checksums in Gradle

Gradle Dependency Verification allows verifying checksums or signatures of resolved dependencies. This is useful because dependencies are also artifacts downloaded from repositories.

Generate verification metadata using SHA-256:

```sh
./gradlew --write-verification-metadata sha256 help
```

Gradle creates or updates `gradle/verification-metadata.xml`. Review this file and commit it alongside your source code. Do not automatically trust new checksums if dependencies were downloaded from an unverified source.

You can enable strict verification mode in `settings.gradle.kts`:

```kotlin
dependencyVerification {
    verificationMode = VerificationMode.STRICT
}
```

In strict mode, dependencies without matching metadata will fail the build. This is the desired behavior when an organization requires dependencies to be verified before use.

When upgrading a dependency:

1. Check which repository the new dependency comes from.
2. Verify the coordinates, version, and publishing source.
3. Generate checksum metadata.
4. Review the diff in `verification-metadata.xml`.
5. Run a clean build and check CI.
6. Commit the lock/verification metadata together with the dependency update.

Dependency verification protects artifact resolution against trusted metadata. It does not replace license checks, vulnerability scanning, or full build provenance verification.

## 16. Maven and dependency checksums

Maven downloads dependencies and plugins from repositories by `groupId`, `artifactId`, `version`, and `classifier` coordinates. Repository managers typically provide checksum metadata alongside artifacts; Maven can use repository checksum policies to validate downloaded data.

To improve reliability:

- Use an organization-controlled repository manager.
- Disallow overwriting already-published release artifacts.
- Restrict or prohibit `SNAPSHOT` dependencies in release builds.
- Pin plugin and dependency versions.
- Enforce checksum/signature checks according to repository policy.
- Store approved dependencies in a repository mirror.
- Record the dependency tree and build metadata.

`.sha1` or `.md5` checksums provided by repositories help detect some download errors, but they are not strong tamper-resistant proof. For higher security requirements, use SHA-256 checksums verified through a trust policy or trusted signatures/provenance.

Do not rely on an arbitrary repository mirror as the sole source of reference digests if that mirror itself is within your threat model.

## 17. Container image and artifact registry checksums

Container images also have digests. Registries typically identify a manifest or image by its content digest, such as `sha256:<hex>`.

Example of an image referenced by digest:

```text
registry.example.com/team/orders-service@sha256:<image-digest>
```

Using a digest instead of a mutable tag like `latest` pins the exact image manifest that gets pulled. However, an image manifest digest is different from the checksum of a JAR file inside the image.

For a Java service packaged in a container, you can verify both layers:

- The SHA-256 of the release JAR.
- The digest of the published container image.

For multi-architecture images, the digest may point to an image index or manifest list; each platform-specific manifest has its own digest. Be explicit about which digest is being pinned and which platform is deployed.

A checksum or digest alone does not verify who published the image. Combine signature verification with a registry identity policy when origin authentication is needed.

## 18. Generating checksums in a CI/CD release pipeline

A release pipeline can follow these steps:

1. Check out a reviewed commit.
2. Use pinned JDK, build tools, and dependencies.
3. Run tests and build the artifacts.
4. Determine the exact list of files to be released.
5. Compute SHA-256 for each artifact.
6. Generate the checksum manifest.
7. Sign the manifest or artifacts per release policy.
8. Upload artifacts, manifest, signature, and provenance.
9. Re-download from the repository/registry to verify.
10. Publish or deploy only after all verification steps succeed.

Linux CI example:

```sh
./gradlew --no-daemon clean build

mkdir -p release
cp build/libs/app.jar release/app.jar

cd release
sha256sum app.jar > SHA256SUMS
sha256sum --check SHA256SUMS
```

If you need to sign the manifest with GPG:

```sh
gpg --armor --detach-sign SHA256SUMS
```

In production, signing keys should be managed by a secret manager or signing service with access controls. Never commit private keys to a repository, never print keys or tokens to logs, and never share personal developer keys for release automation.

If the pipeline generates a checksum and uploads both the artifact and checksum to the same storage, a post-upload verification step is still valuable for catching transfer corruption. To authenticate origin, also verify a signature or attestation against an independent trust root.

## 19. Comparing checksums before and after copying

Checksums are useful for confirming an artifact was not altered while moving across multiple systems:

```sh
sha256sum build/app.jar
sha256sum downloaded/app.jar
sha256sum deployed-copy/app.jar
```

If all three digests match, the three files have identical bytes with negligible collision probability for SHA-256. If they differ, identify which step altered the artifact:

- Incomplete upload or download.
- A storage proxy modified or corrupted the file.
- The pipeline repackaged or re-signed the JAR.
- The artifact was replaced by another version.
- The file was re-compressed or its manifest was edited.
- The deploy script copied from the wrong path.

Do not expect the checksum to stay the same if a step intentionally modifies the artifact—for example, signing a JAR after building it. Signing a JAR adds signatures and metadata to the archive, so the pre-signing and post-signing checksums will differ. Identify the final distributed artifact and hash that exact file.

## 20. Distinguishing file checksums, JAR signatures, and code signing

These mechanisms answer different questions:

| Mechanism | Question answered |
|---|---|
| SHA-256 checksum | Does the file match the reference digest? |
| JAR signing (`jarsigner`) | Are the signed entries intact and do the signatures verify against a certificate? |
| Code signing / release signature | Was the artifact or manifest signed by a trusted identity? |
| Provenance/attestation | Which source, workflow, and builder produced the artifact? |

Example of verifying a JAR signature:

```sh
jarsigner -verify -verbose -certs app-signed.jar
```

`jarsigner -verify` checks entry signatures inside the JAR and integrity under the JAR signing mechanism. To trust the signer's identity, you must also check the certificate chain, trust store, expiration, revocation policy, and issuing organization.

The checksum of a signed JAR remains useful for identifying the exact released file. JAR signatures and SHA-256 checksums complement each other rather than replacing one another.

## 21. Protecting checksums and release metadata

A checksum is only trustworthy when the reference digest is protected. Key principles:

- Publish checksums over HTTPS and authenticated release channels.
- Sign manifests or artifacts with a protected private key.
- Publish public keys or key fingerprints through an independent channel.
- Store digests in release metadata or an artifact repository with controlled access.
- Disallow overwriting published release versions.
- Protect CI signing secrets using a secret manager or workload identity.
- Restrict artifact upload and publish permissions.
- Retain provenance and logs for auditing.
- Verify the signature before the checksum when a manifest is signed.
- Never include private keys in source code, container images, or artifacts.

If a recipient fetches both the file and the digest from the same untrusted source, a checksum is not enough to defend against simultaneous replacement attacks. Verify a signature using an independently trusted key or identity.

## 22. Common errors when generating and verifying checksums

| Symptom | Possible cause | Resolution |
|---|---|---|
| Checksum differs after download | File corrupted, wrong version downloaded, or tampered with | Re-download from a trusted source; compare version and digest |
| Checksum differs between two machines | Artifacts built differently or one file was modified | Identify exact bytes and build inputs |
| `sha256sum --check` reports `FAILED` | Digest mismatch or incorrect file path | Check sidecar file, filename, and artifact content |
| PowerShell comparison fails unexpectedly | Sidecar contains newline, BOM, or whitespace | Use `Get-Content -Raw`, `Trim()`, and normalize hex |
| Java throws `NoSuchAlgorithmException` | Provider lacks the requested algorithm | Use an algorithm supported by the Java provider; inspect providers |
| Java reports wrong digest despite correct file | Hashed wrong file, file modified during hashing, or digest parsed incorrectly | Hash an immutable file, verify path, and check 64-hex format |
| Manifest cannot find file | Relative path or working directory mismatch | Run verification from the right directory or use explicit paths |
| Checksum matches but artifact is malicious | Both digest and artifact were replaced | Verify signature/provenance from an independent trust root |
| SHA-1/MD5 is required | Legacy system uses weak algorithms | Maintain compatibility only if mandatory; add SHA-256 and an upgrade plan |
| JAR checksum changes after signing | JAR signature adds entries/metadata to the archive | Hash the final artifact after signing |
| Checksum changes after re-archiving | ZIP entry order, timestamps, or compression changed | Compare the exact artifact file; do not expect identical archive bytes after repacking |
| Hashing large files uses too much RAM | Used `Files.readAllBytes()` | Stream with `InputStream` and buffered `MessageDigest.update()` |
| Digest has wrong length | Missing characters when copying or wrong algorithm used | Verify exact 64 hex characters for SHA-256 |
| CI still deploys even when verify fails | Pipeline does not check exit code | Make the verify step fail the job and block deployment |

## 23. Runbook for verifying a Java artifact

When receiving a JAR/WAR/ZIP from a release:

1. Obtain the artifact from an approved repository or release URL.
2. Obtain the corresponding checksum manifest and signature.
3. Verify the manifest signature using a trusted public key or identity.
4. Check that the manifest references the expected artifact name and version.
5. Recompute the SHA-256 of the downloaded file.
6. Compare the digest against the manifest.
7. If they do not match, stop using the artifact and preserve the file and logs for investigation.
8. If they match, check provenance/SBOM and security policies as required.
9. Record the digest in the release record or deployment metadata.
10. Deploy the exact verified file; do not replace the file after the verification step.

Never use a digest computed from the downloaded file itself as the reference digest to "verify" that same file. The reference digest must come from a trusted source independent of the file being checked.

## 24. Checklist

- [ ] Understand that checksums hash file bytes.
- [ ] Select SHA-256 or an algorithm approved by security policy.
- [ ] Do not use MD5/SHA-1 for new security verification.
- [ ] Distinguish integrity from authenticity.
- [ ] Generate checksums for the exact final distributed artifact.
- [ ] Use streaming hashing for large files.
- [ ] Validate that digests have the expected length and hex format.
- [ ] Create a manifest for multi-artifact releases.
- [ ] Verify checksums after download/copy before deploying.
- [ ] Obtain reference digests from a trusted source.
- [ ] Sign manifests/artifacts when origin authentication is required.
- [ ] Protect private signing keys and CI credentials.
- [ ] Enable Gradle dependency verification where appropriate.
- [ ] Review Maven repository checksum policies and release immutability.
- [ ] Distinguish JAR signatures, checksums, and provenance.
- [ ] Record digests in release/deployment metadata.
- [ ] Ensure pipelines halt when checksum verification fails.

## 25. References

- Java SE 17 API — MessageDigest: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Java SE 17 API — HexFormat: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- Gradle User Manual — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- GNU Coreutils — sha2 utilities: https://www.gnu.org/software/coreutils/manual/html_node/sha2-utilities.html
- Microsoft Learn — Get-FileHash: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/get-filehash
- Oracle JDK Tool — jarsigner: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Sigstore Documentation: https://docs.sigstore.dev/
- SLSA — Supply-chain Levels for Software Artifacts: https://slsa.dev/

Checksums are a simple yet critical check in artifact management. Hash the exact final file, use SHA-256, verify against a digest from a trusted source, and block deployment on mismatch. When you need to prove origin, sign the manifest or artifact and verify the signer against a trust policy; checksums, signatures, and provenance together form a verifiable, auditable release process.
