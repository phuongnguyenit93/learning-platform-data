# HttpsURLConnection with SSLSocketFactory and Hostname Verification — Java 17

## 1. The Problem: TLS Can Encrypt, But Did You Connect to the Right Server?

A Java client needs to call an internal service over HTTPS. The server uses an X.509 certificate issued by a private CA or a test certificate not yet in the default truststore. The application can configure a custom `SSLSocketFactory` for `HttpsURLConnection` to trust that specific CA/certificate. However, even when the **certificate chain is trusted**, the application still needs to verify that the certificate **was issued for the exact hostname in the URL**.

For example, a server presents a certificate with `subjectAltName: DNS:localhost`:

```text
https://localhost:8443/hello     -> hostname matches DNS SAN
https://127.0.0.1:8443/hello     -> NO match: IP requires iPAddress SAN
```

Both URLs may point to the same loopback server. But from an HTTPS authentication perspective, **the hostname requested by the client is part of the service identity**, not a decorative detail. If you only check "is this certificate trusted?" while ignoring the hostname, a server with a valid certificate for another host could be wrongly accepted.

This lesson helps you:

1. Understand `HttpsURLConnection`, `SSLContext`, `SSLSocketFactory`, `TrustManagerFactory`, truststore, and `HostnameVerifier`.
2. Distinguish **trust chain verification** from **hostname verification**.
3. Attach an `SSLSocketFactory` to **a single connection** without altering the HTTPS configuration of the entire JVM.
4. Understand `subjectAltName` (DNS/IP), SNI, and common hostname errors.
5. Write a real runnable Java 17 example with a **loopback HTTPS server**, generating certificates via the JDK's `keytool`, allowing valid connections to succeed and rejecting mismatched hostname connections.
6. Avoid dangerous anti-patterns such as **trust-all certificates** or a `HostnameVerifier` that always returns `true`.
7. Handle timeouts, response streams, TLS errors, HTTP errors, redirects, and connection lifecycles.

**Scope:** this is the classic `java.net.URLConnection / HttpURLConnection` API extended by `javax.net.ssl.HttpsURLConnection`, not the modern `java.net.http.HttpClient`. The two APIs configure TLS differently; do not mix up methods between them.

## 2. Layer Diagram: Who Decides What?

```text
URL("https://api.example/...") 
        |
        v
HttpsURLConnection (extends HttpURLConnection)
  |  request method, headers, timeouts, input/error stream
  |
  +--- SSLSocketFactory ----> creates TLS socket
  |         ^
  |         |
  |     SSLContext("TLS")
  |       |-- KeyManager(s): client certificate / mTLS if needed
  |       |-- TrustManager(s): verifies peer certificate/trust chain
  |       +-- SecureRandom
  |
  +--- HTTPS hostname identification (ON by default)
  |       +-- HostnameVerifier if additional decision is needed
  |
  +--- TLS handshake -> HTTP request -> HTTP response
```

| Component | Java 17 API | Primary Responsibility |
|---|---|---|
| `URL` | `java.net.URL` | Stores the resource address, including the scheme and hostname the client wants to call |
| `URLConnection` | `java.net.URLConnection` | Configures and opens a connection to the resource |
| `HttpURLConnection` | `java.net.HttpURLConnection` | HTTP method, status, redirects, headers, response/error stream |
| `HttpsURLConnection` | `javax.net.ssl.HttpsURLConnection` | HTTPS + TLS-specific socket factory, hostname verifier, certificate/session |
| `SSLContext` | `javax.net.ssl.SSLContext` | Configures provider/protocol, key/trust managers to create TLS sockets/engines |
| `SSLSocketFactory` | `javax.net.ssl.SSLSocketFactory` | Creates `SSLSocket` instances with TLS configuration |
| `KeyManagerFactory` | `javax.net.ssl.KeyManagerFactory` | Creates key managers from key material, useful for server certificates or client mTLS |
| `TrustManagerFactory` | `javax.net.ssl.TrustManagerFactory` | Creates trust managers from a truststore, validating the certificate path according to policy |
| `KeyStore` | `java.security.KeyStore` | Store for certificates/public trust anchors or private key entries depending on purpose |
| `HostnameVerifier` | `javax.net.ssl.HostnameVerifier` | Interface deciding whether a hostname matches the TLS peer session when hostname checking needs an additional call |
| `SSLSession` | `javax.net.ssl.SSLSession` | Information about the established TLS session (peer, cipher/protocol, session) |

**Two different security questions:**

- **"Do I trust this certificate/chain?"** → TrustManager/PKIX trust path, CA/trust anchor, validity period, signature, key usage, constraints…
- **"Does that trusted certificate belong to the exact service I want to call?"** → HTTPS hostname identity check matching the URL host against the identity in the certificate, prioritizing the matching SAN type.

Answering only the **first question** is not enough. Conversely, a certificate with the exact name but issued by an untrusted CA is also not enough for a secure connection to be accepted.

## 3. How Does `HttpsURLConnection` Differ from `HttpURLConnection`?

For a standard HTTPS URL, Java returns a concrete `HttpsURLConnection` from `openConnection()`. It **inherits** HTTP/URLConnection methods such as `setRequestMethod`, `getResponseCode`, `getInputStream`, `getErrorStream`, `setConnectTimeout`, `setReadTimeout`, and `disconnect`.

Additions for HTTPS include:

- `setSSLSocketFactory(SSLSocketFactory)` / `getSSLSocketFactory()`: per-instance factory.
- `setHostnameVerifier(HostnameVerifier)` / `getHostnameVerifier()`: per-instance verifier, when controlled customization is genuinely needed.
- `getCipherSuite()`: the cipher suite used.
- `getServerCertificates()`, `getPeerPrincipal()`: peer identity/certificates of the TLS connection.
- `getSSLSession()`: Optional of the session (Java 17).
- `getDefaultSSLSocketFactory()` / `setDefaultSSLSocketFactory(...)` and the **static** default hostname verifier methods: default configuration for new instances; class/JVM-wide scope, easily causing unintended side effects.

### Configure Before Opening the Connection

Minimal pattern:

```java
// Illustrative snippet, 'factory' must be created securely from SSLContext.
HttpsURLConnection conn = (HttpsURLConnection)
        new URL("https://api.example.test/data").openConnection();
conn.setSSLSocketFactory(factory);
conn.setConnectTimeout(3000);
conn.setReadTimeout(3000);
conn.setRequestMethod("GET");

// getResponseCode() may trigger the actual TLS/HTTP connection.
int status = conn.getResponseCode();
```

`setSSLSocketFactory`, timeouts, method, headers, and redirect policy must be set **before the connection actually occurs**. `getResponseCode()` or `getInputStream()` may trigger an implicit `connect()`. Do not set a hostname verifier/factory after the request has already been sent and expect it to apply retroactively.

**Do not blindly cast HTTP URLs:** `new URL("http://...").openConnection()` is not an `HttpsURLConnection`; casting it will throw `ClassCastException`. Check that the scheme is `https` when secure transport is required.

## 4. TLS Handshake and Server Identity Verification

An HTTPS request can follow this general flow:

```mermaid
sequenceDiagram
  participant App as Java application
  participant Conn as HttpsURLConnection / JSSE
  participant TLS as HTTPS server
  App->>Conn: openConnection; setSSLSocketFactory
  App->>Conn: getResponseCode / getInputStream
  Conn->>TLS: TCP + TLS ClientHello (possibly with SNI)
  TLS-->>Conn: TLS handshake + server certificate
  Conn->>Conn: Verify trust chain / PKIX policy
  Conn->>Conn: Verify hostname from URL vs certificate SAN
  alt Both trust and hostname are valid
    Conn->>TLS: Encrypted HTTP request
    TLS-->>Conn: Encrypted HTTP response
    Conn-->>App: status + headers + body
  else Trust or identity fails
    Conn-->>App: SSLHandshakeException / SSLException
  end
```

In practice, some steps may happen during the TLS handshake while others are performed next by the HTTP/TLS adapter. The exact implementation order depends on the provider/JDK; the **invariant security expectation** is that the application must not treat the HTTPS peer as the right server until **both trust and service identity** are properly verified.

**TLS is different from HTTP status:** if the TLS handshake fails, there may be no valid HTTP request/response yet. You must not assume `getResponseCode()==401`, `403`, or `500` represents a "certificate error". Server authentication errors belong to the TLS/`IOException` layer.

### Do Not Confuse Hostname, DNS/IP, SNI, Certificate CN, and SAN

- **Hostname in URL**: the name the application expects to communicate with, e.g., `api.example.test`.
- **DNS resolution**: finding one or more IP addresses to connect to; multiple hostnames can point to the same IP.
- **SNI (Server Name Indication)**: a TLS extension allowing the client to send the desired server name so the server can select the certificate/config; **it does not replace identity verification by itself**.
- **Certificate Subject CN**: the legacy subject name field; **CN should not be used as the sole source instead of SAN**.
- **Subject Alternative Name (SAN)**: where multiple DNS and IP identities of a service are declared in modern certificates.

One IP can serve many HTTPS sites. Having connected to the right IP **does not prove** the certificate is right for the hostname you requested.

## 5. What Does `SSLSocketFactory` Do?

`SSLSocketFactory` creates `SSLSocket` instances with TLS settings from the provider/`SSLContext`. A factory can carry a non-default trust policy, a key manager for client certificates, socket creation behavior, and supported TLS configurations.

Safe construction pattern:

```text
Truststore with trusted public CA/certificate
   -> KeyStore.load(...)
   -> TrustManagerFactory.init(trustStore)
   -> SSLContext.getInstance("TLS")
   -> SSLContext.init(null, trustManagers, SecureRandom)
   -> SSLContext.getSocketFactory()
   -> HttpsURLConnection.setSSLSocketFactory(factory)
```

Specifying a custom truststore **does not require disabling hostname checking**. You can trust a self-signed server certificate **for a test environment**, but if the URL host does not match the SAN it must still be rejected.

### The Difference Between "Trust Certificate" and "Trust-All"

**Specific trust:** the truststore contains a specific public certificate or internal CA. `TrustManagerFactory` uses this trust material to validate the certificate path. For test environments, trusting a specific self-signed certificate is reasonable if the source is properly controlled.

**Trust-all:** creating an `X509TrustManager` with an empty `checkServerTrusted(...)`, or a factory that accepts every certificate. This is a **serious anti-pattern**: connections become vulnerable to man-in-the-middle attacks, even if the URL looks like HTTPS. This lesson **does not** provide trust-all code.

### Why Not Modify the Global Default?

`HttpsURLConnection.setDefaultSSLSocketFactory(...)` is a static method affecting **new instances** that use the class default, which can affect other libraries in the same JVM. Changing the global default hostname verifier is even more dangerous. When you only need to call a specific API/truststore, use:

```java
conn.setSSLSocketFactory(context.getSocketFactory());
```

on the **specific connection**, avoiding breaking the trust policy of unrelated HTTPS connections. Instances created before a default change do not automatically adopt the new configuration.

## 6. Truststore and Keystore: Same API, Different Purposes

In Java, both can use `KeyStore`, but their contents and roles differ:

| Material | What Does It Contain? | Used By | Used For What? |
|---|---|---|---|
| **Server keystore** | Server private key + certificate chain | HTTPS server's `KeyManagerFactory` | Server proves it possesses the private key for the certificate |
| **Client truststore** | Public CA certificate or trusted certificate | Client's `TrustManagerFactory` | Client validates the server's certificate chain |
| **Client keystore** (when mTLS) | Client private key + certificate chain | HTTPS client's `KeyManagerFactory` | Client presents its own identity if requested by the server |
| **Server truststore** (when mTLS) | Accepted client CA/certificate | Server-side trust manager | Server validates the client certificate |

**Do not copy the server's private key to the client** just so the client trusts the certificate. In the demo, we run `keytool -exportcert` to extract the **public certificate**, then `-importcert` into a **separate truststore**. `server.p12` remains exclusively on the server side and contains the private key.

### PKCS12 and JKS

`KeyStore.getInstance("PKCS12")` reads the common PKCS #12 format, which can contain private key/certificate entries. JKS is the traditional Java format; do not rely on the default store type without checking, especially when running across different JDK versions.

Example of reading a truststore in a scoped manner:

```java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(trustPath)) {
    trust.load(input, passwordChars);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), new SecureRandom());
SSLSocketFactory factory = context.getSocketFactory();
```

The illustrative snippet imports `java.security.KeyStore`, `java.security.SecureRandom`, `java.nio.file.Files`, `java.nio.file.Path`, `java.io.InputStream`, and `javax.net.ssl.*`. This is a **new truststore-only** configuration in the example; it does not automatically merge with all system trusted roots. If you need to keep default CAs while also trusting a private CA, design explicit trust material/policy rather than dropping or bypassing trust checks.

## 7. Hostname Verification: DNS SAN and IP SAN

Suppose a certificate only has:

```text
Subject: CN=localhost
X509v3 Subject Alternative Name:
    DNS:localhost
```

Expected behavior:

| URL | Reference Identity | Certificate SAN | Result |
|---|---|---|---|
| `https://localhost:8443` | DNS name `localhost` | `DNS:localhost` | **Can match** if trust and other TLS checks are valid |
| `https://127.0.0.1:8443` | IP address `127.0.0.1` | Only `DNS:localhost` | **Does not match**, rejected |
| `https://api.example.test` | DNS `api.example.test` | `DNS:localhost` | **Does not match** |
| `https://foo.example.test` | DNS `foo.example.test` | `DNS:*.example.test` if present | Depends on safe wildcard rules and policy |
| `https://[::1]:8443` | IPv6 literal `::1` | No `IP:::1` | **Does not match** |

**Operational rule:** if the client actually accesses via IP, the certificate must have the corresponding **iPAddress SAN** (for example, `IP:127.0.0.1`); `DNS:localhost` is not a wildcard for an IP and vice versa. DNS resolving `localhost` to `127.0.0.1` does not turn an IP URL host into a DNS host.

The right approach when a certificate does not match:

- Use the **exact hostname** authorized by the certificate with appropriate DNS/routing.
- Or **reissue the certificate** with the right SAN for the official hostname/IP.
- Check whether a load balancer/proxy is presenting the certificate corresponding to SNI.
- Do not change `HostnameVerifier` to always return true as a "quick fix" for the error.

RFC 9525 (Service Identity in TLS, 2023) describes modern methods for verifying service identity, in which DNS names and IPs must be checked according to the appropriate identifier type. JDK 17 has its own HTTPS hostname checking implementation per API, so do not assume every detail of a later RFC is applied identically in JDK 17; applications should keep default security configurations and test with real certificates and provider policies.

### Hostname Is Not the HTTP Host Header

A request may carry a `Host` or `:authority` header in HTTP depending on the version, but this **is not a bypass switch for TLS verification**. Changing the `Host` header while still connecting to a different URL can create unpredictable routing situations or security flaws. The reference identity should be tied to the actual URL/endpoint and client policy, and must not be arbitrarily replaced with an untrusted name from a response.

## 8. `HostnameVerifier`: When Is It Needed, and When Must It Be Avoided?

The `HostnameVerifier` interface has one method:

```java
boolean verify(String hostname, SSLSession session);
```

Java documentation describes that the verifier may be called when the default hostname verification rules **cannot determine an acceptable match**. `hostname` is the name to verify; `session` is the corresponding TLS session. The verifier returns `true` if the hostname is accepted, `false` otherwise.

**Recommendation:** in most applications, **do not override** the verifier. `HttpsURLConnection` has built-in logic to verify the host in the URL against the certificate. When you need to change trust anchors, only replace `SSLSocketFactory` (using a proper `TrustManagerFactory`), and **keep default hostname checking**.

### Dangerous Anti-Pattern

A `HostnameVerifier` with "always return true" logic allows a URL like `https://bank.example` to be accepted when the peer presents a certificate for another host. Combined with trust-all, this strips HTTPS of most of its MITM protection. **Do not use it, not even in sample code that might get copied into production**.

Similarly, do not call `HttpsURLConnection.setDefaultHostnameVerifier(...)` with a permissive verifier: this is a broad change that can cause other HTTP clients in the JVM to accept wrong hostnames.

### Controlled Custom Verifier Cases

A special legacy environment might have a carefully designed/audited additional identity mechanism; in that case, a custom verifier must handle the hostname, session, certificate chain, and specific policy. However, changing the default mechanism requires a threat model, unit/integration tests, security review, and an exception retirement plan. **Do not use a custom verifier just because a cert is self-signed**: self-signed is a **truststore** issue, whereas a hostname mismatch is an **identity** issue.

### Is Calling the Default Verifier Logic Manually Enough?

You should not write an ad-hoc check based solely on `getPeerPrincipal().getName()` or `CN` and then wave the certificate through. Signatures and trust chain, SAN, hostname, EKU, and many other policies must be handled properly by the JSSE/HTTPS verifier. Using the safe default HTTPS stack is far more reliable than coding regex matches on a certificate subject.

## 9. Complete Java 17 Demo: Loopback HTTPS, Custom Truststore, Mismatch Rejected

This example **runs on JDK 17** and uses only built-in JDK modules `java.base` and `jdk.httpserver`:

- `keytool` generates a **demo RSA certificate** with `SAN=DNS:localhost` and server keystore `server.p12`.
- Exports the **public certificate** to `server.crt`, and imports it into `trust.p12` as a truststore solely for the demo client.
- Starts a loopback HTTPS server using `com.sun.net.httpserver.HttpsServer`.
- Creates a client `SSLContext` with `TrustManagerFactory` reading `trust.p12`.
- Opens two `HttpsURLConnection` instances using the **same custom SSLSocketFactory**, without disabling default hostname verification.
- `https://localhost:port/hello` succeeds with HTTP 200 and body `HTTPS OK`.
- `https://127.0.0.1:port/hello` is rejected because the certificate **only has a DNS SAN**, no IP SAN.
- The program self-checks expectations and throws an error if a response/hostname policy deviates.

This is a **test/demo**, not a public HTTPS service. The password `changeit` is only for a temporary keystore created on a learning machine and is **not** a production secret choice.

### 9.1. Creating the Keystore and Truststore with keytool

Run in **a dedicated test directory**. The commands below are written on single lines for easy use in both Bash and PowerShell (assuming `keytool` from the JDK is in `PATH`):

```bash
keytool -genkeypair -alias localhost-demo -keyalg RSA -keysize 2048 -validity 2 -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -dname "CN=localhost, OU=Demo, O=Example, C=VN" -ext "SAN=DNS:localhost" -noprompt

keytool -exportcert -alias localhost-demo -keystore server.p12 -storetype PKCS12 -storepass changeit -file server.crt

keytool -importcert -alias localhost-demo -file server.crt -keystore trust.p12 -storetype PKCS12 -storepass changeit -noprompt
```

**What this means:**

1. `-genkeypair` generates a private key + self-signed certificate into `server.p12` (demo password).
2. `-ext SAN=DNS:localhost` writes the crucial **DNS SAN** into the certificate. `CN=localhost` in Subject does not replace SAN.
3. `-exportcert` exports the public certificate, **not the private key**.
4. `-importcert` places the public certificate into `trust.p12`; the client has a specific trust anchor.
5. The certificate is valid for only 2 days because it is for a lab exercise; running after expiration requires **regenerating the keystore/truststore**. For real systems, use a CA/PKI and proper rotation.
6. Do not commit `server.p12` or passwords to Git; delete demo artifacts after running.

### 9.2. Complete Code: HttpsHostnameDemo.java

```java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

public class HttpsHostnameDemo {
    private static KeyStore loadStore(Path path, char[] password)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, password);
        }
        return store;
    }

    private static SSLContext serverContext(
            Path keyStorePath, char[] password) throws Exception {
        KeyStore keys = loadStore(keyStorePath, password);
        KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keyManagers.init(keys, password);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keyManagers.getKeyManagers(), null,
                new SecureRandom());
        return context;
    }

    private static SSLSocketFactory clientFactory(
            Path trustStorePath, char[] password) throws Exception {
        KeyStore trust = loadStore(trustStorePath, password);
        TrustManagerFactory trustManagers =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
        trustManagers.init(trust);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, trustManagers.getTrustManagers(),
                new SecureRandom());
        return context.getSocketFactory();
    }

    private static HttpsURLConnection connection(
            String address, SSLSocketFactory factory)
            throws IOException {
        HttpsURLConnection conn = (HttpsURLConnection)
                new URL(address).openConnection(Proxy.NO_PROXY);
        conn.setSSLSocketFactory(factory);
        // Keep the JDK's default HostnameVerifier.
        conn.setConnectTimeout(3000);
        conn.setReadTimeout(3000);
        conn.setInstanceFollowRedirects(false);
        return conn;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: HttpsHostnameDemo server.p12 trust.p12 password");
        }
        char[] password = args[2].toCharArray();
        SSLContext tlsServer = serverContext(
                Path.of(args[0]), password);
        SSLSocketFactory tlsClient = clientFactory(
                Path.of(args[1]), password);

        HttpsServer server = HttpsServer.create(
                new InetSocketAddress(
                        InetAddress.getByAddress(
                                new byte[] {127, 0, 0, 1}), 0), 0);
        server.setHttpsConfigurator(
                new HttpsConfigurator(tlsServer));
        server.createContext("/hello", exchange -> {
            byte[] body = "HTTPS OK".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
            exchange.close();
        });
        server.start();

        try {
            int port = server.getAddress().getPort();
            HttpsURLConnection good = connection(
                    "https://localhost:" + port + "/hello",
                    tlsClient);
            try {
                int status = good.getResponseCode();
                boolean peerSubjectHasLocalhost =
                        good.getPeerPrincipal().getName()
                                .contains("CN=localhost");
                String result;
                try (InputStream in = good.getInputStream()) {
                    result = new String(
                            in.readAllBytes(), StandardCharsets.UTF_8);
                }
                if (status != 200 || !"HTTPS OK".equals(result)) {
                    throw new IllegalStateException(
                            "Unexpected HTTPS response");
                }
                System.out.println("Trusted localhost: " + status);
                System.out.println("Response body: " + result);
                System.out.println("Peer subject contains localhost: "
                        + peerSubjectHasLocalhost);
            } finally {
                good.disconnect();
            }

            HttpsURLConnection wrongName = connection(
                    "https://127.0.0.1:" + port + "/hello",
                    tlsClient);
            boolean rejected = false;
            try {
                wrongName.getResponseCode();
            } catch (SSLException expected) {
                rejected = true;
            } finally {
                wrongName.disconnect();
            }
            if (!rejected) {
                throw new IllegalStateException(
                        "IP mismatch was not rejected");
            }
            System.out.println("IP hostname mismatch rejected: true");
        } finally {
            server.stop(0);
        }
    }
}
```

### 9.3. Compile and Run

In the same directory containing the Java source and the two generated `.p12` files:

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 HttpsHostnameDemo.java
java --add-modules jdk.httpserver HttpsHostnameDemo server.p12 trust.p12 changeit
```

The `jdk.httpserver` module needs to be added to use the JDK's built-in HTTPS server; `HttpsURLConnection`, JSSE, and certificate classes are in `java.base`. The `HttpsURLConnection` client itself **does not need** `jdk.httpserver` if a real application does not host its own server.

**Exact stdout when running successfully with JDK 17 and loopback sockets permitted:**

```text
Trusted localhost: 200
Response body: HTTPS OK
Peer subject contains localhost: true
IP hostname mismatch rejected: true
```

`keytool` may print its own messages when creating/exporting certificates; the four lines above are the **stdout of the Java program**, excluding keytool output.

### 9.4. Why Does the Demo Use Separate Files?

`server.p12`: contains the **private key and server certificate**. `KeyManagerFactory` uses it so the HTTPS server can present its identity.

`server.crt`: **public certificate**, carrying no private key.

`trust.p12`: truststore solely for the demo client. `TrustManagerFactory` reads the imported certificate to verify the peer server. This is trusting a specific certificate, **not bypassing PKIX checks**.

`SSLContext.getInstance("TLS")` uses the provider to select TLS versions/protocols enabled by the runtime policy; it does not hardcode legacy SSLv3/TLSv1.0. Do not infer that the name `"TLS"` forces only TLS 1.3. For real operations, manage JDK security updates and protocols/cipher suites according to policy.

### 9.5. Why Is the IP URL Still Rejected When the Certificate Is Trusted?

The certificate is imported into the truststore: the trust path is satisfied for both connections. However, the second connection requires **reference identity = 127.0.0.1**, whereas the certificate only declares **DNS SAN localhost**. Therefore, default HTTPS hostname verification rejects treating that certificate as the identity of the IP URL.

This is what the lesson aims to prove: **a valid truststore does not mean every hostname is valid**.

### 9.6. `getPeerPrincipal()` in the Example Is Only for Observation

The line `Peer subject contains localhost: true` reads `getPeerPrincipal().getName()` after the TLS connection succeeds and before closing the response stream. It helps observe part of the subject, but **is not the primary hostname check** and **does not replace SAN verification**. Secure hostname checking is performed by the JDK HTTPS stack.

When debugging, call `getPeerPrincipal()`/`getCipherSuite()` **after the connection has been established and is still valid**. These methods may throw `IllegalStateException` if not yet connected, or if the session/resource is no longer accessible in the current state. Do not extract the CN string and decide on your own to allow the connection.

### 9.7. Why Use `openConnection(Proxy.NO_PROXY)`?

The demo intentionally connects to loopback **directly** so it does not depend on environment proxies; `Proxy.NO_PROXY` only directs the test connection directly. Production may require an egress proxy: **do not blindly copy `Proxy.NO_PROXY`** to bypass corporate policy. When using an HTTPS proxy, CONNECT, TLS trust, and hostname verification still need to be handled properly.

### 9.8. Honest Limitations

- The server exists only in-JVM and uses a self-signed certificate with a very short validity period; there is no public CA, mTLS, application authentication, rate limiting, or database.
- There is no HTTP load balancer, proxy, redirect, or other hostname outside loopback; it only tests one truststore and one specific mismatch.
- The test assumes `localhost` can reach the IPv4 loopback server on the host machine. Environments that disallow sockets or have altered `localhost`/firewall mappings may cause network errors; that is **not** evidence that hostname verification is disabled.
- TLS errors may have different specific messages across providers/JDK versions; the program only checks the **`SSLException` type** for the mismatched name case, without hardcoding implementation-dependent exception messages.
- Self-signed certificates should only be used in controlled labs/tests. Do not commit private keys, real truststore passwords, or untrusted certificates to repositories or public chats.

## 10. Real HTTPS Connections with URLConnection: Proper Lifecycle Pattern

For a managed endpoint, building the client factory can be separated from business code. The following call pattern illustrates how to use `HttpsURLConnection` **once you already have** an `SSLSocketFactory secureFactory` created from a proper truststore:

```java
// Illustrative inside a method that may throw IOException; not standalone.
URL url = new URL("https://api.example.test/data");
HttpsURLConnection conn =
        (HttpsURLConnection) url.openConnection();
conn.setSSLSocketFactory(secureFactory);
conn.setConnectTimeout(3000);
conn.setReadTimeout(5000);
conn.setInstanceFollowRedirects(false);
conn.setRequestMethod("GET");
conn.setRequestProperty("Accept", "application/json");

try {
    int status = conn.getResponseCode();
    InputStream stream = status >= 400
            ? conn.getErrorStream()
            : conn.getInputStream();

    if (stream != null) {
        try (InputStream in = stream) {
            // Read according to quota/charset/schema defined by the application.
        }
    }

    // Process status, headers, and specific business result.
} finally {
    conn.disconnect();
}
```

**Details to understand:**

- `getResponseCode()` may connect/handshake automatically; therefore configure the factory, timeouts, redirects, and headers **before** this call.
- `getInputStream()` may throw `IOException` for HTTP error responses; if the server returned an HTTP error, you can read `getErrorStream()` to get the error body (which may be `null`), whereas a TLS error **does not necessarily have an HTTP error stream**.
- `getErrorStream()` is not an option for "catching certificate errors"; certificate errors occur before a valid response exists.
- `disconnect()` tells the runtime the connection is no longer needed; it does not replace closing input/output streams, and HTTP keep-alive/reuse depends on the implementation.
- For large bodies, size/time budgets and streaming are required; `readAllBytes()` in the demo applies only to small fixed bodies. Do not buffer gigabyte responses from untrusted URLs into RAM.
- `setInstanceFollowRedirects(false)` prevents the client from automatically following to another target URL. When redirects are allowed, hostname/trust must be evaluated for **each actual target**, avoiding leaking tokens/credentials to an untrusted host.

### Should the Same SSLSocketFactory Be Used for Multiple Connections?

A securely created factory can be reused for connections sharing the same trust/security policy; there is no need to reload the truststore and initialize `SSLContext` on every request. However, dynamic truststore changes, certificate expiration, or CA rotation may require recreating the context/factory according to policy and observing existing connections. Do not rely on editing a `.p12` file on disk for all open TLS connections to automatically update their configuration.

## 11. Timeouts, TLS Errors, and HTTP Status Are Three Different Observations

An HTTPS system has multiple failure points:

| Stage | Error Example | Possible Java Result | Handling Direction |
|---|---|---|---|
| URL validation | Wrong scheme, malformed URI | `MalformedURLException`, `ClassCastException` if cast wrongly | Validate URL/host/scheme first |
| DNS/route | Cannot resolve hostname | `UnknownHostException` | Check DNS/VPN/proxy |
| TCP connect | No service at host:port | `ConnectException`, timeout | Check endpoint/firewall/port |
| TLS trust | Untrusted self-signed certificate, chain does not reach root | `SSLHandshakeException` often with `PKIX path building failed` in cause | Configure CA/truststore properly, no trust-all |
| TLS identity | SAN does not contain URL hostname/IP | `SSLHandshakeException`/`SSLException` with hostname mismatch message | Use the right name or reissue SAN cert |
| TLS protocol | Version/cipher mismatch, handshake alert | `SSLHandshakeException` | Check JDK/protocol/cipher policy |
| TLS certificate validity | Expired/not yet valid, CA constraints, EKU | `SSLHandshakeException` or PKIX validation cause | Reissue certificate, sync clock, fix chain |
| HTTP status | Server returns 401/403/404/500 | `getResponseCode()` returns status or `getInputStream()` throws | Handle status and error stream per API contract |
| App parsing | JSON schema mismatch, charset mismatch | Parser/application error | Validate media type, schema, data |
| Timeout after send | Lost response or slow server processing | `SocketTimeoutException`/`IOException` | Outcome may be unknown; apply retry/idempotency per method |

**Important:** do not treat every `SSLHandshakeException` as "wrong hostname". It could be due to the trust chain, certificate dates, TLS protocol/cipher, client authentication, or algorithm policy. Log the class and **cause** with redaction, and inspect `javax.net.debug=ssl,handshake` in an isolated test environment when needed; do not enable TLS debug indiscriminately in production because logs can contain sensitive metadata.

### Connect Timeout Is Not a Total Deadline

`setConnectTimeout(ms)` primarily controls the wait limit for establishing the connection; `setReadTimeout(ms)` controls blocking reads per `URLConnection` expectations. They **do not replace** a deadline for the entire DNS/TLS/HTTP/parse/retry workflow. A response stream can trickle data just fast enough that no individual read times out while the total duration becomes huge. Production needs total time/byte limits and proper lifecycle cancellation.

### When a Connection Fails Mid-POST/PUT, Do Not Blindly Retry

A TLS/transport error after starting to send a request does not prove the server did not execute the business action. For payment POSTs, an idempotency key/reconciliation must be used. For GET/HEAD or PUT/DELETE with idempotent semantics, a retry policy with budget, timeout, and actual verification is still required; do not treat "using HTTPS" as an exactly-once guarantee.

## 12. SAN, Wildcard, IP, and Certificates Across Multiple Environments

### Accessing by Issued DNS Name

The application requests `https://billing.internal.example`, the certificate contains `DNS:billing.internal.example`, the trust path is valid, and TLS policy is right → hostname validation can succeed.

### Accessing Directly by IP

`https://10.0.2.15` requires a certificate with `iPAddress SAN=10.0.2.15` per policy; a certificate with only `DNS:billing.internal.example` will not be automatically accepted just because DNS for that name returns `10.0.2.15`.

Whenever possible, **use a stable DNS name** in the URL and configure valid DNS/routing; avoid calling services by IP and then altering the verifier to ignore the mismatch. If an IP must be used, issue a certificate with an IP SAN and test it.

### Wildcard Certificates

A certificate such as `DNS:*.example.com` has restricted matching rules; do not treat it as matching every subdomain at any depth or the apex domain. Verify specific names according to standards/policy. Do not write a `.*example.com` regex to replace the JDK verifier yourself.

### TLS Termination / Load Balancer

If a client calls `https://api.example.com` through a load balancer, the certificate at the **TLS termination endpoint seen by the client** must match `api.example.com`. The certificate between the load balancer and the backend is a separate TLS connection with its own trust/hostname policy. A correct backend certificate does not make a wrong frontend certificate valid.

### SNI and Multiple Certificates on One IP

A server may choose a certificate based on SNI in the TLS ClientHello; a client using an IP literal instead of a hostname can affect SNI and cause the server to return an incorrect default certificate. **Do not diagnose every mismatch as a truststore error**: check the URL hostname, SNI, SAN, routing, the certificate chain actually presented by the peer, and proxy configuration.

## 13. Custom HostnameVerifier, Pinning, and Truststore Rotation

### Hostname Verifier Is Not a Trust Manager

`setHostnameVerifier(...)` changes the verification policy for the **hostname in the TLS session** for a specific connection; it is not an API to import CAs or solve PKIX errors. `setSSLSocketFactory(...)` changes the TLS factory/trust/key configuration for the connection. The two must be considered independently.

| Goal | Appropriate Path | What Not to Do |
|---|---|---|
| Trust an internal CA | Add the right CA to the truststore and use `TrustManagerFactory` | Always-true verifier |
| Trust a self-signed certificate in a lab | Import the public cert into a separate truststore | TrustManager skipping all certificate checks |
| Hostname does not match SAN | Call the right host or reissue cert with matching SAN | Disable hostname verification |
| Implement mTLS | `KeyManagerFactory` for client identity + `TrustManagerFactory` for server trust | Copy server private key to client machine |
| Rotate certificates periodically | CA/rotation policy, truststore rollover, testing | Hardcode 1 fingerprint forever with no plan |
| Special TLS certificate pinning | Pin public key/certificate under security review and rotation | Regex CN or skip PKIX checks |

### Certificate Pinning Does Not Automatically Solve Hostname

Pinning is a policy binding a certificate/public key to a service. When pinning, you should still maintain proper **trust path and hostname verification**, unless an equivalent alternative design has been verified by experts. A pinned cert/key used for the wrong host can still violate service identity; review the full security architecture.

### Rotation

If an internal CA or certificate is renewed, a truststore containing only a single leaf certificate may stop working; use appropriate CA trust and prepare a rollover if possible. Set expiration alerts, update trust material through a defined process, and test before deployment. Do not "put out fires" by disabling chain/hostname verification.

### Passwords & Secrets

In the demo, `changeit` is a public example password with **no protective value**. In production, store secrets in a secret manager/keystore ACL, do not log passwords, do not hardcode them in source code, and do not commit private keys. Use `char[]` when APIs support it and clear memory appropriately, even though Java does not guarantee immediate removal of all secret copies.

## 14. Things About TLS That SSLSocketFactory Does Not Solve on Its Own

Choosing a valid `SSLSocketFactory` is a **configuration prerequisite**, not a guarantee of complete system operational security:

1. **Authorization**: an HTTPS server with a valid certificate can still return data to the wrong user if tokens/scopes are not checked.
2. **Cookie/session policy**: HTTPS does not automatically guarantee CSRF protection or Secure/HttpOnly/SameSite cookies.
3. **Redirect policy**: an HTTP redirect can lead to a different host/scheme; the client must evaluate credential leakage and new trust.
4. **SSRF**: user-supplied URLs can point to internal networks/metadata IPs. HTTPS and truststores do not replace URL allowlists, DNS/IP checks, and egress firewalls.
5. **Proxy**: an HTTPS connection may go through an HTTP CONNECT tunnel; proxy auth/routing is not handled by `SSLSocketFactory`.
6. **Response validation**: TLS protects the channel and peer identity; it does not guarantee schema-valid JSON, safe files, or business success.
7. **HTTP status**: `200` does not mean downstream side effects have completed; `202` may only mean accepted.
8. **Logging**: `javax.net.debug` and certificate/session dumps can contain sensitive metadata; enable debug only for as long as needed.
9. **Protocol policy**: `SSLContext.getInstance("TLS")` uses protocols allowed by the provider/JDK; keep the JDK and policies disabling weak algorithms updated.
10. **Connection pooling**: keep-alive/reuse may retain sockets or sessions depending on the implementation; updating policy does not automatically revoke all active connections.

## 15. Common Mistakes: Symptoms and Fixes

| Mistake | Consequence | Right Approach |
|---|---|---|
| Creating a truststore then disabling hostname verifier | May accept a certificate for another host | Keep default hostname verification |
| Writing a TrustManager that accepts all certs | Vulnerable to MITM because chain is not checked | Trust specific CA/cert in KeyStore |
| Verifier always returning `true` to "fix SSL" | Ignores URL host identity | Fix URL or certificate SAN |
| Assuming right IP means right hostname | Multiple hosts share one IP; different reference identity | Match URL hostname/IP with matching SAN type |
| Believing only `CN=localhost` is enough | Ignores SAN and modern rules | Issue proper SAN and let JSSE verify |
| Calling `https://127.0.0.1` with cert `DNS:localhost` | IP does not match DNS SAN | Use `localhost` or add IP SAN |
| Treating `getPeerPrincipal().getName()` as full verification | Subject CN does not replace chain/SAN verification | Use JDK HTTPS default policy |
| Treating `SSLSocketFactory` as `HostnameVerifier` | Confuses trust/transport with identity | Separate truststore and hostname check |
| Changing `setDefaultSSLSocketFactory` JVM-wide | Affects unrelated connections | Use `conn.setSSLSocketFactory` per instance |
| Changing `setDefaultHostnameVerifier` JVM-wide | Risks breaking security of multiple libraries | Do not override global verifier |
| Configuring factory after `getResponseCode()` | Connection already initialized, setting is too late | Set before connect/implicit connect |
| Casting `http://` URL to `HttpsURLConnection` | `ClassCastException` | Check HTTPS scheme |
| Assuming SSL handshake failure is HTTP 500 | No HTTP response exists when TLS fails | Catch `SSLException`/`IOException` separately |
| Using `getInputStream` for HTTP 4xx without checking error | May get IOException, lose error body | `getResponseCode` + `getErrorStream` |
| Forgetting to close response stream | Holds resources/connections | `try-with-resources` + `disconnect` |
| Treating `disconnect` as a replacement for closing stream | May not release as expected | Close stream first, `disconnect` in `finally` |
| Blindly adding `Proxy.NO_PROXY` in production | Bypasses egress policy | Use approved proxy/policy |
| Trusting self-signed certificates outside lab without review | Fake trust, no rotation | Managed internal CA/PKI |
| Committing server keystore/private key | Leaks key to attackers | Keep out of source, use ACLs and secret manager |
| Printing password/Authorization in logs | Secret leakage | Redact and limit diagnostics |
| Setting timeout = 0 thinking it is bounded | 0 usually means wait indefinitely | Positive timeouts and total deadline |
| Limiting only `connectTimeout` | Read/TLS/other logic can still hang | Set `readTimeout` and full-workflow budget |
| Unconditionally retrying POST after TLS/socket timeout | May create duplicate side effects | Idempotency key/reconciliation |
| Thinking a factory automatically reloads truststore on disk | Uses old trust material | Manage `SSLContext`/factory lifecycle |
| Using `"TLSv1.0"` string for "compatibility" | Accidentally enables old/weak algorithms | Follow current JDK protocol policy |
| Confusing frontend/backend certificates at load balancer | Fixing wrong truststore or host | Check TLS termination certificate at the right hop |
| Passing host name from query into verifier | Host spoofing/SSRF/authority confusion | Rely on validated URI and SAN checks |

## 16. Real-World Scenarios: Distinguishing Four Similar-Looking Error Groups

### A. PKIX Chain Errors

`javax.net.ssl.SSLHandshakeException` with a cause related to `SunCertPathBuilderException` or `ValidatorException`, for example, no trusted certificate path found. Check whether the server sends the full chain, root/intermediate CAs, which truststore is actually used, certificate expiry, and policy. **Do not disable hostname checking to fix PKIX**.

### B. Hostname Mismatch

The trust chain may be valid, but the error involves the URL hostname vs. certificate SAN. Check `new URL(...).getHost()`, certificate DNS/IP SANs, SNI, and the load balancer. Do not try to fix it by importing that same certificate into the truststore again if the problem is a **wrong name**.

### C. Connection Refused

`ConnectException: Connection refused` occurs before a TLS handshake can succeed. Check host/port/service binding, firewall, and proxy/VPN. Editing the truststore will not make a stopped TCP endpoint start listening.

### D. HTTP 403/404

If TLS has succeeded, the HTTP server may return `403` or `404` according to access policy/resource. This is an HTTP result, not proof of a wrong SSL config. Use `getResponseCode`/`getErrorStream` and the application contract to handle it; do not retry or change the verifier for these statuses.

**Ordered debugging:** URL scheme/host → DNS/IP/port/proxy → TLS certificate chain → hostname SAN → HTTP status/headers/body → business semantics. This isolates the right layer instead of changing every SSL setting at once.

## 17. Exercises and Self-Check Questions

**Question 1.** Can `HttpsURLConnection` be used with a custom truststore without disabling hostname verification?

**Answer:** Yes. Create an `SSLContext` from a `TrustManagerFactory` using the custom truststore, get its `SSLSocketFactory`, and call `conn.setSSLSocketFactory(factory)`. Keep the default verifier.

**Question 2.** A certificate has `DNS:localhost`, and the client uses `https://127.0.0.1`. Why can it be rejected even though both point to loopback?

**Answer:** The URL requests the **IP** identity `127.0.0.1`, while the certificate only declares **DNS SAN localhost**. Having the same network address does not make the two reference identities equal.

**Question 3.** If you want to use the URL `https://127.0.0.1` for a lab, what is needed?

**Answer:** A certificate with `iPAddress SAN=127.0.0.1`, a valid trust path, and an appropriate TLS policy. Do not use an always-true verifier.

**Question 4.** Do `TrustManagerFactory` and `HostnameVerifier` have the same responsibility?

**Answer:** No. The trust manager checks the certificate trust path/policy; hostname verification checks whether the server identity matches the URL host. Both are necessary.

**Question 5.** Is calling `conn.setSSLSocketFactory(...)` after `conn.getResponseCode()` valid?

**Answer:** It is not the right way to configure it: `getResponseCode()` may have already established the connection. The factory must be set before starting the connection.

**Question 6.** What scope does `HttpsURLConnection.setDefaultSSLSocketFactory(...)` affect?

**Answer:** Static default for new instances of the class, not just the current connection. In libraries sharing a JVM, avoid global changes and prefer per-instance configuration.

**Question 7.** Why does the example export `server.crt` and import it into `trust.p12` instead of copying `server.p12` to the client?

**Answer:** `server.p12` contains the **server private key**, whereas the client only needs the **public certificate/CA trust** to verify; the private key must not be leaked.

**Question 8.** `getPeerPrincipal().getName()` contains `CN=localhost`. Does that prove the certificate matches `https://localhost`?

**Answer:** No. That is only subject information; hostname verification should rely on SAN and the HTTPS verifier's policy, combined with trust chain verification.

**Question 9.** When a TLS handshake fails, are you guaranteed to receive HTTP `500`?

**Answer:** No. A TLS failure may prevent the client from ever receiving a valid HTTP response; it usually throws `SSLException` or `IOException` with a specific cause.

**Question 10.** If the server returns HTTP `404` after a successful TLS handshake, should you adjust the truststore?

**Answer:** Not based on `404` alone. This is an HTTP resource/status issue; check the URL path, access permissions, and response body per the API.

**Question 11.** Should you call `getInputStream()` for every HTTP status to read error JSON?

**Answer:** No. For HTTP errors, `getInputStream()` may throw `IOException`; once a response is received, check `getResponseCode()` and `getErrorStream()` per contract.

**Question 12.** Does a self-signed certificate in a lab automatically disable hostname verification?

**Answer:** No. If the client trusts the certificate via a custom truststore, the URL host must still match the certificate identity.

**Question 13.** Does `SSLContext.getInstance("TLS")` mean TLS 1.3 is always used?

**Answer:** No. The provider/JDK and policy configuration determine which protocol version is enabled/negotiated. Keep the runtime and security policy updated.

**Question 14.** Should you use an always-true `HostnameVerifier` temporarily to run tests and forget to remove it?

**Answer:** No. It breaks HTTPS identity guarantees and easily leaks into production. Use a test truststore and a certificate with the right SAN.

**Question 15.** When using an HTTPS proxy, who is the TLS peer the client needs to verify?

**Answer:** In the standard HTTP CONNECT tunnel model with end-to-end TLS, the client must verify the **origin hostname** it requested, not replace it with the proxy hostname. If managed TLS interception is present, the trust/identity model must be analyzed separately.

**Question 16.** Does `disconnect()` replace closing the response `InputStream`?

**Answer:** No. Close the stream with `try-with-resources` whenever possible, and call `disconnect` in `finally` to signal that the application is no longer using the connection.

**Question 17.** Why does the demo intentionally disable redirects with `setInstanceFollowRedirects(false)`?

**Answer:** So the two requests hit the exact two URLs chosen in the lesson, without a redirect changing the hostname/scheme and confounding verification results. Production needs a controlled redirect policy.

**Question 18.** If you already imported a cert into the truststore but still get "No subject alternative names matching IP address", what should you do?

**Answer:** Verify the URL host/IP and certificate SAN; reissue the certificate with the right IP SAN or call the right DNS name. Importing into a truststore does not resolve a mismatch.

**Question 19.** Can you distinguish an expired cert from a DNS failure solely from an HTTP `statusCode`?

**Answer:** No. Both are errors occurring before or during TLS/transport, and there may be no HTTP status. You must inspect the exception class and cause.

**Question 20.** If there are many internal microservices, should you add each self-signed leaf cert into app source code?

**Answer:** Usually no. Prefer a managed internal PKI/CA, centrally configured truststores scoped as needed, rotation, secrets management, and monitoring; keep standard hostname verification.

## 18. Checklist for Deploying Secure HttpsURLConnection

Before putting a Java HTTPS client into use:

1. **The URL must be HTTPS** and the target hostname/IP allowed by policy; never cast from HTTP.
2. **Identify the trust source**: JVM default, managed internal CA, or dedicated demo certificate. Do not use trust-all.
3. **Create SSLContext properly** via `KeyStore` and `TrustManagerFactory`; `KeyManager` only when client identity/mTLS is needed.
4. **Attach SSLSocketFactory per-instance** before connecting; avoid modifying global defaults in libraries/SDKs.
5. **Keep default hostname verification**, with no always-true verifier.
6. **Certificates must contain the right SAN**: DNS SAN for DNS URLs, iPAddress SAN for IP URLs; do not rely on subject CN.
7. **Verify SNI/termination** when deploying behind a load balancer or with multiple hosts sharing an IP.
8. **Configure positive timeouts** for connect/read and a **total deadline** at the application layer.
9. **Keep redirects controlled**, checking the URL/scheme/host of redirect targets and preventing credential leakage.
10. **Read HTTP responses properly**: status, headers, success input stream, and error stream; separate network/TLS failures.
11. **Close InputStream/OutputStream**, call `disconnect()` when done, and do not call TLS session methods after the lifecycle ends.
12. **Log safely**: appropriate exception class/cause, normalized hostname, never log private keys/passwords/tokens.
13. **Monitor certificate expiry and truststore rotation**, testing before changing CAs/certs.
14. **Test positive and negative cases**: valid cert with matching host must pass; trusted cert with wrong host must be rejected; untrusted cert must be rejected.
15. **Test IPv4/IPv6 and DNS/IP SANs** if clients can access the host in multiple forms.
16. **For upload/payment POSTs**, handle retries/idempotency separately; TLS does not guarantee exactly-once delivery.
17. **Maintain JDK security updates** and protocols/ciphers per policy; do not enable legacy TLS/SSL due to uninvestigated compatibility errors.
18. **Separate transport security from authorization and business validation**; all three matter.

**Conclusion:** `HttpsURLConnection` uses `SSLSocketFactory` to create TLS sockets and appropriate trust configuration, but **trust chain verification does not replace hostname verification**. In Java 17, keep default HTTPS hostname checking, configure trusted CAs/certificates with a dedicated truststore when needed, and treat a connection as the right server only when the URL host matches a verified SAN. The demo shows that `localhost` is trusted and accepted, while `127.0.0.1` is still rejected on the **same server** because the IP identity is absent from the certificate.

### References

- [Java SE 17 — HttpsURLConnection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html)
- [Java SE 17 — SSLSocketFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocketFactory.html)
- [Java SE 17 — HostnameVerifier API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HostnameVerifier.html)
- [Java SE 17 — SSLContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Java SE 17 — TrustManagerFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html)
- [Java SE 17 — KeyStore API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html)
- [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525.html)
- [RFC 2818 — HTTP over TLS (historical context)](https://www.rfc-editor.org/rfc/rfc2818.html)
