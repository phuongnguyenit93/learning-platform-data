# TLS, Certificates, Proxies, and DNS Resolution with Spring WebClient

## 1. Goal: Secure HTTPS Connections and Diagnosing Network Failures

`WebClient` provides the reactive HTTP API, while opening sockets, resolving hostnames, traversing proxies, and performing the TLS handshake are delegated to the underlying HTTP connector. In a Spring Boot application using `spring-boot-starter-webflux`, the auto-configured connector is typically Reactor Netty when that dependency is on the classpath.

An HTTPS request succeeds only when several consecutive steps succeed:

1. **DNS** resolves the hostname to an IP address.
2. **Connection pool/TCP** supplies an existing connection or opens a connection to the server/proxy.
3. **Proxy**, if configured, accepts the connection and establishes an appropriate tunnel.
4. **TLS handshake** negotiates the cipher session and verifies the server's certificate chain and hostname.
5. If the server requires **mutual TLS (mTLS)**, the client also presents a certificate and proves ownership of the corresponding private key.
6. Once the secure channel is ready, WebClient sends the HTTP request and decodes the response.

A failure at each step has a different cause and fix. For example, `UnknownHostException` is a domain name resolution issue; `ConnectTimeoutException` is a connection establishment issue; `SSLHandshakeException` typically relates to certificates, trust, or TLS negotiation; HTTP 407 typically relates to proxy authentication; HTTP 401/403 typically relates to authentication/authorization at the target service.

This lesson uses Spring Framework 6.2, Spring Boot 3.3.x, Java 17+, and Reactor Netty 1.1.x as its baseline. After this lesson, you will be able to:

- Explain truststore, keystore, certificate chain, SAN, SNI, hostname verification, and mTLS.
- Configure WebClient to use an internal CA or a client certificate.
- Connect through an HTTP proxy, use proxy authentication, and configure bypass hosts.
- Understand Reactor Netty's asynchronous DNS resolver, cache TTL, and the effect of the connection pool.
- Configure separate timeouts for pool acquire, DNS, TCP connect, proxy connect, TLS handshake, and response.
- Classify errors by stage and inspect them using command-line tools.
- Test TLS trust and hostname verification using MockWebServer.

## 2. Which Layers Does WebClient Use for HTTPS?

`WebClient` does not implement TCP or TLS itself. It delegates to a `ClientHttpConnector`. Spring supports Reactor Netty, JDK HttpClient, Jetty Reactive HttpClient, Apache HttpComponents, and other connectors. SSL, proxy, and DNS configuration therefore depend on the connector in use.

With Reactor Netty, the connection flow can be visualized as follows:

```text
WebClient request
      |
      v
Connection pool
      |
      +---- matching connection available -> reuse
      |
      +---- no connection yet
                 |
                 v
            DNS resolver
                 |
                 v
              TCP connect
                 |
                 +---- direct to origin
                 |
                 +---- or connect to HTTP proxy
                              |
                              v
                         HTTP CONNECT
                              |
                              v
                         TLS handshake
                              |
                              v
                 Verify certificate chain + hostname
                              |
                    optional client certificate (mTLS)
                              |
                              v
                       HTTP request/response
```

Exact ordering differs between direct connections and proxies, yet these layers must be distinguished:

| Layer | Question to Answer | Common Errors |
|---|---|---|
| Connection pool | Is an idle connection available to use? | `PoolAcquireTimeoutException` |
| DNS | Which IP does the hostname resolve to? | `UnknownHostException`, DNS timeout |
| TCP | Can a socket be opened to the peer? | `ConnectException`, `ConnectTimeoutException` |
| Proxy | Does the proxy accept the connection, authenticate, and open a tunnel? | HTTP 407, proxy connect timeout, tunnel failure |
| TLS | Is the certificate trusted and does it match the hostname? | `SSLHandshakeException`, `CertificateException` |
| HTTP | What status did the target service return? | 401, 403, 404, 429, 5xx |
| Decode | Does the response body match the media type/schema? | `DecodingException` |

If using `WebClient` with a connector other than Reactor Netty, do not mechanically copy `HttpClient` or `ProxyProvider` APIs; configure according to the actual HTTP client library.

## 3. TLS, Certificate Chains, and Server Identity

TLS provides three primary guarantees:

- **Confidentiality**: encrypts data in transit.
- **Integrity**: detects data modification during transit.
- **Peer authentication**: verifies that the server the client connects to has the expected identity.

When calling `https://api.example.com`, the client receives the server's certificate. The client checks whether the certificate chain leads to a trusted trust anchor, whether the certificate is valid, and whether the certificate properly identifies the hostname `api.example.com`.

### 3.1. Certificate Chain

A certificate chain typically consists of:

```text
Root CA (trust anchor)
      |
      v
Intermediate CA
      |
      v
Server/leaf certificate
      |
      v
api.example.com
```

The server typically sends the leaf certificate and required intermediate certificates. The client has the corresponding root CA or trust anchor in its truststore to validate the chain.

Key conditions:

- The certificate signatures must be valid.
- The chain must lead to a trust anchor trusted by the client.
- The certificate must be within its `Not Before` / `Not After` validity window.
- Extended Key Usage must permit server authentication.
- The hostname must match a Subject Alternative Name (SAN).
- The TLS protocol and cipher suite must have a mutually accepted choice.

Merely seeing a certificate in a browser or opening the URL with `curl` on a personal laptop does not prove a Java container has the same truststore or DNS/proxy configuration.

### 3.2. SAN and Hostname Verification

Hostname verification checks whether the hostname in the URL is identified by the certificate. In modern HTTPS, clients should rely on SAN (Subject Alternative Name), for example:

```text
DNS:api.example.com
DNS:*.internal.example.com
IP:10.20.30.40
```

A certificate with SAN `api.example.com` can be valid when calling `https://api.example.com`. If called via `https://10.20.30.40`, the certificate needs a matching IP SAN or another properly verified naming mechanism.

A valid certificate chain does not mean the hostname is valid. A certificate issued by a trusted CA for `other.example.com` still does not prove the peer is `api.example.com`.

### 3.3. What Is SNI?

Server Name Indication (SNI) is hostname information the client sends during the TLS handshake so the server can select the right certificate when multiple domains share one IP.

Reactor Netty uses the hostname from the remote URI as the SNI server name by default. SNI helps the server pick a certificate; hostname verification remains a separate check. Changing SNI does not replace verifying certificate identity.

Avoid replacing a URL with an IP address just to bypass DNS. Doing so can break both SNI and hostname verification against the service's certificate.

## 4. How Do Truststore and Keystore Differ?

These two concepts have different roles:

| Component | What Does It Contain? | What Is It Used For? |
|---|---|---|
| Truststore | CA certificates or trust anchors | Client decides which server certificates to trust |
| Keystore | Private key and certificate chain of the client/server itself | Client or server proves its own identity when requested |

For standard HTTPS connections, the client only needs an appropriate truststore. If the service requires mTLS, the client also needs a keystore containing the client certificate and private key.

Common formats:

- **PKCS12 (`.p12`, `.pfx`)**: typically contains private keys, certificate chains, or trust certificates.
- **JKS (`.jks`)**: Java's keystore/truststore format.
- **PEM (`.pem`, `.crt`, `.key`)**: certificates and private keys as Base64 text with headers/footers; private keys used with Netty must be in a format supported by the API, typically PKCS#8.

Never send a client's private key to the server or commit it to Git. Public certificates can be shared via standard procedures, while private keys must be managed as secrets.

## 5. Using an Internal CA to Verify the Server

If a server uses a certificate issued by an internal CA, the JVM may not trust that CA yet. The standard approach is to place the organization-approved root/intermediate CA into the truststore used by WebClient.

### 5.1. Using a PEM Certificate with Netty `SslContextBuilder`

```java
File internalCa = new File("/etc/app/certs/internal-root-ca.pem");

SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(internalCa)
        .build();

HttpClient httpClient = HttpClient.create()
        .secure(ssl -> ssl.sslContext(sslContext));

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.internal.example")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

`trustManager(File)` accepts a PEM file containing an X.509 certificate collection used to verify the peer's certificate. This example creates a trust context based on an internal CA.

If the application must call both public services and internal services, ensure the truststore contains all required CAs. A custom truststore containing only an internal CA may no longer trust public CAs that the default JVM trusts. You can build a combined truststore or manage separate WebClients with distinct trust policies per service group.

### 5.2. Creating a PKCS12 Truststore

You can import a CA into a truststore using `keytool`:

```bash
keytool -importcert \
  -alias internal-root-ca \
  -file internal-root-ca.pem \
  -keystore internal-truststore.p12 \
  -storetype PKCS12
```

The command prompts for a truststore password and certificate confirmation. Only import certificates whose fingerprint has been verified or that arrived via a trusted channel.

Inspect the contents:

```bash
keytool -list -v \
  -keystore internal-truststore.p12 \
  -storetype PKCS12
```

Java can load the truststore and create a `TrustManagerFactory`:

```java
KeyStore trustStore = KeyStore.getInstance("PKCS12");

try (InputStream input = Files.newInputStream(
        Path.of("/etc/app/certs/internal-truststore.p12"))) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(trustManagers)
        .build();
```

`trustStorePassword` should come from a secret manager or deployment environment secret mechanism, not hardcoded in source code.

### 5.3. When to Use the JVM Default Truststore?

If the service uses a public certificate chain and the JVM truststore already contains the corresponding root CA, you can use the default configuration:

```java
HttpClient httpClient = HttpClient.create().secure();
```

Reactor Netty 1.1 enables hostname verification for `secure()` and the `secure(Consumer<SslContextSpec>)` overload. You do not need to create a custom truststore just for ordinary HTTPS.

If a certificate chain is untrusted, locate the proper CA/intermediate or check whether the server sends the complete chain. Do not use a trust-all manager to make certificate errors disappear.

## 6. Mutual TLS (mTLS): The Client Also Presents a Certificate

In standard one-way HTTPS, the client verifies the server. With mTLS, the server also requires the client to present a certificate to authenticate the client's identity.

```text
Client                              Server
  |                                   |
  |------ ClientHello --------------->|
  |<----- Server certificate ---------|
  |------ Verify server certificate   |
  |<----- CertificateRequest ---------|
  |------ Client certificate -------->|
  |------ CertificateVerify --------->|
  |<----- Handshake complete -------->|
  |------ HTTP request -------------->|
```

The server must trust the CA that issued the client certificate. The client still must trust the CA that issued the server certificate. These are two independent trust decisions.

### 6.1. Configuring a Client Certificate in PEM Format

```java
SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(new File("/etc/app/certs/server-ca.pem"))
        .keyManager(
                new File("/etc/app/certs/client-chain.pem"),
                new File("/etc/app/certs/client-key.pk8"))
        .build();

HttpClient httpClient = HttpClient.create()
        .secure(ssl -> ssl.sslContext(sslContext));

WebClient webClient = WebClient.builder()
        .baseUrl("https://partner.example.com")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

`client-chain.pem` contains the client's certificate chain. `client-key.pk8` is the corresponding PKCS#8 private key. If the private key is encrypted, use the `keyManager` overload accepting a password according to the Netty API in use.

### 6.2. Configuring mTLS with PKCS12

```java
KeyStore clientKeyStore = KeyStore.getInstance("PKCS12");

try (InputStream input = Files.newInputStream(clientKeyStorePath)) {
    clientKeyStore.load(input, clientKeyStorePassword);
}

KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(clientKeyStore, clientKeyStorePassword);

SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(serverTrustManagerFactory)
        .keyManager(keyManagers)
        .build();
```

The keystore must contain the client's private key entry and certificate chain. If it only holds a public certificate without the matching private key, the client cannot prove certificate ownership during the handshake.

### 6.3. Common mTLS Errors

- Not sending a client certificate even though the server requests one.
- Expired client certificate.
- Private key does not match the certificate.
- Server does not trust the CA that issued the client certificate.
- Client sends a chain missing an intermediate certificate.
- EKU/key usage does not permit client authentication.
- Certificate is sent, but is not authorized for the corresponding API/tenant.

HTTP 401/403 after a successful TLS handshake is usually an HTTP authorization or application policy error, not necessarily an mTLS error.

## 7. Hostname Verification: Protecting Endpoint Identity

Reactor Netty 1.1 has SSL overloads with different behaviors:

- `HttpClient.secure()` uses default SSL and enables hostname verification.
- `HttpClient.secure(Consumer<SslContextSpec>)` also enables hostname verification.
- `HttpClient.secure(SslProvider)` takes a pre-built provider; hostname verification is not enabled automatically in this overload.

If building an `SslProvider` manually, attach the hostname verification configurator:

```java
SslProvider sslProvider = SslProvider.builder()
        .sslContext(SslContextBuilder.forClient()
                .trustManager(new File("/etc/app/certs/internal-ca.pem")))
        .handlerConfigurator(
                HttpClientSecurityUtils.HOSTNAME_VERIFICATION_CONFIGURER)
        .build();

HttpClient httpClient = HttpClient.create()
        .secure(sslProvider);
```

If you use the `secure(SslProvider)` overload and forget the configurator, the certificate chain may be trusted while hostname verification is not enforced as expected.

### Do Not Disable Verification to Fix Errors

Do not use the following in production:

- `InsecureTrustManagerFactory.INSTANCE`.
- A trust manager that always treats any certificate as valid.
- Disabling endpoint identification/hostname verification.
- Accepting every certificate just because the environment is staging.
- Calling an IP address to skip a hostname mismatch.

These practices remove server identity verification and open the door to man-in-the-middle attacks. Fix the certificate SAN, trust chain, URL hostname, SNI, or CA configuration instead.

### Distinguishing Trust Chain, SNI, and Hostname Verification

| Mechanism | Question | What Does It Not Replace? |
|---|---|---|
| Trust chain validation | Who issued the certificate and is that CA trusted? | Does not prove the hostname matches |
| SNI | Which hostname does the client want the server to present a certificate for? | Does not verify the certificate |
| Hostname verification | Does the certificate identify the host in the URL? | Does not create a trust anchor |
| mTLS | Does the client have a certificate accepted by the server? | Does not replace HTTP/API authorization |

## 8. HTTP Proxy and HTTPS CONNECT Tunnel

A proxy is a network hop between WebClient and the target service. In enterprise environments, proxies may be used to control outbound traffic, audit connections, or reach the Internet.

For HTTP proxies, Reactor Netty supports `ProxyProvider`:

```java
HttpClient httpClient = HttpClient.create()
        .proxy(spec -> spec
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.internal.example")
                .port(8080)
                .nonProxyHosts("localhost|127\\.0\\.0\\.1")
                .connectTimeoutMillis(10_000));
```

`nonProxyHosts` is a regular expression for hostnames accessed directly. Configure it carefully so you do not accidentally bypass the proxy for hosts that must be controlled.

### 8.1. HTTPS Through an HTTP Proxy

When calling HTTPS through an HTTP proxy, the client typically asks the proxy to open a tunnel using the `CONNECT` method to the target host/port. Once the tunnel is established, the TLS handshake runs with the target endpoint through that tunnel.

```text
WebClient
   |
   | TCP
   v
HTTP proxy
   |
   | CONNECT api.example.com:443
   v
Tunnel to origin
   |
   | TLS handshake with api.example.com
   v
HTTPS API
```

The proxy can see the target hostname/port and network metadata. If the proxy only creates a CONNECT tunnel, HTTP contents inside TLS are encrypted between client and origin.

Some corporate proxies perform TLS inspection: the proxy terminates TLS from the client and opens a separate TLS connection to the origin. In that case, the client sees a certificate issued by the organization's internal CA. Only install an inspection CA with policy and approval from security administration.

Reactor Netty uses CONNECT for HTTP proxy tunnels; some proxies do not support CONNECT in all modes or require dedicated configuration. Check proxy documentation when tunnel connections fail.

### 8.2. Proxy Authentication

Proxy authentication differs from origin authentication:

- `Proxy-Authorization` authenticates the client to the proxy.
- `Authorization` authenticates the client to the target API.

You can configure the HTTP proxy username/password using `ProxyProvider`:

```java
String proxyUser = System.getenv("OUTBOUND_PROXY_USER");
String proxyPassword = System.getenv("OUTBOUND_PROXY_PASSWORD");

HttpClient httpClient = HttpClient.create()
        .proxy(spec -> spec
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.internal.example")
                .port(8080)
                .username(proxyUser)
                .password(ignoredUsername -> proxyPassword)
                .connectTimeoutMillis(10_000));
```

The `password` API accepts a function providing the password for a username. Retrieve credentials from a secret manager/environment; never hardcode them in code, logs, or exception messages.

HTTP 407 Proxy Authentication Required typically relates to proxy credentials or proxy policy. HTTP 401/403 from the origin is a separate layer.

### 8.3. Proxy and Target Hostname DNS

When routing through a proxy, identify which side resolves the target hostname:

- The client may resolve the host and connect to the resulting address depending on connector/proxy configuration.
- The proxy may receive the hostname in CONNECT and resolve it from the proxy's network.
- With a custom resolver, behavior can change.

Therefore, when DNS succeeds on a developer machine yet fails in a container behind a proxy, check DNS at the exact place resolving the hostname: the application runtime, the proxy, or both. Do not assume every proxy uses the same DNS view as the application.

## 9. DNS Resolution in Reactor Netty

Reactor Netty `HttpClient` uses Netty's domain name resolver by default to resolve hostnames asynchronously. This differs from the traditional JVM resolver, which can perform blocking lookups.

Example limiting time per DNS query:

```java
HttpClient httpClient = HttpClient.create()
        .resolver(spec -> spec.queryTimeout(Duration.ofSeconds(2)));
```

Reactor Netty lets you customize the DNS cache:

```java
HttpClient httpClient = HttpClient.create()
        .resolver(spec -> spec
                .queryTimeout(Duration.ofSeconds(2))
                .cacheMaxTimeToLive(Duration.ofSeconds(60))
                .cacheMinTimeToLive(Duration.ofSeconds(5))
                .cacheNegativeTimeToLive(Duration.ofSeconds(2)));
```

Meaning:

| Configuration | Effect |
|---|---|
| `queryTimeout` | Maximum time for each DNS query |
| `cacheMaxTimeToLive` | Upper bound on DNS record TTL in cache |
| `cacheMinTimeToLive` | Lower bound on DNS record TTL in cache |
| `cacheNegativeTimeToLive` | Cache TTL for failed resolution results |

According to Reactor Netty 1.1.21 documentation, the default `queryTimeout` is 5 seconds; default cache min TTL is 0 and default negative TTL is 0. Default cache max TTL is very large (`Integer.MAX_VALUE` seconds), so if the system needs to pick up address changes quickly, set an intentional policy.

### 9.1. Using the JVM Built-In Resolver

If you need to use the JVM resolver instead of Netty's resolver:

```java
HttpClient httpClient = HttpClient.create()
        .resolver(DefaultAddressResolverGroup.INSTANCE);
```

This is a compatibility option, not a default that needs replacing. The JVM built-in resolver has different lookup characteristics from Netty's asynchronous DNS resolver; weigh thread and latency impacts before switching.

### 9.2. Common Causes of DNS Failure

- Wrong hostname or missing DNS record.
- Unreachable DNS server inside container/Kubernetes.
- Unexpected search domain or `/etc/resolv.conf`.
- Split-horizon DNS: laptop and production resolve the same hostname to different IPs.
- A record exists while AAAA record does not work, or vice versa.
- DNS cache retains stale entries or caches negative results.
- Proxy resolves the target host using a different DNS view than the client.
- Internal service exists only in a private DNS zone.

Do not replace a hostname with an IP address as a default fix. That can cause SNI and hostname verification to mismatch the certificate.

## 10. DNS Cache and Connection Pool Are Two Separate Mechanisms

DNS TTL determines how long a resolution result may be reused in the resolver cache. The connection pool retains established TCP connections so subsequent requests can reuse them.

When a DNS record changes:

1. The resolver may pick up the new IP after the cache TTL expires.
2. Open TCP connections still point to the old IP.
3. Subsequent requests can reuse an old connection without a new DNS lookup.
4. Only when opening a new connection does the client resolve and connect to the current address.

Therefore, a short DNS TTL does not automatically close connections already retained by the pool.

You can bound connection lifetime:

```java
ConnectionProvider provider = ConnectionProvider.builder("partner")
        .maxConnections(100)
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .evictInBackground(Duration.ofSeconds(30))
        .build();

HttpClient httpClient = HttpClient.create(provider);
```

When setting `maxIdleTime`, choose a value no greater than the idle timeout allowed by the server/proxy to reduce the risk of reusing a connection closed by the peer. `maxLifeTime` refreshes connections over time, which is useful when endpoint IPs are load-balanced or rotated.

If you create a custom `ConnectionProvider`, manage its lifecycle and dispose it when the application stops. With default global Reactor Netty resources, multiple clients can share event loops and connection resources; this is usually the right choice for Spring applications.

## 11. Timeouts: Configuring Each Stage Separately

A single overall timeout does not tell you exactly where a request slowed down. Reactor Netty provides per-stage timeouts:

| Stage | API | Documented Default in Reactor Netty 1.1.21 |
|---|---|---|
| Wait for connection from pool | `pendingAcquireTimeout` | 45 seconds |
| DNS query | `queryTimeout` | 5 seconds per query |
| TCP connect | `CONNECT_TIMEOUT_MILLIS` | 30 seconds |
| TLS handshake | `handshakeTimeout` | 10 seconds |
| Proxy connect | proxy `connectTimeoutMillis` | 10 seconds |
| Response read interval | `responseTimeout` | Not set by default |

The timeouts have different meanings:

- Pool acquire timeout happens before a connection is obtained to send the request.
- DNS timeout measures hostname resolution time.
- Connect timeout measures time to open a TCP connection.
- TLS handshake timeout measures time to complete the TLS handshake.
- Response timeout limits the duration between network-level response data reads; it is not necessarily an overall deadline for the entire request.
- `Mono.timeout(Duration)` can set a deadline for the whole publisher from subscribe to completion, spanning multiple stages.

### 11.1. Combined Configuration

```java
ConnectionProvider provider = ConnectionProvider.builder("catalog")
        .maxConnections(80)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .build();

HttpClient httpClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
        .responseTimeout(Duration.ofSeconds(8))
        .resolver(spec -> spec.queryTimeout(Duration.ofSeconds(2)))
        .secure(ssl -> ssl
                .sslContext(Http11SslContextSpec.forClient())
                .handshakeTimeout(Duration.ofSeconds(10)));

WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

These values are starting examples, not a universal timeout set for every service. Base yours on latency percentiles, network topology, SLAs, and upstream processing times.

### 11.2. Overall Deadline for a Use Case

```java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(12));
```

An overall deadline is useful when a use case must bound total completion time. However, you should still configure explicit timeouts for DNS, connect, handshake, and response to identify what caused slowness.

### 11.3. Avoiding Unintentional Timeout Overlap

For example, a 2-second pool acquire timeout, 2-second DNS query, 5-second connect, 10-second TLS handshake, and 4-second overall deadline mean some stages cannot exhaust their individual configured time. This is not technically wrong, but understand that the overall timeout cancels the publisher before longer detailed timeouts trigger.

Set the deadline from the use case's time budget and allocate portions of time to inner steps accordingly.

## 12. Connecting WebClient to Reactor Netty

Spring Framework lets you plug a configured connector into WebClient:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(8));

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

In Spring Boot, inject the auto-configured `WebClient.Builder` when you want to inherit Boot's codec configuration and shared resources. `WebClient.create()` builds a client directly and misses customizations applied to the auto-configured builder.

Bean example:

```java
@Configuration
public class PartnerClientConfiguration {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
                .responseTimeout(Duration.ofSeconds(8));

        return builder
                .baseUrl("https://partner.example.com")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

If SSL, proxy, or DNS configurations differ across services, create separate clients per trust policy/route. Avoid a single client with overly broad credentials or trust policies used to call every hostname.

## 13. Diagnosing Errors by Stage

### 13.1. DNS Errors

Symptom:

```text
java.net.UnknownHostException: api.internal.example
```

Test from the exact container/VM running the application:

```bash
nslookup api.internal.example
```

Or:

```bash
dig api.internal.example
```

On Linux, you can check:

```bash
getent hosts api.internal.example
cat /etc/resolv.conf
```

Do not test DNS only on a laptop if the application runs in Kubernetes, Docker, or an isolated subnet.

### 13.2. TCP Connect Errors

Symptoms may include:

```text
Connection refused
ConnectTimeoutException
No route to host
```

Check:

- Are the host and port correct?
- Are security groups, firewalls, NetworkPolicy, or routing rules blocking traffic?
- Is the service listening?
- Is the application connecting directly or via a proxy?
- Are the proxy host/port reachable from the container?

### 13.3. TLS Handshake Errors

Common messages:

| Message | Cause to Check |
|---|---|
| `PKIX path building failed` | Truststore lacks the appropriate CA or server is missing an intermediate |
| `unable to find valid certification path` | Unable to build a trust chain |
| `No subject alternative DNS name matching ...` | Hostname in URL does not match SAN |
| `certificate expired` | Certificate expired or system clock is wrong |
| `bad_certificate` | Client certificate rejected by server |
| `handshake_failure` | Incompatible protocol/cipher/client-auth policy |
| `SSLHandshakeException` | General handshake failure; inspect the cause chain |

You can inspect the certificate chain and hostname with OpenSSL:

```bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error \
  -CAfile internal-root-ca.pem
```

`-servername` sends SNI. `-CAfile` specifies the CA used for verification. OpenSSL output is useful for comparing with the JVM, though it does not prove Java's truststore is configured identically.

In test environments, you can enable Java SSL debug:

```bash
-Djavax.net.debug=ssl:handshake:verbose
```

Enable it only temporarily for diagnosis. TLS logs can be huge and contain sensitive metadata; never leave this debug level running permanently in production.

### 13.4. Proxy Errors

Test the path through the proxy:

```bash
curl -v \
  --proxy http://proxy.internal.example:8080 \
  https://api.example.com/health
```

Distinguish:

- Cannot connect to proxy: proxy DNS/connect/firewall.
- Proxy returns 407: proxy credentials or policy.
- CONNECT fails: proxy disallows tunneling to the target host/port.
- TLS fails after CONNECT: trust chain/hostname/SNI or TLS inspection CA.
- Origin returns 401/403: credentials or authorization at the target API.

### 13.5. Pool and Response Timeout Errors

- `PoolAcquireTimeoutException`: could not obtain a connection within wait time; check max connections, request concurrency, and connection hold times.
- `ReadTimeoutException`/response timeout: no response data arrived within the allowed interval; check upstream latency, proxy, and network.
- Connection closed on reuse: check server/load balancer idle timeout and adjust `maxIdleTime`.
- DNS changed yet traffic still goes to old IP: check the connection pool and connection lifetime, not just the DNS cache.

## 14. Exception Classification and Safe Logging

An outbound client should distinguish transport, TLS, proxy, timeout, and HTTP response errors. `WebClientRequestException` typically wraps errors when a request fails to complete at the connector layer. If the server returned an HTTP response, WebClient exposes status and body via response APIs or `WebClientResponseException` with default `retrieve()`.

Example classifying by cause:

```java
return webClient.get()
        .uri("/health")
        .retrieve()
        .bodyToMono(String.class)
        .doOnError(error -> {
            log.warn(
                    "Outbound call failed: type={}, message={}",
                    error.getClass().getSimpleName(),
                    error.getMessage());
        });
```

This is only general logging. Production should include service name, route template, trace/correlation ID, and error category, while never logging:

- Private keys, keystore passwords, or truststore passwords.
- `Authorization`, `Proxy-Authorization`, cookies, or API tokens.
- Full private certificate material.
- URLs with query parameters containing secrets.
- Raw request/response bodies if they contain personal data.

Reactor Netty metrics can report connection time, TLS handshake time, DNS resolver duration, response time, active/idle/pending connection counts, and error counts. Enable observability per application configuration to pinpoint whether latency lies in the resolver, connect, TLS, or response.

## 15. Runnable Java 17+ Project: WebClient with Custom CA and Hostname Verification

The sample project uses:

- Java 17.
- Spring Boot 3.3.5.
- Spring WebFlux/Reactor Netty versions managed by Spring Boot.
- JUnit 5 and Reactor Test.
- OkHttp MockWebServer and `okhttp-tls` to spin up a local HTTPS server with a `localhost` SAN certificate.

The project verifies two behaviors:

1. The client trusts the supplied CA certificate, connects over HTTPS to `localhost`, and receives a response.
2. The client trusts the same certificate yet calls hostname `127.0.0.1`, while the certificate only has SAN `localhost`; hostname verification must reject the connection.

Test certificates are generated ephemerally in memory, avoiding storing test private keys in the repository.

### 15.1. Structure

```text
webclient-tls-dns/
├── pom.xml
└── src/
    ├── main/java/edu/demo/tls/
    │   ├── TlsWebClientFactory.java
    │   └── CatalogClient.java
    └── test/java/edu/demo/tls/
        └── TlsWebClientTests.java
```

### 15.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webclient-tls-dns</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <okhttp.version>4.12.0</okhttp.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>${okhttp.version}</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>okhttp-tls</artifactId>
            <version>${okhttp.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 15.3. `TlsWebClientFactory.java`

```java
package edu.demo.tls;

import java.security.cert.X509Certificate;
import java.time.Duration;

import io.netty.channel.ChannelOption;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

public final class TlsWebClientFactory {

    private TlsWebClientFactory() {
    }

    public static WebClient create(
            String baseUrl,
            X509Certificate trustedCertificate) throws Exception {

        SslContext sslContext = SslContextBuilder.forClient()
                .trustManager(trustedCertificate)
                .build();

        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
                .responseTimeout(Duration.ofSeconds(5))
                .resolver(spec ->
                        spec.queryTimeout(Duration.ofSeconds(2)))
                .secure(ssl -> ssl
                        .sslContext(sslContext)
                        .handshakeTimeout(Duration.ofSeconds(10)));

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

The factory accepts a trusted certificate to construct a trust manager for testing. In production, pass an organization-verified CA certificate or load a PKCS12 truststore as shown earlier.

Using the `secure(Consumer<SslContextSpec>)` overload retains Reactor Netty 1.1's default hostname verification.

### 15.4. `CatalogClient.java`

```java
package edu.demo.tls;

import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<String> health() {
        return webClient.get()
                .uri("/health")
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

The client defines only the HTTP use case. TLS, trust, and network timeouts are configured in the underlying connector.

### 15.5. `TlsWebClientTests.java`

```java
package edu.demo.tls;

import java.io.IOException;
import java.net.InetAddress;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.SSLHandshakeException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.tls.HandshakeCertificates;
import okhttp3.tls.HeldCertificate;
import okhttp3.HttpUrl;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.web.reactive.function.client.WebClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TlsWebClientTests {

    private MockWebServer server;
    private HeldCertificate serverCertificate;
    private CatalogClient catalogClient;

    @BeforeEach
    void setUp() throws Exception {
        serverCertificate = new HeldCertificate.Builder()
                .commonName("localhost")
                .addSubjectAlternativeName("localhost")
                .build();

        HandshakeCertificates serverCertificates =
                new HandshakeCertificates.Builder()
                        .heldCertificate(serverCertificate)
                        .build();

        server = new MockWebServer();
        server.useHttps(serverCertificates.sslSocketFactory(), false);
        server.start(InetAddress.getByName("127.0.0.1"), 0);

        WebClient webClient = TlsWebClientFactory.create(
                server.url("/").toString(),
                serverCertificate.certificate());

        catalogClient = new CatalogClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void trustedCertificateAndMatchingHostnameSucceed()
            throws Exception {

        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "text/plain")
                .setBody("healthy"));

        StepVerifier.create(catalogClient.health())
                .expectNext("healthy")
                .verifyComplete();

        var request = server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/health", request.getPath());
    }

    @Test
    void trustedCertificateDoesNotAllowWrongHostname()
            throws Exception {

        HttpUrl wrongHostUrl = server.url("/")
                .newBuilder()
                .host("127.0.0.1")
                .build();

        WebClient wrongHostClient = TlsWebClientFactory.create(
                wrongHostUrl.toString(),
                serverCertificate.certificate());

        CatalogClient wrongHostCatalog =
                new CatalogClient(wrongHostClient);

        StepVerifier.create(wrongHostCatalog.health())
                .expectErrorSatisfies(error ->
                        assertTrue(
                                hasCause(error, SSLHandshakeException.class),
                                error.toString()))
                .verify();
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expected) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (expected.isInstance(current)) {
                return true;
            }
        }

        return false;
    }
}
```

The second test uses a trusted certificate while the hostname in the URL does not match the SAN. It demonstrates that trust chain validation and hostname verification are two independent checks.

### 15.6. Running the Tests

From the directory containing `pom.xml`:

```bash
mvn test
```

The test suite has two cases:

1. HTTPS succeeds when the CA is trusted and the hostname matches the SAN.
2. TLS handshake fails when the hostname does not match the SAN, even though the certificate is trusted.

Expected result when Maven completes successfully:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected result for comparison when executing; this document does not claim Maven was run in the authoring environment.

## 16. Common Configuration Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Truststore missing internal CA | `PKIX path building failed` | Import the verified CA/intermediate |
| Server does not send intermediate | Client cannot build chain | Fix the server certificate chain |
| Expired certificate | TLS handshake fails | Renew and deploy a new certificate |
| SAN does not match hostname | Hostname verification fails | Use the right hostname or issue a certificate with matching SAN |
| Using IP instead of hostname | SNI/SAN may not match | Keep the service hostname in the URI |
| Using trust-all manager | Loses server identity verification | Configure a valid truststore |
| Building `SslProvider` while forgetting hostname configurator | May skip hostname verification | Attach `HOSTNAME_VERIFICATION_CONFIGURER` |
| mTLS missing private key or chain | Server rejects client certificate | Check PKCS12/PEM and key pair |
| Using origin `Authorization` for proxy auth | Proxy still returns 407 | Configure proxy credentials separately |
| Proxy disallows CONNECT | HTTPS tunnel cannot be created | Check proxy policy and CONNECT support |
| Incorrect trust CA for TLS inspection | Handshake fails through proxy | Verify proxy CA and trust policy |
| Laptop DNS works but container fails | `UnknownHostException` | Inspect DNS from the actual runtime |
| Short DNS TTL yet still hitting old IP | Connection pool retains old TCP connections | Adjust connection max lifetime/idle policy |
| Response timeout too short | Slow streaming requests get cut off | Use a read interval aligned with the contract |
| Setting only an overall timeout | Hard to diagnose which stage is slow | Set separate DNS/connect/handshake/pool/response timeouts |
| Creating an unbounded connection pool | Increases sockets and resources under high load | Limit max connections and pending acquires |
| Logging full TLS/proxy headers | Exposes credentials or sensitive metadata | Mask secrets and log only necessary metadata |

## 17. Production Checklist

### TLS and Certificates

- URL uses a hostname matching the server certificate's SAN.
- Server sends the complete certificate chain.
- Truststore contains approved CAs.
- Certificate is valid and has appropriate usage extensions.
- Hostname verification is enabled.
- SNI sends the correct target hostname.
- mTLS keystore has the right private key and certificate chain if required by the server.
- Private keys/passwords are managed via a secret manager.
- A rotation procedure exists for certificates/truststores with appropriate client restart/rebuild.
- Never use trust-all or disable hostname verification.

### Proxy

- Proxy host/port match the runtime environment.
- `nonProxyHosts` bypasses only hosts meant for direct access.
- CONNECT is permitted by the proxy when calling HTTPS.
- Proxy authentication is separate from origin authentication.
- Proxy passwords are managed as secrets.
- If TLS inspection is used, the proxy CA is verified and configured per policy.
- Clearly establish whether target hostname DNS is resolved by the client or the proxy.

### DNS and Connection Pool

- DNS resolver/query timeout is appropriate.
- DNS is verified from the actual container/VM/Kubernetes namespace.
- Cache TTL aligns with how the service changes IPs.
- Connection max lifetime matches load balancer/DNS rotation.
- `maxIdleTime` does not exceed the peer's idle timeout.
- Max connections and pending acquires are bounded.
- Do not confuse DNS TTL with TCP connection lifetime.

### Timeouts and Observability

- Connect timeout is configured.
- TLS handshake timeout is configured.
- DNS query timeout is configured.
- Proxy connect timeout is configured if using a proxy.
- Appropriate response timeout is configured.
- Overall deadline is configured for the use case.
- Metrics exist for DNS, connect, TLS handshake, response, and connection pool.
- Logs distinguish DNS, TCP, proxy, TLS, HTTP, and decoding errors.
- Never log private keys, passwords, tokens, or raw sensitive headers/bodies.

## 18. Self-Check Exercises

**Exercise 1.** How do truststore and keystore differ?

**Answer:** A truststore holds CAs/trust anchors used to verify peer certificates. A keystore holds the client/server's own private key and certificate chain to present its identity when requested.

**Exercise 2.** The certificate chain is valid, yet the hostname does not match the SAN. Should HTTPS succeed?

**Answer:** No. Trust chain validation and hostname verification are two separate checks. The certificate must be trusted and must identify the hostname in the URL.

**Exercise 3.** Does SNI replace hostname verification?

**Answer:** No. SNI helps the server pick the appropriate certificate; hostname verification checks whether the certificate properly identifies the host.

**Exercise 4.** When is mTLS needed?

**Answer:** When the server requires the client to present a certificate to authenticate the client's identity at the TLS layer. The client needs a key pair/certificate; the server must trust the CA that issued the client certificate.

**Exercise 5.** What is CONNECT used for when calling HTTPS through an HTTP proxy?

**Answer:** CONNECT asks the proxy to create a TCP tunnel to the origin. The TLS handshake then occurs over the tunnel between the client and the target endpoint, unless the proxy performs TLS inspection.

**Exercise 6.** How does a 407 from a proxy differ from a 401 from an origin?

**Answer:** 407 is proxy authentication; 401 is authentication at the target HTTP service. The two sets of credentials and policies are not the same.

**Exercise 7.** DNS TTL expired, yet requests still go to the old IP. Why?

**Answer:** The connection pool may be reusing an already-open TCP connection to the old IP; no new DNS lookup is needed for that connection. Review connection max lifetime/idle policy.

**Exercise 8.** Is `responseTimeout` an overall request deadline?

**Answer:** No. It limits the interval between network-level response reads. Use `Mono.timeout()` or an equivalent deadline to bound the entire publisher.

**Exercise 9.** Why should you not disable hostname verification when a certificate mismatches?

**Answer:** The client would no longer verify server identity against the hostname and could accept a connection to an impostor peer. Fix the SAN, URL host, SNI, or certificate chain instead.

**Exercise 10.** When using an HTTP proxy, DNS resolves on a laptop, yet the application cannot connect. What should you check?

**Answer:** Check proxy reachability/authentication, CONNECT policy, and the DNS view where the target hostname is actually resolved (client runtime or proxy), rather than checking only the laptop.

## 19. Key Takeaways

- WebClient uses `ClientHttpConnector`; Reactor Netty is the common connector with Spring Boot WebFlux.
- HTTPS involves TCP connection, TLS handshake, trust chain validation, and hostname verification.
- Truststore verifies the server; keystore provides client identity when using mTLS.
- SAN must match the hostname in the URI; SNI only helps the server select a certificate.
- Reactor Netty 1.1 enables hostname verification with `secure()` and `secure(Consumer<SslContextSpec>)`; when passing a pre-built `SslProvider`, configure hostname verification explicitly.
- Never use a trust-all manager or disable hostname verification to bypass errors.
- HTTP proxies use CONNECT to build HTTPS tunnels; proxy authentication is distinct from origin authentication.
- Reactor Netty uses an asynchronous DNS resolver by default; DNS cache TTL and connection pool lifetime are two independent mechanisms.
- Configure separate timeouts for pool acquire, DNS, TCP connect, proxy connect, TLS handshake, and response.
- Diagnose by stage: DNS → TCP → proxy → TLS → HTTP → decode.
- Certificates, proxy credentials, and private keys must be managed as secrets; log only safe metadata.

When WebClient cannot connect, first determine **whether the request is stopping at DNS, TCP, proxy, TLS, or HTTP**. Then inspect the configuration for that exact stage; this separates certificate problems from network issues and proxy authentication failures.

## Official Documentation

- Spring Framework 6.2, **WebClient**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html
- Spring Framework 6.2, **WebClient Configuration and ReactorClientHttpConnector**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html
- Reactor Netty 1.1.21, **HTTP Client – SSL/TLS**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/reference/html/index.html
- Reactor Netty 1.1.21, **Proxy Support**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/reference/html/index.html
- Reactor Netty 1.1.21, **Host Name Resolution**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/reference/html/index.html
- Reactor Netty 1.1.21, **Timeout Configuration**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/reference/html/index.html
- Reactor Netty 1.1.21, **`HttpClient` API**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/api/reactor/netty/http/client/HttpClient.html
- Reactor Netty 1.1.21, **`HttpClientSecurityUtils` API**: https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.21/api/reactor/netty/http/client/HttpClientSecurityUtils.html
- Netty, **`SslContextBuilder` API**: https://netty.io/4.1/api/io/netty/handler/ssl/SslContextBuilder.html