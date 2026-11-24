# Applying SSL Bundles and Verifying Target Server Certificates in Spring Boot HTTP Clients

> **Module:** Spring Boot - web-runtime · **Group:** HTTP client. This lesson focuses on **a Spring Boot application making outbound HTTPS calls**, verifying the **target server's** certificate and identity using an SSL bundle. Do not confuse this with `server.ssl.*`, which enables HTTPS for an inbound server. Examples use **Spring Boot 4.1.2**, **Java 17+**, Maven, OpenSSL, and `RestClient`, with additional coverage of `WebClient`, `RestTemplate`, JKS/PKCS12, mTLS, and safe truststore operations.

## Learning Objectives

After this lesson, you will be able to:

1. Explain TLS server authentication, trust anchors, certificate chains, **Subject Alternative Name (SAN)**, validity windows, and hostname verification.
2. Distinguish an **HTTP client truststore** from a **client's own keystore/private key**, as well as an HTTP server keystore.
3. Configure `spring.ssl.bundle.pem.<name>.truststore.certificate` or `spring.ssl.bundle.jks.<name>.truststore.*`.
4. Apply a bundle to `RestClient` via `RestClientSsl`, to `WebClient` via `WebClientSsl`, and to `RestTemplate` via `RestTemplateBuilder.sslBundle(...)` in Spring Boot 4.1.
5. Run a Maven project with a self-signed HTTPS server on localhost and a `RestClient` trusting that exact certificate **while keeping hostname verification enabled**.
6. Test failures when the CA is untrusted, hostname/SAN mismatches, the cert is expired, or an intermediate is missing; distinguish handshake failures from HTTP 401/403.
7. Design CA rotation, client mTLS identities, timeouts/connection pools, proxies, redirects, and SSRF protections.

## 1. You Must Verify the Server, Not Just Encrypt the Connection

An application sends:

~~~http
GET /v1/orders HTTP/1.1
Host: partner.example.com
Authorization: Bearer (application token)
~~~

If you require an encrypted TLS channel **without verifying the partner's certificate**, an attacker on the network path can present their own certificate and intercept client–server traffic. TLS achieves its purpose only when connecting to **the intended endpoint**, not merely any HTTPS-capable host.

~~~text
Spring Boot / RestClient                   Partner Server
   |
   +---- TCP + TLS ClientHello (SNI=partner.example.com) --->
   |<--- Certificate (leaf + intermediate chain) ------------+
   |
   +-- Verify chain to trusted root/anchor
   +-- Check notBefore/notAfter
   +-- Match cert SAN against URL hostname
   +-- Check key usages / crypto policy
   |           |
   |           +-- INVALID -> handshake error, HTTP body never sent
   |
   +---- HTTP request inside TLS ---------------------------->
   |<--- HTTP response --------------------------------------+
~~~

- **Encryption/integrity:** data is protected in transit.
- **Authentication:** the server actually matches the hostname/identity you intended to call.
- **API Authorization:** tokens, sessions, Basic auth, or mTLS identities still need verification alongside/after TLS.

If TLS succeeds and the API returns HTTP 401, that is usually a **missing or invalid application credential**, not a reason to change the truststore. If TLS fails with a PKIX error, the application lacks sufficient proof to send sensitive data.

### Key Terms

| Term | Practical meaning |
| --- | --- |
| Leaf/server certificate | Public certificate of the endpoint, holding public key, SANs, issuer, and validity |
| Intermediate CA certificate | Intermediate CA certificate forming a trust path toward a trust anchor |
| Root CA/trust anchor | CA/certificate that the client explicitly chooses to trust |
| Certificate chain | Sequence of leaf/intermediate certs used to verify signatures back to a trust anchor |
| **Truststore** | Set of certificates/CAs the client uses to **trust the remote server** |
| **Keystore** | Store holding a certificate chain and **the owner's private key** |
| SSL bundle | Named collection of TLS key/trust material + options in Spring Boot |
| Hostname verification | Comparing the target URL's hostname/IP against SANs on the server certificate |
| SNI | Server Name Indication in TLS ClientHello, helping the server pick the right certificate |
| ALPN | Protocol negotiation such as `h2` or `http/1.1` over TLS; distinct from certificate verification |
| mTLS | Client verifies server cert AND server verifies client certificate |

**Standard server-auth TLS does not require a client private key.** The client only needs trust material for the CA/endpoint; a client private key is needed only when the server requires mTLS.

## 2. Checks the HTTP Client Must Perform

### 2.1. PKIX Path Building to a Trusted CA

Example:

~~~text
server leaf: inventory.internal.example
   signed by: Company Issuing CA
   signed by: Company Root CA

client truststore:
   Company Root CA
~~~

The client receives the leaf and chain (the server should send the required intermediates), verifies signatures, basic constraints, key usages, and validity, and builds a path to a trust anchor. If the client lacks the right CA, a typical error is:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed:
  unable to find valid certification path to requested target
~~~

Common causes: private CA missing from truststore, server omitting intermediate cert, app using **the wrong SSL bundle**, a corporate TLS proxy substituting the chain, expired certificate, or disallowed cryptographic algorithms. **Never fix this by creating a TrustManager that trusts every certificate.**

### 2.2. Hostname/SAN Must Match the Actual URL

When calling `https://orders.example.com`, the certificate must carry a valid identity for `orders.example.com`. A cert for `api.example.com` does not become valid simply because it belongs to the same organization or CA.

- SAN `DNS:orders.example.com` matches that hostname.
- Wildcard SAN `DNS:*.example.com` typically matches one label like `api.example.com`, not `a.b.example.com` or `example.com`.
- Calling `https://127.0.0.1` requires SAN **IP Address:127.0.0.1**; SAN `DNS:localhost` alone is not enough.
- Connecting by IP while setting HTTP `Host: orders.example.com` cannot bypass earlier TLS hostname verification.
- Never rely on `CN` instead of SAN; modern TLS certificates rely on SANs.

Hostname checking is **separate from CA trust**. A CA-valid certificate can still fail hostname verification and must be rejected.

### 2.3. Validity, Key Usage, Revocation, and Clocks

`notBefore` and `notAfter` define the certificate's validity window; clients should keep system clocks synchronized via NTP. Extended Key Usage such as `serverAuth` and algorithm/key-size policies also matter. Revocation checking (OCSP/CRL) depends on provider/policy configuration; never assume every client performs online revocation checks on every handshake by default.

Do not equate a **newly issued certificate on disk** with the certificate **currently served over TLS**. A load balancer or another pod may still serve an older cert.

### 2.4. Public CAs and the Java Default Truststore

The JDK/JVM ships default trust anchors, typically from the runtime truststore (e.g., `cacerts`). If a server uses a public CA already trusted by the runtime, you may **not need a custom truststore**. Dedicated SSL bundles fit when:

- A partner uses an internal/private CA.
- You want to partition trust per external API.
- Running a lab with a self-signed localhost certificate.
- A client keypair is needed for mTLS.

A custom truststore does not automatically **append** a CA to the default JVM truststore: many `SSLContext`/connector setups use only the truststore you provide. Never configure a bundle trusting only an internal CA and assume that same client still trusts all public websites as before. Design **clients per partner** and test trust accordingly.

### 2.5. Avoid Modifying the Global JVM Truststore

Older apps sometimes set `-Djavax.net.ssl.trustStore=...` or edit `$JAVA_HOME/lib/security/cacerts`. That affects **all outbound TLS in the JVM**, including third-party libraries, and creates risks during CA rotation.

SSL bundles keep configuration explicitly scoped:

~~~text
RestClient to billing.internal         -> bundle billing-ca
WebClient to events.partner.example    -> bundle events-ca
RestClient to public API               -> default JVM trust if appropriate
mTLS client to payments                -> bundle payments-client
~~~

This is an **architectural convention**, not an automatic Boot rule selecting bundles by URL. You must apply the right bundle to the corresponding builder.

## 3. Configuring PEM SSL Bundles

Spring Boot supports `spring.ssl.bundle.pem.*` and `spring.ssl.bundle.jks.*`. Any named bundle can be retrieved via `SslBundles` and applied to integrated consumers.

### 3.1. PEM Truststore for an Outbound HTTP Client

~~~properties
spring.ssl.bundle.pem.partner.truststore.certificate=file:/etc/myapp/trust/partner-ca.pem
~~~

- `partner` is the SSL bundle name you choose.
- `truststore.certificate` points to the **public certificate** of the CA/endpoint you explicitly choose to trust by policy.
- `file:` references an operator/secret-mount managed file; `classpath:` works for public certs when app-versioned bundling fits, though it makes out-of-band rotation harder.
- Declaring a truststore **does not automatically make every RestClient/WebClient use the bundle**; you must apply it to the client.

Never place a **CA or server private key** inside a client truststore. When a service rotates its CA, update trust material through a controlled process; never blindly copy a random certificate from an SSL error page and trust it without verifying provenance.

### 3.2. PEM Keystore + Truststore for mTLS

~~~properties
# Client verifies the partner server.
spring.ssl.bundle.pem.payments.truststore.certificate=file:/run/trust/payments-ca.pem

# Partner server verifies our client:
spring.ssl.bundle.pem.payments.keystore.certificate=file:/run/identity/my-client-chain.pem
spring.ssl.bundle.pem.payments.keystore.private-key=file:/run/identity/my-client-key.pem
~~~

In mTLS, the target server must be configured to request/accept client certificates and trust the CA issuing our client certificate. The HTTP API may still require bearer tokens or permissions. The private key is never sent over the network; the client uses it locally to prove possession.

### 3.3. Bundle Names and Lookup

Spring Boot auto-configures an `SslBundles` bean:

~~~java
// Fragment used inside a Spring-managed component:
SslBundle bundle = sslBundles.getBundle("partner");
~~~

In Boot 4.x, these types live in `org.springframework.boot.ssl`. If the bundle name is missing, `NoSuchSslBundleException` is a **configuration error** during lookup, not a server identity error.

Documentation also supports `base64:` or inline PEM content depending on the property; however, for configs needing rotation, managed file paths are usually easier to operate. When configuring bundles via environment variables, Boot normalizes bundle names to lowercase, so name bundles consistently in lowercase.

## 4. Configuring JKS or PKCS12 SSL Bundles

A Java KeyStore can hold CA trust certificates, and for mTLS it can hold a private key/cert chain. An outbound PKCS12 truststore:

~~~properties
spring.ssl.bundle.jks.partner.truststore.location=file:/run/trust/partner-trust.p12
spring.ssl.bundle.jks.partner.truststore.type=PKCS12
spring.ssl.bundle.jks.partner.truststore.password=${PARTNER_TRUSTSTORE_PASSWORD}
~~~

Supply the `PARTNER_TRUSTSTORE_PASSWORD` environment variable/secret through an approved mechanism—never commit real passwords to the repository. Never define the same `partner` name under both `pem` and `jks` and rely on accidental auto-configuration ordering.

To import a public CA cert:

~~~bash
keytool -importcert -noprompt \
  -alias partner-ca \
  -file partner-ca.pem \
  -keystore partner-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

`changeit` is **lab-only**, never for production. Passing passwords on the CLI can expose them in shell history or process listings; real environments should use an approved vault/secret delivery mechanism.

To inspect a keystore:

~~~bash
keytool -list -v \
  -keystore partner-trust.p12 \
  -storetype PKCS12
~~~

Output shows aliases, validity, entry types, and public certificate fingerprints. This verifies **which CAs the truststore contains**, not whether the live server presents the right cert. Never import a private key into a client truststore just to work around a PKIX error.

### Comparing PEM and JKS

| Criterion | PEM trust material | JKS/PKCS12 trust material |
| --- | --- | --- |
| Format | Text file with `BEGIN CERTIFICATE` | Binary keystore/truststore |
| Private CA trust | `spring.ssl.bundle.pem.*.truststore.certificate` | `spring.ssl.bundle.jks.*.truststore.*` |
| mTLS identity | PEM cert chain + PEM private key | Keystore private key entry + chain |
| Secret management | PEM key needs ACLs, secret manager | Keystore and password need ACLs, secret manager |
| Rotation | Publish new cert/chain file, verify consumer reload | Publish new keystore, verify consumer reload |
| Format choice | Based on PKI/secret delivery and client integration | Based on Java/keystore management policy |

Never assume PEM is universally better than JKS or vice versa; the goal is a well-managed format matching your trust policy and client connector.

## 5. Applying SSL Bundles to HTTP Clients in Spring Boot 4.1.2

### 5.1. RestClient (Imperative)

In **Boot 4.x**, `RestClientSsl` lives in package **`org.springframework.boot.restclient.autoconfigure`**:

~~~java
import org.springframework.boot.restclient.autoconfigure.RestClientSsl;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerRestClient {
    private final RestClient client;

    public PartnerRestClient(RestClient.Builder builder, RestClientSsl ssl) {
        this.client = builder
                .baseUrl("https://partner.example.com")
                .apply(ssl.fromBundle("partner"))
                .build();
    }

    public String fetchStatus() {
        return client.get()
                .uri("/health")
                .retrieve()
                .body(String.class);
    }
}
~~~

This class targets a Spring Boot app with a `partner` bundle; to run, the server and endpoint must exist. Inject Boot's auto-configured `RestClient.Builder` to preserve message converters and other integrations instead of calling `RestClient.create()` when Boot settings are needed.

**Caution:** Boot 4.1.2 Javadoc explicitly notes that applying `RestClientSsl.fromBundle(...)` may **replace a previously configured `ClientHttpRequestFactory`**. If you configured proxies, timeouts, or pooling on a separate factory, do not assume they remain intact. Use `HttpClientSettings`/`ClientHttpRequestFactoryBuilder` per documentation and test effective behavior.

### 5.2. WebClient (Reactive)

In **Boot 4.x**, `WebClientSsl` lives in `org.springframework.boot.webclient.autoconfigure`:

~~~java
import reactor.core.publisher.Mono;

import org.springframework.boot.webclient.autoconfigure.WebClientSsl;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class PartnerReactiveClient {
    private final WebClient client;

    public PartnerReactiveClient(WebClient.Builder builder, WebClientSsl ssl) {
        this.client = builder
                .baseUrl("https://partner.example.com")
                .apply(ssl.fromBundle("partner"))
                .build();
    }

    public Mono<String> fetchStatus() {
        return client.get()
                .uri("/health")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

This applies to projects with the Spring WebFlux dependency and Boot's `WebClient.Builder` bean. In WebFlux handlers, return `Mono`/`Flux` to the framework instead of calling `block()` on the Netty event loop. Use `WebClientSsl` to configure connector trust and re-verify if the app also customizes the connector or connection provider.

Having both MVC and WebFlux starters on the classpath does not automatically turn the server into WebFlux; Spring Boot usually prefers **Servlet web application type** when both are present. `WebClient` works as an outbound client—do not confuse that with switching the entire app runtime.

### 5.3. RestTemplate (Legacy Imperative)

Boot 4.1.2 provides `RestTemplateBuilder.sslBundle(...)`:

~~~java
import org.springframework.boot.restclient.RestTemplateBuilder;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class LegacyPartnerClient {
    private final RestTemplate template;

    public LegacyPartnerClient(RestTemplateBuilder builder,
                               SslBundles bundles) {
        this.template = builder
                .sslBundle(bundles.getBundle("partner"))
                .build();
    }

    public String fetchStatus() {
        return template.getForObject(
                "https://partner.example.com/health", String.class);
    }
}
~~~

Some Boot 3.x guides use `setSslBundle(...)` and different packages, so use the **version-appropriate API**. For new non-reactive code, Boot recommends `RestClient`; `RestTemplate` remains important for existing codebases.

### 5.4. Choosing the Right Client

| API | Execution | Applying bundle | Notes |
| --- | --- | --- | --- |
| `RestClient` | Imperative | `builder.apply(restClientSsl.fromBundle("partner"))` | May replace request factory; check timeouts/proxy |
| `WebClient` | Reactive | `builder.apply(webClientSsl.fromBundle("partner"))` | Check Reactor Netty connector; never block event loop |
| `RestTemplate` | Imperative legacy | `builder.sslBundle(sslBundles.getBundle("partner"))` | Has dedicated request factory and updated builder API |
| JDK `HttpClient` | Imperative/async JDK | Create `SSLContext`/trust config via JSSE | Does not auto-apply Boot SSL bundles when manually instantiated |
| Apache/Jetty/custom SDK | Library-specific | Depends on provider/connector | Must verify how trust/hostname checks actually apply |

**Never use one shared HTTP client configured with an internal truststore for arbitrary external URLs.** Clients for partner A and partner B should have separate baseUrls and bundles, reducing over-broad trust and `Authorization` leakage via redirects.

## 6. Runnable Example: Localhost HTTPS + RestClient Trusting the Exact Certificate

Goal: Boot MVC listens on HTTPS at `https://localhost:8443`, and on startup calls `/ping` through a `RestClient` with an independent client SSL bundle. The server uses **private key + certificate**, while the client trusts only the **public certificate**; SAN verification remains active.

**Project structure:**

~~~text
ssl-bundle-httpclient-demo/
  pom.xml
  .gitignore
  tls/                             # generated with OpenSSL, DO NOT commit
    server.crt                     # self-signed public cert
    server.key                     # private key
  src/main/java/com/example/ssldemo/
    SslBundleHttpClientDemoApplication.java
    PingController.java
  src/main/resources/
    application.properties
~~~

### 6.1. `pom.xml`

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
    <artifactId>ssl-bundle-httpclient-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

The MVC starter brings in embedded Tomcat and `RestClient`, without needing WebFlux for this blocking example. To build a separate reactive `WebClient` demo, use the WebFlux starter in a separate project with the snippet from Section 5.2.

### 6.2. `src/main/resources/application.properties`

~~~properties
# HTTPS listener, server TLS identity
server.port=8443
server.ssl.bundle=localserver

spring.ssl.bundle.pem.localserver.keystore.certificate=file:./tls/server.crt
spring.ssl.bundle.pem.localserver.keystore.private-key=file:./tls/server.key

# Outbound HTTP client TLS trust, NO private key included
spring.ssl.bundle.pem.localpeer.truststore.certificate=file:./tls/server.crt
~~~

**Two separate bundles:**

- `localserver` holds the **server's** cert/key for receiving requests.
- `localpeer` holds only the public certificate so **RestClient** trusts the local server.
- `server.ssl.bundle=localserver` does not make outbound clients use `localpeer` automatically; code must call `ssl.fromBundle("localpeer")`.
- Relative paths `file:./tls/...` depend on the working directory when the JVM launches. The demo runs Maven from the project root; production should mount secrets and use operator-managed absolute paths.

A self-signed cert is used as the trust anchor for **the lab**. In production, use an appropriate CA root/chain—never trust an arbitrary leaf cert just because someone pasted it in chat.

### 6.3. `SslBundleHttpClientDemoApplication.java`

~~~java
package com.example.ssldemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.restclient.autoconfigure.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class SslBundleHttpClientDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SslBundleHttpClientDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner verifyHttps(
            RestClient.Builder builder, RestClientSsl ssl) {
        return args -> {
            RestClient client = builder
                    .baseUrl("https://localhost:8443")
                    .apply(ssl.fromBundle("localpeer"))
                    .build();

            String body = client.get()
                    .uri("/ping")
                    .retrieve()
                    .body(String.class);

            System.out.println("Verified HTTPS response: " + body);
        };
    }
}
~~~

`ApplicationRunner` executes after Spring Boot initializes the application context and embedded server. The lab calls its local HTTPS listener to verify trust + hostname verification with a **real client**. If the TLS handshake fails, `RestClient` throws an exception causing the startup runner to fail; **that is a failure signal to fix**, not a reason to disable validation.

### 6.4. `PingController.java`

~~~java
package com.example.ssldemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping(value = "/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }
}
~~~

This controller returns plain text `pong`. There is no business authorization, JWT, or database because the focus is verifying HTTPS server identity. Production APIs require authentication/authorization at the appropriate layer.

### 6.5. `.gitignore`

~~~gitignore
/tls/
/target/
~~~

Never commit private keys. `.gitignore` only ignores untracked files; if a key was ever committed, rotate/revoke it and follow your security incident policy.

### 6.6. Generating a Self-Signed Certificate with SAN Using OpenSSL

Run in the project root on POSIX, macOS, Linux, or WSL:

~~~bash
umask 077
mkdir -p tls

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout tls/server.key \
  -out tls/server.crt \
  -days 7 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 tls/server.key

openssl x509 -in tls/server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

`-nodes` produces an unencrypted private key **for lab use only** so the app can read it without hardcoding a password. In production, use proper PKI, secret managers, and ACLs; never expose real keys on the internet or in repos. On Windows, replace `chmod/umask` with restrictive NTFS ACLs. OpenSSL output changes with generation time, so do not expect a fixed serial or date.

**SAN** includes DNS `localhost` and IP `127.0.0.1`. With only `CN=localhost` and no SAN, many HTTP clients will reject it. If an older OpenSSL version lacks `-addext`, use an equivalent config extension file rather than omitting SANs.

### 6.7. Running the Application

~~~bash
mvn spring-boot:run
~~~

Once the HTTPS server is ready and `RestClient` succeeds, the program prints:

~~~text
Verified HTTPS response: pong
~~~

This line is emitted deterministically by our code, while surrounding Spring Boot logs (port, threads, timestamps) vary by environment. If port `8443` is already in use, update `server.port` and `baseUrl` together or stop the conflicting process first.

Packaging:

~~~bash
mvn package
java -jar target/ssl-bundle-httpclient-demo-0.0.1-SNAPSHOT.jar
~~~

Run the JAR from the project root so `file:./tls/...` resolves properly. Never compile/run a Spring Boot project with bare `javac` without the dependency classpath.

### 6.8. Verifying with cURL

In another terminal, from the project root:

~~~bash
curl -i --cacert tls/server.crt https://localhost:8443/ping
~~~

Expect status 200 and body `pong`. `Content-Type` is typically `text/plain`; byte length, `Date`, and status-line formatting depend on server/client.

~~~bash
curl -i --cacert tls/server.crt https://127.0.0.1:8443/ping
~~~

Calling by IP also succeeds because the demo certificate includes SAN `IP:127.0.0.1`.

**Never use** `-k`/`--insecure` to bypass handshake failures. `--cacert` supplies the trusted public cert **only to that cURL invocation**; it does not alter the JVM truststore or Spring Boot SSL bundles.

### 6.9. Inspecting the Live Certificate with OpenSSL

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile tls/server.crt \
  -verify_hostname localhost \
  -verify_return_error </dev/null
~~~

- `-servername` sends SNI, crucial when servers host multiple hostnames.
- `-CAfile` sets the trusted public cert/CA for the OpenSSL CLI.
- `-verify_hostname` checks the target name, not only the CA chain.
- `-verify_return_error` causes validation errors to fail the command.

Successful output may contain `Verify return code: 0 (ok)`. Know your OpenSSL version and active trust options; inspecting only leaf fields is not enough to prove a client trusts the server.

To inspect the leaf cert being served:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout \
      -subject -issuer -serial -dates -fingerprint -sha256 \
      -ext subjectAltName
~~~

This second pipeline **only prints metadata** from the server-sent certificate; it does not perform full chain and hostname verification unless trust/verify flags are supplied.

## 7. Negative Tests

### 7.1. No Trusted CA/Cert

~~~bash
curl -i https://localhost:8443/ping
~~~

With a self-signed cert not imported into cURL/OS default truststores, the command fails because the certificate is untrusted. This differs from HTTP 401/403: it happens **before the HTTP layer**. To fix the test, pass `--cacert tls/server.crt`—never `--insecure`.

### 7.2. Trusted CA, Wrong Hostname

~~~bash
curl --noproxy "*" \
  --resolve wrong.example.test:8443:127.0.0.1 \
  --cacert tls/server.crt \
  -i https://wrong.example.test:8443/ping
~~~

This forces DNS resolution to localhost while keeping the URL hostname `wrong.example.test`. Because the cert only has SANs `localhost` and `127.0.0.1`, the client must reject it for **hostname mismatch**. This proves **having a truststore does not bypass SAN verification**.

If proxies interfere in your environment, keep `--noproxy "*"` and verify local connectivity first. Never issue an overly broad wildcard cert, and never write a `HostnameVerifier` that always returns `true`.

### 7.3. Truststore Containing a Different CA

To test in an isolated environment: generate a separate self-signed cert, point `localpeer.truststore.certificate` at the cert that **did not sign** `server.crt`, and restart the demo. `RestClient` must fail with PKIX/unknown CA during the handshake, even with a matching server SAN. Never download random certs from unapproved sources as a "fix" for production truststores.

When replacing files on disk, never assume a running HTTP client immediately refreshes its `SSLContext`. In the lab, restart; in production, follow a rotation procedure verified for your connector's reload support.

### 7.4. Expired Certificate

~~~bash
openssl x509 -in tls/server.crt -noout -dates
openssl x509 -in tls/server.crt -noout -checkend 259200
~~~

`-checkend 259200` checks whether the cert remains valid for about three days; exit code 0 normally means yes, nonzero means expiring/error. Checking dates is necessary, **not a substitute for chain/SAN validation**.

### 7.5. Missing Intermediate Certificate

When a server fails to send a required intermediate cert, clients may fail to build a chain to a trusted root. Use `openssl s_client -showcerts` to inspect what the server actually sends and fix the full-chain server config. Never copy a CA private key; distribute public intermediate certificates. Because some clients cache intermediates, test across environments matching production runtime/networking.

### 7.6. Error Table by Stage

| Symptom | Stage | Causes to investigate |
| --- | --- | --- |
| `NoSuchSslBundleException` | Boot configuration | Bundle missing or misspelled name |
| `SSLHandshakeException` / PKIX path building failed | TLS verification | Untrusted CA, missing intermediate, broken chain |
| `CertificateExpiredException` | TLS validity | Expired certificate or clock skew |
| `No subject alternative DNS name matching` | Hostname verification | URL host does not match SAN |
| `handshake_failure` | TLS negotiation | Cipher/protocol mismatch, mTLS identity, server policy |
| `Connection refused` | TCP/connect | Wrong host/port, server down, firewall |
| Timeout | DNS/TCP/TLS/HTTP per exception | Network, proxy, server load, timeouts |
| HTTP 401 | HTTP application | Credential/token rejected |
| HTTP 403 | HTTP application | Insufficient permissions or policy denial |
| HTTP 404 | HTTP application | Incorrect URL/method/path |
| HTTP 5xx | HTTP application/gateway | Server error after TLS |

Never leak raw stack traces or secrets/tokens in API responses when outbound calls fail; standardize the caller error contract and log controlled internal details.

## 8. mTLS: SSL Bundle with Both Trust and Client Identity

When a target server requires **mutual TLS**, the client needs both a truststore to **verify the server** and a keystore with a private key so **the server verifies the client**.

~~~properties
spring.ssl.bundle.pem.mtls-partner.truststore.certificate=file:/run/trust/partner-ca.pem
spring.ssl.bundle.pem.mtls-partner.keystore.certificate=file:/run/identity/client-chain.pem
spring.ssl.bundle.pem.mtls-partner.keystore.private-key=file:/run/identity/client-key.pem
~~~

Applying it:

~~~java
// RestClient fragment inside a Spring-managed component.
RestClient client = builder
        .baseUrl("https://payments.internal.example")
        .apply(ssl.fromBundle("mtls-partner"))
        .build();
~~~

Only use client certificates issued specifically for that workload/service identity. The server must trust the client CA or cert per policy; presenting a valid client cert still does not replace authorization/tenant checks. Never reuse production client keys in a lab.

Specific pitfalls:

- Supplying a truststore without a keystore when the server requires mTLS → handshake fails due to missing client identity.
- Supplying a keystore while disabling truststore/hostname checks → client no longer verifies the real server.
- Putting the server's private key in the client keystore → violates identity boundaries and leaks secrets.
- Sharing one client identity across partners/tenants that need distinct permissions.
- Placing keystore passwords or private keys in source code, JARs, Docker images, logs, or CI artifacts.
- Assuming mTLS grants unrestricted access to every API endpoint.

## 9. Timeouts, Pooling, and SSL Bundles: Check Effective Configuration

A TLS handshake normally runs only when opening a **new connection**. HTTP/1.1 keep-alive and HTTP/2 multiplexing allow multiple HTTP requests to share one TLS connection. Updating a cert on the server or truststore on the client **does not immediately change the cert on already-open connections**.

### 9.1. RestClientSsl May Replace the Request Factory

In Spring Boot 4.1.2, `RestClientSsl.fromBundle(...)` can configure a new `ClientHttpRequestFactory`, replacing an earlier factory. If you previously set proxies, connect timeouts, read timeouts, or a custom `SSLContext` on a custom factory, verify after applying the bundle whether those settings are still active.

Spring Boot provides `HttpClientSettings` and `ClientHttpRequestFactoryBuilder` to combine SSL bundles with client tuning. Never attach a custom factory and assume a subsequent `apply` preserves every setting untouched. On `RestTemplateBuilder`, `sslBundle(...)` and `clientSettings(...)` also affect the underlying factory; check the exact Boot version's Javadoc.

### 9.2. WebClient and Reactor Connection Pools

`WebClient` commonly uses a Reactor Netty pool. When configuring bundles:

- Prefer auto-configured `WebClient.Builder`; avoid setting a custom connector without the right trust policy.
- When customizing `HttpClient`, verify the SSL context, hostname verification, connect/response timeouts, proxy, and pool lifecycle.
- Never call `block()` on the Netty event loop; avoid blocking inside auth handlers, interceptors, or custom filters.
- During CA rotation, test a **new connection** and confirm the connector/`SSLContext` actually refreshed under your rollout mechanism.

### 9.3. HTTP Redirects Can Leak Credentials

If a partner returns a redirect to another domain, your application needs a **redirect/host allowlist**. TLS hostname verification validates the destination hostname of each TLS connection, but it **does not ensure** the redirect target is authorized by business policy to receive your token.

Never forward `Authorization` to hosts outside an allowlist, never follow redirects from HTTPS down to HTTP, and never let user input dictate full URLs (SSRF). On outbound HTTP, DNS rebinding, internal IPs, cloud metadata services, and private networks pose risks that **TLS alone cannot stop**.

### 9.4. Corporate Proxies

A managed TLS-intercepting proxy may present a cert signed by a corporate CA. If approved by your organization, client trust policy may include that CA; otherwise, treat an unexpected chain change as an anomaly to investigate rather than adding trust-all. Verify SNI, hostname, HTTP CONNECT, and proxy routing for your environment.

## 10. Rotating CAs, Leaf Certificates, and Reload Behavior

Distinguish four activities:

1. **Renewing a server leaf:** server swaps in a new cert with a valid chain/SAN.
2. **Rotating an issuing/root CA:** both servers and clients may need new trust material.
3. **Rotating a client mTLS keypair:** client updates its identity; server must trust it.
4. **Reloading SSL context:** running HTTP clients/connectors must pick up new material for new handshakes.

### When Must Clients Update Their Truststore?

| Change | Does the client need a new truststore? |
| --- | --- |
| Leaf cert renewed under the same trusted root CA | Usually **no**, if SAN/chain remain valid |
| New intermediate under the same trusted root | Usually no, if the server sends the proper chain |
| Root CA replaced completely | Yes, add the new CA and retire the old CA in phases |
| Self-signed server cert replaced | If the client directly trusted the old leaf, update trust |
| Server changes hostname or SAN | Needs a cert matching the new hostname; truststore won't fix a SAN mismatch |
| Client mTLS cert expires | Update client keystore, not just truststore |

### Zero-Downtime Plan

1. Inventory hostname:port, SNI, TLS terminators, CAs, cert chains, and clients.
2. Issue new certs/CAs; verify SANs, validity, key usage, chain, and policies.
3. Roll out a client truststore trusting **old + new CAs** during the overlap window if PKI policy allows.
4. Canary-test the client with a **new TLS connection** and verify hostname checking.
5. Roll out the new server leaf/chain and verify each pod/region with fresh handshakes.
6. If the HTTP client does not hot-reload, rebuild the client/connector/pool or perform a rolling restart per supported version.
7. Monitor PKIX errors, TLS handshake failures, latency, and readiness.
8. Remove the old CA/identity only after all components are confirmed migrated.

**Do not assume** `spring.ssl.bundle.pem.*.reload-on-update=true` automatically updates every `RestClient`, `WebClient`, or third-party HTTP SDK. Spring Boot docs describe hot reload for compatible consumers—notably embedded Tomcat/Netty web servers; outbound clients must be verified per connector, pool lifecycle, and version. Replacing a file on disk is not proof the active `SSLContext` uses the new cert.

### Monitoring the Live Endpoint

Monitor all of:

- Certificates at the issuing source / secret mount.
- Certificates **actually served** on the live URL with proper SNI, hostname, and port.
- Chain/intermediates, expiry, fingerprint, and serial across every region.
- Client-side handshake errors from the JVM, not only cURL checks from a laptop.

A file on disk expiring next year while a server still serves an expired cert indicates a deploy, reload, or routing bug. Monitor both server certs and client mTLS certs where used.

## 11. CLI Verification Against Live Endpoints

### cURL

~~~bash
curl -v https://partner.example.com/health
~~~

With an internal CA:

~~~bash
curl -v --cacert /etc/myapp/trust/partner-ca.pem \
  https://partner.example.com/health
~~~

`curl --cacert` does not configure Java `cacerts` or Spring Boot SSL bundles; each library can use different CAs or trust providers. cURL succeeding does not prove a JVM HTTP client applied the right bundle.

### OpenSSL SNI, Chain, and Hostname

~~~bash
openssl s_client \
  -connect partner.example.com:443 \
  -servername partner.example.com \
  -CAfile /etc/myapp/trust/partner-ca.pem \
  -verify_hostname partner.example.com \
  -verify_return_error </dev/null
~~~

This checks trust and hostname according to OpenSSL in the current environment. To inspect the leaf sent by the server:

~~~bash
openssl s_client \
  -connect partner.example.com:443 \
  -servername partner.example.com \
  -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout \
      -subject -issuer -serial -dates -fingerprint -sha256 \
      -ext subjectAltName
~~~

The second pipeline only inspects metadata; it **does not** prove trust chain + hostname validity without verification options. To inspect expiry of a specific cert file:

~~~bash
openssl x509 -in /etc/myapp/trust/partner-ca.pem \
  -noout -dates -fingerprint -sha256
~~~

Note: this inspects the **CA file**, not necessarily the live server's leaf cert.

### Java X509Certificate

Java provides `java.security.cert.X509Certificate`:

~~~java
// Fragment, not a standalone Java program.
cert.checkValidity();
System.out.println(cert.getSubjectX500Principal().getName());
System.out.println(cert.getNotAfter().toInstant());
~~~

`checkValidity()` only checks the validity date window. It **does not** verify chains against a truststore or match SAN hostnames. Never write a custom "verifier" that only reads Subject/CN and returns `true` in place of JSSE.

### JVM Handshake Diagnostics

In a controlled test environment:

~~~bash
java -Djavax.net.debug=ssl,handshake \
  -jar target/ssl-bundle-httpclient-demo-0.0.1-SNAPSHOT.jar
~~~

SSL debug logs print extensive handshake/cert details and hurt performance. Never leave enabled long-term in production, and never log Basic/Bearer tokens, private keys, passwords, or TLS session secrets.

## 12. Designing Outbound HTTP Clients in Production

~~~text
Application
 |
 +-- publicPartnerClient (RestClient)
 |      baseUrl=https://api.public-partner.example
 |      trust=default trusted roots if appropriate
 |
 +-- billingClient (RestClient)
 |      baseUrl=https://billing.internal.example
 |      bundle=billing-ca
 |
 +-- eventStreamClient (WebClient)
 |      baseUrl=https://events.partner.example
 |      bundle=events-ca
 |      reactive pool + response timeouts
 |
 +-- paymentsClient (RestClient)
        baseUrl=https://payments.internal.example
        bundle=payments-mtls
        truststore=payments CA
        keystore=client identity key/cert
~~~

Keep **baseUrl, trust policy, tokens/credentials, and timeouts** isolated per partner; never lump everything into one `RestClient` with global trust-all or a shared `Authorization` interceptor.

### Protecting Secrets

- Public trust certificates can be packaged as needed, while trust policy and certificate provenance must be governed.
- Private keys, keystore passwords, client credentials, and tokens belong in secret managers/volumes with least-privilege ACLs—never in repos, JARs, Docker images, or logs.
- Environment variables alone do not guarantee secret safety if process dumps, diagnostics, shell history, or host permissions expose them.
- Never use `NoopHostnameVerifier`, a TrustManager accepting all X509 certs, or `curl -k` to "fix" TLS errors.
- Avoid pinning a fixed leaf certificate in production without a rotation plan; prefer CA trust or rollover-capable pinning.

### Resilience

- Set sensible connect/handshake/response timeouts, and bound connection pools and concurrency.
- Retry transient failures **only when idempotency permits**; never infinitely retry a payment POST over an SSL/network error.
- Never retry PKIX or hostname mismatches as transient errors, which masks real incidents.
- Check circuit breakers, DNS refresh, proxies, and egress policies.
- Monitor TLS failures, certificate expiration, remote API latency, and response statuses separately.
- Enforce SSRF protections on any endpoint where users influence destination URLs.

## 13. Common Configuration Mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Setting only `server.ssl.bundle=...` | Configures **inbound** server TLS, not outbound HTTP clients | Use `RestClientSsl`/`WebClientSsl` or builder SSL APIs |
| Declaring an SSL bundle without applying it | Client may fall back to JVM defaults | Explicitly apply the named bundle |
| Putting the server private key into a client truststore | Violates trust boundaries and leaks secrets | Truststore must hold only appropriate public CA/certs |
| Right CA, wrong hostname SAN | CA trust does not substitute for hostname verification | Fix URL or reissue cert with matching SAN |
| Using an IP URL when cert only has a DNS SAN | IP and DNS are distinct SAN types | Use DNS hostname or issue an IP SAN |
| Checking only `CN` | Does not fulfill standard hostname verification | Rely on JSSE/Spring HTTP client checks |
| `curl --cacert` passes while JVM fails PKIX | Different CA providers, SSL bundles, routes, or proxies | Inspect the active client bean, trust material, and live chain |
| Using trust-all / `NoopHostnameVerifier` | MITM attackers can impersonate the server | Fix CA/chain/SAN instead of disabling checks |
| Modifying global `cacerts` for one partner | Broadens trust and affects unrelated clients | Use per-partner SSL bundles |
| Applying `RestClientSsl` after a custom factory | Can overwrite the factory and drop timeouts/proxies | Combine `HttpClientSettings`/`FactoryBuilder` properly |
| Blocking on WebClient's event loop | Causes bottlenecks and breaks non-blocking semantics | Return `Mono`/`Flux`; offload only when truly required |
| Copying a new CA file expecting automatic hot reload | Client pools/contexts may still hold old material | Rebuild/restart clients and test fresh handshakes |
| Treating HTTP 401 after TLS as a certificate error | Confuses HTTP auth with TLS | Check tokens and permissions |
| mTLS configured with truststore only | Missing client identity when server demands it | Add client cert/key keystore |
| Following redirects to arbitrary hosts | Leaks `Authorization`/enables SSRF | Allowlist scheme/host/port and restrict redirects |
| Trusting certs from unverified sources | Extends trust to attackers | Verify CA/PKI source, fingerprint, and ownership |
| Inspecting local certs instead of the live endpoint | A pod or edge node may still serve an old cert | Probe handshakes with proper SNI across instances |

## 14. Implementation and QA Checklist

- [ ] Known target endpoint URL and TLS terminator (direct server vs. edge/proxy)?
- [ ] Client trusts the right CA/cert, full chain/intermediates are present, and SAN matches the URL?
- [ ] Certificate within `notBefore/notAfter`, valid EKU, and compliant crypto policy?
- [ ] Correct PEM/JKS SSL bundle type, exact bundle name, no duplicate/conflicting names?
- [ ] HTTP client bean actually applies the bundle via `RestClientSsl`, `WebClientSsl`, or `RestTemplateBuilder`?
- [ ] No trust-all or disabled hostname verification anywhere in code?
- [ ] Standard server-auth clients hold no client private key; mTLS uses dedicated client keys/certs when required?
- [ ] Truststores, keystores, passwords, and identities managed under strict secret policies and OS permissions?
- [ ] Negative tests cover wrong CA, wrong SAN, expired leaf, and incomplete chain?
- [ ] Verified how JVM/connector CA trust differs from cURL/OS behavior?
- [ ] With proxies/redirects, auth tokens cannot leak to non-allowlisted hosts?
- [ ] Timeouts, pooling, DNS/proxies, and retries tested after applying the SSL bundle?
- [ ] CA rotation plan covers canarying, old/new trust overlap, and rollback?
- [ ] Tested a **fresh** handshake after reload or rolling restart?
- [ ] Expiry monitored on the live target server, not only local trust files?
- [ ] No tokens, private keys, passwords, TLS secrets, or excessive handshake debug logs emitted?
- [ ] Tested across individual pods/regions rather than assuming from one load-balanced request?

## 15. Self-Check Questions and Answers

**Q1.** `RestClient` calls an internal HTTPS API and throws `PKIX path building failed`. Must you create a client certificate?

**Answer:** No. This usually means the client **does not trust the server's chain**. Check CA/truststore, intermediates, bundle, proxies, and hostname. A client keypair is only needed if the server enforces mTLS.

**Q2.** Is declaring `spring.ssl.bundle.pem.partner.truststore.certificate=...` enough for every `RestClient` to trust that CA automatically?

**Answer:** No. You must apply the bundle to the client, such as `builder.apply(ssl.fromBundle("partner"))`.

**Q3.** The server cert is signed by a trusted CA, yet SAN only lists `api.example.com` while the client calls `orders.example.com`. Can you disable hostname verification?

**Answer:** No. The certificate must match the URL's hostname in addition to chain trust.

**Q4.** Why is `DNS:localhost` in a certificate insufficient for `https://127.0.0.1`?

**Answer:** Connecting by IP requires an IP Address SAN for that IP; a DNS SAN does not substitute for an IP SAN.

**Q5.** In Spring Boot 4.1.2, where is `RestClientSsl` located?

**Answer:** `org.springframework.boot.restclient.autoconfigure.RestClientSsl`.

**Q6.** Why might HTTP client timeouts or proxies disappear after applying an SSL bundle?

**Answer:** `RestClientSsl` Javadoc notes that applying it may replace an earlier `ClientHttpRequestFactory`. Combine settings/factories using the proper API and test.

**Q7.** Under mTLS, does the client only need a keystore/private key and no truststore/server checks?

**Answer:** No. mTLS requires the client to verify the server as well as the server verifying client identity.

**Q8.** cURL with `--cacert` passes, yet the JVM still reports PKIX. Is that a contradiction?

**Answer:** No. cURL and the JVM may use different truststores, proxies, SNI, or CA providers. Inspect the active HTTP client bean and bundle.

**Q9.** Does replacing a cert file in the truststore automatically make all live `RestClient`/`WebClient` instances use the new CA?

**Answer:** Never assume so. Check connector/`SSLContext` lifecycle, pooling, and refresh mechanisms, then test a new handshake.

**Q10.** HTTPS succeeds, yet the response is HTTP 403—should you change the truststore?

**Answer:** No. 403 is application-layer access control after TLS. Check scopes, roles, tokens, or mTLS identity mapping.

## 16. Official Documentation and Standards

- [Spring Boot — SSL bundles (PEM, JKS, truststore, SslBundles)](https://docs.spring.io/spring-boot/reference/features/ssl.html).
- [Spring Boot — Calling REST Services, RestClientSsl/WebClientSsl/RestTemplateBuilder](https://docs.spring.io/spring-boot/reference/io/rest-client.html).
- [Spring Boot 4.1.2 API — RestClientSsl](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/restclient/autoconfigure/RestClientSsl.html).
- [Spring Boot 4.1.2 API — RestTemplateBuilder.sslBundle](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html).
- [Spring Boot — Application Properties: spring.ssl.bundle.*](https://docs.spring.io/spring-boot/appendix/application-properties/).
- [Spring Boot 4.1.2 release announcement](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html).
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280).
- [RFC 6125 — Service Identity Verification](https://www.rfc-editor.org/rfc/rfc6125).
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446).
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).
- [Oracle Java 17 — X509Certificate API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html).

**Conclusion:** When Spring Boot **calls** HTTPS endpoints, it must verify **the intended target server**, not merely establish an encrypted pipe. Place trust material in PEM/JKS SSL bundles, apply them properly per `RestClient`/`WebClient`/`RestTemplate`, preserve CA chain + SAN hostname + validity checks, and test both valid connections and wrong CA/hostname failures. Add a client private key only when mTLS is actually required. During rotation, verify the active `SSLContext`/connection pool and **live served certificate** with a fresh handshake rather than assuming disk edits took effect.