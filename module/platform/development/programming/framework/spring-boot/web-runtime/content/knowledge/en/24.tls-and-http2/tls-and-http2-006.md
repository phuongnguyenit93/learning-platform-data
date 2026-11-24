# Selecting Permitted TLS Versions and Cipher Suites in Spring Boot

## 1. Why Must You Actively Manage TLS Versions and Cipher Suites?

When a browser accesses `https://api.example.com`, before sending an HTTP request, the client and server establish a secure connection using **TLS (Transport Layer Security)**. During the handshake, both sides negotiate the **TLS version**, suitable encryption/authentication algorithms, and keys to protect data. If the client and server share no compatible options, the connection can fail **before the request ever reaches a Spring MVC controller or WebFlux handler**.

A sound TLS configuration balances:
- **Security**: never negotiating outdated protocols or weak/unsuitable cipher suites.
- **Compatibility**: continuing to support valid clients, Java versions, operating systems, and gateways your product must serve.
- **HTTP/2**: ensuring TLS/cipher choices do not violate HTTP/2 over TLS requirements.
- **Operability**: knowing whether TLS terminates at Spring Boot or a reverse proxy/load balancer, and having ways to measure, roll out, and roll back.

This lesson focuses on **two decisions**:
1. **Which versions are permitted?** For example `TLSv1.3` and `TLSv1.2`.
2. **Which cipher suites are permitted?** For example `TLS_AES_128_GCM_SHA256` for TLS 1.3, `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` for TLS 1.2 with an RSA certificate.

The two lists are related but **not synonymous**. In Spring Boot 3.5, the direct embedded server properties are `server.ssl.enabled-protocols` and `server.ssl.ciphers`. If the server uses an **SSL bundle** via `server.ssl.bundle`, put protocols/ciphers under `spring.ssl.bundle.<type>.<name>.options` instead of relying on direct properties that are ignored under bundle configuration. Details and examples follow below.

> **Version note:** runnable examples use Java 17+, Spring Boot **3.5.x**, Spring MVC, and embedded Tomcat with JDK JSSE. In Spring Boot 4.x, the MVC starter is `spring-boot-starter-webmvc` rather than `spring-boot-starter-web`; properties and per-server support must be checked against the exact version in use. TLS settings may also differ when using Jetty, Reactor Netty, OpenSSL/native providers, or gateway termination.

## 2. Distinguishing TLS, HTTPS, HTTP/2, Certificates, and Cipher Suites

| Component | What problem does it solve? | Example |
|---|---|---|
| TLS protocol version | Handshake rules, key schedule, and transport security | `TLSv1.3`, `TLSv1.2` |
| Cipher suite | Encryption/authentication algorithms selected for the connection | `TLS_AES_128_GCM_SHA256` |
| Certificate | Server proves identity via an X.509 certificate matching hostname | SAN contains `api.example.com` |
| Private key | Server proves control of the corresponding identity | Key in PKCS12/PEM |
| Trust store | CAs/certificates trusted by the verifying party | Public CA roots, internal CA |
| HTTPS | HTTP running over a TLS connection | `https://...` |
| HTTP/2 over TLS | HTTP/2 transported over TLS, application protocol chosen via ALPN | ALPN `h2` |
| SNI | Client indicates desired hostname during TLS handshake | `api.example.com` |
| mTLS | Server also verifies the client's certificate | `server.ssl.client-auth` + trust store |

**Do not conflate them:** enabling `server.http2.enabled=true` does not pick a safe cipher; enabling HTTPS does not verify that old clients can no longer negotiate TLS 1.0/1.1; editing a cipher list does not fix an expired certificate or wrong SAN.

### Two Different Negotiation Layers

~~~text
ClientHello
  +--- Supported TLS versions: TLS 1.3, TLS 1.2
  +--- Cipher suites offered
  +--- Supported groups / signature algorithms
  +--- SNI hostname
  +--- ALPN: h2, http/1.1
                 |
                 v
            TLS endpoint
                 |
                 +--- Selected TLS protocol version
                 +--- Matching cipher suite
                 +--- Key exchange / certificate / signature
                 +--- Selected ALPN protocol
                 |
                 v
       Authenticated TLS connection
                 |
                 v
       HTTP/2 or HTTP/1.1 request
                 |
                 v
       Spring Boot controller / handler
~~~

Simplified handshake diagram; exact message order and details differ between TLS 1.2 and 1.3. Only once the TLS handshake succeeds does the HTTP application get to process a request.

## 3. Which TLS Versions Should Be Allowed?

### TLS 1.3 — Preferred for Modern Clients

TLS 1.3 streamlines and hardens the handshake, removing many legacy algorithms. TLS 1.3 cipher suites specify only the **AEAD cipher** and hash for the key schedule, while key exchange and signatures are negotiated via separate extensions/mechanisms. That is why TLS 1.2 suite names cannot be reused to describe TLS 1.3 selections.

Common TLS 1.3 suites:
- `TLS_AES_128_GCM_SHA256`
- `TLS_AES_256_GCM_SHA384`
- `TLS_CHACHA20_POLY1305_SHA256` when supported by provider/runtime

Data is protected using **AEAD** (authenticated encryption with associated data). Verify JDK/provider support rather than assuming all three suites exist on every runtime/container.

### TLS 1.2 — Still Useful When Compatibility Is Needed

TLS 1.2 can remain in the allowed list to serve legitimate client systems that have not yet upgraded to 1.3. For TLS 1.2, prioritize suites with:
- **ECDHE** key exchange providing forward secrecy.
- AES-GCM or a suitable AEAD mode.
- Signature/certificate matching the authentication algorithm in the cipher name.

Examples with an **RSA server certificate**:
- `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`
- `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384`

Examples with an **ECDSA server certificate**:
- `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256`
- `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384`

`ECDHE_RSA` and `ECDHE_ECDSA` suites in TLS 1.2 are not interchangeable if the server's certificate/authentication capability does not match. 256-bit is not automatically better in every scenario; weigh performance, policy, and client support.

### TLS 1.0 and TLS 1.1 — Do Not Re-enable for Old Clients

TLS 1.0/1.1 are deprecated and should not be reopened in modern systems just to "make some client work." If a legacy client genuinely must remain supported, the solution should be upgrading the client or isolating a controlled forwarding gateway with a sunset plan, rather than weakening the TLS policy of your entire public API.

**Practical starting point:** support `TLSv1.3` and `TLSv1.2` when compatibility is required. Restrict to TLS 1.3-only only once you have evidence all clients/intermediaries are compatible and organizational policy approves. No single fixed list fits every service.

### Decision Table

| Context | Suggested policy to validate | Rationale |
|---|---|---|
| Public API with modern clients and some supported older Java/OS clients | TLS 1.3 + 1.2, appropriate AEAD ciphers | Balances security and compatibility |
| Internal API where one team controls all clients | Consider TLS 1.3-only after testing | Shrinks attack surface once verified |
| HTTP/2 over TLS with TLS 1.2 fallback | Allow HTTP/2-compliant TLS 1.2 suites | Avoids `INADEQUATE_SECURITY` |
| Client only supports TLS 1.0/1.1 | Upgrade client or design an isolated transition path | Avoid downgrading public endpoint security |
| Specific FIPS/regulatory requirements | Follow approved policies and providers | Do not infer compliance solely from cipher names |

## 4. How Do TLS 1.3 Cipher Suites Differ from TLS 1.2?

An easy way to read suite names:

**TLS 1.2:**

~~~text
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
    |     |       |   |   |   |
    |     |       |   |   |   +--- SHA-256 (bound to TLS 1.2 mechanism)
    |     |       |   |   +------- GCM (AEAD mode)
    |     |       |   +----------- 128-bit AES key
    |     |       +--------------- AES
    |     +----------------------- RSA authentication/certificate
    +----------------------------- ECDHE key agreement
~~~

**TLS 1.3:**

~~~text
TLS_AES_128_GCM_SHA256
    |   |   |      |
    |   |   |      +--- HKDF/hash
    |   |   +---------- authenticated encryption mode
    |   +-------------- symmetric key size
    +------------------ AEAD algorithm family
~~~

In TLS 1.3, the cipher name omits `ECDHE_RSA` because key exchange and certificate authentication are chosen independently. `TLS_AES_128_GCM_SHA256` does not run on TLS 1.2 just because it says AES-GCM, nor is `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` a TLS 1.3 suite name.

| Suite | TLS version | When it can be chosen |
|---|---|---|
| `TLS_AES_128_GCM_SHA256` | TLS 1.3 | Client, server, and provider support it |
| `TLS_AES_256_GCM_SHA384` | TLS 1.3 | Client, server, and provider support it |
| `TLS_CHACHA20_POLY1305_SHA256` | TLS 1.3 | Provider supports it and policy permits it |
| `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | TLS 1.2 | Suitable RSA auth + ECDHE capability present |
| `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` | TLS 1.2 | Suitable ECDSA auth + ECDHE capability present |
| `TLS_RSA_WITH_AES_128_CBC_SHA` | TLS 1.2 | Legacy; **do not select for new configs** |

**Do not enable** legacy suites such as RC4, 3DES, NULL, EXPORT, static RSA key exchange, or outdated CBC setups for new applications. It is not merely because the names sound "bad"; the risks involve confidentiality, lack of forward secrecy, implementation pitfalls, and current standards restrictions.

The TLS 1.3 RFC explains these differences; RFC 9325 (BCP 195) provides recommendations for secure use of TLS/DTLS. Always cross-check organizational policies and updated standards.

## 5. Suite Selection in Practice: Intersection of Multiple Constraints

During a TLS handshake, not every suite listed in YAML is automatically negotiable. The resulting suite is constrained simultaneously by:

1. **Client offer:** TLS versions/cipher suites advertised by the client.
2. **Server policy:** allowed versions/suites list.
3. **JDK/provider:** JSSE or OpenSSL/native must implement support.
4. **JDK security restrictions:** `jdk.tls.disabledAlgorithms` in `java.security` can exclude weak protocols/algorithms.
5. **Certificate/key:** RSA/ECDSA key type, key size, signature algorithms, and trust chain.
6. **Groups/key exchange:** whether elliptic curves/finite-field groups overlap.
7. **HTTP application protocol:** for HTTP/2, TLS 1.2 has discouraged suites and specific constraints.
8. **Actual TLS termination layer:** Spring Boot, gateway, Envoy, Nginx, cloud load balancer, or CDN.

Visualize this as:

~~~text
Negotiable suites
  = Client-supported
  ∩ TLS-version-compatible
  ∩ Server-allowed
  ∩ Provider-implemented
  ∩ JDK-security-policy-allowed
  ∩ Certificate/key-compatible
  ∩ Protocol/application constraints
~~~

This set formula is conceptual, not a substitute for an actual handshake test. Configuring an overly narrow single suite can lock out legitimate clients that do not support it.

### `server.ssl.protocol` vs. `enabled-protocols`

In Spring Boot:
- `server.ssl.protocol` (typically defaulting to `TLS`) is the algorithm/protocol name used to initialize the SSL context or TLS implementation.
- `server.ssl.enabled-protocols` is the set of enabled TLS protocol versions, such as `TLSv1.3` and `TLSv1.2`.

**Do not write** `server.ssl.protocol: TLSv1.3` assuming you have set an explicit version allowlist like `enabled-protocols`. Use the right property for enabled versions and verify the handshake on the runtime.

## 6. Direct Spring Boot Configuration via `server.ssl.*`

Spring Boot supports SSL via keystores or PEM. For an embedded server terminating TLS itself, basic direct configuration looks like:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:local-tls.p12
    key-store-type: PKCS12
    key-store-password: changeit
    key-alias: localtls
    enabled-protocols:
      - TLSv1.3
      - TLSv1.2
    ciphers:
      - TLS_AES_128_GCM_SHA256
      - TLS_AES_256_GCM_SHA384
      - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
      - TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
  http2:
    enabled: true
~~~

This is a **learning configuration** for the self-signed RSA keystore created in section 8. `changeit` is just a simple demo password; **never use it in production**. The illustrative TLS 1.2 suites match the RSA certificate generated in this lesson. TLS 1.3 suites do not carry RSA/ECDSA labels in their names; actual compatibility still depends on the provider and signatures/certificates.

If you need to support a client/device failing on the current list, **do not rush to add weak ciphers**. First inspect the server JSSE provider, client capabilities, handshake results, certificate key, AES/GCM/ChaCha support, and compatibility goals.

### Explaining Each Property

| Property | Purpose | What must NOT be inferred |
|---|---|---|
| `server.port: 8443` | Embedded HTTPS server port in the example | Does not enable TLS without valid SSL material |
| `server.ssl.enabled: true` | Enables TLS configuration | Does not remove the need for certificate and private key |
| `server.ssl.key-store` | Where to read keystore key/certificate | Not a truststore for verifying clients |
| `server.ssl.key-store-type` | Keystore type, e.g., `PKCS12` | Does not dictate the TLS version |
| `server.ssl.key-store-password` | Password to open the keystore | Never hardcode in a production repo |
| `server.ssl.key-alias` | Key/certificate entry alias | Must match the alias used when creating the keystore |
| `server.ssl.enabled-protocols` | Allowed TLS versions | Does not determine HTTP protocol version |
| `server.ssl.ciphers` | Permitted cipher suites | Does not force picking the first suite on every provider |
| `server.http2.enabled` | Enables HTTP/2 support if runtime allows | Does not guarantee suitable TLS/ciphers or that clients use h2 |

In this example there is only one HTTPS connector on port 8443. Spring Boot does not simultaneously create an HTTP 8080 connector just because the app previously ran HTTP. Having an HTTP→HTTPS redirect requires proxy configuration or explicit server connector setup; do not expect one property to create both ports.

**Important for production:** hardcoding keystore passwords in YAML committed to a repository is improper. Supply them via a secret manager, mounted secrets, environment bindings such as `SERVER_SSL_KEY_STORE_PASSWORD`, or platform-managed secure configuration. Private key and keystore files must have least-privilege permissions.

## 7. SSL Bundles: Configuring Protocols and Ciphers in the Right Place

In Spring Boot versions supporting SSL bundles, you can group key/trust material and options and reference them by name. Example with a bundle named `webserver`:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        webserver:
          key:
            alias: localtls
          keystore:
            location: classpath:local-tls.p12
            password: changeit
            type: PKCS12
          options:
            enabled-protocols:
              - TLSv1.3
              - TLSv1.2
            ciphers:
              - TLS_AES_128_GCM_SHA256
              - TLS_AES_256_GCM_SHA384
              - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
              - TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384

server:
  port: 8443
  ssl:
    bundle: webserver
  http2:
    enabled: true
~~~

**Do not mix both configuration styles on the same server.** Spring Boot documentation states clearly:
- When setting `server.ssl.bundle`, do not combine it with discrete keystore/PEM options under `server.ssl`.
- `server.ssl.ciphers`, `server.ssl.enabled-protocols`, and `server.ssl.protocol` **are ignored when using a bundle**.
- Place those options under `spring.ssl.bundle.<type>.<name>.options`, such as `spring.ssl.bundle.jks.webserver.options.enabled-protocols`.

This is a common real-world reason operations teams "edit allowed protocols, retest, and still see old TLS": the property was placed at the wrong level alongside `server.ssl.bundle`.

### Bundles and Certificate Management

- `spring.ssl.bundle.jks` supports Java KeyStores (JKS, PKCS12).
- `spring.ssl.bundle.pem` supports PEM certificates/private keys.
- Bundles can be referenced by the embedded server or certain Boot-integrated client/data technologies.
- SSL bundle reloading exists for compatible cases and servers, but **updating material/ciphers on a bundle does not mean every runtime hot-reloads all TLS options completely**. Check exact support and plan clear deployments/rollbacks.

Example using PEM instead of JKS for a bundle:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          keystore:
            certificate: file:/etc/my-app/tls/fullchain.pem
            private-key: file:/etc/my-app/tls/privkey.pem
          options:
            enabled-protocols:
              - TLSv1.3
              - TLSv1.2

server:
  ssl:
    bundle: webserver
~~~

This is a **production fragment**, assuming files and read permissions are provisioned by infrastructure. Never place `privkey.pem` in public static resources or repositories. PEM private keys may need PKCS#8 format depending on the library; check embedded server/Boot docs if material fails to load.

## 8. Java 17 Hands-On Lab: HTTPS with TLS 1.2/1.3

Goal: run a Spring Boot application yourself, create a local self-signed certificate, verify TLS 1.2 and TLS 1.3 succeed, verify legacy TLS is rejected if your client can attempt it, and inspect HTTP/2 ALPN.

**Prerequisites:** JDK 17+, `keytool`, Gradle wrapper in a Spring Boot project, `curl`, and optionally `openssl`. Create a project using Spring Initializr:
- Spring Boot 3.5.x, Java 17+, Gradle.
- Dependency **Spring Web**.
- No Spring Security needed for this lesson.
- Project uses the starter's default embedded Tomcat.

In a Boot 3.5 project with Gradle plugin/dependency management already set up:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

The snippet above is only a **dependency fragment**, not a complete `build.gradle`.

### 8.1. Create a Self-Signed PKCS12 Keystore for localhost

In the project root created by Spring Initializr (which already has `src/main/resources`), run:

~~~bash
keytool -genkeypair \
  -alias localtls \
  -keyalg RSA \
  -keysize 2048 \
  -sigalg SHA256withRSA \
  -validity 30 \
  -storetype PKCS12 \
  -keystore src/main/resources/local-tls.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=localhost, OU=Learning, O=Demo, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

In **Windows PowerShell**, Bash backslash multiline syntax does not work; run `keytool` on **one line** with the same flags or use PowerShell's continuation syntax.

Parameters:
- `-genkeypair`: generates a key pair and self-signed certificate for testing.
- `-keyalg RSA -keysize 2048`: 2048-bit RSA key, suited to demonstrating TLS 1.2 `ECDHE_RSA` suites. Choose production key types/sizes per CA and current security policies.
- `-sigalg SHA256withRSA`: demo certificate signing algorithm.
- `-validity 30`: demo certificate valid for 30 days from creation.
- `-storetype PKCS12`: PKCS12 keystore.
- `-alias localtls`: must match `server.ssl.key-alias`.
- `-ext SAN=...`: adds DNS `localhost` and IP `127.0.0.1` to Subject Alternative Name for proper hostname testing.

**Security:** this file contains a **private key** even though it is for a demo; never commit it to Git or share it publicly. The `changeit` password is unsuitable for real deployments. **Self-signed** certificates are not in default browser/curl trusted CA lists.

### 8.2. Complete Java Class

Create `src/main/java/demo/tls/TlsDemoApplication.java`:

~~~java
package demo.tls;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class TlsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TlsDemoApplication.class, args);
    }

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "hello tls";
    }
}
~~~

This is a complete runnable class inside the created Spring Boot project. Create `src/main/resources/application.yml` using the **direct configuration from section 6**. Do not add section 7's SSL bundle config at the same time.

### 8.3. Start the Application

From the project root:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Once the console indicates the embedded server is ready, the URL is:

~~~text
https://localhost:8443/hello
~~~

Do not call `http://localhost:8443/hello`: the example port speaks TLS, so plaintext HTTP typically gets closed or raises a protocol error.

### 8.4. Test HTTPS with curl

~~~bash
curl -k -i https://localhost:8443/hello
~~~

**Expected response body:**

~~~text
hello tls
~~~

The `-k`/`--insecure` flag only bypasses certificate trust checking **in this local test**. It does not prove production certificate chain/trust/hostname validity; **never use `-k` in production clients**.

Test pinning TLS versions with a curl build supporting those flags:

~~~bash
curl -k --tlsv1.3 --tls-max 1.3 -i https://localhost:8443/hello
curl -k --tlsv1.2 --tls-max 1.2 -i https://localhost:8443/hello
~~~

With supporting JDK/providers and curl, both requests are expected to finish the handshake, return HTTP 200, and output `hello tls`. `--tlsv1.2` in curl means **minimum TLS 1.2** on many curl versions, so adding `--tls-max 1.2` forces exactly 1.2. Same for TLS 1.3.

To see the actual negotiated protocol and cipher:

~~~bash
curl -k -v --tlsv1.3 --tls-max 1.3 \
  https://localhost:8443/hello
~~~

`curl -v` can print handshake/version/cipher details depending on its TLS backend; do not assume one OS's exact verbose text applies to every curl build.

### 8.5. Test via OpenSSL s_client

If your machine has OpenSSL supporting TLS 1.2/1.3:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -tls1_3 \
  -ciphersuites TLS_AES_128_GCM_SHA256 \
  -brief
~~~

To test TLS 1.2 with a specific suite, **OpenSSL uses different suite names than JSSE on some flags**:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -tls1_2 \
  -cipher ECDHE-RSA-AES128-GCM-SHA256 \
  -brief
~~~

**Do not confuse** `-cipher` (for TLS 1.2 and older) with `-ciphersuites` (for TLS 1.3) in OpenSSL. OpenSSL's `ECDHE-RSA-AES128-GCM-SHA256` corresponds to JSSE's `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`.

`s_client` output may warn about a certificate verification error because the **demo self-signed certificate** is untrusted; that is separate from **incompatible handshake protocol/cipher**. To verify the certificate properly, supply appropriate CA/trust material with `-CAfile` or use a valid certificate; never treat `-k`/skipping verification as a successful trust test.

### 8.6. Testing Legacy TLS Versions

With an OpenSSL build that still permits trying TLS 1.1:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -tls1_1 \
  -brief
~~~

Because the server only permits 1.2/1.3, **a TLS 1.1 connection must not succeed**. However, if **client-side** OpenSSL/JDK has disabled TLS 1.1, the command may fail locally before the server responds. A single failed command **is not sufficient proof** the live endpoint rejected TLS 1.1: inspect logs, handshake traces, or a scanner capable of sending a valid legacy `ClientHello`.

### 8.7. Testing HTTP/2 via ALPN

The example `application.yml` already sets `server.http2.enabled=true`. Test with curl if your curl build supports HTTP/2:

~~~bash
curl -k --http2 -v https://localhost:8443/hello
~~~

Look for ALPN selecting `h2` and the corresponding HTTP response version. `curl --http2` typically includes `h2` in the client's offered protocols; if the server/runtime lacks support or negotiates HTTP/1.1, check configuration/ALPN. Do not assume HTTP/2 is active merely because TLS 1.3 succeeded.

If `curl` reports `--http2` is unsupported, that curl binary was built without HTTP/2; this is a test client limitation, not proof the server lacks support.

## 9. Relationship Between TLS and HTTP/2: Which Ciphers Cause Errors?

HTTP/2 over TLS (`h2`) uses **ALPN** to select the application-layer protocol. Per **RFC 9113**:
- HTTP/2 over TLS requires **TLS 1.2 or newer**.
- For TLS 1.2, there is a list of cipher suites **prohibited/discouraged from use** (Appendix A), and an endpoint may close the connection with `INADEQUATE_SECURITY` if an unsuitable suite is negotiated.
- HTTP/2 implementations with TLS 1.2 **must support** `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` and P-256 per specification requirements, preventing pairs from having no compatible suite.
- TLS 1.3 has different mechanisms and follows its own HTTP/2 constraints, such as disallowing post-handshake TLS 1.3 `CertificateRequest`.

This explains why configuring an overly narrow cipher list can result in HTTPS working over HTTP/1.1 while HTTP/2 fails for some clients. Do not enable prohibited TLS 1.2 suites merely to make HTTP/2 "accept" a connection.

### Does HTTP/2 Require TLS 1.3?

**No.** `h2` can run over TLS 1.2 or TLS 1.3, provided HTTP/2's TLS/ALPN/cipher rules are met. Spring Boot can also support `h2c` (HTTP/2 over cleartext TCP) in appropriate contexts, typically behind a proxy—**not as a replacement for TLS encryption at the public edge**.

### TLS Termination at a Proxy Changes Where Policy Lives

~~~text
Browser --TLS/ALPN--> CDN / LB / reverse proxy
                              |
                              +-- HTTP or HTTPS / mTLS --> Spring Boot
~~~

If TLS terminates at a proxy:
- **Client-facing** TLS protocol/cipher policy lives at the proxy/CDN/LB. Changing `server.ssl.ciphers` in Spring Boot **does not change the ciphers browsers negotiate with the proxy**.
- If proxy → Boot uses plaintext HTTP inside a private network, the app might not even have an embedded HTTPS connector. Evaluate the network trust model instead of assuming "internal" automatically means safe.
- If proxy → Boot also uses TLS, you must configure **a separate TLS hop**, with its own policy. Ciphers and certificates on the two hops may differ.
- Boot's `server.http2.enabled` only controls support on the embedded server; whether browsers use HTTP/2 with a CDN depends on the CDN's ALPN.

In production, always identify the **actual TLS endpoint** before editing YAML.

## 10. When You Do Not Want to Maintain a Custom Cipher Allowlist

Two common strategies exist:

**A. Rely on up-to-date defaults from the JDK/embedded server/provider**, while explicitly permitting appropriate TLS versions and keeping the runtime patched. The advantage is inheriting security patches and default compatibility. The risk is policy shifts upon JDK/runtime upgrades, requiring CI scans to catch changes.

**B. Define an explicit cipher allowlist** when compliance rules or exact compatibility requirements demand it. The advantage is a predictable suite set; the downside is accidentally excluding newer strong ciphers, breaking clients after upgrades, or creating drift across servers.

**There is no single best short fixed list for every environment.** Without specific policy mandates, it is usually wiser to start from the secure defaults of a current runtime and **measure which versions/suites are negotiated**. Only pin a custom allowlist after establishing a client inventory and running real tests.

### Periodic Verification Matters More Than "Pin and Forget"

Even without changing YAML:
- A JDK update may modify `jdk.tls.disabledAlgorithms`.
- Tomcat/Jetty/Netty providers may update default enabled suites.
- Load balancers/CDNs may update their TLS policy.
- Certificates may rotate from RSA to ECDSA, affecting valid TLS 1.2 suites.
- Java/OS/browser clients may drop support for older protocols or cipher suites.

Keep policies in version control, record scan results, and retest key clients after upgrading JDK/Boot/servers/gateways.

## 11. Distinguishing Keys, Certificates, Truststores, and TLS Cipher Policies

These items can be configured together under `server.ssl` but serve distinct roles.

**Key store** holds the server certificate and private key used to authenticate the server. With the demo PKCS12 keystore, `keytool -list` verifies the alias:

~~~bash
keytool -list -v \
  -storetype PKCS12 \
  -keystore src/main/resources/local-tls.p12 \
  -storepass changeit
~~~

Actual output lists the alias, certificate chain, and certificate details from creation. Never print private keys to the console, and never copy production keystores into unsafe environments.

**Trust store** holds certificates/CAs used by the server to verify peers as configured, e.g., when mTLS client authentication is enabled. It does not choose cipher suites.

**Certificate SAN** must match the hostname the client connects to; a completely valid cipher list can still be rejected by browsers/curl due to hostname mismatch, expiration, or self-signing. `curl -k` skips identity checks and only serves protocol/cipher experiments, not PKI deployment validation.

### mTLS Is an Independent Option

To require client certificates on an internal service, Spring Boot supports `server.ssl.client-auth` (e.g., `need`) paired with a trusted truststore/CA. However, mTLS requires planning enrollment, revocation/rotation, client identity mapping, and trust boundaries. Simply adding `client-auth: need` without a suitable truststore can lock out all clients.

TLS 1.2/1.3 version and cipher selection still occur on mTLS connections; client authentication **does not replace** strong protocol/cipher policies.

## 12. Outbound TLS from Spring Boot Is a Separate Problem

`server.ssl.*` configures **inbound connections to the embedded server**. It **does not automatically** control TLS versions/ciphers for **outbound** connections made by:
- `RestClient`/`RestTemplate` using an HTTP client implementation.
- `WebClient`/Reactor Netty client.
- JDBC drivers connecting to databases over TLS.
- Kafka, Redis, gRPC, or custom Java sockets.

For outbound connections, TLS settings belong to the **client transport**, client SSL context/bundle, or driver configuration. When Java clients call external APIs, JSSE `jdk.tls.client.protocols` can affect default client protocols in specific cases, but it is not a server configuration switch and does not apply universally to native TLS providers.

**Wrong-target example:** an app calling an older partner API raises `SSLHandshakeException` from an outbound `WebClient`. Editing `server.ssl.enabled-protocols` on embedded Tomcat will not affect the connection to the partner. Inspect the true TLS endpoint, client transport, certificate chain, and outbound policy.

Similarly, `management.server.ssl.*` can apply when Actuator runs on a separate management port; do not assume the management port shares the public traffic policy if configured separately.

## 13. Checking Cipher Support via JDK JSSE Instead of Guessing

A JDK has four distinct sets:
- **Supported cipher suites**: what the provider can implement.
- **Default enabled cipher suites**: what is enabled by default in the context.
- **Application-configured** suites: what the app/server asks to enable.
- **Actually negotiated** suite: the single **one** suite chosen after a handshake.

These are four different sets.

### Standalone Java 17 Example to Inspect JSSE

Save as `JsseCapabilities.java`:

~~~java
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class JsseCapabilities {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLParameters supported = context.getSupportedSSLParameters();
        SSLParameters defaults = context.getDefaultSSLParameters();

        System.out.println("Supported protocols:");
        Arrays.stream(supported.getProtocols()).sorted()
                .forEach(System.out::println);

        System.out.println("Default enabled protocols:");
        Arrays.stream(defaults.getProtocols()).sorted()
                .forEach(System.out::println);

        System.out.println("Default enabled cipher suites:");
        Arrays.stream(defaults.getCipherSuites()).sorted()
                .forEach(System.out::println);
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac JsseCapabilities.java
java JsseCapabilities
~~~

Stdout **has no fixed list** because it depends on JDK vendor, version, provider, security policy, and runtime settings. The three exact labels in output will be:

~~~text
Supported protocols:
...
Default enabled protocols:
...
Default enabled cipher suites:
...
~~~

The ellipses `...` represent lines printed by the JVM, not a literal output line. Check for `TLSv1.3`, `TLSv1.2`, and your desired suites in the actual output; **do not treat Java supporting a cipher as proof that your embedded server advertises it**. For the live endpoint, you still need a TLS handshake test against the listening port.

### Why Can a Suite Appear in JSSE Yet Fail to Handshake?

A suite may be excluded by:
- `jdk.tls.disabledAlgorithms`.
- Incompatible TLS version.
- Incompatible certificate key/signature scheme.
- Active provider/engine being OpenSSL/native rather than default JSSE.
- Additional policies in the embedded server.
- Client offer omitting that suite.

Always combine **runtime inventory** with **network handshake tests**.

## 14. Observing Handshakes and Measuring Risk When Changing Policy

Do not enable verbose TLS debugging broadly in production. In test environments, JSSE offers debugging flags:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar app.jar
~~~

`app.jar` is a placeholder; use your built JAR name. Handshake logs can contain extensive connection details, certificates, and sensitive metadata; use only in test environments and turn off once evidence is collected. If the runtime uses a native TLS provider, the JSSE flag may not show native engine handshake details.

Besides logs, monitor:
- Handshake success/failure rates at the **TLS terminator**.
- TLS version distribution and negotiated cipher suite distribution.
- Certificate trust/hostname mismatch errors, no shared cipher, and wrong protocol version errors.
- Negotiated HTTP version via ALPN: `h2` vs. `http/1.1`.
- TLS handshake latency, session resumption, crypto CPU, and resource usage.
- Affected client/user-agent/SDK segments during policy rollouts.

Never attach session secrets, certificate private material, or personal identifiers to metric labels. If tracking client compatibility, group by protocol/cipher/client SDK version or appropriately coarse, privacy-safe dimensions.

### Practical Policy A/B Rollout

Suppose the old config allows TLS 1.2/1.3 with JDK-selected ciphers. You want to lock TLS 1.2 down to `ECDHE_RSA` AES-GCM while keeping TLS 1.3:

1. Record baseline handshake success by client version and TLSv1.2/TLSv1.3 split.
2. Inventory external systems, mobile apps, Java SDKs, legitimate bots, health probes, and monitoring agents.
3. Test across relevant OS/runtimes, including clients lacking AES-GCM or TLS 1.3 support.
4. Test on a canary or isolated endpoint pool; avoid breaking all public traffic at once.
5. Verify both HTTPS **and** HTTP/2/`h2` ALPN.
6. Monitor handshake errors; if needed, roll back by reverting the policy on the **active TLS endpoint**.
7. Document certificate type, key rotation, JDK/provider, client inventory, and legacy protocol sunset dates.

The goal is **verifiable security and availability**, not chasing an "A grade" from a scanner while leaving real clients broken.

## 15. Common Errors and Verification Methods

| Symptom | Possible cause | Troubleshooting step |
|---|---|---|
| `SSLHandshakeException: handshake_failure` | No compatible suite/version, mismatched cert/signature or groups | Use `openssl s_client`, JSSE debug, inspect both cert and client offer |
| `protocol_version` | Client only supports rejected protocol versions | Compare enabled protocols on both sides; upgrade client |
| `no cipher suites in common` | Allowlist too narrow, wrong cert type, or unsupported provider | Compare suites by TLS version, RSA/ECDSA, JDK/provider |
| `wrong version number` when calling HTTPS | Client sends plaintext HTTP to TLS port, proxy wrong scheme, or wrong port | Verify URL, port, proxy hops, SSL termination |
| `curl: SSL certificate problem` | Untrusted self-signed/CA, wrong hostname, or broken chain | Use valid trust material; `-k` is only for local tests |
| TLS 1.3 works but TLS 1.2 fails | List only has TLS 1.3 ciphers or TLS 1.2/cert mismatch | Add suitable TLS 1.2 AEAD suites if fallback is needed |
| TLS 1.2 works but TLS 1.3 fails | Provider/JDK/version/ciphers lack TLS 1.3 support | Check runtime, `enabled-protocols`, and TLS 1.3 suites |
| Changed `server.ssl.ciphers` with no scan change | Using `server.ssl.bundle`, external TLS termination, or edited wrong instance | Check bundle options, proxy/LB/CDN, and actual deployed config |
| HTTPS OK but `curl --http2` ignores h2 | ALPN did not pick h2, server HTTP/2 disabled, or invalid TLS 1.2 cipher | Check `server.http2.enabled`, provider/server, HTTP/2 deps, ALPN trace |
| HTTP/2 connection gets `INADEQUATE_SECURITY` | TLS 1.2 negotiated a prohibited suite | Use RFC 9113-compliant suites and verify policy |
| Only HTTPS works, HTTP 8080 fails | App only enables a single connector on 8443 | Add proxy redirect or explicit connector setup |
| Local keytool keystore fails to load | Alias/path/password/type mismatch | `keytool -list`, check file in artifact and permissions |
| JAR works locally but fails in container | Missing secret/cert or `file:` path differs in container | Check mounts, filesystem permissions, and env bindings |
| Scanner only sees CDN ciphers | TLS terminates at CDN | Scan origin directly in authorized environment if needed; separate hops |
| mTLS breaks all clients | `client-auth: need` without client certs/trust chain | Check truststore, client certs, and CA |
| OpenSSL `-cipher` fails to force TLS 1.3 | Wrong flag | TLS 1.3 uses `-ciphersuites`; TLS 1.2 uses `-cipher` |
| TLS 1.1 test fails immediately on client | Client tool already disabled TLS 1.1 | Distinguish "client refused to try" from "server rejected" |

**Notable property-value pitfall:** casually writing `TLS1.3`, `TLSv1.3`, and `TLSv1_3`. In JSSE/Spring Boot protocol configuration, the standard names are **`TLSv1.3`** and **`TLSv1.2`**. Wrong names can cause startup/handshake errors depending on provider.

## 16. Security Checklist Before Enabling a New Configuration

- [ ] Identified the exact TLS terminator clients connect to: Spring Boot or proxy/CDN/LB.
- [ ] Selected TLS 1.3 and TLS 1.2 (or TLS 1.3-only based on client inventory), without enabling TLS 1.0/1.1.
- [ ] TLS 1.3 suites and TLS 1.2 suites are not confused by name or version.
- [ ] TLS 1.2 suites prioritize ECDHE + AEAD; no legacy static RSA key exchange/RC4/3DES/NULL/weak CBC.
- [ ] RSA/ECDSA certificate, SAN, key size, CA chain, and expiration are valid.
- [ ] Checked `jdk.tls.disabledAlgorithms`, JDK/provider, embedded server, and native TLS engine.
- [ ] If using an SSL bundle, placed options inside the bundle rather than ignored `server.ssl.ciphers`.
- [ ] If enabling HTTP/2, verified ALPN `h2` and RFC 9113 TLS 1.2 cipher requirements.
- [ ] HTTPS clients validate CA/hostname; never use `-k` or trust-all in production.
- [ ] Private keys/keystore passwords are protected and not committed to repos.
- [ ] Tested TLSv1.3, TLSv1.2, rejection of legacy TLS, allowed/disallowed ciphers, and real clients.
- [ ] Tested behind proxy/CDN and on backend hops if backends also use TLS.
- [ ] Handshake failure telemetry, rollback plan, and canary rollout are ready.
- [ ] Plan exists for JDK/Boot updates and periodic policy reviews.

## 17. Self-Check Questions

**Question 1.** Is `server.ssl.protocol: TLS` equivalent to `server.ssl.enabled-protocols: [TLSv1.3, TLSv1.2]`?

**Answer:** No. `protocol` initializes the SSL context/implementation, whereas `enabled-protocols` specifies which TLS protocol versions are permitted.

**Question 2.** Why cannot `TLS_AES_128_GCM_SHA256` replace `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` in a TLS 1.2 setup?

**Answer:** The first suite is TLS 1.3 and the second is TLS 1.2. TLS 1.3 separates key exchange/auth from cipher suites; names are not interchangeable across versions.

**Question 3.** Can HTTP/2 over TLS work if only TLS 1.2 is allowed?

**Answer:** Yes, provided ALPN and HTTP/2's TLS 1.2 requirements are satisfied. TLS 1.3 is strongly recommended where clients support it, though `h2` does not strictly mandate TLS 1.3.

**Question 4.** You set `server.ssl.bundle: webserver` and `server.ssl.ciphers`, yet endpoint scans show no change. What is the most likely reason?

**Answer:** When using a bundle, direct settings like `server.ssl.ciphers`/`enabled-protocols`/`protocol` are ignored; put them under `spring.ssl.bundle.jks.webserver.options` (or matching bundle type) and verify the actual TLS terminator.

**Question 5.** Why might an ECDSA cert fail to negotiate `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` in TLS 1.2?

**Answer:** That suite requires RSA authentication capability, which an ECDSA certificate does not provide. Choose suites matching your actual certificate type and clients.

**Question 6.** Can `curl -k` be used to conclude a production certificate has the right identity?

**Answer:** No. `-k` skips certificate verification. Use it only for local self-signed demos; production requires proper CA, SAN, chain, and expiration validation.

**Question 7.** If browsers connect to a CDN over TLS 1.0, will changing `server.ssl.enabled-protocols` on the Boot origin block it?

**Answer:** Not if client-facing TLS terminates at the CDN. You must update TLS policy on the CDN; the Boot origin only controls hops where it is the TLS endpoint.

**Question 8.** When a TLS 1.1 handshake test fails, is that sufficient proof the server rejected TLS 1.1?

**Answer:** Not necessarily. Client OpenSSL/curl may block TLS 1.1 locally on the client side. You need a tool capable of sending a valid TLS 1.1 `ClientHello` or inspect server handshake logs to confirm.

**Extension exercise:** Starting from section 8, change `enabled-protocols` to only `TLSv1.3` in a test environment, then test forced TLSv1.3 and forced TLSv1.2 connections. Record the exact errors and explain why the failed request never enters the controller. Next, restore the initial policy, switch to section 7's SSL bundle, and set versions/ciphers only under `spring.ssl.bundle.jks.webserver.options`. Finally, test HTTP/2 and compare ALPN protocol selection with TLS version selection.

## 18. References

- [Spring Boot 3.5 — Common Application Properties (`server.ssl.*`)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Embedded Web Servers: SSL, SSL bundles, and HTTP/2](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot — SSL bundles (JKS/PKCS12/PEM)](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Oracle Java 17 — Transport Layer Security Protocol Overview](https://docs.oracle.com/en/java/javase/17/security/transport-layer-security-tls-protocol-overview.html)
- [Oracle Java 17 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 9325 — Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325)
- [RFC 9113 — HTTP/2, `9.2` and Appendix A on TLS/cipher suites](https://www.rfc-editor.org/rfc/rfc9113.html)

**Takeaway:** choosing **TLS versions**, **cipher suites**, **certificates/keys**, and **HTTP/2 ALPN** are four related yet distinct decisions. Syntactically valid YAML is not enough: policy only has real effect when applied at the **actual TLS endpoint** and verified via handshakes from the clients your service needs to support.