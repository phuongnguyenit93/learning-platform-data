# 13.8 PKCS#10 CSRs, CA Replies, and Certificate Chains in the keytool Workflow

A Java application needing a real X.509 certificate for TLS, mTLS, or digital signing typically cannot stop at `keytool -genkeypair`. That command can create an initial **private key + self-signed certificate** in a KeyStore, yet a certificate trusted by another party must go through a **Certificate Signing Request (CSR, PKCS#10)**, **CA vetting and signing**, receiving a **certificate reply**, and installing the proper **certificate chain** back into the alias holding the original private key.

This lesson walks through the complete workflow from **key in PKCS#12 → PKCS#10 CSR → CA signing → trust anchor → importing the reply into the same alias → verifying the chain with Java 17+**, while explaining chains with intermediate CAs, SANs, key usage, truststores, error handling, and production governance. The example uses a **lab-only self-created CA**, never masquerading as a public certificate trusted by browsers.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain what a **PKCS#10 CSR** contains, what it does not contain, and why a CSR has a signature yet is **not yet a CA-signed certificate**.
2. Distinguish private key, public key, CSR, **CA-issued leaf certificate**, intermediate certificates, root trust anchor, and certificate chain.
3. Use `keytool` to create a PKCS#12 identity, export a CSR, inspect CSR contents, generate a certificate reply from a demo CA, import the root, and install the reply into the **exact alias**.
4. Understand why the alias holding the `PrivateKeyEntry` must be preserved when replacing the self-signed certificate with the issued certificate.
5. Use Java 17+ to reload the `KeyStore`, verify the alias/chain, SAN, issuer relationship, public/private key match, and validate the path with **PKIX**.
6. Recognize the limitations of the example: demo CA, command-line passwords, PKIX revocation disabled **for demo only**, and a SAN check that does not replace a TLS hostname verifier.
7. Troubleshoot common errors: `Failed to establish chain from reply`, `Public keys in reply and keystore don't match`, importing the reply into the wrong alias, missing intermediates, or trusting the wrong CA.

## 2. Objects in a Certificate Issuance Workflow

| Object | Core content | Sensitivity / typical location |
| --- | --- | --- |
| **Private key** | RSA/EC/... private key for signing or private-key operations per algorithm | **Secret**, stored in KeyStore/HSM/KMS; never sent to the CA |
| **Public key** | Public key corresponding to the private key | Included in CSR and leaf certificate |
| **PKCS#10 CSR** | Subject, SubjectPublicKeyInfo, attributes/extension requests, and **requester's signature** | Typically safe to send to CA; carries no private key |
| **CA-issued certificate** | X.509 certificate with subject info, public key, issuer, serial, validity, extensions, and **CA signature** | Public; trusted only after path and policy validation |
| **Intermediate certificate** | Subordinate CA certificate signed by an upper CA, usually with CA rights per constraints | Public; needed for path building |
| **Root CA / trust anchor** | Certificate or public-key trust anchor configured as trusted out-of-band | Public, yet **trust selection** must be policy-protected |
| **Certificate reply** | CA-issued leaf certificate, possibly bundled with intermediates/chain in various formats | Public; used to **replace the chain on the private-key alias** |
| **Identity keystore** | Store holding the private key together with its chain for proving identity | Protect carefully |
| **Truststore** | Store of trust anchors or policy-accepted CA/peer certs | Holds only public certs in typical models; control import sources |

**Three messages to remember:** (1) a CSR does not contain the private key; (2) the CA only signs a certificate after deciding to **authorize the subject/identifiers** per its policy; (3) receiving a certificate file **does not automatically make it trusted**.

### 2.1. Overall Diagram

~~~text
                         SERVER / APPLICANT
   +-----------------------------------------------------------+
   | KeyStore "app.p12"                                         |
   | alias "app-server": PrivateKeyEntry                         |
   |     private key  [KEEP SECRET]                             |
   |     temporary self-signed cert                             |
   +-----------------------------------------------------------+
               | keytool -certreq  (signs CSR with private key)
               v
          PKCS#10 CSR ----- send CSR, never private key --------> CA
                                                               |
                                          check name/domain/policy
                                          vet CSR + sign X.509 leaf
                                                               |
               <---------- leaf + chain reply (when present) ---+
               |
               | import CA certificate from an AUTHENTICATED source
               | import signed leaf into the same alias "app-server"
               v
   +-----------------------------------------------------------+
   | KeyStore "app.p12"                                         |
   | alias "app-server": PrivateKeyEntry                         |
   |     same private key                                       |
   |     chain[0] = CA-issued leaf                              |
   |     chain[1] = intermediate CA or root (depending on path) |
   |     ...                                                     |
   | alias "demo-ca": TrustedCertificateEntry (demo CA)         |
   +-----------------------------------------------------------+
               |
               v
        Java loads + checks PKIX/chain; JSSE when using TLS
~~~

This diagram illustrates a simulated case. In production, the CA, identity store, and truststore typically have separate roles and access controls; the private key may be **non-exportable** from an HSM. The root trust anchor is usually configured on the **verifier (relying party)** side—merely importing it into the server's keystore does not make clients trust it.

## 3. What Exactly Is a PKCS#10 CSR?

**PKCS#10** (RFC 2986) defines the **CertificationRequest** structure. Simply put, a CSR contains:

~~~text
CertificationRequest
  certificationRequestInfo
    version
    subject (X.500 Distinguished Name)
    subjectPublicKeyInfo (public key + algorithm)
    attributes (may contain extensionRequest)
  signatureAlgorithm
  signature (signed with the private key matching the CSR's public key)
~~~

The signature on a CSR is **proof that the requester possesses the corresponding private key** when creating the request (proof of possession in the signature sense); it **does not prove** the requester owns the claimed hostname/domain, organization, or assets. Vetting identity/domain/IP and enforcing issuance policy are the **CA**'s responsibility.

Key facts:

- A CSR **contains no private key**. Never send `.p12`, key files, passwords, or token/HSM secrets to a CA just because it asks for a CSR.
- A CSR **is not an X.509 certificate with a trusted issuer**. The applicant's signature in a CSR differs from the CA's signature on the issued certificate.
- `Subject DN` and attributes such as `extensionRequest` can include **requested SAN, KeyUsage, and ExtendedKeyUsage**; the CA can accept, modify, reject, or omit them per policy.
- For modern HTTPS, **DNS names/IPs must be in the leaf's Subject Alternative Name (SAN)** per client/standard rules. Setting a nice `CN` without an appropriate SAN is insufficient.
- CSRs are typically **DER (binary ASN.1)** or **PEM** labeled `-----BEGIN CERTIFICATE REQUEST-----` (Base64 text wrapping DER). PEM is only a **representation**, not a different cryptographic request type.
- A CSR corresponds to one specific public key. To attach the CA response to **the private key in the existing alias**, the public key in the reply must match that key's public key.

### 3.1. How Does a CSR Differ from a Certificate?

| Comparison point | PKCS#10 CSR | Issued X.509 Certificate |
| --- | --- | --- |
| Signer | Holder of the **requesting private key** | **CA issuer** |
| Purpose | Requests a CA to issue a certificate for public key + subject | Binds public key to identity per CA policy |
| Has CA-assigned serial and validity | Not yet | Yes |
| Has CA issuer | Not in the sense of an issued certificate | Has issuer DN and CA signature |
| SAN/usage | Can be **extension requests** | Actual extensions the CA **decided to issue** |
| Usable immediately as TLS server cert | **No** | Possible, after chain, policy, key, validity, hostname, and trust validation |
| Contains private key | **No** | **No**; private key stays outside both artifacts |

Never assume a file with `CERTIFICATE` in its name contains a private key. Typically `.crt`/`.cer` carry public certificates; `.csr` carries a request; `.p12` may carry a private key, certificate chain, and other entries depending on how it was packaged. **Never determine origin solely by file extension.**

## 4. Chain of Trust: Leaf, Intermediate CA, Root

In a typical hierarchical PKI:

~~~text
Root CA (trust anchor configured by the verifier)
    |
    | signs
    v
Intermediate CA (basicConstraints CA=true, keyCertSign)
    |
    | signs
    v
Leaf certificate (app.example.test, DNS SAN, EKU serverAuth)
    |
    | leaf's public key must match the private key in app.p12
    v
TLS server/application uses private key to prove possession
~~~

A valid certificate path generally requires:

1. The leaf signature verifies using the intermediate CA's public key (or root if there is no intermediate).
2. Intermediate signatures (and any higher CAs) lead to a **pre-selected trust anchor**.
3. Validity period, policy-compliant algorithms/key sizes, `basicConstraints`, `keyUsage`, `pathLenConstraint`, and related constraints pass.
4. **Intended usage** checks pass: e.g., a TLS server requires `ExtendedKeyUsage serverAuth` when EKU is present; the leaf has a SAN matching the hostname the client actually connects to.
5. Revocation status/policy (CRL/OCSP or system mechanism) passes when required; never assume all CAs or applications handle this identically.

**A trust anchor does not “prove itself trusted” via self-signature.** A root may be self-signed, yet what makes it trusted is placing its public key/certificate into the trust anchors set via a **trusted distribution process and policy**. An attacker can self-sign certificates too.

### 4.1. Order in a Certificate Chain

In `KeyStore.PrivateKeyEntry`, the chain is typically structured as:

~~~text
chain[0] = End-entity / leaf certificate for the private key
chain[1] = Issuing intermediate CA (if any), or root (if root signed directly)
chain[2] = Upper CA, if any ...
~~~

**Never put the root at `chain[0]`** and never confuse a trust anchor alias with a private-key alias. For TLS, the server typically sends **leaf and intermediate(s)**; the root usually **need not be sent** since the client already has the root in its truststore, depending on protocol/implementation. If the server sends only the leaf without intermediates and the client cannot fetch intermediates, path building may fail.

**In this lesson's example:** the demo root signs the leaf directly → the chain in the KeyStore has 2 elements: **leaf → root**. Production usually includes intermediates, making the count 3 or more.

### 4.2. Where Does Chain Trust Come From?

`keytool -importcert` can **build a certificate chain from known CA certificates** or from a chain included in the reply. However, successful import and a CA-signed reply do not mean the certificate will be trusted by **every public client**. Each relying party must have the appropriate trust anchor in its own truststore/policy.

Never import a “CA root” from an email or unverified network channel and treat it as independent evidence: an attacker can send a **matching fake root and fake reply**. In the local lab example, you created the CA yourself so you know its origin; production must verify certificate fingerprints, CA tools, and independent trust processes.

## 5. KeyStore and Aliases in the CSR → Reply Flow

In the JDK, the initial key-pair generation command creates a **`PrivateKeyEntry`** in PKCS#12:

~~~text
app.p12:
  alias = app-server
  PrivateKeyEntry
    private key = RSA private key
    certificate chain = self-signed placeholder (when newly created)
~~~

Once the CSR is signed, the right step is to **install the reply on the `app-server` alias that holds the private key**, replacing **the certificate chain** while **keeping the original private key**. Never generate a new key pair just to import the reply, or you will have a public/private key mismatch.

| Alias / command | What happens |
| --- | --- |
| `-genkeypair -alias app-server` | Creates a `PrivateKeyEntry` with private key and initial self-signed certificate |
| `-certreq -alias app-server` | Creates a CSR signed by the private key of **the same alias** |
| `-importcert -alias demo-ca -file ca.crt` | On a new CA alias, adds a `TrustedCertificateEntry` holding the CA cert (demo) |
| `-importcert -alias app-server -file app-issued.crt` | Because `app-server` is already a key entry, treats the file as a **certificate reply**, verifies key match, and replaces the chain |
| `-list -v -alias app-server` | Inspects entry type, chain length, leaf subject, issuer, SAN |
| `-list -v -alias demo-ca` | Inspects the trusted certificate entry; holds no private key |

**Note:** If you import the leaf certificate into a brand **new** alias instead of the alias holding the private key, the tool creates a `TrustedCertificateEntry` rather than **installing the leaf onto the `PrivateKeyEntry`**. When a TLS server needs both the private key and chain, that is a configuration bug.

### 5.1. Store Password and Key Password

- `-storepass`: password for opening/saving the KeyStore per provider.
- `-keypass`: password protecting the private key entry when supported by the provider/store type.
- Some PKCS12 implementations require the key password to **match the store password**; the demo uses the same value `changeit-demo`.
- Password errors can surface when `-certreq` reads the private key or `-importcert` updates the chain, not just on `-list`.

In production, **never put passwords into terminal history, process listings, CI logs, or source code**. This lab intentionally uses a literal so it can be run repeatedly in an isolated test directory. Real systems use secret managers/callbacks, file/HSM permissions, and proper rotation policies.

## 6. End-to-End Practice with `keytool`: Creating a Demo CA and Issuing a CSR

All commands below were tested on **JDK 17+ in an empty temporary directory**. Run each command in a **fresh practice directory**; never run in a directory containing production keystores, as filenames are reused.

Scenario: Create CA `demo-ca`, create server identity `app-server` for DNS `app.example.test`, export a CSR and obtain a leaf cert signed by the demo CA, import the CA and reply. This is a **practice lab**, not a CA system with real domain-vetting procedures.

### Step 1 — Create a Self-Signed Root CA for the Lab

~~~bash
keytool -genkeypair -alias demo-ca -keyalg RSA -keysize 2048 -dname "CN=Training Demo Root,O=Learning,C=VN" -validity 365 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore ca.p12 -storetype PKCS12 -storepass changeit-demo -keypass changeit-demo -noprompt
~~~

- `-genkeypair` generates a private/public key pair and an initial self-signed certificate.
- `-ext "bc=ca:true"` declares `BasicConstraints CA=true`, required for the CA role.
- `-ext "ku=keyCertSign,cRLSign"` allocates `KeyUsage` for signing certificates and CRLs.
- `-dname` is the Subject DN of **the CA**, not the server.
- A 2048-bit RSA key and 365-day validity are for demo only; production CAs must follow dedicated standards, policies, private-key custody, online/offline protection, and lifetimes.

**Never use the demo `ca.p12` as a production CA**: the test CA private key is protected only by a sample password; a real CA needs issuance policies, audits, role separation, backups, and typically an HSM.

### Step 2 — Export the CA's Public Certificate

~~~bash
keytool -exportcert -alias demo-ca -keystore ca.p12 -storepass changeit-demo -rfc -file ca.crt
~~~

The file `ca.crt` is a **public certificate** without a private key. `-rfc` exports PEM format, easy to transfer and inspect. Check certificate details if needed:

~~~bash
keytool -printcert -file ca.crt
~~~

In production, **you must verify the SHA-256 fingerprint / CA distribution source via an authenticated channel** before trusting a certificate, rather than trusting it simply because a file is named `ca.crt`.

### Step 3 — Create a PKCS12 Identity and Self-Signed Placeholder

~~~bash
keytool -genkeypair -alias app-server -keyalg RSA -keysize 2048 -dname "CN=app.example.test,O=Learning,C=VN" -validity 30 -ext "san=dns:app.example.test" -keystore app.p12 -storetype PKCS12 -storepass changeit-demo -keypass changeit-demo -noprompt
~~~

At this point alias `app-server` holds a **`PrivateKeyEntry`** and a temporary self-signed chain. That temporary certificate **is not the leaf signed by the demo CA**; it merely lets `keytool` store the initial identity/key. `CN` gives a sample name; real HTTPS/JSSE must verify **DNS SAN** per TLS standards and policies.

If you re-run `-genkeypair` on the same alias when it already exists, `keytool` may reject it or require alias handling; never delete an existing private key and generate a new one while waiting for a reply to an old CSR.

### Step 4 — Generate a PKCS#10 CSR from the Right Alias

~~~bash
keytool -certreq -alias app-server -file app.csr -rfc -keystore app.p12 -storepass changeit-demo -ext "san=dns:app.example.test" -ext "ku=digitalSignature,keyEncipherment" -ext "eku=serverAuth"
~~~

- `-certreq` signs the CSR with the private key in `app.p12` for alias `app-server`.
- `-file app.csr -rfc` writes the CSR in PEM format. Never confuse this file with the issuer-returned certificate.
- `-ext san=dns:app.example.test` requests a DNS SAN.
- `ku` requests **KeyUsage**, and `eku=serverAuth` requests **ExtendedKeyUsage** for a TLS server. The CA makes the final policy decision; permissions must never be granted just because the CSR asked for them.
- For TLS 1.3, `digitalSignature` is the key usage for the certificate key signing the handshake; `keyEncipherment` is included in the lab for broader RSA compatibility, which does not mean TLS 1.3 uses RSA key transport.

Inspect the CSR:

~~~bash
keytool -printcertreq -file app.csr -v
~~~

You will see the Subject, algorithm, public key, signature, and extension requests. Exact output depends on the JDK/provider and declared info; do not hard-code dynamic fingerprints in tests.

**Safety:** You can send the CSR to the CA because it contains no private key. However, the CSR still contains identity/hostname/organization details, so share it over the proper CA channel and avoid including unnecessary sensitive data.

### Step 5 — Demo CA Vets (Simulated) and Signs the Leaf Certificate

~~~bash
keytool -gencert -alias demo-ca -infile app.csr -outfile app-issued.crt -rfc -keystore ca.p12 -storepass changeit-demo -validity 30 -ext "san=dns:app.example.test" -ext "ku=digitalSignature,keyEncipherment" -ext "eku=serverAuth"
~~~

This command uses the **demo CA**'s private key to sign a certificate for the public key in the CSR.

**Decision point:** In the demo we explicitly have the CA issue the SAN via `-ext`. **A production CA must never blindly take self-declared SAN/Subject values from a CSR and sign unconditionally.** The CA must verify authorization for the domain/organization, select a certificate profile, validate the request, set serial, validity, and extensions, and record an audit trail per standards/policy.

`app-issued.crt` is the **CA-issued leaf certificate**, not a private key. In the demo the root CA signs the leaf directly, so there is no intermediate. With a real CA, the reply may be a standalone leaf, a **PKCS#7 chain**, or a certificate bundle with intermediate(s).

### Step 6 — Import the Demo Root CA as a Trusted Certificate Entry

~~~bash
keytool -importcert -alias demo-ca -file ca.crt -keystore app.p12 -storepass changeit-demo -noprompt
~~~

- `demo-ca` is a **new** alias, not `app-server`.
- Now `app.p12` stores a `TrustedCertificateEntry` for the demo root. Since the root was created **right inside the lab**, we can explicitly place it as the demo trust anchor.
- `-noprompt` skips interactive confirmation; **never use it to auto-trust unverified CAs** in production.
- Before importing a real CA certificate, verify its fingerprint/source over a trusted channel and set proper read/write permissions.

Why import the CA before the reply? `keytool` needs issuer chain and trust information to build/verify the certificate reply's path. In the lab we only have root→leaf, so the root suffices for a 2-element chain. With intermediates, you may need to import intermediate certificates or supply the full chain in a supported format; verify the chain after installation.

### Step 7 — Install the Certificate Reply into **the Same Private-Key Alias**

~~~bash
keytool -importcert -alias app-server -file app-issued.crt -keystore app.p12 -storepass changeit-demo -noprompt
~~~

This is the most critical step:

1. `keytool` looks up the **`PrivateKeyEntry`** with alias `app-server`.
2. It verifies that the public key in the certificate reply matches the existing private key per provider capabilities.
3. It checks the issuer path/certificates needed to install the reply, then replaces the certificate chain of **that exact private-key entry**.
4. **The private key remains under alias `app-server`**, not a new trusted certificate alias.

On success, `keytool`'s lab output states that the certificate reply was installed in the KeyStore.

**Do not make this mistake:**

~~~bash
# WRONG FOR THE PURPOSE: a new alias does not attach to the "app-server" private key.
keytool -importcert -alias issued-copy -file app-issued.crt -keystore app.p12 -storepass changeit-demo -noprompt
~~~

This is solely a **comparison command illustrating a logic bug**; do not run it in the lab. Alias `issued-copy` has no private key, so it does not update `app-server`'s chain; it may create a certificate-only entry or produce provider-specific behavior without forming a valid identity.

### Step 8 — Inspect the KeyStore After Importing the Reply

~~~bash
keytool -list -v -alias app-server -keystore app.p12 -storetype PKCS12 -storepass changeit-demo
keytool -list -v -alias demo-ca -keystore app.p12 -storetype PKCS12 -storepass changeit-demo
~~~

For the lab you just created:

- `app-server` must be a **`PrivateKeyEntry`**, certificate chain length **2**.
- `chain[0]` is the leaf issued for `app.example.test` with SAN `DNSName: app.example.test`.
- `chain[1]` is the demo root CA `Training Demo Root`.
- `demo-ca` is a trusted certificate entry holding only the certificate; it contains no CA private key because it was the **exported public CA certificate**.
- The **demo CA**'s private key remains solely in **`ca.p12`**, never copied into `app.p12`.

If actual values differ, do not ignore them. Verify the right files, aliases, issuer, SAN, chain, and private/public keys before deploying to an application.

## 7. Java 17+: Reloading the Chain and Checking SAN, Signature, and PKIX

The following is a **standalone Java 17+ program**, run after **the eight `keytool` steps in Section 6** in the same directory containing `app.p12`. No external libraries beyond the JDK are needed. It runs useful illustrative checks without printing private keys or passwords.

Save with the exact name **`CsrChainDemo.java`**:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.List;
import java.util.Set;

public class CsrChainDemo {
    public static void main(String[] args) throws Exception {
        // Sample password ONLY for the lab. Production loads from a secret manager.
        char[] password = "changeit-demo".toCharArray();
        try {
            KeyStore store = KeyStore.getInstance("PKCS12");
            try (InputStream in =
                    Files.newInputStream(Path.of("app.p12"))) {
                store.load(in, password);
            }

            String alias = "app-server";
            String caAlias = "demo-ca";
            boolean privateEntry = store.entryInstanceOf(
                    alias, KeyStore.PrivateKeyEntry.class);
            boolean caTrusted = store.entryInstanceOf(
                    caAlias, KeyStore.TrustedCertificateEntry.class);
            KeyStore.PrivateKeyEntry entry =
                    (KeyStore.PrivateKeyEntry) store.getEntry(
                            alias, new KeyStore.PasswordProtection(password));

            Certificate[] chain = entry.getCertificateChain();
            X509Certificate leaf = (X509Certificate) chain[0];
            X509Certificate root =
                    (X509Certificate) store.getCertificate(caAlias);

            boolean issuerMatches = leaf.getIssuerX500Principal()
                    .equals(root.getSubjectX500Principal());
            boolean orderMatches = chain.length == 2
                    && MessageDigest.isEqual(chain[1].getEncoded(),
                            root.getEncoded());
            boolean sanContainsHost = leaf.getSubjectAlternativeNames()
                    .stream().anyMatch(field ->
                            field.get(0).equals(2)
                            && "app.example.test".equals(field.get(1)));

            // Prove the private key in the entry matches the leaf certificate's
            // public key by signing and verifying dummy data.
            byte[] message =
                    "csr-chain-proof".getBytes(StandardCharsets.UTF_8);
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(entry.getPrivateKey());
            signer.update(message);
            byte[] signed = signer.sign();
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(leaf.getPublicKey());
            verifier.update(message);
            boolean keyMatchesCert = verifier.verify(signed);

            leaf.checkValidity();
            root.checkValidity();

            // CertPath excludes the trust anchor from the list of certs to check.
            // Here the lab root signs the leaf directly => path has only the leaf.
            CertPath path = CertificateFactory.getInstance("X.509")
                    .generateCertPath(List.of(leaf));
            PKIXParameters parameters = new PKIXParameters(
                    Set.of(new TrustAnchor(root, null)));
            parameters.setRevocationEnabled(false); // DEMO ONLY!
            CertPathValidator.getInstance("PKIX")
                    .validate(path, parameters);

            System.out.println("KeyStore type        = " + store.getType());
            System.out.println("PrivateKeyEntry      = " + privateEntry);
            System.out.println("Trusted CA entry     = " + caTrusted);
            System.out.println("Chain length         = " + chain.length);
            System.out.println("Issuer matches CA    = " + issuerMatches);
            System.out.println("Chain order correct  = " + orderMatches);
            System.out.println("Leaf SAN DNS correct = " + sanContainsHost);
            System.out.println("Private matches cert = " + keyMatchesCert);
            System.out.println("PKIX path valid      = true");
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac CsrChainDemo.java
java CsrChainDemo
~~~

**Verified output** after running the complete `keytool` sequence (on a fresh PKCS12):

~~~text
KeyStore type        = PKCS12
PrivateKeyEntry      = true
Trusted CA entry     = true
Chain length         = 2
Issuer matches CA    = true
Chain order correct  = true
Leaf SAN DNS correct = true
Private matches cert = true
PKIX path valid      = true
~~~

### 7.1. Exact Explanation of Each Check

- **`PrivateKeyEntry = true`:** Alias `app-server` holds the private key and certificate chain; the reply was not imported into a trusted certificate-only alias.
- **`Trusted CA entry = true`:** Alias `demo-ca` holds the certificate imported as a trust entry; it **did not import the CA's private key** from `ca.p12` into `app.p12`.
- **`Chain length = 2`:** The demo has the root signing the leaf directly; production chains with intermediates are typically longer. This check is **a fixed expectation specific to this lab**.
- **`Issuer matches CA = true`:** The root's Subject matches the leaf's Issuer DN; this is only a **DN name** comparison, **not a substitute for signature verification**. Any attacker can generate a certificate with the same DN.
- **`Chain order correct = true`:** The bytes of `chain[1]` match the root certificate retrieved from alias `demo-ca` in the lab.
- **`Leaf SAN DNS correct = true`:** Checks that the X.509 SAN contains the sample DNS name. A string lookup in SAN **does not replace a full HTTPS hostname verification algorithm**, which also governs wildcards, IDNA, IPs, matching standards, and deriving the target host.
- **`Private matches cert = true`:** Uses the private key in `app-server` to sign a test message and the leaf's public key to verify it. This is a more meaningful check than comparing aliases or Subject DNs.
- **`PKIX path valid = true`:** `CertPathValidator("PKIX")` validates the leaf path → **the demo root explicitly selected as the trust anchor**. The example does not auto-trust every CA on the machine, does not verify client hostnames, and **intentionally disabled revocation** for the lab only.

**Never turn lab code into a production TLS trust manager**: a real trusted certificate chain requires policies, client-side hostname verification, revocation checking when mandated, certificate transparency/pinning per threat model, CA identity protection, and trustworthy anchor selection. The demo program does not open HTTPS, perform an mTLS handshake, or prove this CA is recognized by public browsers.

### 7.2. Why Does the PKIX CertPath Contain Only the Leaf in the Demo?

In `PKIXParameters`, `TrustAnchor` represents **the out-of-path trust point**. Since the root is already specified as the trust anchor, when the root signs the leaf directly, the certificate list to validate is `List.of(leaf)`, without adding the root to the list.

When there is an intermediate:

~~~java
// Illustrative snippet; intermediate must be obtained/verified from a trusted source
// and root must be an authorized TrustAnchor.
CertPath path = CertificateFactory.getInstance("X.509")
        .generateCertPath(List.of(leaf, intermediate));
~~~

The path order is **leaf → intermediate**, while the root sits in the `TrustAnchor` set. This snippet is not a standalone program because `leaf` and `intermediate` must be loaded first. Whether the path validator succeeds depends on extensions, signatures, basic constraints, trust anchor, validity, and policy.

## 8. With Intermediate CAs: Longer Chains and How to Import

In production, the root private key typically does not sign leaves directly. CAs organize a hierarchy:

~~~text
Trust anchor: Example Root CA   [trusted on client/truststore]
      |
      v
Issuing Intermediate CA        [CA=true, keyCertSign; signed by root]
      |
      v
app.example.test leaf          [CA=false, SAN, serverAuth; signed by intermediate]
~~~

**The difference from the lab** is that **the CA signing the leaf CSR** is usually an intermediate, not the root. To import properly:

1. Identify the identity alias that generated the CSR (e.g., `app-server`) and verify that the leaf reply's public key **matches the existing private key**.
2. Obtain the **leaf certificate** and the full **intermediate chain** provided by the CA via the proper channel.
3. Verify the root trust anchor from a trusted source; store it in the appropriate truststore and/or import it where `keytool` needs it to build the chain per provider.
4. Install intermediate certificates according to the rules and formats supported by `keytool`/the provider (or supply a recognized chain/PKCS#7 reply); **do not assume a leaf-only file is always enough**.
5. Import the reply into **the original private-key alias**. Then verify chain length and order: leaf → intermediate → ... root (if root is stored in the chain).
6. Verify issuer/subject linkage, signatures, CA basic constraints, key usage, path length, leaf SAN/EKU, and path to a trust anchor. Never merely count chain length.

**Important:** `KeyStore.getCertificateChain` may contain the root or only the issuing certificates depending on provider/installation method. A TLS server **usually does not need to send the root**; the client finds the root via its truststore, not because the root was in the reply. Never write production logic that checks only `chain.length == 3` while skipping signature and trust anchor verification.

### 8.1. CA Bundles and PKCS#7

A CA may return:

| File | Typical content | Required handling |
| --- | --- | --- |
| `app-issued.crt` / `.cer` | A single X.509 leaf, PEM or DER | Install into the private-key alias once the issuer chain can be built |
| `intermediate.crt` | Intermediate CA X.509 cert | Feed into chain building/trust workflow as required; **do not blindly treat intermediates as trusted roots** |
| `root.crt` | Root public certificate | Set as a trust anchor only after out-of-band verification |
| `.p7b` / PKCS#7 | Certificate set or signed-data certificate chain, typically **no** private key | May be used as a reply by `keytool -importcert` depending on content/provider |
| `.p12` / PKCS#12 | May contain private key and chain or only certificates, depending on export | **Do not blindly import over an identity** if keeping the original private key; inspect contents/type first |

PEM has the form:

~~~text
-----BEGIN CERTIFICATE-----
... Base64 X.509 DER ...
-----END CERTIFICATE-----
~~~

A PEM CSR has a different label:

~~~text
-----BEGIN CERTIFICATE REQUEST-----
... Base64 PKCS#10 DER ...
-----END CERTIFICATE REQUEST-----
~~~

**Never send a PKCS12 containing a private key to a CA when the workflow only asks for a CSR.** Never concatenate certificates in the wrong order and assume the new file has a valid chain. Tools vary in bundle import support; verify `keytool -list -v` output and run real validation.

### 8.2. An Intermediate Is Not Always a Trust Anchor

An intermediate certificate with `CA=true` and a root signature **is not automatically trusted** merely because the server sent it. It is evidence for building a **certificate path**, while the final trust anchor must reside in the verifier's trust policy. If an application blindly adds every received intermediate to its root truststore, it can unintentionally widen trust scope.

`BasicConstraints CA=true` only states that a certificate **is declared to have a CA role**; certifying authority must come from **a valid signature chain and an accepted trust anchor**. Never equate `CA=true` with “a CA trusted by every machine”.

## 9. X.509 Extensions in CSRs and Certificate Replies

A CSR can **request**; the CA **approves/issues**. Each extension has distinct cryptographic and operational semantics:

| Extension | On a TLS server leaf | On a root/intermediate CA |
| --- | --- | --- |
| **Subject Alternative Name (SAN)** | Endpoint DNS/IP; client performs matching per policy | May involve name constraints; not for assigning leaf hostnames |
| **BasicConstraints** | Usually `CA=false` or not a CA | Must be `CA=true` to certify CAs and satisfy path constraints |
| **KeyUsage** | E.g., `digitalSignature` for signature-based TLS; `keyEncipherment` only when profile/protocol needs it | `keyCertSign` for signing certificates, `cRLSign` if signing CRLs |
| **ExtendedKeyUsage (EKU)** | `serverAuth` for TLS server, `clientAuth` for mTLS client per purpose | Usually differs from leaf; depends on policy and path validation |
| **Subject Key Identifier / Authority Key Identifier** | Assists key/issuer lookup when building chains | Assists linking issuer/subject keys; does not replace signature checks |
| **Certificate Policies / NameConstraints** | Per CA/profile | Can restrict issued certificate namespaces or CA purposes |
| **CRL Distribution Points / AIA** | Hints where to check revocation/CA issuer | Assists chain building and revocation checks per implementation |

**Do not look only at CN:** Server certificate names must be verified via **SAN** matching the connected hostname, handling DNS/IP, wildcards, and IDNA per protocol. `CN=app.example.test` in the demo is neither the sole source nor sufficient for hostname validation.

**Do not rely on `-ext` in the CSR to assume the certificate got that extension.** After the CA signs, inspect **the actual issued leaf certificate** using:

~~~bash
keytool -printcert -file app-issued.crt -v
~~~

The CA may drop, edit, or override requested extensions. That is part of CA policy, not a PKCS#10 bug.

## 10. Is a CA Response “Trusted” Immediately Upon Receipt?

**No.** A certificate reply is the CA's output, yet the deploying party must verify multiple layers:

1. **Matches the request:** Public key in the leaf matches the private key that generated the CSR; private-key entry alias is right, no accidental key-pair swap.
2. **Right identity:** SAN/subject and usage purposes match the approved profile.
3. **Right issuer:** Leaf was issued by the expected CA; signature and chain validate to the chosen trust anchor.
4. **Right validity/constraints:** Validity period, basic constraints, key usages, EKU, signature algorithm, key size, policies.
5. **Right source and flow:** CA account, issuance protocol, fingerprint/serial/transaction details match appropriately.
6. **Right usage context:** Never use a `serverAuth` cert as a `clientAuth` cert if disallowed by policy; never treat a demo root as a public CA.
7. **Right operations:** KeyStore file and private key are protected, with controlled backup/rotation/rollback.

Seeing `keytool -importcert` report `Certificate reply was installed in keystore` proves **reply installation** succeeded per the tool and provider checks; it is **not a claim that every peer will trust the CA** or that TLS hostnames are valid.

**Attack example:** An attacker can send a self-signed `ca.crt` of their own and an `app-issued.crt` signed by them; if you import both without authenticating the source and have clients use that truststore, the path will validate **against the newly imported fake trust anchor**. That is why root trust must be distributed and verified over an independent channel.

## 11. Distinguishing Certificate Reply, Import Cert, and Import Keystore

In `keytool`, the exact same `-importcert` command has different semantics depending on **whether the alias already exists**:

~~~text
Alias does not yet exist + certificate
  → typically creates a TrustedCertificateEntry

Alias is already a PrivateKeyEntry + certificate reply
  → processes reply, installs/replaces the certificate chain for that private key
~~~

Meanwhile, `-importkeystore` imports **key entries or certificates from another keystore**; it is **not** a required step when you already hold the original private key in `app.p12` and only received a certificate reply from the CA.

**Never use `-importkeystore` blindly** to “install a CSR reply”. If the source file holds a different private key, you can overwrite the identity, change aliases, or misalign keys and chains. Inspect aliases/types on both source and destination, verify SHA-256 of public keys/certificates, and prepare backups and password policies before migrating.

### 11.1. Certificate Chain in a File vs. Chain in a Verification Path

- `getCertificateChain(alias)` is the list of certificates **stored** in the `PrivateKeyEntry`.
- A PKIX `CertPath` is the list of certificates for **the validator to check**, typically ending **before** your configured trust anchor.
- A TLS peer may receive the chain sent by the server, yet still requires its own trust anchor and hostname validation; a server cannot “send trust” merely by appending a root to the chain.
- A CA-issued certificate can be a valid leaf, yet missing intermediates/trust anchors on the system cause path building to fail; that does not mean the private key is corrupted.

## 12. Diagnosing `keytool` Errors by Stage

| Symptom | Possible cause | Check / resolution |
| --- | --- | --- |
| `-certreq` reports alias/private key not found | Wrong alias or only a `TrustedCertificateEntry` exists | Run `keytool -list -v -alias ...`; ensure a `PrivateKeyEntry` exists |
| `-certreq` cannot unlock private key | Wrong key/store password or provider issue | Identify proper type/entry protection; never log passwords |
| CSR lacks SAN | Requested extension omitted or different command/CA profile | Check `-printcertreq -v`, then inspect the leaf after CA signing |
| `Public keys in reply and keystore don't match` | Reply belongs to a different CSR/key pair, or private key was replaced | Compare key pairs/public keys, right file and alias; never regenerate keys while waiting |
| `Failed to establish chain from reply` | Missing CA issuer/intermediate, wrong chain, untrusted CA, or wrong input format | Verify CA certs from trusted source, import/supply chain in right format, check issuer signature |
| Reply imported yet `app-server` alias remains self-signed | Imported into wrong alias or wrong file | Check `-list -v -alias app-server`; re-import right reply into right alias if safe |
| `-importcert` created `TrustedCertificateEntry` instead of identity | Target alias had no `PrivateKeyEntry` | Use the original CSR-generating alias; never delete the private key |
| Wrong chain order or chain length 1 after reply | Missing CA chain / response had leaf only | Build chain, add intermediate, check provider |
| TLS peer reports certificate unknown | Trust anchor absent from peer's truststore or chain cannot be built | Supply intermediates, configure peer's truststore; never force trust-all |
| TLS reports hostname mismatch | SAN lacks the checked DNS/IP | Have CA re-issue with vetted SAN; never disable hostname verification |
| Certificate expired / not yet valid | Wrong validity window, clock skew, or unrenewed | Check `-printcert -v`, UTC time, and renewal schedule |
| `basicConstraints`/`keyCertSign` fails on issuer | Intermediate lacks CA authority or has wrong constraints | CA must issue with proper CA profile; never “edit certs” after signing |
| Key algorithm/signature rejected | TLS/PKIX policy or unsupported provider | Check algorithm suite, key size, JDK provider, issuance policy |
| PKCS12 fails to load | Wrong password, type, corrupt file, or incompatibility | Check file/type/password, backup, and provider; never rename extension to “convert format” |
| Cert works with one client but fails with another | Differing truststores/cert policies/revocation and intermediates | Check chain and trust per client; never extrapolate from one test |
| All commands succeed yet chain remains untrusted | Demo root CA not installed/checked by relying party | Distinguish local import from client trust policy |

**Safe investigation:** log alias, type, certificate fingerprint, issuer, SAN, chain length, error codes, and **timestamp/JDK version**, while **never logging passwords/private keys/tokens**. Inspect the actual CA response, not just the CSR. Limit printing certificate Subjects if they contain sensitive info outside logging scope.

## 13. Responsibilities of the CA and Certificate Users

**CA issuance** involves steps outside `keytool`:

- **Verify ownership/authorization for identifiers** per policy: DNS/domain, organization, device identity, or application principal.
- Apply issuance profile: subject, SAN, validity, serial, key algorithm, BasicConstraints, KU/EKU, and other extensions.
- Protect the CA private key and signing service, enforce approval separation, auditing, and issuance logging.
- Plan lifetimes, renewal, revocation, CRL/OCSP, and incident response.
- Provide **complete intermediate certificates** so deployers do not fetch them from untrusted sources.

**The applicant / application owner** is responsible for:

- Generating the private key in the right place and protecting it; keeping it non-exportable in HSM/KMS when required.
- Generating the CSR from the right key pair and verifying requested contents.
- Using official CA channels and verifying issued certificates match intended purpose.
- Importing the reply into the **original private-key alias**, maintaining the chain and proper TLS config.
- Restricting keystore read permissions; never sharing passwords/files unnecessarily.
- Tracking expiration/rotation and zero-downtime reload capabilities.

**The verifier (client/peer)** is responsible for:

- Trusting only proper roots/trust anchors per policy; never auto-trusting every server-sent certificate.
- Validating the PKIX path, appropriate hostname/subject identity, KU/EKU, validity, and required revocation/policies.
- Never using an “accept all” `TrustManager` or disabling hostname verification to work around chain import bugs.

A valid certificate chain only answers **which CAs certified this public key under trust policy**; it does not automatically prove the application is authorized to access resources. Authentication and authorization are two separate layers.

## 14. Securing the Issuance Workflow and Key Lifecycle

### 14.1. Never Expose the Private Key When Creating a CSR

Both CSRs and certificate replies can be stored/transferred as public artifacts per policy, whereas **the private key must not**. With `-certreq`, `keytool` reads the private key locally to sign the CSR. Never export `.p12` to the CA, never paste keys into tickets/chat, and never write passwords into audit logs.

This lesson's practice directory holds **`ca.p12`** (demo CA private key) and **`app.p12`** (demo server private key). Both files must be treated as **secret-bearing** even though password-protected. Delete lab copies properly when done; never commit them to Git or submit them to public systems.

### 14.2. Never Swap Certificates and Lose the Private Key

If you generated a CSR from key A and received a leaf for public key A, yet during deployment you generated key B and imported leaf A, connections signed with private B will not match certificate A. The fix is not skipping key-match checks; restore private A safely or generate a new CSR for B and request a new certificate from the CA.

In certificate rotation plans, you can use a **new versioned alias** and deploy blue/green before deleting the old one. For key rotation, generate a new key pair + new CSR, update the certificate chain, test the TLS handshake, and notify any pinning peers. If renewing with the same key pair, evaluate key reuse policies and key lifetimes.

### 14.3. Certificate Revocation and Time

A certificate may still be unexpired yet already revoked due to key compromise or organizational changes. `checkValidity()` checks only `NotBefore`/`NotAfter`, **not revocation**. `CertPathValidator` supports configurable revocation policies; the demo sets `setRevocationEnabled(false)` to avoid depending on a demo CA without CRL/OCSP. **In production, never copy `false` as a default security setting.**

When a TLS client must check certificate revocation, define the mechanism, hard/soft-fail policy, and CRL/OCSP sources per operational standards. Never assume `PKIX path valid = true` in the demo implies revocation, hostname, TLS chain negotiation, and all enterprise policies were checked.

### 14.4. SANs and Trust Decisions Can Change Over Time

Adding a new hostname or switching to mTLS may require a new certificate with different SANs/EKUs; never edit a signed leaf file by modifying PEM text. The CA's signature protects the certificate data, so **any field change requires re-issuance by the CA**.

The verifier's truststore also changes when root CAs are added, removed, rolled over, or updated. Maintain release/rollback plans for both **the server identity certificate** and **the client truststore**, rather than just re-running `-importcert`.

## 15. Real-World Scenarios

### 15.1. Spring Boot HTTPS Needing a CA-Issued Certificate

A dev team has `app.p12` with alias `app-server` holding the private key. After CSR and CA reply, import into the right alias, verify the chain, and configure `server.ssl.key-store`, `server.ssl.key-store-type`, password, and alias per the supported environment/framework. If the private key and certificate chain mismatch, the HTTPS handshake will fail even though the `.p12` file “opens”.

**Note:** specific Spring Boot properties vary by version; this lesson describes KeyStore/PKI concepts rather than prescribing property names for all versions.

### 15.2. mTLS Between Two Java Services

Service A needs both its own **identity `PrivateKeyEntry`** to present to B and a **truststore** holding the CA authorized to sign B's certificate. Service B has a symmetric setup with its own identity/CA authorization. Generate CSRs requesting **EKU `clientAuth` or `serverAuth`** per role; never reuse a `serverAuth`-only certificate across all mTLS flows without checking policy.

### 15.3. CA Sends an Intermediate Bundle, Server Imports Only the Leaf

The server still has the right private key, yet lacks the intermediate in the chain sent to clients. Some clients might find the intermediate via cache/AIA while others fail. Install the **proper intermediate chain** and test from a client with the appropriate trust anchor, rather than forcing clients to disable verification.

### 15.4. Importing a New Root Silences an Error Yet Creates Trust Risk

Someone receives `ca.crt` over an unverified channel, adds it to the truststore with `-noprompt`, and sees the certificate path validate. This could mean **trusting an attacker's CA**. Verify fingerprint/source over an independent channel and restrict trust anchors by policy.

### 15.5. Matching Subject DN, Yet Leaf Signed by a Different CA

Having an identical-looking `CN=Training Demo Root` or `Issuer DN` is not enough. Two CAs can share the same DN string while holding different public keys. The verifier must verify **signatures and the chain to the exact trust anchor**, not just compare name strings in certificates.

### 15.6. Using HSM/PKCS11 Instead of a PKCS12 File

Instead of storing the private key in `app.p12`, the private key resides in a token/HSM provider and may be non-exportable. The CSR is still signed by the private key inside the token; the certificate reply must be bound to the **exact key object/alias** per provider mechanics. `keytool` flags, token login/PINs, and chain import steps may differ, while the principles—**CSR sharing the public key with the private key, proper trust chain, and proper identity**—remain unchanged.

## 16. Self-Check Questions (with Answers)

**Question 1.** Does `keytool -certreq` write the private key into the CSR file?

**Answer:** No. The CSR contains the public key, subject, attributes/extension requests, and a signature created with the private key; the private key stays protected inside the KeyStore/HSM.

**Question 2.** A CSR has a valid signature; can it be used directly as a TLS server certificate?

**Answer:** No. The CSR signature proves the applicant's ability to sign with their key, **not a CA signature** and not authorization for a hostname. You need a CA-issued X.509 leaf + chain and proper trust/hostname verification.

**Question 3.** Why does a CA have the right to reject or modify SANs requested in a CSR?

**Answer:** SANs in a CSR are only **requests**. The CA must vet rights to the identifier and comply with issuance policy; otherwise anyone could request certificates for domains they do not own.

**Question 4.** When the CA returns `app-issued.crt` for a CSR generated from alias `app-server`, which alias should receive the reply?

**Answer:** **`app-server`**, the original `PrivateKeyEntry` alias. Importing into a new alias creates a certificate-only entry instead of pairing the issued certificate with the private key.

**Question 5.** The demo chain has two elements. What are they and in what order?

**Answer:** `chain[0]` is the leaf `app.example.test`; `chain[1]` is the root `demo-ca` that signed the leaf directly. With intermediates, the chain includes elements between the leaf and root.

**Question 6.** The demo root CA is self-signed. What makes the Java PKIX example accept it?

**Answer:** The program **explicitly selects the root as the `TrustAnchor`** in `PKIXParameters`. Self-signing or the root's name is not enough for operating systems or browsers to trust it.

**Question 7.** `-importcert` reports `Public keys in reply and keystore don't match`. Should you bypass the check and force-import?

**Answer:** No. Check whether the reply matches the right CSR and whether the private key was regenerated or the alias changed. Restore the right private key or generate a new CSR from the held key pair and ask the CA to re-issue.

**Question 8.** When a server sends leaf and intermediate, why might a client still report “untrusted certificate”?

**Answer:** The client lacks or disallows the corresponding trust anchor, or the certificate path/policy fails. Certificates sent by the server **do not grant trust to the client on their own**.

**Question 9.** Are `checkValidity()` and `Issuer DN matches` enough to guarantee a certificate is safe for HTTPS?

**Answer:** No. You need signatures/PKIX path, trust anchor, key usage/EKU, SAN hostname matching, revocation policy, and other TLS requirements. Subject/issuer DNs do not replace signature verification.

**Question 10.** A CA returns a `.p7b` file and a `.p12` file. Can both be treated as simple leaf certs and imported blindly?

**Answer:** No. PKCS#7 typically packages a certificate set/chain with no private key; PKCS12 may contain private keys and other entries. Inspect contents/types, preserve the original private key, and follow the proper import procedure.

**Question 11.** The demo Java code prints `PKIX path valid = true`; did that verify the server hostname and revocation?

**Answer:** Not yet. The demo checked a sample SAN separately and disabled revocation to run easily; actual hostname verification is handled by the HTTPS/TLS verifier per policy. Production must configure proper revocation and hostname checks.

**Question 12.** Why must you never put a root certificate downloaded over an unverified network into `TrustManagerFactory` just to silence TLS errors?

**Answer:** Because it could be an attacker's root. Trust anchors must be chosen via a trusted channel/distribution chain with fingerprint verification and change control; “errors gone” does not prove you are talking to the right peer.

## 17. Pre-Install Checklist for Certificate Replies

- [ ] CSR generated from **the exact private-key alias**; public key/subject/extension requests reviewed.
- [ ] Private key **never** sent to the CA; `.p12` file and passwords protected and never committed to source.
- [ ] Real CA vetted domain/identity; SAN, KU/EKU, validity, signature/profile verified in the **issued leaf**.
- [ ] Full intermediate chain obtained and checked for issuer/signature/`basicConstraints`/`keyCertSign`.
- [ ] Root trust anchor distributed from an **authenticated source**; never import unknown CAs with `-noprompt`.
- [ ] Reply installed into **the original `PrivateKeyEntry` alias**; not confused with a new `TrustedCertificateEntry` alias.
- [ ] `keytool -list -v` confirms alias, leaf/chain order/length, issuer/SAN, and entry type.
- [ ] If using Java, `KeyStore.getEntry` returns private key + chain; verify public/private key match and path per policy.
- [ ] The **verifier's** truststore contains authorized CAs, not inferred from server-sent certificates.
- [ ] HTTPS/mTLS still enforces hostname/identity, expiration, KU/EKU, revocation, and policies; no trust-all manager.
- [ ] Workflow has backup/rollback, certificate renewal schedule, rotation, and reload; never loses active keys.
- [ ] Never use demo passwords, demo CAs, or `setRevocationEnabled(false)` as production defaults.
- [ ] Use an isolated test directory; avoid re-running `-genkeypair`/`-importcert` uncontrollably on real keystores.

## 18. Summary

A **PKCS#10 CSR** is a **request signed by the applicant's private key**, containing the public key, identity, and proposed extensions; **it holds no private key and is not a CA-issued certificate**. After vetting, the **CA** signs the X.509 leaf (and supplies the intermediate chain when needed). In `keytool`, the certificate reply must be installed into **the exact `PrivateKeyEntry` alias that created the CSR**, preserving the private key and replacing the self-signed chain with the issued chain. Root trust anchors are verified from trusted sources, never auto-trusted because they are self-signed or sent by a server. Java 17+ can verify the chain, public/private key match, and PKIX path; yet **the PKIX demo does not replace HTTPS hostname verification and revocation policy**. That is the boundary between successfully installing a certificate and genuinely authenticating a connection.

**Foundational references:** PKCS#10 CSR: [RFC 2986](https://www.rfc-editor.org/rfc/rfc2986); X.509 PKIX certificate/path validation: [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280); JDK `keytool`: [Oracle keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html).
