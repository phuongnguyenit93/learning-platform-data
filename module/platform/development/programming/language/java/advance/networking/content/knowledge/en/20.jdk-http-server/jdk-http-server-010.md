# HttpsConfigurator, SSLContext, and Local HTTPS Testing

## Lesson Objectives

Java 17 includes a lightweight HTTP server in the `jdk.httpserver` module, consisting of `HttpServer` for HTTP and `HttpsServer` for HTTPS. To turn an HTTP server into a proper HTTPS server, **it is not enough to just change the URL from `http://` to `https://`**. The server needs an **`SSLContext` initialized with the server's private key and certificate**, and then `HttpsServer` must be configured with **`HttpsConfigurator`**. On the client side, you need to verify the **certificate chain and hostname** of the HTTPS endpoint; with a self-signed certificate for local testing, we create a **dedicated truststore** instead of disabling TLS verification.

After this lesson, you will:

- Distinguish `HttpServer` from `HttpsServer`, and understand the role of the `jdk.httpserver` module.
- Understand why `HttpsConfigurator` and `HttpsParameters` attach TLS settings to each **incoming HTTPS connection**, while `HttpHandler` processes the HTTP request **after** the TLS handshake succeeds.
- Create an `SSLContext` for the **server** using `KeyManagerFactory`/private key and for the **client** using `TrustManagerFactory`/trusted certificate.
- Distinguish a **keystore** containing a private key from a **truststore** storing trusted certificates/CAs, as well as `server.p12`, `server.crt`, and `client-trust.p12`.
- Use `keytool` to generate a self-signed certificate with a **SAN DNS/IP** matching the loopback endpoint, and import it into a dedicated truststore for the test.
- Run a **standalone Java 17+** program that creates an `HttpsServer` on `127.0.0.1` and calls `GET /hello` using `HttpClient` over real HTTPS with full TLS verification.
- Observe **HTTP 200**, the body, the HTTP version, the TLS session, and the `SSLHandshakeException` error when the client does not trust the certificate.
- Understand how to tune TLS protocols/cipher suites, when to use mTLS, and how to manage threads, handlers, stream lifecycle, timeouts, and `stop()`.
- Diagnose SAN/hostname mismatches, missing private keys, wrong passwords, wrong truststores, TLS protocol mismatches, missing HttpsConfigurator setup, and common production pitfalls.

**Scope:** `com.sun.net.httpserver` and `javax.net.ssl` APIs of **Java 17 and later**. The test program binds **loopback** only and uses dummy credentials; it must not be deployed directly as an Internet-facing production HTTPS server.

## 1. The Big Picture: HTTP Running Inside TLS

Plain HTTP transmits requests/responses directly over TCP. With HTTPS, before transmitting HTTP application data, the client and server establish a TLS session:

~~~text
HttpClient                        HttpsServer (jdk.httpserver)
    │                                        │
    │ ─────── TCP connect ──────────────────►│
    │                                        │
    │ ─────── TLS ClientHello ──────────────►│
    │ ◄────── certificate + handshake ──────┤
    │         verify trust + SAN             │
    │ ◄─────► TLS handshake finished ◄─────►│
    │                                        │
    │ ====== GET /hello (encrypted) =======►│
    │       HttpsExchange / HttpHandler      │
    │ ◄====== 200 + body (encrypted) =======│
    │                                        │
    │            session/transport cleanup   │
~~~

This is a **logical model**, not a message-by-message transcript of TLS 1.2/1.3. TLS 1.3 has a different handshake sequence and message protection than TLS 1.2; Java's `SSLContext`/`SSLEngine` APIs handle the protocol details.

What to distinguish:

1. **TCP:** can a connection reach the IP/port? If a firewall blocks it or the wrong address is chosen, it never reaches TLS.
2. **TLS handshake:** does the server have a private key, an appropriate certificate, and a common cipher/protocol? Does the client trust the certificate and hostname?
3. **HTTP:** only when TLS succeeds does the handler receive the method, URI, and headers/body, and return the status/response.
4. **Application authentication:** even after TLS succeeds, an API can still require a token/cookie or return HTTP 401/403 according to its own policy.

**Note:** A TLS server certificate helps the client authenticate the endpoint and protects data on the channel; it does **not** by itself prove that a user is logged in, that a request is authorized, or that the response body is semantically valid for business logic.

## 2. Participating Java Classes and Their Responsibilities

| Component | Module/package | Role |
|---|---|---|
| `HttpServer` | `jdk.httpserver / com.sun.net.httpserver` | HTTP server without TLS |
| `HttpsServer` | `jdk.httpserver / com.sun.net.httpserver` | HTTP server with TLS; requires `HttpsConfigurator` |
| `HttpsConfigurator` | `jdk.httpserver / com.sun.net.httpserver` | Holds `SSLContext`, supplies/configures TLS parameters for an incoming connection |
| `HttpsParameters` | `jdk.httpserver / com.sun.net.httpserver` | Receives the SSL parameters to apply to an HTTPS connection |
| `HttpsExchange` | `jdk.httpserver / com.sun.net.httpserver` | An HTTPS request/response; provides `getSSLSession()` |
| `HttpHandler` / `HttpExchange` | `jdk.httpserver` | Reads the HTTP request, writes headers/status/body |
| `SSLContext` | `java.base / javax.net.ssl` | Foundation for creating TLS engines/sockets, using KeyManager and TrustManager |
| `SSLParameters` | `java.base / javax.net.ssl` | Configures TLS protocols, cipher suites, client auth, endpoint identification, etc. |
| `KeyStore` | `java.base / java.security` | Container for certificates, private-key entries, and trusted certificates |
| `KeyManagerFactory` | `java.base / javax.net.ssl` | Obtains KeyManagers to select the local endpoint's private key + certificate |
| `TrustManagerFactory` | `java.base / javax.net.ssl` | Obtains TrustManagers to decide whether a peer certificate is trusted |
| `HttpClient` / `HttpRequest` | `java.net.http` | Client for sending HTTPS requests and receiving HTTP responses after TLS |

**Important:** `HttpsConfigurator` is neither the encryption engine itself nor an `HttpHandler`. It uses `SSLContext` to configure TLS for the connection; only after the handshake does `HttpsExchange` pass the request to the handler.

### Typical Configuration Graph

~~~text
server.p12  [server private key + cert]
       │
       ▼
KeyStore → KeyManagerFactory
                    │
                    ▼
        SSLContext SERVER (TLS)
                    │
                    ▼
           HttpsConfigurator
                    │ configure(HttpsParameters)
                    ▼
                HttpsServer
                    │
                    ▼
           HttpHandler /exchange


server.crt [public certificate only]
       │ keytool -importcert
       ▼
client-trust.p12  [trusted cert]
       │
       ▼
KeyStore → TrustManagerFactory
                    │
                    ▼
        SSLContext CLIENT (TLS)
                    │
                    ▼
       HttpClient.Builder.sslContext(...)
                    │
                    ▼
    GET https://127.0.0.1:<dynamic-port>/hello
~~~

The `<dynamic-port>` notation in the diagram is only a conceptual placeholder, **not a valid hostname to run**. The program obtains the actual dynamic port via `server.getAddress().getPort()`.

## 3. Keystore, Truststore, Certificate, and Private Key

A **keystore** and a **truststore** often use the same `PKCS12` format, but they serve different **roles**:

- **Server keystore (`server.p12`):** stores the server's *private key* and corresponding certificate/chain. The server needs the private key to prove its identity during the TLS handshake. This file is **secret** and must not be distributed to clients.
- **Public certificate (`server.crt`):** the exported certificate containing the public key and identity/SAN information; it has no private key. Used to import into the test truststore.
- **Client truststore (`client-trust.p12`):** contains the trusted certificates/CAs used by the client to verify the server. In this lesson it trusts only the **specific self-signed certificate**; it does not contain the server's private key.

A `.p12` file by itself **does not indicate** server or client, nor does it prove whether it holds a private key or only a trusted certificate. You must look at the entry type/alias and how the code uses it:
- `KeyManagerFactory.init(keyStore, keyPassword)` reads the local private key source.
- `TrustManagerFactory.init(trustStore)` reads the trust decisions source when verifying a peer certificate.

**Distinguishing principals:**
- Standard server-auth HTTPS has **the server holding a key pair** and the client **holding trust anchors**.
- Client-auth mTLS has **the client also holding a key pair**, and the server needing trust anchors to verify the client. That is an advanced scenario and is not needed for a standard server-auth test.

### Why Use PKCS12?

`PKCS12` is a standard keystore format with built-in support in Java 17. Use `KeyStore.getInstance("PKCS12")` rather than relying on the default keystore type across different JVMs or organizational configurations.

`KeyStore.load(input, password)` opens the file and verifies the password/integrity according to the provider/format. `KeyManagerFactory.init(keys, password)` needs the password to access private key entries; with the wrong password or alias, the server may fail to select a matching private key and the TLS handshake will fail.

**Do not use `server.p12` as the client-side truststore just because that file contains the certificate.** A private key resides inside the server keystore file; copying that file to the client exposes the key. Always **export the public certificate** and import it into the client truststore.

## 4. SAN and Hostname Validation: Two Steps Independent of Trust

A certificate may have subject `CN=localhost`, but modern HTTPS clients require a **Subject Alternative Name (SAN)** matching the **actual name/IP in the URI**.

In this lesson:
- The server binds `127.0.0.1`.
- The client calls `https://127.0.0.1:<port>/hello`.
- The certificate has **`SAN=IP:127.0.0.1`**.
- `SAN=DNS:localhost` is also included so learners can compare a DNS name with an IP literal.

The difference:

| Client URI | Identity required on the certificate |
|---|---|
| `https://127.0.0.1:port/...` | IP SAN containing `127.0.0.1` |
| `https://localhost:port/...` | DNS SAN containing `localhost` |
| `https://api.example.org/...` | DNS SAN valid for `api.example.org` |
| `https://192.0.2.10/...` | Appropriate IP SAN if the client uses an IP literal |

**CN does not reliably replace SAN in modern configurations.** A certificate can be accepted by the truststore in terms of CA/public key and still fail hostname validation because the name/IP does not match. Do not "fix" this by disabling verification; fix the SAN or use the right endpoint URL.

### Trust ≠ Identity ≠ Authorization

A TLS client performs two separate checks:
1. **Trust/path validation:** does the certificate/chain lead to a trusted anchor and satisfy constraints?
2. **Endpoint identification:** does the certificate represent the expected hostname/IP in the URI?

Even when both succeed, the API may still require `Authorization: Bearer ...` or a session cookie. `SSLContext` is not the place to check application roles/scopes.

## 5. Creating a Self-Signed Certificate and Truststore with keytool

Practice in **a separate, temporary directory**, and do not commit it to Git. All filenames in this section belong to that directory. You need **JDK 17+** with `keytool`, `javac`, and `java` installed.

### 5.1. Generate Private Key + Server Certificate

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -validity 2 -dname "CN=localhost" -ext "SAN=DNS:localhost,IP:127.0.0.1" -ext "EKU=serverAuth" -noprompt
~~~

Explanation:
- `-alias server`: name of the key entry managed in the keystore.
- `-keyalg RSA -keysize 2048`: algorithm/key size for the example; production must follow approved cryptography policies, which may choose EC.
- `-storetype PKCS12`: keystore format.
- `-storepass` and `-keypass`: **dummy passwords for the lab**, never for real use.
- `-validity 2`: **two-day** validity, intentionally very short.
- `-dname "CN=localhost"`: subject name.
- `-ext "SAN=DNS:localhost,IP:127.0.0.1"`: two identities allowed for hostname/IP verification.
- `-ext "EKU=serverAuth"`: key/certificate usage purpose for server authentication.

**Security:** passing passwords on the command line can leave them in shell history/logs/process metadata. In real systems, use a secret manager, strict file permissions, and secure key provisioning; do not use `changeit` and do not leave test private keys on production servers.

### 5.2. Export the Public Certificate

~~~bash
keytool -exportcert -alias server -rfc -keystore server.p12 -storepass changeit -file server.crt
~~~

`server.crt` is the public certificate and **contains no private key**. Inspect the certificate contents if needed with:

~~~bash
keytool -printcert -file server.crt
~~~

Verify that the **SubjectAlternativeName** extension includes both DNS `localhost` and IP `127.0.0.1`. When the certificate expires (two days after creation), you must generate a new certificate and update the truststore; expiry errors must not be "fixed" with trust-all.

### 5.3. Create the Client Truststore by Importing the Public Cert

~~~bash
keytool -importcert -noprompt -alias localserver -file server.crt -keystore client-trust.p12 -storetype PKCS12 -storepass changeit
~~~

This accepts the **specific self-signed certificate** as a trust anchor for the test. When you regenerate `server.p12` with a different keypair, the new certificate no longer matches the old certificate in `client-trust.p12`; you must update the truststore.

### 5.4. Check Aliases and Entry Types

~~~bash
keytool -list -v -keystore server.p12 -storetype PKCS12 -storepass changeit
keytool -list -v -keystore client-trust.p12 -storetype PKCS12 -storepass changeit
~~~

Expected:
- `server.p12`: alias `server`, **PrivateKeyEntry** (private key + chain).
- `client-trust.p12`: alias `localserver`, **trustedCertEntry**.

**Do not share `server.p12`** with whoever runs the client. In the example, the server and client run in the same JVM, so the same process reads two different files; production typically separates machines/services and manages certificates/private keys by role.

## 6. `SSLContext`: Where Private-Key Identity and Trust Policy Converge

The `SSLContext` Javadoc describes it as an object representing a TLS/SSL protocol implementation that can create socket factories and `SSLEngine` instances. Typically:

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, null);
~~~

This is a **snippet**, assuming `keyManagers`/`trustManagers` have already been created; passing `null` as the last parameter requests the default `SecureRandom` source. The name `"TLS"` **does not mean** "force TLS 1.3"; the actual protocol is negotiated based on the provider/SSLParameters/client/server policy.

### 6.1. Server SSLContext

In server-auth HTTPS:
- `KeyManagerFactory` is initialized from `server.p12` containing the **private key**.
- `SSLContext.init(kmf.getKeyManagers(), null, null)` attaches the server identity.
- A `null` TrustManagers parameter means using the provider default if trust decisions are needed; since the example **does not enable client authentication**, the server does not need to verify client certificates.

Pattern:

~~~java
KeyStore keys = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("server.p12"))) {
    keys.load(in, "changeit".toCharArray());
}

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
    KeyManagerFactory.getDefaultAlgorithm());
kmf.init(keys, "changeit".toCharArray());

SSLContext serverTls = SSLContext.getInstance("TLS");
serverTls.init(kmf.getKeyManagers(), null, null);
~~~

This is a **snippet** requiring imports `java.security.KeyStore`, `java.io.InputStream`, `java.nio.file.*`, and `javax.net.ssl.*`; it is not a standalone program.

### 6.2. Client SSLContext

On the client:
- `TrustManagerFactory` is initialized from `client-trust.p12`.
- `SSLContext.init(null, tmf.getTrustManagers(), null)` provides no client private key, because **mTLS is not required** in this lesson.
- TrustManagers verify the server certificate; HTTPS endpoint identification/hostname verification continues to be enforced by Java's `HttpClient` according to HTTPS policy.

~~~java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("client-trust.p12"))) {
    trust.load(in, "changeit".toCharArray());
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext clientTls = SSLContext.getInstance("TLS");
clientTls.init(null, tmf.getTrustManagers(), null);
~~~

Also a **snippet**, using `java.security`, `java.nio.file`, `java.io`, and `javax.net.ssl`. For production, the truststore should contain CAs/trust anchors matching organizational policy, not an arbitrarily generated self-signed certificate.

**Warning:** calling `SSLContext.setDefault(...)` can affect the entire JVM and other libraries. When you only want to trust a test certificate for **one HttpClient**, attach `sslContext(clientTls)` on that **specific client builder** instead of changing the global default.

## 7. `HttpsServer`, `HttpsConfigurator`, and `HttpsParameters`

### 7.1. Creating the HTTPS Server

How to create it:

~~~java
HttpsServer server = HttpsServer.create(
    new InetSocketAddress(
        InetAddress.getByName("127.0.0.1"), 0),
    0);
~~~

The call above creates a server bound to **IPv4 loopback** and asks the OS to pick an available port via `0`. The `backlog=0` argument lets the implementation choose an appropriate default. This is a **snippet** requiring imports `com.sun.net.httpserver.HttpsServer` and `java.net.*`.

**Binding loopback is not the same as binding publicly:** `127.0.0.1` accepts connections only from the local machine. Production may bind a specific address and must be paired with firewall/network policy, valid TLS identity, and authorization. Do not bind `0.0.0.0` out of habit in labs with dummy private keys.

### 7.2. Attaching HttpsConfigurator

~~~java
server.setHttpsConfigurator(new HttpsConfigurator(serverTls) {
    @Override
    public void configure(HttpsParameters params) {
        SSLParameters settings =
            getSSLContext().getDefaultSSLParameters();
        params.setSSLParameters(settings);
    }
});
~~~

**This is required by role:** `HttpsServer` needs an `HttpsConfigurator` associated with an initialized `SSLContext`. The Java 17 Javadoc states that `HttpsConfigurator.configure(HttpsParameters)` is called when a new HTTPS connection is being established; the callback supplies the TLS settings for the connection. If you override it, you must call `params.setSSLParameters(settings)` to pass all SSL parameters.

**Do not put TLS configuration inside `HttpHandler`** after a request has already arrived, because by then the TLS handshake has succeeded or the connection has already been established. Certificate selection/protocols/ciphers are handshake responsibilities, not response headers.

### 7.3. SSLParameters from SSLContext

`getSSLContext().getDefaultSSLParameters()` returns a **copy** of the context's default configuration, including the protocols/cipher suites currently enabled by the provider/security policy.

This example is only valid when client compatibility is **already known**:

~~~java
SSLParameters tls = getSSLContext().getDefaultSSLParameters();
// Example only: constrain protocols after verifying support:
tls.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
params.setSSLParameters(tls);
~~~

This is a snippet **inside `configure(...)`**, not standalone code. `TLSv1.3` is supported in many modern JDKs, but provider/policy must be checked; TLS 1.2 is a required protocol under the Java 17 SSLContext contract. Do not enable TLS 1.0/1.1 or legacy cryptography just to make a test pass.

**When mTLS is required**, you can configure `SSLParameters.setNeedClientAuth(true)`, but the server `SSLContext` must have **TrustManagers to trust client certificates**. Without client trust anchors/KeyManager, the handshake fails. Section 11 explains how to add mTLS within proper boundaries without turning this server-auth lesson into a different client-certificate lesson.

### 7.4. Addresses/Ports and TLS Sessions

- `HttpsParameters.getClientAddress()` reports the connecting peer's network address according to the API; **it is not a certificate-proven identity**.
- `HttpsExchange.getSSLSession()` lets you inspect an exchange's TLS session (for example, `getProtocol()`). Do not log raw session IDs/peer certificates indiscriminately in production.
- `server.getAddress().getPort()` returns the OS-assigned port after binding; useful for writing portable tests.
- `server.setExecutor(executor)` can supply an executor to handle HTTP requests; `server.stop(delay)` stops the HTTP listener and closes exchanges according to policy, **without automatically shutting down an application-owned executor**.

## 8. Complete Example: Loopback HTTPS with Trusted and Untrusted Clients

This is a **compiled and tested Java 17+ program**. It:
1. Reads `server.p12` to create the **server SSLContext** (with private key).
2. Reads `client-trust.p12` to create the **client SSLContext** (trusting only the lesson's self-signed certificate).
3. Creates an `HttpsServer` on `127.0.0.1`, attaches `HttpsConfigurator`, and handles `GET /hello`.
4. Makes a client request `https://127.0.0.1:<port>/hello` using `HttpClient.newBuilder().sslContext(clientTls)`; the certificate has a matching IP SAN.
5. Prints the response status, body, HTTP version, and evidence that the handler observed a TLS session.
6. Tries `HttpClient.newHttpClient()` **without** the custom truststore: in a test environment where the certificate is not trusted, the handshake is rejected.
7. Stops the server in `finally`, leaving no listener open in the test process.

**The keystore files must be created beforehand from Section 5.** The program does not download certificates from the network and does not disable TLS validation.

### 8.1. Standalone Source: `LocalHttpsDemo.java`

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsExchange;
import com.sun.net.httpserver.HttpsParameters;
import com.sun.net.httpserver.HttpsServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.TrustManagerFactory;

public class LocalHttpsDemo {
    private static final char[] PASSWORD = "changeit".toCharArray();

    static KeyStore loadStore(Path path) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    static SSLContext serverContext(Path serverKeys) throws Exception {
        KeyStore keys = loadStore(serverKeys);
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, PASSWORD);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), null, null);
        return context;
    }

    static SSLContext clientContext(Path serverTrust) throws Exception {
        KeyStore trust = loadStore(serverTrust);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);
        return context;
    }

    static void handle(HttpExchange exchange,
            AtomicReference<String> negotiatedProtocol)
            throws java.io.IOException {
        try {
            if (!(exchange instanceof HttpsExchange)) {
                throw new java.io.IOException("Expected HTTPS");
            }
            negotiatedProtocol.set(
                ((HttpsExchange) exchange).getSSLSession().getProtocol());

            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                exchange.sendResponseHeaders(405, -1);
                return;
            }
            byte[] body =
                "Hello over HTTPS".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.out.println(
                "Usage: java LocalHttpsDemo server.p12 client-trust.p12");
            return;
        }

        SSLContext serverTls = serverContext(Path.of(args[0]));
        SSLContext clientTls = clientContext(Path.of(args[1]));
        AtomicReference<String> negotiatedProtocol =
            new AtomicReference<>();

        HttpsServer server = HttpsServer.create(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setHttpsConfigurator(new HttpsConfigurator(serverTls) {
            @Override
            public void configure(HttpsParameters params) {
                SSLParameters tls =
                    getSSLContext().getDefaultSSLParameters();
                params.setSSLParameters(tls);
            }
        });
        server.createContext("/hello",
            exchange -> handle(exchange, negotiatedProtocol));
        server.start();
        try {
            URI endpoint = URI.create(
                "https://127.0.0.1:" + server.getAddress().getPort()
                + "/hello");
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(5))
                .GET().build();
            HttpClient client = HttpClient.newBuilder()
                .sslContext(clientTls)
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
            HttpResponse<String> response = client.send(request,
                HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
            System.out.println("HTTPS status: " + response.statusCode());
            System.out.println("HTTPS body: " + response.body());
            System.out.println("HTTP version: " + response.version());
            System.out.println("TLS active: "
                + negotiatedProtocol.get().startsWith("TLSv1."));

            boolean rejected = false;
            try {
                HttpClient.newHttpClient().send(request,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
            } catch (SSLHandshakeException expected) {
                rejected = true;
            }
            System.out.println(
                "Untrusted certificate rejected: " + rejected);
        } finally {
            server.stop(0);
        }
    }
}
~~~

### 8.2. Compile and Run

Make sure you already have the three files `server.p12`, `server.crt`, and `client-trust.p12` from the `keytool` commands in Section 5. Save the source file in the same directory.

~~~bash
javac --release 17 -encoding UTF-8 LocalHttpsDemo.java
java LocalHttpsDemo server.p12 client-trust.p12
~~~

Newer compilers use `--release 17` to verify the code only calls **APIs available in Java 17**. If you are using an actual JDK 17, you can use `javac -encoding UTF-8 LocalHttpsDemo.java`.

**Verified stdout** with a keytool-generated self-signed certificate and HTTP client/server over TCP loopback:

~~~text
HTTPS status: 200
HTTPS body: Hello over HTTPS
HTTP version: HTTP_1_1
TLS active: true
Untrusted certificate rejected: true
~~~

During verification, the test files were created in a temporary directory and deleted after running. The lines above omit random ports or detailed protocol versions to keep output stable; the program checks `SSLSession.getProtocol().startsWith("TLSv1.")`, **not** asserting TLS 1.3 specifically. If your JDK policy supports TLS 1.2 but not TLS 1.3, it is still valid HTTPS with TLS 1.2.

**Condition for the last line:** in the test machine's environment, the newly generated certificate is **not yet in the default JVM truststore**. If the runner already imported the certificate into the default truststore, changed `javax.net.ssl.trustStore` JVM-wide, or installed a different TLS policy, `Untrusted certificate rejected` may print `false`; do not conclude the code is wrong just because the machine already has that trust anchor. The example intentionally does not replace the global truststore.

### 8.3. Step-by-Step Walkthrough

1. **LoadStore:** reads PKCS12 inside `try-with-resources` to close `InputStream`; the `changeit` password is for demo purposes only.
2. **serverContext:** `KeyManagerFactory` loads the private key/certificate from `server.p12`; `context.init(kmf.getKeyManagers(), null, null)` prepares the server TLS identity.
3. **clientContext:** `TrustManagerFactory` loads the trusted certificate from `client-trust.p12`; `context.init(null, tmf.getTrustManagers(), null)` provides no client certificate, which is sufficient for server-authenticated HTTPS.
4. **HttpsServer.create:** binds `127.0.0.1:0`; the OS assigns the port. The server has no public `api.example.org` hostname.
5. **HttpsConfigurator:** gets `getDefaultSSLParameters()` from the server TLS context and calls `params.setSSLParameters(tls)` for the connection.
6. **handle:** accepts only GET; for other methods it returns `405` and `Allow: GET`. For GET, it writes the UTF-8 byte body with the exact byte count passed to `sendResponseHeaders(200, body.length)`.
7. **HttpsExchange:** reads `getSSLSession().getProtocol()`; the server handler only sees a TLS session after the HTTPS handshake succeeds.
8. **HttpClient SSLContext:** the client trusts **only the test certificate**, without trust-all; the Java client still checks the `127.0.0.1` IP SAN per HTTPS identity policy.
9. **HTTP version:** `HTTP_1_1` is the version requested and actually returned by the JDK's lightweight server; it is **distinct from the TLS version**. `HTTP_1_1` does not mean TLS 1.1.
10. **Default client attempt:** because the self-signed certificate is not accepted by the default truststore, `send` throws `SSLHandshakeException`; the handler is not successfully invoked for that request.
11. **Cleanup:** `server.stop(0)` stops the server whether the main test or the negative test fails; the example creates no external executor that needs shutting down.

### 8.4. Why Use `HttpsExchange` Instead of Plain `HttpExchange`?

`HttpsExchange` is a subclass of `HttpExchange` and provides `getSSLSession()`. The standard handler signature still receives `HttpExchange`, so we check `instanceof HttpsExchange` and cast when we actually need to inspect TLS properties.

Do not use `getSSLSession()` as proof that **application permissions** have been checked. The TLS session describes the transport/peer cryptographic context; to validate an access token or cookie, you must implement HTTP authentication and authorization separately.

### 8.5. Why Not Print the Raw Certificate or SSL Session ID?

The lesson only needs to observe that the protocol is TLS-based and see the real response. Printing full SSLSession/certificate/handshake logs in production applications can leak sensitive metadata, inflate log volume, or become hard to manage. Use concise telemetry: negotiated TLS version, cipher family, and HTTP status/latency per policy; do not log private keys, raw tokens, or passwords.

## 9. Distinguishing HTTP Version, TLS Version, and Certificate Identity

These three concepts are often confused:

| Property | Example | Where to inspect? |
|---|---|---|
| HTTP protocol version | `HTTP_1_1`, `HTTP_2` | `HttpResponse.version()` |
| TLS negotiated protocol | `TLSv1.2`, `TLSv1.3` | `HttpsExchange.getSSLSession().getProtocol()` |
| TLS certificate identity | SAN `IP:127.0.0.1` / `DNS:localhost` | Certificate and HTTPS endpoint identification |
| Server TCP address | `127.0.0.1:port` | `HttpsServer.getAddress()` |
| HTTP resource | `/hello` | `HttpExchange.getRequestURI()` |
| HTTP status | `200`, `405`, `404` | `HttpResponse.statusCode()` or `sendResponseHeaders` |

**HTTPS does not mean HTTP/2.** The lightweight `jdk.httpserver` server primarily serves HTTP/1.1; an HTTPS connection can negotiate TLS 1.3 and still carry HTTP/1.1. When you see `HTTP_1_1`, do not assume TLS was downgraded to 1.1.

**A TLS handshake is not an HTTP response:** if the certificate is untrusted, the client typically receives `SSLHandshakeException` before any `HttpResponse` exists. Do not try to read `response.statusCode()==401` when no response exists.

## 10. HttpsConfigurator: Per-Connection Configuration at the Right Time

### Why Does `configure` Receive `HttpsParameters`?

`HttpsServer` must decide TLS protocols, cipher suites, and client-auth requirements while a new connection is being established, **before** knowing the full HTTP request content (because HTTP runs inside the decrypted channel). `HttpsConfigurator.configure(HttpsParameters)` is called during HTTPS connection setup.

An `HttpsServer` can use:
- An `SSLContext` initialized before start.
- The context's default `SSLParameters` for each incoming connection.
- Adjusted TLS protocol/cipher policies on `SSLParameters` when justified by compatibility and security testing.
- `needClientAuth/wantClientAuth` when mTLS is desired, paired with an appropriate server trust policy.

### Do Not Choose TLS Policy Based on an Unreceived HTTP Header

Example of **wrong thinking**: inside `HttpHandler.handle`, read `Authorization` and then enable/disable certificate validation for the current connection. The handshake has already happened; an HTTP header **cannot** retroactively alter the initial TLS certificate check.

If you want to apply different certificate policies per service, typically separate listeners/hosts/ports or design a TLS reverse proxy/gateway whose policy is defined before the handshake. Do not put exceptions like "skip TLS check if header X equals Y" in a handler.

### Can You Use the Default HttpsConfigurator Without Overriding?

Yes. `new HttpsConfigurator(serverTls)` already uses default SSLParameters according to the Javadoc. In this lesson we **override** it to clearly demonstrate how `getSSLContext().getDefaultSSLParameters()` and `params.setSSLParameters(...)` are called, as that is the focus of the topic.

When overriding, **you must complete configuring the parameters**; forgetting to call `params.setSSLParameters(...)` can leave TLS settings unapplied in ways you did not expect. Do not return an `SSLParameters` thinking the API receives it — `configure` returns `void`.

### Be Careful with Per-Client Policy

`HttpsParameters.getClientAddress()` can be used to inspect the remote socket address, but it is **not a trusted identity** to replace certificate/token authentication. A client on the network can change IP/NAT/proxy; in many architectures the peer address is just a reverse proxy.

If a system needs multiple certificates by SNI/virtual host, the key manager must have an alias-selection strategy during the TLS handshake; do not write if-else branches in an HTTP handler to swap certificates after the handshake.

## 11. Extending to mTLS: Knowing the Difference Without Enabling It in the Demo

The `LocalHttpsDemo` example is **server-auth TLS**: the server has a private key/certificate, the client trusts the server, and the server does not request a client certificate.

With **mutual TLS**:
1. The client also needs **its own keystore** containing the client private key/certificate.
2. The server needs a **truststore** trusting the client certificate's issuer/CA.
3. The server's `SSLContext` must be initialized with **KeyManagers (server identity) and TrustManagers (client cert trust)**.
4. The client's `SSLContext` must have **KeyManagers (client identity) and TrustManagers (server cert trust)**.
5. Server `SSLParameters` sets `setNeedClientAuth(true)` **before** `params.setSSLParameters(...)`.
6. Once the handshake succeeds, the server can read the peer principal/certificate from the TLS session and map it to an application identity/permissions.

Server-side configuration pattern (snippet only valid when `serverTls` already contains appropriate trust managers):

~~~java
server.setHttpsConfigurator(new HttpsConfigurator(serverTls) {
    @Override
    public void configure(HttpsParameters params) {
        SSLParameters tls =
            getSSLContext().getDefaultSSLParameters();
        tls.setNeedClientAuth(true);
        params.setSSLParameters(tls);
    }
});
~~~

**Do not copy this snippet into the Section 8 demo and expect the test to keep passing**: the client in the demo does not supply a client certificate; mandatory mTLS will cause the handshake to fail. And if the server only created `serverTls` with `init(kmf.getKeyManagers(), null, null)`, it does not yet have a custom trust policy for the organization's client certificates.

### `needClientAuth` vs. `wantClientAuth`

- `needClientAuth(true)`: requires and verifies a client certificate; if missing or rejected, the TLS handshake fails.
- `wantClientAuth(true)`: requests/prefers a client certificate but does not require it in all cases.
- Both are **TLS handshake policies**; succeeding does not automatically grant application permissions. The service must map the certificate identity to principals/roles/scopes per policy.

Do not use a client's public certificate as a substitute for an Authorization token when business logic requires user-level authorization. mTLS typically identifies a **workload/service**, whereas HTTP auth can identify a user/request.

## 12. HttpExchange Lifecycle and Resource Management

HTTPS only adds TLS; HTTP response handling still follows the `HttpExchange` contract.

### Reading Requests and Writing Responses

A proper handler typically:

1. Reads the method and URI/path.
2. If there is a body, **reads/limits or safely rejects it**. Never buffer an unbounded client body of unknown size into memory.
3. Sets response headers, such as `Content-Type` and security headers appropriate to the use case.
4. Calls `sendResponseHeaders(status, length)`.
5. Writes the exact bytes to `getResponseBody()` and **closes the output stream/exchange**.

In the demo, the body is pre-encoded as a UTF-8 `byte[]` so `body.length` is the **exact byte count**; never use `String.length()` to compute `Content-Length`. Writing fewer bytes than declared can cause stream close to throw `IOException` and drop the connection.

### What Traps Exist in `sendResponseHeaders(status, length)`?

| Passed length | Meaning under JDK HttpExchange |
|---|---|
| `length > 0` | Response body has the exact specified byte count; writing fewer or more is an error |
| `length == 0` | Server uses chunked transfer encoding for HTTP/1.1, allowing arbitrary length |
| `length == -1` | No response body is sent |
| `HEAD` or status without body | Must obey HTTP semantics; do not attempt to write a body |

**Common confusion:** `0` in `sendResponseHeaders` **does not simply mean an empty body**. When you want to send no body, `-1` is usually the appropriate choice per the API.

### Executor and Stopping the Server

`HttpsServer` inherits `HttpServer.setExecutor(...)` and `stop(int delay)`. If an application supplies its own `ExecutorService` to handle multiple requests, it must manage shutting down that executor **separately** from the server. In the small program, we do not supply a custom executor to reduce overhead/complexity.

`server.stop(0)` immediately stops the **test server** listener after receiving the response. It does not delete keystores, revoke certificates, or shut down client pools. In a real service, you need graceful shutdown with a deadline, stopping new requests, waiting for in-flight handlers, and cleaning up secrets/executors per policy.

**Do not keep private key passwords as hard-coded `String`s in real applications.** The demo uses a constant `char[]` only for reproducibility. In production, use a secret manager, minimize secret lifetime in memory, and follow rotation policies.

## 13. Common Errors in Local HTTPS Exercises

| Symptom | Likely Cause | Diagnosis / Fix |
|---|---|---|
| `FileNotFoundException` for `server.p12` | Running Java from a different working directory; file not created yet | Check filename, path, and read permissions |
| `IOException: keystore password was incorrect` | Wrong store password | Check the correct secret; do not disable integrity |
| `UnrecoverableKeyException` | Wrong private key entry password | Distinguish `-storepass` and `-keypass` |
| No suitable server private key | Wrong alias/certificate chain or KeyManagers | `keytool -list -v` to check `PrivateKeyEntry` |
| `HttpsServer` missing configurator | Initialized SSLContext/TLS config not attached | Call `setHttpsConfigurator(...)` before `start()` |
| `SSLHandshakeException: PKIX path building failed` | Client does not trust server certificate/CA | Import the right **public certificate** into the truststore used by the client |
| `SSLHandshakeException` with hostname mismatch | Certificate SAN does not match URI host/IP | Regenerate cert with the right SAN; do not disable hostname check |
| `CertificateExpiredException` | Test certificate expired | Regenerate cert and update client truststore |
| `No appropriate protocol` / handshake failure | TLS versions/ciphersuite policy mismatch | Check enabled/supported TLS versions on both sides |
| `Connection refused` | Server not running, bound wrong IP/port | Check start, localhost port, firewall |
| `UnknownHostException` | Wrong URL hostname | Use `127.0.0.1` for demo, real hostname in production |
| `404 Not Found` over HTTPS | TLS succeeded but handler path did not match | Check `/hello` and context mappings |
| `405 Method Not Allowed` | Client used a method other than GET | Send GET, check `Allow: GET` |
| HTTP `200` but body truncated | Wrong byte length / wrong stream close | Write byte[] with `body.length` and close stream |
| HTTP version `HTTP_1_1` but TLS 1.3 | **Not an error** | HTTP and TLS are protocols at different layers |
| Client untrusted because truststore is new but `server.p12` was regenerated | Certificate/key changed | Re-export `server.crt` and import the new cert under the right alias |
| HTTPS works but `server.stop` hangs/leaks threads | Poor handler/stream/executor management | Bound work, set deadlines, close exchange, shut down owned executor |
| Client reports 401/403 | TLS succeeded; application auth/authorization rejected | Check credentials/token; do not change TLS truststore unnecessarily |

### Do Not Use Trust-All as a "Quick Fix"

A **dangerous** pattern often seen online is installing an `X509TrustManager` whose `checkServerTrusted(...)` does nothing, or disabling endpoint identification. This allows **any certificate** to be accepted and breaks server authentication. For financial, internal, or sensitive APIs, this is a critical vulnerability.

This lesson uses `TrustManagerFactory` from a **dedicated truststore**, so certificate validation is still enforced. The line `Untrusted certificate rejected: true` proves that rejection is the **expected** behavior, not an error to bypass.

## 14. Observing TLS Without Leaking Secrets

When an HTTPS handshake fails, diagnose layer by layer:

~~~text
1) Did TCP connect succeed?
       │
       ├── no: IP/port/firewall/route
       │
       ▼
2) Do TLS ClientHello / ServerHello share a protocol?
       │
       ├── no: protocol/cipher policy mismatch
       │
       ▼
3) Does the server have a matching certificate/private key?
       │
       ├── no: keystore/alias/keypass/cert policy
       │
       ▼
4) Does the client trust the certificate and does SAN match hostname/IP?
       │
       ├── no: truststore/expiry/SAN/PKIX
       │
       ▼
5) Did the HTTP handler receive the request?
       │
       ├── no: routing/context/HTTP version/method
       │
       ▼
6) Application auth/business logic/status/body
~~~

You can enable JSSE debug **in test environments only**:

~~~bash
java -Djavax.net.debug=ssl:handshake LocalHttpsDemo server.p12 client-trust.p12
~~~

Handshake output can be verbose and contains certificate metadata, peer details, and session/crypto information. **Do not enable verbose debug in production and retain logs indefinitely.** Do not treat `javax.net.debug` as a handshake fix: it is a diagnostic tool, not a replacement for trust policy.

To inspect the specific protocol/cipher suite in code, you can read `HttpsExchange.getSSLSession().getProtocol()` and `getCipherSuite()` inside the handler. Do not assume a strong cipher suite automatically proves a request is authorized.

## 15. Scenarios: Why Does the Client Still Fail When the Server Has a Valid Cert?

### A. Certificate Trusted, Wrong Hostname

Suppose the client truststore imported a certificate for `localhost`, but the URL called is `https://service.internal.invalid` or an IP not listed in SAN. **Truststore and endpoint identity are two separate checks.** The connection must be rejected if identity does not match, even when the certificate chain is valid.

**Fix:** use a URI matching the SAN or issue a certificate with a valid SAN for the endpoint; do not merely add the certificate to the truststore and disable hostname verification.

### B. URL Is HTTP, Server Is HTTPS

If you call `http://127.0.0.1:port/hello` on a port that only accepts TLS, the client sends **plaintext HTTP** where the server expects a TLS ClientHello. You will see a connection reset/parse error, **not** the expected HTTP 200 result.

**Fix:** use the `https://` scheme. Conversely, if the server is a non-TLS `HttpServer` and the client calls HTTPS, that is also a protocol-layer mismatch.

### C. Valid Server Certificate, Not Yet in Client Default Trust

This is the lab scenario: the self-signed certificate is **not in the JVM's default trust anchors**. The default client must reject TLS. Only a client configured with the custom truststore can trust the test server's certificate specifically. Do not alter the system-wide default truststore just to run one lesson.

### D. Server Has PKCS12, Yet TLS Still Fails

A `KeyStore` containing a public certificate **without a PrivateKeyEntry** cannot serve as a server-auth identity. The server `SSLContext` needs a KeyManager with a private key to prove handshake identity. Use `keytool -list -v` to distinguish `trustedCertEntry` from `PrivateKeyEntry`.

### E. mTLS Enabled by Mistake

If `setNeedClientAuth(true)` is used in the configurator while the client has no client certificate, the handshake fails before HTTP. This is **not** HTTP `401 Unauthorized`; you must provision and trust a client certificate or disable client-auth if only server-auth HTTPS is required.

## 16. Operating the JDK HTTPS Server: Scope and Limitations

`com.sun.net.httpserver` is suitable for **lessons, test harnesses, lightweight internal tools**, embedded HTTP/HTTPS demos, or simple use cases with a clear threat model. It does not replace full production web server features such as:
- TLS termination/gateway management with automatic certificate rotation.
- Large-scale Authentication/OAuth/OIDC/mTLS policies.
- HTTP/2/HTTP/3 features, multiplexing, and advanced routing/proxying.
- Request limits, rate limiting, WAF/DoS protection, and full observability.
- Graceful rollouts, health checks, load balancing, and distributed tracing.
- Certificate issuance/revocation/OCSP/PKI management and secure secrets handling.

Do not assume the mere existence of `HttpsServer` guarantees all security or scalability requirements. For production, choose an architecture with a reviewed threat model: for example, a maintained web server/framework or a trusted TLS reverse proxy in front of the backend, while still enforcing authentication/authorization in the application.

### What If HTTPS Terminates at a Reverse Proxy?

When a reverse proxy terminates TLS:
- The client verifies the **proxy/gateway** certificate for the public hostname.
- The backend can speak HTTP or **separate** mTLS with the proxy.
- An `HttpsServer` in the backend does not automatically see the Internet client's TLS session if TLS terminated at the gateway.
- Forwarded identity headers (such as `X-Client-Cert`) are only trustworthy when generated by an authenticated proxy, stripped/overwritten on external requests, and when the proxy→backend hop is secured.

In this lesson there is **no proxy**: a single JVM runs both the HTTPS server and the HTTP client, and TLS is end-to-end over loopback between the two demo components.

## 17. Implementation and Testing Checklist

1. Use JDK 17+ with the `jdk.httpserver` and `java.net.http` modules.
2. Create `server.p12` with a private key/certificate, a SAN matching the URI hostname/IP, and appropriate EKU.
3. Export `server.crt` and import it into **client-trust.p12**, keeping the server private key secret.
4. Initialize the server `SSLContext` using `KeyManagerFactory` with the right keystore.
5. Create `HttpsServer` on an allowed address/port; use loopback in the lab.
6. Attach `HttpsConfigurator` holding the initialized server context **before starting**.
7. If overriding `configure`, call `params.setSSLParameters(...)` and enable only policy-approved protocols/ciphers.
8. Register `HttpHandler`, read method/path, write status/exact byte body length, and close the exchange.
9. Initialize the client `SSLContext` using `TrustManagerFactory`; do not use trust-all or skip SAN validation.
10. Create `HttpClient` trusting only the lab truststore, with connect/request timeouts set.
11. Send `GET https://127.0.0.1:<port>/hello`; verify status=200, body, and TLS session.
12. Test the default client without a trust anchor: in an isolated environment it must reject the untrusted self-signed certificate.
13. Test negative cases for SAN mismatch/expiry/wrong truststore without leaking the private key.
14. Stop the server and close request/response streams and any application-owned executor.
15. Do not put test passwords in production source, do not commit `.p12` files containing private keys, and do not log secrets.
16. For real deployment, replace short-lived self-signed certs with approved certificates/PKI and rotation/authorization processes.

## 18. Self-Check Exercises

1. Why is changing `http://` to `https://` while still using `HttpServer` not enough for HTTPS?
2. Which JDK module does `HttpsServer` belong to? Which module does `HttpClient` belong to?
3. What are the different roles of `HttpsConfigurator`, `SSLContext`, and `HttpsParameters`?
4. Does `HttpsConfigurator.configure(...)` run before or after the handler reads HTTP headers? Why?
5. Which entry type must the server keystore contain to act as the server TLS identity: `PrivateKeyEntry` or `trustedCertEntry`?
6. Why should you **not** give `server.p12` to the client even though it contains the public certificate?
7. How do `server.crt` and `client-trust.p12` differ?
8. Why is a `CN=localhost` certificate not sufficient to make `https://127.0.0.1` valid on modern HTTPS clients?
9. What is the difference between `SAN=DNS:localhost` and `SAN=IP:127.0.0.1`?
10. Does `SSLContext.getInstance("TLS")` force the negotiated version to be TLS 1.3?
11. If a client trusts a self-signed certificate in a custom truststore while the default JVM does not, can the two clients produce different results?
12. Does the line `Untrusted certificate rejected: true` in the demo prove the HTTPS code is production-safe? Why?
13. What kind of version does `HttpsExchange.getSSLSession().getProtocol()` report? Is it the same as `HttpResponse.version()`?
14. In `sendResponseHeaders(200, body.length)`, why must you use `body.length` rather than the Java String length?
15. Does `sendResponseHeaders(status, 0)` in the JDK HTTP server simply send an empty body?
16. If you enable `SSLParameters.setNeedClientAuth(true)` without a client private key/certificate, what typically happens?
17. A server enables mTLS with only a `KeyManagerFactory` and no TrustManagers trusting client certs. What needs to change?
18. If an HTTPS URL call throws `SSLHandshakeException` before receiving a response, is there an HTTP status code to read?
19. When a test outputs `HTTP version: HTTP_1_1`, does that mean the TLS version is 1.1?
20. Why shouldn't `SSLContext.setDefault` be used casually in a test when only one client needs a custom truststore?
21. Does `HttpsServer.stop(0)` shut down all application executors and connection pools?
22. When using a TLS-terminating reverse proxy, does the backend `HttpsExchange` automatically see the Internet client certificate?
23. When troubleshooting `SSLHandshakeException` caused by a hostname mismatch, should you disable hostname validation?
24. If you want to test a `POST` request with a large body, what limits/resource checks are needed beyond TLS?
25. Why is a self-signed certificate with `-validity 2` generally only reasonable for a lab and not for production?

**Suggested Answers:**
(1) TLS server identity/handshake is required, using `HttpsServer`; (2) `jdk.httpserver` and `java.net.http`; (3) connection configurator / TLS engines & managers / per-connection settings; (4) before the HTTP handler because HTTP runs inside TLS; (5) `PrivateKeyEntry`; (6) the file contains the server private key; (7) public certificate vs. truststore containing a trusted entry; (8) a URI using an IP requires an IP SAN; (9) DNS name vs. IP identity; (10) no, negotiated per provider/policy; (11) yes; (12) no, it only proves trust validation works in the lab; (13) TLS protocol, distinct from HTTP version; (14) UTF-8 can use multiple bytes per character; (15) no, 0 means chunked in the API; (16) the TLS handshake typically fails; (17) provide TrustManagers/CAs trusting the client; (18) not yet; (19) no; (20) it affects the entire JVM; (21) no, resource owners must clean them up separately; (22) no if TLS terminated at the gateway, a clear trust boundary is needed; (23) no, fix the SAN/endpoint/cert; (24) byte limits, timeouts, streaming, rejection, cleanup; (25) production expiry/rotation/PKI and secret management require a complete operational process.

## 19. Summary

- `HttpsServer` is the TLS-enabled HTTP server in the `jdk.httpserver` module, requiring **`HttpsConfigurator`** with an initialized **`SSLContext`**.
- **Server TLS identity** uses `KeyManagerFactory` and the **private key + cert in `server.p12`**. **Client trust** uses `TrustManagerFactory` from **`client-trust.p12`**. Although both are PKCS12, they have different roles and security levels.
- `HttpsConfigurator.configure(HttpsParameters)` supplies **SSLParameters** to an incoming TLS connection; the handler only processes HTTP requests **after** the handshake.
- The self-signed certificate in the lab has **SAN=IP:127.0.0.1** to avoid hostname mismatch. **Never disable** certificate/hostname verification.
- HTTPS status 200/body, HTTP/1.1, and TLS protocol are **three different pieces of information**; a TLS trust failure is not an HTTP 401 response status.
- Server-auth TLS is enough for this test; enabling **mTLS** requires also configuring a client key and server trust policy, not just setting `needClientAuth`.
- Java 17 testing confirmed that a dedicated client truststore connects successfully, while the default client rejects the untrusted self-signed certificate.
- Use the JDK's lightweight server within its intended scope; production requires proper trust/PKI/certificate rotation, authorization, resource limits, and secure operations.

### References

- [Oracle Java SE 17 — com.sun.net.httpserver package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html)
- [Oracle Java SE 17 — HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html)
- [Oracle Java SE 17 — HttpsConfigurator and configure(HttpsParameters)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html)
- [Oracle Java SE 17 — HttpsParameters](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsParameters.html)
- [Oracle Java SE 17 — HttpsExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsExchange.html)
- [Oracle Java SE 17 — HttpExchange.sendResponseHeaders and body lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [Oracle Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Oracle Java SE 17 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html)
- [Oracle Java SE 17 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html)
- [Oracle Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [Oracle Java SE 17 — HttpClient.Builder.sslContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
