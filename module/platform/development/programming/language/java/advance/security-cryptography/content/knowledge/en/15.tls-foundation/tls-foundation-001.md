# 15.1 TLS Combines Key Agreement, Certificates, Signatures, and Session Encryption

**TLS (Transport Layer Security)** protects data between two connection endpoints by **combining multiple cryptographic mechanisms, each solving a different problem**:

1. **Key agreement** (typically ECDHE in TLS 1.3) so both sides establish shared secret material without sending the session key directly over the wire.
2. **X.509 certificates and trust mechanisms (PKI)** so the receiver determines whether the peer's public key is properly bound to the expected identity.
3. **Handshake digital signature** to verify that the certified party actually controls the corresponding private key and to bind identity to the negotiated contents.
4. **Key derivation and Authenticated Encryption with Associated Data (AEAD)** to exchange application data with confidentiality and integrity, using separate session keys per send/receive direction.

No single mechanism completely replaces the others. **ECDHE alone does not authenticate the server. Successfully parsing an X.509 certificate does not mean it is trustworthy. A signature proves key control but is not used directly to encrypt every byte of data. AES-GCM protects records, but must have the right session keys and be bound to a secure handshake.**

This lesson focuses on **TLS 1.3** and compares it just enough with **TLS 1.2** to avoid confusing algorithms. At the time of this document, **RFC 9846 (07/2026)** is the new TLS 1.3 specification replacing RFC 8446; some documentation and JDK implementations still reference the historical RFC 8446. The concepts of handshake, CertificateVerify, Finished, HKDF, and AEAD are foundational to understand when reading Java JSSE.

## 1. What does TLS protect?

Suppose a Java application sends login credentials and business data to an HTTPS server. An attacker on the network can observe packets, alter data, or attempt to impersonate the server.

TLS is designed to provide:

| Property | Meaning | Primary mechanism |
| --- | --- | --- |
| **Confidentiality** | Network observers cannot read application plaintext. | Symmetric session keys + AEAD record encryption. |
| **Integrity** | Modified records are not accepted as valid data. | AEAD authentication tag, sequence/nonce, and transcript verification. |
| **Server authentication** | The client verifies it is talking to the server bearing the expected identity. | X.509 chain/trust/hostname + handshake signature + Finished. |
| **Optional client authentication** | The server can require the client to provide a certificate and prove possession of the private key. | mTLS: client Certificate/CertificateVerify, trust policy, Finished. |
| **Forward secrecy** (in appropriate key exchange modes) | Later compromise of the long-term signing key does not by itself allow decrypting previously recorded ECDHE sessions. | Ephemeral exchange keys, discarding ephemeral private keys; TLS 1.3 key schedule. |

**Boundary:** TLS does not by itself solve application authorization, SQL injection vulnerabilities, compromised accounts, malware-infected endpoints, plaintext logs on the server, or a user sending sensitive data to a server that is *correctly identified yet malicious*. TLS protects the **connection between endpoints** according to the configured identity/trust policy.

In particular, "having the HTTPS padlock" only means the connection was established according to the client's verification steps; the application still needs proper authorization, data handling, and monitoring.

## 2. Four cryptographic roles and where they appear

| Component | Input / target | Role in TLS 1.3 | **Not its role** |
| --- | --- | --- | --- |
| **(EC)DHE key agreement** | Ephemeral private/public key shares of both sides | Creates the input shared secret for the key schedule. | Does not authenticate hostname or CA on its own. |
| **X.509 certificate & chain** | Identity public key + issuer attestation | Helps bind the public key to an identity through PKI. | Does not directly encrypt application data. |
| **Handshake digital signature** | Certifying party's private key, handshake transcript | Proves control of the private key and prevents silent tampering during negotiation. | Does not individually sign each TLS record. |
| **HKDF key schedule** | DHE shared secret, transcript context, PSK when present | Produces handshake/application traffic secrets and keys per direction and phase. | Does not automatically verify CA trust without certificate/signature/trust. |
| **AEAD symmetric cipher** | Traffic key, nonce/sequence, plaintext/AAD | Encrypts and authenticates TLS records. | Does not inherently know server identity. |
| **Finished message** | Handshake traffic secret + transcript hash | A MAC proving both sides hold the appropriate secret and binding handshake integrity. | Not a digital signature using the certificate's private key. |

Three distinct **key** concepts should be distinguished:
- **Long-term private key** of the certificate (e.g., RSA or EC/Ed25519 signing the handshake): must be kept secret and protected across the certificate lifecycle.
- **Ephemeral private key** in ECDHE key exchange: used to compute the shared secret for the session; not the same as the certificate's private key.
- **Symmetric traffic keys** derived from the key schedule: actually used by AES-GCM or ChaCha20-Poly1305 to encrypt records. Each direction and phase has appropriate key material.

Reading and understanding TLS will go wrong immediately if you equate the public key in the certificate with the public key sent via `key_share`, or think the certificate's RSA key directly decrypts every HTTPS record.

## 3. Flow of a TLS 1.3 handshake with a server certificate

A **simplified diagram, following a 1-RTT handshake without HelloRetryRequest, without resumption, and without a client certificate**:

~~~text
             CLIENT                                        SERVER
               |                                              |
               | ClientHello                                  |
               | - supported_versions: TLS 1.3                |
               | - supported cipher suites                    |
               | - supported_groups / key_share (ECDHE)        |
               | - signature_algorithms, SNI, ALPN...          |
               |--------------------------------------------->|
               |                                              |
               | ServerHello                                  |
               | - selected version, cipher suite, key_share   |
               |<---------------------------------------------|
               |                                              |
               |  Both sides compute ECDHE shared secret       |
               |  and derive handshake traffic keys           |
               |                                              |
               |     {EncryptedExtensions}                     |
               |     {Certificate (server chain)}              |
               |     {CertificateVerify (digital signature)}   |
               |     {Finished (transcript MAC)}               |
               |<---------------------------------------------|
               |  [Messages inside { } are protected with      |
               |   handshake traffic keys]                    |
               |                                              |
               | Client verifies chain/identity, signature,    |
               | transcript/Finished; sends {Finished}        |
               |--------------------------------------------->|
               |                                              |
               |     Derive application traffic keys          |
               |                                              |
               |<==== application data: AEAD records ========>|
~~~

Key points:
1. `ClientHello` advertises versions, cipher suites, key agreement groups, key shares, and protocol extensions. `SNI` helps the server select a certificate by hostname; **SNI by itself does not authenticate the hostname**.
2. `ServerHello` selects the negotiated parameters. With a server certificate and (EC)DHE, each side can compute the corresponding shared secret without transmitting the raw shared secret.
3. TLS 1.3 uses **HKDF** to derive keys; the main authentication messages after `ServerHello` are encrypted with handshake traffic keys.
4. The server sends `Certificate` and `CertificateVerify`. The client verifies the certificate chain/trust, expected identity, signature over the handshake transcript, and `Finished`.
5. `Finished` is a MAC to confirm handshake integrity and key confirmation; the client also sends Finished (after client authentication messages if requested).
6. After the handshake, application data travels as **AEAD TLS records**, using traffic keys derived from the same handshake-bound process.

This does not describe every TLS 1.3 case: there are `HelloRetryRequest`, resumption via PSK, 0-RTT, client certificates, and post-handshake operations. TLS 1.3 can also use **PSK-only key establishment** without a DHE exchange; in that case, the forward secrecy properties differ from PSK+DHE.

**Do not mistakenly think "ServerHello is encrypted from the start"**: `ClientHello` and `ServerHello` start unencrypted by TLS traffic keys; the handshake encryption layer is established after the messages that establish the necessary secret. Encrypting authentication messages in TLS 1.3 is an important difference from the typical TLS 1.2 model.

## 4. Key agreement: why not send an AES key over the network?

### 4.1. ECDHE: using ephemeral public keys without transferring private keys

With ECDHE, each side generates an ephemeral key agreement pair and then exchanges its **public key share**:

~~~text
Client:
  ephemeral private a       public A = a*G  ---> Server

Server:
  ephemeral private b       public B = b*G  ---> Client

Client computes shared secret = ECDH(a, B)
Server computes shared secret = ECDH(b, A)

=> both sides hold the same secret material
=> an observer seeing only A and B should not deduce the secret
~~~

This is the classical ECDH explanatory model; with **X25519**, point computation and encoding rules have their own specifics. Do not use this diagram as a guide to roll a custom key exchange protocol.

Groups used in TLS 1.3 include **X25519**, **secp256r1 (P-256)**, and others per support/standards. Select appropriate groups through JSSE/protocol policy rather than accepting arbitrary groups dictated by one side.

**Key agreement does not authenticate the peer on its own.** A MITM attacker can establish their own key share with each endpoint if there is no authentication/transcript-binding mechanism. Therefore, the certificate, `CertificateVerify` signature, and `Finished` MAC are **core** components, not an add-on after ECDHE.

### 4.2. Forward secrecy is tied to ephemeral keys, not to the generic "TLS" label

When a session uses ephemeral (EC)DHE and ephemeral secrets are handled properly, subsequent compromise of the server's **certificate private key** does not by itself reveal the secret used to encrypt past sessions. This is a central idea of **forward secrecy**.

However:
- If the server is compromised while the session is active, an attacker can access live plaintext/secrets or tamper with the endpoint.
- If ephemeral private keys or traffic secrets are logged, dumped, or retained insecurely, protocol-level forward secrecy cannot save the application.
- Resumption and PSK-only modes have their own conditions; not every TLS establishment path guarantees the same level of forward secrecy.
- This property **does not mean** data already stored in a database or application logs becomes safe.

TLS 1.3 **has no static RSA key transport** like some older TLS 1.2 cipher suites. A server using an **RSA** certificate in TLS 1.3 can still use **X25519/ECDHE for key agreement**; the RSA private key is then used for handshake authentication/signing (according to the negotiated signature scheme), not to directly decrypt a premaster secret as in historical RSA key exchange.

## 5. Java 17 example: observing the X25519 operation in isolation

To identify the **key agreement** part of TLS, let us try a Java SE 17 example that **does not implement TLS**. This program only demonstrates that two X25519 key pairs compute the same shared secret; it **has no certificates, handshake signatures, HKDF-Expand-Label, transcript, or AEAD records**. Do not feed the 32-byte result straight into AES to invent a "lightweight TLS".

**File `X25519RolesDemo.java`:**

~~~java
import java.security.*;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public class X25519RolesDemo {
    static byte[] agreement(PrivateKey own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement kx = KeyAgreement.getInstance("X25519");
        kx.init(own);
        kx.doPhase(peer, true);
        return kx.generateSecret();
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator kpg = KeyPairGenerator.getInstance("X25519");
        kpg.initialize(NamedParameterSpec.X25519);

        KeyPair a = kpg.generateKeyPair();
        KeyPair b = kpg.generateKeyPair();

        byte[] fromA = agreement(a.getPrivate(), b.getPublic());
        byte[] fromB = agreement(b.getPrivate(), a.getPublic());

        System.out.println("Raw shared secret bytes: "
                + fromA.length);
        System.out.println("Agreement matches: "
                + Arrays.equals(fromA, fromB));

        Arrays.fill(fromA, (byte) 0);
        Arrays.fill(fromB, (byte) 0);
    }
}
~~~

Run:

~~~bash
javac X25519RolesDemo.java
java X25519RolesDemo
~~~

Verified output on Java 17 with X25519:

~~~text
Raw shared secret bytes: 32
Agreement matches: true
~~~

**Explanation:** `getInstance("X25519")` selects the key-agreement algorithm, `NamedParameterSpec.X25519` specifies key generation parameters, and `doPhase` combines our own private key with the peer's public key. `Arrays.equals` is used to verify that **both sides compute the same secret bytes**; in production do not log the shared secret and do not assume `Arrays.fill` guarantees erasing every copy of the secret.

**What is still missing to become TLS** is large and mandatory: key share identity authentication, transcript binding, standards-compliant HKDF, Finished verification, record sequence/nonce management, anti-replay, certificate trust, and downgrade protection. Therefore, **use JSSE to run TLS** instead of manually stitching JCA primitives together.

## 6. X.509 certificates: which key is trusted?

### 6.1. Certificates serve identity authentication, not traffic key generation

In a server-authenticated handshake, the `Certificate` message carries the certificate chain associated with the server's identity (typically leaf and intermediate). The leaf certificate contains the **public key for authentication**. The server holds the **corresponding private key** to prove that it is authorized to use that identity, via `CertificateVerify`.

Example scenario:

~~~text
Server hostname: api.example.test
Certificate leaf:
  Subject / SAN: DNS:api.example.test
  Public key: RSA (for example)
  Issuer: Intermediate CA
  Signature: CA signs over certificate contents

Client has:
  Trust store containing trusted root CA
  PKIX policy and expected hostname

Client must:
  Build/validate certificate chain + trust anchor
  Check validity / signature / constraints / EKU / algorithm policy
  Check SAN/hostname api.example.test
  Verify CertificateVerify over handshake transcript
~~~

All names above are strictly **illustrative names**, not a real certificate. The crucial point is that **the public key in the leaf certificate is not necessarily the ECDHE key share**: an RSA certificate can be used for authentication while ephemeral agreement is X25519.

### 6.2. Parsing is not trust

`CertificateFactory.getInstance("X.509")` can read DER/PEM and construct an `X509Certificate`, but **being parseable only proves valid structure**. Authenticating a TLS server requires a PKIX/trust manager mechanism and hostname/endpoint identity verification.

Distinction:

| Action | Result | Not yet guaranteed |
| --- | --- | --- |
| `CertificateFactory.generateCertificate(...)` | X.509 can be parsed. | CA trust, hostname, expiration, purpose, revocation. |
| `cert.checkValidity()` | Current time is within the certificate's validity window. | Trusted CA chain, correct hostname. |
| `cert.verify(issuerPublicKey)` | Certificate signature matches the supplied public key. | Whether the issuer public key belongs to an approved trust anchor. |
| `TrustManagerFactory`/PKIX | Checks the chain against the configured truststore/policy. | Hostname rules if a raw socket application has not enabled endpoint identification. |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Requests HTTPS-style endpoint identity checking during handshake with appropriate JSSE. | Does not replace loading a trustworthy truststore. |

In Java raw `SSLSocket`/`SSLEngine`, **do not assume hostname verification happens by default the same way as in every HTTPS client**. When connecting via raw sockets to a server, enable `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` on the client according to the purpose and JDK version. High-level HTTP clients generally manage trust/hostname already, but avoid customizations that disable verification.

### 6.3. CA signature and handshake CertificateVerify are two different signatures

**Signature on the certificate (CA signature):** the CA signs the `TBSCertificate` content of the leaf certificate to attest its attributes and public key under CA policy. The client validates the chain up to a trust anchor.

**`CertificateVerify` signature (server signature):** the server uses the **private key corresponding to the leaf certificate** to sign data specified from the handshake transcript, proving it controls the private key and binding the negotiation that took place. The signed content/format depends on the TLS 1.3 signature scheme.

If you only check that the certificate has a valid CA signature without **proving the peer holds the private key**, an attacker could replay the public certificate of a legitimate server. `CertificateVerify` is a key part of preventing this.

### 6.4. Two-way mTLS authentication differs from standard HTTPS connections

- **Server-auth TLS:** the client authenticates the server; the server **does not necessarily** authenticate the client with a certificate. Applications typically use separate token/session/user authentication.
- **Mutual TLS (mTLS):** the server requests a client certificate and validates chain/identity/purpose; the client proves possession of its private key during the handshake. This can be tied to workload identity when properly deployed.
- **mTLS does not automatically define authorization**: a client with a valid certificate is not implicitly authorized to read every resource. Mapping identity, tenant, scope, and policy remains the application's responsibility.

A self-signed certificate added directly by the client to its truststore can serve **loopback testing** or approved pinning. This does not mean "disabling trust checks". In production, trust anchors must be provisioned through a trusted configuration channel, with managed rotation and corresponding identity verification.

## 7. How do handshake signatures, Finished, and record MACs differ?

It is very easy to conflate these three concepts:

### 7.1. `CertificateVerify`: signature using the identity private key

The server signs over the transcript/value defined by the TLS standard, and the client verifies it with the certificate's public key. The signature scheme can be RSA-PSS, ECDSA, or EdDSA depending on policy, certificate, and negotiation.

**Do not equate the CA's certificate signing algorithm with the scheme the server uses in CertificateVerify.** A certificate can be signed by the CA with one scheme, while the key in the leaf certificate uses another supported scheme for the handshake.

### 7.2. `Finished`: MAC using a derived key, confirming handshake integrity

TLS 1.3 derives `finished_key` via **HKDF-Expand-Label** and computes an **HMAC over the transcript hash**. The peer verifies `Finished` before considering the handshake complete under protocol rules.

`Finished` is **not a digital signature** and does not use the certificate's private key to sign each time. It confirms that both sides hold the right traffic secret and saw a consistent handshake, thereby helping detect handshake tampering or key mismatch.

### 7.3. AEAD authentication tag: protecting each TLS record

After the handshake, application records are encrypted and authenticated with an AEAD such as AES-GCM or ChaCha20-Poly1305. Each record's tag protects its contents and bound metadata per the TLS record format.

This tag is **neither** `CertificateVerify` nor `Finished`. Application data does not need to be RSA-signed again by the server for every packet: the cost and semantics are different, and TLS uses efficient symmetric traffic keys on the data path.

| Question | `CertificateVerify` | `Finished` | AEAD record tag |
| --- | --- | --- | --- |
| Which key is used? | Certificate private key (asymmetric key). | Secret/key derived from key schedule (MAC). | Symmetric traffic key for the corresponding send/receive direction. |
| What does it protect? | Handshake transcript per standard. | Integrity/binding of handshake context. | Corresponding TLS application/handshake record. |
| Is it a digital signature? | **Yes**. | **No**, it is a MAC. | **No**, it is an authentication tag. |
| Does it appear on every application record? | **No**. | **No**. | **Yes**, per AEAD record format. |

### 7.4. Why are both CertificateVerify and Finished needed?

`CertificateVerify` binds the **certified identity** to the transcript; `Finished` binds the **derived key schedule/secrets** to the transcript and confirms key possession. Combined with certificate trust, TLS defends against negotiation-tampering and MITM attacks far more effectively than plain DH alone.

Do not omit `Finished` or signature checks merely because "a TCP connection exists" or "the server certificate parsed".

## 8. TLS 1.3 session key derivation with HKDF

### 8.1. Do not use the raw shared secret directly as an AES key

The output of DHE/ECDHE is a **shared secret**. TLS 1.3 uses **HKDF-Extract / HKDF-Expand-Label** and transcript context to generate multiple secrets and keys for distinct purposes.

Conceptual diagram (not verbatim implementation code of the entire RFC):

~~~text
       Pre-shared key / PSK (if present)
                    |
                    v
                early secret
                    |
       ECDHE / DHE shared secret
                    |
                    v
              handshake secret
                    |
          +---------+---------+
          |                   |
  client handshake    server handshake
    traffic secret      traffic secret
          |                   |
    handshake keys       handshake keys

       handshake transcript + key schedule
                    |
                    v
                main/master secret
                    |
          +---------+---------+
          |                   |
  client application   server application
    traffic secret       traffic secret
          |                   |
  AEAD key + IV          AEAD key + IV
          |                   |
          +---- application records ----+
~~~

Stage names and output lengths must follow the RFC. **Do not create a single key and reuse it for both directions and every purpose**: TLS separates secrets by role, direction, epoch, and transcript. This illustrative diagram helps clarify separation and does not replace the full specification in **RFC 9846 `7 Key Schedule**.

### 8.2. Traffic keys and IVs differ from the certificate's "private key"

- **Identity private key:** persists across many connections, used for authentication per policy; may reside in an HSM.
- **key_share private key:** ephemeral, used to compute the ECDHE secret within one handshake.
- **Client application traffic key:** encrypts data from client to server.
- **Server application traffic key:** encrypts data from server to client.
- **Traffic IV/nonce:** record encryption parameter, combined with key and sequence rules to prevent nonce reuse.

Even when both directions use **AES-128-GCM**, they do not share the same raw key or nonce sequence.

### 8.3. A TLS 1.3 cipher suite does **not** name every cryptographic component

For example, `TLS_AES_128_GCM_SHA256` means:
- AEAD record cipher: **AES-128-GCM**.
- Hash used for transcript/HKDF: **SHA-256**.

It **does not encode the key agreement group name** and **does not dictate the certificate signature** in the suite name itself. The key agreement group is negotiated via supported groups/key_share, and the signature scheme via the corresponding extensions.

Compared to **TLS 1.2**:
- Legacy suite names such as `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` typically hint at **ECDHE key exchange + RSA authentication + AES-GCM**.
- In **TLS 1.3**, the suite `TLS_AES_128_GCM_SHA256` specifies **AEAD + HKDF hash**, not "TLS no longer uses certificates".
- Do not try to use a TLS 1.2 suite as a TLS 1.3 suite because the two versions define cipher suites differently.

In TLS 1.3, other common suites include `TLS_AES_256_GCM_SHA384` and `TLS_CHACHA20_POLY1305_SHA256`; selection policy depends on provider support, organizational standards, and hardware capabilities. Do not infer certificate type just by looking at the name `AES_128_GCM`.

## 9. Record encryption: why does TLS use AEAD?

Once traffic keys exist, the TLS record layer protects messages using **Authenticated Encryption with Associated Data (AEAD)** rather than unauthenticated encryption.

### 9.1. Record concept

~~~text
Application bytes
      |
      v
TLS record layer
  - split into records per protocol
  - choose traffic key by direction/phase
  - build nonce from traffic IV + sequence number
  - AEAD encrypt and produce tag
      |
      v
Encrypted record over TCP
      |
      v
Peer: verify tag -> accept and decrypt / reject
~~~

In TLS 1.3, the record layer uses appropriate header/metadata as **AAD** and encrypts the inner content per specification. A single flipped bit can cause the AEAD check to fail and terminate the connection under TLS rules.

### 9.2. Critical nonce rule

With AES-GCM, **never repeat a (key, nonce) pair** across independent encryptions. TLS 1.3 manages record nonces through a standardized mechanism based on the **derived static IV and sequence number**, along with appropriate limits and key updates.

Do not manually instantiate `GCMParameterSpec` or `Cipher` to re-encrypt payloads after already using `SSLSocket`: the TLS provider already handles AEAD, nonces, and tags. Adding an arbitrary extra AES layer does not fix certificate trust bugs and can complicate key lifecycles.

`SSLSocket.getInputStream()` returns **application plaintext after TLS authenticates the record**; `getOutputStream()` accepts application plaintext for the record layer to encrypt. The application does not need to know raw traffic keys or nonces.

### 9.3. AEAD does not by itself prevent application replay

TLS record encryption protects record ordering within **a single connection** per protocol mechanics. However, an application can still receive **valid HTTP requests replayed** over a new session, such as client retries, an attacker with a valid token, or 0-RTT. Context-appropriate idempotency keys, business nonces, token expiration/transaction checks, and anti-replay policies are required.

**TLS 1.3 0-RTT early data** is a special case with replay risk; do not use 0-RTT for operations with unacceptable repeatable side effects without standards- and business-aligned safeguards.

## 10. TLS 1.3 vs. TLS 1.2: decisive differences

| Aspect | TLS 1.2 | TLS 1.3 |
| --- | --- | --- |
| Key establishment | Has many cipher suite families, including historical RSA key transport and ECDHE; security depends on choice. | Standard certificate handshakes use (EC)DHE, with no static RSA key transport; supports PSK modes. |
| Identity / signatures | Certificates and signatures/authentication per specific handshake flow and suite. | `Certificate` + `CertificateVerify` bind identity and transcript in certificate-based handshakes. |
| Cipher suite name | Usually indicates key exchange, authentication, bulk cipher, and hash. | Defines **AEAD + HKDF hash**; key_share and signature schemes are negotiated separately. |
| Key derivation | TLS 1.2 PRF/own secret model. | **HKDF key schedule** separating early/handshake/application secrets. |
| Handshake protection | Several handshake messages regarding certificates are sent before encryption is enabled. | Most handshake messages **after ServerHello** are protected with handshake traffic keys. |
| Record protection | May be AEAD or legacy mechanisms depending on allowed suites. | Based on **AEAD**. |
| Resumption / 0-RTT | Has session resumption; no TLS 1.3 0-RTT mechanism. | PSK/tickets and optional 0-RTT with dedicated replay safety requirements. |
| Forward secrecy | Only when key exchange/configuration supports it (e.g., ECDHE). | Standard certificate-based (EC)DHE provides forward secrecy; PSK-only requires separate evaluation. |

Do not mistakenly assume "TLS 1.2 is always insecure" or "TLS 1.3 is always secure regardless of configuration". TLS 1.2 posture also depends on cipher suites, patch level, and deployment constraints; prefer TLS 1.3 when both peers and organizational requirements support it.

Legacy versions such as SSLv3 and TLS 1.0/1.1 are not choices for new connection designs. Inspect protocol lists and cipher suites on the actual JDK rather than hardcoding a fallback to weak versions to get past handshake errors.

## 11. What does Java use to run TLS? JSSE, not hand-assembled JCA primitives

Java SE provides the **Java Secure Socket Extension (JSSE)** via `javax.net.ssl`. JSSE integrates handshake, certificate processing, key exchange, signature verification, key schedule, record encryption, and connection closure.

| Java component | Responsibility |
| --- | --- |
| `SSLContext` | Configures TLS provider, key managers, trust managers, `SecureRandom`. |
| `SSLSocket` / `SSLServerSocket` | TCP socket connections protected by TLS. |
| `SSLEngine` | Transport-independent TLS engine, used for NIO/reactor/non-blocking I/O. |
| `KeyManagerFactory` | Obtains key managers from keystore/provider, helping the server select certificate/private key. |
| `TrustManagerFactory` | Obtains trust managers from truststore to evaluate peer certificates. |
| `SSLParameters` | Protocols, cipher suites, endpoint identification, client auth requirements, SNI/ALPN settings. |
| `SSLSession` | Metadata of the negotiated TLS connection: protocol, cipher suite, peer certificates, and session info. |
| `HttpsURLConnection` / `java.net.http.HttpClient` | HTTP/HTTPS APIs that normally perform TLS and identity checks when default configuration is intact. |
| `KeyStore` | Abstraction storing key/cert/trust material; not necessarily synonymous with an HSM or PKIX validator. |

**Design point:** For ordinary HTTPS, prefer `java.net.http.HttpClient` or a trusted, up-to-date HTTP framework rather than writing raw TLS sockets unless specifically needed. With raw sockets, the application must ensure endpoint identification and trust manager configuration itself; **do not install an `X509TrustManager` with empty methods to "trust all"**.

### 11.1. "SSLContext" does not mean SSLv3 is being used

Class names like `SSLContext` and `SSLSocket` are historical API names; they support modern TLS. `SSLContext.getInstance("TLS")` provides an engine for TLS, while the actual session protocol is chosen through supported/enabled protocols and negotiation. Do not treat the word "SSL" in a class name as evidence that an old SSL protocol is in use.

### 11.2. Applications do not need to call `Signature.verify` manually to verify server certificates

JSSE performs the relevant steps via the trust manager, certificate path processing, and TLS handshake according to policy. Manually parsing certificates or calling `getPeerCertificates()` does not replace identity/chain verification during the handshake.

For raw socket clients, use:

~~~java
SSLParameters parameters = sslSocket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
sslSocket.setSSLParameters(parameters);
sslSocket.startHandshake();
~~~

This is an illustrative snippet; `sslSocket` is an instance created from an appropriate `SSLSocketFactory`. Do not use `setEndpointIdentificationAlgorithm(null)` to "temporarily bypass certificate errors", as that disables a critical identity verification layer.

### 11.3. Avoid "trust-all" and "always-true hostname verifier"

Dangerous code patterns:
- `X509TrustManager.checkServerTrusted(...)` with an empty body.
- `HostnameVerifier.verify(...)` always returning `true`.
- `SSLContext.init(..., new TrustManager[]{trustAll}, ...)` to bypass `PKIX path building failed`.
- Catching `SSLHandshakeException` and reconnecting over plaintext HTTP or a weak TLS version without policy.
- Inserting a certificate from an unauthenticated connection into the truststore and treating it as "trusted" simply because it appeared in a response.

The proper fix is **configuring CA trust/chain, SAN hostname, certificate expiry, algorithm constraints, and an appropriate provider**. In enterprise environments with an internal CA, trust anchors must be distributed through a trusted channel with managed rotation.

## 12. Java 17+: loopback TLS 1.3 handshake demo with server authentication

This example goes through **real JSSE** rather than running standalone ECDHE/AES. Both server and client run in one Java process, connecting over loopback TCP. The server uses a certificate in a PKCS#12 keystore, while the client trusts only the certificate imported into a **separate test truststore**, and **enables "HTTPS" endpoint identity checking**.

This approach serves educational goals:
- **Key agreement, handshake signatures, key derivation, and AES-GCM records** are handled internally by JSSE.
- **Certificate + truststore + hostname verification** are genuinely enforced.
- You can observe the `SSLSession` protocol and cipher suite, and successfully exchange `ping`/`pong` data.
- No raw private key, ECDHE secret, or traffic key needs to be exposed.
- **This is a local demo, not how production CAs/credentials should be managed.**

### 12.1. Creating test certificate/key and truststore with `keytool`

Run in a **dedicated scratch directory**, for local use only, and never commit these test files. The `keytool` commands below run on JDK 17+. `changeit` is a **public demo password**, definitely not a password to use for production keystores.

~~~bash
# 1. Generate an RSA private key + self-signed certificate for localhost only.
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 2 \
  -storetype PKCS12 -keystore server.p12 \
  -storepass changeit -keypass changeit -noprompt

# 2. Export the public certificate, without exporting the private key.
keytool -exportcert -rfc -alias localhost -keystore server.p12 \
  -storepass changeit -file server.crt

# 3. Import that certificate into a DEMO-ONLY truststore.
keytool -importcert -alias localhost -file server.crt \
  -keystore trust.p12 -storetype PKCS12 \
  -storepass changeit -noprompt
~~~

Trailing `\` characters are **Bash** line continuations; in Windows PowerShell/CMD, enter each command on a **single line without `\`**. These steps were verified on Windows PowerShell with the same core flags.

Create the certificate with `SAN=dns:localhost,ip:127.0.0.1` because the client connects over loopback. `CN=localhost` alone is not a standard way to bypass SAN hostname checks. On other hosts, provide the SAN matching the real identity, a CA-issued/certified certificate per policy, and an appropriate truststore.

**Do not commit** `server.p12`, `trust.p12`, or generated private keys. When finished with the demo, delete test files per policy. Importing a self-signed certificate is an **intentional trust action** in a lab environment; do not import unknown certificates from the Internet into a production truststore.

### 12.2. Program `Tls13LoopbackDemo.java`

The program requires the environment variable `TLS_DEMO_PASS` holding the password of the **test keystores** and the two created PKCS#12 paths. There is no production private key or password in the code.

~~~java
import java.io.*;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class Tls13LoopbackDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Expected server and trust store paths");
        }

        String str = System.getenv("TLS_DEMO_PASS");
        if (str == null) {
            throw new IllegalStateException("Missing TLS_DEMO_PASS");
        }
        char[] pass = str.toCharArray();
        try {
            KeyStore ks = KeyStore.getInstance("PKCS12");
            try (InputStream in = new FileInputStream(args[0])) {
                ks.load(in, pass);
            }
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(ks, pass);

            SSLContext server = SSLContext.getInstance("TLS");
            server.init(kmf.getKeyManagers(), null, new SecureRandom());

            KeyStore ts = KeyStore.getInstance("PKCS12");
            try (InputStream in = new FileInputStream(args[1])) {
                ts.load(in, pass);
            }
            TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());
            tmf.init(ts);

            SSLContext client = SSLContext.getInstance("TLS");
            client.init(null, tmf.getTrustManagers(), new SecureRandom());

            try (SSLServerSocket listener = (SSLServerSocket)
                    server.getServerSocketFactory().createServerSocket(
                            0, 10, InetAddress.getLoopbackAddress())) {

                listener.setEnabledProtocols(new String[]{"TLSv1.3"});
                listener.setEnabledCipherSuites(
                        new String[]{"TLS_AES_128_GCM_SHA256"});

                ExecutorService pool = Executors.newSingleThreadExecutor();
                try {
                    Future<String> task = pool.submit(() -> {
                        try (SSLSocket s = (SSLSocket) listener.accept()) {
                            s.setEnabledProtocols(new String[]{"TLSv1.3"});
                            s.setEnabledCipherSuites(
                                    new String[]{"TLS_AES_128_GCM_SHA256"});
                            s.setSoTimeout(10000);
                            s.startHandshake();

                            String request = new String(
                                    s.getInputStream().readNBytes(4),
                                    StandardCharsets.US_ASCII);
                            s.getOutputStream().write(
                                    "pong".getBytes(StandardCharsets.US_ASCII));
                            s.getOutputStream().flush();
                            return request;
                        }
                    });

                    try (SSLSocket s = (SSLSocket)
                            client.getSocketFactory().createSocket(
                                    InetAddress.getLoopbackAddress(),
                                    listener.getLocalPort())) {

                        SSLParameters p = s.getSSLParameters();
                        p.setProtocols(new String[]{"TLSv1.3"});
                        p.setCipherSuites(
                                new String[]{"TLS_AES_128_GCM_SHA256"});
                        p.setEndpointIdentificationAlgorithm("HTTPS");
                        s.setSSLParameters(p);
                        s.setSoTimeout(10000);
                        s.startHandshake();

                        SSLSession session = s.getSession();
                        s.getOutputStream().write(
                                "ping".getBytes(StandardCharsets.US_ASCII));
                        s.getOutputStream().flush();

                        System.out.println(
                                "Protocol: " + session.getProtocol());
                        System.out.println(
                                "Cipher suite: " + session.getCipherSuite());
                        System.out.println("Server authenticated: "
                                + (session.getPeerCertificates().length > 0));
                        System.out.println("Client received: " + new String(
                                s.getInputStream().readNBytes(4),
                                StandardCharsets.US_ASCII));
                    }

                    System.out.println("Server received: "
                            + task.get(10, TimeUnit.SECONDS));
                } finally {
                    pool.shutdownNow();
                }
            }
        } finally {
            Arrays.fill(pass, '\0');
        }
    }
}
~~~

### 12.3. Compile/run and stdout

With **Bash**:

~~~bash
export TLS_DEMO_PASS=changeit
javac Tls13LoopbackDemo.java
java Tls13LoopbackDemo server.p12 trust.p12
~~~

With **Windows PowerShell**:

~~~powershell
$env:TLS_DEMO_PASS = "changeit"
javac Tls13LoopbackDemo.java
java Tls13LoopbackDemo server.p12 trust.p12
Remove-Item Env:TLS_DEMO_PASS
~~~

Only use the password `changeit` because this is a lab whose secret has **no value outside the demo**. Never put production passwords on the command line, stdout, source code, or repository. In production, integrate secret delivery via workload identity/secret manager and keystore/HSM policy.

Verified output on JDK 17 with JSSE supporting TLS 1.3 and AES-128-GCM, and test certificate/keytool created per instructions:

~~~text
Protocol: TLSv1.3
Cipher suite: TLS_AES_128_GCM_SHA256
Server authenticated: true
Client received: pong
Server received: ping
~~~

**When the environment does not support TLS 1.3 or the hardcoded cipher suite in the demo**, the handshake will fail. This should be handled via supported configuration/policy, without silently falling back to weak SSL/TLS. Depending on the provider, exception messages and truststore management may vary.

### 12.4. Precise breakdown of TLS components

**Server side:**
- `KeyStore("PKCS12")` loads the certificate and private key **used to authenticate the server**; `KeyManagerFactory` provides the key material to JSSE.
- `SSLContext.init(kmf.getKeyManagers(), null, ...)` allows the server to present its certificate and prove possession of the private key.
- `SSLServerSocket` accepts TLS connections. TLS 1.3 and the AEAD suite are explicitly requested on both the listener and socket.
- The demo **does not enable client certificate authentication**. Do not mistake this for mTLS; the server only knows the client completed the handshake, **not authenticated by a client certificate**.

**Client side:**
- `TrustManagerFactory.init(ts)` configures a **dedicated truststore containing the demo certificate**; the server certificate is verified against the configured trust.
- `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` enforces checking the expected peer identity. The SAN must match the connected host/IP.
- `SSLSession.getProtocol()` and `getCipherSuite()` only return negotiated metadata, **without exposing raw secrets**.
- `session.getPeerCertificates().length > 0` here demonstrates that the server presented a certificate. By itself, it is **not the full proof of trust**; the real assurance comes from the JSSE handshake with properly configured trust manager + hostname verification, and `startHandshake()` completing without exception.

**Data path:**
- The `ping`/`pong` strings are written/read by the application as plaintext on `InputStream`/`OutputStream`.
- JSSE executes ECDHE, handshake signing/verification, Finished, HKDF, AEAD records, and nonces/tags underneath. The application does not call `Cipher.getInstance("AES/GCM/NoPadding")` for data inside `SSLSocket`.
- Encryption only protects the **transport between the two endpoints**. If the server logs `ping` or forwards plaintext over another unencrypted connection, TLS on the initial connection does not prevent subsequent leakage.

**Demo limitations:**
- The certificate is valid for only 2 days and is self-signed; do not use it to serve a real domain.
- The demo truststore directly pins the self-signed certificate. Production requires a proper PKI/trust model and rotation.
- The TLS record cipher suite is **hardcoded to produce deterministic, verifiable stdout**, which does not mean every production system must exclusively use `TLS_AES_128_GCM_SHA256`.
- The program lacks an HTTP parser, overall timeout handling, certificate rotation, full cancellation, or high-load server architecture. It is a real TLS lab, not a production HTTP server.

## 13. How certificate, signature, keys, and encryption together establish "server authentication"

Consider two scenarios that share the same ECDHE and AES-GCM:

### 13.1. ECDHE + AES-GCM without server authentication

~~~text
Client --key_share--> attacker --key_share--> real server
Client <--attacker share-- attacker <--server share--

Client and attacker share secret A.
Attacker and real server share secret B.
Attacker decrypts/modifies/re-encrypts traffic between both sides.
~~~

ECDHE protects the secret against a **passive observer**, but cannot stop a MITM if the key exchange is not authenticated. The server's handshake signature, certificate chain/trust, and `Finished` prevent someone who merely has a key share from impersonating the certified server.

### 13.2. Valid certificate but hostname verification disabled

The client trusts CA A, and the attacker holds a valid certificate from CA A for a **different domain**. If the client only checks "the cert is trusted by a CA" without checking SAN/expected hostname, the connection may be accepted under the wrong identity.

**Lesson:** "public key signed by a trusted CA" is not enough; it must bind to the **target endpoint identity**, intended usage, and protocol constraints.

### 13.3. Certificate parses cleanly, but private key does not match

The server presents a leaf certificate with RSA public key X, yet the server's private key belongs to RSA Y. The `CertificateVerify` signature cannot be verified with public key X, so the handshake is rejected. This illustrates why **proof of possession** of the private key is required during the handshake.

### 13.4. Certificate and signature valid, but Finished fails

Even if certificate and signature checks succeed, if `Finished` does not match the transcript/key material, the connection must **abort**—do not proceed to application data "just to try". `Finished` verifies consistency of the derived secret and handshake context.

### 13.5. Valid handshake, invalid application tag

An AES-GCM record modified in transit fails the AEAD integrity check, causing the connection to fail per the TLS protocol. Never pass unauthenticated plaintext to the application or ignore errors and process the record as valid.

## 14. Common TLS errors in Java JSSE

| Symptom / exception | Possible cause | What to check |
| --- | --- | --- |
| `SSLHandshakeException`, sometimes containing `PKIX path building failed` | Server chain cannot build to a trusted anchor. | Truststore, missing intermediate, official CA, certificate policy; do not trust-all. |
| `SSLHandshakeException` due to hostname mismatch | SAN lacks target host/IP or endpoint identity does not match. | Actual URL/hostname, SAN, SNI, certificate rotation; do not disable name checks. |
| `CertificateExpiredException` (often as cause) | Certificate is outside its validity period. | System clock, NotBefore/NotAfter, renewal schedule. |
| `SSLHandshakeException` / `SSLProtocolException` | Both sides share no compatible protocol/cipher suite/key share/signature scheme. | TLS 1.3 support, JDK/provider config, disabled algorithms, sanitized negotiation logs. |
| `SSLException` during read/write | AEAD/tag/record processing error, peer error closure, or protocol/transport issue. | Connection context—could be network error or corrupted data; do not guess from a single message. |
| `SocketTimeoutException` | Network/handshake/read timeout per socket policy. | Network connectivity, timeouts, and server load; do not assume a bad cert. |
| `UnrecoverableKeyException` / `KeyStoreException` | Keystore cannot read private key, wrong password, or wrong alias/key config. | KeyManagerFactory, PKCS12/JKS/provider, key alias, password from secret manager. |
| `SSLHandshakeException` with mTLS enabled | Server requires client cert, but client lacks one or is untrusted. | Client key managers, certificate/key usage, server truststore, client auth requirement. |
| Connected with `TLSv1.2` when expecting `TLSv1.3` | Enabled protocols differ from intent or peer lacks support. | `SSLSession.getProtocol()`, config, intermediaries, and policy. |
| TLS completes but HTTP returns 401/403 | TLS may be valid, while user/token/authorization failed. | Application authentication/authorization is **separate** from the TLS handshake. |

**Do not diagnose the root cause solely from the exception name `SSLHandshakeException`.** This general exception can wrap certificate, algorithm, cipher, key material, or protocol errors. Inspect the cause chain, trust manager, and provider in a controlled manner without printing private keys, tokens, or full handshake secrets to logs.

### 14.1. Debugging with JDK properties while protecting logs

In lab environments, JSSE debugging can be enabled, for example:

~~~bash
java -Djavax.net.debug=ssl,handshake Tls13LoopbackDemo server.p12 trust.p12
~~~

**Do not enable this debug mode in production or attach raw logs publicly**. Handshake logs can expose hostnames, certificates, key IDs, internal parameters, and sensitive metadata; other debug flags can reveal material requiring strict protection. Use short-lived log settings, restrict ACLs/retention, and sanitize before sharing.

### 14.2. SNI and ALPN are not signatures

- **SNI (Server Name Indication)**: client informs the server of the desired hostname so the server selects a certificate/virtual host; it is not proof of a valid certificate.
- **ALPN (Application-Layer Protocol Negotiation)**: both sides negotiate the application protocol, such as `h2` or `http/1.1`. It **does not create a separate key exchange** replacing TLS, nor does it grant access rights.
- If the server selects a certificate that does not match SNI/expected host, the JSSE client must still enforce hostname/trust verification per policy.

## 15. Session resumption, PSK, and 0-RTT: certificates are not always resent

TLS 1.3 can resume connections based on **session tickets / resumption PSKs**. In these flows, a resumed handshake may **not send a new Certificate/CertificateVerify**, because authentication is inherited/bound through the PSK/session state by protocol design.

Distinctions to note:

| Mechanism | Role | Risks to manage |
| --- | --- | --- |
| **Full handshake, certificate authentication** | Authenticates server via chain/certificate signature and establishes fresh secrets. | Chain/hostname, signature scheme, key share/trust. |
| **PSK resumption** | Continues association based on a secret derived from an earlier connection/handshake. | Ticket key lifecycle, PSK scope, identity binding, expiry. |
| **PSK + DHE** | Combines PSK resumption with an ephemeral key share. | Proper configuration to retain forward secrecy under the model. |
| **PSK-only** | May omit a fresh DHE exchange where allowed. | Do not assume the same forward secrecy as full DHE. |
| **0-RTT early data** | Allows sending some application data early in eligible resumptions. | Carries **replay risk**; unsuitable for non-idempotent operations without replay protection. |

**Do not claim "TLS always sends a certificate in every handshake"**. The accurate statement is: a **certificate-based TLS full handshake** uses a certificate and proves private key possession; PSK handshakes have different authentication logic. Understand your system's configuration and session state when a packet capture shows no certificate.

### Replay protection concerns both TLS deployment and the application

A `POST /transfer-money` sent as 0-RTT can have dangerous side effects if replayed. Even when the record is encrypted, **encryption does not prove a request is unique**. Deployments need policies disabling 0-RTT for sensitive mutations or reliable anti-replay/idempotency across multiple instances and retries.

## 16. Practical deployment design: what to control at each layer?

| Layer | Question to answer | Recommended control |
| --- | --- | --- |
| **Key generation/certificate lifecycle** | Where is the certificate private key generated/stored/rotated? | Appropriate PKI, HSM/KMS where needed, ownership, expiration alerts, chain checks. |
| **Trust anchors** | Which CAs are permitted to authenticate servers/clients? | Truststore distributed via trusted channel, minimal custom roots. |
| **Endpoint identity** | Which hostname/service does the client expect to reach? | HTTPS endpoint identification, SAN match, no trust-all. |
| **Key agreement** | Which groups/sizes/versions are allowed? | TLS 1.3, supported JDK/provider, disabled-algorithms policy. |
| **Signature schemes** | Can the certificate holder authenticate with allowed algorithms? | RSA-PSS/ECDSA/EdDSA per certificate/provider/security policy. |
| **Key schedule/records** | Who handles HKDF, nonces, AEAD tags, record replay? | Use JSSE/trusted TLS library; do not reimplement TLS primitives. |
| **Application authentication** | Which client/user is authorized to access resources? | Token/mTLS identity mapping, authorization, tenant checks. |
| **Resumption/0-RTT** | Are there side effects? | Manage tickets/PSK, anti-replay, restrict 0-RTT per business rules. |
| **Telemetry** | Can you verify what TLS negotiated without leaking secrets? | Log permitted protocol, cipher suite, normalized certificate/key ID; never log raw secrets. |
| **Incident response** | What happens if a server private key/cert leaks or a CA is distrusted? | Revoke/rotate, update trust material, monitor, assess exposure. |

In Java microservices, good security design means using a **properly configured TLS HTTP client/server framework** rather than letting every team write custom X25519/HKDF/GCM code. Only when building foundational cryptographic libraries should you work directly at the wire-protocol level; even then, rely on audited implementations.

## 17. Common misconceptions

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| "TLS uses RSA to encrypt all HTTPS data." | TLS 1.3 uses **AEAD symmetric keys** for records, not RSA payload encryption. | An RSA certificate can sign the handshake; X25519/ECDHE agrees on a secret; AES-GCM protects data. |
| "ECDHE alone authenticates the server." | An attacker can run separate DH exchanges with each side. | Certificate/trust, CertificateVerify, and Finished are required. |
| "Having an X.509 certificate means the server is trusted." | A parseable certificate can still be self-signed, from an unknown CA, or mismatched in hostname. | Verify chain, trusted root, SAN, EKU/constraints. |
| "The certificate's public key is the key_share." | Identity keys and ephemeral agreement keys serve different purposes. | Distinguish long-term signing private key, ephemeral key exchange key, and traffic keys. |
| "CertificateVerify and Finished are both RSA signatures." | Finished is a MAC based on the key schedule, not an asymmetric signature. | CertificateVerify signs the transcript; Finished confirms transcript/keys. |
| "SHA256 in `TLS_AES_128_GCM_SHA256` means the server uses SHA256withRSA." | SHA256 here is the hash for HKDF/transcript. | Authentication signatures are negotiated separately. |
| "Every TLS record is signed with the certificate's private key." | The record layer uses symmetric AEAD keys and tags. | Handshake signatures establish initial authentication; AEAD handles session data. |
| "Since TLS encrypts data, hostname verification can be disabled." | You lose assurance that the server matches the intended identity, enabling MITM. | Enable endpoint identification and proper trust. |
| "Self-signed certificates can never be used." | They can be used in labs or controlled pinning/trust models. | Only trust via a controlled configuration channel, without skipping identity checks. |
| "`SSLContext` means SSLv3." | The class name is historical. | Select TLS 1.3 via provider and enabled protocols. |
| "TLS 1.3 never needs certificates in any case." | Missing context—PSK handshakes can omit sending certs. | Certificate-based full handshakes use certs; PSK/resumption follow separate rules. |
| "Calling `verify()` on any signature is enough against MITM." | You must verify the right transcript, trusted public key, identity, and Finished. | Use JSSE to execute the protocol; do not stitch JCA calls manually. |
| "A TLS 1.3 cipher suite also defines X25519 and RSA." | A TLS 1.3 suite only describes AEAD + hash. | key_share groups and signature schemes are negotiated separately. |
| "AES-GCM automatically stops all HTTP replay." | AEAD record integrity differs from business/0-RTT anti-replay. | Add idempotency, request nonces, and anti-replay where needed. |
| "Once the socket handshake finishes, every command is allowed." | TLS authenticates endpoints, not user permissions or endpoint authorization. | Perform independent authorization checks. |

## 18. Self-check scenarios

**Question 1.** A server uses an RSA-2048 certificate, while the session negotiates `TLS_AES_128_GCM_SHA256` and `X25519`. Is the RSA key encrypting application data?

**Answer:** No. In a TLS 1.3 certificate-based handshake, the RSA key may be used for the authentication signature, X25519 exchanges the ephemeral secret, and AES-128-GCM uses symmetric traffic keys for records.

**Question 2.** Client and server build their own custom ECDHE exchange and compute the same shared secret. Have they prevented MITM?

**Answer:** Not yet. There is no proof of identity or binding of the transcript to a trusted public key. The full authenticated TLS handshake is needed.

**Question 3.** `CertificateFactory` successfully parses the server's PEM certificate, and `cert.checkValidity()` throws no error. Can `TrustManagerFactory` and hostname checks be skipped?

**Answer:** No. Parsing and validity are only local checks; chain/trust, issuer/signature, usage, and SAN/expected hostname are all required.

**Question 4.** Why does TLS 1.3 need both `CertificateVerify` and `Finished`?

**Answer:** CertificateVerify proves that the private key matching the certified identity signed the handshake context; Finished is a MAC based on the traffic secret confirming key and transcript integrity. They protect different properties.

**Question 5.** One byte of a record is altered; is it correct for AES-GCM to still decrypt the plaintext and let the app report an error afterward?

**Answer:** Unauthenticated plaintext must never be accepted. The AEAD tag must be verified per TLS; a corrupted record is rejected, normally failing the connection.

**Question 6.** Does cipher suite `TLS_AES_256_GCM_SHA384` require an RSA-4096 certificate or the P-384 group?

**Answer:** No. The suite specifies the AEAD and HKDF/transcript hash; certificate signature schemes and key agreement groups are negotiated via separate mechanisms.

**Question 7.** In the Java demo, why does the client still need `setEndpointIdentificationAlgorithm("HTTPS")` when it already has a dedicated `trust.p12`?

**Answer:** The truststore determines which public keys/CAs are trusted; hostname checking ensures the certificate actually belongs to the endpoint being connected to. The two checks complement each other.

**Question 8.** If a long-term certificate private key is compromised after an ECDHE session has ended, can an attacker automatically decrypt an old packet capture?

**Answer:** Not automatically. ECDHE with properly protected and discarded ephemeral keys/traffic secrets provides forward secrecy. However, if traffic secrets, endpoint memory, or logs were exposed while the session ran, risk remains.

**Question 9.** Why not take the output of `KeyAgreement.generateSecret()` as an AES key and call GCM directly on a socket?

**Answer:** TLS requires an HKDF key schedule, transcript binding, nonce/sequence management, handshake authentication, Finished, record framing, and other policies. Hand-assembling without these components leaves the system vulnerable to MITM, nonce reuse, and record confusion.

**Question 10.** In a TLS 1.3 resumption, no new `Certificate` appears in the packet trace. Did a MITM strip the certificate?

**Answer:** You cannot conclude that immediately. PSK resumption may omit sending a new certificate; you must analyze the handshake mode, ticket/PSK binding, and trust of the original session.

**Question 11.** An HTTP API receives a `POST` over 0-RTT fully encrypted with TLS 1.3. Can business-level anti-replay be skipped?

**Answer:** No. 0-RTT carries replay risk; policies restricting side-effecting operations and appropriate idempotency/anti-replay are required.

**Question 12.** Java shows `SSLSession.getCipherSuite()` as `TLS_AES_128_GCM_SHA256`. Does that guarantee the server certificate underwent hostname verification?

**Answer:** Not from the cipher suite alone. You must verify that the trust manager and endpoint identification were enabled and enforced for the connection per policy; the cipher suite only describes record/hash protection.

## 19. Checklist when configuring TLS in Java applications

- [ ] Prefer **TLS 1.3** whenever feasible; only support TLS 1.2 if needed for compatibility and allowed by security policy.
- [ ] Verify actual provider/JDK support for protocols, cipher suites, groups, and signature schemes.
- [ ] Ensure the server certificate has **SAN hostname/IP**, valid dates, proper key usage/EKU, and a chain to the right trust anchor.
- [ ] **Never use trust-all** or an always-true hostname verifier.
- [ ] Ensure raw `SSLSocket` clients have appropriate endpoint identification; HTTP client frameworks must not be customized in ways that lose hostname checks.
- [ ] Keep truststores/keystores/private keys provisioned and protected outside source/repos, with rotation and expiration monitoring.
- [ ] Distinguish long-term identity keys, ephemeral agreement keys, and symmetric traffic keys.
- [ ] Do not hand-code the TLS wire protocol, HKDF record keys, AES-GCM nonces, or Finished verification.
- [ ] If using mTLS, maintain a clear client certificate policy and identity-to-authorization mapping.
- [ ] Control PSK tickets/resumption/0-RTT; reject side-effecting early data without appropriate anti-replay.
- [ ] Log authorized **protocol, cipher suite, normalized peer identity, and error codes**; never log private keys, traffic secrets, or sensitive plaintext.
- [ ] Test certificate failures, hostname mismatches, no shared cipher suite, disabled protocols, stale truststores, and key rotation.
- [ ] Inspect the final hop behind reverse proxies/load balancers: TLS may terminate at the proxy, so the proxy -> backend connection needs separate protection per the threat model.
- [ ] After TLS, the application still performs authentication, authorization, and data validation as usual.

## 20. Official references

1. [RFC 9846 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc9846.html) (07/2026): current specification replacing RFC 8446; handshake, key agreement, `CertificateVerify`, `Finished`, HKDF/traffic key schedule, and AEAD records.
2. [RFC 8446 — TLS 1.3 (2018)](https://www.rfc-editor.org/rfc/rfc8446.html): historical document still frequently cited in JDK/docs; replaced by RFC 9846.
3. [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525.html): identifying/verifying server/service identity in TLS.
4. [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869.html): foundation of HKDF-Extract and HKDF-Expand.
5. [Oracle Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): `SSLSocket`, `SSLEngine`, trust, hostname verification, TLS 1.3, and implementation notes.
6. [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): TLS engine and how to configure key/trust managers.
7. [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): enabled protocols, cipher suites, endpoint identification.
8. [Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): TLS over TCP sockets, `startHandshake`, and streams.
9. [Java SE 17 — SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): inspecting protocol, cipher suite, and peer certificates.
10. [Java SE 17 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html) and [KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): mechanisms for providing trust and identity key material to JSSE.
11. [Java SE 17 — KeyAgreement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): API demonstrating X25519, **not a replacement for TLS**.
12. [Oracle keytool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): generating test key pairs, exporting/importing public certificates, and managing keystores.
