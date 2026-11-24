# Distinguishing h2, h2c, and Protocol Negotiation Mechanisms

**Module:** Spring Boot - web-runtime  
**Parent topic:** TLS and HTTP/2

## 1. Practical Problem: Enabling HTTP/2 Is Not Enough to Know Which Protocol Requests Use

You configure **server.http2.enabled=true** in a Spring Boot application. When calling **https://api.example.com** in a browser, DevTools shows **h2**. Yet when calling **http://localhost:8080** via curl, you may see **HTTP/1.1**, **h2c**, or a failed request depending on how the client initiates the connection. Placing the same server behind a reverse proxy yields yet another result: the browser speaks **h2** to the proxy while the proxy speaks **HTTP/1.1** or **h2c** to Spring Boot.

The difference lies in the **secure transport** and the **mechanism both sides use to agree on HTTP/2**, not merely the Java endpoint configuration.

This lesson clarifies:

1. **h2** and **h2c** share the exact same HTTP/2 framing, streams, flow control, and semantics, differing only in **TLS**.
2. With **HTTPS**, HTTP/2 must be identified via **ALPN during the TLS handshake**, using the protocol identifier **h2**; **h2c is not a valid ALPN value for TLS connections**.
3. With **cleartext HTTP**, HTTP/2 is specified by RFC 9113 via **prior knowledge**, sending the HTTP/2 connection preface directly. The **HTTP/1.1 Upgrade: h2c** mechanism is a historical form from RFC 7540 that RFC 9113 marked deprecated/obsolete, though some servers/clients still support it.
4. Setting **server.http2.enabled=true** in Spring Boot 3.3 can enable **h2 when SSL is configured**, or **h2c when SSL is not enabled**, provided the embedded server supports it; however, **clients and every proxy hop** must still speak a compatible protocol.
5. Verify using **curl, openssl, HTTP response metadata**, and real logs; never infer from URLs, ports, or property names alone.

## 2. Where Are h2 and h2c Alike and Different?

| Property | **h2** | **h2c** |
| --- | --- | --- |
| HTTP semantics and wire framing | HTTP/2 binary frames, streams, HPACK headers, multiplexing | The exact same HTTP/2 mechanism |
| Transport channel | **HTTP/2 running over TLS over TCP** | **HTTP/2 running directly over cleartext TCP**, without TLS on that hop |
| Common URI scheme | **https://** | **http://** on a non-TLS hop |
| Initial identification | **TLS ALPN** selects protocol ID **h2** | **Prior knowledge**: client knows in advance the server supports it and sends the HTTP/2 preface directly |
| HTTP/1.1 Upgrade | Never uses **Upgrade: h2** to enter TLS HTTP/2 | **Upgrade: h2c** was defined in RFC 7540 and is obsolete per RFC 9113 |
| In-transit encryption on hop | TLS security when configured/verified properly | **None**; traffic can be observed/modified over untrusted networks |
| Public web suitability | Standard in browsers/HTTPS CDNs | Mainly for controlled internal networks, backend hops, or dedicated clients; browsers generally do not rely on h2c |
| HTTP/2 frames after setup | **SETTINGS**, **HEADERS**, **DATA**, **WINDOW_UPDATE**, etc. | Exact same frame structure |

**Do not say "h2 is HTTP/2, h2c is a different protocol from HTTP/2."** Both are HTTP/2; the **c** in `h2c` emphasizes cleartext, while **h2** is the identifier used when HTTP/2 runs over TLS.

**Do not say "HTTP/2 always requires TLS."** The standard defines HTTP/2 over cleartext TCP with prior knowledge. However, **HTTP/2 over HTTPS strictly requires TLS and ALPN**, whereas cleartext HTTP/2 has none of TLS's security guarantees. Consequently, public browser HTTPS traffic normally uses `h2`, while backends behind TLS termination may use `h2c`.

### Additional Comparison with HTTP/1.1 and HTTP/3

| Connection style | Transport | Protocol selection | Remember |
| --- | --- | --- | --- |
| HTTP/1.1 + HTTPS | TCP + TLS | Can pick **http/1.1** via ALPN or compatibility fallback | HTTPS **does not equal** h2. |
| HTTP/2 h2 | TCP + TLS | **ALPN h2** | HTTP/2 over a TLS connection. |
| HTTP/2 h2c | Cleartext TCP | **Prior knowledge**, or legacy Upgrade where still supported | No TLS on this hop. |
| HTTP/3 h3 | QUIC (UDP + integrated TLS 1.3) | HTTP/3 mechanics and ALPN **h3** | Not a new name for h2 or h2c. |

HTTP/2 uses multiplexing so multiple streams share one TCP connection; it has **stream-level and connection-level flow control**. HPACK compresses HTTP/2 **header fields**; this is a separate mechanism from **gzip/br on response bodies** via `Content-Encoding`.

## 3. ALPN: Negotiating HTTP/2 During the TLS Handshake

**ALPN** (*Application-Layer Protocol Negotiation*, RFC 7301) is a TLS extension allowing client and server to pick an application protocol on the **same TLS connection**. For h2, the client offers a list of usable protocol IDs such as **h2** and **http/1.1**. The server picks a value supported by both.

Abbreviated timeline:

~~~text
Client                                      TLS server / Spring Boot / Edge
   |                                                    |
   | TCP connect                                        |
   |--------------------------------------------------->|
   | TLS ClientHello: ALPN = ["h2", "http/1.1"]         |
   | TLS ClientHello: SNI = "api.example.com"           |
   |--------------------------------------------------->|
   |       TLS handshake, certificate, key exchange     |
   |<-------------------------------------------------->|
   | TLS ALPN result: "h2"                               |
   |<---------------------------------------------------|
   |                                                    |
   | HTTP/2 connection preface + SETTINGS               |
   |--------------------------------------------------->|
   |<------------------------------- SETTINGS ----------|
   | HEADERS (request stream)                           |
   |--------------------------------------------------->|
   |<--------------------------- HEADERS + DATA --------|
~~~

This diagram is conceptual; in TLS 1.3, handshake details and when the ALPN field is sent/protected differ from TLS 1.2. The main takeaway is that **TLS negotiation and selecting `h2` must finish before exchanging HTTP/2 frames**.

**SNI and ALPN are different:**

- **SNI (Server Name Indication)** tells the server which hostname the client wants to reach so it can select the certificate and virtual host.
- **ALPN** specifies which application protocol client/server will speak over the TLS connection.
- Having a **valid certificate** does not prove the server chose `h2`. Conversely, **ALPN `h2`** does not replace checking the certificate, hostname, and trust chain.
- HTTP/2 over TLS requires **TLS 1.2 or newer** per RFC 9113; TLS 1.2 deployments must also satisfy restrictions on cipher suites, renegotiation, and security properties. TLS 1.3 has its own rules. Do not conclude `h2` is available merely because a TLS handshake succeeded.

### Common ALPN Outcomes

| Client sends | Server supports/selects | Observable outcome |
| --- | --- | --- |
| **h2, http/1.1** | Selects **h2** | Client speaks HTTP/2 over TLS. |
| **h2, http/1.1** | Selects **http/1.1** | Client speaks HTTP/1.1 even over HTTPS. |
| Only **http/1.1** | Selects **http/1.1** | No h2 on this hop. |
| Only **h2** | Server lacks h2 support | No agreed application protocol; handshake/communication may fail without automatic fallback. |
| **h2, http/1.1** | Server lacks ALPN / does not pick h2 | Client/server dependent: may use HTTP/1.1 for compatibility or error out. |

**Fallback is not switching HTTP/2 into HTTP/1.1 mid-stream.** It is the outcome of initial protocol selection or a new connection per client policy. Once `h2` is selected, HTTP bytes on that connection must follow HTTP/2 framing without mixing in HTTP/1.1 request lines.

## 4. h2c with Prior Knowledge: No TLS, and No ALPN

**Prior knowledge** means the client **is already configured or knows out-of-band** that the peer on that port accepts cleartext HTTP/2. The client opens a TCP socket and immediately sends the HTTP/2 connection preface without first sending an HTTP/1.1 upgrade request.

~~~text
Client h2c                              Server h2c
    |                                         |
    | TCP connect                            |
    |---------------------------------------->|
    | HTTP/2 client connection preface        |
    | PRI * HTTP/2.0 + magic sequence         |
    | SETTINGS frame                          |
    |---------------------------------------->|
    |<------------------------- SETTINGS -----|
    | HEADERS (GET /api/protocol)             |
    |---------------------------------------->|
    |<---------------- HEADERS + DATA --------|
~~~

The client connection preface starts with a specific 24-octet sequence:

~~~text
PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n
~~~

In the text above, **\r\n** denotes CRLF bytes, not literal backslash-r and backslash-n characters on the wire. After the magic sequence, the client sends a **SETTINGS frame**, and the server sends its own **SETTINGS frame**. The preface identifies the connection format; it **provides no authentication or encryption** for cleartext traffic.

Per **RFC 9113 §3.3**, cleartext HTTP/2 uses prior knowledge. This creates a deployment rule: **you cannot rely on ALPN on a non-TLS HTTP connection to discover h2c**. The client must know the backend setup or receive out-of-band configuration (e.g., an explicitly configured proxy/backend route).

For mainstream browsers, public **http://** URLs typically use HTTP/1.1 or client-specific behaviors; never assume browsers automatically try h2c. For public web apps, choose **HTTPS/h2** to get both HTTP/2 and TLS; h2c is best suited for controlled backend hops when actually needed.

## 5. HTTP/1.1 Upgrade: h2c — Historical Mechanism, Not the New Standard Choice

You must understand **two generations of the specification** to read docs and logs accurately.

### Under Earlier RFC 7540

A client lacking prior knowledge could start in HTTP/1.1 and attempt an upgrade via headers:

~~~http
GET /api/protocol HTTP/1.1
Host: localhost:8080
Connection: Upgrade, HTTP2-Settings
Upgrade: h2c
HTTP2-Settings: <base64url-encoded-settings>
~~~

If the server accepted, it could reply:

~~~http
HTTP/1.1 101 Switching Protocols
Connection: Upgrade
Upgrade: h2c
~~~

After the 101 response, both sides exchanged HTTP/2 frames and conducted subsequent requests over HTTP/2. This model was described in **RFC 7540**; **<base64url-encoded-settings>** is an illustrative placeholder, not a literal header value to paste into a real request.

### Under Current RFC 9113

**RFC 9113 (2022, obsoleting RFC 7540)** notes that the **HTTP/1.1 Upgrade: h2c** mechanism was not widely deployed and has been **deprecated**. The **HTTP2-Settings** header and **h2c** upgrade token for this mechanism are marked **obsolete**. The current standard specifies starting cleartext HTTP/2 via **prior knowledge**.

**Practical consequences:**

- Running **curl --http2 http://host** may attempt an **HTTP/1.1 Upgrade** because curl retains support for it, even though RFC 9113 considers it obsolete. Do not take a server's 101 reply as a recommendation for new system designs.
- Running **curl --http2-prior-knowledge http://host** sends cleartext HTTP/2 **from the start**, matching the current prior-knowledge model.
- Some real-world servers (such as Tomcat 10.1) still support h2c via both **Upgrade** and **direct/prior-knowledge** for compatibility; supporting it in practice does not mean RFC 9113 reinstated Upgrade as recommended.
- If an h2c environment supports only one of the two styles, a client using the other will fail; check the actual **connection preface** or **101 Switching Protocols** in traces.

**Never use `Upgrade: h2` to enable HTTP/2 over HTTPS.** H2 over TLS must use **ALPN h2**. **Never send `h2c` in ALPN**: that is a cleartext identifier, not a TLS protocol option.

## 6. Why Is Negotiation Required Before Sending HTTP/2 Frames?

HTTP/1.1 uses text-based start lines and headers:

~~~http
GET /hello HTTP/1.1
Host: example.test
Accept: application/json
~~~

HTTP/2 uses **binary frames**; request method/path/authority/scheme are encoded as **pseudo-header fields** like **:method**, **:path**, **:scheme**, and **:authority**. Frames belong to **streams** with distinct IDs and are multiplexed over one connection.

If a client sends an **HTTP/2 connection preface** to a server that only speaks HTTP/1.1, the server cannot parse it as a normal HTTP/2 request. If a client sends an HTTP/1.1 request line to an endpoint accepting only HTTP/2 prior knowledge, the server has no obligation to treat it as an HTTP/2 stream either.

**ALPN h2** solves identifying HTTP/2 framing cleanly over TLS. **Prior knowledge** solves cleartext through pre-agreed configuration. HTTP/1.1 Upgrade used to switch formats mid-connection, but is obsolete under RFC 9113.

HTTP/2 preserves familiar HTTP semantics: methods, status codes, headers, URIs, caching, and cookies. Changing framing does not require rewriting every **@GetMapping** or **@RestController**. However, **HTTP/1.1 connection-specific headers** have no meaning or are forbidden in HTTP/2 (such as **Connection**, **Keep-Alive**, **Upgrade**, **Transfer-Encoding: chunked**). Applications and proxies must translate representations properly across versions.

### SETTINGS Sequence and Flow Control

After HTTP/2 initialization, each peer sends **SETTINGS**, while **HEADERS/DATA** streams carry requests/responses. You may see **WINDOW_UPDATE** when a receiver advertises remaining capacity for DATA bytes; **RST_STREAM** cancels a stream, and **GOAWAY** signals a planned connection shutdown. Whether using h2 or h2c, these are all standard HTTP/2 mechanics.

**HTTP/2 advantages** include stream multiplexing and HPACK header compression, though it does not eliminate **TCP head-of-line blocking** on packet loss. Nor does HTTP/2 turn blocking Spring MVC code non-blocking or guarantee higher speed in every scenario. Those belong to runtime performance, not h2 vs. h2c.

## 7. Spring Boot 3.3: server.http2.enabled Supports h2 and h2c

**Spring Boot 3.3 – Embedded Web Servers** documentation states:

- **server.http2.enabled=true** enables HTTP/2 support on compatible embedded servers.
- When **SSL/TLS** is configured on the server, **h2** is used over TLS when clients negotiate it via ALPN.
- When **SSL is not enabled** on the listener, Spring Boot 3.3 supports **h2c** over cleartext TCP.
- **Tomcat 10.1.x**, **Undertow**, and **Reactor Netty** support h2/h2c per server capabilities; **Jetty** requires extra HTTP/2 dependencies per version documentation.
- **Older** Spring Boot guides stating "Boot does not support h2c" applied to older releases and **must not be used to judge Spring Boot 3.3**.

For projects using **spring-boot-starter-web**, embedded Tomcat is the default. For **spring-boot-starter-webflux**, Reactor Netty is the default; still verify dependencies and which server actually runs. If both starters are present, Spring Boot normally picks Servlet/MVC via auto-configuration; do not assume the app is reactive just because WebFlux is on the classpath.

**Summary:**

~~~properties
# Enable HTTP/2 on the embedded web server
server.http2.enabled=true
~~~

This property does **not** mean:

- Every request is forced to use HTTP/2.
- An HTTPS endpoint works without configuring a TLS certificate/key.
- Browsers automatically use h2c on every `http://` URL.
- Reverse proxies/CDNs also speak h2/h2c upstream.
- ALPN runs on non-TLS connections.
- HTTP/3 is enabled.

Every remaining condition must be verified on **each hop of the topology**.

## 8. Complete Example: Java 17 + Spring Boot 3.3, Testing h2 and h2c

To observe the protocol seen by the Servlet container, create a small project using **Spring MVC + embedded Tomcat**. Use **two profiles** run **one at a time**, not two servers on one port: **h2c** on HTTP 8080 and **h2** on HTTPS 8443.

### 8.1. Project Structure

~~~text
http2-negotiation-demo/
  pom.xml
  src/main/
    java/com/example/h2demo/
      Http2NegotiationDemoApplication.java
    resources/
      application.properties
      application-h2c.properties
      application-h2.properties
      localdev.p12    (created in TLS step)
~~~

**Prerequisites:** Java 17+, Maven, and `keytool` (from JDK) installed. The example uses **Spring Boot 3.3.13**, a 3.3-branch release; for new projects choose a supported Spring Boot version compatible with your environment. Always verify h2/h2c/ALPN against specific documentation and server versions.

### 8.2. Complete pom.xml

Create **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http2-negotiation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

### 8.3. Java Application

Create **src/main/java/com/example/h2demo/Http2NegotiationDemoApplication.java**:

~~~java
package com.example.h2demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class Http2NegotiationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(Http2NegotiationDemoApplication.class, args);
    }
}

@RestController
class ProtocolController {

    @GetMapping(value = "/api/protocol",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> inspect(HttpServletRequest request) {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("servletProtocol", request.getProtocol());
        result.put("scheme", request.getScheme());
        result.put("method", request.getMethod());
        result.put("path", request.getRequestURI());
        return result;
    }
}
~~~

This is a valid Java 17 application:

- Only **one public class** matching the filename **Http2NegotiationDemoApplication.java**.
- The package-private **ProtocolController** class is discovered by component scanning under the root package.
- **HttpServletRequest.getProtocol()** reports the protocol of the **request reaching the Servlet container**, e.g., `HTTP/1.1` or `HTTP/2.0`—**not necessarily the protocol the browser spoke to a CDN/proxy**.
- **request.getScheme()** shows the scheme seen by the app in the current setup; in production behind proxy termination, forwarded headers can influence the scheme seen by the app. The JSON fields aid observation, not standalone proof of TLS or ALPN.

### 8.4. Shared Properties

Create **src/main/resources/application.properties**:

~~~properties
server.http2.enabled=true
spring.application.name=http2-negotiation-demo
~~~

### 8.5. Cleartext h2c Profile

Create **src/main/resources/application-h2c.properties**:

~~~properties
server.port=8080
server.ssl.enabled=false
~~~

In this profile, the Spring Boot/Tomcat listener has no TLS. With HTTP/2 enabled, the server can accept **h2c** (including direct/prior-knowledge per Tomcat capabilities).

### 8.6. h2 Profile with a Local Self-Signed Certificate

First create **src/main/resources** if it does not exist. In a terminal with the JDK, run from the project root:

~~~bash
keytool -genkeypair \
  -alias localdev \
  -keyalg RSA \
  -keysize 2048 \
  -storetype PKCS12 \
  -keystore src/main/resources/localdev.p12 \
  -storepass changeit \
  -keypass changeit \
  -validity 365 \
  -dname "CN=localhost, OU=Learning, O=Demo, C=VN" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1"
~~~

**This command creates a self-signed certificate for a test machine**, never for public production. **changeit** is only an example password; **never** commit demo keystores and passwords to real source control. In production, use valid TLS certificates, proper secret stores/SSL bundles, rotation schedules, and accurate HTTPS settings.

Create **src/main/resources/application-h2.properties**:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:localdev.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=changeit
server.ssl.key-password=changeit
server.ssl.key-alias=localdev
~~~

**server.http2.enabled=true** is already in shared `application.properties`. With TLS on port 8443, the server can use **ALPN** to choose **h2** or **http/1.1** per client/server support.

### 8.7. Build and Run the h2c Profile

~~~bash
mvn -q -DskipTests package

java -jar target/http2-negotiation-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=h2c
~~~

Open a second terminal. Check whether curl supports HTTP/2:

~~~bash
curl -V
~~~

`curl -V` output must list **HTTP2** under Features or equivalent build info. If curl was not compiled with HTTP/2, **--http2** / **--http2-prior-knowledge** will not work even when the server is completely valid.

**Test direct h2c:**

~~~bash
curl -v --http2-prior-knowledge \
  http://localhost:8080/api/protocol
~~~

When both Tomcat and curl support direct h2c, the JSON body looks like:

~~~json
{"servletProtocol":"HTTP/2.0","scheme":"http","method":"GET","path":"/api/protocol"}
~~~

These protocol/scheme values are typical when calling Tomcat directly; check real logs/traces when using another container or a proxy. **--http2-prior-knowledge** does not require HTTPS and performs no ALPN over cleartext TCP.

**Test HTTP/1.1 on the same listener:**

~~~bash
curl -v --http1.1 http://localhost:8080/api/protocol
~~~

Typical JSON body:

~~~json
{"servletProtocol":"HTTP/1.1","scheme":"http","method":"GET","path":"/api/protocol"}
~~~

This demonstrates that **a server supporting h2c does not automatically disable HTTP/1.1**. Protocol selection depends on how the client opens the request and server/connector capabilities.

**Test historical HTTP/1.1 Upgrade (not recommended for new designs):**

~~~bash
curl -v --http2 http://localhost:8080/api/protocol
~~~

Per curl documentation, with **http://**, `--http2` **attempts an Upgrade**. If Tomcat accepts, the trace may contain **Upgrade: h2c**, **101 Switching Protocols**, and then `h2c` frames. If not accepted, actual behavior may be HTTP/1.1 fallback or an error depending on client/server. **RFC 9113 marks `Upgrade: h2c` obsolete**; use this test to understand interoperability, not as a requirement for public browsers.

### 8.8. Run the h2 Profile over TLS

Stop the `h2c` server, then run:

~~~bash
java -jar target/http2-negotiation-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=h2
~~~

Test ALPN with curl:

~~~bash
curl -vk --http2 \
  https://localhost:8443/api/protocol
~~~

- **-v** displays the TLS/ALPN and request trace.
- **-k** skips certificate verification only because the demo uses a self-signed certificate. **Never use `-k` in production configs**.
- **--http2** with HTTPS tells curl to negotiate HTTP/2 via ALPN; a curl build with HTTP/2 support is required.
- When the server chooses `h2`, the trace usually shows a line like **ALPN: server accepted h2** and the HTTP section shows **HTTP/2**.
- Typical JSON body: **servletProtocol=HTTP/2.0**, **scheme=https**. Do not assume exact trace spelling is identical across all curl versions.

Compare by forcing HTTP/1.1 over HTTPS:

~~~bash
curl -vk --http1.1 \
  https://localhost:8443/api/protocol
~~~

You will get **HTTP/1.1** on the same TLS port because the server supports that protocol too. This directly illustrates that **TLS and HTTP/2 are not the same thing**.

**Do not** call **http://localhost:8443** when the port expects TLS, and do not call **https://localhost:8080** against a port running cleartext h2c. Mismatched schemes and listeners trigger handshake/protocol errors.

### 8.9. Inspecting ALPN with openssl

If OpenSSL is available, run:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn h2,http/1.1 \
  </dev/null
~~~

When server and OpenSSL support ALPN, expect **ALPN protocol: h2** or equivalent. Because of the self-signed certificate, OpenSSL may warn about trust chain verification; that is separate from ALPN selection.

Test a client offering only HTTP/1.1:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn http/1.1 \
  </dev/null
~~~

When the server supports it, output shows **ALPN protocol: http/1.1**. **openssl s_client** only checks the handshake/ALPN and **does not send a complete HTTP/2 request**; use curl to verify the full HTTP flow.

## 9. Distinguishing Evidence from Client, Server, and Proxy

In practice, multiple protocols may exist along a single request path:

~~~text
Browser --HTTPS/h2--> CDN / Reverse proxy
          |
          |  TLS termination at edge
          |
          +---- HTTP/1.1 ----> Spring Boot Tomcat
          OR
          +---- HTTP/h2c -----> Spring Boot Tomcat
          OR
          +---- HTTPS/h2 -----> Spring Boot Tomcat
~~~

These are **three possible backend paths**, not three mandatory simultaneous connections. For example, browser DevTools displays **h2** because **browser↔CDN** uses HTTP/2 over TLS, while **HttpServletRequest.getProtocol()** in the backend returns **HTTP/1.1** because the CDN talks HTTP/1.1 to the origin.

**Therefore, every claim that "this API runs HTTP/2" must ask: on which hop?**

- **Client↔CDN:** DevTools Network Protocol column, `curl -v` directly against the public domain, TLS/ALPN traces.
- **CDN↔ingress:** CDN dashboard/logs or ingress network traces, plus origin protocol configuration.
- **Ingress↔Spring Boot:** ingress access logs/traces and **request.getProtocol()** in the app; origin `h2c`/`h2` profile.
- **Spring Boot↔other service:** actual HTTP client setup (`WebClient`, Java `HttpClient`, OkHttp, Apache HttpClient) and negotiated protocol to that service.

Never treat **X-Forwarded-Proto: https** as proof that the client is running HTTP/2. It normally reports the **scheme reported by the proxy**, not an ALPN token. **Forwarded**/**X-Forwarded-*** headers must only be trusted from trusted proxies to prevent scheme/host spoofing.

### Is h2c Behind TLS Termination Secure?

An architecture with **browser↔proxy over h2/TLS** and **proxy↔Spring Boot over h2c/cleartext** protects the first leg with TLS, **without encrypting the proxy↔backend hop**. Inside an internal cluster with network isolation and clear trust boundaries, that may be acceptable per your threat model. If backend traffic crosses untrusted networks, multi-tenant clusters, or sensitive boundaries, consider **TLS/mTLS to the origin** instead of `h2c`.

**h2c does not mean the whole website is insecure** if confined to a privately protected hop, nor **should it be called end-to-end encryption**.

## 10. Choosing a Negotiation Strategy by Deployment Context

| Context | Typical sound choice | Risks / checks |
| --- | --- | --- |
| Public website/API from browsers | **HTTPS + h2 via ALPN**, allowing HTTP/1.1 for compatibility | Certificate, TLS 1.2+, ciphers, ALPN, and proper fallback. |
| Internal service behind TLS termination on controlled network | **h2c prior knowledge** if both client and server support it | Cleartext hop, sidecar/mesh routing, network security policy. |
| Internal service requiring mTLS | **h2 over TLS** with proper server/client certificates | CA trust, SNI, ALPN, and mTLS policy at the real hop. |
| Legacy clients supporting only HTTP/1.1 | Keep HTTP/1.1 on client hop or proxy conversion | Never force h2c prior knowledge on unsupported clients. |
| Gradual upgrade behind a reverse proxy | Enable h2 at edge first, measure backend hop independently | Avoid misreporting "end-to-end h2" while backend still uses HTTP/1.1. |
| Specialized client using old h2c Upgrade | Test interoperability and plan migration to prior knowledge or TLS ALPN | RFC 9113 marks `Upgrade: h2c` obsolete. |

**No single Spring Boot property forces every peer on the Internet onto h2.** Protocol selection depends on the capabilities of clients, TLS stacks, connectors, proxies, and per-hop policies.

## 11. TLS Conditions to Check When h2 Is Not Chosen

Per **RFC 9113 §9.2**, HTTP/2 over TLS requires **TLS 1.2 or newer**. For TLS 1.2, restrictions apply to cipher suites, key exchange, compression, and renegotiation; TLS 1.3 has its own rules.

If a client shows HTTPS yet ALPN picks **http/1.1** or fails to select `h2`, check:

1. **server.http2.enabled** is off, or the server started a different profile/version/config.
2. **TLS/certificate** is mismatched, server or client lacks ALPN support, or the TLS library/JDK is too old.
3. **Negotiated cipher suite/TLS version** violates HTTP/2 requirements; HTTP/1.1 over TLS can still succeed.
4. **Proxy/CDN** terminates TLS elsewhere. Enabling `h2` on your backend does not directly change ALPN on the public endpoint.
5. **HTTP client lacks HTTP/2 support** in its actual build; check **curl -V** or library capabilities.
6. **ALPN only advertises http/1.1** because the client forced **--http1.1**, proxy config, or server policy.
7. **SNI/virtual host** mismatch caused the server to choose another certificate/TLS config than the hostname tested.

Never disable TLS certificate verification in production to "fix ALPN." **-k** in the demo only accepts the local self-signed cert. A server can have working ALPN `h2` with an untrusted certificate; that connection still must be fixed before secure deployment.

## 12. Diagnosing Failures with curl: Quick Test Matrix

Assuming either profile **h2c on :8080** or profile **h2 on :8443** is running at a given time:

| Command | Path and intent | What to observe |
| --- | --- | --- |
| **curl -v --http1.1 http://localhost:8080/api/protocol** | Cleartext HTTP/1.1 | Backend sees `HTTP/1.1`. |
| **curl -v --http2-prior-knowledge http://localhost:8080/api/protocol** | Direct h2c | Backend sees `HTTP/2.0` if Tomcat supports and accepts it. |
| **curl -v --http2 http://localhost:8080/api/protocol** | Legacy h2c Upgrade attempt | May show 101 then h2c, HTTP/1.1 fallback, or an error. |
| **curl -vk --http2 https://localhost:8443/api/protocol** | ALPN h2 over TLS | ALPN trace, HTTP/2 status, demo self-signed certificate. |
| **curl -vk --http1.1 https://localhost:8443/api/protocol** | Force HTTP/1.1 over TLS | Connection stays HTTPS, without necessarily using HTTP/2. |
| **openssl s_client -connect localhost:8443 -servername localhost -alpn h2,http/1.1** | Inspect TLS ALPN only | ALPN negotiated protocol; does not execute an HTTP request. |

Commands using **--http2-prior-knowledge** require curl built with HTTP/2. Some curl/SSL backends print slightly different ALPN or TLS trace wording; go by the capabilities and version of your installed tools.

### Unsuccessful Cases

**One:** **curl --http2-prior-knowledge http://...** fails immediately or the server logs an invalid request. The server may accept only HTTP/1.1 or you hit a TLS port by mistake. Do not try to fix it by adding an **Upgrade: h2c** header blindly, because prior knowledge uses a **direct preface**, distinct from HTTP/1.1 Upgrade.

**Two:** **curl --http2 https://...** still shows HTTP/1.1. Check what **ALPN** picked, whether a reverse proxy is involved, which cert/JDK/container handles TLS, and whether **server.http2.enabled** is set on that public endpoint.

**Three:** **curl reports SSL wrong version number** when calling `https://localhost:8080`. You sent a TLS `ClientHello` to a cleartext HTTP port; verify scheme, port, and active profiles.

**Four:** Browser DevTools shows `h2`, while backend logs show `HTTP/1.1`. Not a contradiction: the browser speaks `h2` to the proxy, and the proxy speaks `HTTP/1.1` to Spring Boot.

**Five:** Testing `h2c` on a public port from the Internet gets blocked by policy. Ingress/CDN/browser policies generally disallow cleartext h2; do not expose `h2c` publicly just to satisfy a test without a genuine requirement.

## 13. HTTP/2 Does Not Fix Every Performance Problem

Once negotiated successfully, `h2` and `h2c` share identical HTTP/2 semantics:

- **Multiplexing** allows multiple streams on a single connection, reducing HTTP/1.1 request ordering bottlenecks.
- **HPACK** reduces repeated header-field overhead; **distinct** from body `Content-Encoding` gzip/br.
- **Flow control** uses byte-level windows for DATA frames at stream and connection levels; **not** Reactor's Reactive Streams **request(n)**.
- **Server push** existed in HTTP/2, but many clients/browsers reduced or dropped support; do not rely on server push as a default benefit in new designs.
- **TCP head-of-line blocking** still occurs when packets are lost on the connection; HTTP/3 with QUIC addresses that differently.
- A Spring MVC controller running blocking JDBC still blocks worker threads; `h2` does not make JDBC non-blocking.
- A low-RTT network with few requests and small payloads may see negligible gains; measure instead of attributing every speedup to enabling HTTP/2.

**h2c is not automatically faster than h2** merely because TLS is removed; TLS session reuse, CPU, network isolation, proxy hops, and infrastructure dictate total latency. Dropping TLS to save a few milliseconds on an untrusted path creates far larger security risks.

## 14. Layered Deployment Verification and True Protocol Measurement

Before declaring a production configuration sound, verify in order:

1. **Right profile/config:** snapshot `server.http2.enabled`, `server.ssl.*`, ports, and actual embedded server; avoid applying dev properties in prod.
2. **TLS handshake on the public domain:** verify cert chain/hostname, TLS version, SNI, and whether ALPN selects **h2** or **http/1.1**.
3. **Actual HTTP request:** curl or browser DevTools confirms the HTTP version used, valid functional responses, and zero stream/protocol errors.
4. **Every proxy hop:** verify edge↔ingress↔Spring Boot run HTTP/1.1/`h2`/`h2c` as designed, never guessing from the public endpoint.
5. **Fallback behavior:** verify whether HTTP/1.1-only clients are served properly; if not, ensure that is an intentional compatibility decision rather than a surprise breakage.
6. **Cleartext policy:** never expose `h2c` on untrusted networks unreviewed; enforce clear security zones.
7. **Observability:** break down requests by protocol, TLS handshake errors, connection resets, stream errors, latency/throughput, and proxy access logs.
8. **Load testing:** compare HTTP/1.1 vs. `h2` with identical TLS/network/connection reuse/concurrency and workloads, never judging from a single localhost request.
9. **Related adjustments:** ensure HTTP/2-incompatible headers are handled by adapters; never inject forbidden **Connection/Upgrade** headers into HTTP/2.
10. **Assess legacy upgrades:** if anything still uses **Upgrade: h2c** and **HTTP2-Settings**, plan migration to prior knowledge or TLS ALPN per RFC 9113, or maintain controlled interoperability.

Tools like **Wireshark** can inspect cleartext connection prefaces and `h2c` frames directly, whereas observing `h2` over TLS requires valid decryption keys or endpoint metrics. Do not assume a TLS packet capture will show HTTP/2 `HEADERS`/`DATA` in plaintext; TLS encrypts the payload.

## 15. Common Errors and Misconceptions

| Claim or symptom | Fact and resolution |
| --- | --- |
| **"HTTP/2 always uses TLS."** | Not strictly: **h2c** is cleartext HTTP/2. **h2 over HTTPS** mandates TLS. |
| **"h2c is HTTP/1.1."** | False: `h2c` uses HTTP/2 binary framing once the connection is established. |
| **"Enabling server.http2.enabled=true turns every request into HTTP/2."** | False: the server enables **support**; clients/hops must still negotiate the protocol. |
| **"HTTPS guarantees h2."** | False: HTTPS can negotiate **http/1.1**. |
| **"ALPN h2c over HTTPS."** | Wrong: HTTP/2 over TLS uses **ALPN h2**, whereas **h2c** uses neither TLS nor ALPN. |
| **"SNI picks h2."** | Wrong: SNI indicates the hostname; ALPN picks the application protocol. |
| **"curl --http2 and --http2-prior-knowledge are identical for http://."** | Wrong: **--http2** tries legacy Upgrade; **--http2-prior-knowledge** sends the h2c preface directly. |
| **"Upgrade: h2c is the latest standard."** | Wrong: RFC 9113 marked **Upgrade h2c/HTTP2-Settings obsolete**; legacy support still exists in places. |
| **"Tomcat 10.1 does not support h2c."** | Incorrect for Spring Boot 3.3/Tomcat 10.1; Boot and Tomcat docs confirm support. |
| **"The browser sees h2, so the backend must be h2."** | Uncertain: a proxy may translate `h2` into HTTP/1.1 or `h2c` on the next hop. |
| **"h2c behind an HTTPS proxy is still end-to-end TLS."** | False: the `h2c` hop is cleartext; evaluate trust boundaries and network policies. |
| **"HPACK compresses the response body."** | False: HPACK is header compression; body gzip/br is a separate content coding. |
| **"HTTP/2 eliminates all HOL blocking."** | False: it still runs over TCP and exhibits transport-level head-of-line blocking. |
| **"An HTTPS profile without a cert still runs h2."** | False: HTTPS requires valid TLS configuration; demos use self-signed keystores only locally. |
| **"curl -k fixes ALPN issues."** | False: `-k` skips certificate trust verification and does not add server `h2` or ALPN support. |

## 16. Self-Check Questions and Practical Scenarios

**Question 1:** Client offers **ALPN=[h2,http/1.1]**, server chooses **http/1.1**, and TLS handshake succeeds. Which protocol does the connection use?  
**Answer:** HTTP/1.1 **over TLS**, not `h2c` or HTTP/2.

**Question 2:** Client runs **curl --http2-prior-knowledge http://localhost:8080** against Tomcat with direct `h2c`. Is there TLS or ALPN?  
**Answer:** No. Cleartext TCP + HTTP/2 preface and frames.

**Question 3:** Why can **curl --http2 http://localhost:8080** emit **Upgrade: h2c** in traces while RFC 9113 recommends prior knowledge?  
**Answer:** curl retains backward compatibility from RFC 7540; RFC 9113 deprecated/obsoleted the `Upgrade`/`HTTP2-Settings` mechanism because it lacked broad adoption.

**Question 4:** Browser DevTools shows **h2**, yet **request.getProtocol()** in Spring Boot returns **HTTP/1.1**. Who is wrong?  
**Answer:** Neither is necessarily wrong: the browser speaks `h2` to the proxy/ingress, and the backend receives HTTP/1.1 from the proxy.

**Question 5:** What kind of endpoint can **server.http2.enabled=true** and **server.ssl.enabled=false** create in Spring Boot 3.3?  
**Answer:** **Cleartext h2c** on supported embedded servers, though it still depends on client/network hops and can also serve HTTP/1.1.

**Question 6:** Can you make **h2** work over HTTPS by adding an **Upgrade: h2** header in an HTTP/1.1 request?  
**Answer:** No; use **TLS ALPN h2**. Sending an HTTP/1.1 Upgrade does not replace the handshake protocol selection.

**Question 7:** Why is a backend `h2c` connection less secure than `h2`?  
**Answer:** `h2c` lacks TLS on the hop, providing no TLS encryption, peer authentication, or integrity protection. It can be used inside an evaluated internal trust boundary, never exposed arbitrarily to the Internet.

**Question 8:** An HTTP/2 request is sent on stream 3 using HEADERS/DATA. Do HTTP status 200 or method GET change semantics?  
**Answer:** No; HTTP/2 preserves HTTP semantics while changing framing/multiplexing and field encoding.

**Question 9:** If **curl -V** lacks HTTP2 support, will setting `server.http2.enabled` make `curl --http2` work?  
**Answer:** No; the client must also support HTTP/2.

**Question 10:** When should you choose `h2c` over `h2`?  
**Answer:** When a backend hop intentionally uses cleartext in a controlled architecture, both client and server support prior knowledge, and security policy permits it. For public-facing HTTPS, prefer `h2` via TLS ALPN.

## 17. Authoritative References

- **RFC 9113 – HTTP/2 (current standard):** https://www.rfc-editor.org/rfc/rfc9113.html — §3.1 identifiers **h2/h2c**, §3.2 **https/TLS/ALPN**, §3.3 **prior knowledge**, §3.4 **connection preface**, §9.2 **TLS requirements**, §11 marking Upgrade `h2c` and `HTTP2-Settings` obsolete.
- **RFC 7540 – HTTP/2 (obsoleted by RFC 9113):** https://www.rfc-editor.org/rfc/rfc7540 — historical description of **HTTP/1.1 Upgrade: h2c** for reading older docs/traces, **do not use in place of RFC 9113**.
- **RFC 7301 – TLS ALPN:** https://www.rfc-editor.org/rfc/rfc7301 — protocol negotiation in TLS.
- **Spring Boot 3.3 – Embedded Web Servers / Configure HTTP/2:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — `server.http2.enabled`, **h2/h2c** support, SSL, Tomcat/Jetty/Netty/Undertow.
- **Spring Boot 3.3 – SSL and Server Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ — `server.ssl.*`, `server.http2.enabled`.
- **Apache Tomcat 10.1 – HTTP Connector:** https://tomcat.apache.org/tomcat-10.1-doc/config/http.html — `h2` TLS, `h2c` Upgrade and direct, HTTP2 `UpgradeProtocol`.
- **curl manual:** https://curl.se/docs/manpage.html — **--http2**, **--http2-prior-knowledge**, **--http1.1**, **-v**, and HTTP/HTTPS behavior.
- **OpenSSL s_client manual:** https://docs.openssl.org/3.0/man1/openssl-s_client/ — **-alpn** and **-servername**.