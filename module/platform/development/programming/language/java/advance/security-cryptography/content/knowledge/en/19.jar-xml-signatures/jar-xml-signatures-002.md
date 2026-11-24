# 19.2. Using `jarsigner` to Sign, Verify, and Check Warnings in `-strict` Mode

## 1. Problem Statement and Desired Outcomes

When publishing a library or application as a JAR, the recipient needs to verify two separate things: **whether the signed entries have been modified after signing** and **whether the signer's certificate is trustworthy according to their policy**. The JDK provides `keytool` to manage keys/certificates and `jarsigner` to sign and verify JARs.

After this lesson, you will be able to:

1. Explain the JAR signature structure and the boundary between *integrity*, *authenticity*, and *trust*.
2. Create a test keystore, sign a JAR with a private key, and verify it with `jarsigner -verify`.
3. Read the `s`/`m`/`k` flags, certificate information, timestamps, and warnings in `-verbose -certs`.
4. Use `-strict` to detect severe warnings via exit codes, distinguish real failures from warnings, and configure release-time verification.

**Scope:** signing and verifying JARs with JDK tools; XML signatures are a different mechanism and are not performed with this `jarsigner` command.

## 2. What Does a JAR Signature Prove?

A JAR is a ZIP-based archive typically containing `.class` bytecode, resources, and `META-INF/MANIFEST.MF`. When signing, `jarsigner` uses the **private key** of an alias in a keystore; the X.509 certificate (containing the corresponding public key) is placed into the signature block so the recipient can verify the signature.

Key components:

| Component | Function |
| --- | --- |
| `META-INF/MANIFEST.MF` | Contains sections recording the digests of signed entries' data. |
| `META-INF/<SIGNER>.SF` | Contains the digest of the manifest or manifest sections; links entry data to the signature. |
| `META-INF/<SIGNER>.RSA` (or `.DSA`/`.EC`) | Contains the digital signature of `.SF` and the signer's certificate chain. |
| Certificate chain | Provides the public key/claimed identity; **does not automatically become a trusted source**. |
| Timestamp token (if TSA is used) | Evidence of the signing time provided by a time-stamping service, supporting verification after the certificate expires. |

Conceptual verification flow:

```text
Private key + JAR data
    -> entry manifest digest
    -> signature file (.SF)
    -> signature block (.RSA/.DSA/.EC)
    -> signed JAR

Recipient:
    signature block valid?
    -> .SF/manifest digest valid?
    -> bytes of each signed entry still match?
    -> algorithms, certificate chain, validity period, trust policy satisfied?
```

**Distinguishing three conclusions:**

- **Integrity:** the content of signed entries has not been altered since signing.
- **Authentication:** the signature matches the public key in the signer's certificate.
- **Trust:** the recipient actually accepts the signer/certificate chain based on their truststore, issuance policy, intended usage, validity period, and (when required) revocation status. A JAR may pass signature verification while its signer is still **self-signed or untrusted**.
- JAR signing **does not encrypt** files, does not certify that the program's content is safe, and does not automatically protect entries added after signing. If unsigned entries exist, you must inspect warnings and check the signing scope.

## 3. Commonly Used Commands and Options

| Tool / option | Practical meaning |
| --- | --- |
| `keytool -genkeypair` | Generate a key pair and certificate in a keystore for testing. |
| `keytool -list -v` | View alias, `Entry type`, fingerprints, chain, validity, and extensions. |
| `jarsigner -keystore <path> <jar> <alias>` | Sign a JAR using the alias's private key; without `-signedjar`, the source file may be overwritten. |
| `-signedjar <output.jar>` | Write the output to a new JAR, keeping the unsigned version for comparison. |
| `-storetype PKCS12` | Explicitly specify the keystore type; PKCS12 is the default in modern JDKs. |
| `-digestalg SHA-256` | Choose the digest algorithm for entries; distinct from the signature algorithm. |
| `-sigalg SHA256withRSA` | Signature algorithm for the RSA key in the example; must match the key type. |
| `-verify` | Verify the existing signature/digests of a JAR instead of creating a new signature. |
| `-verbose`, `-certs` | Display each entry, `s/m/k` status, and signer/certificate details. |
| `-strict` | Turn severe warnings into a **non-zero exit code**; not a “turn on extra cryptography” switch. |
| `-tsa <URL>` | Request an RFC 3161 timestamp from a Time Stamping Authority (TSA) when signing. |
| `-revCheck` | Require revocation checking (OCSP/CRL) when signing/verifying; may require network access. |

You can check tool availability via `java -version`, `javac -version`, `jar --help`, `keytool -help`, `jarsigner -help`. The examples below use **JDK 17+**, with the terminal opened in an empty practice directory. Each long command is written on **one line** so it works in PowerShell, Command Prompt, and Unix shells. Keep the same filenames and aliases for reference.

## 4. Hands-On: From Unsigned JAR to Signed JAR

### Step 1 — Create a class and package the JAR

Create `HelloJar.java`:

```java
public class HelloJar {
    public static void main(String[] args) {
        System.out.println("Hello from JAR");
    }
}
```

Compile, package with `Main-Class`, and run:

```shell
javac HelloJar.java
jar --create --file hello-unsigned.jar --main-class HelloJar HelloJar.class
java -jar hello-unsigned.jar
```

`stdout` of `java -jar`:

```text
Hello from JAR
```

`javac` produces `HelloJar.class`; `jar` packages the bytecode and manifest. Without `--main-class`, `java -jar` would lack an entry point, though the JAR can still be signed.

### Step 2 — Create a PKCS12 keystore and test signer

```shell
keytool -genkeypair -alias demo-signer -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -dname "CN=Demo JAR Signer, O=Example, C=VN" -ext "KU=digitalSignature" -ext "EKU=codeSigning" -keystore demo-signer.p12 -storetype PKCS12
```

The tool prompts for the keystore password. In this PKCS12 example, the private key uses the same store password when no separate key password is specified. Meaning of the fields:

- `-alias demo-signer`: name of the entry holding the private key; must be specified accurately when signing.
- `RSA` 3072-bit and `SHA256withRSA`: illustrative choices compatible with JDK 17+.
- `-validity 365`: the test certificate is valid for 365 days from creation; not an auto-renewing period.
- `KU=digitalSignature`, `EKU=codeSigning`: declares code-signing purpose; extension values must fit the intended usage in a real environment.
- No CA signs the certificate in this step, so `keytool` creates a **self-signed certificate**. This is intentional for observing `-strict` warnings and is **not a production release configuration**.

Inspect the entry before signing:

```shell
keytool -list -v -keystore demo-signer.p12 -storetype PKCS12 -alias demo-signer
```

Confirm `Entry type: PrivateKeyEntry`, alias, certificate chain, fingerprints, validity, `KeyUsage`, and `ExtendedKeyUsage`. Fingerprint values, timestamps, and specific details depend on each run, so there is no fixed output across all machines. Keep the `.p12` file and password in a safe place; **never commit private keys** to Git.

### Step 3 — Sign the JAR with `jarsigner`

```shell
jarsigner -keystore demo-signer.p12 -storetype PKCS12 -digestalg SHA-256 -sigalg SHA256withRSA -signedjar hello-signed.jar hello-unsigned.jar demo-signer
```

The command syntax is `jarsigner [options] jar-file alias`. Enter the password when prompted. The output is `hello-signed.jar`; `hello-unsigned.jar` remains untouched. With a self-signed signer and no TSA, the tool may emit **certificate chain not validated / self-signed** and **no timestamp** warnings. Seeing `jar signed.` does not mean every party trusts it.

Inspect the entries:

```shell
jar --list --file hello-signed.jar
java -jar hello-signed.jar
```

The listing should show `HelloJar.class`, `META-INF/MANIFEST.MF`, and the signature files `META-INF/*.SF` and `META-INF/*.RSA` corresponding to the RSA signer. Running the application still prints exactly:

```text
Hello from JAR
```

The signature filenames are derived from the alias, though they may be normalized to conform to signature entry naming rules; inspect the actual output of `jar --list`.

## 5. Verification: From Basic Check to Detailed Inspection

Run in sequence:

```shell
jarsigner -verify hello-signed.jar
jarsigner -verify -verbose -certs hello-signed.jar
jarsigner -verify -strict -verbose -certs hello-signed.jar
```

- `-verify` checks signature and digest consistency for entries within the signing scope. When cryptographic verification succeeds, the output usually includes `jar verified.`, possibly accompanied by warnings.
- `-verbose` lists entries; the legend typically includes `s = signature was verified`, `m = entry is listed in manifest`, and `k = at least one certificate was found in keystore`. For example, flags `sm` next to `HelloJar.class` indicate that this entry has a verified signature and is listed in the manifest. `k` depends on the keystore used for lookup and **does not by itself prove that the signer is trusted by every machine**.
- `-certs` combined with `-verify -verbose` displays the signer DN, certificate chain, validity dates, and TSA if present. Read the actual certificate instead of looking only at a one-line message.
- With the self-signed key pair from step 2, `-strict` **is expected to return a non-zero exit code**, commonly including bit `4` due to `signerSelfSigned`/`chainNotValidated`, even though the bytecode has not been altered. Exact output and wording vary by JDK version, trust configuration, and concurrent warnings.

After `jarsigner -verify -strict ...`, capture the exit code **immediately**, before running any other command:

```bash
# Bash / zsh (Linux, macOS):
echo $?
```

```powershell
# PowerShell (Windows):
$LASTEXITCODE
```

For example, `jar verified, with signer errors` means the signature may have verified cryptographically, but there is a **severe warning** regarding the signer/release conditions. Conversely, a `java.lang.SecurityException` message related to digests/signatures can indicate that the JAR was tampered with or corrupted and must be treated as a **verification failure**.

### Explicitly checking the expected signer/alias

You can pass the keystore and alias to the verify command:

```shell
jarsigner -verify -strict -verbose -certs -keystore demo-signer.p12 -storetype PKCS12 hello-signed.jar demo-signer
```

When an alias is supplied, `jarsigner` checks whether the signature matches the certificate belonging to that alias; a missing or wrong alias/keystore can trigger severe warnings such as `notSignedByAlias` or `aliasNotInStore`. However, matching an alias in a test keystore still **does not eliminate the fact that the certificate is self-signed**. Use a CA and controlled trust policy when verifying release artifacts.

## 6. What Does `-strict` Actually Change?

Without `-strict`, some dangerous conditions are only printed as warnings while the command may still return `0` if signing/verification itself encounters no direct error. With `-strict`, **severe warnings** are reflected in the exit code so scripts/CI can catch them. It does not fix certificates, does not fetch a new CA, does not enable revocation checking automatically, and does not force every informational warning into an error.

Code table per JDK 21 `jarsigner` documentation:

| Exit code / bit | Condition group | Interpretation |
| --- | --- | --- |
| `0` | No failure or severe warning | **Informational warnings** may still exist, such as `noTimestamp`; must inspect logs/policy. |
| `1` | `failure` | Command failed, syntax/keystore/key error, or signature/digest verification failed. |
| `4` | `hasExpiredCert`, `notYetValidCert`, `chainNotValidated`, `signerSelfSigned`, `disabledAlg`; some timestamp expiration errors | Certificate/chain/algorithm does not satisfy strict requirements. |
| `8` | `badKeyUsage`, `badExtendedKeyUsage`, `badNetscapeCertType` | Certificate extensions do not permit code signing. |
| `16` | `hasUnsignedEntry` | Unsigned data entry present, outside integrity verification coverage. |
| `32` | `notSignedByAlias`, `aliasNotInStore` | Signer does not match the requested alias/keystore. |
| `64` | `tsaChainNotValidated` | The TSA's certificate chain was not validly verified. |

**Severe warning codes are a bitmask (bitwise OR):** for example, `4 | 8 = 12` when both a certificate issue and a bad KeyUsage occur. `1` indicates failure; do not apply bit decomposition as an explanation for a failure log. Multiple causes share bit `4`, so seeing code `4` alone **does not identify the exact error**: you must analyze the warning output directly above it. Codes and warning names can vary across JDK versions; in production, consult the documentation for the exact JDK version in use.

### Severe warnings vs. informational warnings

**Severe warnings** can cause `-strict` to return non-zero: self-signed signer, unvalidated chain, expired/not-yet-valid certificate, extensions not permitting code signing, disabled algorithm, unsigned entry, wrong alias, or invalid TSA chain.

**Informational warnings** normally **do not cause `-strict` to fail on their own**:

- `noTimestamp`: the signature has no timestamp; once the certificate expires or is revoked in the future, proving the signing time may become difficult or violate policy.
- `hasExpiringCert`: certificate expiring soon (roughly six months per the documentation).
- `hasExpiringTsaCert`: TSA certificate expiring soon.
- `legacyAlg`: legacy algorithm soon to be discouraged/disallowed in the future.
- `extraAttributesDetected`: POSIX permission/symlink attributes preserved in the archive but not protected by the signature.

Specifically: **`noTimestamp` has no dedicated severe warning bit** in the table above. Therefore, `-strict` returning `0` does not prove that the JAR has a timestamp. If release policy requires a TSA, you must check the signer's `Timestamped by`/timestamp details in the output.

## 7. Four Scenarios to Diagnose Correctly

### Scenario A — JAR passes digest check, but the signer is self-signed

You create `demo-signer.p12` with `keytool -genkeypair`, sign `hello-unsigned.jar`, and run `-verify -strict`. `HelloJar.class` may show `s` and `m`; `jar verified` may appear alongside `signerSelfSigned` or `chainNotValidated`. With `-strict`, bit `4` commonly appears. This is a lesson about **trust**, not evidence that the file was modified.

How to handle in production: use a code-signing certificate with a chain accepted by recipients; distribute/verify the appropriate certificate chain rather than suppressing warnings just to make the pipeline green.

### Scenario B — A signed entry is modified after signing

If the bytes of `HelloJar.class` in the archive are altered **after signing** without re-signing, the data digest no longer matches the signed manifest. `jarsigner -verify` may throw `SecurityException` or report an invalid digest and fail. Do not “hand-edit the manifest” or remove `-strict` as a workaround: you must **rebuild the final JAR and re-sign** with a valid key.

**Pipeline rule:** compile → test → package → sign → verify → publish. Any step that alters the JAR content after signing requires re-signing and re-verifying.

### Scenario C — Adding a resource after signing

If `extra.txt` is added to an already-signed JAR without signing the new entry, signatures for old entries may remain valid, yet the new entry **is unprotected**. `-verbose` helps distinguish signed from unsigned entries; `-strict` may raise `hasUnsignedEntry` (bit `16`). Do not confuse “old signatures still pass” with “all current content is signed”.

When inspecting packaging, note that technical entries under `META-INF/` and directory entries may not show standard signing flags. Focus on actual data/class entries and `jarsigner` warnings.

### Scenario D — Signature without a timestamp

The signing command in this lesson intentionally omitted `-tsa`, so `noTimestamp` may appear. This is an **informational** warning. Use a timestamp from an organization-approved TSA when you need to prove the signature was created while the certificate was valid:

```text
jarsigner -keystore <signer-keystore.p12> -storetype PKCS12 -tsa <https://approved-TSA-URL> -signedjar <signed.jar> <unsigned.jar> <signer-alias>
```

This is **illustrative syntax**; every placeholder must be replaced with real values and an operational TSA. Network connectivity, the TSA certificate, and algorithm configuration are prerequisites. A valid timestamp **does not make a self-signed certificate trusted**, cannot repair a tampered signature, and does not replace trust-chain evaluation.

## 8. Verification Workflow for Build/CI and Release

Recommended verification sequence for the final JAR:

1. **Build and freeze the artifact:** after compile/package, no further steps modify `.class` files, the manifest, or resources.
2. **Sign with the release key:** protect the private key (vault/HSM/PKCS11 or appropriate secret mechanism), use the right alias, proper certificate chain, and TSA if required by policy.
3. **Verify the exact JAR to be published:** run `jarsigner -verify -strict -verbose -certs <artifact.jar>`; save logs and capture the exit code immediately after the command finishes. Any non-zero exit code is a blocking signal for investigation.
4. **Evaluate logs beyond the exit code:** check for unsigned entries, whether the signer matches the expected identity/certificate, whether algorithms are disabled/legacy, whether a timestamp is required, whether validity/chain meet policy, and whether `-revCheck` is enabled when required.
5. **Acceptance policy:** publish only when integrity, identity/trust, and additional requirements all pass. Never treat `jar verified.` alone as sufficient.

Example CI command for a **real artifact signed with an appropriate certificate**:

```shell
jarsigner -verify -strict -verbose -certs release.jar
```

The script/CI must check the exit code of that exact command and archive stdout/stderr as evidence. If policy requires a timestamp or a specific signer, add structured checks against logs/certificates/keystores and verify the allowed signer; do not infer compliance from `exit 0`. **Never use the lab's self-signed JAR to simulate a passing production CI run.**

With `-revCheck`, verification may require OCSP/CRL and network access. Do not toggle it implicitly; follow the system's revocation-checking policy. Manage the lifecycle, access control, rotation, and revocation of signing keys; passwords should never be passed as command-line literals in real environments (they can leak through command history or process lists). `jarsigner` supports `-storepass:env`/`-storepass:file` in suitable setups, and can also prompt interactively.

## 9. Common Errors and How to Fix Them

| Symptom | Possible cause | Verification action |
| --- | --- | --- |
| `jarsigner: key associated with ... not a private key` or alias not found | Wrong alias, or entry is a trusted certificate instead of `PrivateKeyEntry` | `keytool -list -v -keystore ... -alias ...`; use the right keystore/alias containing the private key. |
| Error opening keystore/password | Wrong file, `-storetype`, storepass/keypass, or provider restriction | Check path, keystore type, password, and key provider; do not print secrets to logs. |
| `jar verified.` but `-strict` reports signer errors | Severe warning about self-signed/chain/cert/unsigned entries | Read specific warnings and bitmask code; fix root cause instead of removing `-strict`. |
| `hasUnsignedEntry` | Entry added after signing or wrong build/sign order | Inspect unsigned entries, complete the build, then re-sign. |
| `invalid ... digest`/`SecurityException` | Signed entry modified, corrupted, or signature/manifest inconsistent | Compare against source artifact; rebuild, re-sign, and verify; do not edit signatures manually. |
| `badKeyUsage` or `badExtendedKeyUsage` | Certificate not permitted for code signing | Use a certificate with proper KU/EKU per CA policy. |
| `noTimestamp` | TSA not used when signing | If required by policy, sign with an approved TSA and verify the timestamp afterward. |
| `disabledAlg` / `legacyAlg` | Algorithm/key size violates or will soon violate JDK policy | Use current algorithms/key sizes; do not relax `jdk.jar.disabledAlgorithms` to bypass checks. |
| Different results between two machines | Different JDK versions, truststores, algorithm policies, system time, revocation, or certificate chains | Record `java -version`, arguments, signer, chain, and logs; standardize the test environment. |

## 10. Self-Check Questions

1. **Is `jar verified.` enough to trust the publisher?** No. It only addresses signature/digest verification; you must evaluate signer identity, certificate chain, trust policy, and warnings.
2. **Why might the lab example return `4` under `-strict`?** The signer created with `keytool -genkeypair` is self-signed; `signerSelfSigned` and `chainNotValidated` belong to severe bit `4`.
3. **Does `noTimestamp` cause `-strict` to return non-zero?** Not if `noTimestamp` is the only warning; it is an informational warning. A custom policy can still reject artifacts missing a TSA.
4. **What code results from two warnings at once?** Severe warning codes are bitwise ORed, e.g., `4` and `8` become `12`; you must read the log to identify each cause.
5. **Is adding `config.properties` after signing safe?** You cannot assume it is protected by default. The new entry may be unsigned even though old entries' signatures remain valid.
6. **When should `-revCheck` be used?** When policy requires revocation checking; plan for OCSP/CRL and network connectivity.
7. **Why should `-signedjar` be used?** To produce a separate output JAR and avoid accidentally overwriting the unsigned artifact, making comparison and reproducibility easier.

## 11. Practice Checklist

- [ ] Create `HelloJar.java`, run `javac`, package, and run `hello-unsigned.jar` successfully.
- [ ] Create `demo-signer.p12` with `keytool`; verify alias `demo-signer` is `PrivateKeyEntry`.
- [ ] Sign into `hello-signed.jar`, observe the two signature files in `META-INF`, and run the JAR as before.
- [ ] Run `-verify`, `-verify -verbose -certs`, and `-verify -strict -verbose -certs`; match `s/m/k` flags against entries.
- [ ] Capture the exit code immediately after `-strict`, identify self-signed/chain severe warnings, and distinguish them from informational `noTimestamp`.
- [ ] Explain the behavior when a signed entry is modified or a new unsigned entry appears.
- [ ] Propose a build → sign → verify → publish workflow with policy-compliant certificates, trust, and TSA.

**JDK 21 reference documentation:** [jarsigner command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html) (signature structure, `-verify`, `-strict`, warnings/exit codes) and [keytool command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html) (PKCS12, `-genkeypair`, X.509 KU/EKU). When deploying on another JDK version, check the documentation and `java.security` configuration for that exact version.
