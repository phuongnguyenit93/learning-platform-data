# Testing Server-Specific Configuration, Proxy Headers, TLS, and HTTP/2 in Spring Boot

> **Module:** Spring Boot - web-runtime · **Group:** Web runtime testing. This lesson guides testing behaviors that genuinely depend on the **embedded web server** and network path: Tomcat/Jetty/Reactor Netty, preserving original client addresses behind reverse proxies, HTTPS/TLS validation, and HTTP/2 negotiation. The focus is not merely declared properties, but whether the **running server behaves accurately** when clients, proxies, and TLS handshakes participate. Examples use **Java 17+**, **Spring Boot 4.1.2**, Maven, Spring MVC/Tomcat, JUnit, JDK `HttpClient`, cURL, and OpenSSL; includes extensions for Jetty, WebFlux, and CI.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish controller testing with `MockMvc` from **testing a real server on a TCP port** via `@SpringBootTest(webEnvironment=RANDOM_PORT)`. Know when real cURL/OpenSSL/ingress checks are mandatory.
2. Understand common `server.*`, `server.tomcat.*`, `server.jetty.*` property groups and custom `WebServerFactoryCustomizer` beans; know that Tomcat properties do not automatically apply to Reactor Netty.
3. Verify `Forwarded` (RFC 7239), `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, and `X-Forwarded-Prefix`, including trust boundaries and header-spoofing risks.
4. Distinguish `server.forward-headers-strategy=none|native|framework`, Tomcat `RemoteIpValve`, and Spring `ForwardedHeaderFilter`/WebFlux `ForwardedHeaderTransformer`.
5. Validate HTTPS certificates, CA trust, hostname/SAN, validity dates, SNI, and TLS handshakes **without trust-all** or `curl -k`.
6. Configure **PEM SSL bundles** for the server, inspect `server.ssl.bundle` interactions with standalone `server.ssl.*` properties, and recognize mTLS testing as distinct from server-auth TLS.
7. Enable `server.http2.enabled=true`, distinguish **h2 over TLS with ALPN**, **h2c over cleartext**, and topologies where the proxy speaks HTTP/2 externally while the backend remains HTTP/1.1.
8. Write real tests using `@LocalServerPort` and Java 17 `java.net.http.HttpClient` to verify forwarded headers, redirect URLs, and direct-to-backend bypasses in a lab.
9. Build a CI integration matrix covering both **positive** and **negative** cases: header injection, wrong hostname/CA, HTTP/2 downgrade, oversized headers, proxy rewrites, and deployment TLS termination.
10. Follow a diagnostic runbook using requests/responses, logs, packet/protocol tools, and metrics rather than guessing from config files.

## 2. Why Can This Topic Not Be Tested with MockMvc Alone?

Suppose a controller declares:

~~~java
@GetMapping("/ping")
String ping() {
    return "pong";
}
~~~

With `MockMvc`, you can verify routes, controller-generated headers, validation, Spring Security filters, and exception handlers inside a **mock Servlet environment**. However, mock MVC tests **do not start a TCP listener**, do not perform TLS handshakes, ALPN negotiation, real-socket WebSocket upgrades, HTTP/2 streams, or Tomcat connector header limits.

~~~text
                         Tests
                           |
              +------------+----------------+
              |                             |
       @WebMvcTest / MockMvc         @SpringBootTest(RANDOM_PORT)
       MockHttpServletRequest         Embedded Tomcat/Jetty/Netty
       Controller + filters           Real TCP request/response
              |                             |
       Logic/mapping contract         Connector, forwarded handling
                                           |
                                  +--------+-------------+
                                  |                      |
                               cURL/JDK                Proxy/Ingress
                               HttpClient              + TLS edge
                                  |                      |
                                  +--- TLS, ALPN, h2 ----+
~~~

| What Needs Verification | Is MockMvc Enough? | Appropriate Test |
| --- | --- | --- |
| `@GetMapping`, body, status, business validation | Usually yes | `@WebMvcTest`/`MockMvc` |
| Property binding into `Environment` | Testable | ApplicationContext/config test |
| Server actually binds IP/port | No | Real server + TCP connect |
| Tomcat max header/connection/thread limits | No | Real embedded Tomcat under load |
| Reverse proxy rewriting scheme/host/redirects | Mock filter tests only part | Direct HTTP test + trusted proxy test |
| Certificate, CA chain, and hostname | No | Real TLS client/OpenSSL |
| ALPN `h2` vs `http/1.1` | No | Real TLS negotiation |
| `h2c` prior knowledge/upgrade | No | HTTP/2-capable client to real connector |
| Browser mixed content, secure cookies, HSTS | Insufficient | Browser through real HTTPS edge |
| LB sticky routing, Ingress rewrites | No | Staging with production-like topology |

**Rule:** a passing “application context starts” or “controller GET returns 200” test does not prove proxies, TLS, and HTTP/2 are working.

### 2.1. Three Distinct Observation Points

Do not conflate metrics across hops in a single trace:

1. **External client → edge proxy:** URL `https://public.example.test/orders/42`; browser may negotiate HTTP/2 with the proxy's TLS certificate.
2. **Edge proxy → Spring Boot:** may talk `http://10.0.0.12:8080/orders/42` over HTTP/1.1 even though the browser externally used HTTPS+h2.
3. **Spring MVC Servlet request:** depending on forwarded strategy, `getScheme()/isSecure()/getServerName()` can reflect the external origin, while `getProtocol()` normally reflects the **backend hop's protocol**, not the browser's HTTP/2 session.

Therefore, a response body reporting `"protocol":"HTTP/1.1"` at the backend does not contradict external cURL negotiating HTTP/2 with the proxy.

## 3. Testing Server-Specific Configurations

Spring Boot supports embedded servers with distinct capabilities and settings:

| Runtime | Typical Stack | Where Configured | What Must Be Tested Live |
| --- | --- | --- | --- |
| **Tomcat 11** | Spring MVC/Servlet, default `webmvc` starter | `server.*`, `server.tomcat.*`, `TomcatServletWebServerFactory` | Connector, header parsing, `RemoteIpValve`, TLS/h2 |
| **Jetty** | Spring MVC/Servlet when swapping starter | `server.*`, `server.jetty.*`, `JettyServletWebServerFactory` | Jetty-specific settings, h2 support modules |
| **Reactor Netty** | WebFlux reactive server | `server.*`, Netty-specific options/customization | Event loop, h2/h2c, headers, forwarded transformer |
| **Reverse proxy/gateway** | Nginx, Envoy, Apache, ingress/CDN | Not Spring Boot properties | External TLS, ALPN, trusted headers, routing/redirects |

**Do not treat old Undertow/Tomcat 9 guides as defaults for Boot 4.1.2.** Spring Boot 4.1 uses Tomcat 11 per current docs, and HTTP/2 behavior differs from legacy versions. Verify the exact dependency versions running in your environment.

### 3.1. Common Server Properties

~~~properties
server.address=127.0.0.1
server.port=8080
server.http2.enabled=false
server.forward-headers-strategy=none
server.max-http-request-header-size=8KB
~~~

This is a **local lab** configuration to isolate one connector cleanly. `server.address=127.0.0.1` avoids exposing a forwarded-header-accepting endpoint in learning setups. Inside Docker/Kubernetes, binding only loopback can block Service/Ingress traffic; production must configure the right bind address and network policies.

- `server.max-http-request-header-size` caps HTTP request headers, not JSON request body size or response headers.
- `server.http2.enabled=false` keeps the baseline free of h2/h2c.
- `server.forward-headers-strategy=none` prevents Spring Boot's built-in strategy from rewriting request info from forwarded headers; custom filters may still read headers if written manually.
- Protocol limits may also be enforced by a proxy upstream of Boot; seeing 431 from an edge proxy does not prove Boot's Tomcat rejected it.

### 3.2. Tomcat-Specific Properties

~~~properties
# Affects embedded Tomcat ONLY; DOES NOT affect Jetty/Netty.
server.tomcat.threads.max=64
server.tomcat.max-connections=1024
server.tomcat.connection-timeout=5s
server.tomcat.redirect-context-root=false
~~~

- Worker thread count does not equal max concurrent clients: keep-alive connections, async I/O, and HTTP/2 multiplexing behave differently.
- Heavy traffic or slow-client scenarios require measuring queues, active threads, connection counts, and timeouts rather than guessing from one property.
- `server.tomcat.redirect-context-root=false` matters when SSL terminates at a proxy: it lets `X-Forwarded-Proto` take effect before context-root redirects.
- Never copy `server.tomcat.*` to WebFlux/Netty expecting an effect.

Tomcat also configures `RemoteIpValve` in native mode, e.g., `server.tomcat.remoteip.protocol-header` and `server.tomcat.remoteip.internal-proxies`. That defines a **trust boundary**, not an invitation to trust every IP.

### 3.3. When Is WebServerFactoryCustomizer Needed?

If a server setting has no Boot property, customize the matching factory bean:

~~~java
// Fragment for a Spring MVC/Tomcat project, not a standalone program.
@Bean
WebServerFactoryCustomizer<TomcatServletWebServerFactory> tomcatCustomizer() {
    return factory -> {
        // Configure only required Tomcat APIs after checking Javadoc
        // and add real connector behavior tests.
    };
}
~~~

Matching types in Boot 4.x:

~~~java
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory;
~~~

Never combine a manual `ForwardedHeaderFilter` with native `RemoteIpValve` rewriting schemes twice without understanding ordering. When switching to Jetty, a Tomcat-typed customizer stops matching any bean; tests must confirm settings still apply.

### 3.4. How to Confirm Which Server Actually Runs

- Inspect the Maven dependency tree, Boot startup logs, and server factory bean type.
- Run `mvn dependency:tree` to check whether `spring-boot-starter-tomcat`, `spring-boot-starter-jetty`, or Reactor Netty is on the classpath.
- Run real-port tests and inspect header/protocol/TLS behavior.
- For limits/timeouts, generate controlled over-limit traffic and observe actual error/path behavior.
- When changing servers, re-run the entire test matrix: identically named properties do not guarantee identical timings or status codes.

## 4. Understanding and Testing Proxy Forwarding Headers

A reverse proxy can terminate TLS and forward plain HTTP to the backend:

~~~text
Client                     Reverse proxy                Spring Boot
https://api.example.test    TLS edge                     HTTP backend
HTTP/2 over TLS             HTTP/1.1 to :8080
       |                          |                          |
       +--- HTTPS /orders/42 ---->|
                                  +--- GET /orders/42 ------->
                                  |   Host: backend:8080
                                  |   X-Forwarded-Proto: https
                                  |   X-Forwarded-Host: api.example.test
                                  |   X-Forwarded-Port: 443
                                  |   X-Forwarded-For: client IP
                                  |                          |
                                  |             Spring computes external origin
                                  |<--- Location: https://api.example.test/... 
       |<--- HTTPS response -------+
~~~

If forwarded headers go unhandled, the app can emit `Location: http://backend:8080/login`, wrong-scheme/host absolute links, broken OAuth `redirect_uri` values, cookies missing `Secure`, or wrong Swagger/OpenAPI server URLs. Conversely, if it **trusts headers injected arbitrarily by Internet clients**, attackers can perform host-header poisoning, open redirects, bypass security decisions, or steal tokens via links.

### 4.1. Common Headers

| Header | Meaning | Verification |
| --- | --- | --- |
| `Forwarded: for=...;proto=https;host=...` | RFC 7239 standard for origin and hops | Parser and header trust |
| `X-Forwarded-For` | Client/proxy IP chain, possibly multi-entry | Never blindly trust the first entry |
| `X-Forwarded-Proto` | Client→proxy scheme, e.g., `https` | `request.getScheme()`/redirects |
| `X-Forwarded-Host` | Original public host | Absolute URL/host validation |
| `X-Forwarded-Port` | Client-facing port | URI builder, redirect ports |
| `X-Forwarded-Prefix` | Proxy-rewritten path prefix | Context path/links; stack support varies |
| `X-Forwarded-Ssl` | Legacy convention | Use only if proxy/handler supports it |

HTTP `Host` and forwarded hosts are **network-supplied data**, not automatically trustworthy domains. At the trust boundary, the proxy must **strip both `Forwarded` and all client-sent `X-Forwarded-*` headers**, then attach validated values from the real connection. Never strip only one header family while letting the other slip through.

### 4.2. Three Boot Strategies

~~~properties
server.forward-headers-strategy=none
~~~

Ignores forwarded headers when determining origin. Fits the lab baseline or apps receiving traffic directly with no trusted proxy.

~~~properties
server.forward-headers-strategy=native
~~~

Uses the container's native mechanism, such as Tomcat `RemoteIpValve`. Can enforce trusted proxy lists, header names, and native rules. Behavior differs across Tomcat/Jetty/Netty; test using requests from **actual proxy source addresses**.

~~~properties
server.forward-headers-strategy=framework
~~~

Uses Spring Framework support: `ForwardedHeaderFilter` on MVC and `ForwardedHeaderTransformer` on WebFlux. Rewrites scheme/host/port and links from headers. However, **the framework cannot verify which proxy set the headers**: if the backend is public, clients can spoof them.

In Boot 4.1, on certain detected cloud environments the default may be `NATIVE`; otherwise it is normally `NONE`. In tests, **declare the strategy explicitly** rather than letting cloud auto-detection alter expectations.

### 4.3. Limitations of Native vs Framework

Tomcat `RemoteIpValve` supports regex `internal-proxies` and resolves remote IP/scheme for headers it recognizes. Spring Framework's filter handles forwarded host/prefix and link building cleanly, yet **is not a proxy IP allowlist**. With native Tomcat, `X-Forwarded-Prefix`/RFC 7239 `Forwarded` support can differ from `X-Forwarded-Proto`/`X-Forwarded-For`: never assume every header behaves identically.

Spring Framework 7.1 documents explicit selection of header formats for filters/transformers and prefix options. When customizing, consult the exact minor version docs for `spring.mvc.forwarded-headers.header-format`/`spring.webflux.forwarded-headers.header-format`; never hardcode assumptions that filters accept both standards automatically in every version.

### 4.4. X-Forwarded-For: Hop Ordering and Trusted Chains

Example header:

~~~text
X-Forwarded-For: 198.51.100.10, 10.0.1.10, 10.0.2.20
~~~

Suppose the external client is `198.51.100.10` passing through two internal proxies. If the edge **fails to strip incoming `X-Forwarded-For`**, an attacker can prepend a fake IP at the front. Therefore:

- Configure trusted proxy CIDRs/addresses in the gateway/Tomcat per environment.
- At the edge, overwrite incoming forwarded headers with the real peer connection IP.
- At downstream proxies, append only from **verified** sources.
- Never use `split(",")[0]` for authorization, rate limiting, or auditing Internet clients without a validated trust boundary.

In Tomcat, **leaving `internal-proxies` empty can trust all proxies** depending on binding. That is a severe anti-pattern—never use it in production.

### 4.5. Redirects and Absolute URLs

Suppose a client requests:

~~~http
GET /go HTTP/1.1
Host: backend.internal:8080
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.test
X-Forwarded-Port: 443
~~~

The controller builds a redirect using Spring's URI builder from the current request. In `framework` mode with trusted lab headers, `Location` should point to `https://shop.example.test/probe`. With `none`, it should reflect the backend origin instead of trusting forwarded headers. This tests far more meaningfully than echoing raw headers.

**Never** rewrite `Host` from arbitrary requests into external links without domain allowlisting, especially for password resets or OAuth. A redirect with `https` scheme yet an attacker-chosen host still enables open redirects and link poisoning.

## 5. Runnable Project: Testing Servlet Server and Forwarding

Lab goals:

- Spring MVC/Tomcat on loopback `127.0.0.1:8080`.
- `GET /probe` reports scheme, host, port, secure flag, request protocol, and absolute URL.
- `GET /go` issues a redirect `Location` derived from the current request.
- JUnit tests spin up embedded servers on random ports comparing `none` and `framework`.
- Two dedicated profiles test TLS+h2 and h2c with cURL/OpenSSL.

### 5.1. Directory Structure

~~~text
web-runtime-integration-lab/
  pom.xml
  src/main/java/com/example/webtest/
    WebRuntimeApplication.java
    ProbeController.java
  src/main/resources/
    application.properties
    application-proxy.properties
    application-tls.properties
    application-h2c.properties
  src/test/java/com/example/webtest/
    ForwardedHeadersTest.java
    NoForwardedHeadersTest.java
  tls/                                # generated by OpenSSL, DO NOT commit
    localhost.crt
    localhost.key
    localhost.pk8.key
  .gitignore
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>web-runtime-integration-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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
~~~

Spring Boot 4.1.2 provides `spring-boot-starter-webmvc-test` for tests. Do not copy Boot 3 habits like `spring-boot-starter-web` or old packages without verifying versions. JUnit/Jackson test and Spring Boot test dependencies are managed by the starter.

### 5.3. WebRuntimeApplication.java

~~~java
package com.example.webtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}
~~~

### 5.4. ProbeController.java

~~~java
package com.example.webtest;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class ProbeController {

    @GetMapping("/probe")
    public Map<String, Object> probe(HttpServletRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scheme", request.getScheme());
        result.put("host", request.getServerName());
        result.put("port", request.getServerPort());
        result.put("secure", request.isSecure());
        result.put("protocol", request.getProtocol());
        result.put("requestUrl", request.getRequestURL().toString());
        result.put("absoluteLink",
                ServletUriComponentsBuilder.fromCurrentRequestUri()
                        .toUriString());
        return result;
    }

    @GetMapping("/go")
    public ResponseEntity<Void> redirectToProbe() {
        URI target = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/probe")
                .build()
                .toUri();
        return ResponseEntity.status(HttpStatus.FOUND)
                .location(target)
                .build();
    }
}
~~~

Code uses `jakarta.servlet.http.HttpServletRequest` matching modern Servlet stacks rather than legacy `javax.servlet.*`. `request.getProtocol()` reflects the HTTP protocol of the backend request being processed, and does not switch to `HTTP/2.0` merely because an edge proxy spoke h2.

`absoluteLink` uses Spring's URI builder to verify **redirect/link generation** differences when `ForwardedHeaderFilter` runs. This is a diagnostic API and must never leak internal backend hostnames/IPs or sensitive info to public users. In real apps, restrict `/probe` to the management plane.

### 5.5. application.properties

~~~properties
# Explicit baseline, loopback only.
server.address=127.0.0.1
server.port=8080
server.forward-headers-strategy=none
server.http2.enabled=false
server.ssl.enabled=false

server.max-http-request-header-size=8KB
server.tomcat.threads.max=64
server.tomcat.max-connections=1024
server.tomcat.connection-timeout=5s
server.tomcat.redirect-context-root=false
~~~

**Do not** define the SSL bundle in the base profile; only the TLS profile adds it. This lets the `h2c` profile run without accidentally inheriting `server.ssl.bundle` from base.

### 5.6. application-proxy.properties

~~~properties
# Enable ONLY when requests arrive from a trusted reverse proxy.
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false
~~~

In the **lab** where the backend listens solely on loopback, you can pass forwarded headers via cURL to observe framework rewriting. In production, never switch to `framework` while the app remains exposed directly to the Internet or without proxy header sanitization. Parsing `X-Forwarded-Proto` does not mean the header is authenticated.

### 5.7. application-h2c.properties

~~~properties
# HTTP/2 over cleartext TCP - for lab/trusted backend ONLY.
server.port=8080
server.ssl.enabled=false
server.http2.enabled=true
~~~

Never use `h2c` to transmit bearer tokens/credentials over the public Internet: `h2c` **lacks TLS encryption**. A proxy may secure the edge hop with TLS, while cleartext backends need private networks, mTLS sidecars, or network policies per threat model.

### 5.8. application-tls.properties

~~~properties
server.port=8443
server.http2.enabled=true

# Embedded Tomcat HTTPS identity (inbound).
server.ssl.enabled=true
server.ssl.bundle=labhttps

spring.ssl.bundle.pem.labhttps.keystore.certificate=file:./tls/localhost.crt
spring.ssl.bundle.pem.labhttps.keystore.private-key=file:./tls/localhost.pk8.key
~~~

`server.ssl.bundle` points to the bundle named `labhttps`. This is the **server keystore** holding the public certificate and private key; clients must trust the public certificate/CA when connecting. Do not confuse an outbound `RestClient`'s truststore with the keystore used by the inbound server.

When using `server.ssl.bundle`, **do not mix** standalone keystore/PEM properties such as `server.ssl.key-store`, `server.ssl.certificate`, and `server.ssl.certificate-private-key`. Standalone `server.ssl.ciphers`/`enabled-protocols` may also be ignored when a bundle is selected; place protocol/cipher options under `spring.ssl.bundle.pem.labhttps.options.*` per version docs.

### 5.9. .gitignore

~~~gitignore
/target/
/tls/
~~~

Never commit private keys. Ignoring `tls/` even when it holds public certs prevents accidentally committing the lab private key. If a key was ever committed, `.gitignore` does not scrub history; rotate it and follow secrets incident procedures.

## 6. Automated Tests Using Real Servers and Random Ports

### 6.1. Why RANDOM_PORT?

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
~~~

Per Spring Boot, `RANDOM_PORT` starts a real embedded server and lets the OS pick an unused port. This avoids collisions during parallel CI runs. `@LocalServerPort` (Boot 4.1 package `org.springframework.boot.test.web.server.LocalServerPort`) injects the port after startup.

Do not use default `@SpringBootTest` (`MOCK`) to claim port/TLS/h2 works. Real-server tests should not fake TLS through mock request builders when testing real protocols.

### 6.2. ForwardedHeadersTest.java

~~~java
package com.example.webtest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "server.ssl.enabled=false",
        "server.http2.enabled=false",
        "server.forward-headers-strategy=framework"
    }
)
class ForwardedHeadersTest {

    @LocalServerPort
    int port;

    @Test
    void trustedProxyHeadersChangeEffectiveOrigin() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/probe");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "edge.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            assertEquals(200, response.statusCode());
            String body = response.body();
            assertTrue(body.contains("\"scheme\":\"https\""), body);
            assertTrue(body.contains("\"host\":\"edge.example.test\""), body);
            assertTrue(body.contains("\"port\":443"), body);
            assertTrue(body.contains("\"secure\":true"), body);
            assertTrue(body.contains("https://edge.example.test/probe"), body);
        }
    }

    @Test
    void forwardedHostAffectsAbsoluteRedirect() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/go");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "edge.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        try (HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build()) {
            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding());
            assertEquals(302, response.statusCode());
            assertEquals(
                    "https://edge.example.test/probe",
                    response.headers().firstValue("Location").orElseThrow());
        }
    }
}
~~~

**Java note:** `java.net.http.HttpClient` implements `AutoCloseable` in JDKs newer than Java 17, **not in Java 17**! Since this lesson targets **Java 17+**, to guarantee the code compiles on JDK 17, instantiate the client normally and **do not use try-with-resources** on `HttpClient`. A Java 17-compliant test version follows:

~~~java
// Concrete replacement for the try-with-resources sections above:
// Use HttpClient client = ...; then call client.send(...) normally.
// Standalone example runnable on JDK 17:
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpClient17Demo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:8080/probe"))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~

Command to run the standalone demo (requires the app listening on 8080):

~~~bash
javac --release 17 HttpClient17Demo.java
java HttpClient17Demo
~~~

When the lab app runs and returns HTTP 200, expected stdout:

~~~text
HTTP status: 200
~~~

Without a server, the program throws a connection error; that is **not** default stdout. In `ForwardedHeadersTest.java` for direct execution, replace the two `try (HttpClient client = ... ) { ... }` blocks with:

~~~java
// First:
HttpClient client = HttpClient.newHttpClient();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
assertEquals(200, response.statusCode());
// ... assertions below.

// Second:
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding());
assertEquals(302, response.statusCode());
// ... assertions below.
~~~

Since the `client` variable lives in separate test method scopes, there is no conflict. `HttpClient17Demo` is standalone; the replacement blocks are fragments and do not compile standalone.

### 6.3. NoForwardedHeadersTest.java

~~~java
package com.example.webtest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "server.ssl.enabled=false",
        "server.http2.enabled=false",
        "server.forward-headers-strategy=none"
    }
)
class NoForwardedHeadersTest {

    @LocalServerPort
    int port;

    @Test
    void spoofedHeadersDoNotChangeEffectiveOrigin() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/probe");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "attacker.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        String body = response.body();
        assertTrue(body.contains("\"scheme\":\"http\""), body);
        assertTrue(body.contains("\"host\":\"127.0.0.1\""), body);
        assertTrue(body.contains("\"secure\":false"), body);
        assertFalse(body.contains("\"host\":\"attacker.example.test\""), body);
    }
}
~~~

**The outcomes of the two test cases differ intentionally.** In `framework`, the test proves the filter **can consume** forwarded headers, not that a real proxy sanitized them. In `none`, the test proves Boot's strategy ignores them when computing effective scheme/host in the baseline config. Production security tests must also run **through the real edge** and prove attackers cannot inject fake values into the backend.

### 6.4. Java 17-Compliant ForwardedHeadersTest.java (Recommended)

To avoid editing fragments by hand, here is the **complete drop-in replacement** for file 6.2 compatible with Java 17:

~~~java
package com.example.webtest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "server.ssl.enabled=false",
        "server.http2.enabled=false",
        "server.forward-headers-strategy=framework"
    }
)
class ForwardedHeadersTest {

    @LocalServerPort
    int port;

    @Test
    void trustedProxyHeadersChangeEffectiveOrigin() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/probe");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "edge.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        String body = response.body();
        assertTrue(body.contains("\"scheme\":\"https\""), body);
        assertTrue(body.contains("\"host\":\"edge.example.test\""), body);
        assertTrue(body.contains("\"port\":443"), body);
        assertTrue(body.contains("\"secure\":true"), body);
        assertTrue(body.contains("https://edge.example.test/probe"), body);
    }

    @Test
    void forwardedHostAffectsAbsoluteRedirect() throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + "/go");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "edge.example.test")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        assertEquals(302, response.statusCode());
        assertEquals(
                "https://edge.example.test/probe",
                response.headers().firstValue("Location").orElseThrow());
    }
}
~~~

**In the project tree, keep only the compliant file from section 6.4**, without keeping version 6.2 or two identically named classes. The first example explained the JDK API pitfall, while the second is the official Java 17 code.

### 6.5. Running Tests

~~~bash
mvn test
~~~

Maven/Surefire discovers class names ending in `Test`. On success, JUnit reports passing tests; test counts and formatting depend on Maven Surefire/JUnit versions. Do not fabricate a fixed stdout string.

**Verified scope:** real Tomcat server, routing, Servlet request wrappers from the forward strategy, absolute redirect behavior, and request headers over TCP. **Not yet verified:** TLS handshakes, actual proxy trust/sanitization, and ALPN; those are tested below.

## 7. Running Baseline and Testing Proxy Headers Manually

### 7.1. Baseline HTTP Ignoring Forwarded Headers

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -sS http://127.0.0.1:8080/probe
curl -i http://127.0.0.1:8080/go
~~~

With baseline `none`, `/probe` JSON reports scheme `http`, secure `false`, port 8080, and HTTP protocol typically `HTTP/1.1`. Absolute URL/`Location` point to loopback. Do not hardcode JSON property order or full headers into automated tests unnecessarily.

### 7.2. Enabling Framework Forwarding

Stop the previous process, then:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.profiles=proxy
~~~

With Maven on Windows PowerShell, `-D` parsing may require quoting the entire option. Alternatively:

~~~bash
java -jar target/web-runtime-integration-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=proxy
~~~

The JAR command requires running `mvn package` first; never run both servers simultaneously on one port.

Send simulated headers set by a trusted proxy:

~~~bash
curl -sS \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: edge.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://127.0.0.1:8080/probe
~~~

When `framework` is enabled, effective scheme/host/port are typically `https`, `edge.example.test`, `443`. Redirect:

~~~bash
curl -i \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: edge.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://127.0.0.1:8080/go
~~~

With the demo controller and framework-trusted headers, `Location` should be `https://edge.example.test/probe`. **This is a functionality test, not a trust-boundary test.** Any client reaching the localhost lab directly can send these headers; production must ensure only trusted proxies connect to the backend.

### 7.3. Checking RFC 7239 Forwarded vs X-Forwarded-*

An RFC 7239 request:

~~~bash
curl -i \
  -H 'Forwarded: for=192.0.2.10;proto=https;host=edge.example.test' \
  http://127.0.0.1:8080/go
~~~

Spring Framework supports `Forwarded`; the **header format mode** and filter used per version/configuration may require testing the explicitly selected header family. Never send conflicting `Forwarded` and `X-Forwarded-*` headers simultaneously and guess “which one definitely wins” without checking docs/runtime.

If a proxy sends `X-Forwarded-Prefix: /public`, test absolute links and redirects to ensure the prefix is prepended **once**, neither missing nor duplicated. Explicitly configure header format/prefix handling per Spring MVC 7.1 if needed. Never hardcode arbitrary client-supplied prefixes as trusted properties.

### 7.4. Security Negative Test: Attacker Spoofs Forwarded Host

~~~bash
curl -i \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://127.0.0.1:8080/go
~~~

In the `framework` lab, `Location` **can** become `https://attacker.example.test/probe`. That demonstrates why backends must never be exposed directly while trusting forwarded headers. **Never use this to introduce an open redirect on a public service**; run locally only.

In staging/production, the real test sends spoofed headers **to the public edge**, not directly to the backend. Expected: the proxy strips/overwrites them and Spring sees the **verified valid origin**, never redirecting `Location` to the attacker host. If `Location` is poisoned with the attacker's value, fix the proxy trust boundary, Host allowlist, and forwarding strategy before deploying.

## 8. Native Forwarding and Tomcat RemoteIpValve

With `server.forward-headers-strategy=native`, Boot relies on the server container. Tomcat supports `RemoteIpValve` to resolve remote IP/protocol from trusted proxies. Configurable (fragment):

~~~properties
server.forward-headers-strategy=native
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto

# Illustrative internal network CIDR expressed as a matching regex:
server.tomcat.remoteip.internal-proxies=10\.\d{1,3}\.\d{1,3}\.\d{1,3}
~~~

**Never copy this regex blindly into production.** Regexes representing trusted address ranges must be designed and tested for real proxy IPs, IPv6, hops, and security boundaries. Tomcat has defaults for internal proxies; internal networks in Docker/k8s vary per cluster.

### 8.1. Why Can Direct Localhost cURL Produce Different Results?

`RemoteIpValve` only trusts forwarded headers when the source peer IP belongs to the trusted proxy set per policy. Testing from an address **outside the trusted set** causes Tomcat to ignore or handle them differently than loopback tests. That is safe behavior, not a bug.

The right native test:

1. Deploy a test proxy with a known IP that sanitizes headers.
2. Verify the app accepts backend traffic solely from that subnet/`NetworkPolicy`.
3. Send requests through the proxy to verify `request.getScheme`/`getRemoteAddr` and `Location`.
4. Send requests from another source or with spoofed headers to verify they are untrusted.
5. Compare against `framework` mode to choose the strategy matching your needs (prefix/RFC 7239/trusted IPs).

**Never** set `server.tomcat.remoteip.internal-proxies=` empty just to turn cURL tests green. Per Boot docs, doing so can cause Tomcat to **trust every proxy**, unsafe in production.

## 9. SSL/TLS: Testing the Real Server Instead of Just Properties

### 9.1. Components of a TLS Handshake

~~~text
TLS client                          Spring Boot HTTPS server
    |                                       |
    +-- ClientHello: SNI=localhost -------->|
    |       ALPN=h2,http/1.1                |
    |<--------- ServerHello + certificate --+
    |                                       |
    +-- Validate cert chain to trusted CA
    +-- Check SAN matches hostname/IP in URL
    +-- Check notBefore/notAfter, key usage, policy
    +-- Verify TLS handshake succeeds
    |                                       |
    +-- HTTP/2 or HTTP/1.1 request -------->|
    |<-------------- response --------------+
~~~

**TLS success** requires both the cryptographic handshake and proper **server identity**. Using `https://...` or an encrypted socket is insufficient if the client disables hostname verification.

### 9.2. Keystore vs Truststore

- **Server keystore**: certificate chain + **server's private key**, used by Tomcat to prove identity.
- **Client truststore**: CA/server public certificates trusted by the client when verifying the server.
- **Server truststore for mTLS**: CA/certs of **client identities** accepted by the server when `client-auth=need`.
- **Client keystore for mTLS**: **client's** certificate + private key, verified by the server.

Never copy the server's private key to clients to “fix certificate unknown.” For normal server-auth HTTPS, clients only need to trust the public CA/cert—no client keypair is needed.

### 9.3. Generating a Self-Signed Certificate with SAN for the Lab

Run at project root on Linux/macOS/WSL with OpenSSL supporting `-addext`:

~~~bash
umask 077
mkdir -p tls

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout tls/localhost.key \
  -out tls/localhost.crt \
  -days 7 \
  -subj '/CN=localhost' \
  -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'

# Export PKCS#8 PEM key, recommended by Spring Boot for server PEM.
openssl pkcs8 -topk8 -nocrypt \
  -in tls/localhost.key \
  -out tls/localhost.pk8.key

chmod 600 tls/localhost.key tls/localhost.pk8.key

openssl x509 -in tls/localhost.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

- `-nodes` creates an **unencrypted** key for lab convenience; run only in isolated environments. Production uses secret managers/ACLs/rotation and never commits keys.
- SAN includes `DNS:localhost` and `IP Address:127.0.0.1`. Connecting by IP requires an **IP SAN**; `CN=localhost` cannot substitute for SAN.
- PKCS#8 PEM keys start with `BEGIN PRIVATE KEY` (or `ENCRYPTED PRIVATE KEY` when encrypted). Verify format instead of confusing with PKCS#1.
- Self-signed lab certificates should only be trusted explicitly by clients for that public cert, never installed as a general CA.

### 9.4. Enabling the TLS+h2 Profile

Stop the HTTP baseline, then run:

~~~bash
mvn package

java -jar target/web-runtime-integration-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=tls
~~~

Per `application-tls.properties`, embedded Tomcat listens for **HTTPS on 127.0.0.1:8443** with HTTP/2 enabled. On port 8443 there is no extra default HTTP 8080 connector; serving HTTP+HTTPS simultaneously requires configuring an additional connector (and redirect policy).

Alternatively:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.profiles=tls
~~~

Maven command-line quoting can differ across PowerShell, Bash, and Maven Wrapper; if launch misses the profile, verify via startup log/port/TLS before testing.

### 9.5. Verifying Cert/Hostname with cURL

~~~bash
curl -v --cacert tls/localhost.crt \
  https://localhost:8443/probe
~~~

Expected: the TLS peer certificate is trusted via the supplied CA/cert, hostname `localhost` matches SAN, returning JSON `scheme=https`, `secure=true`, `port=8443` (unless proxy forwards).

Command by IP:

~~~bash
curl -v --cacert tls/localhost.crt \
  https://127.0.0.1:8443/probe
~~~

This also succeeds because the lab certificate contains IP SAN `127.0.0.1`. Without the IP SAN, the IP-based command must fail hostname verification. Passing `--cacert` affects **that cURL command only**; it does not alter the JDK truststore or Spring outbound clients.

### 9.6. Negative Test: Untrusted CA

~~~bash
curl -v https://localhost:8443/probe
~~~

On machines lacking this self-signed cert in the default truststore, cURL rejects the untrusted cert before sending any HTTP request. If your machine already trusts this cert in its system CA store, the test may **fail to fail**; use an isolated truststore or another untrusted cert to test accurately.

**Never use `-k`/`--insecure` or write an all-trusting `TrustManager`** to make tests pass; that disables server identity verification.

### 9.7. Negative Test: Wrong Hostname/SAN

~~~bash
curl --noproxy '*' \
  --resolve wrong.example.test:8443:127.0.0.1 \
  --cacert tls/localhost.crt \
  -v https://wrong.example.test:8443/probe
~~~

This pins DNS for `wrong.example.test` to `127.0.0.1` while keeping URL hostname `wrong.example.test`. Because the certificate only lists SAN `localhost`/`127.0.0.1`, hostname verification must fail even though the public cert is trusted. If it unexpectedly succeeds, inspect your cURL build, proxy, TLS terminator, and actual SANs.

`--resolve` does not relax hostname validation to `127.0.0.1`; this is very useful for testing SNI and public-domain certificates before cutting over DNS.

### 9.8. OpenSSL to Inspect SNI, Chain, Hostname, and ALPN

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile tls/localhost.crt \
  -verify_hostname localhost \
  -verify_return_error \
  -alpn h2,http/1.1 </dev/null
~~~

Check output:

- `Verify return code: 0 (ok)` when chain/hostname pass OpenSSL trust options.
- ALPN protocol negotiated as `h2` or `http/1.1`.
- Cipher/TLS protocol comply with policy.
- Leaf cert, issuer, validity/SAN match the running listener.

Output/cipher numbers/handshake details vary across OpenSSL/JDK/Tomcat versions; **never hardcode** one specific cipher or TLS 1.3 suite across environments. `openssl s_client` opens a connection and waits for stdin; `</dev/null` keeps it scriptable in POSIX shells.

To inspect the live endpoint certificate (inspection only—insufficient to verify hostname/CA without trust options):

~~~bash
openssl s_client -connect localhost:8443 \
  -servername localhost -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer \
      -serial -dates -fingerprint -sha256 -ext subjectAltName
~~~

Never inspect just a local `tls/localhost.crt` file and assume Tomcat serves the new cert. Inspect the **certificate presented by the live socket**, especially behind multi-instance load balancers.

### 9.9. Expiring Certificates and Clock Checks

~~~bash
openssl x509 -in tls/localhost.crt -noout -dates
openssl x509 -in tls/localhost.crt -noout -checkend 86400
~~~

`-checkend 86400` checks whether the cert remains valid for at least the next 24 hours (exit code 0 means still valid; nonzero means expiring/invalid). This check does not replace chain/SAN/TLS handshake tests.

In CI/staging, test expired certs, missing intermediates, mismatched key/certificate pairs, unsupported ciphers/protocols, and SNI mismatches where in scope. Never expose server private keys in logs/artifacts.

## 10. HTTP/2: Enabling the Property Differs from Proving Negotiation Succeeded

Spring Boot 4.1 supports both:

- **h2:** HTTP/2 over TLS, usually selected via **ALPN** during the handshake.
- **h2c:** unencrypted HTTP/2 over TCP, typically for trusted internal hops or labs.
- **HTTP/1.1 fallback:** a client/server may fall back to HTTP/1.1 despite `server.http2.enabled=true` if ALPN/protocol support does not match.

### 10.1. HTTP/2 Over TLS

With the `tls` profile running:

~~~bash
curl -V
curl --http2 --cacert tls/localhost.crt \
  -v https://localhost:8443/probe
~~~

`curl -V` checks whether the binary supports HTTP/2 via nghttp2 or a compatible backend. If built without HTTP/2, cURL rejects the flag. `--http2` **requests/offers h2**, yet you must check the actual response protocol: on success you see `HTTP/2 200` or verbose confirmation the server accepted `h2`. If output shows `HTTP/1.1`, investigate ALPN/TLS/server/edge rather than assuming h2 is active.

Control command forcing HTTP/1.1:

~~~bash
curl --http1.1 --cacert tls/localhost.crt \
  -v https://localhost:8443/probe
~~~

Expect the route to return the same logical body while the displayed HTTP request protocol differs. H2 does not alter JSON body schemas; it changes **framing, multiplexing, header compression, and flow control** on the transport.

### 10.2. HTTP/2 Cleartext (h2c)

Stop the `tls` profile; start the `h2c` profile:

~~~bash
java -jar target/web-runtime-integration-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=h2c
~~~

Call:

~~~bash
curl --http2-prior-knowledge \
  -v http://127.0.0.1:8080/probe
~~~

`--http2-prior-knowledge` sends h2c directly via prior knowledge without an HTTP/1.1 Upgrade. With Tomcat 11 and Boot h2c support, you get an HTTP/2 response; if cURL/version/connector lacks support, the test must fail and report the root cause rather than silently falling back.

Control command:

~~~bash
curl --http1.1 -v http://127.0.0.1:8080/probe
~~~

**Never deploy `h2c` to the Internet when confidentiality/integrity is needed.** HTTP/2 does not imply TLS; `h2c` is still cleartext. If the edge terminates TLS and the backend speaks `h2c`, verify the backend network's trust policies.

### 10.3. External h2 Does Not Equal Backend h2

~~~text
Browser -- TLS+ALPN h2 --> Ingress / Envoy / Nginx
                               |
                               +-- HTTP/1.1 plaintext --> Spring MVC/Tomcat
                               |
                               +-- or h2c/TLS+h2 ------> Spring Boot
~~~

Verify the two hops separately:

1. At the edge: `curl --http2 https://public-host/probe` and `openssl s_client -alpn h2...` confirm TLS+h2 to the edge.
2. Inside the trusted network: probe the Boot backend IP:port directly with cURL HTTP/1.1/h2c/TLS per topology.
3. In the app: `request.getProtocol()` reflects the backend request seen by the app, not the browser→edge session.
4. In proxy config: confirm upstream protocol, connection reuse, timeouts, forwarded headers, and HTTP2-to-HTTP1 conversion.
5. Never see an HTTP/2 response on the client and assume Boot's `server.http2.enabled` is active.

### 10.4. HTTP/2 Is Not Simply “Faster”

HTTP/2 introduces multiplexing, HPACK header compression, stream priorities/flow control, and connection/stream limits. Test:

- Many concurrent requests over one TLS connection.
- Max concurrent streams, stream resets, flow-control stalls, and header sizes.
- TLS handshake/ALPN fallback and proxy upstreams.
- Client/broker load, p95/p99 latency, and memory/CPU.
- Cookies/large headers when HPACK interacts with header size caps.
- Graceful server shutdown can send HTTP/2 `GOAWAY`; not equivalent to WebSocket close frames.
- HTTP/2 can help over WANs yet does not guarantee higher RPS on all workloads, especially when DB-bound.

### 10.5. HTTP/2 Combined with WebSocket and gRPC

A browser running classic WebSockets over HTTP/1.1 Upgrade does not automatically switch to RFC 8441 HTTP/2 WebSockets merely because `server.http2.enabled` is true. gRPC typically relies on HTTP/2 transport and needs dedicated tests for the gRPC server stack, metadata, streaming, and LB. Never treat a simple `GET /probe` as proof that all WebSocket/gRPC traffic over HTTP/2 works.

## 11. Running TLS and HTTP/2 in Java 17 Client Tests

Besides cURL, JDK 17 provides `java.net.http.HttpClient.Version.HTTP_2`. It **offers HTTP/2**, yet you must check `HttpResponse.version()` to confirm which protocol was actually negotiated.

In a lab with a self-signed cert, create a PKCS12 truststore from the public certificate:

~~~bash
keytool -importcert -noprompt \
  -alias localserver \
  -file tls/localhost.crt \
  -keystore tls/client-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

`changeit` is a demo password only. In production use secret management and avoid passing real passwords via CLI/history/process lists.

### 11.1. Creating Http2ClientDemo.java

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class Http2ClientDemo {

    public static void main(String[] args) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        char[] password = "changeit".toCharArray();

        try (InputStream in =
                     Files.newInputStream(Path.of("tls/client-trust.p12"))) {
            trustStore.load(in, password);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);

        HttpClient client = HttpClient.newBuilder()
                .sslContext(context)
                .version(HttpClient.Version.HTTP_2)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://localhost:8443/probe"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP status: " + response.statusCode());
        System.out.println("Version: " + response.version());
    }
}
~~~

This is a **standalone Java 17 program** outside the Spring Boot classpath. It builds a truststore with the specific public cert, **without disabling hostname verification**. Connecting via hostname `localhost` must match the server cert's SAN. It uses HTTP/2 if negotiation succeeds; if server/client falls back, `response.version()` reports `HTTP_1_1`.

Run (requires the `tls` profile listening on 8443):

~~~bash
javac --release 17 Http2ClientDemo.java
java Http2ClientDemo
~~~

When handshake and HTTP/2 succeed, stdout resembles:

~~~text
HTTP status: 200
Version: HTTP_2
~~~

If it falls back to HTTP/1.1, line two is `Version: HTTP_1_1`. This is **conditional** expected output, not a guarantee the JDK always selects `h2` regardless of server/proxy. If the cert fails CA/SAN checks, the program throws `SSLHandshakeException`/`SSLPeerUnverifiedException` without returning status 200.

**Never** pass global `-Dcom.sun.net.ssl.checkRevocation=false` or custom all-trusting `TrustManager` implementations to make tests pass. Furthermore, a client trusting only the lab self-signed cert does not automatically trust arbitrary public CAs.

### 11.2. Negative Test in Java

Change the URI to:

~~~java
// Fragment: if the URI hostname lacks a matching SAN, handshake must fail,
// even when DNS routes to the server in a controlled way.
URI.create("https://wrong.example.test:8443/probe");
~~~

Changing only the URI requires DNS routing first, so for **reliable** hostname-mismatch tests, prefer `curl --resolve` or staging DNS/hosts setups. Never edit system-wide hosts files carelessly or disable hostname checks.

### 11.3. Testing Cleartext HTTP/2 with JDK

For the `h2c` profile, Java 17 `HttpClient` supports HTTP/2 upgrade semantics, yet how it chooses `h2c` depends on request/implementation and proxies. `curl --http2-prior-knowledge` behaves more explicitly against `h2c` connectors; use cURL to assert direct `h2c` and JDK `HttpClient` to test TLS+h2. Do not assume every JDK client behaves like cURL's prior-knowledge mode.

## 12. Extensions: TLS Client Auth (mTLS), SNI, and Multiple Certs

### 12.1. mTLS Is a Distinct Test Case

If the server requires mTLS:

~~~properties
# Fragment for an mTLS profile; requires matching CA trust material:
server.ssl.client-auth=need

# When using an SSL bundle for the server, declare the client CA truststore inside the bundle:
spring.ssl.bundle.pem.labhttps.truststore.certificate=file:./tls/client-ca.crt
~~~

Server-auth TLS verifies the **server**; mTLS adds **client** identity verification. Testing requires a client private key/cert issued by that CA and calling curl with:

~~~bash
curl --cacert tls/localhost.crt \
  --cert tls/client.crt \
  --key tls/client.key \
  https://localhost:8443/probe
~~~

This is an **illustrative option**: `client-ca.crt`/`client.crt`/`client.key` must be issued by a real PKI or created separately in the lab. Do not expect the command to run before generating those files. Negative tests: missing client cert, expired cert, wrong client CA, client key mismatch. Verify TLS handshake failures before the HTTP layer instead of confusing them with HTTP 401 from Spring Security.

### 12.2. Multi-Hostname SNI

If one TLS listener serves multiple domains, clients send **SNI** so the server picks the right cert. Spring Boot provides `server.ssl.server-name-bundles` on supported server implementations per docs. When testing:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername api.example.test \
  -showcerts </dev/null
~~~

And:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername alt.example.test \
  -showcerts </dev/null
~~~

Never conclude a certificate is valid merely because the leaf has the right `CN`; verify SAN/hostname and chain for **each SNI hostname** with proper trust/verify options. SNI mapping support varies across Tomcat/Jetty/Netty—verify against your runtime. Never expect a localhost demo cert to validate production hostnames.

### 12.3. TLS Termination at the Proxy

In this topology:

~~~text
Client --HTTPS--> proxy --HTTP--> Boot
~~~

The app might not enable `server.ssl.bundle` or an internal HTTPS port; the certificate clients verify is the **proxy's certificate**. You must still:

- Verify public TLS cert/chain/SAN, SNI, and ALPN at the proxy.
- Secure the internal hop (private network, network policies, or TLS/mTLS where needed).
- Sanitize forwarded headers ahead of Boot.
- Verify generated URLs/redirects match the external origin.
- Distinguish `request.isSecure()` derived from forwarded metadata from **actual TLS encryption on the backend**. `isSecure=true` after header rewriting does not prove proxy→Boot traffic is encrypted.

## 13. Testing a Real Reverse Proxy

An isolated cURL directly against the backend only proves Spring **consumes forwarded headers**, not that headers were set by a trusted proxy. In staging, include a real reverse proxy and assert:

~~~text
Public test client:
  URL https://edge.example.test/go
  Injected X-Forwarded-Host: attacker.example.test
  Injected Forwarded: host=attacker.example.test;proto=http

Edge:
  - validates allowed Host
  - strips incoming Forwarded + all client X-Forwarded-* headers
  - sets canonical headers from verified connection/TLS/DNS
  - routes to trusted backend IP:port

Backend:
  - receives trusted forwarded data
  - redirect Location points accurately to https://edge.example.test/probe
  - never uses attacker.example.test in generated absolute URLs
~~~

**Proxy configuration depends on product, version, and topology**. Never drop a “copy-paste production” Nginx file into a README omitting certificate paths, `server_name` allowlists, XFF trust chains, body size/timeouts, and Nginx versions. Use a conceptual fragment:

~~~nginx
# Illustrative fragment inside an HTTPS server's location block,
# requiring allowlisted server_name and server/infra-level network policies.
proxy_set_header Host $host;
proxy_set_header Forwarded "";
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_pass http://127.0.0.1:8080;
~~~

Use `$remote_addr` only at the **edge where the peer is the verified client**. If another trusted intermediary/load balancer sits in front of Nginx, `$remote_addr` is that upstream proxy: handle real client IPs via allowlists and trusted headers. Never use `$proxy_add_x_forwarded_for` carelessly if incoming XFF can be forged by attackers.

An edge must strip forwarded headers from both families if choosing only one family. Also watch out for `X-Forwarded-Prefix`/`X-Forwarded-Ssl` and vendor-specific headers if recognized by your stack.

### 13.1. Testing Redirects Behind a Proxy

~~~bash
curl -i --http2 https://edge.example.test/go
~~~

Expected:
- External TLS certificate matches hostname.
- When the edge supports h2, cURL records HTTP/2 on the **client→edge hop**.
- `Location` contains neither `http://backend:8080` nor an attacker host.
- If the app uses a prefix, absolute paths preserve the prefix once.
- `Secure` cookies/OAuth redirects match the external scheme and domain.

Negative check:

~~~bash
curl -i \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: for=198.51.100.9;host=attacker.example.test;proto=http' \
  https://edge.example.test/go
~~~

The result must **never** use the attacker host. If it does, that is a critical security boundary flaw—never skip or alter the expected value to make the test pass.

## 14. Testing Server Limits and HTTP Parsing

### 14.1. Header Size

Baseline includes:

~~~properties
server.max-http-request-header-size=8KB
~~~

An oversized request header should be rejected by the embedded server before reaching the MVC controller. POSIX shell example:

~~~bash
BIG_VALUE=$(head -c 20000 /dev/zero | tr '\000' 'A')

curl --http1.1 -i \
  -H "X-Large-Test: $BIG_VALUE" \
  http://127.0.0.1:8080/probe
~~~

This is a **negative lab test**—do not run against public production endpoints. Status may be 400, 431, or a closed socket depending on container/version/proxy; confirm the **request was not processed successfully** and memory did not spike abnormally. Do not hardcode HTTP 431 for every server.

HTTP/2 headers use HPACK, so compressed wire size differs from decoded header-list size. Passing a raw TCP HTTP/1.1 header-size check does not mean HTTP/2 header-list limits pass. Conversely, a proxy may reject ahead of Boot; record which layer is under test.

### 14.2. Threads/Connections/Timeouts

Setting `server.tomcat.threads.max=64` does not cap concurrent connections at 64, because keep-alive/HTTP2 multiplexing/async handling work differently from worker threads. To test:

1. Use a load generator with connection/concurrency controls (`k6`, `hey`, `wrk2`) against the lab.
2. Mix short requests, slow clients, and streaming requests.
3. Observe Tomcat busy threads, accepted connections, queue/rejections, latency, and errors.
4. Test timeouts when clients send headers/bodies very slowly, without confusing them with proxy timeouts.
5. Compare against Jetty or WebFlux to see limits do not translate 1-to-1.

**Do not** write a `sleep 1s × 100 requests` test and claim you measured TCP timeouts, since queues and OS scheduling dominate. Distinguish connect timeout, request header timeout, keep-alive timeout, async request timeout, and TLS handshake timeout.

### 14.3. Request/Response Compression

When verifying `server.compression.enabled`, test only when the response meets MIME/size thresholds and the client sends `Accept-Encoding: gzip`, then inspect `Content-Encoding`. Compression is a separate web runtime feature; never treat it as proof of TLS or h2. An HTTPS server sending an uncompressed response over HTTP/2 is still valid HTTPS+h2.

## 15. CI/CD: Designing a Matrix Instead of One Green Test

### 15.1. Recommended Matrix

| Case | Server | Proxy | TLS | HTTP Protocol | Assert |
| --- | --- | --- | --- | --- | --- |
| A | Tomcat | None | Off | HTTP/1.1 | HTTP 200 `/probe`, `scheme=http` |
| B | Tomcat | Spoofed headers, strategy `none` | Off | HTTP/1.1 | Effective origin unchanged |
| C | Tomcat | Framework forwarding (localhost) | Off | HTTP/1.1 | Scheme/host/redirect match external origin |
| D | Tomcat | Real trusted proxy | TLS at edge | External h2, backend h1 | `Location` untainted by attacker |
| E | Tomcat | None | PEM self-signed lab | HTTPS+h2 | Cert/SAN verified, ALPN `h2` |
| F | Tomcat | None | PEM self-signed lab | HTTPS+h1.1 | HTTP/1.1 fallback still works |
| G | Tomcat | None | PEM self-signed lab | Negative hostname | Handshake rejected |
| H | Tomcat | None | PEM self-signed lab | Negative CA | Handshake rejected |
| I | Tomcat | None | Off | `h2c` | cURL prior knowledge selects `h2c` |
| J | Tomcat | None | Off | HTTP/1.1 | Oversized header rejected |
| K | Jetty | Trusted proxy | Varies | h2/h1 | Compare Jetty support and config |
| L | Reactor Netty | Trusted proxy | Varies | h2/h2c | Transformer/Netty flow |
| M | TLS terminator/ingress | Present | Public CA | External HTTP/2 | Proper SNI/cert/scheme; verify upstream separately |
| N | TLS/mTLS | None | Client cert required | h1/h2 | Wrong client cert rejected |

Cases A–C run automatically in the Maven project; D–N require corresponding environment/credentials/tooling setup. **Never claim the entire matrix ran** just because `mvn test` passed.

### 15.2. Pass/Fail Rules

- HTTP status/response body must match the selected route and config.
- In proxy functionality tests, scheme/host/port/`Location` must match expected external values.
- In security tests, attacker headers must **never** alter generated URLs.
- TLS tests must validate CA/chain/hostname/SNI—never use trust-all.
- HTTP/2 tests must **assert the negotiated protocol**, not just status 200.
- Negative tests must fail at the right layer/stage (TLS handshake vs HTTP 400 vs proxy 502).
- Responses must not be truncated under proxy rewrites/h2 multiplexing/timeouts.
- When switching profiles/containers, tests must not reuse the wrong cached `ApplicationContext`/port.
- Tests must emit enough logs/diagnostics to pinpoint the failing layer without exposing secrets or cert private keys.

### 15.3. Profile Isolation

Keep profiles explicit:

~~~text
default       -> HTTP/1.1, no forwarding
proxy         -> HTTP/1.1, framework forwarding
h2c           -> HTTP/2 cleartext
tls           -> HTTPS + h2 with SSL bundle
native-proxy  -> separate option, tests RemoteIpValve from trusted proxy
~~~

Do not activate `tls,proxy,h2c` simultaneously expecting every property to combine intuitively. Test each configuration cleanly with explicit ports/client modes. For the `tls` profile, inject certs via temporary/secret test fixtures and delete private keys when CI finishes.

### 15.4. Testcontainers or Real Proxies

For forwarded-header spoofing warnings, MockMvc or direct HTTP client calls alone **are insufficient**. Run Nginx/Envoy/Traefik in Testcontainers (or Docker Compose) in CI with a trusted network configuration:

- Send traffic through the proxy.
- Inject malicious `Forwarded` and `X-Forwarded-*` headers.
- Assert the proxy strips them and the backend computes the right effective origin.
- Verify forwarding IP chains, prefixes, and redirects.
- Test edge TLS and backend TLS (if used) separately.
- Verify `h2` client-edge and `h1`/`h2c`/`h2` proxy-backend separately.

This is a **test design**, with no self-contained Docker Compose file attached because CA/ports/images/DNS/trust boundaries depend on infrastructure. Never open host networking and unrestricted allowlists just to make integration tests pass.

## 16. Logging, Metrics, and Troubleshooting

### 16.1. Minimum Observations

| Signal | What It Reveals | Caution |
| --- | --- | --- |
| Startup log/server info | Container type and listening port | Does not prove ALPN success |
| `/probe` fields | Backend-observed scheme/host/port/protocol | Does not prove headers are trusted |
| cURL `-v`/`--http2` | Real edge protocol, TLS cert | Check HTTP2 support in cURL build |
| OpenSSL `s_client` | SNI, certificate, trust, ALPN | Needs `-CAfile` and `-verify_hostname` to verify |
| Access logs | HTTP method/path/status/protocol | Mask tokens/queries/PII |
| Micrometer `http.server.requests` | Latency/errors by URI template | Never attach raw URIs/user IDs |
| Tomcat metrics | Threads, connections, sessions | Requires matching connector/MBean settings |
| Proxy logs | Upstream/downstream status, TLS, h2, retries | Client-edge and backend protocols are two hops |
| Packet capture | TLS/HTTP2 frame timing | Privacy/authorization, encrypted payloads |
| CPU/GC/memory | h2/compression/connection load impact | Never extrapolate from one cURL |
| Client cert errors | TLS trust/SAN/protocol | Never log private keys/passwords |

### 16.2. Proper Debugging Order

If clients receive redirect `http://internal:8080/login`:

1. Check browser/cURL external URL/scheme.
2. Check whether the LB/proxy stripped and set forwarded headers.
3. Check whether Boot `server.forward-headers-strategy` matches the trusted environment.
4. Check Tomcat `redirect-context-root=false` under SSL termination.
5. Inspect backend headers using redacted logging; never dump `Authorization`.
6. Check controller URI builders and context paths/prefixes.
7. Check Host allowlists/security, then test spoofed headers.
8. Never “fix” by hardcoding one public host across environments if serving multi-tenant domains without review.

If cURL `--http2` still shows HTTP/1.1:

1. Does `curl -V` support HTTP2?
2. Is the client talking to a proxy or Boot directly?
3. Did the TLS handshake negotiate ALPN `h2`? Run `openssl s_client -alpn...`.
4. Is `server.http2.enabled=true` in the active profile?
5. Does the embedded container support h2/h2c for your version/dependencies?
6. Are SSL bundle/TLS certificate/port configured right?
7. Did the proxy downgrade to HTTP/1.1 upstream?
8. Did SNI/TLS policy/header sizes fail?
9. If testing `h2c`, use `curl --http2-prior-knowledge` on the right cleartext port.
10. Compare logs and packet traces if needed, without disabling certificate validation.

If `curl --cacert` passes yet Java client throws PKIX:

- cURL's per-command truststore differs from the JSSE/JDK truststore.
- Certificate chain/intermediates may differ by SNI/proxy.
- The JDK client may be hitting a different hostname/URL.
- HTTP/2 fallback does not cause PKIX; PKIX is TLS identity validation.
- Never copy the server's private key into a truststore; add only verified public CA/certs.

### 16.3. Security Checklist

- [ ] Backend is not exposed to the public Internet while trusting forwarded headers; proxy strips both `Forwarded` and `X-Forwarded-*`.
- [ ] Proxy peer IP/CIDR allowlist is exact; Tomcat `internal-proxies` is never left empty to trust everyone.
- [ ] Hosts and redirect destinations are allowlisted/validated before entering links/password resets/OAuth.
- [ ] HTTPS verifies CA chains, SAN/hostname, validity, key usage, SNI; never uses trust-all or `curl -k`.
- [ ] TLS secrets/private keys stay in ACL-protected secret managers/volumes; never committed or logged.
- [ ] `h2c` ports run only in trusted unencrypted networks; never treat `h2c` as HTTPS.
- [ ] HTTP/2 max headers/concurrent streams/frame controls and DoS limits are evaluated.
- [ ] Insecure `/probe` or internal Actuator endpoints are never exposed publicly in production.
- [ ] Reverse proxy HTTPS redirects/HSTS/`Secure` cookies are tested against the external origin.
- [ ] mTLS, when enabled, validates both client identity and server trust; HTTP authorization remains required.

## 17. Common Mistakes

| Mistake | Why Is It Wrong? | Fix |
| --- | --- | --- |
| `@WebMvcTest` passes so TLS/h2 must work | MockMvc runs no real handshake/ALPN | Test random port/cURL/OpenSSL |
| Using `server.tomcat.*` on Netty | Different server factory/config | Pick properties/Customizers per runtime |
| Checking only `server.http2.enabled=true` | May fall back to h1 | Inspect HTTP response version and ALPN |
| Seeing HTTP/2 in browser and assuming backend is h2 | Proxy may downgrade h2→h1 | Check each hop |
| Enabling `FRAMEWORK` on a public backend | Clients can spoof forwarded hosts | Network isolation + proxy sanitization |
| Stripping only `X-Forwarded`, keeping `Forwarded` | Attackers inject via `Forwarded` | Strip both families at the edge |
| Trusting the first element of `XFF` | Attackers can prepend fake IPs | Trusted chain, proxy overwrite |
| Setting Tomcat `internal-proxies` empty | May trust all proxies | Explicit IP ranges/regex, negative tests |
| Expecting 404/503 on TLS failures | TLS fails before HTTP exists | Distinguish handshake exceptions |
| Using `curl -k` to “test” certs | Disables trust/hostname validation | Use `--cacert` and negative tests |
| SAN has DNS only yet calling by IP | IP literals need IP SAN | Use matching hostname or add IP SAN |
| Setting `server.ssl.bundle` plus standalone keystore props | Conflicting/ignored configs | Use one clear TLS mechanism |
| Reading local cert file only | Proxy/pod may serve a different cert | Inspect live endpoint with SNI |
| Enabling gzip and claiming h2 is on | Compression is unrelated to HTTP version | Check ALPN/response protocol |
| `h2c` over Internet carrying tokens | `h2c` is unencrypted | TLS h2 or private backend hop |
| `curl --http2` without checking cURL build | May lack `nghttp2` support | `curl -V`, assert negotiated version |
| Assuming HTTP/2 header limit = HTTP/1.1 bytes | HPACK/header list differs | Test both h2 and h1 |
| Assuming `Host` is trustworthy because body looks right | App may accept spoofed headers | Test spoofed hosts/redirects |
| Skipping redirect/cookie tests through proxy | Wrong absolute URLs/http scheme | Verify `Location`/`Secure`/`SameSite` |
| Running TLS+proxy+h2c profiles together | Unpredictable property overrides | Separate configs, assert active profile |
| Testing localhost only | Ingress/CDN/TLS edge have their own bugs | Production-like staging topology |
| Using JDK 21 APIs in `--release 17` source | Fails to compile on Java 17 | Check Java APIs, Maven compile/test |
| Using auto-redirecting client in JUnit | Test skips original `Location` | Disable redirects to assert 302 |
| Hardcoding handshake/cipher stdout | Varies by JDK/OpenSSL/OS | Assert protocol/cert invariants |
| Using TLS edge without securing backend hop | Internal traffic can be sniffed/spoofed | `NetworkPolicy`, service mTLS per threat model |

## 18. Final Verification Checklist

### Embedded Server Configuration

- [ ] Confirmed actual server stack/version and starter dependencies?
- [ ] Tested server binds right address/port and honors network policies?
- [ ] Tested header-size/timeout/connection limits through a real connector, not just MockMvc?
- [ ] Verified Tomcat/Jetty/Netty customizers and ensured none are silently skipped when switching runtimes?
- [ ] Kept separate profiles for h1, h2c, TLS+h2, proxy without conflicting mixes?

### Proxy Headers

- [ ] Positive tests for scheme/host/port/redirects through a trusted proxy.
- [ ] Negative spoof tests for both `Forwarded` and `X-Forwarded-*` at the external edge.
- [ ] Proxy strips/rewrites properly without forwarding malicious client headers.
- [ ] Native trusted proxy CIDRs/regex tested with trusted and untrusted sources.
- [ ] `X-Forwarded-Prefix`/`redirect-context-root` tested thoroughly if used.
- [ ] No internal hosts leaked in `Location`, links, cookies, or OpenAPI/OAuth URLs.
- [ ] `isSecure()` after header transformation is not mistaken for backend TLS.

### TLS/HTTP/2

- [ ] Served certificate passes SAN, hostname, chain, expiry, and SNI checks?
- [ ] Clients trust the right public cert/CA without insecure modes?
- [ ] HTTP/2 over TLS negotiates ALPN `h2` and responds over `h2`?
- [ ] HTTP/1.1 fallback tested explicitly?
- [ ] `h2c` restricted to trusted backends, verified with real curl prior knowledge?
- [ ] HTTP/2 multiplexing/headers/flow-control load-tested if used in production?
- [ ] Checked external edge protocol separately from upstream backend protocol?
- [ ] If using mTLS, negative tests cover missing/wrong client certs?

### CI/Observability

- [ ] `mvn test` runs embedded random-port tests with real assertions?
- [ ] cURL/OpenSSL checks run against right profiles/certs with negative cases?
- [ ] CI never exposes TLS private keys or real passwords in logs/artifacts?
- [ ] Staging deployment replicates production proxy/Ingress topology?
- [ ] Metrics/alerts monitor handshake failures, 4xx/5xx, TLS expiry, h2 fallbacks, and redirect anomalies?
- [ ] All exceptions/security leaks reported at the right layer; never fixed by disabling validation?

## 19. Self-Check Questions with Answers

**Q1.** Why does `MockMvc` not prove Spring Boot enabled HTTP/2?

**Answer:** MockMvc simulates MVC request/response objects without TCP/TLS handshakes or real ALPN/h2 framing. You need an embedded server/cURL/JDK client asserting the negotiated protocol.

**Q2.** When external clients use HTTPS/HTTP2, why can backend `request.getProtocol()` still report HTTP/1.1?

**Answer:** A reverse proxy can terminate TLS/h2 and speak HTTP/1.1 to Spring Boot. The Servlet protocol reflects the backend hop, not the entire client path.

**Q3.** When should `server.forward-headers-strategy=framework` be used?

**Answer:** When Spring must derive forwarded scheme/host/prefix and requests arrive solely from trusted proxies that sanitize headers. The filter itself cannot distinguish spoofed client headers.

**Q4.** Why not strip only incoming `X-Forwarded-Host` while leaving `Forwarded`?

**Answer:** Attackers can inject malicious values via standard `Forwarded`. The edge must strip both families before emitting new trusted headers.

**Q5.** Should `server.ssl.bundle=labhttps` and `server.ssl.key-store=...` be used simultaneously?

**Answer:** No. When using an SSL bundle, keep keystore/cert/key settings inside the bundle; standalone `server.ssl.*` options can conflict or be ignored.

**Q6.** Can HTTP/2 run without TLS? Should `h2c` be exposed to the Internet?

**Answer:** Boot 4 supports `h2c` over TCP, yet `h2c` is unencrypted. Never use it for sensitive traffic over the public Internet; use TLS `h2` or protect trusted internal hops.

**Q7.** Does `curl --http2 https://...` returning 200 prove `h2`?

**Answer:** Not yet. Inspect the actual negotiated response protocol; the client may have fallen back to `h1`. Also verify `curl -V` supports HTTP2.

**Q8.** Why can calling `https://127.0.0.1` fail even when the cert has `CN=localhost`?

**Answer:** Clients check SANs for IP literals. The cert needs `IP Address:127.0.0.1` in SAN; `CN` does not substitute for SAN.

**Q9.** Does passing a spoofed forwarded header test over localhost with `framework` mean security passed?

**Answer:** No. It only proves the framework consumes the header. Security tests must prove the public proxy strips spoofed inputs and the backend is unexposed.

**Q10.** An oversized header yields 400 or a closed socket in cURL; should tests always hardcode 431?

**Answer:** No. Parsers/proxies/containers behave differently; assert the request was rejected at the right layer without causing memory pressure.

**Q11.** Does mTLS only require the client to send a certificate?

**Answer:** No. The server must trust the client CA/cert and still present a valid server certificate to the client. API authorization remains a separate layer.

**Q12.** Why are JUnit `RANDOM_PORT` tests better than `DEFINED_PORT` in parallel CI?

**Answer:** The OS picks free ports per test server, reducing fixed-port collisions. However, TLS/proxy tests still need isolated topologies/cert fixtures.

**Q13.** Does Java 17 `HttpClient` calling `version(HTTP_2)` confirm HTTP/2?

**Answer:** Not alone. The client can fall back; inspect `HttpResponse.version()` and TLS ALPN. Clients must trust the CA and validate hostnames.

**Q14.** What should you check if a password reset link turns into `http://internal-host:8080/...`?

**Answer:** Proxy forwarded scheme/host, Boot strategy, Tomcat `redirect-context-root`, URI builders, host validation, and redirect tests through the public edge.

## 20. Official Documentation and Standards

- [Spring Boot — Embedded Web Servers, Forwarded Headers, HTTPS and HTTP/2](https://docs.spring.io/spring-boot/4.1/how-to/webserver.html).
- [Spring Boot — Testing Spring Boot Applications, RANDOM_PORT and RestTestClient](https://docs.spring.io/spring-boot/4.1/reference/testing/spring-boot-applications.html).
- [Spring Boot — Common Application Properties (server.http2, server.forward-headers, Tomcat)](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/).
- [Spring Boot — SSL Bundles (PEM/JKS and server.ssl.bundle)](https://docs.spring.io/spring-boot/4.1/reference/features/ssl.html).
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/4.1/reference/web/servlet.html).
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html).
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/4.1/reference/features/logging.html).
- [Spring Boot 4.1.2 release announcement](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Framework — ForwardedHeaderFilter and proxy security](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [Spring Framework — ForwardedHeaderTransformer (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html).
- [Spring Framework — REST Client Testing](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html).
- [Jakarta Servlet — HttpServletRequest](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest).
- [Oracle JDK 17 — java.net.http.HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113).
- [RFC 7301 — TLS ALPN](https://www.rfc-editor.org/rfc/rfc7301).
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280).
- [OWASP — TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

**Conclusion:** When testing Spring Boot's web runtime, **prove that the server, proxies, and TLS/HTTP2 behave accurately over real connections**. `MockMvc` fits controller logic yet cannot test connectors, ALPN, or certs. Use random-port integration tests for forwarding and redirects; cURL/OpenSSL/JDK clients for TLS chain/SAN/SNI and `h2`/`h2c`; verify each hop when a reverse proxy sits in front; and always include negative tests against forwarded-header spoofing, wrong CAs/hostnames, and HTTP/2 fallbacks. **Never** disable TLS validation or enable trust-all to turn tests green; production safety depends on verified trust boundaries, topology, and measured live behavior.