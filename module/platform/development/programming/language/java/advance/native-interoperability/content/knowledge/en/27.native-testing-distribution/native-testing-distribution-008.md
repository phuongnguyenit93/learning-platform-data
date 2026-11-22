# Verifying Provenance, Integrity, and Version of Release Binaries

## 1. Why verify before loading a native library?

A Java application may load a native library via JNI (`System.load`, `System.loadLibrary`), use the Foreign Function & Memory API (FFM) to look up functions in a library, or distribute an accompanying native executable/agent. `.so` (Linux), `.dylib` (macOS), and `.dll` (Windows) files are **machine code**, which can access process resources and directly affect the integrity of the JVM. A correct filename does not prove that the contents are safe or compatible.

Before releasing, downloading, or deploying a binary, four related but **distinct** questions must be answered:

1. **Provenance / authenticity:** Who created and published the file? Which source repository, commit, build process, and publisher did it originate from? Is there cryptographic evidence binding the file to a trusted identity?
2. **Integrity:** Do the received bytes match the approved artifact exactly? Are the SHA-256 digest and signature valid?
3. **Version identity:** Is it the exact release, build, commit, and ABI contract that the application requires? Is it the version that was tested and approved for release?
4. **Compatibility:** Does the binary run on the target OS, CPU, libc/ABI, and JDK, with all required native dependencies and exported symbols?

**Control conclusion:** A file with a matching SHA-256 whose digest was obtained from an untrusted source still does not authenticate the publisher. A valid signature belonging to a signer not on the allowlist is also insufficient. A binary with the right version name may still have the wrong architecture or have had its contents altered after release.

## 2. Distinguishing types of evidence

| Evidence | What does it prove when verified properly? | Limitations to remember |
| --- | --- | --- |
| Filename such as `nativebridge-2.4.1-linux-x86_64.so` | Suggests the intended release and platform | Can be renamed arbitrarily; does not authenticate contents |
| File SHA-256 | Contents match the expected digest | Expected digest must come from an authenticated manifest or an independent trusted source |
| Digital signature of artifact/manifest | Data was signed by a verifiable key/identity and has not been altered from the signed content | Must verify publisher identity, trust root, and time/revocation policy; being signed does not mean the code has no vulnerabilities |
| Build provenance / attestation (e.g., SLSA, in-toto) | Can bind the artifact digest to the builder, source commit, and build process information | Only meaningful after verifying the signature, subject digest, builder/source identity, and expected policy |
| `version` metadata, Git tag, build ID | Supports release/build traceability and selecting the right version | Tags can be moved, metadata can be forged if the artifact has not been authenticated |
| SBOM | Lists the declared components/dependencies of the build | An SBOM is not a signature nor does it automatically prove the list is complete; it also needs to be authenticated and matched against the artifact |
| ELF `SONAME`, Mach-O version, Windows `FileVersion` | Provides partial ABI information or version metadata | Does not necessarily match the semantic version; does not replace digests and compatibility tests |

### Where does the source of trust come from?

A usable order of evaluation:

- **Approved distribution source:** official vendor release or controlled registry/package repository; pin specific versions and artifacts, and avoid downloading arbitrarily from unrecognized mirrors.
- **Independently verified publisher identity:** public key/certificate, organization name, Sigstore certificate identity + OIDC issuer, or package signing key distributed over a trusted channel **before** checking the file.
- **Digest bound to signed information:** direct signature on the binary, signed manifest, or attestation containing the artifact digest. Verify the signature of the object that **actually covers the digest** of the received file.
- **Source and build:** approved source repository, specific commit, build workflow, and builder identity; check these values against the organization's expectations instead of only seeing “attestation valid”.
- **Access control and immutability:** release tags, artifact buckets, and package repositories must have policies to prevent overwriting; record the digest at the time of approval.

Downloading `library.so` and `SHA256SUMS` from the same compromised page and comparing the two files **is not sufficient against an attacker** who can replace both the binary and the checksum. HTTPS protects data in transit but does not replace evaluating release identity, signatures, and trust roots.

## 3. Designing identity information for a native release

For each artifact, the release manifest should provide clear, machine-verifiable information:

| Field | Meaning |
| --- | --- |
| Artifact name, size, SHA-256 | Exactly identifies the approved bytes |
| Release version and build number | Published version; build number helps distinguish multiple builds within the same version |
| Source repository and full commit SHA | Ties the version to specific source code; do not only record a branch name |
| Build workflow, builder identity, toolchain/compiler | Traces who/which tool produced the binary |
| Target OS, CPU architecture, ABI/libc baseline | Distinguishes Linux x86-64 glibc from Linux aarch64/musl, Windows x64, macOS arm64… |
| Exported API/ABI version and native dependencies | Checks symbol names, parameter types, calling convention, runtime dependencies |
| Min/max supported JDK or tested compatibility range | Java runtime and JNI/FFM binding expectations |
| Publisher identity, signature/bundle, attestation | Inputs for verifying signature/provenance against policy |
| SBOM and release information | Serves inventory, vulnerability analysis, and traceability |

**Distinguishing version from artifact identity:** the same version `2.4.1` is sometimes rebuilt for a different architecture, using a different compiler, or to patch a release; the digest will differ. If a release version allows multiple targets, there must be a **separate digest list for each artifact**. Using only `2.4.1` or a directory name for verification is not enough. Version fields embedded inside the binary itself can also be modified; they are only trustworthy after the artifact has been verified.

Recording versions via semantic versioning is useful for describing API changes, but **ABI compatibility is not automatically guaranteed by major/minor/patch names**. The JNI/FFM binary must still be checked for symbols, data layout, calling convention, and actual dependency versions.

## 4. Complete verification workflow before loading/running

### Step 1 — Pin the release and expected identity policy

Determine from trusted release documentation: publisher, approved repo/commit or tag, target OS/architecture, artifact digest, and allowed signing key or signing identity. Clearly distinguish **what is expected before downloading** from information declared by the newly downloaded file itself. With Sigstore keyless, the policy must specify the expected **certificate identity and OIDC issuer**; accepting “any valid signature” is not enough.

Do not use floating tags like `latest` to confirm an approved build. When deploying OCI containers, lock the image by **image digest** rather than only by tag; then still verify each native binary extracted by the pipeline if independent traceability is needed.

### Step 2 — Download and place in a non-executable staging area

Store the artifact and accompanying evidence (manifest, signature, verification bundle, attestation, SBOM) in a staging area with write-access controls. Do not call `System.load`, execute the binary, or run bundled scripts from an unauthenticated artifact. Keep the name and path of the checked file; do not switch to another file with the same name after verification.

When the artifact comes from a zip/tar archive, guard against path traversal, unexpected symbolic links, and extracting/overwriting files outside staging. For native libraries, dependencies loaded by the dynamic loader **are also executable code**, and must have a trusted origin and search scope.

### Step 3 — Compute SHA-256 independently on the exact downloaded file

Linux:

```bash
sha256sum nativebridge-2.4.1-linux-x86_64.so
```

macOS:

```bash
shasum -a 256 libnativebridge.dylib
```

Windows PowerShell:

```powershell
Get-FileHash -LiteralPath .\nativebridge.dll -Algorithm SHA256
```

The commands above only **compute** the digest; they do not decide on their own that the file is trustworthy. Compare the 64 hex characters with the digest of the **exact artifact/target** in the authenticated manifest. Any discrepancy must halt usage, trigger rechecking the path/filename, and report an error. Do not ignore warnings because “it is only off by one character”.

Choose SHA-256 or a strong algorithm accepted by policy. Do not use MD5/SHA-1 for defending against intentional tampering. A hash matching an independent source/signed manifest shows the integrity of the **bytes**, and does not by itself prove functionality, safety, or ABI.

### Step 4 — Verify signature and provenance

If the publisher provides a detached/certified release signature, verify the signature against a **trust root provisioned outside the artifact**, then match the signer identity against an allowlist. When using Sigstore/Cosign keyless, you can verify a blob and verification bundle with a command of the form:

```bash
cosign verify-blob release.bin --bundle release.sigstore.json --certificate-identity signer@example.org --certificate-oidc-issuer https://accounts.google.com
```

This is a **command-interface illustrative example**: `release.bin`, `release.sigstore.json`, and the email/issuer identity must be replaced with actual values provided by the **authenticated publisher**; do not trust `signer@example.org` by default. Only conclude PASS when the signature/bundle is valid, the identity/issuer matches policy, and the signed content binds the **digest of the artifact to be released**. Signing-time / transparency-log proof mechanisms must also be checked in the manner supported by the tool.

If receiving an SLSA/in-toto attestation, in addition to validating the signature, you must also cross-check:

1. Does `subject` have the exact SHA-256 of the file being checked?
2. Are `builder.id` and the build system on the approved list?
3. Do the source repository, revision/commit, build type, workflow, and external parameters match expectations?
4. Do the declared dependency/source materials correspond to the selected release?
5. If the attestation is missing, has the wrong subject, or uses an out-of-policy builder, the pipeline **FAILS**, even if the signature may be cryptographically valid.

**Do not confuse:** provenance tells you the conditions and process under which the artifact was created, but does not guarantee the source code is bug-free or that the builder has never been compromised; it is one layer of evidence to control supply-chain risk.

### Step 5 — Check file format, OS/CPU, and native dependencies

The commands below are **metadata inspection commands for an already-verified binary**. They are not signature verification steps.

| Platform | Common commands | What to read? |
| --- | --- | --- |
| Linux | `file nativebridge.so`, `readelf -h nativebridge.so` | ELF class 32/64-bit, `Machine`, endianness, ELF type |
| Linux | `readelf -d nativebridge.so` | `SONAME`, `NEEDED`, `RPATH` / `RUNPATH`, and dynamic dependencies |
| Linux | `readelf -Ws nativebridge.so`, `readelf --version-info nativebridge.so` | Exported symbols, versioned symbols/GLIBC requirements |
| macOS | `file libnativebridge.dylib`, `otool -hv libnativebridge.dylib` | Mach-O architecture and header |
| macOS | `otool -L libnativebridge.dylib` | Install names, dependencies, compatibility/current version of the dylib |
| Windows | `dumpbin /headers nativebridge.dll`, `dumpbin /dependents nativebridge.dll` | PE machine type, DLL dependencies (requires Visual Studio Build Tools) |
| Windows | `dumpbin /exports nativebridge.dll` | Exported symbols |
| Windows PowerShell | `(Get-Item .\nativebridge.dll).VersionInfo` | FileVersion/ProductVersion if embedded by the publisher |

Linux example:

```bash
file nativebridge.so
readelf -h nativebridge.so
readelf -d nativebridge.so
readelf -Ws nativebridge.so
readelf --version-info nativebridge.so
```

Actual output depends on the file being inspected; there is no single fixed stdout valid for every library.

**You must cross-check** both CPU architecture and ABI: Linux x86-64 glibc differs from Linux x86-64 musl; Windows PE differs from Linux ELF; macOS arm64 differs from x86_64 (unless the artifact is a universal/fat binary containing the matching architecture). An ELF with the right architecture may still require a newer GLIBC than the target machine. Also inspect loader search paths: `RPATH/RUNPATH`, `java.library.path`, DLL dependency paths, `@rpath`/`@loader_path` on macOS. Replaced dependencies on the search path can cause a different binary to be loaded than the checked file.

On Linux, prefer `readelf`/`objdump` to **statically inspect** metadata of untrusted files. `ldd` is useful to see how libraries will resolve in the current environment, but with untrusted files or different loaders, using it can carry risks; only run it after the authentication step and in a controlled environment.

### Step 6 — Check platform-appropriate code signing

**Windows:** If the publisher uses Authenticode, read the status, certificate, and publisher identity, rather than only looking at `Status=Valid`.

```powershell
$sig = Get-AuthenticodeSignature -LiteralPath .\nativebridge.dll
$sig | Select-Object Status, SignerCertificate
```

`Get-AuthenticodeSignature` is only available on Windows. Verification must check the publisher/certificate chain against the organization's policy; an unsigned file or one signed by an unauthorized party does not pass provenance checks solely on the basis of a self-published SHA-256.

**macOS:** If releasing a signed dylib/app, verify the signature and signing identity information:

```bash
codesign --verify --verbose=2 libnativebridge.dylib
codesign -dv --verbose=4 libnativebridge.dylib
```

A `codesign --verify` result basically confirms the consistency of the signature on the signed code; to confirm the **right publisher**, you also need to check the designated requirement, Team ID/certificate identity, and appropriate trust policy. An ad-hoc signature or self-signed signature does not automatically represent an approved publisher. Notarization/Gatekeeper, when relevant to a distribution package, is a different check from build provenance.

**Linux:** Many `.so` files do not embed signatures under a common standard like Authenticode. You must use detached signatures, signed package metadata (e.g., package manager), or verified attestations; `readelf` alone does not verify the publisher. Check the identity of the repository/package signing key independently.

### Step 7 — Cross-check version and ABI contract with the application

Before putting the binary into production, check the following version layers:

- **Release version:** do the manifest and release notes match the approved version? Is the OS/CPU target artifact from that exact release?
- **Source/build identity:** do the source commit, toolchain, build number, and artifact digest match the attestation?
- **Embedded file metadata:** Windows `FileVersion/ProductVersion`, Linux `SONAME`/build ID (if present), Mach-O `current_version` / `compatibility_version`. These are **metadata for cross-checking**, not necessarily equal to the release semver and not a substitute for signatures.
- **ABI/contract:** exported JNI names, C symbols for FFM, calling convention, alignment/layout, struct sizes, memory ownership, API names/behavior; for JNI, also `JNI_OnLoad` conventions and JNI version if the library uses them. A mismatch can cause linker errors, corrupted data, or crashes.
- **Runtime compatibility:** supported JDK/JNI version, OS patches, libc/C runtime, native dependency versions, CPU instruction set.
- **Actual loaded artifact:** after verification, verify that the application uses the exact approved path/version/digest. `System.load` uses an absolute path; `System.loadLibrary` searches by logical name and loader search configuration, so there is a risk of loading another file with the same name.

If there are two builds with the same version but different digests, **do not validate by checking only the version name**. You must know it is the approved build, from the right source/attestation, and for the right OS/ABI. Reproducible builds can help compare outputs from the same source/build recipe if the process is truly deterministic; not every binary is reproducible by default due to timestamps, paths, or compilation metadata.

## 5. Java 17+ lab: self-verifying a file's SHA-256

The following example only **reads bytes and compares digests**, without loading or executing the library. It is useful as an independent gate before using JNI/FFM. The expected SHA-256 must be provided from a **verified signed release manifest**, not taken arbitrarily from the same URL as the binary without verifying identity.

Create the file **`VerifyBinary.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class VerifyBinary {
    private VerifyBinary() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[1].matches("(?i)[0-9a-f]{64}")) {
            System.err.println(
                    "Usage: java VerifyBinary <file> <trusted-sha256-hex>");
            System.exit(2);
            return;
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            byte[] buffer = new byte[8192];
            int size;
            while ((size = input.read(buffer)) != -1) {
                if (size > 0) {
                    digest.update(buffer, 0, size);
                }
            }
        }

        byte[] actual = digest.digest();
        byte[] expected = HexFormat.of().parseHex(args[1]);

        if (MessageDigest.isEqual(expected, actual)) {
            System.out.println("SHA-256 OK");
        } else {
            System.out.println("SHA-256 MISMATCH");
            System.exit(1);
        }
    }
}
```

**Explanation:** `Files.newInputStream` reads in blocks so the entire binary does not need to be loaded into RAM; `MessageDigest.getInstance("SHA-256")` computes the digest of the **actual file contents**; Java 17's `HexFormat` converts 64 hex characters into 32 bytes; `MessageDigest.isEqual` compares the two digests. The program only outputs `SHA-256 OK` when they are equal, and returns exit code `1` when they do not match; invalid arguments use exit code `2`. File reading errors are reported via exceptions and the process fails the gate.

To verify with known data instead of a hypothetical binary, create a test file containing **exactly the three ASCII bytes `abc`, with no trailing newline**.

On Linux/macOS:

```bash
printf 'abc' > sample.bin
javac VerifyBinary.java
java VerifyBinary sample.bin ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

On Windows PowerShell (creating the exact three ASCII bytes and using the same `javac`/`java`):

```powershell
[System.IO.File]::WriteAllBytes('sample.bin', [Text.Encoding]::ASCII.GetBytes('abc'))
javac VerifyBinary.java
java VerifyBinary sample.bin ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

**Exact stdout** of the command run against the `abc` file:

```text
SHA-256 OK
```

If you pass a non-matching 64-hex-character SHA-256 (for example, all zeros), the same `abc` file will produce:

```text
SHA-256 MISMATCH
```

On a mismatch, the program exits with code `1`, convenient for CI to reject a release. This example proves the correctness of the digest comparison; it does **not** prove that `sample.bin` is a safe native binary. When substituting a real native file, use the SHA-256 of the approved artifact and verify the signature/attestation of the source containing the digest.

### Note on preventing file replacement after verification

The flow `verify(file A) → an actor modifies the file → load(file A)` can suffer from **time-of-check/time-of-use (TOCTOU)**. Place the artifact in an immutable staging/deploy directory or grant only read permissions to the runtime after checking; do not download/overwrite or swap symlinks at the same path between verify and `System.load`. Confirm that native dependencies resolved by the loader also come from controlled sources. Printing checksums in startup logs is useful for build traceability, but logging does not replace mechanisms that enforce the application uses the exact verified file.

## 6. CI/CD workflow: authenticating and blocking bad releases

Gates can be organized in a sequence:

```text
Build native for each OS/CPU target
  -> Unit + JNI/FFM integration tests on the appropriate target
  -> Record source commit, compiler, ABI/version, and SHA-256 of each artifact
  -> Generate provenance / SBOM and sign artifact or manifest/attestation
  -> Publish immutably (artifact + evidence)
  -> Download to an independent verification environment
  -> VERIFY signer/trust root + provenance policy + artifact digest
  -> VERIFY file format/architecture/dependency + release/ABI version
  -> Smoke test loading and calling JNI/FFM functionality in an isolated environment
  -> Promote the exact digest to the release or deployment channel
```

A transparent set of pass/fail rules:

| Gate | When does it PASS? | When does it FAIL? |
| --- | --- | --- |
| Provenance | Signer/issuer, publisher, builder, and source commit match policy, and artifact subject matches | Cannot be verified, unknown identity, missing/invalid provenance, or unapproved commit |
| Integrity | SHA-256 of the **bytes being released** matches the authenticated digest | Digest mismatch or no trusted digest source |
| Version | Release/build/commit and exact target artifact are approved | Same filename but different version/commit/digest, or release has been altered |
| Compatibility | OS/CPU/ABI/JDK, symbols, loader deps, and native tests pass | Wrong architecture, missing dependency, ABI mismatch, load or smoke test failure |
| Deployment | Immutable artifact, exact pinned digest, logs include sufficient identity | Redeploying a floating tag or replacing the binary after verify |

Minimum audit information to retain includes: artifact digest, release version, source revision, builder + signer identity, verification result, timestamp and test environment, and actual promoted file. In CI/CD, **missing authentication information is a failing state**, and must not be silently passed just because the file downloaded successfully.

## 7. Common failure scenarios

1. **“The checksum is correct because the `SHA256SUMS` file in the same directory says so.”** If both the file and the checksum come from an altered source, there is no independent proof of authenticity. A signature/manifest verified by an approved key or identity is required.
2. **“The signature is valid, so everything is safe.”** The signer must be the expected publisher; a signature does not guarantee there are no logic bugs, malicious code from source, or dependency vulnerabilities.
3. **“Same version `2.4.1` means the same binary.”** Builds per platform or rebuilds have different digests. A version label cannot replace an artifact digest.
4. **“`readelf` shows x86-64, so the library will definitely run.”** It can still have the wrong libc, GLIBC symbol version, instruction set, dependencies, FFM layout, or JNI ABI.
5. **“Windows `FileVersion`, macOS `current_version`, Linux `SONAME` are proof of the publisher.”** They are metadata/ABI hints and can be forged if the signature/digest has not been verified.
6. **“Having verified `libnative.so` is enough.”** The dynamic loader may load another native dependency on a controlled search path; the bundle and dependency chain must also be managed.
7. **“After checking, it is fine to replace the file with the same name.”** That is a TOCTOU risk. Pin the digest, keep the checked copy immutable, and prevent writes/symlink swaps before loading.
8. **“An attached SBOM means provenance is proven.”** An SBOM is an inventory; you still must verify provenance, signatures, and the binding between the SBOM and the artifact.
9. **“Seeing `UnsatisfiedLinkError` means there is a security issue.”** A load failure can also simply be due to a wrong path, missing library, missing symbol, or wrong architecture. Specific evidence is needed, not automatic assumptions.
10. **“Run the unknown file first to inspect its metadata.”** An unauthenticated binary should not be executed; use static inspection first, and only smoke test in a controlled environment after passing the provenance/integrity gates.

## 8. Release checklist

Before bringing a native library into a Java runtime environment, verify each item below:

- [ ] Artifact is obtained from an allowed release source; release/commit/target has been explicitly selected.
- [ ] Publisher/trust root is independently verified; signature or signed provenance is valid and matches policy.
- [ ] The **actual** SHA-256 of the file matches the authenticated digest for the exact target artifact.
- [ ] Version, source revision, build identity, and related metadata are consistent; filename alone is not used as evidence.
- [ ] OS/CPU, ABI/libc, exported symbols, dependencies, and supported JDK/JNI/FFM contract are compatible.
- [ ] Library and dependencies are loaded from approved paths/copies; no overwrite path exists after verify.
- [ ] Integration/smoke tests with JNI or FFM on the exact binary and target environment have passed.
- [ ] Logs/manifests record the digest, publisher, source commit, and release version for traceability or rollback.

**Core takeaway:** Verifying **who created it**, **which exact bytes**, **which build/release it belongs to**, and **whether it runs properly on the target environment** are four verification layers that must be performed together. With native interoperability, skipping one layer can cause the JVM to load the wrong machine code even when the filename looks completely valid.

## Official references

- [Oracle Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html) and [HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): computing and comparing SHA-256 in Java.
- [Sigstore — Cosign quickstart, verify-blob](https://docs.sigstore.dev/quickstart/quickstart-cosign/): verifying blobs, verification bundles, signer identity, and issuer.
- [SLSA — Verifying artifacts](https://github.com/slsa-framework/slsa/blob/main/spec/verifying-artifacts.md): verifying provenance by builder identity, subject, and build policy.
- [Microsoft Learn — Get-FileHash](https://learn.microsoft.com/powershell/module/microsoft.powershell.utility/get-filehash) and [Get-AuthenticodeSignature](https://learn.microsoft.com/powershell/module/microsoft.powershell.security/get-authenticodesignature): hashing and signature verification on Windows.
- [Apple — Code Signing Tasks](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/Procedures/Procedures.html): how to verify signatures and designated requirements.
- [GNU binutils — readelf](https://sourceware.org/binutils/docs/binutils/readelf.html): reading ELF metadata, symbols, and dependencies for native compatibility checks.