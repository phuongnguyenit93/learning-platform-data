# Enabling HTTP/2 and Checking Server Support Requirements in Spring Boot

## 1. Goal: Enable the Right Protocol, Measure the Right Result

HTTP/2 is an HTTP protocol version featuring **binary framing**, **multiplexing** multiple request/response streams over a single connection, and **header compression** (HPACK). In Spring Boot, support can be enabled with one property:

```properties
server.http2.enabled=true
```

However, this is **only a configuration request**. Whether a client actually uses HTTP/2 also depends on:

- **The running HTTP server:** Tomcat, Jetty, Undertow, or Reactor Netty, and their accompanying HTTP/2 modules.
- **Connection mode:** `h2` (HTTP/2 over TLS/HTTPS) or `h2c` (HTTP/2 without TLS).
- **JDK/TLS provider/ALPN:** for `h2`, client and server must negotiate the protocol during the TLS handshake.
- **Client:** whether curl, the browser, load balancer, ingress, or proxy supports HTTP/2 on that exact connection.
- **Network path:** HTTP/2 between **browser and reverse proxy** does not mean HTTP/2 between **reverse proxy and Spring Boot**.
- **Certificates and TLS policy:** certificates, ciphers, TLS versions, and hostnames must satisfy production requirements.

The verification target is not merely seeing the application start cleanly or seeing the property set to `true`. You must observe the **actual HTTP version** on the connection, such as `curl -w '%{http_version}'` output or the selected ALPN protocol.

This lesson illustrates with **Spring Boot 3.5.x, Java 17+, and embedded Tomcat**. When referring to Jetty, Undertow, and Reactor Netty, verify the exact Spring Boot/embedded server versions rather than applying Boot 2.x or 4.x guides verbatim.

## 2. Distinguishing HTTP/1.1, HTTP/2, h2, h2c, and HTTPS

### 2.1. What Does HTTP/2 Improve?

HTTP/1.1 supports keep-alive to reuse connections, but carrying multiple concurrent requests over a single connection is limited. Browsers often open multiple connections or queue requests. HTTP/2 lets multiple **streams** coexist on one connection, with each stream split into binary **frames** and governed by flow control.

Benefits can appear on pages with many small assets or APIs issuing multiple requests over a connection:

- Multiple concurrent streams help avoid some of HTTP/1.1's sequential bottlenecks.
- HPACK reduces repeated headers compared to sending full headers on every request.
- A single connection is used more efficiently under certain traffic patterns.
- HTTP semantics like `GET`, `POST`, URLs, and status codes stay the same; most controllers/services need no changes due to the protocol switch.

HTTP/2 does **not** turn blocking JDBC into reactive I/O, does not speed up slow database queries by itself, and does not guarantee lower latency in every case. A single TCP connection still suffers from TCP head-of-line blocking at the transport layer; HTTP/3 built on QUIC addresses some of those limits differently. Server Push used to be an HTTP/2 feature, but new applications should not rely on it: browser support has largely been deprecated/removed.

### 2.2. Two Ways to Run HTTP/2

| Term | Transport | Where it is used | How it is negotiated |
| --- | --- | --- | --- |
| `http/1.1` | TCP, optionally with TLS | Ubiquitous and broadly compatible | HTTP/1.1, or chosen when HTTP/2 is absent |
| **`h2`** | TLS/HTTPS | Standard browser ↔ server/reverse proxy connections | **ALPN** in the TLS handshake |
| **`h2c`** | TCP without TLS | Internal networks, proxy → backend, test environments | HTTP/1.1 `Upgrade: h2c` or HTTP/2 prior knowledge |
| **HTTP/3** | QUIC/UDP, with built-in TLS | Dedicated HTTP/3 ecosystem | Not enabled by the HTTP/2 property |

**h2 and h2c are not interchangeable:**

- `h2` requires TLS and ALPN negotiating protocol identifier `h2`.
- `h2c` does not encrypt traffic in transit. Only use it where you truly control the network segment, such as an internal link behind a reverse proxy or secure mesh.
- Most browsers implement HTTP/2 **only over HTTPS (h2)**, not arbitrarily using `h2c` for public websites.
- `server.http2.enabled=true` does not issue TLS certificates, does not turn on HTTPS, and does not adjust proxy configuration.

### 2.3. HTTP/2 Is Not "TLS 2" or "SSL 2"

TLS 1.2/1.3 is the **transport security protocol**; HTTP/2 is the **application protocol version** running over it in `h2` mode. The identifier `h2` does not mean TLS version 2. Nor does HTTP/2 force web applications to use reactive programming.

Diagram:

```text
Browser                         Spring Boot embedded Tomcat
  |                                     |
  | TCP connect :8443                   |
  |------------------------------------>|
  | TLS ClientHello + ALPN h2,http/1.1  |
  |------------------------------------>|
  | TLS ServerHello + selected h2       |
  |<------------------------------------|
  | HTTP/2 frames: GET /api/protocol    |
  |====================================>|
  | HTTP/2 frames: 200 + response       |
  |<====================================|
  | multiple streams can share 1 conn   |
```

If TLS selects `http/1.1` instead of `h2`, the same endpoint can still return HTTP 200, yet **that does not count as successfully testing HTTP/2**.

## 3. Core Property in Spring Boot

### 3.1. Enabling HTTP/2 Support

```properties
server.http2.enabled=true
```

Per **Spring Boot 3.5** documentation, both variants are supported:

- When **server SSL/TLS is enabled**, HTTP/2 uses **`h2`** over TLS (when server/JDK/client negotiate it).
- When **SSL is not enabled**, the server can support **`h2c`** over TCP; suited for certain deployments behind a TLS-terminating proxy.

You do not need a special `@RestController` to "turn on HTTP/2": protocol selection occurs at the **web server/connector** before requests reach controllers. Controllers can stay unchanged whether clients speak HTTP/1.1 or HTTP/2.

### 3.2. Combining with HTTPS

A PKCS#12 keystore configuration might look like:

```properties
server.port=8443
server.http2.enabled=true
server.ssl.enabled=true
server.ssl.key-store=file:./dev-keystore.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=localdev
```

This is a **learning environment configuration example**. `file:./dev-keystore.p12` points to a keystore **outside the JAR**, resolved relative to the process working directory. The password comes from an environment variable rather than being hardcoded in source. If the keystore/certificate is invalid, the server may fail to start or handshakes will fail; `server.http2.enabled` cannot fix that.

For production, manage certificates/private keys via a secret manager, mounted secrets, or SSL bundles, using a trusted CA and accurate hostnames. **Do not commit private keys/keystores to Git** and do not serve real traffic with demo self-signed certificates.

### 3.3. Other Settings to Distinguish

| Property/mechanism | Effect | How does it relate to HTTP/2? |
| --- | --- | --- |
| `server.http2.enabled` | Enables HTTP/2 support on the web server | Primary flag |
| `server.port` | Listening port | Does not determine protocol |
| `server.ssl.*` | TLS certificates, keys, protocols/ciphers | Required for `h2` over HTTPS |
| `server.ssl.bundle` | References a named SSL bundle | Alternative to discrete TLS config |
| `server.forward-headers-strategy` | Handles forwarded headers from proxies | Does not directly turn upstream into HTTP/2 |
| `server.compression.enabled` | Compresses HTTP response bodies | Independent of HTTP/2/HPACK |
| `management.server.port` | Separate Actuator port if configured | Must check protocol/cert of that listener separately |
| `spring.main.web-application-type` | Servlet, reactive, or none | Influences which web server starts, does not directly mandate `h2` |

**Do not confuse HPACK with gzip:** HTTP/2 compresses **headers** via HPACK; response **bodies** may still use gzip/br depending on `Accept-Encoding` and compression settings. Enabling HTTP/2 does not mean JSON/images/bodies are automatically compressed.

## 4. Support Requirements by Embedded Server

Spring Boot can run on several web servers; HTTP/2 is not purely a "Spring MVC dependency."

### 4.1. Matrix for Spring Boot 3.5

| Server | Typical web stack | h2 TLS | h2c without TLS | Primary requirements |
| --- | --- | --- | --- | --- |
| **Tomcat 10.1.x** | Default Spring MVC Servlet | Yes | Yes | Java 17+ and valid TLS/ALPN; Boot enables `server.http2.enabled` |
| **Jetty** | Servlet or reactive adapter | Yes | Yes | **Requires adding Jetty HTTP/2 server module**; `h2` TLS also needs an ALPN provider |
| **Reactor Netty** | Default Spring WebFlux | Yes | Yes | Supported in the default stack; native TLS library is an optional optimization, not mandatory |
| **Undertow** | Servlet or adapter if supported by Boot release | Yes | Yes | Proper Boot/server integration and matching version |

**Version scope:** this table reflects **Spring Boot 3.5.x** guides, not a promise that every similarly named starter/server exists in Boot 4.x. Newer Spring Boot major versions may change which web servers are supported. Always verify against your running version's BOM/guide.

### 4.2. Tomcat (Default for `spring-boot-starter-web`)

With Spring Boot 3.5, the web starter typically pulls in **Tomcat 10.1.x**. Tomcat supports both `h2` and `h2c` without needing native libraries to run HTTP/2 in modern Java. JDK 17 includes ALPN in JSSE so `h2` over TLS works immediately with proper configuration.

Tomcat offers an optional `libtcnative`/OpenSSL path for native TLS in certain setups; that is an **optimization/deployment choice**, not a baseline requirement to run HTTP/2 on Java 17.

For a **standalone** Tomcat outside Spring Boot, an administrator might manually configure `UpgradeProtocol`/connectors. For **embedded Tomcat auto-configured by Spring Boot**, start with `server.http2.enabled=true` before writing custom connector code.

### 4.3. Jetty: Watch for HTTP/2/ALPN Modules

In Spring Boot 3.5, when replacing Tomcat with Jetty, adding only `spring-boot-starter-jetty` without the HTTP/2 module **can be insufficient**. Boot docs specify the dependency:

```xml
<dependency>
    <groupId>org.eclipse.jetty.http2</groupId>
    <artifactId>jetty-http2-server</artifactId>
</dependency>
```

This is a **dependency fragment**, not a complete POM. For **h2 over TLS**, on a JDK with ALPN you usually also add:

```xml
<dependency>
    <groupId>org.eclipse.jetty</groupId>
    <artifactId>jetty-alpn-java-server</artifactId>
</dependency>
```

An alternative per Jetty docs is using Conscrypt and `jetty-alpn-conscrypt-server` if the environment is set up for it. Do not pile on every ALPN provider out of habit. For non-TLS `h2c`, the Jetty HTTP/2 server module is the key step; no TLS ALPN provider is needed.

To switch from Tomcat to Jetty in Spring MVC, exclude the Tomcat starter and add the Jetty starter for your exact version. Example **replacement dependencies snippet** for `spring-boot-starter-web`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
<dependency>
    <groupId>org.eclipse.jetty.http2</groupId>
    <artifactId>jetty-http2-server</artifactId>
</dependency>
<dependency>
    <groupId>org.eclipse.jetty</groupId>
    <artifactId>jetty-alpn-java-server</artifactId>
</dependency>
```

Do not paste this snippet into section 7's Tomcat demo `pom.xml` unless you **intentionally switch servers** and verify documentation for your exact Spring Boot version.

### 4.4. Reactor Netty and WebFlux

With `spring-boot-starter-webflux` alone, Spring Boot uses **Reactor Netty**. In the Boot 3.5 line, Reactor Netty supports `h2` and `h2c`. Java 17 provides modern TLS/ALPN; you can add `io.netty:netty-tcnative-boringssl-static` on compatible platforms to use native TLS for optimization, though it is **not required merely to prove HTTP/2 works**.

If a project declares **both** `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot normally selects the **Servlet MVC web application type** unless configured otherwise. Do not spot `reactor-netty` in the dependency tree and conclude your HTTP server is Netty.

### 4.5. Undertow

Spring Boot 3.5 supports HTTP/2 `h2`/`h2c` in Undertow without requiring an extra `h2` module per the embedded web server guide. Actual behavior still depends on configuration, JDK/TLS, and runtime. For newer major Boot versions, verify whether the Undertow starter is still supported before copying an older POM.

### 4.6. Pre-Enablement Checklist

1. Confirm the **exact Spring Boot version** and managed server version via Maven/Gradle dependency tree.
2. Confirm the **web application type**: MVC/Tomcat, WebFlux/Netty, or custom server.
3. Confirm the **TLS termination tier**: whether Spring Boot handles HTTPS directly or a load balancer/ingress does.
4. Check the Java runtime with `java -version`; this lesson uses **JDK 17+**, which includes standard ALPN support.
5. If using Jetty, add the matching HTTP/2/ALPN modules for your version.
6. Configure `server.http2.enabled=true` and certificates/SSL for `h2`.
7. Verify with an **HTTP/2-capable client** rather than checking only the application startup logs.
8. Also verify HTTP/1.1 fallback and security/operational metrics.

## 5. ALPN: Why HTTPS Does Not Automatically Mean HTTP/2

**ALPN** (Application-Layer Protocol Negotiation) is a TLS extension allowing client and server to pick the application protocol on a TLS connection. A browser may offer `h2` and `http/1.1`; the server chooses a supported protocol. If the server selects `http/1.1`, HTTPS still works normally, yet the connection **is not HTTP/2**.

Processing flow:

```text
TLS ClientHello
  ALPN protocols: ["h2", "http/1.1"]
                     |
                TLS server
             certificate + key
             TLS version/ciphers
             HTTP/2 capability
                     |
ALPN selected: h2   (when client/server support aligns)
                     |
 HTTP/2 connection preface and frames
```

### Java and ALPN

- JDK 17 includes ALPN in the standard Java TLS stack; you do not need old instructions requiring the **JDK 8 ALPN boot patch**.
- When running custom JDK/JSSE providers, FIPS environments, SSL proxies, or special native TLS, confirm the negotiated protocol via `curl`/`openssl`.
- HTTP/2 over TLS requires TLS versions and cipher suites compliant with HTTP/2 rules; in production use modern TLS 1.2/1.3 and strong certificates/keys.
- TLS 1.3 is not the **only requirement** for HTTP/2: `h2` can work over compliant TLS 1.2.
- An invalid certificate or hostname mismatch is a TLS/trust error; never "fix" it by disabling certificate checks in production.

### Inspecting ALPN with OpenSSL

While the local TLS server runs on 8443:

```bash
openssl s_client -connect localhost:8443 -servername localhost -alpn h2,http/1.1
```

In a successful output, look for a line like:

```text
ALPN protocol: h2
```

Actual value may be `h2`, `http/1.1`, or none negotiated depending on server/client. The command above **has not sent a full HTTP/2 request**; it only tests TLS/ALPN. Follow up by testing a real request with `curl --http2`.

The local self-signed certificate may still cause OpenSSL to print a verification error—that concerns **certificate trust**, separate from whether ALPN selected `h2`.

## 6. Distinguishing HTTP/2 at the Edge, Upstream, and Client

When using a reverse proxy:

```text
Browser --HTTPS + h2--> Nginx / Ingress / CDN
                              |
                   HTTP/1.1 or h2c or h2
                              |
                       Spring Boot backend
```

There are **two independent connections**. A proxy can easily speak HTTP/2 externally while sending HTTP/1.1 to the app. In that case:

- Browser DevTools shows HTTP/2.
- `curl --http2 https://public-domain` shows HTTP/2.
- Backend requests may still be HTTP/1.1 and might not even need `server.http2.enabled`.
- Protocol optimization on the outside **does not prove** HTTP/2 reaches the backend.

If your architecture needs end-to-end HTTP/2 or upstream gRPC, verify that the proxy explicitly supports **upstream HTTP/2/h2c**, configure the gateway accordingly, and test **directly** or from a pod/host on the backend network. Many proxies default `proxy_pass` HTTP upstreams to HTTP/1.1; they do not automatically upgrade to `h2c` just because the edge speaks `h2`.

### TLS Termination at Spring Boot

```text
Client -- TLS/ALPN h2 --> Spring Boot:8443
```

Enable `server.http2.enabled=true` and Spring Boot TLS. Verify both ALPN and the server handler directly.

### TLS Termination at Proxy

```text
Client -- TLS/ALPN h2 --> Gateway -- HTTP/1.1 --> Spring Boot:8080
```

Client-facing HTTP/2 is handled by the gateway. Having the backend speak HTTP/1.1 can still be a **reasonable** choice, not a bug. Weigh security, compatibility, and measured performance before demanding upstream `h2c`.

### h2c on an Internal Network

```text
Gateway -- h2c on trusted network --> Spring Boot:8081
```

Spring Boot 3.5 can support `h2c` when SSL is off. However, **h2c does not encrypt payload content** and does not authenticate peers via TLS; enforce network-layer security boundaries, a service mesh, or end-to-end TLS for sensitive data.

**Watch out with forwarded headers:** `X-Forwarded-Proto: https` describes the public scheme in front of the proxy, not "the upstream is using HTTP/2." Never use that header to infer HTTP/2, and never trust forwarded headers that Internet clients could forge.

## 7. Runnable Example: Java 17 + Spring Boot MVC + Embedded Tomcat

The demo project below builds and runs on JDK 17+, Maven, and Spring Boot **3.5.0** (a 3.5-line release, not a claim that it is the latest patch). Update the patch version per your real project policy.

We will create three config files:

- `application.properties`: enables HTTP/2 globally.
- `application-tls.properties`: HTTPS/`h2` profile on port 8443.
- `application-h2c.properties`: HTTP/`h2c` profile on port 8081.

Using two independent profiles lets you **run the h2c test without supplying a keystore password**, while making the differences easy to compare.

### 7.1. Directory Structure

```text
http2-demo/
├── pom.xml
├── dev-keystore.p12            (created with keytool; local only, do not commit)
└── src/
    └── main/
        ├── java/
        │   └── com/example/http2demo/
        │       └── Http2DemoApplication.java
        └── resources/
            ├── application.properties
            ├── application-tls.properties
            └── application-h2c.properties
```

`dev-keystore.p12` is **not inside `src/main/resources`** so it is not packaged into the executable JAR in this layout. Run commands from the root directory containing the POM so `file:./dev-keystore.p12` resolves properly.

### 7.2. Complete `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http2-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
```

`spring-boot-starter-web` pulls in Spring MVC and Boot-managed embedded Tomcat. No `jetty-http2-server` dependency is needed because the example **does not use Jetty**. Java 17 is used by the Spring Boot parent/Maven plugin for compilation.

### 7.3. Complete Java Source

File `src/main/java/com/example/http2demo/Http2DemoApplication.java`:

```java
package com.example.http2demo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class Http2DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(Http2DemoApplication.class, args);
    }
}

@RestController
class ProtocolController {

    @GetMapping(value = "/protocol", produces = MediaType.TEXT_PLAIN_VALUE)
    public String protocol(HttpServletRequest request) {
        return "servletProtocol=" + request.getProtocol()
                + "\nscheme=" + request.getScheme()
                + "\nsecure=" + request.isSecure() + "\n";
    }

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "hello\n";
    }
}
```

In the same Java file, `Http2DemoApplication` is the `public` class matching the filename; `ProtocolController` is package-private and still picked up by component scanning. `HttpServletRequest#getProtocol()` reports the protocol **handled directly by the backend server** (typically `HTTP/2.0` in Tomcat with `h2`). `getScheme()`/`isSecure()` reflect how the Servlet container sees the request; if behind a proxy with forwarded-header processing enabled, those values can be affected by trusted forwarded headers.

Having the controller return simple strings proves **business code does not manually write HTTP/2 frames**. Spring/Tomcat generates the corresponding frames and headers.

### 7.4. Properties

File `src/main/resources/application.properties`:

```properties
server.http2.enabled=true
```

File `src/main/resources/application-tls.properties`:

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./dev-keystore.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=localdev
```

File `src/main/resources/application-h2c.properties`:

```properties
server.port=8081
server.ssl.enabled=false
```

**Important:** activate **one profile** per launch. Do not run both profiles `tls,h2c` together in this demo because properties targeting the same keys override each other in order rather than creating two separate listeners.

### 7.5. Create a Self-Signed Certificate with JDK keytool

From `http2-demo`, create a PKCS12 keystore for **local testing**:

```bash
keytool -genkeypair -alias localdev -keyalg RSA -keysize 2048 -storetype PKCS12 -keystore dev-keystore.p12 -storepass changeit -keypass changeit -validity 30 -dname "CN=localhost, OU=Development, O=Example, L=HCMC, ST=HCMC, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1"
```

The command is on a single line so it runs in Bash, PowerShell, or standard shells with JDK/`keytool` in PATH. The SAN includes `localhost` and `127.0.0.1` so the certificate matches the demo hostnames. A **self-signed** certificate is not trusted by public CAs by default; browsers/curl will report verification errors unless trust or test flags are supplied.

Inspect the keystore (without exporting the private key):

```bash
keytool -list -keystore dev-keystore.p12 -storetype PKCS12 -storepass changeit
```

Output should show alias `localdev` (timestamp/metadata lines vary by JDK). **Never take this keystore or the `"changeit"` password into production.** Add `dev-keystore.p12` to `.gitignore` if using Git.

### 7.6. Build the Application

In the directory containing the POM:

```bash
mvn clean package
```

After a successful build, `target/http2-demo-1.0.0.jar` is produced. Important runtime prerequisites:

- `dev-keystore.p12` exists in the working directory.
- Environment variable `TLS_KEYSTORE_PASSWORD` is set.
- Port `8443` is not already in use.
- JDK and OS support TLS/ALPN.

In **Bash/Linux/macOS**:

```bash
export TLS_KEYSTORE_PASSWORD=changeit
java -jar target/http2-demo-1.0.0.jar --spring.profiles.active=tls
```

In **PowerShell**:

```powershell
$env:TLS_KEYSTORE_PASSWORD = 'changeit'
java -jar target/http2-demo-1.0.0.jar --spring.profiles.active=tls
```

This is a **demo password**; in production supply it via a secret manager/secured environment, never log it, and never commit secret files. If the password is omitted, the environment placeholder fails to resolve and the app refuses to start—correct behavior to avoid starting with bad keystore config.

### 7.7. Test HTTPS/h2 with curl

In a second terminal, first verify curl supports HTTP/2:

```bash
curl -V
```

curl/libcurl output must include the **`HTTP2`** feature (or equivalent build info). Not every curl build includes HTTP/2, especially on older Windows systems or minimal custom builds. If missing, `--http2` will error **before** even testing the server; use a curl build compiled with HTTP/2 support or an equivalent test tool.

Test `h2` over TLS:

```bash
curl -sk --http2 -o /dev/null -w 'http_version=%{http_version}\n' https://localhost:8443/hello
```

When `h2` negotiation succeeds, the key output is:

```text
http_version=2
```

**`-k`/`--insecure` is solely to bypass self-signed certificate verification in this demo. Never use `-k` in production security checks.** Against production sites with a trusted CA, omit `-k`.

If the output is `http_version=1.1`, the HTTP status may still be 200, but **ALPN did not pick `h2`** or client/server fell back to HTTP/1.1. Seeing `server.http2.enabled=true` in config is not enough to sign off on QA.

Command with detailed handshake trace:

```bash
curl -vk --http2 https://localhost:8443/protocol
```

Look for signals such as:

```text
ALPN: server accepted h2
using HTTP/2
```

Exact log formatting varies by curl version. The response body will look like:

```text
servletProtocol=HTTP/2.0
scheme=https
secure=true
```

This is a **common output example on embedded Tomcat**; exact protocol strings can vary across servlet servers/adapters, so treat curl's `http_version=2` as the direct evidence of the HTTP wire version.

Test a client intentionally requesting HTTP/1.1 on the same listener:

```bash
curl -sk --http1.1 -o /dev/null -w 'http_version=%{http_version}\n' https://localhost:8443/hello
```

Expected:

```text
http_version=1.1
```

Supporting both HTTP/2 and HTTP/1.1 on the server **is not an error**. `server.http2.enabled=true` allows HTTP/2 without forcing every client onto `h2`.

### 7.8. Test Non-TLS h2c

Stop the TLS app, then run the `h2c` profile:

```bash
java -jar target/http2-demo-1.0.0.jar --spring.profiles.active=h2c
```

No password/keystore is needed for this profile. Connecting to `http://localhost:8081` is **non-TLS HTTP**:

```bash
curl -s --http2-prior-knowledge -o /dev/null -w 'http_version=%{http_version}\n' http://localhost:8081/hello
```

With Tomcat 10.1.x and curl supporting HTTP/2 prior knowledge, expected output is:

```text
http_version=2
```

Tomcat 10.1 supports `h2c` via both HTTP/1.1 Upgrade and **direct HTTP/2 prior knowledge**. Another test:

```bash
curl -v --http2 http://localhost:8081/protocol
```

For `http://` URLs, `curl --http2` typically attempts an upgrade using HTTP/1.1 `Upgrade: h2c`. By contrast, `--http2-prior-knowledge` sends HTTP/2 directly; these are **two different mechanisms**. Proxies/firewalls may allow one and block the other.

If a normal curl request runs over HTTP/1.1:

```bash
curl -s --http1.1 -o /dev/null -w 'http_version=%{http_version}\n' http://localhost:8081/hello
```

Getting `http_version=1.1` is normal. Mainstream browsers do not automatically switch plain HTTP to `h2c`, so do not open `http://localhost:8081` in a browser and conclude the server lacks HTTP/2 support.

**Security:** never expose a public `h2c` port on the Internet as a substitute for HTTPS. If using upstream `h2c`, secure the network segment and access controls.

## 8. Quick Checks Before and After Enabling HTTP/2

### 8.1. Three Distinct Types of Checks

| Question | Tool | Proper evidence |
| --- | --- | --- |
| Is the app **configured** for HTTP/2? | Inspect `server.http2.enabled`, active profile, startup logs | Support is enabled |
| Does TLS **negotiate ALPN `h2`**? | `openssl s_client -alpn h2,http/1.1`; `curl -v` | `ALPN protocol: h2` |
| Do requests **actually run HTTP/2**? | `curl -w '%{http_version}'`, browser DevTools Protocol | `2`/`h2` on the measured hop |

Do not swap these criteria. An app starting cleanly does not prove HTTP/2; a valid certificate does not prove ALPN picked `h2`; a browser speaking `h2` to a CDN does not prove the upstream connection to Spring Boot uses `h2`.

### 8.2. Production h2 Verification Workflow

1. Identify the **URL and hop** under test: browser↔edge or edge↔Spring Boot.
2. Confirm server type, dependency versions, and suitable JDK runtime.
3. Confirm the TLS certificate chain and hostname are valid on the public endpoint.
4. Use HTTP/2-capable curl against the real URL, **without `-k`** in production.
5. Observe ALPN and `http_version=2`.
6. Test `--http1.1` to verify fallback if older clients still rely on it.
7. Test concurrent requests, large bodies, and streaming if the app uses those capabilities.
8. Record protocol versions in proxy logs/metrics **at the exact hop**, not just in the application.
9. If the backend must run `h2c`, test directly against the **backend listener** from a trusted network.
10. Post-deploy, monitor error rates, TLS handshake failures, HTTP/2 stream resets, p95/p99 latency, and proxy upstream errors.

### 8.3. Checking in a Browser

In Chrome/Edge/Firefox, open DevTools → Network and enable the **Protocol** column (how you toggle columns varies by browser version). Over HTTPS, requests may display `h2`, `http/1.1`, or `h3`. That value reflects **the connection between the browser and the endpoint it connects to**—usually a proxy/CDN, not automatically embedded Spring Boot.

With service workers, browser caching, or prefetching, some requests may not correspond to a fresh network hop. To verify protocol negotiation reliably, test with `curl` and inspect gateway access logs simultaneously.

### 8.4. The `nghttp` Tool

`nghttp` (from the nghttp2 suite) can display detailed HTTP/2 frames and settings:

```bash
nghttp -nv https://localhost:8443/hello
```

With self-signed certificates, `nghttp` may require trust configuration or version-specific test flags. Do not assume `nghttp` is installed on every machine; it is an **optional tool** for debugging streams/frames, not needed to run the demo.

## 9. Spring Boot SSL Bundles: Cleaner Production Config

Spring Boot supports **SSL bundles**, grouping keystore/truststore or PEM key/cert material into a named configuration. The server then picks the bundle via `server.ssl.bundle`. Example **fragment** for a server with a PKCS#12 keystore (do not combine with `server.ssl.key-store` from the earlier example):

```properties
spring.ssl.bundle.jks.web.keystore.location=file:/etc/example/tls/web.p12
spring.ssl.bundle.jks.web.keystore.password=${WEB_KEYSTORE_PASSWORD}
spring.ssl.bundle.jks.web.keystore.type=PKCS12
spring.ssl.bundle.jks.web.key.alias=web

server.port=8443
server.http2.enabled=true
server.ssl.bundle=web
```

This fragment assumes `/etc/example/tls/web.p12` is provisioned by deployment tooling and readable by the app. It is not pre-created in the demo project.

**Do not mix** `server.ssl.bundle` with discrete `server.ssl.key-store`, `server.ssl.certificate`, and private key options under `server.ssl.*`. When using a bundle, certain cipher/protocol settings come from the bundle's `options`; consult docs for your exact Spring Boot version instead of duplicating properties and guessing which wins.

For PEM certificates/keys, Spring Boot also supports `spring.ssl.bundle.pem.*`, convenient for secret mounts and reload-capable setups. However, **configuring an SSL bundle alone does not enable HTTP/2**; you still need `server.http2.enabled=true` and ALPN verification.

## 10. Performance Limits and Operational Risks

### 10.1. HTTP/2 Multiplexing Does Not Mean Unlimited Requests

One HTTP/2 connection carries many streams, yet the server still enforces limits on **max concurrent streams, connection counts, request header sizes, body sizes, timeouts, and flow control**. Browsers/clients also enforce limits. If a database pool only has 10 connections, HTTP/2 cannot magically create 1,000 useful DB connections.

HTTP/2 can increase the concurrency arriving over a single connection. Review:

- Servlet thread pools, reactive event loops, async task executors;
- database connection pools / HTTP client pools;
- body sizes and backpressure/streaming;
- timeouts, cancellation, disconnects, and stream resets;
- CPU load from TLS/HPACK/frame processing;
- concurrency limits, max streams, and header limits on your specific web server.

Do not blindly raise `maxConcurrentStreams` to "take advantage of HTTP/2" without benchmarking first.

### 10.2. Apples-to-Apples Comparisons

When benchmarking HTTP/1.1 vs. HTTP/2:

1. Use identical hardware, JVM, JVM flags, and workload.
2. Control JIT warm-up and connection reuse.
3. Use TLS for both for a fair HTTPS endpoint comparison.
4. Measure p50/p95/p99, RPS, CPU, memory, network, TLS handshakes, and errors.
5. Verify the client/load generator **actually uses HTTP/2**. An unverified flag can invalidate the benchmark.
6. Test both many parallel resources/requests and single JSON payloads to observe where gains differ.
7. Measure frontend↔proxy and proxy↔backend separately if a gateway is present.

### 10.3. Response vs. Header Compression

`server.compression.enabled=true` compresses response bodies for eligible MIME types and sizes, **independently** of HTTP/2. For JPEG/PNG images or already-compressed data, extra gzip rarely helps. HTTP/2 HPACK compresses headers, not JSON response bodies.

```properties
server.http2.enabled=true
server.compression.enabled=true
```

This is an **optional add-on snippet**; verify `Content-Encoding` and `Vary: Accept-Encoding` behavior and benchmark CPU/latency before and after. Do not blindly enable compression on secrets alongside attacker-controlled input if your threat model covers compression length side-channel attacks.

### 10.4. Protocol Security

HTTP/2 has faced resource-exhaustion attacks such as frame floods/resets (e.g., "Rapid Reset"). Practical mitigations include:

- Keep embedded servers/proxies updated to maintained patch versions.
- Enable rate limiting, connection/stream caps, and proper timeouts at gateways/servers.
- Monitor HTTP/2 resets, frame errors, and spikes in request volume.
- Enforce strong certificates, TLS cipher policies, and ALPN; never expose non-TLS `h2c` to the public network.
- Do not treat HTTP/2 as DDoS protection or a replacement for WAFs/authorization.

## 11. Common Pitfalls When Enabling HTTP/2

| Symptom | Possible cause | Check / fix |
| --- | --- | --- |
| `server.http2.enabled=true` set yet curl still shows `1.1` | Client lacks HTTP2; ALPN fallback; proxy downgrade | `curl -V`, `curl -v`, `openssl -alpn`, check the exact hop |
| `curl --http2` prints "not supported" | curl built without HTTP2/nghttp2 | Use a curl build with HTTP2 feature or `nghttp` |
| HTTPS fails with `SSLHandshakeException` | Invalid cert/key/ciphers/TLS config | Verify keystore alias/password, handshake, and certificate |
| Browser warns certificate untrusted | Self-signed or missing CA chain | Local test trusts intentionally; production uses a trusted CA |
| `server.ssl.key-store` file not found | Different working directory, wrong `file:` path | Check file location, read permissions, and JAR/container launch dir |
| Spring starts on HTTP port 8080 instead of HTTPS 8443 | Wrong active profile or config not loaded | Check `--spring.profiles.active=tls`, startup logs, and actual listener |
| Curl hits 8443 with `http://` and fails | Wrong scheme for TLS listener | Use `https://localhost:8443` |
| HTTPS returns HTTP 200 but not `h2` | Server negotiated HTTP/1.1 | Print `http_version` and ALPN; HTTP 200 is not enough |
| Boot 3.5 uses Jetty yet lacks `h2` | Missing HTTP/2/ALPN modules | Add Jetty dependencies matching the Boot version |
| Browser test of `h2c` always shows HTTP/1.1 | Browsers do not use `h2c` arbitrarily | Test with `curl --http2-prior-knowledge` or upgrade test |
| `--http2-prior-knowledge` on HTTPS fails in newer curl | ALPN `h2`-only, server lacks `h2` | Check ALPN; use `--http2` and inspect negotiated protocol |
| Gateway reports `h2`, Spring backend sees HTTP/1.1 | Proxy TLS termination / upstream protocol downgrade | Check upstream protocol config and logs at the right hop |
| HTTP/2 enabled yet app remains slow | Blocking DB/service calls / CPU bottleneck / other load | Profile backend bottlenecks instead of blaming protocol only |
| Browser reports `ERR_HTTP2_PROTOCOL_ERROR` | Frame/header/proxy/server-version/TLS/compression bug | Inspect gateway/server logs, reproduce with curl verbose, apply patches |
| HTTP/2 breaks when proxied through ingress | Ingress lacks support or upstream `h2`/`h2c` mismatch | Check route/backend protocol annotations and test directly |
| Multiple instances behave inconsistently | Inconsistent configs/profiles/server versions | Audit deployment and probe each instance |
| Set `server.forward-headers-strategy` expecting HTTP/2 | Forwarded headers do not control ALPN | Enable HTTP2 on the right listener; verify `http_version` |

### Repeatable Troubleshooting Sequence

1. **Identify endpoint and hop.** Testing the app directly or a public proxy?
2. **Confirm runtime.** Spring Boot version, Java version, and actual server; do not guess from classpath dependencies.
3. **Confirm config.** `server.http2.enabled=true` in the active profile; TLS/keystore when testing `h2`.
4. **Confirm client.** `curl -V` includes `HTTP2`.
5. **Confirm TLS.** `openssl s_client -alpn h2,http/1.1`, certificate trust, and hostname.
6. **Confirm request.** `curl --http2 -w '%{http_version}'`. If HTTP/1.1, inspect handshake logs.
7. **If testing `h2c`**, try direct prior-knowledge and HTTP/1.1 Upgrade; do not rely solely on a browser.
8. **If behind a proxy**, check outside/client-facing and inside/backend-facing hops separately.
9. **Once `h2` works**, test 1.1 fallback, concurrency, streaming, error rates, and measure real performance.
10. Reach for server-specific APIs only after standard config and dependencies are verified.

## 12. HTTP/2 and Application Compatibility

### 12.1. Do Controllers and REST APIs Need Changes?

Usually **no**. A Spring MVC handler:

```java
@GetMapping("/orders/{id}")
public OrderDto findOrder(@PathVariable long id) {
    return orderService.findById(id);
}
```

This is an **illustrative snippet**, not a standalone class: `OrderDto` and `orderService` are application components. HTTP requests carry the same method/path/headers/body semantics. Transport and controller mapping are handled by the server and Spring.

### 12.2. What Still Needs Testing

- Filters, reverse proxies, and security middleware handle headers/cookies accurately.
- Long polling, SSE, streaming, and WebSocket upgrades have distinct requirements; do not assume HTTP/2 replaces every legacy upgrade pattern.
- Client/server properly handle content-length, trailers, header normalization, and request buffering.
- HTTP/2 header field names are lowercase on the wire; apps **must not rely on HTTP header name casing**.
- HTTP/1.1 connection-specific headers (`Connection`, `Keep-Alive`, `Upgrade`) must not be forwarded verbatim into HTTP/2 frames; let the HTTP stack handle translation.
- gRPC often runs over HTTP/2; if routing gRPC through a gateway, confirm the proxy preserves HTTP/2 upstream.

### 12.3. When Benchmarks Do Not Improve

HTTP/2 shines with many concurrent requests, yet it cannot fix long blocking controllers, undersized connection pools, GC pauses, or misconfigured HTTP/2 frames/flow control. Adding a reverse proxy/gateway also introduces overhead, so benchmark against your real architecture.

**Do not force HTTP/2 by arbitrarily dropping HTTP/1.1** while older clients still depend on it. If HTTP/2 is mandatory by contract/gRPC, document client requirements, transport paths, and failure tests when `h2` is absent.

## 13. Self-Assessment Questions

1. **Does setting `server.http2.enabled=true` guarantee browsers use HTTP/2?** No. Verify ALPN/client/proxy and actual request protocols.
2. **Core difference between `h2` and `h2c`?** `h2` uses TLS/ALPN; `h2c` is HTTP/2 over cleartext TCP without TLS.
3. **Does Spring Boot 3.5 support `h2c`?** Yes. Boot 3.5 docs state `h2c` is used when SSL is disabled, subject to server support.
4. **Does JDK 17 need the old ALPN boot patch for Tomcat `h2`?** No. ALPN is built into modern Java; still verify TLS negotiation.
5. **Does `curl --http2` returning HTTP 200 prove `h2` was used?** No; curl may have negotiated HTTP/1.1 fallback. Check `%{http_version}`.
6. **Does HTTP/2 between browser ↔ CDN prove the Spring Boot backend uses `h2`?** No; the proxy may connect to the backend over HTTP/1.1.
7. **Does Jetty need an extra HTTP/2 module in Spring Boot 3.5?** Yes per Boot guides; `h2` TLS also requires a corresponding ALPN provider.
8. **Does Reactor Netty support `h2c`?** Yes in the Boot 3.5 stack per docs, given matching server/runtime configuration.
9. **Is TLS 1.3 the only protocol capable of running `h2`?** No; compliant TLS 1.2 can also be used.
10. **Does HTTP/2 automatically compress JSON bodies?** No. HTTP/2 compresses headers with HPACK; body compression is configured separately.
11. **When using a reverse proxy for TLS termination, must SSL be enabled on the backend?** Not necessarily, depending on architecture. Still protect the proxy↔backend segment per your threat model.
12. **Why is `h2c` unsuitable for the public Internet?** It lacks TLS transport encryption and authentication; reserve it for trusted networks when truly needed.
13. **Why test HTTP/1.1 fallback?** Many clients still use 1.1; enabling `h2` does not automatically drop 1.1.
14. **Do you need to write new controllers for HTTP/2 to work?** No. HTTP/2 is negotiated by the server/connector; controllers handle standard HTTP semantics.
15. **If `servletProtocol=HTTP/1.1` appears on the backend while DevTools shows `h2`, is that definitely a bug?** No. It may be an intentional edge `h2` → backend `h1` setup.

## 14. Production Deployment Checklist

- [ ] Confirmed exact Boot version, JDK, and embedded server at runtime.
- [ ] Identified which hops require HTTP/2: client↔edge, edge↔backend, or direct to Spring Boot.
- [ ] Enabled `server.http2.enabled=true` in the active profile/config source.
- [ ] For `h2`, configured TLS certificates with accurate SAN/chain, appropriate TLS/ciphers, and ALPN.
- [ ] Private keys not packaged/committed; using appropriate SSL bundles/secrets.
- [ ] If using Jetty, added matching HTTP/2 server + ALPN modules for the version.
- [ ] If using `h2c`, restricted to protected network segments and tested directly.
- [ ] Verified `curl -V` includes `HTTP2`; never treat a curl build lacking support as a broken server.
- [ ] Observed ALPN and `curl -w '%{http_version}'` on the measured URL/hop.
- [ ] Verified HTTP/1.1 fallback if older clients exist.
- [ ] Tested controllers/filters/security, streaming, body sizes, and proxy compatibility.
- [ ] Measured p95/p99 latency, throughput, stream resets, and TLS/CPU load; never extrapolate from one request.
- [ ] Updated server/proxy patches to mitigate HTTP/2 flood/DoS risks.
- [ ] Checked separate gateway and backend logs/metrics when TLS termination differs.
- [ ] Planned certificate renewal, health checks, and rollback if handshakes fail after deploy.
- [ ] Reviewed context root, forwarded headers, and SNI when hosting multiple virtual hosts/certificates.

## 15. Official Documentation

- Spring Boot 3.5 — [Embedded Web Servers: Configure HTTP/2](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html) — core reference for `server.http2.enabled`, `h2`/`h2c`, and the Tomcat/Jetty/Reactor Netty/Undertow matrix.
- Spring Boot — [SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html) — JKS/PKCS12, PEM, managing trust/key material.
- Spring Boot 3.5 — [Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html) — `server.http2.*` and `server.ssl.*` properties.
- Apache Tomcat 10.1 — [HTTP Connector / HTTP/2 support](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html) — `h2` TLS, `h2c` Upgrade, and prior knowledge.
- Apache Tomcat 10.1 — [HTTP/2 Upgrade Protocol](https://tomcat.apache.org/tomcat-10.1-doc/config/http2.html) — specific limits and settings.
- curl — [HTTP/2 command-line options](https://curl.se/docs/manpage.html) — `--http2`, `--http2-prior-knowledge`, and HTTP2 build requirements.
- Everything curl — [HTTP/2 support](https://everything.curl.dev/http/versions/http2.html) — distinguishing TLS negotiation from HTTP Upgrade.
- IETF — [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113) — framing, `h2`/`h2c`, ALPN, connection preface.
- IETF — [RFC 7301: TLS Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301) — ALPN negotiation.

**Summary:** In Spring Boot 3.5, enabling HTTP/2 starts with `server.http2.enabled=true`, where **`h2` requires TLS + ALPN**, while **`h2c` is for non-TLS TCP**. With Java 17 and embedded Tomcat, both `h2` and `h2c` can run using the sample configuration without mandatory native libraries. Always **measure the exact negotiated protocol** with curl/OpenSSL at the **right hop**, verify server dependencies, protect TLS/private keys, and evaluate performance under realistic load before declaring the deployment complete.