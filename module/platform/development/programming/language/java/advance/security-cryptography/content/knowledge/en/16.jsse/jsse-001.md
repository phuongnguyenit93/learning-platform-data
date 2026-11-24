# 16.1 Roles of SSLContext, KeyManagerFactory, and TrustManagerFactory

**JSSE** (*Java Secure Socket Extension*) is the TLS/SSL security API layer in Java, using objects such as `SSLContext`, `SSLSocket`, `SSLServerSocket`, `SSLEngine`, `KeyManager`, and `TrustManager`. Three classes that frequently appear when configuring HTTPS or mTLS are **`SSLContext`**, **`KeyManagerFactory`**, and **`TrustManagerFactory`**. They are related, but they perform **three distinct responsibilities**:

- **`KeyManagerFactory`**: from an **identity keystore** containing the application's private key and certificate chain, creates **KeyManagers** to select and use **one's own identity** in TLS.
- **`TrustManagerFactory`**: from a **truststore/trust policy**, creates **TrustManagers** to decide whether a **peer's certificate can be trusted**.
- **`SSLContext`**: is the **configured TLS context** containing key managers, trust managers, a randomness source, and a TLS provider; it creates `SSLSocketFactory`, `SSLServerSocketFactory`, `SSLEngine`, and the TLS session context. It does not generate certificates itself or replace trust decisions.

This lesson opens group **16. JSSE** of Java Advance – security-cryptography. The focus is on **accurately distinguishing the responsibilities** of the three objects and identifying who holds the private key, who checks the peer's certificate, and who creates sockets/engines for the handshake. To self-verify without creating certificates, section 9 includes a standalone Java 17+ program illustrating SSLContext and SSLEngine before the handshake. Building a CA, certificate chains, and TLS loopback are studied in depth in lesson 16.2; forcing or requesting a client certificate is verified using the need/want matrix in lesson 16.5.

> **Scope:** all diagrams, snippets, and tests in this lesson aim to clarify JSSE responsibilities; successfully initializing an SSLContext **does not prove** that an actual session has verified the CA, SAN/hostname, client certificate, or authorization. Self-signed certificate labs in in-depth lessons apply only in test environments and must maintain separate trust boundaries.

## 1. Overview diagram: three responsibilities in JSSE

```text
                      JAVA APPLICATION
                            |
                            v
                   +----------------+
                   |   SSLContext   |
                   | protocol="TLS" |
                   +----------------+
                     ^            ^
                     |            |
     "Who am I?"     |            |    "Who do I trust?"
                     |            |
      KeyManagerFactory          TrustManagerFactory
       (identity keystore)        (truststore / policy)
               |                          |
        KeyManager[]                 TrustManager[]
               |                          |
      PrivateKeyEntry             TrustedCertificateEntry
       - private key                 - trusted CA/peer cert
       - leaf certificate           - trust anchor policy
       - certificate chain
                     |            |
                     +------+-----+
                            |
                  SSLContext.init(km, tm, random)
                            |
              +-------------+-------------+
              |             |             |
      SSLSocketFactory  SSLServerSocket  SSLEngine
                            |
                       TLS handshake
                       + protected data
```

**Quick mnemonic:**

| Question in TLS | Who is responsible? | Primary API |
| --- | --- | --- |
| **Which certificate does our side present?** | `KeyManager` selects the local identity and uses the corresponding private key | `KeyManagerFactory`, `X509KeyManager`/`X509ExtendedKeyManager` |
| **Is the peer's certificate trustworthy?** | `TrustManager` checks the chain/trust policy/related conditions | `TrustManagerFactory`, `X509TrustManager`/`X509ExtendedTrustManager` |
| **How are those managers used when creating a connection?** | `SSLContext` accepts managers and supplies a TLS-configured socket/engine | `SSLContext.getInstance`, `init`, `getSocketFactory`, `createSSLEngine` |
| **Does the TLS client use hostname `localhost` or `api.example.com`?** | Endpoint identity must be checked according to configuration/protocol | `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` on the socket/engine when appropriate |
| **Does the server require a certificate from the client?** | Server socket/engine configures client authentication | `setNeedClientAuth(true)`, `setWantClientAuth(true)`, or `SSLParameters` |
| **Which records are encrypted with the session key?** | The TLS provider/engine manages handshake, key schedule, and record encryption | `SSLSocket`, `SSLEngine` — do not handle manually with `Cipher` in the app |

Note: both **TLS clients and TLS servers** can use a **KeyManager** and a **TrustManager**. The difference does not lie in the words "client/server", but in **which side needs to prove its own identity** and **which side needs to verify the peer**. With **mTLS**, both sides do **both**.

## 2. KeyStore and truststore are data sources, not TLS managers

Before configuring JSSE, you must separate **files/storage repositories** from **objects that manage TLS behavior**.

| Object | Function | Has private key? | Enforces trust decision? |
| --- | --- | --- | --- |
| **`KeyStore`** | JCA API holding entries under aliases, which can be backed by PKCS#12, JKS, HSM, OS store | May have one | Not automatically; depends on the data and the API used |
| **Identity keystore** | A `KeyStore` used as the source of the **application's private key + certificate chain** | Usually **yes** | Not the primary purpose |
| **Truststore** | A `KeyStore` used to hold **allowed/trusted certificates/CAs** | Usually **does not need one** | The file itself makes no decision; **TrustManager** enforces the policy |
| **`KeyManager`** | Selects local alias/certificate chain and uses the private key as requested by the handshake | Granted permission to use the key | Has no duty to authenticate the peer |
| **`TrustManager`** | Verifies the peer certificate chain according to policy | Does not need the peer's private key | **Yes**, when performing checks during the handshake |
| **`CertStore`** | Source of **candidate certificates/CRLs** for PKIX path building/revocation | No | Not a trust anchor on its own |

**Java does not have a standard JCA class named `TrustStore`.** The word "truststore" describes the **role** of a `KeyStore`, usually containing `KeyStore.TrustedCertificateEntry`. A certificate residing in a truststore under an alias does not mean every client/SSLContext in the JVM uses that file: only trust managers configured with that store (or the corresponding default logic) use it.

### 2.1 Important KeyStore.Entry types

| Entry type | Content | Purpose |
| --- | --- | --- |
| `KeyStore.PrivateKeyEntry` | Private key + X.509 certificate chain | TLS server/client with a certificate to prove possession of the private key |
| `KeyStore.TrustedCertificateEntry` | Certificate placed into the trust set by an operator | Provides a trust anchor/peer certificate for trust policy |
| `KeyStore.SecretKeyEntry` | Symmetric secret key (e.g., AES) | Serves other cryptographic applications; does **not** become a TLS certificate identity |

For example, an `identity.p12` file containing only a certificate imported with `keytool -importcert`, **without a private key**, cannot allow the server to prove possession of a private key. Conversely, a `trust.p12` file containing a CA certificate is not where the server should obtain its private key when doing TLS.

`KeyStore.isKeyEntry(alias)`, `isCertificateEntry(alias)`, and `entryInstanceOf(alias,...)` help check the exact entry type. `getCertificate(alias)` can return the certificate of a **PrivateKeyEntry** *or* a certificate-only entry, so it is not enough to conclude that an alias is a trusted certificate entry.

## 3. KeyManagerFactory: turning an identity store into a KeyManager

The purpose of `KeyManagerFactory` is to **initialize one or more `KeyManager` instances from local authentication material**. For X.509 TLS, `X509KeyManager` or `X509ExtendedKeyManager` can:

- List local aliases matching the **key type** and peer requirements;
- Select the corresponding certificate chain when the server/client needs to present an identity;
- Provide an **authorized private key** for TLS to prove possession during the handshake;
- Choose a different key based on SNI, key type, or socket/engine context if the provider and configuration support it.

A typical flow:

```text
identity.p12
  |
  | alias "server"
  | PrivateKeyEntry:
  |   private RSA/EC key
  |   certificate chain: leaf -> intermediate...
  v
KeyStore.load(input, storePassword)
  |
  v
KeyManagerFactory.getInstance(
    KeyManagerFactory.getDefaultAlgorithm())
  |
  +-- init(identityStore, keyPassword)
  |
  +-- getKeyManagers() -> KeyManager[]
  |
  v
SSLContext.init(keyManagers, trustManagers, random)
  |
  v
When TLS needs a local certificate:
  KeyManager selects an appropriate key/certificate
```

### 3.1 Essential Java snippet

```java
// Illustration inside a method with appropriate imports/throws.
// identity and keyPassword were securely provided beforehand.
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identity, keyPassword);
KeyManager[] keyManagers = kmf.getKeyManagers();
```

`KeyManagerFactory.getDefaultAlgorithm()` reads the JDK default/provider configuration (typically related to the security property `ssl.KeyManagerFactory.algorithm`). **Do not hardcode provider-specific names** if the application has no such requirement. If policy mandates a specific provider (e.g., an HSM), explicitly verify the algorithm, provider, and key capability before initialization.

**Do not confuse `KeyManagerFactory` with `KeyPairGenerator` or `KeyFactory`:**

- `KeyPairGenerator` **generates** a new key pair;
- `KeyFactory` converts **key representations**/key specs;
- `KeyManagerFactory` prepares **how JSSE uses existing identity keys** during a handshake.

### 3.2 Store password and key password

```java
// Illustration, not a standalone program.
KeyStore ks = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("identity.p12"))) {
    ks.load(in, storePassword);
}
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(ks, keyPassword);
```

`storePassword` is used to open/verify the store depending on the type/provider. `keyPassword` is used to retrieve **private-key entries**. The two passwords **can be the same**, especially in PKCS#12 examples for compatibility, but **you must not assume they must always be identical** across all key stores/providers. If the password is valid for `load` but `kmf.init` fails, check key protection, alias, and provider instead of switching to an unauthenticated TLS mode.

In production, passwords should not be hardcoded as in lab examples, should not be logged on the command line or in unprotected log systems, and private keys must not be stored in a repository.

### 3.3 An alias name is not an automatic TLS identity

The alias `server` is only a **local label**. The certificate checked by the peer has SAN, subject, issuer, key usage/EKU, validity, signature, trust chain, and other policies. Renaming the alias to `api.example.com` **does not automatically fix the SAN**. When multiple private keys exist in a store, the key manager/provider can select an alias based on the handshake; if special alias selection is needed, configure `X509ExtendedKeyManager`/the framework properly and test SNI, key type, and signature algorithms.

## 4. TrustManagerFactory: turning a trust policy into a TrustManager

`TrustManagerFactory` initializes **`TrustManager` instances used to evaluate peer certificates**. For X.509, the object is usually `X509TrustManager` or `X509ExtendedTrustManager`.

```text
trusted-roots-and-peers.p12
  |
  | TrustedCertificateEntry: approved CA/peer cert
  v
KeyStore.load(input, storePassword)
  |
  v
TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm())
  |
  +-- init(trustStore)
  |
  +-- getTrustManagers() -> TrustManager[]
  |
  v
SSLContext.init(keyManagers, trustManagers, random)
  |
  v
When a TLS peer presents a certificate chain:
  TrustManager checks trust/path/constraints per configuration
  => rejects handshake if checks fail
```

### 4.1 Essential Java snippet

```java
// Illustration, not a standalone program.
// trustStore is an operator-managed KeyStore that has already been loaded.
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);
TrustManager[] trustManagers = tmf.getTrustManagers();
```

**`TrustManagerFactory.init(trustStore)` differs from `KeyManagerFactory.init(identity, password)`:** `TrustManagerFactory` does not need the peer's private key. It works with certificates/trust anchors. Do not swap the two factory types just because both use `KeyStore`.

Java has an overload `TrustManagerFactory.init(ManagerFactoryParameters)` for advanced configurations such as `CertPathTrustManagerParameters` to pass `PKIXBuilderParameters` where supported by the provider. That is a more complex way to manage trust policy; not every project needs to use it. The focus of this lesson is the common `init(KeyStore)` flow.

### 4.2 Trust manager and hostname verification

There are **two distinct questions** when a client connects to `https://api.example.com`:

1. *Does the certificate chain lead to a trusted CA/peer key according to policy and algorithms?*
2. *Is the target certificate actually **issued for the hostname api.example.com** and the proper intended usage?*

PKIX chain trust is the foundation of the first question; **endpoint identification** ensures the identity portion of the second question in a TLS client is properly configured.

When manually creating an `SSLSocket` or `SSLEngine`, consider explicitly setting:

```java
// Illustration: socket is an SSLSocket in client mode.
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
```

This is an **illustrative snippet**, not a full class. `"HTTPS"` is the standard endpoint identification algorithm name suitable for an HTTPS/TLS client context. A high-level HTTP client may already perform hostname verification, whereas low-level `SSLSocket`/`SSLEngine` must be configured properly so it is not omitted. **Do not treat chain validation as sufficient to replace SAN/hostname matching.**

### 4.3 A truststore is a list of trust anchors, not a store of all certificates

A `CertStore` can supply **candidate intermediate certificates and CRLs** for PKIX path building/checking. They do not automatically become trust anchors when downloaded. Adding an intermediate into a truststore as a **trusted CA** just to "fix PKIX path building failed" can widen the scope of trust beyond what was intended. Before adding a certificate to a truststore, verify its source/fingerprint, purpose, and scope of approval.

**TrustManager does not automatically prevent business-level replay.** TLS helps protect messages within a session, but the valid replay of a business HTTP request must be handled at the application layer, e.g., with idempotency keys, authorization, and anti-replay per the protocol contract.

## 5. SSLContext: coordinating managers and creating TLS engines

`SSLContext` is the **TLS protocol context** implemented by a provider. It holds the logical configuration for how a TLS socket/engine can use local credentials, trust decisions, randomness, protocols, and sessions.

```text
SSLContext context = SSLContext.getInstance("TLS");
context.init(
    KeyManager[] localIdentityManagers,
    TrustManager[] peerTrustManagers,
    SecureRandom randomSource
);

From context:
  context.getSocketFactory()         -> SSLSocketFactory (client)
  context.getServerSocketFactory()   -> SSLServerSocketFactory (server)
  context.createSSLEngine(...)       -> SSLEngine (socket-independent TLS engine)
  context.getDefaultSSLParameters()  -> default parameters of the context
  context.getSupportedSSLParameters()-> supported capabilities
```

Basic API:

```java
// Illustration inside a method where keyManagers and trustManagers are already created.
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, new SecureRandom());

SSLSocketFactory clients = context.getSocketFactory();
SSLServerSocketFactory servers = context.getServerSocketFactory();
SSLEngine engine = context.createSSLEngine("api.example.com", 443);
```

**`getInstance("TLS")` does not mean a truststore is already configured or a handshake has started.** You must call `init` (except for `SSLContext.getDefault()`, which is already ready per contract), then create a socket/engine and **perform the handshake**. Each socket/engine has its own connection state; an `SSLContext` can be used to create many connections.

### 5.1 Misconceptions about init

| Call | Correct meaning |
| --- | --- |
| `SSLContext.getInstance("TLS")` | Selects a TLS implementation; not connected yet and usually requires `init`. |
| `context.init(kms, tms, random)` | Sets managers and randomness source for the context; **has not verified any server certificate yet**. |
| `context.init(null, null, null)` | Tells JSSE/provider to use appropriate default managers and randomness mechanisms; **does not mean skipping trust validation**. Details of default sources depend on JDK/provider/config. |
| `SSLContext.getDefault()` | Gets an already-usable default context; may reflect system properties, provider, or a context set by `setDefault`. |
| `SSLContext.setDefault(ctx)` | Changes the default context for subsequent calls that use the default; **does not force every library/client with its own context to switch**. |
| `context.getSupportedSSLParameters()` | Parameters that **can be supported**, not necessarily enabled for every socket. |
| `context.getDefaultSSLParameters()` | Default values of the context/provider, which must be checked against policy before concluding security. |

**Distinguish default from safe:** if `tm` is `null`, SSLContext uses the default trust manager per contract/provider; this **does not mean trusting every certificate**. Do not create a custom `X509TrustManager` with an empty `checkServerTrusted` to avoid `SSLHandshakeException`. If the default truststore does not accept an internal CA, manage a separate truststore and verify the certificate source.

For a `null` `KeyManager` on a client context, the behavior is not necessarily the same as "the application already has a certificate." In particular, a **TLS server needs a private key/certificate identity** to perform a standard X.509 handshake; merely creating an `SSLContext` without supplying an appropriate key manager does not automatically give the server a certificate.

### 5.2 SSLContext is not a KeyStore

When building an `SSLContext` from `identity.p12` and `trust.p12`:

```text
identity.p12 -- KeyManagerFactory -> KeyManager[] --+
                                                    |
trust.p12    -- TrustManagerFactory -> TrustManager[]+--> SSLContext
                                                    |
                        new SecureRandom() ---------+
                                                    |
                                                   TLS
```

`SSLContext` **is not a `.p12` file**, does not persist private keys to disk via `store`, does not maintain a list of CAs like a new `KeyStore`, and does not generate key pairs or certificates on its own. It is the tool that **connects policies and credential sources to the TLS provider**.

## 6. One-way TLS and mTLS: who needs which factory?

### 6.1 TLS server authentication (commonly called "one-way TLS")

In the case where an HTTPS client checks the server, but the server **does not require a certificate from the client**:

```text
SERVER                                   CLIENT
  |                                        |
  | Identity KeyStore                      | Truststore
  | Private key + certificate chain        | Trusted CA/peer certificate
  |         |                              |          |
  | KeyManagerFactory                      | TrustManagerFactory
  |         |                              |          |
  | KeyManager[]                           | TrustManager[]
  |         |                              |          |
  +----- SSLContext -----------------------+----- SSLContext
  |                                        |
  | ---- server certificate/handshake ---> |
  |                                        |
  |          client validates chain + hostname
  |                                        |
  +------ encrypted TLS records <--------->+
```

- **Server** needs **KeyManagerFactory** with an identity key to present its certificate.
- **Client** needs **TrustManagerFactory** with a truststore to check the server; a client-side identity key manager may not be needed.
- The server may have initialized a trust manager, yet **does not use it to authenticate the client** if it does not request a client certificate.

### 6.2 Mutual TLS — mTLS

In **mTLS**, in addition to server authentication, the server requests and verifies the client's certificate:

```text
SERVER                                           CLIENT
  Identity key + KeyManager                    Identity key + KeyManager
  Truststore + TrustManager                    Truststore + TrustManager
            |                                            |
   server certificate/possession  ------------> verify server
            |                                            |
   verify client certificate      <------------ client certificate/possession
            |                                            |
           +-------------- TLS secure session -----------+
```

Both sides need their respective identity/trust sources, though **they are not required to share the same CA**. With mTLS, the server enables `setNeedClientAuth(true)` to **require** a client certificate; `setWantClientAuth(true)` only **requests one if available** per contract and is not equivalent to requiring it.

Important: mTLS proves that the handshake participant possesses a credential trusted by policy; it **does not automatically grant business permissions**. The application still has to map the certificate identity (SAN, subject, SPIFFE ID, or approved attributes) to an account/role/tenant and check authorization.

### 6.3 Comparison in one table

| Scenario | Server KeyManager | Server TrustManager | Client KeyManager | Client TrustManager |
| --- | --- | --- | --- | --- |
| HTTPS/TLS server auth | **Yes**: server identity | Not needed for client auth if client cert is not required | Can be `null` | **Yes**: CA/peer for server |
| mTLS | **Yes** | **Yes**: CA/peer for client | **Yes**: client identity | **Yes**: CA/peer for server |
| TLS client talking only to public-CA servers | Not on client side | Not on client side | Usually no client identity needed | Uses default trust or controlled truststore |
| Server authenticates client via another mechanism (OAuth/session) | **Yes** for server auth | Client cert not needed if not using mTLS | Can be `null` | **Yes** to verify TLS server |

Having a `TrustManagerFactory` on the server does not enable mTLS: you must configure the **server socket/engine** to require client authentication, and the client must have an appropriate identity credential.

## 7. Decision matrix: which components need to be configured?

Ask before writing code: **which side must present an identity**, **which side must verify the peer**, and **who drives the handshake**? The table below applies to common X.509 TLS and does not supersede policies of a specific provider or framework.

| Scenario | Local key managers | Peer trust managers | Next action |
| --- | --- | --- | --- |
| Java client calling a public HTTPS API, no client cert | Usually no client identity needed | Trust appropriate public CAs | The HTTP client needs to perform hostname identification and the handshake. |
| Java server with an HTTPS certificate | Needs private key + matching leaf/chain | Depends on client auth policy | SSLServerSocket/engine has server credentials, without enabling mTLS by default. |
| Java client calling an internal API with mTLS | Needs client private key + certificate chain | Trust the server's exact CA/peer | Configure the client SSLContext, then verify server name during handshake. |
| Java server enforcing mTLS | Needs server private key + certificate chain | Needs trust policy for client certs | Set needClientAuth before handshake and map peer identity to a principal. |

**Quick diagnostic example:** the client receives `PKIX path building failed` even though the server has a valid private key. First inspect the **client-side trust policy**, the chain the server actually sends, and whether the CA is approved; adding a private key to the client will usually not resolve this cause. Conversely, when the server cannot find a usable certificate/private key, check **KeyManagerFactory, alias, chain, key password**, and compatibility with the handshake.

**Responsibility boundary:** the trust manager verifies the certificate according to policy, but the application must control endpoint identity in the TLS client stack and business authorization. Having a truststore does not automatically make the server require a client certificate. Each call is only meaningful in its own role.

## 8. Reasoning exercise before using TLS loopback

Solve these three scenarios yourself, explicitly stating **input data → created manager → conditions for handshake success → evidence to verify**:

1. **One-way:** the server has `server-identity.p12` containing a private key and SAN `localhost`; the client has `server-trust.p12` containing only the trusted public certificate. Which side runs `KeyManagerFactory.init`, which side runs `TrustManagerFactory.init`, and at what point does the client check the hostname?
2. **mTLS:** the client is issued `client-identity.p12`, the server adds the client CA to its truststore and sets `needClientAuth(true)`. What differences appear when the client has no certificate, has a certificate from the right CA, or has a certificate from the wrong CA?
3. **CA change:** a team adds a new CA solely for a partner API. Why should they configure a dedicated `SSLContext` for the partner instead of importing that CA into the JVM-wide truststore, and which connections must be tested?

For each scenario, a successfully created `SSLContext` is the **starting point**, not a security conclusion. Verify with an actual handshake, peer certificate, endpoint identity, and negative tests. Lesson 16.2 implements full keystore/CA configuration and handshake; lesson 16.5 verifies the four client authentication cases; lesson 16.11 guides reading failure causes. This lesson keeps the focus on **explaining responsibilities** and a standalone Java example of pre-handshake state in the next section.

## 9. Standalone Java 17+ example: SSLContext and SSLEngine are not yet a handshake

To see that **SSLContext does not automatically make network connections**, run a second program that **does not need any `.p12` file**. We create a context, initialize it with provider-chosen default managers, create an `SSLEngine`, and specify that it is an HTTPS client — **without calling beginHandshake or sending bytes over the network**.

Save as **`JsseParametersDemo.java`**:

```java
import java.security.SecureRandom;
import javax.net.ssl.*;

public final class JsseParametersDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());

        SSLEngine engine = context.createSSLEngine("localhost", 443);
        engine.setUseClientMode(true);

        SSLParameters params = engine.getSSLParameters();
        params.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(params);

        System.out.println(
                "Context protocol: " + context.getProtocol());
        System.out.println(
                "Engine client mode: " + engine.getUseClientMode());
        System.out.println(
                "HTTPS endpoint check configured: "
                        + "HTTPS".equals(
                                engine.getSSLParameters()
                                        .getEndpointIdentificationAlgorithm()));
        System.out.println(
                "No network handshake performed: true");
    }
}
```

```bash
javac -encoding UTF-8 JsseParametersDemo.java
java JsseParametersDemo
```

Stdout:

```text
Context protocol: TLS
Engine client mode: true
HTTPS endpoint check configured: true
No network handshake performed: true
```

What the program **did**: initialized an `SSLContext`, created an `SSLEngine`, set client mode, and configured endpoint verification. What it **did not do**: received no certificate, checked no chain, performed no actual hostname validation, exchanged no session keys, and encrypted no records. **`SSLContext.init` + `SSLParameters` does not replace a handshake**.

### 9.1 Why does SSLEngine exist if SSLSocket already exists?

`SSLSocket` is TLS communicating over a socket and is convenient for blocking I/O. `SSLEngine` provides a **TLS engine not tightly bound to a Socket**; the application/framework controls `wrap`/`unwrap` of `ByteBuffer` instances and transports bytes over the NIO/network layer it manages.

```text
SSLSocket:
  TCP socket + TLS engine + streams (blocking I/O interface)

SSLEngine:
  TLS handshake + record processing
             |
         application-managed buffers/network transport
```

Both use the **managers from SSLContext**, but `SSLEngine` requires complex state machine/handshake tasks/buffer management. **Do not** call `SSLEngine.wrap` once and consider the connection complete. Frameworks like Netty can manage this part, yet still require proper configuration of trust, hostname, and identity.

## 10. Roles of factories during the TLS handshake

A successful TLS handshake has multiple steps. The following diagram is a **conceptual flow**, not reflecting every TLS 1.2/1.3 message:

```text
CLIENT                                                   SERVER
   |                                                        |
   | ClientHello (versions, ciphers, key share, SNI...)      |
   |------------------------------------------------------->|
   |                                                        |
   |                                  server selects TLS policy
   |<---------------------- ServerHello / certificate / proof
   |                                                        |
   | TrustManager(client):                                   |
   |  - chain to trusted CA/peer?                            |
   |  - certificate/path/algorithm policy?                   |
   | SSLParameters/endpoint:                                  |
   |  - hostname/SAN matches?                                |
   |                                                        |
   |      [If mTLS: server requests client certificate]      |
   |                                                        |
   | KeyManager(client):                                     |
   |   selects client identity/certificate/private key       |
   |------------------------------------------------------->|
   |                                                        |
   |                           TrustManager(server):
   |                             client certificate valid?
   |                                                        |
   |<================= authenticated TLS records ===========>|
```

**Accurate role details:**

- `KeyManager` assists in proving the **private key of the local identity** when the protocol requires it; it does not decide whether the peer is trustworthy.
- `TrustManager` decides whether the **peer certificate is acceptable** per configuration, while ensuring endpoint identification and application policy are not bypassed.
- `SSLContext` provides TLS provider resources, session cache, factories/engines, and configuration; it does not issue certificates, manage root CAs, or choose TCP routes.
- The TLS provider also handles **key exchange, key schedule, record encryption, and transcript integrity**, without the app having to coordinate `Cipher`/`KeyAgreement` for each record.
- **TLS 1.3** and **TLS 1.2** differ in messages/mechanics; do not tie the lines of the diagram above to an invariant packet order of a single version.

## 11. Configuring client authentication in the right place

### 11.1 Difference between need and want

| Server setting | Behavior |
| --- | --- |
| `setNeedClientAuth(true)` | Requires the client to present an accepted certificate; otherwise the handshake fails per policy |
| `setWantClientAuth(true)` | The server **wants** a client certificate and checks it if presented, but **does not require it** like need |
| No client cert requested | Standard server authentication only |
| Server has a TrustManager without enabling client auth | **Does not create mTLS**: the server does not automatically request a client certificate just because it has a truststore |

A proper mTLS test suite must test a **client with a valid identity**, a **client sending no certificate**, and a **client sending an untrusted certificate**. If the server sets `want` and the client has no certificate yet the handshake succeeds, that **may be correct per contract** — do not misread it as a TrustManager bug.

### 11.2 Certificate identity vs. authorization

Once the server TrustManager approves a client certificate, the app must still decide **which APIs** and tenant the client is allowed to call, and whether the identity proof applies to that endpoint. Do not automatically map `CN=admin` or a file alias `admin` to admin privileges; use a policy-verified identity (SAN/URI/SPIFFE ID/fingerprint pinning or PKI policy) and separate authorization rules.

## 12. Default JSSE vs. custom SSLContext

Java has both a **default configuration** and **application-built custom contexts**. Do not confuse them.

### 12.1 SSLContext.getDefault()

`SSLContext.getDefault()` returns an already-ready context. If no context has been set via `setDefault`, the first call may create a `"Default"` implementation according to the JDK/provider. System properties may exist such as:

```text
javax.net.ssl.keyStore
javax.net.ssl.keyStoreType
javax.net.ssl.keyStorePassword

javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
```

These properties are part of JSSE configuration for matching providers; not every HTTP client, Netty config, HSM, or custom SSLContext automatically uses them. **`-Djavax.net.ssl.trustStore` does not mean every context in the process will automatically swap its trust managers**, especially if a framework passes an explicit trust manager.

In the SunJSSE implementation, the default truststore may refer to `jssecacerts` and then `cacerts` by rule when no path is specified; details depend on the JDK/distribution. A misconfigured/nonexistent truststore path can lead to an empty trust set or handshake failure; it is unsafe to rely on automatic fallback.

### 12.2 Why use separate contexts per trust domain?

For example, an application calls both public APIs and internal APIs:

```text
HTTPS public endpoint  ---> SSLContext using public CA trust policy
HTTPS internal API     ---> SSLContext using dedicated internal CA trust policy
mTLS to partner        ---> SSLContext with client identity + partner trust policy
```

This reduces the **blast radius** when adding a CA. Modifying the JVM-wide `cacerts` file or calling `SSLContext.setDefault` to support one partner can impact many unrelated connections. It is better to configure the context/truststore with the exact scope that the HTTP library actually uses, and then test it.

### 12.3 Do not equate default with provider-independent

`KeyManagerFactory.getDefaultAlgorithm()` and `TrustManagerFactory.getDefaultAlgorithm()` may differ across JDKs/providers/security properties. `SSLContext.getInstance("TLS")` also depends on registered providers. When an application requires HSM/FIPS or a specific trust implementation, verify the **actual provider, supported algorithms, key sizes, cipher suites, and compliance certifications** — do not conclude based solely on API presence.

## 13. Certificate chain, PKIX, and hostname in TrustManager

When a peer presents a certificate chain, JSSE's TrustManager typically contains logic based on **X.509/PKIX** and the truststore:

```text
Peer leaf -> intermediate(s) -> approved trust anchor
                |
                +-- signature checks
                +-- validity and algorithm constraints
                +-- appropriate basic/key usage/extended key usage
                +-- certificate policies, name constraints if applicable
                +-- revocation per configuration/policy
                +-- endpoint identity/hostname per TLS client configuration
```

**Do not assume the provider performed every item** solely from an `SSLContext + TrustManagerFactory` pair. JSSE APIs/providers, hostname algorithm, revocation settings, algorithm constraints, TLS role, and custom trust managers determine what is enforced. For HTTPS, hostname/SAN must match the endpoint; for mTLS, the client certificate must be mapped to a clear identity/authorization policy.

### 13.1 What if you only import an intermediate into the truststore?

An intermediate is a **link in the chain**, not necessarily something to configure as a **trusted CA anchor**. Adding an intermediate directly as an anchor can unintentionally broaden trust. When the full chain cannot be found, the right approach is usually:

- Check whether the server has sent the appropriate **leaf + intermediate**;
- Obtain a trusted intermediate source and supply it to the path builder/provider per policy;
- Keep trust anchors inside a managed truststore;
- Verify issuer/subject, signature, key usage, SAN, certificate path, and validity period;
- Do not disable certificate or hostname checks to get past the handshake.

### 13.2 Revocation is not automatically enabled just by having a truststore

CRL and OCSP are mechanisms to check for revoked certificates. `TrustManagerFactory.init(trustStore)` does not mean a system has selected a **complete revocation policy** for every certificate type. You must evaluate `PKIXRevocationChecker`, provider defaults, CRL/OCSP sources, stapling, caching, timeouts, and fail-open/fail-closed behavior per your threat model. Do not copy a `setRevocationEnabled(false)` line from a PKIX unit test into production without justification.

## 14. SSLParameters: per-connection policy

In addition to the context's managers, a socket/engine has **session configuration**: protocol/cipher suites, endpoint identification, SNI, ALPN, and client auth.

| Attribute | Example API | Notes |
| --- | --- | --- |
| Endpoint identification | `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | For TLS clients needing hostname verification per the HTTPS contract |
| TLS protocols | `SSLParameters.setProtocols(...)` / socket `setEnabledProtocols` | Check defaults and policy; do not re-enable SSLv3/TLSv1.0 |
| Cipher suites | `SSLParameters.setCipherSuites(...)` | Select only suites supported by the provider and approved by policy |
| Mandatory client certificate | `SSLServerSocket.setNeedClientAuth(true)` / `SSLParameters.setNeedClientAuth(true)` | Server-side setting to require mTLS |
| Optional client certificate | `setWantClientAuth(true)` | Not equivalent to a hard requirement |
| Server Name Indication | `SSLParameters.setServerNames(...)` | Helps the server pick a virtual host/cert when the client sends SNI; does not replace hostname verification |
| ALPN | `SSLParameters.setApplicationProtocols(...)` | Negotiates application protocols like HTTP/2 when supported by the stack |
| Socket/Engine | `SSLSocket.setSSLParameters(...)`, `SSLEngine.setSSLParameters(...)` | Apply parameters before the handshake |

**Do not hardcode every protocol/cipher in an introductory lesson**: supported and default sets change across JDKs/providers/security updates. Choose from organizational security policy, avoid deprecated algorithms, and test interoperability. Prefer TLS 1.3 or securely configured TLS 1.2 per policy when compatible; do not enable legacy TLS simply because a partner's handshake failed.

## 15. Troubleshooting: distinguishing KeyManager, TrustManager, and SSLContext

| Symptom / Exception | Stage that may cause it | Resolution approach |
| --- | --- | --- |
| `KeyStoreException`, `IOException` when loading PKCS#12 | Identity/truststore file wrong path, corrupted, wrong password/type | Check path, store type, permissions, and password; do not log secrets |
| `UnrecoverableKeyException` during `KeyManagerFactory.init` | Wrong key password / inaccessible entry | Distinguish key password from store password and HSM permissions |
| `NoSuchAlgorithmException` when creating factory/context | Provider/JDK does not support the requested algorithm | Check security providers and algorithm names |
| `KeyManagementException` during `SSLContext.init` | Manager/config/provider failed to initialize | Preserve the cause, fail fast, and never fall back to trust-all |
| `SSLHandshakeException: PKIX path building failed` | Client/server TrustManager cannot find a valid path to an anchor per policy | Inspect the **effective truststore**, chain, intermediate, root, expiration, usages, algorithm constraints |
| `SSLHandshakeException: No subject alternative ...` | Endpoint identification/SAN does not match hostname/IP | Issue a certificate with the right SAN and use the right hostname; do not disable hostname verification |
| `SSLHandshakeException: bad_certificate` / `certificate_unknown` | Peer certificate rejected or unsuitable | Check role, CA, chain, EKU, mTLS policy; avoid guessing from a single alert |
| `handshake_failure` / `no cipher suites in common` | No agreement on protocol, cipher, key type, signature scheme, or identity | Check JDK/provider, enabled protocols, server certificate, and peer requirements |
| `SSLPeerUnverifiedException` when reading peer cert | No authenticated peer/appropriate session yet, or peer provided no cert | Use only after handshake and per role; do not treat solely as a CA error |
| `SSLException: Connection reset` / `SocketTimeoutException` | Network, firewall, timeout, peer closed, or hung connection | Separate transport errors from certificate errors; apply timeout and retry policies |
| `IllegalStateException` from `SSLEngine`/TLS API | Calling handshake/engine in wrong mode/state or improper reinit | Follow the state machine; do not skip the handshake |

### 15.1 Concise diagnostic workflow

1. **Isolate the failing side:** is the client rejecting the server, or the server rejecting the client?
2. **Check roles:** does the identity keystore have a `PrivateKeyEntry` with the right alias/chain? Does the truststore have approved CAs/peers?
3. **Check the actual runtime:** is the app using a custom SSLContext or the default? Are system properties overridden by a framework/container?
4. **Inspect the chain:** leaf/intermediate/trust anchor, expiration, SAN, EKU, key usage, algorithm policy.
5. **Check hostname:** what name is the client connecting to? Does the certificate have a matching SAN? IP literals differ from DNS names.
6. **Check mTLS:** does the server have `needClientAuth` or only `wantClientAuth`? Does the client have a key manager?
7. **Check protocols/cipher suites:** TLS 1.2/1.3, provider, key type, signature algorithms, disabled algorithms.
8. **Log safely:** `-Djavax.net.debug=ssl,handshake` in test environments; avoid exposing secrets or sensitive info publicly.

**A PKIX error is not always caused by a missing private key.** If the client does not trust the server certificate, that is usually the **TrustManager** flow; if the server lacks a suitable local certificate, that is usually the **KeyManager** flow. Accurate classification prevents "fixing" the wrong thing by importing batches of CAs into the JDK `cacerts`.

## 16. Safety principles when customizing Managers

### 16.1 Never create a trust-all X509TrustManager

A common anti-pattern:

```java
// Illustrative ANTI-PATTERN, DO NOT use.
// This is a method, not a standalone class:
public void checkServerTrusted(
        java.security.cert.X509Certificate[] chain, String authType) {
    // Checks nothing -> accepts forged certificates.
}
```

If you need to trust an internal CA, verify that CA and **initialize `TrustManagerFactory` from a truststore containing that exact CA**. Do not use an empty `checkServerTrusted` implementation, set a `HostnameVerifier` that always returns `true`, or ignore certificate errors. Such "quick fixes" disable TLS authentication and open the door to MITM attacks.

### 16.2 Minimize writing custom KeyManagers and TrustManagers

Customizing `X509ExtendedKeyManager` may be needed when selecting an alias by SNI, tenant, or a special keystore. Customizing `X509ExtendedTrustManager` may be needed for pinning or custom PKIX policies. When doing so:

- Reuse standard chain/path verification; never compare only subject strings;
- Maintain endpoint identity checks and cipher/algorithm policies per role;
- Ensure every overload used by `SSLSocket` and `SSLEngine` is implemented properly;
- Do not accept a certificate lacking a trust anchor on the grounds that "the app checked the fingerprint" if fingerprints are not reliably managed;
- Write tests for public CAs, internal CAs, certificate rotation, wrong hostname, expired, revoked, wrong EKU, attacker/self-signed, and different TLS providers.

### 16.3 HSMs and non-exportable private keys

A key manager can use a **private key handle** from an HSM/PKCS#11 provider without extracting raw key bytes. `PrivateKey.getEncoded() == null` is not necessarily an error; it may be a **non-extractable** policy. Do not try to export keys just to put them into a `.p12`. Configure the proper keystore type/provider, permissions, and signing capabilities per the TLS stack.

## 17. Self-check scenarios

**Scenario A — Client calls HTTPS and reports `PKIX path building failed`.**  
**Answer:** Usually start with the client's **TrustManager/TrustManagerFactory** and effective truststore: check whether the root/intermediate are valid, along with SAN/hostname and algorithm constraints. Do not import a private key into the client or disable cert verification.

**Scenario B — Server has `trust.p12` but no `identity.p12`, and wants to present a certificate.**  
**Answer:** A truststore has no private key. The server needs an appropriate local identity/key manager. `SSLContext` does not generate certificates on its own.

**Scenario C — Server has a trust manager containing the client's CA, but the client never sends a certificate.**  
**Answer:** Having a trust manager **does not activate mTLS**. The server must enable client authentication (`needClientAuth`), and the client must have a KeyManager/certificate matching the policy.

**Scenario D — Client calls `context.init(null, null, null)`. Did it just "trust all certificates"?**  
**Answer:** No. `null` requests default behavior defined by the implementation/provider/JDK; it does **not** mean skipping peer authentication. Check the default trust path if it does not meet policy.

**Scenario E — `SSLContext` initialized successfully, so has the hostname been verified?**  
**Answer:** No. There is no peer certificate or handshake yet. Hostname/endpoint identification applies when performing the handshake per client configuration.

**Scenario F — `KeyManagerFactory.init(store, pass)` succeeded, yet the server still has no matching certificate.**  
**Answer:** Check the alias/private-key entry/chain, certificate validity/usage, key type/signature algorithms, SNI, and TLS provider. Initializing the factory does not guarantee every handshake will find a suitable identity.

**Scenario G — `TrustManagerFactory` uses a truststore containing only public CAs, with no private keys. Is anything missing?**  
**Answer:** No. To verify the signatures of a peer's certificate chain, **no private key of the CA/peer is needed**; only public certificates/trust anchors and policy are used.

**Scenario H — The root CA is trusted, yet the URL `https://wrong.example` does not match the leaf's SAN.**  
**Answer:** It must be rejected if HTTPS endpoint identity does not match. Chain trust and hostname are two separate checks.

**Scenario I — All services in the process use the default SSLContext; we want to add a CA for just one partner.**  
**Answer:** Create/customize a **dedicated SSLContext** for the partner's trust domain if the client library supports it, rather than expanding the JVM-wide `cacerts`.

**Scenario J — The mTLS client certificate is valid, but the caller attempts an action belonging to another tenant.**  
**Answer:** mTLS is only credential authentication; **application-layer authorization** is required to bind the verified identity to permissions/tenants.

## 18. Checklist before deploying JSSE to production

- Clearly determine **TLS server auth** vs. **mTLS**; which side needs a local private key and which needs a trust policy.
- Provide an identity `KeyStore` with a `PrivateKeyEntry` and proper certificate chain; avoid using a certificate-only alias as an identity.
- Provide a properly scoped truststore; trust only source-verified and approved CAs/peers.
- `KeyManagerFactory.init(identity, keyPassword)`; `TrustManagerFactory.init(trustStore)`; `SSLContext.init(km, tm, random)` in their proper roles.
- Enable **HTTPS endpoint identification** on low-level TLS clients if the framework does not guarantee it; do not skip SAN/hostname checks.
- For mTLS, configure **needClientAuth** properly on the server, and map the client certificate to an authorization policy in the application.
- Use TLS versions/cipher suites and key algorithms that comply with the current runtime's policy; no weak fallbacks.
- Verify revocation, chain, EKU/key usage, certificate expiry, rotation, trust anchor changes, and provider compatibility.
- Do not hardcode private keys/passwords, do not log secrets/handshake secrets, and do not import untrusted certificates just to silence errors.
- Include **positive** tests (valid server/client) and **negative** tests (wrong CA, hostname, expired, missing private key, mTLS client without cert).
- Test on the actual target JDK, JSSE provider, OS/container, and HTTP client; do not extrapolate everything from an `SSLContext.init` unit test.
- Separate contexts by trust domain when appropriate; govern root CAs and private keys through dedicated security processes.

## Official documentation

1. [Java SE 17 — `SSLContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): `getInstance`, `init`, socket factories, `SSLEngine`, default context, and parameters.
2. [Java SE 17 — `KeyManagerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): creating a `KeyManager` from a local identity keystore.
3. [Java SE 17 — `TrustManagerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): creating a `TrustManager` from a truststore or parameters.
4. [Java SE 17 — `SSLSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html), [`SSLServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html), [`SSLEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): TLS handshake with sockets or transport-independent engines.
5. [Java SE 17 — `SSLParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification, client auth, protocols, cipher suites, and SNI.
6. [Java SE 17 — `KeyStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): entry types and load/alias/password.
7. [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): key/trust manager model, default keystore/truststore, and TLS configuration.
8. [Java SE 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): generating and exporting/importing lab certificates.
9. [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html): authentication roles, key schedule, and record protection in TLS 1.3.
10. [RFC 5280 — X.509 PKIX](https://www.rfc-editor.org/rfc/rfc5280.html): certificate path, validity, certificate policies, and trust anchors.

**Conclusion:** Remember the three distinct areas of effect: **KeyManagerFactory = supplies local identity/private-key credentials**, **TrustManagerFactory = verifies peer certificate/trust**, and **SSLContext = context coordinating managers and the TLS provider to create sockets/engines**. A secure connection also requires a complete TLS handshake, proper hostname/endpoint identity, managed CAs/trust anchors, and **separate authorization** when using mTLS.