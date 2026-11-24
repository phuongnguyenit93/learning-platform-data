# 16.7. HttpsURLConnection, HttpClient, and Boundaries for Configuring SSLContext or Hostname Verification

## Learning objectives

After this lesson, you will be able to:

1. Distinguish the two built-in JDK HTTP(S) clients: **`HttpsURLConnection`** (traditional connection style in `java.net`) and **`java.net.http.HttpClient`** (modern HTTP API since Java 11, usable with Java 17+).
2. Identify the responsibilities of **`SSLContext`, `KeyManagerFactory`, `TrustManagerFactory`, truststore, keystore, TLS handshake, certificate chain validation, and hostname/SAN verification** in each client.
3. Understand that **attaching a custom `SSLContext` does not automatically disable or replace hostname verification**; and a valid certificate chain must still match the endpoint name in the URL.
4. Configure **per-HTTP-client trust anchors** without disabling certificate verification; know where `SSLSocketFactory` or `HostnameVerifier` can be customized and where the API has **no** equivalent hook.
5. Recognize the risks of **global defaults**, trust-all managers, always-true hostname verifiers, improper certificate pinning, mTLS configurations missing private keys, or choosing the wrong identity.
6. Run a **Java 17+** lab generating X.509 root/leaf certificates with `keytool`, starting a local HTTPS server, and calling it via both APIs using the **same CA-trusting `SSLContext`**, confirming both receive the JSSE-protected HTTPS response.
7. Design a diagnostic flow when encountering `SSLHandshakeException`/`PKIX path building failed`/hostname mismatch without "fixing errors" by dropping security.

**Scope:** This lesson belongs to **Java Advance – security-cryptography / 16. JSSE**. The primary topic is **TLS configuration and hostname verification boundaries across the two HTTP clients**. The lab uses a self-created CA for learning, not setting up production PKI, OAuth, or full authorization.

---

## 1. Technical problem: Having `https://` is not enough to understand security configuration

In Java 17, the same endpoint:

```text
https://api.example.com/orders
```

can be called in two ways:

```java
// Traditional API:
HttpsURLConnection connection =
        (HttpsURLConnection) new URL(url).openConnection();

// Modern API:
HttpClient client = HttpClient.newHttpClient();
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
```

These are **non-standalone illustrative snippets**: corresponding type imports, `url`/`request` variables, checked exception handling, and proper response reading/closing are required. Complete runnable code is in section 8.

Both APIs can use **JSSE (Java Secure Socket Extension)** to establish TLS, yet their configuration mechanisms and lifetimes differ. **You cannot assume the two APIs share the same TLS state or the same hooks merely because they run in the same JVM.**

### 1.1. What must be guaranteed when accessing HTTPS?

When a client connects to an HTTPS server:

1. The URL explicitly specifies the **`https` scheme**, host, port, path, and query.
2. The TLS connection must negotiate appropriate versions/cipher suites.
3. The server provides an X.509 certificate and the required chain components.
4. The trust manager checks the chain up to a client-approved **trust anchor**, plus PKIX/purpose/validity constraints per policy.
5. The client verifies that the **intended endpoint's hostname or IP literal** matches a Subject Alternative Name (SAN) per HTTPS rules.
6. The TLS handshake verifies the server actually possesses the corresponding private key, authenticates the transcript/`Finished`, and establishes traffic keys.
7. HTTP requests/responses run over the authenticated TLS channel protecting record integrity/confidentiality.
8. The application must still verify business **authentication/authorization**, content-type/size, redirects, SSRF, received data, and key/certificate lifecycle.

**Two checks commonly confused:** (4) *certificate chain trusted* and (5) *certificate issued for the host being accessed* are **two separate conditions**. If you create an `SSLContext` trusting only one specific CA yet disable hostname checking, an attacker holding a different certificate signed by that CA may be mistaken for the target server depending on system risk and policy.

### 1.2. Layer diagram

```text
             URL: https://api.example.com:443/path
                               │
               HTTP client (URL, host, redirects, proxy)
                               │
              TLS configuration / SSLContext
                  ┌────────────┴────────────┐
                  │                         │
             KeyManagers              TrustManagers
       (client's private key)     (peer's trust anchors)
                  │                         │
                  └────────────┬────────────┘
                               │
                JSSE validates certificate path
                               │
             HTTPS endpoint identity / SAN check
                               │
              TLS handshake + authenticated keys
                               │
                      HTTPS request/response
                               │
                       Application policy
```

The diagram shows **logical responsibilities**, not the internal call order of a specific provider. Some certificate chain/hostname checks occur inside the same trust manager flow taking socket/engine parameters.

---

## 2. Comparison table of `HttpsURLConnection` and `HttpClient` in Java 17

| Criterion | `HttpsURLConnection` | `java.net.http.HttpClient` |
| --- | --- | --- |
| Package | `javax.net.ssl.HttpsURLConnection` (opened from `java.net.URL`) | `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse` |
| Style | Per-connection/URL, calling `getInputStream`, `getResponseCode`, etc. | Reusable client, builder-style request/response, with `send`/`sendAsync` |
| HTTP versions | Legacy API typically uses HTTP/1.1; behavior depends on handler | HTTP/1.1 and HTTP/2 when supported; chosen via `HttpClient.Version` |
| Default TLS | JSSE and default SSLSocketFactory/hostname verifier per config | JSSE and default SSLContext if none provided; HTTP stack manages TLS/identity |
| Dedicated SSLContext | No `connection.setSSLContext(...)`; use `context.getSocketFactory()` via `setSSLSocketFactory` | `HttpClient.newBuilder().sslContext(context)` |
| Dedicated truststore | Build trust manager/context then set socket factory on the connection | Build trust manager/context then attach to the client builder |
| Client certificate for mTLS | KeyManagers inside the SSLContext used to create socket factory | KeyManagers inside the HttpClient's SSLContext |
| Hostname verification | Has `setHostnameVerifier` hook and default verifier; **should not be disabled** | **No corresponding public `setHostnameVerifier` builder API**; preserves HTTP client endpoint identification |
| Configuration scope | `setSSLSocketFactory`/`setHostnameVerifier` per instance; `setDefault...` are process-wide defaults for future instances | `sslContext(...)`/`sslParameters(...)` bound when building an `HttpClient`; reuse client appropriately |
| Connection reuse | Handler may keep-alive; must read/close responses properly | Connection pooling and HTTP/2 multiplexing managed by client; reuse instead of creating one client/request |
| Redirects | Depends on `setInstanceFollowRedirects` and handler | `followRedirects(NORMAL/ALWAYS/NEVER)`; defaults to `NEVER` |
| Timeouts | `setConnectTimeout` and `setReadTimeout` | `connectTimeout` on client, `timeout` on request; asynchronous cancellation per its semantics |
| Asynchronous API | Primarily blocking | `sendAsync` returns `CompletableFuture` |
| Proxy customization | `openConnection(Proxy)` or JVM handler policy | `proxy(ProxySelector)` on builder |
| Things to watch | Global defaults, instance lifetime, input/error streams, redirect & response ownership | Shared client config, pooling, async, proxy/HTTP2; do not rely on internal flags disabling hostname checks |

**A single `SSLContext` can be used by both APIs**, yet each API retains its own HTTP/hostname/redirect/proxy configuration. Not all behaviors, TLS session reuse, ALPN, or HTTP/2 behave identically after setting the same context.

### 2.1. Why are there two APIs?

`HttpsURLConnection` is the long-standing option: easy to apply for simple HTTP calls, widespread in legacy Java apps, older frameworks, and traditional proxy/URL handlers. `HttpClient` is the modern API: request builders, response handlers, reusable clients, async, HTTP/2, and clear redirect/timeout policies.

Do not switch APIs just believing "HttpClient is always more secure" or "HttpsURLConnection always skips hostname checks." **Both can verify TLS safely when configured properly; both can be broken if you use trust-all, fail to protect keys, or mishandle URLs/proxies.**

---

## 3. What does `SSLContext` do and not do?

In JSSE, `SSLContext` combines:

- **`KeyManager[]`**: selects **this side's own** private key/certificate identity when TLS needs client authentication (for an HTTP client) or server authentication (for an HTTPS server).
- **`TrustManager[]`**: verifies the **peer's** certificate based on trust anchors and policy.
- **`SecureRandom`**: appropriate randomness source for the provider's TLS operations.
- TLS parameters/implementations managed by JSSE/provider.

Brief initialization:

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, new SecureRandom());
```

This is a **non-standalone illustrative snippet** requiring imports `javax.net.ssl.SSLContext`, `java.security.SecureRandom`, and pre-configured `keyManagers`, `trustManagers` variables. The string `"TLS"` selects the TLS protocol engine; **it does not mean the application automatically sets safe SSL versions, hostnames, or trust policies** with a single line of code.

### 3.1. `SSLContext` does not decide the target URL on its own

In an HTTPS application:

- The URL/request defines the intended hostname to access;
- the context defines key/trust infrastructure;
- the HTTP/TLS client decides how to combine the **hostname in the URL** with the certificate in the handshake.

If you use a custom `SSLContext`, **do not assume hostname verification is disabled**. Nor should you assume an `SSLContext` returned by an API suffices to verify hostnames if using a **raw `SSLSocket`** without configuring endpoint identification. The key boundary is **who holds the intended hostname and who enforces endpoint identity rules**.

### 3.2. Truststore and keystore are different

```text
One-way HTTPS client:
    Truststore: accepted CA/root or server certificate
    KeyStore:   usually NO client private key needed

HTTPS client using mTLS:
    Truststore: CA/root trusting the server
    KeyStore:   client private key + client cert chain

HTTPS server:
    KeyStore:   server private key + server cert chain
    Truststore: CA/root trusting the client if server requires mTLS
```

**Never copy the server private key into the client truststore.** A truststore holds public trust anchors/certificates, though its integrity is critical; a keystore holds private material that must be protected from unauthorized read/write access.

`KeyManagerFactory` and `TrustManagerFactory` are two separate pieces:

```java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identityStore, password);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);
```

This is **non-standalone illustrative code** requiring imports, variables, and exception handling. For a one-way HTTPS client needing no identity key, you can pass `null` for key managers in `SSLContext.init(...)`, yet valid trust managers are still needed.

### 3.3. `tmf.init(customStore)` usually replaces trust anchors rather than appending

A real-world pitfall occurs when an app needs to trust an internal CA and writes:

```java
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(internalTrustStore);
```

Then developers are surprised when public HTTPS sites are no longer accepted. **When initialized from a KeyStore containing only an internal CA, the trust manager normally trusts only the anchors in that store**, not automatically merging with the JDK's default truststore.

Design options:

1. **Separate clients by trust domain:** one `HttpClient` trusting only the internal CA; another client using default trust anchors for the public Internet.
2. **Build a managed truststore containing the exact needed roots:** controlled merging from trusted sources, updated per lifecycle; never arbitrarily add every CA received over the network.
3. **Make trust decisions based on specific policy/protocol** if the organization requires pinning or custom PKIX, preferring evaluated libraries/providers.

**Do not** write a custom `X509TrustManager` that "tries all of them and trusts if one succeeds" without understanding endpoint/algorithm constraints, exception handling, and trust scope. A custom trust manager can inadvertently drop hostname/purpose checks.

### 3.4. Default SSLContext and JVM system properties

When no custom context is set, JSSE can use the default truststore/JDK configuration (e.g., `cacerts`, `javax.net.ssl.trustStore` property and truststore password/type, provider policies). **Do not assume every JVM/container has the same set of root CAs**: JDK distributions, images, OSes, and enterprise policies can differ.

Illustrative command configuring a **dedicated truststore for a Java process**:

```shell
java -Djavax.net.ssl.trustStore=truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.trustStorePassword=changeit YourApp
```

This command only works if `YourApp` exists, uses corresponding JSSE default trust managers, and runs in the directory containing the file. This is **not the main lab**; the main lab passes `SSLContext` explicitly. Avoid putting real passwords on command lines or public configs.

**Important:** a code path that creates an `SSLContext` with a custom `TrustManagerFactory` and passes it into the client **is not necessarily overridden** by JVM `javax.net.ssl.trustStore`. Distinguish **JVM default context** from **per-client explicit context** when debugging.

---

## 4. Hostname verification is a separate identity check

A certificate for `api.example.com` typically contains:

```text
Subject: CN=Example API
Subject Alternative Name:
  DNS:api.example.com
  DNS:orders.example.com
Issuer: Trusted CA / Intermediate CA
Public key: ...
```

Suppose that certificate has a valid chain to a CA in the truststore. When the client calls `https://admin.example.com`, the chain can still be valid, yet **the hostname does not match the SAN**. A secure HTTPS client **must reject it**.

### 4.1. Two conditions with AND, not OR

```text
            Server certificate
                │
        ┌───────┴───────────┐
        ▼                   ▼
  PKIX trust path      Endpoint identity
  / trusted CA         / hostname or IP SAN
        │                   │
        └───────── AND ─────┘
                     │
               Peer accepted
             (subject to other
               TLS policies)
```

`Certificate chain valid` only answers "was the certificate issued by a valid issuer chain from an approved trust anchor?". `Hostname valid` answers "is the certificate valid for the **target name the application requested**?". Never compromise on either.

In modern HTTPS, name matching relies on **SAN**, not "matching a CN substring." If the URL uses an IP literal, an **iPAddress** SAN is required; do not treat `DNS:127.0.0.1` as equivalent. For Unicode/IDNA domains, wildcards, and multiple identifier types, **use a standard endpoint identity implementation** instead of homemade `String.contains`/regex.

### 4.2. `HostnameVerifier` of `HttpsURLConnection`

`HttpsURLConnection` has:

```java
HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
connection.setSSLSocketFactory(sslContext.getSocketFactory());
// Do not call setHostnameVerifier(...) when using standard verification.
```

This is illustrative; `url` and `sslContext` must be created beforehand. **Keep the default verifier** for HTTPS unless you are genuinely implementing a verified alternative identity policy; supplying a custom verifier easily breaks hostname validation.

Some APIs expose `setDefaultHostnameVerifier(...)` at JVM/handler default scope, affecting connections created afterward. Never treat a global operation as a "change just one request" option. Avoid relying on mutable global defaults in multi-threaded or multi-tenant services.

#### Extremely dangerous anti-pattern

```java
// WRONG: bypasses hostname verification!
connection.setHostnameVerifier((hostname, session) -> true);
```

An attacker can present a valid certificate for **another name**, or combine it with an overly broad trust configuration to perform MITM. When encountering a hostname mismatch, fix the URL/certificate SAN or PKI issuance; **never** change the verifier to always-true.

### 4.3. `HttpClient` has no public `setHostnameVerifier`

`java.net.http.HttpClient` allows:

```java
HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .build();
```

This is illustrative, requiring `import java.net.http.HttpClient;` and an `sslContext` variable. In standard usage, the HTTP client performs HTTPS endpoint identification during TLS per implementation policy. **There is no `HttpClient.Builder.hostnameVerifier(...)`** to attach a callback like `HttpsURLConnection.setHostnameVerifier`.

`HttpClient.Builder.sslParameters(SSLParameters)` can adjust supported TLS parameters; it is not a per-URL hostname verifier hook. Parameters disallowed by the implementation may be ignored depending on JDK/provider. **Never rely on `sslParameters` or internal JVM flags to disable hostname checking.**

Likewise, do not use internal properties like `jdk.internal.httpclient.disableHostnameVerification` to work around errors. That is neither a secure design nor a stable public API; disabling endpoint identity introduces MITM risk.

### 4.4. Raw `SSLSocket` is a different story

If using `SSLSocket` directly instead of an HTTP client:

```java
SSLSocket socket = (SSLSocket)
        sslContext.getSocketFactory().createSocket("api.example.com", 443);
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
```

This is **not a standalone program**. Do not assume raw `SSLSocket` automatically verifies URL names when the app has not specified an algorithm; the raw socket API does not understand HTTP host semantics at the same level as an HTTP client. When using `HttpClient`/`HttpsURLConnection`, **preserve** the client's own standard hostname verification mechanism.

---

## 5. Configuring `HttpsURLConnection`: instance scope vs. global defaults

Common usage sequence:

1. Create a `URL` starting with `https://`.
2. Obtain `HttpsURLConnection` from `url.openConnection()`.
3. Before connecting, call `connection.setSSLSocketFactory(sslContext.getSocketFactory())`.
4. Set timeouts and required HTTP headers/verb.
5. Read `getResponseCode()` and response/error streams properly, then close them.
6. Call `disconnect()` when the connection is no longer needed; note that underlying HTTP keep-alive has handler pooling rules.

```java
HttpsURLConnection connection =
        (HttpsURLConnection) new URL("https://api.example.com").openConnection();
connection.setSSLSocketFactory(sslContext.getSocketFactory());
connection.setConnectTimeout(5000);
connection.setReadTimeout(5000);
try {
    int status = connection.getResponseCode();
    // Read the proper input/error stream and handle status.
} finally {
    connection.disconnect();
}
```

This is a **non-standalone illustrative snippet** requiring imports, `sslContext`, and exception handling. **Do not attach an unverified `HostnameVerifier`.**

### 5.1. Instance scope vs. global default

| Call | Meaningful scope |
| --- | --- |
| `connection.setSSLSocketFactory(factory)` | Factory for this `HttpsURLConnection` object, before connecting |
| `connection.setHostnameVerifier(verifier)` | Hostname policy callback for this instance; never use to bypass |
| `HttpsURLConnection.setDefaultSSLSocketFactory(factory)` | Changes the default factory for future instances per API behavior; affects other parts of the JVM |
| `HttpsURLConnection.setDefaultHostnameVerifier(verifier)` | Changes the default verifier for future instances; can break identity checking broadly |
| `SSLContext.setDefault(context)` | Changes the JVM default SSLContext; do not treat as a per-URL setting |

In multi-threaded/multi-tenant/multi-library web apps, **never mutate global defaults while handling a request**. Other threads may open connections while defaults are altered; previously created clients may still retain old factories. Choose **per-connection factories** or clients built specifically per trust domain.

### 5.2. Limitations and traits of the legacy API

- Response code/status and input vs. error streams must be handled explicitly; `getInputStream` can throw exceptions for HTTP error statuses.
- Timeouts/caching/redirects and keep-alive are managed by `HttpURLConnection`/handler. Never treat a single instance as an infinitely concurrent immutable client.
- Avoid long blocking I/O on critical event-loops.
- Each `openConnection` call yields a new connection object; the underlying network connection may be reused per policy, so do not assume a fresh handshake on every HTTP request.
- When redirecting from host A to B, evaluate security policy: credentials/authorization headers, host allowlists, and TLS identity of the **destination host**; a truststore alone does not prevent SSRF/open redirects.

---

## 6. Configuring `HttpClient`: reusable client, per-client TLS context

In Java 17, the modern pattern:

```java
HttpClient client = HttpClient.newBuilder()
        .sslContext(customSslContext)
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NEVER)
        .version(HttpClient.Version.HTTP_1_1)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/orders"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

This is a **non-standalone illustrative snippet**: `java.net.http.*`, `java.net.URI`, `java.time.Duration`, `java.nio.charset.StandardCharsets` imports, `customSslContext`, and exception handling are required. The complete runnable version is in section 8.

### 6.1. Why reuse `HttpClient`?

`HttpClient` is designed to be reused across many requests: it manages connections, HTTP/2 streams, threads, and internal TLS sessions. Creating a new `HttpClient` per HTTP request forfeits reuse and increases handshake/connection setup overhead. **However, reuse must align with trust domains**: if tenant A uses a dedicated CA, do not put that CA into one client trusted across all tenants just for reuse.

A service design:

```text
ClientRegistry
 ├─ publicApiClient   : default/public trust policy
 ├─ internalApiClient : enterprise CA truststore
 └─ partnerClient     : partner CA + client identity (mTLS)

Each client:
  SSLContext fixed when built
  connection pool and HTTP protocol policy
  URL/host allowlist + request authorization policy
```

The URL in `HttpRequest` determines the endpoint. `HttpClient` is built with a specific `SSLContext`; for truststore changes or certificate rotation, build a new client/context under controlled lifecycle management and migrate/close associated sessions per JDK/framework behavior. Never assume editing `truststore.p12` on disk immediately updates keys/trust anchors in already-running `HttpClient` instances.

### 6.2. What is `sslParameters(...)` for?

`HttpClient.Builder.sslParameters(SSLParameters)` lets you specify a set of SSL/TLS parameters, such as protocols/cipher suites per policy if accepted by the provider/implementation. However, per the Java API, **some parameters may be disallowed or ignored** in the `HttpClient` context.

Never pass an `SSLParameters` with an empty endpoint identification to "skip hostname checking." When non-standard hostname verification is needed (such as workload URI identity), choose a supported protocol/HTTP stack and identity verification layer rather than bypassing TLS and doing unsafe string comparisons yourself.

### 6.3. Redirects, async, and proxies are separate responsibilities from TLS trust

- Default is `HttpClient.Redirect.NEVER`; if redirects are enabled, requests may travel to another host, and the **new URL must be evaluated** against policy/allowlists. An SSLContext trusting multiple CAs will not stop redirection to unintended endpoints.
- `sendAsync` returns `CompletableFuture`; exceptions may be wrapped in `CompletionException`; never swallow TLS errors and treat requests as successful.
- Proxies may use `ProxySelector`; if a proxy terminates TLS (gateway/SSL inspection), the certificate observed by JSSE may be issued by an enterprise CA. Trust that CA only when backed by organizational policy; **never disable certificate checks** just because of a proxy.
- HTTP/2/ALPN does not replace verifying the certificate chain and endpoint name.
- Read body streams/responses within limits; `HttpClient` has a different resource lifecycle and body handler model than legacy `getInputStream`.

### 6.4. `HttpClient.sslContext()` only tells you the context, not that identity was verified

`client.sslContext()` returns the configured context used by the client. An `SSLContext` object could have been created with a broken trust-all manager. **Never verify security merely by asserting `client.sslContext() != null`.** Write integration tests with untrusted CAs, mismatched SANs, expired certs, and matching `clientAuth` policies.

---

## 7. Same truststore, yet results can still differ

Suppose two HTTP clients share the same `sslContext` trusting an internal root CA. Why can outcomes still differ?

| Difference | Example | How to check |
| --- | --- | --- |
| URL/hostname | Legacy calls `localhost`, modern calls `127.0.0.1` | DNS SAN vs. iPAddress SAN |
| Proxy | One client uses an enterprise proxy, the other goes direct | Certificate visible at TLS endpoint, proxy policy |
| Redirect | One client follows a redirect to another host | New host, credential forwarding, trust policy |
| TLS protocols/ciphers | One side forces TLS 1.3, the other's provider picks TLS 1.2 | Enabled protocols, JSSE debug |
| Client identity | One context has a `KeyManager`, the other does not | mTLS `CertificateRequest`, alias, EKU |
| Trust anchors | Newer client built post-rotation, old client holds prior context | Keystore reload/rebuild, truststore inventory |
| Connection pool | Reused connection/session vs. fresh full handshake | TLS session identity, resumption, and logs |
| Hostname policy | Legacy has unsafe custom `HostnameVerifier`, modern uses strict default | Remove unsafe overrides; check SAN and endpoint |
| HTTP version | HTTP/1.1 vs. HTTP/2, ALPN | Request format/network behavior, **never a reason to turn off TLS** |
| JVM configuration | Different system properties, security providers, or internal flags | Effective runtime, process config, build/deployment |

**Logical debugging order:** check URL/port/SAN → trust chain/root → key usage/EKU → SSLContext & key managers → TLS protocol/proxy → HTTP redirects/body. Never change both the trust manager and hostname verifier at the same time; you will lose track of where the real failure lies.

---

## 8. Java 17+ lab: local HTTPS server + two HTTP clients

The lab uses a **training root CA** to sign a `localhost` certificate, and then both clients trust that root via **`truststore.p12`**. Both access a **real HTTPS endpoint** inside the JVM while preserving standard JDK hostname checking.

**Assets:**

- `ca.p12`: contains the training CA's private key; **do not pass into client applications**.
- `ca.pem`: public root CA certificate.
- `server.p12`: server private key + `DNS:localhost` leaf certificate + chain.
- `truststore.p12`: **contains only the trusted public CA certificate**, no private key.
- `HttpsClientsLab.java`: starts a local HTTPS server and runs both `HttpsURLConnection` and `HttpClient` with the same client `SSLContext`.

**Lab security:** the password `changeit` and private CA key are for learning only; never use in production. Run in an **empty lab directory**, never overwrite real keystores, and never add the demo root into system `cacerts`. Putting passwords on the command line is solely for the lab; production must never expose passwords via shell history/process lists.

### 8.1. Generating a simulated root CA

```shell
keytool -genkeypair -alias training-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=HTTPS Lab Root CA, O=Training, C=VN" -validity 3650 -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -keystore ca.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
```

Export the public CA certificate:

```shell
keytool -exportcert -alias training-ca -keystore ca.p12 -storepass changeit -file ca.pem -rfc
```

**Do not use the CA certificate itself as the server certificate.** In this lab the root directly signs the leaf (path length without an intermediate). A real system may use intermediate CAs, HSMs, and specific issuance policies.

### 8.2. Creating the server private key and CSR for `localhost`

```shell
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost, O=Training, C=VN" -validity 365 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
keytool -certreq -alias localhost -keystore server.p12 -storepass changeit -file localhost.csr -ext "SAN=dns:localhost"
```

The CSR requests a certificate binding the server's public key to `localhost`, yet it is **not yet a trusted certificate**; the CA will issue the leaf per policy.

### 8.3. Root signs the server leaf with exact SAN and EKU

```shell
keytool -gencert -alias training-ca -keystore ca.p12 -storepass changeit -infile localhost.csr -outfile server.pem -rfc -validity 30 -ext "SAN=dns:localhost" -ext "KU:critical=digitalSignature" -ext "EKU=serverAuth" -ext "BC=ca:false"
```

Import the CA and then the certificate reply into the server keystore, ensuring the private-key entry holds the chain:

```shell
keytool -importcert -alias training-ca -file ca.pem -keystore server.p12 -storepass changeit -noprompt
keytool -importcert -alias localhost -file server.pem -keystore server.p12 -storepass changeit -noprompt
```

`server.p12` holds the **server private key**; `server.pem` is only the public certificate copy, excluding the private key.

### 8.4. Client trusts the root in a separate truststore

```shell
keytool -importcert -alias training-ca -file ca.pem -keystore truststore.p12 -storetype PKCS12 -storepass changeit -noprompt
```

This is the client's **trust decision** in the lab. Never import this root into the system-wide JVM truststore. Using an unknown root from an unverified channel allows attackers to make the client trust forged certificates.

Inspect the target fields before running:

```shell
keytool -printcert -file server.pem
keytool -list -v -keystore server.p12 -storetype PKCS12 -storepass changeit
keytool -list -v -keystore truststore.p12 -storetype PKCS12 -storepass changeit
```

Expect to see `SAN=dns:localhost`, `ExtendedKeyUsage=serverAuth`, server `PrivateKeyEntry`, and root `trustedCertEntry`; serials, fingerprints, and timestamps vary, so **there is no fixed stdout for keytool**.

### 8.5. Complete Java program

Create **`HttpsClientsLab.java`** in the same directory as `server.p12` and `truststore.p12`:

```java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class HttpsClientsLab {
    private static final char[] LAB_PASSWORD =
            "changeit".toCharArray(); // DEMO ONLY

    private static KeyStore load(String path) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            store.load(in, LAB_PASSWORD);
        }
        return store;
    }

    private static SSLContext context(String ownKeyStore)
            throws Exception {
        KeyManager[] keys = null; // HTTPS client one-way: no client cert.
        if (ownKeyStore != null) {
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(load(ownKeyStore), LAB_PASSWORD);
            keys = kmf.getKeyManagers();
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(load("truststore.p12")); // Explicit trusted CA(s).

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys, tmf.getTrustManagers(),
                new SecureRandom());
        return context;
    }

    private static String legacyGet(String endpoint,
            SSLContext tlsContext) throws Exception {
        HttpsURLConnection connection = (HttpsURLConnection)
                new URL(endpoint).openConnection();
        connection.setSSLSocketFactory(
                tlsContext.getSocketFactory());
        // No unsafe custom HostnameVerifier: HTTPS name checked normally.
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(5000);
        try {
            int status = connection.getResponseCode();
            if (status != 200) {
                throw new IllegalStateException(
                        "Legacy HTTP status: " + status);
            }
            try (InputStream in = connection.getInputStream()) {
                return new String(in.readAllBytes(),
                        StandardCharsets.UTF_8).trim();
            }
        } finally {
            connection.disconnect();
        }
    }

    private static String modernGet(String endpoint,
            SSLContext tlsContext) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .sslContext(tlsContext)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(endpoint))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Modern HTTP status: " + response.statusCode());
        }
        return response.body().trim();
    }

    public static void main(String[] args) throws Exception {
        SSLContext serverContext = context("server.p12");
        SSLContext clientContext = context(null);

        HttpsServer server = HttpsServer.create(
                new InetSocketAddress("localhost", 0), 0);
        server.setHttpsConfigurator(
                new HttpsConfigurator(serverContext));
        server.createContext("/hello", exchange -> {
            byte[] body = "OK\n".getBytes(StandardCharsets.UTF_8);
            try {
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream output =
                        exchange.getResponseBody()) {
                    output.write(body);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            String endpoint =
                    "https://localhost:" + port + "/hello";
            String legacy = legacyGet(endpoint, clientContext);
            String modern = modernGet(endpoint, clientContext);

            System.out.println("legacyBody=" + legacy);
            System.out.println("modernBody=" + modern);
            System.out.println(
                    "bothReadSamePayload=" + legacy.equals(modern));
            System.out.println(
                    "separateKeyAndTrustManagers=true");
        } finally {
            server.stop(0);
        }
    }
}
```

**Why does this example observe the right boundaries?**

- The HTTPS server gets its **server private key** from `server.p12` via `KeyManagerFactory`.
- Both HTTP clients get the **CA-containing truststore** via `TrustManagerFactory`, without a private-key identity (since this is one-way HTTPS).
- `HttpsURLConnection` sets the context via `setSSLSocketFactory` on the **instance**, not changing global defaults; keeps the default hostname verifier.
- `HttpClient` takes `sslContext` on the **builder**, with no custom verifier; both call `https://localhost:port/hello`, matching `SAN DNS:localhost`.
- The server binds an ephemeral port (`0`) to avoid colliding with running services; accesses only the local lab endpoint.
- Both requests are read over the JSSE HTTPS channel; the program **does not manually implement TLS handshakes or AES**.
- Only fixed application-level values are printed; **no private keys, truststore passwords, certificate fingerprints, or session secrets are printed**.

### 8.6. Compiling and running on Java 17+

The `jdk.httpserver` module contains `com.sun.net.httpserver.HttpsServer` and `HttpsConfigurator`. Use explicit flags so the module resolves at both compile time and runtime:

```shell
javac --add-modules jdk.httpserver HttpsClientsLab.java
java --add-modules jdk.httpserver HttpsClientsLab
```

**Expected stdout** after creating keystore/truststore in steps 8.1–8.4 and running in the lab directory on a standard JDK 17 supporting RSA/PKCS12/JSSE:

```text
legacyBody=OK
modernBody=OK
bothReadSamePayload=true
separateKeyAndTrustManagers=true
```

Serials/fingerprints and random TLS session keys are not printed, so the program's stdout does not depend on them. If `server.p12` or `truststore.p12` is missing, the password is wrong, private key/chain is missing, or the root is untrusted, the program **does not** print those lines and instead throws an exception; that is a useful security check, not a reason to disable TLS.

### 8.7. What did the lab intentionally omit?

- This is a local educational HTTPS server, **not a production web server**. There is no auth/token, IAM, quota, rate limiting, request validation, multiple handlers, monitoring, revocation/OCSP infrastructure, certificate rotation, or HSM/KMS.
- There is no client certificate/mTLS yet. Implementing mTLS requires adding a **client private key/certificate chain**, configuring the server to require client certificates, and adding a truststore for the client CA; never just call `setNeedClientAuth(true)` without configuring keystores/trust managers.
- The program contains no negative tests altering the hostname: default behavior is preserved, while negative tests are guided in section 9.
- `HttpsServer` uses default TLS parameters from `HttpsConfigurator`. Production must enforce protocol/cipher suites, key/certificate lifecycles, and resource controls per policy.
- Configuring a dedicated root CA truststore in the lab means **not trusting the entire public Web PKI by default**; this is an intentional scope.

---

## 9. Failure tests to verify boundaries

Run only against the **lab certificate/truststore set**; never modify production or system truststores. Check the outcome and actual exception type/certificate chain rather than **matching exact exception message text**, which varies by JDK/provider/OS.

### 9.1. Test 1 – Untrusted certificate chain

Create `untrusted.p12` without `training-ca` or the CA signing the server leaf. Build a new `SSLContext` from that store and pass it to each API. Connections will be rejected when the peer cannot build a trust path to a trust anchor; errors typically include `SSLHandshakeException`, `PKIX path building failed`, or `unable to find valid certification path`.

**Never fix with trust-all:** import the properly approved root CA into the truststore via a trusted channel and maintain a valid certificate chain.

### 9.2. Test 2 – Hostname does not match SAN

The server certificate has only `SAN DNS:localhost`. If the server is still reachable at `127.0.0.1` while the request URL is `https://127.0.0.1:port/hello`, HTTPS endpoint identification must check `iPAddress` SANs and reject when the certificate **lacks** `IP:127.0.0.1`.

**Note:** an environment might map `localhost` to IPv6 `::1`, IPv4 `127.0.0.1`, or other hosts settings; if connecting via IP literal fails at TCP, that is a **connection error**, not proof that hostname checking ran. To test reliably, bind the test server to the right interface with clear SAN/connection setup, then inspect the name-related exception.

Never solve with `connection.setHostnameVerifier((h,s) -> true)`. For clients needing to call an IP literal, the certificate must have the matching IP SAN, or use a certified DNS hostname.

### 9.3. Test 3 – Swap server certificate while keeping the trusted root CA

Generate a new leaf signed by the **same root CA**, but with SAN containing only `DNS:other.example`. The chain can still validate to the trust anchor, yet a request to `https://localhost` **must be rejected** due to identity mismatch.

This test proves **a truststore trusting a CA is not an allowlist of automatically accepted hosts**. One CA can issue many certificates for many names; the client checks the exact name for each URL.

### 9.4. Test 4 – mTLS client missing private key

If the server requires `clientAuth`, merely importing the public client certificate into the client truststore does not enable the client to prove possession of a private key. The client needs a **`PrivateKeyEntry` with cert chain** in its keystore, `KeyManagerFactory` loading the right entry, and the server trusting the client CA. Never repurpose a `clientAuth` cert for `serverAuth` arbitrarily.

### 9.5. Test 5 – Danger of global defaults

A JVM runs service A trusting partner A's CA and service B trusting partner B's CA. If service A calls `HttpsURLConnection.setDefaultSSLSocketFactory(factoryA)` at startup or during a request, other connections created later may inadvertently use trust configuration A.

**Proper design:** build `SSLContext` per trust domain, use `setSSLSocketFactory` per legacy connection or `HttpClient.Builder.sslContext` per reusable client. Global settings should be applied only when the **entire process genuinely shares one policy** and is managed as deployment config.

---

## 10. mTLS across both APIs: what configuration changes?

In **one-way HTTPS**, the client needs a trust manager to verify the server, without needing a client private key. In **mTLS**, the client must have a private key/certificate chain, and the server must request and authenticate the client certificate.

Similar to a context-creation method in the lab:

```java
SSLContext clientTls = context("client.p12");
```

This is **only an illustrative snippet**: `client.p12` must exist, hold a `PrivateKeyEntry` with `clientAuth` EKU, and the server's CA must be trusted in the truststore. `context(...)` in the lab also initializes `TrustManagerFactory` so the **client continues verifying the server**. This line alone **does not force the server to require clientAuth**; the server must be configured accordingly.

### 10.1. `HttpsURLConnection` with mTLS

```java
connection.setSSLSocketFactory(clientTls.getSocketFactory());
```

This sets the **identity/trust context** on the legacy connection. When the server sends `CertificateRequest` during the handshake, the JSSE key manager picks a matching client certificate to present. Never confuse the client keystore with the server truststore.

### 10.2. `HttpClient` with mTLS

```java
HttpClient mtlsClient = HttpClient.newBuilder()
        .sslContext(clientTls)
        .build();
```

This sets the context on the builder. mTLS works if the server actually requests it and both sides have policy-compliant keys/certificates/trust chains. There is no standard `HttpClient.Builder.clientCertificate(...)` shortcut replacing `KeyManagerFactory` in a single step.

### 10.3. Selecting a client certificate is more than "having a file"

If the keystore holds multiple aliases/certificates, `X509KeyManager`/`X509ExtendedKeyManager` can select based on key type, CA hints, signature algorithms, TLS version, and provider. An alias with wrong `clientAuth`, a private key mismatched with the chain, or an identity unapproved by the server will cause the handshake to fail. Depending on framework/JDK, controlled alias selection policy may be needed; **never drop trust/hostname validation to fix key selection errors**.

### 10.4. mTLS and authorization

Even after the server successfully authenticates the client certificate, the server must still map the identity (SAN URI, DNS, Subject DN per CA policy) to a principal and check **role, tenant, object, and action**. Having a client certificate does not automatically grant `admin` privileges. If mTLS terminates at a proxy/service mesh, the application must trust only the verified source of forwarded principals and block client-spoofed headers.

---

## 11. Common errors and how to diagnose them

| Symptom | Root-cause area | Action to take |
| --- | --- | --- |
| `PKIX path building failed` | Truststore missing root, chain missing intermediate, disallowed CA | Check trust anchors and chain on the **client side**; import via authorized channel |
| `No subject alternative names matching IP address` | URL uses IP while cert has only DNS SAN | Issue proper IP SAN or use a certified DNS hostname |
| `No name matching ... found` | DNS SAN does not match URL hostname | Check URL/SAN/certificate issuance; never disable hostname verifier |
| `certificate_unknown`/`bad_certificate` | Peer rejects cert/chain/purpose | Check issuer, EKU, KU, validity, protocol, and trust managers |
| `certificate_required`/`Empty client certificate chain` | Server requires mTLS yet client lacks identity key | Load client keystore into KeyManagerFactory; check chain/alias |
| `handshake_failure` | TLS version/cipher/signature incompatibility or auth failure | Check effective protocols, cert/key types, and JSSE debug |
| `UnrecoverableKeyException` | Wrong keystore/entry password or inaccessible private key | Check keystore path, alias, provider, and secret source |
| `FileNotFoundException` | Store file not in process working directory | Use explicit paths and check deployment filesystem |
| HTTPS returns `401`/`403` post-handshake | App rejects token/role/tenant | Check application auth; do not blindly tweak TLS |
| Legacy succeeds, modern fails `PKIX` | Clients use different SSLContexts/truststores, proxies, or certs | Record context source, URL, and truststore policy; never assume same JVM ⇒ same trust |
| Legacy succeeds, modern reports wrong hostname | Legacy has unsafe custom HostnameVerifier or different URL | Restore standard hostname verification; check certificate SAN |
| One HttpClient calls multiple domains needing separate CAs | Trust scope too broad or misconfigured | Use separate clients per trust domain/policy |
| Old cert still used after CA rotation | Pre-built context/client; connections reuse sessions | Controlled rebuild/reload and truststore update |
| System works when validation is disabled | Config or actual certificate is wrong; test masks MITM risk | Never put bypasses in production; fix root cause |
| Client follows redirect to off-allowlist host | Redirect policy/SSRF/credential forwarding | Disable or validate redirect targets, secrets, and host policy |
| Proxy swaps TLS certificate | TLS termination/enterprise inspection | Identify organization-approved proxy/CA policy |

### 11.1. Controlled JSSE debugging

Debugging can be enabled in a lab environment:

```shell
java -Djavax.net.debug=ssl,handshake,trustmanager --add-modules jdk.httpserver HttpsClientsLab
```

The command produces many debug lines about handshakes, trust managers, and certificate chains; stdout/stderr are **not fixed** across JDKs/providers. **Never leave sensitive debugging on long-term in production**, and never place private keys, tokens, plaintext, or out-of-scope identity data into logs.

A practical debug checklist:

1. Record the exact URL/hostname/port each API uses.
2. Identify any proxy/redirect/TLS termination changing the real endpoint.
3. Check the server leaf `SAN`, validity window, `serverAuth` EKU, and intermediates.
4. Determine **which root CA** the trust manager loaded, from default store or custom store.
5. Check the client identity `KeyManager` if using mTLS.
6. Check provider/JDK TLS version/cipher suites, `jdk.tls.disabledAlgorithms`, and TLS session reuse.
7. If the certificate is trusted yet host mismatches, **fix host/SAN**, not the trust manager.
8. If the host matches yet the chain is untrusted, **fix truststore/chain**, not the hostname verifier.

### 11.2. A valid certificate signature is not enough

`cert.verify(issuerPublicKey)` may succeed while the server is still rejected because:

- the issuer public key is not a trusted CA;
- path constraints, key usage, or critical extensions are invalid;
- the cert is expired or revoked;
- the SAN hostname does not match the URL;
- the peer failed to prove private-key possession during the handshake;
- the TLS/certificate algorithm is disallowed by policy.

**Do not "fix" by verifying the issuer signature yourself and skipping JSSE/HTTPS validation.** Maintain the entire validation chain per protocol.

---

## 12. Boundaries beyond `SSLContext`

### 12.1. Certificate pinning

**Pinning** binds an approved certificate/public key/SPKI or key set to a service to narrow the trust surface. However, pinning **must never be an excuse to arbitrarily skip CA/hostname validation**. Plan for rotation, backup pins, pin-set updates, and proper recovery mechanisms so you do not lock yourself out when certificates rotate.

`HttpClient` has no public `HostnameVerifier` callback like legacy. If the organization requires pinning, prefer fully evaluated libraries/providers/HTTP stacks or custom trust logic; preserve **trust, identity, and lifecycle** rather than merely comparing fingerprints or disabling hostname checks. Pinning suits specific threat models and should not be forced onto every API.

### 12.2. TLS client certificates and network identity

An `SSLContext` with `KeyManagers` can supply a client certificate when requested by the server, yet **does not decide authorization**. On the server side, TLS authenticates a principal via PKI; the application must still verify resource permissions. If a client uses tenant A's certificate to call tenant B's API, authorization must reject it even with a valid certificate chain.

### 12.3. SNI, IP literals, and virtual hosts

A client calling `https://example.com` can send SNI `example.com` so the server selects the matching certificate; the client still checks the `example.com` SAN. If the client connects to an IP literal, the certificate needs the matching IP SAN. **SNI is not proof of CA trust or hostname match**; it is input for server virtual hosting/routing.

Do not use a custom `SSLSocketFactory` to arbitrarily route traffic to an internal IP while reporting a different hostname unless you understand how JSSE applies endpoint identity. With reverse proxies, distinguish URL host, TLS server name, HTTP `Host`/`:authority` header, certificate SAN, and backend route.

### 12.4. Redirects and SSRF: valid trust can still hit the wrong host

An HTTPS request to a trusted host can return `302` to another host. If the HTTP client follows redirects automatically, authorization headers, cookies, or data flows can be affected. The client needs an allowlist/redirect policy rather than relying on "the destination host's TLS certificate is also valid." SSRF is a destination-selection flaw; certificate validation **is not** a safe host filter.

### 12.5. Working through proxies

An HTTP proxy can forward a CONNECT tunnel without decrypting TLS; an enterprise inspection proxy can **terminate/re-sign** TLS using an enterprise CA. The client verifies the certificate it **actually sees**, per the JVM/context trust policy. Never import an unverified CA or turn off TLS verification simply because traffic traverses a proxy.

### 12.6. JDK runtime and algorithm policy updates

JDK updates revise disabled algorithms lists, TLS protocol defaults, root CA bundles, and provider behaviors. A configuration that once worked may be rejected when weak algorithms/certificates are no longer accepted. The solution is upgrading keys/certificates and policy per documentation, **not loosening `jdk.tls.disabledAlgorithms` arbitrarily** just to pass tests.

---

## 13. Self-check questions and answers

**1. Does `SSLContext` directly hold the URL hostname?**  
No. The URL/request supplies the endpoint; SSLContext supplies TLS key/trust infrastructure. The HTTPS client/JSSE applies appropriate endpoint identification during the handshake.

**2. Why can a certificate signed by a trusted CA still be rejected by HTTPS?**  
Because the hostname mismatches the SAN, it is expired/revoked, EKU/KU/path constraints fail, or an algorithm is disallowed. "Trusted CA" is only part of the criteria.

**3. How do you attach a custom SSLContext to `HttpsURLConnection`?**  
Call `connection.setSSLSocketFactory(context.getSocketFactory())` **before connecting**, while keeping the standard hostname verifier.

**4. How do you attach a custom SSLContext to Java 17 `HttpClient`?**  
Use `HttpClient.newBuilder().sslContext(context).build()`, reusing the client for the corresponding trust domain.

**5. Does `HttpClient.Builder` have `hostnameVerifier(...)` like the legacy API?**  
No. Never use internal JVM flags or `SSLParameters` to bypass HTTPS endpoint verification.

**6. When does a client need `KeyManagerFactory`?**  
When the HTTP client must present a private-key identity, typically mTLS. One-way TLS usually needs a trust manager without a client certificate.

**7. Does `tmf.init(internalStore)` automatically trust the public Web PKI too?**  
No. Trust scope depends on store/provider; a store containing only an internal root normally trusts only that root. To trust distinct domains, design separate clients/truststores per policy.

**8. Why never use `setHostnameVerifier((h,s)->true)`?**  
It abandons endpoint identity checking and risks accepting a certificate for another name, increasing MITM exposure.

**9. Why never mutate `HttpsURLConnection.setDefaultSSLSocketFactory` per request?**  
It is a global default for new connections in the JVM, causing side effects outside the request scope and race conditions with other threads/clients.

**10. Two clients have SSLContexts with the same truststore; why does one still fail?**  
They may differ in URL host, proxy/redirects, key managers/cert selection, TLS version/provider, or a misconfigured legacy custom hostname verifier. Compare both context **and** endpoint policy.

**11. A new root CA is added to the truststore on disk; does an already-built HttpClient automatically trust it?**  
Do not assume so. You need a mechanism to reload/rebuild SSLContext/HttpClient and handle connection/session lifecycles.

**12. Can checking only `X509Certificate.verify(caKey)` replace HTTPS validation?**  
No. It does not check trust anchors, PKIX path, hostname, revocation, proof-of-possession, or TLS handshake integrity.

**13. Is a `SAN DNS:localhost` certificate valid when the URL is `https://127.0.0.1`?**  
Not under standard IP identity checks if `iPAddress:127.0.0.1` SAN is missing. Avoid confusing a successful socket connection with valid hostname verification.

**14. Does mTLS automatically grant the client access to all APIs?**  
No. TLS authenticates the principal; IAM/ACL/tenant permissions belong to the application layer.

**15. Should you create a new `HttpClient` for every request?**  
Usually no; reuse it to manage connection pooling and TLS overhead, while separating clients per trust domain/policy.

**16. Is there any way to run HTTPS when a partner's certificate is broken without enabling trust-all?**  
Fix the root cause: issue a certificate with proper SAN/EKU, send complete intermediates, use a truststore with the approved CA, and use the exact URL. Never ship fake security to production.

---

## 14. Checklist for secure Java HTTPS deployment

- [ ] **Choose client API**: legacy when integrating old code, modern `HttpClient` for reusable/async/HTTP2; understand TLS config scope.
- [ ] **Exact URL**: host/port/path/scheme and redirect policy; prevent SSRF and credential leakage.
- [ ] **Trust anchors**: CAs/certs placed in truststores from trusted sources; no trust-all or unverified CAs.
- [ ] **Server certificate**: chain, validity, SAN, `serverAuth` EKU, KU/purpose, and algorithms/key sizes per policy.
- [ ] **Hostname verification**: keep HTTPS endpoint identity checking; no always-true verifiers or undocumented disable flags.
- [ ] **Scope**: `setSSLSocketFactory` per legacy instance, `sslContext` on modern builder; avoid mutating global defaults when running multiple clients.
- [ ] **mTLS**: if required, client has `PrivateKeyEntry` + chain + KeyManagerFactory; server has trusted client CA and `needClientAuth`.
- [ ] **AuthZ**: map certificate identity → service principal → tenant/role/operation checks, separate from TLS trust.
- [ ] **Lifecycle**: CA/root, leaf, and private key have rotate/revoke/reload strategies; connection pools/resumption and long-lived sessions have policies.
- [ ] **Timeout/resource**: connect/read/request timeouts, HTTP status/error streams, body size, redirect, and proxy controls.
- [ ] **Observability**: adequate logging for TLS handshake failures and certificate chains without dumping private keys/passwords/plaintext.
- [ ] **Negative tests**: untrusted CA, wrong host/IP SAN, expired cert, wrong EKU, missing intermediates, mTLS missing client key, cross-host redirect, misconfigured proxy.
- [ ] **Production QA**: test on the exact target JDK/provider/container image and real JSSE config; never treat "demo pass" as proof of the entire security policy.

**Key conclusion:** `SSLContext` manages **key/trust sources and the TLS engine**; **HTTPS endpoint identification** binds the certificate to the **target hostname**. `HttpsURLConnection` lets you set `SSLSocketFactory` per connection and exposes an easily abused `HostnameVerifier`. `HttpClient` takes `SSLContext` on the builder and provides no equivalent public hostname-verifier callback. **Fixing CA/hostname errors with trust-all or disabling verifiers breaks security—it is not proper configuration.**

## 15. Official references

- [Java SE 17 – HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): `setSSLSocketFactory`, `setHostnameVerifier`, default factories/verifiers.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): reusable HTTP/1.1/HTTP2 client, SSLContext, request/response, async, and client lifecycle.
- [Java SE 17 – HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `sslContext`, `sslParameters`, `connectTimeout`, `followRedirects`, and `proxy`.
- [Java SE 17 – SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html), [KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html), and [TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): creating TLS contexts from identity and peer trust.
- [Java SE 17 – SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification/protocol/cipher parameters.
- [Java SE 17 – HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html) and [HttpsConfigurator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html): implementing a local HTTPS server for labs.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, truststore/keystore, PKIX, `SSLSocket`, and debugging.
- [JDK 17 keytool manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): key pairs, CSRs, CA signing, importing cert replies, PKCS12.
- [RFC 5280 – X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate path validation, CA constraints, and SAN.
- [RFC 9525 – Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): HTTPS/TLS endpoint identity checks.
- [RFC 8446 – TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake and server authentication.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): secure TLS configuration and anti-patterns to avoid.