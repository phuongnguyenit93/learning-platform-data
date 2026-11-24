# Using PEM Certificates and Applying Bundles to an Embedded Server

> **Context:** Spring Boot web-runtime → TLS and HTTP/2. This lesson is based on **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+** and focuses on using **PEM certificates (PEM-encoded X.509 certificates)** with private keys to create an **SSL bundle** and apply it to an embedded HTTP server (Tomcat or Reactor Netty; differences for other containers are noted where limitations apply). Examples run with Maven, OpenSSL, and curl. Self-signed certificates in the lab are for development machines only.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **TLS**, **HTTPS**, **X.509 certificate**, **private key**, **CA/trust chain**, **PEM**, **PKCS#8**, **JKS/PKCS#12**, and **SSL bundle** without confusing their names.
2. Create a PEM private key/certificate pair for localhost with an appropriate **Subject Alternative Name (SAN)**; distinguish lab self-signed certs from CA-signed certificates used in production.
3. Correctly configure `spring.ssl.bundle.pem.<name>.keystore.certificate`, `spring.ssl.bundle.pem.<name>.keystore.private-key`, and `server.ssl.bundle` to enable HTTPS on the embedded server.
4. Run Spring Boot MVC + Tomcat on Java 17; verify the certificate, hostname, trust, and HTTPS connectivity with curl and OpenSSL instead of relying only on `-k`.
5. Understand how the same SSL bundle configuration applies when switching from Spring MVC/Tomcat to Spring WebFlux/Reactor Netty, and enable **HTTP/2 over TLS** with `server.http2.enabled`.
6. Keep private keys out of JARs in production; manage certificate chains, file permissions, certificate provisioning, rotation, and **reload-on-update** on supported containers.
7. Correctly diagnose typical TLS failures: wrong file, mismatched key, hostname mismatch, expired certificate, missing intermediate, untrusted CA on the client, misconfigured bundle, conflicts with legacy properties, and ALPN/HTTP2 issues.

## 2. Where Does TLS Operate in Spring Boot?

HTTP is a request/response protocol. **HTTPS** is HTTP transported over a connection protected by **TLS**. TLS addresses three core needs:

- **Authentication:** the client can verify the server possesses the private key matching the certificate and that the certificate is trusted per trust policy.
- **Confidentiality:** data is encrypted in transit across the connection; an observer on the wire cannot easily read the contents.
- **Integrity:** exchanged data is protected against unauthorized modification in transit under the protocol's guarantees.

The TLS handshake occurs **before** a request reaches any Spring controller. The embedded server (Tomcat/Jetty/Undertow or Reactor Netty depending on the application) initializes the SSL/TLS engine, selects the matching certificate, completes the handshake, and only then exchanges HTTP traffic.

~~~text
Client / browser / curl
    |
    |  TCP connect
    v
Embedded HTTP server :8443
    |
    |  TLS handshake:
    |    - ClientHello, SNI, ALPN, TLS versions/ciphers
    |    - server certificate chain
    |    - certificate validation + key agreement
    v
Encrypted TLS connection
    |
    |  HTTP/1.1 or HTTP/2 request
    v
Spring MVC DispatcherServlet / WebFlux DispatcherHandler
    |
    v
Controller -> Service -> Response
~~~

**A controller returning `200 OK` does not prove the TLS configuration is secure.** The client might have skipped certificate checks, or TLS might be terminated at a proxy rather than at Spring Boot. You must identify where **TLS termination** actually occurs.

### Which Embedded Server?

| Web stack | Common starter | Default embedded server | Key point to remember |
|---|---|---|---|
| Spring MVC (Servlet) | `spring-boot-starter-web` | Tomcat | Uses `server.ssl.bundle` to configure the HTTPS connector. |
| Spring WebFlux (Reactive) | `spring-boot-starter-webflux` | Reactor Netty | Also uses `server.ssl.bundle`; no need to build a Netty `SslContext` manually just to enable HTTPS. |
| MVC/WebFlux with swapped container | Jetty or Undertow when configured | Depends on dependencies | Basic TLS is supported, though hot-reload/SNI/HTTP2 features differ. |

Do not assume seeing the WebFlux dependency means the app runs Reactor Netty: when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot normally selects Servlet/MVC. Check the actual web application type and server in startup logs before diagnosing TLS.

## 3. Certificate, Private Key, Trust: Three Distinct Roles

### Server Certificate and Private Key

An **X.509 certificate** typically contains the public key, subject name, SAN, issuer, validity dates, signature algorithm, and CA signature. It can be distributed publicly to clients during the TLS handshake.

The **private key** is the server's secret. It corresponds to the public key in the certificate and is used in TLS authentication. The private key must never be sent to clients and should never appear in source code, Git, public container images, or application logs.

~~~text
Server identity:
  server.crt / fullchain.pem       [certificate or certificate chain]
  server.key / privkey.pem         [matching private key]

Client checks:
  certificate SAN matches requested host?
  certificate still valid?
  issuer chain trusted by client?
  signature and protocol requirements valid?
  server proves possession of corresponding key?
~~~

If the private key does not match the certificate, the TLS server cannot initialize properly or complete handshakes. If the certificate is valid but its SAN omits the hostname the client accesses, compliant clients will reject hostname verification.

### CA, Truststore, and Certificate Chain

A **CA (Certificate Authority)** signs certificates. For production certificates, the server usually presents its own leaf certificate plus the required **intermediate certificates**; the client verifies the chain up to a trust anchor it already trusts. A file like `fullchain.pem` normally puts the leaf before the intermediate(s). Do not confuse a client-facing certificate chain with a private key or secret root CA key.

A **truststore** is data one party uses to **trust a peer's certificates**:

- In standard HTTPS, the **server** has a certificate and private key; the **client** verifies the server via trust roots. The server **does not need** a client-CA truststore unless requiring client certificates.
- When enabling **mutual TLS (mTLS)**, the server also validates the client's certificate, so the server needs an appropriate CA/certificate trust configuration for checking clients. The client must also have its own identity certificate/private key.
- An SSL bundle can hold both identity material and trust material, but **the two serve different purposes**.

### PEM and PKCS#8

**PEM** describes encoding binary data (certificates, private keys, etc.) as Base64 text delimited by BEGIN/END lines. A certificate typically starts with `-----BEGIN CERTIFICATE-----`. A **PKCS#8** private key typically starts with `-----BEGIN PRIVATE KEY-----` or `-----BEGIN ENCRYPTED PRIVATE KEY-----`.

Spring Boot recommends PEM private keys in **PKCS#8** format whenever possible. Legacy keys in PKCS#1 (RSA) or SEC 1 (EC) use different headers and should be converted when needed. PEM is not a type of certificate authority, and a `.pem` file extension alone does not guarantee valid or matching contents.

### PEM vs. Java KeyStore

| Concept | PEM | JKS / PKCS#12 |
|---|---|---|
| Storage format | Text blocks for cert/key, often separate files | Binary keystore container that can store key/cert/trust |
| Common in | Kubernetes Secrets, Certbot/ACME, reverse proxies, container deployments | Java keystores, traditional Java applications |
| Spring Boot bundle | `spring.ssl.bundle.pem.*` | `spring.ssl.bundle.jks.*` |
| Applied to embedded server | `server.ssl.bundle=<name>` | Also `server.ssl.bundle=<name>` |
| What must be protected | Private key and file/secret read permissions | Keystore and password/key material |
| Conversion | No need to convert to PKCS#12 when using PEM bundles | Can use `keytool`/OpenSSL as needed |

**You do not need to convert every PEM certificate to `.p12`** to enable HTTPS in Spring Boot 3.3: PEM SSL bundles are supported directly.

## 4. What Problem Do SSL Bundles Solve?

Introduced in Spring Boot 3.1, an **SSL bundle** is a **named** configuration grouping the details needed to set up TLS: server identity material (certificate/private key) or client-side trust material, along with options when needed. Instead of scattering `server.ssl.key-store`, passwords, and certificate properties, you define a bundle under `spring.ssl.bundle.*` and **reference it by name** where needed.

Conceptual example:

~~~text
spring.ssl.bundle.pem.webserver  --> [certificate + private key]
                                     |
                                     v
server.ssl.bundle=webserver     --> Embedded Tomcat / Reactor Netty
                                     |
                                     v
HTTPS :8443
~~~

The name `webserver` is **user-chosen**, not a magic keyword. If you define `spring.ssl.bundle.pem.frontend.*` while setting `server.ssl.bundle=webserver`, Boot will not find the matching bundle. Use short, distinct names for server vs. client and keep them consistent across deployments.

### Configuration Layers

| Property | Meaning |
|---|---|
| `spring.ssl.bundle.pem.<name>.keystore.certificate` | Resource containing the PEM server certificate or chain. |
| `spring.ssl.bundle.pem.<name>.keystore.private-key` | Resource containing the PEM private key matching the certificate. |
| `spring.ssl.bundle.pem.<name>.truststore.certificate` | Trusted CA/certificate (useful for client-side TLS or mTLS), does not replace the identity key. |
| `server.ssl.bundle` | Specifies the bundle applied to the **embedded HTTP server**. |
| `server.port` | Server listening port, e.g., 8443. |
| `spring.ssl.bundle.pem.<name>.reload-on-update` | Watches material files for reloads on supported servers (Tomcat/Netty in Boot 3.3). |
| `server.http2.enabled` | Enables HTTP/2; with HTTPS, negotiates h2 via TLS/ALPN when container/client support it. |

The `spring.ssl.bundle.pem...` properties **only define the bundle**. They do **not** make the embedded server use the bundle until `server.ssl.bundle` is set or another consumer references that name.

## 5. Lab: Creating a PEM Certificate for localhost

This lab uses OpenSSL 1.1.1 or 3.x with `-addext` support, Maven 3.x, and Java 17+. Perform it in a fresh test project directory. **Do not use this self-signed certificate/key in production**.

### 5.1. Sample Directory Layout

~~~text
pem-ssl-demo/
  pom.xml
  src/
    main/
      java/
        example/
          pemserver/
            PemServerApplication.java
      resources/
        application.properties
        tls/
          localhost.crt
          localhost.key
~~~

Create `src/main/resources/tls/` before running OpenSSL.

### 5.2. Generate a PKCS#8 RSA Private Key

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out src/main/resources/tls/localhost.key
~~~

`openssl genpkey` creates a PKCS#8-encoded PEM private key, typically with header `BEGIN PRIVATE KEY`. RSA 2048 is used here for lab compatibility; production must follow current security policies and organizational key lifecycles. **Protect the private key file**: on Linux/macOS, restrict read access to the owner via `chmod 600 src/main/resources/tls/localhost.key`. On Windows, use appropriate ACLs/secret stores.

### 5.3. Generate a Self-Signed Certificate with SAN

~~~bash
openssl req -new -x509 -sha256 -days 7 -key src/main/resources/tls/localhost.key -out src/main/resources/tls/localhost.crt -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
~~~

This creates a self-signed certificate valid for **7 days from creation**; the SAN lists both DNS `localhost` and IP `127.0.0.1`, enabling tests against both URLs. The validity period and hosts here are only for the lab. A **self-signed certificate is not trusted by browsers/curl by default**, so we will pass `--cacert` during testing.

This is **not** a certificate issued by a public CA. A self-signed certificate can be explicitly trusted by a client via trust anchor configuration, but never confuse "handshake succeeded with verification disabled" with "a trusted certificate chain."

### 5.4. Verify PEM Files Before Configuring Boot

~~~bash
openssl pkey -in src/main/resources/tls/localhost.key -check -noout
openssl x509 -in src/main/resources/tls/localhost.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

Expect both commands to succeed without errors; the certificate output shows a subject with `CN=localhost`, SANs `DNS:localhost` and `IP Address:127.0.0.1`, and the actual validity dates. Because serial numbers, timestamps, and OpenSSL versions vary, **there is no single fixed stdout**.

Verify that the public key extracted from the certificate matches the private key by comparing the SHA-256 digests of the DER public keys:

~~~bash
openssl x509 -in src/main/resources/tls/localhost.crt -pubkey -noout | openssl pkey -pubin -outform DER | openssl dgst -sha256
openssl pkey -in src/main/resources/tls/localhost.key -pubout -outform DER | openssl dgst -sha256
~~~

Both digests should **match**. This check does not rely on RSA modulus comparisons (which do not apply to every key algorithm). It checks public key matching, **not** certificate chains, SANs, or trust policies.

**Security note:** the key file is placed under `src/main/resources` solely to make the demo self-contained; building the JAR embeds it into the archive. Therefore, never commit this file to Git, distribute the test JAR, or treat this as a production deployment pattern. The production section below moves to mounted files outside the artifact.

## 6. Runnable Spring Boot MVC + Tomcat Project

This project uses **Spring Boot 3.3.13** and Java 17. Other 3.3.x releases can be used if the BOM/plugins are compatible. We use Maven so you have the full build definition rather than assuming an existing Gradle setup.

### 6.1. Complete pom.xml

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

    <groupId>example</groupId>
    <artifactId>pem-ssl-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>pem-ssl-demo</name>

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

`spring-boot-starter-web` brings in Tomcat by default; you do **not** need to build a WAR or manually register a Servlet connector just to enable HTTPS on a port.

### 6.2. Complete Java File

Create `src/main/java/example/pemserver/PemServerApplication.java`:

~~~java
package example.pemserver;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PemServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(PemServerApplication.class, args);
    }

    @RestController
    static class HelloController {

        @GetMapping("/hello")
        public String hello() {
            return "TLS OK";
        }

        @GetMapping("/api/status")
        public ResponseEntity<Map<String, String>> status() {
            return ResponseEntity.ok(Map.of(
                    "service", "pem-ssl-demo",
                    "status", "ready"
            ));
        }
    }
}
~~~

This is a **complete** Java application class in package `example.pemserver`, containing a nested `@RestController` discovered by component scanning. `/hello` returns the text `TLS OK`; `/api/status` returns JSON with two keys (JSON key ordering is not guaranteed). The controller knows nothing about the private key and never touches `SSLContext` manually; Boot configures the embedded server before requests ever reach handlers.

### 6.3. Complete application.properties

Create `src/main/resources/application.properties`:

~~~properties
# HTTPS listener of the embedded web server
server.port=8443

# Define a bundle named "webserver" from PEM resources
spring.ssl.bundle.pem.webserver.keystore.certificate=classpath:tls/localhost.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=classpath:tls/localhost.key

# Instruct the embedded server to apply the defined bundle
server.ssl.bundle=webserver
~~~

This is the **core of the lesson**:

- `spring.ssl.bundle.pem.webserver...` = **declaring the bundle**.
- `server.ssl.bundle=webserver` = **applying the bundle to the embedded HTTP server**.
- `server.port=8443` = the HTTPS port you will call.

Both the certificate and private key sit on the JAR classpath, so the demo resource paths start with `classpath:tls/`. Property names **differ** from legacy `server.ssl.certificate-private-key`: in a bundle, the PEM property is `keystore.private-key`.

You do not need to explicitly set `server.ssl.enabled=true` for this demo once `server.ssl.bundle` is properly configured; do not set `server.ssl.enabled=false` and expect HTTPS to still run.

### 6.4. Running the Application and Testing HTTPS

From the project root, after creating the files:

~~~bash
mvn spring-boot:run
~~~

Or build an executable JAR and run it:

~~~bash
mvn clean package
java -jar target/pem-ssl-demo-0.0.1-SNAPSHOT.jar
~~~

Both options require Maven/Java 17 installed and port 8443 free. When the server starts successfully, it listens for HTTPS on port 8443. It does **not** simultaneously open a plaintext HTTP port on 8080 merely because Spring Boot defaults to 8080 without SSL.

Call with curl while trusting the self-signed certificate **intentionally**:

~~~bash
curl --cacert src/main/resources/tls/localhost.crt -i https://localhost:8443/hello
curl --cacert src/main/resources/tls/localhost.crt -i https://127.0.0.1:8443/api/status
~~~

Expect HTTP 200 and exact body `TLS OK` for the first request. The second returns JSON containing `service=pem-ssl-demo` and `status=ready`. The certificate contains SANs for both `localhost` and `127.0.0.1`, so hostname validation succeeds when the client trusts that certificate, it is unexpired, and the TLS stack accepts the algorithms.

**Do not use `curl -k` or `--insecure` as acceptance verification:** they skip certificate/hostname checks. `-k` can help quickly isolate trust errors from transport errors in a lab, but a connection that succeeds only by disabling verification **does not prove server identity was authenticated**.

### 6.5. Verifying Plaintext HTTP Is Rejected

~~~bash
curl -v http://localhost:8443/hello
~~~

This sends unencrypted HTTP to an HTTPS port; you should see the request fail—e.g., rejected or returning an error depending on the connector—and **not** receive a valid HTTPS response. Do not assume every curl error across server versions is the exact same exception.

If you call `http://localhost:8080/hello` with only the config above, port 8080 is no longer created by Boot as a second HTTP listener. Spring Boot 3.3 does **not** have a single `application.properties` setting to create both an HTTP connector and an HTTPS connector on the same server; having both requires adding a connector programmatically/via container or placing a reverse proxy in front.

## 7. Inspecting the Certificate and TLS Handshake Separately

Use OpenSSL to inspect the connection to the embedded server:

~~~bash
openssl s_client -connect localhost:8443 -servername localhost -CAfile src/main/resources/tls/localhost.crt -verify_hostname localhost
~~~

A valid lab handshake prints chain info, TLS version, cipher, and verification status, typically showing `Verify return code: 0 (ok)` when the certificate is trusted by the client and the hostname matches. Exact output varies by OpenSSL/JDK/cipher, so **there is no fixed transcript** to copy. You can add `-verify_return_error` if you want OpenSSL to exit on verification failure.

To see the exact certificate the server presents:

~~~bash
openssl s_client -connect localhost:8443 -servername localhost -showcerts
~~~

Check the subject, SAN, validity dates, and chain. When serving multiple hostnames via SNI, `-servername` is critical to confirm which bundle/certificate is selected. Omitting SNI may cause the server to return a default certificate instead of the virtual hostname's certificate.

### Distinguishing Verification Steps

| Check | What does it prove? | What does it NOT prove? |
|---|---|---|
| `openssl x509 -in file.crt -noout -text` | The file parses cleanly and shows subject, SAN, validity/extensions | That the server loaded this file or clients will trust it |
| Matching public key digests from cert and key | The key and cert share the same public key | That the CA chain/hostname and client policies are valid |
| `curl --cacert cert ...` passes verification | Under curl's trust policy, TLS identity for the host was verified | That public CAs trust the cert or the overall security architecture is sound |
| `curl -k ...` succeeds | The transport layer can handshake with verification disabled | Any guarantee about hostname, trust, or issuer |
| `openssl s_client ... -servername` | Observes the TLS handshake and certificate sent by the server | That Spring controllers/authorization after the handshake work properly |
| `curl --http2 ...` shows h2 | Client and endpoint negotiated HTTP/2 (if curl supports it) | That upstream proxy hops/backends also run HTTP/2 |

If a certificate is expired, the server can sometimes still start, while clients reject it during validation. Check both startup logs **and** a real TLS client.

## 8. Writing the Same Configuration in application.yaml

If your project uses YAML instead of properties, the equivalent configuration is:

~~~yaml
server:
  port: 8443
  ssl:
    bundle: webserver

spring:
  ssl:
    bundle:
      pem:
        webserver:
          keystore:
            certificate: "classpath:tls/localhost.crt"
            private-key: "classpath:tls/localhost.key"
~~~

Do not put the same settings in both `application.properties` and `application.yaml` and create ambiguity about which Boot loads or prioritizes. In real applications, configure via Spring profiles, environment variables, or a configuration service; keep track of property precedence and **never log the PEM private-key value**.

### Bundle Names and Environment Variables

A PEM bundle name like `webserver` is a logical identifier. Boot documentation notes that **when configuring bundles via environment variables, the bundle name is converted to lowercase**. Therefore, stick to simple lowercase names when relying on environment variables or Kubernetes config injection, and use the exact same name in `server.ssl.bundle`.

With dev/prod profiles, each profile can point `webserver` to different certificates; how it is applied remains `server.ssl.bundle=webserver`.

## 9. Using External PEM Files Outside the JAR in Production

You should never package **production private keys** inside a JAR. A common deployment layout is:

~~~text
app.jar                                 [application artifact, contains no key]
/etc/myapp/tls/fullchain.pem            [leaf certificate + intermediate(s)]
/etc/myapp/tls/privkey.pem              [private key, restricted read permissions]
~~~

`application-prod.properties` can be written as:

~~~properties
server.port=8443
server.ssl.bundle=webserver

spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/myapp/tls/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/myapp/tls/privkey.pem
~~~

In Linux/Kubernetes deployments, `file:/...` paths must exist **inside the runtime container/host** where the JVM runs—not on a developer's laptop. The certificate chain in `fullchain.pem` must follow the proper order/issuer per your certificate tooling; the private key must match the leaf certificate's public key. Never place a root CA private key on an application server.

In Kubernetes, use a read-only Secret volume containing the certificate/key and point the paths to the mount. Restrict process read permissions; avoid storing keys in ConfigMaps or source control. In cloud environments, consider a secret manager or ACME automation/certificate manager instead of copying files manually.

**Another option** supported by Boot is inline PEM or Base64 values prefixed with `base64:` for the corresponding properties. This can be handy when injecting through a config/secret provider, though it increases exposure risk via logs, environments, debug tools, or exported configs. Never paste raw private keys into issues, screenshots, or public docs.

### Question: Does the Server Need a Truststore?

For **one-way HTTPS server authentication**, the server normally only needs its **identity** (certificate + private key). Clients/browsers use their own truststores/root stores to verify the server. Adding `spring.ssl.bundle.pem.webserver.truststore.certificate` does not make Internet clients automatically trust your self-signed certificate. For clients to trust it, there must be a chain from a CA they trust or an explicitly installed trust anchor.

A server truststore becomes clearly relevant when enabling **mTLS** so the server can validate client certificates; see section 13.

## 10. Do Not Mix server.ssl.bundle with Legacy SSL Settings

Spring Boot still supports traditional SSL configuration properties:

~~~properties
# Direct configuration example (CHOOSE ONE APPROACH, DO NOT COMBINE WITH BUNDLE)
server.ssl.certificate=classpath:tls/localhost.crt
server.ssl.certificate-private-key=classpath:tls/localhost.key
~~~

However, once you set:

~~~properties
server.ssl.bundle=webserver
~~~

do **not combine** it with discrete certificate/private-key or JKS keystore properties under `server.ssl` such as:

- `server.ssl.key-store` / `server.ssl.key-store-password`;
- `server.ssl.certificate` / `server.ssl.certificate-private-key`;
- `server.ssl.trust-certificate` in the direct style.

Spring Boot 3.3 documentation explicitly states that `server.ssl.bundle` **cannot be combined** with discrete JKS/PEM options under `server.ssl`. In particular, properties such as `server.ssl.ciphers`, `server.ssl.enabled-protocols`, and `server.ssl.protocol` **are ignored when using a bundle**; place protocol/cipher options under `spring.ssl.bundle.<type>.<name>.options` according to your Boot version's property metadata.

**Common mistake:** copying an old guide with `server.ssl.key-store` and adding `server.ssl.bundle` to the same file. That leaves the application without a reliable single configuration; remove one branch rather than "trying more properties."

## 11. The SslBundles API and Reusing Bundles in the Application

Spring Boot automatically registers an `SslBundles` bean for bundles declared via `spring.ssl.bundle.*`. Each bundle has a name and can be retrieved to construct TLS objects for client libraries with suitable integrations.

Illustrative **snippet inside a Spring-managed component**:

~~~java
package example.pemserver;

import javax.net.ssl.SSLContext;

import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.stereotype.Component;

@Component
public class SslInspection {
    private final SslBundles bundles;

    public SslInspection(SslBundles bundles) {
        this.bundles = bundles;
    }

    public SSLContext contextForWebserver() {
        SslBundle bundle = bundles.getBundle("webserver");
        return bundle.createSslContext();
    }
}
~~~

This is a **complete Java class** if added as `SslInspection.java` in the example app, though the method is never invoked automatically and is not needed for the HTTPS server to run. Use it only when a client library or custom integration genuinely needs an `SSLContext`.

An `SslBundle` exposes API methods including:

- `getStores()`: accesses the key store/trust store and related metadata;
- `getManagers()`: key managers and trust managers;
- `createSslContext()`: creates an `SSLContext`;
- other options/protocol/key details matching the configuration.

**Do not confuse a server identity bundle with a client trust bundle.** Reusing a server private key for outbound HTTP clients is not always appropriate. If the app calls an external API and needs to trust that API's custom CA, define a **separate bundle for outbound clients** containing the required trust certificate.

Example defining another trust bundle:

~~~properties
spring.ssl.bundle.pem.partnerclient.truststore.certificate=file:/etc/myapp/tls/partner-ca.pem
~~~

Compatible client integrations can then reference `partnerclient` via Spring Boot/HTTP client mechanisms. This snippet **only declares the bundle**; it does not automatically reconfigure every custom HTTP client running in the app.

## 12. SSL Bundles and Spring WebFlux / Reactor Netty

For a WebFlux application, replace the Maven web starter with:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

This is a **replacement dependency snippet** for a different project; do not add it alongside the MVC starter in this lab. With the default embedded Reactor Netty, `server.port`, `spring.ssl.bundle.pem.webserver...`, and `server.ssl.bundle=webserver` play the exact same role in declaring/applying the HTTPS server's identity.

A simple WebFlux controller:

~~~java
package example.reactivepem;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("TLS OK");
    }
}
~~~

This class **is not a standalone runnable application by itself**; it needs `@SpringBootApplication`, the WebFlux starter, and the certificates/properties as in the lab. The difference lies in the web stack/HTTP handling after TLS, not in how the bundle is defined. With Reactor Netty, Boot applies the SSL bundle via auto-configuration; you do not need to write `HttpServer.secure(...)` manually just for a default HTTPS connector.

**Important:** the TLS handshake does not turn blocking application code into non-blocking code. If a WebFlux handler performs blocking JDBC calls or synchronous file I/O on the event loop, throughput can still suffer even when HTTPS is properly configured. SSL and reactive runtime concurrency are separate concerns.

## 13. mTLS: Applying a Trust Certificate to the Embedded Server

One-way HTTPS: the client verifies the server. **Mutual TLS (mTLS)**: the server also requires or requests a certificate from the client. In Spring Boot 3.3, you can put server trust material in the bundle and enable client-auth on the server.

Example **only for environments that already have a CA issuing suitable client certificates**:

~~~properties
server.port=8443
server.ssl.bundle=webserver
server.ssl.client-auth=need

spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/myapp/tls/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/myapp/tls/privkey.pem
spring.ssl.bundle.pem.webserver.truststore.certificate=file:/etc/myapp/tls/client-ca.pem
~~~

- `keystore.certificate` + `keystore.private-key` = **server identity**;
- `truststore.certificate` = CA/certificate used to **trust client identities**;
- `server.ssl.client-auth=need` = requires a valid client certificate for the TLS handshake;
- `server.ssl.client-auth=want` = may request one without mandating it; identity/authorization must still be checked at the application layer if required by policy.

Do not swap `need` for `want` expecting equivalent security. After TLS client authentication, **authorization is still necessary**: a valid certificate does not automatically grant all application permissions. Depending on your model, map identity from SAN/subject to a service account/role and manage revocation/rotation.

With a client holding an identity certificate/key trusted by the server's CA, curl can call:

~~~bash
curl --cacert server-ca.pem --cert client.crt --key client.key https://api.example.test:8443/hello
~~~

The files in this command represent **actually issued PKI artifacts**; the command will not run with the lab localhost cert unless you generate CA/client certificates. Depending on client, key algorithm, certificate chain, and TLS handshake settings, extra options may be needed. Verify that requests without a client certificate are rejected at the handshake level when the policy is `need`.

## 14. Enabling HTTP/2 on an HTTPS Server Configured with a Bundle

**TLS and HTTP/2 are related but not identical.** Working HTTPS does not mean HTTP/2 is enabled. Spring Boot provides:

~~~properties
server.http2.enabled=true
~~~

Combined with the lab bundle:

~~~properties
server.port=8443
server.ssl.bundle=webserver
server.http2.enabled=true

spring.ssl.bundle.pem.webserver.keystore.certificate=classpath:tls/localhost.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=classpath:tls/localhost.key
~~~

**HTTP/2 over TLS** is typically negotiated via the **ALPN** extension. Client and server can select `h2` or fall back to `http/1.1` depending on TLS version, stack, and ALPN support. On Spring Boot 3.3, Tomcat 10.1.x and Reactor Netty support HTTP/2 when appropriately configured; Jetty requires the appropriate HTTP/2 dependencies.

### Verifying HTTP/2 in Practice

~~~bash
curl -V
curl --http2 --cacert src/main/resources/tls/localhost.crt -v https://localhost:8443/hello
~~~

`curl -V` must list HTTP2 support; if not, that curl binary cannot run this test. In verbose output, look for ALPN info and the HTTP version actually negotiated. When working properly, the request may show `HTTP/2 200` or equivalent output depending on curl version. The body remains `TLS OK`.

You can check ALPN with OpenSSL:

~~~bash
openssl s_client -connect localhost:8443 -servername localhost -CAfile src/main/resources/tls/localhost.crt -alpn h2,http/1.1
~~~

If negotiated successfully, the selected ALPN protocol is shown. Do not treat passing `-alpn h2` on the client as proof the server accepted `h2`; check the **negotiated protocol**.

**Proxy note:** if nginx/ingress terminates TLS and speaks HTTP/2 with browsers while connecting to Spring Boot via HTTP/1.1, clients still see h2 externally. This does not prove Spring Boot's embedded backend uses HTTP/2. Inspect the exact hop you care about.

### h2 vs. h2c

- `h2`: HTTP/2 over TLS, normally used with HTTPS and ALPN.
- `h2c`: HTTP/2 without TLS (cleartext), usable on some internal hops when the stack/infrastructure supports it.
- Enabling `server.http2.enabled=true` when SSL is disabled can result in an h2c setup depending on server behavior; it is not HTTPS.

Product security policies determine whether h2c is acceptable on internal hops or end-to-end encryption is mandatory. HTTP/2 **does not by itself solve** certificate validation, rotation, client-auth, resource limits, or authorization.

## 15. Direct HTTPS on the JVM or TLS Termination at a Reverse Proxy?

Two common architectures:

~~~text
A. TLS terminates at Spring Boot:
Browser --HTTPS--> embedded Tomcat/Netty :8443
                      |
                      v
                    Controller

B. TLS terminates at ingress:
Browser --HTTPS--> CDN/ingress/proxy :443
                      |
                      | Internal HTTP or HTTPS re-encryption
                      v
              Spring Boot :8080 / :8443
~~~

**Model A:** Spring Boot needs the identity certificate/private key/bundle on the embedded server. The JVM manages the TLS listener and can use `reload-on-update`. You must manage key files and application read permissions.

**Model B:** certificates for the public domain can be managed by the ingress/proxy. The Spring Boot backend may listen only on HTTP in a trusted network, so it **does not necessarily need `server.ssl.bundle`** for client-facing connections. If the proxy → app hop also needs TLS (internal mTLS, zero-trust, compliance), configuring a bundle on the backend is still required.

Do not conclude the app is "HTTPS end-to-end" merely from seeing `https://` in the browser: map out every hop. If the proxy populates `X-Forwarded-Proto` or standard `Forwarded`, Spring Boot has settings to handle forwarded headers per environment, but **only trust headers from controlled proxies**; never accept them from arbitrary clients to determine URL redirects or secure-cookie handling.

## 16. SNI: Serving Multiple Certificates for Different Hostnames

SNI (*Server Name Indication*) lets the client declare the server name in `ClientHello`, helping the server choose the right certificate for that hostname. Spring Boot 3.3 provides `server.ssl.server-name-bundles` on embedded servers that support the feature.

Assuming a default bundle `webserver` and a second bundle `tenant2` exist, you can declare:

~~~properties
server.port=8443
server.ssl.bundle=webserver

server.ssl.server-name-bundles[0].server-name=tenant2.example.test
server.ssl.server-name-bundles[0].bundle=tenant2
~~~

This is an **additional configuration snippet**, requiring you to define bundle `tenant2` with a certificate matching that hostname. Otherwise the configuration is incomplete. In Boot 3.3, SNI bundle mapping support depends on the embedded server: Tomcat, Netty, and Undertow support it; Jetty has its own SNI/container mechanism rather than the exact property API above.

The default `webserver` bundle remains important for connections without SNI or not matching any mapping. Creating an SNI mapping does not replace checking SANs/trust on each certificate. When testing, use the exact hostname and `openssl s_client -servername tenant2.example.test` pointing at the corresponding IP/service.

## 17. Rotating and Reloading PEM Certificates

Certificates expire. Production requires a plan for issuance, expiry monitoring, renewal, deploying new material, and verifying the server presents the new leaf certificate. **Spring Boot does not automatically request/renew Let's Encrypt certificates**; you need an ACME client/certificate manager or PKI workflow.

Spring Boot 3.3 supports **reloadable SSL bundles** with compatible consumers; official documentation names **Tomcat web server** and **Netty web server** as consumers compatible with `reload-on-update`. This is an important limitation: **do not assume Jetty or Undertow shares the same hot-reload behavior**.

Production example using PEM files outside the JAR:

~~~properties
server.port=8443
server.ssl.bundle=webserver

spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/myapp/tls/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/myapp/tls/privkey.pem
spring.ssl.bundle.pem.webserver.reload-on-update=true
~~~

When the certificate/private key files change, the file watcher checks the new material and the bundle can reload, letting compatible server consumers apply the new certificate. You can configure the watcher delay via `spring.ssl.bundle.watch.file.quiet-period`, helping avoid reloading mid-way through a multi-file update.

### Rotation Risks to Handle

1. **Cert and key must stay synchronized:** updating one file at a time can briefly create a mismatched pair. Use an appropriate atomic update / deployment transaction strategy, then verify reload.
2. **Chain must be complete:** provide the leaf + intermediate bundle properly, not a bare leaf missing its issuer.
3. **Permissions:** updates can alter ownership, permissions, symlinks, or mounts; the JVM must retain read access to the new material.
4. **Existing connections:** rotation does not mean all currently open TLS sessions immediately re-handshake. Verify behavior on new connections, connection reuse, and long-lived HTTP/2 connections.
5. **Do not assume reload always succeeds:** parse errors, key mismatches, permissions, watcher limits, or unsupported containers can break it. Monitor logs/metrics and probe externally to confirm the new certificate.
6. **Keep secrets confidential:** old private keys may still reside in backups, volume snapshots, or archives. Revocation/rotation workflows must account for leak exposure and secret disposal.

With Certbot/Let's Encrypt, `/etc/letsencrypt/live/<domain>/fullchain.pem` and `privkey.pem` are usually symlinks into `archive`. Boot documentation notes that the file watcher tracks symlink targets appropriately to detect updates; nevertheless, test on your exact deployment filesystem/container runtime.

Do not turn on `reload-on-update=true` in a lab using `classpath:tls/localhost.crt` embedded in the JAR and expect editing source files on disk to hot-swap the running JAR's certificate. Reloading is meant for when the server reads **physical files** at runtime.

## 18. Diagnosing TLS Errors in Order

### 18.1. Server Fails to Start: Wrong Resource Path

**Symptom:** startup exception indicating certificate/private key could not be found or SSL material failed to load.

**Checks:**

- Does `classpath:tls/localhost.crt` exist under `src/main/resources/tls/` and get packaged into the JAR?
- Is the resource in the executable JAR under `BOOT-INF/classes/tls/...` or excluded by the build?
- Does `file:/etc/myapp/tls/...` actually exist **inside the container**?
- Does the JVM user have read permission on the file?
- Does the bundle name in `server.ssl.bundle` match `spring.ssl.bundle.pem.<name>`?

Avoid relative paths tied to the current working directory when resources belong on the classpath, as IDE/Docker/production environments have different working directories.

### 18.2. Unreadable PEM Key

**Symptom:** exception parsing private key, unsupported key format, invalid PEM header, or password error.

**Common causes:** PKCS#1/SEC 1 file instead of PKCS#8; truncated PEM, altered encoding, encrypted private key without password configured; file contains a certificate instead of a key.

For an unencrypted legacy key, you can convert to PKCS#8:

~~~bash
openssl pkcs8 -topk8 -nocrypt -in old-server.key -out server-pkcs8.key
~~~

This creates an **unencrypted** PKCS#8 private key, so protect the file with access controls/secret storage. If production policy requires an encrypted private key, use the password options supported by your Boot version and a secret manager; never paste passwords directly into shared docs.

### 18.3. Certificate and Private Key Do Not Match

**Symptom:** failure initializing TLS key material or handshake failure.

Verify using the two DER public-key digests in section 5.4. If they do not match, do not force-pair the mismatched key/cert; retrieve the matching key from your PKI process or issue a new certificate.

### 18.4. curl Reports Self-Signed / Unable to Get Local Issuer

**Meaning:** the client cannot build a chain to a trusted CA, or an intermediate is missing. For the self-signed demo, pass `--cacert localhost.crt` to grant trust explicitly. Production requires a valid chain and trusted CA; do not "fix" it with `-k`.

When a chain misses an intermediate, the server may start cleanly while clients fail verification. Check `fullchain.pem`, leaf/intermediate ordering, and client truststores.

### 18.5. Hostname Mismatch

**Symptom:** certificate is invalid for the URL hostname or IP requested. Check SAN:

~~~bash
openssl x509 -in src/main/resources/tls/localhost.crt -noout -ext subjectAltName
~~~

If the SAN only has `DNS:localhost`, requests to `https://127.0.0.1` can fail. Do not just fix CN; modern clients verify names via SAN. The certificate must list appropriate DNS or IP SANs, and public URLs must match the issued hostname.

### 18.6. Certificate Expired or Not Yet Valid

~~~bash
openssl x509 -in src/main/resources/tls/localhost.crt -noout -dates
~~~

`notBefore` and `notAfter` must align with real time on client/server; clock skew causes validation failures. Monitor expiry ahead of time rather than waiting for production handshakes to break.

### 18.7. server.ssl.bundle Conflicts with Legacy SSL Config

Remove discrete certificate/key-store properties under `server.ssl` when choosing a bundle. Remember `server.ssl.ciphers` and `server.ssl.enabled-protocols` do not control bundles as you might expect; check bundle options for your exact Boot version. Use `--debug`/condition logs in a controlled setting when startup config is unclear, without enabling debug that exposes secrets in public environments.

### 18.8. HTTP 8080 Stops Working After Enabling HTTPS

You configured an HTTPS connector on `server.port=8443`. Boot does not automatically keep plaintext HTTP on port 8080. This is normally **expected behavior**, not a bug. If you want an HTTP → HTTPS redirect, configure it at a trusted proxy/ingress or programmatically add an HTTP connector when architecture requires it.

### 18.9. HTTP/2 Is Not Negotiated

Check in order:

1. Is `server.http2.enabled=true` in the effective config?
2. Did you call `https://` on the TLS-enabled port?
3. Does curl support HTTP2? Check `curl -V`.
4. In verbose output, did ALPN actually select `h2`?
5. Which embedded server is running (Tomcat/Netty/Jetty)? Does Jetty have the extra HTTP2/ALPN dependencies?
6. Is a TLS-terminating proxy in the middle speaking h2 to clients and h1 to the backend?
7. Client/server may validly fall back to HTTP/1.1; do not assume h2 solely from seeing body `TLS OK`.

### 18.10. Certificate Reload Has No Effect

Check: using external `file:` resources outside the JAR, `reload-on-update` on the right bundle, consumer is Tomcat/Netty on Boot 3.3, file watcher sees changes (including symlinks), cert/key match, permissions, and startup logs. Use a **new TLS connection** and `openssl s_client` to inspect the served serial/expiry instead of relying on a browser reusing an existing HTTP/2 connection.

### 18.11. Proxy Succeeds but App Logs Show No TLS

TLS may already be terminated at the ingress. Distinguish which port and hop your tool is testing. `server.ssl.bundle` is not mandatory on the backend when the proxy → backend model uses controlled internal HTTP.

## 19. Production Security: Mandatory Checklist

- **Separate identity and trust:** server private key is secret; certificate chain is normally public; truststore defines trusted peer CAs.
- **Lifecycle management:** who issues, who renews, when it expires, who rotates, how to revoke, pre-expiry alerts, and fallback workflow.
- **Exact hostname/SAN:** issue certs for production DNS names; avoid self-signed localhost certs or overly broad wildcards when unnecessary.
- **Modern TLS config:** choose versions/ciphers matching policy/security baselines and client support; do not re-enable legacy protocols for a single incompatible client without formal approval.
- **Key access control:** secret volume, filesystem ACL, least-privilege user; no log/key dumps, no Git commits, no keys baked into container images.
- **Certificate chain and trust:** complete intermediates, trust valid roots/trust anchors, avoid trusting unnecessary CAs.
- **mTLS when needed:** configure client-auth and client CAs properly; do not treat mTLS as a substitute for app authorization or resource-level access control.
- **Do not use `--insecure` as a test standard:** acceptance tests must enforce hostname/chain validation.
- **Runtime observability:** handshake failures by category, certificate expiry, HTTPS connection counts, HTTP/2 negotiation, and renewal/reload outcomes.
- **Multi-hop architecture:** diagram client → CDN → ingress → service; verify which hops use TLS and who holds keys.
- **Deployment rotation:** update cert/key atomically/consistently, verify on new connections, and roll back if reload fails.
- **Additional scope:** TLS protects data in transit; it does not prevent XSS, SQL injection, broken authorization, or credential theft at endpoints.

## 20. Testing and Reporting Results

A complete lab run should record the following information:

~~~text
Runtime:
  Spring Boot: 3.3.x
  Java: 17+
  Embedded server: Tomcat (MVC) or Reactor Netty (WebFlux)
  Port: 8443
  Source of key material: classpath (lab) or mounted file (production)

Identity material:
  certificate subject
  SAN
  notBefore / notAfter
  issuer chain
  public-key match test result

TLS checks:
  openssl pkey -check passed
  curl --cacert https://localhost:8443/hello -> 200 TLS OK
  hostname/IP SAN verified
  no --insecure flag used for acceptance
  curl http://localhost:8443 -> not valid plaintext HTTP

HTTP/2 checks, if enabled:
  curl -V shows HTTP2 support
  ALPN negotiated protocol
  HTTP response version observed

Production/rotation checks, if applicable:
  externally mounted key and certificate
  access permissions
  refresh/reload policy
  new-handshake certificate serial/expiry
  no secret leaked in logs/artifact
~~~

**Do not state unverified metrics.** A 200 status from curl proves the endpoint is reachable with the configured certificate trust; to claim "HTTP/2 is active," you must observe the actual HTTP version. To claim "rotation succeeded," compare the cert serial/fingerprint or validity window on a **new connection**.

### Exercise A – Rename the Bundle

Rename `webserver` to `frontend` in all `spring.ssl.bundle.pem.webserver...` lines and `server.ssl.bundle`. Restart and verify HTTPS. Intentionally rename only one side first, predict the bundle lookup error, and inspect the startup exception.

### Exercise B – Verify SAN

Create a certificate containing only `DNS:localhost`, call it via IP and via hostname with `--cacert`. Observe the difference. Explain why CN is insufficient for modern hostname validation.

### Exercise C – Switch from Classpath to File Mount

Move `localhost.crt` and `localhost.key` to a folder outside the project, update properties to `file:/...`, and rerun. Verify file permissions and ensure the private key is absent from the production JAR.

### Exercise D – HTTP/2 over TLS

Add `server.http2.enabled=true`, run `curl -V`, `curl --http2 -v --cacert ...`, and record the negotiated ALPN. Distinguish negotiated `h2` from merely passing `--http2` on the request.

### Exercise E – Test Rotation

Only in a local lab, use external files outside the JAR and `reload-on-update=true` on Tomcat/Netty. Issue a new certificate with valid SAN and matching key, swap consistently, test new handshakes, and record timestamps/fingerprints. Note how non-atomic file updates can create a brief cert/key mismatch window.

### Exercise F – Multi-Hop TLS Diagram

Diagram a system with browser → HTTPS ingress → internal HTTP Spring Boot. Indicate where the bundle lives, who holds the public-domain private key, and whether TLS is needed for ingress → backend. If internal mTLS is added, which parties need identity and trust material?

## 21. Review Questions with Answers

**1. Is merely defining a PEM SSL bundle under `spring.ssl.bundle.pem.*` enough to enable HTTPS on the embedded server?**  
No. A consumer must apply the bundle—for example `server.ssl.bundle=webserver`—along with a server port and valid certificate/key.

**2. Are a PEM certificate and a private key the same kind of file?**  
No. A certificate contains the public key and published X.509 metadata; the private key is secret. Both can be PEM-encoded, but they do not share content or roles.

**3. Why should you use PKCS#8?**  
Because Spring Boot recommends PKCS#8 PEM private keys for broader compatibility; this format typically uses the `BEGIN PRIVATE KEY` header (or its encrypted variant).

**4. Can a localhost self-signed certificate be tested without `curl -k`?**  
Yes. Use `curl --cacert localhost.crt https://localhost:8443/hello` to explicitly trust the lab certificate while still verifying the hostname.

**5. Can `server.ssl.bundle` be used together with `server.ssl.certificate-private-key`?**  
No. When using a bundle, do not mix discrete JKS/PEM properties under `server.ssl`.

**6. Does a standard HTTPS server need a client-CA truststore?**  
Not necessarily. The server primarily needs an identity certificate/key; trust certificates are for peer verification, especially mTLS.

**7. If a certificate SAN only lists `localhost` but a client connects to `127.0.0.1`, what can happen?**  
Hostname/IP verification fails. An `IP:127.0.0.1` SAN is needed for IP-based URLs.

**8. Does enabling `server.http2.enabled=true` guarantee clients always use HTTP/2?**  
No. Client, TLS ALPN, container/proxy, and compatibility determine the negotiated protocol. Verify the actual response version and ALPN.

**9. Why should private keys not be embedded inside a production JAR?**  
Because JARs/images/logs/backups are copied and distributed much more widely than where secrets are allowed to reside. Use secret mounts/secret management with least-privilege permissions.

**10. Does bundle `reload-on-update` support hot reload across all embedded servers in Boot 3.3?**  
No. Boot 3.3 documentation names Tomcat and Netty as compatible web server consumers. Do not assume Jetty/Undertow share that behavior.

**11. Why can a browser access HTTPS even when the Spring Boot backend has no `server.ssl.bundle` configured?**  
Because an upstream proxy/ingress can terminate TLS and forward internal HTTP. Inspect the architecture hop by hop.

**12. Does a client getting HTTP 200 with `curl -k` prove the certificate chain is valid?**  
No. `-k` disables verification; you must use proper CA/trust material and verify SAN, issuer, and validity.

## 22. Official References and Further Reading

- [Spring Boot 3.3 – SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html): PEM/JKS SSL bundles, `SslBundles` API, `reload-on-update`, and trust material principles.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.ssl.bundle`, PEM/PKCS#8, SNI, HTTP/2, embedded container compatibility, and discrete SSL config constraints.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): property names, defaults, and version-specific bundle options.
- [Spring Boot Blog – Securing Spring Boot Applications with SSL](https://spring.io/blog/2023/06/07/securing-spring-boot-applications-with-ssl/): motivation behind SSL bundles and applying them to embedded servers/client connections.
- [OpenSSL – genpkey](https://docs.openssl.org/3.0/man1/openssl-genpkey/): generating PEM/PKCS#8 private keys.
- [OpenSSL – req](https://docs.openssl.org/3.0/man1/openssl-req/): generating CSRs or self-signed certificates with SANs.
- [OpenSSL – s_client](https://docs.openssl.org/3.0/man1/openssl-s_client/): inspecting TLS handshakes, SNI, ALPN, and certificate chains.
- [RFC 8446 – TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3 foundation.
- [RFC 7301 – TLS Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301): ALPN for negotiating HTTP/2 over TLS.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 framing and protocol specification.