# 16.6 X509ExtendedKeyManager Selecting Aliases and X509ExtendedTrustManager Verifying Peers

## 1. Two distinct responsibilities in JSSE

**JSSE (Java Secure Socket Extension)** implements TLS using components such as `SSLContext`, `SSLSocket`, `SSLEngine`, `KeyManager`, and `TrustManager`. In a certificate-based TLS handshake, there are **two separate questions**:

1. **"Which certificate and private key will I present?"** — `X509ExtendedKeyManager` chooses an *alias* pointing to a matching private key + certificate chain for **this endpoint itself**. When JSSE needs a signature or private-key operation, the key manager supplies the private key via the chosen alias.
2. **"Do I trust the peer's certificate?"** — `X509ExtendedTrustManager` verifies the **peer's certificate chain**, PKIX constraints, intended usage, algorithms, and **connection context** (socket/engine) per configuration and policy. If untrusted, it must throw `CertificateException` instead of allowing the handshake to finish.

Both components use X.509 terminology, yet **do not replace each other**:

| Component | Primary inputs | Decision | Output |
| --- | --- | --- | --- |
| `X509ExtendedKeyManager` | `keyType`, `issuers`, `Socket` or `SSLEngine`, local keystore | Selects a local alias so client/server presents a matching certificate | `String alias` or `null`; `getPrivateKey` and `getCertificateChain` |
| `X509ExtendedTrustManager` | `X509Certificate[] chain` from **peer**, `authType`, and connection | Is the peer chain trustworthy, valid, and compliant with constraints? | Returns normally when accepted; throws `CertificateException` when rejected |
| `KeyManagerFactory` | KeyStore with private key and certificate chain, password/protection | Initializes provider key managers | `KeyManager[]` |
| `TrustManagerFactory` | TrustStore or PKIX trust anchors/policy | Initializes trust managers | `TrustManager[]` |

A certificate may be **selected for sending** by a key manager yet **rejected** by the peer's trust manager. Conversely, the peer may trust the chain, yet the handshake still fails because the key manager cannot find a compatible alias/private key.

### Roles of client, server, and mTLS

```text
                   TLS server                         TLS client
        +-----------------------------+    +-----------------------------+
        | KeyManager                  |    | KeyManager (in mTLS)        |
        | selects server cert alias   |    | selects client cert alias   |
        +--------------+--------------+    +--------------+--------------+
                       |                                  |
        sends Certificate/CertificateVerify -->    <-- sends Certificate/
                                              CertificateVerify (mTLS)
                       |                                  |
        +--------------v--------------+    +--------------v--------------+
        | TrustManager                |    | TrustManager                |
        | verifies client (if mTLS)   |    | verifies server             |
        +-----------------------------+    +-----------------------------+
```

In **server-auth-only** TLS, the client normally does not send a certificate and the client key manager may not be called to select an alias. In **mutual TLS (mTLS)**, the server requires a client certificate; **both sides** typically have a key manager to present their own certificate and a trust manager to verify the other side.

**Never turn "an alias was selected" into "the peer trusts the certificate."** An alias is merely the name of a local entry (usually in a `KeyStore`), not a trust decision.

## 2. KeyManager, X509KeyManager, and X509ExtendedKeyManager

`X509KeyManager` is the interface for selecting X.509 credentials with `Socket`. `X509ExtendedKeyManager` extends it, adding overloads for **`SSLEngine`**. When building a TLS client/server on NIO, an HTTP framework, a proxy, or a custom network stack using `SSLEngine`, the extended overloads are essential.

| Method | Function |
| --- | --- |
| `getClientAliases(String keyType, Principal[] issuers)` | Lists local aliases usable as a client certificate for the key type and issuer constraints |
| `chooseClientAlias(String[] keyTypes, Principal[] issuers, Socket socket)` | Selects a suitable client alias during a socket-based handshake |
| `getServerAliases(String keyType, Principal[] issuers)` | Lists aliases usable as a server certificate for the key type/issuers |
| `chooseServerAlias(String keyType, Principal[] issuers, Socket socket)` | Selects a server alias on a handshake socket |
| `chooseEngineClientAlias(String[] keyTypes, Principal[] issuers, SSLEngine engine)` | Selects a client alias for `SSLEngine` |
| `chooseEngineServerAlias(String keyType, Principal[] issuers, SSLEngine engine)` | Selects a server alias for `SSLEngine` |
| `getCertificateChain(String alias)` | Retrieves the certificate chain presented for the alias, usually leaf to intermediate |
| `getPrivateKey(String alias)` | Retrieves the private key **of the local alias** for signing/handshaking; may be an opaque provider handle |

### Meaning of keyType, issuers, and alias

- **`keyType`:** the key/algorithm type fitting the handshake context, e.g., `"RSA"`, `"EC"`; exact value names and selection constraints may depend on provider, TLS version, and signature schemes. **Do not** assume a TLS 1.3 cipher suite named `TLS_AES_128_GCM_SHA256` requires an AES key for certificate selection; TLS 1.3 negotiates signature schemes separately.
- **`String[] keyTypes` on the client:** multiple credential types may fit the server's request. The key manager considers permitted types and issuer constraints; returns `null` if no credential matches.
- **`Principal[] issuers`:** list of CA distinguished names accepted by the side requesting the certificate, or `null` when unrestricted. This is a **selection hint/constraint**, not a certificate validating that a chain is trustworthy. Apply/respect constraints semantically rather than ignoring them.
- **`alias`:** local key entry identifier known to the manager; it may correspond to a `KeyStore` alias, though a provider may synthesize internal aliases. Never assume an alias is a hostname, user ID, proof of identity, or stable identifier across providers.
- **`getCertificateChain(alias)` and `getPrivateKey(alias)`:** must correspond to the **same credential**. The private key must match the public key in the leaf certificate. Never mix alias A's chain with alias B's private key.

Alias selection may also need handshake details such as **SNI**, TLS version, signature algorithms, and key usages. With `Socket`, inspect the handshake session on `SSLSocket` when available; with `SSLEngine`, inspect `engine.getHandshakeSession()` and related context. **The handshake session may be `null` if not ready yet**; never treat missing data as a reason to return arbitrary credentials.

### Why not hardcode `"server"` as the alias for every handshake?

When a server holds multiple certificates (e.g., RSA and ECDSA, or multiple virtual hosts), alias selection must account for:

- `keyType` and signature schemes supported by the peer;
- **Configured/authorized** SNI and virtual host;
- Certificate SAN, chain, validity, KU/EKU, and disabled algorithms;
- Issuer constraints and policy;
- Cipher/TLS version, and provider or HSM capabilities.

Just because an alias named `"server"` exists does not mean it is a valid choice for every SNI/key type. If no valid credential exists, **return `null`/let the handshake fail** instead of picking the wrong tenant or presenting an identity mismatch certificate.

## 3. TrustManager and X509ExtendedTrustManager

`X509TrustManager` has three basic methods:

```java
void checkClientTrusted(X509Certificate[] chain, String authType)
        throws CertificateException;
void checkServerTrusted(X509Certificate[] chain, String authType)
        throws CertificateException;
X509Certificate[] getAcceptedIssuers();
```

`X509ExtendedTrustManager` extends it with **four context-aware overloads**:

```java
void checkClientTrusted(
        X509Certificate[] chain, String authType, Socket socket)
        throws CertificateException;
void checkServerTrusted(
        X509Certificate[] chain, String authType, Socket socket)
        throws CertificateException;
void checkClientTrusted(
        X509Certificate[] chain, String authType, SSLEngine engine)
        throws CertificateException;
void checkServerTrusted(
        X509Certificate[] chain, String authType, SSLEngine engine)
        throws CertificateException;
```

The overloads accepting `Socket`/`SSLEngine` are crucial: the provider can use **SSLParameters, endpoint identification algorithm, handshake session, requested server name, negotiated signature algorithm, and TLS-specific constraints** when verifying the peer. **Certificate path** validation typically checks trust anchor, validity, signatures, BasicConstraints, KeyUsage/ExtendedKeyUsage, algorithm constraints, critical extensions, and profile-specific revocation policies.

**Critical boundary:** `checkServerTrusted(chain, authType, socket)` **must not be replaced by** `delegate.checkServerTrusted(chain, authType)` when a socket is available, because you can lose context-dependent checks, especially hostname/endpoint identification. Likewise, in `SSLEngine`, pass the engine intact to the delegate's extended overload.

### "Accept" does not mean returning true

`checkServerTrusted`/`checkClientTrusted` return `void`:

- **Success:** returns normally (no exception).
- **Failure:** throws `CertificateException` (or a subtype) so the TLS handshake rejects the peer.

A custom trust manager like the following is **unsafe**:

```java
// INTENTIONALLY WRONG: DO NOT USE IN PRODUCTION.
@Override public void checkServerTrusted(
        X509Certificate[] chain, String authType) {
    // Do nothing => trust-all, does not check certificate chain.
}
```

Even having `getAcceptedIssuers()==new X509Certificate[0]` does **not** make `check...Trusted` methods safe automatically. Never use trust-all to "fix PKIX path building failed" or "fix hostname mismatch."

### Role of authType

`authType` is a parameter supplied by JSSE indicating the authentication type used in the handshake per the API and provider contract—**not the EKU OID `serverAuth`/`clientAuth`** and not an app-chosen value. Never write policies like `authType.equals("serverAuth")`. Never deduce a fixed `authType` from a TLS 1.3 cipher suite name: TLS version/signature schemes/providers can vary the representation.

## 4. KeyStore and TrustStore: different materials

In JSSE there are typically **two stores with distinct roles**:

| Store | Contents | Used by | Contains local private key? |
| --- | --- | --- | --- |
| **KeyStore** | `PrivateKeyEntry`: private key + matching certificate chain | `KeyManagerFactory` | Yes, for software credentials; HSMs may use handles |
| **TrustStore** | `TrustedCertificateEntry` or trusted anchors/certificates | `TrustManagerFactory` | Usually **no** private key needed |
| **Server key store** | Server private key and server certificate/chain | Server key manager | Yes |
| **Client key store** | Client private key and client certificate/chain | Client key manager in mTLS | Yes |
| **Server trust store** | CAs/certificates trusted by the server for **client certificates** | Server trust manager | No |
| **Client trust store** | CAs/certificates trusted by the client for **server certificates** | Client trust manager | No |

In mTLS, **the server checks the client** and **the client checks the server**. Swapping truststores (e.g., client trusts only the client certificate instead of the server's issuer) causes the handshake to fail even when both key managers pick valid aliases.

### Initializing factories properly

Illustrative snippet inside a Java method, not a standalone program:

```java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(keyStore, keyPasswordChars);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext ctx = SSLContext.getInstance("TLS");
ctx.init(kmf.getKeyManagers(), tmf.getTrustManagers(),
         new SecureRandom());
```

Note that `KeyManagerFactory.getDefaultAlgorithm()` or `TrustManagerFactory.getDefaultAlgorithm()` **selects the factory algorithm**; it does not mean "used the right KeyStore," "enabled hostname verification," or "configured mTLS." Those must be configured separately on the socket/engine/server.

**Some factories return only basic `X509KeyManager`/`X509TrustManager` or a different implementation depending on the JSSE profile:** the runnable example in this lesson explicitly requires `X509Extended...` types. When the extended type is unavailable, **fail closed with `IllegalStateException`** rather than casting blindly or building a trust-all adapter.

## 5. Configuring a secure mTLS handshake

For an mTLS channel over `SSLSocket`:

1. Server has a certificate + private key matching hostname/algorithms and an initialized `KeyManagerFactory`.
2. Client has a `TrustManagerFactory` bound to trust anchors for the server. Client enables **endpoint identification**: `socket.getSSLParameters().setEndpointIdentificationAlgorithm("HTTPS")` and **re-applies** `socket.setSSLParameters(...)` before `startHandshake()`.
3. Server sets **`setNeedClientAuth(true)`**, not merely `setWantClientAuth(true)`. `need` forces the client to provide a valid certificate; `want` may permit a peer with no certificate.
4. Client has a key manager supplying a client certificate/private key matching the issuer/key type; server has a trust manager trusting the client's issuer/certificate per policy.
5. Both execute the TLS handshake; `X509ExtendedKeyManager` is invoked to choose the right alias and `X509ExtendedTrustManager` is invoked to verify the peer.
6. Upon success, the application **must still** perform authorization based on the verified identity: role, tenant, endpoint/purpose, ACL, scopes. mTLS certificate authentication **does not** automatically authorize all APIs.

If the app uses NIO/`SSLEngine`, install **both the `chooseEngine...Alias` and `check...Trusted(..., SSLEngine)` overloads**, and ensure peer host and endpoint identification are configured properly. Using `Socket` overloads for an engine is the wrong context.

### SSLParameters and hostname verification

In a raw `SSLSocket` client, a `TrustManager` verifying the chain **does not automatically guarantee** hostname checking unless the matching endpoint identification is enabled. In HTTPS client frameworks, this is usually configured by the stack; with raw sockets/engines, check explicitly.

Example:

```java
// Illustrative snippet; socket must be a client SSLSocket before handshake.
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
```

`"HTTPS"` here is the endpoint identification algorithm per `SSLParameters`, **not** a TLS protocol string or cipher suite. A server certificate for IP `127.0.0.1` needs an `iPAddress` SAN; `CN=localhost` alone cannot replace SAN in modern protocols.

## 6. Java 17+ hands-on: wrapping extended managers without bypassing trust

This exercise runs **server and client on loopback `127.0.0.1`** with demo certificates:

- Two separate local KeyStores `server.p12`/`client.p12`, each containing one private key alias and a self-signed certificate for its peer.
- Two separate truststores `server-trust.p12`/`client-trust.p12`. Server-trust trusts the test client cert; client-trust trusts the test server cert.
- `ObservedKeyManager extends X509ExtendedKeyManager` **delegates to the manager created by KeyManagerFactory**, counting successful alias selections. Do not log aliases/private keys/certificate chains to avoid exposing unnecessary metadata.
- `ObservedTrustManager extends X509ExtendedTrustManager` **delegates to the matching overload**; increments counters **only after the delegate check succeeds**. Never implement "trust-all."
- The mTLS handshake mandates a client certificate, checks HTTPS endpoint identity against the IP SAN, and exchanges one byte of application data post-handshake.
- Runs two separate sessions for **TLSv1.3** and **TLSv1.2**, verifying both sides agree on the negotiated protocol.

**Security:** This is a demo program using **temporary self-signed certificates** imported by the test app itself as trust anchors. In production, trust only CAs or public keys/certificates distributed via trusted channels; never import a certificate sent by a remote peer and immediately use it as a trust anchor.

### 6.1 Creating certificates and truststores (PowerShell)

Run these commands in the **same PowerShell session** with JDK 17+ `keytool`. Both certificates here are test fixtures, and password `changeit` is purely illustrative.

```powershell
$t = Join-Path $env:TEMP ("extended-managers-demo-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $t | Out-Null
$pw = "changeit"  # DEMO ONLY; never hardcode production passwords.

# Server: SAN with iPAddress 127.0.0.1 so client verifies hostname/IP.
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost" -ext "SAN=ip:127.0.0.1,dns:localhost" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -validity 7 -storetype PKCS12 -keystore (Join-Path $t "server.p12") -storepass $pw -keypass $pw -noprompt

# Client: certificate for mTLS client authentication.
keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=client-demo" -ext "KU:critical=digitalSignature" -ext "EKU=clientAuth" -validity 7 -storetype PKCS12 -keystore (Join-Path $t "client.p12") -storepass $pw -keypass $pw -noprompt

# Export PUBLIC CERTIFICATE, not the private key.
keytool -exportcert -alias server -keystore (Join-Path $t "server.p12") -storepass $pw -rfc -file (Join-Path $t "server.pem")
keytool -exportcert -alias client -keystore (Join-Path $t "client.p12") -storepass $pw -rfc -file (Join-Path $t "client.pem")

# Server trusts client, client trusts server.
keytool -importcert -alias client -file (Join-Path $t "client.pem") -keystore (Join-Path $t "server-trust.p12") -storetype PKCS12 -storepass $pw -noprompt
keytool -importcert -alias server -file (Join-Path $t "server.pem") -keystore (Join-Path $t "client-trust.p12") -storetype PKCS12 -storepass $pw -noprompt
```

`-noprompt` is used only for fixtures you just created yourself. **Never automatically import remote/unverified certificates** into production truststores. Never reuse these `server.p12`/`client.p12` files for a real service.

### 6.2 Complete Java program

Save as **`ExtendedManagersMutualTlsDemo.java`** in your working directory (can be different from `$t`). The code is **Java 17+ compatible**, including all six trust manager overloads, four alias selection paths, and required key manager getters.

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.*;

public final class ExtendedManagersMutualTlsDemo {
    private static KeyStore load(Path path, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(path)) {
            store.load(stream, password);
        }
        return store;
    }

    private static X509ExtendedKeyManager keyManager(
            Path path, char[] password) throws Exception {
        KeyManagerFactory factory = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        factory.init(load(path, password), password);
        for (KeyManager manager : factory.getKeyManagers()) {
            if (manager instanceof X509ExtendedKeyManager ext) return ext;
        }
        throw new IllegalStateException("Extended key manager unavailable");
    }

    private static X509ExtendedTrustManager trustManager(
            Path path, char[] password) throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(load(path, password));
        for (TrustManager manager : factory.getTrustManagers()) {
            if (manager instanceof X509ExtendedTrustManager ext) return ext;
        }
        throw new IllegalStateException("Extended trust manager unavailable");
    }

    private static final class ObservedKeyManager extends X509ExtendedKeyManager {
        private final X509ExtendedKeyManager base;
        final AtomicInteger serverSelections = new AtomicInteger();
        final AtomicInteger clientSelections = new AtomicInteger();

        ObservedKeyManager(X509ExtendedKeyManager base) { this.base = base; }
        private String count(String alias, boolean server) {
            if (alias != null) {
                (server ? serverSelections : clientSelections).incrementAndGet();
            }
            return alias;
        }
        @Override public String chooseClientAlias(
                String[] types, java.security.Principal[] issuers, Socket socket) {
            return count(base.chooseClientAlias(types, issuers, socket), false);
        }
        @Override public String chooseServerAlias(
                String type, java.security.Principal[] issuers, Socket socket) {
            return count(base.chooseServerAlias(type, issuers, socket), true);
        }
        @Override public String chooseEngineClientAlias(
                String[] types, java.security.Principal[] issuers, SSLEngine engine) {
            return count(base.chooseEngineClientAlias(types, issuers, engine), false);
        }
        @Override public String chooseEngineServerAlias(
                String type, java.security.Principal[] issuers, SSLEngine engine) {
            return count(base.chooseEngineServerAlias(type, issuers, engine), true);
        }
        @Override public String[] getClientAliases(
                String type, java.security.Principal[] issuers) {
            return base.getClientAliases(type, issuers);
        }
        @Override public String[] getServerAliases(
                String type, java.security.Principal[] issuers) {
            return base.getServerAliases(type, issuers);
        }
        @Override public X509Certificate[] getCertificateChain(String alias) {
            return base.getCertificateChain(alias);
        }
        @Override public PrivateKey getPrivateKey(String alias) {
            return base.getPrivateKey(alias);
        }
    }

    private static final class ObservedTrustManager extends X509ExtendedTrustManager {
        private final X509ExtendedTrustManager base;
        final AtomicInteger serverChecks = new AtomicInteger();
        final AtomicInteger clientChecks = new AtomicInteger();

        ObservedTrustManager(X509ExtendedTrustManager base) { this.base = base; }
        @Override public void checkServerTrusted(
                X509Certificate[] chain, String authType, Socket socket)
                throws CertificateException {
            base.checkServerTrusted(chain, authType, socket);
            serverChecks.incrementAndGet();
        }
        @Override public void checkClientTrusted(
                X509Certificate[] chain, String authType, Socket socket)
                throws CertificateException {
            base.checkClientTrusted(chain, authType, socket);
            clientChecks.incrementAndGet();
        }
        @Override public void checkServerTrusted(
                X509Certificate[] chain, String authType, SSLEngine engine)
                throws CertificateException {
            base.checkServerTrusted(chain, authType, engine);
            serverChecks.incrementAndGet();
        }
        @Override public void checkClientTrusted(
                X509Certificate[] chain, String authType, SSLEngine engine)
                throws CertificateException {
            base.checkClientTrusted(chain, authType, engine);
            clientChecks.incrementAndGet();
        }
        @Override public void checkServerTrusted(
                X509Certificate[] chain, String authType)
                throws CertificateException {
            base.checkServerTrusted(chain, authType);
            serverChecks.incrementAndGet();
        }
        @Override public void checkClientTrusted(
                X509Certificate[] chain, String authType)
                throws CertificateException {
            base.checkClientTrusted(chain, authType);
            clientChecks.incrementAndGet();
        }
        @Override public X509Certificate[] getAcceptedIssuers() {
            return base.getAcceptedIssuers();
        }
    }

    private record Side(SSLContext context, ObservedKeyManager key,
                        ObservedTrustManager trust) {}

    private static Side side(Path keys, Path trust, char[] password)
            throws Exception {
        ObservedKeyManager km = new ObservedKeyManager(keyManager(keys, password));
        ObservedTrustManager tm = new ObservedTrustManager(trustManager(trust, password));
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(new KeyManager[]{km}, new TrustManager[]{tm}, new SecureRandom());
        return new Side(context, km, tm);
    }

    private static void test(String version, Side server, Side client)
            throws Exception {
        int sAlias = server.key.serverSelections.get();
        int cAlias = client.key.clientSelections.get();
        int sTrust = server.trust.clientChecks.get();
        int cTrust = client.trust.serverChecks.get();
        try (SSLServerSocket listener = (SSLServerSocket)
                server.context.getServerSocketFactory().createServerSocket(
                        0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(20000);
            listener.setEnabledProtocols(new String[]{version});
            listener.setNeedClientAuth(true);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> future = executor.submit(() -> {
                    try (SSLSocket peer = (SSLSocket) listener.accept()) {
                        peer.setSoTimeout(20000);
                        peer.setEnabledProtocols(new String[]{version});
                        peer.setNeedClientAuth(true);
                        peer.startHandshake();
                        int request = peer.getInputStream().read();
                        peer.getOutputStream().write(request + 1);
                        peer.getOutputStream().flush();
                        return peer.getSession().getProtocol();
                    }
                });
                try (SSLSocket socket = (SSLSocket)
                        client.context.getSocketFactory().createSocket(
                                "127.0.0.1", listener.getLocalPort())) {
                    socket.setSoTimeout(20000);
                    socket.setEnabledProtocols(new String[]{version});
                    SSLParameters p = socket.getSSLParameters();
                    p.setEndpointIdentificationAlgorithm("HTTPS");
                    socket.setSSLParameters(p);
                    socket.startHandshake();
                    socket.getOutputStream().write(17);
                    socket.getOutputStream().flush();
                    int response = socket.getInputStream().read();
                    String serverProtocol = future.get(20, TimeUnit.SECONDS);
                    System.out.println(version + " negotiated="
                            + (version.equals(socket.getSession().getProtocol())
                                && version.equals(serverProtocol)));
                    System.out.println(version + " serverAliasSelected="
                            + (server.key.serverSelections.get() > sAlias));
                    System.out.println(version + " clientAliasSelected="
                            + (client.key.clientSelections.get() > cAlias));
                    System.out.println(version + " clientVerifiedServer="
                            + (client.trust.serverChecks.get() > cTrust));
                    System.out.println(version + " serverVerifiedClient="
                            + (server.trust.clientChecks.get() > sTrust));
                    System.out.println(version + " applicationData="
                            + (response == 18));
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 5)
            throw new IllegalArgumentException(
                    "server.p12 server-trust.p12 client.p12 client-trust.p12 password");
        char[] password = args[4].toCharArray();
        try {
            Side server = side(Path.of(args[0]), Path.of(args[1]), password);
            Side client = side(Path.of(args[2]), Path.of(args[3]), password);
            test("TLSv1.3", server, client);
            test("TLSv1.2", server, client);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 6.3 Compiling, running, and verified output

In the **same PowerShell session** while `$t`/`$pw` are set, from the directory containing `ExtendedManagersMutualTlsDemo.java`:

```powershell
javac --release 17 -encoding UTF-8 -d $t ExtendedManagersMutualTlsDemo.java
java -cp $t ExtendedManagersMutualTlsDemo (Join-Path $t "server.p12") (Join-Path $t "server-trust.p12") (Join-Path $t "client.p12") (Join-Path $t "client-trust.p12") $pw
```

Exact **12-line output as verified on JDK 17+ with SunJSSE**:

```text
TLSv1.3 negotiated=true
TLSv1.3 serverAliasSelected=true
TLSv1.3 clientAliasSelected=true
TLSv1.3 clientVerifiedServer=true
TLSv1.3 serverVerifiedClient=true
TLSv1.3 applicationData=true
TLSv1.2 negotiated=true
TLSv1.2 serverAliasSelected=true
TLSv1.2 clientAliasSelected=true
TLSv1.2 clientVerifiedServer=true
TLSv1.2 serverVerifiedClient=true
TLSv1.2 applicationData=true
```

**Interpretation of each group:**

- `negotiated=true`: both sides report the same TLS version, matching the sole version enabled for that run. Do not extrapolate that all Internet peers support both versions.
- `serverAliasSelected=true`: the server-side delegate key manager selected an accepted local server certificate alias; this **counts successful selections**, not a separate proof of trust.
- `clientAliasSelected=true`: because the server requested a client certificate (`setNeedClientAuth(true)`), the client side selected an alias to present the mTLS certificate.
- `clientVerifiedServer=true`: the client-side **extended trust manager** called the right delegate and incremented the counter only after the server check succeeded.
- `serverVerifiedClient=true`: the server side also verified the client certificate successfully, demonstrating the difference between mTLS and server-only TLS.
- `applicationData=true`: after the handshake, the client sent byte `17` and the server returned `18`, forcing both sides to complete the handshake flow and confirming the channel can exchange data. Some handshake implementations may finish read/write at different points; never rely solely on `Future.get` without proper I/O/timeouts.
- Counters are captured **before and after each session**, because the same `Side` objects stay alive across both runs. Counters prove the delegate callbacks **ran and succeeded** in that session; they are not an analysis tool for the entire TLS certificate policy.

**There is no trust-all here:** `ObservedTrustManager` passes `chain`, `authType`, and `socket/engine` intact to `base`, while the client enables HTTPS endpoint identification. The two truststores trust the **generated test certificates** and do not blindly accept every chain. In real systems, trusted roots must come from controlled trust configuration, never created from unverified peer-sent certificates.

**Why not print aliases/private keys?** Key aliases, issuers, chains, and SNI are sometimes sensitive operational metadata. Minimal boolean/count logs and secret-free error codes are safer than logging `getPrivateKey(alias).getEncoded()` (never do that).

When finished, remove the demo fixtures:

```powershell
if ($t -like (Join-Path $env:TEMP "extended-managers-demo-*")) {
    Remove-Item -LiteralPath $t -Recurse -Force
}
```

Deleting files does not guarantee wiping all copies on SSDs/snapshots; **use test private keys only** and never store them in repositories.

## 7. Why must a decorator implement and delegate completely?

The example uses two decorator classes whose sole job is **observation, not changing policy**. A real wrapper might add custom certificate selection or authorization checks, yet it must honor the full superclass contract.

### 7.1 Key manager methods you must not forget

When extending `X509ExtendedKeyManager`, implement:

- `getClientAliases` and `getServerAliases`: may return `null` if no matching credential exists.
- `chooseClientAlias` / `chooseServerAlias`: for socket-based handshakes.
- `chooseEngineClientAlias` / `chooseEngineServerAlias`: for `SSLEngine`.
- `getCertificateChain` and `getPrivateKey`: JSSE needs the certificate chain/private key of the selected alias.

Never implement `chooseEngineServerAlias` and **always return `null`** thinking the app only uses sockets: many frameworks use an engine even when the protocol runs over TCP. When migrating from blocking sockets to NIO, certificate selection can stop working if engine overloads are missing.

If you need to enforce a specific alias:

1. Let the delegate select candidates per `keyType`/issuers/provider.
2. Accept only aliases allowed by verified tenant/hostname config, key usage, certificate chain, algorithms, and handshake context.
3. If no suitable alias exists, fail closed with `null`/a clear error.
4. Never return an arbitrary alias lacking a matching private key or certificate.

**SNI is not identity authentication.** Client-proposed SNI helps the server pick a virtual host, yet the SNI name itself does not prove the client is authorized. The server certificate must match the hostname and the client must still check SAN/endpoint identification. Never use SNI to grant tenant access or override mTLS client certificate trust policies.

### 7.2 Trust manager methods you must not forget

When extending `X509ExtendedTrustManager`, there are **six** overloads:

- `checkServerTrusted(chain, authType)`, `checkClientTrusted(chain, authType)` (basic);
- `checkServerTrusted(chain, authType, Socket)` and `checkClientTrusted(chain, authType, Socket)`;
- `checkServerTrusted(chain, authType, SSLEngine)` and `checkClientTrusted(chain, authType, SSLEngine)`.

Plus `getAcceptedIssuers()`. When wrapping a trusted delegate, every extended method must **call the delegate's matching overload**; never fall back to the basic overload just because it is simpler to code. Callers may need the exact context to verify hostname/SNI/SSLParameters/signature algorithms.

**When adding post-chain-verification checks**, follow the principle of *monotonic restriction*: call the safe delegate first, then **only tighten** policy—e.g., checking a securely distributed public-key pin or subject mapping. When requirements fail, throw `CertificateException`. Do not strip out trust chain verification just because you added pinning (unless it is a thoroughly analyzed and approved alternative pinning design).

Conceptual snippet (not a standalone program):

```java
@Override
public void checkServerTrusted(X509Certificate[] chain, String authType,
                               SSLEngine engine) throws CertificateException {
    delegate.checkServerTrusted(chain, authType, engine);
    // Only after delegate verification succeeds:
    // verifyApprovedPublicKeyPin(chain[0]); // throws CertificateException on mismatch
}
```

**Pin carefully:** never hardcode raw certificate DER bytes without a rotation/backup plan. Public key pins (SPKI hashes) and certificate pins have different lifetimes/rotation dynamics. A pin can block even valid certificates during key rotation, so maintain protected rollout/escape hatches; never turn this into "skip CA trust when the pin matches" without a clear threat model.

## 8. Socket and SSLEngine: context affects the outcome

| Criterion | `SSLSocket` | `SSLEngine` |
| --- | --- | --- |
| Communication model | Blocking I/O over a socket | TLS state machine with ByteBuffers in NIO/async/frameworks |
| Method picking local client key | `chooseClientAlias(...,Socket)` | `chooseEngineClientAlias(...,SSLEngine)` |
| Method picking local server key | `chooseServerAlias(...,Socket)` | `chooseEngineServerAlias(...,SSLEngine)` |
| Method verifying peer on client | `checkServerTrusted(...,Socket)` | `checkServerTrusted(...,SSLEngine)` |
| Method verifying peer on mTLS server | `checkClientTrusted(...,Socket)` | `checkClientTrusted(...,SSLEngine)` |
| Endpoint identification | `SSLParameters` on socket | `SSLParameters` on engine; requires proper host context |
| SNI/handshake context | Via `SSLSession`/`ExtendedSSLSession` depending on timing | `engine.getHandshakeSession()` and SNI/peer host if available |
| Risk when wrapper misses overloads | May work on sockets yet fail when switching frameworks | Engine path easily fails or loses verification context |

**Especially with SSLEngine:** when creating an engine for a TLS client, supply an appropriate peer host/port (`SSLContext.createSSLEngine(host, port)`) and enable endpoint identification if required by the protocol. Calling hostless `createSSLEngine()` and assuming "HTTPS hostname verification runs automatically" can leave identity info missing. If the handshake goes through a reverse proxy, ensure the hostname checked is the expected service identity, **not** merely the proxy's IP.

When overriding alias selection by SNI, read `ExtendedSSLSession.getRequestedServerNames()` if the handshake session and data support it; do not rely on old `getSession()` mid-handshake and never let null/unsupported SNI become a reason to bypass policy.

## 9. Selecting a certificate and verifying a peer do not equal application authorization

Even when mTLS succeeds:

- **Trust manager** proves the certificate/chain meets PKIX/TLS constraints for that environment. It **does not** map a client certificate to an "admin" role or tenant.
- **Certificate subject/CN** is not a sufficiently strong application identifier in every profile. Use approved mapping rules (SAN URI/DNS, SPIFFE ID, or relevant certificate field), trusted issuer, policy, and key lifecycle.
- **KeyUsage/ExtendedKeyUsage** defines cryptographic/protocol purpose: `serverAuth` differs from `clientAuth`. A `clientAuth` certificate must never automatically pass as a `serverAuth` identity.
- **Hostname identification** checks server identity per TLS/HTTPS; it does not replace client API authorization.
- **KeyManager alias selection** may depend on SNI, issuers, signature algorithms, and key types; it does not mean the alias owner has permission to access every service.

For instance, on an API managing sensitive data, "mTLS handshake succeeded" alone is insufficient; the service must compare the verified client identity against endpoint/dataset/tenant permissions, and audit it.

Never log raw private keys or full certificate chains on every handshake. When forensics require it, log key ID/certificate fingerprint, issuer, certificate serial, role, and TLS version per data policy, without putting secrets in logs.

## 10. Real-world issues and how to diagnose them

| Error symptom | Likely cause | Check/remediation |
| --- | --- | --- |
| `SSLHandshakeException: no suitable certificate` | KeyManager lacks an alias matching `keyType`/issuers/signature schemes | Check KeyStore entries, chain, provider, `choose...Alias`, and certificate profile |
| `no available authentication scheme` | Server cannot find a credential matching key type/protocol | Check certificates, signature schemes, server key manager, and TLS 1.3 compatibility |
| `PKIX path building failed` | TrustStore does not trust CA/peer cert or lacks intermediates | Check exact trust anchors, chain, and trust manager; never use trust-all |
| `No subject alternative names matching ...` | HTTPS endpoint identification found peer host differs from SAN | Reissue cert with matching SAN or connect to matching hostname; do not disable hostname checks |
| `bad_certificate` / `certificate_unknown` | Peer rejected certificate/chain | Inspect logs on both ends; distinguish selection failure from trust failure |
| `certificate_required` / client handshake rejected | Server requires client certificate yet client key manager returned null/wrong type | Check `setNeedClientAuth`, client KeyStore, issuer list, `clientAuth` EKU |
| mTLS "succeeds" even though client has no cert | Server set `setWantClientAuth(true)` or failed to enable need | Use `setNeedClientAuth(true)` on the right socket/engine |
| Socket TLS succeeds yet SSLEngine framework fails | Wrapper overrode only Socket methods; engine methods return null/fail to delegate | Implement engine overloads too |
| Hostname unchecked when using a wrapper | `checkServerTrusted(...,Socket)` called basic overload, or missing HTTPS SSLParameters | Delegate to exact contextual overload and enable endpoint identification |
| `InvalidKeyException` / key not found | Alias lacks private key or key handle/provider mismatch | Align `getCertificateChain`, `getPrivateKey`, provider, and key policy |
| Multi-cert server sends wrong virtual host | Alias selected only by `keyType`, ignoring SNI/tenant and SAN | Implement safe SNI policy selection; test each hostname |
| `getAcceptedIssuers()` returns list breaking client selection | Advertised CA list mismatches client's issuer chain | Check trust anchors and issuer constraints; never return arbitrary lists |
| Valid certificate chain yet app rejects client | mTLS authentication passed but lacks role/permission | Map verified identity to business authorization |
| Fails during certificate rotation | Old alias/chain cached, new alias lacks key, truststore un-updated | Roll out trust first, rotate keys/certs with versioning, and test |
| Fails only on TLS 1.3 | Key/cert/sig scheme or group/provider differs from TLS 1.2 | Inspect JSSE trace, signature algorithms, and KeyManager alias compatibility |
| `ClassCastException` getting extended manager | Factory returned implementation conforming only to legacy interface | Use `instanceof`, switch to supporting provider; never force-cast or trust-all |
| `KeyStoreException` / `UnrecoverableKeyException` | Wrong password, alias, store type, or token permissions | Check stores, PIN, key material, and provider |

**Never fix errors by returning arbitrary aliases or using trust-all.** A failed handshake is a useful security boundary; fix the root cause via proper truststore/credentials/hostname/profile.

### Safe debugging and observation

In staging/test, JSSE tracing can be enabled:

```powershell
java "-Djavax.net.debug=ssl,handshake,keymanager,trustmanager" -cp $t ExtendedManagersMutualTlsDemo (Join-Path $t "server.p12") (Join-Path $t "server-trust.p12") (Join-Path $t "client.p12") (Join-Path $t "client-trust.p12") $pw
```

Logs contain certificate details, hostnames, issuers, aliases, and handshake metadata, and depending on debug flags can be very sensitive. **Use only with test certificates, restrict log access, and never share raw production logs publicly.** Never enable traffic-secret dumping modes. Across frameworks, also check enabled protocols/suites, SNI, ALPN, trust anchors, and TLS termination hops.

### Tests to include before deploying

- Server certificate with matching SAN and `serverAuth` EKU is verified by the client; wrong SAN is rejected.
- Valid mTLS client certificate is verified by the server; missing client cert when `needClientAuth=true` must fail.
- Client/server certificates from untrusted issuers are rejected, never silently imported into the truststore.
- A `clientAuth`-only certificate is rejected as a `serverAuth` identity per profile.
- Missing key alias matching type/issuer: handshake fails, never falls back to another tenant.
- Using `SSLEngine`: engine overloads are invoked and context/hostname checks remain effective.
- Certificate rotation: aliases/cert chains and trust anchors change in a controlled way without unplanned outages.
- Test policy-compliant TLS 1.2 and 1.3; never downgrade to weak protocols because of a certificate error.

## 11. Checklist for designing X509Extended managers

- [ ] Clearly separate **local credential selection** and **peer trust validation** as two distinct steps.
- [ ] `KeyManagerFactory` receives the right KeyStore/private key chain; `TrustManagerFactory` receives the right TrustStore/trust anchors.
- [ ] Implement all `X509ExtendedKeyManager` methods, especially `chooseEngineClientAlias` / `chooseEngineServerAlias`.
- [ ] Implement all six overloads of `X509ExtendedTrustManager`; delegation receives the exact `Socket`/`SSLEngine`.
- [ ] Never use empty `checkServerTrusted`, trust-all, or fake `getAcceptedIssuers` to bypass chain verification.
- [ ] Client verifies endpoint identity via HTTPS/SAN on raw sockets or engines with proper peer host.
- [ ] mTLS server enables `setNeedClientAuth(true)` and verifies client chains against the right truststore.
- [ ] Alias selection respects `keyType`, `issuers`, SNI/context, algorithm policy, chain, and key usage.
- [ ] Never hardcode one alias for all tenants/hosts; fail closed if credentials do not match.
- [ ] Successful authentication flows into application authorization based on the permitted certificate identity.
- [ ] Manage key/cert/truststore rotation, backups, auditing, and real handshake testing.
- [ ] Restrict debugging and logs; never print private keys or TLS secrets to observe callbacks.

## 12. Knowledge self-check

1. **What does `X509ExtendedKeyManager` do?** Selects a local key alias and supplies the certificate chain/private key for the handshake.
2. **What does `X509ExtendedTrustManager` do?** Verifies the peer's certificate chain, throwing `CertificateException` if untrusted.
3. **Who selects and who verifies the server certificate?** The server key manager selects it; the client trust manager verifies it.
4. **In mTLS, who selects the client certificate?** The client key manager, when the server requests client authentication.
5. **How does `setNeedClientAuth(true)` differ from `setWantClientAuth(true)`?** Need mandates the client supply a valid certificate; want may allow omission.
6. **Which alias methods does Socket need?** `chooseClientAlias` and `chooseServerAlias`; engines need `chooseEngineClientAlias`/`chooseEngineServerAlias`.
7. **When writing an extended trust decorator, why preserve Socket/SSLEngine?** To retain hostname, handshake, SSLParameters, and policy context for the delegate.
8. **Does `checkServerTrusted` return a `boolean`?** No, `void`; it throws `CertificateException` on rejection.
9. **Does `getAcceptedIssuers()` return a trust decision for a specific certificate?** No; it returns the list of issuer certificates per contract, without verifying the current chain.
10. **Is `authType` the `serverAuth` OID?** No; it is handshake authentication-type info supplied by JSSE.
11. **Is any alias in a `KeyStore` enough for a handshake?** No; it needs a matching private key/chain, `keyType`, issuer, protocol, and provider policy.
12. **Does SNI authenticate a client's tenant permission?** No; SNI is a virtual-host selection hint, not proof of access rights.
13. **Why does the client need `setEndpointIdentificationAlgorithm("HTTPS")` in the raw SSLSocket demo?** To verify the IP/DNS SAN of the server identity.
14. **If a wrapped trust manager only calls `delegate.checkServerTrusted(chain,authType)`, what is the risk?** It loses socket/engine-dependent checks, potentially weakening hostname/connection validation.
15. **Does successful mTLS automatically grant permission to call every API?** No; certificate identity must be mapped to business roles/permissions.
16. **Why does the example have separate `server-trust.p12` and `client-trust.p12`?** Both sides trust **different** peers; the server needs to trust the client, and the client needs to trust the server.
17. **If the client cannot select an alias in mTLS, what should it do?** Return `null`/fail handshake and fix credentials/issuer constraints; never send the wrong private key or pick the wrong tenant.
18. **If a factory does not return an extended manager, how to handle it?** Check type with `instanceof`, fail closed, or use an evaluated provider/adapter; never blind-cast.
19. **Does both TLS 1.2 and 1.3 succeeding on loopback prove another Internet service supports them?** No; the result applies only to the two configured local contexts.
20. **How do you safely add custom restrictions?** Delegate full peer validation first, then only add rejection conditions with `CertificateException`; never replace trust with "accept all."

## Standards and Java API documentation

- [X509ExtendedKeyManager, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedKeyManager.html)
- [X509ExtendedTrustManager, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html)
- [X509KeyManager / X509TrustManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509KeyManager.html)
- [KeyManagerFactory / TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html)
- [SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [SSLParameters and endpoint identification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [SSLSocket and SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html)
- [SSLEngine and handshake context](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html)
- [ExtendedSSLSession, SNI, and peer signature algorithms](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/ExtendedSSLSession.html)
- [Oracle Java 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [RFC 5280: X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html)
- [RFC 8446: TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)