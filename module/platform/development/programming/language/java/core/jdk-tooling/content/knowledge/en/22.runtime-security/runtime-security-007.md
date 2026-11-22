# Certificate Validation in Java

**Certificate validation** is the process of verifying whether an X.509 certificate can be accepted for a specific purpose. For TLS, an application must verify the peer's certificate, the signature path to a trusted trust anchor, the validity period, the hostname, the intended usage, and the relevant security policies.

A certificate that can be read with `keytool` is not necessarily trustworthy. Inspecting a few fields such as Subject, Issuer, or Not After is only an informational step. Full validation must also verify the signature of each certificate in the chain, CA constraints, hostname/SAN, Key Usage, Extended Key Usage, and revocation status according to policy.

A command to inspect certificate details:

~~~bash
keytool -printcert -v -file server.pem
~~~

A Java program can validate a certificate path using PKIX:

~~~java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
validator.validate(certPath, pkixParameters);
~~~

For HTTPS connections, the Java TLS stack also needs to check the hostname. A successful PKIX path validation must not be treated as sufficient to conclude that the certificate matches the hostname the client is accessing.

## 1. What Problem Does Certificate Validation Solve?

An X.509 certificate binds a public key to an identity. In TLS, the server sends its certificate so the client can verify the server's identity and establish a secure channel.

Validation must answer these questions:

- Was the certificate signed by a valid issuer?
- Can a path be built from the leaf certificate to a trust anchor that the application trusts?
- Is the signature on each certificate valid?
- Is the certificate currently valid and not yet expired?
- Does the certificate match the hostname or IP address that the client is accessing?
- Is the certificate permitted for TLS server or TLS client use?
- Has the certificate been revoked, if policy requires revocation checking?
- Do the algorithms, key sizes, and extensions meet the security policy?

For example, a server might send a certificate with Subject `CN=localhost` and a valid signature. However, if the client accesses `api.example.com`, a certificate that only has a `localhost` DNS SAN must still be rejected. A valid signature cannot fix a hostname mismatch.

Certificate validation is part of runtime security because it determines which peers are allowed to participate in a TLS connection and which identities the application accepts.

## 2. Components of an X.509 Certificate

A certificate typically contains the following important fields:

| Component | Meaning |
|---|---|
| Subject | Identity of the entity that owns the public key |
| Issuer | CA or entity that signed the certificate |
| Serial Number | Certificate identifier within the issuer's scope |
| Not Before | Timestamp when the certificate becomes valid |
| Not After | Timestamp when the certificate expires |
| Subject Public Key Info | Public key and algorithm |
| Signature Algorithm | Algorithm used to sign the certificate |
| Extensions | SAN, Key Usage, EKU, Basic Constraints, Name Constraints, etc. |

A certificate does not contain the private key. The private key must be protected separately in a keystore, HSM, or key management device.

Extensions determine the context in which a certificate may be used. A CA certificate must have appropriate Basic Constraints; a TLS server certificate typically has a SAN containing the hostname and an EKU of `serverAuth` if EKU is specified.

## 3. Certificate Chain and Trust Anchor

A certificate chain links an endpoint's certificate to a trusted CA.

A chain typically looks like this:

~~~text
TLS server certificate (leaf)
          |
          v
Intermediate CA certificate
          |
          v
Root CA certificate (trust anchor)
~~~

- **Leaf certificate:** the server or client certificate being verified.
- **Intermediate CA:** an intermediate CA that signs the leaf or a subordinate CA.
- **Root CA:** the trust anchor configured as trusted in the application or environment.

A `CertPath` usually includes the leaf and intermediate certificates ordered toward the nearest issuer. The trust anchor is passed separately to `PKIXParameters` and is typically not included in the `CertPath` to be validated.

A trust anchor does not become trustworthy simply because the certificate is self-signed. It is trusted because the organization or operator has installed and accepted that public key/certificate through a trusted process.

Self-signed certificates can be used in labs or private PKIs. To be accepted, the client must configure the corresponding trust anchor. Never import a certificate of unknown origin just to suppress a TLS error.

## 4. PKIX Path Building and Path Validation

Java supports PKIX (Public Key Infrastructure using X.509) to build and validate certificate paths.

Two related but distinct operations are:

- **Path building:** finding a certificate chain from the leaf to a trust anchor based on available certificates.
- **Path validation:** checking whether a selected chain complies with PKIX rules.

Java provides:

- `CertPathBuilder` to build a path.
- `CertPathValidator` to validate an existing path.
- `PKIXBuilderParameters` and `PKIXParameters` to configure trust anchors and policies.
- `CertificateFactory` to read certificates or create a `CertPath`.

In a simple example, when you already have the leaf and root, you can create a `CertPath` directly and call `CertPathValidator`. In real systems, a chain may contain intermediate certificates or must be constructed from multiple sources; in that case, use `CertPathBuilder` or provide a `CertStore` containing the intermediate certificates.

During validation, PKIX checks factors such as signatures, validity periods, CA constraints, path length, name constraints, certificate policies, and algorithm constraints according to the configuration and provider.

## 5. Trust Anchors and Truststores

A trust anchor is the endpoint accepted by the application as the root of trust. It is usually a root CA certificate, though it can also be a certificate trusted directly by policy.

Java uses `KeyStore` to store trusted certificates. A truststore can be PKCS12 or JKS.

List the default `cacerts`:

~~~bash
keytool -list -cacerts
~~~

View details:

~~~bash
keytool -list -cacerts -v
~~~

List a custom truststore:

~~~bash
keytool -list -v -keystore truststore.p12 -storetype PKCS12
~~~

Import a root CA certificate into a custom truststore:

~~~bash
keytool -importcert \
    -alias example-root \
    -file root-ca.pem \
    -keystore truststore.p12 \
    -storetype PKCS12
~~~

Before confirming the import, verify the Subject, Issuer, and SHA-256 fingerprint through an independent, trusted channel.

### JSSE Default Truststore

If no custom truststore is specified, JSSE uses the JDK's default truststore lookup mechanism. Typically, if the `javax.net.ssl.trustStore` system property is set, that file is used; otherwise, JSSE looks for `jssecacerts` and then `cacerts` in the `security` directory of Java home.

You can configure the truststore when running the application:

~~~bash
java \
    -Djavax.net.ssl.trustStore=truststore.p12 \
    -Djavax.net.ssl.trustStoreType=PKCS12 \
    com.example.Client
~~~

If a password is required, use secret injection appropriate for the runtime environment; avoid putting real passwords directly on the command line, in source code, or in logs.

Selecting the wrong truststore can cause the application to fail to trust a required CA or to trust too many CAs. Verify the exact truststore that the runtime is actually using.

## 6. Checking the Validity Period

A certificate has two timestamps:

- `Not Before`: the time when it becomes valid.
- `Not After`: the time when it expires.

In Java:

~~~java
certificate.checkValidity();
~~~

This call throws `CertificateNotYetValidException` if the current time is before `Not Before` and `CertificateExpiredException` if it is past `Not After`.

You can also check validity at a specific point in time:

~~~java
certificate.checkValidity(new Date());
~~~

A validity check does not verify the issuer signature, hostname, trust anchor, or revocation. It only checks the validity time window.

Common time-related errors:

- System clock skew.
- A certificate created with `Not Before` in the future.
- An expired certificate.
- A certificate chain with an expired intermediate CA even though the leaf is still valid.
- Incorrect timezone or time synchronization on the system.

For production, ensure system clocks are synchronized and have a certificate renewal process in place before expiration.

## 7. Verifying Signatures and the Certificate Path

A certificate can be parsed successfully without having a valid signature. Parsing only proves that the data conforms to an X.509 structure understood by `CertificateFactory`.

PKIX validation requires:

1. The leaf certificate.
2. Intermediate certificates, if any.
3. Accepted trust anchors.
4. A properly ordered `CertPath`.
5. `PKIXParameters` and corresponding policies.

Conceptual example:

~~~java
CertificateFactory factory = CertificateFactory.getInstance("X.509");
CertPath path = factory.generateCertPath(certificates);

PKIXParameters parameters = new PKIXParameters(trustAnchors);
CertPathValidator validator = CertPathValidator.getInstance("PKIX");

validator.validate(path, parameters);
~~~

If the chain does not terminate at a trust anchor, a signature is invalid, a CA certificate lacks appropriate Basic Constraints, or a path policy is violated, the validator throws `CertPathValidatorException`.

Do not verify a certificate yourself by simply comparing the Issuer to the Subject of the next certificate. Matching names do not prove a valid signature.

## 8. Subject Alternative Name and Hostname Validation

Hostname validation is a separate step from PKIX path validation.

For HTTPS, the client must verify that the URL hostname matches a Subject Alternative Name (SAN) in the leaf certificate. A SAN can contain:

- DNS name.
- IP address.
- Email address.
- URI and other `GeneralName` types.

Example SAN:

~~~text
DNS:api.example.com
DNS:api.internal.example.com
IP:192.0.2.10
~~~

If the client accesses `https://api.example.com`, the SAN must contain a matching DNS name. If the client accesses by IP, the certificate needs a matching IP SAN. Do not rely solely on the Common Name (CN), as modern clients use SAN for hostname verification.

### Wildcard DNS Names

A wildcard certificate such as `*.example.com` typically matches only a single label at the wildcard position, such as `api.example.com`; it does not implicitly match `a.b.example.com`. Detailed rules depend on the hostname verifier and TLS client.

Do not write a simple custom wildcard matcher for production. Use the hostname verification built into JSSE or a trusted HTTP client.

### HttpsURLConnection

`HttpsURLConnection` performs hostname verification by default. If you replace only the `SSLSocketFactory` to use a custom truststore, do not disable the default `HostnameVerifier`.

### SSLSocket and Endpoint Identification

For a raw `SSLSocket`, you must configure endpoint identification:

~~~java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
~~~

If you skip this step, the application may validate the certificate path without verifying that the certificate belongs to the hostname being connected to.

## 9. Key Usage, Extended Key Usage, and Basic Constraints

A certificate may have a valid signature and validity period yet still be unsuitable for the intended use.

### Key Usage

Key Usage restricts how the public key may be used, for example:

- `digitalSignature`.
- `keyEncipherment`.
- `keyAgreement`.
- `keyCertSign`.
- `cRLSign`.

A CA certificate typically requires `keyCertSign` if used to sign other certificates. A TLS server certificate may require `digitalSignature` or a key usage appropriate for the cipher suite and key exchange in use.

### Extended Key Usage (EKU)

EKU specifies extended purposes, for example:

| OID / Name | Purpose |
|---|---|
| `serverAuth` | TLS server authentication |
| `clientAuth` | TLS client authentication |
| `codeSigning` | Code signing |
| `emailProtection` | Email protection |
| `timeStamping` | Timestamp authority |

If EKU is present, the certificate must permit the corresponding usage. If EKU is absent, its interpretation depends on PKI rules and applicable policy; do not assume that the certificate is prohibited from all uses.

### Basic Constraints

Basic Constraints determines whether a certificate is a CA and can set a path length constraint. An intermediate CA must not exceed the declared path length limit.

The PKIX validator checks the CA constraints of certificates in the path. Trust anchors must be managed and accepted according to their own policy.

## 10. Name Constraints and Certificate Policies

Some CAs restrict the namespaces or certificate types that subordinate CAs are permitted to issue.

**Name Constraints** can restrict DNS suffixes, IP ranges, email domains, or other namespaces. For example, an intermediate CA may only be allowed to issue certificates for hosts under `internal.example.com`.

**Certificate Policies** carry OIDs describing issuance policies. An application can require a specific set of policies via `PKIXParameters`.

Not every application needs to configure policy OIDs manually, but enterprise PKIs or regulated industries may require checking these policies.

PKIX validation must be configured to match the CA's certificate profile. A certificate signed by a CA does not mean it is suitable for every purpose or every namespace.

## 11. Certificate Revocation Checking: CRL and OCSP

A certificate can be revoked before `Not After`—for example, if the private key is compromised, the identity changes, or the CA discovers the certificate was misissued.

Two common mechanisms:

- **CRL (Certificate Revocation List):** a list of serial numbers of revoked certificates published by the CA.
- **OCSP (Online Certificate Status Protocol):** querying a responder for the status of a certificate.

Validation can check revocation status via CRL/OCSP according to the PKIX provider, system, and policy configuration.

In Java, `PKIXRevocationChecker` allows configuring revocation checking:

~~~java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));

parameters.addCertPathChecker(checker);
~~~

This is an illustrative configuration; production deployments must clearly define CRL/OCSP sources, timeouts, caching, fallback behavior, and how to handle unreachable responders.

There are two common policies:

- **Fail closed:** reject the connection if revocation status cannot be verified.
- **Soft fail:** allow proceeding in certain cases when the responder is unreachable, depending on policy.

Soft fail improves availability but may accept certificates whose revocation status is unknown. Do not enable soft fail just to avoid network errors without assessing the risk.

Revocation checking can introduce network dependencies and latency. The design should account for caching, responder availability, and offline behavior.

## 12. Algorithm Constraints and Security Policy

Certificate validation is also governed by algorithms and key sizes.

The JDK provides security properties such as:

- `jdk.certpath.disabledAlgorithms`: algorithms or key sizes restricted in certificate paths.
- `jdk.tls.disabledAlgorithms`: algorithms restricted in the TLS handshake.

These restrictions can vary by JDK version and security configuration. For example, a key that is too short or a signature using a weak algorithm may be rejected even if the certificate is structurally valid.

Do not weaken global security properties just to connect to a legacy server. Obtain an appropriate certificate or TLS configuration, upgrade the server, and evaluate exceptions through a security review process.

## 13. Validating Certificates in Java with PKIX

Java provides standard APIs to parse X.509 certificates and validate paths.

Key classes:

| API | Role |
|---|---|
| `CertificateFactory` | Parse X.509 certificates and generate `CertPath` |
| `X509Certificate` | Access fields, extensions, and check validity |
| `TrustAnchor` | Declare a trust anchor |
| `PKIXParameters` | Configure validation |
| `CertPathValidator` | Validate a `CertPath` |
| `CertPathBuilder` | Build a `CertPath` from available certificates |
| `CertStore` | Supply intermediate certificates or CRLs |
| `PKIXRevocationChecker` | Configure revocation checking |

A minimal workflow:

1. Read the leaf and trust anchor.
2. Check validity.
3. Build a `CertPath` containing the leaf and intermediate certificates.
4. Create `PKIXParameters` with the trust anchor.
5. Configure revocation and policy as required.
6. Invoke `CertPathValidator`.
7. Check hostname/SAN separately.
8. Check EKU/Key Usage for the intended purpose.
9. Handle exceptions and log without exposing secrets.

## 14. Runnable Java 17+ Example: Validate a Leaf Certificate

This example validates a server certificate signed by a demo root CA. It checks the PKIX path, validity period, SAN hostname, and `serverAuth` EKU.

The program takes three arguments:

- Leaf certificate file.
- Root CA certificate file.
- Hostname to verify.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public final class CertificateValidation {
    private static final String SERVER_AUTH = "1.3.6.1.5.5.7.3.1";

    private CertificateValidation() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: CertificateValidation <leaf.pem> <root.pem> <hostname>");
        }

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        X509Certificate leaf = readCertificate(factory, Path.of(args[0]));
        X509Certificate root = readCertificate(factory, Path.of(args[1]));
        String hostname = args[2];

        leaf.checkValidity();
        root.checkValidity();
        if (root.getBasicConstraints() < 0) {
            throw new IllegalArgumentException(
                    "Trust anchor is not a CA certificate");
        }

        CertPath path = factory.generateCertPath(List.of(leaf));
        PKIXParameters parameters = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));

        // Demo only: production must configure revocation checking.
        parameters.setRevocationEnabled(false);

        CertPathValidator.getInstance("PKIX").validate(path, parameters);

        checkHostname(leaf, hostname);
        checkServerUsage(leaf);

        System.out.println("PKIX path: PASS");
        System.out.println("Leaf certificate validity: PASS");
        System.out.println("Hostname " + hostname + ": PASS");
        System.out.println("Extended Key Usage serverAuth: PASS");
    }

    private static X509Certificate readCertificate(
            CertificateFactory factory, Path file) throws Exception {
        try (InputStream input = Files.newInputStream(file)) {
            return (X509Certificate) factory.generateCertificate(input);
        }
    }

    private static void checkHostname(
            X509Certificate certificate, String hostname) throws Exception {
        Collection<List<?>> names = certificate.getSubjectAlternativeNames();
        if (names == null) {
            throw new IllegalArgumentException(
                    "Certificate has no Subject Alternative Name");
        }

        boolean matched = names.stream().anyMatch(name -> {
            Integer type = (Integer) name.get(0);
            String value = name.get(1).toString();
            return (type == 2 && hostname.equalsIgnoreCase(value))
                    || (type == 7 && hostname.equals(value));
        });

        if (!matched) {
            throw new IllegalArgumentException(
                    "Hostname does not match certificate SAN");
        }
    }

    private static void checkServerUsage(
            X509Certificate certificate) throws Exception {
        List<String> usages = certificate.getExtendedKeyUsage();
        if (usages != null && !usages.contains(SERVER_AUTH)) {
            throw new IllegalArgumentException(
                    "Certificate is not valid for TLS server use");
        }

        boolean[] keyUsage = certificate.getKeyUsage();
        if (keyUsage != null && keyUsage.length > 0
                && !(keyUsage[0]
                || (keyUsage.length > 2 && keyUsage[2])
                || (keyUsage.length > 4 && keyUsage[4]))) {
            throw new IllegalArgumentException(
                    "Key Usage does not permit TLS server signing/agreement");
        }
    }
}
~~~

Save this as `CertificateValidation.java`.

Notes on the example's scope:

- The `CertPath` contains only the leaf because the lab uses a directly signing root CA.
- The trust anchor is provided separately and must be trusted through an out-of-band channel.
- Revocation checking is explicitly disabled so the lab can run offline; do not use this setting as a production policy.
- Hostname matching only demonstrates exact DNS/IP SAN matching; it does not implement wildcards, IDN, or the full HTTPS rules.
- Production HTTPS should use the default hostname verification of JSSE or an HTTP client rather than writing a custom matcher.

## 15. Creating a Root CA and Leaf Certificate for the Lab

The following commands create a demo root CA and a TLS server certificate for `localhost`. Use these only in a learning environment; a demo root CA is not a public CA.

Create the directory:

~~~bash
mkdir -p build
~~~

### Step 1: Create the Root CA

~~~bash
keytool -genkeypair \
    -alias root-ca \
    -keyalg RSA \
    -keysize 3072 \
    -dname "CN=Example Demo Root CA, O=Example, C=VN" \
    -ext BC=ca:true \
    -ext KU=keyCertSign,cRLSign \
    -validity 3650 \
    -keystore build/root-ca.p12 \
    -storetype PKCS12
~~~

`keytool` will prompt for a password. Keep the root CA private key protected; in a lab, you can use a temporary keystore file.

Export the public certificate:

~~~bash
keytool -exportcert -rfc \
    -alias root-ca \
    -keystore build/root-ca.p12 \
    -storetype PKCS12 \
    -file build/root-ca.pem
~~~

### Step 2: Create the Server Key Pair

~~~bash
keytool -genkeypair \
    -alias localhost \
    -keyalg RSA \
    -keysize 2048 \
    -dname "CN=localhost, O=Example, C=VN" \
    -ext SAN=dns:localhost,ip:127.0.0.1 \
    -validity 365 \
    -keystore build/server.p12 \
    -storetype PKCS12
~~~

### Step 3: Create a CSR for the Server

~~~bash
keytool -certreq \
    -alias localhost \
    -keystore build/server.p12 \
    -storetype PKCS12 \
    -file build/server.csr \
    -ext SAN=dns:localhost,ip:127.0.0.1 \
    -ext KU=digitalSignature,keyEncipherment \
    -ext EKU=serverAuth
~~~

The CSR contains the public key and Subject information; the private key remains in `server.p12`.

### Step 4: Sign the CSR with the CA

~~~bash
keytool -gencert \
    -alias root-ca \
    -keystore build/root-ca.p12 \
    -storetype PKCS12 \
    -infile build/server.csr \
    -outfile build/server.pem \
    -rfc \
    -validity 365 \
    -ext SAN=dns:localhost,ip:127.0.0.1 \
    -ext KU=digitalSignature,keyEncipherment \
    -ext EKU=serverAuth
~~~

This simulates a demo CA operation. In production, a CA issues certificates according to identity verification procedures and policies.

### Step 5: Inspect the Certificates

~~~bash
keytool -printcert -v -file build/server.pem
keytool -printcert -v -file build/root-ca.pem
~~~

Verify that the leaf's Issuer matches the root's Subject, the SAN contains `localhost`, the EKU contains `serverAuth`, and the validity period is appropriate.

### Step 6: Compile for Java 17

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/CertificateValidation.java
~~~

Place `CertificateValidation.java` in `src` before running the command.

### Step 7: Run Validation

~~~bash
java -cp build/classes CertificateValidation \
    build/server.pem \
    build/root-ca.pem \
    localhost
~~~

Output verified with JDK 24.0.2:

~~~text
PKIX path: PASS
Leaf certificate validity: PASS
Hostname localhost: PASS
Extended Key Usage serverAuth: PASS
~~~

Test with a wrong hostname:

~~~bash
java -cp build/classes CertificateValidation \
    build/server.pem \
    build/root-ca.pem \
    wrong.example
~~~

This command must fail with a message stating that the hostname does not match the SAN. This is a negative test confirming that the program checks more than just signatures and expiration.

## 16. Using a Custom Truststore with JSSE

In real TLS applications, let JSSE perform PKIX path validation via `TrustManagerFactory` instead of writing a custom `TrustManager` from scratch.

Create a truststore from the verified root CA:

~~~bash
keytool -importcert \
    -alias example-root \
    -file build/root-ca.pem \
    -keystore build/truststore.p12 \
    -storetype PKCS12
~~~

Java snippet to create an `SSLContext` from the truststore:

~~~java
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(
        Path.of("build/truststore.p12"))) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, tmf.getTrustManagers(), null);
~~~

Then configure the `SSLContext` on an HTTP client or `HttpsURLConnection`.

With `HttpsURLConnection`:

~~~java
HttpsURLConnection connection =
        (HttpsURLConnection) url.openConnection();

connection.setSSLSocketFactory(sslContext.getSocketFactory());
~~~

The default hostname verification of `HttpsURLConnection` must still be preserved. Do not replace it with a `HostnameVerifier` that always returns `true`.

With Java `HttpClient`:

~~~java
HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .build();
~~~

Java `HttpClient` performs endpoint verification using the default HTTPS mechanism. When customizing TLS, ensure you do not accidentally disable endpoint identification.

## 17. Custom TrustManagers and the Trust-All Anti-Pattern

A dangerous anti-pattern is creating a `TrustManager` that accepts every certificate:

~~~java
// DO NOT USE IN PRODUCTION APPLICATIONS
X509TrustManager trustAll = new X509TrustManager() {
    public void checkClientTrusted(X509Certificate[] chain, String authType) {
    }

    public void checkServerTrusted(X509Certificate[] chain, String authType) {
    }

    public X509Certificate[] getAcceptedIssuers() {
        return new X509Certificate[0];
    }
};
~~~

Empty methods bypass proper certificate verification. An attacker can impersonate the server in a man-in-the-middle attack if the application accepts the connection.

Do not work around SSL errors by:

- Accepting all certificates.
- Disabling hostname verification.
- Ignoring expired certificate errors.
- Disabling signature or algorithm constraint checks.
- Importing an unknown certificate without verifying its fingerprint.

If a private CA is needed, add the appropriate CA certificate to a dedicated truststore and keep PKIX and hostname verification enabled.

If a custom `TrustManager` is required, prefer delegating to the standard `TrustManagerFactory` and adding narrow, reviewed, and tested policy checks. Do not rewrite full PKIX validation unless there is a clear requirement.

## 18. Mutual TLS (mTLS)

In standard TLS, the client verifies the server's certificate. With mutual TLS, the server also requires the client to present a certificate to verify the client's identity.

mTLS involves two sides:

- Client truststore containing the CA used to verify the server.
- Client keystore containing the client's private key and certificate chain.
- Server truststore containing the CA used to verify the client.
- Server keystore containing the server's private key and certificate chain.

An `SSLContext` can be configured with both a `KeyManager` and a `TrustManager`:

~~~java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(clientKeyStore, clientKeyPassword);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(serverTrustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
~~~

`KeyManager` selects the identity certificate/private key presented by the client. `TrustManager` verifies the peer's certificate.

mTLS does not mean every certificate signed by the CA is allowed to access every API. The application must still enforce identity, role, authorization, and policy checks at the application layer.

## 19. Certificate Pinning

Certificate or public key pinning is a technique where an application accepts only a pre-configured fingerprint or public key.

Pinning can reduce risk when a device's truststore contains unwanted CAs, but it also introduces operational risks:

- Certificate or key rotation can break application connectivity.
- Compromised or misconfigured pins can cause outages.
- Backup pins and a rotation plan must be in place.
- Pinning does not replace hostname verification and PKIX validation.

When using pinning, it is generally better to pin the public key/SPKI or a set of pins with a rotation plan rather than pinning only a short-lived leaf certificate. You must manage old/new pins, overlap windows, and recovery procedures.

Do not implement pinning by comparing a Subject or CN string. Use a standard fingerprint/SPKI format and test rotation.

## 20. Diagnosing Certificate Validation Errors

### CertificateExpiredException

The leaf or a certificate in the path has expired. Check `Not After`, the system clock, and the renewal process.

### CertificateNotYetValidException

The current time is earlier than `Not Before`. Check the system clock, issuance time, and timezone.

### CertPathValidatorException: Path does not chain with any of the trust anchors

No path could be built to a trust anchor. Check the truststore, root CA, intermediate certificates, and the certificate chain order.

### Signature does not verify

A certificate has an invalid signature or the chain is wrong. Verify the certificate source, issuer, file contents, and the chain provided by the CA.

### No subject alternative DNS name matching

The hostname accessed by the client does not match a DNS SAN. Check the URL, SAN, and DNS configuration. Do not disable hostname verification to hide the error.

### No subject alternative names present

The certificate lacks the SAN required for the current hostname/IP. Reissue the certificate with the appropriate SAN.

### Extended key usage does not permit use

The EKU does not permit `serverAuth` or `clientAuth` for the connection's purpose. Issue a certificate with the right profile; do not skip validation just to make the connection succeed.

### Algorithm constraints check failed

The algorithm or key size was rejected by the security policy. Upgrade the certificate/key or configure the server to comply with current policy.

### Revocation status unknown

Could not fetch CRL/OCSP or determine revocation status. Check the network, responder URL, cache, firewall, and fail-open/fail-closed policy.

### Certificate revoked

The certificate has been revoked by the CA. Stop using it and reissue a certificate through the CA process. Do not add a revoked certificate to the truststore.

### PKIX path building failed

General path-building failure. Inspect the underlying cause chain and check intermediate CAs, trust anchors, validity, constraints, and certificate policies.

## 21. Certificate Validation Workflow in Production

A server certificate validation workflow may include:

1. Receive the leaf certificate and intermediate chain from the TLS peer.
2. Build a certification path to a configured trust anchor.
3. Verify signatures and CA constraints according to PKIX.
4. Check the validity period of all certificates in the path.
5. Apply algorithm constraints and certificate policies.
6. Check revocation according to CRL/OCSP policy.
7. Verify that the SAN matches the connected hostname or IP.
8. Verify EKU and Key Usage for TLS server/client.
9. Establish the connection only when all required conditions pass.
10. Log sufficient diagnostic information without logging private keys, passwords, or sensitive data.

For TLS clients, prefer JSSE and standard HTTP clients. Only build a custom `CertPathValidator` when the application needs offline certificate checks, auditing, or specialized policy enforcement.

## 22. Operational Checklist

- [ ] Trust anchors are distributed through a trusted channel.
- [ ] The truststore matches the application and environment.
- [ ] The certificate chain includes the leaf and required intermediates.
- [ ] Root CAs are explicitly accepted according to policy.
- [ ] `Not Before` / `Not After` are valid.
- [ ] SAN matches the hostname/IP.
- [ ] Key Usage and EKU are appropriate.
- [ ] Basic Constraints and path length are valid.
- [ ] Algorithm constraints meet policy.
- [ ] Revocation checking is configured as required.
- [ ] System clocks are synchronized.
- [ ] No trust-all `TrustManager` is present.
- [ ] Hostname verification is not disabled.
- [ ] Certificate rotation and truststore updates are planned.
- [ ] Positive and negative tests exist for expired, untrusted, wrong hostname, and wrong EKU cases.
- [ ] Logs do not contain private keys or passwords.

Certificate validation is more than reading a certificate or checking an expiration date. A secure connection requires verifying the chain to a trust anchor, the intended usage, the hostname, the validity period, and compliance with revocation and algorithm policies. Let JSSE handle standard validation in TLS, manage truststores deliberately, and write custom PKIX logic only when specifically needed.

## References

- [Java Secure Socket Extension (JSSE) Reference Guide — Java SE 24](https://docs.oracle.com/en/java/javase/24/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Java Security Developer's Guide — PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/24/security/java-pki-programmers-guide.html)
- [CertPathValidator API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [PKIXParameters API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/PKIXParameters.html)
- [X509Certificate API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/X509Certificate.html)
