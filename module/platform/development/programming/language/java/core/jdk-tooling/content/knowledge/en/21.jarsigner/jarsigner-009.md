# Troubleshooting JAR Signature Verification Errors with jarsigner

`jarsigner -verify` is the JDK command for verifying the digital signature and integrity of a signed JAR. When verification fails, you need to determine whether the error lies in the **JAR contents**, the **signature structure**, the **signer's certificate**, or the **JDK security policy**.

A `jar verified` message is not enough to conclude that a JAR is safe. A JAR may pass cryptographic signature verification even when the signer's certificate is not trusted or the JAR contains additional unsigned entries. For release and CI workflows, use `-strict` to turn severe warnings into errors with a non-zero exit code.

## 1. What Does a JAR Signature Protect?

When signing a JAR, `jarsigner` uses the publisher's private key to sign data associated with the manifest. A signed JAR typically includes additional files in `META-INF/`:

- `MANIFEST.MF`: contains the digest (hash) of each signed entry, such as class files or resources.
- `.SF` signature file: contains the digest of the manifest or manifest sections.
- `.RSA`, `.DSA`, or `.EC` signature block file: contains the signature of the `.SF` file and the certificate/certificate chain corresponding to the signer's public key.

During verification, the tool verifies the signature of the `.SF` file, checks the digests between the `.SF` file and the manifest, and then recomputes the digests of the signed entries to compare them with the values in the manifest. If an entry's contents are modified after signing, the digest no longer matches and verification fails.

A JAR signature detects whether contents have been altered since signing and binds the signature to the signer's public key. It does not prove that the software is free of malware, does not replace code review, and does not by itself prove that the certificate owner is a trusted organization.

## 2. Running the Basic Verification Command

Syntax:

~~~sh
jarsigner -verify <jar-file>
~~~

Example:

~~~sh
jarsigner -verify app-signed.jar
~~~

If the signature and the digests of the signed entries are valid, the output typically includes:

~~~text
jar verified.
~~~

To view each entry and the signer's certificate:

~~~sh
jarsigner -verify -verbose -certs app-signed.jar
~~~

Options:

| Option | Purpose |
|---|---|
| `-verify` | Verifies the JAR signature |
| `-verbose` | Displays detailed verification output and each entry |
| `-certs` | Displays the signer's certificate when used with `-verify` and `-verbose` |
| `-strict` | Treats severe warnings as errors and returns a non-zero exit code |
| `-keystore <file>` | Specifies the keystore used to match the signer's certificate/alias |
| `-storetype <type>` | Specifies the keystore type, for example `PKCS12` |
| `-revCheck` | Enables certificate revocation status checking |
| `-verbose:all` | Displays detailed information for all entries |

`-certs` only displays certificates in verbose verify mode. It lets you inspect the Subject, Issuer, validity period, and chain packaged in the signature. If you want to match the signer against a specific alias, you can provide the keystore and alias according to the `jarsigner` verify syntax.

## 3. Reading Symbols in Verbose Output

When running `jarsigner -verify -verbose`, each entry may have prefix symbols at the start of its line:

| Symbol | Meaning |
|---|---|
| `s` | The entry's signature has been verified |
| `m` | The entry is listed in the manifest |
| `k` | At least one certificate was found in the keystore used for matching |
| `?` | Unsigned entry |

For example, an entry marked `sm` has typically had its signature verified and is present in the manifest. An entry marked `?` is content not protected by a signature. Do not confuse `k` with the certificate being trusted by a CA; this symbol indicates that the certificate matches an entry in the checked keystore, whereas chain validation and trust policy must be evaluated separately.

Verbose output may list `META-INF` files such as the manifest, `.SF`, and signature block files. These are components of the signing mechanism, not classes executed by the application.

## 4. Distinguishing Digest Errors from Certificate Trust Errors

These two error categories mean different things:

| Category | What Is Being Checked | Example |
|---|---|---|
| Integrity/signature | Whether the signature matches the signed data and entry digests remain intact | `SHA-384 digest error for Hello.class` |
| Certificate validation/trust | Whether the signer certificate is valid and the chain leads to an accepted trust anchor | `Invalid certificate chain: PKIX path building failed` |

If a signed class is modified after signing, content verification fails with a digest error. If the cryptographic signature is valid but the certificate is self-signed or missing an intermediate CA, the tool may report `jar verified` along with an invalid chain warning. This means the signed contents match the signature, but the signer's identity has not been validated against the trust policy.

Therefore, always read all warnings after the `jar verified` line. Never ignore warnings about self-signed certificates, invalid chains, unsigned entries, expired certificates, or disabled algorithms just because the summary line appears.

## 5. Common Causes of Verification Errors

### 5.1. Entry Contents Were Modified

If a signed class or resource is modified after signing, the digest stored in the manifest no longer matches. The message may look like:

~~~text
jarsigner error: java.lang.SecurityException:
SHA-384 digest error for Hello.class
~~~

Common causes:

- The JAR file was edited after signing.
- The build pipeline overwrote or updated a class/resource in an already-signed JAR.
- A tool repackaged the JAR without re-signing it.
- The artifact was corrupted during transfer or storage.

To resolve this, retrieve the artifact from a trusted release source or rebuild from source, complete all packaging steps before signing, and then re-verify. Do not modify the contents of a signed JAR and continue distributing the old signature.

### 5.2. JAR Contains Unsigned Entries

A JAR may have valid signatures for some entries while still containing new files added after signing. In verbose mode, such an entry may appear with the `?` symbol. The tool may print:

~~~text
This jar contains unsigned entries which have not been integrity-checked.
~~~

This case differs from a digest mismatch: the new entry has no signature to verify. If the release policy requires every class/resource to be signed, this is still a blocking error.

How to resolve:

1. Identify the unsigned entry from the verbose report.
2. Check whether the entry was added after the signing step or if the artifact was assembled from multiple sources.
3. Finalize the JAR before signing.
4. Re-sign the final artifact.
5. Run strict verification before releasing.

Do not add files to a JAR after the signing step. If you need to update contents, rebuild and re-sign the entire artifact.

### 5.3. Self-Signed Certificate or Untrusted Chain

Messages may include:

~~~text
The signer's certificate is self-signed.
Invalid certificate chain: PKIX path building failed
~~~

A self-signed certificate can be used to produce a cryptographically valid signature, but the system has no trusted CA basis to verify the signer's identity. An invalid chain can also result from a missing intermediate CA or a truststore that does not contain the appropriate root CA.

How to resolve:

- Use a code-signing certificate issued by a CA or internal PKI trusted by your organization.
- Ensure the required chain is properly packaged in the signature block.
- Configure trust anchors according to the verification environment's policy.
- Verify the certificate chain and fingerprint through an independent channel.
- Use self-signed certificates only for testing or when trust is explicitly distributed and managed.

Do not import a certificate of unknown origin into the truststore just to silence verify warnings. Adding a trust anchor is a trust decision, not a routine technical fix.

### 5.4. Expired or Not-Yet-Valid Certificate

If the signer certificate has expired or is not yet within its validity period, `jarsigner` may issue a severe warning. Check `Valid from`, `Valid until`, and the system clock.

If the JAR was signed while the certificate was valid, a valid timestamp can help prove the signing time. A timestamp does not make a new certificate valid and does not fix an invalid signature; it provides evidence of when the signature was created.

If the certificate was already expired at signing time or the timestamp is invalid, issue an appropriate certificate and re-sign the artifact according to policy.

### 5.5. Signature Without a Timestamp

When signing without a timestamp authority, the output may warn:

~~~text
This jar contains signatures that do not include a timestamp.
~~~

Without a timestamp, verifiers may not be able to prove that the JAR was signed while the signer certificate was valid after the certificate expires or is revoked in the future.

When your organization has a Timestamping Authority (TSA), you can create a timestamped signature using the `-tsa` option when signing:

~~~sh
jarsigner -keystore signer.p12 -storetype PKCS12 -tsa <tsa-url> -signedjar app-signed.jar app.jar release
~~~

`-tsa` is the URL of a TSA supporting the Time-Stamp Protocol. Only use endpoints designated by your organization or a trusted provider. The timestamp must be verified against the TSA's chain; a timestamp with an invalid chain can still generate warnings.

### 5.6. Revoked Certificate or Unable to Check Revocation Status

You can enable certificate revocation checking with:

~~~sh
jarsigner -verify -revCheck -verbose -certs app-signed.jar
~~~

`-revCheck` enables revocation status queries, typically via OCSP or CRL. This check may require network connectivity, a proxy, and reachable PKI endpoints. Network errors or unreachable OCSP/CRL servers should be analyzed separately from JAR digest errors.

Under current JDK defaults, revocation checking is not enabled unless `-revCheck` is specified. Apply this option according to your organization's security policy and CI environment.

### 5.7. Weak or Disabled Signature/Digest Algorithms

The JDK applies security properties to control algorithms that are no longer secure. If a JAR uses a disabled algorithm, `jarsigner` may treat the JAR as unsigned or issue an algorithm warning.

Check `jdk.jar.disabledAlgorithms` and `jdk.security.legacyAlgorithms` in the JDK security file when diagnosing. The sustainable fix is to re-sign using algorithms and keys that comply with current policy.

Do not weaken the global security policy or re-enable weak algorithms just to pass the verification step.

## 6. Using `-strict` to Catch Severe Warnings

By default, `jarsigner -verify` may return exit code 0 when the cryptographic signature and digests of signed entries are valid, even if it prints warnings about the certificate chain, self-signed signer, or unsigned entries. This is why a standard verify command is insufficient as a strict release gate.

Use:

~~~sh
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

The `-strict` option turns severe warnings into errors and makes the exit code reflect those warnings. Common codes from the JDK documentation:

| Warning Code | Meaning |
|---:|---|
| 1 | Verification failed, e.g., invalid signature or digest |
| 4 | Certificate expired/not yet valid, chain not validated, self-signed, or disabled algorithm |
| 8 | Key Usage or Extended Key Usage does not permit code signing |
| 16 | JAR contains unsigned entries |
| 32 | Signature does not match the specified alias or alias is not in the keystore |
| 64 | TSA certificate chain is invalid |

Multiple severe warnings can occur at once; the strict exit code can be a bitwise OR of the warning codes. Therefore, do not hardcode a single number for all failures. In CI, the simple and safe rule is to require the command to exit with code 0; if non-zero, stop the pipeline and save the full output for investigation.

Informational warnings such as a missing timestamp may not produce a strict error code, but still need to be evaluated against release policy. `-strict` does not replace reading the warning output.

## 7. Hands-On Example: Creating, Signing, and Verifying a JAR

The following example uses JDK 17+ and creates a small JAR for demonstration. Self-signed certificates are only for learning environments and do not represent a CA-trusted signer.

Create `src/Hello.java`:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from signed JAR!");
    }
}
~~~

Compile and create the JAR:

~~~sh
mkdir -p classes
javac -d classes src/Hello.java
jar --create --file app.jar -C classes .
~~~

Create a test PKCS#12 keystore and key pair:

~~~sh
keytool -genkeypair -alias signer -keyalg RSA -keysize 2048 -validity 365 -dname "CN=Example Signer" -keystore signer.p12 -storetype PKCS12
~~~

Keytool will prompt for the keystore password. Do not use real passwords in learning examples or commit keystores to a repository.

Sign the JAR and write to a new file:

~~~sh
jarsigner -keystore signer.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar signer
~~~

Keytool/jarsigner will prompt for the required passwords when run interactively. You can inspect the signature contents:

~~~sh
jar --list --file app-signed.jar
~~~

Inside `META-INF`, you will see the manifest and signature files, such as `SIGNER.SF` and `SIGNER.RSA` for an RSA key.

Verify:

~~~sh
jarsigner -verify -verbose -certs app-signed.jar
~~~

Run the class from the JAR:

~~~sh
java -cp app-signed.jar Hello
~~~

Stdout output:

~~~text
Hello from signed JAR!
~~~

Because the demo certificate is self-signed, the verify command may report an invalid chain or self-signed warning even though the digests and cryptographic signature match. This trust warning is intentional in this example; do not treat it as a production release certificate.

Run strict mode to see severe warnings reflected in the exit code:

~~~sh
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

With an untrusted self-signed certificate, the strict command is expected to return a non-zero exit code. Only when using a code-signing certificate with a chain accepted by the trust policy and no severe warnings will the command exit with code 0.

## 8. Simulating Two Common Errors

### Modifying a Signed Entry

Create another version of `Hello.java` that prints `tampered`, then compile it into a separate directory:

~~~sh
mkdir -p changed
javac -d changed src-tampered/Hello.java
~~~

Replace the class entry in the signed JAR:

~~~sh
jar --update --file app-signed.jar -C changed Hello.class
~~~

Re-verify:

~~~sh
jarsigner -verify -verbose app-signed.jar
~~~

The output may be:

~~~text
jarsigner error: java.lang.SecurityException:
SHA-384 digest error for Hello.class
~~~

The digest name depends on the algorithm used when signing. The error indicates that the entry's bytes no longer match the signed digest. Discard the modified artifact and rebuild/re-sign from a trusted source.

### Adding a New Entry After Signing

On another copy of the signed JAR, add a new resource after the signing step:

~~~sh
mkdir -p extra
jar --update --file app-signed.jar -C extra info.txt
jarsigner -verify -verbose app-signed.jar
~~~

The new entry may appear with the `?` symbol and an unsigned entry warning. The standard verify command may still print `jar verified` and return exit code 0 because the signed entries were not modified. With `-strict`, an unsigned entry is a severe warning and the pipeline will receive a non-zero exit code.

The two situations require different responses: a digest mismatch means signed data was altered; an unsigned entry means part of the content is not covered by the signature.

## 9. Integrating Verification into CI

In a build pipeline, run verification on the **final artifact** after packaging and signing. Do not run any JAR update step after verification, as any subsequent change can invalidate the signature.

Verification command:

~~~sh
jarsigner -verify -strict -verbose -certs build/libs/app-signed.jar
~~~

On PowerShell:

~~~powershell
jarsigner -verify -strict -verbose -certs build/libs/app-signed.jar
if ($LASTEXITCODE -ne 0) {
    throw "JAR signature verification failed"
}
~~~

On Bash:

~~~sh
jarsigner -verify -strict -verbose -certs build/libs/app-signed.jar
status=$?
if [ "$status" -ne 0 ]; then
  echo "JAR signature verification failed" >&2
  exit "$status"
fi
~~~

If the pipeline needs to verify a signature belonging to a specific alias, specify the keystore and alias using the `jarsigner -verify` syntax. The verification keystore should be provided securely; do not pass private keys or signing passwords into the verification step if not needed.

Save the `-verbose -certs` output when the pipeline fails. This output helps distinguish between digest mismatch, unsigned entry, invalid certificate chain, expired certificate, alias mismatch, and disallowed algorithm.

## 10. Step-by-Step Troubleshooting Workflow

When encountering a signature verification error, follow these steps in order:

1. **Identify the artifact**: verify that you are checking the exact JAR used by the pipeline or runtime; compare the filename, size, and download source.
2. **Run verbose verify**: use `jarsigner -verify -verbose -certs app.jar` to see which entry has an issue and inspect the certificate.
3. **Read the first error**: a digest error usually indicates a modified entry; `?` indicates an unsigned entry.
4. **Check signature files**: confirm that the `.SF` and signature block files in `META-INF` are intact and match.
5. **Inspect the signer certificate**: check Subject, Issuer, validity, Key Usage, Extended Key Usage, and chain.
6. **Check trust**: confirm the trust anchor and intermediate CA against the environment's truststore/policy.
7. **Check the timestamp**: determine whether the signature has a timestamp and whether the TSA's chain is valid.
8. **Check revocation**: if required by policy, run with `-revCheck` and verify that OCSP/CRL endpoints are reachable.
9. **Check algorithms**: look for warnings about weak or disabled algorithms in the JDK security policy.
10. **Run strict**: use `jarsigner -verify -strict` before release and require exit code 0.

Never resolve a digest mismatch by importing a certificate into the truststore; a truststore cannot make modified content validly signed. Conversely, re-signing a JAR will not solve a trust issue if the signer certificate is still untrusted.

## 11. Common Errors and Resolutions

| Message/Symptom | Common Cause | Resolution |
|---|---|---|
| `SHA-384 digest error for <entry>` | Entry contents were modified or JAR is corrupted | Retrieve the original artifact, rebuild, and re-sign after all packaging steps |
| `This jar contains unsigned entries` | Files were added after signing or JAR was only partially signed | Check for `?` symbols and re-sign the final artifact |
| `signer's certificate is self-signed` | Self-signed certificate with no CA trust anchor | Use a certificate issued by a trusted organization/CA or an approved trust policy |
| `PKIX path building failed` | Missing intermediate/root CA or untrusted chain | Check the chain and truststore; verify the fingerprint via an independent channel |
| Certificate expired/not yet valid | Certificate expired, not yet valid, or system clock is wrong | Check time, validity, and timestamp; issue an appropriate certificate |
| `no timestamp` | Signature lacks a timestamp from a TSA | Use a trusted TSA when signing if required by policy |
| `disabled algorithm` | JAR uses a digest/signature algorithm disabled by JDK policy | Re-sign with current algorithms; do not lower security policy to bypass |
| Unknown revocation status | OCSP/CRL unreachable or PKI misconfiguration | Check network, proxy, OCSP/CRL, and revocation policy |
| `jar verified` but CI should still fail | Default verify can return 0 despite severe warnings | Use `-strict` and check the exit code |
| Alias mismatch | JAR was signed by a signer other than the expected alias | Check alias/keystore and allowed signer policy |

## 12. Pre-Release Checklist

- [ ] Verifying the exact final JAR to be released.
- [ ] Every class/resource requiring protection is signed.
- [ ] No digest mismatches or corrupted signature files.
- [ ] No unintended or unapproved unsigned entries.
- [ ] Signer certificate has the correct identity and chain is accepted by trust policy.
- [ ] Certificate was valid at signing time; timestamp is valid if required.
- [ ] Key Usage/Extended Key Usage permits code signing.
- [ ] Algorithms are not disabled by JDK security policy.
- [ ] Revocation check is enabled when required by policy.
- [ ] `jarsigner -verify -strict` completes with exit code 0.
- [ ] JAR is not modified or updated after signing and verification.
- [ ] Verification output and signer details are archived with release records.

`jarsigner -verify` checks the signature and digests of signed content; `-strict` helps CI block severe warnings about the signer and unprotected entries. By separating content integrity errors from certificate trust errors, you can pinpoint the root cause, restore a trusted artifact, and release only JARs that satisfy your verification policy.

## References

- [Oracle JDK 26 — The jarsigner Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
- [Java Archive (JAR) File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)