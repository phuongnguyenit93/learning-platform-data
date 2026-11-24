# 15.3 TLS 1.2, TLS 1.3, and How to Read Available Protocol Configurations

## 1. Goal: "Supported TLS" differs from "Used TLS"

**Transport Layer Security (TLS)** protects data in transit between two endpoints: negotiating cryptographic mechanisms, authenticating parties per policy, establishing session keys, encrypting records, and verifying record integrity. With Java 17+, most applications work with TLS through **JSSE (Java Secure Socket Extension)**: `SSLContext`, `SSLSocket`, `SSLServerSocket`, `SSLEngine`, `SSLParameters`, `SSLSession`, and `KeyManager`/`TrustManager`.

In operations, distinct questions frequently arise:

1. Which TLS versions does the JDK/provider **know about**?
2. Which versions is an `SSLContext` or socket **configured to allow**?
3. Does the Java Security policy **forbid** any algorithms or versions?
4. Which versions does the peer server/client **accept** and manage to negotiate?
5. Which version and cipher suite did an **actually completed handshake connection** use?

These five questions can yield **five different answers**. For example, on a tested SunJSSE runtime, `SSLSocket.getSupportedProtocols()` contains `TLSv1`, `TLSv1.1`, `SSLv3`, while `getEnabledProtocols()` by default only has `TLSv1.3` and `TLSv1.2`. **Do not** conclude the machine allows SSLv3/TLS 1.0 just because they appear in the "supported" list.

Learning objectives:

- Distinguish the handshake, key schedule, and cipher suites of **TLS 1.2** and **TLS 1.3**.
- Correctly read supported/enabled/default/disabled/negotiated from JSSE.
- Understand the impact of `jdk.tls.disabledAlgorithms`, `jdk.tls.client.protocols`, `jdk.tls.server.protocols`, `https.protocols`, `SSLParameters`, and providers.
- Inspect the real protocol/cipher suite **after the handshake** with `SSLSession`.
- Diagnose `protocol_version`, `handshake_failure`, and `SSLHandshakeException` errors without disabling protections.
- Run two Java 17 programs yourself: configuration inventory and TLS 1.2/TLS 1.3 loopback connections with trust/hostname verification.

This lesson focuses on TLS over TCP via JSSE; **DTLS**, QUIC/TLS, and application protocols like HTTP/2 and HTTP/3 have their own constraints. Do not extrapolate the status of every service on a machine from a single TLS connection.

## 2. Comparing TLS 1.2 and TLS 1.3

TLS 1.2 is specified by **RFC 5246**; TLS 1.3 by **RFC 8446**. Both are usable for compatible, properly configured systems, but TLS 1.3 simplifies many details and removes obsolete cryptographic methods.

| Aspect | TLS 1.2 | TLS 1.3 |
| --- | --- | --- |
| RFC | `5246` | `8446` |
| Typical full handshake | Usually about **2 RTT** before application data, depending on handshake type | Usually **1 RTT**, supports resumption and optional **0-RTT early data** per protocol |
| Key exchange | Depends on cipher suite: ECDHE, DHE, historical RSA key transport... | Redesigned (EC)DHE/PSK key schedule model; eliminates RSA key transport |
| Cipher suites | Names typically carry **key exchange + authentication + symmetric encryption + hash/MAC** | Names primarily describe **AEAD + hash**; key exchange groups and signature schemes negotiated separately |
| Example cipher suite | `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | `TLS_AES_128_GCM_SHA256` |
| Application data encryption | GCM/ChaCha20-Poly1305 or older mechanisms depending on suite | **AEAD** such as AES-GCM or ChaCha20-Poly1305 |
| Key derivation | TLS 1.2 PRF and key block/Finished per protocol | **HKDF-based key schedule**, secrets separated per phase |
| Forward secrecy | Yes with ECDHE/DHE; **not inherently present** with static RSA key transport | Typically yes with (EC)DHE; **PSK-only lacks the same forward secrecy** without fresh DHE |
| Renegotiation | Has renegotiation mechanisms requiring safe handling per version/provider | **No TLS 1.2 renegotiation**, has post-handshake mechanisms such as `KeyUpdate` |
| Certificate authentication | Certificate + handshake signatures per cipher suite/profile | Certificate + separately negotiated signature schemes (e.g., RSA-PSS/ECDSA) |
| Compatibility | Broader legacy system support | May require updating proxies/load balancers/servers or hardcoded cipher suites |

**Note:** 0-RTT early data carries **replay risk**, is unsuitable for all operations (e.g., non-idempotent transactions), and **does not mean** any Java/JSSE application supports it automatically. Do not enable 0-RTT merely because client and server advertise TLS 1.3 support.

### 2.1 Sketch of a TLS 1.2 handshake

A typical TLS 1.2 full handshake with a server certificate and ECDHE:

```text
Client                                           Server
ClientHello ------------------------------->
                           <--------------- ServerHello
                           <--------------- Certificate
                           <--------------- ServerKeyExchange
                           <--------------- ServerHelloDone
ClientKeyExchange ------------------------->
ChangeCipherSpec / Finished --------------->
                           <--------------- ChangeCipherSpec / Finished
          <======== Protected application data ========>
```

Messages vary by cipher suite, client authentication, and resumption. This is a **conceptual diagram** for comparison, not a complete byte transcript or every variant.

TLS 1.2 allows some cipher suites with legacy key exchange (e.g., RSA key transport) and historical CBC/SHA-1 mechanisms. **Never re-enable weak options just for compatibility**. For TLS 1.2 where still needed, prefer suites with **ECDHE/DHE + AEAD** permitted by security policy, and handle signatures/certificates per profile.

### 2.2 Sketch of a TLS 1.3 handshake

TLS 1.3 full handshake with key share:

```text
Client                                           Server
ClientHello + supported_versions
            + key_share -------------------->
                           <--------------- ServerHello + key_share
                           <--------------- EncryptedExtensions
                           <--------------- Certificate
                           <--------------- CertificateVerify
                           <--------------- Finished
Finished ----------------------------------->
          <======== Protected application data ========>
```

Phases after `ServerHello` are protected by handshake traffic keys. TLS 1.3 uses HKDF to separate handshake/application secrets, enabling forward-secure key exchange with fresh (EC)DHE and removing RSA key transport. In PSK resumption, message counts and secrets differ; `HelloRetryRequest` may occur if the proposed key share is unsuitable.

**Do not treat RTT count as a guaranteed connection latency:** TCP setup, DNS, proxies, network latency, crypto provider, certificate chain, OCSP, HTTP/2/ALPN, session cache, and the application all affect real latency.

### 2.3 TLS 1.2 vs. 1.3 cipher suite names

```text
TLS 1.2: TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
                |      |        |          |
           key agreement  cert  AEAD    hash/PRF

TLS 1.3: TLS_AES_128_GCM_SHA256
                  |      |
                AEAD     HKDF hash
```

In TLS 1.3, **the cipher suite name does not determine the ECDHE/DHE group or certificate signature type**. Those components are negotiated via extensions such as `supported_groups`, `key_share`, `signature_algorithms`, and `signature_algorithms_cert` as applicable. A server using an RSA certificate can still negotiate `TLS_AES_128_GCM_SHA256`; no TLS 1.3 suite needs "RSA" in its name.

**Do not specify** only a TLS 1.2 suite like `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` and expect a TLS 1.3 connection to succeed. Conversely, allowing only TLS 1.3 suite names while attempting to negotiate TLS 1.2 can cause the handshake to fail.

## 3. What do "supported", "enabled", "configured", and "negotiated" mean?

This is the most important part of **reading available protocol configurations**.

| Level | Question | Java API / info | Meaning |
| --- | --- | --- | --- |
| **Supported** | Which versions does this implementation *know*? | `SSLSocket.getSupportedProtocols()`, `SSLEngine.getSupportedProtocols()`, `SSLContext.getSupportedSSLParameters().getProtocols()` | List supported by the implementation; **may include disabled protocols** |
| **Enabled** | Which versions is the socket/engine *configured* to try? | `SSLSocket.getEnabledProtocols()`, `SSLEngine.getEnabledProtocols()`, `SSLParameters.getProtocols()` | Allowed negotiation scope from this object's side; does not prove peer acceptance |
| **Default** | What does the context/provider allow *by default* before overrides? | `SSLContext.getDefaultSSLParameters()` or a fresh socket/engine | Depends on JDK, provider, role, and security/system properties |
| **Security policy** | Are any protocols/ciphers/algorithms forbidden? | `Security.getProperty("jdk.tls.disabledAlgorithms")`, `jdk.certpath.disabledAlgorithms` | Can **block negotiation** even if code puts the protocol in enabled |
| **Peer capability** | What does the peer accept? | Server/client settings or verified handshake trace | Cannot be inferred from the local machine's `getSupportedProtocols` |
| **Negotiated** | Which version did the **handshaked** connection use? | `socket.getSession().getProtocol()`, `getCipherSuite()` | Actual value of a **specific connection**, reliable only after handshake succeeds |

Example:

```text
SunJSSE supported: [TLSv1.3, TLSv1.2, TLSv1.1, TLSv1, SSLv3, SSLv2Hello]
SunJSSE enabled:   [TLSv1.3, TLSv1.2]
Server enabled:    [TLSv1.2]
Shared usable:     [TLSv1.2]
Negotiated:        TLSv1.2 (only after handshake succeeds)
```

Even if the client supports and enables TLSv1.3, it **can** still negotiate TLSv1.2 because the server does not support/enable TLSv1.3. If the server enables only TLSv1.1 and the client enables only TLSv1.2/1.3, the handshake has **no common protocol**, though the exact error symptom depends on the implementation.

**Specifically:** many JDKs still list TLSv1/TLSv1.1 in `getSupportedProtocols()`, while `jdk.tls.disabledAlgorithms` forbids negotiating them. Even if `setEnabledProtocols(new String[]{"TLSv1"})` is accepted by the object, that does not mean a TLSv1 handshake is allowed. Never remove TLSv1/TLSv1.1/SSLv3 from the security disabled list just to "make a test pass".

### Inspection rules in the right order

1. Read **provider/JDK version and security properties**.
2. Read **supported** of the exact engine in use.
3. Read **enabled/default** before handshaking; check whether the app overrides via `setEnabledProtocols`/`SSLParameters` or system properties.
4. Inspect **cipher suites, named groups, signature schemes**, keys/certificates/trust, and the peer.
5. Perform a **real handshake** with trust/hostname verification.
6. After success, read `SSLSession.getProtocol()` and `getCipherSuite()` to see the **actually negotiated** values.

## 4. JSSE APIs for inspecting TLS

| API | Purpose | Notes |
| --- | --- | --- |
| `SSLContext.getInstance("TLS")` | Selects a generic TLS engine/provider | Does not mean "TLS 1.0 only"; inspect default/supported/actual |
| `SSLContext.init(...)` | Supplies key managers, trust managers, RNG | Trust/certificate setup cannot be inferred from the name `TLS` |
| `SSLContext.getSupportedSSLParameters()` | Supported parameters of the context | Includes supported protocols/suites but does not guarantee negotiation |
| `SSLContext.getDefaultSSLParameters()` | Enabled-by-default parameters in the context | Can differ by SunJSSE/provider and client/server role |
| `SSLSocket.getSupportedProtocols()` | Protocols known to the implementation | List may include disabled ones |
| `SSLSocket.getEnabledProtocols()` | Protocols enabled on the current socket | Only **pre-handshake/allowed** state |
| `SSLSocket.setEnabledProtocols(String[])` | Restricts protocols on the socket | Throws `IllegalArgumentException` if unsupported by implementation; policy may still block |
| `SSLParameters.getProtocols()/setProtocols(...)` | Reads/sets protocol list on a parameter object | Must be applied via `socket.setSSLParameters(...)` or engine |
| `SSLSocket.getSupportedCipherSuites()` | Cipher suites known to the implementation | Weak suites may appear yet be blocked by policy |
| `SSLSocket.getEnabledCipherSuites()` | Currently enabled suite list | Must be compatible with TLS version, key algorithm, and peer |
| `SSLSocket.startHandshake()` | Starts/waits for the handshake | Fails when protocol, trust, cipher, cert, etc. mismatch |
| `SSLSession.getProtocol()` | **Negotiated version** | Only inspect after a successful handshake |
| `SSLSession.getCipherSuite()` | **Negotiated suite** | Does not reveal the full ECDHE group or identity policy |
| `SSLEngine.getSupportedProtocols()/getEnabledProtocols()` | Equivalent for NIO/async TLS | Handshake engine must handle `NEED_WRAP`/`NEED_UNWRAP`/`NEED_TASK` states |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Enables HTTPS identity/hostname verification in JSSE | Crucial for manually created SSLSockets; requires proper trust manager |

`SSLParameters.setProtocols(...)` does not mutate an existing socket/engine automatically; you must call `setSSLParameters(...)` on that exact object before the handshake. Note: `getDefaultSSLParameters()` and socket factories do not necessarily reflect **one identical list for every socket in every role**. Use the actual socket/engine your app creates and print `getEnabledProtocols()` when diagnosing.

For `SSLEngine`, the methods share the same supported/enabled concepts; however, nonblocking handshakes require driving wrap/unwrap buffers and delegated tasks. Do not mistake creating an `SSLEngine` or reading enabled protocols for completing a handshake.

## 5. Program 1 — inventory TLS from Java without network connections

Save as **`TlsProtocolInventoryDemo.java`**, using Java 17 or newer. The program creates an `SSLContext("TLS")` and an **unconnected** `SSLSocket`, printing the provider, supported/enabled/default protocols, TLS 1.2/TLS 1.3 flags, and a few configuration properties. **No network connection and no negotiated version** occur in this program.

```java
import java.security.Security;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class TlsProtocolInventoryDemo {
    private static boolean has(String[] values, String target) {
        return Arrays.asList(values).contains(target);
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);
        SSLParameters defaults = context.getDefaultSSLParameters();
        SSLParameters supported = context.getSupportedSSLParameters();
        SSLSocketFactory factory = context.getSocketFactory();
        try (SSLSocket socket = (SSLSocket) factory.createSocket()) {
            System.out.println("contextProtocol=" + context.getProtocol());
            System.out.println("provider=" + context.getProvider().getName());
            System.out.println("supportedProtocols="
                    + Arrays.toString(socket.getSupportedProtocols()));
            System.out.println("enabledProtocols="
                    + Arrays.toString(socket.getEnabledProtocols()));
            System.out.println("defaultProtocolsFromContext="
                    + Arrays.toString(defaults.getProtocols()));
            System.out.println("supportedProtocolsFromContext="
                    + Arrays.toString(supported.getProtocols()));
            System.out.println("supportsTLS12="
                    + has(socket.getSupportedProtocols(), "TLSv1.2"));
            System.out.println("supportsTLS13="
                    + has(socket.getSupportedProtocols(), "TLSv1.3"));
            System.out.println("enabledTLS12="
                    + has(socket.getEnabledProtocols(), "TLSv1.2"));
            System.out.println("enabledTLS13="
                    + has(socket.getEnabledProtocols(), "TLSv1.3"));
            System.out.println("disabledAlgorithmsPresent="
                    + (Security.getProperty("jdk.tls.disabledAlgorithms") != null));
            System.out.println("clientProtocolsProperty="
                    + System.getProperty("jdk.tls.client.protocols", "(not set)"));
            System.out.println("httpsProtocolsProperty="
                    + System.getProperty("https.protocols", "(not set)"));
            System.out.println("noHandshakePerformed=true");
        }
    }
}
```

Compile and run from the directory containing the file:

```powershell
javac --release 17 -encoding UTF-8 TlsProtocolInventoryDemo.java
java TlsProtocolInventoryDemo
```

**Exact output in the tested SunJSSE environment** (not fixed output across every machine):

```text
contextProtocol=TLS
provider=SunJSSE
supportedProtocols=[TLSv1.3, TLSv1.2, TLSv1.1, TLSv1, SSLv3, SSLv2Hello]
enabledProtocols=[TLSv1.3, TLSv1.2]
defaultProtocolsFromContext=[TLSv1.3, TLSv1.2]
supportedProtocolsFromContext=[TLSv1.3, TLSv1.2, TLSv1.1, TLSv1, SSLv3, SSLv2Hello]
supportsTLS12=true
supportsTLS13=true
enabledTLS12=true
enabledTLS13=true
disabledAlgorithmsPresent=true
clientProtocolsProperty=(not set)
httpsProtocolsProperty=(not set)
noHandshakePerformed=true
```

### Reading the output accurately

- `contextProtocol=TLS` states the requested engine name, **not** the `SSLSession` negotiated protocol.
- `supportedProtocols` lists older entries: `SSLv3`, `TLSv1`, `TLSv1.1`. They are "known" to the provider, **not** necessarily allowed to be negotiated in default configurations.
- `enabledProtocols=[TLSv1.3,TLSv1.2]` is the default negotiable range of the socket in the test environment. Running with `-D...`, editing `java.security`, selecting another provider, or changing JDK versions can alter this list.
- `disabledAlgorithmsPresent=true` **only** says a security property value exists. To evaluate fully, read the **actual content** with `Security.getProperty("jdk.tls.disabledAlgorithms")` and check the relevant algorithms/groups rather than just checking for `null`.
- `noHandshakePerformed=true` is a reminder that `getEnabledProtocols()` **does not prove** any real TLS connection succeeds.

Do not use this program's `SSLContext.init(null,null,null)` as a "complete trust configuration for production". Here the context makes no network connections, so there is no peer certificate to verify.

## 6. Program 2 — verifying the *negotiated protocol* with a real TLS handshake

The second program **creates both a TLS server and client on loopback `127.0.0.1`**, performing one TLS 1.3-only handshake and one TLS 1.2-only handshake.

Unlike the inventory in section 5, this example verifies:

- Server has a `KeyManagerFactory` supplying certificate and private key from PKCS12.
- Client has a `TrustManagerFactory` trusting **only the local demo certificate** you generated, without disabling certificate validation.
- Client calls `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` to verify the `127.0.0.1` IP SAN in the certificate, without a trust-all `X509TrustManager`.
- Both sides call `setEnabledProtocols(new String[]{version})` before the handshake.
- After `startHandshake()`, read **`SSLSession.getProtocol()`**, **`getCipherSuite()`**, and peer certificates; verify both sides agree on the version.

**For learning environments only.** Self-signed private keys are test fixtures, the password `changeit` is trivial to guess, and the certificate is not in any public trust store. A successful result **does not validate any Internet server or production service**.

### 6.1 Create test certificate and truststore with keytool

Run in **PowerShell**, from the directory containing the two Java source files. Keep the **same PowerShell session** to reuse `$t`. Commands create files only inside the machine's `$env:TEMP`:

```powershell
# Temporary directory; do not place demo keys into the repository.
$t = Join-Path $env:TEMP ("tls-protocol-lesson-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $t | Out-Null
$pw = "changeit"  # For demo use only!

# 7-day RSA test server certificate; SAN includes IP and DNS for loopback.
keytool -genkeypair -alias localserver -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost" -ext "SAN=ip:127.0.0.1,dns:localhost" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -validity 7 -storetype PKCS12 -keystore (Join-Path $t "server.p12") -storepass $pw -keypass $pw -noprompt

# Export public certificate; do not export server private key.
keytool -exportcert -alias localserver -keystore (Join-Path $t "server.p12") -storepass $pw -rfc -file (Join-Path $t "server.pem")

# Client trusts only localserver's certificate in the demo.
keytool -importcert -alias localserver -file (Join-Path $t "server.pem") -keystore (Join-Path $t "trust.p12") -storetype PKCS12 -storepass $pw -noprompt
```

**Why must `127.0.0.1` have an IP SAN?** The client connects using an IP string and enables the `HTTPS` endpoint identification algorithm; identity verification must match an **iPAddress SAN**, not only the subject CN. Without the SAN, TLS may reject the connection for hostname/IP mismatch even when the truststore contains the certificate.

### 6.2 Complete Java code

Save as **`LoopbackTlsHandshakeDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
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

public final class LoopbackTlsHandshakeDemo {
    private static KeyStore load(Path file, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, password);
        }
        return store;
    }

    private static SSLContext serverContext(Path keyStorePath,
                                            char[] password) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(load(keyStorePath, password), password);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    private static SSLContext clientContext(Path trustStorePath,
                                            char[] password) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(load(trustStorePath, password));
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    private static void run(String version, SSLContext server,
                            SSLContext client) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (SSLServerSocket listener = (SSLServerSocket)
                server.getServerSocketFactory().createServerSocket(
                        0, 1, loopback)) {
            listener.setEnabledProtocols(new String[]{version});
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverSession = executor.submit(() -> {
                    try (SSLSocket peer = (SSLSocket) listener.accept()) {
                        peer.setEnabledProtocols(new String[]{version});
                        peer.startHandshake();
                        return peer.getSession().getProtocol();
                    }
                });
                try (SSLSocket socket = (SSLSocket)
                        client.getSocketFactory().createSocket(
                                "127.0.0.1", listener.getLocalPort())) {
                    socket.setEnabledProtocols(new String[]{version});
                    SSLParameters params = socket.getSSLParameters();
                    params.setEndpointIdentificationAlgorithm("HTTPS");
                    socket.setSSLParameters(params);
                    socket.startHandshake();

                    String negotiatedClient = socket.getSession().getProtocol();
                    String negotiatedServer =
                            serverSession.get(10, TimeUnit.SECONDS);
                    System.out.println(version + " negotiated="
                            + negotiatedClient);
                    System.out.println(version + " peersAgree="
                            + (version.equals(negotiatedClient)
                            && negotiatedClient.equals(negotiatedServer)));
                    System.out.println(version + " cipherSuiteNonEmpty="
                            + !socket.getSession().getCipherSuite().isBlank());
                    System.out.println(version + " peerCertificatePresent="
                            + (socket.getSession().getPeerCertificates().length > 0));
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: java LoopbackTlsHandshakeDemo server.p12 trust.p12 password");
        }
        char[] password = args[2].toCharArray();
        try {
            SSLContext server = serverContext(Path.of(args[0]), password);
            SSLContext client = clientContext(Path.of(args[1]), password);
            run("TLSv1.3", server, client);
            run("TLSv1.2", server, client);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Compile and run on Java 17+ (from the source directory, with `$t` created above):

```powershell
javac --release 17 -encoding UTF-8 -d $t LoopbackTlsHandshakeDemo.java
java -cp $t LoopbackTlsHandshakeDemo (Join-Path $t "server.p12") (Join-Path $t "trust.p12") $pw
```

**Verified exact output** on a SunJSSE runtime with TLS 1.2 and TLS 1.3:

```text
TLSv1.3 negotiated=TLSv1.3
TLSv1.3 peersAgree=true
TLSv1.3 cipherSuiteNonEmpty=true
TLSv1.3 peerCertificatePresent=true
TLSv1.2 negotiated=TLSv1.2
TLSv1.2 peersAgree=true
TLSv1.2 cipherSuiteNonEmpty=true
TLSv1.2 peerCertificatePresent=true
```

**Specific cipher suite names are omitted** to avoid assuming a fixed output: selection depends on provider, policy, certificate, supported groups, and JDK version. Here we only check that `getCipherSuite()` is non-empty; during real diagnostics, log the negotiated suite name in an authorized environment and compare against policy.

### 6.3 Interpreting the results and ensuring safety

- `TLSv1.3 negotiated=TLSv1.3` is the **`SSLSession` value after a successful handshake**, distinct from `supportedProtocols` or `enabledProtocols` in the inventory.
- `peersAgree=true` proves both server and client see the negotiated version and that it matches the version configured for that test run.
- `peerCertificatePresent=true` indicates the `SSLSession` holds a peer certificate. In the code, **`TrustManagerFactory`** validated trust against the demo truststore and **endpoint identification** was enabled. This boolean line **alone would not prove** valid chain/hostname if the code failed to enable those mechanisms.
- The demo runs only on loopback and connects to no external hosts. The truststore trusts only the generated test certificate; never import certificates from unverified senders into a production truststore.
- The server accepts one connection in a background thread (without reusing engine state across sessions); the thread executor terminates after each test. Real servers need timeouts, request limits, resource lifecycles, and centrally managed TLS configuration.
- If a runtime's security policy disables TLS 1.2 or 1.3, one test may fail; **that is an environment policy signal**, not a reason to bypass policy. Check `getEnabledProtocols()` and `jdk.tls.disabledAlgorithms` before selecting corresponding test cases.

Clean up test data:

```powershell
# Only delete the exact demo directory created in section 6.1; never use on real data.
if ($t -like (Join-Path $env:TEMP "tls-protocol-lesson-*")) {
    Remove-Item -LiteralPath $t -Recurse -Force
}
```

Normal file deletion **does not guarantee secure erasure** from SSDs, snapshots, or backups; hence only use test keys and sample passwords. **Never hardcode passwords/secrets** in real applications.

## 7. JSSE configuration: precedence and scope of impact

Java has two important configuration groups:

- **System properties** such as `jdk.tls.client.protocols`, `jdk.tls.server.protocols`, `https.protocols`, typically passed via `-D...` at JVM startup and scoped by API/provider.
- **Security properties** such as `jdk.tls.disabledAlgorithms` or `jdk.certpath.disabledAlgorithms`, read via `java.security.Security.getProperty` and configured in `java.security`. They can **forbid** protocols/algorithms even if the application puts them in its allowed/enabled list.

**Do not confuse `System.getProperty("jdk.tls.disabledAlgorithms")` with `Security.getProperty("jdk.tls.disabledAlgorithms")`.** Oracle/OpenJDK JSSE's TLS policy setting is a Java Security property, not just an ordinary system property.

### 7.1 Properties you must know

| Property / setting | Primary scope | Correct interpretation |
| --- | --- | --- |
| `jdk.tls.disabledAlgorithms` (**Security**) | JSSE protocol, cipher, key exchange/signature/algorithm restrictions | Can block TLSv1/TLSv1.1/SSLv3 and weak algorithms even if explicitly enabled |
| `jdk.certpath.disabledAlgorithms` (**Security**) | Certificate path verification | Can reject chains using weak key sizes/algorithms even when TLS versions overlap |
| `jdk.tls.client.protocols` (**System**) | **SunJSSE** default client protocol list | Limits versions for client defaults; explicit `setEnabledProtocols` can override the list but cannot bypass security restrictions |
| `jdk.tls.server.protocols` (**System**) | **SunJSSE** default server protocol list, generic context | Has its own scope; version-specific contexts or explicit sets may ignore default settings |
| `https.protocols` (**System**) | `HttpsURLConnection` defaults | **Not** a global switch for all TLS connections/`java.net.http.HttpClient`/Netty/gRPC |
| `jdk.tls.client.cipherSuites` / `jdk.tls.server.cipherSuites` (**System**) | Default cipher suites in SunJSSE | Cannot override allowed algorithms, certificates, named groups, versions, or peer support |
| `jdk.tls.namedGroups` (**System**) | Named finite-field/elliptic-curve groups | Can cause TLS 1.3/1.2 handshakes to fail if peers share no common group |
| `javax.net.ssl.keyStore` / `javax.net.ssl.trustStore` (System) | Default key/trust material for some factories/default managers | Does not automatically enforce hostname/identity; explicit `SSLContext` may use other stores |
| `SSLParameters.setProtocols` / `SSLSocket.setEnabledProtocols` | Specific client/server object/session | Directly specifies version list; still subject to peer and security policy |
| `SSLContext.getInstance("TLS")` | Generic JSSE context algorithm | Does not mean a single negotiated version; supports multiple TLS versions per provider |

**Configuration precedence for the default enabled list** in SunJSSE can generally be understood as:

```text
Explicit application setting (socket/engine SSLParameters)
        > relevant SunJSSE system property
        > JSSE provider defaults

Afterward, it still remains subject to Java Security properties
(e.g., jdk.tls.disabledAlgorithms, jdk.certpath.disabledAlgorithms),
algorithms/curves/certificates, and peer capabilities.
```

Do not interpret the "`>`" sign as a mechanism to override security policy. It only describes precedence for **configuring the enabled/default list**; the **prohibitions** in `jdk.tls.disabledAlgorithms` still apply during negotiation.

Example launching the inventory demo with client default **TLSv1.3** (PowerShell):

```powershell
# Demo: set the system property before the context is created.
java "-Djdk.tls.client.protocols=TLSv1.3" TlsProtocolInventoryDemo
```

Rerun in a fresh terminal/JVM and compare `enabledProtocols`. **Do not** assume every application uses the same defaults: they may create a custom `SSLContext`, call `setEnabledProtocols`, use a different provider, or be configured by a framework. Some properties are read by JSSE when initializing the provider/context; setting them mid-run may not update existing contexts.

Example with an already-created `SSLSocket`:

```java
// Illustrative snippet inside a Java method, not a standalone program.
String[] desired = { "TLSv1.3", "TLSv1.2" };
socket.setEnabledProtocols(desired);
// Read back from the socket itself before starting the handshake.
System.out.println(java.util.Arrays.toString(
        socket.getEnabledProtocols()));
```

The code above **has not yet** run a handshake. For servers with legacy clients, choose the list based on a real compatibility policy; never enable SSLv3/TLS 1.0/TLS 1.1 or weak ciphers just because of a "no common protocol" error without an approved security exception.

### 7.2 Quick CLI check of JVM configuration

The Java JDK provides:

```powershell
# Summary of enabled TLS protocols/suites for the current JDK/provider.
keytool -showinfo -tls

# In JDK environments supporting this flag:
java -XshowSettings:security:tls -version
```

The `keytool -showinfo -tls` command was tested on the JDK runtime used in this lesson; opening excerpt:

```text
Enabled Protocols
-----------------
TLSv1.3
TLSv1.2

Enabled Cipher Suites
---------------------
TLS_AES_256_GCM_SHA384
TLS_AES_128_GCM_SHA256
TLS_CHACHA20_POLY1305_SHA256
```

**Many more suites** follow in the list (only the first three lines are intentionally shown for illustration; **do not treat this as the complete CLI output**). This command is useful to inspect the JDK process's enabled profile, yet **does not verify the specific configuration of every application**, which may override defaults via provider/SSLContext/socket settings.

To view the **actual** security properties at runtime without modifying policy files, in Java 17 JShell:

```java
System.out.println(java.security.Security.getProperty(
        "jdk.tls.disabledAlgorithms"));
System.out.println(java.security.Security.getProperty(
        "jdk.certpath.disabledAlgorithms"));
```

This is a **Java snippet for JShell** or a method, not a standalone PowerShell command. Do not treat that property as a "password"; it is a configuration policy, though you should still avoid posting full production debug logs to public channels.

## 8. Reading cipher suite configurations and related extensions

**Protocol intersection is only a necessary condition, not a sufficient one.** Two peers can both enable TLS 1.3 and still fail the handshake because of:

- No common permitted **cipher suite**, or a key/cipher blocked by policy.
- No common **named group/key share**: `secp256r1`, `x25519`, `ffdhe2048`... depending on provider and protocol.
- No **signature scheme** compatible with the certificate/key manager; e.g., a certificate only supporting a signing algorithm unusable in TLS 1.3.
- Untrusted certificate chain, missing intermediate, expired cert, mismatched SAN/hostname, unsuitable EKU/KU, or rejection by `jdk.certpath.disabledAlgorithms`.
- Server requesting a client certificate and the client failing to supply the right certificate/private key.
- Errors in **SNI** routing, **ALPN** (HTTP/2 vs. HTTP/1.1), proxies, load balancers, or mTLS policy.
- Unsupported critical extensions, revocation failures, or framework-specific TLS policies.

**ALPN is not a TLS protocol version.** When HTTP/2 runs over TLS, the application can use ALPN to select `h2`; the TLS version such as `TLSv1.3` belongs to a **different** layer. `SSLParameters.setApplicationProtocols(...)` and `SSLSocket.getApplicationProtocol()` serve ALPN, while `SSLSession.getProtocol()` returns the TLS version. SNI selects the server identity/certificate by hostname; it is not where `TLSv1.2`/`TLSv1.3` is set.

### 8.1 How to read cipher suite names correctly

| Cipher suite | Primary version | Meaning |
| --- | --- | --- |
| `TLS_AES_128_GCM_SHA256` | TLS 1.3 | AES-128-GCM AEAD, SHA-256 in the HKDF key schedule |
| `TLS_AES_256_GCM_SHA384` | TLS 1.3 | AES-256-GCM AEAD, SHA-384 |
| `TLS_CHACHA20_POLY1305_SHA256` | TLS 1.3 | ChaCha20-Poly1305 AEAD, SHA-256 |
| `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | TLS 1.2 | ECDHE key exchange, RSA certificate signature/auth, AES-128-GCM |
| `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384` | TLS 1.2 | ECDHE, ECDSA authentication, AES-256-GCM |
| `TLS_RSA_WITH_AES_128_CBC_SHA` | Legacy TLS 1.2-era | RSA key transport and CBC; **do not use** for new configurations |

Even when `getSupportedCipherSuites()` includes a legacy name, system policy may forbid it outright. Prefer the JDK's safe defaults and restrict suites **per a verified policy**; a hand-written allow-list that is overly strict or incompatible with the certificate can prevent TLS 1.3 even when `enabledProtocols` is right.

TLS 1.3 uses a different key schedule from TLS 1.2; when troubleshooting, do not expect a TLS 1.2-style `ServerKeyExchange` in TLS 1.3. A TLS record showing `legacy_record_version` or a `ClientHello` with `legacy_version=0x0303` **does not mean** TLS 1.2 was negotiated: TLS 1.3 uses the `supported_versions` extension to negotiate the actual version. Inspect `SSLSession.getProtocol()` or the `supported_versions` and `ServerHello` fields in context.

## 9. Diagnosing handshake failures by layer

| Symptom | Possible causes | How to inspect |
| --- | --- | --- |
| `SSLHandshakeException: No appropriate protocol` | No matching version/cipher, or disabled by policy | Print enabled/supported on **both sides**, security properties, and cipher suites |
| `Received fatal alert: protocol_version` | Peer rejected proposed protocol versions | Compare TLS versions and server-side policy; do not hastily enable obsolete protocols |
| `Received fatal alert: handshake_failure` | **Many possibilities**: cipher, key exchange group, sig scheme, certificate, client auth, SNI | Inspect handshake trace and peer config; do not conclude from the alert alone |
| `PKIX path building failed` | Truststore missing CA/intermediate, broken chain, invalid cert | Use the right truststore, chain, and path validation; never trust-all |
| `No subject alternative names matching ...` | Host/IP does not match SAN | Reissue cert with proper DNS/iPAddress SAN or connect to the real hostname |
| `No available authentication scheme` | Server lacks certificate/key/algorithm compatible with negotiated settings | Check `KeyManagerFactory`, `keyStore`, key algorithms, and sig schemes |
| Handshake uses TLSv1.2 despite client supporting TLSv1.3 | Server does not enable 1.3, TLS terminator/proxy, or another policy | Check `SSLSession.getProtocol` at the exact endpoint and peer config |
| `getSupportedProtocols()` lists TLSv1 yet handshake cannot use it | TLSv1 is in `jdk.tls.disabledAlgorithms` or blocked by another policy | Check security properties; do not edit policy merely because it is supported |
| `SSLSession.getProtocol()` is not meaningful yet | Socket has not completed handshake or handshake failed | Call `startHandshake` and read session only upon success |
| Java code sets `SSLParameters` but nothing changes | Forgot `socket.setSSLParameters(params)`, set after handshake, or used a different socket | Print params/objects right before the handshake |
| HTTPS URL works while raw `SSLSocket` fails | The two paths have different trust, hostname, and default protocol configs | Inspect the configuration of each stack/framework independently |
| TLS protocol succeeds yet HTTP/2 fails | ALPN did not agree on `h2`, or server/application policy | Separate TLS `getProtocol` from ALPN `getApplicationProtocol` |
| Connects via LB/CDN with TLS 1.3 while backend is older | TLS termination and re-encryption happen on two separate connections | Inspect each hop; never infer backend posture from frontend results |

### JSSE debugging

In a test environment with proper access:

```powershell
# Example enabling JSSE trace for the local program.
java "-Djavax.net.debug=ssl,handshake" -cp $t LoopbackTlsHandshakeDemo (Join-Path $t "server.p12") (Join-Path $t "trust.p12") $pw
```

JSSE logs can be very long, containing handshake structures, certificate metadata, hostnames, security parameters, and depending on flags, sensitive bytes. **Never enable key/dump loggers in production or share raw logs publicly**. Use them only on test fixtures, store them with restricted permissions, and delete them after diagnosing.

When reading a trace, check in order: `ClientHello`, `supported_versions`, `ServerHello`, selected cipher suite, `Certificate`/certificate validation, and handshake `Finished`. Do not confuse `legacy_version` with the negotiated protocol. In TLS 1.3, many handshake messages after `ServerHello` are encrypted; an in-process logger sees more than an off-box network packet capture.

## 10. Practical configuration by security model

**New environments with modern clients/servers:** typically enable both TLS 1.3 and TLS 1.2 per organizational policy, with TLS 1.3 preferred when both sides are compatible. Do not disable TLS 1.2 solely because TLS 1.3 exists if valid peers still require TLS 1.2. However, if policy mandates **TLS 1.3 only**, enforce it on both client and server and run compatibility tests.

**With legacy services:** first inventory endpoints, certificates, cipher suites, named groups, load balancers, and JDK versions; schedule upgrades. **Never** downgrade to TLS 1.0/1.1, SSLv3, RC4, 3DES, or NULL/anonymous cipher suites to mask negotiation failures. If legacy support must persist temporarily, perform risk assessment and time-bounded isolation per security policy.

**In JSSE code:** use generic `SSLContext("TLS")`, build on safe provider/security defaults, and explicitly configure protocols and cipher suites when policy dictates. Enforce trust chains, hostnames, EKU/KU, key sizes, and certificate lifecycles via the trust manager/JSSE. When using `HttpClient`/Netty/gRPC/server frameworks, verify where that stack configures SSL; **never assume** `-Dhttps.protocols` affects every library.

**Real monitoring:** measure the negotiated TLS version/cipher suite **on successful connections**, per endpoint/hop and time window. Do not treat supported info returned by a scanner (or JDK source code) as evidence of what is negotiated. Never record session secrets or sensitive auth data in telemetry.

**Configuration changes:** deploy to staging, run client/server integration handshake tests, test protocol intersection and cert trust, and monitor errors by version. JDK and security policy updates can alter defaults and disabled lists, so never hardcode a snapshot of one JDK as "permanent truth".

## 11. Misconceptions to eliminate

**"Does `SSLContext.getInstance("TLS")` mean TLS 1.0?"** No. `"TLS"` is a generic context name capable of multiple versions; inspect `getEnabledProtocols` and actual handshakes.

**"Having TLSv1.1 in supported means the server allows TLSv1.1?"** No. Supported can list disabled versions; socket configuration, security policy, and peer support determine negotiation.

**"Will `setEnabledProtocols({"TLSv1"})` bypass `jdk.tls.disabledAlgorithms`?"** No. Security restrictions still apply even if the API accepts a supported name.

**"Does the TLS 1.3 suite `TLS_AES_128_GCM_SHA256` use RSA or ECDHE?"** The suite name **does not encode** the key agreement or certificate authentication algorithm; inspect negotiated groups/signature schemes/handshake.

**"Does TLS 1.3 always provide forward secrecy regardless of PSK?"** No. PSK-only modes lack the same guarantee as fresh (EC)DHE; inspect the actual mode/protocol.

**"Does TLS 1.3 0-RTT mean sending any request early is safe?"** No. Early data has replay risk and may not be supported by JSSE/app; the protocol needs replay protection/idempotency policies.

**"After calling `getEnabledProtocols`, can we log the negotiated version?"** Not yet. Only `SSLSession.getProtocol` after a successful handshake reflects the real version.

**"Using TLS 1.3 means we can skip certificate and hostname checks?"** False. TLS version does not replace trust, EKU/KU, SAN/hostname, revocation, or policy.

**"Does `https.protocols` control all Java SSL/TLS connections?"** No. It primarily affects `HttpsURLConnection`, and does not automatically apply to all HTTP clients, servers, or libraries.

**"A TLS record packet shows `0x0303`, so TLS 1.2 was definitely negotiated?"** No. TLS 1.3 uses compatibility/legacy fields; check `supported_versions` and the session.

**"A handshake failure definitely means TLS 1.3 is missing?"** No. Failures can also stem from truststores, SANs, cipher suites, named groups, signature schemes, SNI, ALPN, or client auth.

## 12. Self-check

1. **What are the three most important protocol levels when debugging?** Supported, enabled, and **negotiated**, plus security restrictions and peer capability.
2. **Which Java API returns the negotiated TLS version?** `SSLSession.getProtocol()` after a successful handshake.
3. **Can `getSupportedProtocols()` contain disabled protocols?** Yes; the SunJSSE test shows TLS 1.0/1.1 and SSLv3 even when not enabled.
4. **Which security property disables protocols/suites?** `jdk.tls.disabledAlgorithms`; read via `Security.getProperty`.
5. **Is `jdk.tls.client.protocols` the same as `https.protocols`?** No; their scopes differ—the latter targets `HttpsURLConnection`.
6. **How does a TLS 1.2 cipher suite differ from TLS 1.3?** 1.2 normally encodes key exchange/auth/symmetric/hash; 1.3 encodes AEAD + HKDF hash, while groups/signatures are negotiated separately.
7. **Does TLS 1.3 still have RSA key transport?** No; RSA certificates/signatures can still be used, but not legacy-style RSA key transport.
8. **Does TLS 1.3 always enable 0-RTT?** No, it is optional and carries replay risk.
9. **If client enables TLSv1.3 and TLSv1.2, and server enables only TLSv1.2, what can be negotiated?** TLSv1.2 if all other conditions pass.
10. **If both enable TLSv1.3, is the handshake guaranteed to succeed?** No; cipher suites, groups, sig schemes, trust, hostname, and policy can still fail it.
11. **Why did the demo enable `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`?** To verify the IP/DNS SAN, not just trust the certificate.
12. **What does `SSLSession.getCipherSuite()` tell you?** The cipher suite of a successful connection, without replacing knowledge of groups/signatures in TLS 1.3.
13. **Does `legacy_version=0x0303` in TLS 1.3 prove TLSv1.2 was negotiated?** No; inspect `supported_versions`/ServerHello and `SSLSession`.
14. **Should TLSv1 be removed from `disabledAlgorithms` because a legacy test fails?** Not by default; upgrade the legacy target or obtain an explicit security exception approval.
15. **Distinguish ALPN from TLS version.** ALPN chooses the application protocol (e.g., `h2`); TLS version is `TLSv1.2`/`TLSv1.3`.
16. **Can you retrieve the negotiated protocol from an unconnected socket like the inventory program?** No; only supported/enabled/default exist before negotiation.
17. **Why not infer system-wide TLS support from a single `SSLContext`?** Each client, server, framework, provider, and hop has its own configuration.
18. **Both sides support TLSv1.2 yet `SSLHandshakeException` occurs—what to check next?** Trust/certificates, cipher suites, named groups, signature schemes, security policy, SNI, and logs.
19. **When does a `protocol_version` alert occur?** When the peer rejects the proposed versions or no compatible version can be negotiated; it is not enough to infer the entire root cause alone.
20. **How should you verify after deployment?** Run real integration handshakes against the target endpoints, check session protocol/cipher, certificate identity, and logging/monitoring policies.

## Official references

- [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Oracle Java 17 — JDK Providers Documentation, SunJSSE protocols and cipher suites](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html)
- [Oracle Java 17 — Standard Algorithm Names, SSLContext](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html)
- [SSLContext (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [SSLSocket (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html)
- [SSLParameters (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [SSLSession (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html)
- [SSLEngine (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html)
- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246.html)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)