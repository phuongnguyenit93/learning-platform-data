# Client Authentication and Truststores When Requiring mTLS in Spring Boot

## 1. Context and Objectives

**Mutual TLS (mTLS)** is HTTPS in which **both the server and the client prove their identity with X.509 certificates**. Standard HTTPS requires the client to verify the server's certificate; mTLS adds the requirement that the **server verifies the client's certificate** during the TLS handshake, before the request reaches a Spring MVC Controller.

This lesson belongs to **Spring Boot - web-runtime**, under **TLS and HTTP/2**. Examples are based on **Spring Boot 3.3.x, Java 17+, embedded Tomcat, and Spring MVC**, while also noting differences when the application acts as an outbound HTTP client, runs behind a reverse proxy, or goes through a service mesh. A self-generated CA solely for learning environments is used for hands-on practice; never use demo certificates and passwords in production.

By the end of this lesson, you will be able to:
1. Accurately explain **server keystore**, **server truststore**, **client keystore**, and **client truststore**.
2. Choose **server.ssl.client-auth: need/want/none** appropriately without confusing TLS handshake failures with HTTP 401/403.
3. Configure mTLS via **direct PEM**, **PKCS12/JKS**, or **SSL bundles** without mixing approaches.
4. Generate a CA, server certificate, and client certificate, distinguishing **SAN**, **EKU**, chain, CA, and private key.
5. Run a Spring Boot HTTPS server requiring a client certificate, and test both success and failure cases with **curl/OpenSSL**.
6. Send a client certificate from another Spring Boot application using **RestClientSsl**.
7. Understand the roles of Spring Security, proxies/ingress, SSL bundle rotation, and HTTP/2 ALPN.
8. Build a test checklist covering valid certificates as well as missing client certificates, wrong CAs, wrong hostnames, and expired certificates.

## 2. Where Does mTLS Happen in the Request Lifecycle?

### 2.1. One-Way HTTPS

~~~text
Client                                      HTTPS server
   |                                             |
   | --------- TLS ClientHello ----------------> |
   | <-------- Server certificate -------------- |
   |                                             |
   | Verify CA chain, SAN/hostname, validity     |
   | and trust policies                          |
   |                                             |
   | ===== TLS connection accepted =====         |
   | GET /api/ping                               |
   | ------------------------------------------> |
   | <--------------- HTTP response ------------ |
~~~

The server does not necessarily know the client's identity after one-way HTTPS. If an API requires authentication, it normally relies on a bearer token, session, API key, OAuth2, or another application-layer mechanism.

### 2.2. Mutual TLS

~~~text
Client / Service A                          Server / Service B
    |                                               |
    | ------------ TLS ClientHello ----------------> |
    | <---- Server cert + CertificateRequest --------|
    |                                               |
    | A verifies server cert, hostname, CA          |
    | A sends client cert & proof of private key    |
    | ---------------------------------------------> |
    |                                               |
    |               B verifies client cert/chain/CA  |
    |                                               |
    | ==== Handshake succeeds if mutually trusted == |
    | GET /api/ping                                 |
    | ---------------------------------------------> |
    | <---------------- HTTP response -------------- |
~~~

This diagram illustrates conceptual logic, not the exact message order of TLS 1.2 and TLS 1.3. Certificate validation steps occur at the **TLS layer**. If the client has no certificate while the connector enforces **client-auth: need**, the request is normally rejected **before DispatcherServlet**. Therefore, a **@ControllerAdvice** cannot turn a TLS handshake error into an HTTP 401 JSON response from a controller.

**The TLS layer and application layer answer two different questions:**

- **TLS client authentication:** does the client hold the private key matching a certificate issued by a trust anchor the server accepts?
- **Authorization:** does the authenticated service/user have permission to perform the operation on the resource?

A client that passes mTLS **does not automatically get admin permissions**. The server still needs to map the certificate identity to a principal and enforce role/scope/tenant authorization.

## 3. Keystore, Truststore, and Two-Way Trust

### 3.1. Role Matrix

| Material | Used by | Contents | Purpose |
| --- | --- | --- | --- |
| **Server keystore** | Spring Boot server | Server private key + server leaf certificate/chain | Proves the server's identity. |
| **Server truststore** | Spring Boot server | Trusted client CAs/CA chains or pinned certificates | Verifies certificates sent by clients. |
| **Client keystore** | HTTP client | Client private key + client leaf certificate/chain | Proves the client's identity. |
| **Client truststore** | HTTP client | CA that issued server cert or trusted server certificate | Verifies the server alongside hostname verification. |

**Keystore = the owner's own identity; truststore = the identities/CAs that party trusts.** A keystore holds a private key that must be protected, whereas a truststore typically holds public certificates. A **.crt** file usually does not contain a private key; a **.key** file must be kept secret. A **.p12** file can hold a private key, certificate, and certificate chain depending on how it was created.

A common setup:

~~~text
CA issues server.crt               CA issues client.crt
       |                                  |
server.crt + server.key          client.crt + client.key
       |                                  |
server keystore                  client keystore

server truststore  ---- trusts CA that issued ----> client.crt
client truststore  ---- trusts CA that issued ----> server.crt
~~~

In a lab, you can use the **same CA** to issue both certificates for convenience. Production can use **separate CAs for server identity and client identity**, avoiding unnecessary expansion of trust scope.

### 3.2. Certificate Chain

~~~text
Trusted Root CA (present in truststore)
      |
      +-- Intermediate CA
              |
              +-- Leaf certificate (client or server)
~~~

The party presenting a certificate normally sends the leaf and required intermediates. The peer verifies the chain back to a trust anchor in its truststore; you may see **PKIX path building failed**, **unknown_ca**, or **unable to get local issuer** if a suitable CA/chain is missing.

You do not necessarily have to import **every individual leaf** into the truststore. Trusting the CA makes rotating leaf certificates easier, though if that CA issues certificates to many workloads, **all of those workloads will pass chain validation**. Therefore, mTLS must be paired with strict certificate issuance policies and proper authorization.

### 3.3. X.509 Fields to Inspect

- **Not Before / Not After:** validity window; expired or not-yet-valid certs must be rejected.
- **SAN (Subject Alternative Name):** server certificates need DNS SANs/IP SANs matching the hostname/IP the client actually accesses. Relying solely on **CN** is no longer an acceptable way to verify server names.
- **EKU (Extended Key Usage):** server leaf certs may require **serverAuth**, client leaf certs require **clientAuth**; the wrong EKU can cause TLS verification to fail.
- **Key Usage:** leaf/CA must have appropriate usages (`digitalSignature`, `keyCertSign`, etc.).
- **Basic Constraints:** CA certificates must have `CA:TRUE`; leaf certs normally have `CA:FALSE`.
- **Issuer, Subject, serial, public key:** assist with identity mapping and policy enforcement.
- **Revocation:** a truststore holding a CA does not prove CRL/OCSP/revocation checking is enforced; explicit policy is required.

A certificate that is valid by chain alone is not enough to decide whether the caller may invoke every API.

## 4. server.ssl.client-auth: none, want, need

| Setting | Behavior |
| --- | --- |
| **none** | Does not request a client certificate; one-way HTTPS. |
| **want** | The server **requests** the client present a certificate but **does not require** it. Clients without a cert can still connect. |
| **need** | **Requires** a client certificate; missing or untrusted certificates normally fail the TLS handshake. |

In Spring Boot 3.3, the main property is **server.ssl.client-auth**. When an API requires mTLS on **every request** through the embedded HTTPS connector, the right choice is usually:

~~~yaml
server:
  ssl:
    client-auth: need
~~~

This setting alone **is not enough**. The server must also have a **server private key + server certificate**, plus **trust material** to verify clients. Spring Boot notes that client authentication requires a trust store.

**Do not confuse want with need.** `want` fits a transition period supporting clients both with and without certificates or complex app-level policies; if you claim "this connector only allows clients with certs" while setting `want`, the policy is not enforced.

Do not assume **client-auth: need** automatically creates an identity in Spring Security. It operates at the connector level; security filters/controllers still need to know which workload the client identity maps to and what permissions it holds.

## 5. Lab: Generating a CA, Server Cert, and Client Cert with OpenSSL

The commands below use **OpenSSL 1.1.1+ or 3.x** on Linux/macOS/Git Bash/WSL. In PowerShell, replace here-document file creation commands with standard text writing. This is a local lab; never distribute the CA private key.

### 5.1. Create a Directory Protecting Keys

Run from the project root:

~~~bash
mkdir -p tls
umask 077
~~~

**umask 077** on Unix restricts permissions on newly created files. Add **tls/** to **.gitignore**, and do not commit private keys or bake them into Docker images. The CA private key is only for signing certificates and must never be deployed into the running server container.

### 5.2. Create the Lab CA

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out tls/lab-ca.key

openssl req -new -x509 -sha256 -days 3 \
  -key tls/lab-ca.key \
  -out tls/lab-ca.crt \
  -subj "/CN=Study-mTLS-CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
~~~

- **lab-ca.crt:** public certificate of the CA; used to configure trust.
- **lab-ca.key:** secret private key; never place inside the Spring Boot application.
- **3 days:** short lifetime for lab exercises, not a production policy.

### 5.3. Create Server Key, CSR, and Server Certificate with SAN

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out tls/server.key

openssl req -new \
  -key tls/server.key \
  -out tls/server.csr \
  -subj "/CN=localhost"
~~~

Create **tls/server.ext**:

~~~text
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,IP:127.0.0.1
~~~

Sign:

~~~bash
openssl x509 -req -sha256 -days 3 \
  -in tls/server.csr \
  -CA tls/lab-ca.crt \
  -CAkey tls/lab-ca.key \
  -CAcreateserial \
  -out tls/server.crt \
  -extfile tls/server.ext
~~~

The server private key is in **server.key**, and the certificate is in **server.crt**; SAN covers **localhost** and IP **127.0.0.1**. Therefore, when testing hostname mismatch, choose a hostname other than those two values.

### 5.4. Create Client Certificate with EKU clientAuth

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out tls/client.key

openssl req -new \
  -key tls/client.key \
  -out tls/client.csr \
  -subj "/CN=demo-client"
~~~

Create **tls/client.ext**:

~~~text
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=clientAuth
~~~

Sign:

~~~bash
openssl x509 -req -sha256 -days 3 \
  -in tls/client.csr \
  -CA tls/lab-ca.crt \
  -CAkey tls/lab-ca.key \
  -CAcreateserial \
  -out tls/client.crt \
  -extfile tls/client.ext
~~~

**client.crt + client.key** form the client identity. The server only needs to know the CA to verify the client and never needs **client.key**. Sharing a single lab CA does not mean production should hand out the same client certificate to multiple services.

### 5.5. Verify Purposes and Hostname

~~~bash
openssl x509 -in tls/server.crt -noout -text
openssl x509 -in tls/client.crt -noout -text

openssl verify -CAfile tls/lab-ca.crt \
  -purpose sslserver -verify_hostname localhost tls/server.crt

openssl verify -CAfile tls/lab-ca.crt \
  -purpose sslclient tls/client.crt
~~~

Normally both verify commands will output **tls/server.crt: OK** and **tls/client.crt: OK**. Exact output depends on your OpenSSL version. Inspect **SAN**, EKU, Issuer, and validity, and never print private keys to logs.

## 6. Spring Boot Demo: Direct PEM Configuration Requiring Client Certificates

### 6.1. Project

Initialize a Spring Boot Maven project with:
- Java 17, group **com.example**, artifact **mtls-server-demo**.
- Package **com.example.mtlsserver**.
- Dependencies **Spring Web** and **Spring Boot Starter Test**.
- Embedded Tomcat from `spring-boot-starter-web`.

File tree:

~~~text
mtls-server-demo/
  pom.xml
  mvnw
  mvnw.cmd
  tls/
    lab-ca.crt
    lab-ca.key
    server.crt
    server.key
    client.crt
    client.key
  src/main/java/com/example/mtlsserver/
    MtlsServerApplication.java
    SecurePingController.java
  src/main/resources/
    application.yml
~~~

**tls/** inside the project is for the demo only. When deploying, **mount certificates/private keys outside the JAR** with least-privilege permissions, and never keep the root CA private key on the application server.

### 6.2. Complete pom.xml

~~~xml
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
    <artifactId>mtls-server-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

The version is pinned to demonstrate Spring Boot 3.3 APIs; real projects should use a maintained version with security updates and avoid pinning Tomcat/SSL dependencies separately from the BOM arbitrarily.

### 6.3. Main Class

**src/main/java/com/example/mtlsserver/MtlsServerApplication.java**

~~~java
package com.example.mtlsserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MtlsServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(MtlsServerApplication.class, args);
    }
}
~~~

### 6.4. application.yml Using Direct PEM

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: mtls-server-demo

server:
  port: 8443
  ssl:
    enabled: true
    certificate: "file:./tls/server.crt"
    certificate-private-key: "file:./tls/server.key"
    trust-certificate: "file:./tls/lab-ca.crt"
    client-auth: need
~~~

Meaning:

- **certificate** and **certificate-private-key** form the **server identity**.
- **trust-certificate** is the CA the server uses to verify **client certs**.
- **client-auth: need** mandates a client certificate on the inbound HTTPS connector.
- **file:./tls** depends on the working directory. Run commands from the project root so paths resolve properly.
- Port **8443** is HTTPS; the application does not automatically open HTTP 8080 or an HTTP→HTTPS redirect.

**Note:** If the certificate chain includes intermediates, provide the complete chain as required by the server/container. The demo CA signs the leaf directly, so there is no intermediate. In production, verify the chain carefully and do not copy only the leaf without its issuer.

### 6.5. Controller Inspecting the Client Certificate

**src/main/java/com/example/mtlsserver/SecurePingController.java**

~~~java
package com.example.mtlsserver;

import java.security.cert.X509Certificate;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class SecurePingController {
    @GetMapping("/ping")
    public Map<String, String> ping(HttpServletRequest request) {
        Object raw = request.getAttribute(
                "jakarta.servlet.request.X509Certificate");

        if (!(raw instanceof X509Certificate[] certs)
                || certs.length == 0) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "A client certificate is required");
        }

        X509Certificate leaf = certs[0];
        return Map.of(
                "status", "ok",
                "clientSubject",
                leaf.getSubjectX500Principal().getName());
    }
}
~~~

**Jakarta Servlet 6.0** defines the **jakarta.servlet.request.X509Certificate** attribute as an array **java.security.cert.X509Certificate[]** when an HTTPS request carries a client certificate. The first element is the client's leaf certificate. The controller exposes **clientSubject** for lab observation; it does not enforce production role/permission checks.

With **client-auth: need**, Tomcat has already validated the certificate at the TLS layer before the request reaches the controller. Without a cert, you will normally **not receive an HTTP 401 from this method**; the handshake fails. The 401 branch is a defensive guard if routing changes or the cert attribute is missing.

**Never use Subject CN as the sole production identity.** A CA can issue multiple leaves with matching Subjects, or a Subject can change upon rotation. Use controlled certificate issuance profiles, SAN/URI workload IDs, issuer/serial/allowlists, and appropriate Spring Security authorization.

### 6.6. Run

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/mtls-server-demo-0.0.1-SNAPSHOT.jar
~~~

Windows CMD/PowerShell:

~~~text
mvnw.cmd clean package
java -jar target/mtls-server-demo-0.0.1-SNAPSHOT.jar
~~~

Run from the project root containing **tls/**. If the wrapper is absent, use a preinstalled Maven with **mvn clean package**. The HTTPS server will listen on **8443** as configured.

## 7. Positive and Negative Tests with curl

### 7.1. Success Case

~~~bash
curl -i \
  --cacert tls/lab-ca.crt \
  --cert tls/client.crt \
  --key tls/client.key \
  https://localhost:8443/api/ping
~~~

- **--cacert**: used by the client to **trust and verify the server**.
- **--cert, --key**: client presents its certificate/private key for server verification.
- The URL uses **localhost**, matching the DNS SAN in the server certificate.

Expect **HTTP 200** and a JSON body containing:

~~~json
{"status":"ok","clientSubject":"CN=demo-client"}
~~~

**The ordering of the two JSON keys is not guaranteed** because `Map.of` is used. Status 200 and the two values are what matter.

### 7.2. Missing Client Cert

~~~bash
curl -v --cacert tls/lab-ca.crt \
  https://localhost:8443/api/ping
~~~

When **need** is enforced, the handshake normally fails because the client presents no certificate. Specific errors may be **tlsv13 alert certificate required**, **bad certificate**, or different curl error codes depending on TLS version/SSL backend. **Do not assume you must get HTTP 403**: no HTTP request may even take place.

### 7.3. Client Does Not Trust Server CA

~~~bash
curl -v \
  --cert tls/client.crt \
  --key tls/client.key \
  https://localhost:8443/api/ping
~~~

If the lab CA is not in curl's default system trust store, the connection normally fails while the **client verifies the server certificate**. The right fix is adding **--cacert tls/lab-ca.crt**; **do not use --insecure/-k** in production.

### 7.4. Server Does Not Trust Client CA

Create a different CA, issue a new client leaf, and test with the new **--cert/--key** while the server still only trusts `lab-ca`. The server must reject the certificate from the untrusted CA. That is a **server truststore** failure, distinct from omitting **--cacert** on the client.

### 7.5. Verifying the Handshake with OpenSSL

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile tls/lab-ca.crt \
  -cert tls/client.crt \
  -key tls/client.key \
  -verify_return_error
~~~

Inspect the server chain, TLS version, cipher suite, and verify status. Getting **Verify return code: 0 (ok)** indicates certificate verification passed according to OpenSSL's checks, **not application authorization**. Use curl to verify HTTP status/body.

### 7.6. Testing Hostname Mismatch

The sample server cert has SAN **DNS:localhost, IP:127.0.0.1**. To test hostname mismatch, access via another DNS name pointing to the server that is **not** in the SAN; do not use `127.0.0.1` for this test since that IP is permitted. Compliant clients will reject the mismatched name even when the CA is trusted.

### 7.7. Acceptance Matrix

| Test | Condition | Expected result |
| --- | --- | --- |
| Valid CA and client cert | Trust server + present valid client cert | TLS pass, HTTP 200. |
| Missing client cert | Only --cacert | TLS fail with `need`. |
| Client cert from unknown CA | Issuer absent from server truststore | TLS fail. |
| Server CA unknown | Issuer absent from client truststore | Client rejects server. |
| Wrong hostname | Target DNS/IP missing from SAN | Client rejects server. |
| Expired client cert | Past Not After | Validation fail. |
| Wrong EKU | Using serverAuth cert as client | May be rejected by validation policy. |
| Valid cert without permissions | Client passes TLS, app denies | HTTP 403 per policy. |
| Bypass gateway | Calling backend directly around mTLS proxy | Must be blocked by network/auth policy. |

**Important point:** Seeing HTTP 200 alone does not prove mTLS is **enforced**; you must test **without presenting a certificate** to catch `want`/`none` misconfigurations or misplaced TLS termination.

## 8. Alternative: PKCS12/JKS Keystore and Truststore

Spring Boot supports key/trust material via Java KeyStore. This is an **alternative** to direct PEM in section 6, not an additional simultaneous config.

### 8.1. Create PKCS12 Containing Server Key and Certificate

~~~bash
openssl pkcs12 -export \
  -name mtls-server \
  -inkey tls/server.key \
  -in tls/server.crt \
  -certfile tls/lab-ca.crt \
  -out tls/server.p12 \
  -passout pass:changeit
~~~

**server.p12** holds the private key and must be protected just like **server.key**. The password **changeit** is for lab use only; production uses a secret manager and never hardcodes it in Git or logs.

### 8.2. Create a Truststore for the Client CA

~~~bash
keytool -importcert -noprompt \
  -alias lab-client-ca \
  -file tls/lab-ca.crt \
  -keystore tls/server-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit

keytool -list -v \
  -keystore tls/server-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

The truststore holds **trusted CA certificates**; it does not contain **client private keys**. Set appropriate file permissions. When rotating CAs or leaves, choose trust policies appropriate for the number of workloads issued certs.

### 8.3. Configure server.ssl with PKCS12

Replace the entire SSL block in `application.yml`:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:./tls/server.p12"
    key-store-type: PKCS12
    key-store-password: changeit
    key-alias: mtls-server
    trust-store: "file:./tls/server-trust.p12"
    trust-store-type: PKCS12
    trust-store-password: changeit
    client-auth: need
~~~

**key-store** holds the server identity; **trust-store** holds the CA verifying clients. If you hit **Cannot recover key**, **Keystore was tampered with**, or **alias not found**, verify password, type, `PrivateKeyEntry`, key alias, and file path. If the private key password differs from the store password, configure it accordingly.

## 9. Alternative: Spring Boot 3.3 SSL Bundles

An SSL bundle is a named set of identity/trust material, convenient when one application acts as both a server and an outbound HTTP client. Spring Boot supports **spring.ssl.bundle.pem** and **spring.ssl.bundle.jks**; named bundles are applied to the web server via **server.ssl.bundle**.

### 9.1. PEM Bundle for an Inbound Server

Replace the direct PEM configuration with:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inbound-mtls:
          keystore:
            certificate: "file:./tls/server.crt"
            private-key: "file:./tls/server.key"
          truststore:
            certificate: "file:./tls/lab-ca.crt"

server:
  port: 8443
  ssl:
    bundle: inbound-mtls
    client-auth: need
~~~

**The bundle's keystore** holds the server identity; **the bundle's truststore** is the client CA trusted by the server; **server.ssl.client-auth** must still be set to **need** if all clients must present certificates.

**Do not mix server.ssl.bundle with discrete properties like server.ssl.key-store, server.ssl.certificate, or trust-certificate**. Spring Boot 3.3 documentation notes the two cannot be used together. When using a bundle, protocol/cipher settings have their own options inside the bundle; do not assume all direct properties still take effect.

### 9.2. JKS/PKCS12 Bundle

Using the `.p12` files from section 8:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        inbound-mtls:
          key:
            alias: mtls-server
          keystore:
            location: "file:./tls/server.p12"
            password: changeit
            type: PKCS12
          truststore:
            location: "file:./tls/server-trust.p12"
            password: changeit
            type: PKCS12

server:
  port: 8443
  ssl:
    bundle: inbound-mtls
    client-auth: need
~~~

This is a **separate alternative**. Do not register both a PEM bundle and a JKS bundle under the same name and guess which wins.

### 9.3. SSL Bundles Are Not a CA Service

SSL bundles manage loading key/truststores and creating `SSLContext`/`KeyManager`/`TrustManager`. They **do not issue, renew, revoke, authorize roles, or block spoofed headers**. Pair them with PKI, secret management, and security filters.

Spring Boot includes **reload-on-update** for PEM bundles and compatible consumers—Tomcat and Netty per documentation; do not assume every outbound client or existing live connection reloads immediately. Test rotation against your actual implementation.

## 10. When Spring Boot Is an HTTP Client Calling an mTLS Service

**server.ssl.\*** primarily configures the **inbound connector**. If Spring Boot service A calls service B over mTLS HTTPS, **A's RestClient/WebClient does not automatically use the server SSL identity**. A needs its own **client keystore** and a **truststore** to verify B.

### 10.1. Outbound SSL Bundle

In the downstream-calling application's configuration:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        partner-outbound:
          keystore:
            certificate: "file:./tls/client.crt"
            private-key: "file:./tls/client.key"
          truststore:
            certificate: "file:./tls/lab-ca.crt"
~~~

Here **keystore** is the client cert/key presented to service B; **truststore** is the CA verifying server B. In real systems, those two CAs may differ.

### 10.2. RestClientSsl in Spring Boot 3.3

Complete example class for a Spring Boot 3.3 + Spring Web project **that already configured the partner-outbound bundle**:

~~~java
package com.example.mtlsserver;

import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerClient {
    private final RestClient client;

    public PartnerClient(RestClient.Builder builder,
                         RestClientSsl ssl) {
        this.client = builder
                .baseUrl("https://localhost:8443")
                .apply(ssl.fromBundle("partner-outbound"))
                .build();
    }

    public String checkPartner() {
        return client.get()
                .uri("/api/ping")
                .retrieve()
                .body(String.class);
    }
}
~~~

This class **compiles** in the project above, though it will not make an outbound call unless other code invokes **checkPartner()**. Calling the local server as downstream is for practice only. Spring Boot **3.3** provides **RestClientSsl** in package **org.springframework.boot.autoconfigure.web.client**; check package names in other major versions.

Spring Boot also offers **SslBundles** and **SslBundle.createSslContext()** when configuring an `SSLContext` for other libraries. However, when built-in `RestClient`/`WebClient` integrations exist, prefer the framework API rather than writing ad-hoc `TrustManager` implementations.

**Never create a "trust-all" TrustManager** or an always-true `HostnameVerifier` to silence certificate errors. Fix the truststore, chain, SAN, and certificate profile.

## 11. Authentication and Authorization After Passing mTLS

### 11.1. "Trusted CA" Does Not Mean "Authorized Client"

If one CA issues client certs to both **service-a** and **service-b**, both pass TLS if the server only verifies the chain up to that CA. Yet `service-a` might be allowed to read data while `service-b` must not delete data. The server still must enforce specific authorization:

~~~text
TLS handshake:
    client presents certificate
       -> validate signature, chain, validity, usage, trust CA
       -> connection accepted
                      |
                      v
Application security:
    verified certificate -> service principal
       -> lookup identity/roles/tenant
       -> authorize route and resource
       -> permit (2xx) or deny (403)
~~~

In production, use **Spring Security X.509 authentication** or a well-designed identity-mapping layer combined with **UserDetailsService**, custom authentication, and appropriate policies. Never automatically grant ADMIN simply because Subject CN equals a string not strictly governed by the issuer.

### 11.2. Better Identity Extraction Than CN

Options include **URI SAN** workload identities, SPIFFE IDs, service-specific DNS SANs, fingerprint/serial+issuer bindings, or CA-issued profile identities. Verify that issuance policies prevent duplicate identities and handle changes across revocation/rotation. Bind permissions to normalized, audited principals.

### 11.3. HTTP Status Does Not Replace TLS Alerts

- **TLS handshake failure:** no HTTP request completes; curl/OpenSSL typically report a TLS error.
- **401 Unauthorized:** the connection passed TLS, but application authentication is missing/invalid.
- **403 Forbidden:** the application identified the principal, but denied permission.
- **200 OK:** the application succeeded; **does not prove mTLS is required** unless negative tests are also run.

Do not write `@ControllerAdvice` expecting to catch embedded Tomcat handshake failures like ordinary controller exceptions.

## 12. Reverse Proxies, API Gateways, Ingress, and Service Meshes

### 12.1. Spring Boot Terminates TLS Directly

~~~text
Client -- mTLS --> Spring Boot embedded Tomcat
                     server.ssl.client-auth=need
                               |
                               v
                            Controller
~~~

In this setup, `server.ssl` settings directly control the TLS connector receiving requests.

### 12.2. TLS Terminates at Ingress

~~~text
Client -- mTLS --> Ingress/API Gateway -- HTTP/TLS --> Spring Boot
                          |
                          +-- verify client certificate
                          +-- map verified service identity
                          +-- forward trusted identity context
~~~

When HTTPS/mTLS **terminates at a proxy**, Spring Boot **does not directly verify the original client certificate**. Enabling **server.ssl.client-auth=need** on the backend only affects the backend's own TLS connector (if the backend receives TLS), and does not protect **client→ingress**. To enforce mTLS at the edge, configure the ingress/gateway.

### 12.3. Certificate Headers Can Be Spoofed

Headers such as **X-Forwarded-Client-Cert** or **X-SSL-Client-Cert** are **plain text sent by a hop**, not cryptographic proof that the peer completed mTLS. The gateway must **strip/overwrite headers from external clients**, forwarding identity only after verifying the certificate over a protected backend connection. The backend should not be directly reachable from public networks to bypass the gateway. Where high assurance is needed, use signed/authenticated identity assertions, network policies, or an additional mTLS hop between gateway and backend.

### 12.4. Service Mesh

A service mesh can enforce mTLS at sidecars/proxies and propagate workload identity. The Spring Boot app still needs resource-level authorization and clarity on **whether the actual TLS peer is the sidecar or the original client**. Avoid layering redundant mTLS settings blindly just because property names look similar without checking topology.

### 12.5. Actuator/Management Port

If the management server uses a separate port, it can have separate **management.server.ssl** settings. Do not assume TLS/mTLS on the main port automatically applies identically to another listener. Health checks, management routes, and service-to-service ingress must be segmented by network policies and real authentication.

## 13. mTLS and HTTP/2

mTLS provides **authentication and encryption at the TLS layer**; HTTP/2 is the HTTP protocol normally negotiated via **ALPN** over HTTPS. A connection can pass mTLS and still speak HTTP/1.1; conversely, negotiating `h2` does not prove a client certificate was required.

Enable HTTP/2 in Spring Boot:

~~~yaml
server:
  http2:
    enabled: true
~~~

This is an **additional** setting on a server that already has SSL/mTLS. Java 17 and modern embedded Tomcat support ALPN; client, proxy, protocols/ciphers, and connector determine whether HTTP/2 is selected.

Test:

~~~bash
curl -V
curl --http2 -v \
  --cacert tls/lab-ca.crt \
  --cert tls/client.crt \
  --key tls/client.key \
  https://localhost:8443/api/ping
~~~

**curl -V** shows whether your binary supports HTTP/2. If `h2` is negotiated, verbose/response output normally displays **HTTP/2** and ALPN `h2`. Otherwise, an HTTP/1.1 request can still use mTLS correctly. Do not change CAs/truststores when the actual issue is HTTP/2 negotiation.

With TLS 1.2/TLS 1.3, check enabled protocols/ciphers per Java/container and security policy. When using an SSL bundle, configure options inside the bundle rather than assuming every `server.ssl.ciphers`/protocol override takes effect.

## 14. Rotation, Revocation, and Secret Management

### 14.1. Certificate Lifecycle

A production mTLS system requires:
1. Issuing distinct certs per workload/service; never share one private key across all services.
2. Bounding certificate lifetime, SAN, EKU, CA path, algorithms, and issuance privileges.
3. Storing private keys in a secret manager/HSM/secure mounted secret—never in Git, logs, or JARs.
4. Monitoring `Not After` and alerting before expiration.
5. Scheduling client/server leaf rotation while accounting for connection pooling/keepalive.
6. Having a playbook for CA/trust-root changes and rollback on faulty rollouts.
7. Revoking credentials if a key leaks or a service is decommissioned.
8. Monitoring TLS failures without logging private keys, tokens, or excessive sensitive data.

### 14.2. Changing CAs Without Dropping Traffic

When rotating a root or intermediate CA, the safe approach is normally temporary **trust overlap**:

~~~text
Step 1: distribute the new CA into the verifier's truststore
Step 2: issue and roll out the new leaf certificates
Step 3: confirm all clients/servers use the new chain
Step 4: revoke/remove the old CA on schedule
~~~

Do not remove the old CA while workloads still present old certs; likewise, do not keep overly broad CAs indefinitely out of fear of downtime.

### 14.3. Reloading SSL Bundles

Spring Boot provides **reload-on-update** for PEM bundles and compatible consumers, documented as Tomcat/Netty. However, swapping cert/key files does not guarantee all existing connections immediately switch over: connection pooling, TLS session resumption, file watchers, and individual HTTP clients have distinct behaviors. Test rotation with both new and existing connections; do not assume outbound `RestClient` instances auto-reload merely because a bundle is defined.

### 14.4. Revocation Is Not Automatically Active When Importing a CA

A truststore containing a root CA does not guarantee **CRL/OCSP** or revocation is enforced by policy. In high-security environments, combine short-lived certs, CA services, and appropriate revocation enforcement with application-layer authorization and permission revocation.

## 15. Layer-by-Layer Troubleshooting

| Symptom | Suspected layer | Resolution |
| --- | --- | --- |
| **PKIX path building failed** in Java client | Client does not trust server CA/chain | Check outbound truststore, issuer/intermediate, chain. |
| **unable to get local issuer certificate** in curl | Missing `--cacert` or incomplete server chain | Supply right CA, do not use `-k`. |
| **certificate required / bad certificate** | Server requires mTLS, client missing/bad cert | Provide valid client cert/key, check `client-auth: need`. |
| **unknown_ca** on server | Server does not trust client's CA | Fix server truststore, chain, CA scope. |
| **No subject alternative DNS name** | Wrong hostname/SAN | Reissue server cert with right SAN; do not disable verify. |
| **certificate expired / not yet valid** | Validity dates or clock skew | Rotate cert, synchronize clocks. |
| **unsupported_certificate / wrong EKU** | Client cert has wrong usage | Use certificate with `clientAuth` and proper profile. |
| **Keystore password incorrect** | Wrong store/key password | Check PKCS12 type, secret, file path. |
| **Cannot recover key / alias not found** | Wrong `PrivateKeyEntry`/alias | `keytool -list -v`, verify key alias. |
| **HTTP 401 after TLS passes** | Principal not mapped in application | Check Spring Security / verified cert attribute. |
| **HTTP 403 after TLS passes** | Principal lacks permission | Check scope, role, tenant authorization. |
| **Client without cert still gets 200** | `want`/`none` or proxy terminates TLS | Test actual connection path and `client-auth` policy. |
| **HTTP/2 not used** | ALPN/client/proxy/HTTP/2 config | Check `curl -V`, `--http2`, inspect protocol negotiation. |
| **Passes locally, fails on deploy** | Different key/secret path, trust CA, SAN/proxy | Compare artifact, runtime paths, listener, and CA chain. |

**Ordered debugging approach:** first determine **where TLS terminates**; then inspect server identity, client identity, both sides' trust material, SAN/EKU/validity, and `client-auth` mode; finally check Spring MVC/Spring Security authorization. Never blindly tweak HTTP controllers when requests never get past TLS.

In dev environments, you can enable JVM TLS debugging:

~~~bash
java -Djavax.net.debug=ssl,handshake \
  -jar target/mtls-server-demo-0.0.1-SNAPSHOT.jar
~~~

Logs can expose highly detailed certificate and handshake info; enable temporarily only and avoid leaking output into public logging systems.

## 16. Which Tests Truly Prove mTLS?

**MockMvc** tests controller/security logic using mock Servlet requests and **does not perform a real TLS handshake**. It can test how the app maps a verified cert/role when you mock attributes/principals, but it **cannot prove `server.ssl.client-auth=need`, truststores, CA chains, or hostname verification**.

To validate mTLS properly, run **HTTP integration tests against a real embedded HTTPS server**, or run the packaged JAR and test with curl/OpenSSL. Do not test only the positive 200 path; include no-cert, wrong-CA, wrong-hostname, and authorization-deny tests.

Essential lifecycle test coverage:

- **Build:** `application.yml` loads the right profile; key/cert files are readable yet excluded from public artifacts.
- **Handshake positive:** valid client cert/key and server CA trust → TLS passes.
- **Handshake negative:** missing client cert or wrong CA → TLS fails under `need`.
- **Hostname negative:** server SAN mismatch → client verification fails.
- **Expiry/rotation:** old and new certs transition smoothly; revoked certs are rejected.
- **HTTP policy:** valid cert whose principal lacks permission gets 403.
- **Proxy:** backend cannot be bypassed, and identity headers cannot be spoofed.
- **HTTP/2:** ALPN verified separately, not conflated with client authentication.

## 17. Anti-Patterns to Avoid

**1. Trust-all SSLContext or `curl --insecure` to "fix" cert errors.** Disables peer/hostname verification and opens MITM risk. Fix the CA/chain/SAN properly.

**2. Deploying `lab-ca.key` onto the server.** The CA private key is only for issuing certificates; if leaked, attackers can mint spoofed certificates trusted by peers.

**3. Sharing one client key across multiple services.** Makes per-workload auditing, rotation, and revocation hard, with a huge blast radius.

**4. Trusting all public CAs for `clientAuth`.** An overly broad truststore lets too many clients pass TLS; scope the client CA tightly and enforce app authorization.

**5. Setting `client-auth: want` while claiming all requests are mTLS-protected.** Clients without certificates can still reach the application.

**6. Granting admin rights to any cert with a specific Subject CN.** Subjects can collide, be misissued, or lack binding to principal policies. Use verified identity mapping and RBAC/ABAC.

**7. Letting the Internet send `X-Forwarded-Client-Cert` directly.** Headers not protected by the gateway can be spoofed and never replace a TLS handshake.

**8. Ignoring outbound client settings.** `server.ssl` controls inbound traffic; apps calling partner mTLS APIs need separate HTTP client certificate/trust configuration.

**9. Confusing TLS failures with HTTP 401/403.** When a handshake fails, `@ControllerAdvice` typically cannot return ordinary JSON responses.

## 18. Practice Exercises

### Exercise 1 — Need vs. Want

Run the same server setup, changing only **client-auth: need** to **want** in your lab; test with curl both with and without a client certificate. Explain why `want` does not guarantee blocking certless clients at the connector, even if one specific controller manually checks the attribute.

### Exercise 2 — Two Independent Truststores

Run 1: send a valid client cert without passing the server CA to curl. Run 2: pass the valid server CA while sending a client cert from an unknown CA. Explain which side rejects the connection and why.

### Exercise 3 — SAN and EKU

Issue a server cert missing the `localhost` SAN and observe the hostname error; issue a client cert with only EKU `serverAuth` and test it as a client. Do not use `curl -k` or disable verification to make it pass.

### Exercise 4 — Spring Boot Outbound

Configure the **partner-outbound** SSL bundle and create `PartnerClient`. Test first without the keystore (truststore only), then add the client certificate/private key. Explain why `server.ssl.client-auth` does not make `RestClient` present a certificate automatically.

### Exercise 5 — Reverse Proxy

Diagram an mTLS ingress + HTTP Spring Boot backend. Show where certificates are verified, how trusted identity is forwarded, and how external callers are blocked from spoofing headers or bypassing the gateway.

## 19. Pre-Deployment Checklist

- [ ] You know whether **TLS terminates at the embedded server, proxy, or service mesh**.
- [ ] Connectors requiring strict mTLS have **client-auth: need**.
- [ ] Server has valid certificate/private key, SAN matching hostname, and EKU `serverAuth`.
- [ ] Server has a truststore for the **client CA**, not confused with the server keystore.
- [ ] Client has its own certificate/private key and truststore for the **server CA**.
- [ ] Certificate chain, issuer/intermediate, validity, EKU, and Key Usage are all accurate.
- [ ] Picked one of **direct PEM**, **direct PKCS12**, or **SSL bundle** without mixing.
- [ ] No private keys in Git/JAR/logs; secret management and file permissions enforced.
- [ ] Certificate trust leads to identity mapping and **authorization**, never automatic full access.
- [ ] No trust-all, `-k`, or disabled hostname verification.
- [ ] Rotation/revocation/expiry alerts and CA-change playbooks are in place.
- [ ] Negative tests for no-cert, wrong-CA, and hostname mismatch run against a real TLS runtime.
- [ ] Outbound `RestClient`/`WebClient` has dedicated SSL config when calling mTLS APIs.
- [ ] Proxy/header trust boundaries and bypass prevention are tested.
- [ ] HTTP/2 and ALPN verified separately if `h2` is required.
- [ ] Management/Actuator port is secured per policy.

## 20. Self-Check Questions

**1. How do keystore and truststore differ?** Keystore holds the owner's identity/private key; truststore holds CAs/certs that party accepts when verifying peers.

**2. Whom does `server.ssl.trust-store` on a Spring Boot server normally trust in mTLS?** Certificates sent by **clients** to the server—not for holding the server's own private key.

**3. Does `client-auth=want` make client certificates mandatory?** No. **Need** makes them mandatory at the connector.

**4. If no client cert is sent under `need`, do you get HTTP 401?** Normally no: the handshake fails before the controller. HTTP 401/403 belong to application authentication/authorization after TLS.

**5. If a valid client cert is sent while the client lacks the server CA, will it succeed?** The client can still reject the server certificate. Trust must be valid in both directions.

**6. Does having a CA-trusted client cert grant access to every endpoint?** No. Identity mapping and authorization are still required.

**7. Can `server.ssl.bundle` be used alongside `server.ssl.certificate`/keystore?** No, per Spring Boot configuration rules; pick one way to declare SSL key/trust material.

**8. Does `server.ssl` config make `RestClient` automatically send a cert?** No. Outbound clients need their own SSL bundle/`SSLContext`.

**9. Does HTTP/2 eliminate the need for a truststore?** No. ALPN negotiates the HTTP protocol; mTLS certificate validation happens in TLS.

**10. When TLS terminates at the ingress, who verifies the client cert?** The ingress/gateway; the backend only trusts the forwarded verified identity if the assertion path is secured.

## 21. Official Documentation

- [Spring Boot 3.3 — SSL and SSL Bundles](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html): PEM/JKS bundles, keystore, truststore, reload semantics.
- [Spring Boot 3.3 — Embedded Web Servers / Configure SSL](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): discrete `server.ssl` properties, bundles, and HTTPS connectors.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.ssl.client-auth`, `key-store`, `trust-store`, HTTP/2.
- [Spring Boot 3.3 — RestClientSsl Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html): `RestClient` + SSL bundle.
- [Jakarta Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/jakarta-servlet-spec-6.0.html): `X509Certificate` request attribute.
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): certificate authentication and principal mapping.
- [OpenSSL Verification Options](https://docs.openssl.org/3.0/man1/openssl-verification-options/): certificate purpose, hostname, and chain verification.

**Summary:** mTLS requires **each side to have its own certificate/private key and a set of trusted CAs/certificates to verify the other side**. For a Spring Boot server terminating TLS directly, you need **server identity + client trust material + `server.ssl.client-auth=need`**; for a Spring Boot HTTP client, you need independent outbound SSL config. Verify both successful and failed handshakes while enforcing authorization at the application layer; **HTTP 200 alone does not prove the system enforces mTLS**.