# Distinguishing HTTP/1.1, HTTP/2, and TLS Requirements

**Module:** Spring Boot - web-runtime  
**Parent topic:** HTTP Foundation

## 1. Objectives and Proper Distinctions

After this lesson, you should be able to explain how HTTP/1.1 and HTTP/2 differ in message transmission, concurrent request handling, header encoding, and latency impact; while clearly separating **HTTP version**, **HTTPS/TLS**, and **Spring Boot configuration**.

Three sentences to remember:

- **HTTP/1.1 and HTTP/2** both implement the core HTTP semantics: method, URI, status, headers, request body, and response body. Controllers do not need business-logic changes just because the transport uses HTTP/2.
- **TLS** is the transport protection layer providing encryption, integrity verification, and server authentication via certificates. **HTTPS does not mean HTTP/2**: HTTP/1.1 also runs over TLS.
- **HTTP/2 has two TLS-related modes:** **h2** is HTTP/2 over TLS (standard for browsers); **h2c** is HTTP/2 over cleartext TCP without TLS (usable in some internal connections). When using h2, the specification requires TLS 1.2 or higher.

## 2. How Does HTTP/1.1 Work?

HTTP/1.1 uses messages with a text-based start line and headers, followed by a body according to message framing rules. Illustrative request and response for a simple resource:

~~~http
GET /hello HTTP/1.1
Host: example.test
Accept: text/plain

~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Length: 2

OK
~~~

Actual wire transmission uses standard HTTP line endings; this presentation is formatted for readability. Method **GET**, status **200**, headers, and body retain the exact same meaning in HTTP/2.

Important operational characteristics:

1. **Connections can be reused.** HTTP/1.1 supports persistent connections by default: multiple request/response pairs can reuse one TCP connection instead of reconnecting per resource. Keeping a connection open does not automatically enable interleaved responses.
2. **A typical HTTP/1.1 connection does not multiplex independent requests.** Pipelining was defined to send multiple requests before receiving responses, yet responses still had to return in order; browsers rarely use it due to complexity and head-of-line blocking.
3. **For concurrency, clients often open multiple TCP connections** to the same host or maintain connection pools. This consumes extra sockets, handshakes, and resources.
4. **HTTP-layer head-of-line blocking:** on a single connection/pipeline, a slow earlier response delays later responses. HTTP/1.1 has no concept of independent streams like HTTP/2.

Example: a page needs CSS, JavaScript, and images; with HTTP/1.1, the browser can open multiple connections to fetch concurrently, yet within each connection it remains bound by sequential ordering limits.

## 3. What Does HTTP/2 Change?

HTTP/2 is currently standardized in **RFC 9113**. It preserves HTTP semantics while replacing the TCP wire representation with **binary framing**:

- **Frames** are transmission units, including **HEADERS** (request/response metadata), **DATA** (body), **SETTINGS** (connection parameter negotiation), and **WINDOW_UPDATE** (flow control).
- **Streams** are logical flows bound to a single request/response exchange. Many concurrent streams exist on the same TCP connection; frames from different streams can be interleaved.
- **Multiplexing** prevents a slow response from forcing other responses to wait in line at the HTTP/2 layer. Parallelism remains constrained by max concurrent streams, memory, flow control, and server resources.
- **HPACK** compresses headers, reducing redundant header names/values across requests on a connection. **HPACK does not compress the response body**; payload compression like gzip/br is a separate mechanism.
- **HTTP/2 is not plain HTTP/1.1 text with encryption added.** Logical HTTP/2 fields are sent inside HEADERS frames using the spec's binary encoding; a single packet does not necessarily hold an entire request.

Logical representation of the same request in HTTP/2 (this is **not raw bytes on the wire**):

~~~text
:method: GET
:scheme: https
:authority: example.test
:path: /hello
accept: text/plain
~~~

The four colon-prefixed fields are **pseudo-headers** representing method, scheme, authority, and path. HTTP/2 requires lowercase header names in encoded headers. What the application sees through Spring MVC is still a GET request to path `/hello`.

**Key limitation:** HTTP/2 still runs over **TCP**. If a TCP segment is lost, TCP must recover bytes in order, which can stall all HTTP/2 streams sharing that connection. HTTP/2 solves head-of-line blocking **at the HTTP layer**, yet it **does not eliminate TCP head-of-line blocking**. Do not assume HTTP/2 is faster than HTTP/1.1 in every scenario.

## 4. Practical Comparison Table

| Aspect | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Method/status/URI semantics | Yes | Preserved |
| Wire representation | Text start line and headers | Binary frames and logical streams |
| Multiple requests per connection | Sequential reuse; limited pipelining | Multiplexes multiple streams on one connection |
| HTTP-layer head-of-line blocking | Pronounced in pipelining | Greatly reduced via interleaved frames |
| TCP-layer packet loss | Affects the connection | Still affects all streams sharing the connection |
| Headers | Repeated per message | HPACK header compression |
| TLS | Optional at HTTP/1.1 protocol level; HTTPS adds TLS | h2 uses TLS 1.2+; h2c is cleartext TCP |
| Common environments | HTTP or HTTPS, legacy and modern systems | Browsers over HTTPS/h2; some internal h2c hops |

HTTP/2 includes server push in the specification, though real-world client support and utility vary; **do not** treat server push as a prerequisite for HTTP/2 or the main reason to adopt it.

## 5. TLS and HTTPS: Exact Requirements

**TLS (Transport Layer Security)** protects data in transit between two TLS endpoints: encryption prevents eavesdropping, integrity checks detect tampering, and certificate chain / trust store / hostname verification authenticates server identity. TLS **does not** replace application-layer authentication or authorization; endpoints must still verify users and permissions appropriately.

Distinguish these cases:

| Connection | HTTP version | TLS | Conclusion |
| --- | --- | --- | --- |
| http://... with HTTP/1.1 | HTTP/1.1 | No | Content can travel in cleartext on the network |
| https://... with HTTP/1.1 | HTTP/1.1 | Yes | Normal TLS-protected HTTP/1.1 (HTTPS) |
| https://... with ALPN selecting h2 | HTTP/2 (h2) | **Yes, TLS 1.2+** | Standard browser usage of HTTP/2 |
| http://... with HTTP/2 prior knowledge | HTTP/2 (h2c) | No | Use only when both ends and a trusted network support it |

Per RFC 9113 for **HTTP/2 over TLS**:

1. **TLS 1.2 or higher is required.** TLS 1.3 is the modern choice; legacy TLS versions should not be configured. With TLS 1.2, HTTP/2 restrictions against weak features/cipher suites must be respected.
2. **ALPN (Application-Layer Protocol Negotiation) selects the application protocol during the TLS handshake.** Clients can advertise **h2** and **http/1.1**; the server picks one it supports. If the connection negotiates **http/1.1**, merely enabling HTTP/2 in app config does not mean requests use HTTP/2.
3. **SNI (Server Name Indication)** helps the server select the right certificate/host when serving multiple hostnames. Certificates must be valid, trusted by the client, and match the hostname; SNI, ALPN, and certificates serve distinct roles.
4. When using **TLS 1.2 with h2**, the spec forbids TLS compression and TLS renegotiation and restricts legacy ciphers. Server and TLS library configuration—not just an HTTP/2 toggle—determines compliance.
5. **h2c is unencrypted.** RFC 9113 describes starting via prior knowledge on cleartext TCP; the HTTP/1.1 **Upgrade: h2c** mechanism is deprecated in the current spec. Regular web browsers use h2 over HTTPS rather than h2c.

Conceptual handshake when a client visits https://example.test/hello and the server supports h2:

~~~text
Client                           Server / TLS termination
  |---- TCP connect ------------------------>|
  |---- TLS ClientHello: SNI, ALPN h2 ------>|
  |<--- TLS selects h2, sends certificate ---|
  |---- Verify certificate, complete TLS --->|
  |==== Encrypted TLS channel ===============|
  |---- HTTP/2 connection preface/SETTINGS ->|
  |<--- SETTINGS ----------------------------|
  |---- HEADERS stream 1 ------------------->|
  |---- HEADERS stream 3 ------------------->|
  |<--- DATA/HEADERS on streams -------------|
~~~

This diagram shows only the conceptual flow: exact ordering/details of handshakes, SETTINGS, and frames may vary. One TLS connection can carry many HTTP/2 streams; **there is no separate TLS handshake per stream**.

## 6. Applying in Spring Boot (Java 17+, Spring Boot 3.x)

Spring Boot enables HTTP/2 via **server.http2.enabled=true**. When SSL/TLS is enabled, the listener serves **h2**; when SSL is disabled, compatible servers can serve **h2c**. The example below uses **spring-boot-starter-web** (Spring MVC + embedded Tomcat) in a minimal application. For Jetty, Reactor Netty, or reverse proxies, verify capabilities and dependencies against the actual web server.

**File src/main/java/com/example/httplab/HttpLabApplication.java:**

~~~java
package com.example.httplab;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpLabApplication.class, args);
    }
}

@RestController
class ProtocolController {
    @GetMapping("/protocol")
    String protocol(HttpServletRequest request) {
        return request.getProtocol();
    }
}
~~~

Prerequisites to run: a Spring Boot 3.x project with **org.springframework.boot:spring-boot-starter-web**, Java 17+, and the class placed under a component-scanned package. The endpoint returns the protocol string observed at the Servlet container; output may be **HTTP/1.1** or **HTTP/2.0** depending on the actual connection.

**Generate a self-signed certificate for local testing only** (JDK keytool command, run from the project root after ensuring src/main/resources exists):

~~~bash
keytool -genkeypair -alias localdev -keyalg RSA -keysize 3072 -validity 30 -storetype PKCS12 -keystore src/main/resources/localdev.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

**File src/main/resources/application.properties:**

~~~properties
server.port=8443
server.http2.enabled=true
server.ssl.enabled=true
server.ssl.key-store=classpath:localdev.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
~~~

In a Bash shell, set the matching password and start the app using the Gradle wrapper of a configured Spring Boot project:

~~~bash
export TLS_KEYSTORE_PASSWORD=changeit
./gradlew bootRun
~~~

The password and self-signed certificate above are **for local learning only**. Never commit real private keys, keystores, or passwords; production deployments require proper secret management, valid certificates, TLS policies, and certificate renewal. This example configures HTTPS on port **8443**; it does not automatically open an extra HTTP listener on port 8080.

**Verify the negotiated version** using a curl build with HTTP/2 support (run **curl -V** to check for the HTTP2 feature):

~~~bash
curl -k -sS --http1.1 -o /dev/null -w '%{http_version}' https://localhost:8443/protocol
curl -k -sS --http2 -o /dev/null -w '%{http_version}' https://localhost:8443/protocol
curl -vk --http2 https://localhost:8443/protocol
~~~

- The first command should print **1.1**.
- The second command should print **2** **if ALPN selects h2**. If it prints **1.1**, inspect server/proxy/TLS configuration and logs, because **--http2 over HTTPS requires negotiation and can fall back**.
- The third command shows the ALPN trace and HTTP status line for confirmation. **-k** skips certificate verification only because this is a local self-signed certificate; never use **-k** by default against real systems.

**Testing h2c separately in a controlled environment:** remove the server.ssl.* properties, set **server.port=8080** and **server.http2.enabled=true**, restart, and use a client supporting prior knowledge:

~~~bash
curl --http2-prior-knowledge -sS -o /dev/null -w '%{http_version}' http://localhost:8080/protocol
~~~

If both server and curl support h2c prior knowledge, the expected output is **2**. This is **an alternative configuration** to the HTTPS demo above, not opening both ports simultaneously just by adding a few property lines. Do not expose h2c directly over untrusted networks.

## 7. TLS Termination and Reverse Proxies in Production

Many systems do not have Spring Boot terminate TLS directly with browsers:

~~~text
Browser ---- HTTPS + h2 ----> Reverse proxy / Load balancer
                                      |
                                      +---- HTTP/1.1 or h2c/h2 ----> Spring Boot
~~~

Here, **the HTTP version can differ across the two hops**. Browsers can speak h2 to Nginx / Ingress / Load Balancer while the proxy speaks HTTP/1.1 to Tomcat. This still provides h2 benefits on the browser–proxy leg; the backend's **server.http2.enabled** flag does not automatically change the public leg's protocol. Conversely, if the proxy needs HTTP/2 on the upstream hop, the proxy must also be configured to use it.

In operations, identify clearly where **TLS termination** occurs, verify ALPN and certificates at that edge, check the upstream protocol separately, and only trust forwarded headers such as Forwarded/X-Forwarded-* from trusted proxies. External HTTPS does not guarantee the proxy–backend hop is encrypted; consider internal TLS/mTLS depending on your trust model.

## 8. When Does HTTP/2 Help and What Should You Measure?

HTTP/2 typically helps when a client fetches **many small/independent resources** with high concurrency, because it reduces connection count and header overhead. For APIs with a single large request or lossy networks, speed may not noticeably improve; HTTP/2 also requires proper stream limits, flow control, and frame handling.

When comparing, keep payloads and client conditions constant and measure **p50/p95/p99 latency**, throughput, connection count, CPU, proxy load, packet loss, TLS handshake time, and negotiated HTTP version. Do not flip a flag and assume it is already optimal. **HTTP/3** uses QUIC with different packet-loss behavior; it is a separate version, not another name for HTTP/2.

## 9. Common Issues and Troubleshooting

| Symptom or claim | Root cause to check / proper understanding |
| --- | --- |
| Enabled server.http2.enabled=true but curl still shows 1.1 | Check the actual endpoint hit, front proxies, whether SSL is enabled, whether ALPN chose h2, and whether the server supports h2. |
| Browser does not use h2 with http://localhost | h2c is not a standard browser HTTP/2 path; test with HTTPS/h2 or an h2c-capable client. |
| curl reports --http2 is unsupported | Current libcurl build lacks the HTTP2 feature; check curl -V and use a build that supports it. |
| SSL handshake or certificate verification fails | Check the HTTPS port, keystore path/password, hostname/SAN, certificate validity and trust chain, and TLS/cipher config. |
| All streams slow down together on a lossy network | HTTP/2 multiplexes at the application layer yet shares one TCP connection; check packet loss, flow control, and network health. |
| Using HTTPS guarantees it is HTTP/2 | HTTPS can carry HTTP/1.1; inspect ALPN results or client-reported protocol. |
| HTTP/2 automatically secures endpoints | TLS does not replace authorization, user authentication, input validation, or application policies. |
| Backend receives HTTP/1.1 even though browser uses h2 | The proxy may actively translate protocol versions between hops; inspect each hop independently. |

## 10. Self-Check Questions

1. **Does HTTP/2 change GET/POST or status codes compared to HTTP/1.1?** No; differences are mainly wire representation/transport, multiplexing, header compression, and flow control.
2. **Does HTTP/2 require TLS in every case?** No: h2 requires TLS 1.2+; h2c is cleartext TCP when supported. In browsers, h2 over HTTPS is the norm.
3. **Does one slow request in HTTP/2 block all other requests?** Usually not at the HTTP frame/stream layer, though TCP packet loss or resource/flow-control limits can still affect all streams.
4. **Does enabling HTTP/2 in Spring Boot automatically issue a certificate?** No. You must configure TLS/certificates or handle TLS termination at a proxy.
5. **Where should you check to see if real users are using HTTP/2?** Check the client–proxy/edge hop via ALPN, DevTools, or curl; backend logs may show another version if a proxy translates protocols.

## 11. References

- **IETF RFC 9113 – HTTP/2:** https://www.rfc-editor.org/rfc/rfc9113 (specification for framing, multiplexing, h2/h2c, ALPN, TLS 1.2+).
- **Spring Boot 3.3 – Embedded Web Servers:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html (server.http2.enabled, SSL, and embedded server support).
- **curl manual:** https://curl.se/docs/manpage.html (--http1.1, --http2, --http2-prior-knowledge options, inspecting negotiated protocol).