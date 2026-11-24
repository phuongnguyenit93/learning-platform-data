# TLS Termination at the Proxy vs. TLS Directly to the Application

## 1. Lesson Objectives

A user opens `https://shop.example.com` and sees the padlock icon in the browser. That proves the connection **from the browser to the TLS endpoint it connected to** is encrypted and verified per the client's TLS policy, yet **does not prove** that every hop from the reverse proxy/load balancer to the Spring Boot application uses TLS.

In a modern web system, there are at least three designs:

1. **TLS termination at the reverse proxy:** the browser uses HTTPS to the proxy, and the proxy forwards plaintext HTTP over the backend network to Spring Boot.
2. **Direct TLS to the application:** browsers or HTTPS clients connect straight to embedded Tomcat/Jetty/Undertow/Reactor Netty with TLS; Spring Boot holds the certificate/private key for that endpoint.
3. **TLS termination and re-encryption:** the browser speaks HTTPS to the proxy, and the proxy **opens a new HTTPS connection** to Spring Boot; each hop has its own TLS session and requires its own certificate verification.

This lesson belongs to the **TLS and HTTP/2** group of Spring Boot web runtime. After studying it, you will be able to:

- Accurately draw encryption boundaries and private-key placement for each topology.
- Distinguish TLS termination, L4 TLS passthrough, and proxy-to-origin TLS re-encryption.
- Explain why `request.isSecure()`, `request.getScheme()`, and redirect URLs can report `http` even while browsers use HTTPS.
- Configure `server.forward-headers-strategy` and understand `Forwarded` / `X-Forwarded-*` spoofing risks.
- Configure HTTPS directly in Spring Boot using `server.ssl.*` or SSL bundles, and inspect certificates and ALPN.
- Build and run a Spring Boot 3.3.5/Java 17 lab with an NGINX proxy, `keytool`, OpenSSL, and curl.
- Identify **which hop** is running HTTP/2 without equating HTTP/2 with end-to-end TLS across all hops.
- Make grounded architectural decisions based on network trust, compliance, mTLS, performance, certificate operations, and security requirements.

**Primary scope:** Spring Boot 3.3.x, Java 17+, Spring MVC with embedded Tomcat. TLS and forwarded-header principles also apply to WebFlux/Reactor Netty, though request APIs and configuration adapters differ.

## 2. Terms That Must Not Be Equated

**TLS** (Transport Layer Security) encrypts and authenticates a network connection between two TLS peers. In HTTPS, HTTP messages travel inside the TLS connection. TLS peers can be browser–proxy or proxy–application; TLS does not automatically span an entire request path end-to-end if it is terminated and re-established.

**TLS termination:** where an inbound TLS connection is decrypted. The reverse proxy holds the appropriate certificate and private key so browsers can authenticate it. After decrypting, the proxy can read the HTTP request and perform routing, caching, WAF inspection, rate limiting, or header modification.

**Upstream / origin:** the application or server sitting behind a proxy. For Spring Boot, this is usually embedded Tomcat on port 8080 or 8443.

**Re-encryption:** the proxy initiates an **independent** TLS connection to the upstream after terminating the client's TLS connection. This is not a single unbroken TLS tunnel passing through the proxy: the proxy still reads the HTTP request between the two TLS sessions.

**TLS passthrough:** a Layer 4 proxy/load balancer forwards raw TCP/TLS byte streams to the application without decrypting payloads. The endpoint certificate and private key reside on the backend application. An L4 proxy may inspect SNI in `ClientHello` to select a backend if supported, but it cannot route based on encrypted HTTP URLs/paths without terminating TLS.

**HTTP/2:** an HTTP protocol version with its own multiplexing and framing. On the public web, HTTP/2 usually runs over TLS as `h2` negotiated via ALPN; inside backend networks, cleartext HTTP/2 `h2c` can also be used where server/proxy support it. Two hops may run different HTTP versions.

**Forwarded headers:** metadata sent by a trusted proxy to the backend describing the original scheme/host/port/IP used by the client, such as `X-Forwarded-Proto: https`. These headers do not create encryption; they only **describe** the preceding hop.

**TLS certificate:** a certificate containing a public key and endpoint identity verified against a CA/trust store. The private key must be protected; the endpoint's DNS names/IPs must appear in the certificate's SAN so clients can validate the hostname.

## 3. Three Core Topologies and Protection Boundaries

### 3.1. Option A — HTTPS to Proxy, HTTP to Spring Boot

~~~text
           Encrypted TLS                   HTTP in backend
Browser ==================> NGINX/LB --------------------> Spring Boot
  |    HTTPS :443            |        HTTP :8080               |
  |                          |                                 |
  |    verifies edge cert    |  can read/modify headers/body   |
  |                          |                                 |
  '----- Trust proxy --------'---- relies on internal net -----'
                               ^
                        TLS terminates here
~~~

The browser only establishes TLS with the proxy. Spring Boot can run:

~~~properties
server.port=8080
server.ssl.enabled=false
~~~

**Pros:** centralized certificate management at the proxy/ingress/load balancer; lighter TLS config in applications; proxy can perform WAF, HTTP/2, redirects, caching, rate limiting, and host/path routing.

**Security prerequisites:** the proxy→app hop **must not be assumed secure by default**. If it traverses networks with potential attackers, shared LANs, peering, or untrusted nodes, traffic and cookies/auth headers can be read or tampered with. Isolate the backend via private networks, security groups/firewalls, a service mesh, or add TLS on that hop.

**Easy-to-miss observation:** at Spring Boot, the incoming socket is plain HTTP, so `request.isSecure()` may be `false` and `getScheme()` may return `http`. The app only knows the original HTTPS context via forwarded headers **when the path to the backend is strictly controlled**.

### 3.2. Option B — Direct HTTPS to Spring Boot

~~~text
Browser ================================> Spring Boot
         HTTPS :8443                          |
         cert + private key at app            |
                                              |
                   TLS terminates at app -----'
~~~

The application listens for HTTPS and handles the handshake, certificate selection, and cipher/protocol negotiation. Example:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:/etc/app/tls/app.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=CHANGE_WITH_SECRET
server.ssl.key-alias=app
~~~

This is an **architectural configuration example**, not a command to use a literal placeholder password in production. The keystore must exist, private key and certificate must match, and passwords must come from a secret manager/environment injection. Browsers connect directly and verify the app's certificate.

**Pros:** protects connections all the way to the application server; supports mTLS directly at the app; less reliance on proxies for accurate `scheme`.

**Trade-offs:** every instance must manage certificates, rotation, DNS/SAN, trust, ciphers/protocols, and observability; across multiple replicas, you need consistent key distribution or automated provisioning. Without a reverse proxy, any edge features normally handled by proxies must be implemented elsewhere if still needed.

### 3.3. Option C — Terminate at Proxy, Then TLS to Spring Boot

~~~text
Browser ================ HTTPS ================> NGINX/LB
                                                     |
                                   proxy reads HTTP and opens a new connection
                                                     |
Proxy ================= HTTPS/mTLS =================> Spring Boot
           backend certificate verified by proxy
~~~

Both hop 1 and hop 2 are encrypted, yet they are **two separate TLS sessions** with two separate trust and certificate decisions. Because the proxy sees HTTP between the two hops, it can still perform routing, logging, WAF, or header manipulation.

Common upstream NGINX configuration:

~~~nginx
proxy_pass https://127.0.0.1:8443;
proxy_ssl_server_name on;
proxy_ssl_name localhost;
proxy_ssl_trusted_certificate /tmp/tls-lab/app.crt;
proxy_ssl_verify on;
~~~

In this lab, the upstream certificate has SAN `localhost`, so NGINX connects to IP `127.0.0.1` while verifying the name `localhost` via `proxy_ssl_name`. **Never leave `proxy_ssl_verify off` in production**: speaking HTTPS to a backend without properly verifying certificate/hostname removes peer authentication and invites MITM risks on non-isolated networks.

**Pros:** HTTPS at the edge plus encryption/trust on the backend; pairs well with mTLS and workload identity controls. **Trade-offs:** two TLS handshakes (mitigated by keep-alive/session reuse), two sets of certificate/CA configs, and extra TLS CPU/latency. Rotation and monitoring are needed for both hops.

## 4. Comparison Table for Choosing a Topology

| Criterion | TLS at proxy + HTTP backend | Direct TLS at app | TLS at proxy + TLS backend |
| --- | --- | --- | --- |
| Browser HTTPS | Yes | Yes | Yes |
| Proxy→app connection | Plaintext HTTP | No L7 proxy in direct option | HTTPS |
| App needs TLS private key | No | Yes | Yes |
| Proxy sees HTTP body | Yes | No L7 proxy | Yes |
| Backend traffic encrypted | No | Direct link is encrypted | Yes |
| Proxy can route by path/cookie | Yes | No, unless another layer sits in front | Yes |
| Upstream authenticated via cert | Not on HTTP hop | Client authenticates app | Proxy authenticates app |
| TLS handshake at app | No | Yes | Yes |
| Forwarded headers config | Usually needed for URLs/cookies | Usually unnecessary | Often needed for public host/port |
| Browser-facing HTTP/2 | Proxy decides | App decides | Proxy decides |
| Upstream HTTP/2 | Can be enabled/disabled independently | No separate upstream | Both proxy and app must support it |
| Certificate management | Centralized at proxy | Distributed to app | Both sides, multiple cert/trust policies |

**No single option is always best.** Proxy TLS termination with internal HTTP fits well when the backend network is tightly isolated and policy permits it; organizations mandating encryption for all east–west traffic favor re-encryption/mTLS/service meshes; small deployments without a proxy can use direct HTTPS. Real architectures also depend on ingress, managed load balancers, Kubernetes, PKI tooling, and compliance.

## 5. Why Does the App See `http` Even When Users Visit `https`?

Suppose NGINX receives:

~~~http
GET /go HTTP/2
Host: shop.example.com
:scheme: https
~~~

This is a **semantic illustration of an HTTP/2 request**: real HTTP/2 pseudo-headers are `:method`, `:scheme`, `:authority`, `:path` rather than HTTP/1.1 text lines; the block above is not a literal raw wire transcript.

The proxy terminates TLS and calls the backend:

~~~http
GET /go HTTP/1.1
Host: shop.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.com
X-Forwarded-Port: 443
X-Forwarded-For: 203.0.113.25
~~~

At the socket layer, the backend receives HTTP. Without processing forwarded metadata, Servlet request APIs reflect the **proxy→app hop**—for instance `getScheme() = "http"`, `isSecure() = false`, and `getServerPort() = 8080` (when the backend inspects its local port and no header overrides host/port).

Consequences:

1. **Wrong redirects:** the server generates `Location: http://shop.example.com/...` instead of HTTPS; browsers may flag mixed schemes or enter redirect loops.
2. **Wrong absolute links:** URLs in emails, HATEOAS JSON, or HTML include `http://` or internal ports.
3. **Cookies missing `Secure`:** code relying on `request.isSecure()` to emit `Set-Cookie: ...; Secure` omits the flag even though the browser is on HTTPS.
4. **Wrong IP logging:** `request.getRemoteAddr()` only sees the proxy's IP, degrading IP-based rate limiting and auditing.
5. **Wrong base URL:** base path/host/port get altered, especially when a proxy mounts the app under a path prefix.

None of these are solved merely by installing a certificate on the proxy. The backend must **be configured to read metadata accurately within a strict trust boundary**.

## 6. Forwarded and X-Forwarded-*: Accurate and Safe

### 6.1. Common Headers

| Header | Sample value | Meaning |
| --- | --- | --- |
| `Forwarded` (RFC 7239) | `for=203.0.113.25;proto=https;host=shop.example.com` | Standardized metadata capable of representing multiple hops |
| `X-Forwarded-Proto` | `https` | Scheme between client and proxy |
| `X-Forwarded-Host` | `shop.example.com` | Public host |
| `X-Forwarded-Port` | `443` | Public port |
| `X-Forwarded-For` | `203.0.113.25` | Client IP / chain of hops depending on topology |
| `X-Forwarded-Prefix` | `/shop` | Route prefix added or stripped by proxy |
| `X-Real-IP` | `203.0.113.25` | Original client IP per proxy convention |

RFC 7239 `Forwarded` and `X-Forwarded-*` headers can coexist. Policies should establish **one trusted source**, avoiding conflicting values from both header families.

### 6.2. server.forward-headers-strategy in Spring Boot 3.3

~~~properties
# Do not apply forwarded headers to alter the request view:
server.forward-headers-strategy=none

# Let the embedded server handle them natively where supported:
server.forward-headers-strategy=native

# Use Spring Framework's mechanism:
server.forward-headers-strategy=framework
~~~

- **`none`:** does not apply forwarded headers to URLs/schemes/requests.
- **`native`:** leverages server-native support; on Tomcat, typically its Remote IP Valve. Fits proxies providing `X-Forwarded-For` and `X-Forwarded-Proto` per server conventions.
- **`framework`:** Spring MVC uses `ForwardedHeaderFilter` and WebFlux uses `ForwardedHeaderTransformer` as appropriate. Useful when handling RFC 7239 `Forwarded`, prefixes, or host semantics beyond a container's native valve.

Per Spring Boot 3.3 documentation, certain recognized cloud platforms default to `NATIVE`, whereas other environments default to `NONE`. **Setting it explicitly** in deployment ensures predictable behavior that does not silently change across environments.

With Tomcat and proxy TLS termination, Spring Boot 3.3 documentation recommends:

~~~properties
server.tomcat.redirect-context-root=false
~~~

This ensures the forwarded scheme is applied before certain context-root redirects performed by Tomcat.

### 6.3. A Trust Boundary Is Mandatory

**Clients can forge HTTP headers.** An attacker can send:

~~~http
X-Forwarded-Proto: https
X-Forwarded-For: 127.0.0.1
X-Forwarded-Host: attacker.example
~~~

If the app trusts them unconditionally, attackers can manipulate schemes, IPs, generated links, or host/protocol-dependent logic. With `framework`, the Filter/Transformer reads headers; by themselves they **cannot tell whether a header came from a proxy or a spoofing client**.

Safeguards:

1. **Allow only trusted proxies to call the backend**: firewalls, network policies, security groups, private/loopback listeners, and service identity/mTLS if needed. Never expose the backend HTTP port to the Internet.
2. **Edge proxies must strip/overwrite** external client `Forwarded` and `X-Forwarded-*` headers. Multi-hop proxy chains require explicit rules for trusted hops.
3. **Configure trusted proxies / internal proxy IPs** matching your container version, and test with real IPs. Do not assume `$proxy_add_x_forwarded_for` is safe if the edge blindly preserves client-sent `XFF`.
4. **Validate Host headers:** restrict accepted domains/hosts at both proxy and application; avoid using arbitrary request hosts to build password-reset links or sensitive redirects.
5. **Never use forwarded headers as authentication**: `X-Forwarded-For` does not prove user identity, and `X-Forwarded-Proto: https` does not encrypt backend links.

Local test commands can send spoofed headers directly to `localhost:8080`; that **does not mean** Internet users should reach the backend in production. Network boundaries must be enforced independently.

## 7. Foundational Lab: Spring Boot 3.3.5, Java 17+

The following example runs with Maven/Java 17 and needs no database. Three endpoints let you inspect what Spring Boot observes about each request:

- `GET /info` returns JSON showing the scheme, secure flag, host, port, IP, and protocol seen by the app.
- `GET /go` returns `302 Found` with an absolute `Location` built from the request context to demonstrate scheme/host/port.
- `GET /cookie` sets a demo cookie illustrating how `request.isSecure()` affects cookie issuance.

**Important:** endpoints reflecting request metadata and cookies are **learning diagnostics, not meant for verbatim public exposure in production**; avoid leaking infrastructure details and never base production secure-cookie policies on untrusted headers.

### 7.1. File Structure

~~~text
tls-topology-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/tlslab/
    │   ├── TlsTopologyApplication.java
    │   └── RequestProbeController.java
    └── resources/
        └── application.properties
~~~

### 7.2. Maven: pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tls-topology-lab</artifactId>
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

`spring-boot-starter-web` includes Spring MVC, Jackson, and Boot 3.3's default embedded Tomcat.

### 7.3. application.properties: Internal HTTP App

**File `src/main/resources/application.properties`:**

~~~properties
# Local lab binds only to IPv4 loopback.
server.address=127.0.0.1
server.port=8080
server.ssl.enabled=false

# Only trust forwarded headers after placing behind a trusted proxy.
server.forward-headers-strategy=none
server.tomcat.redirect-context-root=false
~~~

Locally, binding to loopback avoids opening port 8080 on all network interfaces. In production, proxy and app may sit on separate hosts/containers; bind to the appropriate **private interface** and block untrusted sources via firewalls. Never copy `127.0.0.1` verbatim into Kubernetes pods and then wonder why an external ingress cannot reach the pod.

### 7.4. Startup Class

**File `src/main/java/com/example/tlslab/TlsTopologyApplication.java`:**

~~~java
package com.example.tlslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TlsTopologyApplication {
    public static void main(String[] args) {
        SpringApplication.run(TlsTopologyApplication.class, args);
    }
}
~~~

### 7.5. Request Inspection Controller

**File `src/main/java/com/example/tlslab/RequestProbeController.java`:**

~~~java
package com.example.tlslab;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class RequestProbeController {

    @GetMapping("/info")
    public Map<String, Object> info(HttpServletRequest request) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("scheme", request.getScheme());
        data.put("secure", request.isSecure());
        data.put("serverName", request.getServerName());
        data.put("serverPort", request.getServerPort());
        data.put("remoteAddr", request.getRemoteAddr());
        data.put("protocol", request.getProtocol());
        return data;
    }

    @GetMapping("/go")
    public ResponseEntity<Void> redirect() {
        URI location = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/info")
                .build()
                .toUri();
        return ResponseEntity.status(HttpStatus.FOUND)
                .location(location)
                .build();
    }

    @GetMapping("/cookie")
    public ResponseEntity<String> cookie(HttpServletRequest request) {
        // Demonstrates request.isSecure() only; do not use dynamic
        // cookie Secure flags without a strictly trusted proxy.
        ResponseCookie cookie = ResponseCookie.from("demo", "1")
                .path("/")
                .httpOnly(true)
                .secure(request.isSecure())
                .sameSite("Lax")
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("cookie-created");
    }
}
~~~

Explanation:

- `request.getScheme()` and `request.isSecure()` reflect what the server/request wrapper trusts when the controller reads them.
- `request.getServerName()` and `getServerPort()` are used when constructing absolute URLs. Once forwarded metadata is handled properly, they can reflect the public host/port.
- `request.getRemoteAddr()` changes depending on how the proxy/native/framework handles client IPs, not automatically equaling the real user IP.
- `getProtocol()` normally reflects the **proxy→app hop** protocol. It **does not automatically** become HTTP/2 just because the client speaks HTTP/2 with NGINX.
- `/go` builds an absolute redirect so you can compare `Location` before/after forwarded headers config.
- `/cookie` deliberately uses `secure(request.isSecure())` to show the impact when the app misreads the original HTTPS scheme. For production apps served exclusively over public HTTPS, enforce a fixed `secure(true)` cookie policy rather than trusting client-supplied metadata unconditionally.

### 7.6. Run the HTTP App Directly

In `tls-topology-lab`, using JDK 17+ and Maven 3.9+:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -sS http://127.0.0.1:8080/info
curl -i http://127.0.0.1:8080/go
curl -i http://127.0.0.1:8080/cookie
~~~

With the current setup, the JSON response looks similar to:

~~~json
{
  "scheme": "http",
  "secure": false,
  "serverName": "127.0.0.1",
  "serverPort": 8080,
  "remoteAddr": "127.0.0.1",
  "protocol": "HTTP/1.1"
}
~~~

This is a **sample lab output**, not a guaranteed identical string across every OS/client. `/go` typically returns `302 Found` with `Location` pointing to `http://127.0.0.1:8080/info`. `/cookie` returns `cookie-created` with a `Set-Cookie` header containing `HttpOnly` and `SameSite=Lax`, without `Secure` because the request was not HTTPS.

So far there is no proxy and no TLS; this is the baseline.

## 8. Lab A — NGINX Terminates TLS and Proxies HTTP to the App

Requires Linux or a compatible environment with NGINX, OpenSSL, Bash, Java 17, Maven, and curl. The lab uses high port `9443` so root privileges are not needed to bind. `/tmp/tls-lab` is strictly for experiments; never put real private keys in public directories.

### 8.1. Generate a Self-Signed Edge Certificate

In Bash:

~~~bash
mkdir -p /tmp/tls-lab

openssl req -x509 -nodes -newkey rsa:2048 -sha256 \
  -days 7 \
  -keyout /tmp/tls-lab/edge.key \
  -out /tmp/tls-lab/edge.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 /tmp/tls-lab/edge.key
~~~

The certificate has SAN `localhost`/`127.0.0.1` so curl can validate the demo hostname. This is a **self-signed certificate, not trusted by public browsers by default**. Production must use a client-trusted CA, full issuance/renewal lifecycles, private-key protection, and hardened cipher/protocol config.

### 8.2. Local NGINX Config File

Create **`/tmp/tls-lab/nginx.conf`** with the exact contents below:

~~~nginx
worker_processes 1;
pid /tmp/tls-lab/nginx.pid;
error_log /tmp/tls-lab/error.log info;

events {
    worker_connections 512;
}

http {
    access_log /tmp/tls-lab/access.log;

    server {
        listen 127.0.0.1:9443 ssl;
        server_name localhost;

        ssl_certificate /tmp/tls-lab/edge.crt;
        ssl_certificate_key /tmp/tls-lab/edge.key;
        ssl_protocols TLSv1.2 TLSv1.3;

        location / {
            proxy_pass http://127.0.0.1:8080;
            proxy_http_version 1.1;

            # Host header forwarded by the proxy.
            proxy_set_header Host $http_host;

            # Strip standardized metadata sent directly by the client.
            proxy_set_header Forwarded "";

            # Edge proxy sets metadata for the backend.
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Port $server_port;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Real-IP $remote_addr;

            # Do not trust client-supplied prefix/SSL headers.
            proxy_set_header X-Forwarded-Prefix "";
            proxy_set_header X-Forwarded-Ssl "";
        }
    }
}
~~~

This is a **single-hop** local proxy. `X-Forwarded-For $remote_addr` intentionally overwrites prior values; do not use `$proxy_add_x_forwarded_for` at an Internet edge without stripping untrusted client headers first. Across multiple proxy hops, establish a clear chain of trust and `real_ip`/CIDR config rather than copying the local single-hop formula verbatim into production.

**Note:** the file above is a minimal learning proxy config. Production needs Host/domain allowlisting, proxy timeouts/limits, health checks, secret-safe logging, backend access blocking, TLS certificate renewal, and any additional forwarded headers used by your proxy chain. For browser WebSockets/upgrades, appropriate Upgrade/Connection handling is also needed, which this minimal config does not cover.

Validate and start NGINX:

~~~bash
nginx -t -c /tmp/tls-lab/nginx.conf
nginx -c /tmp/tls-lab/nginx.conf
~~~

If NGINX is already running with this config, do not launch a second process on port 9443. When editing config:

~~~bash
nginx -t -c /tmp/tls-lab/nginx.conf
nginx -s reload -c /tmp/tls-lab/nginx.conf
~~~

### 8.3. Start the App with Native Forwarded Headers

Stop the previously running Spring Boot instance, then run from the project directory:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.arguments="--server.forward-headers-strategy=native"
~~~

If Maven/your shell does not pass that argument cleanly, build the JAR and run explicitly:

~~~bash
mvn clean package
java -jar target/tls-topology-lab-0.0.1-SNAPSHOT.jar \
  --server.forward-headers-strategy=native
~~~

**Run only one instance bound to port 8080.** Spring Boot still receives HTTP on port 8080; `native` does not turn on TLS. Tomcat reads headers from the trusted proxy to reconstruct the original scheme/host/port.

### 8.4. Call HTTPS Through NGINX

~~~bash
curl -sS --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/info

curl -i --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/go

curl -i --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/cookie
~~~

What to observe:

- `/info` in the lab now returns `"scheme":"https"` and `"secure":true` even though the **NGINX→app connection is actually HTTP**.
- With the forwarded port processed properly, `/go` returns `Location` starting with `https://localhost:9443/info`, not port 8080.
- `/cookie` now includes the `Secure` flag because the request wrapper sees the original HTTPS scheme.
- `getProtocol()` still shows `HTTP/1.1` because NGINX uses `proxy_http_version 1.1` upstream, even if browsers speak HTTP/2 to NGINX when edge HTTP/2 is enabled.

If `native` cannot handle a particular header style, host, or prefix, test `framework` **only after securing the trust boundary**:

~~~properties
server.forward-headers-strategy=framework
~~~

Do not manually register a `ForwardedHeaderFilter` alongside Boot's auto-configuration without reason; avoid parsing forwarded headers twice or in the wrong order.

### 8.5. Diagnosing Redirect Loops

Suppose the proxy redirects all HTTP requests to HTTPS, while the app ignores `X-Forwarded-Proto`, sees incoming HTTP from the proxy, and also redirects to HTTPS. The result is an infinite loop or wrong `Location` bouncing clients back to the edge.

**How to fix:**

1. Assign **one layer** responsibility for HTTP→HTTPS redirects (usually the edge) to avoid duplicate logic.
2. Ensure the proxy forwards accurate scheme/host/port and only trusted proxies may send these headers.
3. Set `server.forward-headers-strategy` appropriately for your stack/server.
4. Inspect `Location` hop-by-hop with `curl -i`; avoid testing solely in a browser that follows redirects automatically and hides intermediate hops.

In this lab, `/go` is an explicit HTTP 302 redirect solely to inspect generated URIs, not an HTTPS enforcement policy.

## 9. Lab B — Direct HTTPS on Embedded Spring Boot

Keep the same project and controller, but have the app terminate TLS directly on port `8443`. Because configuring server SSL via properties configures a single main connector in this lab, the app **no longer listens on HTTP 8080** unless you add an extra connector in Java.

### 9.1. Create a PKCS12 Keystore with keytool

In Bash, using JDK 17 `keytool`:

~~~bash
mkdir -p /tmp/tls-lab

keytool -genkeypair \
  -alias app \
  -keyalg RSA -keysize 2048 \
  -validity 7 \
  -storetype PKCS12 \
  -keystore /tmp/tls-lab/app.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=localhost, OU=Lab, O=Example, C=VN" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1"

keytool -exportcert -rfc \
  -alias app \
  -keystore /tmp/tls-lab/app.p12 \
  -storepass changeit \
  -file /tmp/tls-lab/app.crt
~~~

`app.p12` holds the private key and certificate for TLS; `app.crt` is the exported public certificate for the lab client/proxy to trust. Password `changeit` is **strictly a demo value**. Production must never commit keystores or passwords to Git; use secret mounts, secret management, and strict file permissions.

### 9.2. Run Spring Boot with HTTPS

Stop the running HTTP app process. If you built the JAR in section 8.3, run:

~~~bash
java -jar target/tls-topology-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8443 \
  --server.ssl.enabled=true \
  --server.ssl.key-store=file:/tmp/tls-lab/app.p12 \
  --server.ssl.key-store-type=PKCS12 \
  --server.ssl.key-store-password=changeit \
  --server.ssl.key-alias=app \
  --server.forward-headers-strategy=none \
  --server.http2.enabled=true
~~~

Notice `server.address=127.0.0.1` from `application.properties` remains in effect, so the listener binds locally only. In real deployments, bind to an appropriate private address or interface while enforcing firewalls/security groups.

**Key detail:** `server.ssl.key-store` and `server.ssl.key-store-password` supply key material directly to embedded Tomcat. With `server.http2.enabled=true` and valid TLS/config, Tomcat can negotiate `h2` via ALPN with supporting clients.

### 9.3. Verify Certificate and HTTP Response

~~~bash
curl -i --cacert /tmp/tls-lab/app.crt \
  https://localhost:8443/info

curl -i --cacert /tmp/tls-lab/app.crt \
  https://localhost:8443/go

curl -i --cacert /tmp/tls-lab/app.crt \
  https://localhost:8443/cookie
~~~

In the lab, `/info` reports `scheme=https`, `secure=true` **without needing forwarded headers**, because the app's socket itself is real TLS. `/go` points to `https://localhost:8443/info`.

Inspect the handshake/certificate:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -alpn h2,http/1.1 \
  -CAfile /tmp/tls-lab/app.crt
~~~

In the output, examine the certificate chain/verify result, TLS protocol, and negotiated `ALPN protocol`. Do not copy a fixed expected stdout: ciphers and ALPN depend on client, JDK, Tomcat, OpenSSL, and builds.

If `curl` supports HTTP/2:

~~~bash
curl --http2 -sS -o /dev/null \
  -w 'HTTP version: %{http_version}\n' \
  --cacert /tmp/tls-lab/app.crt \
  https://localhost:8443/info
~~~

Expect version `2` when both client and app negotiate HTTP/2. If curl was not built with HTTP/2, `curl --http2` will error; that is **not** proof the server lacks HTTP/2 support.

**Never use `curl -k` to "fix" certificate errors in production.** `-k` merely skips TLS verification temporarily in a lab; passing `--cacert` with the matching CA/trust anchor validates the trust relationship in this exercise.

### 9.4. SSL Bundles Instead of key-store Properties

Spring Boot 3.3 supports named **SSL bundles**. You can replace the `server.ssl.key-store*` properties with:

~~~properties
server.port=8443
spring.ssl.bundle.jks.backend.key.alias=app
spring.ssl.bundle.jks.backend.keystore.location=file:/tmp/tls-lab/app.p12
spring.ssl.bundle.jks.backend.keystore.password=changeit
spring.ssl.bundle.jks.backend.keystore.type=PKCS12
server.ssl.bundle=backend
~~~

This is an **alternative configuration**, not extra lines layered onto discrete `server.ssl.key-store` properties. Per Boot 3.3 documentation, `server.ssl.bundle` **cannot be combined** with discrete keystore/PEM options under `server.ssl`.

SSL bundles also support trust material/PEM and hot reloading where consuming components support it. Issuing new certificates, rotating private keys, reloading, or changing CA chains requires a rotation plan and smoke tests rather than ad-hoc restarts.

## 10. Lab C — NGINX HTTPS to Spring Boot HTTPS (Re-Encryption)

Leave Spring Boot running on `https://127.0.0.1:8443` from Lab B. Edge NGINX still terminates TLS on `9443`, while switching Lab A's HTTP upstream to HTTPS.

In `/tmp/tls-lab/nginx.conf`, keep `server`, the edge certificate, and the trusted headers from Lab A; replace the **entire `location /` block** with:

~~~nginx
location / {
    # HTTPS to backend; NGINX opens a new TLS session.
    proxy_pass https://127.0.0.1:8443;
    proxy_http_version 1.1;

    # Upstream name for SNI and SAN verification.
    proxy_ssl_server_name on;
    proxy_ssl_name localhost;

    # App's self-signed demo cert; in production
    # use the trusted upstream CA chain.
    proxy_ssl_trusted_certificate /tmp/tls-lab/app.crt;
    proxy_ssl_verify on;
    proxy_ssl_verify_depth 2;

    proxy_set_header Host $http_host;
    proxy_set_header Forwarded "";

    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Prefix "";
    proxy_set_header X-Forwarded-Ssl "";
}
~~~

NGINX validates the upstream certificate using `proxy_ssl_verify on` and trust anchor `app.crt`. If the certificate changes to one NGINX does not trust or `localhost` is missing from the SAN, the upstream connection fails—this is the **desired security behavior**, not a reason to turn verification off.

Validate and reload:

~~~bash
nginx -t -c /tmp/tls-lab/nginx.conf
nginx -s reload -c /tmp/tls-lab/nginx.conf
~~~

Call through the edge:

~~~bash
curl -i --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/info

curl -i --cacert /tmp/tls-lab/edge.crt \
  https://localhost:9443/go
~~~

**Explaining the results:**

- Browser/curl verifies only the **edge certificate**. NGINX is the peer verifying the **backend certificate** via `proxy_ssl_verify on`.
- Spring Boot sees a TLS connection on port 8443, so `request.isSecure()` is `true` even before forwarded headers are processed.
- However, the public external port is **9443**, not backend 8443. If the app constructs absolute URLs without restoring forwarded host/port, `Location` can leak port 8443 or an internal host instead of 9443.
- Therefore, **upstream HTTPS does not eliminate the need for forwarded host/port handling**. If the app builds public URIs, enable `server.forward-headers-strategy=native` or `framework` with a proper trust boundary as in Lab A. After updating properties, restart or reconfigure the app accordingly.
- Frontend TLS and backend TLS can use **completely different certificates**. You do not need to copy the edge private key to every backend; issuing distinct upstream identities is cleaner.

### 10.1. Choosing mTLS If the Backend Needs to Authenticate the Proxy

Standard upstream TLS lets NGINX verify the app server. **Mutual TLS (mTLS)** requires the app to also verify the **proxy's client certificate**, ensuring the backend only accepts workloads with trusted certificates alongside network policies. This protects machine/connection identity and **does not replace** end-user authentication.

In NGINX, the relevant directives are:

~~~nginx
# Illustrates mTLS mechanism; requires appropriate PKI/certificates
# before enabling in a live system.
proxy_ssl_certificate /etc/nginx/tls/proxy-client.crt;
proxy_ssl_certificate_key /etc/nginx/tls/proxy-client.key;
proxy_ssl_trusted_certificate /etc/nginx/tls/backend-ca.crt;
proxy_ssl_verify on;
~~~

In Spring Boot/Tomcat, configure the server keystore, a truststore trusting the CA that issued the proxy client cert, and `server.ssl.client-auth` such as `need`; issue certs with valid SAN/EKU and handle rotation/revocation. This snippet is **illustrative config**, not a complete runnable lab since those CA/client certificates were not generated.

## 11. How Does TLS Passthrough Differ from Re-Encryption?

~~~text
A. L4 TLS passthrough
Client ===================== TLS =====================> Spring Boot
         [TCP proxy only forwards bytes, never decrypts HTTP]

B. L7 TLS termination + re-encryption
Client ========= TLS 1 =========> Proxy
                                   |
                          decrypt + inspect + route
                                   |
Proxy ============ TLS 2 =============================> Spring Boot
~~~

An L4 passthrough proxy can route by destination address/port or by SNI observed in `ClientHello` if supported, yet it cannot inspect `/checkout` paths, `Cookie` headers, or encrypted JSON bodies.

With L7 re-encryption, the proxy sees HTTP fields and can modify them before re-protecting the next hop with a new TLS session. Thus **TLS to the backend does not mean end-to-end encryption unreadable by the proxy**.

If regulatory or security requirements dictate "no intermediary may read business data," design application-level encryption or appropriate TLS passthrough, accepting the trade-off of losing proxy inspection/WAF/path-based routing.

## 12. HTTP/2: Negotiated Per Hop

HTTP/2 at the browser and HTTP/2 at the app are **two separate questions**.

### 12.1. When a Proxy Terminates TLS

~~~text
Browser -- HTTPS + ALPN h2 --> NGINX
NGINX  -- HTTP/1.1 ----------> Spring Boot
~~~

The browser can show HTTP/2 while `request.getProtocol()` in Spring Boot is `HTTP/1.1`. That is completely normal. Client-side HTTP/2 multiplexing does not automatically turn upstream connections into multiplexed HTTP/2.

Modern NGINX versions can be configured with:

~~~nginx
server {
    listen 443 ssl;
    http2 on;
    # TLS certificate and proxy_pass must be configured separately
}
~~~

`http2 on` applies to NGINX versions supporting that directive (such as 1.25.1+); older releases typically used `listen 443 ssl http2;`. This snippet is **incomplete illustrative config**, not a replacement for the lab NGINX file. NGINX `proxy_pass http://...` normally still speaks HTTP/1.x to upstreams and does not switch to HTTP/2 merely because clients speak `h2`.

### 12.2. Direct HTTPS at the App

~~~text
Browser -- HTTPS + ALPN h2 --> Spring Boot
~~~

In Spring Boot 3.3, enabling `server.http2.enabled=true` with valid TLS lets the embedded server negotiate `h2`:

~~~properties
server.port=8443
server.http2.enabled=true
server.ssl.enabled=true
~~~

These three lines **are not enough for HTTPS without a certificate/private key**; configure a keystore or SSL bundle as in Lab B. Tomcat 10.1 in Boot 3.3 supports HTTP/2 with compatible JDK/TLS; JDK/client versions and ciphers/ALPN still determine the actual outcome.

### 12.3. Cleartext HTTP/2 h2c

Spring Boot 3.3 documents support for `h2` (over TLS) and `h2c` (cleartext TCP) on certain embedded servers. `h2c` can be useful **on internal networks** behind TLS termination, provided you keep in mind:

- `h2c` **is unencrypted**; it does not replace TLS where backend networks need security.
- Upstream proxies must support/be configured for `h2c`; never assume NGINX `proxy_pass http://...` uses `h2c`.
- Verify using tools/proxy logs on the **upstream hop**, not just browser DevTools.

### 12.4. Other Related HTTP/2 Terms

- **ALPN:** TLS extension allowing client/server to agree on the protocol, e.g., `h2` or `http/1.1`.
- **SNI:** TLS `ClientHello` metadata used to pick certificates/backends by hostname. SNI **does not** validate the HTTP `Host` header.
- **Multiplexing:** multiple HTTP/2 streams on one connection; does not mean all backend requests share one thread or DB connection pool.
- **Connection reuse:** lowers handshake overhead; proxies may pool and reuse upstream connections independently of client connections.

## 13. TLS, HTTPS Redirects, HSTS, and Cookies in Practice

### 13.1. HTTP to HTTPS: Where Should It Be Enforced?

With edge termination, typically:

~~~text
HTTP :80 -> 301/308 -> https://public-host/...
HTTPS :443 -> NGINX -> backend
~~~

Redirecting at the proxy upgrades clients to HTTPS **before** reaching the app. On the backend, avoid a second redirect rule ignorant of the forwarded scheme, which easily causes redirect loops.

Pick `301`, `302`, `307`, or `308` per proper method/caching semantics; avoid unintended method-changing redirects on APIs. Because the lab uses port 9443 rather than 443, do not configure HSTS or public 80/443 redirects here.

### 13.2. HSTS

`Strict-Transport-Security` instructs browsers to connect only over HTTPS for that hostname for a specified duration. Browsers accept it over valid HTTPS responses; it does not encrypt the proxy→backend hop and does not replace certificate validation.

In production, consider HSTS at the **HTTPS edge**, evaluating domain scope, `includeSubDomains`, preload, and recovery paths carefully. Never enable `includeSubDomains` or preload experimentally if any subdomains are not ready for permanent HTTPS.

### 13.3. Secure / HttpOnly / SameSite Cookies

- `Secure`: browsers send the cookie only over connections deemed secure per browser policy; vital for session cookies on public HTTPS.
- `HttpOnly`: restricts JavaScript access to cookies; does not replace XSS/CSRF defenses.
- `SameSite`: restricts certain cross-site contexts; evaluate SSO and cross-origin login flows carefully.
- `Domain`/`Path`: scopes where cookies are sent, not an authorization boundary.

If a proxy terminates TLS while the backend sees `request.isSecure() = false`, code relying on that flag can omit `Secure`. Configure trusted forwarded headers **and** explicit production cookie policies rather than relying solely on a header clients might forge.

### 13.4. Spring Security and OAuth/OIDC Callbacks

OAuth/OIDC logins rely on redirect URIs matching the registered public host/scheme/port. If the app generates `http://internal:8080/login/oauth2/code/...`, providers may reject the callback or redirect users wrongly.

Inspect forwarded headers, reverse-proxy host/path rewriting, cookie scoping, and `Location`. Never relax OAuth redirect URI validation to paper over proxy misconfiguration.

## 14. Certificate Validation, SNI, CA, and Key Rotation

### 14.1. Browsers and Proxies Verify Different Peers

In re-encryption:

~~~text
Browser ---- verifies edge cert: shop.example.com ----> NGINX
NGINX  ---- verifies app cert: backend.internal ------> Spring Boot
~~~

Each check needs:

- A certificate valid by time and trust anchor/CA policy.
- A SAN listing the exact DNS name/IP verified by that peer.
- Matching public/private keys, a complete chain, and compatible TLS protocols/ciphers.
- Revocation/rotation workflows per infrastructure policy.

**Never treat the proxy's public certificate as proof that upstream app TLS is verified.** Nor should you confuse `proxy_ssl_server_name on` (sending SNI) with `proxy_ssl_verify on` (validating chain/host). They serve distinct purposes and both matter.

### 14.2. Backend Ports and Certificates

If the backend uses HTTPS purely to protect internal hops, certificates are typically issued via a private PKI/service mesh rather than a public DNS CA. Ensure the reverse proxy trusts that internal CA, validates SANs, and the backend only accepts permitted connections.

### 14.3. Rotation and Private Keys

When keys/certs expire or rotate:

- The edge must reload/restart its TLS listener or use proxy hot reload.
- The app can reload via SSL bundles and supported embedded servers; exact capability depends on version/consumer.
- Verify the new certificate across every hop after rotation, not merely by checking files on disk.
- Alert ahead of expiration dates and monitor handshake errors, `unknown_ca`, hostname mismatches, and mTLS failures.
- Never print secrets/passwords/key files in logs, commit them to source control, or ship them in static assets.

Boot 3.3 supports SSL bundles and reloading on supported consumers (such as Tomcat/Netty). Do not assume every truststore change or every embedded server hot-reloads identically.

## 15. Performance: Is Proxy TLS Termination Always Faster?

Offloading TLS at a proxy can reduce CPU/crypto work on apps and centralize certificate management. Yet backend HTTP/HTTPS hops, connection reuse, TLS 1.3, keep-alive, CPU cores, and load balancer sizing all affect performance.

| Factor | TLS at proxy | Direct TLS / re-encryption |
| --- | --- | --- |
| CPU spent on TLS | Centralized at proxy | On app, or both proxy and app |
| Certificate management | Fewer key distribution points | More identities/certs, though automatable |
| Handshake latency | At edge | At edge and/or upstream |
| Network hops | Adds proxy hop | Direct has fewer hops; re-encryption has proxy plus backend TLS |
| Inspection / WAF capability | Easy at proxy | Direct needs other layers; re-encryption still allows inspection |
| Backend link security | Depends on network/other layers | Protected by TLS if verification is configured properly |

**Do not automatically assume** re-encryption makes requests "twice as slow": keep-alive, session resumption, TLS offload, and proxy pooling mitigate much of it. Conversely, do not ignore real overhead. Measure RPS, p95/p99 latency, handshake rates, CPU, TLS errors, upstream connect/response times, and connection reuse under representative workloads.

Note: HTTP/2 between browser and proxy improves multiplexing, yet if the proxy opens excessive HTTP/1.1 connections to the backend, the app still hits its own worker/thread/DB pool limits. HTTP/2 does not cure database bottlenecks.

## 16. Multi-Tier Reverse Proxies and Kubernetes/Ingress

A realistic topology might look like:

~~~text
Browser -> CDN TLS -> Cloud LB TLS/HTTP -> Ingress -> Service -> Pod
~~~

Avoid saying simply "TLS terminates at the proxy" without specifying **which proxy** and every hop behind it. Ask:

1. Does initial TLS terminate at the CDN or cloud LB?
2. Is there TLS and certificate validation from CDN to LB?
3. Are LB→ingress and ingress→pod HTTP, HTTPS, or service mesh mTLS?
4. Can node/pod/backend ports be reached directly from untrusted sources?
5. Which hop sets/overwrites `Forwarded` and `X-Forwarded-*`? Is the XFF chain parsed against trusted proxy lists?
6. Do host/SNI/public URLs stay consistent across layers?
7. Which hops speak HTTP/2? Is `h2c` used internally?
8. Who rotates and monitors certificates/truststores on every hop?

An **Ingress TLS secret** for `example.com` normally only means the ingress holds a key/cert for browser→ingress. Service→Pod traffic may still be plain HTTP. If policy requires encryption to the pod, configure upstream HTTPS, service mesh mTLS, or TLS passthrough as appropriate rather than assuming `tls:` in an Ingress manifest encrypts the whole cluster.

**Trust chain note:** an ingress behind a cloud LB receives `X-Forwarded-For` populated by the LB. The ingress must trust the LB's exact CIDR/IP to recover the client IP—never trust headers straight from arbitrary Internet clients.

## 17. Common Errors and How to Check Them

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| Browser is HTTPS yet app `getScheme()==http` | Proxy terminates TLS; forwarded metadata unprocessed | Check `X-Forwarded-Proto`, `server.forward-headers-strategy`, trusted proxies |
| `Location` returns `http://...:8080` | App builds URLs from backend socket | Probe `/go`, fix forwarded host/port/proto, check context path |
| Session cookie lacks `Secure` | App sees HTTP or cookie config wrong | Check `Set-Cookie` at client and request scheme at app |
| HTTP↔HTTPS redirect loop | Two layers both redirect while backend misses public scheme | Use `curl -i`, trace every `Location` and redirect rule |
| Backend enables TLS yet NGINX uses `proxy_pass http://` | Protocol mismatch between proxy and upstream | Switch to `https://` and verify upstream |
| NGINX returns 502 after enabling upstream HTTPS | Cert mismatch, CA trust, SNI, port, or service down | Check NGINX error logs, `openssl s_client`, app listener |
| Re-encryption sets `proxy_ssl_verify off` | Upstream not securely authenticated | Issue cert with right SAN/CA, enable verification |
| Browser speaks HTTP/2, app speaks HTTP/1.1 | Two hops use different protocols | Check edge ALPN and backend `proxy_http_version` |
| Logs record only proxy IP | Trusted XFF unhandled or proxy misconfigured | Check `remoteAddr`, XFF chain, and proxy CIDR |
| Logs record spoofed `127.0.0.1` from external client | App trusts client-supplied headers | Strip/overwrite forwarded headers, block direct access |
| Direct app HTTPS hits trust errors | Self-signed/expired/hostname mismatch/missing chain | Inspect SAN, CA, SNI, `notBefore`/`notAfter` |
| KeyStore present yet Spring fails to start | Wrong password, alias, type, or path | Check `keytool -list`, `server.ssl` config, startup exception |
| Frontend `h2` works yet upstream `h2c` fails | Proxy lacks `h2c` support or it is disabled | Test protocols per hop rather than inferring from browser |
| HSTS blocks plain HTTP access | Browser cached prior HTTPS policy | Check HSTS policy, host/subdomain, use separate test host in lab |
| OAuth callback redirects to wrong host | Missing forwarded scheme/host/prefix | Check redirect URIs, proxy headers, and app config |
| TLS enabled at ingress yet internal traffic is HTTP | TLS terminates only at ingress | Check ingress upstream protocol / service mesh and network traffic |

### 17.1. Systematic Debugging Workflow

1. **Map every hop:** client → CDN/LB → ingress/reverse proxy → Spring Boot. Note ports, HTTP/HTTPS, TLS peers, and certificates per hop.
2. **Inspect the client hop:** `curl -v` or `openssl s_client` to check certificate, protocol, ALPN, and verify result. Avoid `-k` when validating real trust.
3. **Inspect the proxy→app hop:** is NGINX using `proxy_pass http://` or `https://`? Are `proxy_ssl_verify on` and CA/SNI valid?
4. **Inspect headers:** `Host`, `Forwarded`, `X-Forwarded-Proto/Host/Port/For` from trusted hops. Confirm the edge strips forged values.
5. **Inspect Spring Boot:** `server.forward-headers-strategy`, `server.ssl.*`, `server.http2.enabled`, and actual active server.
6. **Test redirects/cookies:** call `/go` and `/cookie`, check `Location` and `Set-Cookie`.
7. **Test security:** verify direct backend access is blocked from untrusted sources without exposing services in testing.
8. **Test operations:** rotate certificates in staging, test CA trust removal/SAN changes cleanly, verify alerts and rollback.

## 18. Crucial Mental Pitfalls

1. **"The browser shows the HTTPS padlock, so the backend must be HTTPS."** False when a proxy terminates TLS and forwards HTTP.
2. **"`X-Forwarded-Proto=https` means traffic to the app is encrypted."** False. It merely declares the preceding hop's scheme; clients can spoof it if trust boundaries fail.
3. **"TLS between proxy and app means end-to-end encryption no middlebox can read."** With re-encryption, the proxy decrypts requests between the two TLS sessions.
4. **"Setting `server.http2.enabled=true` makes NGINX speak `h2` upstream."** False. Protocols are chosen per hop based on proxy capabilities.
5. **"Using `proxy_pass https://` guarantees the backend link is safe."** False if upstream certificate verification is off or identity checks are broken.
6. **"Framework forwarded headers are safe when the app is public."** False if attackers can send headers straight to the app or the edge fails to strip them.
7. **"HTTP/2 is an encryption mechanism."** HTTP/2 is an HTTP version; TLS is the transport security layer. `h2c` is cleartext HTTP/2.
8. **"HSTS protects internal hops."** HSTS governs browser behavior toward the public origin, not proxy→app links.
9. **"mTLS between proxy and app means the end user is logged in."** mTLS authenticates the workload/connection peer; end-user identity is a separate layer.
10. **"No need to test certificates after rotation."** Truststores/chains/SANs/SNI can cause proxy 502s even after copying the new certificate into the right folder.

## 19. Self-Check Exercises

**Question 1.** Browser connects to NGINX via HTTPS and NGINX sends HTTP to Spring Boot. What does `getScheme()` in the app usually return before processing forwarded headers? And after properly trusting `X-Forwarded-Proto`?

**Question 2.** Why can two requests both show `https://shop.example.com` in the browser yet have very different backend security?

**Question 3.** In re-encryption, who verifies the backend's certificate: the browser or the proxy? When `proxy_ssl_verify off` is set, what protection is missing?

**Question 4.** If a Spring Boot app serves HTTPS directly on 8443, which properties configure the keystore and port? Does Boot keep an HTTP 8080 connector automatically when only `server.ssl` is set in `application.properties`?

**Question 5.** The user has HTTP/2 to the edge, yet the controller's `getProtocol()` returns `HTTP/1.1`. Is that an error?

**Question 6.** Why must sending `X-Forwarded-For: 127.0.0.1` from an external client never make the application treat that as the real client IP?

**Question 7.** An organization mandates encrypting traffic from ingress to pod. Is declaring a certificate on the ingress alone enough? What are two implementation paths?

**Question 8.** Compare TLS passthrough and re-encryption regarding the proxy's ability to inspect HTTP paths and bodies.

**Question 9.** Why might a proxy still need to send `X-Forwarded-Port`/`X-Forwarded-Host` even when the upstream already uses HTTPS?

**Question 10.** An NGINX HTTPS upstream starts returning 502 right after rotating the app's certificate. What should you check in order instead of disabling `proxy_ssl_verify`?

**Suggested answers:**

1. Before processing, usually `http`; after trusting a valid forwarded scheme, `https`. That still does not turn the HTTP backend link into TLS.
2. Because TLS only protects each session between peers; the proxy-to-app leg may be HTTP or HTTPS depending on design.
3. NGINX/proxy acts as the TLS client to the backend and must verify the backend cert. Disabling verify removes peer/CA/hostname authentication.
4. `server.port`, `server.ssl.enabled`, `server.ssl.key-store`, `server.ssl.key-store-type`, `server.ssl.key-store-password`, `server.ssl.key-alias` (or an SSL bundle). Boot properties do not keep an extra HTTP connector once the main connector switches to HTTPS.
5. No. Client→proxy uses HTTP/2 while proxy→app uses HTTP/1.1.
6. Because HTTP headers are text clients can forge; only the proxy at the trust boundary may set/overwrite them, and the app must accept them only from trusted proxies.
7. Not enough. Configure upstream HTTPS with certificate verification or service mesh mTLS; TLS passthrough can also fit where routing constraints allow.
8. Passthrough only forwards TLS bytes, so the L4 proxy cannot read HTTP bodies/paths. Re-encryption terminates and starts a new TLS session, letting the proxy inspect/modify HTTP.
9. TLS secures the upstream scheme, yet the public host/port can differ from the backend's; absolute redirects/links must reflect the client's URL.
10. Check app listener/port, CA/truststore, SAN/hostname, SNI, certificate chain/expiry, NGINX error logs, and TLS handshake; fix trust/certs properly rather than turning off verification.

## 20. Deployment Checklist

- [ ] Accurately diagrammed all TLS endpoints/hops and private-key locations.
- [ ] Identified where TLS terminates, where plaintext HTTP travels, and where re-encryption/mTLS applies.
- [ ] Blocked direct backend access from untrusted clients.
- [ ] Edge validates and fully overwrites inbound `Forwarded`/`X-Forwarded-*` headers.
- [ ] `server.forward-headers-strategy` matches your proxy and web stack.
- [ ] Redirects, links, public Host, and port are accurate in `Location`.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite` attributes verified at the client.
- [ ] Certificates and SAN/trust verified on **every hop**, without `-k`/`proxy_ssl_verify off` in production.
- [ ] HTTP/2/`h2`/`h2c` verified **per hop**.
- [ ] Clear policies exist for HSTS, TLS protocols, session resumption, and certificate rotation.
- [ ] Tested proxy 502s, trust failures, expired certificates, host mismatches, app restarts, and rollbacks.
- [ ] Monitored handshake errors, latency, TLS certificate expiration, and redirect loops.

## 21. References

- Spring Boot 3.3 — Embedded Web Servers: SSL, HTTP/2, proxy forwarded headers, reverse proxies: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — SSL bundles and key/trust material: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.2 — Forwarded headers and Security Considerations: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
- NGINX — Securing HTTP Traffic to Upstream Servers: https://docs.nginx.com/nginx/admin-guide/security-controls/securing-http-traffic-upstream/
- NGINX — `proxy_ssl_verify`, `proxy_ssl_name`, `proxy_ssl_server_name`: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- RFC 9110 — HTTP Semantics, scheme and authority: https://www.rfc-editor.org/rfc/rfc9110
- RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3: https://www.rfc-editor.org/rfc/rfc8446
- RFC 9113 — HTTP/2: https://www.rfc-editor.org/rfc/rfc9113