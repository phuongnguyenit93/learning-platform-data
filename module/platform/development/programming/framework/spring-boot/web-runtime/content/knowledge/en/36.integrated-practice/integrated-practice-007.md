# Deploying HTTPS with an SSL Bundle and Verifying HTTP/2

## 1. Objectives and Completion Criteria

This is an **Integrated Practice** lesson in the **Spring Boot - web-runtime** module. The goal is to run **Spring Boot 3.3.13, Java 17, embedded Tomcat 10.1** over HTTPS using a **named SSL bundle**, and then verify that requests actually use **HTTP/2 (h2) over TLS**.

Two very common—but false—assumptions:
- **`server.http2.enabled=true`** does not guarantee every client or reverse proxy is using HTTP/2. It only enables the capability on the server. Actual negotiation depends on TLS, ALPN, the client, and the request path.
- A client successfully calling an HTTPS URL does not prove Spring Boot is terminating TLS. An Ingress or Load Balancer might terminate HTTPS and forward cleartext HTTP/1.1 to Tomcat.

This lesson requires three independent layers of evidence:
1. **Valid TLS identity**: certificate chain verified by a trusted CA, SAN matches the hostname, and the certificate is within its validity dates. Never use trust-all or `curl -k` to make tests pass.
2. **Valid protocol**: ALPN actually selects **h2** and the client receives **HTTP/2**, not merely checking a configuration flag.
3. **Valid endpoint behavior**: endpoint returns HTTP 200 and the expected body, Spring Boot/Pod are ready, TLS keys are mounted outside the JAR, and rotation/failure scenarios are tested.

You will practice generating a localhost CA and certificate, configuring **spring.ssl.bundle.pem**, running curl/OpenSSL/Java `HttpClient`, writing a real-port integration test, building a Docker image without baking private keys, deploying to Kubernetes with a TLS Secret, and diagnosing HTTP/1.1 fallback.

**Scope:** Spring Boot 3.3.13, Spring MVC (Servlet), Tomcat 10.1, Java 17+. Certificates created in this guide are **strictly for localhost or authorized lab environments**. Production must follow your organization's PKI/CA and security policies.

## 2. Where Do HTTPS, TLS, ALPN, and HTTP/2 Differ?

~~~text
Client
   |
   | TCP connect to localhost:8443
   v
TLS handshake
   |-- Verify CA chain, expiry, SAN/hostname
   |-- Negotiate TLS version and cipher
   |-- ALPN: client offers h2, http/1.1
   |-- Server selects h2 if both support it
   v
HTTP/2 framing: streams, headers, flow control
   |
   v
Embedded Tomcat HTTP/2 support (Java 17)
   |
   v
DispatcherServlet / Controller
   |
   v
HTTP 200 + body secure-ok
~~~

**TLS** encrypts and authenticates a connection between TLS peers; **HTTP/2** is the application protocol carried over that connection. HTTP/2 uses binary frames, stream multiplexing over a single TCP connection, HPACK, and stream flow control. "Enabling HTTP/2" does not automatically enable TLS.

| Protocol | TLS on That Hop? | Example |
| --- | --- | --- |
| **HTTP/1.1** | May (HTTPS) or may not have TLS | An HTTPS client that does not negotiate h2 |
| **h2** | Yes; HTTP/2 over TLS | Client/embedded Tomcat using ALPN `h2` |
| **h2c** | No; cleartext HTTP/2 | Internal hop behind a proxy if network-protected |

Per **Spring Boot 3.3**, **`server.http2.enabled=true`** supports both h2 and h2c on compatible web servers. When server SSL is enabled, HTTP/2 runs `h2` over TLS; when SSL is disabled, `h2c` may be used. Java 17 provides JSSE ALPN support; Tomcat 10.1 supports h2 **without requiring `tomcat-native`** in this lab.

### 2.1. HTTPS and HTTP/2 Do Not Require TLS 1.3

HTTP/2 over TLS can run over either TLS 1.2 or TLS 1.3 with policy-compliant ciphers and protocols. Claiming "HTTP/2 requires TLS 1.3" is false. Java 17 typically enables TLS 1.3, yet ALPN negotiation and certificate verification still must be observed.

### 2.2. Enabling h2 Does Not Solve Every Bottleneck

HTTP/2 cuts per-request connection overhead and multiplexes streams, yet blocking JDBC, Tomcat threads, database pools, request timeouts, TCP congestion, header limits, and memory remain finite. One HTTP/2 connection can carry many streams; **connection count does not equal concurrent request count**.

## 3. Topology: Identify Exactly Where TLS Terminates

~~~text
A. Direct HTTPS
Client -- h2/TLS --> Tomcat HTTPS 8443
                     (server.ssl.bundle=web)

B. HTTPS at Ingress
Client -- h2/TLS --> Ingress -- HTTP/1.1 --> Tomcat HTTP 8080

C. TLS re-encryption
Client -- h2/TLS --> Ingress -- TLS/h2 or TLS/h1 --> Tomcat HTTPS

D. TLS passthrough
Client -- TLS/h2 --> TCP Load Balancer --> Tomcat HTTPS
                     (LB does not decrypt TLS)
~~~

This lesson **practices topology A**, so curl/Java results directly reflect TLS and HTTP/2 at embedded Tomcat. In B, a browser seeing HTTP/2 on the public domain **does not prove backend Tomcat runs h2**. In C, there are **two separate TLS handshakes**, each negotiating ALPN independently. In D, TLS terminates at Tomcat even across a TCP load balancer.

When reporting a test run, always record:
- Exact URL and endpoint address called.
- Whether TLS terminates at a proxy or at the application.
- Which CA/certificate verified which hop.
- Which TLS peer selected ALPN.
- Request protocol at both client-facing and backend-facing hops.

Never treat **`X-Forwarded-Proto: https`** as proof that the backend hop is encrypted. That header only reports proxy-forwarded metadata when coming from a trusted proxy; attackers can forge it if ingress fails to sanitize headers.

## 4. SSL Bundles: PEM, JKS/PKCS12, Names, and Scope

Spring Boot 3.3 supports **named SSL bundles**. A bundle holds key material, trust material, and TLS options:
- **`spring.ssl.bundle.pem.<name>`**: PEM certificates, private key, and trust certificates.
- **`spring.ssl.bundle.jks.<name>`**: JKS or PKCS12 keystores and truststores.
- **`server.ssl.bundle: <name>`**: binds the named bundle to the embedded web server.
- **`SslBundles`**: bean API allowing consumers/integrations to look up named bundles.
- **`spring.ssl.bundle.<type>.<name>.options`**: bundle-level TLS options.

Example PEM bundle named **web**:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        web:
          keystore:
            certificate: "file:./tls/server.crt"
            private-key: "file:./tls/server-pkcs8.key"

server:
  port: 8443
  ssl:
    bundle: web
~~~

This supplies the certificate and private key the **server presents as its identity**. Clients must **trust the CA that signed the server cert** (or an appropriate trust anchor) to complete verification. A **server-side truststore** does not replace the server's private key; it is used when the server verifies peer certificates, e.g., in mTLS.

### 4.1. Do Not Mix Bundles with Discrete server.ssl.* Properties

When using **`server.ssl.bundle`**, do not simultaneously declare discrete **`server.ssl.key-store`**, **`server.ssl.certificate`**, or **`server.ssl.certificate-private-key`** pointing to a second source of key material. Per Boot 3.3 docs, **`server.ssl.ciphers`**, **`server.ssl.enabled-protocols`**, and **`server.ssl.protocol`** are ignored when a bundle is configured; place TLS options under **`spring.ssl.bundle...options`** instead.

Keep bundle names consistent across environments: **`server.ssl.bundle: web`** must match **`spring.ssl.bundle.pem.web`** or the configured JKS branch. Boot docs note that bundle names passed via environment variables are normalized to **lowercase**.

### 4.2. PEM, Keystore, and Certificate Chain

Three main files for the lab:
- **`tls/ca.crt`**: test CA certificate; used by **clients** as the trust anchor.
- **`tls/server.crt`**: leaf certificate with SANs `localhost` and `127.0.0.1`; presented by the **server**.
- **`tls/server-pkcs8.key`**: server private key in PKCS#8 format; kept secret by the **server**.

**`tls/ca.key`** is the CA private key used to sign certificates. It **must never be mounted into Spring Boot**. With public PKIs, servers normally present the full ordered intermediate chain while clients hold the root trust store.

## 5. Generating a Valid Local CA and Localhost Certificate

Run on Linux/macOS/WSL with OpenSSL. Generate files before running Maven tests; run all commands from the **root of `https-h2-lab`**.

### 5.1. Local CA (Lab Use Only)

~~~bash
mkdir -p tls

openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 10 \
  -keyout tls/ca.key -out tls/ca.crt \
  -subj "/CN=Local HTTPS H2 Demo CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
~~~

An **unencrypted** private key is used purely for lab convenience; production must manage CA and server keys under PKI/secret-management policies. This demo CA is not a public CA and should not be installed system-wide.

### 5.2. Generating the Server Key and CSR

~~~bash
openssl req -newkey rsa:3072 -nodes -sha256 \
  -keyout tls/server.key \
  -out tls/server.csr \
  -subj "/CN=localhost"
~~~

CN alone is insufficient for modern hostname verification. You must add **SAN** entries so clients can match hostname/IP.

### 5.3. Declaring SANs and Key Usage

~~~bash
cat > tls/server.ext <<'EOF'
subjectAltName=DNS:localhost,IP:127.0.0.1
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF
~~~

Explanation:
- **`DNS:localhost`**: matches `https://localhost:8443`.
- **`IP:127.0.0.1`**: matches `https://127.0.0.1:8443`.
- **`CA:FALSE`**: leaf certificate cannot act as a CA.
- **`serverAuth`**: certificate is valid for server authentication.

Never reuse a certificate with SAN `localhost` to serve `api.example.com`; TLS hostname validation must fail for hosts outside the SAN.

### 5.4. Signing and Converting the Private Key to PKCS#8

~~~bash
openssl x509 -req -in tls/server.csr \
  -CA tls/ca.crt -CAkey tls/ca.key -CAcreateserial \
  -out tls/server.crt -days 7 -sha256 \
  -extfile tls/server.ext

openssl pkcs8 -topk8 -nocrypt \
  -in tls/server.key \
  -out tls/server-pkcs8.key

chmod 600 tls/ca.key tls/server.key tls/server-pkcs8.key
~~~

PKCS#8 PEM keys start with **BEGIN PRIVATE KEY**. If OpenSSL initially outputs PKCS#1 **BEGIN RSA PRIVATE KEY**, converting to PKCS#8 avoids key-parsing quirks across library versions.

### 5.5. Proving the Certificate Is Valid Before Starting the JVM

~~~bash
openssl verify -CAfile tls/ca.crt \
  -verify_hostname localhost tls/server.crt

openssl x509 -in tls/server.crt -noout \
  -subject -issuer -dates -ext subjectAltName

openssl pkey -in tls/server-pkcs8.key -noout -check
~~~

With a validly generated certificate, **`openssl verify`** ends with **OK**, and SAN lists `DNS:localhost` and `IP:127.0.0.1`. `notBefore`, `notAfter`, serial, and fingerprint vary per generation; never treat dynamic output as a fixed snapshot.

Create **`.gitignore`**:

~~~gitignore
tls/*.key
tls/*.p12
tls/*.srl
tls/*.csr
target/
~~~

Even though public certificates are not private keys, do not reuse demo material in real environments. Never commit **`tls/ca.key`**, **`tls/server.key`**, or **`tls/server-pkcs8.key`**.

## 6. Maven Project and Directory Structure

~~~text
https-h2-lab/
├── pom.xml
├── Dockerfile
├── k8s.yaml
├── Http2Proof.java
├── tls/
│   ├── ca.crt
│   ├── ca.key
│   ├── server.crt
│   ├── server.key
│   ├── server-pkcs8.key
│   └── server.ext
└── src/
    ├── main/
    │   ├── java/com/example/httpsdemo/HttpsDemoApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/httpsdemo/HttpsHttp2Test.java
~~~

Certificates and keys stay out of **`src/main/resources`**; keeping them on the external filesystem allows key rotation without rebuilding the JAR. Never bake SSL secrets into source packages.

Create **`pom.xml`**:

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
    <artifactId>https-h2-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

**`spring-boot-starter-web`** runs Spring MVC + embedded Tomcat 10.1 in Boot 3.3. Java 17 supports ALPN out of the box. **`spring-boot-starter-actuator`** exposes health probes for deployment; **`spring-boot-starter-test`** brings JUnit Jupiter and Spring Boot integration tests. This lab requires no Tomcat Native, Netty, or Jetty HTTP/2 modules.

## 7. application.yml: Bundle web, Port 8443, HTTP/2 Enabled

Create **`src/main/resources/application.yml`**:

~~~yaml
server:
  port: 8443
  ssl:
    bundle: web
  http2:
    enabled: true
  shutdown: graceful

spring:
  ssl:
    bundle:
      pem:
        web:
          keystore:
            certificate: "${TLS_CERT_LOCATION:file:./tls/server.crt}"
            private-key: "${TLS_KEY_LOCATION:file:./tls/server-pkcs8.key}"
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
  endpoints:
    web:
      exposure:
        include: health
~~~

**Property breakdown:**
- **`server.port=8443`:** Tomcat listens for TLS HTTPS on port 8443.
- **`server.ssl.bundle=web`:** selects the PEM bundle defined at `spring.ssl.bundle.pem.web`.
- **`server.http2.enabled=true`:** enables `h2` negotiation over TLS.
- **`certificate`/`private-key`:** reads from **`TLS_CERT_LOCATION`/`TLS_KEY_LOCATION`** env vars when set, otherwise **`file:./tls/server.crt`** and **`file:./tls/server-pkcs8.key`** at lab root.
- **`server.shutdown=graceful`:** lets in-flight HTTP requests drain on shutdown; does not directly control h2.
- **`probes.enabled` / `add-additional-paths`:** exposes **`/readyz`** and **`/livez`** on **the app's main HTTPS port**.
- **`management.endpoints...include=health`:** avoids exposing Actuator `env`, `heapdump`, `shutdown`, or `beans`.

If a profile or CLI override specifies an invalid `server.ssl.bundle`, the app should fail TLS startup rather than silently falling back to HTTP. Inspect effective properties through secure internal workflows—**never expose `/actuator/env` publicly** to debug secrets.

### 7.1. Use file: Rather Than classpath:

**`classpath:`** suits static resources packaged in the JAR, which risks baking private keys into build artifacts. **`file:`** points outside the image/JAR, fitting Docker bind mounts, Kubernetes Secrets, and certificate rotation. When running from a different working directory, pass absolute URIs like **`file:/etc/tls/tls.crt`**.

### 7.2. HTTPS Does Not Automatically Open HTTP 8080

Configuring SSL on port 8443 does not open plain HTTP 8080 or add a redirect. Supporting both HTTP and HTTPS inside one Boot instance requires registering an additional connector in Java; production typically handles HTTP→HTTPS redirects at a trusted Ingress or LB. Never send cleartext HTTP to 8443 expecting a 301.

## 8. Runnable Java 17 Spring MVC Controller

File **`src/main/java/com/example/httpsdemo/HttpsDemoApplication.java`**:

~~~java
package com.example.httpsdemo;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpsDemoApplication.class, args);
    }
}

@RestController
class TransportController {

    @GetMapping(
        path = "/api/hello",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String hello() {
        return "secure-ok";
    }

    @GetMapping("/api/transport")
    Map<String, Object> transport(HttpServletRequest request) {
        return Map.of(
            "scheme", request.getScheme(),
            "secure", request.isSecure(),
            "protocol", request.getProtocol(),
            "serverPort", request.getServerPort()
        );
    }
}
~~~

**`/api/hello`** returns exact plain text **`secure-ok`** (no trailing newline). **`/api/transport`** exposes Tomcat's view of the HTTP request:
- **`scheme`** is typically **`https`** when the client connects via TLS directly to Tomcat.
- **`secure`** is typically **`true`**.
- **`protocol`** typically shows **`HTTP/2.0`** when Tomcat serves over h2, or **`HTTP/1.1`** if the client falls back.
- **`serverPort`** is 8443 when no reverse proxy/forwarded headers rewrite scheme or port.

Never treat `Servlet` `request.getProtocol` as proof of certificate trust: a client could connect with verification disabled. Likewise, behind a TLS-terminating proxy, these fields reflect only the **backend hop** and trusted forwarded headers.

## 9. Local Maven/JAR Build and Basic HTTPS Checks

After creating the PEM files in section 5:

~~~bash
mvn test
mvn package
java -jar target/https-h2-lab-1.0.0.jar
~~~

The test suite starts real HTTPS Tomcat on a random port; **the cert/key files must exist before running `mvn test`**. Startup failure when certs/keys are missing or invalid is the intended safety signal—never disable SSL to make tests pass.

In a second terminal:

~~~bash
curl -v --cacert tls/ca.crt \
  https://localhost:8443/api/hello

curl -sS --cacert tls/ca.crt \
  https://localhost:8443/api/transport
~~~

With valid TLS, `/api/hello` returns **HTTP 200**, body **`secure-ok`**. `/api/transport` returns JSON; key order may vary. Passing `--cacert` makes curl trust the test CA **only for this connection**, while still enforcing SAN hostname verification.

### 9.1. Why Never Use curl -k?

~~~bash
# DO NOT use as proof of valid identity:
curl -k https://localhost:8443/api/hello
~~~

**`-k`/`--insecure`** disables certificate chain and hostname checks. A request can still return h2/200 under an active MITM or invalid cert. Use **`--cacert tls/ca.crt`**, a properly managed OS/browser trust store, or your organization's CA.

### 9.2. Comparing TLS HTTP/1.1

~~~bash
curl -i --http1.1 --cacert tls/ca.crt \
  https://localhost:8443/api/hello
~~~

In the default lab, HTTP/1.1 over TLS also returns **200 `secure-ok`**. This is an important control check: HTTPS 200 **does not prove** HTTP/2.

## 10. Proving h2 with curl Rather Than Trusting Flags

Check whether your curl build supports HTTP/2:

~~~bash
curl -V
~~~

If the build lacks the **HTTP2** feature, **`curl --http2`** may fail as unsupported. Use the Java `HttpClient` proof in section 12 instead. Never blame the server just because a client binary lacks h2 support.

With curl:

~~~bash
curl --http2 -v --cacert tls/ca.crt \
  https://localhost:8443/api/hello
~~~

In the verbose TLS output, look for:
1. Client ALPN offering **h2** and http/1.1.
2. Server ALPN accepting **h2**.
3. Response protocol **`HTTP/2`** with status 200.
4. Successful certificate chain and hostname verification.

Exact log lines vary across curl/OpenSSL/Schannel versions, so avoid snapshotting `-v` output verbatim.

**Concise check with write-out:**

~~~bash
curl -sS --http2 --cacert tls/ca.crt \
  -o /dev/null \
  -w 'http_version=%{http_version} http_code=%{http_code}\n' \
  https://localhost:8443/api/hello
~~~

Expected stdout when h2 is negotiated and the request succeeds:

~~~text
http_version=2 http_code=200
~~~

If **`http_version=1.1`** appears, HTTPS worked yet h2 was not selected. Inspect **`server.http2.enabled`**, client HTTP2 support, ALPN, TLS termination/proxy hops, or TLS compatibility. Passing **`--http2`** by itself does not prove the server accepted h2.

## 11. OpenSSL s_client Tests TLS + ALPN, Not HTTP Requests

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn h2,http/1.1 \
  -CAfile tls/ca.crt \
  -verify_return_error < /dev/null
~~~

With valid TLS/ALPN, verify:
- **ALPN protocol: h2**
- **Verify return code: 0 (ok)**
- Policy-compliant TLS protocol and cipher.

**`-servername localhost`** sends SNI so the server picks the right certificate when multiple bundles exist. **`-CAfile`** verifies the chain against the demo CA. **`-verify_return_error`** ensures verification errors fail the connection.

**Limitation of `s_client`:** it checks only the TLS handshake and ALPN; it is **not an HTTP/2 client sending frames**. Follow up with curl or Java `HttpClient` to verify real HTTP/2 responses.

### 11.1. Plain HTTP Sent to a TLS Port

~~~bash
curl -v http://localhost:8443/api/hello
~~~

This uses the **wrong scheme**. The connection typically fails with a protocol/network error or an error response from the connector; do not expect the server to emit an HTTP 301/302 redirect on its TLS port. HTTP→HTTPS redirects belong on a separate HTTP listener or Ingress.

### 11.2. Valid TLS Cert Does Not Imply Valid h2

A client can verify the certificate cleanly yet negotiate HTTP/1.1 via ALPN. Conversely, `curl -k` can negotiate h2 against an invalid certificate. **Verify both**, never just one.

## 12. Standalone Java 17 HttpClient: Inspecting response.version()

JDK **`java.net.http.HttpClient`** supports HTTP/2. Builder **`.version(HTTP_2)`** expresses only a **preferred protocol** and can fall back to HTTP/1.1 depending on proxies or constraints. **`HttpResponse.version()`** reveals what actually ran.

Create standalone **`Http2Proof.java`** at project root:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.time.Duration;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class Http2Proof {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                "Usage: java Http2Proof <ca.crt> <https-url>"
            );
            System.exit(2);
        }

        Certificate ca;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            ca = CertificateFactory.getInstance("X.509")
                .generateCertificate(in);
        }

        KeyStore trust = KeyStore.getInstance("PKCS12");
        trust.load(null, null);
        trust.setCertificateEntry("demo-ca", ca);

        TrustManagerFactory tmf =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        tmf.init(trust);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), new SecureRandom());

        HttpClient client = HttpClient.newBuilder()
            .sslContext(ssl)
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

        HttpRequest request = HttpRequest.newBuilder(
            URI.create(args[1])
        ).timeout(Duration.ofSeconds(10)).GET().build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("status=" + response.statusCode());
        System.out.println("version=" + response.version());
        System.out.println("body=" + response.body());

        if (response.statusCode() != 200
                || response.version() != HttpClient.Version.HTTP_2
                || !"secure-ok".equals(response.body())) {
            throw new IllegalStateException(
                "Verified TLS HTTP/2 request failed"
            );
        }
    }
}
~~~

Compile and run on Java 17:

~~~bash
javac Http2Proof.java
java Http2Proof tls/ca.crt \
  https://localhost:8443/api/hello
~~~

Expected stdout when the lab works properly:

~~~text
status=200
version=HTTP_2
body=secure-ok
~~~

The program uses **`CertificateFactory` X.509**, an in-memory `KeyStore` holding only the test CA, **`TrustManagerFactory`**, and a dedicated **`SSLContext`**. **Never** build a trust-all `TrustManager` or disable hostname verification; JDK `HttpClient` enforces HTTPS hostname checks by default. If the CA or hostname is wrong, it must throw `SSLHandshakeException` or fail validation rather than bypassing security.

If `response.version()` is **`HTTP_1_1`**, the program throws even on HTTP 200, ensuring HTTP/2 verification cannot be masked by TLS HTTP/1.1.

## 13. @SpringBootTest(RANDOM_PORT) Integration Test for Real HTTP/2

Create **`src/test/java/com/example/httpsdemo/HttpsHttp2Test.java`**:

~~~java
package com.example.httpsdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.time.Duration;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HttpsHttp2Test {

    @LocalServerPort
    int port;

    @Test
    void negotiatesVerifiedH2OverRealTomcat() throws Exception {
        Certificate ca;
        try (InputStream in = Files.newInputStream(
                Path.of("tls/ca.crt"))) {
            ca = CertificateFactory.getInstance("X.509")
                .generateCertificate(in);
        }

        KeyStore trust = KeyStore.getInstance("PKCS12");
        trust.load(null, null);
        trust.setCertificateEntry("demo-ca", ca);

        TrustManagerFactory tmf =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        tmf.init(trust);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), new SecureRandom());

        HttpClient client = HttpClient.newBuilder()
            .sslContext(ssl)
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

        HttpRequest request = HttpRequest.newBuilder(
            URI.create("https://localhost:" + port + "/api/hello")
        ).timeout(Duration.ofSeconds(10)).GET().build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, response.statusCode());
        assertEquals(HttpClient.Version.HTTP_2, response.version());
        assertEquals("secure-ok", response.body());
    }
}
~~~

**This is a real integration test**: Spring Boot launches embedded HTTPS Tomcat on a random port, loads the PEM bundle from disk, and the Java client validates the CA/hostname, ALPN HTTP/2 negotiation, status, and body.

**`MockMvc` is insufficient** here because it bypasses real HTTP connector networking, TLS, and ALPN. Unit-testing the controller does not verify HTTPS.

**Test prerequisites:** **`tls/ca.crt`**, **`tls/server.crt`**, and **`tls/server-pkcs8.key`** must exist before running Maven, with working directory at project root. In CI, generate ephemeral certificates in test setup; never commit private keys. If CI runs from a different working directory, adjust absolute file URIs and the CA path accordingly.

## 14. Alternative: JKS/PKCS12 SSL Bundle

Enterprise environments often supply a **PKCS12** archive containing the certificate chain and private key rather than raw PEM files. Generate `.p12` for the lab:

~~~bash
openssl pkcs12 -export \
  -in tls/server.crt \
  -inkey tls/server-pkcs8.key \
  -certfile tls/ca.crt \
  -name demo-server \
  -out tls/server.p12 \
  -passout pass:changeit
~~~

**Completely replace** the PEM branch of `application.yml` with the JKS/PKCS12 config:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        web:
          key:
            alias: demo-server
          keystore:
            location: "file:./tls/server.p12"
            password: "changeit"
            type: PKCS12

server:
  port: 8443
  ssl:
    bundle: web
  http2:
    enabled: true
~~~

This is a **complete replacement for PEM**, not an extra block to add alongside it. Password **`changeit`** is for the lab only; production must inject passwords from secret management rather than committing plaintext. **`.p12` contains the private key**—never treat it as public like `.crt`.

Inspect contents:

~~~bash
keytool -list -v \
  -keystore tls/server.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

Verify alias **`demo-server`**, chain, expiry, and SANs. If the alias or password is wrong, Boot fails to extract the private key and the web server refuses to start.

## 15. Non-Root Docker Image Without Baking Private Keys

Create **`Dockerfile`**:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY target/https-h2-lab-1.0.0.jar /app/app.jar
USER 10001:10001
EXPOSE 8443
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Never `COPY tls/`** into the image: private CA and server keys belong outside build artifacts. At runtime, mount certs/keys read-only at **`/etc/tls`** and pass paths via environment variables. **`USER 10001:10001`** avoids running Java as root; ensure the process can read the key file and write to a temp directory for Tomcat/JDK.

Build:

~~~bash
mvn package
docker build -t https-h2-lab:1.0.0 .
~~~

Locally in Docker, mount a **`docker-tls`** directory holding only `server.crt` and `server-pkcs8.key` (never `ca.key`), readable by UID 10001:

~~~bash
docker run --rm --name https-h2-lab \
  -p 127.0.0.1:8443:8443 \
  -v "$(pwd)/docker-tls:/etc/tls:ro" \
  -e TLS_CERT_LOCATION="file:/etc/tls/server.crt" \
  -e TLS_KEY_LOCATION="file:/etc/tls/server-pkcs8.key" \
  https-h2-lab:1.0.0
~~~

**Common permission pitfall:** a host file `chmod 0600` owned by the developer UID will be **unreadable by container UID 10001**. Set proper mount ownership or group ACLs—never run as root or `chmod 777` private keys. In Kubernetes, use a Secret volume and `fsGroup` per policy.

If enabling Docker **`--read-only`**, supply **`--tmpfs /tmp`** or a writable volume for Tomcat/JDK; keep the SSL cert mount **`:ro`**.

## 16. Kubernetes TLS Secret and HTTPS Health Probes

In a lab `kind` cluster:
1. Build the Docker image.
2. Load the image into `kind`.
3. Create a **`kubernetes.io/tls`** Secret with `tls.crt` and `tls.key`.
4. Deploy Pods with UID 10001, read-only rootfs, read-only key mount, and scratch `emptyDir`.
5. Port-forward service 8443 and verify h2 using curl and the Java client.

~~~bash
docker build -t https-h2-lab:1.0.0 .
kind load docker-image https-h2-lab:1.0.0

kubectl create secret tls https-h2-local-tls \
  --cert=tls/server.crt \
  --key=tls/server-pkcs8.key
~~~

A Kubernetes Secret is **not a CA key store**. Never put **`ca.key`** into a Pod. Protect Secrets with namespaces, RBAC, and encryption-at-rest; raw Kubernetes Secrets alone do not replace full KMS/PKI tooling.

Create **`k8s.yaml`**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: https-h2-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: https-h2-lab
  template:
    metadata:
      labels:
        app: https-h2-lab
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          image: https-h2-lab:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: https
              containerPort: 8443
          env:
            - name: TLS_CERT_LOCATION
              value: "file:/etc/tls/tls.crt"
            - name: TLS_KEY_LOCATION
              value: "file:/etc/tls/tls.key"
            - name: JAVA_TOOL_OPTIONS
              value: "-Djava.io.tmpdir=/tmp"
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tls-keypair
              mountPath: /etc/tls
              readOnly: true
            - name: scratch
              mountPath: /tmp
          startupProbe:
            httpGet:
              scheme: HTTPS
              path: /livez
              port: https
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              scheme: HTTPS
              path: /readyz
              port: https
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              scheme: HTTPS
              path: /livez
              port: https
            periodSeconds: 10
            timeoutSeconds: 2
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
      volumes:
        - name: tls-keypair
          secret:
            secretName: https-h2-local-tls
            defaultMode: 0440
        - name: scratch
          emptyDir:
            sizeLimit: 64Mi
---
apiVersion: v1
kind: Service
metadata:
  name: https-h2-lab
spec:
  type: ClusterIP
  selector:
    app: https-h2-lab
  ports:
    - name: https
      port: 8443
      targetPort: https
~~~

**Why this manifest fits the goal:**
- The TLS key lives in a **read-only Secret mount**, never inside the Docker image.
- **`runAsNonRoot`**, UID/GID, and **`fsGroup`** drop privileges; verify `tls.key` readability inside a real Pod, since volume driver/policies can affect Secret file permissions.
- **`readOnlyRootFilesystem=true`** pairs with **`emptyDir /tmp`** for Tomcat/JDK scratch space.
- **HTTPS startup/liveness/readiness** probes target port 8443 directly rather than sending plain HTTP to the HTTPS port.
- **ClusterIP Service** routes TCP without terminating TLS itself.
- **`replicas=2`** is illustrative; zero-downtime rollouts still require proper rolling strategy and capacity rather than relying on replica count alone.

**Critical warning:** kubelet **HTTPS `httpGet` probes skip certificate verification**. Readiness 200 proves the app answers health checks—it **does not** verify valid CA/SANs and **does not** prove ALPN `h2`. Always verify externally with `curl --cacert`, `openssl -verify_return_error`, or CA-validating Java clients.

Apply and verify:

~~~bash
kubectl apply -f k8s.yaml
kubectl rollout status deployment/https-h2-lab
kubectl get pods -l app=https-h2-lab
kubectl logs deployment/https-h2-lab
kubectl port-forward service/https-h2-lab 8443:8443
~~~

In another terminal:

~~~bash
curl -sS --http2 --cacert tls/ca.crt \
  -o /dev/null \
  -w 'http_version=%{http_version} http_code=%{http_code}\n' \
  https://localhost:8443/api/hello

java Http2Proof tls/ca.crt \
  https://localhost:8443/api/hello
~~~

Port-forward tunnels TCP, so TLS still terminates at Tomcat. When testing behind a public Ingress, measure both edge and backend hops rather than assuming both speak h2.

## 17. Certificate Rotation and SSL Bundle Reloading

Spring Boot 3.3 supports **reload-on-update** for PEM SSL bundles when files change, for compatible consumers including **Tomcat** and **Netty web servers** per documentation. Optional configuration snippet:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        web:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/tls/tls.crt"
            private-key: "file:/etc/tls/tls.key"
~~~

This is a **fragment**, not a complete `application.yml`; `server.ssl.bundle`, port, and HTTP/2 settings are still required.

Do not treat a **Secret update** as sufficient proof that the new certificate is being served:
- Projected Kubernetes Secret volumes update via atomic symlink replacement; file watchers must support the actual mount mechanism.
- **`subPath` mounts** do not receive automatic Secret updates like standard projected Secret volumes.
- Certificate and key must update atomically together so no key mismatch occurs mid-reload.
- Some consumers do not support live reload; verify Tomcat/Netty support for your exact Boot version.
- Existing TLS connections may keep using the old certificate/session; open a **fresh TLS handshake** when verifying rotation.
- **Rolling restarts** keyed by Secret version are predictable to measure, provided you have replicas, readiness, grace periods, and draining.

Compare certificate fingerprints before and after rotation via OpenSSL in a script checking chain/SNI—never log private keys. Monitor certificate **`notAfter`** dates and alert well ahead of expiry.

## 18. SNI, mTLS, and Truststores: Extensions Not to Confuse

**SNI (Server Name Indication)** lets the server pick a certificate matching the hostname sent by the client in the TLS handshake. Spring Boot 3.3 offers **`server.ssl.server-name-bundles`** for compatible web servers. Fragment:

~~~yaml
server:
  port: 8443
  ssl:
    bundle: web
    server-name-bundles:
      - server-name: api1.example.test
        bundle: web-api1
      - server-name: api2.example.test
        bundle: web-api2
  http2:
    enabled: true
~~~

Use only when bundles **`web-api1`** and **`web-api2`** exist with matching SAN certificates; never use a `localhost` cert for those domains. OpenSSL **`-servername`** lets you test SNI selection.

**mTLS** adds **client certificate authentication**: the server trusts a client CA and enforces **`server.ssl.client-auth=need`** (where supported). **mTLS is not required for h2.** If `client-auth=need` is active while curl/Java presents no client cert/key, the handshake fails before reaching the controller. Do not confuse client-auth failures with ALPN h2 issues.

**HTTPS only authenticates the server** in this lab; it **does not authenticate end users or enforce authorization**. Production APIs still need Spring Security, sessions, OAuth2, or JWTs per architecture.

## 19. HTTP/2 Behind Ingress, Proxies, and h2c

Example where browsers see HTTP/2 publicly:

~~~text
Browser -- h2/TLS --> nginx/Ingress -- HTTP/1.1 --> Tomcat
~~~

This is not a bug if the architecture intentionally terminates h2 at Ingress. Here Servlet **`request.getProtocol()`** returns **`HTTP/1.1`**. To make Tomcat also speak h2, configure upstream h2/h2c or TLS passthrough/re-encryption as supported by your gateway and verify the backend hop directly.

Another architecture:

~~~text
Client -- TLS/h2 --> Ingress -- h2c/TCP --> Tomcat h2c
~~~

On the ingress→Tomcat hop, **`h2c` is unencrypted**, so use it only inside trusted networks meeting encryption policies; never describe it as "end-to-end TLS." Spring Boot 3.3 supports `h2c` when server SSL is off and HTTP/2 is enabled, provided Ingress is configured for upstream `h2c`.

**Forwarded headers:** when a proxy terminates TLS, the app may see scheme `http` and emit wrong redirects or insecure cookies unless forwarding is configured properly. Use **`server.forward-headers-strategy`** for trusted proxies and sanitize `X-Forwarded-*` at the edge. Never accept untrusted forwarding headers from arbitrary clients.

A chain like client→CDN→Ingress→Tomcat involves multiple independent TLS sessions, each with its own ALPN negotiation. Curling the public domain verifies only the client-facing hop, never the backend.

## 20. Troubleshooting SSL Bundles and HTTP/2

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| Bundle `web` not found | Wrong `server.ssl.bundle` name, profile/env binding | Check `spring.ssl.bundle.pem.web` and effective config |
| Certificate file not found | Bad `file:` path, missing mount/Secret | Check path, UID permissions, `kubectl logs` |
| Cannot parse private key | PKCS#1/SEC1 PEM, encrypted key, or corrupt file | Convert to PKCS#8, run `openssl pkey` |
| Private key mismatch | Cert and key do not belong to same pair | Compare public keys with OpenSSL |
| `SSLHandshakeException` PKIX path | Client doesn't trust CA or chain is incomplete | Use `curl --cacert`, Java truststore |
| Hostname mismatch | SAN missing URL/SNI hostname | Check `openssl x509 -ext subjectAltName` |
| Certificate expired / not yet valid | Clock drift or cert lifecycle mismatch | Check `openssl x509 -dates`, NTP |
| `curl -k` succeeds yet CA verify fails | Cert trust or hostname is still invalid | Never disable verify; fix CA/cert |
| HTTPS 200 yet HTTP/1.1 | h2 not negotiated, client lacks HTTP2, or proxy | Check `curl -V`, ALPN, `response.version()` |
| `s_client` ALPN h2 yet Java HTTP/1.1 | Different proxy route or client constraint | Hit direct endpoint, inspect logs and trust config |
| Spring `getProtocol()` HTTP/1.1 while browser shows h2 | Ingress terminates client-facing h2 | Verify upstream protocol per hop |
| Plain HTTP to 8443 fails | Wrong scheme for TLS port | Use `https://` |
| TLS runs, port 8080 closed | Only HTTPS 8443 connector exists | Check `server.port` and LB routing |
| K8s HTTPS readiness passes, curl verify fails | Kubelet probe skips cert verification | Run CA-aware external verification |
| K8s Pod `CrashLoopBackOff` | Secret permissions, missing `/tmp`, bad key path | Inspect describe/logs, `fsGroup`, `readOnlyRoot` |
| Secret updated, old cert still served | File watcher/reload inactive; reused TLS sessions | Test fresh handshake, check rollout/cert fingerprint |
| Client-auth handshake failure | mTLS enabled, client sent no cert | Check `server.ssl.client-auth` and client trust CA |
| ALPN shows no h2 | SSL off, Boot setting, proxy, JDK/TLS mismatch | Check config, `s_client`, Tomcat version |
| HTTP/2 streams reset under load | Timeouts, stream caps, memory, proxy limits | Inspect metrics, run authorized load tests |
| One hostname works, another fails | SNI/SAN/bundle mapping mismatch | Test `openssl -servername` and SANs |

### 20.1. 10-Step Runbook

1. Record the target URL, port, DNS/SNI, and TLS topology of the request.
2. Confirm embedded Tomcat starts cleanly and loads the intended PEM bundle.
3. Verify certificate chain, SANs, expiry, and private key format.
4. Run **`openssl verify -verify_hostname localhost`** against the test CA.
5. Run **`openssl s_client -servername localhost -alpn h2,http/1.1 -CAfile`**.
6. Run **`curl --http2 --cacert`** and check `http_version`.
7. Run **Java `Http2Proof`** to verify `response.version()` and body.
8. Hit `/api/transport` to inspect the protocol from Tomcat's perspective.
9. If behind an LB/Ingress, verify protocol and security on every hop.
10. After certificate rotation, verify the new cert via a **fresh TLS handshake** and re-run integration/regression tests.

**Never "fix" TLS errors in production by enabling trust-all or disabling SSL.** That is a severe security vulnerability, not a fix.

### 20.2. Keep TLS Debugging Private

You can temporarily enable **`-Djavax.net.debug=ssl,handshake`** in staging to inspect TLS handshakes, though logs are verbose and reveal deployment/cert details. Never log private keys, keystore passwords, `Authorization`, or `Cookie` values. Never expose Actuator `env` or `heapdump` just to debug TLS.

## 21. Negative Tests and Acceptance Matrix

| Test | How to Trigger in Lab | Expected Outcome |
| --- | --- | --- |
| Valid local CA + valid hostname | `curl --cacert ca.crt https://localhost` | 200, verified TLS |
| Client doesn't trust CA | Omit `--cacert` when untrusted | TLS validation fails |
| Wrong SAN | Request hostname absent from SAN | Hostname verification fails |
| Expired cert | Test with controlled expired test cert | TLS verification fails |
| Mismatched server key | Bundle points to wrong private key | Startup/reload fails |
| Bad PEM path | Point to nonexistent file | Startup fails with key-material error |
| Plain HTTP on 8443 | `curl http://localhost:8443` | Protocol error / connection closed |
| HTTPS HTTP/1.1 | `curl --http1.1 --cacert` | 200, h1 if server permits |
| HTTPS HTTP/2 | `curl --http2 --cacert` | 200, `http_version=2` |
| ALPN offers only http/1.1 | `s_client -alpn http/1.1` | Does not prove h2 |
| Client lacks HTTP2 | `curl -V` missing HTTP2 | Do not use that curl binary as h2 proof |
| Java client fallback | Disable server h2 in isolated test env | `response.version()` falls back to `HTTP_1_1` |
| Public edge h2, upstream h1 | Ingress terminates TLS | Report protocol per hop accurately |
| K8s HTTPS readiness passes | Kubelet probe | Not certificate validation |
| Rotate Secret | New Secret + reload/rolling restart | Fresh handshake serves new cert |
| TLS disabled accidentally | Remove `server.ssl.bundle` | Must not count as success |

Run negative tests only in authorized environments—never tamper with production certificates. Remember TLS failures happen **before HTTP**, so never expect a JSON 400/401 body when a TLS handshake is rejected.

## 22. Operational Security and Performance

Operational requirements:
- Certificates must come from a trusted CA, match domain SANs, include full chains, and stay unexpired.
- Private keys belong in Secrets/KMS/PKI with restricted access and rotation policies.
- Never place CA private keys or TLS server keys into images, JARs, or Git.
- Enforce org-approved TLS versions and ciphers; keep Java, Boot, and Tomcat patched.
- Keep HTTPS termination distinct from user authentication/authorization.
- When external port 80 exists, enforce proper HTTPS redirects/HSTS and `Secure`/`HttpOnly`/`SameSite` cookies.
- Monitor TLS handshake failures, negotiated ALPN versions, cert expiration, 4xx/5xx rates, and client errors.
- HTTP/2 stream limits, header compression, buffer sizes, request deadlines, and Tomcat workers still need capacity planning.
- Never benchmark h2 vs h1 using a single localhost request to project production throughput.
- Under high load, `RST_STREAM`/`GOAWAY` can appear despite valid TLS; tune proxy/HTTP2 SETTINGS, flow control, timeouts, and concurrency.
- Never run cleartext `h2c` outside explicitly authorized internal networks.
- Test HTTP/2 through a real server, not MockMvc alone.

**Never assume HTTP/2 is always faster**: compare h1 keep-alive against h2 multiplexing under identical TLS trust, warm connections, concurrency, response sizes, and workloads; inspect p95/p99, CPU/GC/memory, and error rates.

## 23. Review Questions with Answers

**1.** Does `server.ssl.bundle=web` generate a certificate automatically?  
**Answer:** No. It selects a declared bundle already configured with valid key material.

**2.** What is the PEM bundle namespace in Spring Boot 3.3?  
**Answer:** `spring.ssl.bundle.pem.<name>`.

**3.** Does setting `server.http2.enabled=true` force every client to use h2?  
**Answer:** No. Clients, ALPN, TLS, and proxies may negotiate HTTP/1.1 instead.

**4.** Is `h2c` HTTP/2 over TLS?  
**Answer:** No. `h2c` is cleartext HTTP/2.

**5.** Does Java 17 require `libtcnative` for Tomcat 10.1 to serve h2 over TLS?  
**Answer:** Not required; Java 17 supports ALPN natively.

**6.** Is TLS 1.3 mandatory for HTTP/2?  
**Answer:** No. TLS 1.2 can also be used when meeting cipher/protocol requirements.

**7.** Why can a certificate with `CN=localhost` but no SAN fail trust verification?  
**Answer:** Modern hostname verification checks SAN entries.

**8.** Is `curl --http2` alone proof of h2?  
**Answer:** No. Verify `http_version=2` or an actual HTTP/2 response.

**9.** What does `openssl s_client -alpn h2` test?  
**Answer:** TLS handshake and negotiated ALPN, not sending/receiving HTTP/2 frames.

**10.** Is Java `HttpClient` `.version(HTTP_2)` a guarantee?  
**Answer:** No. `response.version()` can still be `HTTP_1_1` on fallback.

**11.** Does `curl -k` returning 200 prove the CA and hostname are valid?  
**Answer:** No, because it skips verification.

**12.** Why should `ca.key` never be mounted into a Kubernetes Pod?  
**Answer:** It is the CA's private signing key, unnecessary for a server serving TLS.

**13.** How do a keystore and truststore differ?  
**Answer:** A keystore holds identity certificates and private keys; a truststore holds CAs/certs used to verify peers.

**14.** Does an HTTPS listener on 8443 automatically open HTTP 8080 for redirects?  
**Answer:** No. A separate connector or proxy is required.

**15.** Does a Kubelet HTTPS readiness probe validate CA/SANs?  
**Answer:** No; HTTPS `httpGet` probes skip certificate verification.

**16.** If the browser sees h2 on the public domain while Java `getProtocol()` reports h1, is that a bug?  
**Answer:** Not necessarily; Ingress may terminate h2 and proxy upstream over h1.

**17.** Does a TLS session between Ingress and a Pod automatically share the browser's ALPN choice?  
**Answer:** No; each TLS hop performs its own handshake.

**18.** Does updating a Secret volume guarantee Tomcat reloaded the certificate?  
**Answer:** No. Watcher/consumer support or a rolling restart plus fresh-connection verification is needed.

**19.** Is mTLS required to run HTTP/2?  
**Answer:** No; mTLS is client certificate authentication.

**20.** Why use `@SpringBootTest(RANDOM_PORT)` instead of MockMvc to test h2?  
**Answer:** Real Tomcat, TLS, and ALPN sockets are required.

**21.** Can a PKCS12 `.p12` file contain a private key?  
**Answer:** Yes; protect it as a secret.

**22.** Does enabling TLS prevent XSS, CSRF, or authorization flaws?  
**Answer:** No. TLS protects transport; application-layer security is still required.

## 24. Deployment Checklist

- [ ] TLS termination topology and per-hop protocols clearly defined.
- [ ] Valid certificate chain, matching SANs, and unexpired dates.
- [ ] PKCS#8 PEM or PKCS12 private key matching the certificate.
- [ ] Bundle **`spring.ssl.bundle.pem.web`** or **`jks.web`** declared.
- [ ] **`server.ssl.bundle=web`** set without mixing discrete SSL key properties.
- [ ] **`server.http2.enabled=true`** set on the HTTPS web server to verify.
- [ ] HTTPS port 8443 listening; plain HTTP not sent to TLS port.
- [ ] Local curl tests use **`--cacert tls/ca.crt`**, never **`-k`**.
- [ ] OpenSSL ALPN selects **`h2`** with verify return code **`0`**.
- [ ] curl reports `http_version` **`2`** and HTTP status **`200`**.
- [ ] Java `HttpClient` reports **`response.version()==HTTP_2`** and body **`secure-ok`**.
- [ ] JUnit `@SpringBootTest(RANDOM_PORT)` proves real TLS/ALPN.
- [ ] Behind Ingress, both public edge and backend hops verified.
- [ ] Docker image embeds zero private keys and runs non-root.
- [ ] Kubernetes TLS Secret mounted read-only with valid file permissions.
- [ ] Read-only rootfs paired with writable `/tmp` for Tomcat if required.
- [ ] HTTPS readiness is not treated as CA trust or ALPN proof.
- [ ] Certificate expiry monitoring and rotation tested with fresh handshakes.
- [ ] Rollback plan exists for cert/reload failures, with no cleartext fallback.
- [ ] TLS debug logs expose no keys, tokens, or sensitive details.
- [ ] Negative tests cover CA, SAN, key mismatch, HTTP/1.1 fallback, and proxy topology.
- [ ] Properties cross-checked against exact Spring Boot, Tomcat, and JDK versions.

## 25. Conclusion

**SSL bundles** keep certificates and private keys out of source code and bind named key material cleanly to Spring Boot's embedded web server. With **Spring Boot 3.3.13 + Tomcat 10.1 + Java 17**, setting **`server.ssl.bundle=web`** and **`server.http2.enabled=true`** enables HTTPS to negotiate **`h2`** via ALPN. Yet a configuration flag alone is never proof of the wire protocol.

This practice is complete only when **CA and SAN/hostname verification pass**, **ALPN selects `h2`**, **curl and Java `HttpClient` confirm HTTP/2**, **real-port JUnit tests pass**, and deployments load keys from external Secrets without leaking private material. Behind Ingress, report protocol per hop; after rotation, verify with a fresh TLS handshake.

## Official References

- Spring Boot 3.3.13 — SSL bundles, PEM/JKS and reload-on-update: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Spring Boot 3.3.13 — Embedded Web Servers, SSL bundles and HTTP/2 over h2/h2c: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3.13 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Actuator Kubernetes readiness/liveness: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Apache Tomcat 10.1 — HTTP Connector/TLS/HTTP2: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Oracle Java 17 — HttpClient protocol selection: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java 17 — HttpResponse.version: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- OpenSSL — s_client, verification and ALPN: https://docs.openssl.org/3.0/man1/openssl-s_client/
- OpenSSL — x509 and certificate verification: https://docs.openssl.org/3.0/man1/openssl-x509/
- curl — --http2, --cacert and --write-out: https://curl.se/docs/manpage.html
- Kubernetes — Secrets and TLS keys: https://kubernetes.io/docs/concepts/configuration/secret/
- Kubernetes — HTTPS probes skip certificate verification: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Kubernetes — Security context and runAsNonRoot: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- RFC 9113 — HTTP/2: https://www.rfc-editor.org/rfc/rfc9113
- RFC 7301 — TLS Application-Layer Protocol Negotiation: https://www.rfc-editor.org/rfc/rfc7301