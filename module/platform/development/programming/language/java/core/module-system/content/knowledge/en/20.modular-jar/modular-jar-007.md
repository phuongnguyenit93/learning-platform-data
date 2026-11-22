# jarsigner, Signatures, and the Module Path

## 1. Objectives

A modular JAR is a JAR package that contains a **module-info.class** module descriptor at its root directory. When placed on the module path, Java recognizes it as an explicit module and uses the module descriptor to determine its module name, dependencies, exported packages, used services, and provided providers.

A JAR can be digitally signed using the **jarsigner** tool. A signature allows recipients to verify the integrity of the entries in the package and identify the certificate containing the signer's public key. This topic explains signature structure, how to create a keystore, sign and verify a JAR, and the relationship between signatures and the module path.

After this lesson, you can:
- Explain what data a JAR signature protects and what problems it does not solve.
- Identify the manifest, signature file, and signature block files in META-INF.
- Use `keytool` to create or inspect a keystore and use `jarsigner` to sign and verify.
- Distinguish cryptographic signature verification from trusting the signer's certificate.
- Package, sign, inspect, and run a modular JAR on the module path.

## 2. What Is a JAR Digital Signature Used For?

A JAR is a ZIP-based archive that can contain classes, resources, configurations, and metadata. A digital signature is bound to the contents of the entries in the archive. The publisher uses a private key to sign; the recipient uses the corresponding public key to verify the signature.

JAR signing supports two primary goals:

1. **Integrity:** detects whether signed contents were altered after signing. If the bytes of a protected entry change, the digest no longer matches and verification fails.
2. **Authenticity:** the signature is bound to the public key inside the signer's certificate. When the certificate chain validates up to a trust anchor trusted by the recipient, the recipient has grounds to associate the artifact with the subject named in the certificate.

Digital signing **does not encrypt the JAR**. Recipients can still open the archive and read classes/resources. Signing also does not automatically grant package access permissions, does not replace JPMS readability/export rules, and does not turn a module into a privileged module. The module path handles module structure and relationships; signing handles content verification and signing key identity.

A modular JAR can be unsigned. A signed JAR does not necessarily have to be a modular JAR. These are two independent properties that can coexist on the same artifact.

## 3. Where Are the Signature Components Located?

When **jarsigner** signs a JAR, the tool updates the manifest and adds signature files into the **META-INF** directory. For an RSA signer, you typically see files like:

~~~text
META-INF/
  MANIFEST.MF
  RELEASE.SF
  RELEASE.RSA
~~~

The name **RELEASE** comes from the alias or from the **-sigfile** option. The extension of the signature block depends on the key/signature type; common forms are **.RSA**, **.DSA**, and **.EC**.

The three components serve different roles:

- **MANIFEST.MF:** contains metadata and the digests of each signed entry. A digest is a hash of the entry's contents, not an encrypted version of the contents.
- **.SF file (signature file):** contains digests of the manifest or corresponding sections. It describes the data that the signer intends to sign.
- **Signature block file (.RSA, .DSA, or .EC):** contains the cryptographic signature of the signature file along with the certificate or certificate chain used to verify the public key.

The verification chain can be envisioned as follows:

1. The recipient verifies the signature in the signature block against the `.SF` file using the public key in the certificate.
2. The recipient compares the digests in `.SF` against the manifest.
3. The recipient recomputes the digest of each entry and compares it against the value in the manifest.
4. The verification tool also checks the certificate against the active policy and trust store, reporting warnings if the certificate is invalid or untrusted.

Related signature files reside directly in `META-INF`. When using `jarsigner`, ordinary archive entries are included in the signing process; specialized signature files are excluded from mutually signing one another. Do not manually edit the manifest or signature files with a ZIP editor.

## 4. Keystore, Private Key, and Certificate

A **keystore** stores a private key and the certificate chain attached to that key. Each entry in a keystore has an **alias** to refer to it by name. The **keytool** utility included with the JDK is used to generate keys, generate certificates, import certificates, and view keystore contents.

When signing, `jarsigner` needs the private key. When verifying, the recipient uses the public key in the certificate accompanying the signature; a specified trust store or keystore can help verify whether the certificate belongs to a trusted set of certificates.

Example creating an RSA key pair for a practice environment:

~~~bash
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -storetype PKCS12 \
  -keystore release.p12 \
  -dname "CN=Example Release, O=Example, C=VN"
~~~

The command creates a PKCS12 keystore named **release.p12**, containing the alias **release**, a private key, and a self-signed certificate. `keytool` will prompt for a keystore password and may prompt for a key password.

A self-signed certificate is suitable for learning or testing in a controlled environment. It does not automatically become a trusted certificate on end-user machines. For production releases, organizations typically use a code-signing certificate from an appropriate CA or a managed internal trust distribution mechanism.

You can view keystore contents:

~~~bash
keytool -list -v -keystore release.p12 -storetype PKCS12
~~~

Inspect the alias, entry type, certificate validity period, subject, issuer, fingerprint, and certificate chain. Private keys must be protected; do not commit keystores containing private keys or passwords into source control, do not share release keys over insecure channels, and grant signing permissions only to authorized processes/personnel.

## 5. Signing a JAR

Suppose you have an artifact **app.jar** and a keystore **release.p12** with alias **release**. You can produce a separate signed copy:

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

`jarsigner` will prompt for passwords when needed. Key options:

- **-keystore:** path to the keystore containing the private key.
- **-storetype:** keystore type, e.g., PKCS12.
- **-signedjar:** output signed file name. If omitted, `jarsigner` overwrites the input JAR.
- **-sigfile:** optional base name for the `.SF` and signature block files.
- **-digestalg:** digest algorithm for entries.
- **-sigalg:** signature algorithm compatible with the private key.
- **-tsa:** URL of a Time Stamping Authority if attaching a timestamp.

Modern JDKs select default algorithms based on key type, key size, and security properties. Use the secure defaults of the JDK in use unless specific compatibility requirements mandate pinning algorithms. Avoid weak or disabled algorithms such as MD5 or SHA-1 for new release workflows.

After signing, you can list the archive contents:

~~~bash
jar --list --file app-signed.jar
~~~

You will see the updated manifest and the new signature files inside `META-INF`. The original classes and resources remain in the JAR. Signing does not make the contents secret.

## 6. Verifying a Signature

Basic command:

~~~bash
jarsigner -verify app-signed.jar
~~~

To view each entry and certificate details:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

The **-verbose** option displays verification progress; **-certs** adds signer certificate details. You can enforce strict checking:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

**-strict** causes severe warnings to result in a non-zero exit code. This is useful in CI/CD because the pipeline can fail if an artifact has severe warnings. Do not look only at a single **jar verified** line and conclude the certificate is trusted by your organization: read all warnings and trust check results.

If you want to match the signer against an alias in a keystore, specify the keystore and alias during verification:

~~~bash
jarsigner \
  -verify \
  -verbose \
  -certs \
  -strict \
  -keystore release.p12 \
  -storetype PKCS12 \
  app-signed.jar \
  release
~~~

When an alias is passed, `jarsigner` checks whether the certificate used to verify the entries matches the requested alias. A keystore is not required for every verification; if omitted, the tool may use a default keystore if available. A keystore used to match a signer does not automatically prove that all recipient machines trust that signer.

Distinguish between:

- **Valid signature:** the cryptographic signature matches the signed data and entry digests.
- **Valid certificate:** the certificate is within its validity period, has the proper key usage, has a validatable chain, and has no related validation errors.
- **Trusted signer:** the certificate chain terminates at a trust anchor configured as trusted in the recipient environment, or the certificate is trusted by internal policy.

A JAR can have matching digests and signatures yet still emit warnings because the certificate is self-signed, its chain cannot be validated, the certificate has expired, or the algorithm is no longer accepted. In release environments, address these warnings according to security policy rather than ignoring them.

## 7. Timestamps and Certificate Expiration

Code-signing certificates have an expiration date. If you sign without a timestamp, once the certificate expires, recipients may lack sufficient evidence to determine whether the signature was created while the certificate was still valid.

You can request a timestamp during signing using an RFC 3161-compliant TSA:

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -tsa https://tsa.example.com \
  -signedjar app-signed.jar \
  app.jar \
  release
~~~

**https://tsa.example.com** is only an illustrative address; replace it with the real TSA URL designated by your organization or trusted provider. When successful, a timestamp token is stored alongside the signature block. The TSA attests to the signing time via the timestamp service, providing evidence when evaluating the signature after the signer certificate expires.

A timestamp does not modify JAR contents and does not replace a trusted certificate chain. If the timestamp server is unreachable or the TSA certificate cannot be validated, the signing/verification process may report errors or warnings. Save the signing logs and verify the timestamp in the verification output.

## 8. Modular JARs and the Module Path

A modular JAR has a **module-info.class** file at the root directory of the archive. Example module descriptor:

~~~java
module com.example.app {
    requires com.example.codec;
    exports com.example.api;
}
~~~

Package the compiled classes, including `module-info.class`:

~~~bash
jar --create --file app.jar -C out .
~~~

Inspect the module descriptor:

~~~bash
jar --describe-module --file app.jar
~~~

If the JAR is placed on the classpath, the module descriptor does not cause it to operate as a named module; it is treated as an ordinary JAR in the unnamed module. When placing the modular JAR on the module path, the runtime recognizes it as an explicit module and reads the descriptor for module resolution.

You can sign the JAR after packaging:

~~~bash
jarsigner -keystore release.p12 -storetype PKCS12 app.jar release
~~~

Or use **-signedjar** to output a separate file as in the earlier example. After signing, **module-info.class** remains at the root, so the JAR remains a modular JAR. Signature files sit inside `META-INF` and do not replace the module descriptor.

Run the application using the module path:

~~~bash
java --module-path mods \
  --module com.example.app/com.example.Main
~~~

The **mods** directory can contain the application's modular JAR and its dependency modules. Module names and dependencies are still determined by the module descriptor; the signing alias and certificate do not participate in naming the module or determining **requires**, **exports**, **opens**, **uses**, or **provides**.

**Signing and the module path solve two different questions:**

- The module system asks: which modules are present, which modules does a module depend on, which packages are exported, and which services are used or provided?
- JAR signing asks: is the signed data still intact, which public/private key created the signature, and is the signer's certificate validated/trusted by the environment?

Therefore, **java --module-path** resolving modules does not mean you have checked signer trust. If deployment policy requires running only artifacts signed by an approved publisher, verify the JAR before placing it in the deployment directory or prior to launching.

## 9. Packaging and Release Workflow

A modular JAR release pipeline typically follows this sequence:

1. Compile the module and dependencies using the same chosen target API/JDK version.
2. Create the JAR, ensuring **module-info.class** is at the root directory.
3. Inspect the module descriptor with **jar --describe-module --file app.jar**.
4. Sign the final artifact using `jarsigner` and a securely managed release key.
5. Verify the signature with **jarsigner -verify -strict -verbose -certs**.
6. If using a timestamp, confirm the timestamp appears and the TSA's certificate chain validates.
7. Place the verified file into the artifact repository or deployment directory.
8. Test module resolution and launch using the module path in a production-like environment.

Sign after build and packaging are complete. If you modify the contents of a signed entry, its digest will no longer match. If you add an entry after signing, the new entry will lack signature protection and `jarsigner` may warn about **unsigned entries**. When changing an artifact, rebuild and re-sign a new release; do not edit a signed JAR by manually adding or removing files.

If an organization requires multiple parties to co-sign, a single JAR can contain multiple sets of `.SF` and signature block files, one set per signer. During verification, you can specify required aliases to check the signatures of expected signers. This is useful in multi-party approval workflows, though you must establish a clear policy on which signers are mandatory.

## 10. Common Warnings

| Warning or Error | Possible Meaning | What to Check |
|---|---|---|
| **jar is unsigned** or missing signature file | The JAR is not signed, or the signature is unrecognized | Check `META-INF` files and verify you are checking the right input artifact |
| **Invalid signature file digest** | The manifest digest does not match the signature file | The manifest may have been modified after signing; rebuild and re-sign |
| **digest error** or entry digest mismatch | Signed entry contents changed or the archive is corrupted | Compare artifacts; avoid updating the JAR after signing |
| **unsigned entries** | Some entries are not protected by the signer | Check for files added after signing or omitted entries |
| **signer certificate is self-signed** | Self-signed certificate with no default trusted CA chain | Use an appropriate release certificate or configure internal trust |
| **certificate chain not validated** | Cannot validate chain to a trust anchor | Check chain, trust store, and certificate validity dates |
| **certificate expired** | The signer certificate has expired | Check timestamp, signing time, and renewal process |
| **disabled algorithm** | Algorithm disabled by the JDK's security policy | Re-sign with a currently accepted algorithm/key strength |
| **not signed by alias** | Signature does not match the requested signer alias | Verify the right keystore, alias, and artifact source |
| **no timestamp** | Signature has no timestamp | Review release policy and consider using a TSA |

A warning does not always mean the JAR's bytes were tampered with. For example, a self-signed certificate can accompany a cryptographically valid signature that lacks a default trust chain. Separate digest errors, signature errors, and certificate/trust errors before making a release decision.

## 11. How to Investigate a Rejected Modular JAR

When you receive a JAR that an application cannot use, inspect it in this order:

1. **Identify the exact artifact.** Record the path, filename, version, and checksum of the received file. Make sure you are inspecting the actual deployed copy.
2. **Inspect the module descriptor.** Run **jar --describe-module --file app.jar**; confirm the module name and descriptor are correct.
3. **Inspect the signature.** Run **jarsigner -verify -verbose -certs app.jar**; look for failing entries, signers, and certificate warnings.
4. **Check strict mode.** Re-run with **-strict** in CI or a release environment so severe warnings yield a non-zero exit code.
5. **Verify the signer.** Compare the certificate fingerprint, subject, issuer, and alias against information published by the vendor via an independent channel.
6. **Check module resolution.** If the signature is valid, inspect **requires**, **exports**, **opens**, **uses**, **provides**, the module path, and dependencies. A valid signature cannot fix module resolution errors.
7. **Re-run on the target JDK.** Security properties and accepted algorithms can differ across JDK versions. Verification results on one machine do not automatically represent every environment.

Do not disable signature verification or weaken security policies just to get an old JAR running. Identify why it was rejected and request an artifact signed with an appropriate algorithm/certificate from the publisher.

## 12. Common Misconceptions to Avoid

- **Thinking signing a JAR encrypts it:** signing protects integrity and signer identity information; archive contents remain readable.
- **Thinking every JAR on the module path must be signed:** JPMS does not require all modules to be signed. Signing requirements come from release or deployment policies.
- **Thinking the signature determines the module name:** an explicit module's name resides in the module descriptor; the alias is just an entry name in the keystore.
- **Thinking the module descriptor is exempt from signing:** **module-info.class** is a JAR entry and is protected by a digest when signed along with the other entries.
- **Thinking `jar --describe-module` verifies signatures:** that command reads the module descriptor; use `jarsigner` to check signatures.
- **Thinking `jar verified` always means the signer is trustworthy:** read certificate warnings and verify trust according to the target environment.
- **Modifying a JAR after signing:** modifying a signed entry breaks its digest; adding entries can create unsigned entries. Always sign the final artifact.
- **Using a self-signed certificate like a public certificate:** self-signed certificates require intentional distribution and trust configuration; they do not automatically establish trust on other machines.

## 13. Self-Check

**1. Is a JAR with module-info.class that has not been signed still a modular JAR?**

Yes. **module-info.class** at the root directory makes it a modular JAR. Signing is a separate property, not a requirement for the module path to recognize a module.

**2. Does signing a modular JAR alter the module name or requires directives?**

No. `jarsigner` adds metadata/signatures in `META-INF` and digests in the manifest. The module descriptor still determines the module name, dependencies, and JPMS directives.

**3. Why can `jarsigner -verify` report a self-signed certificate even when digests are valid?**

Because cryptographic signature checking and certificate trust checking are two distinct parts. A self-signed certificate can verify against its own public key yet lack a chain to a trust anchor trusted by the recipient machine.

**4. Why must signing happen after the build finishes?**

Because the signature is bound to digests of entry contents. Changing a signed entry breaks digest matching; adding an entry after signing can leave the new entry unprotected.

**5. Can `jar --describe-module` and `jarsigner -verify` replace each other?**

No. The first reads the descriptor to describe the module; the second checks the signature and integrity of the JAR.

## 14. Key Takeaways

JAR signing and JPMS complement each other but solve different layers of concerns. The module descriptor defines module structure; `jarsigner` uses a private key, certificate, and digests to sign and then verify archive contents. A modular JAR remains a modular JAR after signing, as long as the module descriptor remains intact at the root directory.

In a release pipeline, build and package first, sign the final artifact, verify the signature and certificate, and only then place that exact artifact onto the module path. Always read `jarsigner` warnings and verify signer trust according to deployment policy.

## References

- [The jarsigner Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html)
- [The jar Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [JAR File Specification — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html)
- [keytool Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)