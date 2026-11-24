# Inspecting Handshakes, Hostnames, Truststores, and Certificate Chain Errors

## 1. What Checks Must a Successful HTTPS Connection Pass?

In **Spring Boot - web-runtime**, HTTPS relies on TLS to encrypt connections, authenticate the peer, and protect data integrity in transit. When a Java application calls an HTTPS API or a browser connects to a Spring Boot server, **an open TCP connection does not mean TLS is valid**; nor does valid TLS mean the API returns HTTP 200.

Questions to separate:

1. **DNS/TCP:** Which address did the host resolve to? Is port 443/8443 accepting connections? Is there a proxy, gateway, or TLS terminator in between?
2. **TLS negotiation/handshake:** Did both sides agree on a TLS version, cipher suite, cryptographic parameters, and (if used) ALPN? Did the server prove possession of the private key for its certificate?
3. **Trust/PKIX:** Can the client build and verify a certificate path from **leaf → intermediate CA → trusted root/trust anchor** under its policy?
4. **Hostname verification:** Is the certificate actually valid **for the hostname or IP the client requested**, specifically in Subject Alternative Name (SAN)?
5. **HTTP:** After TLS succeeds, is the HTTP/1.1 or HTTP/2 request processed cleanly? Status codes 401/403/404/500 belong to the HTTP layer and do not indicate a broken TLS handshake.

Example:

~~~text
Java Client / Browser                      Server / TLS termination
     |                                            |
     | DNS -> TCP connect                         |
     |------------------------------------------->|
     | ClientHello (+ SNI, ALPN)                  |
     |------------------------------------------->|
     | ServerHello, TLS parameters                |
     |<-------------------------------------------|
     | Certificate: leaf + intermediates          |
     |<-------------------------------------------|
     | Verify chain, validity, hostname, key usage|
     | ... TLS key confirmation / Finished ...    |
     |<------------------------------------------>|
     | HTTP request (inside TLS)                  |
     |------------------------------------------->|
     | HTTP response (200, 401, 500, ...)         |
     |<-------------------------------------------|
~~~

This diagram illustrates conceptual flow only. **TLS 1.3 and TLS 1.2 have different handshake structures**; in TLS 1.3, many handshake messages after `ServerHello` are already encrypted. Do not interpret the diagram as a byte-level order across all versions.

**Foundational conclusion:** a PKIX error is not a DNS error, a hostname error cannot be fixed by stuffing CAs into a truststore, and HTTP/2 does not have a "separate certificate set" divorced from TLS.

## 2. Four Concepts Often Lumped Together as "the SSL Certificate"

| Concept | Role | Who holds / checks it? |
| --- | --- | --- |
| **Leaf/server certificate** | Binds public key to service identity; SAN lists valid names/IPs | Server presents; client verifies |
| **Intermediate CA certificate** | Bridges signatures from leaf up to a higher CA | Server usually sends intermediate; client uses it to build chain |
| **Root CA / trust anchor** | Endpoint **explicitly trusted** by the client | Client's truststore; root usually does not need to be sent by server |
| **Server private key** | Proves key ownership matching leaf; used during TLS authentication | Held only by server/TLS terminator; never placed in client truststores |

Example of a valid chain:

~~~text
api.example.test  (leaf; SAN DNS:api.example.test)
       |
       | signed by
       v
Example Intermediate CA  (CA=true)
       |
       | signed by
       v
Example Root CA  (trusted in client's truststore)
~~~

A valid signature chain is not enough. Clients also inspect **validity dates**, **hostname**, key usage / extended key usage (usually requiring **serverAuth**), CA constraints, allowed algorithms, and configured revocation policies.

**Keystore vs. truststore:**
- **Server keystore:** normally holds **private key + server certificate chain** for the server to present to clients.
- **Client truststore:** holds **trusted CAs/certificates** to verify server certificates; normally **contains no private key**.
- In **mutual TLS (mTLS)**, the client also has a keystore holding its private key + client cert, while the server has a truststore to verify client certs. Both sides still have distinct responsibilities.

You can use **PKCS12 (.p12/.pfx)** or **JKS**, yet the file format does not decide whether it is a keystore or truststore. Its contents and how the app uses it are what matter.

## 3. TLS Handshake and Where Certificate Validation Occurs

A TLS client typically sends **ClientHello** listing supported versions/cipher suites, the **SNI** extension for hostname, and optionally **ALPN** to negotiate HTTP/2 (`h2`) or HTTP/1.1. The server selects compatible parameters and sends an appropriate certificate; the client validates it before trusting the connection.

Phases to distinguish:

1. **Network connection:** DNS resolution and TCP connect to target; failures here yield `UnknownHostException`, `ConnectException`, timeouts, or connection refused.
2. **TLS negotiation:** `ClientHello`/`ServerHello`; lack of shared version/cipher, crypto policy, or SNI routing issues yield `handshake_failure`, `protocol_version`, or related alerts.
3. **Server identity verification:** validating signatures/chain/trust anchor, expiry, SAN, and constraints. Failures here produce **`SSLHandshakeException`**; the root-cause message pinpoints the specific failure.
4. **Handshake completion:** exchanging key-confirmation messages and switching to encrypted application traffic. Only then do compliant clients send HTTP requests.
5. **HTTP and ALPN:** if both support and enable HTTP/2, ALPN can select **h2**; otherwise HTTP/1.1 is used. HTTP errors like 404 or 502 belong to the API/proxy layer and are not fixed via truststores.

**SNI (Server Name Indication)** is critical when multiple hostnames share an IP: the server or load balancer selects the certificate by SNI. Connecting by IP or running OpenSSL without SNI can show a **default certificate belonging to another site** rather than the one you meant to inspect.

**ALPN does not replace certificate verification.** Returning ALPN `h2` does not prove the leaf has the right SAN or a trusted root. Conversely, a TLS handshake succeeding with ALPN picking `http/1.1` is not a certificate defect; check HTTP/2 config separately.

## 4. Hostname Verification: SAN Must Match Where the Client Connects

### 4.1. Where Does the Hostname Come From?

When Java calls **https://api.example.test/orders**, the hostname checked is **api.example.test**. When a client calls **https://10.20.0.15/orders**, that is an **IP address** matched against the certificate; a DNS name in the cert does not count just because DNS happens to resolve to that IP.

In modern certificates, server identities are listed under **Subject Alternative Name**:
- **DNS:api.example.test** → valid for that DNS name.
- **DNS:*.example.test** → matches under restricted single-label wildcard rules, not multi-level subdomains.
- **IP Address:10.20.0.15** → identity for that IP; a DNS SAN holding an IP string does not replace a proper IP SAN.

**Common Name (CN)** in the Subject should not be the sole check. Many modern TLS clients rely on **SAN** for hostname checks; a certificate with a matching CN but missing/wrong SAN can still be rejected.

Illustrative examples:

| Client URL | Leaf SAN | Identity match |
| --- | --- | --- |
| https://api.example.test | DNS:api.example.test | Match |
| https://api.example.test | DNS:shop.example.test | Mismatch |
| https://a.example.test | DNS:*.example.test | May match under valid wildcard rules |
| https://a.b.example.test | DNS:*.example.test | Single-label wildcard does not span two levels |
| https://10.20.0.15 | DNS:api.example.test | IP mismatch |
| https://10.20.0.15 | IP Address:10.20.0.15 | IP match |

**"May match"** in the table means it must still pass chain, expiry, algorithm, and other checks. A hostname match alone does not guarantee TLS succeeds.

### 4.2. Typical Java Symptoms

In Java 17, hostname errors are often wrapped in:

~~~text
javax.net.ssl.SSLHandshakeException:
  No subject alternative DNS name matching api.example.test found
~~~

or a variant mentioning **No subject alternative names matching IP address ... found**, depending on connection and JDK. These are **illustrative error templates**, not exact character-for-character output across every runtime.

When the chain is already trusted yet the hostname mismatches, **adding the certificate to a truststore will not fix the SAN error**. Fix the URL hostname or reissue the certificate with the proper SAN. Never disable hostname verification in production.

### 4.3. Testing a Backend IP While Keeping the Real Hostname

To connect to a specific IP while still verifying the server against **api.example.test**, use **curl --resolve** to keep the hostname in the URL:

~~~bash
curl -v --resolve api.example.test:443:10.20.0.15 \
  https://api.example.test/health
~~~

The command above is a **template**: substitute your own hostname/IP/endpoint. Curl connects to the specified IP while using the URL's hostname for SNI and certificate verification. Calling **https://10.20.0.15/** directly makes the client verify the IP instead, failing against a DNS-only SAN even on the exact same backend.

If an HTTP proxy sits in the path, DNS routing and TLS termination may be governed by the proxy; confirm the true path before blaming the backend's certificate.

## 5. Truststore and PKIX: How Are Certificates Trusted?

Java typically uses **JSSE (Java Secure Socket Extension)** with a **TrustManager** to validate the certificate path. The `TrustManager` searches for a **valid path to a trust anchor** trusted by the JVM/client.

Different failure modes:

**A. Root CA not trusted:** the server sends valid leaf + intermediate, yet the Java client lacks the matching root in its active truststore. Result often looks like:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed:
  sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

**B. Server omits intermediate:** the root may already be in the truststore, but the server sent only the leaf; the client lacks the intermediate to bridge the chain. Some browsers have cached intermediates or extra AIA fetching, while Java clients fail. **Never conclude a server sends a full chain just because a browser opens it.**

**C. CA is trusted yet the cert is expired, not yet valid, or uses restricted algorithms:** still invalid. Errors may mention **validity check failed**, **NotAfter**, **NotBefore**, **Algorithm constraints check failed**, etc. Check system clocks/NTP, chains, and JDK policies.

**D. Chain is valid yet hostname is wrong:** a SAN/hostname error, not fixed by importing new roots.

**E. Client uses a different truststore than expected:** the app configures **javax.net.ssl.trustStore**, a custom `SSLContext`, an SSL bundle, a container image truststore, or an HTTP client's own truststore. Importing a CA into the build machine's JDK will not affect the JVM inside a production container.

### 5.1. Key Reminders About Root and Intermediate

Servers normally send **leaf first followed by required intermediates**, and **need not send the root**. Clients must hold the matching trust anchor. Having a server send its root does not make that root trusted: **trust lives in the client's truststore**.

When intermediates are missing, the priority fix is **configuring the server/TLS terminator to serve the full chain**, not forcing every client to "trust the leaf" as a workaround. For an untrusted internal private CA, administrators can distribute the **verified CA certificate** into the proper client truststores.

### 5.2. Do Not Edit the Wrong Truststore

On many JDKs, the default truststore resides near **$JAVA_HOME/lib/security/cacerts**. Yet the running JVM may come from a different path, vendor, or property override. Run:

~~~bash
java -version
keytool -list -cacerts
~~~

to verify the Java version and inspect the truststore of the **invoked `keytool`**; `keytool` may prompt for a password. For containerized apps, run diagnostics inside the **exact image/JDK/container** or inspect the live JVM configuration rather than only your laptop.

Flags to inspect in JVM startup options:

~~~text
-Djavax.net.ssl.trustStore=/path/to/client-truststore.p12
-Djavax.net.ssl.trustStorePassword=...
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

These are **system property templates**; the ellipsis is not a runnable config value. Never log passwords. **Setting a custom `trustStore` can replace the default set of trusted CAs** for the default JSSE `SSLContext`, causing previously working public endpoints to fail with PKIX errors. When only one HTTP client needs a private CA, configure trust per client/SSL bundle instead of altering global `cacerts`.

## 6. Inspection Tools Ordered from Outside In

When troubleshooting HTTPS, start with the **exact URL/host/port from the exact machine and network where the app fails**, checking layer by layer. Do not swap truststores the moment you see `SSLHandshakeException`.

### 6.1. curl: Checking Network Path and HTTP Status

~~~bash
curl -v --connect-timeout 5 --max-time 15 \
  https://api.example.test/health
~~~

This is a **template command**; substitute an endpoint you control. Verbose output reveals:
- Which IP DNS picked, and whether a proxy was used.
- Which TLS version was negotiated, and whether the server certificate validated.
- SNI/ALPN and the HTTP version supported/negotiated by curl.
- Which HTTP status came back after TLS.

If curl reports **SSL certificate problem**, inspect chain/trust/hostname. If curl returns **HTTP 401**, the TLS handshake already succeeded; the next issue is API authentication, not adding a root CA.

**Curl uses trust sources and TLS backends specific to its build/OS**, which need not match Java's truststore. Curl succeeding while Java fails **does not prove Java has a bug**; compare trust roots, proxies, and real hostnames.

### 6.2. OpenSSL s_client: Inspecting Certificates Sent by the Server

~~~bash
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -showcerts \
  -verify_hostname api.example.test \
  -verify_return_error < /dev/null
~~~

On Linux/macOS, **/dev/null** closes stdin after the handshake so the command does not wait interactively; on Windows PowerShell, omit POSIX redirection and quit interactively per your installed OpenSSL version.

Options:
- **-connect**: target IP/host and TCP port.
- **-servername**: sets SNI, avoiding inspecting a virtual host's wrong default certificate.
- **-showcerts**: prints the certificate list **sent by the peer**, without proving the chain is trusted.
- **-verify_hostname**: enables DNS hostname verification; for IP connections, use IP verification such as **-verify_ip**.
- **-verify_return_error**: exits with an error on verification failures instead of continuing the diagnostic session.

In supporting OpenSSL versions, **Verify return code: 0 (ok)** with proper verify flags and trust stores indicates verification succeeded under **this OpenSSL installation**, not necessarily that Java shares the same CA/policy. Do not stop reading at `CONNECTED` or `Certificate chain` and declare victory.

With a verified private CA, pass **-CAfile /path/to/ca.pem** so OpenSSL uses the right trust anchors. The path is an example; never grab an arbitrary certificate off a server and blindly treat it as a trusted CA.

### 6.3. OpenSSL x509: Reading Leaf and SAN

Once you have a leaf certificate file from a trusted source, e.g., **leaf.pem**, run:

~~~bash
openssl x509 -in leaf.pem -noout -subject -issuer -dates -ext subjectAltName
openssl x509 -in leaf.pem -noout -text
openssl x509 -in leaf.pem -noout -fingerprint -sha256
~~~

Focus on:
- **Subject Alternative Name:** DNS/IP must match the hostname used by clients.
- **Not Before/Not After:** validity period against system clocks.
- **Issuer:** who signed the leaf; which intermediate is needed.
- **Basic Constraints, Key Usage, Extended Key Usage:** suitable for a server leaf cert.
- **SHA-256 fingerprint:** compares certificates against another trusted source; fingerprints do not replace chain validation.

**Never** rely on a matching Subject CN to ignore a missing/wrong SAN.

### 6.4. OpenSSL verify: Validating a Chain from Files

Given three files **leaf.pem**, **intermediates.pem**, and **root-ca.pem** (with the root verified out-of-band):

~~~bash
openssl verify \
  -CAfile root-ca.pem \
  -untrusted intermediates.pem \
  -verify_hostname api.example.test \
  leaf.pem
~~~

This is a **template on existing files**, not a command that creates files. **-untrusted** provides intermediate certificates for chain building **without promoting them to trust anchors**. **-CAfile** specifies the trusted root/CA for the check. On success, OpenSSL prints **leaf.pem: OK**, though behavior depends on OpenSSL policies and versions.

If verify prints **unable to get local issuer certificate**, check whether the server omitted an intermediate, whether the root is right, and whether `-untrusted` includes what is needed. Never import a leaf as a trusted root just to make the check turn green.

### 6.5. keytool: Inspecting Certificates and Truststores from Java's Perspective

To view a live server's certificate:

~~~bash
keytool -printcert -sslserver api.example.test:443 -v
~~~

This command mainly **prints certificate details**, and does not equate to full HTTP client trust/hostname verification. To inspect a file:

~~~bash
keytool -printcert -file leaf.pem -v
~~~

To inspect your designated truststore:

~~~bash
keytool -list -v -keystore client-truststore.p12 -storetype PKCS12
~~~

The last command prompts for a password; the path is illustrative. Compare the **trusted CA/fingerprint** with the live server chain, and never import a private key by mistake.

## 7. Self-Built Spring Boot HTTPS Lab: Testing Both Trust and Hostname Separately

This lab runs locally, **requiring no domain or public certificate**, using JDK 17, Maven, and OpenSSL/curl to inspect TLS on **https://localhost:8443/ping**. It intentionally generates a **self-signed certificate with only DNS SAN:localhost** and no IP SAN, simulating two distinct errors:
- **Untrusted CA/certificate:** Java/curl rejects the self-signed certificate by default.
- **Trust configured yet hostname wrong:** accessing **https://127.0.0.1:8443/ping** fails to match `DNS SAN:localhost`.

This is an educational lab. **Never take these self-signed certificates, sample passwords, or demo truststores into production.**

### 7.1. Project Tree

~~~text
tls-handshake-lab/
├── pom.xml
├── certs/
│   ├── dev-server.p12
│   ├── dev-server.pem
│   └── lab-truststore.p12
├── TlsProbe.java
└── src/main/
    ├── java/com/example/tls/
    │   └── TlsLabApplication.java
    └── resources/application.yml
~~~

The three files in `certs/**` are generated by the commands below and **do not exist in source beforehand**. Never commit real private keys or passwords. **TlsProbe.java** is a standalone Java 17 client in the project root runnable directly via `javac`/`java`.

### 7.2. Complete pom.xml

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
    <artifactId>tls-handshake-lab</artifactId>
    <version>1.0.0</version>

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

### 7.3. Generate a Self-Signed Certificate with SAN localhost

Open a terminal in **tls-handshake-lab/**. Create the folder:

~~~bash
mkdir -p certs
~~~

On PowerShell use **New-Item -ItemType Directory -Force certs**. Then use **JDK 17+ keytool**:

~~~bash
keytool -genkeypair \
  -alias lab-server \
  -keyalg RSA -keysize 2048 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore certs/dev-server.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost, OU=Lab, O=Demo, C=VN" \
  -ext "SAN=dns:localhost"
~~~

Trailing **\** characters are line-continuation markers for Linux/macOS shells; in Windows PowerShell place the command on **one line** or use PowerShell continuation syntax. The password **changeit** is a demo value only—**never use in production**.

This creates a **private key + self-signed certificate** inside PKCS12. Inspect the SAN:

~~~bash
keytool -list -v \
  -keystore certs/dev-server.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -alias lab-server
~~~

Verify **SubjectAlternativeName** lists **DNSName: localhost**. Since only a DNS SAN was declared, **there is no IP SAN:127.0.0.1**.

Export the **public certificate** (without private key) so curl/OpenSSL can trust it in the lab:

~~~bash
keytool -exportcert -rfc \
  -alias lab-server \
  -keystore certs/dev-server.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -file certs/dev-server.pem
~~~

**dev-server.p12 contains the private key**, while **dev-server.pem** exported here contains only the public certificate. Do not confuse it with a public CA's `fullchain.pem`.

### 7.4. Configure the HTTPS Server in Spring Boot

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:./certs/dev-server.p12
    key-store-type: PKCS12
    key-store-password: changeit
    key-alias: lab-server
  http2:
    enabled: true
~~~

This uses **server.ssl.key-store** with **`file:`** so Spring Boot reads the external file outside the JAR. **./certs** is relative to the process working directory. Run **java -jar** from the project root or override the path when deploying, otherwise the server will fail to find the keystore.

**server.http2.enabled: true** demonstrates HTTP/2 negotiation capability. TLS/ALPN and HTTP/2 work according to embedded server, JDK, and client capabilities; **HTTP/2 is not guaranteed to be picked on every connection**.

In production, never put literal passwords inside packaged YAML. Use a secret store/environment with proper permissions and consider Spring Boot SSL bundles.

### 7.5. Spring Boot Java Server

**src/main/java/com/example/tls/TlsLabApplication.java**:

~~~java
package com.example.tls;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TlsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TlsLabApplication.class, args);
    }
}

@RestController
class PingController {

    @GetMapping(path = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    String ping() {
        return "TLS OK\n";
    }
}
~~~

This is the complete Java file. If keystore path/password is wrong or the key alias is missing, **the server will fail at startup**, before any HTTPS request arrives. That is a **server key material** error, not a client truststore error.

### 7.6. Build and Run the Spring Boot Server

~~~bash
mvn package
java -jar target/tls-handshake-lab-1.0.0.jar
~~~

Run in the first terminal from the project root. Once the server listens on **8443**, test from another terminal:

~~~bash
curl -v https://localhost:8443/ping
~~~

**Expected result:** curl normally rejects the **untrusted** self-signed certificate. Exact error wording varies by OS/curl/TLS backend; do not assert exact stdout text.

Pass the exported public certificate as a trusted CA for the lab:

~~~bash
curl -v --cacert certs/dev-server.pem \
  https://localhost:8443/ping
~~~

When the lab works and curl uses the right PEM, expected **body**:

~~~text
TLS OK
~~~

This command **does not turn off certificate verification**: curl verifies against the certificate file we **intentionally trusted for this lab** and still validates the **localhost** hostname.

### 7.7. Triggering Hostname Mismatch Without Breaking Trust

Keeping the exact same **--cacert**, deliberately call by IP address:

~~~bash
curl -v --cacert certs/dev-server.pem \
  https://127.0.0.1:8443/ping
~~~

**Expected result:** the TLS client rejects the connection because the certificate **has only DNS SAN:localhost, without IP SAN:127.0.0.1**. Trust passed in the lab, yet **hostname/IP validation failed**. You cannot "fix this by re-importing the certificate"; use the **localhost** URL or issue a new certificate with an **IP SAN** if IP access is genuinely required.

Verify the equivalent via OpenSSL:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -CAfile certs/dev-server.pem \
  -verify_ip 127.0.0.1 \
  -verify_return_error < /dev/null
~~~

**-verify_ip** validates IP addresses; do not confuse it with **-verify_hostname** for DNS names. **-servername localhost** pins the lab SNI; in production distinguish SNI, TCP IP, and the URL's real hostname.

### 7.8. Properly Verifying the Local Lab with s_client, Including ALPN

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile certs/dev-server.pem \
  -verify_hostname localhost \
  -verify_return_error \
  -showcerts \
  -alpn h2,http/1.1 < /dev/null
~~~

**When successful**, OpenSSL prints:

~~~text
Verify return code: 0 (ok)
~~~

Output also reports TLS version, cipher, and negotiated ALPN protocol if available. **ALPN protocol: h2** means the TLS link picked HTTP/2; if it picked `http/1.1`, the certificate can still be completely valid. Because `openssl s_client` only exercises TLS/ALPN, it **is not a full HTTP/2 client**; verify HTTP responses with an HTTP/2-capable curl or Java `HttpClient`.

With curl supporting HTTP/2:

~~~bash
curl -v --http2 --cacert certs/dev-server.pem \
  https://localhost:8443/ping
~~~

If your curl build lacks HTTP/2 support, `--http2` may be rejected; that is **not a certificate error**.

## 8. Java 17 Lab: Truststore and Hostname Verified Separately

### 8.1. Standalone Java HttpClient Without Maven

Create **TlsProbe.java** in the project root:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class TlsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java TlsProbe https://host:port/path");
            System.exit(2);
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .version(HttpClient.Version.HTTP_2)
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(args[0]))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        System.out.println("status=" + response.statusCode());
        System.out.println("body=" + response.body().strip());
    }
}
~~~

This is a **standalone Java 17 program**. It uses the JDK's default/configured trust policy with **no** trust-all hacks, dummy `HostnameVerifier`, or disabled certificate checks. **HttpClient.Version.HTTP_2** is a protocol preference, not a guarantee ALPN picks `h2`; the code prints only status and body for stable stdout.

Compile:

~~~bash
javac -encoding UTF-8 TlsProbe.java
~~~

Test without the lab truststore:

~~~bash
java TlsProbe https://localhost:8443/ping
~~~

**Expected:** the JDK rejects the lab's self-signed certificate if untrusted; the stack trace typically mentions **SSLHandshakeException / PKIX path building failed**. If the runtime was already preconfigured to trust the lab CA, results may differ.

### 8.2. Create a Dedicated Truststore for the Lab

Use the public certificate exported in section 7:

~~~bash
keytool -importcert \
  -alias lab-server-trusted \
  -file certs/dev-server.pem \
  -keystore certs/lab-truststore.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -noprompt
~~~

**-noprompt is only appropriate in a lab**, where we created the certificate ourselves and know its origin. In production, **verify the CA/fingerprint via an independent channel** and never blindly trust a certificate pulled off a failing connection. This truststore holds the trusted certificate and needs no server private key.

Verify alias:

~~~bash
keytool -list -v \
  -keystore certs/lab-truststore.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

Run Java with the **proper truststore**:

~~~bash
java \
  -Djavax.net.ssl.trustStore=certs/lab-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  TlsProbe https://localhost:8443/ping
~~~

`-D` flags must appear **before the class name**. On Linux/macOS, trailing `\` is line continuation; in PowerShell write the command on **one line**.

**Exact stdout when the demo server is running and connection succeeds:**

~~~text
status=200
body=TLS OK
~~~

The server may negotiate HTTP/2 or HTTP/1.1; status and body remain the same. If launched from a different working directory, relative truststore paths can fail; use absolute paths when diagnosing.

### 8.3. Still Fails on Wrong Hostname Despite Being Trusted

Run with the same truststore, changing the URL to IP:

~~~bash
java \
  -Djavax.net.ssl.trustStore=certs/lab-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  TlsProbe https://127.0.0.1:8443/ping
~~~

**Expected:** TLS/hostname error because the certificate lacks **IP SAN:127.0.0.1**. This clearly proves the two checks are independent:

- **Trust properly configured:** the leaf is accepted as the lab trust anchor.
- **Hostname mismatch:** Java must still reject an IP URL absent from the SAN.

**Never fix this by disabling hostname verification.** Use the matching hostname URL or reissue a certificate containing the required SAN.

### 8.4. When Can a Custom Truststore Cause Extra Failures?

Setting **javax.net.ssl.trustStore** for the JVM's default `SSLContext` typically makes clients use **that store's trust anchors** instead of merging with all default CAs. A file holding only the lab certificate can cause calls to **https://public.example** through the same client to fail PKIX.

In Spring Boot applications calling multiple upstreams, configure a **dedicated SSLContext or SSL bundle for the client needing the internal CA**, avoiding altering global trust policy unnecessarily. In production, never leak real passwords into shell history or startup logs; use secret injection per system policy.

## 9. Spring Boot 3.3: SSL Bundles, Server Keystore, and Client Truststore

### 9.1. Server SSL Bundle (Private Key + Cert Chain)

Spring Boot 3.3 supports **spring.ssl.bundle** for declaring named SSL material. Reference example using PEM files from an internal certificate system, assuming files exist with proper permissions:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        web-server:
          keystore:
            certificate: "file:/etc/app/tls/fullchain.pem"
            private-key: "file:/etc/app/tls/server-key.pem"
server:
  port: 8443
  ssl:
    bundle: web-server
~~~

This is an **illustrative deployment configuration**, not the local lab example using section 7's files. **fullchain.pem** here must contain the leaf and required intermediates; the private key must match the leaf and be readable only by the service process. Spring Boot does not automatically fetch/renew CA certificates; rotation must be managed externally.

**A server keystore requires a private key** to authenticate the server; configuring only a server truststore without a server key/cert cannot enable HTTPS.

### 9.2. Client SSL Bundle (Custom CA Truststore)

If a Spring Boot client calls only an internal upstream with an enterprise-trusted CA, configure it separately:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        internal-ca:
          truststore:
            location: "file:/etc/app/tls/internal-ca-truststore.p12"
            password: "provided-by-secret-system"
            type: PKCS12
~~~

**provided-by-secret-system** is a structural placeholder string, **not a real password**; in production use secret injection instead of literals. Use files from a managed CA and verify chain/fingerprints. If this client also needs public CAs, design its trust set accordingly rather than assuming a custom truststore merges system CAs automatically.

In **Spring Boot 3.3**, **RestClientSsl** applies a bundle to `RestClient.Builder`:

~~~java
// Fragment inside @Configuration; not a standalone program.
@Bean
RestClient internalRestClient(RestClient.Builder builder, RestClientSsl ssl) {
    return builder.baseUrl("https://internal-api.example.test")
            .apply(ssl.fromBundle("internal-ca"))
            .build();
}
~~~

Import **org.springframework.boot.autoconfigure.web.client.RestClientSsl**, **org.springframework.web.client.RestClient**, and **@Bean**, placed inside a configuration class. **The bundle name must match** your properties. This isolates the custom CA to a single client rather than disabling certificate checks app-wide.

Spring Boot also offers SSL bundle integration for `WebClient`, `RestTemplate`, and other supported components, though **exact APIs depend on Boot version and client connector**. With Reactor Netty/WebFlux, do not blindly copy JDK `HttpClient` or Tomcat settings over to Netty.

### 9.3. TLS Termination at Ingress / Load Balancer

In Kubernetes or enterprise infrastructure, TLS may terminate at:
- Ingress/Reverse proxy (client → ingress TLS; ingress → Spring Boot may be HTTP or separate HTTPS);
- Service mesh sidecars;
- Embedded Tomcat/Netty itself;
- Intermediate gateways doing HTTPS inspection.

When the certificate users see sits at the ingress, **changing Spring Boot's `server.ssl.key-store` will not change the ingress's public certificate**. Trace the actual **hops** and inspect the true termination point; each TLS hop can have its own CA, hostname, SNI, and truststore.

## 10. Four Error Patterns to Keep Distinct

### 10.1. SSLHandshakeException: PKIX path building failed

**Meaning:** the client could not construct a valid certificate path to a trust anchor under active policy.

Possibilities:
- Root CA is absent from the truststore.
- Server/TLS proxy omitted an intermediate.
- Client runs in a JDK/container image with stale/different `cacerts`.
- Corporate HTTPS inspection replaced the leaf with a cert signed by an internal CA Java does not trust.
- App uses a custom truststore/SSL bundle lacking the needed CA.

What to do:
1. Confirm the exact URL/SNI/port/proxy.
2. Dump the chain with **openssl s_client -showcerts -servername**.
3. Check Issuer/Subject/SAN/timestamps and verify against known trust anchors.
4. Check which truststore the JVM/container actually uses.
5. If the server omitted an intermediate, fix the full chain on the server/ingress. If a valid internal CA is untrusted, import the **verified CA** into the store of the **client that needs it**.

Never solve this with **curl -k**, **trustAllCertificates**, always-true **HostnameVerifier**, or loosening global policies arbitrarily.

### 10.2. Hostname Mismatch / No Subject Alternative Name

**Meaning:** the presented certificate lacks the exact hostname/IP requested by the client.

Causes:
- URL uses an IP instead of a DNS name present in the SAN.
- Cert was issued for another domain.
- SNI was omitted or wrong, causing a load balancer to serve a default certificate.
- Certificate rotated on one replica but not all.

**Fix:** verify cert/SAN for the exact SNI and route, then reissue/configure the right certificate. **Importing a CA never alters a SAN**.

### 10.3. Certificate Expired / Not Yet Valid

**Meaning:** certificate falls outside `NotBefore`/`NotAfter`, or client/server clocks are skewed. Check **both leaf and intermediates**.

**Fix:** verify UTC/NTP clocks and deploy a fresh chain on time. If browsers cached sessions or a node rollout is partial, probe every endpoint/replica individually with SNI/IP. Never disable date checks.

### 10.4. handshake_failure / protocol_version / bad_certificate

Broader alerts—**do not immediately blame the root CA**. Possible causes:
- No common TLS version/cipher/signature algorithm.
- Proxy SNI or ALPN policy.
- Server keystore lacks a valid private key/certificate or has invalid key usage.
- mTLS requires a client certificate not sent by the client, or the server distrusts the client CA.
- Client sent a cert with the wrong purpose or an incomplete client chain.

Inspect **both client and server TLS logs**, especially which peer sent the alert. In mTLS, the client keystore holds the client's certificate + private key, while the server truststore holds the CA trusting clients. Avoid editing the client truststore when the **server is rejecting the client certificate**.

## 11. Controlled JSSE Debugging and Diagnostic Workflow

### 11.1. Java TLS Debug Flags

When running in a lab or protected diagnostic environment:

~~~bash
java \
  -Djavax.net.debug=ssl,handshake,trustmanager \
  -Djava.security.debug=certpath \
  TlsProbe https://localhost:8443/ping
~~~

This is a **diagnostic command**: Java writes verbose logs to stderr covering handshake, trust manager, and path building. You can add **-Djavax.net.ssl.trustStore...** as in section 8 if needed. Do not assume seeing a `Certificate` message in logs proves verification passed; read down to the root error/verification check.

**Security warning:** TLS debugging can expose certificate metadata, hostnames, and session details; options printing data/packets/plaintext carry even greater disclosure risks. Enable temporarily only, secure log files, turn off afterward, and omit secrets from public reports.

### 11.2. Checklist in Exact Order

1. **Pick a specific failing URL**, recording timestamp, host, port, scheme, environment, and root cause (`Caused by`).
2. **Check network:** DNS, TCP, proxies, ingress, and real endpoints.
3. **Check TLS server certificate** with `s_client` and the **exact -servername**; remember virtual hosting.
4. **Check hostname/IP:** compare leaf SAN against actual URL; IP URLs need IP SANs.
5. **Check chain:** leaf/intermediates sent by server; trace path to trusted root; verify dates, EKU, KeyUsage, and policies.
6. **Check real Java truststore** of the active JDK/container/client; inspect JVM flags and SSL bundles/custom `SSLContext`.
7. **Check mTLS** if the server demands client certs; clarify who checks whose cert.
8. **Check HTTP/2 ALPN** once TLS is healthy; separate failing to pick `h2` from handshake failure.
9. **Fix at the right layer:** add missing intermediates on the server, provision valid root CAs on clients, reissue with right SANs, replace expired certs, or fix proxy routing.
10. **Re-test from the real Java application**, not just browser/curl, keeping hostname verification and trust validation enabled.

In multi-instance deployments, test each IP individually while preserving **SNI hostname and hostname verification** (e.g., `curl --resolve`), avoiding generalizing from a single replica.

## 12. Quick Diagnostic Table

| Symptom | Closest layer | What to distinguish |
| --- | --- | --- |
| Connection refused / timed out | TCP/network | Port, firewall, proxy, service readiness |
| UnknownHostException | DNS | Hostname, resolver, network |
| SSLHandshakeException + PKIX path building failed | Certificate chain/trust | Missing intermediate vs. missing root CA vs. custom truststore |
| No subject alternative DNS name matching ... | Hostname | URL/SAN/SNI/default cert |
| No subject alternative names matching IP address ... | IP hostname | Needs IP SAN or valid DNS URL |
| CertificateExpiredException | Validity | Leaf/intermediate dates and clock/NTP |
| Received fatal alert: bad_certificate | TLS/mTLS or cert policy | Who sent the alert, and which side's cert failed |
| Received fatal alert: protocol_version | TLS negotiation | Client/server versions, policies |
| TLS handshake OK, HTTP 401/403 | HTTP authentication/authorization | Credentials, roles, request context |
| TLS OK, HTTP 404 | Routing | URL/context path/controller/ingress |
| TLS OK, HTTP 502 | Gateway/upstream | Which hop failed; separate gateway → app TLS? |
| TLS OK yet no h2 | HTTP/2 ALPN/runtime | Client ALPN, `server.http2.enabled`, TLS termination |
| Browser works, Java throws PKIX | Differing trust sources | JDK truststore vs. OS/browser, missing intermediate, corporate proxy |
| Only one Pod/host fails | Cert/config rollout | Keystore/chain/CA/expiry differs across replicas |

**Rule:** always inspect the **root cause** of the stack trace, not only the top-level exception. An `IOException` can wrap `SSLHandshakeException`; an ingress HTTP 502 can hide an upstream TLS failure.

## 13. Common Mistakes and Security Consequences

**Mistake 1 — Using `curl -k` as a production fix.** `-k`/`--insecure` disables curl's certificate checking; it is only for temporary isolation in controlled environments. Long-term use leaves clients exposed to MITM attacks.

**Mistake 2 — Trusting all certificates in Java.** Writing a no-op `TrustManager` or always-true `HostnameVerifier` defeats server authentication entirely. Never ship this in production code.

**Mistake 3 — Importing an arbitrary leaf fetched from a server into `cacerts`.** The tester might be talking to a spoofed server. Only trust CAs/certs after verifying **fingerprint and origin via an independent channel**; prefer endpoint-scoped truststores.

**Mistake 4 — Thinking the server must send the root.** The root is the client's trust anchor; servers normally send leaf + intermediates. Missing intermediates are the real culprit to check.

**Mistake 5 — Thinking a matching CN is sufficient.** SAN is the modern primary identity field. IP URLs need IP SANs; adding roots does not fix mismatches.

**Mistake 6 — Omitting SNI when testing shared-IP virtual hosts.** You may receive a default cert and misdiagnose the server. Use `s_client -servername` or `curl` URL hostnames with `--resolve`.

**Mistake 7 — Fixing the laptop truststore instead of the failing container.** The container's actual JDK image and JVM properties govern Java trust policy.

**Mistake 8 — Confusing keystore with truststore.** Servers need a private key for HTTPS; clients need trust anchors to verify servers; mTLS adds client-side cert material.

**Mistake 9 — Confusing HTTP/2 handshake with PKIX.** ALPN selects the HTTP application protocol without replacing chain verification; HTTP/2 cannot fix CA errors.

**Mistake 10 — Sharing TLS debug logs indiscriminately.** Metadata or diagnostic traces may contain sensitive data; limit enabling, storing, and sharing them.

## 14. Practice Exercises

**Exercise 1.** Curl trusts `dev-server.pem` and `https://localhost:8443/ping` returns 200, yet `https://127.0.0.1:8443/ping` fails. Why?

**Answer:** The certificate only has `DNS SAN:localhost`, lacking `IP SAN:127.0.0.1`. This is **hostname/IP validation**, not a missing trust anchor.

**Exercise 2.** Java throws `PKIX path building failed` while a browser opens the same URL. Can you conclude the website's root CA is wrong?

**Answer:** No. Java and browsers can use different trust stores/chain caching; the server may lack an intermediate, or the JVM uses a different JDK/custom truststore. Inspect actual SNI/chain/Java truststores.

**Exercise 3.** Server sends leaf and root while omitting the intermediate. Java already trusts the root—why can the client still fail?

**Answer:** It lacks the intermediate certificate needed to verify the leaf's signature up to the root. Fix the server to send the proper intermediate/full chain (or provision a trusted chain cleanly); sending the root does not substitute for a truststore.

**Exercise 4.** Importing a private CA into the truststore fixed Java connecting to host A, yet host B still fails with `No subject alternative DNS name matching`. Should you import another root?

**Answer:** No by default. Hostname B is missing from the presented certificate's SAN; inspect URL/SNI/certificate for that host and reissue if needed.

**Exercise 5.** Java passes `-Djavax.net.ssl.trustStore=lab-truststore.p12` containing one lab leaf, and then calls to a public API fail with PKIX. Why?

**Answer:** With default JSSE `SSLContext`, a custom truststore replaces the default root set, dropping public CAs from the active trust sources. Configure trust per internal client or construct a combined trust policy intentionally.

**Exercise 6.** A browser receives HTTP 401 from an HTTPS endpoint. Did the TLS handshake necessarily fail?

**Answer:** HTTP 401 means an HTTP response arrived over the transport channel; if the browser connected directly over HTTPS without special proxy error pages, the handshake to the responding endpoint succeeded, and 401 points to credentials/authorization.

**Exercise 7.** `openssl s_client` without `-servername` hits an IP hosting multiple virtual hosts. Is that reliable proof that `api.example.test`'s certificate is wrong?

**Answer:** Not yet. The server may have returned a default certificate. Pass the right SNI and verify against the actual URL hostname.

**Exercise 8.** TLS connects cleanly, yet ALPN picks `http/1.1` when you expected `h2`. Should you edit the truststore?

**Answer:** No if chain/hostname already pass. Check `server.http2.enabled`, ALPN support, JDK/connector, and proxy/TLS terminator.

**Exercise 9.** `bad_certificate` occurs when a server requires mutual TLS. Which side's certificate should you check?

**Answer:** Likely the certificate **sent by the client to the server**; check which peer raised the alert and inspect the server truststore, client keystore, EKU/`clientAuth`, and chain in that direction.

**Exercise 10.** Why should you avoid sending full `javax.net.debug` stdout externally?

**Answer:** Debug output can expose hostnames, certificates, session metadata, or sensitive payloads depending on flags; mask/restrict access and collect only what is necessary.

## 15. Conclusion and Checklist

**TLS handshake** establishes the secure connection; **certificate chain/truststore** determines whether the server's public key is trusted; **hostname verification** confirms the certificate covers the exact host/IP accessed. All of these checks **must pass together**—they are not interchangeable labels.

Before fixing an HTTPS error in Spring Boot/Java:
- Trace the exact **URL → DNS/IP → proxy/ingress → port**.
- Inspect the **SNI and actual certificate** sent by the server.
- Verify **SAN, NotBefore/NotAfter, leaf/intermediate/root, EKU, and algorithms**.
- Verify the **truststore of the active JVM/container**; never use trust-all.
- If an intermediate is missing, **fix the server full chain**; if a valid private CA is missing, **provision the trust anchor** strictly to the scoped clients.
- If SAN is wrong, fix **hostname/routing/certificate**, never randomly import CAs.
- If mTLS is required, separate **client key material** from **server trust material**.
- Once TLS is healthy, inspect **HTTP/2 ALPN** and HTTP statuses.
- Re-verify from the **real Java client** rather than inferring solely from curl/browsers.
- Protect private keys and logs; never carry demo passwords or lab truststores into production.

## Official References

- RFC 8446 — TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- Oracle Java 17 — keytool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Oracle — Java Secure Socket Extension Reference Guide: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- Spring Boot 3.3 — SSL bundles: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Spring Boot 3.3 — RestClientSsl: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html
- Spring Boot 3.3 — Embedded Web Servers and HTTP/2: https://docs.spring.io/spring-boot/3.3/reference/how-to/webserver.html
- OpenSSL s_client: https://docs.openssl.org/master/man1/openssl-s_client/
- OpenSSL verify: https://docs.openssl.org/master/man1/openssl-verify/