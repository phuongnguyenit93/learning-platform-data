# HTTPS, SSLContext, and Server Certificate Verification

## 1. What Does HTTPS Protect?

HTTP transmits application data between a client and a server. When using **HTTPS**, HTTP runs inside a connection protected by **TLS (Transport Layer Security)**. TLS provides three critical properties:

1. **Confidentiality:** an eavesdropper on the wire cannot read the contents without the appropriate keys.
2. **Integrity:** tampering with data in transit is detected.
3. **Peer authentication:** the client verifies the server's identity via digital certificates and a trust chain; depending on configuration, the server can also authenticate the client using a certificate.

A basic HTTPS flow:

~~~text
Java HTTP client
       |
       | 1. TCP connection
       v
    TLS handshake
       |
       | 2. Server sends certificate chain
       v
Client verifies:
  - Does the certificate chain lead to a trust anchor?
  - Is the certificate within its validity period and valid for its purpose?
  - Does the URL hostname match the certificate SAN?
       |
       | 3. Key and algorithm agreement
       v
TLS channel established
       |
       | 4. HTTP requests/responses travel inside the TLS channel
       v
     HTTPS server
~~~

In Java 17, TLS is implemented through **JSSE (Java Secure Socket Extension)**. Key APIs include:

- `SSLContext`: configures the TLS environment, including key managers, trust managers, and random source.
- `TrustManager`: decides whether a peer's certificate should be trusted.
- `KeyManager`: supplies the client's identity and private key when client authentication is required.
- `SSLSocket`/`SSLEngine`: low-level TLS APIs.
- `HttpsURLConnection` and `java.net.http.HttpClient`: high-level HTTP/HTTPS APIs.

**HTTPS does not mean encryption alone.** If a client skips certificate or hostname verification, the connection may be encrypted to an imposter server. Encryption without proper peer authentication does not protect users from man-in-the-middle attacks.

## 2. SSL, TLS, and Which Versions to Use

### 2.1. TLS is the modern protocol

The name `SSLContext` is a historical JSSE API name. In new applications, use TLS. SSL 2.0/3.0 and older TLS versions such as TLS 1.0/1.1 are obsolete and should not be casually re-enabled to work around compatibility issues.

On Java 17, TLS 1.3 and TLS 1.2 are the modern versions to prefer. The JDK generally provides a default set of protocols and ciphers according to runtime and provider security policies. Do not hardcode an outdated cipher list simply because it appeared in an online example.

### 2.2. `SSLContext.getInstance("TLS")` does not mean only one TLS version is used

Example:

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, null, null);
~~~

`"TLS"` is the protocol/algorithm family name used to obtain an SSLContext from a provider. The actual protocol versions enabled on sockets/engines depend on provider and JSSE configuration.

If an application has an explicit policy restricting versions, configure `SSLParameters` to permit only TLS 1.3 and TLS 1.2. Do not re-enable SSLv3, TLS 1.0, or TLS 1.1 just to make an old server connect; upgrade the server configuration or handle exceptions according to your organization's security process.

### 2.3. Do not confuse TLS protocol with certificate algorithms

TLS version, cipher suite, certificate signature, and public key algorithm are related yet distinct parts:

- **TLS version:** the handshake and record layer protocol.
- **Cipher suite:** the combination of encryption/authentication algorithms used by TLS 1.2; TLS 1.3 uses a different naming and suite structure.
- **Certificate signature algorithm:** the algorithm the CA used to sign the certificate.
- **Public key algorithm/size:** the certificate's key type, such as RSA or EC.

A connection can fail due to having no shared TLS version, incompatible ciphers, a certificate algorithm rejected by runtime policy, or an invalid trust chain. Read the root cause in the exception/handshake logs instead of changing every setting at once.

## 3. What Is a Server Certificate?

### 3.1. X.509 certificate

In standard HTTPS, the server sends one or more X.509 certificates to prove its identity. A certificate typically contains:

- Subject: the entity attested by the certificate.
- Issuer: the CA or entity that issued/signed the certificate.
- Public key: the subject's public key.
- Validity: start and end timestamps of validity.
- Subject Alternative Name (SAN): DNS names or IP addresses to which the certificate applies.
- Key Usage and Extended Key Usage (EKU): permitted purposes of the key/certificate.
- Digital signature of the issuer.

The client uses the public key and signature to verify certificate integrity, while checking whether the certificate is valid for server authentication.

### 3.2. Certificate chain

A server certificate is usually not trusted directly by the client. It is signed by an intermediate CA; the intermediate may be signed by a root CA that the client already trusts:

~~~text
Client's trust store
       |
       v
Root CA (trust anchor)
       |
       | signs
       v
Intermediate CA
       |
       | signs
       v
Server certificate
       |
       v
api.example.com
~~~

The server typically sends the leaf certificate along with any required intermediates. The client builds and validates a certification path up to a trusted trust anchor.

Root certificates are normally configured in the client's trust store. A server cannot make its certificate trustworthy simply by sending an unfamiliar root certificate along; the client must possess the corresponding trust anchor or be configured to trust it according to policy.

### 3.3. Chain validation is not the same as hostname verification

This distinction is critical:

1. **Path validation/trust:** does the certificate have a valid signature chain leading to a trust anchor, within its validity period, with the right usage and constraints?
2. **Hostname verification:** was the certificate issued for the exact host the client is connecting to?

A certificate can be signed by a trusted CA yet belong to `other.example.com`, while the URL is `api.example.com`. The certificate chain may be valid, but the hostname does not match; the client must reject the connection.

## 4. Hostname Verification and Subject Alternative Name

### 4.1. The certificate must match the host in the URL

Suppose the client calls:

~~~text
https://api.example.com/v1/orders
~~~

The server certificate must have a SAN matching `api.example.com`. For DNS names, certificates typically carry a `dNSName` SAN. If the URL uses an IP address, the certificate needs an `iPAddress` SAN matching that IP.

For example, a certificate containing:

~~~text
Subject Alternative Name:
  DNS:api.example.com
  DNS:orders.example.com
~~~

allows the corresponding hosts to be verified under hostname verification rules. A certificate carrying only SAN `DNS:other.example.com` is invalid for `https://api.example.com`.

### 4.2. Do not rely on Common Name as a substitute for SAN

Modern certificates must include SANs. New systems should not rely on matching the hostname against the Subject's Common Name (CN) field. When issuing certificates, ensure the CA or internal PKI populates accurate SAN entries for the required DNS names or IPs.

### 4.3. Wildcards have limited scope

A wildcard certificate such as:

~~~text
DNS:*.example.com
~~~

can match a single subdomain label, such as `api.example.com`, according to hostname verification rules. It does not automatically cover multiple levels like `v2.api.example.com` or the apex domain `example.com`.

Do not write your own hostname verifier with naive string comparisons or ad-hoc regexes. Let the HTTPS client/JSSE perform hostname verification using standard rules.

## 5. Trust Store, Key Store, and the Role of SSLContext

### 5.1. Trust store: which CAs does the client trust?

A **trust store** holds certificates trusted by the application as trust anchors or configured trusted certificates. In a typical HTTPS client, the trust manager uses the trust store to verify the server's certificate chain.

Java normally includes a default trust store in the JDK/JRE installation. JSSE also supports configuration via system properties, such as:

- `javax.net.ssl.trustStore`: path to the trust store.
- `javax.net.ssl.trustStorePassword`: password to open the trust store.
- `javax.net.ssl.trustStoreType`: keystore type, such as `PKCS12`.

Do not place trust store passwords in source code, public command lines, or logs. Use secret/configuration management suited to your deployment environment.

### 5.2. Key store: which identity does the client own?

A **key store** typically holds the application's own private key and certificate chain. It is used by KeyManager when the client must present a certificate for server-side client authentication (mutual TLS/mTLS).

| Component | Question |
|---|---|
| Trust store | Which peer certificates/CAs do I trust? |
| Key store | Which private key/certificate do I hold to prove my identity? |
| TrustManager | Should the peer's certificate be accepted? |
| KeyManager | When the peer requests a client certificate, which identity do I present? |

Standard one-way HTTPS only requires the client to authenticate the server. The client does not need its own key store if the server does not require mTLS.

### 5.3. SSLContext ties TLS components together

`SSLContext` is the initialization factory for TLS sockets and engines. The method:

~~~java
context.init(keyManagers, trustManagers, secureRandom);
~~~

accepts:

- `KeyManager[]`: local identity/keys if needed.
- `TrustManager[]`: trust policy for peers.
- `SecureRandom`: source of randomness used during TLS.

For an HTTPS client using the default trust store, the simplest approach is usually the default SSLContext:

~~~java
SSLContext context = SSLContext.getDefault();
~~~

Or initialize a `TLS` context with JSSE's default managers:

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, null, null);
~~~

Never create a custom TrustManager just to "bypass" certificates. If a certificate is valid but not yet trusted, update the trust configuration properly.

## 6. Default HTTPS Client in Java 17

### 6.1. Using java.net.http.HttpClient

Java 11 and later include `java.net.http.HttpClient`, so Java 17 can use this API without external libraries:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class DefaultHttpsClient {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(20))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("Status: " + response.statusCode());
        System.out.println(response.body());
    }
}
~~~

When no custom SSLContext is configured, `HttpClient` uses the runtime's default TLS configuration. For HTTPS, the client performs certificate chain and hostname verification under the default security configuration. You do not need to write a custom hostname verifier for normal cases.

Notes:

- `connectTimeout` limits connection establishment time.
- `HttpRequest.timeout` sets a timeout for the request.
- HTTP timeouts do not replace retry, cancellation, or business timeout policies.
- The `ofString()` body handler handles charsets per HTTP response rules; it is unrelated to the console charset.

### 6.2. HTTPS with HttpsURLConnection

The `HttpsURLConnection` API remains available in Java 17 and is useful when working with legacy code or URLConnection:

~~~java
import javax.net.ssl.HttpsURLConnection;
import java.net.URI;
import java.net.URL;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

URL url = URI.create("https://example.com/").toURL();
HttpsURLConnection connection =
        (HttpsURLConnection) url.openConnection();

connection.setConnectTimeout(10_000);
connection.setReadTimeout(20_000);
connection.setRequestMethod("GET");

int status = connection.getResponseCode();
try (InputStream input = status < 400
        ? connection.getInputStream()
        : connection.getErrorStream()) {
    if (input != null) {
        String body = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );
        System.out.println(body);
    }
} finally {
    connection.disconnect();
}
~~~

`HttpsURLConnection` uses the default SSL socket factory and hostname verifier unless changed by the application. Never install a hostname verifier that accepts all hosts; doing so disables an essential part of HTTPS authentication.

## 7. Creating an SSLContext with a Custom Trust Store

An internal application may connect to servers using certificates signed by an organization's private CA. In that case, place the trusted CA in the application's trust store and build an SSLContext using a trust manager backed by that trust store.

### 7.1. Creating a PKCS12 trust store

Example using `keytool` bundled with the JDK to import an internal CA certificate:

~~~shell
keytool -importcert ^
  -alias company-root-ca ^
  -file company-root-ca.crt ^
  -keystore app-truststore.p12 ^
  -storetype PKCS12
~~~

On Unix-style shells, replace the line continuation `^` with the appropriate line-continuation character or run the entire command on a single line.

The command prompts for a trust store password and certificate confirmation. Import a CA certificate only after verifying its fingerprint or obtaining it from a trusted distribution channel. Never blindly accept a certificate from an untrusted source just to make a connection succeed.

You can inspect certificate details before importing:

~~~shell
keytool -printcert -file company-root-ca.crt
~~~

PKCS12 is the modern keystore format supported in Java 17. Legacy JKS files may still exist in older systems, but for new configurations prefer a widely supported format like PKCS12 unless special compatibility dictates otherwise.

### 7.2. Loading a trust store and creating TrustManagerFactory

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

static SSLContext createSslContext(
        Path trustStorePath,
        char[] trustStorePassword
) throws Exception {
    KeyStore trustStore = KeyStore.getInstance("PKCS12");

    try (InputStream input = Files.newInputStream(trustStorePath)) {
        trustStore.load(input, trustStorePassword);
    }

    TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm()
            );
    trustManagerFactory.init(trustStore);

    SSLContext context = SSLContext.getInstance("TLS");
    context.init(
            null,
            trustManagerFactory.getTrustManagers(),
            null
    );
    return context;
}
~~~

Explanation:

1. `KeyStore.getInstance("PKCS12")` creates a handle to read the trust store.
2. `load(...)` reads the file and unlocks it using the password.
3. `TrustManagerFactory` creates trust managers using the provider's default algorithm.
4. `init(trustStore)` configures the trusted certificates.
5. `SSLContext.init` attaches the trust managers to the context; no KeyManager is needed for one-way HTTPS.

In real applications, do not hardcode the password as a String literal in source code. Retrieve secrets from a secret management system, keep them in memory only as long as necessary, and clear the char array afterward when the lifecycle permits.

### 7.3. Using SSLContext with HttpClient

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;

char[] password = obtainTrustStorePassword();
try {
    SSLContext sslContext = createSslContext(
            Path.of("config", "app-truststore.p12"),
            password
    );

    HttpClient client = HttpClient.newBuilder()
            .sslContext(sslContext)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://internal.example.com/api/status"))
            .timeout(Duration.ofSeconds(20))
            .GET()
            .build();

    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    System.out.println(response.statusCode());
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

`obtainTrustStorePassword()` is an illustrative placeholder for the application's secret-retrieval mechanism. Never store real passwords in source files.

A custom SSLContext replaces the trust configuration used by that client. **If the trust store contains only the internal CA, the client may no longer trust default public CAs.** If the application needs both internal and public endpoints, the trust store must include all required trust anchors or use a carefully designed and audited trust manager strategy.

Do not write a "composite" TrustManager lacking proper order/condition checks. Preserve PKIX validation and hostname verification.

### 7.4. Using SSLContext with HttpsURLConnection

~~~java
SSLContext sslContext = createSslContext(
        Path.of("config", "app-truststore.p12"),
        password
);

HttpsURLConnection connection =
        (HttpsURLConnection) URI
                .create("https://internal.example.com/health")
                .toURL()
                .openConnection();

connection.setSSLSocketFactory(sslContext.getSocketFactory());
connection.setConnectTimeout(10_000);
connection.setReadTimeout(10_000);

int status = connection.getResponseCode();
~~~

Setting the socket factory changes the trust configuration for this connection. Keep `HttpsURLConnection`'s default hostname verification; never set a `HostnameVerifier` that always returns `true`.

## 8. How Does Certificate Chain Validation Work?

### 8.1. TrustManagerFactory and PKIX

In standard configurations, `TrustManagerFactory` creates an X.509 trust manager. When the TLS handshake receives the server's certificate chain, the trust manager validates the certification path per the provider's PKIX policy:

- Does each certificate have a valid signature from its issuer?
- Can the chain reach a trust anchor in the trust store?
- Are the certificates within their validity period?
- Is each CA permitted to sign subordinate certificates per Basic Constraints/Key Usage?
- Does the leaf certificate have an appropriate purpose, such as server authentication?
- Are there any violations of runtime cryptographic algorithms or security policies?

When a trusted path cannot be built, errors commonly report causes such as:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

This indicates the client could not build a certificate path to a trusted trust anchor. It does not automatically mean the server certificate is forged; the server may be missing an intermediate certificate, an internal CA may not be imported yet, or the wrong trust store may be configured.

### 8.2. The server must send all required intermediate certificates

If the server sends only the leaf certificate and omits a necessary intermediate, the client may fail to build the chain. The proper fix is normally configuring the server to send the complete certificate chain (leaf + intermediates), while the client trusts the appropriate root CA.

Avoid solving this by arbitrarily importing individual server leaf certificates into the trust store. That creates key-rotation overhead and undermines CA-level trust management.

### 8.3. Checking validity periods and system clocks

Certificates have `Not Before` and `Not After` timestamps. If the client machine's clock is significantly wrong, a valid certificate may appear not yet valid or expired.

When encountering validity errors:

1. Check the client's system clock.
2. Inspect `Not Before`/`Not After` on the leaf and intermediate certificates.
3. Verify the server deployed the renewed certificate and sends the right chain.
4. Verify which trust store the JVM is actually using.

Never disable expiration checks just to force a connection to work.

### 8.4. Revocation and revocation status

A certificate can be revoked before it expires. CRL and OCSP are common mechanisms for distributing revocation status. However, **do not assume every default JSSE configuration performs online revocation checking according to your application's desired policy**.

If a system requires revocation checks, explicitly configure and test PKIX/OCSP/CRL per provider, network policy, and operational requirements. Enabling revocation checking may introduce network dependencies on responders or CRL distribution points.

## 9. Hostname Verification: Confirming the Server's Name

### 9.1. Why is a valid chain still not enough?

Suppose:

- The client calls `https://payments.example.com`.
- The server presents a certificate signed by a trusted public CA.
- The certificate's SAN contains only `DNS:marketing.example.com`.

Successful chain validation does not mean the server is `payments.example.com`. The client must check the URL hostname against the certificate's SAN.

This is the hostname verification step. Standard HTTPS clients perform this step automatically.

### 9.2. Do not disable hostname verification

A dangerous anti-pattern:

~~~java
// NEVER use this in an application:
HostnameVerifier trustEveryHost = (hostname, session) -> true;
HttpsURLConnection.setDefaultHostnameVerifier(trustEveryHost);
~~~

This snippet accepts every hostname, even certificates issued to completely different servers. It weakens HTTPS authentication and opens the door to man-in-the-middle attacks.

Another anti-pattern is a TrustManager that accepts every certificate:

~~~java
// NEVER use:
// X509TrustManager.checkServerTrusted(...) { } // left empty
// getAcceptedIssuers() { return new X509Certificate[0]; }
~~~

Disabling chain validation and disabling hostname verification are two independent flaws; keeping only one of the two is still insufficient for secure HTTPS.

### 9.3. HttpClient and HttpsURLConnection

With standard `HttpClient` and `HttpsURLConnection`, keep the default hostname verification configuration. When using a custom `SSLContext`, the goal is changing trust anchors or client identity as needed, **not skipping hostname verification**.

Do not use internal properties or debug flags to disable hostname verification in production. If tests need a mock server, issue test certificates with SANs matching the test hostname and a test CA trusted by the test trust store.

## 10. Using Low-Level SSLSocket and Enabling Endpoint Identification

When opening a TLS socket directly instead of using a high-level HTTPS client, the developer is responsible for configuring endpoint identification properly.

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import java.net.InetSocketAddress;
import java.net.Socket;

String host = "api.example.com";
int port = 443;

SSLContext context = SSLContext.getDefault();
Socket tcp = new Socket();
tcp.connect(new InetSocketAddress(host, port), 10_000);
try (SSLSocket socket = (SSLSocket) context.getSocketFactory()
        .createSocket(tcp, host, port, true)) {

    SSLParameters parameters = socket.getSSLParameters();
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    parameters.setProtocols(new String[] { "TLSv1.3", "TLSv1.2" });
    socket.setSSLParameters(parameters);

    socket.startHandshake();

    System.out.println("TLS protocol: " +
            socket.getSession().getProtocol());
    System.out.println("Cipher suite: " +
            socket.getSession().getCipherSuite());
}
~~~

Key points:

- `setEndpointIdentificationAlgorithm("HTTPS")` requires verifying the endpoint name per HTTPS rules.
- `setProtocols(...)` restricts enabled protocols for this socket per the example policy.
- `startHandshake()` runs the handshake before the application uses the channel.
- `getSession()` reports the negotiated TLS session.

With low-level sockets, do not assume checking the chain via TrustManager alone verifies the hostname. Enable endpoint identification. Also consider SNI, especially when connecting to servers using virtual hosting; creating the socket with the hostname gives the provider the host info needed for SNI in typical configurations.

If connecting by IP address while the certificate only contains a DNS SAN, verification will fail. Use the hostname the certificate was issued for, or issue a certificate with an IP SAN if the contract genuinely uses IP literals.

## 11. Mutual TLS (mTLS): When the Server Also Authenticates the Client

### 11.1. One-way HTTPS vs. mTLS

In regular HTTPS:

- The client verifies the server's certificate.
- The server does not necessarily require a client certificate.

In **mutual TLS (mTLS)**:

- The client verifies the server.
- The server asks the client to present a certificate.
- The client uses its matching private key to prove possession of that identity.
- The server verifies the client certificate against the server's own trust store.

~~~text
Client                              Server
  |                                  |
  | -------- TLS ClientHello ------> |
  | <------- Server certificate --- |
  |                                  |
  | Verify server chain + hostname  |
  |                                  |
  | <----- CertificateRequest ------ |
  |                                  |
  | ----- Client certificate -----> |
  | ----- CertificateVerify ------> |
  |                                  |
  |                         Verify client chain
  |                                  |
  | <======= TLS channel ===========>|
~~~

### 11.2. Creating an SSLContext with KeyManager and TrustManager

Conceptual example:

~~~java
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

static SSLContext createMtlsContext(
        Path clientKeyStorePath,
        char[] clientKeyStorePassword,
        char[] privateKeyPassword,
        Path serverTrustStorePath,
        char[] serverTrustStorePassword
) throws Exception {
    KeyStore clientKeys = KeyStore.getInstance("PKCS12");
    try (InputStream in = Files.newInputStream(clientKeyStorePath)) {
        clientKeys.load(in, clientKeyStorePassword);
    }

    KeyManagerFactory keyManagerFactory =
            KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm()
            );
    keyManagerFactory.init(clientKeys, privateKeyPassword);

    KeyStore serverTrust = KeyStore.getInstance("PKCS12");
    try (InputStream in = Files.newInputStream(serverTrustStorePath)) {
        serverTrust.load(in, serverTrustStorePassword);
    }

    TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm()
            );
    trustManagerFactory.init(serverTrust);

    SSLContext context = SSLContext.getInstance("TLS");
    context.init(
            keyManagerFactory.getKeyManagers(),
            trustManagerFactory.getTrustManagers(),
            null
    );
    return context;
}
~~~

Here:

- The client key store holds the client's private key and certificate chain.
- KeyManagerFactory builds KeyManagers to select the client identity when requested by the server.
- The server trust store holds the CAs/certificates the client trusts when verifying the server.
- TrustManagerFactory builds TrustManagers to verify the server peer.

The server side must also be configured to request client certificates and trust the appropriate client CA. Creating a client SSLContext alone does not enable mTLS if the server does not request it.

### 11.3. Permissions and private key lifecycle

The client's private key is a sensitive asset:

- Never commit key store files or passwords to a repository.
- Restrict file read permissions to the service account.
- Prefer secret managers, HSMs, or appropriate key-management solutions.
- Maintain processes for issuance, rotation, revocation, and auditing.
- Never write private keys or passwords to logs.

Do not use the trust store to hold the client's private key just because both are KeyStore files. The two artifacts serve distinct purposes.

## 12. Configuring TLS via System Properties

JSSE supports system properties to configure the default trust store at JVM startup:

~~~shell
java ^
  -Djavax.net.ssl.trustStore=config/app-truststore.p12 ^
  -Djavax.net.ssl.trustStoreType=PKCS12 ^
  -Djavax.net.ssl.trustStorePassword=<secret-from-runtime> ^
  -jar application.jar
~~~

On Unix shells, use the corresponding line-continuation syntax. Avoid placing real secrets in committed scripts or shell history whenever possible.

System properties affect the JVM's default JSSE configuration and have a broader scope than a single client. If only one `HttpClient` needs a custom trust store, creating a dedicated SSLContext and passing it to the builder is usually easier to control.

When updating a trust store:

- Verify the file exists, keystore type, and password.
- Verify the certificate was imported under the intended alias.
- Verify the CA fingerprint/origin through a trusted channel.
- Verify the application actually uses the new SSLContext/trust store.
- Consider the lifecycle of HttpClient/SSLContext; already-created clients may keep using the old context.

## 13. Diagnosing HTTPS Errors in Java

### 13.1. Common errors

| Symptom | Possible cause | Investigation steps |
|---|---|---|
| `PKIX path building failed` | Unable to build chain to a trust anchor | Check trust store, CAs, and intermediates sent by server |
| `unable to find valid certification path` | CA not trusted or missing chain | Inspect certificate chain and trust anchors |
| `CertificateExpiredException` | Leaf/intermediate/root expired | Check validity dates and machine clock |
| `No subject alternative DNS name matching ...` | SAN does not match URL hostname | Check URL and certificate SANs |
| `No subject alternative names matching IP address ...` | URL uses IP while certificate lacks matching IP SAN | Use proper hostname or issue IP SAN |
| `SSLHandshakeException` | General error during TLS handshake | Inspect nested cause and debug handshake |
| `protocol_version` | No shared TLS version or server supports only legacy versions | Check protocol policies on both ends |
| `handshake_failure` | May stem from ciphers, key algorithm, client auth, or policy | Check server logs and TLS debug output |
| `bad_certificate`/client certificate rejected | mTLS certificate unsuitable or untrusted by server | Check client key store, chain, and server trust |
| `UnrecoverableKeyException` | Wrong private key password or unreadable key entry | Check alias and private key's own password |
| `NoSuchAlgorithmException` | Provider lacks requested algorithm/context | Check JDK/provider and algorithm name |

Do not jump to conclusions from the outermost exception class. `SSLHandshakeException` often wraps a more specific cause such as `CertPathValidatorException`.

### 13.2. Inspecting a server's certificate

`keytool` can display certificates:

~~~shell
keytool -printcert -sslserver api.example.com:443
~~~

You can inspect:

- Subject and issuer.
- Validity.
- SANs.
- Public key and signature algorithm.
- The chain presented by the server.

This command is a diagnostic tool; its output does not replace application security checks, and you should never automatically import a displayed certificate without verifying its trusted origin.

### 13.3. Enabling JSSE debugging safely

To investigate handshakes, you can run in a development environment:

~~~shell
java -Djavax.net.debug=ssl,handshake,trustmanager -jar application.jar
~~~

Logs can be very verbose and contain details about certificates, handshakes, addresses, and configuration. Enable only when needed, restrict access to logs, and disable once investigation finishes. Never use debug logs as a substitute for fixing validation issues properly.

### 13.4. Recommended investigation order

1. Confirm the exact URL, hostname, and port.
2. Confirm the system clock.
3. Inspect the certificate chain sent by the server.
4. Check which trust store the JVM/client is actually using.
5. Check hostname/SAN alignment.
6. Check TLS versions/ciphers/providers.
7. If using mTLS, inspect client certificate and server trust.
8. Enable JSSE debug in a controlled environment if the root cause remains unclear.

Fix the server configuration, certificate, or trust anchor properly. Do not disable chain or hostname verification "just to make it work."

## 14. Testing HTTPS Locally Safely

### 14.1. Using a dedicated test CA

To test clients against self-signed or test-CA servers:

1. Issue a server certificate for the test hostname with matching SANs.
2. Generate a test CA or test certificate following testing procedures.
3. Import the test CA into a separate trust store used exclusively for tests.
4. Connect using a URL whose hostname matches the SAN.
5. Verify both valid cases and hostname-mismatch rejection cases.

Never ship a test CA or test trust store to production.

### 14.2. Scenarios that must be rejected

A thorough test suite should include:

- Certificate signed by an untrusted CA.
- Expired certificate.
- Not-yet-valid certificate.
- Certificate chain missing an intermediate.
- URL hostname not matching SAN.
- Certificate lacking appropriate server authentication purpose.
- No common TLS protocol version.
- Server requiring mTLS when the client presents no certificate.
- Client presenting a certificate from the wrong CA or an expired certificate.

The goal is not only to test successful requests, but also to verify the client **properly rejects invalid peers**.

### 14.3. Do not use trust-all in unit tests

A test can spin up a local server with a test CA and test trust store. That preserves real verification mechanics. A TrustManager that accepts every certificate prevents tests from verifying chain validation and can mask production bugs.

If you are only testing business logic unrelated to TLS, mock at the HTTP boundary or use a test server with valid certificates instead of disabling verification globally.

## 15. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| "HTTPS only needs data encryption." | Server authentication via certificate chain and hostname is also required. |
| "SSLContext checks everything automatically." | SSLContext creates sockets/engines using managers; TrustManager and endpoint identification execute their respective verification steps. |
| "A certificate signed by a trusted CA works for any hostname." | The hostname must match a SAN on the certificate. |
| "Trust store and key store are the same." | A trust store stores trust anchors; a key store typically holds the local side's private key and certificate identity. |
| "A custom trust store simply appends a new CA to the default trust store." | Configuring a trust manager from a custom trust store can replace the default trust anchors; you must manage all required roots. |
| "If the server sends a root certificate, the client trusts it." | The client needs a configured trusted trust anchor; a self-sent certificate does not establish trust. |
| "Disabling hostname verification is how you fix a SAN mismatch." | That strips host identity verification and weakens HTTPS. |
| "A trust-all TrustManager is safe if used only in tests." | It removes chain checks; use a proper test CA and test trust store. |
| "Using `SSLContext.getInstance("TLSv1.3")` is the only way to use TLS 1.3." | You can use a `TLS` context and configure appropriate protocol parameters/policies. |
| "TLS 1.0/1.1 should be enabled if an old server fails to connect." | These protocols are deprecated; upgrade the server or handle exceptions per security policy. |
| "An HTTPS client always needs a client certificate." | Only when the server requires mTLS/client authentication. |
| "Having a valid certificate means revocation was checked." | Revocation checking is a separate configuration/policy; do not assume it is always enabled. |
| "Console charset or default charset affects TLS certificates." | Console charset has nothing to do with verifying certificate chains or hostnames. |

## 16. Complete Example: HTTPS Client with Private CA and Server Verification

File **VerifiedHttpsClient.java**:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;

public class VerifiedHttpsClient {

    static SSLContext loadTrustContext(
            Path path,
            char[] password
    ) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            trustStore.load(in, password);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);
        return context;
    }

    public static void main(String[] args) throws Exception {
        Path trustStorePath = Path.of(
                "config", "internal-ca-truststore.p12"
        );
        char[] password = readSecretFromApprovedSource();

        try {
            SSLContext context =
                    loadTrustContext(trustStorePath, password);

            HttpClient client = HttpClient.newBuilder()
                    .sslContext(context)
                    .connectTimeout(Duration.ofSeconds(10))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(
                            "https://api.internal.example/health"
                    ))
                    .timeout(Duration.ofSeconds(15))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            System.out.println("HTTP status: " + response.statusCode());
            System.out.println(response.body());
        } finally {
            java.util.Arrays.fill(password, '\0');
        }
    }

    private static char[] readSecretFromApprovedSource() {
        // Placeholder: retrieve secret from secret manager or runtime config.
        throw new UnsupportedOperationException(
                "Configure secret source for the deployment environment"
        );
    }
}
~~~

The example shows the core components but intentionally leaves `readSecretFromApprovedSource()` as a placeholder because secret retrieval depends on the deployment platform. When completing it:

- The trust store must be provisioned from a trusted source and contain the required CAs.
- The URL hostname must match a SAN on the server certificate.
- `HttpClient` retains default hostname verification.
- No TrustManager or HostnameVerifier bypasses validation.
- Passwords are never hardcoded in source files.

Compile the code after providing an implementation for the secret loader:

~~~shell
javac --release 17 VerifiedHttpsClient.java
java VerifiedHttpsClient
~~~

## 17. Practice Exercises

### Exercise 1 — Observing default HTTPS

Write an `HttpClient` that sends a GET request to a public HTTPS endpoint you are permitted to access. Print the HTTP status and TLS protocol/cipher if your environment provides a way to inspect them. Explain why no custom TrustManager is required for public CAs trusted by the JDK.

### Exercise 2 — Creating a trust store for an internal CA

In a lab environment, obtain a test CA certificate from a trusted source, verify its fingerprint, and import it into a PKCS12 trust store using `keytool`. Use TrustManagerFactory and SSLContext to configure a dedicated client.

Never arbitrarily import a certificate captured from a failed connection without verifying its origin.

### Exercise 3 — Distinguishing chain validation and hostname verification

Create two test endpoints:

- An endpoint whose certificate chain is trusted by the trust store and whose SAN matches the host.
- An endpoint whose chain is trusted but whose SAN belongs to a different hostname.

Observe that the first succeeds and the second is rejected. Explain why adding the CA to the trust store cannot fix a hostname mismatch.

### Exercise 4 — Analyzing PKIX errors

Try connecting to a test endpoint with a trust store that lacks the corresponding CA. Read the `SSLHandshakeException` and its nested cause. Then add the proper test CA to the trust store and explain what changed.

### Exercise 5 — Using SSLSocket

Open an `SSLSocket` to a test hostname, enable `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`, restrict to TLS 1.3/1.2, and call `startHandshake()`. Test with a hostname that does not match the SAN to confirm the handshake fails.

### Exercise 6 — mTLS

In a lab, create a PKCS12 client key store containing a certificate/private key, a server trust store trusting the client CA, and a client trust store trusting the server CA. Use KeyManagerFactory + TrustManagerFactory to build an SSLContext. Verify that the server rejects a client without a certificate and accepts a client with a valid identity.

### Exercise 7 — Investigating handshakes

Enable `-Djavax.net.debug=ssl,handshake,trustmanager` in a test environment, and read the logs for certificate chain, trust decisions, and protocol negotiation. Explain why debug logging should not stay enabled continuously in production.

## 18. Self-Check Questions

1. Which security properties does HTTPS add over plain HTTP?
2. What is the role of the TLS handshake?
3. How do a certificate chain and a trust anchor differ?
4. Which component of SSLContext does TrustManagerFactory create?
5. In what scenario is KeyManagerFactory used?
6. What is the difference between a trust store and a key store?
7. Why is a valid certificate chain insufficient to verify a hostname?
8. What role do SANs play, and why should you not rely on CN?
9. Why can a custom trust store cause a client to stop trusting default public CAs?
10. Does `SSLContext.getInstance("TLS")` mean only TLS 1.3 is enabled?
11. Why should SSLv3/TLS 1.0/TLS 1.1 not be enabled to work around compatibility errors?
12. How do HttpClient and HttpsURLConnection handle hostname verification by default?
13. When using SSLSocket directly, why must the HTTPS endpoint identification algorithm be enabled?
14. How does mTLS differ from one-way HTTPS?
15. Which category of issues does `PKIX path building failed` usually indicate?
16. Is revocation checking always enabled according to an application's expectations?
17. Why is a TrustManager that accepts every certificate dangerous?
18. How can you test TLS without disabling certificate verification?

## 19. References

- [Java SE 17 API — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): creating contexts, initializing key/trust managers, and creating socket factories.
- [Java SE 17 API — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): creating trust managers from a trust store.
- [Java SE 17 API — KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): creating key managers from a key store.
- [Java SE 17 API — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): configuring protocols, ciphers, and endpoint identification.
- [Java SE 17 API — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): configuring an HTTPS client and SSLContext.
- [Java SE 17 API — HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS via URLConnection and related TLS configurations.
- [Java SE 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): trust stores, key stores, TLS, certificate validation, and JSSE properties.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3 specification.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): rules for verifying service identity and hostnames in TLS.

When implementing HTTPS on Java 17, keep both verification layers intact: **TrustManager validates the certificate chain up to a trust anchor**, and **hostname verification confirms the certificate is issued for the exact host in the URL**. Use `SSLContext` to configure trust and key material as needed, retain modern TLS protocols, and enable mTLS only when the contract requires a client certificate. Never use trust-all managers or always-true hostname verifiers; when a connection fails, fix the chain, SAN, trust store, or TLS configuration at the root cause.
