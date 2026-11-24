# Configuring `server.ssl.*` with JKS or PKCS12 Keystores in Spring Boot

## 1. Goal: Enable HTTPS Properly Without Confusing TLS with HTTP/2

A Spring Boot web application can serve HTTP on port 8080 or HTTPS on port 8443/443. When enabling HTTPS directly on the **embedded web server** (the default Tomcat in Spring MVC, or another supported server), the server must have an **X.509 certificate and its corresponding private key**. Spring Boot provides the `server.ssl.*` property group to configure key material, protocols, and client authentication options; Java keystores in **JKS** or **PKCS12** format are two common ways to store key material.

This lesson needs to answer clearly:

1. What does a keystore contain? How does it differ from a truststore?
2. How do you create JKS and PKCS12 keystores with `keytool`, including an alias and Subject Alternative Name (SAN)?
3. How do you configure `server.ssl.key-store`, `key-store-type`, `key-store-password`, `key-alias`, and `key-password` so Spring Boot can load the private key?
4. How do you test HTTPS, hostnames, certificate chains, and HTTP/2/ALPN?
5. How do you handle dev/prod differences, secrets, reverse proxies, mTLS, and startup errors?

Scope: **Spring Boot 3.3.x, Java 17+**, illustrated with Spring Boot 3.3.13/Java 21 and embedded Tomcat. Shell commands focus on Linux/macOS; Windows has corresponding ways to set environment variables. Do not use self-signed learning certificates as public production certificates.

**Distinguish two important settings:**

```properties
# HTTPS/TLS: the server must present a certificate + private key.
server.ssl.enabled=true

# HTTP/2: HTTP protocol option (enabled separately, does not generate a certificate).
server.http2.enabled=true
```

In Spring Boot 3.3, `server.http2.enabled=true` with SSL supports HTTP/2 over TLS (`h2`); when SSL is disabled, the server may support cleartext HTTP/2 (`h2c`) depending on the stack. **Enabling HTTP/2 does not replace TLS**, and enabling TLS does not guarantee every client will use HTTP/2.

## 2. Foundational Concepts: TLS Certificate, Private Key, Keystore, and Truststore

When a browser connects to `https://api.example.com`, the server presents a **certificate chain** (leaf certificate and required intermediate certificates). The browser checks the domain name, expiration, trust path to a Certificate Authority (CA), status, and other factors per browser policy. The server proves it holds the corresponding **private key** during the TLS handshake.

| Concept | Contents | Responsibility |
| --- | --- | --- |
| Private key | Secret key of the server; never shared with clients | Server proves ownership of TLS identity |
| Leaf certificate | X.509 certificate binding public key to domain/IP (via SAN) | Client verifies endpoint identity |
| Intermediate/root CA certificate | Certificates in the verification chain | Helps the client build a trust path |
| **Keystore** | Container holding `PrivateKeyEntry` + certificate chain and possibly other entries | Provides **server identity** for HTTPS |
| **Truststore** | Holds trusted CAs/certificates, typically `trustedCertEntry` | Used by server/client to **verify peers** |
| Keystore password | Password to open/verify the keystore | `server.ssl.key-store-password` |
| Private-key password | Password to access the private-key entry, may differ from store password | `server.ssl.key-password` |
| Alias | Entry name of the key pair and chain in the keystore | `server.ssl.key-alias` |

**A keystore is not simply a `.crt` file containing a certificate.** For direct HTTPS to work, the server keystore must have a **private key entry**; importing only a CA certificate into a truststore is not enough for the server to sign the handshake.

For standard HTTPS, the server needs a keystore with its private key and certificate chain; **you do not need `server.ssl.trust-store` just so clients/browsers trust the server**. Browser trust relies on the trust store and policies **on the browser side**, not a server truststore. A server-side truststore is typically used to verify **client** certificates in mutual TLS (mTLS).

```text
Browser (trust anchors / CA policy)
     |
     |  GET https://localhost:8443/hello
     |  TLS handshake: server certificate + proof of private key
     v
Embedded Tomcat (server.ssl.* -> keystore)
     |
     +-- PrivateKeyEntry: alias web-local
           +-- private key
           +-- leaf certificate
           +-- certificate chain
```

A self-signed certificate can be used for local testing, but browsers do not automatically trust it: it is not signed by a trusted CA. `curl -k` skips server certificate verification and **should only be used for local debugging**, not as release configuration.

## 3. JKS and PKCS12: Same Role, Different Formats

**JKS (Java KeyStore)** is Java's traditional keystore format. **PKCS12 (`.p12`, `.pfx`)** is a standard key/certificate interchange format widely used across Java, OpenSSL, operations tooling, and certificate tools. Modern Java uses PKCS12 as the default keystore format for `keytool`/`KeyStore` in many cases, but **you should not rely on the filename extension to infer the format**.

| Criterion | JKS | PKCS12 |
| --- | --- | --- |
| Common file extension | `.jks` | `.p12`, `.pfx` |
| Spring Boot config value | `server.ssl.key-store-type=JKS` | `server.ssl.key-store-type=PKCS12` |
| Can hold private key + cert chain | Yes | Yes |
| Usable with Java `keytool` | Yes | Yes |
| Interoperability outside Java | Usually lower than PKCS12 | More widespread |
| When to choose | Legacy Java systems / standardized on JKS | Flexible choice for new projects |

There is no rule that "JKS is always more secure than PKCS12" or vice versa based purely on file extension. Real protection comes from key algorithms, passwords, file permissions, valid certificates, TLS configuration, secrets management, and update procedures.

A keystore can contain multiple aliases, but in a typical web application you should **specify the server alias** explicitly when multiple key entries might exist. If `key-alias` is wrong or the entry lacks a private key, the server may fail to start or fail to present the expected certificate.

## 4. Generating a PKCS12 Keystore for Local HTTPS with `keytool`

On JDK 17 or 21, `keytool` is included in the JDK's `bin` directory. To check:

```bash
java -version
keytool -help
```

Example creating a **3072-bit RSA key pair** and a **self-signed certificate** with SANs for both `localhost` and the loopback IP. Run in a test directory **outside a Git repository** or in a location protected by `.gitignore`; never push files containing private keys to source control.

```bash
keytool -genkeypair \
  -alias web-local \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -storetype PKCS12 \
  -keystore local-keystore.p12 \
  -dname "CN=localhost,OU=Development,O=Example,L=HCM,ST=HCM,C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

`keytool` prompts interactively for passwords if not specified. For the PKCS12 example, use a strong password and use the same password for the private key if the tool requires/expects it. **Do not pass passwords on the command line via `-storepass ...`** on shared machines unless you accept the risk of shell history, process arguments, or build logs.

Parameter breakdown:

- `-genkeypair`: creates a public/private key pair along with a self-signed certificate for local testing.
- `-alias web-local`: key entry name, which will be used in `server.ssl.key-alias`.
- `-keyalg RSA`, `-keysize 3072`: example algorithm and key size; in real systems choose per PKI policy.
- `-validity 365`: self-signed certificate valid for 365 days; **not automatically trusted by public CAs**.
- `-storetype PKCS12`: fixes the format instead of relying on JDK defaults.
- `-keystore local-keystore.p12`: file created in the current working directory.
- `-dname`: Distinguished Name of the subject; `CN` does not replace `SAN`.
- `-ext SAN=...`: sets Subject Alternative Names matching the host/IP clients will access.

**SAN is critical:** When a client calls `https://localhost:8443`, the certificate needs `DNS:localhost`; when calling `https://127.0.0.1:8443`, it needs `IP Address:127.0.0.1`. Having only `CN=localhost` may not suffice for modern clients.

Inspect alias, entry type, SAN, and expiration date:

```bash
keytool -list -v \
  -keystore local-keystore.p12 \
  -storetype PKCS12 \
  -alias web-local
```

In the output, inspect `Entry type: PrivateKeyEntry`, `Certificate chain length`, `Owner`, `Issuer`, validity, and `SubjectAlternativeName`. Do not merely check that `keytool -list` prints an alias: a `trustedCertEntry` **has no private key** and cannot serve as a server identity.

## 5. Generating JKS and Converting Between JKS ↔ PKCS12

If your system already uses JKS, you can create one similarly:

```bash
keytool -genkeypair \
  -alias web-local \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -storetype JKS \
  -keystore local-keystore.jks \
  -dname "CN=localhost,OU=Development,O=Example,L=HCM,ST=HCM,C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

With JKS, the tool may prompt separately for the key entry password; for simplicity while learning, you can choose the **same password as the keystore**. When the key entry has a different password, you must set `server.ssl.key-password` to match the key password. Some JDK versions recommend PKCS12 for new keystores; JKS remains a Java-supported format.

Verify:

```bash
keytool -list -v \
  -keystore local-keystore.jks \
  -storetype JKS \
  -alias web-local
```

If you need to convert JKS to PKCS12:

```bash
keytool -importkeystore \
  -srckeystore local-keystore.jks \
  -srcstoretype JKS \
  -destkeystore converted-keystore.p12 \
  -deststoretype PKCS12
```

The command prompts for source and destination passwords; if the private-key password differs from the store password, it may also ask for the source key password. Do not replace the original file before verifying the output.

```bash
keytool -list -v \
  -keystore converted-keystore.p12 \
  -storetype PKCS12 \
  -alias web-local
```

After conversion, check the alias, **PrivateKeyEntry**, certificate chain, and test a real handshake; do not merely rename `.jks` to `.p12`. Renaming the extension **does not convert the format**. The application must declare `key-store-type` matching the actual format and use the password/alias of the target file.

## 6. Common `server.ssl.*` Properties in Spring Boot 3.3

| Property | Purpose | Practical notes |
| --- | --- | --- |
| `server.ssl.enabled` | Enables/disables TLS on the embedded server connector | Example: `true`; setting `enabled=true` without key material will not create a certificate |
| `server.ssl.key-store` | Spring resource location of the keystore | `classpath:tls/keystore.p12` (demo) or `file:/etc/myapp/tls/server.p12` (deployment) |
| `server.ssl.key-store-type` | Format: `JKS` or `PKCS12` | Must match actual format; declare explicitly |
| `server.ssl.key-store-password` | Password to open keystore | Provide via secret/env; do not commit passwords |
| `server.ssl.key-alias` | Selects the private key entry | Verify alias with `keytool -list -v` |
| `server.ssl.key-password` | Private key password if needed | May differ from `key-store-password`, especially in JKS |
| `server.ssl.key-store-provider` | Java security provider | Only needed with a custom provider |
| `server.ssl.protocol` | Protocol family to create TLS/SSL context | Defaults to `TLS`, **does not force only TLSv1.2** |
| `server.ssl.enabled-protocols` | List of allowed TLS versions | Example `TLSv1.3,TLSv1.2` per policy and JVM/server |
| `server.ssl.ciphers` | Restricts cipher suites | Must match suite names and JVM/container capabilities |
| `server.ssl.client-auth` | Client certificate check (`none`, `want`, `need`) | Only enable mTLS when actually needed |
| `server.ssl.trust-store` | Trust material to validate client certificates | Usually only needed when `client-auth` requires it |
| `server.ssl.trust-store-type` | Truststore format | Example `PKCS12` |
| `server.ssl.trust-store-password` | Truststore password | Store via secrets |
| `server.ssl.bundle` | Reference to an SSL bundle configured via `spring.ssl.bundle.*` | **Do not combine** with discrete keystore/PEM options |
| `server.port` | Listening port | Demo `8443`; not an SSL-specific property name |
| `server.http2.enabled` | Enables HTTP/2 | Does not provide certificates/TLS by itself |

Valid values must fit the Java version, container, and packaging used. For instance, specifying a cipher unsupported by the JVM can cause TLS negotiation to find no common algorithm.

**Never confuse this:** `server.ssl.key-store-password` does not encrypt HTTP communications; it only protects the keystore at rest / when loading the key. TLS uses the private key and handshake session, and never sends the store password to browsers.

## 7. Example `application.properties` Running HTTPS with PKCS12

This configuration loads the keystore via a **resource location** stored in an environment variable, instead of committing the private key or password to Git:

**`src/main/resources/application.properties`:**

```properties
server.port=8443
server.ssl.enabled=true

server.ssl.key-store=${TLS_KEYSTORE_LOCATION}
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=web-local

# Use when private-key password differs from store password:
# server.ssl.key-password=${TLS_KEY_PASSWORD}

# Optionally restrict TLS versions per JVM/policy:
server.ssl.enabled-protocols=TLSv1.3,TLSv1.2

# Independent option: allow HTTP/2 when client/server support it.
server.http2.enabled=true
```

Example environment setup on Linux/macOS, if currently inside the directory containing `local-keystore.p12`:

```bash
export TLS_KEYSTORE_LOCATION="file:$(pwd)/local-keystore.p12"

# Enter password without echoing to screen:
read -rs TLS_KEYSTORE_PASSWORD
export TLS_KEYSTORE_PASSWORD
printf '\n'
```

`read -rs` is a shell builtin in Bash/zsh. On Windows PowerShell, environment variables are declared differently; **do not use Bash syntax verbatim**. In production, it is better to retrieve secrets from a secret manager/protected mount instead of typing them manually.

A `file:` configuration outside the JAR lets you replace the keystore according to deployment schedules without embedding the private key inside the build artifact. It still requires read permissions for the app service account and a **confirmed restart/reload mechanism** after certificate updates; do not assume overwriting the file on disk while running automatically updates the live TLS context immediately.

If you want to illustrate a keystore **inside the classpath** for development, you can place the file at:

```text
src/main/resources/tls/local-keystore.p12
```

and configure:

```properties
server.ssl.key-store=classpath:tls/local-keystore.p12
```

However, packaging **production private keys** inside a JAR or public repository is not recommended. `classpath:` uses the Spring resource loader; it does not require the resource to exist outside the JAR as a writable filesystem file.

## 8. Equivalent Configuration for JKS and YAML

When using `local-keystore.jks`, update the corresponding properties:

```properties
server.port=8443
server.ssl.enabled=true

server.ssl.key-store=${TLS_KEYSTORE_LOCATION}
server.ssl.key-store-type=JKS
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=web-local

# Only add when the private key inside JKS has its own password:
# server.ssl.key-password=${TLS_KEY_PASSWORD}

server.http2.enabled=true
```

Here `TLS_KEYSTORE_LOCATION` must point to the JKS file, e.g. `file:/etc/myapp/tls/local-keystore.jks`. **Do not keep `key-store-type=PKCS12` while pointing to a JKS** and rely on JDK keystore autodetection: explicit configuration avoids version/provider-dependent behavior.

The same configuration in `application.yml`:

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: ${TLS_KEYSTORE_LOCATION}
    key-store-type: JKS
    key-store-password: ${TLS_KEYSTORE_PASSWORD}
    key-alias: web-local
  http2:
    enabled: true
```

These are **two equivalent options**; do not define duplicate keys with conflicting values in both `.properties` and `.yml` at the same config location. Spring Boot has a precedence order across configuration sources/profiles/env vars; verify the effective value when debugging.

If the key password **differs** from the keystore password:

```properties
server.ssl.key-password=${TLS_KEY_PASSWORD}
```

If the private key uses the **same password**, a simple setup usually does not need `key-password`. On `UnrecoverableKeyException`, always check the **store password**, **private-key password**, and alias—not just file format.

## 9. Minimal Spring Boot Application to Test HTTPS

This example uses Gradle, Java 21, and Spring Boot 3.3.13. The code below creates a runnable application once you have a project `gradlew`, a suitable JDK, downloaded dependencies, and the keystore from section 4 or 5.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/tls/TlsApplication.java`:**

```java
package com.example.tls;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TlsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TlsApplication.class, args);
    }
}
```

**`src/main/java/com/example/tls/HelloController.java`:**

```java
package com.example.tls;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "secure-ok";
    }
}
```

**`src/main/resources/application.properties`** uses the PKCS12 configuration from section 7 (or JKS from section 8, **not both at once**). At startup, Spring Boot binds `server.ssl.*` into `ServerProperties`, auto-configures the embedded server factory, and applies TLS to the connector. You do not need to manually write `SSLContext`/`TomcatServletWebServerFactory` for basic use cases.

In a terminal with `TLS_KEYSTORE_LOCATION` and `TLS_KEYSTORE_PASSWORD` set:

```bash
./gradlew bootRun
```

Once the server is ready, test:

```bash
# Only for checking self-signed cert in development:
curl -k -i https://localhost:8443/hello
```

A successful body is:

```text
secure-ok
```

Headers, TLS version, status line, and ALPN output may vary by client/server; **only the literal body `secure-ok` is fixed by the controller**. `curl -k` disables certificate verification and is therefore not an acceptable production verification method.

If you choose JKS instead of PKCS12, the HTTP test is identical: only the keystore file, type, password, and alias change on the server. Browsers do not know whether the server loaded the private key from JKS or PKCS12; the client only sees the public certificate and TLS negotiation result.

## 10. Real TLS Verification Without Relying on `curl -k`

### 10.1. Exporting the Public Certificate of the Test Keystore

With the self-signed PKCS12 keystore from section 4:

```bash
keytool -exportcert \
  -rfc \
  -alias web-local \
  -keystore local-keystore.p12 \
  -storetype PKCS12 \
  -file local-cert.pem
```

`-exportcert` exports the **public certificate**, not the private key. The command prompts for a password if needed; `local-cert.pem` should still be verified by fingerprint if used as a trust anchor.

Then test with certificate and hostname verification enabled (for local purposes, not a public CA):

```bash
curl --cacert local-cert.pem -i https://localhost:8443/hello
```

With a self-signed leaf certificate, a compatible curl/OpenSSL build can trust the explicitly provided certificate as a local trust anchor. If a client has a different PKI policy or chain verification fails, inspect the verification reason and configure trust appropriately rather than adding `-k` in production.

In production, use a certificate issued by a CA trusted by clients for the **exact hostname** and configure a valid chain; normally `curl https://api.example.com/...` succeeds without `--cacert`. Do not disable hostname verification or certificate checks to work around certificate errors.

### 10.2. Inspecting the Certificate and TLS Handshake with OpenSSL

```bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -showcerts </dev/null
```

Check **subject, issuer, validity, chain, negotiated protocol/cipher**, and verification messages. `-servername` sends SNI when needed; it does not prove hostname verification passed. To have OpenSSL verify hostname/trust, add appropriate flags such as `-verify_hostname localhost` and `-CAfile local-cert.pem` when trusting a self-signed certificate.

A successful `s_client` connection does not prove the HTTP endpoint returns the expected content, nor does it prove the certificate is trusted by browsers.

### 10.3. Separating HTTPS and HTTP Checks

```bash
# HTTPS is enabled on 8443:
curl -k -i https://localhost:8443/hello

# DO NOT automatically expect HTTP on the same port 8443:
curl -i http://localhost:8443/hello
```

A plaintext HTTP request sent to an HTTPS port is not a valid request. Do not misinterpret a handshake/protocol error on the second request as an `@GetMapping` error.

Per Spring Boot 3.3 documentation, configuring HTTPS with `server.ssl.*` **does not simultaneously keep an HTTP connector on 8080**. To have both connectors in an embedded server, you must configure at least one connector programmatically or place an HTTP redirect at a reverse proxy. **There is no automatic 8080 → 8443 redirect just by setting `server.ssl.key-store`.**

## 11. Enabling HTTP/2 over TLS (h2) and Confirming ALPN

HTTP/2 is an HTTP protocol version; TLS protects the transport channel. To use `h2` directly in this example:

```properties
server.ssl.enabled=true
server.http2.enabled=true
```

In Spring Boot 3.3 with embedded Tomcat 10.1.x and Java 17+, h2 over TLS is supported. When a browser/curl connects, selecting `h2` usually happens via **ALPN (Application-Layer Protocol Negotiation)** during the TLS handshake. If a client does not support HTTP/2, the connection can be served via HTTP/1.1; enabling the property on the server does not force every client to use h2.

Check curl version and HTTP/2 support:

```bash
curl -V
```

If the output includes the HTTP2 feature, run:

```bash
curl -k --http2 -v https://localhost:8443/hello
```

With proper configuration and client/server builds supporting it, verbose output shows ALPN accepted protocol `h2`, and the status line may show `HTTP/2 200`; the body is `secure-ok`. **Do not assume `curl --http2` works if the curl binary was not built with HTTP/2 support.**

You can inspect ALPN at the TLS layer:

```bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn h2,http/1.1 </dev/null
```

If selected, OpenSSL typically prints `ALPN protocol: h2`. If not, check the server stack, client, TLS parameters, and proxy/terminator; do not rush to convert JKS to PKCS12 because the keystore format does not determine HTTP version.

**`h2c` differs from `h2`:** If SSL is disabled while HTTP/2 is enabled, Spring Boot can support h2c over cleartext TCP, such as behind a proxy performing TLS termination. Public browser traffic normally uses h2 over TLS; do not treat public h2c as HTTPS.

Spring Boot 3.3 supports HTTP/2 across multiple servers, though dependency requirements differ: Tomcat 10.1.x and Undertow support h2/h2c per documentation; Jetty may require an extra HTTP/2/ALPN dependency; Reactor Netty (WebFlux) supports h2/h2c and has optional native libraries for optimization. Do not copy a Jetty configuration to Tomcat without checking the stack.

## 12. Standalone Java 17 Exercise: Verifying That a Keystore Actually Contains a Private Key

`keytool -list` is useful, but Java can also open a keystore and verify an alias is a **key entry**, not merely a certificate entry. The following program uses **Java 17+ only**, has no Spring dependencies, reads the password from the `KS_PASSWORD` environment variable, and never prints the password.

**File `KeyStoreCheck.java`:**

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;

public class KeyStoreCheck {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: java KeyStoreCheck PKCS12|JKS path alias");
            System.exit(2);
        }

        String value = System.getenv("KS_PASSWORD");
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("KS_PASSWORD is not set");
        }

        char[] password = value.toCharArray();
        try {
            KeyStore store = KeyStore.getInstance(args[0]);
            try (InputStream input =
                         Files.newInputStream(Path.of(args[1]))) {
                store.load(input, password);
            }

            String alias = args[2];
            System.out.println("type=" + store.getType());
            System.out.println("alias=" + alias);
            System.out.println("hasPrivateKey=" + store.isKeyEntry(alias));

            var chain = store.getCertificateChain(alias);
            System.out.println("certificateChainLength="
                    + (chain == null ? 0 : chain.length));
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Compile:

```bash
javac KeyStoreCheck.java
```

Set the environment variable without echoing the password (Bash/zsh):

```bash
read -rs KS_PASSWORD
export KS_PASSWORD
printf '\n'
```

Run with the PKCS12 keystore created in section 4:

```bash
java KeyStoreCheck PKCS12 local-keystore.p12 web-local
```

**Expected exact stdout** when the file contains only the key pair and self-signed cert created by section 4's command, with the alias intact:

```text
type=PKCS12
alias=web-local
hasPrivateKey=true
certificateChainLength=1
```

With the JKS file created by section 5's command:

```bash
java KeyStoreCheck JKS local-keystore.jks web-local
```

The `type` field will be `JKS`; the remaining lines are similar if the alias/private-key entry is valid. If the program throws `IOException: keystore password was incorrect`, `UnrecoverableKeyException`, or a provider exception, inspect the underlying cause rather than bypassing password verification.

Security note: Environment variables can be visible to privileged processes on the system and a Java `String` holding a password is not zeroed in memory like `char[]`; this example is only meant to inspect key entries and avoid printing secrets, not serve as a complete secrets management guide.

## 13. Using CA-Issued Certificates in Production

Self-signed certificates are helpful for learning TLS but unsuitable for public websites. In production, the PKI flow is typically:

1. Generate a private key and CSR (Certificate Signing Request) per policy.
2. Submit the CSR to an authorized internal or public CA.
3. Receive the **leaf certificate** for the right DNS names/SANs and any required intermediate certificates.
4. Combine leaf + chain with the **matching private key** in a keystore or import the certificate reply into the alias holding the private key.
5. Verify the certificate chain, SAN, validity, key usage, Extended Key Usage, and hostname.
6. Deploy the keystore with least-privilege permissions; verify the handshake with a real client.

Example creating a CSR from a PKCS12 keystore with alias `web-local`:

```bash
keytool -certreq \
  -alias web-local \
  -keystore local-keystore.p12 \
  -storetype PKCS12 \
  -file server.csr \
  -ext "SAN=dns:api.example.com"
```

**This is an example CSR command**, not a guarantee a CA will issue immediately. The original private key stays in the keystore; the CSR contains the public key and request info. In production, you should generally **generate a dedicated key pair for the production domain** rather than reusing a local self-signed key/certificate.

Once the CA returns a valid leaf and chain, you can use `keytool -importcert` to import the certificate reply into the **exact private-key entry alias**, with the chain constructed per PKI documentation and CA policy:

```bash
keytool -importcert \
  -alias web-local \
  -keystore server-keystore.p12 \
  -storetype PKCS12 \
  -file server-chain.pem
```

This command is an **operational template**: it requires `server-keystore.p12` containing the key pair matching the CSR and `server-chain.pem` formatted as a proper certificate reply/chain. With intermediate CAs, you may need to import CA certificates or provide the chain in an order `keytool` recognizes. **Do not import a reply into a keystore lacking the matching private key**, and do not force a result by bypassing trust/chain verification.

Verify after import using `keytool -list -v`, `openssl s_client -showcerts`, and client trust checks. The domain must match the SAN; expiration date and issuer must be right; a leaf certificate does not replace an intermediate chain in deployments where clients need to build a trust path.

## 14. `server.ssl.trust-store` and mTLS: A Separate Case, Not Required for HTTPS

Standard HTTPS typically uses a **server certificate** so the client verifies the server. mTLS adds a step where the server **verifies the client's certificate**. In Spring Boot:

```properties
server.ssl.client-auth=need

server.ssl.trust-store=file:/etc/myapp/tls/client-ca-truststore.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=${TLS_TRUSTSTORE_PASSWORD}
```

`need` requires the client to present a valid certificate according to the server's trust material. `want` requests/suggests one but may accept clients without a certificate, depending on TLS implementation; `none` does not request a client certificate. This mTLS configuration **accompanies the HTTPS server keystore**, rather than replacing it.

Example creating a truststore containing the **CA permitted to issue client certificates**:

```bash
keytool -importcert \
  -alias permitted-client-ca \
  -file client-ca.pem \
  -storetype PKCS12 \
  -keystore client-ca-truststore.p12
```

Only import a CA certificate after verifying its source/fingerprint via a trusted channel. Putting an arbitrary user's public certificate into the truststore is not equivalent to a policy permitting every other user.

More importantly, **TLS client authentication is not automatically application authorization**. Accepting a certificate from a CA only proves the chain is valid per the truststore; Spring Security or the business layer must still map the certificate/principal to a user, tenant, and roles per policy. Never treat every CA-signed client certificate as an admin.

If Spring Boot runs behind a reverse proxy and the **proxy** handles mTLS with the client, `server.ssl.client-auth` on the backend might not be used for the original client. When the application needs client identity forwarded by the proxy, configure a specific trusted mechanism and avoid trusting HTTP headers sent directly by public clients.

## 15. Server Keystore Does Not Configure Outbound TLS Clients

A common misconception: having `server.ssl.key-store` makes every `RestClient`, `RestTemplate`, `WebClient`, JDBC, Kafka, or HTTP client in the app automatically use that truststore/certificate. **Incorrect.**

`server.ssl.*` configures **inbound connections to the embedded web server**. When the application makes an HTTPS call to another server, it acts as a **TLS client** and needs separate trust material/client key material for the HTTP client or driver in use.

| Flow | Who is the TLS server? | Where is it typically configured? |
| --- | --- | --- |
| Browser → Spring Boot HTTPS | Spring Boot | `server.ssl.*` |
| Spring Boot → another HTTPS API | Remote API | Java client/HTTP client SSL context or SSL bundle |
| NGINX (HTTPS) → Spring Boot (HTTP) | NGINX is the public-facing TLS server | TLS cert on NGINX; backend does not need `server.ssl.*` if internal transport is intentionally HTTP |
| NGINX (HTTPS) → Spring Boot (HTTPS) | Both NGINX and Boot on two TLS hops | Independent TLS configuration on each hop |
| Spring Boot → DB `jdbc:...ssl...` | DB is the TLS server | JDBC driver/DataSource SSL settings, not `server.ssl.*` |

Spring Boot supports `spring.ssl.bundle.jks` and `spring.ssl.bundle.pem` to define named SSL material sets usable in multiple places where integrating libraries support them. However, a `server.ssl.bundle` assigned to the inbound server **does not automatically switch all outbound clients to that same truststore**.

## 16. SSL Bundles Are an Alternative; Do NOT Mix with Discrete `server.ssl.key-store`

Spring Boot 3.3 offers SSL bundles to manage key/trust material by name. This is **an alternative** to configuring `server.ssl.key-store` directly:

```properties
# Bundle approach, replacing discrete key-store configs:
spring.ssl.bundle.jks.web.keystore.location=${TLS_KEYSTORE_LOCATION}
spring.ssl.bundle.jks.web.keystore.password=${TLS_KEYSTORE_PASSWORD}
spring.ssl.bundle.jks.web.keystore.type=PKCS12
spring.ssl.bundle.jks.web.key.alias=web-local

server.port=8443
server.ssl.bundle=web
server.http2.enabled=true
```

**Do not use both simultaneously**:

```properties
server.ssl.bundle=web
server.ssl.key-store=file:/etc/myapp/tls/server.p12
```

These two approaches conflict over SSL material selection. Spring Boot 3.3 documentation states that `server.ssl.bundle` **cannot be combined** with discrete Java keystore or PEM options under `server.ssl`. When using a bundle, `server.ssl.ciphers`, `server.ssl.enabled-protocols`, and `server.ssl.protocol` are also not the place to control bundle TLS options; configure them via `spring.ssl.bundle.<type>.<name>.options` accordingly.

Notice the bundle example uses `spring.ssl.bundle.jks.web...` even though the keystore file is in `PKCS12` format: `jks` in the **SSL bundle property group** denotes Java KeyStore-based configuration, supporting both JKS **and** PKCS12.

This lesson focuses on discrete `server.ssl.*` configuration with JKS/PKCS12. Switch to bundles only when you want consistent, component-reusable SSL material organization or more modern certificate management; do not switch merely because of an undiagnosed alias/password error.

## 17. Direct HTTPS vs. TLS Termination at a Reverse Proxy

In production, two architectures are common.

**A. TLS terminates directly at Spring Boot**

```text
Client -- HTTPS (443/8443) --> Spring Boot embedded server
                                  server.ssl.key-store
```

The application needs a keystore with a certificate matching the public hostname. If running multiple replicas, each instance must receive the proper material or use an appropriate TLS management strategy. You need policies for private-key storage, rotation, network exposure, HSTS/redirects at the edge, and cert expiry monitoring.

**B. TLS terminates at a reverse proxy/load balancer**

```text
Client -- HTTPS --> NGINX/Ingress/LB -- HTTP or HTTPS --> Spring Boot
                      cert/key at edge                   backend transport
```

When the proxy handles TLS termination, `server.ssl.*` on Spring Boot **does not determine the browser-facing certificate**. The backend can use HTTP on a controlled private network; if end-to-end encryption is required, configure HTTPS on the backend as well with its own certificate and trust policy.

Protecting forwarded headers: the application should only trust `X-Forwarded-Proto`, `Forwarded`, and similar headers from **trusted proxies**; do not let public clients set headers themselves to trick scheme/cookie/redirect logic. Spring Boot has `server.forward-headers-strategy`, but how it is enabled must match the infrastructure's topology and proxy allowlist.

**Do not add `server.ssl.*` to the backend expecting to "fix" the certificate on the load balancer**: if browser TLS terminates at the edge, you must fix the certificate/trust/hostname at the edge.

## 18. Certificates, SNI, Domains, and Ports: Easy-to-Miss Details

### 18.1. CN Differs from SAN

A certificate for `api.example.com` must have `subjectAltName` containing `DNS:api.example.com`. In the local demo, SAN includes `DNS:localhost` and `IP:127.0.0.1`. Modern browsers evaluate SAN; `CN` alone does not replace listing the exact DNS/IPs.

### 18.2. Certificate Chain Must Be Complete

A CA-issued leaf certificate usually needs an intermediate chain for clients to build a trust path. If the keystore only contains the leaf and lacks a required intermediate, some clients may still connect via cached CAs while others fail. Check the chain served by the **server over the network**, not just by reading the local file with `keytool`.

### 18.3. Each SNI Hostname May Need a Different Certificate

If the same embedded web server serves multiple hostnames with separate certificates, Spring Boot 3.3 supports SNI via `server.ssl.server-name-bundles` on compatible servers (Tomcat/Netty/Undertow per documentation; Jetty has its own mechanism). This is an advanced topic using **SSL bundles**, not throwing arbitrary aliases into one JKS and expecting Boot to pick by hostname automatically.

A single certificate with SANs for multiple hostnames can also serve those hosts if PKI policy allows. Do not treat a keystore alias name as a URL hostname; an alias is an internal label for a key entry.

### 18.4. Ports 443 and 8443

`server.port=8443` only chooses the port; TLS is controlled by `server.ssl.*`. When HTTPS is configured on port 8443, plaintext HTTP requests to that port are invalid. Production HTTPS usually uses 443 at the edge or server; low ports on Linux require elevated permissions/capabilities, so many deployments use 8443 on the app and 443 on the load balancer.

## 19. Protecting Keystores and Secrets in Real Environments

**A keystore containing a private key is a high-sensitivity secret.** Do not commit `.jks` or `.p12` files with private keys to Git, public container images, or static directories. Do not print base64 files, passwords, PEM private keys, or sensitive `keytool -list -v` details to public tickets/logs.

A sound management plan includes:

- **Secret source:** secret manager, vault, Kubernetes Secret with proper RBAC/encryption at rest per infrastructure, or protected file mounts; environment variables have pros/cons and can leak via diagnostics/process contexts.
- **Filesystem ACL:** the service account only has the required read access to the keystore; not world-readable; ancestor directories do not allow untrusted users to swap files.
- **Passwords:** do not put them directly in committed `application.properties`; use placeholders from secret/env and exclude secrets from logs/config endpoints.
- **Certificate rotation:** manage expiry monitoring and procedures to replace certs/keys before expiration. Update keystores and passwords consistently, performing controlled restarts/reloads per server capability.
- **Rollback:** retain the previous valid certificate according to security policy and ensure a recovery path if the new cert/chain is faulty.
- **Least privilege:** separate roles for certificate management, deployment, and log reading; avoid distributing private keys to services that do not need them.
- **Audit:** log TLS configuration results and allowed certificate metadata (alias, expiry, controlled fingerprint), never private keys/passwords.

In particular, "base64-encoding a password or keystore" **is not secret encryption**; anyone with the base64 string can decode it. SSL bundles support base64 sources in some setups, but security still depends on secret management.

## 20. Common Errors and Ordered Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `Keystore was tampered with, or password was incorrect` or MAC error | Wrong password/format/provider or corrupted file | `keytool -list -storetype ... -keystore ...`, check secret |
| `UnrecoverableKeyException` | Key entry password differs from store password | Check `server.ssl.key-password` and how key was imported |
| `Alias name ... does not identify a key entry` | Wrong alias or entry is only a certificate | `keytool -list -v -alias ...`, needs `PrivateKeyEntry` |
| `FileNotFoundException` / resource does not exist | Wrong `classpath:`/`file:` path, file not packaged/mounted | Check absolute path, resource URL, and permissions |
| `Invalid keystore format` / load failed | File format differs from property or file is corrupt | Check `key-store-type`, conversion, provider |
| SSL server starts but browser warns self-signed | Browser does not trust demo cert's CA | Use trusted CA in production; intentional local trust |
| `NET::ERR_CERT_COMMON_NAME_INVALID` | Hostname does not match SAN | Check DNS/IP in certificate and actual URL |
| Certificate expired / not yet valid | Validity dates or wrong host/client clock | `keytool -list -v`, system time, rotation |
| `PKIX path building failed` on client | Incomplete trust chain / untrusted CA, or wrong client truststore | Verify chain sent by server and client trust anchors |
| `No appropriate protocol` / handshake failure | No overlap in TLS versions/cipher suites | Compare JDK, TLS config, OpenSSL/curl negotiated values |
| `curl: (35) ...` or abnormal handshake | HTTP sent to HTTPS port, TLS mismatch, proxy | Compare URL scheme, port, proxy, and server logs |
| HTTPS 8443 works, HTTP 8080 does not respond | Normal when Boot only configures an HTTPS connector | Adding an HTTP connector requires code/proxy |
| `curl --http2` does not produce h2 | curl lacks HTTP2 support, ALPN did not pick h2, proxy, or server stack | `curl -V`, verbose ALPN, `server.http2.enabled` |
| Backend uses HTTPS but browser sees edge cert | TLS termination at reverse proxy | Check edge cert, do not mis-edit backend |
| Server demands a client certificate | `server.ssl.client-auth=need` and mTLS truststore | Test client cert, client trust chain, policy |
| Another SNI hostname shows wrong cert | Multiple hostnames but mapping/bundle differs from expectation | Check `-servername`, SAN, SNI bundle config |
| Works in IDE, `java -jar` keystore error | Relative file path, keystore missing from JAR, or secret unset | Check `file:`/`classpath:`, mounts, and actual process env |

**Layer-by-layer debugging order:**

1. Confirm **process and port** (`server.port`, reverse proxy).
2. Confirm **keystore file** at runtime, format, and `PrivateKeyEntry` via `keytool`.
3. Confirm **secret** and key password, alias.
4. Confirm **handshake** with `openssl s_client`; read the certificate the server sends.
5. Confirm **hostname/SAN and trust chain** from the client's perspective.
6. Confirm HTTP path via `curl` (the app may return 404 even when TLS works properly).
7. If using HTTP/2, confirm **ALPN h2**, server container, and curl features.
8. If there is a proxy, clearly separate the public TLS hop from the backend TLS hop.

You can run the application with `--debug` to view the Spring Boot Condition Evaluation Report, though that report does not decode all certificate/key errors. `javax.net.debug=ssl,handshake` can assist JSSE debugging in controlled environments; **be careful as logs can be very verbose and contain sensitive details about TLS sessions/peers**.

## 21. Integration Testing and Pre-Deployment Checks

An HTTPS test should verify both the **server certificate and HTTP response**. For instance, the controller in section 9 can be tested in two layers.

**Layer A — verify key material before running:**

```bash
keytool -list -v \
  -storetype PKCS12 \
  -keystore local-keystore.p12 \
  -alias web-local
```

Verify the entry is `PrivateKeyEntry`, the certificate is unexpired, SAN includes `localhost`, the chain makes sense, and the password works.

**Layer B — HTTP over TLS after boot:**

```bash
curl --cacert local-cert.pem -i https://localhost:8443/hello
```

Expected body:

```text
secure-ok
```

Test negative cases in a controlled test environment:

- Change alias to a nonexistent name → server must report a configuration error instead of silently serving another identity.
- Supply wrong keystore password → startup fails; do not disable TLS to run temporarily.
- Point `TLS_KEYSTORE_LOCATION` to a nonexistent path → resource error; fix the path.
- Request a hostname without a matching SAN → client hostname verification fails.
- Omit a trusted CA → client chain verification fails; only use `-k` locally to verify the TLS engine is listening.
- `server.http2.enabled=false` → TLS can still use HTTP/1.1; does not mean HTTPS is off.
- Test through a proxy → compare the response cert on the public URL with the backend; they may belong to two different TLS hops.

For automated tests, do not commit production private keys for testing. Generate an ephemeral self-signed keystore in a temporary directory or use a separately protected test fixture, with an ephemeral TLS port and test keystore password. When using JUnit `@SpringBootTest(webEnvironment = RANDOM_PORT)`, you may need custom trust material for the HTTP test client if the server uses a self-signed certificate; do not assume `TestRestTemplate` automatically trusts self-signed certs like a CA-signed browser session.

For production traffic, beyond a valid certificate you must consider TLS security policy, HTTP response headers, HSTS at the HTTPS edge, rate limiting, and monitoring. **Enabling TLS does not mean all endpoints are authenticated and authorized by Spring Security.**

## 22. Important Misconceptions

**"Having a `.p12` file guarantees it contains a private key."** False. It might only be a truststore with `trustedCertEntry`. An HTTPS server needs a key entry and corresponding certificate chain.

**"JKS and PKCS12 only differ in file extension."** False. Their binary formats differ; use `keytool -importkeystore` when conversion is needed, never rename the file.

**"`server.ssl.trust-store` makes browsers trust the server."** False. Browsers need **browser** trust anchors and a valid chain/SAN. A server truststore verifies peers (especially client certs in mTLS).

**"Setting `server.ssl.enabled=true` without a keystore makes Boot generate a cert."** False. Valid key material must be provided (a keystore or PEM/bundle configuration in another setup).

**"Enabling `server.http2.enabled=true` means you already have HTTPS."** False. HTTP/2 and TLS are different layers. H2 over TLS requires SSL enabled; h2c can be cleartext HTTP/2.

**"Enabling HTTPS on 8443 automatically redirects 8080 to 8443."** False. Boot does not create both connectors solely from application properties. Redirects are usually done at a reverse proxy or via additional connector configuration.

**"Having `CN=localhost` guarantees clients accept the hostname."** False. Modern hostname verification relies on SAN and the trust chain.

**"Putting passwords in `application.yml` encrypts them because HTTPS is enabled."** False. TLS protects network traffic, not config files/secrets at rest.

**"Use both an SSL bundle and discrete key-store together to be safe."** False; the two approaches cannot be combined.

**"Requiring client certs via mTLS means every user is authorized."** False. mTLS authenticates the peer certificate; authorization remains an application policy.

**"Having a server keystore makes outbound API clients use it automatically."** False. Inbound server and outbound TLS clients must each be configured for their respective roles.

## 23. Self-Check and Advanced Exercises

**Review questions:**

1. What type of entry must `server.ssl.key-store` point to so the server can present a TLS identity? Why is a `trustedCertEntry` alone insufficient?
2. For a local PKCS12 with alias `web-local`, which minimum `server.ssl.*` properties must align?
3. If JKS uses a separate password for the private-key entry, which missing property can cause `UnrecoverableKeyException`?
4. What role does `-ext SAN=dns:localhost,ip:127.0.0.1` play compared to `CN=localhost`?
5. Why does `server.ssl.key-store=file:/...` differ from `classpath:...` when packaging and rotating certificates?
6. If a reverse proxy terminates TLS, where does the certificate seen by browsers live? When does the backend still need HTTPS?
7. Why does a successful `curl -k` connection not prove a certificate is valid for production?
8. When can `server.http2.enabled=true` select `h2`, `h2c`, or HTTP/1.1? What is the role of ALPN?
9. To validate client certificates in mTLS, which keystore and which truststore does the server need?
10. Why should `server.ssl.bundle` not be configured alongside `server.ssl.key-store`?
11. During certificate rotation, why is updating the file on disk not sufficient proof that the server is serving the new certificate?
12. If the SSL handshake succeeds but `GET /hello` returns 404, which layer needs debugging and why should you not change the keystore format?

**Exercise:** Create both `local-keystore.p12` and `local-keystore.jks` with the same alias, adjust `server.ssl.key-store-type` and `TLS_KEYSTORE_LOCATION` accordingly; run the `/hello` demo; use `keytool`, `openssl s_client`, and `curl --cacert` to record the certificate, TLS protocol, and negotiated HTTP version. Intentionally misconfigure each property **in a test environment** and describe whether the failure belongs to keystore loading, TLS handshake, or HTTP routing.

**Conclusion:** `server.ssl.*` provides a direct way to configure HTTPS on the embedded server, where the **keystore must contain the private key and certificate chain**, the format is **JKS** or **PKCS12**, and the path/password/alias must match. HTTP/2 is an additional setting (`server.http2.enabled`), mTLS requires a separate truststore/policy, and production requires properly CA-issued certificates, secrets management, rotation, and real testing across every TLS hop.

### Official Documentation

- Spring Boot 3.3, Embedded Web Servers — Configure SSL, SSL Bundles, HTTP/2: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3, Common Application Properties (`server.ssl.*`, `server.http2.enabled`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3, SSL Bundles (JKS/PKCS12): https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Java 17 `keytool`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- JSSE Reference Guide: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- RFC 8446 — TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- RFC 9113 — HTTP/2: https://www.rfc-editor.org/rfc/rfc9113