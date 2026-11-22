# Trust anchors in Java and PKIX

A trust anchor is the trust point selected by an application or system prior to verifying an X.509 digital certificate. When a server sends a certificate to a client during TLS, the client needs to determine which CA signed that certificate, whether intermediate certificates form a valid chain, and whether the path terminates at a CA that the client accepts.

In Java, a trust anchor is represented directly by the `java.security.cert.TrustAnchor` class. This class is used together with `PKIXParameters` and `CertPathValidator` to validate a certification path. For TLS, trust material is typically stored in a `KeyStore` and loaded into a `TrustManagerFactory` to create trust managers for an `SSLContext`.

## 1. What is a trust anchor?

A trust anchor, also known as a *most-trusted CA*, is a CA that the verifying party decides to trust as the starting point for validating a certification path. The core information of an anchor includes:

- The CA's name (distinguished name).
- The CA's public key.
- Constraints applied to paths validated using that public key, if any.

In the common PKI model, a trust anchor is usually represented by a root CA certificate. However, in PKIX terms, a trust anchor is an input to the validation algorithm; it can be provided either as a trusted X.509 certificate or as a pair of CA name and public key.

An important point to understand: a self-signed certificate does not automatically become trusted. Anyone can generate a certificate with a Subject DN matching the name of a well-known CA. Trust in a CA's public key must come from a trusted channel and a local policy decision, such as the set of root CAs managed by the OS/JDK or a certificate whose fingerprint has been verified by an administrator and installed into a truststore.

### 1.1. Roles in the certificate hierarchy

A typical certificate chain has three roles:

| Component | Role |
|---|---|
| Root CA | The highest-level CA in the hierarchy; typically self-signed and distributed as a trust anchor |
| Intermediate CA | A CA signed by a higher-level CA; used to issue certificates for other CAs or end entities |
| Leaf / end-entity certificate | The certificate of the server, client, user, or application to be verified |

Example path:

~~~text
Trust anchor: Example Root CA
        |
        | signs
        v
Intermediate CA
        |
        | signs
        v
Leaf certificate: api.example.test
~~~

The client does not trust the leaf certificate simply because the server sends it. The client verifies the leaf's signature using the intermediate's public key, then checks the intermediate against the CA above it, and finally verifies that the path terminates at a trust anchor accepted by the client.

A trust anchor does not have to be a globally public root CA. An organization can choose an internal CA or an intermediate CA as the anchor for a specific application or usage domain. Choosing an anchor is a policy decision; two different applications can use two different sets of trust anchors.

### 1.2. Trust anchor vs. certificate chain vs. truststore

Three concepts that are often confused:

| Concept | Meaning |
|---|---|
| Trust anchor | The trust point passed into the PKIX algorithm |
| Certification path / certificate chain | The certificates linking from the target certificate toward the issuing CA |
| Truststore | The repository of certificates used by an application as its source of trust material; typically a KeyStore file |

A truststore is where data is stored. A trust anchor is the role of a CA in the verification decision. When Java creates `PKIXParameters` from a `KeyStore`, the trusted certificate entries in the store are used as the set of most-trusted CAs for the PKIX process.

A truststore does not need to contain the CA's private key. To verify certificate signatures, the application only needs the public key and confirmed trust information. The root CA's private key must be protected separately, typically offline or in an HSM.

## 2. How does a trust anchor participate in PKIX validation?

PKIX (Public Key Infrastructure using X.509) verifies that the target certificate is validly bound to the public key of a CA trusted by the verifying party.

General process:

1. The application receives the target certificate and the necessary intermediate certificates.
2. Identify one or more trust anchors that match the policy.
3. Build a certification path from the target certificate toward the issuing CA.
4. Check signatures, issuer/subject relationships, validity periods, constraints, key usage, and related PKIX rules.
5. Check revocation status if revocation checking is enabled and configured.
6. Return a valid result or throw an exception if the path does not meet the conditions.

Common checks during validation:

- The signature on each certificate must verify with the public key of its corresponding issuer.
- The Issuer of a child certificate must match the Subject of the parent certificate.
- Certificates in the path must be valid at the verification time.
- CA certificates must have appropriate Basic Constraints and Key Usage for the certificate-signing role.
- Certificate policies, path length, and name constraints are enforced according to configuration and provider support.
- No certificate may appear more than once in a single path.
- Revocation status is checked via CRL or OCSP if enabled.

### 2.1. The trust anchor is not included in CertPath

For X.509, the list of certificates in a `CertPath` is typically ordered from the target certificate up to the certificate issued by the trusted CA. The certificate representing the trust anchor is not included in the path list; it is passed separately via `PKIXParameters`.

For example, if a root CA directly signs a leaf certificate:

~~~text
TrustAnchor: Root CA
CertPath:
  1. Leaf certificate
~~~

If there is an intermediate:

~~~text
TrustAnchor: Root CA
CertPath:
  1. Leaf certificate
  2. Intermediate CA certificate
~~~

Do not append the root anchor certificate to the end of `CertPath` just because it appears in a chain file sent by the server. The root anchor is provided separately in the set of trust anchors.

### 2.2. CertPathBuilder and CertPathValidator

Two APIs with different responsibilities:

| API | Responsibility |
|---|---|
| `CertPathBuilder` | Finds or builds a certification path from a target certificate, trust anchors, and certificate sources |
| `CertPathValidator` | Validates an existing `CertPath` against a set of PKIX parameters |

If the application already has the list of certificates in the correct order, it can create a `CertPath` using `CertificateFactory` and then use `CertPathValidator`.

If the application only knows the target certificate and needs to discover intermediate certificates from multiple sources, use `CertPathBuilder` together with `PKIXBuilderParameters` and `CertStore`.

## 3. Key Java classes

### 3.1. java.security.cert.TrustAnchor

`TrustAnchor` represents the most-trusted CA in a path. There are three main constructors:

~~~java
new TrustAnchor(X509Certificate trustedCert, byte[] nameConstraints);

new TrustAnchor(
        X500Principal caPrincipal,
        PublicKey pubKey,
        byte[] nameConstraints);

new TrustAnchor(
        String caName,
        PublicKey pubKey,
        byte[] nameConstraints);
~~~

The most common way is to pass a verified CA certificate:

~~~java
TrustAnchor anchor = new TrustAnchor(rootCertificate, null);
~~~

The `nameConstraints` parameter is the ASN.1 DER encoding of an additional NameConstraints extension. Support for this parameter depends on the provider; Oracle JDK 21 documentation notes that the SUN provider's PKIX implementation does not support the `TrustAnchor` name constraints parameter and may throw `InvalidAlgorithmParameterException` if provided. Therefore, do not assume every provider handles it the same way.

### 3.2. PKIXParameters

`PKIXParameters` holds the set of trust anchors and parameters used in the PKIX validation algorithm.

It can be initialized from a `Set<TrustAnchor>`:

~~~java
Set<TrustAnchor> anchors = Set.of(anchor);
PKIXParameters parameters = new PKIXParameters(anchors);
~~~

Or from a `KeyStore` containing trusted certificate entries:

~~~java
PKIXParameters parameters = new PKIXParameters(trustStore);
~~~

Important properties:

| Method | Purpose |
|---|---|
| `getTrustAnchors()` / `setTrustAnchors(...)` | Reads or updates the set of trust anchors |
| `setDate(...)` | Specifies the time used to check validity |
| `setRevocationEnabled(...)` | Enables or disables revocation checking |
| `setInitialPolicies(...)` | Sets the acceptable certificate policy OIDs |
| `setCertStores(...)` | Provides certificate/CRL sources for the provider |
| `setTargetCertConstraints(...)` | Constrains the target certificate |

Revocation checking is enabled by default in `PKIXParameters`. If disabled, the application will not detect revoked certificates through that checking mechanism. Only disable it in fixtures or scenarios with a specific evaluated policy; production environments need proper CRL/OCSP configuration.

### 3.3. CertPathValidator

`CertPathValidator` performs the validation:

~~~java
CertPathValidator validator =
        CertPathValidator.getInstance("PKIX");

CertPathValidatorResult result =
        validator.validate(certPath, parameters);
~~~

Every Java platform implementation must support the `PKIX` algorithm. If the path is invalid, `validate` throws `CertPathValidatorException`. The exception provides details about the error and the index of the offending certificate if the provider can determine it.

### 3.4. TrustManagerFactory and SSLContext

In TLS, you usually do not call `CertPathValidator` manually for each socket. JSSE creates trust managers to verify peer certificates:

~~~java
TrustManagerFactory tmf =
        TrustManagerFactory.getInstance("PKIX");

tmf.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), null);
~~~

`TrustManagerFactory` takes trust material from a `KeyStore` and produces one or more `TrustManager` instances. `SSLContext` uses those trust managers when performing the TLS handshake.

When using `TrustManagerFactory.init(KeyStore)` in SunJSSE, default PKIX parameters are used, but revocation checking is disabled. If revocation checking is required, an appropriate mechanism must be configured, such as using `CertPathTrustManagerParameters` with `PKIXBuilderParameters` that have revocation enabled and CRL/OCSP sources configured.

## 4. Truststore, keystore, and cacerts

### 4.1. Keystore and truststore are roles, not file formats

Both a keystore and a truststore can be a `KeyStore` with entries such as:

| Entry type | Contents | Purpose |
|---|---|---|
| `PrivateKeyEntry` | Private key and corresponding certificate chain | Proves the identity of the application/server itself |
| `TrustedCertificateEntry` | A certificate trusted by the application | Provides a trust anchor or trust material to verify peers |
| `SecretKeyEntry` | Symmetric secret key | Encrypts/decrypts data |

A keystore typically holds the application's own private key and certificate. A truststore typically holds trusted certificate entries of CAs that the application accepts. The same file can hold multiple entry types, but separating the two roles is generally easier to manage and reduces risk.

### 4.2. The JDK's cacerts

The JDK provides a truststore named `cacerts` in:

~~~text
JAVA_HOME/lib/security/cacerts
~~~

This store contains a default set of root CAs. You can list them with:

~~~bash
keytool -list -cacerts
~~~

Do not assume every certificate in `cacerts` is appropriate for every application. Administrators should review and maintain the set of CAs that the organization actually trusts.

### 4.3. How JSSE selects the default truststore

In Oracle JDK's SunJSSE implementation, when creating a default trust manager without passing a KeyStore, the search order for trust material is:

1. If the `javax.net.ssl.trustStore` system property is set, use the specified file.
2. If the property is not set, look for `JAVA_HOME/lib/security/jssecacerts`.
3. If `jssecacerts` does not exist, look for `JAVA_HOME/lib/security/cacerts`.
4. If no store is found, there is no default truststore.

A common pitfall: if `javax.net.ssl.trustStore` is set but points to a nonexistent file, SunJSSE creates a trust manager with an empty keystore. The application may fail with `PKIX path building failed` even though the JDK still has `cacerts`.

Commonly used system properties:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/opt/app/conf/truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  -jar app.jar
~~~

The example above only illustrates how to configure the properties. Do not put real passwords on the command line or in CI logs; use a secret manager, protected file, console prompt, or credential mechanism appropriate for your deployment environment.

A custom truststore usually replaces the default trust source for that SSLContext. If an application needs to trust both public CAs and internal CAs simultaneously, you must proactively build a truststore containing both sets or implement a tested mechanism that combines trust managers.

## 5. Adding a trust anchor with keytool

`keytool` manages key pairs, certificates, and keystores. When adding a root CA to a truststore, only import the certificate containing the public key; never import the CA's private key.

### 5.1. Inspecting the certificate before trusting it

Suppose you receive `company-root.cer` from the security team or CA:

~~~bash
keytool -printcert -file company-root.cer -v
~~~

Check the Subject, Issuer, validity period, and SHA-256 fingerprint. Compare the fingerprint against a value obtained through an independent, trusted channel (such as an official CA portal or an authenticated administrator).

Being self-signed and having a Subject name matching the expected CA is not enough to verify the authenticity of the public key.

### 5.2. Importing into a dedicated truststore

~~~bash
keytool -importcert \
  -alias company-root \
  -file company-root.cer \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

When keytool displays the certificate and asks whether to trust it, confirm only after verifying the fingerprint. Do not use `-noprompt` to bypass confirmation unless there is a reliable automated fingerprint verification process.

Verify the entry after importing:

~~~bash
keytool -list -v \
  -alias company-root \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

The root CA entry should be a `trustedCertEntry`. The truststore does not need to contain the root CA's private key.

### 5.3. Importing into cacerts

If the organization decides an internal CA must be trusted broadly across the JDK, an administrator can add the certificate to `cacerts`:

~~~bash
keytool -importcert \
  -alias company-root \
  -file company-root.cer \
  -cacerts
~~~

This change affects many applications using that JDK. It is usually better to prefer a dedicated truststore per application or application group to limit the scope of trust. Only modify `cacerts` when operational policy requires it and a change-management process is in place.

## 6. Hands-on: creating a CA, signing a leaf certificate, and validating the path

This exercise creates a root CA for lab use only, signs a leaf certificate with a DNS SAN, and validates the leaf using Java PKIX. Do not use a lab CA or demo private key to issue real certificates.

### 6.1. Creating the root CA

Create a PKCS12 keystore containing the CA's private key and a self-signed certificate with certificate-signing capability:

~~~bash
keytool -genkeypair \
  -alias root \
  -dname "CN=Example Test Root CA,O=Example,C=US" \
  -ext bc=ca:true \
  -ext ku=keyCertSign,cRLSign \
  -keyalg RSA \
  -keysize 2048 \
  -sigalg SHA256withRSA \
  -validity 3650 \
  -keystore root.p12 \
  -storetype PKCS12
~~~

Keytool will prompt for a password. In practice, protect the root CA's private key strictly and do not place the root CA keystore on application servers.

Export the public certificate:

~~~bash
keytool -exportcert \
  -alias root \
  -keystore root.p12 \
  -storetype PKCS12 \
  -file root.cer
~~~

Inspect the certificate and fingerprint:

~~~bash
keytool -printcert -file root.cer -v
~~~

### 6.2. Generating a key pair and CSR for the server

Create a keystore containing the server's private key:

~~~bash
keytool -genkeypair \
  -alias service \
  -dname "CN=service.example.test" \
  -keyalg RSA \
  -keysize 2048 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -keystore service.p12 \
  -storetype PKCS12
~~~

Generate a Certificate Signing Request:

~~~bash
keytool -certreq \
  -alias service \
  -keystore service.p12 \
  -storetype PKCS12 \
  -file service.csr
~~~

### 6.3. Signing the server certificate with the root CA

~~~bash
keytool -gencert \
  -alias root \
  -keystore root.p12 \
  -storetype PKCS12 \
  -infile service.csr \
  -outfile service-signed.pem \
  -rfc \
  -validity 90 \
  -ext bc=ca:false \
  -ext ku=digitalSignature,keyEncipherment \
  -ext eku=serverAuth \
  -ext san=dns:service.example.test
~~~

The issued leaf certificate has a DNS SAN, `serverAuth` EKU, and no CA signing capability.

Import the root certificate into the server's keystore so keytool can build the chain when receiving the certificate reply:

~~~bash
keytool -importcert \
  -alias example-root \
  -file root.cer \
  -keystore service.p12 \
  -storetype PKCS12
~~~

Then import the CA-signed certificate into the same alias that holds the private key:

~~~bash
keytool -importcert \
  -alias service \
  -file service-signed.pem \
  -keystore service.p12 \
  -storetype PKCS12
~~~

Keytool pairs the certificate reply with the existing private key and updates the chain of the `service` entry. Verify the chain:

~~~bash
keytool -list -v \
  -alias service \
  -keystore service.p12 \
  -storetype PKCS12
~~~

### 6.4. Creating a truststore containing only the root CA

Create a separate truststore for the client:

~~~bash
keytool -importcert \
  -alias example-root \
  -file root.cer \
  -keystore truststore.p12 \
  -storetype PKCS12
~~~

Verify the fingerprint before accepting the import. Check it again:

~~~bash
keytool -list -v \
  -keystore truststore.p12 \
  -storetype PKCS12
~~~

The truststore contains only the CA's public certificate. The root private key remains in the CA keystore and is never distributed to clients.

Export the leaf certificate for the Java example:

~~~bash
keytool -exportcert \
  -alias service \
  -keystore service.p12 \
  -storetype PKCS12 \
  -file service.cer
~~~

## 7. Java 17+ program validating with TrustAnchor

Create `TrustAnchorDemo.java`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class TrustAnchorDemo {
    public static void main(String[] args) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        X509Certificate root;
        try (var input = Files.newInputStream(Path.of(args[0]))) {
            root = (X509Certificate) factory.generateCertificate(input);
        }

        X509Certificate leaf;
        try (var input = Files.newInputStream(Path.of(args[1]))) {
            leaf = (X509Certificate) factory.generateCertificate(input);
        }

        // X.509 CertPath starts with the target; the trust anchor is separate.
        CertPath path = factory.generateCertPath(List.of(leaf));
        TrustAnchor anchor = new TrustAnchor(root, null);

        PKIXParameters parameters =
                new PKIXParameters(Set.of(anchor));

        // This isolated demo has no CRL/OCSP source.
        // Production validation should configure revocation checking.
        parameters.setRevocationEnabled(false);

        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");

        PKIXCertPathValidatorResult result =
                (PKIXCertPathValidatorResult)
                        validator.validate(path, parameters);

        System.out.println("Trust anchor: "
                + root.getSubjectX500Principal().getName());
        System.out.println("Validated target: "
                + leaf.getSubjectX500Principal().getName());
        System.out.println("Public key algorithm: "
                + result.getPublicKey().getAlgorithm());
        System.out.println("Certificate path length: "
                + path.getCertificates().size());
    }
}
~~~

Compile and run in the directory containing `TrustAnchorDemo.java`, `root.cer`, and `service.cer`:

~~~bash
javac --release 17 TrustAnchorDemo.java
java TrustAnchorDemo root.cer service.cer
~~~

Exact stdout for the fixture created in the previous section:

~~~text
Trust anchor: CN=Example Test Root CA,O=Example,C=US
Validated target: CN=service.example.test
Public key algorithm: RSA
Certificate path length: 1
~~~

This example demonstrates that the leaf certificate is validated against a root CA passed separately as a `TrustAnchor`. The path contains only the leaf certificate; the root CA is not in `CertPath`.

In a chain with intermediate CAs, put the leaf first, followed by intermediate certificates in issuer order. The root anchor is still passed separately. If the path is not already constructed, use `CertPathBuilder` rather than assuming an arbitrary list of certificates forms a valid path.

### 7.1. Using a KeyStore as the trust anchor source

Instead of creating `TrustAnchor` directly, you can load a truststore containing trusted certificate entries:

~~~java
KeyStore anchors = KeyStore.getInstance("PKCS12");
try (var input = Files.newInputStream(Path.of("truststore.p12"))) {
    anchors.load(input, password);
}

PKIXParameters parameters = new PKIXParameters(anchors);
~~~

The trusted certificate entries in the `KeyStore` are used as the most-trusted CAs. In real applications, obtain the password from a console or secret provider and close/release resources properly.

## 8. Using a truststore in JSSE/TLS

A TLS client typically uses a truststore to create trust managers:

~~~java
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (var input = Files.newInputStream(Path.of("truststore.p12"))) {
    trustStore.load(input, password);
}

TrustManagerFactory tmf =
        TrustManagerFactory.getInstance("PKIX");
tmf.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), null);
~~~

`TrustManagerFactory` uses the trusted certificate entries in the store to create trust managers. When the client performs a TLS handshake, the trust manager evaluates the certificate chain sent by the peer against the trust material and PKIX policy.

You can use `SSLContext` to create a socket factory or HTTP client. Ensure the application uses the context initialized with the intended trust manager.

### 8.1. Path validation does not replace hostname verification

Certificate path validation answers the question: was the certificate issued through a CA chain ending at an anchor that the application trusts?

Hostname verification answers a different question: does the target certificate authenticate the exact hostname that the application intends to connect to?

A certificate with a valid chain can still belong to a different hostname. HTTPS requires endpoint identification; `HttpsURLConnection` performs hostname verification by default. For raw `SSLSocket` or `SSLEngine`, the application must enable endpoint identification or verify peer identity itself.

Example with `SSLSocket`:

~~~java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
~~~

Do not skip hostname verification and do not use a trust-all `X509TrustManager` in production. Doing so makes every certificate acceptable and defeats the purpose of trust anchors.

## 9. Revocation, validity, and trust policies

### 9.1. Expired or revoked certificates

A valid trust anchor does not make every certificate signed by that CA permanently acceptable. The target and intermediate certificates must still satisfy path validation conditions such as validity, signatures, and constraints.

A certificate can be revoked before its expiration date. PKIX supports status checking using CRL or OCSP, provided the corresponding mechanism and data sources are configured.

- A CRL is a list of revoked certificates issued by a CA.
- OCSP allows querying certificate status via a responder.
- OCSP stapling allows the server to attach the status response during TLS.

In Java, you can enable revocation on `PKIXParameters` or use `PKIXRevocationChecker` for detailed configuration. With SunJSSE, `TrustManagerFactory.init(KeyStore)` disables revocation checking by default; to enable it, configure it according to the JSSE guide for your target JDK.

### 9.2. A trust anchor can be constrained

Trusting a root CA should not be interpreted as accepting every certificate that CA could ever issue across all applications. Policy can restrict:

- Accepted certificate policy OIDs.
- Permitted DNS names or namespaces.
- Intended purposes via Key Usage and Extended Key Usage.
- Permitted signature algorithms and key sizes.
- Validity periods and revocation status.
- Which intermediate CAs are permitted to appear in the path.

PKIX provides policy and constraint parameters; an application can use a dedicated set of trust anchors to limit the scope of trust for that service.

### 9.3. Trust anchor rotation

When a CA is nearing expiration or being replaced, plan the transition:

1. Verify the new root CA through an independent channel.
2. Distribute the new root to client truststores before servers switch certificates.
3. During the transition period, keep both the old and new anchors if policy permits.
4. Rotate leaf/intermediate certificates and test paths across all runtime targets.
5. Monitor updated clients; remove the old anchor only when no valid path depends on it.
6. Record fingerprints, addition/removal timestamps, and change approvers.

Do not replace a global truststore on production machines with an unverified file. Do not remove the old root before clients have received the new root.

## 10. Common errors and troubleshooting

| Symptom | Common cause | How to check |
|---|---|---|
| `PKIX path building failed` | No path found to a trust anchor | Check truststore, root/intermediate, and certificates sent by the server |
| `unable to find valid certification path` | Root CA is not trusted or intermediate is missing | Inspect the chain with `keytool -list -v` and verify the anchor set |
| `No subject alternative DNS name matching...` | Hostname does not match SAN | Check DNS/IP SANs and the hostname the client is connecting to |
| Certificate reported as expired or not yet valid | Incorrect system clock or expired certificate | Check system time, `Not Before`, and `Not After` |
| Imported certificate but still not trusted | Imported into server keystore instead of client truststore | Verify `javax.net.ssl.trustStore` or the KeyStore passed to TrustManagerFactory |
| Root certificate rejected during import | Unverified fingerprint or chain cannot be built | Verify fingerprint via an independent channel and check CA chain |
| `trustStore` property set but CA still not found | Wrong file path or nonexistent file | Verify exact path, type, and read permissions; SunJSSE may use an empty store |
| Client does not detect revoked certificate | Revocation checking disabled or no CRL/OCSP source | Check PKIX parameters and responder/distribution point configuration |
| Certificate chain is valid but TLS still fails | Protocol, cipher, EKU, hostname, or policy error | Check the root exception and enable JSSE debug in a test environment |
| One app trusts the CA while another does not | Each app uses a different truststore or SSLContext | Check system properties and TrustManagerFactory of each app |

## 11. Trust anchor management checklist

- [ ] Select only CAs verified and approved by the organization.
- [ ] Verify the SHA-256 fingerprint via an independent channel before importing.
- [ ] Use an application-specific truststore when you need to limit the scope of trust.
- [ ] Never distribute the root CA's private key to client applications.
- [ ] Check Subject, Issuer, Basic Constraints, Key Usage, SAN, and certificate validity.
- [ ] Ensure required intermediate certificates are available to build the path.
- [ ] Separate path validation, revocation checking, and hostname verification into explicit controls.
- [ ] Never use a trust-all trust manager or disable hostname verification.
- [ ] Record the fingerprint, alias, issuing source, and truststore change history.
- [ ] Plan rotation before a CA or certificate expires.
- [ ] Retest on the exact JDK/provider and production runtime configuration.

## 12. Summary

A trust anchor is the CA chosen as the trust point for certification path validation. Java represents it with `TrustAnchor`; `PKIXParameters` carries the anchor set and validation policy; `CertPathValidator` validates the path. In TLS, trust material is typically stored in a truststore and loaded via `TrustManagerFactory` into `SSLContext`.

Trust does not come from a certificate being self-signed or having a name matching a desired CA. It comes from a verified and securely managed trust decision. Always verify fingerprints before importing, protect CA private keys, manage revocation, and perform hostname verification separately when establishing TLS connections.

References:

- [RFC 5280 — Internet X.509 Public Key Infrastructure: Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html)
- [TrustAnchor API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/TrustAnchor.html)
- [CertPathValidator API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [Java PKI Programmer's Guide — Java SE 21](https://docs.oracle.com/en/java/javase/21/security/java-pki-programmers-guide.html)
- [JSSE Reference Guide — Java SE 21](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
- [The keytool Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)