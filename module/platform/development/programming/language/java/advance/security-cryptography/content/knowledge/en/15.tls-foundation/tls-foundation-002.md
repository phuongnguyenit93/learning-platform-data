# 15.2. Handshake Flow, Server Authentication, and Mutual TLS (mTLS)

## Learning objectives

After this lesson, you can:

1. Describe how **TLS (Transport Layer Security)** protects a connection by negotiating cryptographic parameters, establishing session keys, authenticating identities, and protecting exchanged data from eavesdropping/tampering.
2. Read the exact order of key messages in a **TLS 1.3 full handshake**, especially `ClientHello`, `ServerHello`, `EncryptedExtensions`, `Certificate`, `CertificateVerify`, `Finished`, and `CertificateRequest` for client authentication.
3. Distinguish **one-way TLS** (client authenticates server) from **mutual TLS/mTLS** (both sides authenticate each other's certificates), including the roles of **keystore**, **truststore**, and separate CAs on each side.
4. Explain **X.509 certificate chain verification, hostname/SAN, KeyUsage/EKU, proof of private-key possession**, and why merely "checking a valid CA signature" or "having a certificate" is not enough.
5. Understand the relationship between **(EC)DHE key exchange, HKDF, handshake transcript, Finished, AEAD record protection, forward secrecy**, and key differences between TLS 1.3, TLS 1.2, resumption, and 0-RTT.
6. Use **Java 17+ JSSE** together with `keytool` to create lab CA/leaf certificates, run a real TLS server and client in both modes, **keep hostname verification enabled**, and demonstrate behavior when a client certificate is missing in mTLS.
7. Identify operational pitfalls: `trust-all`, always-true `HostnameVerifier`, confusing mTLS with authorization, confusing serverAuth/clientAuth, failing to check certificate expiry/revocation, and a valid certificate for the wrong endpoint.

**Scope:** Part of **Java Advance – security-cryptography / 15. TLS Foundation**. This lesson focuses on **handshake flow and the two authentication modes**; the CA/certificate commands and socket code are for learning, not a complete PKI configuration or production deployment.

---

## 1. What does TLS protect and why is a "handshake" needed?

TCP provides a bidirectional byte stream but **does not encrypt data, authenticate the server, or prevent content modification**. An on-path attacker can listen, modify, or spoof data if the application lacks another layer of protection.

TLS layers a cryptographic protocol over a suitable transport, most commonly TCP for HTTPS. The **handshake** creates a security context that both endpoints agree on:

- **Version and parameters**: e.g., TLS 1.3, AEAD cipher suite, and allowed algorithms.
- **Key agreement**: a shared secret from ephemeral key exchange, usually (EC)DHE, derived into handshake and application traffic keys via the key schedule; or using PSK/resumption per protocol.
- **Server authentication**: the client verifies the server certificate's chain to a trust anchor, correct hostname/endpoint identity, and valid proof of private-key possession.
- **Client authentication (optional)**: the server can request a client certificate and verify it; this is **mTLS** when the client also authenticates the server.
- **Handshake integrity**: handshake summaries (transcript) are bound into authentication and `Finished`, detecting tampering or forgery during negotiation.
- **Record protection**: post-handshake application data is encrypted and authenticated using AEAD; each direction uses its own traffic keys/nonce and sequence managed by the protocol.

```text
Application: HTTP / gRPC / custom Java application
                   │
                   ▼
     TLS handshake → authenticated traffic keys
                   │
                   ▼
      TLS record protection (AEAD)
                   │
                   ▼
             TCP connection
```

**TLS does not replace business authorization**: a client with a valid TLS session is not automatically allowed to read any database record or perform any action. TLS also **does not guarantee data safety after decryption in the application**, does not eliminate XSS/SQL injection flaws, and does not hide metadata such as IP addresses or all traffic characteristics.

### 1.1. Easily confused terms

| Term | Meaning | Not synonymous with |
| --- | --- | --- |
| **Handshake** | Sequence for establishing keys, validating parameters, authenticating peers, and finalizing a secure connection | An HTTP request or a single AES encryption call |
| **TLS record** | Transport unit of data encrypted/authenticated under traffic keys | An X.509 certificate |
| **Cipher suite (TLS 1.3)** | Identifier for AEAD and hash used in the key schedule, e.g., `TLS_AES_128_GCM_SHA256` | Full bundle of key-exchange/authentication algorithms as in TLS 1.2 naming |
| **Key share** | Public value for ephemeral key agreement, typically ECDHE | The private key inside the server certificate |
| **Certificate chain** | Leaf + intermediate(s) needed to build a path to a trust anchor | A truststore that already blindly trusts every certificate sent by the server |
| **Keystore** | Store holding this side's own private key and certificate chain | A truststore used to trust the peer's CAs |
| **Truststore** | Repository of trust anchors/certificates accepted by the verifying side | The server's private key |
| **Server authentication** | Client verifies server identity and proof-of-possession during handshake | Server authenticating client |
| **Client authentication** | Server verifies client identity and proof-of-possession | Client API permissions |
| **mTLS** | Both directions perform appropriate TLS authentication | Two nested TLS layers or sending username/password twice |
| **ALPN** | Application protocol negotiation such as `h2`/`http/1.1` | Proof of peer identity |
| **SNI** | Server name indicated by client to help server select certificate/virtual host | Hostname verification mechanism on behalf of the client |
| **Session resumption** | Reusing state/PSK permitted by TLS on a subsequent connection | Guaranteeing a full fresh certificate exchange like the first connection |

---

## 2. One-way TLS: client authenticates server

In typical HTTPS, the **server presents a certificate**, while the client is **not required** to present a client certificate. This is **server-authenticated TLS**, or one-way TLS.

```text
CLIENT                                  SERVER
  |                                       |
  | ClientHello ------------------------->|
  |<------------------------- ServerHello |
  |<------------------ EncryptedExtensions|
  |<-------------------------- Certificate|
  |<-------------------- CertificateVerify|
  |<--------------------------------Finished|
  |                                       |
  | Validate server chain, SAN/hostname, |
  | certificate purpose, private-key    |
  | possession via handshake, transcript|
  |                                       |
  | Finished ---------------------------> |
  |                                       |
  |<======== protected app data =========>|
```

This simplified diagram shows a **full TLS 1.3 certificate-based handshake**. It omits alerts, optional messages, HelloRetryRequest, and record/key schedule details. Messages after `ServerHello` in TLS 1.3 are protected by appropriate handshake traffic keys (with protocol-level record structure details/visible fields). Do not treat this diagram as an exact packet capture for every version.

### 2.1. Step 1 – `ClientHello`

The client sends supported capabilities, such as:

- Supported TLS versions via the `supported_versions` extension.
- Usable TLS 1.3 cipher suites.
- `supported_groups` and `key_share` for key agreement.
- `signature_algorithms` so both sides know which signature schemes are accepted.
- **SNI** for the intended server name and **ALPN** if the application needs protocol negotiation.
- Possible PSK/session resumption information, depending on handshake mode.

The client **does not send raw secret keys or keystore passwords** in `ClientHello`. A `key_share` contains public data for the key agreement mechanism; the ephemeral private key remains local.

**SNI is not "verifying a trusted server":** SNI mainly helps the server pick the right virtual host/certificate; the client must still authenticate the certificate and intended target name.

### 2.2. Step 2 – `ServerHello` and shared secret

The server chooses the TLS version, cipher suite, and appropriate key share. Both sides combine their own ephemeral private key with the peer's public key share to produce the corresponding shared secret, then run the HKDF-based TLS 1.3 **key schedule** to derive traffic secrets.

```text
Client ephemeral secret + Server public key share ──┐
                                                    ├─ same key agreement secret
Server ephemeral secret + Client public key share ──┘
                                  │
                                  ▼
                  HKDF-based TLS 1.3 key schedule
                                  │
                handshake traffic keys / Finished keys
                                  │
                       application traffic keys
```

This illustrates key agreement conceptually; it is not a byte concatenation or custom KDF that applications should implement themselves. In TLS 1.3, an RSA certificate can be used **for authentication signing**, not for "RSA encrypting a premaster secret" as in some legacy TLS 1.2 handshakes. **(EC)DHE** provides the basis for **forward secrecy** when ephemeral secrets are properly managed and discarded: later compromise of the server certificate's private key does not by itself allow decrypting previously recorded TLS 1.3 sessions.

**Note:** Forward secrecy does not protect you if an attacker already controls an endpoint during the session, reads live traffic keys or endpoint plaintext, or successfully impersonates the server during the handshake. Resumption/PSK and other key exchange methods have distinct properties requiring protocol-specific evaluation.

### 2.3. Step 3 – Server sends certificate and proves key possession

The server sends `Certificate` with the leaf certificate (and usually intermediate certificates). Important elements:

1. **SubjectAlternativeName** (SAN) must cover the endpoint identity the client intends to reach, such as `DNS:api.example.com` or an appropriate IP SAN when connecting by IP literal.
2. **Certificate chain** must build a path to a root/trust anchor trusted by the client, with valid CA signatures and CA/BasicConstraints/name constraints, key usage, and policy checks.
3. **Validity/revocation** are evaluated against current time and policy; an unexpired certificate can still be revoked.
4. **ExtendedKeyUsage** on a server certificate normally requires `serverAuth` per profile/policy; do not arbitrarily treat `clientAuth` or `codeSigning` as substitutes.
5. **`CertificateVerify`** contains a signature produced by the server using the leaf's private key over the transcript/structure with TLS 1.3 domain separation. This proves the server holds a valid private key for the handshake, rather than merely copying a public PEM.

```text
CA trusted? ----yes----+
                       |
Chain valid? ---yes----+
                       |
Hostname SAN? --yes----+---> Can accept server identity
                       |     if all other TLS/policy checks pass
Key usage? ----yes-----+
                       |
CertificateVerify? yes-+
                       |
Finished? ----yes------+
```

**A leaf certificate containing a public key is not enough:** anyone can send a copy of `api.example.com`'s certificate. What stops an attacker from impersonating the server is that they must also produce a valid `CertificateVerify` using the **server private key** and satisfy the entire key exchange and handshake.

### 2.4. Step 4 – `Finished` and application data

`Finished` protects the handshake completion boundary with a MAC/verify_data bound to the transcript and appropriate handshake secrets. The client treats the session as secure only after all required TLS/identity checks succeed.

After the handshake completes, **application data** (HTTP requests/responses or bytes from `SSLSocket`) is protected by record-layer AEAD. Each direction has separate traffic keys per the key schedule with internal nonce/sequence management; **applications do not manually pick AES-GCM nonces for TLS records**.

**Do not confuse:** server-authenticated TLS tells the client it is talking to an authorized server; it **does not automatically provide client identity**. In one-way TLS, the server typically still needs a bearer token, session cookie, OAuth/OIDC, or separate application authentication to know who the requester is.

---

## 3. mTLS: the server also authenticates the client

**mTLS – mutual TLS** uses the same TLS foundation while adding the step where the **server requests a client certificate** and verifies the client's identity. The client must still authenticate the server as in one-way TLS; there is no exception "because the server trusts the client, the client can skip hostname verification".

```text
CLIENT                                          SERVER
  |                                               |
  | ClientHello ---------------------------------> |
  |<---------------------------------- ServerHello |
  |<----------------------------- EncryptedExtensions
  |<-------------------------------- CertificateRequest
  |<-------------------------------------- Certificate
  |<-------------------------------- CertificateVerify
  |<----------------------------------------- Finished
  |                                               |
  | Verify SERVER chain + SAN/hostname + signature|
  |                                               |
  | Client Certificate --------------------------> |
  | Client CertificateVerify --------------------> |
  | Client Finished -----------------------------> |
  |                                               |
  |        SERVER verifies CLIENT certificate     |
  |        trust chain / purpose / possession     |
  |                                               |
  |<============== protected app data ===========> |
```

This is the **TLS 1.3 mTLS flow in an initial/full handshake**; ordering can vary by version/handshake type, and optional/resumption/post-handshake auth cases follow specific rules. `CertificateRequest` signals that the server requests client authentication; if no matching certificate is available the client may send an empty list, but a server requiring **mandatory** authentication will reject the handshake.

### 3.1. Who owns which key?

| Asset | Server side | Client side |
| --- | --- | --- |
| Server private key | **Kept secret** in server keystore/HSM | Not issued |
| Server leaf + chain | Presented in handshake | Received to verify server |
| Server-trust CA/root | Not needed to trust itself | **Client truststore** holds approved trust anchors |
| Client private key | Not issued | **Kept secret** in client keystore/HSM |
| Client leaf + chain | Received when server requests | Presented in handshake |
| Client-trust CA/root | **Server truststore** holds CAs issuing to allowed clients | Not implicitly used as server trust anchor |
| Application authorization | **Enforce** identity → role/tenant/action | Only sends requests within granted permissions |

In a lab, a shared root CA reduces setup steps; in production, **you can and usually should separate the CA/profile for serverAuth from the CA/profile for clientAuth** to narrow trust scope. Having `server.p12` on the server does not mean the server trusts `client.p12`: the server must be separately configured with trust anchors and client authentication requirements.

### 3.2. `CertificateRequest` and `CertificateVerify`

When the server enables mTLS:

1. In a TLS 1.3 full handshake, the server sends `CertificateRequest`; the request may carry accepted CAs, signature algorithms, and extensions.
2. The client selects a matching certificate chain/private key; selection logic depends on the JSSE key manager, key type, CA hints, and signing capabilities.
3. The client sends `Certificate` and `CertificateVerify` to prove private-key possession over the appropriate transcript.
4. The server validates the client certificate/chain against the **server's** trust anchors, checks `clientAuth` purpose, and enforces constraints/identity policy.
5. `Finished` seals handshake integrity. The server lets the client use the channel only when handshake authentication satisfies policy.

**Sending just a public certificate is insufficient for mTLS authentication.** Anyone with a public PEM copy can transmit it, but cannot complete proof-of-possession without the corresponding private key.

### 3.3. `needClientAuth` and `wantClientAuth`

In a JSSE server:

- `SSLServerSocket.setNeedClientAuth(true)` or `SSLEngine.setNeedClientAuth(true)`: client certificate is **mandatory**; if the client fails to present a valid credential, the handshake is rejected.
- `setWantClientAuth(true)`: the server **requests** a client certificate but may accept a client without one. The application must handle empty identity paths itself.
- By default, servers do not require a client certificate. When the server does not ask for one, having `client.p12` loaded does not mean the client sends it unprompted.
- When enabling need/want, you must configure a trust manager and CA policy for client identities—never flip a boolean and trust every client certificate.

In Spring Boot, Netty, gRPC, proxies, ingress, or service meshes, configuration names differ, but the meaning of **require client auth** and **trusted client roots** must remain clear. Know **where mTLS terminates** (edge proxy, sidecar, or JVM application).

### 3.4. mTLS authenticates identity, not authorization

Suppose a client holds a certificate:

```text
Subject: CN=payments-worker, O=Example
SAN: URI:spiffe://company.example/ns/prod/sa/payments-worker
EKU: clientAuth
Issuer: Internal Workload CA
```

Once the handshake succeeds, the server can map the verified identity to a **service principal** like `payments-worker`, yet must still check **whether that service is allowed to read tenant T or invoke the refund operation**. If every certificate issued by the CA receives admin privileges, mTLS has been misused into an overly broad authorization policy.

Never accept a Subject DN, hostname, or `X-Client-Cert` header unprotected by a trusted proxy to grant permissions. With proxy termination, ensure identity headers are **stripped/re-created** by the trusted proxy rather than forged by Internet clients.

---

## 4. Where do TLS 1.3 and TLS 1.2 differ?

| Aspect | TLS 1.3 | TLS 1.2 |
| --- | --- | --- |
| Key exchange mechanism | Designed to use mechanisms providing forward secrecy in common full handshakes such as (EC)DHE, or PSK/resumption per standard | Can use ECDHE; older suites still used static RSA key transport (should not be chosen today) |
| Cipher suite naming | AEAD + hash, e.g., `TLS_AES_128_GCM_SHA256`; key exchange/signature negotiated independently | Suite name may embed key exchange, authentication, symmetric cipher, and MAC/hash |
| After `ServerHello` | Most handshake messages past this point are protected by handshake traffic keys | Many certificate/handshake messages travel in cleartext per classic TLS 1.2 flow |
| Server certificate proof | `CertificateVerify` in full certificate authentication | Signature in `ServerKeyExchange` for ECDHE suites; exact flow differs—do not force TLS 1.3 formulas |
| Server requests client certificate | `CertificateRequest` in TLS 1.3 full handshake, typically after EncryptedExtensions | `CertificateRequest` has TLS 1.2 position/sequence |
| Key derivation | HKDF-based TLS 1.3 key schedule | TLS 1.2 PRF/key expansion per RFC 5246 |
| 0-RTT | Can support early data in PSK resumption with replay risk, depending on support | Not an equivalent standard TLS 1.2 handshake feature |
| Recommended standard | Generally **prefer TLS 1.3** when client/server are compatible | Retain only when needed for interoperability with strong configs and permitted by policy |

**Do not apply the description "ClientKeyExchange / ChangeCipherSpec activates keys like TLS 1.2" to TLS 1.3.** In TLS 1.3, a compatibility `ChangeCipherSpec` record exists across implementations, but it plays no key-switching role as in TLS 1.2; keys are activated by handshake/key schedule state.

### 4.1. Session resumption may not resend certificates

A new TLS 1.3 connection can **resume a session** using a PSK/ticket from an earlier connection. In a resumption flow, a new `Certificate`/`CertificateVerify` is not necessarily sent as in a full certificate handshake. Therefore, a packet capture can only be interpreted accurately if you know whether it is a full handshake, PSK-only, or PSK combined with a fresh key exchange.

Specifically with mTLS, if your organization requires **re-checking client identity on every request**, understand how the server, TLS stack, proxy, and session resumption bind identity to sessions, and the impact of rotation/revocation. Do not assume "no client Certificate visible in capture = no mTLS" or "resumption always revalidates the client certificate".

### 4.2. 0-RTT does not replace client authentication

TLS 1.3 **0-RTT early data** is a resumption option; early data carries **replay risk** even when records are encrypted. Never place non-idempotent operations or money transfers in 0-RTT without replay protections. Do not confuse 0-RTT with full client-certificate authentication freshly performed in the same full handshake.

### 4.3. Which layer do ALPN and SNI belong to?

- **SNI**: hints the server name the client wants to connect to so the server/proxy chooses the certificate/route. Avoid mismatches across SNI, HTTP Host/:authority, certificate SAN, and routing policy.
- **ALPN**: negotiates e.g. `h2` for HTTP/2 or `http/1.1`. ALPN does not grant client identity; it is protocol negotiation.
- **SAN/hostname validation**: a **separate** check the client runs for the expected endpoint identity; never skip it just because SNI was sent.
- **HTTP Authorization**: happens at the application layer after TLS; usually still needed even when mTLS authenticates service identity.

---

## 5. Why do X.509, CA, keystore, and truststore matter for the handshake?

An **X.509 certificate** is a CA-signed structure binding a public key to a subject/SAN and policy extensions. In TLS, certificates enable client/server to verify that the presented public key belongs to an acceptable identity.

### 5.1. What conditions does server authentication require?

For `https://api.example.com`, the client does more than a single check:

1. The certificate has valid X.509 structure and policy-approved algorithms/key strengths.
2. A chain from leaf through intermediate(s) reaches a **trust anchor** actually trusted by the client.
3. `notBefore/notAfter` validity and revocation/status match applicable policy.
4. BasicConstraints/KeyUsage/EKU and path constraints, especially ensuring the issuing CA holds appropriate `keyCertSign` authority.
5. Target identity `api.example.com` matches an appropriate **DNS Subject Alternative Name**; connecting via IP literal requires a matching **iPAddress** SAN.
6. Proof that the server possesses the corresponding private key via handshake signature/proof, not merely possessing a copy of the leaf certificate.
7. Verification of transcript/`Finished` and that TLS parameters were not tampered with.
8. Checking that the application uses the right URL, trust configuration, and related security policies.

`X509Certificate.verify(issuerPublicKey)` only checks **the certificate signature against the supplied public key**; it does not guarantee the issuer is trusted, the hostname is right, or the peer holds the private key. Likewise, `CertPathValidator("PKIX")` does not automatically know the URL's hostname unless the application pairs it with endpoint identity verification.

**Do not arbitrarily substitute `CN` for SAN.** Modern TLS identity relies on SAN entries per service identity rules; JSSE/HTTPS must enforce proper endpoint identification.

### 5.2. With mTLS, the client certificate must have the proper purpose

In a TLS server accepting client certificates:

- The server truststore holds CAs/trust anchors for **client identities**, not only the CA issuing server certificates.
- The client leaf has an appropriate ExtendedKeyUsage, normally `clientAuth` (OID `1.3.6.1.5.5.7.3.2`), and KeyUsage matching the signature mechanism.
- The server must decide **whether to accept this specific client identity**, not merely "any chain under the root is allowed".
- Internal profiles may use URI, DNS, email SANs, or Subject DNs per policy; identify the identity source explicitly and avoid treating an arbitrary CN as an access grant.
- If a certificate is revoked, its private key is lost, or a service loses authorization, you need key/trust/revocation lifecycle and authorization updates.

### 5.3. Keystore and truststore

```text
ONE-WAY TLS
===========
Server:
  server.p12 = server private key + server leaf + chain
Client:
  truststore.p12 = trusted server CA/root(s)
  (no client private key needed)

mTLS
====
Server:
  server.p12 = server private key + server leaf + chain
  truststore.p12 = trusted client CA/root(s)
Client:
  client.p12 = client private key + client leaf + chain
  truststore.p12 = trusted server CA/root(s)
```

**A truststore is not a place to copy the peer's private key.** Public CA certificates are not necessarily secret, yet **truststore integrity** is security-critical: an attacker altering trust anchors can make the application trust rogue certificates.

**Right keystore path but wrong password** → the JVM cannot load the private key. **Unauthorized individual certificates in the truststore** → broken chain validation or overly broad trust. **Certificate chain missing an intermediate** → the client may fail to build a path to the root even when the root is already trusted.

---

## 6. Java JSSE: which API corresponds to which operation?

**JSSE** (*Java Secure Socket Extension*) is Java's TLS foundation. Foundational APIs in Java 17:

| API | Primary responsibility | Notes |
| --- | --- | --- |
| `SSLContext` | Sets up key managers, trust managers, and TLS engine configuration | Misconfiguring the context can trust the wrong CA |
| `KeyStore` | Loads `PKCS12` files or provider stores containing certificate/private-key entries | Having a file/alias does not automatically establish trust |
| `KeyManagerFactory` / `X509KeyManager` | Selects **this side's own** private key/certificate to present when requested | mTLS client needs client identity; server needs server identity |
| `TrustManagerFactory` / `X509TrustManager` | Verifies the **peer's** certificate chain against trust anchors/policy | Never use a custom trust-all manager |
| `SSLSocketFactory` | Creates client TLS sockets | Raw `SSLSocket` requires explicit endpoint identification config |
| `SSLServerSocketFactory` | Creates server TLS listening sockets | Server decides `setNeedClientAuth`/`setWantClientAuth` |
| `SSLSocket` | TLS connection, `startHandshake`, application reads/writes plaintext bytes | Data on the wire is protected by TLS records |
| `SSLEngine` | Nonblocking/transport-agnostic TLS for frameworks | Must properly manage handshake state, buffers, and task callbacks |
| `SSLParameters` | Configures endpoint identification, protocols, cipher suites, ALPN... | `setEndpointIdentificationAlgorithm("HTTPS")` enforces host check on raw clients |
| `SSLSession` | Protocol info, peer certificates/principal, cipher suite | Peer identity does not equal authorization |
| `HttpsURLConnection` / `HttpClient` | HTTP(S) clients over TLS | Normally prefer standard HTTP stack over raw TLS sockets |
| `SSLHandshakeException` | Handshake failure, e.g., chain/hostname/client cert/protocol | Never disable authentication just to "make it work" |

### 6.1. `setNeedClientAuth(true)` does not mean "configure TLS for both sides"

Enabling `needClientAuth` only requires the **client to present and authenticate a certificate**. The server must still have a keystore containing the **server private key/cert**, a truststore with the right client-issuing CA, and enforced application authorization. If the server enables `needClientAuth` while the client lacks a certificate or presents an untrusted one, the handshake will not complete.

### 6.2. Raw `SSLSocket` requires explicit endpoint identification

Example using JSSE on a client:

```java
SSLSocket socket = (SSLSocket) context.getSocketFactory()
        .createSocket("api.example.com", 443);
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
```

This is a **non-standalone illustrative snippet**: it requires JSSE imports, an `SSLContext context` initialized with the right truststore, network/exception handling, and closing the socket. The `HTTPS` algorithm uses JSSE's TLS endpoint identification rules; never hand-roll hostname checks with `contains` or disable hostname verification.

A raw `SSLSocket` **should not be assumed to automatically check hostnames like an HTTPS client** unless you configure endpoint identification. With Java `HttpClient`/`HttpsURLConnection`, preserve secure default TLS/hostname verification and avoid properties or `HostnameVerifier` bypasses.

### 6.3. mTLS at a reverse proxy or service mesh

Many systems terminate TLS at an ingress, load balancer, Envoy, or service mesh. There, mTLS may authenticate a **peer workload to the proxy**, while the Java app receives internal connections from the proxy. Therefore:

- Clearly identify **which TLS endpoint** verifies the client certificate and where the truststore lives.
- If the proxy forwards `X-Client-Cert`/principal headers, block Internet clients from injecting those headers; the trusted proxy must strip/rewrite them, and the proxy→app hop must be protected accordingly.
- Never let the Java app treat every HTTP request from the proxy as one shared identity and skip per-tenant/per-action authorization.
- Check rotation/expiry/revocation of workload certificates in the control plane, logging identity and policy across hops.

---

## 7. Java 17+ Lab: preparing root CA, server certificate, and client certificate

The lab below uses **`keytool` bundled with JDK 17**. The goal is to clarify which private key each side owns and which CA it trusts. We use a **training root CA** directly signing both the server leaf and client leaf, with **different ExtendedKeyUsage values**.

**Security warning:**

- The password `changeit`, root CA, and private keys created here are **for learning environments only**. Never reuse them in production and never commit `.p12` files to git.
- Commands pass store passwords on the command line for convenience; in real systems, passwords in process lists or shell history can leak. Use a secret manager, interactive prompt, or secure provider per policy.
- Run commands in an **empty lab directory** so you do not overwrite existing keystores. Do not import the demo CA into the system-wide `cacerts`.
- To run both modes back-to-back, terminate the previous server process before starting a new server on port 8443; the program handles one connection per run.
- Use **`localhost`** as the hostname, because the server certificate will have SAN `DNS:localhost`. Do not replace it with `127.0.0.1` while keeping the same certificate, since an IP literal requires an `iPAddress` SAN.

### 7.1. Create a training root CA

The following command generates an RSA CA key pair in `root-ca.p12`, self-signing the root certificate with `BasicConstraints CA:true` and `KeyUsage keyCertSign/cRLSign`:

```shell
keytool -genkeypair -alias lab-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Training TLS Root CA, O=Learning, C=VN" -validity 3650 -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -keystore root-ca.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
```

Export the **public** CA certificate:

```shell
keytool -exportcert -alias lab-ca -keystore root-ca.p12 -storepass changeit -file root-ca.pem -rfc
```

`root-ca.p12` contains the CA's private key and must be protected. `root-ca.pem` is the public certificate usable to establish a trust anchor. A self-signed root **is not automatically trusted** until the relying party intentionally places it in a truststore. `pathlen:0` is appropriate since the lab root signs leaves directly without intermediate CAs.

### 7.2. Generate server key pair and CSR

```shell
keytool -genkeypair -alias tls-server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost, O=Learning, C=VN" -validity 365 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
keytool -certreq -alias tls-server -keystore server.p12 -storepass changeit -file server.csr -ext "SAN=dns:localhost"
```

The CSR contains the server public key and requests a SAN. The CA must verify identity/policy; a CSR requesting `SAN=dns:localhost` does not mean a real CA must accept arbitrary DNS names.

### 7.3. CA signs server leaf with `serverAuth`

```shell
keytool -gencert -alias lab-ca -keystore root-ca.p12 -storepass changeit -infile server.csr -outfile server.pem -rfc -validity 365 -ext "SAN=dns:localhost" -ext "KU:critical=digitalSignature" -ext "EKU=serverAuth" -ext "BC=ca:false"
```

Import the CA certificate and then the certificate reply into `server.p12`:

```shell
keytool -importcert -alias lab-ca -file root-ca.pem -keystore server.p12 -storepass changeit -noprompt
keytool -importcert -alias tls-server -file server.pem -keystore server.p12 -storepass changeit -noprompt
```

Alias `tls-server` holds the private-key entry along with the certificate chain presented by the JSSE server. `server.pem` is only the public certificate and does not replace the private key inside `server.p12`.

### 7.4. Generate client key pair and CSR

```shell
keytool -genkeypair -alias tls-client -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=demo-client, O=Learning, C=VN" -validity 365 -keystore client.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
keytool -certreq -alias tls-client -keystore client.p12 -storepass changeit -file client.csr
```

Below, the CA signs a leaf **intended for TLS client auth**, not a server:

```shell
keytool -gencert -alias lab-ca -keystore root-ca.p12 -storepass changeit -infile client.csr -outfile client.pem -rfc -validity 365 -ext "KU:critical=digitalSignature" -ext "EKU=clientAuth" -ext "BC=ca:false"
```

Import the root before importing the certificate reply into the client keystore:

```shell
keytool -importcert -alias lab-ca -file root-ca.pem -keystore client.p12 -storepass changeit -noprompt
keytool -importcert -alias tls-client -file client.pem -keystore client.p12 -storepass changeit -noprompt
```

**Comparison:** `server.p12` contains **server private key + server certificate (`serverAuth`)**. `client.p12` contains **client private key + client certificate (`clientAuth`)**. Both chains lead to `lab-ca` solely to simplify the lab; in production you should not assume one CA issues every identity/purpose.

### 7.5. Create a dedicated truststore for the lab

```shell
keytool -importcert -alias lab-ca -file root-ca.pem -keystore truststore.p12 -storetype PKCS12 -storepass changeit -noprompt
```

In the lab, both server and client are configured to trust the root in `truststore.p12`. In one-way TLS, the **client** uses this truststore to verify the server. In mTLS, the **server** also uses it to verify the client. A truststore holds **public root certificates**, not the CA's private key.

### 7.6. Inspect certificate contents with keytool

```shell
keytool -printcert -file server.pem
keytool -printcert -file client.pem
keytool -list -v -keystore server.p12 -storetype PKCS12 -storepass changeit
keytool -list -v -keystore client.p12 -storetype PKCS12 -storepass changeit
keytool -list -v -keystore truststore.p12 -storetype PKCS12 -storepass changeit
```

In the output:

- Server certificate: `SAN DNSName: localhost` and `ExtendedKeyUsages serverAuth`.
- Client certificate: `ExtendedKeyUsages clientAuth`.
- KeyStore for each identity contains a `PrivateKeyEntry` under its alias.
- Truststore contains a `trustedCertEntry` for `lab-ca`.
- Each leaf's issuer matches the signing root; the root carries proper CA constraints.

**There is no fixed stdout for keytool commands**, because serial numbers, fingerprints, public keys, timestamps, and ASN.1 encodings vary per run. Compare **meaningful attributes** rather than matching long raw output verbatim.

---

## 8. Java 17+ runnable: server-authenticated TLS and mTLS

Create **`TlsHandshakeLab.java`** in the same directory as `server.p12`, `client.p12`, and `truststore.p12`. This is **one Java class run in two separate processes**: the server process listens on port 8443, and the client process connects to `localhost:8443`.

Two modes:

- `oneway`: server presents the server certificate; client verifies the chain and SAN hostname. **No client certificate is presented**.
- `mtls`: server enables `setNeedClientAuth(true)`; client loads `client.p12` and presents its client certificate when requested. Server verifies the client chain against `truststore.p12`.
- Both modes use **TLS 1.3** and the same test bytes `P`/`K`. Traffic keys and record encryption are handled by JSSE, not custom AES in the demo.
- The raw `SSLSocket` client code **enables `"HTTPS"` endpoint identification** before `startHandshake`, avoiding a very common security bug.

**Note:** `changeit` is hardcoded strictly so the lab matches the `keytool` commands; production must use protected secret injection/keystore access. This is a **minimal TLS learning app**, not an HTTP server, and lacks certificate revocation services, IAM, ACLs, auditing, timeouts, or production rate limits.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class TlsHandshakeLab {
    private static final char[] PASSWORD =
            "changeit".toCharArray(); // ONLY FOR THE TRAINING LAB
    private static final String[] PROTOCOLS = {"TLSv1.3"};
    private static final int PORT = 8443;

    private static KeyStore loadStore(String path) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    // identityPath == null: this endpoint has no client identity.
    private static SSLContext context(String identityPath)
            throws Exception {
        KeyManager[] identities = null;

        if (identityPath != null) {
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(loadStore(identityPath), PASSWORD);
            identities = kmf.getKeyManagers();
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(loadStore("truststore.p12"));

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(identities, tmf.getTrustManagers(),
                new SecureRandom());
        return context;
    }

    private static void runServer(boolean mutual) throws Exception {
        SSLContext context = context("server.p12");
        try (SSLServerSocket listener = (SSLServerSocket)
                context.getServerSocketFactory()
                        .createServerSocket(PORT)) {
            listener.setEnabledProtocols(PROTOCOLS);
            listener.setNeedClientAuth(mutual);

            // One connection, one request byte: minimal lab only.
            try (SSLSocket socket = (SSLSocket) listener.accept()) {
                socket.setEnabledProtocols(PROTOCOLS);
                socket.startHandshake();

                boolean clientCertificateSeen;
                try {
                    clientCertificateSeen =
                            socket.getSession()
                                    .getPeerCertificates().length > 0;
                } catch (SSLPeerUnverifiedException expected) {
                    clientCertificateSeen = false;
                }

                int request = socket.getInputStream().read();
                if (request != 'P') {
                    throw new IOException("Unexpected demo request");
                }
                socket.getOutputStream().write('K');
                socket.getOutputStream().flush();

                System.out.println("mode="
                        + (mutual ? "mtls" : "oneway"));
                System.out.println("serverHandshake=success");
                System.out.println("protocol="
                        + socket.getSession().getProtocol());
                System.out.println("clientCertificateSeen="
                        + clientCertificateSeen);
                System.out.println("received=P");
            }
        }
    }

    private static void runClient(boolean mutual) throws Exception {
        // One-way client has no private-key identity to present.
        SSLContext context = context(mutual ? "client.p12" : null);
        try (SSLSocket socket = (SSLSocket)
                context.getSocketFactory()
                        .createSocket("localhost", PORT)) {
            socket.setEnabledProtocols(PROTOCOLS);

            // Critical: raw SSLSocket must check intended server name.
            SSLParameters params = socket.getSSLParameters();
            params.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(params);
            socket.startHandshake();

            boolean serverCertificateSeen =
                    socket.getSession()
                            .getPeerCertificates().length > 0;
            socket.getOutputStream().write('P');
            socket.getOutputStream().flush();

            int reply = socket.getInputStream().read();
            if (reply != 'K') {
                throw new IOException("Unexpected demo response");
            }
            System.out.println("mode="
                    + (mutual ? "mtls" : "oneway"));
            System.out.println("clientHandshake=success");
            System.out.println("protocol="
                    + socket.getSession().getProtocol());
            System.out.println("serverCertificateSeen="
                    + serverCertificateSeen);
            System.out.println("reply=K");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2
                || !("server".equals(args[0])
                     || "client".equals(args[0]))
                || !("oneway".equals(args[1])
                     || "mtls".equals(args[1]))) {
            System.err.println(
                    "Usage: java TlsHandshakeLab server|client oneway|mtls");
            return;
        }

        boolean mutual = "mtls".equals(args[1]);
        if ("server".equals(args[0])) {
            runServer(mutual);
        } else {
            runClient(mutual);
        }
    }
}
```

**Compile** once:

```shell
javac TlsHandshakeLab.java
```

### 8.1. Run one-way TLS

Open **terminal 1** in the lab directory:

```shell
java TlsHandshakeLab server oneway
```

Open **terminal 2** in the same directory, after the server is bound and listening:

```shell
java TlsHandshakeLab client oneway
```

**Expected stdout on the server terminal:**

```text
mode=oneway
serverHandshake=success
protocol=TLSv1.3
clientCertificateSeen=false
received=P
```

**Expected stdout on the client terminal:**

```text
mode=oneway
clientHandshake=success
protocol=TLSv1.3
serverCertificateSeen=true
reply=K
```

**Explanation:** The client receives the server certificate, JSSE verifies the chain against the root in `truststore.p12` and checks the `localhost` endpoint hostname thanks to `setEndpointIdentificationAlgorithm("HTTPS")`. The server **does not request** a client certificate, and the client loads no private key; hence `clientCertificateSeen=false`. A one-way TLS connection still encrypts and authenticates post-handshake traffic, yet the server has **no TLS-level client identity**.

### 8.2. Run mTLS

Wait for both processes from the one-way run to finish. Then reopen **terminal 1**:

```shell
java TlsHandshakeLab server mtls
```

In **terminal 2**:

```shell
java TlsHandshakeLab client mtls
```

**Expected stdout on the server terminal:**

```text
mode=mtls
serverHandshake=success
protocol=TLSv1.3
clientCertificateSeen=true
received=P
```

**Expected stdout on the client terminal:**

```text
mode=mtls
clientHandshake=success
protocol=TLSv1.3
serverCertificateSeen=true
reply=K
```

**Explanation:** The server enabled `setNeedClientAuth(true)` so JSSE sends a client certificate request. The client picks the key/cert from `client.p12`, and the server checks the chain back to the root in `truststore.p12` and client authentication purpose per JSSE/provider. The client still checks the server hostname and chain. Each side proves possession during the handshake per TLS 1.3. Both sides communicate over an authenticated and encrypted record layer.

**To avoid misinterpretation:** The line `clientCertificateSeen=true` is merely an **observation after the JSSE handshake succeeds**; it is not business authorization. A production server must retrieve the authenticated principal/certificate from a trusted context, map it to a structured identity, and enforce ACL/IAM/tenant policy.

### 8.3. Try important failure cases

**Test 1 – Server requires mTLS, but client lacks a certificate.**

Server terminal:

```shell
java TlsHandshakeLab server mtls
```

Client terminal:

```shell
java TlsHandshakeLab client oneway
```

Expected: **no matching pair of success stdout outputs**. The server rejects the certificate-less client and throws an appropriate handshake/protocol exception; the client may also observe an error during handshake or subsequent read/write. **Do not hardcode exact exception text** because TLS 1.3 alert delivery, providers, and socket close ordering can differ.

**Test 2 – Client trusts a different CA.** Replace the truststore with another valid truststore that does not contain the `lab-ca` root in your test environment. The JSSE client cannot build a trust path for the server leaf, so the handshake fails (typically with `PKIX path building failed` or equivalent). Never fix this by installing a `TrustManager` that accepts all certificates.

**Test 3 – Hostname mismatch.** Temporarily change `createSocket("localhost", PORT)` to `createSocket("127.0.0.1", PORT)` while keeping the server cert with only SAN `DNS:localhost`. With endpoint identification enabled, the client must reject the connection because there is no matching `iPAddress` SAN for `127.0.0.1`. **Do not** fix this by disabling hostname verification; reissue the certificate with the SAN matching actual needs.

**Test 4 – Client certificate with `serverAuth` instead of `clientAuth`.** If the server trust manager enforces purpose checks as standard JSSE does, a certificate with the wrong purpose will be rejected. Never reuse a server certificate as a client identity just to work around a config error.

**Test 5 – Expired or revoked certificate.** An expired certificate must be rejected per validity policy; revocation checking depends on OCSP/CRL/trust manager configuration and must be tested separately. This demo **does not enable formal revocation checking**. An unexpired certificate must not be accepted automatically when reliable revocation information exists.

### 8.4. What does the demo intentionally omit?

- Multiple concurrent connections, timeouts, size limits, request parsing, or an HTTP server.
- KMS/HSM, secret manager, certificate enrollment/renewal, multi-tier CA chains, role-based authorization, audit logging, or production revocation policy.
- The hardcoded store password is valid only for learning; never hardcode any password or key into a deployed JAR.
- Client truststore and server truststore share the same root here; production may separate trusted server CAs from trusted client CAs.
- `TlsHandshakeLab` does not by itself prevent replay of **HTTP/business actions**. While the TLS record layer protects integrity and ordering within a session, a valid HTTP request can be re-sent as a new request if business logic lacks transaction IDs or idempotency controls.
- The demo forces TLS 1.3 for clear handshake observation. Legacy peers require an explicit compatibility policy rather than arbitrarily disabling security.

---

## 9. From handshake to identity and authorization in the application

### 9.1. Example: mTLS between two microservices

Suppose service `billing-worker` calls `payment-api`:

```text
billing-worker                      payment-api
(client)                            (server)

client truststore                   server keystore
  trusts payment CA                   private key + serverAuth cert
client keystore                     server truststore
  private key + clientAuth cert        trusts workload CA
        |                                    |
        +--- mTLS TLS 1.3 handshake --------+
        |                                    |
        | server authenticated              |
        | client authenticated              |
        |                                    |
        +--- POST /refund ------------------>|
                                              |
                                  map verified client principal
                                  check role=refund-writer
                                  check tenant and amount policy
                                              |
        |<--- authorized response ----------+
```

If the server only checks the certificate chain without checking roles or tenants, **every service** issued a certificate under the workload CA could effectively act as a trusted admin. mTLS strengthens connection-level identity; business policy remains the server's decision.

### 9.2. What can certificate identity be?

Depending on the PKI profile:

- **DNS SAN**: appropriate for servers/hostnames per service identity rules.
- **URI SAN**: used in many workload identity systems, such as SPIFFE IDs; requires proper URI validation and separate trust domain checks.
- **Subject DN**: usable for organizations/people, though you should not rely on an unrestricted CN if the PKI does not enforce uniqueness/identity policy.
- **OtherName/email/IP SAN**: carries type-specific semantics; never collapse everything into a string `contains(...)`.
- **Certificate fingerprint/public key pinning**: can bind a specific key to a system, though rotation is complex and does not replace authorization.

The identity read in code via `SSLSession.getPeerPrincipal()` must be mapped according to organizational PKI standards—never let a client pick an arbitrary DN and gain permissions.

### 9.3. Separating security boundaries

An API request may traverse:

1. TLS termination at public ingress (server authentication).
2. mTLS between ingress and internal services.
3. mTLS between sidecars in a service mesh.
4. End-user authentication tokens.
5. Authorization checks on user/tenant/object/action.

Each hop has distinct identity and trust policies. **mTLS between proxy and app does not authenticate the end user**, and a valid bearer token does not replace verifying the TLS server identity when calling a partner.

### 9.4. mTLS rotation and revocation

Workload certificates are typically short-lived and automatically reissued:

- The CA enforces an **issuance policy** verifying workload identity before issuing a cert.
- Agents/proxies rotate private keys/certs with safe overlap, reloading `SSLContext`/keystores if required by the framework.
- Peers update trust bundles / CA rotations in a controlled manner; never remove an old CA before dependent certificates expire or migrate.
- **Existing** TLS connections may not terminate immediately when a certificate is revoked or expires after the handshake; servers need session lifecycles, reauthentication, or connection draining per security policy.
- Revocation via CRL/OCSP has varying practicality for very short-lived workload certs; system design must account for the capabilities of the exact TLS stack.

**Rotating a server certificate** does not automatically close all old TLS sessions; **rotating a client certificate** does not automatically revoke access for an identity whose private key was copied. If a private key is compromised, assess scope, replace identity/key material, update trust policy, invalidate sessions, and investigate potential exposure.

---

## 10. Diagnostic map for TLS and mTLS errors in Java

| Symptom | Common cause | Correct way to check |
| --- | --- | --- |
| `PKIX path building failed` / `unable to find valid certification path` | Untrusted CA, missing intermediate, wrong truststore config | Check server chain, client truststore, right CA; never trust-all |
| `No subject alternative names matching IP address` | Connecting via IP literal when cert only has DNS SAN or lacks IP SAN | Issue proper `iPAddress` SAN or connect using the certified DNS name |
| `No name matching ... found` | Endpoint hostname does not match SAN | Check URL/SNI/host and SAN; do not disable hostname verification |
| `bad_certificate` / `certificate_unknown` | Invalid certificate or rejected by peer | Check chain, alias, EKU/KU, validity times, CA policy |
| `certificate_required` | Server requires client cert but client did not present an eligible certificate | Load client `KeyManager` and PKCS12 containing private key + chain |
| `Empty client certificate chain` | Client has no matching credential or lacks a key entry | Check `client.p12`, alias, CA hints, and key manager |
| `handshake_failure` | No intersection of TLS protocol/cipher/signature, mismatched cert/key, or auth error | Check `supported_versions`, schemes, provider, certificate policy |
| `protocol_version` | One side does not support the version required by the other | Check JDK, enabled protocols, and compatibility policy |
| `No appropriate protocol` | TLS 1.3 disabled or unsupported by policy/provider | Check `jdk.tls.disabledAlgorithms` and JSSE configuration |
| `UnrecoverableKeyException` | Wrong private-key entry password or corrupted keystore | Check secure password, alias/entry type/provider |
| `FileNotFoundException` loading store | Java working directory differs from where files were created | Check working directory and keystore file paths |
| `BindException: Address already in use` | Port 8443 is busy or a previous lab server is still running | Stop the previous process and run only one lab server |
| `SSLPeerUnverifiedException` on one-way server | Server did not request or verify a client cert | Expected for one-way; mTLS requires `needClientAuth` |
| Client handshake succeeds, but API returns `403` | Valid TLS identity lacks business permission | Check role/tenant/resource policy |
| TLS 1.3 resumption shows no new `Certificate` | PSK/session resumption replaced a full certificate handshake | Check session mode, ticket/PSK, and identity binding |
| Valid certificate, yet connection is still blocked | Revocation, policy, hostname, algorithm, KU/EKU, or app authorization | Inspect every layer instead of checking only validity dates |

### 10.1. Viewing handshake debug logs

Java 17 can enable JSSE debugging in a **lab environment**:

```shell
java -Djavax.net.debug=ssl,handshake TlsHandshakeLab client mtls
```

The output consists of many debug lines varying by JDK/provider/config, with **no fixed stdout**. You can observe TLS version, certificate requests, selected signature algorithms, alerts, and certificate path info. Avoid leaving verbose debugging enabled in production because logs can expose identities, endpoints, metadata, and other sensitive details.

**Follow the right order when debugging:**

1. Verify the client is calling the **right hostname and port**.
2. Compare the leaf/server certificate's SAN with the requested hostname.
3. Check trusted CA roots and chain intermediates on the **verifying side**.
4. Check `serverAuth`/`clientAuth` purposes and signature/key algorithms.
5. Check whether the server actually requests mTLS (`CertificateRequest`, need vs. want).
6. Check that the client keystore holds an eligible `PrivateKeyEntry` and the key manager selects the right alias.
7. Check TLS versions/cipher suites/trust manager first, and only then examine business authorization.

Never diagnose by turning off hostname checks, trusting all CAs, or accepting every client certificate just to "get it working".

### 10.2. Errors can surface asymmetrically

When an mTLS server rejects a client without a certificate, the **server may send a TLS fatal alert and throw `SSLHandshakeException`**. Depending on when the alert arrives and how TLS 1.3 buffering behaves, the client may observe the error during `startHandshake`, on write, or when reading the response. Therefore, **do not rely on a single exact exception string** to determine protocol correctness; log conditions safely and verify actual outcomes at both endpoints.

### 10.3. TLS and application data after the handshake

A successful `startHandshake()` only indicates that the TLS channel was established per JSSE policy. The application layer must still implement:

- request size limits/timeouts, parser/schema validation;
- user/service-level authentication and authorization;
- replay controls/idempotency for state-changing operations;
- per-tenant/per-object permission checks;
- protecting secrets after TLS decryption and before sending responses;
- monitoring and response for certificate/key compromise.

---

## 11. Configuration patterns to avoid

### 11.1. Trust-all certificate manager

**Never use code like this in production, even "just temporarily":**

```java
// ANTI-PATTERN: rejects nothing and destroys peer authentication.
TrustManager[] trustAll = new TrustManager[]{
    new X509TrustManager() {
        public void checkClientTrusted(
                X509Certificate[] chain, String authType) {}
        public void checkServerTrusted(
                X509Certificate[] chain, String authType) {}
        public X509Certificate[] getAcceptedIssuers() {
            return new X509Certificate[0];
        }
    }
};
```

This is an **intentionally non-standalone snippet to recognize an anti-pattern**, not code to use. Skipping chain verification means an attacker can present their own certificate and still be trusted. Fix the truststore or certificate chain rather than replacing the trust manager with one that accepts every peer.

### 11.2. Always-true hostname verifier

```java
// ANTI-PATTERN: do not use!
HostnameVerifier unsafe = (host, session) -> true;
```

Using this shortcut skips verification of the intended host, opening the door to MITM attacks even when some CA signed the certificate. On raw `SSLSocket`, use `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`; in standard HTTP clients, keep TLS/hostname verification enabled.

### 11.3. Attaching a `clientAuth` certificate without enforcing client identity

A server might call `setWantClientAuth(true)` and then trust any request passing over TLS. That does not enforce mandatory mTLS; clients without certificates are still accepted. Use `needClientAuth` or an equivalent policy when client certificates are mandatory, and **enforce identity→permission mapping**.

### 11.4. Using one root CA as the entire authorization model

A root authorized to sign certificates for multiple services does not mean every service is allowed to call admin endpoints. Use certificate profiles/purposes, trust-domain segmentation, and application-layer authorization. Bind to a stable service identity rather than relying solely on a Subject CN that could be arbitrarily claimed under a weak issuance process.

### 11.5. Verifying the right certificate on the wrong target

If a proxy connects to `api.example.com` while the HTTP client requested `payments.example.com`, do not arbitrarily treat the verified identity of one host as valid for the other. SAN, SNI, HTTP `:authority`, routing, and service policy must agree per protocol.

---

## 12. Self-check questions with answers

**1. In one-way TLS, is the client required to send a certificate?**  
No. The typical model is client authenticating the server; client identity may be authenticated after TLS using tokens/cookies. The server may have no client TLS principal.

**2. In mTLS, can the client skip server certificate validation because the server already requested a client certificate?**  
No. mTLS requires **both** sides to authenticate their peer properly. The client must still trust the right server CA and check SAN/hostname.

**3. Does `ClientHello` prove client identity?**  
No. `ClientHello` advertises capabilities/key shares/SNI, etc.; client certificate authentication requires the proper handshake messages and proof-of-possession when enabled by the server.

**4. What is the role of `CertificateVerify` in TLS 1.3?**  
The sender uses the private key corresponding to its certificate to sign a protocol-defined transcript structure, proving control of a valid key for the handshake. Sending a public certificate alone is not enough.

**5. What is the role of `Finished`?**  
It binds and verifies handshake transcript integrity against the derived secrets/key schedule, detecting unauthorized tampering and completing handshake authentication.

**6. Does mTLS prove the client is authorized to issue a refund?**  
No. It verifies service identity; the server must map the principal and check ACL/IAM/tenant/amount rules.

**7. In Java, how do `KeyManagerFactory` and `TrustManagerFactory` differ?**  
Key manager supplies **your own** private key/cert when needed; trust manager verifies the **peer's** cert against trust anchors/policy.

**8. A server enables `setNeedClientAuth(true)` without configuring a client truststore. What can happen?**  
The server may fail to verify the client chain or fall back to an unintended trust configuration; you must configure the right client-issuing root CA and identity policy.

**9. Why must a raw `SSLSocket` use `setEndpointIdentificationAlgorithm("HTTPS")`?**  
So JSSE checks that the server certificate matches the target name per endpoint identification rules. A valid chain with the wrong hostname is still insecure.

**10. If a server cert has SAN `DNS:localhost`, is a client connecting via IP literal `127.0.0.1` valid?**  
No, under strict IP identity checks if the certificate lacks SAN `iPAddress:127.0.0.1`. Switch to the certified hostname or issue a certificate with the right SAN type.

**11. Why does TLS 1.3 provide forward secrecy in a full ECDHE handshake?**  
Traffic secrets are derived from ephemeral key agreement; later compromise of the certificate signing private key does not recreate ephemeral shared secrets that were properly handled and erased.

**12. Is `setWantClientAuth(true)` the same as `setNeedClientAuth(true)`?**  
No. `want` is an optional request; `need` mandates valid client certificate authentication.

**13. Does a client not sending a client certificate during session resumption automatically mean mTLS is absent?**  
No. Check whether it is a resumption/PSK session carrying identity bound from an earlier session or a full handshake. Verify your stack's reauthentication policy.

**14. Is 0-RTT safe for all money-transfer `POST` operations?**  
No. Early data carries replay risk; replay protection/idempotency and strict business checks are required.

**15. Will placing only a PEM certificate in the server directory allow the server to complete handshakes?**  
No. The server needs the **corresponding private key** and proper certificate chain/key manager; the client must trust the server's chain and identity.

**16. Does mTLS at a reverse proxy automatically make the Java app authenticate the end user's identity?**  
No. You need a trusted path passing the principal from proxy to app with protected headers/context; distinguish mTLS workload identity from user identity.

## 13. Checklist for secure TLS/mTLS deployment in Java

- [ ] **Protocol:** prefer TLS 1.3 per compatibility; remove weak versions/cipher suites per policy.
- [ ] **Server key/cert:** valid private key and leaf chain; SAN matches host; `serverAuth` EKU, proper KU/policy; managed rotation and file/KMS permissions.
- [ ] **Client trust:** trust only approved CAs/trust anchors, keep JSSE chain validation and HTTPS endpoint identity active; never trust-all or bypass hostnames.
- [ ] **Client identity (mTLS):** client has `clientAuth` private key + leaf/chain selected by proper alias; server requires cert (need vs. want) and trusts the right client CA.
- [ ] **Proof-of-possession:** verify handshake signatures, `Finished`, and traffic key derivation through a standard TLS stack; never simulate handshakes manually with Java RSA/AES.
- [ ] **Authorization:** map verified client identity → principal/role/tenant; check every API/resource/action; never trust merely because a client cert exists.
- [ ] **Key lifecycle:** provisioning, PKCS12/KMS/HSM management, rotation, revocation, auditing, managing client/server roots, and reauthenticating live sessions.
- [ ] **Network/architecture:** define where TLS terminates; authenticate proxy headers; protect ingress/backend/mesh hops appropriately.
- [ ] **Session nuances:** understand full handshake vs. resumption, client-auth policy on resume, and 0-RTT/replay.
- [ ] **Logging:** log protocol/cipher/version/identity/outcome with controls; never log private keys, passwords, or sensitive decrypted payloads.
- [ ] **Testing:** verify one-way and mTLS success; missing client cert, wrong server hostname, untrusted CA, wrong server/client EKU, expiration, revocation policy, spoofed identity, and permission denied.
- [ ] **Recovery:** have paths for key/certificate renewal, controlled rollback, and CA compromise handling—never turn off verification during a certificate incident.

**Conclusion:** In **one-way TLS**, the client authenticates the server; in **mTLS**, the server also authenticates the client's certificate and private-key possession. Even after a successful handshake, **application authorization**, key/certificate lifecycle, hostname identity, and post-decryption data protection remain separate responsibilities.

## 14. Authoritative references

- [RFC 8446 – The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): `ClientHello`/`ServerHello`, `CertificateRequest`, `CertificateVerify`, `Finished`, HKDF key schedule, record protection, resumption, and early data.
- [RFC 5246 – The Transport Layer Security (TLS) Protocol Version 1.2](https://www.rfc-editor.org/rfc/rfc5246): TLS 1.2 handshake structure and key exchange/record protection differences.
- [RFC 5280 – Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate path validation, CA constraints, SAN, KeyUsage, ExtendedKeyUsage, and CRL.
- [RFC 9525 – Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): rules for verifying server/service identity by name in TLS.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): TLS/JSSE, `SSLContext`, key/trust managers, `SSLSocket`/`SSLEngine`, endpoint identification, and debugging.
- [Java SE 17 – SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html), [SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html), and [SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): configuring handshakes, clientAuth, and hostname endpoint identification.
- [Java SE 17 – KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html), [TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html), and [KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): local TLS identity vs. peer trust configuration.
- [JDK 17 keytool manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): commands to generate PKCS12 key pairs, CSRs, certificate replies, and trusted roots.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS configuration, certificate verification, and operational anti-patterns.