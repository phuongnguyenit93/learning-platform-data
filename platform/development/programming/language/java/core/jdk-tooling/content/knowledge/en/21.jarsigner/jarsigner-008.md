# Unsigned JAR: How to Identify, Sign, and Verify with jarsigner

## 1. What is an Unsigned JAR?

A JAR (Java ARchive) is a ZIP file used to package classes, resources, and metadata for a Java application or library. An **unsigned** JAR is a JAR that does not yet have a valid digital signature from a publisher.

An unsigned JAR is not necessarily corrupted or unable to run. A Java application can still use an unsigned JAR on the classpath or module path in standard deployment scenarios. The issue is that recipients have no digital signature to verify that the JAR contents were signed by a specific identity and that the signed entries have not been modified since signing.

It is important to distinguish:

- **Unsigned JAR**: has no digital signature yet.
- **Signed JAR**: contains signature metadata to verify the contents and the signer's certificate.
- **JAR modified after signing**: the entry digest no longer matches the signature; verification will report an error.
- **Partially signed JAR**: has a signature, but still contains unsigned entries, such as files added after signing.

An unsigned JAR does not automatically mean malicious code. A signed JAR also does not prove a program is safe. A signature helps verify integrity and signer identity according to the certificate; deciding whether to trust the signer still depends on the organization's trust policy.

## 2. A Manifest Is Not a Digital Signature

A typical JAR may contain:

~~~text
application.jar
  META-INF/
    MANIFEST.MF
  com/example/Main.class
  config/app.properties
~~~

`META-INF/MANIFEST.MF` contains metadata such as the manifest version, main class, and per-entry attributes. Having a manifest alone does not mean the JAR is signed.

After signing, the structure typically includes additional files in `META-INF`:

~~~text
application-signed.jar
  META-INF/
    MANIFEST.MF
    RELEASE.SF
    RELEASE.RSA
  com/example/Main.class
  config/app.properties
~~~

The names and extensions depend on the signer name and signature algorithm. You may encounter `.SF` alongside `.RSA`, `.DSA`, or `.EC` signature blocks.

Main roles:

- `MANIFEST.MF`: lists the entries and their metadata.
- `RELEASE.SF`: contains digests of the manifest or manifest sections.
- `RELEASE.RSA` (or `.DSA` / `.EC`): contains the digital signature of the `.SF` file and the signer's certificate.

When signing, `jarsigner` creates or updates manifest digests for the signed entries, and generates the signature file and signature block. When verifying, the tool checks the digest chain and signature to detect content mismatches.

You should not manually edit signature files in `META-INF`. If the JAR contents change, rebuild the artifact and re-sign it through your release process.

## 3. What Does a JAR Signature Protect?

A JAR digital signature supports two goals:

**Integrity**

Entry digests are verified. If a signed class or resource is modified, the digest will not match and verification will report an error.

**Signer identity**

The signature block contains the signature and digital certificate. Recipients can inspect the certificate, CA chain, validity period, and the identity attested by the certificate.

Signing does not encrypt the JAR. Recipients can still list and read bytecode, manifests, and resources.

Signing also does not guarantee that the code is free of vulnerabilities or malicious behavior. A malicious JAR can still be signed by a signer that the recipient already trusts. Therefore, combine signature verification with publisher source checks, code reviews, security scanning, and testing.

## 4. Checking an Unsigned JAR with jar and jarsigner

First, list the contents:

~~~bash
jar --list --file application.jar
~~~

Verify the JAR:

~~~bash
jarsigner --verify --verbose --certs application.jar
~~~

For an unsigned JAR, JDK 24.0.2 outputs something like:

~~~text
?     425 ... demo/Hello.class

  s = signature was verified
  m = entry is listed in manifest
  k = at least one certificate was found in keystore
  ? = unsigned entry

jar is unsigned.
~~~

The `?` mark indicates an entry without a signature. The phrase `jar is unsigned.` is the direct diagnostic indicating that the archive has not been signed.

An important detail for CI scripts: on JDK 24.0.2, `jarsigner --verify` on an unsigned JAR still returns exit code 0 even though it prints `jar is unsigned.`. Therefore, checking for exit code 0 alone is not enough to confirm that an artifact is signed. Check the output text or use a strict verification policy tested with the JDK version in your pipeline.

## 5. Generating a Key Pair for Signing a JAR

`jarsigner` uses a private key and certificate retrieved from a keystore. It does not generate a signer identity on its own.

To generate an RSA key pair in a PKCS12 keystore for hands-on practice:

~~~bash
keytool -genkeypair \
  -alias demo-signer \
  -keyalg RSA \
  -keysize 3072 \
  -validity 30 \
  -dname "CN=JAR Signing Demo, OU=Test, O=Example, C=VN" \
  -keystore signer.p12 \
  -storetype PKCS12
~~~

`keytool` will prompt for the keystore password and may ask for a separate password for the private key. This example creates a self-signed certificate for learning the workflow; it does not create a certificate trusted by public CAs.

Parameters:

| Parameter | Meaning |
|---|---|
| `-genkeypair` | Generates a public/private key pair and certificate |
| `-alias demo-signer` | Identifier name for the entry in the keystore |
| `-keyalg RSA` | Key generation algorithm |
| `-keysize 3072` | RSA key size |
| `-validity 30` | Certificate validity period in days |
| `-dname` | Distinguished Name in the certificate |
| `-keystore signer.p12` | Keystore file |
| `-storetype PKCS12` | Keystore format |

For production releases, use an appropriate code-signing certificate issued by a CA or your organization's PKI. Protect the private key with least-privilege access, a hardware security device, or a suitable secret manager. Do not put real passwords in scripts, command history, or CI logs.

Inspect the entry:

~~~bash
keytool -list -v -keystore signer.p12 -storetype PKCS12
~~~

The signer needs a private key entry (typically displayed as `PrivateKeyEntry`) along with its certificate chain. A trusted certificate entry only contains a public certificate and has no private key for signing.

## 6. Signing an Unsigned JAR with jarsigner

Suppose you have `application-unsigned.jar` and a keystore `signer.p12` containing a private key entry with alias `demo-signer`.

Signing command:

~~~bash
jarsigner \
  -keystore signer.p12 \
  -storetype PKCS12 \
  -signedjar application-signed.jar \
  application-unsigned.jar \
  demo-signer
~~~

The tool prompts for the keystore/private key password when needed. Use `-signedjar` to write the output to a new file and keep the original unsigned artifact for comparison.

You can explicitly specify the digest and signature algorithms when required by your project's compatibility policy:

~~~bash
jarsigner \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -keystore signer.p12 \
  -storetype PKCS12 \
  -signedjar application-signed.jar \
  application-unsigned.jar \
  demo-signer
~~~

Choose algorithms according to current security policies and runtime environment support. Do not use weak or disabled algorithms just to make legacy commands work.

If `-signedjar` is omitted, `jarsigner` signs the input JAR in place. For build/release pipelines, creating a new artifact is usually easier to inspect and trace.

On success, the tool reports:

~~~text
jar signed.
~~~

If the signer uses a self-signed certificate, the tool will warn that the certificate is self-signed. This is normal in a lab environment, but it does not prove that recipients can independently verify the signer's identity.

## 7. Verifying a Signed JAR

Run:

~~~bash
jarsigner --verify --verbose --certs application-signed.jar
~~~

Options:

- `--verify`: verifies the JAR's signatures and digests.
- `--verbose`: lists the status of each entry.
- `--certs`: displays signer certificates.
- `-strict`: treats verification warnings as errors and returns a non-zero exit code when signer warnings/errors occur according to the tool's rules.

When an entry is validly signed, the verbose output may show `s` and `m` markers before the entry:

~~~text
sm       425 ... demo/Hello.class

  s = signature was verified
  m = entry is listed in manifest
~~~

If a signer certificate is present, the output also displays certificate details and the signature algorithm. A self-signed lab example may end with:

~~~text
jar verified.

Warning:
This jar contains entries whose certificate chain is invalid.
This jar contains entries whose signer certificate is self-signed.
This jar contains signatures that do not include a timestamp.
~~~

`jar verified.` confirms that signature/digest checks for the signed entries succeeded. The warnings above are still significant: the certificate chain is untrusted, the certificate is self-signed, and the signature has no timestamp. You should not interpret `jar verified.` as meaning the organization trusts the signer.

In a release pipeline, you can use:

~~~bash
jarsigner --verify --strict --verbose --certs application-signed.jar
~~~

CI policy should clearly define the truststore, certificate chain, timestamp, and which warnings are acceptable. Do not disable `-strict` just to hide warnings without understanding the root cause.

## 8. Distinguishing Unsigned, Modified, and Partially Signed JARs

The three scenarios produce different outputs:

| Scenario | Verification result |
|---|---|
| Unsigned JAR | Reports `jar is unsigned.` and marks entries as unsigned |
| Signed entry modified | Digest mismatch; verification fails |
| New entry added after signing | New entry may be marked with `?`; older entries remain signed |

For example, after signing, if you modify the contents of `demo/Hello.class`, JDK 24.0.2 reports an error similar to:

~~~text
jarsigner error: java.lang.SecurityException:
SHA-256 digest error for demo/Hello.class
~~~

If you only add `readme.txt` after signing, the new file is not automatically signed. `jarsigner --verify --verbose` will mark the new file with `?` and warn:

~~~text
This jar contains unsigned entries which have not been integrity-checked.
~~~

Therefore, do not update resources or classes in a JAR after the signing step. Complete building, packaging, and inspecting the artifact first; sign at the final step; then verify the exact file that will be distributed.

## 9. Self-Signed Certificates vs. Trusted Certificates

A cryptographically valid signature and a trusted certificate are two separate questions.

**Self-signed certificates**

Self-signed certificates are useful for technical testing. Recipients have no independent CA confirming the subject's identity. If both the JAR and the certificate file come from the same unauthenticated source, an attacker could replace both.

**Certificates issued by a CA or organizational PKI**

The certificate chain can be verified up to a trust anchor that the recipient's machine already trusts. The publisher must provide the proper chain, and the recipient must have an appropriate truststore.

If an organization uses an internal self-signed certificate, recipients should only import the certificate after verifying its fingerprint through an independent, authenticated channel. Do not import a certificate just because the file was sent alongside the JAR.

You can export the public certificate from the keystore:

~~~bash
keytool -exportcert \
  -alias demo-signer \
  -keystore signer.p12 \
  -storetype PKCS12 \
  -file signer.cer
~~~

View the fingerprint:

~~~bash
keytool -printcert -file signer.cer
~~~

If organizational policy requires a dedicated truststore, import the certificate after verifying the fingerprint:

~~~bash
keytool -importcert \
  -alias trusted-demo-signer \
  -file signer.cer \
  -keystore trusted-signers.p12 \
  -storetype PKCS12
~~~

A truststore holds trusted certificates; it does not need a private key to verify signatures. Do not share a keystore file containing a private key with recipients just so they can verify a JAR.

## 10. Timestamps and Certificate Validity

A JAR signature can be sent to a Timestamping Authority (TSA) to generate an authenticated timestamp. In the build environment, configure the `TSA_URL` environment variable with the actual TSA endpoint designated by your organization or certificate provider:

~~~bash
jarsigner \
  -tsa "$TSA_URL" \
  -keystore signer.p12 \
  -storetype PKCS12 \
  application-unsigned.jar \
  demo-signer
~~~

A timestamp helps prove that the signature was created at a point in time when the signer's certificate was still valid. Without a timestamp, users may be unable to verify the signature after the certificate expires, depending on verification policy and certificate status.

A timestamp does not make an untrusted certificate trusted, nor does it replace revocation or trust chain checks. Configure the TSA, certificate chain, and revocation checking policy according to release requirements.

## 11. Complete Java 17 Example: Create, Sign, and Verify a JAR

Create the source file `src/demo/Hello.java`:

~~~java
package demo;

/** A small JAR signing demonstration. */
public final class Hello {
    /** Runs the example. */
    public static void main(String[] args) {
        System.out.println("JAR signing demo");
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d build/classes src/demo/Hello.java
~~~

Package the unsigned JAR:

~~~bash
jar --create \
  --file build/hello-unsigned.jar \
  --main-class demo.Hello \
  -C build/classes .
~~~

Verify the initial state:

~~~bash
jarsigner --verify --verbose build/hello-unsigned.jar
~~~

The output should contain `jar is unsigned.`. Do not conclude it is unsigned from the exit code alone, as JDK 24.0.2 returns 0 in this case.

Create a PKCS12 keystore for the lab:

~~~bash
keytool -genkeypair \
  -alias demo-signer \
  -keyalg RSA \
  -keysize 3072 \
  -validity 30 \
  -dname "CN=JAR Signing Demo, OU=Test, O=Example, C=VN" \
  -keystore build/signer.p12 \
  -storetype PKCS12
~~~

Sign into a new file:

~~~bash
jarsigner \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -keystore build/signer.p12 \
  -storetype PKCS12 \
  -signedjar build/hello-signed.jar \
  build/hello-unsigned.jar \
  demo-signer
~~~

Verify:

~~~bash
jarsigner --verify --verbose --certs build/hello-signed.jar
~~~

List signature metadata:

~~~bash
jar --list --file build/hello-signed.jar
~~~

The listing typically includes:

~~~text
META-INF/MANIFEST.MF
META-INF/DEMO-SIG.SF
META-INF/DEMO-SIG.RSA
demo/Hello.class
~~~

The signature file name may vary depending on the alias or the `-sigfile` configuration. With a self-signed certificate, verification output will include warnings about the trust chain and timestamp; this is an intentional limitation of the lab.

Run the JAR:

~~~bash
java -jar build/hello-signed.jar
~~~

Exact stdout:

~~~text
JAR signing demo
~~~

Signing does not alter program logic. `java -jar` runs the main class as normal; the signature is metadata used to verify integrity and the signer.

## 12. Common Signing and Verification Errors

### jar is unsigned.

The JAR does not have signature metadata yet. Check the alias, keystore, and signing command; re-verify the output file you intend to distribute.

### keystore was tampered with, or password was incorrect

The keystore password is incorrect, the keystore file is corrupted, or the keystore format does not match. Check `-storetype`, the file path, and the credentials.

### Alias ... does not exist

The alias does not exist in the specified keystore. Use `keytool -list -keystore ...` to view aliases. Ensure the alias points to a `PrivateKeyEntry` when signing.

### This jar contains unsigned entries

One or more entries are not signed. Files may have been added after the signing step, or the signing process did not cover all entries. Rebuild the artifact and re-sign it.

### digest error

An entry's content changed after signing, or the digest metadata does not match. Do not edit files directly inside a signed JAR; regenerate the JAR from source/build output and re-sign it.

### Certificate chain invalid or self-signed

The signature may be cryptographically valid, but the certificate is not trusted by the truststore. Check the chain, root CA, alias, truststore, and signer fingerprint. Do not import unverified certificates.

### Expired certificate or missing timestamp

Check the certificate validity period and TSA configuration. Timestamps must come from a trusted service and be verified according to your organization's policy.

### JAR is signed but newly added files are unsigned

Any update after the signing step can introduce unsigned entries. Sign last, then re-verify the exact final artifact.

## 13. Pre-Distribution JAR Checklist

- [ ] Identify the final artifact and inspect its entry list.
- [ ] Use the correct keystore type and an alias with a `PrivateKeyEntry`.
- [ ] Keep private keys and passwords out of source code, logs, and repositories.
- [ ] Use a certificate chain appropriate for recipients and release policy.
- [ ] Sign after completing all changes to the JAR contents.
- [ ] Choose digest/signature algorithms according to security policy.
- [ ] Configure TSA and timestamping if required by the release process.
- [ ] Run `jarsigner --verify --verbose --certs`.
- [ ] Use `-strict` when CI must block on signer warnings/errors.
- [ ] Verify there are no unexpected `?` entries.
- [ ] Check the trust chain, validity period, and certificate status.
- [ ] Test-run the signed artifact and archive verification results with the build.

An unsigned JAR simply indicates that the archive does not yet have a digital signature. `jarsigner` can sign an artifact using a private key in a keystore and verify digests/signatures afterward. For secure distribution, you must check entry integrity, signer identity, trust chain, timestamp, and ensure no content was added after signing.
