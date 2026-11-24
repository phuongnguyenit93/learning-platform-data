# SSL Bundles and Shared Trust Material Configuration in Spring Boot

## 1. Problem: TLS Has Multiple Connections, So Certificates Should Not Be Scattered

A Spring Boot application can play two roles at the same time:

- **TLS server:** accepts HTTPS connections from browsers, API clients, gateways, or other services.
- **TLS client:** calls downstream services via `RestClient`, `WebClient`, connects to databases, message brokers, or another TLS protocol.

If each library reads a certificate file from its own path, builds its own `SSLContext`, or configures a JVM-wide truststore via system properties, the application becomes difficult to rotate certificates on, hard to test, and prone to bugs where "client A trusts this CA while client B does not."

Since **Spring Boot 3.1**, **SSL bundles** allow declaring **named sets of key/trust material** via `spring.ssl.bundle.*`, and referencing that bundle name in supported components. A bundle can hold key material, trust material, and TLS options; the application no longer needs to duplicate file paths and passwords everywhere.

Conceptual example:

```text
                    Spring Boot configuration
                  spring.ssl.bundle.jks.* / pem.*
                              │
                  ┌───────────┴──────────────┐
                  │                          │
        local-server bundle            partner-trust bundle
        [certificate + key]             [CA / truststore]
                  │                          │
          server.ssl.bundle        ┌─────────┴────────────┐
                  │                │                      │
           Embedded Tomcat    RestClientSsl          WebClientSsl
             HTTPS :8443          │                      │
                  │         HTTPS to partner      HTTPS to partner
                  │                │                      │
             Browser/client       Verify cert chain + hostname
```

**Core point:** the same **bundle declared once** can be referenced by **multiple consumers** whenever those consumers support the bundle API. However, declaring a bundle **does not automatically make every TLS client use that bundle**; each consumer must be wired with the appropriate configuration.

This lesson uses APIs and properties for **Spring Boot 3.3.13 / Java 17+** so examples remain consistent and verifiable. For production systems, use a supported Spring Boot version with security patches; package APIs may change in newer major versions.

## 2. Terms to Understand Before Configuring

| Concept | Purpose | Where it is commonly used |
|---|---|---|
| **TLS** | Authenticates peers, encrypts traffic, and protects integrity | HTTPS, TLS to DB/broker |
| **Certificate (X.509)** | Contains public key, subject/SAN, issuer, validity, and CA signature | Sent by server to client during TLS handshake |
| **Private key** | Proves ownership of the corresponding certificate/public key | Identity holder; must be strictly protected |
| **CA / trust anchor** | Basis for accepting a peer's certificate chain | Client truststore or mTLS server truststore |
| **Keystore** | Stores identity/key material: certificate chain + private key (or multiple entries) | HTTPS server, mTLS client |
| **Truststore** | Stores certificates/CAs that the program accepts when verifying a peer | HTTPS client; server when requiring client certificates |
| **SAN (Subject Alternative Name)** | DNS names/IPs the certificate is permitted to represent | Hostname verification by HTTPS clients |
| **mTLS (mutual TLS)** | Both sides prove identity with certificates | Service-to-service, private APIs |
| **ALPN** | Negotiates the application protocol during TLS handshake | HTTP/2 `h2` and HTTP/1.1 |
| **SSL bundle** | Named logical container for key/trust/options managed by Spring Boot | Server, clients, and supported integrations |

**Key ≠ trust:** the application's certificate/private key **proves who you are**, whereas CA certificates/truststores **decide whom to trust**. An SSL bundle can contain only a truststore (client trusting a CA), only a keystore (server presenting its identity), or both (mTLS). Having only a keystore does not mean the application trusts every other CA.

**"SSL" in API names is historical**, while the protocols to use are modern TLS. Do not enable SSLv3/TLSv1.0/TLSv1.1 in production, and do not disable hostname verification to work around certificate errors.

## 3. Structure of Spring Boot's SSL Bundle API

Spring Boot auto-configures an `org.springframework.boot.ssl.SslBundles` bean to look up named bundles defined via properties. Access it like this:

```java
import javax.net.ssl.SSLContext;

import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;

// Example inside a constructor or method where Spring injects SslBundles.
SslBundle bundle = sslBundles.getBundle("partner-trust");
SSLContext context = bundle.createSslContext();
```

This is an **illustrative code snippet**, requiring an `SslBundles sslBundles` variable/parameter and an enclosing class/method scope.

Important classes/capabilities:

- `SslBundles.getBundle(name)`: retrieves a bundle by name; if the name does not exist, a configuration error is reported. The name must match the registered name (note normalization rules when using env vars).
- `SslBundle.getStores()`: returns an `SslStoreBundle` with Java `KeyStore` keystore/truststore instances and related metadata.
- `SslBundle.getManagers()`: accesses key/trust manager factories and manager arrays.
- `SslBundle.createSslContext()`: creates a `javax.net.ssl.SSLContext` convenient for client libraries expecting a JSSE context.
- `SslBundle.getOptions()` and `getProtocol()`: exposes the bundle's TLS options; do not assume every consumer honors all options.
- `SslBundle.getKey()`: key alias/password details for the bundle.

A bundle is a **named, managed configuration**, not a "global JVM certificate." Specific consumers must still support and apply it. Creating an `SSLContext` and discarding it does not make `WebClient`/`RestClient` automatically use that context.

## 4. Two Common Formats: JKS/PKCS12 and PEM

### 4.1. JKS or PKCS12

For Java KeyStore, the prefix is:

```properties
spring.ssl.bundle.jks.<bundle-name>.keystore.location=...
spring.ssl.bundle.jks.<bundle-name>.keystore.password=...
spring.ssl.bundle.jks.<bundle-name>.keystore.type=PKCS12
spring.ssl.bundle.jks.<bundle-name>.key.alias=...
spring.ssl.bundle.jks.<bundle-name>.truststore.location=...
spring.ssl.bundle.jks.<bundle-name>.truststore.password=...
spring.ssl.bundle.jks.<bundle-name>.truststore.type=PKCS12
```

`<bundle-name>` in the block above is a syntax placeholder and must be replaced with an actual name (e.g., `local-server`, `partner-trust`); **you cannot paste it verbatim to run**. A bundle does not have to contain both a keystore and a truststore.

- `keystore` can hold the service's private key and certificate chain.
- `truststore` holds certificates/CAs used to authenticate the peer.
- `type=PKCS12` should be declared when the file is `.p12`/`.pfx`; JKS uses type `JKS` if needed.
- `key.alias` is useful if the keystore contains multiple key entries.
- If the key password differs from the keystore password, configure the key password via the corresponding property; do not assume both passwords always match.

**PKCS12 and JKS are binary containers**, not network protocol names or certificate signing algorithms. Java `keytool` can create and inspect these containers.

### 4.2. PEM: Certificates and Private Keys as Text

For PEM files, the prefix is:

```properties
# Application identity (to present during TLS handshake).
spring.ssl.bundle.pem.local-server.keystore.certificate=file:/etc/tls/server-chain.crt
spring.ssl.bundle.pem.local-server.keystore.private-key=file:/etc/tls/server.key

# Trust anchor for a downstream service (contains no private key).
spring.ssl.bundle.pem.partner-trust.truststore.certificate=file:/etc/tls/partner-ca.pem
```

Here `local-server` and `partner-trust` are **two independent bundles**. The server certificate file normally needs to contain the leaf certificate and required chain to send to peers; the trust certificate file contains the trusted CA/certificate. Never put a partner's private key inside a truststore.

Spring Boot 3.3 can read PEM from resource locations (`classpath:`, `file:`), `base64:` data, or inline PEM content per the property contract. For PEM private keys, prefer **PKCS#8** (`BEGIN PRIVATE KEY` or an appropriately encrypted PKCS#8 form). Never paste raw private keys into source code, Git, logs, or tickets.

**Environment variables:** when defining bundles via environment variables, Spring Boot converts bundle names to lowercase. Use short, consistent lowercase ASCII names such as `partnertrust` or `partner-trust`, and avoid relying on case sensitivity.

### 4.3. Which Configuration Should You Choose?

| Scenario | Suitable approach |
|---|---|
| Java application with a `.p12` file issued by a CA/tool | `spring.ssl.bundle.jks.*` |
| Kubernetes Secret mounting PEM certificate/key files | `spring.ssl.bundle.pem.*` |
| Client that only needs to trust an internal CA | Bundle with truststore only |
| Server that only needs HTTPS with its own certificate | Bundle with keystore |
| mTLS client | Bundle with both client identity and server trust material |
| TLS server requiring client certificates | Server bundle with identity and client-CA trust material; enable client auth |
| Multiple HTTP clients calling services under the same CA | Multiple clients referencing the **same trust bundle name** |

Never use a truststore that "trusts every certificate" to avoid configuring a CA, especially avoiding trust-all `TrustManager` implementations and hostname verifiers that always return `true`.

## 5. Using a Bundle for an HTTPS Server and HTTP/2

To have the embedded server listen on HTTPS port 8443 using bundle `local-server`:

```properties
server.port=8443
server.ssl.bundle=local-server
server.http2.enabled=true
```

In Spring Boot 3.3, `server.ssl.bundle` references a declared SSL bundle, e.g., `spring.ssl.bundle.jks.local-server.keystore.*`. Boot translates this configuration to Tomcat/Jetty/Undertow/Reactor Netty depending on your stack and active embedded server.

**Important rules:**

- **Do not combine** `server.ssl.bundle` with **discrete keystore/PEM properties** under `server.ssl` (such as `server.ssl.key-store` or `server.ssl.certificate`). Use only one identity source per the contract.
- When using a bundle, `server.ssl.ciphers`, `server.ssl.enabled-protocols`, and `server.ssl.protocol` **are ignored**; place those options under `spring.ssl.bundle.<type>.<name>.options.*` if supported by the consumer.
- `server.ssl.client-auth` still controls whether client certificates are required. If `need` is enabled, server trust material must be configured and clients must present a valid certificate.
- `server.port=8443` is now **HTTPS**, and does not automatically open an additional plaintext HTTP port on 8080. To have both connectors, configure another connector programmatically or use an appropriate reverse proxy/ingress.
- If TLS termination happens at a load balancer/ingress, HTTP traffic inside the container may be HTTP/1.1 or h2c. Do not conclude "clients are using HTTP/2 to Spring Boot" solely from `server.http2.enabled=true` when TLS terminates at a proxy.

**HTTP/2 is not a certificate format.** With `server.http2.enabled=true` and server SSL enabled, Spring Boot supports `h2` over TLS via ALPN when both the embedded server and client negotiate it successfully. Without SSL enabled, `h2c` is non-TLS HTTP/2 in supported setups/servers. A client may still negotiate HTTP/1.1 even when the server allows HTTP/2; verify the protocol actually negotiated.

## 6. Runnable Example: Creating Local Certificates, Declaring Two Bundles, and Reusing Trust

This example uses **Spring Boot 3.3.13, Java 17+, Gradle**, creating an HTTPS server with Tomcat and two HTTP clients sharing **one trust bundle**: `RestClient` (blocking) and `WebClient` (reactive). The demo app calls **the same local server** so you can observe both clients sharing the same certificate trust policy without requiring an external network.

Note: the self-signed certificate and password `changeit` here are **for local/demo purposes only**. Do not bring demo keys/certs/passwords into production, and do not commit keystore private keys to repositories.

### 6.1. Project Structure

```text
ssl-bundle-demo/
├── build.gradle
├── certs/
│   ├── server.p12           # Generated locally with keytool, do not commit.
│   ├── server.crt           # Public certificate of the local server.
│   └── truststore.p12       # Public certificate imported to trust the server.
└── src/main/
    ├── java/com/example/sslbundle/SslBundleApplication.java
    └── resources/application.properties
```

In practice, add `certs/*.p12` and `certs/*.key` to `.gitignore`. Public certificates are not secrets though they still require lifecycle management; private keys and passwords are top-secret material.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Why include both starters?** The example intentionally demonstrates `RestClient` and `WebClient` in the same app. When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot 3.3 normally chooses **Servlet/MVC + Tomcat** as the web server, while `WebClient` remains usable for outbound calls. This does **not** automatically make the server run on WebFlux.

### 6.2. Generating Local Certs and Truststore with keytool

From the project root (with JDK 17+ and `keytool`), create the `certs` directory and run three commands **on a development machine**:

```bash
mkdir -p certs

keytool -genkeypair \
  -alias local-server \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore certs/server.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost, OU=Learning, O=Demo, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

keytool -exportcert \
  -alias local-server \
  -keystore certs/server.p12 \
  -storetype PKCS12 -storepass changeit \
  -rfc -file certs/server.crt

keytool -importcert \
  -alias local-server \
  -file certs/server.crt \
  -keystore certs/truststore.p12 \
  -storetype PKCS12 -storepass changeit \
  -noprompt
```

- `server.p12` stores the HTTPS server's **private key and certificate**.
- `server.crt` is the exported public certificate so clients can inspect/set the trust anchor in the local example.
- `truststore.p12` stores the trusted public certificate. **It does not need to contain the server private key.**
- `SAN=dns:localhost,ip:127.0.0.1` lets the certificate match local hosts. If only `CN` is given without appropriate SANs, modern clients may report a hostname mismatch.
- `-validity 30` creates a 30-day demo certificate; regenerate it after expiration.

The commands above use Bash-style syntax; on Windows PowerShell, run each `keytool` command on a single line or adjust line-continuation characters per PowerShell syntax. `mkdir -p` is Bash syntax for creating directories; PowerShell can use `New-Item -ItemType Directory -Force certs`.

**Do not use this self-signed certificate as a shared company root CA.** Production normally uses a managed CA, valid certificate chains, protected private keys, and scheduled rotation.

### 6.3. Defining the Server Bundle and Shared Trust Bundle

**`src/main/resources/application.properties`:**

```properties
# HTTPS server (identity):
server.port=8443
server.ssl.bundle=local-server
server.http2.enabled=true

spring.ssl.bundle.jks.local-server.keystore.location=file:./certs/server.p12
spring.ssl.bundle.jks.local-server.keystore.type=PKCS12
spring.ssl.bundle.jks.local-server.keystore.password=${LOCAL_SERVER_STORE_PASSWORD:changeit}
spring.ssl.bundle.jks.local-server.key.alias=local-server

# ONE trust bundle reused across multiple HTTP clients:
spring.ssl.bundle.jks.local-trust.truststore.location=file:./certs/truststore.p12
spring.ssl.bundle.jks.local-trust.truststore.type=PKCS12
spring.ssl.bundle.jks.local-trust.truststore.password=${LOCAL_TRUST_STORE_PASSWORD:changeit}
```

In Spring properties, `${LOCAL_SERVER_STORE_PASSWORD:changeit}` means: use the environment variable if present, otherwise fall back to the demo password `changeit`. In production, **remove the secret fallback** and use an appropriate secret store/file mount/credential manager. `file:./certs/...` is relative to the process working directory; when running a JAR in a container, this path may differ. For stability in production, use an absolute path from a secret mount.

Bundle `local-server` uses a **keystore** and is referenced by `server.ssl.bundle`. Bundle `local-trust` uses a **truststore** and is reused across multiple HTTP clients. The properties above do not use discrete `server.ssl.key-store`.

### 6.4. Java 17+ Code Using RestClientSsl and WebClientSsl

**`src/main/java/com/example/sslbundle/SslBundleApplication.java`:**

```java
package com.example.sslbundle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class SslBundleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SslBundleApplication.class, args);
    }
}

@Service
class LocalTlsClients {
    private final RestClient blockingClient;
    private final WebClient reactiveClient;

    LocalTlsClients(RestClient.Builder restBuilder, RestClientSsl restSsl,
                    WebClient.Builder webBuilder, WebClientSsl webSsl) {

        this.blockingClient = restBuilder
                .baseUrl("https://localhost:8443")
                .apply(restSsl.fromBundle("local-trust"))
                .build();

        this.reactiveClient = webBuilder
                .baseUrl("https://localhost:8443")
                .apply(webSsl.fromBundle("local-trust"))
                .build();
    }

    String pingBlocking() {
        return blockingClient.get()
                .uri("/ping")
                .retrieve()
                .body(String.class);
    }

    Mono<String> pingReactive() {
        return reactiveClient.get()
                .uri("/ping")
                .retrieve()
                .bodyToMono(String.class);
    }
}

@RestController
class ProbeController {
    private final LocalTlsClients clients;

    ProbeController(LocalTlsClients clients) {
        this.clients = clients;
    }

    @GetMapping(path = "/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String ping() {
        return "pong over tls";
    }

    @GetMapping(path = "/probe/rest",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String checkBlockingClient() {
        return clients.pingBlocking();
    }

    @GetMapping(path = "/probe/webclient",
            produces = MediaType.TEXT_PLAIN_VALUE)
    Mono<String> checkReactiveClient() {
        return clients.pingReactive();
    }
}
```

This is a **valid single Java file**: only `SslBundleApplication` is a top-level `public class`; the remaining classes are package-private in the same package so component scanning discovers them. The `RestClientSsl` and `WebClientSsl` imports are **Spring Boot 3.3 packages**; do not copy Spring Boot 4.x packages into a 3.3 project.

Main flow:

1. Boot reads the `local-server` definition and creates the embedded HTTPS Tomcat server.
2. `LocalTlsClients` receives the auto-configured builders along with the two SSL adapters.
3. `restSsl.fromBundle("local-trust")` and `webSsl.fromBundle("local-trust")` use the **same trust bundle name**, configuring each client/connector via its corresponding API.
4. When `/probe/rest` is called, the MVC handler calls the blocking `RestClient`; for `/probe/webclient`, the handler returns `Mono<String>`, which MVC adapts as an async return value.
5. Both clients validate the server certificate and hostname `localhost` using the truststore; there is no `trustAll`/`insecure`.

**Why does the project call itself?** To verify end-to-end TLS without needing a separate downstream server. This self-calling design is **for demonstration only**, not a recommended production architecture: it consumes extra network/connections, can impact thread pools, and can cause deadlocks under tight resource limits.

### 6.5. Run and Observe Results

In the project directory with all three cert files at the expected paths:

```bash
gradle bootRun
```

If using the Gradle Wrapper, run `./gradlew bootRun` (Linux/macOS) or `.\gradlew.bat bootRun` (Windows PowerShell). Use JDK 17+ and a Gradle version compatible with Spring Boot 3.3.

Call with curl and **explicitly pass the local CA/certificate**, rather than disabling TLS verification:

```bash
curl -i --cacert certs/server.crt https://localhost:8443/ping

curl -i --cacert certs/server.crt https://localhost:8443/probe/rest

curl -i --cacert certs/server.crt https://localhost:8443/probe/webclient
```

All three requests are expected to return **HTTP 200** with the exact text body:

```text
pong over tls
```

Headers and HTTP version shown may vary depending on curl, proxy, and ALPN. If `curl` is run from another directory, adjust the `--cacert` path. If connecting via another IP not listed in the SAN, hostname verification can fail even if the certificate is trusted.

If you run `curl https://localhost:8443/ping` **without `--cacert`** on a machine that does not trust the self-signed certificate, the connection will normally be rejected because the certificate is not in the trust anchors. That is the **correct security outcome**, not something to "fix" with `-k`/`--insecure` in production.

### 6.6. Checking Real HTTP/2 h2

If your curl build supports HTTP/2, try:

```bash
curl --http2 -v --cacert certs/server.crt \
  https://localhost:8443/ping
```

Observe the TLS/ALPN negotiation in the verbose output. When both server and client support `h2` and negotiate it successfully, the request uses HTTP/2; otherwise it may fall back to HTTP/1.1 or report an error depending on the client. `server.http2.enabled=true` **does not prove** every client uses HTTP/2. In infrastructure with a reverse proxy, check the two hops separately: browser→proxy and proxy→Spring Boot.

## 7. Writing a TLS Test Instead of Only Reading Logs

A useful smoke test starts HTTPS on a random port, uses a `RestClient` with the trust bundle, and asserts the response. This is an **additional test file** for the `ssl-bundle-demo` project; it runs when `certs` exist and the application config from section 6.3 is valid.

**`src/test/java/com/example/sslbundle/TlsBundleIntegrationTest.java`:**

```java
package com.example.sslbundle;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TlsBundleIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    RestClient.Builder builder;

    @Autowired
    RestClientSsl ssl;

    @Test
    void customTrustBundleValidatesHttpsServer() {
        RestClient trusted = builder
                .baseUrl("https://localhost:" + port)
                .apply(ssl.fromBundle("local-trust"))
                .build();

        String body = trusted.get()
                .uri("/ping")
                .retrieve()
                .body(String.class);

        assertEquals("pong over tls", body);
    }
}
```

Run:

```bash
gradle test
```

This test uses `@SpringBootTest(RANDOM_PORT)` to avoid colliding with port 8443; the SSL configuration remains active. `@LocalServerPort` captures the **actual port** Tomcat bound to. The client still verifies the certificate and hostname `localhost` through the bundle. If the certificate is expired or the truststore lacks the certificate, the test must fail during the TLS handshake, rather than passing because verification was disabled.

**Limitation note:** this test uses a local self-signed certificate and checks one `RestClient`; it does not replace tests for rotation, mTLS, or real production certificate chains. In CI, you can generate a test keystore/truststore in a test setup step instead of committing private keys to the repository.

## 8. Reusing Trust Material Across Multiple Outbound Clients

The primary purpose of SSL bundles is to avoid duplicated and fragmented configurations.

Suppose the application calls two HTTPS APIs within the same internal trust domain. Configure one bundle:

```properties
spring.ssl.bundle.pem.internal-ca.truststore.certificate=file:/etc/company/pki/internal-ca-chain.pem
```

With Spring Boot 3.3 **`RestClient`**:

```java
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.web.client.RestClient;

// Snippet inside a constructor/service with builder and restSsl injected:
RestClient billing = restBuilder
        .baseUrl("https://billing.internal.example")
        .apply(restSsl.fromBundle("internal-ca"))
        .build();

RestClient inventory = restBuilder
        .baseUrl("https://inventory.internal.example")
        .apply(restSsl.fromBundle("internal-ca"))
        .build();
```

Both `RestClient` instances share the **same trust policy** named `internal-ca`, while each client keeps its own base URL and behavior.

With **`WebClient`**:

```java
import org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl;
import org.springframework.web.reactive.function.client.WebClient;

// Snippet inside a constructor/service with webBuilder and webSsl injected:
WebClient billingReactive = webBuilder
        .baseUrl("https://billing.internal.example")
        .apply(webSsl.fromBundle("internal-ca"))
        .build();

WebClient inventoryReactive = webBuilder
        .baseUrl("https://inventory.internal.example")
        .apply(webSsl.fromBundle("internal-ca"))
        .build();
```

These are **code snippets** requiring a service/context with injected beans; they are not two standalone Java files. Only share the same trust bundle if those services genuinely belong to the same trust domain and that CA is appropriate; being "internal" does not mean every service must trust the same CA.

**A custom truststore can replace rather than automatically merge with all default Java trust anchors.** If the same client must call both public APIs and an internal CA, verify the exact trust manager construction of your HTTP client library: configuring a custom truststore can stop standard public CAs from being trusted. Do not fix that by going trust-all; instead separate clients by trust domain or build a properly managed combined truststore.

**Do not unconditionally call `System.setProperty("javax.net.ssl.trustStore", "...")`** when you only want to configure one client. That JVM property alters trust across many connections using default JSSE, creating coupling and hard-to-debug behavior. Named SSL bundles keep the blast radius clear.

## 9. Extending to mTLS: Both Client and Server Verify Certificates

Standard HTTPS TLS: the server presents a certificate, and the client verifies it. **mTLS** adds: the server requests a client certificate and verifies it against its trust material.

```text
              mTLS between two services

Service A (client)                         Service B (server)
  │                                                │
  │──── ClientHello + SNI/ALPN ────────────────────►│
  │◄─── Server certificate chain ───────────────────│
  │                                                │
  │  Validate B: chain + CA + SAN + validity        │
  │                                                │
  │◄─── Request client certificate ─────────────────│
  │──── Client certificate + proof of private key ─►│
  │                                                │
  │          Validate A: chain + client CA          │
  │◄──────────────── TLS established ───────────────►│
  │                      HTTP
```

An **mTLS client bundle** contains both:
- `keystore`: the **client certificate and client private key** issued by an appropriate CA.
- `truststore`: the **server CA** that the client accepts when calling Service B.

PEM example for outbound mTLS:

```properties
spring.ssl.bundle.pem.partner-mtls.keystore.certificate=file:/etc/tls/client/client-chain.pem
spring.ssl.bundle.pem.partner-mtls.keystore.private-key=file:/etc/tls/client/client-key.pk8
spring.ssl.bundle.pem.partner-mtls.truststore.certificate=file:/etc/tls/partner/server-ca.pem
```

The consumer references `partner-mtls` instead of `internal-ca`, e.g., `restSsl.fromBundle("partner-mtls")`. The downstream server **must be configured to request client certificates**; otherwise the client merely having key material does not turn standard HTTPS into mTLS per policy.

On an **inbound Spring Boot server**, if you want to require client certificates, the server bundle can include the server keystore and a truststore containing the CA that issues client certificates:

```properties
spring.ssl.bundle.pem.inbound-mtls.keystore.certificate=file:/etc/tls/server/server-chain.pem
spring.ssl.bundle.pem.inbound-mtls.keystore.private-key=file:/etc/tls/server/server-key.pk8
spring.ssl.bundle.pem.inbound-mtls.truststore.certificate=file:/etc/tls/client-ca.pem

server.port=8443
server.ssl.bundle=inbound-mtls
server.ssl.client-auth=need
```

This is an **alternative configuration** (do not place it alongside the `local-server` example in the same profile). `client-auth=need` requires a valid client certificate during the TLS handshake; `want` accepts a client certificate if presented without making it mandatory.

**Having a valid client cert is not enough to authorize every endpoint.** TLS authenticates the certificate at the transport layer, whereas business authorization must map the identity (subject/SAN/SPIFFE, etc.) to a trusted principal/role/tenant and enforce permissions. Never grant admin privileges simply because a client cert was signed by the same CA.

## 10. Truststores, CA Bundles, and Certificate Rotation

### 10.1. Separating Responsibilities

Manage separate bundles by **role and trust domain**:

| Bundle | What it contains | Consumer |
|---|---|---|
| `server-identity` | Application's certificate chain + private key | Embedded HTTPS server |
| `billing-ca` | Billing gateway's CA | Billing RestClient/WebClient |
| `partner-mtls` | Client cert/key + trusted partner CA | Outbound HTTP mTLS |
| `db-ca` | CA verifying database server | JDBC/R2DBC connector with bundle integration |
| `admin-server` | Dedicated certificate for management endpoints | Management server if on separate port/TLS |

Other integrations (databases, messaging, mail, etc.) **only use SSL bundles when the specific library/auto-configuration supports them**. Do not assume that defining `spring.ssl.bundle.*` makes every JDBC driver, R2DBC driver, Kafka client, or arbitrary HTTP library pick it up automatically. Check integration-specific properties such as `spring.data.redis.ssl.bundle` or the relevant SSL config in your exact Spring Boot and driver versions.

### 10.2. Rotation Is Not Simply Swapping a File

When a certificate approaches expiration or a CA changes, you need to:
1. Issue the new certificate/key and check SAN, validity, key usage, and certificate chain.
2. Distribute the new trust anchor to the **verifying** side before the **presenting** side switches certificates when changing CAs.
3. Provide an overlap period: have the truststore temporarily trust both old and new CAs if policy allows; avoid gaps that break handshakes.
4. Update certificates/keys/config and identify which components require a restart vs. which support hot reload.
5. Monitor handshake failures, certificate expiry, h2/ALPN if affected, and have a rollback plan.
6. Revoke/retire the old certificate/CA per policy once the transition window closes.

Spring Boot 3.3 supports `spring.ssl.bundle.pem.<name>.reload-on-update=true` and a file watcher in certain scenarios, with **reload-capable consumers**, documented in 3.3 as the Tomcat web server and Netty web server. Example:

```properties
spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/tls/webserver/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/tls/webserver/key.pk8
spring.ssl.bundle.pem.webserver.reload-on-update=true
server.ssl.bundle=webserver
```

**Do not misunderstand this as "all clients and libraries will hot reload."** Clients that built an `SSLContext`/connection pool once from a bundle may need recreation or a restart to pick up new trust/key material, depending on the API and version. Only confirm a component reloaded after opening a new connection and observing the live certificate. With `classpath:` paths packaged inside a JAR, the file watcher does not behave like a mutable runtime `file:` mount.

In Kubernetes, secret mount updates may change symlinks or file inodes; test watcher behavior on your specific Boot/OS version. For PKCS12/JKS and secret rotation, do not assume hot reload if consumer documentation does not commit to it.

### 10.3. Password and Secret Handling

- Use a secret manager or least-privilege environment/volume instead of committing `keystore.password` in the repo.
- Never print private keys, keystore bytes, or passwords when debugging. If logging config is needed, log only the **bundle name** and public metadata, never secret values.
- Separate keystore and truststore permissions. Public CA certificates can be shared more broadly than private keys.
- Each environment (dev/staging/prod) should have distinct trust roots/keys and a clear rollback mechanism.
- Monitor before certificate expiration; rotating a leaf certificate does not necessarily require changing the CA.
- When calling external TLS services, always enforce hostname verification. A trust anchor only proves the chain was signed by a trusted CA, not that the server matches the DNS name you intended to reach.

## 11. Techniques to Verify HTTPS, Trust, and HTTP/2

**Inspecting the public certificate:**

```bash
keytool -list -v \
  -keystore certs/truststore.p12 \
  -storetype PKCS12 -storepass changeit
```

Inspect alias, Subject, Issuer, validity, and certificate SANs. There is no need to open or print the private key.

**Checking the handshake with OpenSSL (if installed):**

```bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile certs/server.crt \
  -verify_return_error </dev/null
```

This uses Bash/macOS/Linux syntax; PowerShell handles stdin redirection differently. With valid local TLS, OpenSSL reports chain verification succeeded. When debugging servers requiring SNI, `-servername` ensures the hostname is sent so the server selects the right certificate.

**Checking HTTP/2:**

```bash
curl --http2 -v --cacert certs/server.crt \
  https://localhost:8443/ping
```

Observe the ALPN accepted protocol or HTTP version in the output. Support for `--http2` depends on the curl build. If only HTTP/1.1 appears, check server implementation, client ALPN, proxy TLS termination, or `server.http2.enabled`; **do not blame the truststore** solely for not negotiating h2 if the TLS handshake succeeded.

**Intentionally testing trust failures:**
- Try a different CA that did not sign the server certificate: the handshake must fail—never "fix" it by going trust-all.
- Try connecting with a hostname absent from the SAN: hostname verification must fail when the client validates properly.
- Try an expired certificate in a test fixture (if available): the client must reject it.
- Test rotation with old/new CA overlap and observe the behavior.
- With mTLS, test a client presenting no cert or a cert signed by a CA outside the trust domain: an inbound server with `client-auth=need` must reject it during the handshake.

**Note:** Passing `curl -k`/`--insecure` as a certificate test only proves connectivity when verification is skipped; it **does not** prove the system's trust configuration is secure.

## 12. Common Errors and Troubleshooting

| Symptom | Suspected cause | How to verify and fix properly |
|---|---|---|
| `NoSuchSslBundleException` | `fromBundle("name")` differs from declared name, or env var casing mismatch | Check key `spring.ssl.bundle.<type>.<name>`, verify lowercase name |
| `FileNotFoundException` / resource load failure | Wrong `classpath:`/`file:` path, different working directory | Check mount path, runtime cwd, file read permissions |
| `UnrecoverableKeyException` / key password failure | Wrong password or key alias | Check keystore type/alias/password with `keytool -list` |
| TLS handshake fails with "PKIX path building failed" | Client missing trusted CA/certificate | Configure proper truststore on the **client**, check chain and CA rotation |
| `No subject alternative DNS name matching` | URL hostname missing from SAN | Reissue cert with proper SAN; do not disable hostname verification |
| `SSLHandshakeException: Received fatal alert: bad_certificate` | mTLS missing client cert or cert untrusted | Check both bundles and `client-auth` |
| Server error from `server.ssl.bundle` and `server.ssl.key-store` | Conflicting configuration styles | Use only the bundle, put key/trust material in the bundle |
| Updating `server.ssl.enabled-protocols` has no effect | When using a bundle, discrete server protocol properties can be ignored | Move to `spring.ssl.bundle.<type>.<name>.options.enabled-protocols` |
| `RestClient` works, `WebClient` does not trust CA | `WebClient` uses a different connector / bundle not applied | Apply `WebClientSsl.fromBundle` to that specific builder |
| Public HTTPS client fails PKIX after adding internal truststore | Custom truststore replaced default trust anchors | Split clients by trust domain or manage a combined CA truststore explicitly |
| Only HTTP/1.1 despite HTTP/2 enabled | ALPN/client/proxy/server did not negotiate h2 | Use curl verbose, check actual TLS endpoint and server |
| Old certificate still served after rotation | Consumer does not support hot reload, pool/context not recreated | Check version support; restart/recreate client when needed |
| TLS works locally but fails in Docker | Secret not mounted properly, different cwd, permissions, or DNS/SAN mismatch | Use absolute file mounts and certificates matching real DNS |
| "Connection refused" | Server not listening or wrong port | This is a TCP/bind issue, distinct from certificate/PKIX errors |
| TLS handshake succeeds but HTTP 401/403 | Application authentication/authorization failed | Check Spring Security, tokens, roles, client identity mapping; do not blindly edit truststores |

## 13. Misconceptions to Avoid

- **An SSL bundle is not a certificate.** It is a named structure for managing keys/trust/options; certificates are just one part of it.
- **Keystore is not the same as truststore.** Server identity and client trust are two separate roles.
- **Having a bundle does not mean all connections automatically use it.** Each consumer must be wired or support the integration.
- **Adding a public CA to a truststore does not mean disabling hostname verification.** Both a valid chain and matching SAN are required.
- **`server.ssl.bundle` must not be arbitrarily mixed with discrete SSL settings.** This is an explicit constraint in Boot.
- **HTTP/2 is not automatically enabled just by having TLS.** You need `server.http2.enabled` and proper protocol negotiation.
- **mTLS does not mean the user is already authorized.** Certificate authentication and business authorization are two distinct steps.
- **`reload-on-update` is not magic for every client.** Verify reload-capable consumers and be prepared to restart when required.
- **Using `-k` does not fix trust errors.** It removes one of TLS's core protections.
- **Trust-all in development easily leaks into production.** Use a test CA/certificate with valid SANs and a dedicated truststore.
- **A PKCS12 file with multiple entries will not necessarily pick the right key automatically.** Specify the exact alias/configuration.
- **A truststore containing an internal CA is not guaranteed to include Java default roots.** Design each client's trust domain explicitly.

## 14. Self-Check Questions

**Question 1:** A browser calls HTTPS on Spring Boot. Which bundle must contain a private key?  
**Answer:** The server bundle referenced by `server.ssl.bundle`; it must contain a matching certificate and private key so the server can prove its identity.

**Question 2:** Two RestClient/WebClient instances call partners under the same internal CA. Must you duplicate the certificate path in every service class?  
**Answer:** Not when the API/consumer supports SSL bundles; declare one trust bundle and apply `RestClientSsl.fromBundle(name)` and `WebClientSsl.fromBundle(name)` to each builder.

**Question 3:** Why can TLS still fail even when the CA is already in the truststore?  
**Answer:** The certificate might not match the hostname/SAN, might be expired, the server might send an incomplete chain, the wrong bundle might be used, or TLS protocols/ciphers might be incompatible. Separate chain validation from hostname verification.

**Question 4:** Can you use `server.ssl.bundle=local-server` together with `server.ssl.key-store=...`?  
**Answer:** No, per the Spring Boot 3.3 contract; put the key material inside the bundle and have the server reference the bundle.

**Question 5:** Does `server.http2.enabled=true` prove responses are using HTTP/2?  
**Answer:** No; client and server/proxy must actually negotiate `h2`. Inspect ALPN/HTTP versions in live traffic.

**Question 6:** When rotating a CA, do you update the server certificate first or the client truststore first?  
**Answer:** Normally clients must trust the new CA **before** the server begins presenting the new chain, with trust overlap to avoid disruption; details depend on the deployment model.

**Question 7:** If HTTPS is already in place, why must you still enforce authorization?  
**Answer:** TLS authenticates the connection/peer per policy; it does not decide which endpoints or data a user/service is allowed to access.

## 15. Official Documentation for Reference

1. Spring Boot 3.3.13, **SSL** — JKS/PKCS12 bundles, PEM bundles, `SslBundles`/`SslBundle`, and reload: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
2. Spring Boot 3.3.13, **Embedded Web Servers** — `server.ssl.bundle` and HTTP/2: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
3. Spring Boot 3.3.13, **Calling REST Services** — `RestClientSsl` and `WebClientSsl`: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
4. Spring Boot 3.3.13 API, **SslBundle** — stores/managers/options/`createSslContext()`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ssl/SslBundle.html
5. Spring Boot 3.3.13 API, **SslBundles** — registry lookup by name: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ssl/SslBundles.html
6. Spring Boot 3.3.13 **Common Application Properties** — `spring.ssl.bundle.*`, `server.ssl.*`, `server.http2.enabled`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/

**Conclusion:** SSL bundles turn scattered TLS settings for keys, certificates, and truststores into **named trust/key material** that can be referenced and shared within the right trust domain. Keep identity separate from trust, use `server.ssl.bundle` for inbound HTTPS, `RestClientSsl`/`WebClientSsl` for outbound HTTPS, verify certificate chains + hostnames, and design rotation/mTLS/HTTP/2 around the actual capabilities of each consumer.