# Verifying Hostname and Truststore with a Test HTTPS Client/Server Pair

**Topic:** Java Advance - networking  
**Group:** Networking Labs  
**Language and tools:** Java 17+, **java.net.http.HttpClient**, **com.sun.net.httpserver.HttpsServer**, **javax.net.ssl.SSLContext**, **KeyStore PKCS12**, **keytool**.

## 1. Problem Statement and Expected Observations

When an HTTPS client connects to a server, **a successful TCP connect is not enough to consider the server trustworthy**. During the TLS handshake, the client must validate the server certificate, which involves two independent questions:

1. **Trust/chain validation:** does the server certificate or certificate chain lead to a **trust anchor** that the client is configured to trust? Does the certificate satisfy the relevant usage constraints, signatures, validity period, and policies?
2. **Hostname verification (endpoint identification):** does the hostname identity in the **target URL** match an appropriate **Subject Alternative Name (SAN)** on the server certificate?

This lab builds a **local HTTPS server/client pair running on the same machine**, without calling the Internet, to verify both mechanisms:

| Test case | Client truststore | Target URI | Expected result |
| --- | --- | --- | --- |
| A | Contains the trusted server certificate | **https://localhost:PORT/hello** | TLS succeeds; HTTP 200 and body TLS_OK |
| B | Contains only an **unrelated** certificate | **https://localhost:PORT/hello** | TLS handshake is rejected because the server cannot be authenticated |
| C | Contains the trusted server certificate | **https://127.0.0.1:PORT/hello** | TLS handshake is rejected because the SAN only has **DNS:localhost**, not **IP:127.0.0.1** |

**Key takeaway:** B and C fail for **two different reasons**, even though they use the same server/port. Fixing the truststore does **not** automatically fix a hostname mismatch; fixing the URL to the right hostname does **not** automatically make an untrusted certificate trusted.

The demo uses a self-signed certificate and illustrative passwords in a **temporary test environment**; do not copy this private key, truststore, or password into production. **Do not disable hostname verification or use a trust-all TrustManager** to force the HTTPS handshake to succeed.

## 2. Where Is HTTPS Authenticated?

Simplified flow:

~~~text
HttpClient                 TCP/TLS server
    |                           |
    | --- TCP connect --------> |
    | <--- TCP established ----- |
    |                           |
    | --- TLS ClientHello ----> | (may contain SNI "localhost")
    | <--- certificate chain --- |
    |                           |
    | [1] verify trust chain    |
    | [2] verify SAN            |
    | [3] policy, validity,     |
    |     key usage, algorithms |
    |                           |
    | --- TLS handshake done -->| if valid
    |                           |
    | --- HTTPS GET /hello ---> |
    | <--- HTTP 200 TLS_OK ----- |
~~~

The **TLS handshake** happens before the HTTP request is processed in the server handler. If the chain or hostname is invalid, the client typically throws **SSLHandshakeException** (or an I/O exception with an underlying cause) and **there is no normal HttpResponse.statusCode()** to read.

### Three identities to distinguish

- **Destination IP of the TCP socket:** the actual address used to reach the server, for example **127.0.0.1**.
- **Host in the HTTPS URI:** the hostname requested by the application, for example **localhost** or **127.0.0.1**.
- **Hostname in the certificate SAN:** the endpoint identities the certificate is allowed to represent, for example **DNS:localhost**.

When the URL is **https://localhost:PORT**, the client can resolve localhost to a loopback address. Even though TCP actually connects to **127.0.0.1**, endpoint identification still checks the **localhost name in the URL** against the DNS SAN. When changing the URI to **https://127.0.0.1:PORT**, the client must match the **IP address** against an **IP address SAN**; **a DNS:localhost SAN does not substitute for an IP SAN**.

**Successful DNS resolution is not proof of successful TLS identity.** One IP can serve multiple virtual hosts; a certificate is only valid for the exact DNS/IP identities it was issued for.

## 3. Keystore and Truststore Have Different Responsibilities

### Server keystore

An HTTPS server must prove its right to use a **private key** corresponding to the public key on the certificate. In the demo, the PKCS12 file **server.p12** contains:

- The server's RSA **private key**.
- A **self-signed certificate** carrying the public key, subject CN=localhost, and **SAN DNS:localhost**.
- The alias **localhost** so the JSSE server selects this key/certificate.

The server reads this file using **KeyStore**, passes it into **KeyManagerFactory**, and uses the KeyManagers when creating the **SSLContext** for HttpsServer.

**Do not give server.p12 to the client**: it contains the private key. If the client only needs to trust the server, export the **public certificate** to **server.cer**, and import that certificate into the client truststore.

### Client truststore

A client truststore contains certificates considered **trusted entries/trust anchors** under PKIX policy. In the demo:

- **client-trusted.p12** contains the server's public certificate (alias server), sufficient to trust the test self-signed certificate itself.
- **client-untrusted.p12** contains the public certificate of a **different, unrelated** keypair, so it cannot authenticate the test server.

The client reads the truststore using **TrustManagerFactory**, creates an **SSLContext**, and passes the SSLContext to **HttpClient.newBuilder().sslContext(...)**.

**A valid truststore alone is still not enough**: HttpClient must also verify the **hostname** of the URI. If the URI contains the IP 127.0.0.1 while the SAN only has DNS:localhost, the request must be rejected.

### Comparison table

| Concept | Contains private key? | Who uses it in the demo? | Purpose |
| --- | --- | --- | --- |
| **server.p12** | Yes | HttpsServer/KeyManagerFactory | Server presents its certificate and proves ownership of the private key |
| **server.cer** | No | Exported from server.p12 | Public certificate for controlled trust distribution |
| **client-trusted.p12** | No server private key | HttpClient/TrustManagerFactory | Client trusts the exact test self-signed certificate |
| **client-untrusted.p12** | Only public certificate of an unrelated machine | HttpClient/TrustManagerFactory | Creates a negative trust validation case |
| **JDK cacerts** | Usually public CA trust anchors | HTTPS clients using defaults | Does not automatically trust the test self-signed certificate |
| **SAN extension** | Embedded in the certificate | Client hostname verifier | Verifies that the requested host/IP is represented by the certificate |

**Warning:** PKCS12 is a **keystore/certificate storage format**; it does not inherently mean "keystore" or "truststore". The two roles are determined by **the contents and how the application uses them**.

## 4. Generating a Self-Signed Certificate with SAN DNS:localhost Using keytool

To keep the lab reproducible, use **JDK 17+** with **keytool**, **javac**, and **java** on your PATH. Create a **separate test directory** and run the following commands inside it. Do not use a production repository working directory to store keys/certs. All generated files are **short-lived fixtures**—delete them after studying.

### Step 1 — create server.p12

~~~bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 7 -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -dname "CN=localhost, OU=Learning, O=Example, C=VN" -ext "SAN=DNS:localhost" -ext "EKU=serverAuth" -noprompt
~~~

Explanation:

- **-genkeypair:** generates a private key and a self-signed certificate.
- **-alias localhost:** keypair alias inside the server keystore.
- **RSA 2048 / SHA256withRSA:** algorithms for testing purposes, not a recommendation for production algorithm choices.
- **-validity 7:** the certificate is valid for only 7 days from creation; it must be regenerated when expired.
- **-storetype PKCS12:** portable format in Java/JDK.
- **-dname CN=localhost:** subject; **do not rely on CN as a substitute for SAN**.
- **-ext SAN=DNS:localhost:** explicitly declares the hostname protected by the certificate.
- **-ext EKU=serverAuth:** marks the certificate for TLS server authentication.
- **changeit:** sample password, **never use as a production secret**.

**Important:** Only include **DNS:localhost**, **do not include IP:127.0.0.1**, so that case C fails as intended. If you add IP:127.0.0.1 to the SAN, case C **may succeed**, and the hostname mismatch test will no longer demonstrate the failure.

### Step 2 — export the public certificate, not the private key

~~~bash
keytool -exportcert -alias localhost -keystore server.p12 -storepass changeit -file server.cer
~~~

**server.cer** contains the **public certificate**. Exporting/importing a certificate is completely different from copying **server.p12**: this export does not contain the private key and only tells the client which certificate to trust. In practice, you must verify the fingerprint and certificate distribution channel before deciding to trust it; importing an arbitrary certificate from an untrusted source can break the security model.

### Step 3 — create the truststore that accepts the test server

~~~bash
keytool -importcert -alias server -file server.cer -keystore client-trusted.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

**-noprompt** is only appropriate in a controlled experiment where the certificate was exported from a keypair you generated yourself. In real systems, do not use it to automatically trust an unverified certificate. This truststore will contain the server's public certificate as the trust anchor for the test.

### Step 4 — create an unrelated certificate and a wrong truststore

Generate an independent keypair with a different domain name:

~~~bash
keytool -genkeypair -alias unrelated -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 7 -storetype PKCS12 -keystore unrelated.p12 -storepass changeit -keypass changeit -dname "CN=unrelated.example, OU=Learning, O=Example, C=VN" -ext "SAN=DNS:unrelated.example" -noprompt
~~~

Export the unrelated public certificate:

~~~bash
keytool -exportcert -alias unrelated -keystore unrelated.p12 -storepass changeit -file unrelated.cer
~~~

Import it into a truststore to test the negative trust path:

~~~bash
keytool -importcert -alias unrelated -file unrelated.cer -keystore client-untrusted.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

Do **not** use an empty truststore if you want to rule out provider-specific issues when no trust anchors are present; using an **unrelated** certificate makes the test unambiguous: there is a valid truststore, it simply **does not trust this server**.

### Step 5 — inspect details before running

~~~bash
keytool -list -v -alias localhost -keystore server.p12 -storepass changeit
keytool -list -v -alias server -keystore client-trusted.p12 -storepass changeit
keytool -list -v -alias unrelated -keystore client-untrusted.p12 -storepass changeit
~~~

Check the **SHA-256 fingerprint**, **Owner/Issuer**, **SubjectAlternativeName**, validity, EKU, and aliases. On the server certificate you should see **DNSName: localhost** in the SAN (the exact keytool formatting may vary across JDKs). Do **not** look for or expect an IP SAN because we did not create one.

**Shell compatibility note:** the commands above are single-line and work in standard JDK terminals. In PowerShell 5.1, depending on how options starting with -D are parsed, you may need to pass JVM arguments as **a quoted string** in the program execution step below. The .p12 files are for testing only; do not upload them to git, email, or share them publicly.

## 5. Complete Java 17 HTTPS Server/Client Demo

The **HttpsTrustAndHostnameDemo.java** program implements all three cases A/B/C. The entire HTTPS server runs inside the JVM:

- **HttpsServer** binds to **127.0.0.1** and port 0 (the OS picks an unused port), avoiding the public network.
- **KeyManagerFactory** loads the private key/certificate from **server.p12**.
- **HttpsConfigurator** attaches the SSLContext to the server.
- **GET /hello** after successful TLS returns **HTTP 200**, content type **text/plain; charset=UTF-8**, body **TLS_OK**.
- **TrustManagerFactory** loads one of the two client truststores, creating an SSLContext for each HttpClient.
- Client A calls **https://localhost:PORT/hello** with the right truststore.
- Client B calls the same URI with the truststore containing the unrelated certificate, expected to fail handshake.
- Client C uses the right truststore but the URI **https://127.0.0.1:PORT/hello**, expected to fail the hostname check.

**No line disables hostname verification.** The demo also does not alter the system-wide default truststore; it creates two **per-client** SSLContexts, avoiding any impact on other HTTPS requests in the same JVM.

### Source: HttpsTrustAndHostnameDemo.java

~~~java
import com.sun.net.httpserver.HttpsConfigurator;
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
import java.security.SecureRandom;
import java.time.Duration;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.TrustManagerFactory;

public class HttpsTrustAndHostnameDemo {
    static final char[] PASSWORD = "changeit".toCharArray();

    static KeyStore loadStore(Path file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    static SSLContext serverContext(Path file) throws Exception {
        KeyManagerFactory keys =
                KeyManagerFactory.getInstance(
                        KeyManagerFactory.getDefaultAlgorithm());
        keys.init(loadStore(file), PASSWORD);

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(keys.getKeyManagers(), null, new SecureRandom());
        return tls;
    }

    static SSLContext clientContext(Path file) throws Exception {
        TrustManagerFactory tm =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
        tm.init(loadStore(file));

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(null, tm.getTrustManagers(), new SecureRandom());
        return tls;
    }

    static HttpClient client(Path file) throws Exception {
        return HttpClient.newBuilder()
                .sslContext(clientContext(file))
                .connectTimeout(Duration.ofSeconds(3))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }

    static HttpRequest request(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
    }

    static boolean rejectsHandshake(
            HttpClient client, URI uri) throws Exception {
        try {
            client.send(
                    request(uri),
                    HttpResponse.BodyHandlers.ofString());
            return false;
        } catch (SSLHandshakeException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Expected 3 PKCS12 files");
        }

        SSLContext serverTls = serverContext(Path.of(args[0]));
        HttpsServer server = HttpsServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setHttpsConfigurator(
                new HttpsConfigurator(serverTls));

        server.createContext("/hello", exchange -> {
            try (exchange) {
                byte[] bytes = "TLS_OK".getBytes(
                        StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type",
                        "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream output =
                             exchange.getResponseBody()) {
                    output.write(bytes);
                }
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();

            URI good = URI.create(
                    "https://localhost:" + port + "/hello");
            URI badName = URI.create(
                    "https://127.0.0.1:" + port + "/hello");

            HttpClient trusted = client(Path.of(args[1]));
            HttpClient untrusted = client(Path.of(args[2]));

            HttpResponse<String> response = trusted.send(
                    request(good),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println(
                    "trustedHostStatus=" + response.statusCode());
            System.out.println(
                    "trustedHostBody=" + response.body());

            System.out.println(
                    "wrongTrustRejected="
                            + rejectsHandshake(untrusted, good));
            System.out.println(
                    "wrongHostnameRejected="
                            + rejectsHandshake(trusted, badName));
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Running the demo

Save the exact source to **HttpsTrustAndHostnameDemo.java** in **the directory containing the three .p12 files** created earlier. Compile on JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 HttpsTrustAndHostnameDemo.java
~~~

Run it, forcing the JVM to prefer IPv4 so **localhost** connects to the fixture bound on **127.0.0.1** even on IPv6-enabled machines:

~~~bash
java -Djava.net.preferIPv4Stack=true HttpsTrustAndHostnameDemo server.p12 client-trusted.p12 client-untrusted.p12
~~~

**If using Windows PowerShell 5.1**, you can wrap the -D argument in quotes:

~~~powershell
java '-Djava.net.preferIPv4Stack=true' HttpsTrustAndHostnameDemo server.p12 client-trusted.p12 client-untrusted.p12
~~~

**Verified stdout when compiled with javac --release 17 and run on JDK 24.0.2 with freshly generated keytool fixtures:**

~~~text
trustedHostStatus=200
trustedHostBody=TLS_OK
wrongTrustRejected=true
wrongHostnameRejected=true
~~~

**Note:** the exact JSSE/PKIX exception message may vary by JDK, provider, OS, certificate state, and truststore. Therefore, the demo **does not match the literal exception text**, and instead confirms the **SSLHandshakeException** category for both negative cases. If a case unexpectedly throws another type of I/O error (for example, failing to connect due to a bind/IPv6 mismatch), the program fails clearly instead of misleadingly printing "rejected=true".

### Output explanation

1. **trustedHostStatus=200**: the truststore has the server certificate and the URL host matches the SAN; the TLS handshake completes, and only then does the HTTP handler run.
2. **trustedHostBody=TLS_OK**: the response body was decoded as UTF-8 by HttpClient.
3. **wrongTrustRejected=true**: the truststore only has the unrelated certificate; the client cannot build a trust path to the server certificate, so SSLHandshakeException is caught.
4. **wrongHostnameRejected=true**: the client trusts the server certificate, but the URI host is the IP address 127.0.0.1, whereas the server SAN only has **DNS:localhost**. Endpoint identification rejects it.
5. The server remains bound to the same port in all cases. **There is no 404/500** for the two handshake failures; the HTTP handler is never invoked to return a status for requests that fail TLS.
6. The program calls **server.stop(0)** in finally and closes the InputStream when loading the keystore/truststore. In Java 17, HttpClient does not yet have the Java 21+ AutoCloseable/close API, so try-with-resources is not used for HttpClient under --release 17.

**Security:** The password **changeit** is only to make the commands reproducible in a short-lived test environment. Do not use this password or the self-signed fixture private key in production. In real systems, secrets should be provisioned via a secrets manager or keystore with restricted permissions.

## 6. Deep Dive: Trusting a Certificate Is Not the Same as Trusting the Hostname

Suppose the server certificate has:

~~~text
Subject: CN=localhost
Subject Alternative Name:
    DNSName: localhost

Public Key: RSA 2048-bit
Extended Key Usage: TLS Web Server Authentication
Issuer: self-signed for this demo
~~~

The **CN** field may be used in legacy compatibility corner cases, but **modern HTTPS should not be designed around CN fallback when SAN is present**. For a certificate with SAN DNS:localhost, hostname verification must match the DNS name in the URI.

**Three separate checks:**

### A — right trust, right name

~~~text
URI host: localhost
Cert SAN: DNS:localhost
Truststore: contains server public certificate

Trust path: PASS
Hostname:   PASS
HTTP:       GET /hello -> 200 TLS_OK
~~~

### B — wrong trust, right name

~~~text
URI host: localhost
Cert SAN: DNS:localhost
Truststore: contains only unrelated certificate

Trust path: FAIL
Hostname:   may not even be evaluated further
HTTP:       no successful HttpResponse
~~~

### C — right trust, wrong name

~~~text
URI host: 127.0.0.1
Cert SAN: DNS:localhost
Truststore: contains server public certificate

Trust path: PASS
Hostname:   FAIL (missing SAN IP Address 127.0.0.1)
HTTP:       no successful HttpResponse
~~~

**Do not try to infer the exact order of every check from exception messages**: JSSE providers may order checks or report errors differently. What is guaranteed is that the client only allows HTTP after all required TLS identity/trust constraints pass.

### Why does changing localhost to 127.0.0.1 matter?

This is not a routing/IP error. Both URIs can reach **the exact same local server**, but **the HTTPS URI host is the identity that must be proven**. When the client uses an IP literal, the certificate must have a matching **IP Address SAN**. Even a DNS SAN containing the string "127.0.0.1" (if present) should not be used in place of a proper IP SAN. If both access methods are genuinely needed in production, the CA must issue a certificate containing **both the corresponding DNS SAN and IP SAN** per policy; with public PKI, issuing certificates for internal names/IPs has its own restrictions.

## 7. JDK Default Truststore vs. Custom SSLContext

A Java application has several ways to manage trust:

- **Default:** HttpClient uses the JVM's default SSLContext/trust manager, typically backed by a JDK truststore such as **cacerts**, along with any applicable Java security/system properties.
- **Per-client:** Create an **SSLContext** from a designated truststore, then pass it to **HttpClient.newBuilder().sslContext(tls)**. The demo uses this approach to **isolate the test**.
- **System-wide:** The system properties **javax.net.ssl.trustStore**, **javax.net.ssl.trustStorePassword**, and **javax.net.ssl.trustStoreType** can affect the default trust manager at initialization time. You must understand process-wide impact, initialization timing, and environment effects.

**Do not confuse:**

~~~text
javax.net.ssl.keyStore        -> usually client/server key material
javax.net.ssl.trustStore      -> trust anchors for peers
HttpClient.Builder.sslContext -> attaches an SSLContext to a specific HTTP client
~~~

In this lab, **server.p12** holds the server's private key; **client-trusted.p12** holds the trusted public certificate. If you only set **javax.net.ssl.keyStore** on the client without configuring a truststore, you have not solved how the client trusts the server.

**Caution with replacement truststores:** A custom SSLContext built solely with trust managers from a small truststore may **no longer trust the public CAs** included in the JVM default. The demo only talks to the test server, so this is desirable. In production applications, you need a clear trust policy: private CAs, public CAs, trust bundle rotation, and blast-radius limits. Do not add an arbitrary certificate and assume the entire trust chain is safe.

### How to inspect the fingerprint

~~~bash
keytool -list -v -alias localhost -keystore server.p12 -storepass changeit
keytool -list -v -alias server -keystore client-trusted.p12 -storepass changeit
~~~

Use the **SHA-256** fingerprint to verify that the client actually trusts the exact certificate just created. If the certificate changes after the server rotates its key/cert, the old client truststore may no longer trust it. When using a real private CA, you typically trust the **appropriate CA** rather than pinning the leaf server certificate directly to support rotation; SAN/validity/usage must still be checked.

## 8. TLS Handshake Failure Is Different from HTTP 4xx/5xx Status

This is a very common diagnostic mistake. **HTTP 401/403/404/500** only have meaning once the HTTP layer has exchanged a response. When the certificate is untrusted or the SAN does not match, **the TLS handshake fails before any HTTP request/response**. No HTTP 500 is sent by the HttpsServer handler itself in that demo.

| Scenario | TCP connect? | TLS succeeds? | HttpResponse? | What to check/handle |
| --- | --- | --- | --- | --- |
| Right trust + right hostname | Yes | Yes | Yes, 200 | Read status/body |
| Truststore does not trust cert | Possibly | No | No | Check trust anchors/cert chain |
| SAN does not match URI host | Possibly | No | No | Fix URI or issue cert with right SAN |
| Expired cert | Possibly | Not under normal policy | No | Renew/redeploy valid cert |
| DNS fails to resolve | No | Does not reach TLS | No | Check DNS/URI |
| TCP connect refused | Cannot connect | Does not reach TLS | No | Check bind/port/firewall |
| HTTP 404 after good TLS | Yes | Yes | Yes, 404 | Handle HTTP route |
| HTTP 503 after good TLS | Yes | Yes | Yes, 503 | Service readiness/backend |
| TLS client certificate rejected | Yes | Does not complete | No | Check mTLS client identity |

In Java, **SSLHandshakeException** extends **SSLException**, which is a subtype of **IOException**. With **HttpClient.sendAsync**, the error may be wrapped in **CompletionException** when calling join(), or in **ExecutionException** when calling get(). Unwrap the cause via **getCause()** and log the exception class and sanitized endpoint, without logging private keys/passwords.

**Do not do this:**

~~~java
catch (IOException e) {
    return 500; // WRONG: fabricating HTTP 500 when there is no response.
}
~~~

Instead, APIs should use a result type that distinguishes **HttpOutcome(status,body)** from **TransportOrTlsFailure(cause)**, as well as service-level health responses from business validation errors.

## 9. Dangerous "Fixes" to Avoid

### Do not use a TrustManager that trusts every certificate

Anti-pattern example (do not run):

~~~java
// ANTI-PATTERN: TrustManager accepting every certificate.
// Do not implement an empty X509TrustManager checkServerTrusted().
// Do not use a trust-all SSLContext in production or real tests.
~~~

If the client skips certificate chain validation, a middlebox attacker can present a certificate they generated. The connection may still be encrypted, but **the peer is not authenticated**.

### Do not disable hostname verification

Do not set a "disable endpoint identification" configuration or implementation-specific property so that **https://127.0.0.1** accepts a cert that only has DNS:localhost. Doing so **destroys the exact test being verified** and creates the risk of connecting to a server other than the intended identity.

Specifically avoid passing arbitrary **SSLParameters** or unsupported properties to HttpClient to bypass endpoint identification. The demo uses **HttpClient.sslContext(custom)** while keeping **default hostname verification** and proves that a mismatch is blocked.

### Do not blindly import certificates when seeing a handshake error

Running keytool importcert -noprompt on a certificate downloaded from an unauthenticated endpoint can cause you to trust an impersonator's certificate. To stay safe:

1. Obtain the certificate/trust bundle from a **trusted administrative channel**.
2. Verify the SHA-256 fingerprint out-of-band or via a managed PKI.
3. Import only the approved CA or certificate.
4. Verify that the **URI hostname** matches the SAN.
5. Set up rotation/expiration monitoring.
6. Keep truststore read/write permissions tight and do not leak secrets.

### Do not switch to unencrypted HTTP

Changing **https://** to **http://** to bypass TLS errors removes transport security. In the demo, doing so also sends an HTTP request to a **TLS-only port**, which will fail differently rather than genuinely succeeding.

## 10. Verifying SAN, Trust Chain, and Failure Causes

### Using keytool

~~~bash
keytool -list -v -alias localhost -keystore server.p12 -storepass changeit
keytool -list -v -alias server -keystore client-trusted.p12 -storepass changeit
keytool -list -v -alias unrelated -keystore client-untrusted.p12 -storepass changeit
~~~

Check:

- **Alias** and **Entry type**: server.p12 contains a PrivateKeyEntry; client-trusted.p12 is typically a trustedCertEntry.
- **Subject, issuer, validity**: CN=localhost, self-signed fixture, start/end dates.
- **SAN**: only DNSName: localhost.
- **ExtendedKeyUsage**: serverAuth if printed.
- **SHA-256 fingerprint**: the server certificate in the right truststore must have a fingerprint matching server.cer.

If you import the wrong alias/certificate or mistype the password, the error may occur **when initializing KeyStore/SSLContext** before any network activity. Do not confuse an **IOException decrypting a keystore** with an **SSLHandshakeException from the remote server**.

### SSL debug only in controlled environments

JDK JSSE supports diagnostics:

~~~bash
java -Djava.net.preferIPv4Stack=true -Djavax.net.debug=ssl,handshake,trustmanager HttpsTrustAndHostnameDemo server.p12 client-trusted.p12 client-untrusted.p12
~~~

**The output is very verbose** and may contain TLS exchange details, certificates, and environment info; enable it only in controlled test/dev environments. Do not send raw logs containing secrets/sensitive traces to public systems. JDK/provider versions may change the format, so do not write business parsers that depend on message text.

Diagnostic hints:

| Symptom | What to check first |
| --- | --- |
| **PKIX path building failed** or unable to find valid certification path | Which truststore is being used? Does it have the right certificate/CA? |
| **No subject alternative names matching IP address** | The URL is an IP; does the SAN have an IP Address type with the matching value? |
| **No name matching ... found** | Does the host in the URI match a DNS SAN? |
| **Keystore was tampered with / password incorrect** | Password, PKCS12/JKS format, file bytes, alias |
| **Connection refused** | Is the server bound to the right IP/port, and is the process running? |
| **Unrecognized SSL message/plaintext connection** | Wrong HTTP/HTTPS scheme/port, or proxy termination? |
| **Handshake timeout** | Network path, proxy, TLS capabilities, and deadline |
| **Received fatal alert: bad_certificate** | May relate to mTLS client certificate or server policy |
| **Certificate expired/not yet valid** | Clock/timezone, certificate validity, rotation |

Exception messages are only hints. Examine the **cause chain** and evidence from the actual environment before drawing conclusions.

## 11. SAN DNS vs. SAN IP and Hostname Changes

Beginners often ask: "localhost and 127.0.0.1 both resolve to loopback, so why does HTTPS still fail?". TLS endpoint identity does not validate "same destination IP"; it validates **the name or IP in the URI** according to the rules. If you want it to **be valid for both DNS localhost and IP 127.0.0.1 in a different test**, you must issue a cert containing both SAN types:

~~~bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 7 -storetype PKCS12 -keystore server-both.p12 -storepass changeit -keypass changeit -dname "CN=localhost, OU=Learning, O=Example, C=VN" -ext "SAN=DNS:localhost,IP:127.0.0.1" -ext "EKU=serverAuth" -noprompt
~~~

**This is a separate lab variant**; do not use that file in place of server.p12 in the original demo if you still want to verify that case C fails. If you change the server certificate, you must also export/import the new certificate or CA into the corresponding client truststore; merely updating the SAN on a new certificate while the client still only trusts the old leaf will cause a trust failure.

**SNI is not hostname verification:** In the TLS ClientHello, SNI typically tells the server which host the client wants to reach so the server can select a certificate. However, the server selecting a certificate does not mean the client accepts it; the client still checks the trust chain and SAN. With IP literals, some implementations do not send SNI the same way as when the URL has a DNS name; do not rely on SNI to skip the SAN check.

**DNS name behind a proxy:** If the client connects through a proxy, the host to verify is normally the hostname of the HTTPS origin from the URL, not automatically the hostname of the proxy hop; check the specific proxy/TLS mode documentation to avoid mixing up connections.

## 12. Distinguishing Server Trust from mTLS

In the demo, **the server uses a private key/certificate**, and the client verifies the server certificate. The server **does not require a client certificate**. This is standard TLS server authentication.

**Mutual TLS (mTLS)** is a different requirement: the server also needs to verify the client's certificate. This requires:

- The client has a **client keypair/certificate** in a client keystore and **KeyManagerFactory**.
- The server has a **truststore** containing the appropriate CA/certificate to verify clients.
- The server is configured to request/require client authentication via SSLParameters (such as needClientAuth) according to the API.
- The client still verifies the **server trust chain and hostname** as before.

**Adding mTLS does not replace client hostname verification**; the two authentication directions are independent. A server may require a valid client cert, yet the client must still reject a server with a hostname mismatch.

Do not confuse **server-keystore** with **server-truststore** in mTLS. The server keystore holds **the server's** private key, whereas the server truststore holds trust anchors for trusting **client certificates**. The original demo does not need a separate server truststore because it does not require client certificates.

## 13. Real-World Deployment: Policies Instead of Trust-All

In production, one of the following models is typically used:

1. **Public CA**: the server certificate has a chain leading to a public CA trusted by the JDK/client; the hostname in the URL has the right SAN. There is no need to manually import the server leaf into every client if the truststore has the appropriate root.
2. **Private/enterprise CA**: certificates are issued from an internal CA; client truststores contain the managed internal CA; leaf certificates can be rotated without updating every truststore as long as the CA is unchanged.
3. **Scoped pinning**: some systems apply a policy to pin a specific public key/certificate. This requires rotation, rollback, and outage controls; **never** treat importing a random leaf from the network as safe pinning.

Practical checklist of requirements:

- **Hostname/SAN** matches the service DNS.
- **Certificate chain** is complete and signed by a trusted CA.
- **Validity** and rotation before expiration; synchronized system clocks.
- **Server authentication EKU/key usage**, algorithms/keys strong enough per security policy.
- **TLS versions/cipher suites** are appropriate; do not enable weak protocols just to make tests pass.
- **Truststore/keystore permissions** are tight, with proper password/secret management.
- **Load balancer/ingress certificate termination**: identify where TLS terminates; if a proxy terminates TLS, the certificate the Java client sees may be the proxy-facing endpoint's certificate.
- **HTTP connect/request timeouts** and separate DNS error handling; certificate verification does not replace network retry policy.
- **Observability**: distinguish certificate verification errors, hostname mismatches, DNS, TCP, TLS protocol, HTTP status, and application errors.
- **Deployment tests**: verify certificates/SANs/truststores after changing endpoints, CAs, or running container images with different JDKs.

**Do not hard-code an absolute path to JDK cacerts** across environments. JDK/container images may differ; use standard configuration, per-client SSLContext, or managed secrets/CA bundles with verification tests.

## 14. Regression Tests Should Isolate Causes

| Test | Single condition changed | What to assert |
| --- | --- | --- |
| Baseline | Right trust, URL localhost | HTTP 200, body TLS_OK |
| Negative trust | Truststore has only unrelated certificate, URL localhost | TLS handshake rejected |
| Negative hostname | Right trust, URL 127.0.0.1, cert only has DNS:localhost | TLS handshake rejected |
| Valid SAN for both IP and DNS | New cert has DNS + IP SAN and truststore is updated | Both URIs can succeed |
| Certificate rotated | Server replaces leaf, client still only trusts old leaf | Trust path fails unless trust policy is updated |
| CA truststore | Leaf signed by private CA trusted by client | Passes if chain/identity/usage are valid |
| Expired certificate | Tested under normal policy | Expired certificate should not be accepted |
| Wrong port | Server not bound | Connection refused/timeout, not hostname mismatch |
| Plain HTTP on TLS port | Wrong scheme/protocol | Protocol error before any expected HTTP response |
| Wrong truststore password | Wrong password for PKCS12 file | Keystore loading fails before network |
| Client certificate required | mTLS server needClientAuth but client has no keypair | Handshake fails per server policy |

**Do not test negative hostname by changing both the truststore and the URL at the same time**: when multiple errors exist simultaneously, the first exception can mask the second. The original demo isolates the two conditions to clearly show trust vs. name.

### Safe testing in CI

- Generate certificates/keypairs in the job's temporary directory; never commit private keys.
- Use loopback **127.0.0.1** and port 0; do not expose the server publicly.
- Use **short-lived** certs; never let production depend on test certificates.
- Run **java -Djava.net.preferIPv4Stack=true** to avoid localhost IPv4/IPv6 differences in this fixture.
- Do not assert on full exception messages; assert on the error type/contract such as SSLHandshakeException.
- Configure connect/request timeouts so tests do not hang indefinitely.
- Clean up all fixtures after the job finishes.
- Do not import test certificates into **machine-wide cacerts** or alter the system-wide truststore just for tests.

## 15. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Setting only CN=localhost, omitting SAN | Modern HTTPS clients rely on SAN | Issue an explicit DNS SAN |
| Accessing via 127.0.0.1 with only DNS SAN localhost | IP identity does not match DNS SAN | Use localhost or issue the right IP SAN |
| Trusting server.cer and assuming any hostname is allowed | Trust and hostname are independent | Always verify endpoint identity |
| Using trust-all to "fix PKIX" | Allows MITM/forged certs | Import a verified CA/certificate |
| Disabling hostname verification | Allows servers with the wrong name | Fix the URI or the certificate |
| Copying server.p12 to client-truststore | Leaks the private key | Export the public cert, import the certificate |
| Confusing javax.net.ssl.keyStore with trustStore | Client does not trust the server | Configure the right trust anchors |
| Trying GET and catching HTTP 500 when handshake fails | There is no HTTP response yet | Classify SSLHandshakeException |
| Thinking localhost resolves to IP so IP SAN does not matter | TLS compares the host in the URI | Issue the right DNS/IP SAN type |
| Reusing an expired certificate from a previous run | Handshake fails for the wrong reason | Generate fresh fixtures, check validity |
| Not checking the fingerprint when importing | Could trust a cert from the wrong source | Verify out-of-band/via trusted channel |
| Installing test certs into JDK cacerts so every app trusts them | Unintentionally widens trust scope | Per-client SSLContext |
| Using the same wrong truststore in both negative tests | Cannot distinguish trust vs. name | Change only one condition per test |
| Removing timeouts because test network is slow | Hangs are hard to diagnose | Appropriate timeouts and controlled logs |
| Using URL host 127 while server binds only IPv6 | TCP fails before TLS | Choose matching bind/resolution, prefer IPv4 for fixture |
| Relying on full exception message text | Varies by provider/JDK | Use exception class, cause chain, and cert metadata |
| Using the HttpsServer fixture as a production server | Lacks auth/rate limits/hardening | Use a maintained server/framework for production |

## 16. Further Exercises

1. Explain the difference between **server keystore** and **client truststore**; where does the private key live?
2. When the client trusts the right certificate but the URL host is wrong, why does the handshake still fail?
3. Why are **https://localhost** and **https://127.0.0.1** two different TLS endpoint identities?
4. If a certificate only has **SAN DNS:localhost**, which of cases A/B/C must pass/fail?
5. Generate a certificate that also includes **IP:127.0.0.1 SAN**, export the public cert, and import it into a new truststore. Predict the result when using the IP URL.
6. Read **keytool -list -v** to confirm fingerprint/issuer/subject/SAN/EKU. Do not confuse CN and SAN.
7. Remove client-trusted.p12 from the program and let HttpClient use the default truststore. On a machine that does not trust the demo cert, at which layer is the error expected? Why should you not rely unconditionally on the default environment for assertions?
8. Explain why a truststore with an unrelated certificate is a stronger negative case than changing trust and hostname simultaneously.
9. In **sendAsync**, which CompletableFuture exception types can wrap SSLHandshakeException?
10. Try binding HttpsServer to 127.0.0.1 while the JVM prefers IPv6 for localhost. How does a connect refusal differ from a TLS name mismatch?
11. Why is importing a certificate from an unknown source dangerous, even if it makes the PKIX error go away?
12. Distinguish **certificate validity error** from **hostname mismatch**, **trust chain failure**, **DNS failure**, and **HTTP 503**.
13. State the prerequisites for a server to require **mTLS client authentication**; why does mTLS not exempt hostname verification?
14. Design a CI test that generates short-lived certs, runs on loopback, does not commit private keys, and does not modify machine-wide cacerts.
15. In an ingress proxy environment, which certificate does the Java client see? Distinguish client→ingress TLS from ingress→backend TLS.
16. A service changes its DNS host from api-old.example to api-new.example but still uses a certificate with only SAN api-old.example. Should you fix the truststore or the certificate/URI?
17. If the server certificate is rotated while the client pins the old leaf directly, what happens? When does trusting an internal CA help with rotation?
18. Write an error mapper that distinguishes IOException from connect failure, SSLHandshakeException from TLS, HttpResponse 404, and HttpResponse 503; do not fabricate an HTTP status when there is no response.

## 17. Lab Completion Checklist

- [ ] Does HttpsServer use the **private key** in server.p12 and a certificate with SAN DNS:localhost?
- [ ] Does the client truststore **contain only the public certificate**, without the server's private key?
- [ ] Is the password changeit used only temporarily for testing, not in production?
- [ ] Does the client create TrustManagerFactory/SSLContext from the right PKCS12?
- [ ] Is certificate validation or hostname verification never disabled?
- [ ] Does Case A (trusted + localhost) receive **200 TLS_OK**?
- [ ] Does Case B (unrelated truststore + localhost) throw **SSLHandshakeException**?
- [ ] Does Case C (trusted + 127.0.0.1, missing IP SAN) throw **SSLHandshakeException**?
- [ ] Are the two handshake failures not mistaken for HTTP 4xx/5xx?
- [ ] Does the JDK 17 source compile with javac --release 17?
- [ ] Does the server bind only to loopback and use a dynamic port?
- [ ] Are connect/request timeouts and fixture cleanup in place?
- [ ] Have SAN/fingerprint/validity been inspected with keytool?
- [ ] Are URI hostname, DNS resolution, SNI, and SAN clearly distinguished?
- [ ] Are global cacerts/truststores left unmodified outside the test scope?
- [ ] Do you know how handling CA rotation/mTLS/ingress differs from the self-signed demo?

**Summary:** a proper HTTPS client must both **trust the certificate chain** and **verify that the hostname in the URL matches the SAN**. With the same server certificate having SAN DNS:localhost, a client with the right truststore calling localhost will receive HTTP 200; a different truststore will be rejected due to the **trust path**; and the right truststore calling 127.0.0.1 will be rejected due to **hostname/IP SAN mismatch**. The solution is to configure the **certificate, trust anchor, and URI identity** properly, not to disable TLS verification.

### References

- [Java SE 17: HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17: HttpClient.Builder.sslContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 17: SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Java SE 17: KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html)
- [Java SE 17: TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html)
- [Java SE 17: KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html)
- [Java SE 17: HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html)
- [Java SE 17: HttpsConfigurator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html)
- [Java keytool command reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html)
- [RFC 5280 — PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 6125 — Service Identity Verification](https://www.rfc-editor.org/rfc/rfc6125)
- [RFC 2818 — HTTP Over TLS](https://www.rfc-editor.org/rfc/rfc2818)
