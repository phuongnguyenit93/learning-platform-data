# 16.4 SSLSocket, SSLServerSocket, and Controlling Handshake Timing

## Objectives and context

This lesson belongs to **16. JSSE** of Java Advance – security-cryptography. Upon completion, you will be able to:

- Distinguish `SSLContext`, `SSLSocketFactory`, `SSLServerSocketFactory`, `SSLServerSocket`, `SSLSocket`, `SSLParameters`, and `SSLSession`.
- Understand the sequence **TCP connect/accept → TLS configuration → handshake → identity verification → read/write application data → close**.
- Explain the difference between **explicitly calling `startHandshake()`** and **implicit handshaking** triggered by `SSLSocket` I/O.
- Identify APIs that can **trigger an unintended handshake** (especially `getSession()`), and understand the meaning/limits of `getHandshakeSession()` and `HandshakeCompletedListener`.
- Configure TLS versions, cipher suites, endpoint identification, mTLS, SNI/ALPN, and timeouts **before the handshake begins**.
- Run a standalone example with **Java 17+**, `keytool`, and two `SSLContext` instances: server/client on loopback `127.0.0.1` with certificate verification via a truststore; compare explicit handshake and implicit handshake with a single data exchange.
- Diagnose `SSLHandshakeException` errors at the right stage, avoiding custom trust managers that skip certificate checks or calling `startHandshake()` repeatedly to try to "renegotiate" TLS 1.3.

**Key takeaway:** A TCP connection that has completed `connect()/accept()` **does not yet mean** an authenticated TLS channel exists. And `SSLServerSocket` is a listener, **not** an individual client's application channel. Only after the handshake succeeds per trust/identity policy, plus business-layer authorization, should the application process privileged requests.

## 1. How JSSE components work together

JSSE (*Java Secure Socket Extension*) provides TLS in the JVM. The following classes do not share the same responsibility:

| Component | Role | Example API |
| --- | --- | --- |
| `SSLContext` | Aggregates key manager, trust manager, and randomness source; provides socket factories | `SSLContext.getInstance("TLS")`, `init(...)` |
| `KeyManagerFactory` | Selects private key and certificate chain to **prove our own identity** | `init(keyStore, keyPassword)` |
| `TrustManagerFactory` | Creates trust anchor/chain verification for certificates from the **peer** | `init(trustStore)` |
| `SSLSocketFactory` | Creates client-side TLS connections or wraps an already-connected socket | `createSocket(host, port)` |
| `SSLServerSocketFactory` | Creates a TLS listener on the server | `createServerSocket(port, backlog, bindAddress)` |
| `SSLServerSocket` | Bind/listen/accept; sets TLS defaults for accepted connections | `accept`, `setEnabledProtocols`, `setNeedClientAuth` |
| `SSLSocket` | A specific TLS connection; handshake, stream I/O, and session | `startHandshake`, `getInputStream`, `getOutputStream` |
| `SSLParameters` | Socket-related SSL/TLS configuration such as endpoint identification, ALPN, and SNI | `setEndpointIdentificationAlgorithm`, `setApplicationProtocols` |
| `SSLSession` | TLS session info, e.g., protocol/cipher suite/peer cert | `getProtocol`, `getCipherSuite`, `getPeerCertificates` |
| `HandshakeCompletedListener` | Receives handshake completion events from `SSLSocket` | `addHandshakeCompletedListener` |

**Diagram:**

```text
        CLIENT                                      SERVER
  truststore -> TrustManagerFactory         keystore -> KeyManagerFactory
                    |                                      |
               SSLContext                              SSLContext
                    |                                      |
            SSLSocketFactory                    SSLServerSocketFactory
                    |                                      |
               SSLSocket  -------- TCP -------->  SSLServerSocket
                    |                                 accept()
                    |                                      |
                    |                                 SSLSocket (peer)
                    |                                      |
          pre-TLS configuration                    pre-TLS configuration
                    +---------- TLS handshake -----------+
                    |                                      |
              identity check                       client-cert if mTLS
                    |                                      |
                    +==== encrypted application bytes ====+
```

The client side may need only a **trust manager** to check the server certificate; the server needs a **key manager** containing the server private key and chain to present itself. With mTLS, the client must also have a key manager/client certificate and the server must have a trust manager to evaluate the client cert.

A successful `SSLContext.init(...)` **performs no handshake**. `SSLServerSocket.accept()` accepts a connection to the listener and returns an `SSLSocket`; the TLS handshake may not have occurred yet. `SSLSession` should only be used to inspect the session after a successful handshake; calling `getSession()` early can itself start the handshake.

## 2. Distinguishing TCP timing from TLS timing

| Stage | What is certain | What is not yet certain |
| --- | --- | --- |
| Create `SSLContext` | Cryptographic services configuration is selected | No peer/connection yet |
| Create `SSLServerSocket` | Server is listening on the port | No TLS-authenticated client yet |
| Client `SSLSocketFactory.createSocket(...)` | Socket created; typically TCP connected | TLS handshake may not have occurred yet |
| Server `SSLServerSocket.accept()` | TCP connection accepted | Certificate/client identity not yet verified |
| Configure `setEnabledProtocols(...)` | Restricts TLS versions allowed by the app | Actual negotiated version unknown yet |
| `startHandshake()` or I/O-triggered handshake | JSSE executes negotiation, key establishment, and appropriate validation | May fail right here |
| Handshake returns successfully | TLS channel established per current JSSE policy | Does not automatically grant the client API access |
| Read `SSLSession` after handshake | Can inspect negotiated protocol/cipher | Does not prove resource authorization on its own |

In standard TLS server authentication, the client checks the server's chain up to a pre-trusted **trust anchor**, and the **target hostname/IP** must match a certificate SAN. **Do not treat** a certificate valid under any CA as the right server if the SAN does not match. Similarly, the server cannot infer user identity merely because a TCP connection was accepted.

TLS is a **protected byte stream**, not a complete auth/authorization system. The application layer must still parse requests, check permissions per resource/tenant/user, prevent replay if required by the protocol, and manage lifecycle.

## 3. Explicit handshake with `SSLSocket.startHandshake()`

You can request the handshake at an explicit point after creating and configuring the socket:

```java
SSLSocket socket = (SSLSocket) sslFactory.createSocket(host, port);
socket.setEnabledProtocols(new String[] {"TLSv1.3"});
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();  // TLS checkpoint: succeeds or throws.
SSLSession session = socket.getSession();
```

The code above is **only a snippet**, not a standalone program: it requires `sslFactory` created from an `SSLContext` with the proper trust manager, `host/port`, `javax.net.ssl.*` imports, exception handling, and closing the socket in try-with-resources.

**Benefits of explicit `startHandshake()`:**

- Certificate/trust errors, TLS protocol mismatches, or cipher negotiation errors appear at **`startHandshake()` itself**, rather than on the first `write/read`.
- The application can send sensitive data **only after** TLS is established and additional policies are checked.
- Clearer logging, telemetry, and timeouts for the TLS phase, separated from the application request.
- Avoids accidentally altering handshake ordering by calling `getSession()` before configuring endpoint identity.

On the server, obtain the `SSLSocket` from the listener and proactively initiate the handshake:

```java
try (SSLSocket peer = (SSLSocket) serverSocket.accept()) {
    peer.setSoTimeout(10_000);
    peer.startHandshake();
    // Begin processing requests only after the handshake succeeds.
}
```

This is also a **snippet**, assuming `serverSocket` is a configured `SSLServerSocket`, illustrating only the checkpoint. `peer.startHandshake()` can block while waiting for the client; the server must bound time and resources. Never perform unbounded blocking handshakes on a production server's single accept thread.

**Note:** A call to `startHandshake()` only "starts the handshake" per the TLS socket contract; to properly authenticate the server, the client still needs a **truststore/trust manager and endpoint identification**. If the app configures "trust all," the handshake may succeed without guaranteeing the right identity.

## 4. Implicit handshake: the first I/O operation can also be the handshake

`SSLSocket` automatically performs the **initial handshake** when an operation requires a usable TLS connection. For example:

```java
try (SSLSocket socket = (SSLSocket) sslFactory.createSocket(host, port)) {
    // Must configure protocol, hostname/trust, and timeout beforehand.
    socket.getOutputStream().write(requestBytes); // Handshakes if needed.
    socket.getOutputStream().flush();
    int firstResponseByte = socket.getInputStream().read();
}
```

The snippet above is not standalone: `sslFactory`, `host/port`, and `requestBytes` must be supplied; omitting trust/endpoint configuration is a security bug. If no handshake has occurred yet, `write`/`read` triggers it, because **application bytes cannot be transmitted over a proper TLS channel before session keys are established**.

**The most important difference is where errors surface:**

| Flow | TLS start point | Where can TLS errors be observed? |
| --- | --- | --- |
| Explicit | `socket.startHandshake()` | Directly at `startHandshake()` |
| Implicit | `getOutputStream().write(...)` or `getInputStream().read()` | **During I/O** instead of an explicit handshake call |
| Early session read | `socket.getSession()` | `getSession()` can trigger the initial handshake itself |
| Server explicit | `peer.startHandshake()` after `accept` | Inside the handshake on the accepted socket |
| Server implicit | `peer.getInputStream().read()` | During the I/O call on the accepted socket |

Obtaining `getInputStream()`/`getOutputStream()` should not be relied upon as a validation checkpoint across all providers; when **actually reading/writing**, JSSE must protect application data and may initiate the handshake. If you want a clear boundary before requests, **call `startHandshake()` explicitly**.

### The `getSession()` and `getHandshakeSession()` trap

`SSLSocket.getSession()` may automatically initiate a handshake if the initial handshake has not started. **Do not** use it to "check whether the handshake already happened" before setting `SSLParameters`. A getter with side effects can cause a certificate to be accepted before endpoint identification is properly enabled.

`getHandshakeSession()` is used during an **in-progress handshake** (when a handshake session exists) and may return `null` when no handshake is active. However, `null` **does not prove** the socket has never handshaken: after the handshake completes, there may also no longer be a handshake session.

### Two timelines

```text
EXPLICIT                                  IMPLICIT
createSocket()                            createSocket()
setEnabledProtocols(...)                  setEnabledProtocols(...)
set SSLParameters (HTTPS identity)         set SSLParameters (HTTPS identity)
startHandshake() ---------------- TLS     output.write(42) -------- TLS
  | success or SSLHandshakeException         | success or SSLHandshakeException
output.write(42)                           app byte 42 follows handshake
input.read()                               input.read()
getSession()                               getSession()
```

Both can achieve the same negotiated TLS version and trust policy. **Implicit is not inherently less secure just because `startHandshake()` is omitted**; risk arises when code does not realize where the actual handshake occurs and **fails to handle errors or configures parameters too late**.

## 5. `SSLServerSocket`: server-side control

Steps for a direct JSSE server:

1. Load the keystore containing the server's private key and chain; initialize `KeyManagerFactory` and `SSLContext`.
2. Create the listener via `SSLServerSocketFactory.createServerSocket(...)` with appropriate address/port and backlog.
3. Set protocol/cipher allowlists, `SSLParameters`, and client certificate policy **on the listener before `accept`**.
4. Call `accept()` to obtain an `SSLSocket` for **each individual connection**.
5. Set `setSoTimeout(...)` on the accepted socket, attach listeners/adjust needed policy **before the handshake**.
6. Call `startHandshake()` or let the first I/O trigger it.
7. Only after TLS succeeds and appropriate identity/authorization binding is performed should you process application data.
8. Close the connection socket when done; the listener can continue accepting other connections.

`SSLServerSocket` is not an application stream. `getInputStream` and `getOutputStream` belong to the **accepted `SSLSocket`**, not the listener.

### mTLS: `setNeedClientAuth` and `setWantClientAuth`

- `setNeedClientAuth(true)`: the server **requires** a client certificate. The client must have an appropriate certificate/private key and the server must have a trust manager verifying that certificate; otherwise, the handshake fails.
- `setWantClientAuth(true)`: the server asks for a certificate but may proceed if the client supplies none; **do not treat all clients as authenticated**.
- If a client certificate is present and trusted, you **must still map** the certificate identity to a user/service/tenant/role and check business permissions.

Set client-auth policy **before the handshake**. Never "turn on mTLS" after a connection is already established expecting the client to immediately supply a certificate as a fresh login.

### A TLS server is not a single thread

`accept()` can block, and handshakes can also block waiting on the peer. Production requires an accept loop, bounded concurrency, timeouts, rate limiting, quotas, and graceful shutdown. A client can send TCP SYN/connect and intentionally stall the TLS handshake. Never allow thousands of sockets to wait indefinitely and exhaust file descriptors/threads.

## 6. Settings that must be applied before starting TLS

| Setting | Right timing | Meaning |
| --- | --- | --- |
| `SSLContext.init(keyManagers, trustManagers, random)` | Before obtaining socket factories | Source of private keys/certificates and trust anchors |
| `SSLSocket.setUseClientMode(true/false)` | Before handshake | Role of the TLS endpoint; changing after TLS begins may be invalid |
| `SSLServerSocket.setEnabledProtocols(...)` | Before `accept`/handshake of connections | Allowed versions for accepted peer sockets |
| `SSLSocket.setEnabledProtocols(...)` | Before handshake on the socket | Allowed TLS versions; **not the negotiated version** |
| `setEnabledCipherSuites(...)` | Before handshake | Allowed cipher suites; support depends on provider |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Client before handshake | Requires verifying target hostname/IP against certificate |
| `SSLParameters.setServerNames(...)` | Client before handshake if needed | SNI helps select virtual host/certificate |
| `SSLParameters.setApplicationProtocols(...)` | Before handshake if using ALPN | List of allowed application protocols |
| `setNeedClientAuth(...)`/`setWantClientAuth(...)` | Server before handshake | Client certificate policy |
| `addHandshakeCompletedListener(...)` | Before handshake to observe | Callback when handshake completes |

Java 17 supports TLS 1.3 in standard compliant providers. Using `SSLContext.getInstance("TLS")` may allow multiple versions depending on provider/policy, whereas `setEnabledProtocols(new String[]{"TLSv1.3"})` restricts the socket. **Always check the actual negotiated version** after the handshake via `SSLSession.getProtocol()`. Never enable TLS 1.0/1.1 or weak cipher suites just to avoid interoperability errors.

### Endpoint identification is separate from the trust chain

The client needs **both** a trust path to a trust anchor **and** endpoint identity verification. For example, when connecting to `127.0.0.1`, the lab certificate below includes **IP SAN 127.0.0.1**. `CN=localhost` alone does not substitute for an IP SAN when the target host is an IP literal.

SNI can help the server pick a certificate, but **does not replace hostname verification**. With an IP literal in the lab, the demo does not rely on SNI; with DNS virtual hosts, SNI, SAN, and trust manager policies must work together.

## 7. Java 17 lab: two handshake modes with a trusted certificate

The goal is to build an example that **actually runs** on the same machine, with no internet access and no trust-all.

### 7.1 Preparing the keystore/truststore

Create a **test-only self-signed** certificate with `SAN=dns:localhost,ip:127.0.0.1`. Import the public certificate into the client's truststore. This is **explicitly provisioned out-of-band trust**, completely different from blindly trusting whatever certificate a server sends.

Open PowerShell with `java`, `javac`, and `keytool.exe` from JDK 17+ on `PATH`. Run the entire script below. Use only `%TEMP%\jsse-handshake-lab`, **never modify `cacerts` or the OS truststore**:

```powershell
$ErrorActionPreference = 'Continue'
$qa = Join-Path $env:TEMP 'jsse-handshake-lab'
New-Item -ItemType Directory -Force -Path $qa | Out-Null
Set-Location $qa
$p = 'changeit'

function Run-Keytool([string[]]$arguments) {
    $out = & keytool.exe @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("keytool failed: " + ($arguments -join ' ') + ' => ' + ($out -join ' '))
    }
}

if (Test-Path -LiteralPath 'server.p12') {
    Remove-Item -LiteralPath 'server.p12' -Force
}
if (Test-Path -LiteralPath 'trust.p12') {
    Remove-Item -LiteralPath 'trust.p12' -Force
}

Run-Keytool @("-genkeypair","-alias","localhost",
    "-keyalg","RSA","-keysize","2048",
    "-sigalg","SHA256withRSA","-validity","30",
    "-dname","CN=localhost,O=TLS Training",
    "-ext","SAN=dns:localhost,ip:127.0.0.1",
    "-ext","EKU=serverAuth",
    "-ext","KU=digitalSignature,keyEncipherment",
    "-storetype","PKCS12","-keystore","server.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Run-Keytool @("-exportcert","-alias","localhost",
    "-rfc","-file","server.pem",
    "-keystore","server.p12","-storepass",$p)

Run-Keytool @("-importcert","-alias","localhost",
    "-file","server.pem",
    "-keystore","trust.p12","-storetype","PKCS12",
    "-storepass",$p,"-noprompt")

Write-Output "Local TLS lab stores ready"
```

**Final stdout on the test environment:**

```text
Local TLS lab stores ready
```

Three files:

- `server.p12`: keystore containing **server private key + certificate**; needed only on the server side.
- `server.pem`: exported **public certificate**; can be distributed, though the source must be verified in real-world use.
- `trust.p12`: client-side truststore containing the **deliberately trusted** lab certificate.

`changeit` is a fixed password **for lab use only**. Never put `server.p12` into git, never use this certificate in production, and never blindly trust a public certificate file supplied by an attacker. For production, use proper CA/KMS/HSM, issuance policies, renew/revoke processes, and secure secret storage.

**PowerShell note:** The script runs in an **isolated temporary** directory and deletes `server.p12`/`trust.p12` inside that lab directory when regenerating. Do not place personal files with the same names in the lab directory. Keep PowerShell syntax; do not copy verbatim into Bash.

### 7.2 `HandshakeTimingDemo.java` program

Save the source below in the **same directory** as `server.p12` and `trust.p12`. Use the exact filename `HandshakeTimingDemo.java`:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.CountDownLatch;
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

public final class HandshakeTimingDemo {
    private static final String PASSWORD = "changeit"; // Local lab ONLY.
    private static final String TLS_VERSION = "TLSv1.3";
    private static final String HOST = "127.0.0.1";

    private record ServerResult(boolean received, boolean event,
                                String protocol) {}

    public static void main(String[] args) throws Exception {
        SSLContext server = serverContext("server.p12");
        SSLContext client = clientContext("trust.p12");
        runScenario("EXPLICIT", true, server, client);
        runScenario("IMPLICIT", false, server, client);
    }

    private static SSLContext serverContext(String keyStoreFile)
            throws Exception {
        KeyStore store = loadKeyStore(keyStoreFile);
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(store, PASSWORD.toCharArray());
        SSLContext context = SSLContext.getInstance(TLS_VERSION);
        context.init(kmf.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    private static SSLContext clientContext(String trustStoreFile)
            throws Exception {
        KeyStore store = loadKeyStore(trustStoreFile);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(store);
        SSLContext context = SSLContext.getInstance(TLS_VERSION);
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    private static KeyStore loadKeyStore(String file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(file))) {
            store.load(in, PASSWORD.toCharArray());
        }
        return store;
    }

    private static void runScenario(String label, boolean explicit,
                                    SSLContext serverContext,
                                    SSLContext clientContext) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (SSLServerSocket listener = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(
                        0, 5, InetAddress.getByName(HOST))) {
            listener.setEnabledProtocols(new String[] {TLS_VERSION});

            Future<ServerResult> serverTask = executor.submit(() -> {
                try (SSLSocket peer = (SSLSocket) listener.accept()) {
                    peer.setSoTimeout(10000);
                    peer.setEnabledProtocols(new String[] {TLS_VERSION});
                    CountDownLatch event = new CountDownLatch(1);
                    peer.addHandshakeCompletedListener(done -> event.countDown());

                    if (explicit) {
                        peer.startHandshake();
                    }
                    int request = peer.getInputStream().read(); // Implicit if needed.
                    peer.getOutputStream().write(43);
                    peer.getOutputStream().flush();
                    boolean fired = event.await(2, TimeUnit.SECONDS);
                    return new ServerResult(request == 42, fired,
                            peer.getSession().getProtocol());
                }
            });

            try (SSLSocket socket = (SSLSocket)
                    clientContext.getSocketFactory().createSocket(
                            HOST, listener.getLocalPort())) {
                socket.setSoTimeout(10000);
                socket.setEnabledProtocols(new String[] {TLS_VERSION});
                SSLParameters parameters = socket.getSSLParameters();
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                socket.setSSLParameters(parameters);
                CountDownLatch event = new CountDownLatch(1);
                socket.addHandshakeCompletedListener(done -> event.countDown());

                if (explicit) {
                    socket.startHandshake();
                }
                socket.getOutputStream().write(42); // Implicit if needed.
                socket.getOutputStream().flush();
                int answer = socket.getInputStream().read();
                boolean clientEvent = event.await(2, TimeUnit.SECONDS);
                ServerResult serverResult = serverTask.get(15, TimeUnit.SECONDS);
                boolean versionOk = TLS_VERSION.equals(
                        socket.getSession().getProtocol())
                        && TLS_VERSION.equals(serverResult.protocol());
                System.out.println(label + " TLSv1.3: " + versionOk);
                System.out.println(label + " handshake listeners: "
                        + (clientEvent && serverResult.event()));
                System.out.println(label + " one-byte exchange: "
                        + (answer == 43 && serverResult.received()));
            }
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Compile and run in PowerShell (still inside `jsse-handshake-lab`):

```powershell
javac --release 17 HandshakeTimingDemo.java
java -cp . HandshakeTimingDemo
```

**Verified stdout on a JDK supporting TLSv1.3:**

```text
EXPLICIT TLSv1.3: true
EXPLICIT handshake listeners: true
EXPLICIT one-byte exchange: true
IMPLICIT TLSv1.3: true
IMPLICIT handshake listeners: true
IMPLICIT one-byte exchange: true
```

**Timing note:** The program uses `setSoTimeout(10000)`, waits up to **2 seconds** for callbacks, and waits for the server worker via `Future.get(15,...)`; these values prevent the **lab from hanging indefinitely** and are not JSSE API guarantees. If the machine is overloaded, a run may time out before the callback event is processed; that is not necessarily a TLS algorithm error.

### 7.3 Why does the Java code accurately demonstrate both modes?

**Separate server and client contexts:** `serverContext` loads the keystore and initializes `KeyManagerFactory` to present the server certificate. `clientContext` loads the truststore and initializes `TrustManagerFactory` to verify the certificate. No "return true" trust manager is used. The client enables `HTTPS endpoint identification` before starting the handshake, matching the lab certificate's **IP SAN**.

**Loopback only:** The listener binds to `InetAddress.getByName("127.0.0.1")`, OS-assigned port `0`. It does not expose a server lacking authorization to external networks. Using a dynamic port prevents collisions across repeated runs.

**Concurrency:** `ExecutorService` runs server-side `accept/read/write`; the main thread acts as client. Without separation, client and server would block each other. `accept()` does not handle application bytes directly; the code uses the **accepted `SSLSocket`** inside the lambda.

**Explicit:** both sides call `startHandshake()` before I/O. If the client does not trust the server certificate, the failure normally occurs right here (the peer receives the corresponding TLS alert/error). After TLS completes, the client sends byte `42` and the server replies `43`.

**Implicit:** no `startHandshake()` call is made. The client starts `OutputStream.write(42)` while the server waits on `InputStream.read()`; JSSE automatically initiates the initial handshake and protects the transmitted bytes. The one-byte exchange is still `42/43`, but **the TLS failure location can be inside `write/read`**.

**Listener:** `HandshakeCompletedListener` simply calls `CountDownLatch.countDown()`. Callbacks may fire asynchronously; the code waits briefly on the event for verification. Never treat callback invocation as application authorization; both endpoints must check identity/role policies per use case.

**Protocol:** `SSLSession.getProtocol()` is read **after** the handshake/I/O. Only then is negotiated `TLSv1.3` confirmed; `setEnabledProtocols` beforehand is an allowlist, not proof of negotiation.

**Application logic check:** `answer == 43 && serverResult.received()` proves both endpoints exchanged the expected bytes. It is **not** a production message format: TLS does not provide application framing.

## 8. `startHandshake()` is not a TLS 1.3 renegotiation switch

Distinguish:

1. **Initial handshake** on a new `SSLSocket`.
2. **Session resumption** on a **new TLS connection**, potentially using session tickets/caches per protocol and policy; even when resumed, the new connection still has a handshake.
3. Legacy TLS **renegotiation**: **TLS 1.3 does not support TLS 1.2-style renegotiation**. TLS 1.3 has other mechanisms like KeyUpdate, but they are not repeated `startHandshake()` calls to automatically change users/certificates or redo a full handshake.

**Never build a security workflow assuming calling `startHandshake()` multiple times creates a new session.** Subsequent calls depend on TLS version/provider and may be rejected, do nothing, or perform a different mechanism. If you need a new connection/new identity, design a **new TLS connection** and a proper authentication workflow.

`SSLSession.invalidate()` does not revert an active TLS socket to an "un-handshaken" state; it relates to session reuse/caching. `getHandshakeSession()==null` is likewise not a check for "whether authentication occurred."

### TLS 1.3 early data and resumption

**0-RTT early data** in TLS 1.3 has its own conditions and replay risks. The `SSLSocket` program here **does not use 0-RTT**; do not confuse `OutputStream.write` prior to calling `startHandshake()` with sending 0-RTT. In JSSE, calling I/O triggers a normal handshake before transmitting application data.

Never use the `SSLSession` object as a business login session. Application-layer authorization and anti-replay require tokens/roles/nonces/sequences per protocol; they cannot be replaced by counting how many times a handshake callback fired.

## 9. Can `HandshakeCompletedListener` be used to grant permissions?

**No.** The listener only notifies of handshake completion events for the socket. Minimal example (snippet):

```java
CountDownLatch latch = new CountDownLatch(1);
socket.addHandshakeCompletedListener(event -> latch.countDown());
socket.startHandshake();
```

This snippet requires a valid `socket` and `java.util.concurrent.CountDownLatch`; handle exceptions and wait timeouts in real code. **Do not** assume the callback runs synchronously before the line right after `startHandshake()`, and never perform network I/O, DB queries, or long blocking work inside the callback, as it complicates concurrency/lifecycle.

If using the listener for metrics, attach **connection ID**, protocol/cipher, and event timestamp. With mTLS, `HandshakeCompletedEvent.getPeerCertificates()` can provide the peer chain when authenticated, yet you must still map identity to authorization. In standard server TLS **there is no client certificate**, so the listener is not proof of a logged-in user.

## 10. When the handshake fails, where do exceptions appear?

| Scenario | Common error class/symptom | Investigation |
| --- | --- | --- |
| Server certificate does not chain to a trusted root | `SSLHandshakeException`, possibly with `CertPathValidatorException`/builder cause | Truststore, issuer, intermediates, key policy |
| Connecting to IP when certificate has only a different DNS SAN | `SSLHandshakeException`/certificate mismatch | Issue right SAN, check endpoint identity |
| Server requires client cert but client has none | TLS alert/`SSLHandshakeException` on one or both sides | `needClientAuth`, client key manager/cert, server trust manager |
| No common TLS version/cipher suite | TLS negotiation failure | Version/cipher allowlists, JDK/provider/policy |
| Implicit client sends first request | TLS exception may be thrown **at `write` or `read`** | Do not catch only around `startHandshake` |
| Implicit server waits on read | Handshake error may occur **at `read`** | Peer certificate if mTLS, protocol/trust, slow client |
| Peer says nothing or connection hangs | `SocketTimeoutException`/connection timeout or EOF depending on phase | Timeouts/deadlines, firewall, load, and resource quotas |
| `getPeerCertificates` when peer was not cert-authenticated | `SSLPeerUnverifiedException` | Proper mTLS configuration and TLS role |
| Handshake succeeded, subsequent I/O fails | `SSLException` or other IO exception | Do not assume it is an initial TLS handshake error |

`SSLHandshakeException` extends `SSLException`. TLS handshake errors may be wrapped inside HTTP/JDBC/network library errors; inspect `getCause()` carefully. **Never fix this by changing the trust manager to trust-all** or importing an unverified root certificate into global `cacerts`.

**Likewise, do not assume every `SSLException` is a certificate error.** It may be a TLS protocol alert, close/truncation, network issue, unsupported cipher, or record-layer error after the connection is established.

### Reading debug logs in context

Temporary JSSE debugging can be enabled in test environments:

```powershell
java -Djavax.net.debug=ssl,handshake,trustmanager -cp . HandshakeTimingDemo
```

Debug output is not fixed-format and can be verbose; logs may contain certificates/metadata/protocol details so restrict access and never enable broadly in production. Fields to record: connection ID, TCP connect/accept duration, TLS handshake duration, negotiated version/cipher, truststore version, expected identity, exception category, and correlation ID — never log private keys, keystore passwords, or sensitive payloads.

## 11. Timeouts, deadlocks, I/O framing, and resource management

### Handshake timeout is not TCP connect timeout

`setSoTimeout(...)` sets the deadline for **blocking reads** on the socket and generally affects reading TLS records during the handshake; it does not replace **TCP connect timeout** and does not guarantee an overall request deadline.

Snippet example when a connect deadline is needed:

```java
Socket raw = new Socket();
raw.connect(new InetSocketAddress(host, port), 3_000);
SSLSocket tls = (SSLSocket)
        factory.createSocket(raw, host, port, true);
tls.setSoTimeout(10_000);
// Configure SSLParameters/trust/endpoint identity before handshake.
tls.startHandshake();
```

This is a snippet requiring `java.net.Socket`/`InetSocketAddress` imports, `factory/host/port`, and socket closing management. `autoClose=true` causes the wrapper to close the raw socket per contract when the TLS socket closes. Production also needs overall deadlines, connection limits, cancellation, and explicit handling of timeouts/partial I/O.

### Do not let both sides wait for application bytes

If both sides call `read()` before either sends application data, they can deadlock **even though TLS is established**:

```text
CLIENT                         SERVER
read()  -- waiting             read() -- waiting
   (nobody sends application data first)
```

For request/response protocols, explicitly define **who sends first**, framing, timeouts, and EOF handling. The demo chooses client sending `42`, server reading and replying `43`, avoiding a wait cycle.

### TLS is a byte stream, not a message queue

A single `read` must not be assumed to return an entire application message. For multi-byte messages, handle partial reads, length prefixes or delimiters, size limits, timeouts, checksums if required by protocol, and connection close handling. Never mix raw `Socket.getInputStream` with the `SSLSocket` streams once TLS wraps that socket — raw reads can consume handshake bytes/encrypted records.

## 12. ALPN, SNI, and client authentication

**SNI** helps the server select the virtual host/certificate matching the DNS name requested by the client. It can be configured via `SSLParameters.setServerNames(...)` before the handshake when needed. SNI does not prove a certificate is trustworthy; the client must continue verifying the trust chain and SAN/hostname. The loopback IP demo does not rely on SNI.

**ALPN** negotiates the **application protocol name** such as `h2` or `http/1.1` during the TLS handshake. `SSLParameters.setApplicationProtocols(...)` sets the list before the handshake and `SSLSocket.getApplicationProtocol()` reads the result afterward. Selecting `h2` does not implement HTTP/2 automatically; the application needs a real framing/parser stack. The `42/43` demo sets no ALPN since there is no HTTP.

**mTLS** requires the server to authenticate the client-side certificate and map the certificate identity to a service/role/tenant. Enable `setNeedClientAuth(true)` before the handshake and properly configure the trust manager and CA/client cert. `setWantClientAuth(true)` only requests optionally: a client without a certificate can still establish a TLS connection. Never assume all clients of a server are authenticated merely because the server uses `SSLServerSocket`.

## 13. Practical deployment checklist

**Before handshake:**

- [ ] Server has private key and proper certificate chain via `KeyManagerFactory`; client has a trust manager with trusted trust anchors.
- [ ] Client enables **endpoint identification** matching hostname/IP; certificate has matching SAN.
- [ ] Protocol/cipher allowlists are set before the socket begins I/O/TLS; avoid configuring too late.
- [ ] Client/server roles and mTLS/SNI/ALPN (if needed) are prepared upfront.
- [ ] Handshake timeouts, connect/read timeouts, overall deadlines, and connection/CPU limits are defined.

**During handshake and I/O:**

- [ ] Know whether code uses explicit or implicit mode; `getSession()` is not used as a side-effect-free state probe.
- [ ] If explicit: process data only after `startHandshake()` succeeds and policy checks pass.
- [ ] If implicit: the first `write/read` can throw handshake errors; never swallow exceptions.
- [ ] After handshake, inspect negotiated `SSLSession.getProtocol/getCipherSuite` and role/identity per policy.
- [ ] `HandshakeCompletedListener` is used solely for observation, not as a request handler or authorization decision.
- [ ] Properly manage EOF, close, record/stream boundaries, backpressure, and concurrency.

**Operations and security:**

- [ ] Never use trust-all, skip hostname verification, or import untrusted roots into truststores.
- [ ] Certificate rotation/renewal, truststore updates, and root revocation follow defined procedures.
- [ ] For mTLS, map client certificate identity to authorization; never rely solely on certificate presence.
- [ ] Do not assume TLS 1.3 allows classic renegotiation or that repeated `startHandshake()` calls re-authenticate.
- [ ] Have tests for valid cases, untrusted server cert, SAN mismatch, protocol mismatch, mTLS missing client cert, slow peer, and timeouts.
- [ ] Logs include authorized correlation/metrics; never log private keys, passwords, session secrets, or sensitive data.

## 14. Exercises

1. In `HandshakeTimingDemo`, point out which line creates the **listener**, which line calls `accept()`, and which line triggers the explicit TLS handshake. Does `accept()` guarantee the client certificate has been authenticated?
2. Change `explicit=true` to `false`. Why is application byte `42` not sent "in the clear" even without `startHandshake()` in that branch?
3. Create a second truststore **without** the server certificate. Run both modes and record the exception location/cause. Why can the error appear at `OutputStream.write` in implicit mode?
4. Issue a server certificate with only `DNS:localhost` and omit `IP:127.0.0.1`, keeping the client connecting to `127.0.0.1` with `HTTPS` endpoint identification. Predict the result; propose a proper fix that does not use trust-all.
5. Move `socket.getSession()` **before** `setEndpointIdentificationAlgorithm("HTTPS")`. Analyze why calling this getter to "peek at the session" can trigger the handshake too early.
6. Print the negotiated `getCipherSuite()`/`getProtocol()` after TLS. Why is this value fundamentally different from `getEnabledProtocols()` before the handshake?
7. Enable `SSLServerSocket.setNeedClientAuth(true)` without adding a client cert/private key for the client in the lab. Record the result; what configuration must be added for real mTLS?
8. Give the client and server disjoint TLS protocol lists. In explicit/implicit modes, at which operation is the exception thrown?
9. Change both client and server to call `read()` waiting for an application byte before writing. Explain the application-layer deadlock and design proper framing/timeouts.
10. Design the TLS connection lifecycle for a production server: accept queue, handshake timeout, quotas, listener callbacks, peer identity, authorization, request parsing, and close.
11. Compare initial handshake, TLS session resumption, and renegotiation. Why can't repeated `startHandshake()` calls on TLS 1.3 serve as an API to re-authenticate a user?
12. Write a checklist for inspecting `SSLHandshakeException` that may be wrapped in `getCause()` inside an HTTP application; how to distinguish truststore, SAN mismatch, and protocol version issues without lowering security.

## References

- [Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): `startHandshake`, `getSession`, `getHandshakeSession`, and implicit handshake.
- [Java SE 17 — SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): listener, protocols, and client authentication.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): SSLContext init, key/trust managers, and socket factories.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification, SNI, ALPN, and SSL/TLS parameters.
- [Java SE 17 — SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated protocol/cipher and peer.
- [Java SE 17 — HandshakeCompletedListener](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HandshakeCompletedListener.html): callback when TLS handshake completes.
- [Java SE 17 — SSLSocketFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocketFactory.html) and [SSLServerSocketFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocketFactory.html): creating client/server sockets.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): JSSE initialization, debugging, TLS socket coding, and trust.
- [Java SE 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): working with keystores and truststores.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): initial handshake, session resumption, 0-RTT, key update, and security.