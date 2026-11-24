# TLS, Server Certificates, Private Keys, and Certificate Chains in Spring Boot

**Context:** Spring Boot → web-runtime → TLS and HTTP/2. This lesson explains how HTTPS authenticates a server via an X.509 certificate, the roles of the private key and public key, the CA trust chain, how to configure HTTPS in Spring Boot (PKCS12, PEM, and SSL bundles), how to inspect endpoints with `keytool`/`openssl`/`curl`, certificate operations, TLS termination, mTLS, and the relationship with HTTP/2.

**Example environment:** Java 17+, Maven, Spring Boot **3.5.0**, Spring MVC with embedded Tomcat. The domains, paths, passwords, and certificate files in this lesson are **illustrative**. Only create self-signed certificates for learning on `localhost`; production must use an identity and CA chain that match your infrastructure.

## 1. The Big Picture: What Does HTTPS Use TLS For?

**HTTPS = HTTP running over TLS**. TLS is a protocol that establishes an encrypted and integrity-checked channel between two connection endpoints. In the standard public HTTPS model, TLS provides:

1. **Server authentication:** the client can verify that the server it is talking to actually controls the private key corresponding to a valid certificate for the hostname the client intends to access.
2. **Confidentiality of content in transit:** third parties observing the network cannot directly read the encrypted HTTP requests/responses.
3. **Tamper detection in transit:** data is authenticated using the cryptographic mechanisms of the TLS session.
4. **Connection parameter negotiation:** the TLS version, algorithms, and in many deployments the application protocol (ALPN: `h2` or `http/1.1`).

TLS does **not** automatically authenticate users into accounts, does not fix SQL injection/XSS vulnerabilities, does not hide all network metadata (such as the destination IP address), and does not protect data after the application has decrypted it at the TLS termination point.

~~~text
                       HTTPS request
Browser/client ─────────────────────────────────────► HTTPS endpoint
   │                      TLS handshake                    │
   │  1. ClientHello, SNI, ciphers, key shares, ALPN        │
   │  2. ServerHello + X.509 certificate and chain          │
   │  3. Verify hostname, CA, validity, key usage           │
   │  4. Server proves private key possession; finish keys  │
   │◄───────────────────────────────────────────────────────│
   │             Then send encrypted HTTP                   │
   │◄══════════════════ protected data ════════════════════►│
~~~

Note: this diagram is a conceptual explanation, **not** an exact transcript of the order of every TLS 1.2/1.3 message. In TLS 1.3, part of the handshake (including certificate messages) is already protected by handshake traffic keys. TLS 1.3 typically uses (EC)DHE to establish a shared secret; the private key associated with the certificate is used for **authentication/signature**, and one should not loosely say that "the server uses the private key to decrypt all HTTPS traffic."

## 2. Four Objects to Distinguish

| Object | What does it contain? | Sent to the client? | Must be kept secret? |
| --- | --- | --- | --- |
| **Server certificate (leaf/end-entity)** | X.509: public key, SAN/identity, issuer, serial, validity, extensions, CA signature | **Yes** during handshake | **No**, though information inside the cert may still need classification |
| **Server private key** | Secret key matching the public key in the leaf certificate | **Never** sent in the handshake | **Yes — strictly** |
| **Intermediate CA certificate(s)** | Public key and identity of intermediate CAs, signed by a higher-level CA | **Usually yes**, sent by the server alongside the leaf | No; these are public certificates |
| **Root CA certificate / trust anchor** | Public key of the root CA trusted by the client via its trust store | Usually **not needed** from the server; the client already has it | The certificate is not secret; the **root CA private key** is extremely sensitive |

How to remember: **a certificate states "which identity this public key belongs to, and who vouches for it,"** **the private key proves control over that public key**, and **the certificate chain provides a verification path back to a CA that the client trusts**.

### 2.1. Do Not Equate a Certificate with a Private Key

A certificate can be inspected with `openssl x509 -text` because it is public data. Copying a certificate does not give anyone the ability to impersonate a website if that party **does not possess the corresponding private key**. Conversely, if a private key is compromised, another party can impersonate the endpoint for a valid certificate under the right conditions; you must **revoke/replace the key and certificate**, not merely change the Java KeyStore password and assume you are safe.

A certificate file typically contains a block like:

~~~text
-----BEGIN CERTIFICATE-----
... Base64-encoded X.509 certificate ...
-----END CERTIFICATE-----
~~~

A PEM private key may be in PKCS#8 format:

~~~text
-----BEGIN PRIVATE KEY-----
... private key material: NEVER share ...
-----END PRIVATE KEY-----
~~~

Or encrypted PKCS#8 starting with `-----BEGIN ENCRYPTED PRIVATE KEY-----`. Do not paste real private keys into issues, logs, chats, READMEs, Git, public container images, or URLs. The placeholders here are **not real keys**.

### 2.2. What Is a CSR?

A **Certificate Signing Request (CSR)** contains the certificate request details and public key, usually with a signature proving the requester holds the private key. The CSR is sent to a CA to verify the subject/domain and issue a certificate. **Do not send the private key to the CA** in a normal certificate issuance workflow.

~~~text
Domain owner:
  Generate key pair → keep private key secret
                    → create CSR (public key + identity)
                    → submit CSR / prove domain control
CA:
  Check policy → sign leaf certificate
Domain owner:
  Receive leaf cert and chain
  Deploy leaf + intermediates + matching private key
~~~

A CSR accepted by a CA does not guarantee every SAN the requester included will be issued: the CA may restrict them based on domain validation/policy. For public clients, the domain name must match the **SAN of the actual certificate** the server sends.

## 3. Reading a Server X.509 Certificate

Important fields/extensions:

| Field | Meaning | What to check |
| --- | --- | --- |
| **Subject / CN** | Subject recorded in the certificate | Do not use CN instead of SAN as the modern hostname rule |
| **Subject Alternative Name (SAN)** | DNS names/IPs covered by the certificate | `DNS:api.example.com` or `IP:192.0.2.10` must match the accessed name |
| **Issuer** | CA that issued the certificate | Valid chain exists from issuer to a trusted root |
| **Not Before / Not After** | Validity period | Client/server clocks and certificate expiration |
| **Subject Public Key Info** | Algorithm and public key | Matches the private key in the keystore |
| **Signature Algorithm** | How the issuer signed the certificate | Sufficiently strong algorithm supported by clients |
| **Basic Constraints** | `CA:FALSE` on leaf; `CA:TRUE` on CA | Do not confuse a leaf certificate with a CA certificate |
| **Key Usage** | For example `digitalSignature`; CAs usually have `keyCertSign` | Matches the certificate's purpose |
| **Extended Key Usage (EKU)** | For example `serverAuth`, `clientAuth` | A server TLS certificate must be valid for server authentication per client policy |
| **Serial Number / SKI / AKI** | Identifier and issuer linking hints | Useful when debugging chains and rotation |

**The hostname must match a SAN of the right type.** If accessing `https://api.example.com`, the certificate must match `DNS:api.example.com` or a valid wildcard. If accessing via `https://127.0.0.1`, a SAN containing only `DNS:localhost` is not equivalent to `IP:127.0.0.1`. A wildcard `*.example.com` typically matches a single label such as `api.example.com` but does **not** automatically match `example.com` or `a.b.example.com`.

**Not being expired does not automatically make a certificate valid.** A certificate within its validity window that has the wrong hostname, is missing an intermediate, was issued for the wrong purpose, cannot chain to a trust anchor, or has a mismatched key can still cause handshake/verification failure.

## 4. Certificate Chains and Trust Stores

Example of a simple PKI hierarchy:

~~~text
                       CLIENT TRUST STORE
                    ┌─────────────────────┐
                    │ Root CA certificate │  ◄── Trust anchor
                    │   Root public key   │      chosen by the client
                    └──────────┬──────────┘
                               │ verify issuer signature
                    ┌──────────▼──────────┐
                    │ Intermediate CA cert│  ◄── Server usually sends
                    │  Inter public key   │
                    └──────────┬──────────┘
                               │ verify issuer signature
                    ┌──────────▼──────────┐
                    │ Server leaf cert    │  ◄── Server sends first
                    │ SAN: api.example.com│
                    │  Server public key  │
                    └──────────┬──────────┘
                               │ verify proof of key possession
                    ┌──────────▼──────────┐
                    │ SERVER private key  │  ◄── Stored only on server
                    └─────────────────────┘
~~~

**Verification direction:** the client uses the intermediate CA's public key to verify the signature on the leaf; uses the root CA's public key to verify the signature on the intermediate; the root is trusted by **the client's trust policy**, not merely because the root is self-signed. The client also checks SAN, validity period, CA constraints, EKU, signatures/algorithms, and validation/revocation policies depending on the environment.

A self-signed root **does not automatically become trusted**. Adding your own root to a trust store is an independent trust decision by the client/organization.

### 4.1. Which Certificates Should the Server Send?

In typical deployments, the server sends the chain in order:

1. **Leaf/server certificate** (containing the public key matching the server private key).
2. One or more **intermediate CA certificates**, chaining sequentially toward the trust anchor.
3. **The root CA certificate usually does not need to be included in fullchain**; the client must already trust that root. Sending the root does not make a client accept an unknown root.

~~~text
fullchain.pem  (contains only public certificates)
  -----BEGIN CERTIFICATE-----  # leaf: api.example.com
  ...
  -----END CERTIFICATE-----
  -----BEGIN CERTIFICATE-----  # intermediate CA
  ...
  -----END CERTIFICATE-----

privkey.pem    (DIFFERENT file, contains private key)
  -----BEGIN PRIVATE KEY-----
  ...
  -----END PRIVATE KEY-----
~~~

**Do not put the private key into `fullchain.pem`.** A server configuration needs the **certificate chain + corresponding private key**; accidentally providing only the intermediate instead of the leaf, using a private key from another certificate, or omitting an intermediate are common operational mistakes.

Some CAs provide separate files `cert.pem` (leaf), `chain.pem` (intermediates), and `fullchain.pem` (leaf + intermediates). **Filenames are only a convention**: inspect the actual contents rather than assuming from the filename.

### 4.2. Keystore and Truststore Serve Two Different Purposes

- **Server keystore / key material:** holds the server private key **and** its corresponding certificate chain so the server can perform the TLS handshake.
- **Client truststore:** contains the trust anchors (CA certificates) that the client uses to decide which server certificates to trust. Browsers, the JVM, the OS, and some applications maintain separate trust stores.
- **Server truststore** is relevant when the server needs to **authenticate client certificates** (mTLS), or when the JVM acts as a TLS client calling external services via the corresponding trust configuration. It does not replace the certificate chain the server must present.

**Common misconception:** Importing a root CA into the keystore holding the server key and thinking HTTPS is now automatically valid on client machines. A client that does not trust that root will still reject it. Conversely, adding the root CA to a browser trust store **does not fix** a server missing its private key or having the wrong SAN.

## 5. TLS 1.3 Handshake: How Do the Public Key and Private Key Participate?

In TLS 1.3 certificate-based server authentication, the abbreviated flow is:

1. The browser sends `ClientHello`, containing TLS versions/cipher suites, key shares (for key exchange), and possibly **SNI** (`api.example.com`) and **ALPN** (`h2`, `http/1.1`).
2. The server selects parameters, returns `ServerHello`, along with the required handshake messages; both sides compute handshake traffic secrets from (EC)DHE or an appropriate mechanism.
3. The server sends its certificate chain; the client verifies it against a trust anchor along with the hostname, validity period, and constraints.
4. The server sends `CertificateVerify`, signing the handshake transcript with the **private key corresponding to the leaf certificate** to prove key possession.
5. Both sides verify `Finished`, derive application traffic keys, and proceed to exchange protected HTTP traffic.

**The private key is not sent over the network.** In TLS 1.3, the certificate's private key is not "the symmetric key used to encrypt each HTTP packet"; traffic keys are derived from the key exchange/handshake. Consequently, keys/certificates can be rotated per policy without confusing them with session keys; modern TLS 1.3 provides forward secrecy in handshakes using appropriate ephemeral DHE.

A certificate does not itself encrypt requests; it serves to **authenticate** the peer during the TLS handshake. An attacker can generate a self-signed certificate for `api.example.com`, but normal browsers will **not trust it** unless the attacker can get their trust anchor into the client truststore or exploit a PKI incident.

### 5.1. SNI and ALPN Are Not the Same Thing

- **SNI (Server Name Indication):** the client sends the hostname so the server/proxy can select the right certificate when multiple domains share an IP:port. Having SNI **does not prove** the certificate is valid; the client must still verify the SAN and chain.
- **ALPN (Application-Layer Protocol Negotiation):** the TLS handshake selects the application protocol such as `h2` (HTTP/2 over TLS) or `http/1.1`. A valid certificate **does not guarantee** HTTP/2 is used.
- **TLS termination:** the point where the TLS connection ends and HTTP is decrypted (a load balancer, ingress, reverse proxy, or Spring Boot itself). The certificate/private key must reside at the **point that actually terminates TLS**, not necessarily in the JVM.

## 6. Common Certificate/Key File Formats

| Format | Characteristics | Usage in Java/Spring Boot |
| --- | --- | --- |
| **PEM** | Base64 + `BEGIN/END ...`; can hold cert, chain, private key (often separate files) | Spring Boot supports direct PEM config or a PEM SSL bundle |
| **DER** | Binary ASN.1/X.509 data | Can be converted to PEM for inspection/configuration |
| **PKCS#12** (`.p12`, `.pfx`) | Container that can hold private key + certificate chain, usually password-encrypted | `server.ssl.key-store` or JKS-type SSL bundle with type `PKCS12` |
| **JKS** | Traditional Java keystore | `keytool` and `server.ssl.*` config or SSL bundle |
| **PKCS#8** | Private key format (can be PEM/DER, encrypted/unencrypted) | Preferred for PEM private keys with Spring Boot |
| **CSR** (`.csr`) | Certificate signing request and public key, **not a server certificate** | Sent to a CA, not used as a server certificate |

PEM `-----BEGIN RSA PRIVATE KEY-----` may be PKCS#1; `-----BEGIN EC PRIVATE KEY-----` is the traditional EC format. Spring Boot documentation recommends **PKCS#8** where possible, with `-----BEGIN PRIVATE KEY-----` or `-----BEGIN ENCRYPTED PRIVATE KEY-----`. For an existing private key file in another format, it can be converted using a securely controlled procedure, for example:

~~~bash
# For secure environments; this command produces an unencrypted PKCS#8 private key.
openssl pkcs8 -topk8 -nocrypt -in legacy-server.key -out server-pkcs8.key
~~~

**Warning:** `-nocrypt` produces an unencrypted private key without a password. Only use it when the key is strictly protected by file permissions, secret volumes, access controls, backup/encryption, and an appropriate rotation process. Do not assume PKCS#8 means an encrypted key by default.

## 7. Runnable Lab: Spring Boot HTTPS on localhost with PKCS12

A minimal example with one Java class, one properties file, and a self-created keystore using the JDK `keytool`. The app has a `GET /` endpoint returning exact text, allowing you to actually test HTTPS, SAN, and trust. **No public CA is required**, so clients that have not added trust will warn about the self-signed certificate.

### 7.1. Create the Maven Project

Directory tree:

~~~text
tls-demo/
├── pom.xml
├── certs/                       # local-dev.p12, local-dev.crt (do not commit)
└── src/main/
    ├── java/com/example/tlsdemo/TlsDemoApplication.java
    └── resources/application.properties
~~~

**`pom.xml`**:

~~~xml
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
  <artifactId>tls-demo</artifactId>
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

**`src/main/java/com/example/tlsdemo/TlsDemoApplication.java`**:

~~~java
package com.example.tlsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class TlsDemoApplication {
    @GetMapping("/")
    public String hello() {
        return "HTTPS ready\n";
    }

    public static void main(String[] args) {
        SpringApplication.run(TlsDemoApplication.class, args);
    }
}
~~~

This Java code runs in Spring Boot, so use Maven to resolve dependencies and compile, **not** just `javac TlsDemoApplication.java` unless you manually provide the full Spring Framework classpath.

### 7.2. Generate a Private Key and Self-Signed Certificate with SAN

In the **root of the `tls-demo` project**, create the `certs` directory. In Bash:

~~~bash
mkdir -p certs
keytool -genkeypair \
  -alias local-server \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 7 \
  -storetype PKCS12 \
  -keystore certs/local-dev.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=localhost, OU=Training, O=Example, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -ext "EKU=serverAuth"
~~~

On PowerShell, you can write the entire `keytool` command on **one line** (or use backtick continuation per PowerShell syntax; do not copy Bash's `\` continuation character). The command creates a `PrivateKeyEntry` with an RSA private key and a self-signed certificate valid for 7 days, with SANs for **localhost** and **127.0.0.1**. The password `changeit` is only a **demo value**; do not use it in production and do not commit the keystore.

Export the **public** certificate to PEM so `curl` can trust this specific certificate in the lab:

~~~bash
keytool -exportcert -rfc \
  -alias local-server \
  -keystore certs/local-dev.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -file certs/local-dev.crt
~~~

Important: `local-dev.crt` **contains only the certificate**, not the private key. `local-dev.p12` contains the private key and **must** be protected. Only export the certificate to a public file to grant trust in a test environment.

Inspect the keystore:

~~~bash
keytool -list -v \
  -keystore certs/local-dev.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -alias local-server
~~~

In the output, look for `Entry type: PrivateKeyEntry`, `Certificate chain length: 1` (self-signed demo), `SubjectAlternativeName` containing `localhost`/`127.0.0.1`, and the validity dates. Do not expect a chain of length 1 to be trusted by browsers: self-signed certificates are not in public root stores.

### 7.3. Configure HTTPS with server.ssl.* (PKCS12)

File **`src/main/resources/application.properties`**:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./certs/local-dev.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=local-server

# Optional: enable HTTP/2 when supported by the embedded web server/runtime.
server.http2.enabled=true
~~~

`file:./certs/local-dev.p12` is resolved relative to the process **working directory**, not the Java source directory; run from the project root when testing. When deploying via JAR/Docker, you can use an absolute path such as `file:/etc/tls/server.p12` provided by a container volume.

**Do not hard-code the keystore password in `application.properties`**. Set an environment variable so Spring reads `${TLS_KEYSTORE_PASSWORD}`. In Bash (local lab only):

~~~bash
TLS_KEYSTORE_PASSWORD=changeit mvn spring-boot:run
~~~

In PowerShell:

~~~powershell
$env:TLS_KEYSTORE_PASSWORD = "changeit"
mvn spring-boot:run
~~~

Environment variables are a simple example, **not** a replacement for a production secret manager. Do not print passwords to logs, do not commit shell history containing real secrets, and restrict who can read secrets at runtime.

When `server.ssl.key-store` and a valid SSL config are present, Spring Boot opens HTTPS on **8443**. The app does not simultaneously create an HTTP 8080 connector just because 8080 was previously the default; wanting both separate HTTP and HTTPS on an embedded server usually requires additional programmatic configuration or using a proxy/ingress.

### 7.4. Run Trust Tests Properly

In another terminal:

~~~bash
# Only to observe the expected error of an untrusted self-signed certificate.
curl -v https://localhost:8443/

# Tell curl to trust the lab's specific certificate; still verifies the hostname.
curl --cacert certs/local-dev.crt -sS https://localhost:8443/
~~~

**Expected stdout of the second command (response body):**

~~~text
HTTPS ready
~~~

The body has a trailing newline because the Java method returns `"HTTPS ready\n"`. The first `curl -v` line typically fails with a trust/self-signed certificate error — this is **correct and expected**, not a Spring Boot bug. After providing `--cacert`, `curl` uses the certificate file as the trust anchor for the lab; this only trusts that specific certificate and **does not automatically add it to every browser/JVM trust store**.

You can test accessing via `127.0.0.1` since the SAN includes `IP:127.0.0.1`:

~~~bash
curl --cacert certs/local-dev.crt -sS https://127.0.0.1:8443/
~~~

Do not use `-k`/`--insecure` as a way to "fix SSL" in production: it disables certificate/hostname verification and masks real errors. If used temporarily to separate routing from trust in a lab, note clearly that it is only for local diagnostics.

**Note when testing HTTP/2:** If `curl` was compiled with HTTP/2 support, you can run:

~~~bash
curl --http2 --cacert certs/local-dev.crt -v https://localhost:8443/
~~~

Observe ALPN and the HTTP version in the output. Getting `h2` depends on the actual runtime/configuration; if it only uses `http/1.1`, HTTPS can still be working properly. **HTTP/2 is an HTTP protocol selection, not proof that the chain is trusted**.

## 8. Configuring PEM and SSL Bundles in Spring Boot

Spring Boot 3.5 supports multiple ways to provide TLS key material. **Choose one configuration style for the same connector**; avoid mixing certificate/key sources where it becomes unclear which material is used.

### 8.1. Direct PEM via server.ssl.*

If you have the certificate chain and private key in PEM:

~~~properties
server.port=8443
server.ssl.certificate=file:/etc/tls/fullchain.pem
server.ssl.certificate-private-key=file:/etc/tls/privkey.pem
server.http2.enabled=true
~~~

This is an **alternative** to PKCS12 in section 7; do not use it simultaneously with `server.ssl.key-store` on the same connector. `fullchain.pem` contains the leaf and intermediates in the right order; `privkey.pem` must be the private key matching the leaf, ideally in PKCS#8. Permissions on the private key file must be sufficiently strict.

### 8.2. SSL Bundle with PEM (Named, Reusable Configuration)

~~~properties
server.port=8443

spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/tls/fullchain.pem
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/tls/privkey.pem

server.ssl.bundle=web
server.http2.enabled=true
~~~

An **SSL bundle** groups certificates/keys/trust/options into a named unit. `server.ssl.bundle=web` instructs the web server to use that bundle. Outgoing connections such as HTTP clients and databases can also be configured to use separate bundles when the integration supports it; **a bundle for the server does not automatically change the truststore of all outbound clients**.

**Important:** `server.ssl.bundle` **cannot be combined** with discrete keystore/PEM options like `server.ssl.key-store`, `server.ssl.certificate`, etc. The properties `server.ssl.ciphers`, `server.ssl.enabled-protocols`, and `server.ssl.protocol` are ignored when using a bundle; those TLS options must be placed under `spring.ssl.bundle.<type>.<name>.options` per the corresponding documentation.

### 8.3. SSL Bundle with PKCS12

If the cert/key are already in PKCS12:

~~~properties
server.port=8443

spring.ssl.bundle.jks.web.keystore.location=file:/etc/tls/server.p12
spring.ssl.bundle.jks.web.keystore.type=PKCS12
spring.ssl.bundle.jks.web.keystore.password=${TLS_KEYSTORE_PASSWORD}
spring.ssl.bundle.jks.web.key.alias=server

server.ssl.bundle=web
~~~

The `jks` property group supports keystore material of type **JKS or PKCS12**; it does not mean you must convert PKCS12 to JKS format. The alias `server` must match the alias holding the **PrivateKeyEntry** in `server.p12` (inspect with `keytool -list`).

### 8.4. Reloading Changed Certificates on Disk

With a compatible Spring Boot version and PEM bundle, you can enable:

~~~properties
spring.ssl.bundle.pem.web.reload-on-update=true
spring.ssl.bundle.pem.web.keystore.certificate=file:/etc/tls/fullchain.pem
spring.ssl.bundle.pem.web.keystore.private-key=file:/etc/tls/privkey.pem
server.ssl.bundle=web
~~~

Spring Boot has a watcher that detects changes and reloads the bundle; **the consumer must support reloading**—for example, the **Tomcat** and **Netty** web servers listed in Spring Boot documentation. Do not assume every embedded container, every open connection, or every custom `SSLContext` automatically picks up the new certificate. Reloading **does not issue/renew certificates**: Certbot/ACME controllers/CAs and external operational processes remain responsible for renewing and updating the files.

When automating rotation, update files safely (for example via atomic updates or a coordinated key/cert procedure) so the watcher never catches a **new certificate + old private key** mid-update. Monitor error logs, post-reload handshakes, and expiration dates. In multi-instance deployments, ensure every instance receives the corresponding matching version.

## 9. Production Certificate Chains: Leaf, Intermediate, and Root

Suppose the organization receives:
- `leaf.pem`: the certificate issued for `api.example.com`;
- `intermediate.pem`: the intermediate certificate(s) from the CA;
- `root.pem`: the **public** root CA, used only to test path validation under the trust policy;
- `privkey.pem`: the private key generated and kept secure beforehand.

### 9.1. Assembling fullchain in the Right Order

In Bash:

~~~bash
cat leaf.pem intermediate.pem > fullchain.pem
~~~

If there are multiple intermediates, append them in order from the issuer closest to the leaf up toward the root. **Do not append the private key to fullchain**. The root usually does not need to be sent. On Windows, avoid concatenating PEM files using operations that change encoding to UTF-16 or add stray characters; use a tool that preserves bytes.

### 9.2. Verifying the Chain and Hostname

~~~bash
openssl verify \
  -purpose sslserver \
  -verify_hostname api.example.com \
  -CAfile root.pem \
  -untrusted intermediate.pem \
  leaf.pem
~~~

When the root CA is trusted in your command and the chain/purpose/hostname are valid, the typical result is:

~~~text
leaf.pem: OK
~~~

**`openssl verify ... -CAfile root.pem` does not prove that Chrome, Java, or all client machines trust that root.** It only verifies under the **trust root you just specified**. In production, you must verify the chain against the real trust anchors of your target clients.

Inspect the certificate:

~~~bash
openssl x509 -in leaf.pem -noout -subject -issuer -dates -serial
openssl x509 -in leaf.pem -noout -ext subjectAltName
openssl x509 -in intermediate.pem -noout -text
~~~

Check `Basic Constraints: CA:TRUE` on the intermediate, the leaf SAN, validity dates, and algorithms. An expired certificate will cause clients to reject connections even though the Spring Boot process is still running normally.

### 9.3. Checking Whether the Private Key Matches the Leaf Certificate

A safe check is to compare the **SHA-256 of the DER-encoded public key** extracted from both sources:

~~~bash
# Public key recorded in the leaf certificate:
openssl x509 -in leaf.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256

# Public key derived from the private key:
openssl pkey -in privkey.pem -pubout -outform DER \
  | openssl dgst -sha256
~~~

If both digests match, the public/private keys belong to the same pair (per the public representation used for comparison). You do **not** need to export or print the private key contents to the terminal/logs to verify this. If the private key is encrypted, OpenSSL may prompt for a passphrase; handle input securely.

### 9.4. Packaging into PKCS12 When Needed

If Spring Boot needs PKCS12 instead of PEM:

~~~bash
openssl pkcs12 -export \
  -inkey privkey.pem \
  -in leaf.pem \
  -certfile intermediate.pem \
  -name server \
  -out server.p12
~~~

OpenSSL will prompt for a password to protect the output file. Verify:

~~~bash
keytool -list -v -storetype PKCS12 -keystore server.p12
~~~

The alias `server` needs a **PrivateKeyEntry** and certificate chain (usually length 2 or more depending on intermediates). Do not import only a leaf certificate as a `trustedCertEntry` and expect the embedded server to have a private key to prove its identity.

**Do not put the root CA private key into the server keystore.** The root public certificate can be placed in client truststores; the root private key must be protected separately per CA policy.

## 10. Using OpenSSL to Inspect a Live Endpoint

### 10.1. Viewing Which Certificates the Server Sends

~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error < /dev/null
~~~

Observe:
- The chain sent by the server (usually leaf, intermediate).
- The leaf's `subject`, `issuer`, validity dates, and SAN.
- The verification result against the trust store OpenSSL is using.
- Negotiated protocol/cipher.

`-servername` provides **SNI**, which is critical when a shared IP serves multiple virtual hosts. If `-servername` is omitted, the server may return the **default certificate of another domain**, causing the misunderstanding that "the wrong cert is installed on the server." Running `s_client` alone does not replicate all browser hostname validation logic; when you need to check the hostname on the CLI, use:

~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -verify_hostname api.example.com \
  -verify_return_error < /dev/null
~~~

Depending on the OpenSSL version, output and exit codes may vary; check the specific `Verify return code` and errors, and do not conclude success merely from `CONNECTED` (that only indicates TCP opened).

### 10.2. Testing with curl

~~~bash
curl -v https://api.example.com/health
curl --http2 -v https://api.example.com/health
~~~

`curl --http2` only works when curl was built with HTTP/2 support, and successful negotiation also depends on the server/proxy. Do not add `-k` to "make it work": if TLS verification fails, fix the SAN, chain, CA trust, or system time.

With a managed private CA where you have the public root file:

~~~bash
curl --cacert root.pem -v https://api.internal.example/health
~~~

`--cacert` makes curl trust the specified CA **for that request**. Verify that the hostname matches the SAN; do not force an IP URL when the cert only has a DNS SAN.

### 10.3. Distinguishing Root/Intermediate Issues from Local Trust

Scenario A: the server sends the leaf but **forgets the intermediate**. Clients that do not already have the intermediate cached may fail with `unable to get local issuer certificate` or `PKIX path building failed`. The primary fix is to configure **fullchain** properly on the server; do not force all clients to import the intermediate themselves.

Scenario B: the server sends the complete leaf + intermediate, but the private CA's root is **not in the client's trust store**. You must manage distributing/provisioning the trust root to authorized clients, rather than trying to fix the chain by appending an unknown root and expecting browsers to trust it.

Scenario C: the leaf cert has a valid chain, but the hostname is wrong. Replace the certificate with one containing the **correct SAN**, rather than importing another root CA to bypass hostname validation.

## 11. SNI and Multiple Domains on the Same HTTPS Port

A load balancer or embedded server can serve multiple hostnames sharing an IP:443. The client sends `server_name` in the TLS ClientHello so the endpoint can choose the appropriate certificate. Each certificate must still match the SAN for its corresponding domain.

Spring Boot 3.5 supports mapping **SSL bundles by SNI** on compatible embedded servers. For example, assuming bundles `web` and `web-alt` are declared:

~~~properties
server.port=8443
server.ssl.bundle=web

server.ssl.server-name-bundles[0].server-name=alt.example.com
server.ssl.server-name-bundles[0].bundle=web-alt
~~~

Bundle `web` is the default; `web-alt` is for `alt.example.com`. SNI support differs across **Tomcat, Netty, Undertow, and Jetty**; per Spring Boot 3.5 documentation, explicit server-name bundle configuration applies to Tomcat/Netty/Undertow; Jetty has its own SNI mechanism that selects automatically when multiple certificates are present. Test against your exact embedded server and Java version.

**Important note:** SNI happens **before the HTTP request path**. You cannot select a certificate based on `/api/v1` or a controller while the TLS handshake has not yet completed. The SNI hostname and HTTP Host should be checked appropriately; a reverse proxy may route based on host, but it must protect against unauthorized Host headers.

## 12. TLS and HTTP/2: Related but Not the Same

HTTP/2 is a protocol version **at the HTTP layer**, whereas TLS is the transport security layer. Spring Boot has the property:

~~~properties
server.http2.enabled=true
~~~

If the server uses TLS, client and server can negotiate HTTP/2 over TLS (ALPN protocol **`h2`**) when both support it. Without TLS in certain configurations/stacks, Spring Boot can support **h2c** (HTTP/2 cleartext) for backends or internal connections behind a proxy. Modern web browsers generally use HTTPS for public HTTP/2.

Comparison:

| Scenario | Client ↔ TLS point | TLS point ↔ Spring Boot | What you observe |
| --- | --- | --- | --- |
| Spring Boot terminates TLS itself | `https://app.example.com` → Spring Boot | No proxy terminator | Cert/key live in JVM/embedded server; ALPN may select h2 |
| Proxy terminates TLS | `https://app.example.com` → Nginx/Ingress/LB | Proxy → Boot may be HTTP/1.1/h2c or new TLS | Public cert lives on proxy; Boot does not necessarily need public-domain private key |
| End-to-end / re-encryption | TLS client → proxy | TLS proxy → Boot (another TLS hop) | Two handshakes, two potentially different cert/trust sets |
| TLS 1.3 succeeds but HTTP/1.1 used | TLS is still fine | Any | Server/client did not pick h2 or h2 is disabled, not a certificate error |

If TLS termination happens at a proxy, `server.http2.enabled=true` on Spring Boot **does not force** browsers to use HTTP/2; the browser negotiates ALPN with the **proxy**. Configure the proxy accordingly. When the proxy forwards `X-Forwarded-Proto`/`Forwarded`, Spring Boot must be configured to trust and parse forwarded headers **from trusted proxies**, preventing external clients from spoofing scheme/host via headers.

**HTTPS redirect and HSTS:** For public websites, consider appropriate HTTP → HTTPS redirects and `Strict-Transport-Security`. Only enable HSTS (especially `includeSubDomains` or preload) when the entire domain/subdomains reliably support HTTPS; misconfiguration can make test environments hard to access.

## 13. Server Authentication vs. Mutual TLS (mTLS)

Standard **TLS server authentication**: the server presents a certificate, the client verifies the server; the client authenticates users at the application layer (cookies, OAuth, tokens, etc.) if needed.

**mTLS (mutual TLS):** adds a step where the **server requests and verifies a client certificate**. Both sides have key material; the server needs a truststore/CA policy to validate the client certificate.

~~~text
One-way TLS:
  Client ── checks server certificate/chain/SAN ─► Server
  Server has a private key; client does not necessarily have a client certificate.

mTLS:
  Client ⇄ Server
  Client checks server certificate.
  Server checks client certificate/chain/purpose/policy.
  Client proves possession of client private key.
~~~

In Spring Boot, server mTLS configuration includes properties such as:

~~~properties
server.ssl.client-auth=need
server.ssl.trust-store=file:/etc/tls/client-ca-truststore.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=${CLIENT_TRUSTSTORE_PASSWORD}
~~~

**This is an illustrative configuration snippet, not a replacement for the server certificate config:** you still need the server keystore/SSL bundle. `need` requires a client certificate (without one or if invalid, the handshake typically fails); `want` requests it optionally, depending on authentication policy. The truststore here is for **verifying client certs**, not holding the server private key.

In an ingress/proxy mTLS model, the **proxy** itself may validate the client certificate and pass the verified identity to Spring Boot. The app must not trust headers such as `X-Client-Cert` from public clients if headers can be spoofed; accept them only from a trusted proxy over a protected channel with header stripping/overwriting configured.

mTLS authenticates a machine/application identity or certificate holder; **business-level permissions** still require authorization. Do not turn "has a valid certificate" into unlimited admin privileges.

## 14. Secure Certificate and Private Key Operations

### 14.1. Create, Issue, Deploy, Rotate

Production workflows should be designed as a lifecycle:

1. **Identify ownership** of the domain, hostname, TLS termination point, environment, and responsible owner.
2. **Generate the key pair** using an appropriate tool/HSM/KMS; minimize cases where the private key leaves protected storage.
3. **Create a CSR** containing the public key and required SANs; the CA validates domain/policy and signs the certificate.
4. **Receive leaf + intermediates**, verify SAN, Key Usage/EKU, key match, validity, and chain to a CA trusted by clients.
5. **Deploy** the cert/key at the right TLS terminator; protect private keys and passwords, configure file permissions/secret volumes.
6. **Verify live via hostname** using curl/OpenSSL/browser/JVM clients, including clients with different truststores.
7. **Monitor expiration dates**, TLS handshake errors, presented certificate chains, and HTTP/2 ALPN if used.
8. **Renew/rotate before expiry** via ACME/CA workflows; ensure new certs match new keys (if rotating keys), reload/roll out instances safely.
9. When **private key compromise** is suspected, issue a new key pair/cert, revoke the old cert when appropriate, purge the old key from storage, and investigate blast radius.

Spring Boot is not an ACME client that automatically generates/renews certs simply by enabling SSL. For example, Let's Encrypt/Certbot typically provides `fullchain.pem` and `privkey.pem`, with the external tool responsible for renewal; Boot can reload a PEM bundle when files change on compatible servers.

### 14.2. Preventing Private Key Leaks

- Do not store real private keys/passwords in Git, public Docker images, release artifacts, or logs.
- Restrict OS file permissions/ACLs strictly to the process that needs read access; mount secret volumes read-only when feasible.
- Avoid sending private keys into chat/ticket systems or pipeline stdout; do not print PEM private key contents in debug logs.
- Encrypt backups and manage access/rotation; do not share keystore passwords broadly among users.
- Do not use the same production private key on a development laptop.
- Do not place root/intermediate CA private keys on a web server. The web server only needs its own **leaf private key**.

### 14.3. Configuring TLS Versions and Cipher Suites

On Java 17 with a suitable embedded server/provider, prefer **TLS 1.3** and allow **TLS 1.2** when needed for compatibility per organizational policy. Do not enable TLS 1.0/1.1/SSLv3 for new services. Choose cipher suites according to the JDK, TLS provider, client population, and security policy; do not copy an overly narrow cipher list that causes all clients to fail handshakes.

Example when **not using an SSL bundle**:

~~~properties
server.ssl.enabled-protocols=TLSv1.3,TLSv1.2
~~~

If **using `server.ssl.bundle`**, protocol/cipher options belong under `spring.ssl.bundle.<type>.<name>.options`; `server.ssl.enabled-protocols` does not control the bundle. Do not assume clients are using TLS 1.3 just from properties; use `openssl s_client` or TLS metrics to verify in practice.

## 15. Common Issues and Diagnostic Table

| Symptom | Possible cause | Proper resolution |
| --- | --- | --- |
| Browser reports `CERT_AUTHORITY_INVALID` or OpenSSL `self-signed certificate` | Root not trusted, local self-signed certificate | For local lab use `--cacert`; production uses a trusted CA / managed internal CA |
| `PKIX path building failed` / `unable to get local issuer certificate` | Missing intermediate or client does not trust root | Check `-showcerts`, leaf→intermediate fullchain, and client truststore |
| `certificate verify failed: hostname mismatch` | SAN does not match accessed name | Issue certificate with right DNS/IP SAN; use matching hostname |
| `certificate has expired` | Past `Not After` | Renew, roll out, and verify across all replicas |
| `certificate is not yet valid` | `Not Before` in the future or clock skew | Check system time/NTP sync and certificate validity |
| Spring fails to start, `keystore password was incorrect` | Wrong PKCS12/JKS password | Check secret mapping, `keytool -list`, do not print secret |
| `Cannot recover key` / alias does not exist | Wrong alias or key password; only `trustedCertEntry` present | Verify `PrivateKeyEntry`, alias, and password |
| `Private key does not match certificate` | New cert + old key, or wrong PEM file | Compare SHA-256 of leaf/private key public keys; deploy matching pair |
| Server sends certificate of another domain | Missing SNI or wrong default bundle selected | `openssl s_client -servername ...`, check SNI routing at terminator |
| `curl: (35) wrong version number` | Using HTTPS against an HTTP port or misrouted proxy | Check port/scheme and TLS termination |
| Java client fails while browser works | JVM truststore differs from browser/OS; proxy/chain policy | Inspect JVM `cacerts`/SSL bundles and actual trust anchors |
| TLS handshake succeeds but HTTP returns 404 | Wrong URL/router/backend | Debug HTTP routing after TLS, do not replace certificate |
| HTTPS works but no HTTP/2 | h2 not enabled/no ALPN or proxy not negotiating | Check `server.http2.enabled` and ALPN at TLS endpoint |
| Replaced PEM file but server still serves old cert | Reload not enabled, unsupported consumer, or symlink/rollout unchanged | Check SSL bundle reload support, deployment, and live handshake |
| mTLS client fails before HTTP | Client cert missing/untrusted, server `client-auth=need` | Check client key/cert, CA trust, EKU, and policy |
| Only one node serves old cert | Rolling deployment or inconsistent secret mounts | Compare fingerprint/SNI per node, audit rotation |
| Error from SSL bundle and direct properties | Using `server.ssl.bundle` together with `server.ssl.key-store`/`certificate` | Choose one configuration strategy |
| Testing only with `curl -k` always says "OK" | Skipping certificate validation | Remove `-k`, fix SAN, issuer chain, root trust, and time |

**Separate layers when debugging:**
1. **TCP/DNS:** is the client connecting to the right IP:port and right TLS termination point?
2. **TLS handshake:** are SNI, TLS version, certificate/key/chain, and validator correct?
3. **HTTP/ALPN:** are negotiated `h2`/`http/1.1` and request routing correct?
4. **Spring Boot app:** did the server bind 8443? Controllers, security, reverse proxy forwarded headers?
5. **Deployment:** did the new cert reach all instances? Any key/cert mismatch during rotation?

Do not check certificate expiration **only in local files**; the certificate clients actually see may come from a load balancer, an old replica, or another SNI virtual host.

## 16. Practice: Checking a Staging or Production Environment

Practical checklist in order:

1. List domains/SANs to serve: `api.example.com`, `app.example.com`, and (if any) internal endpoints accessed by specific IPs.
2. Identify whether TLS sits at the load balancer/proxy or the Spring Boot embedded web server.
3. Inspect live certs by **SNI hostname** with `openssl s_client -servername ... -showcerts`.
4. Inspect leaf SAN, validity, issuer, signature, and intermediate chain; verify leaf/key match where private key access is permitted.
5. Verify hostname and trust with `curl -v https://...` or `openssl verify -verify_hostname` under the proper trust policy.
6. Compare `Not After` across all domains/replicas, schedule rotation before expiration.
7. Verify key material is not in image sources, logs, or Git; passwords come from secret management.
8. If mTLS is needed, verify client certificate CA/purpose and post-handshake authorization.
9. If HTTP/2 is enabled, check ALPN at the actual TLS termination point, not just `server.http2.enabled` in the app.
10. Test restart/reload with a new cert/key pair before enabling production auto-renew; monitor handshake failures after deployment.
11. Verify the proxy does not expose unprotected HTTP backends in untrusted zones and does not trust forwarded headers from external senders.
12. Document the runbook: operators, secret paths, CA renewal workflow, time-to-expiry alerts, rollback, and key compromise handling.

## 17. Self-Check Exercises

1. Does a certificate contain a private key? Does a client receive the private key during the TLS handshake?
2. A leaf certificate is signed by an intermediate CA, and the intermediate is signed by a root. Which certificates does the server usually send?
3. Why does sending the root certificate during the handshake not automatically make the client trust that root?
4. Website `https://api.example.com` has a leaf SAN containing only `DNS:app.example.com`. Will adding the root to the truststore fix the hostname mismatch?
5. Is accessing `https://127.0.0.1:8443` valid with a cert whose SAN only has `DNS:localhost`? What must be added to use the IP?
6. How do `server.ssl.key-store` and `server.ssl.trust-store` differ in responsibility?
7. When using `server.ssl.bundle=web`, should you also keep `server.ssl.certificate` and `server.ssl.key-store` on the same connector?
8. In a Spring Boot PEM bundle, should `keystore.certificate` point to the leaf or fullchain? What does `keystore.private-key` contain?
9. When a private key is compromised, why does merely changing the password of `server.p12` not restore security?
10. Why does a valid certificate not guarantee HTTP/2 is enabled?
11. When a load balancer terminates TLS, must the public cert live on the proxy or necessarily in the Spring Boot app?
12. Is `curl -k` suitable for confirming that a production HTTPS system is secure?
13. If a Java client fails with `PKIX path building failed` while a browser can connect, which truststores should be compared?
14. Why is `CN=localhost` alone not enough? What extension did the lab command add?
15. What does `mTLS` add compared to one-way HTTPS? Does it automatically grant access to every API?
16. When a cert renews successfully on disk but clients still see the old cert, where should you check?
17. How do you verify that a leaf cert and server private key form a matching pair without printing the private key?
18. Why does TLS 1.3 use the private key to prove identity rather than as the key encrypting each HTTP response?

**Suggested answers:** (1) No, a cert only holds the public key/metadata; the server keeps the private key. (2) Leaf + intermediates; the root is usually in the client truststore. (3) The client chooses its own trust anchors. (4) No, the SAN must match `api.example.com`. (5) No, `IP:127.0.0.1` SAN is needed. (6) Server keystore holds key+chain; truststore holds trusted CAs for verifying peers. (7) Do not mix direct options with bundles. (8) Fullchain with leaf before intermediates; the private key matching the leaf. (9) The leaked key can still be used; you must rotate the key/cert. (10) HTTP/2 depends on ALPN and server/proxy support. (11) At the point actually terminating TLS. (12) No, it skips cert verification. (13) JVM `cacerts`/custom truststore vs OS/browser trust. (14) Modern hostname validation uses SAN; the command added `SAN=dns:localhost,ip:127.0.0.1`. (15) Server authenticates the client cert; authorization is still required. (16) Reload/rollout, SNI, replicas, proxy cert cache. (17) Compare SHA-256 of DER public keys from leaf and key. (18) TLS 1.3 uses ephemeral key exchange and derives separate traffic secrets; the leaf private key proves identity via signature.

## 18. Official Documentation and Standards

- RFC 8446, **TLS 1.3**, `CertificateVerify` and handshake: https://www.rfc-editor.org/rfc/rfc8446.html
- RFC 5280, **Internet X.509 PKI Certificate and CRL Profile**, chain validation and extensions: https://www.rfc-editor.org/rfc/rfc5280.html
- RFC 6125 and RFC 9525, **Service Identity in TLS** (DNS SAN, hostname verification): https://www.rfc-editor.org/rfc/rfc9525.html
- Spring Boot 3.5, **Configure SSL / PEM / PKCS12 / SSL Bundles / SNI / HTTP/2**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5, **SSL bundles and reload**: https://docs.spring.io/spring-boot/3.5/reference/features/ssl.html
- Spring Boot 3.5, **Common Application Properties**: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Oracle Java 17, **keytool Command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Oracle Java 17, **Java Secure Socket Extension (JSSE) Reference Guide**: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- OpenSSL, **s_client**: https://docs.openssl.org/3.0/man1/openssl-s_client/
- OpenSSL, **verify**: https://docs.openssl.org/3.0/man1/openssl-verification-options/
