# Impact of HTTPS, Proxy, and SSLContext on Using HTTP/3

## 1. Seeing the Issue Clearly: HTTP/3 Is Not Just Enabling TLS

HTTP/3 is a way of transporting HTTP semantics over **QUIC/UDP**, not HTTP/2 under a different name. QUIC integrates the **TLS 1.3** handshake, uses ALPN **h3** to select HTTP/3, and allows multiple independent streams within a single connection. HTTP/2 is typically transported over **TLS/TCP** with ALPN **h2**. The same address starting with **https://** can be used with HTTP/2 or HTTP/3 depending on the actual capabilities of the client and server.

**Java version limitations are the most important starting point:**

| JDK Version | java.net.http.HttpClient.Version | Is HTTP/3 in the built-in HttpClient? |
| --- | --- | --- |
| **Java 17** | HTTP_1_1, HTTP_2 | **No** |
| **Java 21/25** | HTTP_1_1, HTTP_2 | **No** |
| **Java 26 and later** | Adds HTTP_3 via **JEP 517** | **Yes**, under appropriate conditions and must be opt-in |

**JDK 26** was released in March 2026 and added HTTP/3 to HttpClient. A program compiled with JDK 17 cannot reference **HttpClient.Version.HTTP_3**, because the symbol does not exist yet. SSLContext or setApplicationProtocols cannot add QUIC to Java 17's HttpClient on their own. If you want to use HTTP/3 while staying on Java 17, you need a **separate compatible QUIC/HTTP3 library** that is carefully evaluated, or switch to JDK 26+ for testing built-in HTTP/3.

**Even on JDK 26, HTTP/3 is not enabled by default.** HttpClient still prefers HTTP/2 unless **Version.HTTP_3** is set on HttpClient or HttpRequest. The preferred version is only a preference; the response can be HTTP_2 or HTTP_1_1 due to fallback. To know what was actually used, always check **HttpResponse.version()**.

### Six Important Conditions

1. **HTTPS URI:** The JDK 26 HttpClient does not use HTTP/3 for requests whose URI scheme is other than **https**.
2. **HTTP_3 preferred:** JDK 26 requires opt-in and appropriate H3 discovery.
3. **QUIC/UDP reachable:** the server supports H3, and the UDP path and port are open; TCP/443 working is not enough.
4. **Proxy:** the JDK 26 implementation does not support HTTP/3 **when a proxy is selected** for the request.
5. **SSLContext/SSLParameters:** the TLS provider and configuration must support QUIC/TLS 1.3 requirements; a custom TLS context may be incompatible.
6. **Certificate identity:** the TLS server must still be verified against the HTTPS origin; do not disable certificate/hostname validation to achieve H3.

## 2. HTTP/3, HTTPS, QUIC, and TLS 1.3

### 2.1. Different Transport Paths

~~~text
HTTP/2 over HTTPS:                HTTP/3 over HTTPS:

URI https://api.example.com      URI https://api.example.com
          |                                |
       HTTP/2                           HTTP/3
          |                                |
     TLS 1.2/1.3                         QUIC
          |                      (integrated TLS 1.3)
         TCP                               |
          |                               UDP
         IP                                |
                                          IP
~~~

HTTP/3 preserves HTTP concepts such as method, status, header, request, and response, but changes the transport from TCP to QUIC. QUIC uses UDP and can multiplex streams with stream-level packet loss handling; the performance advantage is a **possibility**, not a guarantee that HTTP/3 is always faster than HTTP/2 on every network.

**https:// does not mean HTTP/3.** It is the scheme of an HTTPS origin. In built-in JDK 26, HTTP/3 is considered **only when the URI scheme is https**, but not every HTTPS connection is QUIC. Do not use a fake URL like **http3://** expecting HttpClient to understand it automatically.

### 2.2. TLS 1.3 in QUIC Differs from TLS over TCP

QUIC version 1 uses TLS 1.3 for the handshake inside the QUIC transport. ALPN **h3** advertises the HTTP/3 application protocol. HTTP/2 over TLS/TCP typically uses ALPN **h2**. Creating a TCP SSLSocket and calling setApplicationProtocols("h3") yourself **does not turn it into QUIC/HTTP3**, even when TLS 1.3 is enabled.

With HTTPS, the client needs to verify that the server certificate is trusted and **matches the origin name** in the URI. If the URI is **https://api.example.com**, the certificate must represent **api.example.com**. SNI helps the server select a certificate, and ALPN helps select the protocol, but **they do not replace server identity verification**.

Especially when HTTP/3 is discovered via an alternative service on a different host or port, the endpoint must still be **authorized to represent the origin**. Do not blindly trust a new host just because it appears in the Alt-Svc header.

### 2.3. The UDP Path Can Be Blocked

For example, a firewall allows TCP/443 but blocks UDP/443:

~~~text
JDK 26 client prefers H3
       |
     QUIC/UDP ----X----> server (UDP blocked)
       |
       +--> ANY / fallback-capable mode: HTTP/2 or HTTP/1.1 over TCP
       |
       +--> HTTP_3_URI_ONLY: fails if H3 is unavailable
~~~

Other causes can also make H3 fail: DNS, a load balancer without UDP enabled, NAT/firewall, a different QUIC port, the server not enabling H3, certificate errors, or an incompatible TLS provider. **Response.version() = HTTP_2** is not enough to prove the server lacks H3.

## 3. Discovery: Alt-Svc and HTTP/3 Modes on JDK 26

A server can advertise HTTP/3 via a header:

~~~http
Alt-Svc: h3=":443"; ma=86400
~~~

That header indicates that an H3 service may be used for the origin. **It does not mean the request carrying the header was sent over H3**: the header can appear in an HTTP/2 response. An HTTP/3-capable client can remember this advertisement to try HTTP/3 on subsequent requests.

With **Java 17**, HttpClient can see the Alt-Svc string but **cannot switch to H3 using the built-in client**. You must distinguish between **the server advertising H3** and **the client being capable of and actually using** H3.

### H3_DISCOVERY on JDK 26

**HttpOption.H3_DISCOVERY** and **HttpOption.Http3DiscoveryMode** were added alongside the HTTP/3 API:

| Mode | How H3 is discovered | Can it fall back? |
| --- | --- | --- |
| **ANY** | The implementation decides how to try QUIC, TLS/TCP, and/or Alt-Svc; this is the default when H3 is preferred without a hint | **Yes**, the response can be H1/H2/H3 |
| **ALT_SVC** | Only uses HTTP Alternative Services to find an H3 address; typically uses H1/H2 until an h3 advertisement is received | **Yes** |
| **HTTP_3_URI_ONLY** | Only tries H3 at the exact host/port in the URI, **does not use Alt-Svc** to switch to an alternative service | **No**, fails if H3 is unavailable |

**An important pitfall:** attaching **H3_DISCOVERY** while both the client and request still prefer **HTTP_2** means the hint **does not activate HTTP/3**. You must select **HttpClient.Version.HTTP_3** on the client or request.

With ANY, JDK 26 may try both QUIC and TCP paths, using whichever connection succeeds first or according to its internal algorithm. Therefore, **an initial request returning HTTP_2 is still valid when the client prefers HTTP_3**. Avoid designing tests that rigidly depend on the outcome of a single run.

### Preferred and Strict Configuration

~~~java
// JDK 26+ ONLY, no HTTP_3 enum on Java 17.
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();
~~~

This is a **preference**, not an absolute requirement. To enforce HTTP/3 at the URI, a hint on the request is needed:

~~~java
// JDK 26+ ONLY, when the request or client has HTTP_3 preferred.
HttpRequest request = HttpRequest.newBuilder(uri)
        .setOption(
                HttpOption.H3_DISCOVERY,
                HttpOption.Http3DiscoveryMode.HTTP_3_URI_ONLY)
        .GET()
        .build();
~~~

These are **snippets**; the imports and the **uri** variable are in the full JDK 26 program below. HTTP_3_URI_ONLY only attempts QUIC at the URI's authority; if the server only advertises h3 on a different port, strict URI-only will not use that alternative.

## 4. How Does a Proxy Affect HTTP/3 Availability?

### 4.1. HTTP Proxy Over TCP Is Not QUIC

A traditional HTTP proxy handles HTTPS using HTTP CONNECT, creating a tunnel **over TCP**. Inside the tunnel, the client uses TLS/TCP with the origin or with an endpoint according to network configuration. This mechanism does not automatically provide the QUIC/UDP transport path required for HTTP/3.

There are QUIC proxy, CONNECT-UDP, or MASQUE designs on the market, but **the JDK 26 HttpClient implementation states in its Javadoc that it does not support HTTP/3 when a proxy is selected**. Do not assume that because your organization's proxy has UDP capabilities, the built-in HttpClient will definitely be able to use HTTP/3 through the proxy.

### 4.2. ProxySelector: Configured vs. Actually Selected

HttpClient has **Builder.proxy(ProxySelector)**. If not set, the implementation typically uses the **default proxy selector** and related system properties/proxy policies. A ProxySelector may select a proxy for URI A but return **DIRECT** for URI B.

**client.proxy().isPresent()** only indicates that the client has a selector configured; it **does not prove that a specific request went through a proxy**. You need to check the result of **ProxySelector.select(uri)** with the exact environment and how HttpClient uses it; do not read a single boolean and conclude that H3 is disabled.

| JDK 26 / Connection Route | H3 preferred (ANY/ALT_SVC) | H3 strict URI-only |
| --- | --- | --- |
| No proxy selected | Can use H3 when other conditions are met; can also fall back | Tries H3 directly, errors if unavailable |
| Proxy selected for the URI | **Does not use H3**, falls back to HTTP/2 or HTTP/1.1 if successful | **Fails**, does not fall back automatically |
| Selector configured but returns DIRECT | H3 can still be used | Can try direct H3 |

If your organization requires going through a proxy, **do not bypass proxy policy just to achieve HTTP/3**. Using H2/H1 is the expected outcome within the implementation's limits, or evaluate a proxy/client stack supported by your organization.

### 4.3. Proxy and TLS Truststore

When HTTPS goes through a gateway/proxy with authorized TLS inspection, the certificate presented to the client may be signed by an internal CA. Certificate chain/hostname errors must be handled according to CA policy and allowed endpoints; **do not fix them with a TrustManager that trusts every certificate**. A proxy working with HTTP/2 does not prove that an HTTP/3 path is available.

### 4.4. Proxy Configuration Example in JDK 17

~~~java
// Illustrative snippet. No proxy connection is needed to create the client.
HttpClient client = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .proxy(ProxySelector.of(new InetSocketAddress("127.0.0.1", 3128)))
    .build();
~~~

This code snippet only configures the selector; it **does not enable HTTP/3**. The dummy proxy address in this offline example is not a recommendation for production.

## 5. SSLContext, SSLParameters, and QUIC Compatibility

### 5.1. SSLContext Includes More Than Just the TLS Version

**SSLContext** determines the TLS implementation/provider along with the key manager (client identity for mTLS), trust manager (peer CA/certificate chain), and random source. HttpClient can use the **default SSLContext** or a custom context via **Builder.sslContext(...)**. **SSLParameters** allows configuring the protocols/ciphers/properties to be applied.

~~~text
HttpClient.Builder
    |
    +-- sslContext(context)
    |      |
    |      +-- Provider / TLS implementation
    |      +-- TrustManager / certificate verification
    |      +-- KeyManager / client auth (mTLS)
    |
    +-- sslParameters(params)
    |      |
    |      +-- Enabled TLS versions / cipher / properties
    |
    +-- version(HTTP_3)  [JDK 26+]
             |
        QUIC-compatible TLS context + TLS 1.3 required
~~~

A custom SSLContext may run **TLS/TCP for HTTP/2** but **be incompatible with the QUIC TLS part** that JDK 26 requires. JDK 26 documentation describes the possibility of **UnsupportedProtocolVersionException** when the context/SSLParameters do not allow H3 (when building the client or when sending a strict request). **Do not conclude that all custom SSLContexts are forbidden**; evaluate the actual provider and configuration.

### 5.2. TLS 1.3 Is Necessary but Not Sufficient

HTTP/3 over QUIC version 1 requires TLS 1.3. If SSLParameters only enables **TLSv1.2**, HTTP/3 cannot be established, even though HTTP/2 may still run.

~~~java
// Snippet to check the default context.
SSLContext ctx = SSLContext.getDefault();
boolean tls13 = Arrays.asList(
        ctx.getDefaultSSLParameters().getProtocols())
        .contains("TLSv1.3");
System.out.println("TLSv1.3 enabled: " + tls13);
~~~

Even when it prints true, you still need **JDK 26+ with the HTTP/3 API**, a QUIC-compatible context/provider, a UDP path, no selected proxy, an H3/ALPN-capable server, and a valid certificate. **Enabling TLS 1.3 on a TCP SSLSocket cannot turn HTTP/2 into HTTP/3 by itself.**

### 5.3. Do Not Manually Override ALPN or Disable Verification

HttpClient.Builder.sslParameters(...) notes that some parameters are **managed internally by the HTTP client**, such as the list of application protocols, and may be ignored if set manually by the user. Calling **setApplicationProtocols(new String[]{"h3"})** does not replace selecting **Version.HTTP_3** and certainly cannot add HTTP/3 to JDK 17.

**Do not replace TrustManager with an implementation that accepts all certificates.** When the certificate chain, hostname/SAN, or truststore is wrong, fix the CA, cert, or endpoint; H3 still must verify the origin of the HTTPS URI. For mTLS, configure a valid client certificate/key via KeyManager; do not weaken server authentication just because you are switching to HTTP/3.

## 6. Java 17: Standalone Offline and Live Check Program

The **HttpClientTransportAudit.java** program is designed to compile with **--release 17**. It does not reference the **HTTP_3** symbol so it can run on Java 17. The self-test only reads APIs/config, **does not send any requests**, and does not verify QUIC or a real server.

The live mode takes an https URL, creates an HttpClient preferring HTTP_2, and prints **response.version()** after the actual request. On a **JDK 17 runtime**, the actual version can be HTTP_1_1 or HTTP_2, and cannot be HTTP_3.

### File HttpClientTransportAudit.java

~~~java
import java.net.*;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import javax.net.ssl.SSLContext;

public class HttpClientTransportAudit {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--self-test".equals(args[0])) {
            SSLContext context = SSLContext.getDefault();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .proxy(ProxySelector.of(
                            new InetSocketAddress("127.0.0.1", 3128)))
                    .sslContext(context)
                    .build();

            boolean hasHttp3 = Arrays.stream(HttpClient.Version.values())
                    .anyMatch(v -> "HTTP_3".equals(v.name()));
            boolean tls13 = Arrays.asList(context.getDefaultSSLParameters()
                    .getProtocols()).contains("TLSv1.3");

            System.out.println("HTTP versions: " +
                    Arrays.toString(HttpClient.Version.values()));
            System.out.println("HTTP/3 enum present: " + hasHttp3);
            System.out.println("Preferred version: " + client.version());
            System.out.println("Proxy configured: " +
                    client.proxy().isPresent());
            System.out.println("TLSv1.3 enabled: " + tls13);
            System.out.println("No network request performed");
            return;
        }

        if (args.length != 1 || !args[0].startsWith("https://")) {
            throw new IllegalArgumentException(
                    "Usage: java HttpClientTransportAudit --self-test | https-url");
        }

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(7))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(args[0]))
                .timeout(Duration.ofSeconds(15))
                .GET()
                .build();

        HttpResponse<Void> response =
                client.send(request, HttpResponse.BodyHandlers.discarding());
        System.out.println("Status: " + response.statusCode());
        System.out.println("Actual version: " + response.version());
        response.headers().firstValue("alt-svc")
                .ifPresent(v -> System.out.println("Alt-Svc: " + v));
    }
}
~~~

### How to Run

~~~bash
javac --release 17 -encoding UTF-8 HttpClientTransportAudit.java
java HttpClientTransportAudit --self-test
~~~

**Actual stdout verified on OpenJDK 21, compiled with --release 17, default SSLContext in the test environment:**

~~~text
HTTP versions: [HTTP_1_1, HTTP_2]
HTTP/3 enum present: false
Preferred version: HTTP_2
Proxy configured: true
TLSv1.3 enabled: true
No network request performed
~~~

Distinguish what is **always true on a JDK 17 runtime** (only H1/H2 enum values) from what is **configuration-dependent** (TLSv1.3 enabled may differ if the provider/security policy differs). Proxy configured=true is only because the code attaches a proxy selector in the self-test; **no connection is made to 127.0.0.1:3128**.

When running **the same class compiled with --release 17 on JDK 26**, Version.values may also list HTTP_3 because the enum is loaded from the runtime. This is normal behavior and does not mean the source code uses new Java 26 APIs.

To run a live check against an endpoint you are authorized to access:

~~~bash
java HttpClientTransportAudit https://api.example.com/
~~~

**The URL is illustrative only.** When running live, the code uses the environment's default ProxySelector (not the dummy proxy address from the self-test), verifies the certificate per HttpClient policy, and prints the actual status/version; if the response has Alt-Svc, it prints that header too. **Network results cannot have fixed stdout**; do not claim an HTTP_3 response just because Alt-Svc is present.

## 7. JDK 26+: Program Requesting HTTP/3, with Optional Strict Mode

This example **only compiles/runs on JDK 26 and later**, not for --release 17. It is based on JDK 26 Javadoc and JEP 517; it does not assume the illustrative endpoint is reachable or that the current network allows UDP.

Normal mode: **prefers HTTP_3**, accepts fallback under the default **ANY** mode. **--require-h3** mode: adds **HTTP_3_URI_ONLY**, rejects fallback, and only attempts H3 at the URI's authority. Both use the default SSLContext, **do not disable certificate verification**, and preserve the JVM's default proxy policy.

### File Http3Probe26.java

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Arrays;
import javax.net.ssl.SSLContext;

public class Http3Probe26 {
    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            throw new IllegalArgumentException(
                    "Usage: java Http3Probe26 https-url [--require-h3]");
        }

        boolean strict = args.length == 2 &&
                "--require-h3".equals(args[1]);
        if (args.length == 2 && !strict) {
            throw new IllegalArgumentException(
                    "Only --require-h3 is supported");
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme()) ||
                uri.getHost() == null) {
            throw new IllegalArgumentException(
                    "A valid https:// URI is required");
        }

        SSLContext context = SSLContext.getDefault();
        boolean tls13 = Arrays.asList(
                context.getDefaultSSLParameters().getProtocols())
                .contains("TLSv1.3");
        if (!tls13) {
            throw new IllegalStateException(
                    "HTTP/3 requires TLSv1.3 support");
        }

        HttpRequest.Builder requestBuilder =
                HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(20))
                        .GET();
        if (strict) {
            requestBuilder.setOption(
                    HttpOption.H3_DISCOVERY,
                    HttpOption.Http3DiscoveryMode.HTTP_3_URI_ONLY);
        }

        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .sslContext(context)
                .connectTimeout(Duration.ofSeconds(8))
                .build()) {

            HttpResponse<Void> response = client.send(
                    requestBuilder.build(),
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("Status: " + response.statusCode());
            System.out.println("Actual version: " + response.version());
            response.headers().firstValue("alt-svc")
                    .ifPresent(v -> System.out.println("Alt-Svc: " + v));

            if (strict &&
                    response.version() != HttpClient.Version.HTTP_3) {
                throw new IllegalStateException(
                        "HTTP/3 was required but not used");
            }
        }
    }
}
~~~

### Compiling and Running with JDK 26+

~~~bash
javac Http3Probe26.java
java Http3Probe26 https://api.example.com/
java Http3Probe26 https://api.example.com/ --require-h3
~~~

**No fixed stdout is printed** for the JDK 26 program because the result depends on the hostname, network, server, certificate, proxy, and QUIC. This article does not claim any HTTP_3 result without an actual **response.version() = HTTP_3**. The JDK 26 file above was written according to public API docs, whereas the Java 17 example in Section 6 was compiled and run directly with javac --release 17.

If a custom SSLContext is incompatible with QUIC or SSLParameters does not enable TLS 1.3, requesting HTTP/3 may fail with **UnsupportedProtocolVersionException** or an error with a corresponding cause. Do not work around this by allowing untrusted certificates.

### ALT_SVC on JDK 26

To wait for the server to advertise H3 first, you can set **HttpOption.H3_DISCOVERY** to **HttpOption.Http3DiscoveryMode.ALT_SVC** on a request where HTTP_3 is preferred:

~~~java
// JDK 26+; illustration assuming HttpRequest.Builder rb is already available.
rb.setOption(
        HttpOption.H3_DISCOVERY,
        HttpOption.Http3DiscoveryMode.ALT_SVC);
~~~

**ALT_SVC** typically causes initial requests to use H1/H2 until Alt-Svc h3 information is received. Do not confuse it with HTTP_3_URI_ONLY (which enforces H3 directly on the same authority). You must inspect each response.version.

## 8. Distinguishing Causes When HTTP_3 Does Not Appear

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| **Java 17 compile error on HTTP_3** | No enum/HTTP3 implementation | Upgrade to JDK 26+ or use a separate QUIC/HTTP3 library |
| **HTTPS response is HTTP_2** | May be valid fallback | Check preferred version, response.version, proxy route, UDP/H3 |
| **Alt-Svc h3 present but H3 not used** | Alt-Svc is not proof of protocol switch | Check runtime H3 support, discovery, subsequent requests |
| **JDK 26 has a proxy selected** | Built-in HTTP/3 through proxy is not supported | Accept H2/H1 per proxy policy or evaluate another permitted stack |
| **Strict H3 fails when a proxy is present** | HTTP_3_URI_ONLY does not fall back | This is expected in strict mode; do not drop a required proxy |
| **TCP/443 works but QUIC fails** | UDP/port blocked, server has not enabled H3 | Investigate network path and UDP listener |
| **Custom SSLContext runs HTTP/2 but H3 fails** | Provider is not QUIC-compatible or SSLParameters lacks TLS 1.3 | Check provider, enabled protocols, and JDK 26 docs |
| **Certificate handshake error** | Invalid CA/chain/SAN/hostname or algorithm | Fix certificate and truststore, keep verification |
| **URL has http scheme** | Built-in JDK 26 does not use H3 for this URI | Use a proper HTTPS origin if the service supports it |
| **Same code gives different results on CI** | Different JDK, proxy selector, DNS, truststore, or egress | Compare environments and actual version |

### Things You Should Not Do

- Do not treat **preferred HTTP_3** as the actual result; always check **response.version()**.
- Do not treat **Alt-Svc: h3** as confirmation that the preceding request used QUIC.
- Do not think **SSLSocket TLSv1.3 over TCP** is equivalent to HTTP/3.
- Do not bypass an **organizational proxy** just because JDK 26 built-in does not support H3 through a proxy.
- Do not replace **TrustManager** or hostname checking with an accept-all mechanism.
- Do not remove **disabledAlgorithms** in java.security just to make H3 work.
- Do not assume every custom SSLContext supports QUIC.
- Do not hard-code **Status=200** or **Actual version=HTTP_3** in network tests, as endpoints and networks vary.

## 9. Meaningful Test Scenarios

**Test A — Java 17 offline.** Run the Section 6 program with --self-test; prove that the runtime API only has H1/H2 while understanding the configured proxy selector and SSLContext. Do not claim H3 has been verified.

**Test B — Java 17 live.** Send a request to an authorized HTTPS endpoint; print the status and actual HTTP version. Alt-Svc, if present, is only an advertisement; Java 17 built-in still does not make an HTTP/3 request.

**Test C — JDK 26 H3 preferred.** Use Http3Probe26 in default mode. May receive HTTP_3/H2/H1 depending on QUIC, discovery, server, and proxy. Record all test conditions instead of only recording status 200.

**Test D — JDK 26 strict.** Use --require-h3, clearly identifying a host/port that supports QUIC. If H3 cannot be used, it must fail; do not treat HTTP_2 as PASS.

**Test E — Proxy selected.** Configure a proxy in an authorized test environment. With built-in JDK 26, verify that H3 is not used; strict mode must fail. Do not use tricks to bypass the proxy when policy requires it.

**Test F — SSLContext/TLS.** Compare a provider and SSLParameters with TLSv1.3 against a case with only TLSv1.2 enabled. H3 must be unusable when TLS 1.3 is missing; adjust per policy without downgrading security.

**Test G — Certificate verification.** An endpoint with a valid chain/SAN can succeed. An untrusted endpoint or mismatched hostname must be rejected **even when attempting H3**; this confirms SSLContext did not accidentally skip verification.

### Production Checklist

1. Record the actual JDK vendor/version and supported HttpClient.Version values.
2. Verify the request uses an https URI and the correct hostname.
3. Set preferred H3 on JDK 26+ if needed, and choose the right discovery mode.
4. Log the actual HttpResponse.version() per request.
5. Observe Alt-Svc, but do not infer the version from the header.
6. Check whether the proxy selector chooses **a proxy or DIRECT** for that exact URI.
7. Verify the UDP/QUIC path, port, and ALPN/server H3 support.
8. Check SSLContext provider, TLSv1.3, SSLParameters, and CA/hostname.
9. Test fallback and strict H3 separately; define expectations for each environment.
10. Preserve certificate/hostname verification and network policies when configuring.

## 10. Self-Check Questions

**Question 1.** Why does HttpClient.Version.HTTP_3 not compile on JDK 17?  
**Answer:** JDK 17 only has HTTP_1_1 and HTTP_2 in the enum; built-in H3 support was added in JDK 26.

**Question 2.** Does an HTTPS request always use HTTP/3?  
**Answer:** No. The HTTPS scheme does not determine the transport; H3 support, opt-in, QUIC, TLS, and a suitable network path are required.

**Question 3.** Does enabling TLSv1.3 on a TCP SSLSocket turn HTTP/2 into HTTP/3?  
**Answer:** No. HTTP/3 uses QUIC/UDP and integrated TLS 1.3, not just a parameter change on SSLSocket.

**Question 4.** What does Alt-Svc h3 on an HTTP/2 response prove?  
**Answer:** The server is advertising an H3 alternative service; it does not prove the just-completed request used H3.

**Question 5.** On JDK 26, if HTTP_3 is preferred but response.version is HTTP_2, is that an error?  
**Answer:** Not necessarily. It may be valid fallback; check discovery, proxy, UDP, and the server.

**Question 6.** Is having a configured ProxySelector enough to conclude HTTP/3 is disabled?  
**Answer:** No. You must know whether the ProxySelector **actually selects a proxy** for the URI or returns DIRECT.

**Question 7.** In JDK 26, when a proxy is actually selected, what happens with strict HTTP_3_URI_ONLY?  
**Answer:** The request fails because the implementation does not support HTTP/3 over a proxy and strict mode does not fall back.

**Question 8.** Is an SSLContext with TLSv1.3 sufficient for H3?  
**Answer:** Not yet. The provider must also be QUIC-compatible, the certificate must be valid, UDP networking must work, and the client must support HTTP/3.

**Question 9.** When H3 fails due to a certificate error, should you replace TrustManager with one that accepts everything?  
**Answer:** No. Fix the trust anchor/certificate/SAN at the source while keeping verification intact.

**Question 10.** When you want to wait for Alt-Svc before using H3, which mode is appropriate?  
**Answer:** ALT_SVC, when HTTP_3 preferred is already set on JDK 26+.

**Question 11.** When you want to force HTTP/3 directly at the URI's host/port only, which mode do you use?  
**Answer:** HTTP_3_URI_ONLY; it does not use Alt-Svc to switch host/port and does not fall back.

**Question 12.** How can you be sure a request used HTTP/3?  
**Answer:** Check **HttpResponse.version() == HTTP_3** on an H3-capable runtime; combine with connection logs/telemetry if investigation is needed.

## Conclusion

**HTTPS** is the origin and peer-verification condition, and in the JDK 26 HttpClient it is also a required scheme condition for H3. **Proxy** determines the connection route; when built-in JDK 26 selects a proxy, H3 is not used and the request must fall back or fail in strict mode. **SSLContext/SSLParameters** supply the TLS provider/trust/key/protocols, and can make HTTP/3 unavailable if QUIC/TLS 1.3 requirements are not met, even if HTTP/2 over TCP still runs.

With **Java 17**, the standard HttpClient **does not yet support HTTP/3**. With **JDK 26+**, enabling preferred HTTP_3 is not enough: you need QUIC/UDP, appropriate discovery, no blocking proxy route, a compatible TLS context, and proper certificate verification. Base your conclusions on the **actual HttpResponse.version()**, not on an HTTPS URL or an Alt-Svc header alone.

### Official References

- [Java 17 — HttpClient.Version](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Version.html): HTTP_1_1 and HTTP_2.
- [Java 17 — java.net.http package](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/package-summary.html): scope of the available HttpClient.
- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517): HTTP/3 added in JDK 26.
- [Java 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): H3 selection, HTTPS/proxy/SSLContext.
- [Java 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): proxy, SSLContext, SSLParameters, and version.
- [Java 26 — HttpClient.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html): HTTP_3 enum.
- [Java 26 — HttpOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.html): H3_DISCOVERY and proxy limitations.
- [Java 26 — Http3DiscoveryMode](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html): ANY, ALT_SVC, HTTP_3_URI_ONLY.
- [Java 26 — UnsupportedProtocolVersionException](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/UnsupportedProtocolVersionException.html): incompatible SSLContext.
- [Oracle Java team — HTTP Client Updates in Java 26](https://inside.java/2026/03/04/jdk-26-http-client/): H3 discovery strategies.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html): QUIC, TLS 1.3, ALPN h3, Alt-Svc, origin authority.
