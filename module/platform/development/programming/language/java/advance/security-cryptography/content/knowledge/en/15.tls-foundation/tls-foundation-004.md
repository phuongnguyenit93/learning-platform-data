# 15.4 Cipher Suites and Differences in Negotiated Components Across TLS Versions

When a Java application connects over HTTPS, gRPC, or a TLS-secured TCP service, the two sides do not simply "turn on TLS" and exchange data. They must agree on the **protocol version, record protection algorithm, key establishment method, and authentication mechanism**. Part of this is described by the **cipher suite**. However, **TLS 1.2 and TLS 1.3 define the meaning of a cipher suite in fundamentally different ways**.

In TLS 1.2, a cipher suite name usually specifies both the **key exchange / server authentication mechanism**, the record encryption algorithm, and the MAC or PRF algorithm. In TLS 1.3, the cipher suite primarily selects the **record AEAD** and the **hash used in HKDF/key schedule**; the **key exchange group** and **signature algorithm** are negotiated separately via extensions. Therefore, reading a TLS 1.3 name as if it were a TLS 1.2 name leads to misconfigurations, wrong log analysis, and sometimes misunderstanding security posture.

This lesson explains TLS 1.2 and TLS 1.3 negotiation in detail, how to read suite names, the roles of ClientHello/ServerHello, certificates, `supported_groups`/`key_share`/`signature_algorithms`, PFS, ALPN, incompatibility scenarios, and how to inspect them in Java 17+ JSSE. Two compilable, runnable Java examples help distinguish **supported**, **enabled**, and **actually negotiated**.

## 1. What does TLS negotiate?

**TLS (Transport Layer Security)** protects the communication channel between two endpoints. In typical configurations, TLS requires:

1. **Protocol version:** TLS 1.2 or TLS 1.3, governing handshake structure, key schedule, and record protection.
2. **Record-protection algorithm:** how data is encrypted, authenticated, and tamper-detected, e.g., AES-GCM or ChaCha20-Poly1305.
3. **Key establishment:** how both sides produce traffic secrets, typically using ephemeral (EC)DHE; TLS 1.3 also supports PSK and PSK+(EC)DHE.
4. **Peer authentication:** how the receiver verifies the server (and optionally the client), typically via X.509 certificates and digital signatures; or via PSK per configuration.
5. **Key derivation / transcript integrity:** key derivation algorithm, transcript hash, and Finished to bind handshake steps together.
6. **Application-layer metadata:** SNI to select a virtual host; ALPN to select HTTP/2, HTTP/1.1, or another application protocol. These are separate extensions/policies, **not part of the cipher suite name**.

~~~text
Java Application (HTTPS, gRPC, TCP/TLS)
                   |
             JSSE / SSLEngine
                   |
        +----------+----------------------------+
        |                                       |
   TLS handshake                            TLS records
        |                                       |
protocol + cipher suite                  traffic keys/nonce
key exchange + authentication            AEAD / record integrity
SNI + ALPN + transcript                  protected application data
        |
        v
  SSLSession: SELECTED protocol and cipher suite
~~~

**A cipher suite is not equivalent to the entire TLS security profile.** A connection may record `TLS_AES_128_GCM_SHA256`, yet separate logs are still needed to determine the certificate/issuer, key exchange group, signature scheme, ALPN, and TLS endpoint policy for a complete assessment.

### 1.1. Three frequently confused states

| Concept | Meaning | Common Java APIs |
| --- | --- | --- |
| **Supported** | The implementation/provider can support the algorithm or version | `SSLContext.getSupportedSSLParameters`, `SSLSocket.getSupportedCipherSuites` / `getSupportedProtocols`. |
| **Enabled** | Choices enabled in the endpoint configuration, potentially restricted by policy/provider | `SSLContext.getDefaultSSLParameters`, `SSLSocket.getEnabledCipherSuites` / `getEnabledProtocols`. |
| **Negotiated** | **A specific choice selected by both sides after a successful handshake** | `SSLSocket.getSession().getCipherSuite()`, `getSession().getProtocol()`. |

**Supported does not guarantee enabled; enabled does not guarantee negotiated.** If the peer lacks support, the certificate does not match, groups/key shares are missing, or algorithm constraints disallow it, the handshake can fail. The final outcome also depends on the provider, JDK config, key material, and both sides' policies.

## 2. How to read cipher suite names in TLS 1.2

A common structure of TLS 1.2 suites:

~~~text
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
|    |     |         |   |   |   |
|    |     |         |   |   |   +--> PRF hash: SHA-256
|    |     |         |   |   +------> AES mode GCM (AEAD)
|    |     |         |   +----------> 128-bit AES key
|    |     |         +--------------> record encryption algorithm
|    |     +------------------------> RSA-based server authentication
|    +------------------------------> Ephemeral EC Diffie–Hellman key agreement
+-----------------------------------> TLS cipher suite name prefix
~~~

This is an interpretation of a specific name, not a grammar covering every historical cipher suite: some suites use RSA key transport, static DH, PSK, CBC/HMAC, or other variants.

**TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** means:

- **ECDHE:** both sides perform **ephemeral Elliptic Curve Diffie–Hellman** to produce a shared secret. Ephemeral key agreement provides **forward secrecy** when properly implemented.
- **RSA:** the server proves possession of the certificate's **RSA private key** by signing the handshake (authentication). **It does not mean the client encrypts the premaster secret with the RSA public key** in an `ECDHE_RSA` suite.
- **AES_128_GCM:** record protection uses AES-128-GCM from the **AEAD** family, protecting both confidentiality and integrity.
- **Trailing SHA256:** per RFC 5289, this is the **TLS 1.2 PRF hash** for this GCM suite. **It is not an independent HMAC-SHA256 computed over every record**, because GCM already has its own authentication tag.

### 2.1. Comparing several TLS 1.2 suites

| TLS 1.2 suite name | Key establishment / authentication | Data protection | Notes |
| --- | --- | --- | --- |
| **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** | Ephemeral ECDH, RSA server certificate | AES-128-GCM AEAD | ECDHE gives PFS; SHA256 is the PRF hash. |
| **TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256** | Ephemeral ECDH, ECDSA server certificate | AES-128-GCM AEAD | ECDHE is key exchange, ECDSA is signing/authentication. |
| **TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384** | Ephemeral ECDH, RSA authentication | AES-256-GCM AEAD | SHA384 is the PRF hash per profile. |
| **TLS_RSA_WITH_AES_128_GCM_SHA256** | RSA key transport and RSA authentication | AES-128-GCM AEAD | **No PFS** due to RSA key transport; do not use for new designs. |
| **TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA** | Ephemeral ECDH, RSA authentication | AES-CBC + HMAC-SHA1 | Legacy CBC/MAC; requires careful padding-oracle handling—avoid when better AEAD exists. |

Names in this table are **not automatically enabled** on every Java runtime. An algorithm supported by a provider can be disabled by **`jdk.tls.disabledAlgorithms`**, certificate policy, missing key material, or application configuration.

### 2.2. Why `_SHA` and `_SHA256` do not always mean the same thing

In **TLS 1.2 CBC suites**, a suffix like **_SHA** can identify HMAC-SHA1 used for the record MAC, while the TLS 1.2 PRF follows the specified hash (usually SHA-256). In **TLS 1.2 AEAD/GCM suites** like `ECDHE_RSA_WITH_AES_128_GCM_SHA256`, the **GCM authentication tag** replaces the record HMAC function; **SHA256** specifies the PRF hash.

**Never see SHA256 and conclude records use HMAC-SHA256**, and never see `_RSA` and conclude RSA key exchange is in use. Analyze the **full scheme** per the suite specification.

## 3. How does TLS 1.2 negotiate key exchange and authentication?

A TLS 1.2 full handshake using certificates and ECDHE can be pictured as:

~~~text
Client                                           Server
  |                                                |
  | ClientHello: version, suites, groups, extensions|
  |----------------------------------------------->|
  |                                                |
  |       ServerHello: version, chosen cipher suite|
  |       Certificate (RSA/ECDSA per suite)        |
  |       ServerKeyExchange: ephemeral params + sig|
  |       ServerHelloDone                           |
  |<-----------------------------------------------|
  | ClientKeyExchange: ephemeral key share          |
  | ChangeCipherSpec + Finished                     |
  |----------------------------------------------->|
  |                  ChangeCipherSpec + Finished    |
  |<-----------------------------------------------|
  |            application data protected           |
~~~

This is a **simplified diagram** for a TLS 1.2 full handshake using ECDHE; extensions, certificate requests/client authentication, and resumed handshakes alter the messages. The **ServerKeyExchange** line is crucial for ECDHE, because the server must bind the ephemeral parameters with an appropriate signature/authentication mechanism.

- **ClientHello** advertises acceptable cipher suites, versions, and extensions.
- **ServerHello** selects an eligible suite from the client's list and server policy.
- The ECDHE and certificate parts must be **compatible with the key exchange and authentication chosen in the suite**.
- Both sides compute key material and verify the handshake transcript/Finished; on mismatch or untrusted certificate, the handshake fails.
- **ALPN** can be negotiated via an independent extension; a TLS 1.2 connection can carry HTTP/2 or HTTP/1.1 depending on policy and configuration.

If the server only has an ECDSA certificate, it cannot simply pick an **ECDHE_RSA** suite without an RSA key and matching authentication capability. Conversely, a TLS 1.2 **ECDHE_ECDSA** suite requires a matching ECDSA certificate and signing capability.

### 3.1. RSA key transport vs. ECDHE_RSA

| TLS 1.2 mechanism | Role of RSA | Forward secrecy if certificate private key is later compromised? |
| --- | --- | --- |
| **TLS_RSA_...** | Client encrypts premaster secret with server's RSA public key | **No**, because captured handshake records can later be decrypted with the leaked RSA private key. |
| **TLS_ECDHE_RSA_...** | RSA private key signs/authenticates ephemeral ECDHE handshake | **Can provide PFS** when ephemeral secrets are safely handled and erased. |

Therefore, **"having RSA in the name" is not enough to know whether PFS applies**. Distinguish **TLS_RSA_** from **TLS_ECDHE_RSA_**.

## 4. TLS 1.3 redefines cipher suites from scratch

RFC 8446 makes a major change: a **TLS 1.3 cipher suite** specifies the **pair (AEAD for record protection, hash used for HKDF)**, and **does not encode key exchange or authentication in the suite name**.

~~~text
TLS_AES_128_GCM_SHA256
|   |   |   |   |
|   |   |   |   +--> SHA-256 hash for HKDF and handshake transcript
|   |   |   +------> GCM mode
|   |   +----------> 128-bit AES key
|   +--------------> AEAD algorithm for TLS records
+------------------> TLS cipher suite
~~~

**TLS_AES_128_GCM_SHA256** does not indicate whether the server uses an RSA, ECDSA, or Ed25519 certificate, nor whether the key exchange group is X25519 or P-256. Those components are negotiated **separately**, so **the same TLS 1.3 suite can work with many allowed certificate types and groups**.

### 4.1. Suites defined by RFC 8446

| TLS 1.3 cipher suite | AEAD / protection | Hash for HKDF / transcript | Remarks |
| --- | --- | --- | --- |
| **TLS_AES_128_GCM_SHA256** | AES-128-GCM | SHA-256 | Common, can leverage AES hardware acceleration. |
| **TLS_AES_256_GCM_SHA384** | AES-256-GCM | SHA-384 | 256-bit AES key; requires matching support/policy. |
| **TLS_CHACHA20_POLY1305_SHA256** | ChaCha20-Poly1305 | SHA-256 | Suitable for environments without fast AES acceleration. |
| **TLS_AES_128_CCM_SHA256** | AES-128-CCM | SHA-256 | Defined by RFC; support depends on implementation. |
| **TLS_AES_128_CCM_8_SHA256** | AES-128-CCM 8-byte tag | SHA-256 | Short-tag profile; requires checking policy and application limits. |

This is the **initial list of TLS 1.3 suites defined by RFC 8446**, not a guarantee that the current Java runtime/provider supports or enables all of them. Later RFCs may register additional cipher suites; real-world evaluation must rely on registries, relevant standards, and deployment policy.

### 4.2. What is SHA256 in a TLS 1.3 name used for?

TLS 1.3 uses **HKDF** to derive **handshake traffic secrets, application traffic secrets, and keys/IVs** from the shared secret and handshake transcript. The cipher suite's hash is also used for the **transcript hash and Finished key schedule**.

**SHA-256 is not used as a separate record MAC** when AES-GCM is chosen: records are already authenticated by the **AEAD** authentication tag. Thus, from `TLS_AES_128_GCM_SHA256` we know AES-GCM and HKDF-SHA256, and **cannot infer the public key algorithm or certificate version**.

### 4.3. TLS 1.3 and TLS 1.2 suites are not interchangeable

Per RFC 8446:

- **TLS 1.3 cipher suites** such as `TLS_AES_128_GCM_SHA256` **are only used in TLS 1.3**.
- **TLS 1.2 suites** such as `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` **cannot be negotiated as TLS 1.3 suites**.
- Even though both names contain **AES_128_GCM_SHA256**, they are not merely two spellings of the same parameter set. One specifies key exchange/authentication in TLS 1.2; the other specifies only AEAD/HKDF hash in TLS 1.3.

This is why you must **never configure only TLS 1.2 suite names and expect TLS 1.3 to use them**. JSSE shares `setEnabledCipherSuites` across both versions, but developers must pick cipher suites **appropriate for each TLS protocol**.

## 5. What additional components does TLS 1.3 negotiate?

Per RFC 8446 §4.1.1, in a certificate-based connection (without choosing PSK), selection groups are largely independent:

1. **cipher_suites:** AEAD/HKDF hash pair.
2. **supported_groups + key_share:** supported (EC)DHE groups and actual key shares sent to establish the shared secret.
3. **signature_algorithms** (and optionally `signature_algorithms_cert`): signing algorithms accepted by the receiver for authentication and certificates.
4. **supported_versions:** TLS versions actually supported by the client.
5. If using PSK: **pre_shared_key + psk_key_exchange_modes** add an authentication/key-establishment path, changing the valid combination sets.

Additionally, **ALPN** can select an application protocol, and **server_name (SNI)** helps route virtual hosts/certificates. They **do not appear inside the cipher suite name**.

~~~text
TLS 1.3 ClientHello
 |
 +-- supported_versions: [TLS 1.3, TLS 1.2]
 +-- cipher_suites: [TLS_AES_128_GCM_SHA256, TLS_CHACHA20_POLY1305_SHA256, ...]
 +-- supported_groups: [X25519, secp256r1, ...]
 +-- key_share: key-share for one or more groups
 +-- signature_algorithms: [RSA-PSS, ECDSA, Ed25519, ...]
 +-- signature_algorithms_cert: optional
 +-- server_name / ALPN: e.g. api.example and h2/http1.1
 +-- PSK extensions: when using PSK/resumption
 |
 v
Server selects a compatible combination
 |
 +-- TLS version
 +-- one TLS 1.3 cipher suite (AEAD + hash)
 +-- group/key share (if using DHE)
 +-- cert + handshake signature scheme (if using certificate)
 +-- ALPN (if application uses it)
 |
 v
Handshake transcript -> HKDF traffic keys -> AEAD records
~~~

**Independence does not mean every combination works**. The server must possess a certificate/key compatible with the signature algorithms accepted by the client, supported groups and key shares, overlapping cipher suites, and provider/policy permission. TLS 1.3 requires a matching certificate key to emit `CertificateVerify`; a suite name **cannot rescue an invalid certificate**.

### 5.1. `supported_groups` and `key_share` are not the same

**supported_groups** is the set of key exchange groups the client supports; **key_share** is the public shares the client actually sent for specific groups.

For instance, the client supports **X25519 and secp256r1** but sends a `key_share` only for X25519. If the server prefers secp256r1 and both are compatible, the server can send a **HelloRetryRequest** asking the client to send a matching `key_share`. `HelloRetryRequest` is a transcript-bound handshake branch; it is not automatically an error or a request to "allow downgrade".

If no shared group exists for a connection requiring (EC)DHE, the handshake fails. However, TLS 1.3 **PSK-only** mode has different logic: it can omit (EC)DHE and therefore may not require overlapping `supported_groups`. Never infer PFS from the cipher suite alone.

### 5.2. `signature_algorithms` and certificates in TLS 1.3

A server may use:

- An **RSA public key** with a supported **RSA-PSS** profile to sign `CertificateVerify`.
- An **ECDSA P-256 public key** with a compatible signature scheme.
- **Ed25519** with the matching signature scheme, if both JSSE/provider and trust policy support it.

Alongside any of these profiles, the connection can still negotiate **TLS_AES_128_GCM_SHA256** for records. This is a memorable shift from TLS 1.2 **ECDHE_RSA** vs. **ECDHE_ECDSA** reflected in suite names.

**Detail to note:** the signature scheme for **CertificateVerify** and the signature algorithm used to sign **certificates in the certificate chain** are two distinct matters that can be governed by separate extensions/policies. In TLS 1.3, the cipher suite name dictates neither; never conclude "SHA256 in the suite name means the certificate must be signed with SHA-256".

### 5.3. TLS 1.3 1-RTT diagram with certificate

~~~text
Client                                            Server
  |                                                 |
  | ClientHello + supported_versions + suites       |
  | + supported_groups + key_share + signature_algs  |
  |------------------------------------------------>|
  |                                                 |
  |            ServerHello + selected suite/key_share|
  |            {EncryptedExtensions}                |
  |            {Certificate}                        |
  |            {CertificateVerify}                  |
  |            {Finished}                           |
  |<------------------------------------------------|
  | {Finished}                                      |
  |------------------------------------------------>|
  |        [Protected application data]             |
~~~

In RFC 8446 diagrams, braces **{ }** indicate handshake messages protected by **handshake traffic keys**; brackets **[ ]** indicate application data protected by **application traffic keys**. The figure omits optional client authentication, resumption/PSK, HelloRetryRequest, and other fields.

TLS 1.3 moves many handshake messages under encryption earlier than TLS 1.2, has an **HKDF-based key schedule**, and protects records with AEAD. **ChangeCipherSpec** may appear in compatibility mode, but must not be interpreted like the key-transition state in TLS 1.2.

### 5.4. 0-RTT/PSK is a security exception requiring separate scrutiny

TLS 1.3 allows **PSK resumption**, with or without DHE:

- **psk_dhe_ke:** uses PSK and (EC)DHE; can provide forward secrecy for applicable traffic when properly implemented.
- **psk_ke:** uses PSK only, **lacking forward secrecy** due to no ephemeral DHE.
- **0-RTT early data:** sends data before the handshake finishes, protected via PSK; **lacks cross-connection anti-replay guarantees** like normal 1-RTT, and early-data keys lack full forward secrecy.

Hence, stating **"TLS 1.3 always has PFS"** is an oversimplification. For APIs that mutate state such as money transfers, order creation, or coupon issuance, **do not treat 0-RTT as a guaranteed non-replayed fresh request**. When using 0-RTT, enforce replay/idempotency controls and adhere to application policy.

## 6. Comparison table of TLS 1.2 vs. TLS 1.3 by negotiated component

| Item | TLS 1.2 | TLS 1.3 |
| --- | --- | --- |
| **Cipher suite meaning** | Usually names key exchange/authentication, record cipher, MAC/PRF | Selects **AEAD + HKDF hash**; omits key exchange/certificate signature from name. |
| **Example suite** | `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | `TLS_AES_128_GCM_SHA256` |
| **Version negotiation** | Version fields/extensions per TLS 1.2; does not use TLS 1.3 `supported_versions` rules | **`supported_versions`** extension determines TLS 1.3; `legacy_version` holds a compatibility value. |
| **Key establishment** | RSA transport, (EC)DHE, or older methods per suite | (EC)DHE, PSK+(EC)DHE, PSK-only per profile/mode. |
| **Certificate/signature** | Closely tied to RSA/ECDSA part of suite name; `signature_algorithms` extension still matters | **`signature_algorithms`**, optionally `signature_algorithms_cert`; certificate/key chosen separately. |
| **Groups/key shares** | Supported curves/groups via extension and key exchange messages | **`supported_groups` + `key_share`**, `HelloRetryRequest` if another share is needed. |
| **Record protection** | Includes CBC/HMAC and AEAD depending on suite | Initially **AEAD** suites per RFC 8446; supplemental RFCs require separate review. |
| **Key schedule** | TLS 1.2 PRF, master secret, key expansion | **HKDF** combining handshake transcript and per-phase secrets. |
| **Forward secrecy** | Present with proper ECDHE/DHE; absent with static RSA key transport | Possible with (EC)DHE; **PSK-only and 0-RTT** lack the same guarantee. |
| **Handshake flow** | ServerHello, Certificate, ServerKeyExchange, ChangeCipherSpec, Finished per profile | ServerHello, EncryptedExtensions, CertificateVerify, Finished; early encrypted messages. |
| **Renegotiation** | Has mechanisms and historical risks; applications should restrict/control | **No TLS 1.2-style renegotiation**; has `KeyUpdate` and post-handshake authentication under specific conditions. |
| **ALPN/SNI** | Separate extensions, not part of cipher suite | Still separate extensions, not part of cipher suite. |
| **Resumption** | Commonly session ID/ticket per TLS 1.2 | PSK/ticket per TLS 1.3; optional 0-RTT if permitted. |

**Note on exceptions:** RFC 8446 originally defined AEAD-plus-hash suites for TLS 1.3; later extensions such as RFC 9150 define integrity-only TLS 1.3 suites. When saying "TLS 1.3 uses AEAD" in common HTTPS, understand that as the standard encrypted profile; do not claim every suite registered later encrypts content.

### 6.1. Same hash name, different purpose

**TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** (TLS 1.2):
- **SHA256** is used in the TLS 1.2 PRF per RFC 5289.
- **RSA** is the certificate/handshake authentication method.
- **ECDHE** specifies key establishment.
- **GCM** already handles the record authentication tag.

**TLS_AES_128_GCM_SHA256** (TLS 1.3):
- **SHA256** is used in HKDF/key schedule and transcript per RFC 8446.
- Does not specify whether the certificate uses RSA or ECDSA.
- Does not specify X25519 or P-256 group.
- Still uses AES-128-GCM to protect records.

Both include AES-128-GCM, yet **cipher suites cannot be swapped between the two versions**.

## 7. ALPN, SNI, certificates, and hostnames: outside the cipher suite name

### 7.1. ALPN

**Application-Layer Protocol Negotiation (ALPN)** selects the application protocol over TLS: e.g., client advertises `h2` and `http/1.1`, server picks an eligible protocol.

- ALPN **is not a TLS protocol version**: `h2` does not mean TLS 1.2, and `http/1.1` does not mean TLS 1.3.
- ALPN **is not a cipher suite**: the same `TLS_AES_128_GCM_SHA256` can serve permitted application protocols.
- ALPN configuration must match application policy: HTTP/2 has specific version and cipher suite constraints per its standard.
- In Java, **`SSLParameters.setApplicationProtocols`** configures the list; after the handshake, **`SSLSocket.getApplicationProtocol`** reports the negotiated protocol if supported by the implementation.

### 7.2. SNI

**Server Name Indication (SNI)** helps a multi-virtual-host server choose the right certificate and configuration. Never treat SNI as proof of hostname: the client must still verify **certificate chain + hostname** per endpoint identification and trust policy, especially on raw `SSLSocket`/`SSLEngine`.

- SNI can influence which certificate the server selects, thereby affecting signature schemes.
- Never assume a TLS 1.3 suite requires RSA because of a name: TLS 1.3 suite names never specify RSA.
- Java HTTPS libraries usually perform hostname verification by default; when using raw `SSLSocket`, apply **`SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`** and a proper trust manager rather than a TrustManager that accepts every certificate.

### 7.3. mTLS (mutual TLS)

TLS normally authenticates the **server**; a **client certificate** is optional per policy. In Java, the server can require it via **`SSLServerSocket.setNeedClientAuth(true)`** or `SSLParameters`. mTLS adds client identification, yet still requires application-layer authorization: a valid certificate does not equal permission to call every API.

## 8. Java JSSE: APIs related to cipher suites

Key classes in **`javax.net.ssl`**:

| API | What it does | Notes |
| --- | --- | --- |
| **SSLContext** | Configures key managers, trust managers, and randomness source; creates sockets/engines | `SSLContext("TLS")` does not force a single version. |
| **SSLSocketFactory / SSLServerSocketFactory** | Creates TLS client/server sockets | Each socket still has enabled settings. |
| **SSLSocket / SSLServerSocket** | Reads supported/enabled versions and suites, sets policy | `setEnabledCipherSuites` must use provider-supported names; cannot bypass algorithm constraints. |
| **SSLParameters** | Passes cipher suites/protocols, ALPN, endpoint identification, client auth... | Fields affect the handshake independently. |
| **SSLSession** | Records protocol and suite on an **established** connection | `getProtocol`/`getCipherSuite` are only handshake outputs, not the complete security profile. |
| **SSLEngine** | Transport-independent TLS state machine for async frameworks | Also exposes handshake status, supported/enabled, and `SSLSession`. |
| **KeyManagerFactory** | Supplies private keys/certificates | Key/certificate affects which signature schemes can be chosen. |
| **TrustManagerFactory** | Configures peer certificate verification | Never replace with trust-all in production. |

**Supported ≠ enabled ≠ negotiated** is an invariant when inspecting JSSE. **`SSLContext.getSupportedSSLParameters`** may list more protocols/suites than the defaults. **`setEnabledProtocols`** or **`setEnabledCipherSuites`** narrows the offered list, yet **does not guarantee handshake success** if the peer has no overlap or security policy blocks it.

### 8.1. Which version does `SSLContext.getInstance("TLS")` use?

**"TLS"** is a generic context name for the JSSE provider, capable of supporting multiple versions. The actual version is determined by **enabled protocols**, supported protocols, JDK policy, and peer negotiation. After **`startHandshake`**, read **`SSLSession.getProtocol()`**; never print `SSLContext.getProtocol()` and treat it as the connection's session protocol.

### 8.2. Should you pin a single cipher suite?

- **Benefits:** meets specific security policy, reproducible tests, excludes weak suites, controls compatibility.
- **Risks:** client/server have no overlap, mismatched certificate type, unsupported provider, or policy changes after a JDK upgrade.
- **Practice:** configure an **approved set of modern suites**, preferring TLS 1.3; retain TLS 1.2 ECDHE+AEAD when compatibility is needed. Avoid hardcoding a single suite without a clear requirement and thorough testing.

In integration tests, you can pin one suite to **prove two handshakes differ**, whereas production usually needs a flexible policy for valid clients and an upgrade path.

## 9. Java 17+: inventorying supported and enabled suites

The first example opens no network connections; it simply queries **`SSLContext`** on the running JDK for protocols and cipher suites. This is configuration inspection, **not proof that a connection will pick that suite**.

Create **`TlsSuitesInspectDemo.java`**:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class TlsSuitesInspectDemo {
    private static boolean contains(String[] values, String wanted) {
        return Arrays.asList(values).contains(wanted);
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());

        SSLParameters supported = context.getSupportedSSLParameters();
        SSLParameters enabled = context.getDefaultSSLParameters();
        System.out.println("Provider: " + context.getProvider().getName());
        System.out.println("TLSv1.3 supported: " +
                contains(supported.getProtocols(), "TLSv1.3"));
        System.out.println("TLSv1.2 supported: " +
                contains(supported.getProtocols(), "TLSv1.2"));
        System.out.println("TLS 1.3 AES-GCM supported: " +
                contains(supported.getCipherSuites(), "TLS_AES_128_GCM_SHA256"));
        System.out.println("TLS 1.2 ECDHE-RSA supported: " +
                contains(supported.getCipherSuites(),
                        "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"));
        System.out.println("TLSv1.3 enabled by default: " +
                contains(enabled.getProtocols(), "TLSv1.3"));
        System.out.println("TLSv1.2 enabled by default: " +
                contains(enabled.getProtocols(), "TLSv1.2"));
    }
}
~~~

Run with **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 TlsSuitesInspectDemo.java
java TlsSuitesInspectDemo
~~~

Result **on the tested SunJSSE JDK** (other runtimes may report different providers or booleans):

~~~text
Provider: SunJSSE
TLSv1.3 supported: true
TLSv1.2 supported: true
TLS 1.3 AES-GCM supported: true
TLS 1.2 ECDHE-RSA supported: true
TLSv1.3 enabled by default: true
TLSv1.2 enabled by default: true
~~~

### 9.1. Explanation

- **`SSLContext.getInstance("TLS")`** picks the provider and context supporting TLS versions per implementation; opens no TCP connection.
- **`init(null,null,new SecureRandom())`** uses provider default key/trust managers; in this example no connection occurs.
- **`getSupportedSSLParameters`** describes advertised capabilities; **`getDefaultSSLParameters`** is the default enabled set.
- TLS 1.2 and TLS 1.3 suite names appear in the same Java API, yet they **only work with their matching protocol version during handshake**.
- A `true` output does not prove the server key is configured, the certificate is trusted, groups match, or ALPN is negotiated.
- **`jdk.tls.disabledAlgorithms`**, providers, and security policies can alter enabled/default values across environments. Do not copy stdout as a universal standard.

To prove which suite a connection actually chose, perform a **handshake** and read **`SSLSession`**, as in the next example.

## 10. Java 17+: two real handshakes for TLS 1.2 and TLS 1.3

The second example runs a TLS server **only on loopback `127.0.0.1`**, then uses a JSSE client to perform real handshakes. The program checks **`SSLSession.getProtocol()`**, **`getCipherSuite()`**, and **`getApplicationProtocol()`** on both sides to show that TLS 1.2 and TLS 1.3 negotiated **two different cipher suites**.

To avoid a "trust-all" `TrustManager` (an extremely dangerous habit), this test uses a **self-signed certificate generated solely for localhost with `keytool`**, loads that same test keystore as trust anchors in the client context, and enables **HTTPS endpoint identification**. This is strictly an illustration of **explicitly configured local trust**; production must use the organization's truststore/PKI or appropriate trust mechanism—never copy this test certificate.

### 10.1. Create test PKCS12 file with `keytool`

In a writable exercise directory, using **JDK 17+ `keytool`**:

~~~bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -validity 1 -storetype PKCS12 -keystore loopback.p12 -storepass local-demo-pass -keypass local-demo-pass -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1" -noprompt
~~~

The command creates a **test-only** RSA key and self-signed certificate with a Subject Alternative Name for localhost. **`local-demo-pass` is solely a public exercise password**, never to be used in real applications. The certificate has a one-day validity to reduce the risk of treating it as a long-term asset. If `loopback.p12` already exists, work in a fresh test directory rather than overwriting valuable data.

### 10.2. Create `TlsNegotiationDemo.java`

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class TlsNegotiationDemo {
    private static final String ALPN = "demo/1";

    private static SSLContext[] contexts(Path file, char[] password)
            throws Exception {
        KeyStore keys = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(file)) {
            keys.load(input, password);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, password);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(keys);

        SSLContext server = SSLContext.getInstance("TLS");
        server.init(kmf.getKeyManagers(), null, new SecureRandom());
        SSLContext client = SSLContext.getInstance("TLS");
        client.init(null, tmf.getTrustManagers(), new SecureRandom());
        return new SSLContext[] {server, client};
    }

    private static String runOne(SSLContext serverContext,
            SSLContext clientContext, String protocol, String suite)
            throws Exception {
        InetAddress host = InetAddress.getByName("127.0.0.1");
        try (SSLServerSocket server = (SSLServerSocket)
                serverContext.getServerSocketFactory()
                        .createServerSocket(0, 8, host)) {
            server.setEnabledProtocols(new String[] {protocol});
            server.setEnabledCipherSuites(new String[] {suite});
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverResult = pool.submit(() -> {
                    try (SSLSocket peer = (SSLSocket) server.accept()) {
                        peer.setEnabledProtocols(new String[] {protocol});
                        peer.setEnabledCipherSuites(new String[] {suite});
                        SSLParameters p = peer.getSSLParameters();
                        p.setApplicationProtocols(new String[] {ALPN});
                        peer.setSSLParameters(p);
                        peer.startHandshake();
                        SSLSession session = peer.getSession();
                        return session.getProtocol() + "|"
                                + session.getCipherSuite() + "|"
                                + peer.getApplicationProtocol();
                    }
                });

                try (Socket tcp = new Socket(host, server.getLocalPort());
                     SSLSocket client = (SSLSocket)
                             clientContext.getSocketFactory().createSocket(
                                     tcp, "localhost", server.getLocalPort(), true)) {
                    client.setEnabledProtocols(new String[] {protocol});
                    client.setEnabledCipherSuites(new String[] {suite});
                    SSLParameters p = client.getSSLParameters();
                    p.setEndpointIdentificationAlgorithm("HTTPS");
                    p.setApplicationProtocols(new String[] {ALPN});
                    client.setSSLParameters(p);
                    client.startHandshake();
                    SSLSession session = client.getSession();
                    String clientState = session.getProtocol() + "|"
                            + session.getCipherSuite() + "|"
                            + client.getApplicationProtocol();
                    if (!clientState.equals(serverResult.get())) {
                        throw new IllegalStateException("TLS peers disagree");
                    }
                    return session.getProtocol() + " / "
                            + session.getCipherSuite() + " / ALPN="
                            + client.getApplicationProtocol();
                }
            } finally {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: keystore.p12 password");
        }
        char[] password = args[1].toCharArray();
        try {
            SSLContext[] both = contexts(Path.of(args[0]), password);
            System.out.println(runOne(both[0], both[1], "TLSv1.3",
                    "TLS_AES_128_GCM_SHA256"));
            System.out.println(runOne(both[0], both[1], "TLSv1.2",
                    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"));
        } finally {
            java.util.Arrays.fill(password, '\0');
        }
    }
}
~~~

### 10.3. Compile and run

~~~bash
javac --release 17 -encoding UTF-8 TlsNegotiationDemo.java
java TlsNegotiationDemo loopback.p12 local-demo-pass
~~~

With SunJSSE on tested JDK 17, the program prints:

~~~text
TLSv1.3 / TLS_AES_128_GCM_SHA256 / ALPN=demo/1
TLSv1.2 / TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256 / ALPN=demo/1
~~~

**Key observation:** both handshakes used the **same RSA test certificate**, the same ALPN choice `demo/1`, and possibly the same AES-128-GCM at the record layer. Yet the suite names **differ because of different semantics between TLS 1.2 and TLS 1.3**. In TLS 1.2 the suite name explicitly states **ECDHE_RSA**; in TLS 1.3 the name **TLS_AES_128_GCM_SHA256** mentions neither the RSA certificate nor the key exchange group.

### 10.4. Explaining the demo lifecycle

1. **KeyStore PKCS12** is created via `keytool`, holding the server's private key/certificate and the client's test trust anchor.
2. **KeyManagerFactory** supplies the certificate/private key to the server `SSLContext`. **TrustManagerFactory** creates a trust manager accepting only anchors in the test keystore, without disabling verification.
3. The ServerSocket binds only to **127.0.0.1** on a random free port, exposing no service to the Internet.
4. In each **`runOne`** call, server and client enable one protocol and one matching suite; this is a **deterministic selection test**, not a production policy with full fallback.
5. **`SSLSocket.startHandshake()`** completes the TLS handshake. Afterward, **`SSLSession.getProtocol`**, **`getCipherSuite`**, and **`getApplicationProtocol`** report the actual negotiated outcome.
6. **`SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`** forces the client to check hostname `localhost` against the trusted certificate; wrapping the connected TCP socket supplies `localhost` as the peer host for hostname checking.
7. **`serverResult.get()`** compares both sides' views after the handshake. Do not treat a successful handshake as proof of a valid public CA certificate; trust is scoped to the test file.
8. **`ExecutorService`** runs server `accept` on one thread and the client on another to perform the loopback handshake; sockets are closed via try-with-resources.
9. The temporary **`char[] password`** is cleared in `finally`; however, the initial password is passed via **`String args[1]`**, so this demo does not meet production secret-handling standards.

**Never use test passwords as real store passwords**, never pass production passwords on the command line (visible in process listings), and delete/control test files after the exercise. Retrieve secrets from an appropriate secure environment such as a secret manager or callback in real applications.

### 10.5. If the demo fails to run on another machine

If the JDK/provider lacks support for a protocol/suite, the certificate is wrong, disabled algorithms block the RSA key size, the truststore mismatches, `keytool` is not on `PATH`, or local policy forbids binding sockets, you may receive `SSLHandshakeException`, `NoSuchAlgorithmException`, `IllegalArgumentException`, or an appropriate I/O error. Never downgrade to TLS 1.0/1.1 or skip certificate verification just to "make it run".

Use the program in section 9 to check supported/default settings, then inspect **`jdk.tls.disabledAlgorithms`**, provider configuration, key material, and certificate SANs. To also test negotiating TLS 1.3 with an ECDSA certificate, generate a test EC certificate and matching trust setup; **the TLS 1.3 suite name can remain `TLS_AES_128_GCM_SHA256`** when profiles and keys align.

## 11. Choosing cipher suites by security and compatibility requirements

Suite selection must rest on **TLS version + key management + security policy + supported client/server types**—not solely on the AES 128/256 bit count.

### 11.1. Practical architectural recommendations

1. **Prefer TLS 1.3** once all parties deploy and test it; common suites like AES-GCM or ChaCha20-Poly1305 should be governed by security policy/provider.
2. **Retain TLS 1.2 when compatibility is needed** with supported clients, preferring **ECDHE + AEAD** such as `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` or `ECDHE_ECDSA` matching the certificate.
3. **Never re-enable TLS 1.0/1.1** or RC4, 3DES, or anonymous cipher suites just to connect an unsupported client; upgrade the peer or define a migration path.
4. **Never use RSA key transport** in new designs. In TLS 1.2, choosing `ECDHE_RSA` does not mean using `TLS_RSA`; ECDHE provides proper forward secrecy.
5. **Configure compatible certificates and signature algorithms** in practice: RSA/ECDSA/EdDSA, certificate chain, and trust manager; TLS 1.3 suite names do not choose the certificate for you.
6. **Do not enable 0-RTT by default for side-effecting APIs** without replay/idempotency policies and risk assessment.
7. **Do not overuse cipher-suite pinning**: configure an approved set and test against a peer matrix, since provider defaults can shift across JDK upgrades.
8. **Treat negotiated session results as operational evidence**, combined with certificate validation and authorization, rather than relying only on config files.

### 11.2. Why isn't AES-256 automatically better for the whole system?

**TLS_AES_256_GCM_SHA384** uses AES-256-GCM and HKDF-SHA384; **TLS_AES_128_GCM_SHA256** uses AES-128-GCM and HKDF-SHA256. Both offer strong protection in modern TLS profiles. A connection with AES-256 that lacks certificate validation, uses a weak PSK, suffers business-layer replay, or exposes its private key **can still be insecure**.

Beyond security strength, consider hardware acceleration, latency, client support, formal policy, and provider limits. **Never rank security solely from a cipher suite string.**

## 12. Negotiation errors and how to diagnose them

| Symptom | Check first | Pitfall to avoid |
| --- | --- | --- |
| **No appropriate protocol** | Enabled versions, `jdk.tls.disabledAlgorithms`, peer versions | Never force TLS 1.0 just to silence the error. |
| **No cipher suites in common** | Both sides' enabled suites, matching protocol, certificate/key type | Do not assume any name with AES-GCM works for both TLS 1.2 and 1.3. |
| **No available authentication scheme** | RSA/ECDSA/Ed25519 certificate, `signature_algorithms`, key managers | TLS 1.3 suites omit certificate type, so check extensions/key material. |
| **No appropriate key exchange group/share** | `supported_groups`, `key_share`, provider/curve policy, `HelloRetryRequest` | Do not assume the record cipher caused the failure. |
| **CertificateUnknown / PKIX path building failed** | Trust anchors, certificate chain, hostname, validity, and revocation policy | Never use a trust-all `TrustManager` to bypass the error. |
| **ALPN negotiation error** | Application protocols allowed by both sides, server preference, HTTP/2 policy | ALPN is not a cipher suite. |
| **Handshake succeeds, yet application fails** | TLS session vs. HTTP/2 policy, service authorization, and protocol framing | A valid cipher suite does not prove business logic is right. |
| **TLS 1.2 works, TLS 1.3 fails** | `supported_versions`, TLS 1.3 signature schemes/groups/certificates, provider support | Do not map TLS 1.2 suite names directly onto TLS 1.3. |
| **0-RTT request replayed** | Early-data policy, replay/idempotency, state mutation | Do not expect signatures/cipher suites to block app-layer replay. |

In Java, **`SSLHandshakeException`** indicates a general failure; the root cause can be certificates, algorithm constraints, key exchange, ALPN, version, or I/O. In test environments, JSSE supports **`javax.net.debug`** to observe handshakes, e.g.:

~~~bash
java -Djavax.net.debug=ssl,handshake TlsNegotiationDemo loopback.p12 local-demo-pass
~~~

The line above only illustrates enabling logs on the exercise. **Never run with production passwords on the command line**, and never enable verbose handshake logs unconditionally in production: logs can contain certificate metadata, hostnames, and sensitive diagnostics; restrict time/audience and protect logs.

**When reading logs:**
- Confirm what **the client offered**: TLS 1.3/TLS 1.2 and which cipher suites.
- Confirm what **ServerHello selected**: suite for the matching version.
- For TLS 1.3, inspect **`supported_groups`/`key_share`**, `signature_algorithms`/`cert`, PSK policy, and ALPN **separately**.
- Check trust, hostname, and certificate chain; cipher suite differences are only part of the picture.
- If a peer downgrades or lacks TLS 1.3 support, review configuration and policy; never disable protections to get past errors.

### 12.1. Downgrade protection and version negotiation

TLS 1.3 has **`supported_versions`** and downgrade protections specified in RFC 8446. The **`legacy_version`** field and compatibility messages **must not be interpreted as TLS 1.2 being selected** when `supported_versions` specifies TLS 1.3. TLS 1.2 also has fallback/renegotiation mechanisms such as `TLS_FALLBACK_SCSV`; never rely on automatic fallback to lower versions to connect at all costs.

Configure server/client with the **minimum TLS version permitted by policy**, upgrading older peers rather than dropping to non-compliant protocols. Never use packet captures or isolated legacy bytes to infer the active version; conclude from a **completed handshake and `SSLSession.getProtocol()`**.

## 13. Recommended compatibility test suite

| Test case | Configuration | Expected outcome |
| --- | --- | --- |
| **TLS 1.3 happy path** | Both sides enable TLSv1.3 + `TLS_AES_128_GCM_SHA256`, valid cert/trust | Handshake succeeds; `SSLSession` reports TLSv1.3 and matching suite. |
| **TLS 1.2 happy path** | Both sides enable TLSv1.2 + `ECDHE_RSA_WITH_AES_128_GCM_SHA256` | Handshake succeeds with TLSv1.2 and matching suite. |
| **Version mismatch** | Client TLSv1.3 only, server TLSv1.2 only | Handshake fails; no silent downgrade. |
| **Suite mismatch** | No overlapping valid suites for the same protocol | Handshake fails. |
| **Certificate mismatch** | TLS 1.2 `ECDHE_RSA` while server only has an ECDSA key unusable for RSA | Profile cannot be chosen; error handled cleanly. |
| **Wrong trust anchor** | Self-signed certificate absent from client truststore | Rejected; trust-all never enabled. |
| **Hostname mismatch** | Certificate lacks SAN for the accessed hostname | Endpoint identification rejects connection. |
| **TLS 1.3 group mismatch** | No shared valid DHE group and no permitted PSK-only mode | Handshake fails. |
| **Key share differs from server's preferred group** | Client supports group but did not send its share | `HelloRetryRequest` in eligible profiles, or controlled failure. |
| **ALPN mismatch** | No mutually supported application protocol per policy | Picks eligible protocol or fails; never infers weak cipher suite. |
| **PSK-only** | TLS 1.3 allows `psk_ke` | Check PFS requirements and PSK policy separately; never claim PFS from suite alone. |
| **0-RTT replay** | Replay early-data request with side effects | Application enforces replay defense/idempotency or rejects 0-RTT. |
| **Provider upgrade** | Switch JDK/security provider/HSM | Re-run supported/default/handshake tests for approved suites. |
| **Load/concurrency** | Many concurrent connections with different certs/ALPN | No mixing of `SSLSession`, certificate/key usage, or exceeding HSM capacity. |

A test inside one JVM only proves the **test environment**; it does not guarantee browsers, mobile clients, reverse proxies/CDNs, or production HSMs share the same suite/extension set. Maintain a **test matrix across actual JDK/client/proxy versions and key sources**.

## 14. Misconceptions to avoid

1. **TLS 1.3 cipher suites include certificate/key exchange types like TLS 1.2.** No: TLS 1.3 suites describe AEAD/HKDF hash.
2. **Having RSA in the name means RSA key transport.** `ECDHE_RSA` uses ephemeral ECDH and RSA authentication; unlike `TLS_RSA_`.
3. **SHA256 in a GCM suite name means records have an independent HMAC-SHA256.** No: GCM already has an authentication tag; the suffix in TLS 1.2 GCM is normally the PRF hash.
4. **`TLS_AES_128_GCM_SHA256` can be used verbatim on TLS 1.2.** Wrong version cipher suite definition.
5. **`TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` can be used verbatim on TLS 1.3.** This name belongs to the TLS 1.2 profile.
6. **Supported means enabled and negotiated.** Supported is only capability; inspect configuration and `SSLSession`.
7. **Calling `setEnabledCipherSuites` forces the server to accept them.** Peer, certificate, group, signature, and policy must still align.
8. **TLS 1.3 always has PFS in every case.** PSK-only and 0-RTT have critical limitations.
9. **ALPN/SNI are part of the suite.** They are extensions with distinct purposes.
10. **A TLS 1.3 suite dictates certificate signature hash as SHA256.** The cipher-suite hash is for HKDF/transcript; handshake/certificate signatures are governed separately.
11. **Checking the certificate chain alone is sufficient.** Clients also need hostname/identity, validity, key usage, revocation policy, and apps need authorization.
12. **Installing a TrustManager that trusts every cert fixes handshakes.** That removes peer authentication and enables MITM.
13. **Seeing `legacy_version` `0x0303` proves TLS 1.2.** In TLS 1.3 that can be a compatibility field; check `supported_versions` and handshake results.
14. **Enabling TLSv1.2 forces enabling CBC/3DES.** Modern TLS 1.2 ECDHE+AEAD can be configured without weak suites.
15. **Enabling AES-256 solves all risks.** Key/cert trust, PSK, replay, implementation, and application auth still matter.
16. **Using `SSLSession.getCipherSuite` alone reveals group, certificate type, and ALPN.** Each component must be inspected separately.
17. **Allowing 0-RTT on money-transfer APIs without replay protection.** TLS does not guarantee cross-connection anti-replay for 0-RTT.
18. **Equating TLS encryption with whole-system security.** TLS protects the channel, not user controls or business logic.

## 15. Self-check questions

**1. Does `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` use RSA key transport?**  
No. **ECDHE** creates the shared secret via ephemeral EC Diffie–Hellman; **RSA** is used for server/handshake authentication per the suite.

**2. Does `TLS_AES_128_GCM_SHA256` prove the server uses an RSA certificate?**  
No. The TLS 1.3 suite only specifies **AES-128-GCM + SHA-256 HKDF/transcript**. Certificates/signatures are chosen separately.

**3. Does SHA256 in a TLS 1.2 AES-GCM suite mean every record carries HMAC-SHA256?**  
No. For RFC 5289 GCM suites, SHA256 specifies the **TLS PRF hash**; the authentication tag comes from AES-GCM.

**4. Java reports `TLS_AES_128_GCM_SHA256` in supported suites. Will a TLSv1.3 connection definitely succeed?**  
No. Protocol enabled, peer overlap, certificate/trust, group/key share, signature, and policy compatibility are all needed.

**5. Why does TLS 1.3 separate `supported_groups` and `key_share`?**  
`supported_groups` advertises key-agreement group capabilities; `key_share` carries the public shares actually sent. If a share is missing for the server's preferred group, `HelloRetryRequest` can occur.

**6. Does TLS 1.3 connecting via `psk_ke` have the same PFS as ECDHE?**  
No. PSK-only lacks ephemeral (EC)DHE; evaluate forward secrecy according to the actual mode.

**7. Can TLS 1.3 0-RTT be freely used for payment transactions?**  
Not without replay protection and idempotency. Early data carries replay risk and weaker security guarantees than 1-RTT.

**8. Why read `SSLSession` after the handshake?**  
To learn the **actually negotiated protocol and suite**, distinct from initial supported/enabled lists.

**9. Is ALPN `h2` a cipher suite or a TLS version?**  
No. ALPN selects an application-layer protocol, not a TLS suite or version.

**10. Can TLS 1.2 with `ECDHE_RSA` and TLS 1.3 with `AES_128_GCM_SHA256` use the same RSA certificate?**  
Yes, if the server certificate and signing schemes meet both profiles/policies; TLS 1.3 suites omit RSA from the name.

## 16. Summary and authoritative references

**TLS 1.2:** cipher suite names typically express **key establishment/authentication + record cipher + MAC/PRF**, e.g., **`TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`**.  
**TLS 1.3:** cipher suite names primarily express **AEAD + HKDF hash**, e.g., **`TLS_AES_128_GCM_SHA256`**. **Groups/key shares, signature schemes/certificates, PSK modes, and ALPN** are handled separately, so TLS 1.3 cannot be read using TLS 1.2 naming rules.

In Java 17+, **`SSLContext` and `SSLParameters`** declare policy; **`SSLSocket`/`SSLEngine` + `SSLSession`** reveal the **actual negotiated outcome**. Good configuration protects **certificate validation, hostnames, allowed versions, modern suites, key exchange, replay, and application policy** simultaneously.

Official reading sources:

- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246)
- [RFC 5289 — ECC Cipher Suites for TLS 1.2](https://www.rfc-editor.org/rfc/rfc5289)
- [RFC 5288 — AES-GCM Cipher Suites for TLS](https://www.rfc-editor.org/rfc/rfc5288)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 7301 — Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301)
- [RFC 9150 — TLS 1.3 integrity-only cipher suites (extension exception)](https://www.rfc-editor.org/rfc/rfc9150)
- [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Java SE 17 — SSLContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Java SE 17 — SSLParameters API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [Java SE 17 — SSLSession API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html)
- [Java SE 17 — SSLSocket API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html)