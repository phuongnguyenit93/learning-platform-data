# Managing Secrets, Expiration, and Per-Server Certificate Reloading

> **Module:** Spring Boot - web-runtime · **Group:** TLS and HTTP/2. This lesson focuses on the **TLS certificate** and **private key** lifecycle when Spring Boot runs on Tomcat, Reactor Netty, Jetty, or behind a reverse proxy; it explains expiration, automated renewal, reloading/rotation, per-server compatibility, and client-side verification procedures. Examples use **Spring Boot 4.1.2**, **Java 17+**, Maven, OpenSSL, and SSL bundles. Production guidance must be tailored to your real architecture and security policies.

## Objectives

After this lesson, you will be able to:

1. Distinguish **private keys, certificates, certificate chains, truststores, and keystore passwords**; know what is secret and what can normally be public.
2. Design certificate and key provisioning through a **managed secret manager/volume**, never committing private keys to Git, baking them into images/JARs, or printing them in logs.
3. Read `notBefore`/`notAfter`, SAN, issuer, and certificate chains, and verify domain names, expiration dates, key matching, and key usages.
4. Configure `spring.ssl.bundle.pem.*` or `spring.ssl.bundle.jks.*` and bind the bundle to `server.ssl.bundle`; understand how this differs from `server.ssl.key-store` or discrete TLS properties.
5. Understand the **reload-on-update** support matrix: Spring Boot documents Tomcat and Reactor Netty; never assume Jetty/Undertow or every SSL consumer shares the same hot-reload capability.
6. Build an HTTPS/HTTP/2 demo, test certificates **over the wire**, and swap a certificate without restarting on compatible servers.
7. Build a runbook for certificate expiry monitoring, early renewal, multi-instance rollout, alerting, and safe rollback.

## 1. Objects Involved in a TLS Connection

To an HTTPS client, the server normally presents a **leaf certificate** proving its hostname identity. The certificate contains the **public key**, certificate identity, validity dates, issuer, and CA signature; it does not contain the private key. The server uses the matching **private key** during the TLS handshake to prove key possession.

~~~text
HTTPS client / browser
   |
   | TCP connect, TLS ClientHello
   | SNI = api.example.com, ALPN = h2,http/1.1
   v
TLS terminating endpoint
   |
   +-- certificate for api.example.com
   +-- intermediate certificate chain when needed
   +-- private key matching the leaf certificate
   |
   +-- TLS handshake / verify / negotiate ALPN
   v
HTTP/2 (h2) or HTTP/1.1
   |
   v
Spring controller, API, static resources
~~~

**Note:** ALPN determines the negotiated HTTP protocol after TLS; replacing/editing a TLS certificate **does not automatically enable HTTP/2**, and enabling HTTP/2 **does not automatically renew certificates**.

| Object | Nature | How to manage |
| --- | --- | --- |
| **Private key** (e.g. `privkey.pem`) | **Most critical secret**; holding the key allows impersonation alongside the matching cert | Secret manager/KMS/HSM or dedicated volume; minimal read permissions; never log or commit |
| Leaf certificate (e.g. `cert.pem`) | Public certificate containing SAN, issuer, `notBefore`/`notAfter` | May be public; still requires valid chain and lifecycle management |
| Certificate chain (e.g. `fullchain.pem`) | Leaf + intermediates typically sent to clients | Ensure valid order and chain; never include the private key in the chain |
| CA root/trust anchor | Used to verify peer identity | Configure in truststore/OS/browser trust; do not confuse with server private-key keystore |
| JKS/PKCS12 keystore | Container that can hold private key + cert chain, password-protected | Both file and password must be protected, permissioned, and rotated |
| Truststore | Holds certificates/CAs trusted by the connecting party | Not a place for the web server's private key; manage trust carefully |
| TLS certificate expiry | Time when the certificate becomes invalid; measured in UTC | Monitor from the **live served endpoint**, not only files on disk |

A valid TLS setup needs the **right private key, leaf cert, CA chain, SAN domain names, and validity period**. Browsers trust domains based on CA/trust chains and name checks. Do not use `CN` as the sole domain check; for modern TLS certificates, **Subject Alternative Name (SAN)** is essential.

### Expiration Concepts

- `notBefore`: certificate is not yet valid before this timestamp.
- `notAfter`: certificate is expired after this timestamp; check in UTC against an accurate clock.
- `subject`/`SAN`: hostnames and IPs represented by the certificate.
- `issuer`: signing authority; must chain up to a suitable trust anchor.
- `keyUsage` and `extendedKeyUsage`: permitted key/certificate purposes, typically including `serverAuth` for TLS server certificates.

An expired certificate causes TLS validation failures even while the app stays alive and internal health endpoints return 200. Certificate expiration is **unrelated** to DNS record TTLs, session timeouts, cookies, or private key lifetimes.

## 2. Identify Where TLS Actually Terminates

Before editing Spring Boot settings, find out where TLS **terminates**:

~~~text
A. End-to-end TLS at the application:
Browser HTTPS -> Tomcat/Netty HTTPS -> application

B. TLS termination at gateway/CDN:
Browser HTTPS -> CDN/Nginx/Ingress (public certificate)
              -> internal HTTP or HTTPS -> Spring Boot

C. Internal re-encryption/mTLS:
Browser HTTPS -> ingress TLS -> Spring Boot HTTPS backend
              -> database/client HTTPS with separate trust and secrets
~~~

| Architecture | Which certificate needs rotation? | Who reloads it? |
| --- | --- | --- |
| Direct TLS on Tomcat | Cert/key served by embedded Tomcat | Spring Boot SSL bundle → Tomcat connector when compatible |
| Direct TLS on Reactor Netty | Cert/key served by embedded Netty | Spring Boot SSL bundle → Netty when compatible |
| Public TLS on Nginx/Envoy/CDN/Ingress | Gateway/CDN cert/key, **not necessarily inside the JVM** | Ingress, CDN, or proxy controller via its own mechanism |
| Ingress HTTPS then backend HTTPS | **Two** TLS hops and possibly two different certs | Separate rotation and expiry monitoring for each hop |
| Internal `h2c` HTTP after TLS termination | Cert lives at TLS edge; backend speaks `h2c` if allowed | No backend TLS cert for Spring Boot to hot-reload on that hop |
| Outbound `WebClient`/JDBC TLS/mTLS | Client identity/trust material may differ from inbound cert | Depends on whether that client/connector supports bundle reload |

**Do not edit `server.ssl.*` expecting to "renew the cert" if browsers actually see a CDN's certificate.** Inspect the certificate from outside on the public network with the proper SNI, identifying frontend vs. backend first.

HTTP/2 over TLS is normally negotiated via ALPN token `h2`. Spring Boot supports `server.http2.enabled=true` on compatible servers: **`h2`** when TLS is enabled, or **`h2c`** (cleartext HTTP/2) on non-SSL hops if permitted. Never send `h2c` over the Internet just to avoid configuring TLS.

## 3. Secret Management: Private Keys Must Never Live in Source Code

### Which Items Are Secrets?

- Private keys in PEM/PKCS12/JKS containing private keys, secret-manager tokens, keystore passwords, and client-auth private keys: **secrets**.
- Public PEM certificates/CA trust chains: normally public per PKI design; paths, metadata, and internal topology may still require access control.
- A keystore password does not substitute for filesystem permissions: even if a PKCS12 file is password-protected, an attacker who steals the file can brute-force it offline. Unencrypted PEM private keys demand even stricter ACLs/volumes.

**Do not do this:**

~~~properties
# Never use in committed production configuration:
server.ssl.key-store-password=my-real-production-password
spring.ssl.bundle.jks.web.keystore.password=super-secret
~~~

Never copy private keys into `src/main/resources/` and commit them or bake them into executable JARs/Docker images. Never paste private keys into tickets, logs, emails, crash dumps, or issue trackers.

### Recommended Provisioning Approaches

1. **Secret manager/KMS/Vault**: the app or orchestrator has a workload identity; the secret manager grants read access to the right secret with centralized rotation and auditing.
2. **Mounted files from a secret volume**: e.g., Kubernetes Secret/CSI volume, Docker secrets, or files written by a security agent; Spring Boot reads them via `file:...`. Set strict root/owner permissions across all ancestor directories.
3. **Managed PKCS12 keystores**: if your organization standardizes on PKCS12/JKS, inject passwords without hardcoding.
4. **TLS termination at the edge**: public Internet certificates are managed by Ingress/CDN; the JVM can serve internal HTTP or separate TLS when required.

**Pick a method that rotates keys without rebuilding images.** Files on the classpath or inside a JAR may be convenient in dev, but are a poor choice for production cert rotation. For Spring Boot PEM reloading, use **real filesystem paths** and the file watcher; do not assume classpath resources inside a JAR can be modified live at runtime.

### Secret Mount Example

~~~text
/run/secrets/webserver/
  fullchain.pem   # leaf + intermediate certs
  privkey.pem     # private key, readable only by the service account
~~~

Example properties (paths vary by environment):

~~~properties
server.port=8443
server.ssl.bundle=webserver

spring.ssl.bundle.pem.webserver.keystore.certificate=file:/run/secrets/webserver/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/run/secrets/webserver/privkey.pem
spring.ssl.bundle.pem.webserver.reload-on-update=true
~~~

Ensure the Spring Boot container/process can read the files once the volume is mounted, while preventing untrusted accounts from **writing** to the directory or swapping symlinks. Never `chmod 777` to fix permission errors.

### Are Environment Variables Completely Safe?

No. Passing passwords via environment variables avoids committing them in repositories, yet process environments can leak through crash logs, `/proc`, diagnostics, or admin tooling if access is loose. Choose secret delivery fitting your threat model; mask/exclude secrets from `/actuator/env` and logs. Never dump the entire Spring `Environment` or config properties to logs while debugging TLS.

Spring property placeholders can reference keystore passwords:

~~~properties
spring.ssl.bundle.jks.web.keystore.password=${WEB_KEYSTORE_PASSWORD}
~~~

This is a **syntax example**, containing no real password and still requiring secure secret delivery.

## 4. SSL Bundles in Spring Boot

Spring Boot provides the `SslBundle` abstraction configured via `spring.ssl.bundle.pem.*` or `spring.ssl.bundle.jks.*`. A bundle groups key/trust material and TLS settings so consumers such as the embedded web server can reference it by name.

### 4.1. PEM Certificate and Private Key

~~~properties
spring.ssl.bundle.pem.webserver.keystore.certificate=file:/run/secrets/webserver/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/run/secrets/webserver/privkey.pem
server.ssl.bundle=webserver
server.port=8443
~~~

`webserver` is a **user-chosen bundle name**. `keystore.certificate` supplies the server certificate chain to present; `keystore.private-key` must match the leaf certificate. For Let's Encrypt, Boot documentation illustrates `fullchain.pem` and `privkey.pem`.

### 4.2. JKS/PKCS12 with Password from a Secret Manager

~~~properties
spring.ssl.bundle.jks.webserver.keystore.location=file:/run/secrets/webserver/server.p12
spring.ssl.bundle.jks.webserver.keystore.password=${WEB_KEYSTORE_PASSWORD}
spring.ssl.bundle.jks.webserver.keystore.type=PKCS12
spring.ssl.bundle.jks.webserver.key.alias=server

server.port=8443
server.ssl.bundle=webserver
~~~

The alias must point to the actual private key/cert chain entry in the keystore. If the key password differs from the keystore password, configure the appropriate key password property or align them during keystore creation. **Do not combine** `server.ssl.bundle` with discrete private key/keystore settings under `server.ssl`: Boot states these approaches cannot be mixed. When using a bundle, configure protocols/ciphers inside the bundle options if needed rather than expecting `server.ssl.enabled-protocols` to override it.

### 4.3. Keystore vs. Truststore

- An inbound HTTPS **server** needs a key pair + certificate; that is **server identity**.
- When enabling **client certificate authentication (mTLS)**, the server also needs trust material to verify client certs; configure a `truststore`/CA policy and `server.ssl.client-auth` appropriately.
- When Spring Boot calls **outbound HTTPS** via `WebClient`/`RestClient`, the client needs to trust the server's CA; for mutual TLS, it also needs its own client cert/private key.

Never drop a server's public PEM certificate into a global truststore for all clients and disable hostname verification. Never use `trust-all` or `NoopHostnameVerifier` to work around certificate errors. The goal is a valid chain, SAN, and trust policy—never disabling TLS checks.

## 5. Certificate Reloading: reload-on-update Is Not Certificate Renewal

There are **three distinct operations**:

1. **Issuance:** a CA/ACME/internal PKI signs a new certificate.
2. **Deployment:** the new cert/key/chain files are placed at the paths read by the server.
3. **Reload (activation):** the TLS server begins serving the new key/certificate for **new handshakes**.

Spring Boot **does not automatically register/renew** Let's Encrypt certificates. Tools like Certbot, cert-manager, Vault PKI, or enterprise CA systems handle step 1 and often step 2. Spring Boot SSL bundle reload assists with step 3 for compatible consumers.

### Actual Support by Server

| Location / Server | Spring Boot 4.1.x | Documented SSL bundle reload | Notes |
| --- | --- | --- | --- |
| **Embedded Tomcat** (Spring MVC) | Yes | **Yes** | Spring Boot bundle watcher notifies Tomcat to refresh certificates on SSL connectors |
| **Embedded Reactor Netty** (WebFlux) | Yes | **Yes** | Netty consumer supports reloadable SSL bundles |
| **Embedded Jetty** | Yes | **Not listed** as a reload-supporting consumer in current Boot docs | Do not promise hot reload; test in practice or use restarts/rolling deployments |
| **Embedded Undertow** | **Removed in Spring Boot 4** due to Servlet 6.1 requirements | Not applicable to Boot 4 | Spring Boot 3 included Undertow; do not use older docs to infer Boot 4 support |
| **Nginx/Envoy/Ingress/CDN** | Outside the JVM | Not controlled by `spring.ssl.bundle.*` | Use the TLS terminator's own reload/rolling mechanism |
| **Custom embedded server / SSL consumer** | Depends on integration | Not by default | Consumer must support reload; `SslBundles` having a bundle does not mean every client refreshes its `SSLContext` |
| **Load balancer managed TLS** | Outside the app | Not decided by Spring Boot | Rotation belongs to the cloud LB / certificate manager |

**Important:** "Jetty is not listed" does not claim Jetty can never refresh certificates on its own. It simply means **Spring Boot SSL bundle hot reload is not guaranteed** without testing your exact version, connector, and integration. For Jetty in production, plan rolling restarts or a separately verified refresh mechanism.

### Enabling PEM reload-on-update

~~~properties
spring.ssl.bundle.pem.webserver.reload-on-update=true
spring.ssl.bundle.pem.webserver.keystore.certificate=file:/run/secrets/webserver/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/run/secrets/webserver/privkey.pem
server.ssl.bundle=webserver
~~~

Boot docs describe a **file watcher** monitoring changes to the configured files; when the watcher detects a change and the quiet period elapses, the bundle reloads and compatible consumers like Tomcat/Netty pick up the new material.

You can tune the watcher quiet period:

~~~properties
spring.ssl.bundle.watch.file.quiet-period=2s
~~~

Waiting through a quiet period reduces the chance of reloading mid-write while an external tool updates files; it does **not** turn updating a cert/key pair into an atomic transaction. A new cert paired with an old key will fail reload. Therefore, cert and key deployment must be coordinated consistently.

### With Certbot / Let's Encrypt

Official example using the standard paths:

~~~properties
spring.ssl.bundle.pem.webserver.reload-on-update=true
spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/letsencrypt/live/example.com/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/letsencrypt/live/example.com/privkey.pem
server.ssl.bundle=webserver
server.port=8443
~~~

Paths under `/etc/letsencrypt/live/...` are usually symlinks into `archive/...`. Boot docs note that the file watcher **follows symlinks** to handle those target updates. Even so, symlink target permissions, filesystem/container watch events, update timing of both files, and live server reload **must still be tested**.

Use `certbot renew --dry-run` to test your environment's ACME setup *if you have already configured Certbot with a valid domain and permissions*. That command cannot mint real certificates on arbitrary laptops. Do not run live ACME requests during a local demo.

### Avoid Misconceptions About JKS Hot Reload

Spring Boot supports JKS/PKCS12 bundles for TLS configuration. However, the **reload-on-update** documentation shows **PEM file bundle** examples and names Tomcat/Netty as compatible consumers. Do not assume every keystore format or legacy `server.ssl.*` config auto-reloads when files change on disk. If your system uses PKCS12/JKS and needs zero-downtime rotation, verify support for your **exact version, bundle type, and embedded server**; without clear evidence, use rolling restarts.

### Relationship Between Existing Connections and New Connections

A TLS certificate is presented during the **handshake**. Upon reload, already-established connections can keep running with their prior TLS state until closed; what matters is that a **new connection after reload** sees the new certificate. HTTP/2 can keep a connection alive for a long time multiplexing requests. Therefore, never check rotation solely in a browser tab holding an existing connection.

TLS session resumption, keep-alive, reverse proxy pools, and HTTP/2 connection reuse can complicate observation. Always **open a fresh connection**, send the right SNI, and force no session reuse when needed to verify the server's live leaf cert.

## 6. HTTP/2 and TLS: How Certificates Affect the Server

Spring Boot provides:

~~~properties
server.http2.enabled=true
~~~

When SSL is enabled and supported by the server, clients can negotiate HTTP/2 via TLS/ALPN token `h2`; otherwise client/server may use HTTP/1.1. When SSL is disabled, some embedded servers support `h2c` on internal networks, though **`h2c` is unencrypted**.

| Server | HTTP/2 per Boot 4.x docs | TLS/rotation notes |
| --- | --- | --- |
| Tomcat 11.x | Supports `h2` and `h2c` | Use TLS bundle for HTTPS; bundle reload is documented |
| Reactor Netty | Supports `h2` and `h2c` | SSL bundle reload is documented; ensure clients support ALPN |
| Jetty | HTTP/2 needs extra dependencies per docs (and proper ALPN) | Do not assume bundle hot reload; test exact config |
| Edge reverse proxy | May negotiate `h2` publicly and HTTP/1.1 or `h2c` to backend | Public cert must be managed at the edge |

**TLS version differs from HTTP version.** TLS 1.3 does not automatically mean HTTP/2, and HTTP/2 over TLS still requires a valid certificate chain. An expired cert blocks HTTPS authentication before HTTP/2 requests can safely flow.

If TLS terminates at a CDN while the Spring Boot backend runs HTTP/1.1, browsers can still speak HTTP/2 to the CDN. To determine protocols on **each hop**, measure both client→edge and edge→backend.

## 7. Hands-On Project: Spring Boot 4.1.2 HTTPS/HTTP/2 with PEM Hot Reload

This example is intentionally compact to focus on TLS: Spring MVC's default Tomcat reads PEM files from a local directory configured via `file:` resources with `reload-on-update=true`. Keep keys out of `src/main/resources/` and Git; this example uses self-signed certificates **for learning only**.

**Prerequisites:** JDK 17+, Maven compatible with Spring Boot 4, and OpenSSL CLI on macOS/Linux/WSL/Git Bash. On Windows, you can use PowerShell with an OpenSSL binary; `\` in Bash commands is strictly POSIX shell line continuation.

### 7.1. Layout

~~~text
tls-rotation-demo/
  pom.xml
  .gitignore
  tls/                         # created at runtime; do not commit
    server.crt                 # demo public cert
    server.key                 # demo private key
  src/main/java/com/example/tlsdemo/
    TlsDemoApplication.java
    PingController.java
  src/main/resources/
    application.properties
~~~

### 7.2. pom.xml

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
    <artifactId>tls-rotation-demo</artifactId>
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

`spring-boot-starter-webmvc` is the Boot 4.x MVC starter; Tomcat is the default embedded server unless swapped via dependencies. If adapting this demo to WebFlux/Reactor Netty, use `spring-boot-starter-webflux` and reactive handlers; the same PEM SSL bundle properties apply to Netty, though Servlet APIs must not be used on WebFlux.

### 7.3. TlsDemoApplication.java

~~~java
package com.example.tlsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TlsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TlsDemoApplication.class, args);
    }
}
~~~

### 7.4. PingController.java

~~~java
package com.example.tlsdemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

The endpoint knows nothing about keys/certs; TLS happens **before** HTTP requests reach the controller.

### 7.5. application.properties

~~~properties
server.port=8443
server.http2.enabled=true
server.ssl.bundle=webserver

spring.ssl.bundle.pem.webserver.keystore.certificate=file:./tls/server.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=file:./tls/server.key
spring.ssl.bundle.pem.webserver.reload-on-update=true
spring.ssl.bundle.watch.file.quiet-period=2s
~~~

- `file:./tls/server.crt` and `file:./tls/server.key` are paths relative to the process **working directory**. In production, use absolute paths pointing to secret mounts.
- `server.ssl.bundle=webserver` binds the declared bundle to the embedded server; do not also set `server.ssl.key-store` or `server.ssl.certificate`.
- `server.http2.enabled=true` requests HTTP/2 support from embedded server and clients, using ALPN with TLS.
- `quiet-period=2s` only affects the file watcher; it does not replace checking cert/key consistency and does not automatically issue or renew certificates.

### 7.6. .gitignore

~~~gitignore
/tls/
/target/
~~~

Do not treat `.gitignore` as complete security: it only keeps Git from tracking untracked files. If a key was ever committed, you must **revoke/rotate the real key**, purge the secret from exposed systems, and clean history per procedure. Never use demo private keys on Internet-accessible servers.

### 7.7. Generate a Self-Signed Certificate for localhost

In the project root, with OpenSSL supporting `-addext`:

~~~bash
mkdir -p tls

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout tls/server.key \
  -out tls/server.crt \
  -days 7 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

# Restrict private key read permissions (POSIX); proper ACL/ownership still required.
chmod 600 tls/server.key

# Inspect public cert metadata without printing the private key.
openssl x509 -in tls/server.crt -noout \
  -subject -issuer -dates -serial -ext subjectAltName
~~~

Generating an unencrypted RSA private key is **only for local demos** so the server can read it automatically. In production, prefer trusted CAs/ACME, secret managers or HSMs where appropriate, and least-privilege permissions. Never use self-signed certs on public sites. `-days 7` is a short lifetime for learning, not a production validity recommendation.

A self-signed certificate is not in browser/OS truststores; normal HTTPS requests will fail with "unknown authority" errors. **Never resolve that by disabling certificate verification in real applications.**

### 7.8. Run Spring Boot

~~~bash
mvn spring-boot:run
~~~

Run from the project root so Boot reads both files in `tls/` and starts an HTTPS listener on port 8443. Some systems may lack client-side ALPN/`h2` support; with Tomcat/JDK 17, the server supports HTTP/2 per Boot docs.

Call while explicitly trusting the demo self-signed certificate:

~~~bash
curl --cacert tls/server.crt -i https://localhost:8443/ping
~~~

Typical successful response:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"status":"ok"}
~~~

This is a **structural illustration**; the actual status line may be `HTTP/2 200` if curl negotiates `h2`, and header order/content length may vary. Pass `--cacert` to trust the **exact demo cert file**, avoiding `-k` unnecessarily. On other machines, never copy the private key around for testing; distribute only the public cert/root CA.

To test HTTP/2 (depends on a curl build with HTTP/2):

~~~bash
curl --http2 --cacert tls/server.crt -i https://localhost:8443/ping
curl -V
~~~

Observe the protocol in the status/verbose output. HTTP/2 may not be active on a hop even when HTTPS works. Behind a load balancer, distinguish protocols between browser→edge and edge→app.

### 7.9. Inspecting the Live Certificate Presented by the Server

The command below inspects a handshake directly against the listener; **run on a fresh connection**:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn h2 \
  -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout -serial -subject -dates -fingerprint -sha256
~~~

- `-servername localhost` sends **SNI**. When a server hosts multiple domains, omitting SNI may return a default certificate instead of the hostname's cert.
- `-connect localhost:8443` checks only the **local listener**. If public traffic goes through a CDN, inspect the public hostname on port 443 rather than only the backend.
- `-fingerprint -sha256` and serial allow comparing before/after rotation without printing the private key.
- `-alpn h2` proposes HTTP/2; to see the ALPN result, read `s_client`'s verbose output directly (not piped through `openssl x509`).

In production, inspect both certificate and chain:

~~~bash
openssl s_client -connect api.example.com:443 \
  -servername api.example.com \
  -verify_return_error -showcerts </dev/null
~~~

Do not rely on `Verify return code: 0` alone if client truststores, SNI, or hostname checking are misconfigured. Use a standard HTTP client that validates hostnames/CAs like `curl -v https://api.example.com/...` **without** `-k`. `openssl s_client` also supports `-verify_hostname api.example.com` on compatible versions to check SANs.

### 7.10. Testing Reload with a New Cert While KEEPING the Same Key

To isolate the watcher mechanism, create a **new certificate signed with the same demo private key**, updating only one file. **This tests certificate reload, not private-key rotation.**

~~~bash
openssl req -new -x509 -sha256 \
  -key tls/server.key \
  -out tls/server-next.crt \
  -days 8 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

openssl x509 -in tls/server-next.crt -noout -serial -dates

# On the same POSIX filesystem, rename over the target file.
# Perform only in local demo; never manipulate production certs manually like this.
mv -f tls/server-next.crt tls/server.crt
~~~

Once the watcher detects the change, the bundle reloads the cert and the compatible Tomcat consumer applies it to new handshakes. After waiting slightly longer than the watcher/quiet period, rerun the `-serial`/`-fingerprint` check on port 8443; **the new values must differ** from before if reload succeeded.

Because the self-signed demo cert changed, the old public cert previously trusted by `curl --cacert tls/server.crt` will no longer match if the client still holds an older copy. Clients must use the updated cert file/CA to validate, rather than assuming a new cert is trusted merely because it shares the private key.

**On Windows:** file replacement/rename semantics differ; use appropriate OpenSSL/PowerShell operations and check permissions. Never copy POSIX `mv -f` into Windows production scripts without verifying atomicity and file watcher behavior.

**If reload does not trigger:** inspect file watcher logs, file read permissions, `file:` paths, quiet period, Boot/server versions, and live handshakes. Never assume reload happened just because the file changed on disk. In CI, you can generate two certs and test new handshakes without restarting the app, avoiding hardcoded sleeps that cause flaky tests.

### 7.11. When Both Private Key and Certificate Must Rotate

In production, use issuance/deployment tooling that guarantees:

- Generating a new key/cert pair and verifying they **match**.
- Updating the full chain, SAN, EKU, and validity window.
- Staging files in a restricted directory with proper ACLs and verifying before publishing.
- Publishing the cert/key pair **consistently** (e.g., versioned secret volumes or atomic symlink switches managed by orchestrators) so the watcher never observes a new cert with an old key.
- Alerting on reload failures and keeping the prior version for policy-compliant rollback.
- Testing new handshakes against **each instance/pod**, not just once through a load balancer that might route to an already-updated pod.
- Revoking/destroying the old key only after confirming services no longer rely on it per PKI rules.

Even after deploying cert/key files somewhere, **that does not prove every listener/SSLContext refreshed**. Measure the cert **actually served** on the socket.

## 8. Monitoring Certificate Expiration: Monitor Endpoints, Not Just Disks

Recommended observation thresholds:

| Window before expiration | Suggested action |
| --- | --- |
| 30 days | Early warning; verify auto-renew job and owner |
| 14 days | Investigate if no new cert has been issued or renewal is failing |
| 7 days | Escalate priority and verify deployment across all instances |
| 3 days / 1 day | Urgent alert per SLO; prepare failover/manual rotation |
| Past expiration | Incident; clients will likely fail TLS handshakes |

These thresholds are **operational policy examples**, not RFC mandates. For short-lived certificates, set alerts proportionally to their lifetime and renewal cadence, keeping buffer for CA/challenge/maintenance windows. Monitoring only right before expiry leaves no margin for clock skew or CA outages.

### Two Separate Targets to Measure

1. **Certificate at the source**: updated `fullchain.pem` file, secret manager entry, or PKCS12 metadata.
2. **Certificate served over TLS**: the leaf cert returned by a **new handshake** to the endpoint with the right SNI and port.

If the file on disk expires next year while the server still serves a cert expiring this week, **deployment or reload is broken**. If the edge cert is fresh while an internal mTLS backend cert is stale, checking only the public URL misses the internal failure.

### Basic OpenSSL Commands

~~~bash
# Local certificate file:
openssl x509 -in /run/secrets/webserver/fullchain.pem -noout \
  -subject -issuer -serial -dates -ext subjectAltName

# Check whether the certificate expires within the next 30 days (2,592,000 seconds).
# Exit code 0: still valid past that window; non-zero: expiring soon or error.
openssl x509 -in /run/secrets/webserver/fullchain.pem \
  -noout -checkend 2592000
~~~

`-checkend` is easy to run in cron/monitoring, though it only inspects the given **file**; it does not check whether the private key matches or whether the listener reloaded. Pair it with live TLS probes.

### Java 17 CLI: Reading Leaf Expiration Without Touching Private Keys

Create `CertDeadline.java` outside the Spring Boot project; this is a **standalone Java program** needing only JDK 17:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.time.Instant;

public class CertDeadline {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CertDeadline <certificate.pem>");
            System.exit(2);
        }

        Path certificatePath = Path.of(args[0]);
        CertificateFactory factory = CertificateFactory.getInstance("X.509");

        X509Certificate certificate;
        try (InputStream in = Files.newInputStream(certificatePath)) {
            certificate = (X509Certificate) factory.generateCertificate(in);
        }

        Instant now = Instant.now();
        Instant notBefore = certificate.getNotBefore().toInstant();
        Instant notAfter = certificate.getNotAfter().toInstant();
        long hoursLeft = Duration.between(now, notAfter).toHours();

        System.out.println("Subject: "
                + certificate.getSubjectX500Principal().getName());
        System.out.println("Not before: " + notBefore);
        System.out.println("Not after:  " + notAfter);
        System.out.println("Hours left: " + hoursLeft);

        if (now.isBefore(notBefore) || !now.isBefore(notAfter)) {
            System.err.println("Certificate is outside validity window");
            System.exit(2);
        }
        if (!notAfter.isAfter(now.plus(Duration.ofDays(30)))) {
            System.err.println("Certificate expires within 30 days");
            System.exit(1);
        }
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac --release 17 CertDeadline.java
java CertDeadline tls/server.crt
~~~

Output depends on the certificate and system clock:

~~~text
Subject: CN=localhost
Not before: <ISO-8601 timestamp from cert>
Not after:  <ISO-8601 timestamp from cert>
Hours left: <integer hours from current run time>
~~~

The placeholders in the sample output describe variable values, **not fixed literal stdout**. The command will exit 1 on a 7-day self-signed demo cert; that **matches the 30-day warning threshold by design**, not a broken program. In real monitoring, probe live endpoints over TLS rather than relying solely on reading local files.

### Tracking Multiple Domains / SNI / Instances

A service may involve multiple:

- Public domains, wildcard certificates, SAN entries.
- SNI bundles per hostname.
- Ingress replicas, regional load balancers, blue/green deployments.
- Internal mTLS identities for a service mesh.
- Client certificates for databases/third-party APIs.

Monitors must probe **each hostname + port + SNI** and, wherever possible, each individual instance/backend. A load balancer returning the new cert on 95% of requests does not mean the remaining 5% of instances updated. Monitor expiration of both leaf and required intermediate certs; an expired intermediate breaks validation too.

## 9. Safe Certificate Renewal and Deployment Runbook

### Step A — Inventory and Ownership

Record in your management system:

- Hostnames/SANs and public/internal endpoints.
- TLS termination point: CDN, ingress, Nginx, Tomcat, Netty, Jetty.
- CA/issuer, ACME challenge type, or internal PKI workflow.
- Secret path/object ID (never store private keys in the inventory).
- Dependents (apps, load balancers, external clients, mTLS peers).
- Owners, expiration dates, renewal tools, alert schedules, and rollback plans.

### Step B — Early Renewal

Automate renewal with monitoring for CA/network/DNS/ACME failures. With Let's Encrypt + Certbot, `certbot renew` only applies where the host is configured for issuance; Spring Boot will not handle it for you. On Kubernetes, `cert-manager` can renew Secrets automatically, yet the application must still observe the updated files and reload its consumers. **A newly issued certificate is not the same as one live-served by the server.**

### Step C — Pre-Publish Validation

Verify:

1. SAN covers all served hostnames; wildcards do not match arbitrary multi-level subdomains.
2. `notBefore`/`notAfter` are valid against NTP-synced clocks with sufficient remaining buffer.
3. Leaf cert matches the private key.
4. Certificate chain includes intermediates and a trusted issuer; never mistake `cert.pem` for `fullchain.pem`.
5. Certificate has `serverAuth`/`KeyUsage` and algorithms/key sizes complying with organizational PKI policy.
6. File paths, owners, ACLs, and symlink targets are accurate; secret managers do not leak secrets to logs.

Example comparing cert and key **via SPKI hash** (without printing the private key):

~~~bash
# Both SHA-256 hashes must match when cert and key form a pair.
openssl x509 -in tls/server.crt -pubkey -noout \
  | openssl pkey -pubin -outform DER | openssl dgst -sha256

openssl pkey -in tls/server.key -pubout -outform DER \
  | openssl dgst -sha256
~~~

Never upload private key files to third-party "certificate checker" websites to test. Use local OpenSSL/`keytool`.

### Step D — Deployment

- Stage and verify the new cert/key in a restricted location.
- Publish atomically via secret manager/versioned mounts; for PEM pairs, avoid partial updates.
- When using Boot's SSL bundle watcher + Tomcat/Netty, ensure `reload-on-update` is enabled, the path is watched, and files actually changed.
- When the server lacks documented hot reload, use a **rolling restart** with readiness probes/connection draining instead of forcing an unsupported API.
- When TLS terminates at a gateway/CDN, invoke the gateway/CDN reload flow.
- Avoid restarting all pods simultaneously without a canary; minimize downtime within system limits.

### Step E — Post-Deployment Verification

- Open a fresh external TLS handshake per hostname/SNI.
- Compare fingerprint, serial, `notAfter`, SAN, and chain of the **served cert** against expectations.
- Verify HTTP 200 and HTTP/2 ALPN (if required).
- Check individual pods/instances or canary routes, not just one request through an LB.
- Check mTLS clients, outbound TLS dependencies, and app health/error rates.
- Retain rollback keys/certs per policy window; clean up afterward.

### Step F — Continuous Monitoring

Track TLS handshake failure rates, expiry alerts, watcher/reload logs, connectivity errors, certificate inventory drift, and renewal job health. Alert if **source files change while served certificates stay unchanged** past the expected propagation window. Rehearse rotation drills before an actual incident strikes.

## 10. SNI, Multiple Domains, and Multiple Certificates

A single JVM listener can serve multiple hostnames using **Server Name Indication (SNI)**. Clients send the hostname in `ClientHello` so the TLS terminator picks the matching cert before any HTTP request is parsed.

Spring Boot supports mapping bundles by server name for **Tomcat and Netty** per Embedded Web Servers docs:

~~~properties
server.port=8443
server.ssl.bundle=defaultweb

server.ssl.server-name-bundles[0].server-name=api.example.com
server.ssl.server-name-bundles[0].bundle=apiweb

server.ssl.server-name-bundles[1].server-name=admin.example.com
server.ssl.server-name-bundles[1].bundle=adminweb
~~~

Bundles `defaultweb`, `apiweb`, and `adminweb` must each be declared separately with matching keys/certs. This is an **illustrative config fragment**, not runnable on its own without those bundles. The default bundle handles connections lacking SNI or matching no mapping per server rules.

Monitor every hostname individually: a healthy listener can still fail for one domain whose SNI cert expired. When testing, always use real hostnames or `openssl s_client -servername ...`; calling an IP directly can hit the default cert and cause domain errors.

**Jetty:** Boot docs note that SNI mapping via `server-name-bundles` is not supported identically to Tomcat/Netty; Jetty uses its own SNI mechanism when multiple certificates are loaded in certain setups. Do not copy the fragment above assuming Jetty handles it identically.

## 11. Common Pitfalls and Diagnostics

| Symptom | Possible cause | Check / resolution |
| --- | --- | --- |
| Browser reports certificate expired while internal app returns 200 | Public TLS cert on edge/Tomcat expired | Probe public endpoint/hostname/SNI, inspect `notAfter` |
| Cert file updated yet browser still sees old cert | Reload did not run, checked wrong hop, cached session, or stale pod | Open fresh TLS connection; compare served fingerprint per instance |
| Boot fails to start TLS | Unreadable private key, key/cert mismatch, wrong bundle name/path | Inspect logs, file ACLs, public-key hashes, PEM/PKCS12 format |
| `NoSuchFileException` on `file:` path | Unexpected working directory; secret mount missing | Use absolute paths in prod; mount secrets before startup |
| `SSLHandshakeException` hostname mismatch | Cert SAN lacks hostname or wrong SNI | Check SAN and `-servername`; reissue cert with right names |
| `PKIX path building failed` | Client lacks trusted root/intermediate, missing chain, or wrong truststore | Inspect chain/trust; never disable TLS verification |
| 443 works yet HTTP/2 is unused | ALPN/HTTP2 disabled on right hop or client lacks support | Check `server.http2.enabled`, `curl --http2`, and proxy config |
| New cert paired with old private key | Inconsistent deployment of file pair | Stage pair and verify SPKI match before publishing |
| Certbot renewed yet Tomcat serves old cert | Certbot updated files only; watcher/consumer missed it | Enable bundle reload/right path or perform rolling restart |
| Disk cert expires far in future while public cert expires soon | Public TLS terminates at another CDN/LB or different pod | Inventory termination points; monitor live endpoints |
| `reload-on-update` enabled yet Jetty does not reload | Jetty is not in Boot's supported reload consumer list | Check version docs; use rolling restarts or custom integration |
| Boot 3 Undertow config fails on Boot 4 | Spring Boot 4 removed embedded Undertow | Switch to Tomcat/Jetty or stay on a supported stack/version |
| New cert installed yet clients report unknown CA | Untrusted self-signed cert or wrong CA chain | Use a trusted CA in prod; use `--cacert` in demos |
| Only some clients get TLS errors | Uneven pod rollout, SNI, differing chains/legacy clients | Probe each backend/region/client capability |
| Monitoring expiry via files inside containers | File is not the live cert served by the edge | Monitor external handshakes + files for diagnosis |
| Private key leaked in Git/logs | Missing secret-handling hygiene | Rotate/revoke key, restrict access, run credential incident process |
| Rotation drops HTTP/2 sessions | Server restarts without graceful connection drain | Configure graceful shutdown, connection draining, canary rollouts |
| Cert appears before `notBefore` | CA/server/client clock skew or premature publish | Sync NTP; never publish before validity starts |

### Investigation Order When TLS Breaks After Rotation

1. Who is the TLS terminator for the failing request?
2. Which SNI/hostname/port and which certificate serial/fingerprint were served?
3. Is the certificate valid and accurate in SAN, EKU, chain, and CA trust?
4. Do the expected files/secrets contain the new content with proper read permissions?
5. Did the watcher report a change/reload? Does the consumer have documented support?
6. Is some instance/pod, cached session, or proxy layer still serving the old cert?
7. Is HTTP/2 ALPN directly involved, or did TLS fail before HTTP began?
8. Can you safely roll back or rolling-restart without leaking private keys in debug output?

## 12. When Should You Choose Rolling Restart Over Hot Reload?

Hot reload reduces restarts during routine rotations, yet is not always the best fit:

- Running Jetty or another consumer without documented bundle reload in your Boot version.
- Using a keystore/format whose watcher/refresh behavior is unverified.
- Secrets injected via environment variables at process start, which cannot change in a running JVM.
- Systems with multiple `SSLContext`/listeners (inbound, management, clients) having uneven reload support.
- Files mounted on filesystems that do not emit expected watch events, or non-atomic pair updates.
- Organizations mandating canary rollouts, immutable versioned configs, and strict audits.

For rolling restarts, maintain **at least two replicas** with readiness/health gating for high availability; replace one pod/node at a time, verify fresh handshakes/new certs, and proceed. "Zero downtime" must be validated under real traffic rather than assumed solely from `server.shutdown=graceful`.

### Hot Reload Needs Rollback Too

If a new cert has a bad SAN or mismatched private key, the watcher can fail. Know whether your server keeps serving the old cert, halts the listener, or behaves differently—**never assume** one universal behavior across versions. Keep the prior version, watch logs, and maintain a playbook to republish the old pair or trigger a controlled restart after fixing the issue.

## 13. Production Checklist

### Secret Management and Provisioning

- [ ] Private keys, passwords, and CA issuance credentials are absent from repositories, Docker images, JARs, tickets, logs, and build artifacts?
- [ ] Secret manager/volumes enforce proper identity, RBAC/IAM, ACLs, and auditing; processes read only what they need?
- [ ] TLS termination point for every public/internal hostname is documented, never confusing edge certs with backend certs?
- [ ] Keys use organizational standard algorithms/lengths and are rotated immediately upon suspected compromise?
- [ ] Files/secrets can rotate without rebuilding and redeploying application code where required?

### Certificate Quality

- [ ] SANs cover exact hostnames/IPs instead of relying solely on CN?
- [ ] Certificates are within `notBefore/notAfter` and chain cleanly to a trusted CA?
- [ ] Cert/key SPKI match verified; intermediates complete, trust roots valid?
- [ ] EKU/KeyUsage and revocation/policy checked per organizational mandates?
- [ ] System clocks and cert monitoring are synced and leak-free?

### Reload and Continuity

- [ ] Confirmed actual embedded server is Tomcat, Reactor Netty, or Jetty?
- [ ] For Boot reload, using PEM file bundles with a documented Tomcat/Netty consumer?
- [ ] `reload-on-update` enabled watching real filesystem paths with an appropriate quiet period?
- [ ] Rotated cert/key pairs deploy atomically/consistently without loading mismatched pairs?
- [ ] Probed certs via fresh handshakes with exact SNI per instance/region, including post-rotation?
- [ ] Rolling restart fallback ready if watcher/reload fails?
- [ ] HTTP/2 keepalive, graceful shutdown, and connection draining handled properly?

### Operations and Observability

- [ ] Certificate inventory and owners maintained with pre-expiry alert thresholds?
- [ ] Renewal jobs monitored, dry-run/rollback tested, and live served TLS checked?
- [ ] Alerts configured for expired/not-yet-valid certs, chain mismatches, pod cert drift, and TLS handshake errors?
- [ ] Status tracked separately across public TLS hops, backend re-encryption, and outbound/mTLS?
- [ ] Never enabled `trust-all`/`disableHostnameVerification` just to bypass certificate errors?

## 14. Self-Check Questions with Answers

**Question 1.** Does enabling `spring.ssl.bundle.pem.webserver.reload-on-update=true` in Spring Boot automatically renew Let's Encrypt certs?

**Answer:** No. Boot watches and reloads material when files change; ACME/Certbot/cert-manager/Vault PKI issue and renew certs. You still must verify the new cert deploys and is served live.

**Question 2.** A new cert file shows `notAfter` a year away, yet browsers warn it is expired. What should you do?

**Answer:** Probe the real external TLS terminator using hostname + SNI and inspect the fingerprint/serial/expiry of the **served cert**. A different edge, un-updated pod, inactive watcher, or reused connection may be involved.

**Question 3.** Does SSL bundle hot reload work by default on all Spring Boot 4 servers?

**Answer:** No. Boot docs list Tomcat and Netty; Jetty is not guaranteed through that mechanism, and embedded Undertow was removed in Boot 4. Check exact version support and fall back to rolling restarts.

**Question 4.** Does `server.http2.enabled=true` bypass an expired certificate?

**Answer:** No. HTTP/2 is negotiated after TLS; clients must still validate the certificate and complete the TLS handshake.

**Question 5.** If a keystore password lives in an environment variable, is the private key completely safe?

**Answer:** No. Environments and files can still be exposed via system permissions, logs/dumps, or ops tooling. Enforce least-privilege IAM/ACLs, auditing, and rotation.

**Question 6.** Why is checking only `fullchain.pem` on disk insufficient?

**Answer:** Because the file on disk may differ from the certificate currently served; reload, proxies, or other instances may still hold an old cert. Probe fresh client handshakes per hop.

**Question 7.** When replacing both private key and cert, can you copy each file casually one at a time into the watched path?

**Answer:** No. Mid-copy, the watcher can hit a cert/key mismatch and fail reload. Stage/verify the pair and publish consistently via supported atomic/versioned secret mechanisms.

**Question 8.** One listener serves `api.example.com` and `admin.example.com`. What must you test?

**Answer:** Check SNI/hostname for each domain, plus SAN/chain and `notAfter` for each leaf cert. Checking the default certificate without SNI does not prove every hostname's cert is valid.

**Question 9.** Localhost self-signed certs work with `curl -k`; should you do the same in production?

**Answer:** No. In demos, use `--cacert tls/server.crt` to trust that specific cert. Production uses trusted PKI; never disable hostname/trust validation.

**Question 10.** Does a successful TLS reload automatically swap the certificate on an already-open HTTP/2 connection?

**Answer:** No. TLS handshakes occur at connection establishment; HTTP/2 reuses open connections. Open a fresh handshake to verify the post-reload certificate.

## 15. Official Documentation

- [Spring Boot — SSL bundles, PEM/JKS, reload-on-update, Let's Encrypt](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot — Embedded Web Servers, SSL bundle, SNI, HTTP/2](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot — Common Application Properties: server.ssl.*, spring.ssl.bundle.*](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot 4.0 Migration Guide — Undertow removed](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 7301 — ALPN](https://www.rfc-editor.org/rfc/rfc7301)
- [Let's Encrypt — Certificates](https://letsencrypt.org/docs/)
- [Certbot — Renewing Certificates](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates)
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)

**Key takeaway:** A server certificate is only effective when paired with a **protected private key, valid chain and SAN, unexpired dates, and deployment at the real TLS terminator**. Keep secrets out of source/images; renew from CA/ACME, deploy files consistently, and reload via **SSL bundles on Tomcat or Netty where supported**—or use rolling restarts otherwise. Verify success via **fresh client handshakes with proper SNI** and monitor live endpoints/instances rather than only files on disk.