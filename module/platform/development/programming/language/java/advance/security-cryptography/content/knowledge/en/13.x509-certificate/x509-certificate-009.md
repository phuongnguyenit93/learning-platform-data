# 13.9 Setting Up a Test CA and Isolating Test Certificates from Production

## Learning Objectives

After this lesson, you can:

1. Explain **Certificate Authority (CA)**, **root CA**, **end-entity (leaf) certificate**, **Certificate Signing Request (CSR)**, **trust anchor**, **certificate chain**, and X.509 verification mechanics.
2. Use **`keytool` in JDK 17+** to set up a practice root CA, generate server keys, create a CSR, issue a server certificate with **Subject Alternative Name (SAN)** and **Extended Key Usage (EKU)**, store the certificate in **PKCS12**, and create a **separate test truststore**.
3. Distinguish **a certificate signed by a CA** from **a certificate trusted by a client**. A valid signature is not enough: you also need an authorized trust anchor, a valid chain, valid dates, matching hostname, and suitable usage policy.
4. Read and inspect certificates with `keytool` and use **Java `CertPathValidator`/PKIX** to test certification paths solely to **the lab root CA**.
5. Maintain an unmistakable boundary between **lab/test** and **production**: never place test CAs into `cacerts`, OS trust, user devices, production containers, or shared truststores; never use test private keys in production; never disable TLS verification to bypass errors.
6. Design negative tests (untrusted CA, wrong hostname, wrong EKU, expired or tampered certificate), revocation/rotation procedures, and pre-deployment checklists.

**Key message:** Creating your own test CA is a great way to learn **PKI/X.509/TLS**, yet it simultaneously creates significant power: any client that trusts that CA can trust certificates issued by it **according to the client's verification policy**. Therefore, a lab CA must have **a dedicated trust scope, short lifetimes, lab-only identifiers, and must never be pushed to production**.

## 1. What Does a CA Do, and What Makes a Certificate Trusted?

In PKI, a **CA** owns a key pair. The CA's private key is used to **sign** X.509 certificates for other subjects/public keys; the CA's certificate contains its public key and identifying info. When a TLS client receives a server certificate, it verifies signatures and the certification path up to a **trust anchor** it has explicitly configured as trusted.

~~~text
                       TRUST ANCHOR (chosen by client)
                           Lab Root CA certificate
                           Lab Root CA public key
                                      |
                               signs leaf certificate
                                      v
Server key pair ---> CSR ----> Lab Server certificate
(private key stays on server)  SAN=DNS:localhost,IP:127.0.0.1
                               EKU=serverAuth
                                      |
                                  TLS handshake
                                      |
Client checks:
   does server cert match the public/private key in use?
   does the signature path reach a CA the client TRUSTS?
   unexpired? valid extensions and key usage?
   does hostname/IP match SAN?
   any trust policy or revocation violations?
~~~

**Self-signed** merely states that the certificate was signed with the private key matching the public key inside that certificate itself. It is **not automatically trusted by every machine**. Only when a client explicitly trusts that CA certificate (or an equivalent trust mechanism) does it become a **trust anchor** for verification.

### 1.1 “Signed” Differs from “Trusted”

Suppose the lab root issues a certificate for `server.example.com`. Somehow an attacker inserts the lab root into a production application's truststore. Then anyone holding the lab CA private key can issue certificates for domains the application accesses. Without other controls, **the cert chain can be treated as trusted**, creating endpoint impersonation / MITM risk.

Therefore, the **truststore boundary** is a critical security boundary: adding a root CA is not simply “adding a cert file to make an error go away”—it **grants authority to issue trusted certificates** within the usage scope of that truststore.

### 1.2 Components to Distinguish

| Component | Function | Has private key? | Put into production? |
| --- | --- | --- | --- |
| **Lab root CA private key** | Signs leaf certificates in the lab | **Yes, extremely sensitive** | **Never** |
| **Lab root CA certificate** | Supplies public key for signature checks and can serve as trust anchor | No | **Must not be installed as a production trusted root** |
| **CSR** | Certificate request holding public key and proposed subject | Contains no private key | Only via controlled issuance workflows |
| **Lab server leaf private key** | Server proves key possession in TLS | Yes | Never use for production identity |
| **Lab leaf certificate** | Binds server public key to name/attributes certified by lab CA | No | Not a trusted production certificate |
| **Server keystore** | Stores keypair and certificate chain for server | Usually has private key | Lab use only |
| **Dedicated client truststore** | Holds lab root certificate explicitly trusted by practice client | Usually public certs only | Must not be used as shared/prod truststore |

**Both keystores and truststores can use PKCS12**. The difference is **role**: the server needs identity keys, while the client needs trust anchors it intentionally trusts.

## 2. Essential X.509 Terminology Before Issuance

### 2.1 BasicConstraints: CA or End Entity?

The X.509 **BasicConstraints** extension specifies whether the subject may act as a CA, with an optional path length.

- **Test root CA:** BasicConstraints **`CA=true`**, marked **critical** per proper policy. A CA can sign leaves; this lab uses **`pathLen=0`** to avoid creating unnecessary intermediate CA chains.
- **Server leaf:** BasicConstraints **`CA=false`**. It is an end entity, **not granted CA certificate-issuance rights**.
- **`pathLen=0`** caps the number of subsequent intermediate CAs in the certification path; it **does not mean the CA cannot sign leaf certificates**.

If a leaf has `CA=false` yet carries `KeyUsage keyCertSign`, the configuration is inconsistent in purpose and must not be treated as a valid CA per profile. Never accidentally make a CA certificate into a server certificate.

### 2.2 KeyUsage and ExtendedKeyUsage

**KeyUsage (KU)** restricts cryptographic operations permitted for the public key in the certificate:

- CA: **`keyCertSign`**; may add **`cRLSign`** if designed to sign revocation lists.
- TLS server with RSA: typically needs **`digitalSignature`** (especially modern TLS); depending on protocol/config, may include **`keyEncipherment`** for legacy compatibility.
- Never set **`keyCertSign`** on a leaf.

**ExtendedKeyUsage (EKU)** expresses higher-level application purposes. For an HTTPS server leaf, this lab uses:

~~~text
EKU = serverAuth
OID = 1.3.6.1.5.5.7.3.1
~~~

To issue a certificate for an mTLS client, EKU **`clientAuth`** is a different purpose; never assume every leaf automatically works for authenticating both servers and clients.

### 2.3 Subject Alternative Name and Hostname Verification

Today's HTTPS clients use **Subject Alternative Name (SAN)** to verify server identity under appropriate rules. Subject CN **does not replace** SAN for a modern TLS configuration.

In this lab, we issue the leaf with:

~~~text
Subject: CN=localhost, O=Local Training, C=VN
SAN: DNS:localhost, IP:127.0.0.1
EKU: serverAuth
BasicConstraints: CA=false
~~~

This serves accessing **`https://localhost`** or **`https://127.0.0.1`** in the lab depending on server/client setup. **Never add SANs for real company domains or production domains**. If the hostname you access is `service.prod.example.com`, a lab certificate for `localhost` must **not** match; never disable hostname verification to hide the error.

### 2.4 Validity, Serial Number, Issuer, and Trust

Every X.509 certificate has:

- **Subject:** certified identity, e.g., `CN=localhost`; not the entire hostname-checking rule set.
- **Issuer:** signing CA's name.
- **Validity:** Not Before and Not After, subject to clock and policy.
- **Serial number:** identifier within the issuer's scope.
- **Signature algorithm and CA signature:** used to confirm the certificate bytes were signed by the CA.
- **Public key:** the subject's public key.
- **Extensions:** SAN, KU, EKU, BasicConstraints, SKI/AKI, policy, CRL/OCSP depending on design.

**Having a valid signature does not mean belonging to a trusted certification path**. The client needs a trust anchor, path validation, validity, purpose, hostname, and revocation status per policy and application.

## 3. Lab Scope and Isolation Rules Upfront

**Lab model used in this lesson:**

- A separate directory **`ca-lab/`**, **never synced to repos or CI artifacts**.
- One self-signed root CA, issuing leaves **only for `localhost`**.
- Root validity **30 days**, leaf validity **7 days**.
- **3072-bit** RSA keys, **`SHA256withRSA`** signatures for demo, requiring no tools outside the JDK.
- All keystores/truststores created by the lab use **PKCS12**.
- Passwords entered interactively; **never embedded in shell history, scripts, READMEs, Dockerfiles, or command lines**.
- Never copy any lab certificate to production truststores, **`$JAVA_HOME/lib/security/cacerts`**, OS/system trust, shared browser profiles, or non-lab service accounts.
- Root private key does not reside on any host/container running a real server. The lab uses one directory for learning convenience; real designs separate the CA host from runtime services.
- Never authorize public DNS domains, company IPs, or arbitrary SANs from unfamiliar CSRs.

**Lab limitations:** This is a learning environment for certificate issuance, not operating a full-scale Public CA or Internal PKI. It **does not set up** CRL/OCSP responders, CA audits, certificate transparency, HSMs, approval workflows, or high availability. Never treat the lab root as a production-grade CA simply because `keytool` generated it.

## 4. Hands-On with JDK 17+ `keytool`: Root → CSR → Leaf → Truststore

The **`keytool`** commands below are complete, each on **a single line**, so you can type them in Bash, PowerShell, or any terminal with `keytool` on `PATH`. If JDK 17+ is not installed, install an appropriate JDK; **`java -version`** and **`keytool -help`** verify the active tools.

**Never run these commands in a directory containing production keystores**. Filenames intentionally include `lab`. Never use a fixed sample password from documentation; when `keytool` prompts, enter a strong password used solely for this lab. You do not need to reuse one password across root, server, and truststore.

### 4.1 Create an Isolated Workspace

~~~bash
mkdir ca-lab
cd ca-lab
~~~

Ensure the directory is outside repositories/shared drives with restricted permissions. The files to be created are **`lab-root.p12`**, **`lab-root.pem`**, **`lab-server.p12`**, **`lab-server.csr`**, **`lab-server.pem`**, and **`lab-client-trust.p12`**. When starting over, use a fresh lab directory; never overwrite files containing valuable keys or certificates.

### 4.2 Create a Test Root CA, Not a Server Certificate

~~~bash
keytool -genkeypair -alias lab-root -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Lab Root CA, O=Local Training, C=VN" -validity 30 -ext BC:critical=ca:true,pathlen:0 -ext KU:critical=keyCertSign,cRLSign -keystore lab-root.p12 -storetype PKCS12
~~~

This generates a **`PrivateKeyEntry`** with a 3072-bit RSA private key and a **self-signed X.509 root CA certificate** in `lab-root.p12`.

Key explanations:

- **`BC:critical=ca:true,pathlen:0`:** indicates the certificate acts as a CA, disallowing subsequent intermediate CAs in a normal certification path.
- **`KU:critical=keyCertSign,cRLSign`:** grants the root permission to sign certificates and CRLs per KU bits, though the lab **does not yet run CRLs** and must not be treated as having revocation controls.
- **`-validity 30`:** 30-day root certificate lifetime; implies no default production CA lifetime standard.
- **`-sigalg SHA256withRSA`:** specifies the signing algorithm for the example.
- **`lab-root.p12`:** contains the **CA private key**; protect carefully, never send to clients/servers, and never commit to Git.

Inspect the root certificate in the keystore:

~~~bash
keytool -list -v -alias lab-root -keystore lab-root.p12 -storetype PKCS12
~~~

Expect **`Entry type: PrivateKeyEntry`**, issuer/subject as the lab root, `BasicConstraints CA:true`, and `KeyUsage` containing `keyCertSign`. `keytool` displays a fingerprint, serial, and validity specific to that generation run.

### 4.3 Export **Only the Public Certificate** of the Root

~~~bash
keytool -exportcert -rfc -alias lab-root -file lab-root.pem -keystore lab-root.p12 -storetype PKCS12
~~~

**`lab-root.pem`** is a public PEM certificate **containing no private key**. It can be distributed to **authorized lab clients** once the client verifies its fingerprint over a trusted channel. Never confuse an arbitrary PEM copy with an origin-verified trust anchor.

Inspect:

~~~bash
keytool -printcert -file lab-root.pem
~~~

Examine subject, issuer, validity, `BasicConstraints`, KU, and **SHA-256 fingerprint**. When importing this root into a truststore, the administrator must compare the fingerprint against a value delivered via an **independent authenticated channel**, never blindly trusting a file sent over an untrusted channel.

### 4.4 Generate the Server Key and Temporary Self-Signed Certificate

~~~bash
keytool -genkeypair -alias lab-server -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=localhost, O=Local Training, C=VN" -validity 7 -keystore lab-server.p12 -storetype PKCS12
~~~

`keytool` generates a private key and a temporary self-signed certificate in **`lab-server.p12`**. **This is not yet a certificate signed by `lab-root`.** When you import the certificate reply from `lab-root`, the entry under alias `lab-server` is updated to hold the corresponding certificate chain.

The **server private key** in `lab-server.p12` must stay within the lab server's boundary. The CA needs **the CSR**, never the raw server private key.

### 4.5 Create a Certificate Signing Request (CSR)

~~~bash
keytool -certreq -alias lab-server -file lab-server.csr -keystore lab-server.p12 -storetype PKCS12
~~~

The CSR is signed with **`lab-server`'s private key** and carries the public key and requested subject info. The CSR **does not contain the server private key**. A real CA must also check which identities/SANs the requester is authorized to request.

To view CSR contents:

~~~bash
keytool -printcertreq -file lab-server.csr -v
~~~

**Security warning:** Never automatically grant every domain name claimed in a CSR. In this lab, **the CA signs with SANs explicitly set by the issuance command**, never using **`-ext honored=all`** to accept all extensions requested by an untrusted CSR.

### 4.6 CA Signs the CSR into a Leaf for `localhost`, with SAN and `serverAuth`

~~~bash
keytool -gencert -alias lab-root -keystore lab-root.p12 -storetype PKCS12 -infile lab-server.csr -outfile lab-server.pem -rfc -validity 7 -ext BC:critical=ca:false -ext KU:critical=digitalSignature,keyEncipherment -ext EKU=serverAuth -ext SAN=dns:localhost,ip:127.0.0.1
~~~

Key points:

- **`-alias lab-root`:** uses the CA's private key to sign the certificate reply for the CSR's subject.
- **`-rfc`:** Base64 PEM output instead of DER.
- **`-validity 7`:** short-lived leaf; root validity should cover the leaf's lifetime in the lab.
- **`BC:critical=ca:false`:** leaf is an end entity and cannot act as a CA.
- **`KU:critical=digitalSignature,keyEncipherment`:** restricts RSA public key usage to declared capabilities; modern TLS relies on `digitalSignature`.
- **`EKU=serverAuth`:** marks the TLS server authentication purpose.
- **`SAN=dns:localhost,ip:127.0.0.1`:** local-lab-only identities; never issue certificates for real domains.

**In practice**, a CA requires identity verification workflows, SAN restrictions, serial management, private-key controls, CRL/OCSP, and auditing. A local `keytool -gencert` does not create those operational controls.

Inspect the signed leaf:

~~~bash
keytool -printcert -file lab-server.pem
~~~

Observe and verify: **`Issuer = Lab Root CA`**, **`Subject = localhost`**, SAN has `localhost`/`127.0.0.1`, `BasicConstraints CA:false`, and matching KU and EKU.

### 4.7 Add the Public Root to the Server Keystore to Build the Certificate Chain

Before importing the leaf reply, import **the verified root certificate** into the server keystore under a different alias from the private key:

~~~bash
keytool -importcert -alias lab-root-trust -file lab-root.pem -keystore lab-server.p12 -storetype PKCS12
~~~

`keytool` may ask whether you trust this root certificate. **Answer yes only after verifying the exact lab root fingerprint**. In the practice server keystore, this public certificate lets `keytool` build the chain for the leaf. It does **not** mean the server should simultaneously use its identity keystore as a general truststore.

Then import the certificate reply into **the exact `lab-server` alias** to replace the temporary self-signed certificate:

~~~bash
keytool -importcert -alias lab-server -file lab-server.pem -keystore lab-server.p12 -storetype PKCS12
~~~

**Import order matters**: the issuer root must be available for `keytool` to build the chain before importing a standalone leaf reply. Verify the result:

~~~bash
keytool -list -v -alias lab-server -keystore lab-server.p12 -storetype PKCS12
~~~

Expect **`PrivateKeyEntry`** with **certificate chain length = 2** in this single-root + single-leaf lab: the first cert is `lab-server` signed by root; the next is the root CA. Exact counts/formatting can vary by import method or provider; if the expected chain does not appear, diagnose rather than skipping verification.

**Never copy `lab-root.p12` onto the server machine**. The server needs only **its own private key** and public cert chain; the CA signing key must remain isolated.

### 4.8 Create a Dedicated Truststore for the Test Client

~~~bash
keytool -importcert -alias lab-root-trust -file lab-root.pem -keystore lab-client-trust.p12 -storetype PKCS12
~~~

If the truststore does not exist yet, `keytool` creates a new file and prompts for a password. When asked whether to trust the cert, confirm only after checking and comparing the SHA-256 fingerprint of `lab-root.pem` via an independent channel.

Inspect:

~~~bash
keytool -list -v -keystore lab-client-trust.p12 -storetype PKCS12
~~~

**Expected:** the truststore has a **`TrustedCertificateEntry`** for alias `lab-root-trust`, containing the exact root CA public certificate, **no private key**, and **no other root certificates**. Keep this truststore isolated from production and enterprise-wide truststores.

### 4.9 Final File Inventory

| File | Contents | Who may use it? | Protection rules |
| --- | --- | --- | --- |
| **`lab-root.p12`** | Root CA private key + root certificate | Lab CA operator only | Keep secret; never ship to clients/servers/production |
| **`lab-root.pem`** | Root CA public certificate | Lab client after fingerprint check | Must not be installed as a machine-wide trusted root |
| **`lab-server.p12`** | Server private key + leaf cert chain (plus root trusted entry for chain building) | Lab server only | Restrict file permissions/password |
| **`lab-server.csr`** | CSR with public key/subject | Lab CA | Contains no private key; still verify requester/SAN |
| **`lab-server.pem`** | Leaf public certificate signed by lab root | Lab client/server | Not secret, yet does not prove self-trust |
| **`lab-client-trust.p12`** | `TrustedCertificateEntry` for lab root | Lab client process only | Never replace `cacerts`/OS trust store |

**Absolutely never** place `lab-root.p12` anywhere near production applications. The root private key is the most sensitive asset in this model because it can issue new certificates trusted by clients.

## 5. Java 17+: Reading and Verifying the Path to the Exact Lab CA

`keytool` commands inspect store and certificate contents, yet to understand JCA, write a program that reads the two created files and runs **PKIX certificate path validation**.

This **`LabCaCheck.java`** program:

- Reads keystore and truststore passwords via **`Console.readPassword()`** (keeping passwords off the command line).
- Loads **`lab-server.p12`** and **`lab-client-trust.p12`** as PKCS12.
- Retrieves the leaf from alias `lab-server` and the root certificate from alias `lab-root-trust`.
- Checks that root has `BasicConstraints CA=true`, leaf has `CA=false`, leaf has EKU `serverAuth`, and leaf has DNS SAN `localhost`.
- Calls **`CertPathValidator.getInstance("PKIX")`** with **only the lab root certificate** as `TrustAnchor`.
- Does **not** disable or replace PKIX signature/path validation; sets **`revocationEnabled(false)`** only in the lab because the example runs no CRL/OCSP.
- Does not use the default truststore/`cacerts` and does not grant JVM-wide trust.

**This is a certificate path practice example, not a complete TLS client.** Checking SAN manually here only proves SAN data exists; it does not replace HTTPS hostname verification rules; server certificates must still be checked by the TLS stack against the actual endpoint.

File **`LabCaCheck.java`**:

~~~java
import java.io.Console;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public class LabCaCheck {
    private static KeyStore openPkcs12(
            String filename, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(Path.of(filename))) {
            store.load(input, password);
        }
        return store;
    }

    private static boolean hasLocalhostSan(X509Certificate certificate)
            throws Exception {
        Collection<List<?>> san = certificate.getSubjectAlternativeNames();
        if (san == null) {
            return false;
        }
        for (List<?> item : san) {
            // SAN type 2 = dNSName
            if (Integer.valueOf(2).equals(item.get(0))
                    && "localhost".equalsIgnoreCase(
                            String.valueOf(item.get(1)))) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                "Run from an interactive terminal (Console required)");
        }

        char[] serverPassword =
                console.readPassword("Lab server keystore password: ");
        char[] trustPassword =
                console.readPassword("Lab client truststore password: ");
        if (serverPassword == null || trustPassword == null) {
            throw new IllegalStateException("Password input aborted");
        }

        try {
            KeyStore server = openPkcs12(
                    "lab-server.p12", serverPassword);
            KeyStore trust = openPkcs12(
                    "lab-client-trust.p12", trustPassword);

            X509Certificate leaf = (X509Certificate)
                    server.getCertificate("lab-server");
            X509Certificate root = (X509Certificate)
                    trust.getCertificate("lab-root-trust");

            if (leaf == null || root == null) {
                throw new IllegalStateException(
                    "Required lab certificate alias missing");
            }

            leaf.checkValidity();
            root.checkValidity();

            boolean rootIsCa = root.getBasicConstraints() >= 0;
            boolean leafIsEndEntity = leaf.getBasicConstraints() == -1;
            List<String> eku = leaf.getExtendedKeyUsage();
            boolean serverAuth = eku != null &&
                    eku.contains("1.3.6.1.5.5.7.3.1");
            boolean localhostSan = hasLocalhostSan(leaf);

            System.out.println("Root is CA: " + rootIsCa);
            System.out.println(
                    "Leaf is end entity: " + leafIsEndEntity);
            System.out.println(
                    "Leaf allows serverAuth: " + serverAuth);
            System.out.println(
                    "Leaf SAN includes localhost: " + localhostSan);

            if (!rootIsCa || !leafIsEndEntity
                    || !serverAuth || !localhostSan) {
                throw new SecurityException(
                    "Lab certificate extensions do not match policy");
            }

            CertificateFactory factory =
                    CertificateFactory.getInstance("X.509");
            CertPath path = factory.generateCertPath(List.of(leaf));

            PKIXParameters parameters = new PKIXParameters(
                    Set.of(new TrustAnchor(root, null)));

            // Lab checks only the chain; CRL/OCSP is NOT yet operated.
            // Production must configure revocation per PKI policy.
            parameters.setRevocationEnabled(false);

            CertPathValidator.getInstance("PKIX")
                    .validate(path, parameters);
            System.out.println("PKIX chain to lab root: VALID");
        } finally {
            Arrays.fill(serverPassword, '\0');
            Arrays.fill(trustPassword, '\0');
        }
    }
}
~~~

Compile and run **from the `ca-lab` directory** after creating the files in Section 4:

~~~bash
javac -encoding UTF-8 LabCaCheck.java
java LabCaCheck
~~~

The program prompts interactively for two passwords. If all files/aliases/extensions/chains are valid and unexpired, the **stdout after the two prompts** will be:

~~~text
Root is CA: true
Leaf is end entity: true
Leaf allows serverAuth: true
Leaf SAN includes localhost: true
PKIX chain to lab root: VALID
~~~

The program intentionally **throws an exception** on a wrong password, missing alias, expired certificate, policy mismatch, or failed PKIX path validation. This is **fail-closed** behavior, far better than returning true unconditionally.

### 5.1 Why Does `CertPath` Contain Only the Leaf?

A certificate path **does not need the root trust anchor inside the certificate list to be validated**; the root is declared separately via **`PKIXParameters(Set<TrustAnchor>)`**. This lab has no intermediate CA, so the path contains only **the leaf**. In multi-tier PKIs, the path must list intermediates in order or use `CertPathBuilder` appropriately to find the chain.

**`TrustAnchor` is a pre-trusted application input**. Putting any network-supplied root certificate into `Set.of(new TrustAnchor(...))` without verifying its origin **breaks the trust boundary**. In the example, the root is loaded from a dedicated, authorized, fingerprint-verified truststore.

### 5.2 Why Is `revocationEnabled(false)` Acceptable Only in the Lab?

A certificate may need to be revoked before `NotAfter` due to private-key compromise, server decommissioning, or CA misissuance. In production PKI, policy-compliant revocation checks use **CRL, OCSP, properly implemented TLS mechanisms, and lifecycle controls**.

This lab **provides no CRL/OCSP**, so it intentionally disables revocation in the program solely to focus on chain/signature/path validation. **Never copy this line as a production security default**, and never assume toggling a boolean suffices if the PKI lacks proper revocation status infrastructure.

### 5.3 Does This Code Fully Verify Hostnames?

**Not yet.** `hasLocalhostSan` checks only **one DNS SAN** matching the lab's goal. It does **not** implement full HTTPS hostname verification rules (wildcards, IP SAN, IDN, normalization, policy). For HTTPS, let a **reputable HTTPS/TLS library** verify the hostname. If using `SSLSocket` directly, configure endpoint identification appropriately.

## 6. Using a Lab Truststore in JSSE Without Expanding Trust to Production

### 6.1 Never Put the Lab Root into `cacerts`

**Never run** any variant of importing the lab root targeting:

~~~text
$JAVA_HOME/lib/security/cacerts
keytool -importcert -cacerts ...
Windows Trusted Root Certification Authorities
macOS System Keychain trust
Shared browser/OS trust profiles
Production container images or trust bundles
~~~

The lines above are a **list of places forbidden for the lab CA**, not commands to run. Importing the root into a shared truststore allows many applications outside the lab **to potentially** trust leaves issued by the lab CA. That change exceeds the test scope and creates MITM risk.

**Key distinction:** A public root certificate is not necessarily secret, yet **placing it in the trusted roots list** is a trust-granting action with major security impact.

### 6.2 Per-Process Usage: Supply the Truststore Only to the Lab App

For a dedicated Java process used to study TLS, you can point **`javax.net.ssl.trustStore`** to **`lab-client-trust.p12`** with **`javax.net.ssl.trustStoreType=PKCS12`** under a dedicated test configuration. However, **never put plaintext passwords on the command line or in logs** in real systems. A more controlled approach is **loading the truststore in Java and creating a dedicated `SSLContext`** for the lab HTTP/TLS client.

The Java snippet below **is not a standalone program**: it assumes **`labTrust`** has been loaded from PKCS12 with the right password and the lab endpoint URL has a running TLS server.

~~~java
TrustManagerFactory factory = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
factory.init(labTrust);

SSLContext labTls = SSLContext.getInstance("TLS");
labTls.init(null, factory.getTrustManagers(), null);

HttpsURLConnection conn = (HttpsURLConnection)
        new URL("https://localhost:8443/").openConnection();
conn.setSSLSocketFactory(labTls.getSocketFactory());
conn.connect();
// Never replace HostnameVerifier; HTTPS continues checking the hostname.
~~~

To compile this snippet into a program, you need imports for **`javax.net.ssl.TrustManagerFactory`**, **`javax.net.ssl.SSLContext`**, **`javax.net.ssl.HttpsURLConnection`**, **`java.net.URL`**, and code loading `labTrust`. This snippet illustrates an **`SSLContext` scoped to a single lab connection**; do not run it without a lab TLS server listening on port 8443.

**Never do the following:**

~~~java
// ANTI-PATTERN: Never use in lab or production.
HttpsURLConnection.setDefaultHostnameVerifier(
        (hostname, session) -> true);
~~~

That disables host identity verification for many connections using that API class, removing an essential safeguard. A “trust-all `X509TrustManager`” is equally dangerous. **Fix certificate errors by adding the right root CA to an authorized lab truststore**, never by disabling verification.

### 6.3 Remember: Truststore and Hostname Validation Are Two Separate Steps

Even when **the PKIX path** is valid:

- If the client accesses **`https://service.company.example`** while the cert only has `SAN=localhost`, **the hostname must be rejected**.
- If the cert has the right SAN yet does not chain to a client-trusted root, **path validation must fail**.
- If the cert is expired or not yet valid, **time validation must fail**.
- If EKU/KU does not match or the TLS stack rejects the algorithm/signature, **the handshake must fail**.
- If revocation checks are required but cannot be completed per policy, handle per policy; never silently skip.

Never confuse “I can print the certificate” with “TLS authenticated the right peer”.

### 6.4 Server Keystore and Client Truststore Must Not Swap Roles

A server needs **`KeyManagerFactory`** accessing its private key and chain to prove identity to TLS peers. A client needs **`TrustManagerFactory`** with CA roots/anchors to verify server certificates. In **mutual TLS (mTLS)**, both sides may have both an identity keystore and a truststore, yet responsibilities and permissions remain distinct.

Never use **`lab-root.p12`** as a server keystore: that puts **the CA signing private key** on the server, creating huge risk. The server must use only `lab-server.p12` containing the **server leaf** private key. The client receives only `lab-root.pem`/`lab-client-trust.p12`, **never server/CA private keys**.

## 7. Negative Test Suite to Prove the Boundary Truly Exists

A lab CA succeeds not because “we have files and a chain”, but because **only authorized lab clients trust it; unauthorized parties still reject it**.

| Scenario | Expected result | What is verified |
| --- | --- | --- |
| Lab client uses right lab truststore and connects to lab server's `localhost` | Handshake succeeds if server/protocol are properly configured | CA trust + SAN + key usage + validity |
| Another client uses default truststore lacking the lab root | **Does not trust lab server certificate** | No trust leakage outside lab scope |
| Lab client accesses server using a hostname absent from SAN | **Rejects hostname** | Hostname verification not disabled |
| Lab client trusts a different test root but not this lesson's root | **Rejects chain** | Trust anchor is not just any self-signed cert |
| Leaf replaced with cert signed by a key not belonging to lab root | **Rejects path** | Signatures and path must verify |
| Byte modified in signed certificate contents | **Rejects** | Cannot tamper with cert without breaking signature |
| Leaf expired, before `NotBefore`, or major clock skew | **Rejects per policy** | Validity checks |
| Leaf lacks `serverAuth` EKU when required by policy | **Rejects** | Purpose checks |
| `CA=true` leaf used as server identity | **Do not use for lab server** | Distinguishes CA from end entity |
| Root CA private key appears inside container/app runtime | **Architectural bug to fix** | CA signing keys are never distributed |
| Someone proposes importing lab root into production `cacerts` | **Reject change** | Blocks out-of-scope trust expansion |
| Revoked certificate yet still unexpired | Must be handled via revocation policy in production | Validity dates do not replace revocation |
| Remove lab truststore from lab process | Lab certificate is no longer trusted without external trust | Trust can be revoked by scope |

**Important:** To test “default truststore does not trust lab CA”, confirm the environment has not had the lab CA installed previously. You cannot claim every machine rejects it if the lab CA was imported into a shared truststore during an earlier test.

### 7.1 Failing Identity Checks Are No Reason to Bypass HTTPS

A familiar mistake:

~~~text
SSLHandshakeException: PKIX path building failed
                   |
Developer: "Probably self-signed cert, let's enable trust-all"
                   |
           All fake endpoints can now be accepted too
~~~

The right fix:

1. Classify the error: **untrusted issuer**, **hostname mismatch**, **expired cert**, **EKU/KU mismatch**, **missing chain**, **wrong key**, or **revocation**.
2. For a **lab CA**, verify the truststore file of **only the test client** and check the fingerprint.
3. For production domains, use certificates/chains from CAs trusted under production policy; **never put a lab CA into production to silence errors**.
4. Keep hostname verification, PKIX path validation, and proper TLS versions/cipher suites enabled.
5. Add negative tests to ensure fixes do not unintentionally widen trust.

### 7.2 Never Issue Arbitrary SANs from a CSR

A CSR proves control over **the requesting keypair's private key** via the CSR signature; it **does not prove ownership of DNS names/IPs**. If a CA blindly accepts `-ext honored=all` and whatever SAN a client requests, it could sign certificates for domains outside lab scope.

In this lesson, the CA signs with SANs **`localhost`/`127.0.0.1`** via a tightly controlled `-gencert` command. A real internal CA must enforce identity verification, domain/namespace approvals, and issuer configuration limits.

## 8. Boundaries That Must Be Maintained Between Test and Production

### 8.1 Separate Key Material

**Never share CA or leaf keys** between lab and production.

- **Lab root private key** exists only in authorized lab storage/accounts.
- **Production CA/private keys** must be provisioned via approved CA/KMS/HSM workflows, never taken from an exercise.
- Never place lab root keys in source code, shared environment variables, CI artifacts, Docker images, or production backups.
- If demoing mTLS across multiple teams, use **dedicated per-environment/per-team CAs or approved namespaces**, never an enterprise-wide lab root.

### 8.2 Separate Trust Anchors and Truststores

**Production truststores must not contain lab roots**. Test clients trust the lab root only within test runtime scope; production processes use only roots approved by production policy.

A separate truststore file that gets mounted into every service is still a **shared truststore in impact**. Separate **deployment paths, permissions, accounts, CI/CD variables, container mounts, and runtime environments** as well.

### 8.3 Separate Identifiers and Infrastructure

Use only **`localhost`, loopback, or DNS namespaces reserved by your organization for testing**. Never put public company domains in SANs, never name a root similarly to a real CA, and never issue production-looking subjects that could easily be copied by mistake.

Prefix filenames clearly:

~~~text
lab-root.p12
lab-root.pem
lab-server.p12
lab-server.csr
lab-server.pem
lab-client-trust.p12
~~~

Filenames are only **operational signals**, not security barriers. Enforce actual isolation with IAM, policies, code reviews, and truststore checks.

### 8.4 Short Lifetimes Do Not Replace Scope Limits

A 7-day leaf certificate can still be abused if production clients already trust the lab root. Short lifetimes shrink the exposure window, yet **do not eliminate impersonation** before expiration.

A 30-day root expiration likewise does not protect against all operational flaws, especially when processes fail to enforce policies or retain old trust anchors. Manage validity, revoke trust, remove bad deployments, and monitor.

### 8.5 Never Turn a Lab Certificate into Production by Importing It

**A valid path to production is NOT:**

~~~text
lab-root.pem
       |
import into $JAVA_HOME/lib/security/cacerts
       |
"Works in prod"  <- TRUST SEPARATION FAILURE
~~~

**The right workflow:**

~~~text
Lab documentation/prototype
       |
Review production PKI requirements
       |
Request/issue keys and certificates via an authorized CA
       |
Verify identity, SAN, EKU, chain, validity
       |
Provision trust per production policy
       |
Test, audit, rotate, and monitor
~~~

Ensure production never inherits a lab root via image layers, mounted volumes, keystores, secrets, env vars, or config bundles.

## 9. Revocation, Rotation, and Decommissioning the Lab

### 9.1 Difference Between Deleting a Leaf and Revoking Root Trust

Deleting only `lab-server.p12` still leaves lab clients trusting the root, and the root private key can still issue a new leaf. **To stop trusting the entire lab CA**, you must **remove the root from the truststores of every authorized lab client** and revoke truststore distribution access.

If the root key is compromised, you cannot “change the PKCS12 password” and consider all issued CA certificates safe. You must **stop trusting that root**, build a new root if the lab is still needed, re-issue leaves, update truststores, and assess the blast radius.

### 9.2 Certificate Revocation and Status Checking

**CRL and OCSP** are common mechanisms for publishing/checking certificate status. A lab CA created with the `keytool` command above **does not automatically run** revocation infrastructure. `KeyUsage cRLSign` only describes **the key's permission/capability to sign CRLs**; it does not generate CRLs by itself.

For production, establish clear policies: whether status is checked, where responders/CRLs live, offline behavior, logging, and revocation SLAs. Never take **`PKIXParameters.setRevocationEnabled(false)`** from the lab example to skip revocation by default in real systems.

### 9.3 Post-Lesson Cleanup Checklist

1. Stop lab TLS server/client processes.
2. Verify **no lab CA exists** in `cacerts`, OS trust, shared browser profiles, images, or production deployments.
3. Revoke/remove access to the lab truststore when no longer needed.
4. Securely delete or archive **`lab-root.p12`/`lab-server.p12`** and related passwords/backups per organizational policy. Never upload key files to tickets/chat.
5. Remove per-process configs and truststore mounts used for the lesson.
6. Verify no test environment is using expired/broken certificates as an excuse to disable TLS verification.
7. If a lab root was accidentally added to production trust, treat it as a **security incident**, inventory affected systems, remove the root, rotate affected credentials, and assess impersonation risk.

**Note:** Never blindly delete `cacerts` or shared truststores to “clean up the lab”; remove only the specific lab root **if it was installed, following approved change procedures**.

## 10. Common Mistakes to Avoid

1. **“The CA was created by `keytool`, so all Java clients automatically trust it.”** False: a self-signed root has no trust anchor in clients yet.
2. **“A valid leaf signature alone makes TLS secure.”** False: trust anchor, hostname, EKU/KU, validity, algorithms, revocation status, and policy also apply.
3. **“Leaf `CN=localhost` is enough; no SAN needed.”** Violates modern HTTPS hostname verification; supply properly typed DNS/IP SANs.
4. **“The root CA can be used as the server identity.”** No: the server needs a purpose-built leaf private key/cert; never put the CA signing key on servers.
5. **“The lab root CA is already in a truststore, so share it with production for convenient testing.”** Serious mistake: widens trusted certificate issuance authority.
6. **“A short CA password is fine since it's only used for 7 days.”** False: the CA signing key can still be abused and cracked offline if the file is copied.
7. **“Whatever SAN the CSR requested, the CA must sign it.”** False: the CA must verify and decide which identities to issue.
8. **“Set `CA=true` on the leaf so it can be reused in many places.”** False: breaks the CA/end-entity boundary.
9. **“Having `cRLSign` means CRL checking happens automatically.”** False: requires publishing and status-checking infrastructure.
10. **“The PKIX demo disables revocation, so disable it in production too.”** False: the demo runs no CRL/OCSP; production must follow policy.
11. **“Using trust-all fixes `SSLHandshakeException` quickly without hurting security.”** False: removes identity/trust verification.
12. **“A `HostnameVerifier` returning true everywhere is reasonable for `localhost`.”** False: easily leaks into other runtimes and removes protection.
13. **“Importing `lab-root.pem` into `cacerts` affects only my app.”** False: can affect every app sharing that trust store.
14. **“The CA private key can be copied to the server since it's in the same test group.”** False: compromising the server gives attackers certificate-issuance power.
15. **“Using a 30-day root validity guarantees the root is safe.”** False: expiration does not mitigate root key compromise prior to expiry.
16. **“The filename `demo.p12` makes it obvious it's for testing, so it won't be misused.”** False: enforce isolation with IAM, deployment controls, and trust policies.
17. **“The leaf reply was imported, so no need to inspect the chain.”** False: verify alias, chain, issuer, SAN, EKU, and signatures.
18. **“One machine trusts the lab CA, so another machine trusts it too.”** False: trust configuration is per runtime/system/profile.
19. **“The same lab root can sign certs for production domains to test staging.”** False: issue under test namespaces and approved processes.
20. **“Once the certificate expires, there's no need to remove the trusted root.”** False: a trusted root can still validate other certificates if still valid, or be handled differently across clients.

## 11. Self-Check Exercises

**Question 1.** Does a self-signed root CA automatically become a trusted root on every Java runtime?

**Answer:** No. Clients must be authorized to trust an origin-verified trust anchor; self-signing does not create trust on its own.

**Question 2.** Why must a lab truststore be kept separate from `cacerts` or production truststores?

**Answer:** Because adding a lab root to a production truststore lets production clients trust certs issued by the lab CA under verification rules, creating an endpoint impersonation surface.

**Question 3.** How does a lab CA differ from a server leaf in `BasicConstraints` and `KeyUsage`?

**Answer:** The CA needs `CA=true` and appropriate `keyCertSign`; the leaf needs `CA=false` and key usage/EKU suited for a TLS server, with no CA certificate-signing authority.

**Question 4.** In this lesson, why can the root with `pathLen=0` still sign a leaf?

**Answer:** `pathLen` caps the number of non-self-issued intermediate CAs following that CA in a certification path; it does not prevent issuing end-entity certificates.

**Question 5.** A server certificate has `CN=localhost` yet its SAN contains only another address; should HTTPS to `localhost` be accepted?

**Answer:** No under modern hostname validation policies. It must have an appropriate `DNS:localhost` SAN, and trust/path must also pass.

**Question 6.** Does a CSR containing a real domain's SAN prove ownership of that domain?

**Answer:** No. The CSR signature only proves possession of the CSR's private key; the CA must verify domain/name ownership before issuance.

**Question 7.** `keytool` creates a server keystore with a self-signed certificate. When does it have a root→leaf chain?

**Answer:** Once the CA signs the CSR, the root public certificate is imported for chain building, and the certificate reply is imported into the exact private-key alias, followed by verifying the chain.

**Question 8.** In Java code, what does placing the lab root into `TrustAnchor` signify?

**Answer:** The application explicitly trusts that CA; the PKIX validator checks the path up to that anchor. Never use an arbitrary root fetched from the network without verifying its identity/fingerprint.

**Question 9.** The lab has no CRL/OCSP so it calls `setRevocationEnabled(false)`. Does this prove revocation is safe to skip?

**Answer:** No. That is an intentional lab limitation; production must operate revocation per policy and evaluate behavior when status services fail.

**Question 10.** If the CA private key is compromised, is changing the store password enough?

**Answer:** No. The attacker may already hold the private key and issue certificates. You must stop trusting the compromised CA, issue a new CA/leaves, and assess the incident.

**Question 11.** Once you have `lab-root.pem`, can the client use it as an identity keystore?

**Answer:** No. A public PEM root certificate has no private key; client identity (for mTLS) requires its own private key and cert chain.

**Question 12.** An HTTPS client connects to `localhost` with the wrong truststore; should you disable certificate verification?

**Answer:** No. Load the right lab truststore, verify the root fingerprint, chain, SAN, and TLS policy; fail closed if authentication fails.

## 12. Official Documentation and Standards

- [Oracle Java SE 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): `genkeypair`, `certreq`, `gencert`, `importcert`, `exportcert`, BC/KU/EKU/SAN extensions, and chain import ordering.
- [Oracle Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): keystore/truststore file API, PKCS12, aliases, certificate chains.
- [Oracle Java SE 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): `TrustAnchor` and certification path validation parameters.
- [Oracle Java SE 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): building and validating certification paths per PKIX.
- [Oracle Java SE 17 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): trust anchor mechanics, PKIX, and extensions/checkers.
- [Oracle Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): `KeyManager`/`TrustManager`, TLS, and truststores.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html): BasicConstraints, KeyUsage, EKU, SAN, path validation, revocation, and trust model.

## Conclusion

**Setting up a test CA is easy in terms of `keytool` commands, yet deciding where that CA is trusted is the core security matter.** A proper lab setup comprises: a root CA with `CA=true` and a closely guarded private key; a leaf with `CA=false`, `SAN=localhost`, `EKU=serverAuth` signed from a CSR; a server keystore holding **the leaf private key + certificate chain**; and a client with an **isolated PKCS12 truststore** holding only the fingerprint-verified public root certificate. Java can validate the path via PKIX; HTTPS must still verify hostname, purpose, and TLS conditions.

**Strictly keep test CAs, truststores, and keys out of production, never edit system `cacerts` to silence errors, never disable TLS verification, and never treat a lab root as a general trust anchor.** Moving to production requires approved PKI workflows, verified identities, proper certificate/key custody, and lifecycle, audit, and revocation management.
