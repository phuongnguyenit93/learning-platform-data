# 16.5. Requiring or Requesting Client Certificates with needClientAuth and wantClientAuth

## 1. Problem: should a TLS server require clients to present a certificate?

In standard HTTPS/TLS, the **server** presents a certificate so the **client** verifies the server's identity. The client normally **does not need** an X.509 certificate; users can log in at the application layer via sessions, OAuth 2.0, tokens, or other mechanisms.

In **mutual TLS (mTLS)**, the server also **requires or requests the client to provide a certificate**, and uses a corresponding trust mechanism to verify the client certificate. Java Secure Socket Extension (**JSSE**) lets you configure two important modes:

- `setNeedClientAuth(true)`: **mandatory** client authentication during the TLS handshake. Without a suitable client certificate/credentials, the server **rejects the TLS connection**.
- `setWantClientAuth(true)`: the server **requests** client authentication. If the client does not supply a certificate, the handshake **can still succeed**; if the client presents a certificate, that certificate must still be checked against trust policy.

**Both are server-side policies**, not a toggle for the client to "force" the server to send a certificate. And **neither automatically grants business permissions** to the client: a cryptographically trusted certificate only provides input for the application to map identity, role, tenant, and scope.

This lesson focuses on the lifecycle of the `needClientAuth` and `wantClientAuth` flags in JSSE, cases of absent/valid/invalid certificates, the roles of `KeyManager`–`TrustManager`, inspecting the peer via `SSLSession`, observable differences in TLS 1.3, plus a runnable **Java 17+** program executing four real TLS tests over loopback.

### Expected outcomes after this lesson

1. Distinguish **required**, **requested/optional**, and **not requested**.
2. Know how to configure on `SSLServerSocket`, `SSLSocket`, or `SSLParameters` before the handshake.
3. Understand why `wantClientAuth` **does not** mean "accept any certificate."
4. Distinguish **TLS client authentication** from **authorization**.
5. Create test keystores/truststores with `keytool` and test all four scenarios on JDK 17+.
6. Know how to read `getPeerCertificates()`, handle unauthenticated clients, and avoid configurations that bypass trust validation.

## 2. Distinguishing server authentication and client authentication

### 2.1. One-way HTTPS

The common model:

```text
HTTPS CLIENT                                   TLS SERVER
    |                                            |
    | ----- ClientHello -----------------------> |
    | <----- Server cert / handshake ----------- |
    |                                            |
    | Client verifies CA chain, hostname/IP,     |
    | validity, EKU, and TLS policy              |
    |                                            |
    +---- TLS channel established ---------------+
    |                                            |
    | POST /login, bearer token, session... ---> |
```

Server identity is verified via the **server's** certificate. Whether the client has an application-layer account or login token is a separate matter.

### 2.2. Mutual TLS (two-way TLS)

When the server asks to identify the client via a certificate:

```text
TLS CLIENT                                      TLS SERVER
    |                                                |
    | --------- ClientHello ------------------------> |
    | <-------- Server Certificate / handshake ----- |
    | <-------- CertificateRequest (if configured) - |
    |                                                |
    | ---- Client Certificate (if any/matching) ----> |
    | ---- Proof of private key possession ---------> |
    |                                                |
    |                                  TrustManager verifies
    |                                  cert chain / policy
    |                                                |
    +----- TLS handshake succeeds or is rejected ----+
```

This is a **logical** diagram. The exact sequence of TLS messages differs between **TLS 1.2 and TLS 1.3**. In TLS 1.3, the client can send an empty `Certificate` message when it has no matching certificate; the server then applies its required/optional policy. Do not infer from diagram ordering that all TLS versions transmit certificates identically.

### 2.3. What is a client certificate?

A client certificate is an X.509 certificate carrying a public key; the client must possess the **corresponding private key** to participate in a client-authentication handshake. A `client.cer` file containing only the **public certificate** is insufficient as an identity for the client to prove private-key possession.

A typical mTLS setup requires:

- **Server:** the **server's** private key + certificate chain, and a **TrustManager** configured to trust allowed client certificates.
- **Client:** a **TrustManager** to verify the server certificate; if mTLS is requested/required, a **KeyManager** holding the corresponding private key and client certificate chain.
- **Both sides:** algorithm/TLS version configuration, trust anchors, certificate usage policies, and valid endpoint identities.

## 3. Three client authentication modes

For an accepted `SSLSocket` operating in **server mode**, there are three logical states:

| Mode | Configuration | When the client **has no** certificate | When the client has a **trusted, matching** certificate | When the client **presents** an untrusted certificate |
| --- | --- | --- | --- | --- |
| **Not requested** | `setNeedClientAuth(false)` or `setWantClientAuth(false)` depending on state | Handshake can succeed | Server normally does not request a client cert in this handshake | Do not extrapolate: if unrequested, the client may send no cert |
| **Requested / optional** | `setWantClientAuth(true)` | **Handshake can succeed** but **has no mTLS identity** | Handshake succeeds; server has a verified peer certificate | If a certificate is actually sent and validation fails, **handshake is rejected** |
| **Mandatory / required** | `setNeedClientAuth(true)` | **Handshake is rejected** | Handshake succeeds; TLS client authentication is performed | **Handshake is rejected** |

The "succeed" outcomes in the table also depend on other TLS conditions: whether the server certificate is trusted, whether the hostname matches, whether the version/cipher suite is allowed, and whether the client certificate meets certificate policy.

**Keywords to remember:**

- `need` = **MUST**: without a valid client certificate, do not allow the server-side handshake to complete.
- `want` = **ASK / OPTIONAL**: without a client certificate, TLS can still succeed.
- `want` **does NOT** = "bad certificate still accepted." If a certificate is sent and `TrustManager` rejects it, the connection must fail per security policy.
- Client-auth flags are not directly tied to the client verifying the **server hostname**; never forget HTTPS endpoint checks just because mTLS is enabled.

### 3.1. Sensitivity of optional client authentication

If the server sets `wantClientAuth(true)` and the client presents no certificate, the application can still receive a valid TLS connection in terms of **channel encryption**, yet **without a client-certificate-authenticated identity**.

For example, a system allowing both regular users and certificate-bearing robots:

```text
TCP/TLS accepted with wantClientAuth=true
                  |
                  v
Server checks: does peer have a verified client certificate?
        | no                                 | yes
        v                                    v
   Anonymous branch /                     Map identity
   other authentication                   from trusted cert
        |                                    |
   Allow public APIs only             Check role, tenant, scope
   or require login                   before protected APIs
```

If an admin API **mandates mTLS**, merely setting `wantClientAuth(true)` is **not enough**. You must reject sessions without a certificate right at TLS using `needClientAuth(true)` (on the corresponding listener), or enforce a tested mandatory gate at the application/proxy layer before execution, depending on architecture. Never label an API "mTLS required" merely because the listener has `wantClientAuth`.

### 3.2. Required client authentication is still not authorization

`needClientAuth(true)` proves the server required a certificate **accepted by the trust manager** during the handshake; it **does not prove that client is allowed to call every function**.

If the truststore holds an internal CA that issues certificates for multiple applications or multiple tenants, a valid certificate from application A may still belong to that trust domain even when accessing application B's API.

After the handshake, map the certificate identity (per DNS SAN, URI SAN, subject, issuer, public-key binding policy...), check `clientAuth`/EKU purpose, validity, revocation status, and authorize according to the **actual system-trusted identity**. Never use raw `CN` or `SAN` without defining how identification/verification works.

## 4. Which JSSE APIs set needClientAuth/wantClientAuth?

### 4.1. SSLServerSocket: applies to newly accepted connections

**Illustrative snippet** example:

```java
SSLServerSocket listener = (SSLServerSocket)
        serverContext.getServerSocketFactory().createServerSocket(8443);

listener.setNeedClientAuth(true); // Client cert required.
System.out.println(listener.getNeedClientAuth()); // true
System.out.println(listener.getWantClientAuth()); // false
```

`SSLServerSocket` is the **listening socket**; when `accept()` creates a server-mode `SSLSocket`, the new socket **inherits the initial configuration** of the listener. When the server calls `setNeedClientAuth(true)`, a client failing to provide authentication stops TLS negotiation and drops the connection per Java 17 Javadoc.

When using:

```java
listener.setWantClientAuth(true);
```

the server only **requests** client authentication and allows a client not to present a certificate. That call **overrides** any prior `setNeedClientAuth` setting on the listener.

**Avoid:** flipping flags on the listening socket expecting **already-accepted/handshaken** connections to pick up the new settings. Modifying the listener affects only how subsequent accepted sockets are initialized; on an accepted socket, settings must be placed **before the initial handshake**. For already-established sessions, do not expect flag changes to force the client to present a certificate mid-session.

### 4.2. SSLSocket on the server side

When per-connection policy is needed:

```java
try (SSLSocket peer = (SSLSocket) listener.accept()) {
    peer.setNeedClientAuth(true); // Before starting the handshake.
    peer.startHandshake();
    // Peer auth/TLS handshake has been checked per configuration.
}
```

This snippet depends on an already-created `listener` and `serverContext`; it is **not a standalone program**. `SSLSocket.setNeedClientAuth` or `setWantClientAuth` is only meaningful when the socket operates in **server mode**.

Distinguish:

- `SSLServerSocket.setNeedClientAuth`: **initial** configuration for newly accepted sockets.
- `SSLSocket.setNeedClientAuth`: configuration for a **specific accepted socket** before handshake.
- `SSLParameters.setNeedClientAuth`: stores policy to apply to a socket/engine, typically via `setSSLParameters(...)`.

When developing a server with multiple endpoint groups, configure controlled dedicated listeners/ports or policies; do not rely on flipping flags based on unauthenticated client data.

### 4.3. SSLParameters: need/want are mutually exclusive states

Example:

```java
SSLParameters params = socket.getSSLParameters();
params.setNeedClientAuth(true);
System.out.println(params.getNeedClientAuth()); // true
System.out.println(params.getWantClientAuth()); // false

params.setWantClientAuth(true);
System.out.println(params.getNeedClientAuth()); // false
System.out.println(params.getWantClientAuth()); // true

socket.setSSLParameters(params); // Apply to socket before handshake.
```

**Rule per Java 17 Javadoc:**

- `SSLParameters.setNeedClientAuth(...)` **clears the wantClientAuth flag**.
- `SSLParameters.setWantClientAuth(...)` **clears the needClientAuth flag**.
- The two flags **do not stack**. If both are accidentally called with `true`, the later call changes the policy.
- `SSLServerSocket` and `SSLSocket` also override the related setting: calling `setWantClientAuth(true)` after `setNeedClientAuth(true)` leaves the final state as **want**, no longer **need**.

If configuration code is spread across multiple layers (framework, adapters, security config methods), inspect the **final state after all setters have run** using `getNeedClientAuth()` and `getWantClientAuth()`. One small config change can inadvertently downgrade mTLS from **required** to **optional**.

### 4.4. SSLEngine

With NIO/Netty or a transport managed directly with `SSLEngine`, you can use:

```java
SSLEngine engine = sslContext.createSSLEngine();
engine.setUseClientMode(false); // Engine on the TLS server side.
SSLParameters params = engine.getSSLParameters();
params.setNeedClientAuth(true);
engine.setSSLParameters(params);
```

This is an illustrative snippet. Creating `SSLEngine`, TLS/hostname settings, buffers, tasks, and non-blocking handshakes must be fully implemented per JSSE/transport library. The core rule remains **setting server mode and client-auth policy before the handshake**. If using a framework, know where its `clientAuth=REQUIRE/OPTIONAL/NONE` option maps to JSSE.

## 5. How are certificates accepted by KeyManager and TrustManager?

### 5.1. Two roles that are easily swapped

In `SSLContext.init(KeyManager[], TrustManager[], SecureRandom)`:

- **`KeyManager`** selects the local private key + certificate chain for **this side to present** when required by the protocol.
- **`TrustManager`** verifies the **peer's** (the other side's) certificate when presented.

For an mTLS server:

| Server component | Required content | Function |
| --- | --- | --- |
| `KeyManagerFactory` initialized from `server.p12` | Server private key + certificate chain | Presents server identity to the client; proves possession of the server private key. |
| `TrustManagerFactory` initialized from `server-trust.p12` | CAs/client certs trusted by the server per policy | Verifies the certificate presented by the client. |
| `setNeedClientAuth(true)` or `setWantClientAuth(true)` | Server-side socket policy flag | Determines whether a client certificate is mandatory during the handshake. |

For the client:

| Client component | Required content | Function |
| --- | --- | --- |
| `TrustManagerFactory` from `client-trust.p12` | Server certificates/CAs trusted by the client | Verifies the server; **must also check hostname/IP** if required by protocol. |
| `KeyManagerFactory` from `client.p12` | Client private key + certificate chain (when present) | Can select and send the client certificate when requested/required by the server. |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Reference identity from the endpoint the client intends to call | Checks server name when performing HTTPS/TLS per JSSE. |

**Common mistake:** creating `server.p12` for the server and enabling `needClientAuth(true)`, without configuring a truststore so the server **trusts the client certificate's issuer**. Even a client with a certificate will be rejected.

Conversely, a client with `client.p12` but **no** truststore trusting the server certificate will reject **server authentication**; this failure is independent of the server's want/need setting.

### 5.2. Client must have a matching private key, not just a public certificate

`KeyManagerFactory` selects a certificate chain/private key based on the algorithms and acceptable issuers list sent by the server. If no matching alias/certificate is found, the client may **send no certificate**, even if the keystore holds another entry.

With `wantClientAuth`, this situation can let the handshake **succeed with no peer cert** — leaving no proof the client authenticated via mTLS. With `needClientAuth`, the server will **reject**.

That differs from "the client definitely sent an untrusted certificate": if a certificate **was sent** and trust validation failed, the handshake must not pass automatically just because want=optional.

### 5.3. Trust does not automatically mean "authorized"

`TrustManagerFactory` under PKIX/truststore can recognize many client certificates issued by the same CA. To authorize a specific service:

- Choose an **identity attribute** and stable mapping standard, such as a workload URI SAN per service-mesh profile, or a registry-pinned public-key identity.
- Verify the issuer/trust anchor and relevant attributes (`clientAuth` EKU, key usage, validity, revocation if policy requires).
- Map certificate → application principal → role/tenant/scope.
- Never just match `CN` strings as arbitrary usernames or grant admin access to every certificate from an internal CA.
- Account for certificate rotation: do not bind authorization to mutable serial numbers/subjects if the architecture needs a stable identity.

### 5.4. Requiring a client certificate still does not replace verifying the server

The client must authenticate the server before sending sensitive data or credentials; mTLS **does not** permit the client to skip hostname verification. If the client connects to `https://api.example.test`, the server certificate must have a matching SAN for `api.example.test` and the PKIX trust path must be checked per policy.

In the lab below, connections use IP `127.0.0.1`, so the test server certificate contains **SAN:IP Address 127.0.0.1**. The client calls `setEndpointIdentificationAlgorithm("HTTPS")` to demonstrate JSSE-layer endpoint checking; there is no trust-all manager.

## 6. Java 17+ lab: four real TLS 1.3 handshakes

This example uses tools built into the JDK (`keytool`, `javac`, `java`) and a single Java file. We create **four PKCS#12 test stores**:

```text
server.p12         -- private key + cert of localhost
client.p12         -- private key + cert of demo-client
server-trust.p12   -- server trusts the test client certificate
client-trust.p12   -- client trusts the test server certificate

Client without certificate:
  SSLContext.init(null, clientTrustManagers, random)

Client with certificate:
  SSLContext.init(clientKeyManagers, clientTrustManagers, random)

Server always has:
  SSLContext.init(serverKeyManagers, serverTrustManagers, random)
```

Here the certificates are **self-signed for testing only**, with each side **explicitly installing the other's certificate into its own truststore**. This is an intentional way to create test anchors for a lab, **not** a recommended production model. In real environments, use proper CA/PKI, provisioning, and certificate lifecycle management.

### 6.1. Creating certificates and truststores with keytool

Create a **new lab directory** and run the following commands inside it. The `keytool` commands below are single-line so they work in both standard shells and PowerShell (with the JDK on PATH):

```bash
mkdir client-auth-lab
cd client-auth-lab

keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -validity 365 -dname "CN=localhost, O=TLS Demo, C=US" -ext "SAN=dns:localhost,ip:127.0.0.1" -ext "EKU=serverAuth" -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -validity 365 -dname "CN=demo-client, O=TLS Demo, C=US" -ext "EKU=clientAuth" -keystore client.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -exportcert -alias server -keystore server.p12 -storepass changeit -file server.cer

keytool -exportcert -alias client -keystore client.p12 -storepass changeit -file client.cer

keytool -importcert -alias server -file server.cer -keystore client-trust.p12 -storetype PKCS12 -storepass changeit -noprompt

keytool -importcert -alias client -file client.cer -keystore server-trust.p12 -storetype PKCS12 -storepass changeit -noprompt
```

**Warning:** the password `changeit`, self-signed certificates, and test RSA keys in these commands are **for lab use only**. Never use them in real environments, never commit `*.p12`, `*.jks`, or `*.key` to repositories, never paste private keys into chats/tickets, and never use a test CA as a production trust anchor. After the lab, delete the test directory per policy. The test keys are valid for **365 days from generation**, so regenerate them later instead of reusing expired keystores.

The `server.cer` and `client.cer` files contain only **public certificates**, with no private keys. They are imported into truststores for trust decisions; when the client authenticates itself, the private key resides in `client.p12`.

### 6.2. ClientAuthDemo.java program

Create `ClientAuthDemo.java` in the directory containing the four `.p12` files:

```java
import java.io.IOException;
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
import javax.net.ssl.SSLPeerUnverifiedException;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public final class ClientAuthDemo {
    private static final char[] PASSWORD = "changeit".toCharArray(); // Test only.
    private record Outcome(boolean accepted, boolean peerCertificate) {}

    private static KeyStore load(Path file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    private static SSLContext context(String identityFile, String trustFile)
            throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(load(Path.of(trustFile)));

        KeyManagerFactory kmf = null;
        if (identityFile != null) {
            kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(load(Path.of(identityFile)), PASSWORD);
        }

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf == null ? null : kmf.getKeyManagers(),
                tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    private static Outcome run(SSLContext serverContext,
                               SSLContext clientContext,
                               boolean need) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (SSLServerSocket listener = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(
                        0, 5, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5000);
            listener.setEnabledProtocols(new String[]{"TLSv1.3"});
            if (need) {
                listener.setNeedClientAuth(true);
            } else {
                listener.setWantClientAuth(true);
            }

            Future<Outcome> serverResult = executor.submit(() -> {
                try (SSLSocket peer = (SSLSocket) listener.accept()) {
                    peer.setSoTimeout(5000);
                    peer.startHandshake();
                    boolean hasCertificate;
                    try {
                        peer.getSession().getPeerCertificates();
                        hasCertificate = true;
                    } catch (SSLPeerUnverifiedException noCertificate) {
                        hasCertificate = false;
                    }
                    return new Outcome(true, hasCertificate);
                } catch (IOException handshakeOrSocketFailure) {
                    return new Outcome(false, false);
                }
            });

            try (SSLSocket client = (SSLSocket)
                    clientContext.getSocketFactory().createSocket(
                            "127.0.0.1", listener.getLocalPort())) {
                client.setSoTimeout(5000);
                client.setEnabledProtocols(new String[]{"TLSv1.3"});
                SSLParameters parameters = client.getSSLParameters();
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                client.setSSLParameters(parameters);
                try {
                    client.startHandshake();
                } catch (IOException expectedForRejectedHandshake) {
                    // We report the server's result, not an early TLS 1.3 client result.
                }
                return serverResult.get(10, TimeUnit.SECONDS);
            }
        } finally {
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        try {
            SSLContext server = context("server.p12", "server-trust.p12");
            SSLContext withoutCertificate = context(null, "client-trust.p12");
            SSLContext withCertificate = context("client.p12", "client-trust.p12");

            Outcome optionalAbsent = run(server, withoutCertificate, false);
            Outcome requiredAbsent = run(server, withoutCertificate, true);
            Outcome optionalPresent = run(server, withCertificate, false);
            Outcome requiredPresent = run(server, withCertificate, true);

            System.out.println("want + no cert: accepted=" +
                    optionalAbsent.accepted() + ", authenticated=" +
                    optionalAbsent.peerCertificate());
            System.out.println("need + no cert: accepted=" +
                    requiredAbsent.accepted() + ", authenticated=" +
                    requiredAbsent.peerCertificate());
            System.out.println("want + trusted cert: accepted=" +
                    optionalPresent.accepted() + ", authenticated=" +
                    optionalPresent.peerCertificate());
            System.out.println("need + trusted cert: accepted=" +
                    requiredPresent.accepted() + ", authenticated=" +
                    requiredPresent.peerCertificate());
        } finally {
            Arrays.fill(PASSWORD, '\0');
        }
    }
}
```

### 6.3. Running the program and stdout

```bash
javac ClientAuthDemo.java
java ClientAuthDemo
```

After completing the `keytool` commands above, the Java program prints exactly:

```text
want + no cert: accepted=true, authenticated=false
need + no cert: accepted=false, authenticated=false
want + trusted cert: accepted=true, authenticated=true
need + trusted cert: accepted=true, authenticated=true
```

**Explanation of the four lines:**

1. `want + no cert: accepted=true, authenticated=false`: server requests optionally. The client has no `KeyManager` containing a client identity, so it sends no certificate; the server-side TLS handshake completes; `SSLSession.getPeerCertificates()` throws `SSLPeerUnverifiedException`, which is mapped to `authenticated=false`.
2. `need + no cert: accepted=false, authenticated=false`: server strictly requires it. The client has no matching certificate, so the server-side TLS handshake is rejected; there is no client-authenticated connection to process requests.
3. `want + trusted cert: accepted=true, authenticated=true`: server only requests, yet the client has a private key and server-trusted cert, so the client can present its certificate and the TLS server handshake accepts it.
4. `need + trusted cert: accepted=true, authenticated=true`: server requires a certificate, and the client has a trusted one; the handshake completes and the server reads `peerCertificates` verified by handshake validation.

These are **server-side outcomes**. The demo uses a separate thread for `listener.accept()` and `peer.startHandshake()`, while the main thread creates the client connection. In TLS 1.3, some server errors can occur **after one side thinks its local `startHandshake` step has completed**; therefore the code returns the result **after retrieving the server's `Future`** rather than treating the return of `client.startHandshake()` alone as proof the server admitted the client.

Catching `IOException` and condensing it to a boolean in the demo is solely to produce stable stdout. **Production must never ignore the cause of a TLS failure**; log non-sensitive error categories and fail closed. The test also uses 5–10 second timeouts to prevent hanging indefinitely in a lab environment; those are not mandatory JSSE timeouts.

### 6.4. What the program actually proves

- It opens a **TCP connection on 127.0.0.1** using **real SSLServerSocket/SSLSocket**, not simulating a handshake with mere boolean flags.
- Both sides enable `TLSv1.3`; the program will fail if the JDK/provider used does not support it.
- The server uses `server.p12` to present its certificate to the client; the client has its own truststore.
- The server uses `server-trust.p12` to authenticate the client certificate when sent by the client.
- The client enables `setEndpointIdentificationAlgorithm("HTTPS")` and connects to `127.0.0.1`, matching the test IP SAN.
- After the handshake, the server checks `getPeerCertificates()` to determine whether the peer has a certificate chain verified within that TLS session.
- When the client has no identity, `SSLContext` receives `null` for `KeyManager[]`: the client still **verifies the server** using `TrustManager[]`, but has no private key for client authentication.

### 6.5. What the program does not prove

- The demo **is not a public PKI** and does not have a production-style CA certificate chain; the truststores hold directly imported test leaf certificates.
- There is no real URL, no DNS/public server, no HTTP request, and no post-TLS role/tenant/scope check.
- It does not automatically prove every certificate from the same CA is permitted; the lab trusts one specific certificate in each direction to test behavior.
- It does not test CRL/OCSP revocation, HSMs, certificate rotation, truststore updates, or production credential separation.
- It does not test the scenario where **the client actually sends a certificate whose chain is untrusted**: when JSSE inspects the acceptable CAs list and cannot pick an alias, the client may **send no certificate** at all. Therefore, testing "untrusted presented certificate" requires a dedicated lab setup.
- It does not guarantee every JDK/provider version emits the same exception messages; the required/optional logic is an API property, while messages/stack traces may vary.

## 7. SSLSession: determining whether the client authenticated with a certificate

After the **server-side TLS handshake succeeds**, you can read the peer's certificate chain:

```java
SSLSession session = peerSocket.getSession();
try {
    Certificate[] chain = session.getPeerCertificates();
    // In server mode: the peer is the client.
    // Identity/authorization mapping per policy is still required.
} catch (SSLPeerUnverifiedException noClientCertificate) {
    // Can happen with wantClientAuth; handle as unauthenticated by mTLS.
}
```

The snippet above requires importing `javax.net.ssl.SSLSession`, `javax.net.ssl.SSLPeerUnverifiedException`, and `java.security.cert.Certificate`, with `peerSocket` being a server-accepted `SSLSocket` that has completed its handshake.

**Notes:**

- `SSLSession.getPeerCertificates()` can throw `SSLPeerUnverifiedException` if no certificate-based peer authentication occurred. Never call it assuming a non-empty array is always returned.
- On a **server-side socket**, the peer certificate is the **client certificate**. On a **client-side socket**, the peer certificate is the **server certificate**. Do not mix up the context.
- In a TLS session verified by a proper trust manager, the chain was evaluated by JSSE per trust policy. Yet the presence of a chain **does not replace** application identity mapping/authorization.
- `session.getPeerPrincipal()` can provide the associated principal; however, `CN` or `X500Principal.toString()` alone is usually insufficient as an identification policy across mTLS models.
- `getLocalCertificates()` (if present) refers to **this local side's own** certificates, unlike `getPeerCertificates()`. Using the wrong one makes code think the client authenticated when it is only seeing the server's cert.

### 7.1. Controlling the anonymous branch of wantClientAuth

If you want optional mTLS for two API groups, enforce a rule such as:

```text
if TLS handshake failed:
    drop connection
else if verified client identity exists:
    map certificate -> approved principal -> authorized routes/scopes
else:
    restrict to anonymous/public routes or require other authentication
```

This is pseudocode, not executable Java. Never allow logic like `if (TLS session exists) allowAdmin()` because **a successful TLS session with want/no-cert does not mean an mTLS identity exists**.

If only certain endpoints require a certificate while others allow anonymous access, consider separating listeners/hostnames with dedicated `needClientAuth` so policy enforcement is explicit. Flipping flags after the handshake based on URL path **does not make the client automatically re-run initial authentication**, especially in TLS 1.3.

## 8. Why wantClientAuth does not mean accepting every certificate

Separate two kinds of failure:

### A. No client certificate

The client may lack a private key/client certificate, or `KeyManager` cannot find a matching alias. With `wantClientAuth`, TLS can succeed and the application receives an **unauthenticated client connection**.

### B. A certificate is sent but fails validation

When the client actually presents a certificate chain, the server must verify it via a properly configured `TrustManager`; for instance:

- The certificate does not chain to a server-accepted trust anchor.
- The certificate is expired, not yet valid, or revoked per policy.
- EKU/KeyUsage does not match `clientAuth`.
- Invalid certificate chain or signature, or disallowed algorithm.
- Issuer/subject/name constraints or other mTLS policies fail.

If a certificate was presented and certificate verification fails, the server **must not** proceed as an anonymous client just because `wantClientAuth(true)` is set. Optional means **a certificate may be omitted**, not "an invalid certificate is acceptable."

**Testing risk:** JSSE `KeyManager` might omit sending a cert if the acceptable issuers list does not match. When the server wants a cert and the client sends none, optional mode can succeed. That result **does not prove** the server accepts an untrusted cert. To test "untrusted certificate was presented," verify via handshake trace or a test-only custom `KeyManager` ensuring the cert is actually transmitted.

Never create a "trust-all" `X509TrustManager` to avoid client certificate errors. Doing so defeats both need and want: an attacker's self-signed certificate could be treated as "authenticated."

## 9. Need/want and TLS 1.2 vs. TLS 1.3

### 9.1. Required/optional policy exists in both

The functional meaning of `setNeedClientAuth` and `setWantClientAuth` stays the same at the JSSE level: whether the server requires or requests a client certificate. What changes are the **handshake message mechanics and timing**, alerts, and session/resumption.

With TLS 1.3, the server can send `CertificateRequest` during the initial handshake. If the client sends no certificate when required by the server, the server rejects (e.g., with a `certificate_required` alert per TLS 1.3). Some stacks may surface exceptions at different moments between client and server. Never test solely by checking whether `client.startHandshake()` returns; verify **whether the server actually completed/admitted the session**.

### 9.2. Do not rely on TLS renegotiation to "upgrade" optional to required

An older pattern once existed: start TLS without a client cert, then on a sensitive HTTP route enable required client auth and try to trigger renegotiation. **Do not design like this.** TLS 1.3 has no TLS 1.2-style renegotiation; post-handshake authentication has its own support conditions and **does not automatically occur** merely because Java code calls `setNeedClientAuth(true)` on an already-handshaken socket.

A stronger design:

- Specify from the **initial handshake** which listeners mandate mTLS.
- If the app needs to upgrade identity, use a new connection with required policy or a specifically designed/audited re-authentication protocol.
- Never allow sensitive operations to execute before the desired identity is established and checked.
- Control session resumption, proxy TLS termination, and caching so mismatched authentication states are never inadvertently reused.

### 9.3. Know which server "actually" grades the certificate

In systems with a load balancer, API gateway, or service mesh, TLS may **terminate before reaching the Java backend**. In that case:

```text
Internet client --(mTLS)--> Gateway --(HTTP or new TLS)--> Java backend
                            |
                            +-- gateway checks client cert
```

The Java backend cannot simply call `SSLSocket.getPeerCertificates()` and assume it is seeing the Internet client's certificate if outer TLS terminated at the gateway. Some proxies forward identity via headers, yet headers are trustworthy only when arriving from an authenticated gateway with spoofing blocked, hop-by-hop protection, and authorization policy. Otherwise, an attacker can send forged headers directly.

Likewise, enabling `needClientAuth` on the backend will not enforce certificates for **client → gateway** connections if outer TLS is managed by the gateway; configure the exact TLS termination point.

## 10. SSLParameters.setNeedClientAuth and setWantClientAuth: common ordering bugs

### 10.1. Both flags cannot be true at once

```java
SSLParameters p = new SSLParameters();
p.setNeedClientAuth(true);
System.out.println(p.getNeedClientAuth()); // true
System.out.println(p.getWantClientAuth()); // false

p.setWantClientAuth(true);
System.out.println(p.getNeedClientAuth()); // false
System.out.println(p.getWantClientAuth()); // true
```

If one configuration module sets required first, and another sets optional later, **the final policy is optional**. And vice versa.

Inspect the state **after configuration assembly completes**, rather than merely grepping source code to see if `setNeedClientAuth(true)` appears somewhere. In high-level frameworks, verify the mapping down to JSSE and run negative handshake tests.

### 10.2. Not every class in an application is naturally in server mode

An `SSLSocket` created to call an external API is normally in **client-mode**; setting `setWantClientAuth(true)` on it **does not** mean the client is telling the server to send a certificate. Server authentication is handled by the TLS client's trust manager and endpoint identification, while the client certificate (if requested by the server) is chosen by `KeyManager`.

Only a **server-mode SSLSocket** gives effect to need/want per Javadoc. If using `SSLEngine`, be sure to call `setUseClientMode(false)` when acting as a TLS server.

### 10.3. Do not mutate state post-handshake to force client auth

Set client-auth policy while the socket has not started its handshake. Once a session is established, flipping flags may not make the peer supply a certificate in the same session, and renegotiation-related behavior should not be relied upon in new designs. Use a listener/new handshake with the right policy.

### 10.4. Do not forget to configure TrustManager

`setNeedClientAuth(true)` **does not** specify which CAs are permitted to sign client certificates. That is the responsibility of trust management. If misconfigured, the server may reject valid clients or accept a broader scope than intended if using an overly broad truststore/wrong manager.

## 11. Production design with mandatory and optional mTLS

### 11.1. When to use needClientAuth

- Internal service-to-service connections where policy requires every client to carry a workload certificate.
- Admin/privileged APIs accessible only from machines or service identities issued a certificate.
- Partner data-ingestion channels with registered client certificates and clear identity mapping policies.
- Dedicated listeners for robots/batch jobs requiring authentication at the TLS handshake.

In every case, verify thoroughly: the TLS client certificate is **trusted** and **the right client identity** for that service; then assign specific permissions. `needClientAuth` does not replace application authorization.

### 11.2. When to use wantClientAuth

- A listener serving both mTLS-identified clients and anonymous visitors, with clear **routing/authorization** after the handshake.
- Client certificate migration phases, provided sensitive APIs remain **blocked server-side** when no identity is present, with a plan to transition to required.
- Models seeking an additional machine/service identification signal via certificates **without defaulting** to extra privileges when a certificate is absent.

**High risk:** configuring want while marketing/security policy declares "all APIs enforce mTLS." Any client without a cert can complete TLS; if application checks miss a single route, anonymous connections can slip through.

If mandatory enforcement across every handler path is truly needed, use `needClientAuth` or an equivalent client-certificate-enforcing gateway layer, backed by negative tests.

### 11.3. Avoid overly broad truststores

Trusting a public root CA or broad CA bundle to authenticate **client machine identity** can cause the server to accept certificates not issued under your organization's expected process. For secure production mTLS, check issuer/policy/OID/EKU, SAN identity, issuance authority, trust rotation, and revocation; consider a dedicated internal CA scoped to client certificates rather than the default truststore used for HTTPS servers.

### 11.4. Certificate lifecycle and revocation

- Client private keys need protection: strong-password KeyStore, OS secret manager, or HSM/TPM if required by threat model; never hardcode test credentials.
- Certificate rotation must plan ahead for both sides updating trust anchors, accepted issuers, identity mappings, and overlap windows.
- If a client private key is compromised, revoke/disable the identity and rotate certificates/keys; **want/need does not automatically know a key was stolen**.
- PKIX validity/revocation/algorithm policies must match the environment; never disable trust/revocation checks just to make a demo pass.
- Never take a client-supplied subject DN outside TLS and treat it as an authenticated certificate identity.

## 12. Operational errors and symptoms

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| `needClientAuth=true`, client has no cert, handshake fails | **By design**: required yet no certificate | Provision client cert/private key or adjust listener type per policy; do not disable trust. |
| `wantClientAuth=true`, client has no cert, handshake succeeds | **By design**: optional | In the app, deny mTLS privileges when the peer cert is absent. |
| Client has `client.p12` yet server still sees no certificate | KeyManager could not match alias, issuer list/algorithm mismatch, private key not loaded | Check client key entry, certificate chain, acceptable issuers, handshake trace, and KeyManager. |
| Client cert presented yet handshake fails | Untrusted CA, expired, wrong EKU/key usage, invalid chain | Fix truststore and PKIX policy; reissue valid cert. |
| Server certificate presented yet client rejects | Client truststore does not trust server or SAN hostname/IP mismatch | Fix server cert/truststore/reference identity; never drop hostname checks. |
| `SSLPeerUnverifiedException` when calling `getPeerCertificates()` on server | No certificate-based peer authentication | Handle the anonymous branch of optional mTLS; if mandatory, inspect listener/policy. |
| `SSLHandshakeException` with `bad_certificate` or other alert | Trust/certificate/handshake policy failure; message varies by provider | Log cause safely; inspect actual handshake logs. |
| Server still allows anonymous despite calling `setNeedClientAuth(true)` | `setWantClientAuth(true)` called afterward; set on wrong socket; proxy terminates TLS | Verify final state, TLS termination point, and negative handshake tests. |
| `needClientAuth` enabled on backend yet API gateway admits public clients | External client TLS terminates at the gateway | Enable client-auth on the gateway or properly protect the backend hop. |
| Some clients authenticate, some do not with want | Only some clients have matching private keys and certificate chains | Design explicit identity fallback/authorization; never assume all are mTLS. |
| Valid client certificate yet rejected by API | TLS trust succeeded but application authorization lacks role/scope | Check identity mapping and policy; do not weaken TLS. |
| Upgraded want to need yet old connections remain active | Sessions/handshakes created prior to the change | Terminate/close old sessions per policy or follow safe transition procedures. |

### 12.1. Debugging JSSE without weakening security

In a lab, TLS handshake diagnostics can be enabled via JVM flag:

```bash
java -Djavax.net.debug=ssl:handshake -cp . ClientAuthDemo
```

Depending on the system, output can be verbose and contain sensitive details (hostnames, certificate chains, identifiers, TLS metadata). Enable only when authorized, protect logs, and **never put private keys, passwords, or secrets** into logs. Use only on test machines, never enabled by default in production.

Distinguish clearly:

- **Client sends no certificate**: with want, may proceed; with need, rejected.
- **Server does not trust presented client certificate**: rejected, never "falls back to anonymous" as a safe design.
- **Client does not trust server**: client rejects, unrelated directly to need/want.
- **Application denies permission**: TLS handshake can still succeed; HTTP API returns 401/403 per policy — this is a separate layer.

Never recommend configuring `trustAll()` or `HostnameVerifier((h,s)->true)` while debugging. The right fix is fixing the identity/certificate/truststore or policy.

## 13. Pre-release test matrix

| Server mode | Client identity | Presents cert? | Expected server-side TLS result | Identity in application |
| --- | --- | --- | --- | --- |
| None | None | Not requested | TLS can succeed | No mTLS identity. |
| Want | No key pair | No | **Succeeds** if other conditions pass | Anonymous / other auth, no mTLS identity. |
| Need | No key pair | No | **Fails** | Do not process request. |
| Want | Trusted cert | Yes | **Succeeds** | Has certificate identity; still check authorization. |
| Need | Trusted cert | Yes | **Succeeds** | Has certificate identity; still check authorization. |
| Want | Cert actually sent but untrusted | Yes | **Fails** | Do not process request. |
| Need | Cert actually sent but untrusted | Yes | **Fails** | Do not process request. |
| Need | Cert from right CA but wrong role/tenant | Yes | TLS can succeed | **Application must reject** if unauthorized. |
| Want | Has cert yet KeyManager selects no alias | No | TLS can succeed | No mTLS identity. |
| Need | Client has cert yet does not trust server | May not even send | TLS fails on server identity/trust | Do not process request. |

**Do not test only the positive case** `need + valid cert`. The negative case **need + no cert** must be blocked; **want + no cert** must never be assigned an mTLS identity. When policy for a route requires mTLS, test requests through **every TLS termination point**, not just a single isolated JSSE class.

### 13.1. Assertions to include in integration tests

1. `getNeedClientAuth()`/`getWantClientAuth()` reflect the **final state** of the listener/engine.
2. No client cert + required → server-side TLS handshake **fails**.
3. No client cert + optional → server-side TLS handshake **can succeed**; `getPeerCertificates()` reports no authenticated peer.
4. Valid and trusted client cert → handshake succeeds; server receives the peer cert.
5. Invalid or revoked client cert → handshake rejected per trust policy, including optional mode when a cert is actually sent.
6. Valid client cert lacking tenant permission → application returns rejection, never treating a cert as blanket admin access.
7. Server cert with wrong SAN → client handshake fails even when the server requests a valid client cert.
8. Rotation and truststore updates create no window accepting unwanted aliases/issuers.
9. Proxy/gateway blocks spoofed identity headers from untrusted sources.
10. TLS 1.3 session reuse/connection pooling never reuses the wrong authentication state for protected routes.

## 14. FAQ and misconceptions to eliminate

**Q: Does `wantClientAuth(true)` differ from `needClientAuth(true)` only by the word "optional"?**

The main difference is **handshake behavior when the client supplies no certificate**. With want, the server can accept a connection without a certificate, so the **application layer must explicitly distinguish anonymous traffic**. With need, the server must not let the handshake complete if the client cannot authenticate with a matching certificate.

**Q: With want=true, if a client sends an expired or untrusted certificate, does the server proceed as anonymous?**

It should not. When **a certificate has been sent and validation fails**, the handshake must fail. Optional means omitting a certificate is allowed, not that presenting a bad certificate is allowed. However, when `KeyManager` cannot pick an alias, the client may **send no cert**, in which case inspect the handshake trace to be sure.

**Q: With need=true, can I drop the server's KeyManager because the server only checks the client cert?**

No. In standard TLS server authentication, the server also needs a local identity/private key so the client verifies the server; mTLS adds the **client certificate** step rather than replacing the server certificate.

**Q: What should `serverTruststore` contain?**

Trust anchors or certificates that the **server is permitted to trust to verify clients** per policy; this may be an internal CA dedicated to issuing client certs, not necessarily the same store the client uses to trust the server. Yet a broad trust anchor is insufficient: identity/authorization mapping is needed.

**Q: If the client has `client.cer` on the classpath, is it ready for mTLS?**

Not yet. The client must have the corresponding private key and a `KeyManager` able to select the right credential. A public certificate file provides no proof of private-key possession.

**Q: What does `getPeerCertificates()` tell us?**

It returns the peer's certificate chain in a session verified by certificate authentication (with an appropriate trust manager); it throws `SSLPeerUnverifiedException` if the peer was not verified that way. It does not evaluate whether the application should grant a role.

**Q: Should we enable wantClientAuth across all APIs first, and switch to need only on admin routes?**

Do not rely on changing flags mid-TLS-session. Set required policy on the appropriate listener **right from the handshake**, or design strict application-layer and gateway authentication/authorization. TLS 1.3 lacks legacy renegotiation to upgrade like that.

**Q: If the TLS server sits behind a load balancer, does setting needClientAuth in Java check the Internet client?**

Not necessarily. If TLS terminates at the gateway, Java only sees the downstream connection from the gateway (or plain HTTP). Client certificates must be enforced **at the actual TLS termination point** and verified identity passed across a trusted, anti-spoofing boundary.

**Q: If I enable needClientAuth, is the server certificate automatically verified for DNS SAN?**

No. Having the **client verify the server** is the opposite direction. The HTTPS client needs proper trust paths and endpoint identification, unrelated directly to the server's client-cert flag.

## 15. Deployment checklist

- [ ] Explicit decision on **NONE**, **WANT**, or **NEED** per listener/port/route/proxy.
- [ ] For APIs requiring strict mTLS, server-side handshake must **reject clients without a cert**.
- [ ] Verified final state of `getNeedClientAuth()` and `getWantClientAuth()`; no unintended reverse overrides.
- [ ] Server has valid KeyManager/certificate/private key; client has TrustManager trusting server and proper hostname verification.
- [ ] Server has TrustManager trusting the right client issuers/certificates per PKIX policy; no accept-all.
- [ ] Client has private key/cert chain when requesting or requiring certificate authentication.
- [ ] Client certificates have proper EKU/KeyUsage, validity, policy/revocation; root CAs distributed via trusted channels.
- [ ] Under want/optional, application handles **absent peer certificate** as anonymous or requires alternative auth.
- [ ] When a peer cert is present, application also verifies **identity mapping, authorization, role, tenant, and scope**.
- [ ] Never attempt to upgrade optional to required post-handshake without explicit protocol support.
- [ ] Tested all four baseline cases plus bad client cert / wrong server hostname cases.
- [ ] Demo truststores/keystores/passwords never copied to production; private keys never stored in repos.
- [ ] Gateway/proxy/service-mesh TLS termination points identified; identity headers cannot be spoofed by clients.
- [ ] Monitoring and plans in place for rotation/revocation of client certificates, session/connection pooling, and fail-closed behavior.

## 16. Self-practice exercises

1. Precisely distinguish `setNeedClientAuth(true)` and `setWantClientAuth(true)` when the client has no certificate.
2. Why is `wantClientAuth` **not** a mechanism for letting through a certificate rejected by `TrustManager`?
3. Server has `needClientAuth=true` without a matching truststore; client has a certificate. Is the handshake guaranteed to succeed?
4. In `SSLContext.init(keyManagers, trustManagers, random)`, what does the server use each array for? What about the client?
5. If a client has only `client.cer` without a private key, can it present proof of private-key possession?
6. If `SSLParameters` calls `setNeedClientAuth(true)` and then `setWantClientAuth(true)`, what is the final state?
7. Why can `SSLSession.getPeerCertificates()` throw `SSLPeerUnverifiedException` when want=true?
8. Why does `needClientAuth=true` not tell you the client's role, tenant, scope, or database read permissions?
9. When TLS terminates at a gateway, where should the Java backend trust client identity from and how is spoofing prevented?
10. Does TLS 1.3 allow you to simply flip a flag on an already-handshaken socket to force the client to present a cert immediately? Why shouldn't you rely on that?
11. If the server verifies the client cert, yet the HTTPS client disables hostname verification for the server, what risk remains?
12. Which negative tests would you write to prove an "mTLS required" API truly refuses anonymous connections?

**Exercise A:** run `ClientAuthDemo` and record all four lines. Then change the code from `listener.setWantClientAuth(true)` to `listener.setNeedClientAuth(true)` in all cases; predict the outcome when the client has no cert.

**Exercise B:** replace `server-trust.p12` with a test truststore lacking the issuer of `client.p12`. Check whether the handshake fails or the client chooses not to send a cert; use `javax.net.debug=ssl:handshake` in a test environment to tell them apart.

**Exercise C:** add a local HTTP handler behind TLS with `/public` and `/admin` routes. When the listener is in want mode, ensure `/public` allows anonymous clients per policy, while `/admin` rejects unless the session carries a trusted client certificate identity and admin permission. Then compare with need mode.

**Exercise D:** create a second client cert issued by the same test CA but mapped to a different tenant. Prove that `needClientAuth` can accept the certificate per trust policy while authorization still rejects routes for the wrong tenant.

**Exercise E:** simulate an accidental config override: call need=true in a security config layer and then want=true in a framework layer. Write an assertion `getNeedClientAuth() == true` when the listener is ready to accept connections to catch the regression.

## 17. Official API documentation

- [SSLServerSocket — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): `setNeedClientAuth`, `setWantClientAuth`, getters, three-state behavior, and effect on accepted sockets.
- [SSLSocket — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): server-side socket configuration, `startHandshake`, and `getSSLParameters`.
- [SSLParameters — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setNeedClientAuth` clears want flag, `setWantClientAuth` clears need flag, `setEndpointIdentificationAlgorithm`.
- [SSLContext — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): `init(KeyManager[], TrustManager[], SecureRandom)` and TLS socket factories.
- [SSLSession — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): `getPeerCertificates()`, `getPeerPrincipal()`, and `SSLPeerUnverifiedException`.
- [KeyManagerFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): using key stores/private keys to select local identity.
- [TrustManagerFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): creating trust managers from a truststore.
- [X509ExtendedTrustManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): verifying certificates per TLS peer/socket/engine context.
- [Java Secure Socket Extension (JSSE) Reference Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): key/trust manager model, TLS 1.3, and SSL/TLS programming.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): CertificateRequest, client authentication, `certificate_required` alert, and TLS 1.3 differences.