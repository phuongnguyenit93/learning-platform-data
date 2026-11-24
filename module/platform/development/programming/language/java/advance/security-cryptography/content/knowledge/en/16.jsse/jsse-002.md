# 16.2 Initializing SSLContext from Private Key, Certificate Chain, and Trusted CAs

In **JSSE (Java Secure Socket Extension)**, the **`javax.net.ssl.SSLContext`** object is where the application combines two completely distinct groups of information:

1. **The application's own identity (local identity):** a **private key** and its corresponding **X.509 certificate chain**, so the Java side can prove possession of the private key when required by the TLS handshake. The source is typically an **identity keystore**.
2. **The CAs/certificates the application accepts as trusted (peer trust):** a set of **trust anchors** used to verify the other party's certificate, typically provisioned via a **truststore** and `TrustManagerFactory`.

Both data sets are fed into `SSLContext` via **`KeyManagerFactory`** and **`TrustManagerFactory`**. The name "SSLContext" is a historical API name: in modern programs, use **TLS**, and do not enable SSLv2/SSLv3 or legacy TLS versions no longer permitted by policy.

This lesson covers the complete model of private key → certificate chain → `KeyManager`, trust anchors → `TrustManager`, the steps to call `SSLContext.init(...)`, socket configuration, and endpoint identification; it includes a **`keytool` command set to create a demo CA, a CA-signed server certificate, and a truststore**, along with a **Java 17+ program** tested with a TLS 1.3 handshake over loopback. The end of the lesson analyzes mTLS, certificate rotation, store/key passwords, handshake errors, and common security pitfalls.

> **Remember:** `KeyManager` decides **"which identity and private key do I present?"**; `TrustManager` decides **"do I trust the peer's certificate chain?"**. They cannot substitute for each other.

## 1. Four components to distinguish before writing code

| Component | Nature | Who holds it | Role in TLS |
| --- | --- | --- | --- |
| **Private key** | Asymmetric secret key, such as RSA or EC | Only the identity owner, or that owner's HSM/KMS | Performs signing/proof-of-possession operations during the TLS handshake |
| **Leaf certificate** | X.509 certificate carrying the public key and DNS/IP/SAN identifiers | Can be public | Binds the public key to an identity according to CA-verified information |
| **Certificate chain** | Leaf followed by corresponding intermediate CAs; may include root depending on store/format | Can be sent over TLS; not a secret | Allows the peer to build a path to a CA that **the peer** already trusts |
| **Trusted CA/root** | Trust anchor approved by the application per policy | Resides in a truststore or configured trust source | Serves as the termination point of the verification path for the **peer's** certificate |

### 1.1. "Having a certificate" does not mean "having a private key"

A `server.crt` or `server.pem` file typically contains a **public certificate**, not a private key on its own. When an application acts as a TLS server and presents an identity, `KeyManagerFactory` needs to obtain the **private key matching the leaf certificate's public key**, along with the appropriate chain. Simply loading a trusted certificate into a `KeyStore` with `setCertificateEntry(...)` does not turn the application into a TLS server with that identity.

### 1.2. Root CA in the chain vs. root CA in the truststore

For example:

```text
                              SERVER                          CLIENT
             +--------------------------------+    +-------------------------+
             | Identity Keystore (PKCS12)     |    | Truststore (PKCS12)     |
             |   Alias: service               |    |  TrustedCertEntry: ca   |
             |     PrivateKey (secret)        |    |   Root CA certificate   |
             |     Leaf: CN=localhost         |    +------------+------------+
             |     Issuer: Demo Root CA       |                 |
             |     Chain: [leaf, Root CA]     |                 |
             +----------------+---------------+                 |
                              |                                 |
                     KeyManagerFactory                   TrustManagerFactory
                              |                                 |
                          KeyManager                       TrustManager
                              |                                 |
                              +------------+--------------------+
                                           |
                                SSLContext.init(...)
                                           |
                             SSLSocket / SSLServerSocket
```

In **production**, the certificate chain sent over TLS usually consists of **leaf + intermediate**, while the **root trust anchor** is held independently by the peer and normally does not need to be sent. This lesson's fixture has a **2-certificate chain [leaf, root]** because only a single demo CA signs directly, making the full relationship visible. Having the root present in the server's chain **does not make the client automatically trust that root**: the client must still have the root in its pre-provisioned truststore.

### 1.3. Identity keystore and truststore can both be `KeyStore`

`java.security.KeyStore` is the abstract API for holding keys/certificates. There are no two separate Java classes named "IdentityKeyStore" and "TrustKeyStore":

- An **identity keystore** typically holds a `PrivateKeyEntry` and the application's own certificate chain.
- A **truststore** typically holds `TrustedCertificateEntry` entries for trusted CAs. It **does not need** the CA's private key.
- Both can use the `PKCS12` format; a `.p12`/`.jks` extension is not absolute proof of the type.
- `KeyStore` can also represent an HSM/PKCS11 token, where private keys are not exported as bytes.
- Modern Java usually uses `PKCS12` as the default keystore type, but you should specify the type explicitly in tutorials and verify the provider.

A `PKCS12` containing a CA certificate **imported by the application from an untrusted source** does not make that CA trustworthy in business terms. **Truststore inputs must be independently verified and approved.**

## 2. Full path from certificate/key to SSLContext

There are two critical JSSE factories:

```text
[identity key file + certificate chain]       [approved trusted CA certificates]
             |                                               |
       KeyStore identity                               KeyStore trusted
             |                                               |
       KeyManagerFactory                              TrustManagerFactory
       init(identity, keyPass)                         init(trusted)
             |                                               |
          KeyManager[]                                  TrustManager[]
             |                                               |
             +-------------------+---------------------------+
                                 |
          SSLContext.getInstance("TLS")
          SSLContext.init(keyManagers, trustManagers, SecureRandom)
                                 |
                +----------------+---------------+
                |                                |
        getSocketFactory()              getServerSocketFactory()
        SSL client socket               SSL server socket
                |                                |
        SSLParameters/handshake/peer certificate validation
```

### 2.1. `KeyStore.load` — reading the store, not yet retrieving the key

```java
KeyStore identity = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("server.p12"))) {
    identity.load(in, storePassword);
}
```

This is an **illustrative snippet** requiring the appropriate `import` statements and `storePassword` variable. `storePassword` is typically used when loading/protecting the integrity of the store per provider and format. **Loading successfully does not mean** the private key under the desired alias has been recovered.

Check the required contents:

```java
boolean hasKey = identity.isKeyEntry("service");
Certificate[] chain = identity.getCertificateChain("service");
```

If `hasKey == false`, the alias may not exist or may only be a certificate entry. If `chain == null`, there is no suitable certificate chain for the alias; do not access `chain.length` before checking in production code.

### 2.2. `KeyManagerFactory.init` — recovering the private key identity

```java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identity, keyPassword);
KeyManager[] managers = kmf.getKeyManagers();
```

`keyPassword` is the **password protecting the private key entry** per keystore type/provider. It **can differ** from `storePassword`. Some PKCS12 tools, especially many versions of `keytool`, may require or assume the two passwords are the same. Rely on how the file/provider actually works rather than treating the two concepts as identical.

`KeyManagerFactory.getDefaultAlgorithm()` selects the environment's default key manager algorithm; avoid hardcoding provider/algorithm names unnecessarily. `kmf.init(...)` can throw `UnrecoverableKeyException` when keypass is wrong even though `KeyStore.load(...)` just succeeded.

**Important note:** the `KeyManagerFactory.init(KeyStore, char[])` overload supplies **a single key password**. With multiple private-key entries protected by different passwords, the provider/framework may require `KeyStore.Builder`/`KeyStoreBuilderParameters`, alias configuration, or multiple separate contexts/keystores. Do not assume every entry will open automatically.

### 2.3. `TrustManagerFactory.init` — list of trusted CAs

```java
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);
TrustManager[] managers = tmf.getTrustManagers();
```

This snippet uses a `trustStore` that is already loaded and **contains approved trust anchors**. The factory creates a provider-appropriate trust manager, typically containing `X509TrustManager`/`X509ExtendedTrustManager` to validate certificate chains per PKIX/JSSE policy.

- **Do not** take whatever certificate a server just sent and call `setCertificateEntry` to "create a trusted CA" on the fly.
- **Do not** replace `tmf.init(trustStore)` with a homemade `X509TrustManager` that returns without checking: that is **trust-all**, disabling peer authentication.
- If `null` is passed instead of a truststore to `TrustManagerFactory.init((KeyStore)null)`, the provider usually uses the **environment's default trust source**; it does not mean "skip certificate checking."
- If an empty truststore is passed, handshakes to certificates without a matching trust anchor will normally fail.

### 2.4. `SSLContext.init` — where the two manager sets meet

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(kmf.getKeyManagers(), tmf.getTrustManagers(),
             new SecureRandom());
```

This is the core assembly step. Signature:

```text
SSLContext.init(KeyManager[] km, TrustManager[] tm, SecureRandom random)
```

Meaning:

- **`km`:** supplies the **local endpoint's** credentials when TLS needs to present an identity. A standard TLS server needs a server identity; a TLS client only needs a client identity when the server requires **mTLS/client certificate**.
- **`tm`:** checks the **peer certificate chain** when peer authentication occurs. A TLS client needs to trust the server's CA; an mTLS server must also trust the client's CA.
- **`random`:** cryptographic randomness source for the JSSE provider, typically `new SecureRandom()` or letting the provider manage an appropriate source. Never substitute `java.util.Random`.
- **`SSLContext.getInstance("TLS")`:** selects a provider-supported TLS family; **does not automatically force** sockets to use only TLS 1.3. Protocol versions, cipher suites, endpoint ID, and client-auth are policies configured **on the socket/engine/SSLParameters** or HTTP framework layer.

`context.init(...)` **opens no network ports, sends no certificates, and performs no TLS handshake**. A handshake occurs only when using `SSLSocket`/`SSLEngine` with an actual connection.

## 3. Distinguishing three common initialization patterns

### 3.1. One-way TLS server (server authentication)

The server has a private key + certificate chain. The client verifies the server certificate via CA.

```text
SERVER: init(KeyManager[server identity], TrustManager[optional peer CA], random)
CLIENT: init(null, TrustManager[server CA], random)
```

In one-way TLS, the server is **not required** to have a truststore for client certificates if it does not request client-auth; a trust manager configured on the server side might not be used during that handshake. The client has a truststore to authenticate the server.

### 3.2. Mutual TLS — mTLS

Both the server **and** the client possess a private key + certificate chain, and both have a list of trusted CAs to authenticate the peer.

```text
SERVER: init(KeyManager[server identity], TrustManager[trusted client CA], random)
CLIENT: init(KeyManager[client identity], TrustManager[trusted server CA], random)
SERVER: setNeedClientAuth(true) / equivalent SSLEngine configuration
```

**Merely configuring a trust manager on the server does not enable mTLS.** The server must require a client certificate via `SSLServerSocket.setNeedClientAuth(true)` or `SSLParameters.setNeedClientAuth(true)` at the framework layer. The client must have a key manager with the corresponding certificate/key.

Some applications may use `setWantClientAuth(true)`, meaning it requests a client certificate but may allow none; that is **not equivalent** to a mandatory requirement. If business logic requires client authentication, use `needClientAuth` and verify identity/permission mapping.

### 3.3. Client needing only to authenticate an HTTPS server

An HTTPS client without a client certificate can initialize:

```java
SSLContext clientContext = SSLContext.getInstance("TLS");
clientContext.init(null, tmf.getTrustManagers(), new SecureRandom());
```

**`km == null`** does not mean "do not authenticate the server"; the responsibility of checking the server lies with the **trust manager**. Conversely, configuring a trust-all `TrustManager[]` is what compromises peer authentication.

**`tm == null`** in `SSLContext.init` lets the provider use the default trust manager; that is **different** from passing in a custom trust manager array with allow-all logic.

## 4. Initializing an identity keystore from a private key and certificate chain

The most common case is reading a **PKCS12 that already contains the private key and chain**. At the API level, however, an application might already have a validly parsed/recovered `PrivateKey` and `Certificate[]`, and then build an in-memory `KeyStore`:

```java
// Illustrative fragment, NOT a standalone program.
// privateKey: PrivateKey matching the leaf's public key.
// chain: Certificate[] ordered as [leaf, issuer, ...].
// storePassword/keyPassword: char[] from a secret manager or secure source.

KeyStore identity = KeyStore.getInstance("PKCS12");
identity.load(null, storePassword);
identity.setKeyEntry("service", privateKey, keyPassword, chain);

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identity, keyPassword);
```

### 4.1. Certificate chain requirements

The certificate chain must be ordered from the **leaf** up to the parent CAs. If intermediate CAs exist, each certificate must be signed by the next CA in line and satisfy BasicConstraints, KeyUsage, algorithms, validity, path-length, name constraints, and policy.

Example:

```text
chain[0] = Leaf:       Subject=CN=api.example, Issuer=CN=Intermediate
chain[1] = Intermediate: Subject=CN=Intermediate, Issuer=CN=Root
# Root is usually trusted separately by the client in its truststore.
```

**Do not** take an arbitrary list of certificates and concatenate them into a chain by name order. **Do not** take an untrusted CA's cert and add it to the truststore yourself just to stop TLS from reporting an error.

The private key must **match the leaf's public key**. `KeyStore.setKeyEntry` may accept some inputs at the API level without guaranteeing a working handshake; always test the actual operation and validate inputs through your certificate issuance process.

### 4.2. If the private key is in a PEM file

A PEM private key file may be in **PKCS#8**, **encrypted PKCS#8**, an algorithm-specific format, or a format exported by a specific tool. You cannot simply call `Base64.getDecoder()` on an arbitrary PEM blob and pass it to `SecretKeySpec`:

- `SecretKeySpec` is for **symmetric keys**, not RSA/EC `PrivateKey` objects.
- If it is unencrypted PKCS#8, after proper DER parsing you can use `PKCS8EncodedKeySpec` + a `KeyFactory` for the corresponding algorithm.
- If it is encrypted PKCS#8, it must be decrypted using the appropriate password/PBE and provider; never log key bytes.
- With HSM/PKCS11, the private key may exist only as a **non-exportable key handle** and should not be converted into a PEM file.
- Parsing a PEM/certificate **does not replace** verifying the key/certificate chain and trust source.

Because this lesson focuses on **JSSE**, the runnable example uses PKCS12 issued by `keytool`, avoiding ad-hoc PEM/private-key parsers.

## 5. Creating a truststore from an approved CA

In code, only when an `X509Certificate trustedCa` has been received from a **trusted provisioning channel** and verified for fingerprints/policy should the application place it into a truststore:

```java
// Fragment: trustedCa has been verified outside the context of this code.
KeyStore trustStore = KeyStore.getInstance("PKCS12");
trustStore.load(null, trustStorePassword);
trustStore.setCertificateEntry("approved-ca", trustedCa);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);
```

`setCertificateEntry` does not require the CA's private key and **does not** require a separate keypass for the CA certificate. However, **placing a certificate into a truststore is an act of granting trust**, because it can allow accepting all valid leaf certificates under that CA and the corresponding validation policy.

### 5.1. Which CAs should be trusted?

- For internal systems, the truststore can contain only the **authorized internal CAs**, without importing all public CAs.
- For public HTTPS, the JDK/OS default truststore may already hold a managed set of CAs; do not copy CA lists from an unverified website.
- For mTLS, the server may need an internal CA dedicated to signing **client certificates**, separate from the CA set for servers.
- For Certificate Pinning, understand pinning the exact identifier/key and planning rotation; bad pinning can cause outages when certificates change.

A **small truststore** reduces the trust surface but increases CA rotation operational needs. An **overly broad truststore** may accept issuers beyond business requirements. Weigh this according to environment and risk level.

### 5.2. A truststore does not replace hostname verification

A certificate chain may be validly signed by a trusted CA **yet carry the SAN of a different service**. A TLS client must verify endpoint identity based on the **hostname or IP it is connecting to**, not merely validate the CA. With `SSLSocket`, enable:

```java
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
```

This is a fragment; `socket` is an `SSLSocket` configured **before the handshake**. The name `"HTTPS"` governs endpoint verification rules matching the DNS name or IP supplied by the client when creating the socket/SSLEngine. **Do not** pass `""` or omit this property to bypass a "hostname mismatch" certificate error.

With high-level HTTP client APIs (such as `HttpClient`), many endpoint identification steps are handled by the framework per its contract; do not configure manually in a way that conflicts with or disables existing checks.

## 6. Building a test CA, certificate chain, and truststore with `keytool`

To clearly see **private key + certificate chain + trusted CA**, let's create three stores/files in an **empty temporary test directory**:

```text
ca.p12       = demo CA, containing the CA's private key (used only for issuing certs)
ca.pem       = public certificate of the demo CA
server.p12   = server private key + chain [server leaf, demo CA]
server.csr   = server's certificate signing request (CSR)
server.crt   = leaf certificate signed by the demo CA
trust.p12    = trusted certificate entry containing the demo CA, no CA private key
```

**Warning:** the commands below use the sample password `demo-changeit` on the command line so anyone can reproduce them in an isolated environment. **Never do this with production secrets**: command-line arguments can leak via shell history, process lists, and CI logs. Create fixtures in a test directory, never commit private keys/PKCS12 files, and delete them after testing; in production use a secret manager, prompts, and a controlled certificate issuance workflow.

The commands below run as single lines in Bash, PowerShell, or CMD when the JDK's `keytool` is on `PATH`. Run them in order inside an **empty directory**.

### 6.1. Step 1 — create the demo CA

```bash
keytool -genkeypair -alias ca -keyalg RSA -keysize 2048 -validity 30 -dname "CN=Demo Local CA,O=Learning" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -storetype PKCS12 -keystore ca.p12 -storepass demo-changeit -keypass demo-changeit -noprompt

keytool -exportcert -rfc -alias ca -keystore ca.p12 -storepass demo-changeit -file ca.pem
```

- `ca.p12` holds the **CA private key**; never place it into client/server apps or share it over a network.
- `ca.pem` holds only the **CA public certificate**, used to verify leaf signatures and import into the test truststore.
- `BasicConstraints: CA=true` and `KeyUsage: keyCertSign,cRLSign` give the certificate proper CA purpose in the demo.
- This self-created CA is **not** trusted by browsers/JDK by default. Only test apps that explicitly import it will trust it.

### 6.2. Step 2 — create the server identity key and CSR

```bash
keytool -genkeypair -alias service -keyalg RSA -keysize 2048 -validity 30 -dname "CN=localhost,O=Learning" -ext "SAN=dns:localhost,ip:127.0.0.1" -storetype PKCS12 -keystore server.p12 -storepass demo-changeit -keypass demo-changeit -noprompt

keytool -certreq -alias service -keystore server.p12 -storepass demo-changeit -file server.csr -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Before importing the CA-signed certificate, `server.p12` contains a private key and a temporary self-signed certificate. `server.csr` provides the public key and proposed details for the CA to issue the **official leaf certificate for the demo**. The SAN must include **`DNS:localhost`** so a client connecting to `localhost` passes hostname verification. SAN `IP:127.0.0.1` supports testing when a client connects directly by IP address.

Having only `CN=localhost` is **not** a reason to omit SAN; modern TLS stacks prefer/require SAN for endpoint name verification.

### 6.3. Step 3 — CA signs the leaf certificate

```bash
keytool -gencert -alias ca -keystore ca.p12 -storepass demo-changeit -infile server.csr -outfile server.crt -rfc -validity 30 -ext "SAN=dns:localhost,ip:127.0.0.1" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -ext "BC:critical=ca:false"
```

Meaning of the extensions:

- **SAN:** binds the server certificate to the expected hostnames or IPs.
- **KeyUsage:** enables TLS operations permitted by the algorithm and protocol.
- **ExtendedKeyUsage: `serverAuth`:** the certificate is issued for TLS server authentication.
- **BasicConstraints: `ca:false`:** the leaf does not act as a CA.

Both the demo CA certificate and the leaf have a `30-day` validity to shorten fixture lifetime. Validity still depends on the machine's clock/calendar; if expired, generate fresh fixtures.

### 6.4. Step 4 — assemble the server chain and client truststore

```bash
keytool -importcert -alias root-ca -file ca.pem -keystore server.p12 -storepass demo-changeit -noprompt

keytool -importcert -alias service -file server.crt -keystore server.p12 -storepass demo-changeit -noprompt

keytool -importcert -alias root-ca -file ca.pem -keystore trust.p12 -storetype PKCS12 -storepass demo-changeit -noprompt
```

**Order matters:** import the CA certificate into `server.p12` **before** importing the certificate reply for alias `service` so `keytool` can build the chain. Once complete:

- `server.p12` alias `service` is a **PrivateKeyEntry** with chain `[server leaf, CA]`.
- `trust.p12` alias `root-ca` is a **TrustedCertificateEntry** with no private key.
- The client trusts the demo CA because we **explicitly** put the CA into the test truststore; this is a trust configuration action, not an automatic consequence of the server's certificate.

Inspect the certificate chain with:

```bash
keytool -list -v -alias service -keystore server.p12 -storepass demo-changeit
```

The expected output includes **`Certificate chain length: 2`**. Do not use `-list` alone as proof of a complete handshake: you must also verify private key accessibility, trust anchor, SAN, EKU, and an actual TLS handshake.

### 6.5. Why not just use a self-signed leaf without a CA?

A server can use a self-signed certificate in some test environments where the client pins it directly. However, when studying **"private key, certificate chain, and trusted CAs"**, using a **demo CA signing a leaf** clearly demonstrates the boundaries:

- A CA signing a leaf **does not** give the CA private key to the server.
- The server presents the **server private key** and **certificate chain**; the client does not need the server private key.
- The client holds only the **CA public certificate** as its trust anchor.
- A leaf certificate signed by a demo CA must still have a matching SAN and be unexpired.

## 7. Runnable Java 17+: initializing two SSLContexts and doing a TLS 1.3 handshake

The **`JsseSslContextDemo.java`** program is a complete demonstration using the files from section 6. It:

1. Loads `server.p12` with `KeyStore.load`; verifies alias `service` is a key entry with a two-certificate chain.
2. Loads `trust.p12` containing one trusted CA certificate.
3. Initializes `KeyManagerFactory` from the identity keystore; `TrustManagerFactory` from the truststore; combines them into the **server SSLContext**.
4. Initializes the **client SSLContext** solely from the truststore (no client private key because this is **one-way TLS**).
5. Opens an `SSLServerSocket` on loopback `127.0.0.1` with an OS-chosen port; uses a client `SSLSocket`, sets `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`, and performs a **TLS 1.3** handshake.
6. Exchanges a single byte value `41` and the server returns `42`, proving both sides have a real TLS channel rather than merely having created an `SSLContext`.

No internet, external DNS, or public server is needed. The server runs one internal task to accept **one** connection, then closes the socket/Executor. This file is for testing only; do not deploy it as a multi-client server.

### 7.1. Complete source code: `JsseSslContextDemo.java`

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class JsseSslContextDemo {
    private static KeyStore loadPkcs12(Path file, char[] password)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, password);
        }
        return store;
    }

    private static SSLContext createServerContext(KeyStore identity,
            char[] privateKeyPassword, KeyStore trustStore) throws Exception {
        KeyManagerFactory keys = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keys.init(identity, privateKeyPassword);

        TrustManagerFactory trust = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trust.init(trustStore);

        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(keys.getKeyManagers(), trust.getTrustManagers(),
                new SecureRandom());
        return ctx;
    }

    private static SSLContext createClientContext(KeyStore trustStore)
            throws Exception {
        TrustManagerFactory trust = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trust.init(trustStore);

        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, trust.getTrustManagers(), new SecureRandom());
        return ctx;
    }

    private static void exchangeOnce(SSLContext serverContext,
            SSLContext clientContext) throws Exception {
        try (SSLServerSocket listener = (SSLServerSocket) serverContext
                .getServerSocketFactory()
                .createServerSocket(0, 20,
                        InetAddress.getByName("127.0.0.1"))) {
            listener.setEnabledProtocols(new String[]{"TLSv1.3"});
            listener.setSoTimeout(10_000);

            ExecutorService workers = Executors.newSingleThreadExecutor();
            Future<String> serverJob = workers.submit(() -> {
                try (SSLSocket peer = (SSLSocket) listener.accept()) {
                    peer.setEnabledProtocols(new String[]{"TLSv1.3"});
                    peer.setSoTimeout(10_000);
                    peer.startHandshake();
                    int value = peer.getInputStream().read();
                    peer.getOutputStream().write(value + 1);
                    peer.getOutputStream().flush();
                    return peer.getSession().getProtocol();
                }
            });

            try {
                // TCP socket goes to 127.0.0.1, but the TLS identity is localhost.
                try (Socket tcp = new Socket("127.0.0.1",
                        listener.getLocalPort());
                     SSLSocket tls = (SSLSocket) clientContext
                             .getSocketFactory()
                             .createSocket(tcp, "localhost",
                                     listener.getLocalPort(), true)) {
                    tls.setEnabledProtocols(new String[]{"TLSv1.3"});
                    tls.setSoTimeout(10_000);
                    SSLParameters parameters = tls.getSSLParameters();
                    parameters.setEndpointIdentificationAlgorithm("HTTPS");
                    tls.setSSLParameters(parameters);

                    tls.startHandshake();
                    tls.getOutputStream().write(41);
                    tls.getOutputStream().flush();
                    int response = tls.getInputStream().read();

                    System.out.println("client protocol: "
                            + tls.getSession().getProtocol());
                    System.out.println("response 42: " + (response == 42));
                }
                System.out.println("server protocol: "
                        + serverJob.get(10, TimeUnit.SECONDS));
            } finally {
                workers.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java JsseSslContextDemo server.p12 trust.p12");
        }
        String demoValue = System.getenv("JSSE_DEMO_PASSWORD");
        if (demoValue == null || demoValue.isEmpty()) {
            throw new IllegalArgumentException(
                    "Set JSSE_DEMO_PASSWORD for the local fixture");
        }
        char[] password = demoValue.toCharArray();
        try {
            KeyStore identity = loadPkcs12(Path.of(args[0]), password);
            KeyStore trustStore = loadPkcs12(Path.of(args[1]), password);

            System.out.println("identity key entry: "
                    + identity.isKeyEntry("service"));
            System.out.println("identity chain length: "
                    + identity.getCertificateChain("service").length);
            System.out.println("trusted CA entries: " + trustStore.size());

            SSLContext server = createServerContext(
                    identity, password, trustStore);
            SSLContext client = createClientContext(trustStore);
            exchangeOnce(server, client);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

**Demo password:** the code reads the password from the `JSSE_DEMO_PASSWORD` environment variable instead of putting secrets directly into Java source. Environment variables **are not a secure secret store by default**: they can still leak via debug tools, process dumps, or the runtime depending on the OS. This lesson only uses a sample password in a local environment; production uses an appropriate secret manager/credential provider. `String demoValue` is not erased from the Java heap by `Arrays.fill(char[])`, because Java `String` is immutable; this is a limitation of the demo.

### 7.2. Compile and run with Bash/Linux/macOS

After creating the fixtures in the same directory as the Java file:

```bash
javac -encoding UTF-8 JsseSslContextDemo.java
export JSSE_DEMO_PASSWORD=demo-changeit
java JsseSslContextDemo server.p12 trust.p12
unset JSSE_DEMO_PASSWORD
```

### 7.3. Compile and run with PowerShell/Windows

```powershell
javac -encoding UTF-8 JsseSslContextDemo.java
$env:JSSE_DEMO_PASSWORD = "demo-changeit"
java JsseSslContextDemo server.p12 trust.p12
Remove-Item Env:JSSE_DEMO_PASSWORD
```

**Do not run on a public host**: this is a loopback TLS test and performs no authorization. Do not commit `server.p12` or `ca.p12` to the repository. If the runtime does not support TLS 1.3, the program will fail at `setEnabledProtocols`/handshake; this lesson requires **Java 17+ with a provider supporting TLSv1.3**, without automatically falling back to legacy TLS.

### 7.4. Tested expected stdout

```text
identity key entry: true
identity chain length: 2
trusted CA entries: 1
client protocol: TLSv1.3
response 42: true
server protocol: TLSv1.3
```

The code was **compiled with `javac --release 17`** and run on a compatible JDK: the server chain has 2 certificates, the truststore has 1 CA, the client performs a TLS 1.3 handshake with endpoint identification `HTTPS`, and the response byte equals `42`. This is the result of fixtures freshly generated following the exact steps; if certificates expire or are created with a different structure, the chain count/handshake conditions may change.

### 7.5. Explanation of key code sections

**`loadPkcs12`:** separates file loading from TLS logic, uses `try-with-resources` to close the stream rather than a `FileInputStream` that might be left unclosed. Accepts a `char[]` password for loading the store. Using one demo password for both files does not make them the same type of store.

**`createServerContext`:** uses **server identity** to create key managers, and **truststore** to create trust managers. In one-way TLS, the server's trust manager is pre-installed in preparation for mTLS, though not necessarily invoked when the server does not request a client certificate.

**`createClientContext`:** passes `null` for `keyManagers` because the client **has no identity certificate** in one-way TLS. The client still **has a trust manager** for the demo CA to verify the server chain.

**`SSLContext.getInstance("TLS")`:** selects the TLS provider; `setEnabledProtocols(new String[]{"TLSv1.3"})` on the socket restricts the TLS profile for the demo. Production must follow compatibility and policy rather than enabling legacy TLS to work around trust errors.

**Outer socket and hostname:** the client opens a TCP connection to `127.0.0.1`, then wraps it via `SSLSocketFactory.createSocket(tcp, "localhost", port, true)` so the desired TLS identity is `localhost`. The certificate has SAN `DNS:localhost`, and `setEndpointIdentificationAlgorithm("HTTPS")` enforces checking this name. Omitting the target name or skipping endpoint ID checks in a raw `SSLSocket` app can allow accepting another host's certificate even from a trusted CA.

**`startHandshake()`:** this is where the handshake and certificate validation actually take place. If the chain is invalid, the CA is untrusted, or the SAN mismatches, the handshake must fail per default policy; never resolve failures using trust-all.

**Read/write 41→42:** exists solely to prove that after the handshake there is an application channel protected by TLS. There is no user permission check, application-level anti-replay, or client authentication in the example.

**Timeouts:** `setSoTimeout(10_000)` bounds socket read/accept operations at the API level; production also needs connect timeouts, appropriate handshake timeouts, overall deadlines, concurrency limits, and exception/retry handling.

**`Arrays.fill`:** reduces the lifetime of the temporary password array; it does not guarantee erasing all password copies in the environment/heap, nor does it replace secret management.

## 8. Three security points the demo intentionally preserves

### 8.1. SSLContext only prepares policy; it does not verify endpoints immediately

Many people create an `SSLContext` successfully and assume the certificate chain has already been checked. In reality:

```text
SSLContext.init(...)       => Factory/manager configuration accepted
SSLSocket.startHandshake  => Protocol negotiation + certificate validation
Application authorization => Decides whether user/service may perform the business action?
```

`SSLContext.init` connects to no host, so it does not know the actual hostname to verify. Nor does it force TLS 1.3 on its own. **Wrong CA, wrong SAN, or wrong key entry may only surface during manager initialization or handshake**, not necessarily at `SSLContext.getInstance`.

### 8.2. A certificate chain file is not a truststore on its own

When a server sends a chain [leaf, intermediate], the client uses it as a **candidate path**, but the **root must already be in the client's trust policy**. If a client accepts a root supplied by the server and promotes it to a trust anchor, an attacker can send a self-created CA and sign a forged leaf.

Similarly, importing the **demo CA** from section 6 into `trust.p12` is only meaningful in a sandbox. Do not import this CA into real truststores of learning systems, public websites, or customer applications.

### 8.3. JSSE trust manager checks the chain; hostname must be handled properly

The default trust manager follows JSSE/PKIX standards, but **hostname verification is not always enabled automatically when using raw `SSLSocket` or `SSLEngine`**. The lesson enabled `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` on the client before the handshake.

If the application uses a high-level HTTP client, the framework may already perform this step; still test it and **never disable the verifier** just to avoid SAN errors.

## 9. When do you need to add a client certificate for mTLS?

In **mTLS**, the server does not just verify a username/password or bearer token; it requires the client to prove possession of a private key whose certificate chain is trusted under **client-CA policy**.

Necessary additions:

1. Create a **client key pair + client certificate chain**, with SAN/EKU matching `clientAuth` per policy.
2. Provision the **client identity keystore** to the client and call `KeyManagerFactory.init(clientIdentity, clientKeyPassword)`.
3. Provision the **CA that issues client certificates** into the **server truststore**. If the server CA and client CA differ, both sides need appropriate truststores.
4. Initialize the client context with **both** `keyManagers` and `trustManagers`; the server context has both as well.
5. Enable **`needClientAuth`** on the socket/server socket/SSL engine or framework; otherwise, the server may not request a client certificate even though a trust manager is configured.

Illustrative server fragment:

```java
// After having a configured serverContext and created SSLServerSocket:
serverSocket.setNeedClientAuth(true);
```

Illustrative client fragment:

```java
KeyManagerFactory clientKeys = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
clientKeys.init(clientIdentityKeyStore, clientKeyPassword);

TrustManagerFactory serverCaTrust = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
serverCaTrust.init(trustStoreOfServerCAs);

SSLContext clientContext = SSLContext.getInstance("TLS");
clientContext.init(clientKeys.getKeyManagers(),
                   serverCaTrust.getTrustManagers(),
                   new SecureRandom());
```

These snippets are **not standalone programs**; they assume the proper keystore/truststore already exist. **Do not turn on `needClientAuth(true)` in the one-way demo above without preparing a client identity**, because the server will reject a client without a certificate, which is the correct behavior.

### 9.1. mTLS only authenticates key material; business permissions are separate

Even when TLS reports a valid client certificate, the application must still map the certificate to an authorized identity by **SAN/subject/public key** and lifecycle/tenant policies. A trusted CA can issue many certificates to many services or users; **it does not mean every certificate signed by that CA is allowed to call every API**.

Consider checking:

- `ExtendedKeyUsage clientAuth` when required;
- Chain to the right **client CA** and revocation/expiry policy;
- Specific service identity (SPIFFE ID/SAN or controlled internal convention);
- Endpoint/method permissions, tenant, and application-layer constraints.

### 9.2. Difference between `needClientAuth` and `wantClientAuth`

| Setting | Meaning | Consequence |
| --- | --- | --- |
| `setNeedClientAuth(true)` | Client authentication is mandatory | A client without a valid certificate must be rejected per protocol/policy |
| `setWantClientAuth(true)` | Client authentication is desired if available | May allow a client that presents no certificate; insufficient for mandatory requirements |
| Client auth disabled | Common one-way TLS | Server presents identity; client verifies server |

Some frameworks recreate `SSLParameters` or manage the handshake in their own way; verify which settings are effective at actual runtime rather than only reading a config file.

## 10. Store formats and certificate chains when integrating with Java

### 10.1. PKCS12/JKS/JCEKS/PKCS11

| Type | Common role | Notes |
| --- | --- | --- |
| `PKCS12` | File-based identity/truststore that can contain private keys/certificates | PBE/entry-password capabilities vary across providers and tools |
| `JKS` | Legacy Java keystore | Do not pick legacy JKS solely for a separate keypass; review protection level/compatibility |
| `JCEKS` | Legacy store supporting secret keys | Not the default choice for TLS identity; requires security policy review |
| `PKCS11` | KeyStore-like view of a token/HSM | Private keys may be non-exportable; PIN/provider handles replace password files |
| `KeyStore.getDefaultType()` | Runtime's default type | Can vary via security properties; specify type explicitly when interoperability is needed |

Many systems use PEM certificates while keeping private keys in an HSM: you can still create a `KeyManager` via the appropriate provider. **You are not required to export private keys into PKCS12** to use JSSE if the provider supports in-device private-key operations.

### 10.2. Key length/algorithm does not replace the trust chain

If an RSA-2048 leaf has a valid chain but the CA is untrusted, TLS will not accept it merely because the RSA key is 2048 bits long. If a leaf uses RSA-3072 yet has SAN `other.example` while the client connects to `localhost`, endpoint identification must still reject it. Validity of a TLS identity comprises **public/private key match, certificate chain, trust anchor, validity, key usage/EKU, algorithms, and endpoint name**.

### 10.3. Do not load the wrong file

`ca.p12` contains the CA private key used for issuance, **not** the server's identity store. `trust.p12` contains the CA certificate, **not** the keystore holding the server's private key. If you only glance at filenames and accidentally load `ca.p12` as the server identity, the app may present an inappropriate certificate or inadvertently grant server code access to the CA private key — a severe incident.

**Only the service's own private key** is provisioned to that service; the root CA private key must remain under CA/HSM procedures with strictly restricted access.

## 11. Initializing SSLContext in HTTP libraries/frameworks

### 11.1. Java `HttpClient` (Java 11+)

With `java.net.http.HttpClient`, you can pass a custom SSLContext into the builder:

```java
// Illustrative fragment, not a standalone program:
HttpClient client = HttpClient.newBuilder()
        .sslContext(clientContext)
        .build();
```

`clientContext` here must use the desired trust managers. `HttpClient` manages connection/hostname validation per JSSE and its own API contract; never enable an "insecure hostname verifier" to bypass certificate errors. Never take a `serverContext` holding a test CA private key and use it for a production client.

### 11.2. Spring Boot, Tomcat, Jetty, and other frameworks

Frameworks usually provide equivalent configuration fields:

- Keystore path/type, **store password**, alias, and **key password**;
- Truststore path/type/password;
- Client authentication mode;
- Protocol/cipher-suites policy;
- Certificate reload/rotation settings.

Property names and default behavior vary by **framework version**. Never copy an arbitrary YAML snippet assuming every framework understands it the same way. Verification means running a real handshake and checking the certificate chain, SAN, TLS version, client-auth policy, and post-rotation behavior.

### 11.3. Default SSLContext and system properties

Java has system properties such as `javax.net.ssl.keyStore`, `javax.net.ssl.keyStorePassword`, `javax.net.ssl.trustStore`, and `javax.net.ssl.trustStorePassword` that affect **certain default JSSE configurations**. However:

- An `SSLContext` manually initialized via `kmf/tmf` **does not automatically** use those system properties if you passed explicit key/trust managers.
- `SSLContext.getDefault()` is the process-wide default context; mutating system properties at runtime after contexts/connection pools have initialized **does not guarantee** all sockets update automatically.
- When using multiple trust policies for different tenants/services, it is usually better to **create independent contexts and manage their lifecycles explicitly**, avoiding constant mutation of global system properties.

## 12. Diagnosing SSLContext, key manager, and handshake errors

| Location/error | Common cause | How to check |
| --- | --- | --- |
| `KeyStore.load` reports `IOException` | Wrong storepass, corrupted file, incompatible format/PBE | Type/provider, path, storepass, backup |
| `KeyManagerFactory.init` throws `UnrecoverableKeyException` | Wrong key password or unreadable entry | Alias, keypass, provider, key entry |
| `identity.isKeyEntry(alias) == false` | Wrong alias or certificate-only entry | `keytool -list -v`, check entry type |
| `getCertificateChain(alias) == null` | No matching chain | Re-import leaf/intermediate in proper order, verify key match |
| `SSLContext.init` fails to build managers | Provider/algorithm mismatch, invalid parameters | JDK security providers, private key handle, key/trust manager types |
| `SSLHandshakeException: PKIX path building failed` | No trusted path to a CA in truststore, missing intermediate, other PKIX constraints | Truststore, approved CA, chain, EKU/validity, algorithm constraints |
| `SSLHandshakeException` with hostname/SAN mismatch | Server certificate does not match the name/address the client connects to | SAN DNS/IP, endpoint ID, how socket is created, SNI |
| Handshake has no matching certificate | Server lacks key entry or cannot select a certificate/key type | `KeyManager`, alias, TLS algorithms, certificate chain |
| mTLS reports missing client certificate | Client sends no identity, or server requires clientAuth while truststore doesn't match | Client key manager, server trust CA, and `needClientAuth` |
| `protocol_version` / `handshake_failure` | No overlapping TLS protocol/cipher suite, policy mismatch | EnabledProtocols, JDK version, crypto policy |
| `certificate_expired` | Certificate outside `notBefore/notAfter` | Check UTC clock, reissue from the right CA |
| Truststore has CA yet still rejects | Wrong SAN/EKU/algorithm/policy, bad chain, revocation | Read PKIX cause and test each constraint |
| Demo test reports `Connection refused` | Server socket not open yet, blocked by loopback/firewall, or wrong port | Loopback support, port, timeout; do not disable TLS to fix TCP issues |

### 12.1. Know which step failed

Reading logs by stage:

```text
1) KeyStore.load(identity)      -> Reading file/store password
2) KeyManagerFactory.init(...)  -> Unlocking private key entries
3) TrustManagerFactory.init(...) -> Preparing trust anchors
4) SSLContext.init(...)         -> Combining managers
5) SSLSocket.startHandshake()   -> Protocol selection, certificate chain,
                                   peer validation, key proof
6) Application request          -> Authorization and business logic
```

If it stops at step 1 or 2, the error does not necessarily involve the remote peer's certificate. If it stops at step 5, examine **trust path, hostname, protocol, key usage, algorithm constraints, client-auth, and revocation policy**. Do not just randomly swap a password string and assume everything is fixed.

### 12.2. Debugging TLS without leaking secrets

The JDK provides JSSE debug logging, e.g., property `javax.net.debug=ssl,handshake` in test environments. Debug logs can contain **certificate details, hostnames, SNI, and connection metadata**, so they require access control and retention policies rather than pushing directly to public log systems. **Never log private key bytes, store/keypass passwords, or TLS secrets.**

Do not enable session-key logging like `SSLKEYLOGFILE` or equivalent options in production without strict controls; session key files can decrypt TLS traffic and must be protected like secrets if ever used for authorized diagnostics.

### 12.3. Recommended negative tests

- Replace the truststore with one that lacks the demo CA: **handshake must fail** due to no matching trust anchor.
- Use a hostname other than `localhost` while endpoint identification remains enabled: **must be rejected** if SAN does not cover that name.
- Supply an expired server certificate or one lacking the right EKU: **rejected** per PKIX/JSSE policy.
- Use the wrong private-key password: `KeyManagerFactory` initialization must fail if entry protection requires a specific password.
- Enable `needClientAuth(true)` while the client has no identity: mTLS must fail per policy.
- Use a TLS version/cipher suite with no overlap: handshake fails; never fall back to insecure legacy protocols just to make tests pass.

Negative cases are **security expectations to verify**, not fixed stdout of the one-way program. Exception types may vary by provider/JDK.

## 13. Managing the lifecycle of SSLContext, certificates, and CAs

### 13.1. When a private key or certificate is rotated

Several independent changes can occur:

1. **Changing store password:** changes the credential protecting the store, without necessarily changing the private key/certificate.
2. **Changing key password:** changes the entry protection info, without changing key material if no new key is generated.
3. **Renewing/replacing certificate:** the same private key may receive a new certificate per policy, but chain/SAN/EKU still need updating.
4. **Rotating private key:** generate a new key pair and matching certificate; do not use a mismatched old chain.
5. **Rotating CAs/trust anchors:** client/server truststores must have a properly sourced transition plan, rather than "trusting all CAs" to avoid downtime.

**An already-initialized `SSLContext` does not automatically detect changes to a PKCS12 file on disk.** Some frameworks support reloading, but a standard code-created JSSE context is not a live file watcher by default. You must build a new context with the new store/certs, validate it, and switch traffic/connection pools via a safe mechanism.

### 13.2. Two-phase CA rotation

For example, the server's CA changes from A to B:

- Preparation: client truststores are updated to **trust B** through an approved process; A and B may be temporarily trusted during a transition window.
- Replace server identity with leaf+chain issued by B.
- Test handshake and hostname with real applications.
- After an appropriate transition window: remove A when no longer needed, narrowing the trust policy.

Do not simply switch the CA on the server before clients know CA B, because handshakes will fail, and do not keep old trust anchors indefinitely when no longer permitted.

### 13.3. Compromised private key

If the server's raw private key is compromised, **changing the `.p12` password does not make that key safe again**. You must rotate the key pair/certificate, revoke the affected certificate per PKI, assess data/sessions, and update server/clients per incident response. A compromised CA private key has a broader blast radius and may require replacing the trust anchor and the entire issued chain.

### 13.4. Revocation checking is not guaranteed across all configurations

TLS uses chain validation via `TrustManager`/PKIX, but whether **CRL/OCSP revocation checking** is enabled and how it behaves depends on **JDK/provider/configuration**. Never assume that having a truststore and calling `SSLContext.init` means every revoked certificate is immediately detected.

If the application has strict revocation requirements, configure the PKIX revocation checker/OCSP/CRL and network/cache policies explicitly. Weigh fail-closed vs. soft-fail against your risk model and test with actually revoked certificates.

## 14. Common conceptual mistakes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| "SSLContext only needs a private key." | Lacks identity chain and trust policy | Key manager from private key + chain; trust manager from approved CAs |
| "Putting the CA in the server's identity keystore makes the client trust it." | The client has an independent truststore | Provision the right CA into the client truststore |
| "Putting the server's leaf into the truststore on every connection." | Automatically promotes external data to trusted; vulnerable to MITM | Trust CAs/pins via verified channels and policy |
| "`KeyStore.load` succeeded, so TLS is ready." | Key not recovered yet, no handshake yet | Verify alias/chain/keypass and run TLS |
| "`storepass` always equals `keypass`." | Different roles; tools/providers have constraints | Configure each step properly; document when shared |
| "Only `TrustManagerFactory` gives the server an identity." | Trust manager verifies peers, does not prove local identity | `KeyManagerFactory` and private key/certificate chain |
| "`KeyManagerFactory` verifies the remote server's CA." | Key manager handles local identity | Client trust manager verifies the remote chain |
| "`SSLContext.getInstance("TLS")` always forces TLS 1.3." | Only selects the TLS context/provider | Set protocol policy on socket/engine |
| "Raw `SSLSocket` always checks the hostname automatically." | Endpoint identification may need explicit enabling | `setEndpointIdentificationAlgorithm("HTTPS")` |
| "Having the right certificate CN is enough; no SAN needed." | Modern rules use SAN | Issue certificates with proper DNS/IP SANs |
| "Trust-all manager to fix `PKIX path building failed`." | Disables authentication; exposes to MITM | Fix truststore/chain/hostname from the real source |
| "mTLS only needs the server to have a truststore." | Server may not request a client certificate | Enable `needClientAuth` and provision client identity |
| "Any CA-signed client cert may call every API." | Authentication differs from authorization | Map SAN/identity and specific permissions |
| "After rotating `.p12` files, the old SSLContext updates itself." | Contexts/connection pools do not auto-reload | Safely rebuild and swap the context |
| "If TLS works, the root CA private key must be on the server." | Server only needs the leaf private key | CA private key stays in CA/HSM; truststore needs only public cert |
| "Trusting all CAs prevents outages." | Expands trust beyond requirements | Govern anchors by scope and policy |

## 15. Pre-deployment checklist for SSLContext

1. **Identity:** is the service's private key properly issued and protected? Does the leaf certificate have a matching public key and proper DNS/IP SANs?
2. **Chain:** does `getCertificateChain(alias)` contain leaf followed by intermediate in order, with no missing required issuers? Are certificates valid with proper KeyUsage/EKU?
3. **Store/key password:** does `KeyStore.load` use storepass, and `KeyManagerFactory.init` use keypass matching the provider? Neither hardcoded nor logged?
4. **CA trust:** is the CA set source-verified and appropriately scoped, with no automatic importing of peer certificates?
5. **Factory:** are `KeyManagerFactory` (for local identity) and `TrustManagerFactory` (for peer trust) properly wired into `SSLContext.init`?
6. **TLS protocol:** are only policy-approved TLS versions/cipher suites enabled, with insecure fallbacks disallowed?
7. **Endpoint ID:** for raw JSSE clients, is hostname verification configured for the target name and checked against SAN?
8. **mTLS:** if needed, does the client have a key manager, and does the server have a trust manager for the right client CA with `needClientAuth(true)` enabled?
9. **Authorization:** are service/user identity and business permissions checked after the TLS handshake, rather than treating any valid CA as full access?
10. **Testing:** did a real client/server handshake succeed; do missing CA, wrong SAN, wrong keypass, and missing client cert cases fail properly?
11. **Operations:** are rotation, context reload, trust anchor overlap, backup/restore, revocation policy, and auditing tested?
12. **Environment protection:** no private keys/secret-bearing `.p12` files in source control, no CA private keys in runtime, and no TLS secrets in logs?

## 16. Self-check questions

**Q1.** To build an HTTPS server from `server.p12`, is calling `KeyStore.load` with storepass enough?  
**Answer:** **No.** You need the key manager to recover the private key with keypass, a valid certificate chain, `SSLContext.init`, socket configuration, and a real handshake.

**Q2.** The server has chain [leaf, intermediate, root]. The client does not trust the root; can it trust the server just because the root is sent in the chain?  
**Answer:** **No.** The root trust anchor must be provisioned to the client as trusted **beforehand**, not promoted from a server-sent root into a trusted CA.

**Q3.** How do `KeyManagerFactory` and `TrustManagerFactory` differ?  
**Answer:** `KeyManagerFactory` prepares the **local identity's private key + certificate chain**; `TrustManagerFactory` prepares the **rules/CA set** to verify the **peer's** certificate.

**Q4.** Can a TLS client without a client certificate call `SSLContext.init(null, tm, random)`?  
**Answer:** **Yes.** `null` key managers mean no local client identity is provided in this configuration; trust managers still verify the server certificate.

**Q5.** A TLS server has installed the client CA's trust manager. Is it automatically doing mTLS?  
**Answer:** **No.** The server must also require client authentication (`needClientAuth`), the client must have the right key manager, and certificate policy must be satisfied.

**Q6.** A server certificate has a valid CA chain, yet its SAN is only `wrong.example` while the client connects to `localhost`. What should happen?  
**Answer:** **Reject** when hostname verification is properly enabled; a valid CA signature does not replace endpoint identity verification.

**Q7.** Switching from a server certificate signed by CA A to one signed by CA B without updating the client truststore—what happens?  
**Answer:** Handshakes may fail due to lacking trust anchor B. An overlap and trust rotation plan between both sides is required.

**Q8.** If you know the demo CA's private key, should you put it into the client's `trust.p12`?  
**Answer:** **No.** A truststore needs only the **public CA certificate**. The CA private key must be protected by the CA system.

**Q9.** Does `SSLContext.getInstance("TLS")` guarantee that connections always use TLS 1.3 and verify hostnames?  
**Answer:** **No.** You must configure protocols/SSLParameters or use a framework with verified defaults. The demo explicitly enables TLS 1.3 and endpoint identification.

**Q10.** After replacing `server.p12` on disk, does an already-initialized `SSLContext` automatically use the new certificate on all connections?  
**Answer:** **Cannot be assumed.** Context and connection pool lifecycles/reloading must be managed per framework/provider.

**Q11.** If the server certificate expires, can we fix it by making `TrustManager` ignore the expiration date?  
**Answer:** **No.** Issue/rotate a valid certificate, check clocks and chains; never bypass security checks.

**Q12.** In the demo, `server.p12` has chain length 2 and `trust.p12` has one CA. Why doesn't that result mean these are safe production certificates?  
**Answer:** The CA was self-created in a sandbox, keys/passwords are demo fixtures, scope is localhost-only, and validity is short. Production requires proper PKI/trust distribution, secret management, authorization, revocation, operations, and testing.

### References

- [Java SE 21 — SSLContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html): `getInstance`, `init`, and socket factories.
- [Java SE 21 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): loading local identities/private keys.
- [Java SE 21 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): creating trust managers from a KeyStore.
- [Java SE 21 — SSLParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification and client-auth.
- [Java SE 21 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS handshake, managers, truststores, SSLContext.
- [Java SE 21 — keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): generating key pairs, CSRs, signing certificates, importing chains, exporting/importing CAs.
- [RFC 5280 — X.509 Public Key Infrastructure](https://www.rfc-editor.org/rfc/rfc5280): certificate path validation, key usage, and X.509 policy.

### Key takeaways

**`SSLContext` is configured along two independent axes: `KeyManagerFactory` for the application's own private key + certificate chain, and `TrustManagerFactory` for the CAs the application already trusts to verify peers.** A certificate chain sent by a server does not create a trust anchor on its own; a truststore does not supply a server private key; creating an `SSLContext` does not replace a handshake, hostname verification, or authorization. Test the flow **load store → recover key → TLS handshake → endpoint identity → business logic** with policy-compliant certificates and CAs, while protecting keys, passwords, and rotation mechanisms.